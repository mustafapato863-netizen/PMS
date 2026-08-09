"""Cleaner for the Pre-Approvals IP Elective Dubai employee sheet.

The workbook contains two possible approval workstreams in one sheet.  The
current workbook stores the turnaround count in one combined column and uses
the pair of target columns to identify the applicable SLA.  A row is assigned
from exactly one source signal; ambiguous, incomplete, or unsupported target
pairs fail explicitly so that scoring never silently uses the wrong SLA.
"""

from __future__ import annotations

import io
import logging
import re
from typing import Iterable

import pandas as pd

from cleaned import clean_sheet_data


logger = logging.getLogger(__name__)

SHEET_NAME = "Pre-Approvals IP Elective Dubai"
IP_ELECTIVE = "IP Elective"
ER_IP_APPROVAL = "ER / IP Approval"

EXCLUDED_VALUES = {"-", "leave", "new staff"}
TURNAROUND_48_TARGET = 0.75
TURNAROUND_1_5_TARGET = 1.0
IP_REJECTION_TARGET = 0.03
ER_REJECTION_TARGET = 0.01

# The rejection target has changed over the historical months in the supplied
# workbook, so it is not safe to classify a row from the turnaround target
# alone.  These are the observed, approved target pairs: the first value is
# ``T.Initial Rejection %`` and the second is
# ``T.% Of Approval within 48 HR/1.5 HR``.
TARGET_PAIR_WORKSTREAMS = {
    (0.03, 0.75): IP_ELECTIVE,
    (0.06, 0.75): IP_ELECTIVE,
    (0.01, 1.0): ER_IP_APPROVAL,
    (0.03, 1.0): ER_IP_APPROVAL,
}


def _numbers(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric series while treating missing/NA markers as missing."""
    if column not in frame.columns:
        return pd.Series(float("nan"), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _first_column(frame: pd.DataFrame, *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in frame.columns), None)


def _read_sheet(file_source, header: int) -> pd.DataFrame:
    source = io.BytesIO(file_source) if isinstance(file_source, (bytes, bytearray)) else file_source
    return pd.read_excel(source, sheet_name=SHEET_NAME, header=header)


def _has_employee_identifiers(frame: pd.DataFrame) -> bool:
    normalized = {
        re.sub(r"\s+", "", str(column)).casefold()
        for column in frame.columns
    }
    return {"hrid", "agentname"}.issubset(normalized)


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Calculate a ratio only where the denominator is positive."""
    result = pd.Series(float("nan"), index=denominator.index, dtype="float64")
    valid = numerator.notna() & denominator.notna() & denominator.gt(0)
    result.loc[valid] = numerator.loc[valid] / denominator.loc[valid]
    return result


def _normalised_values(series: pd.Series) -> pd.Series:
    return series.map(
        lambda value: "" if pd.isna(value) else str(value).strip().casefold()
    )


def _excluded_mask(frame: pd.DataFrame) -> pd.Series:
    mask = pd.Series(False, index=frame.index)
    for column in ("Status", "PerformanceGrade"):
        if column in frame.columns:
            mask |= _normalised_values(frame[column]).isin(EXCLUDED_VALUES)
    return mask


def _employee_ids(frame: pd.DataFrame, indexes: Iterable) -> list[str]:
    if "HRID" in frame.columns:
        return [str(value).strip() for value in frame.loc[list(indexes), "HRID"].tolist()]
    return [str(index) for index in indexes]


def _raise_for_invalid_workstream_rows(
    frame: pd.DataFrame,
    has_48_hours: pd.Series,
    has_1_5_hours: pd.Series,
) -> None:
    ambiguous = has_48_hours & has_1_5_hours
    missing = ~has_48_hours & ~has_1_5_hours
    invalid_indexes = frame.index[ambiguous | missing]
    if len(invalid_indexes):
        details = []
        for index in invalid_indexes:
            label = "both turnaround numerators" if ambiguous.loc[index] else "no turnaround numerator"
            details.append(f"{_employee_ids(frame, [index])[0]} ({label})")
        raise ValueError(
            "Cannot determine Pre-Approvals IP Elective Dubai workstream for rows: "
            + ", ".join(details[:10])
        )


def _workstreams_from_target_pair(
    frame: pd.DataFrame,
    rejection_target: pd.Series,
    turnaround_target: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Classify rows from the complete target pair, including revisions."""
    missing = rejection_target.isna() | turnaround_target.isna()
    if missing.any():
        ids = ", ".join(_employee_ids(frame, frame.index[missing])[:10])
        raise ValueError(
            "Both target columns are required to determine the Pre-Approvals "
            f"workstream for employees: {ids}"
        )

    workstreams = pd.Series(index=frame.index, dtype="object")
    unsupported = []
    for index in frame.index:
        pair = (float(rejection_target.loc[index]), float(turnaround_target.loc[index]))
        match = next(
            (
                workstream
                for (known_rejection, known_turnaround), workstream in TARGET_PAIR_WORKSTREAMS.items()
                if abs(pair[0] - known_rejection) <= 1e-9
                and abs(pair[1] - known_turnaround) <= 1e-9
            ),
            None,
        )
        if match is None:
            unsupported.append((index, pair))
        else:
            workstreams.loc[index] = match

    if unsupported:
        details = ", ".join(
            f"{employee_id} (targets={pair!r})"
            for (index, pair), employee_id in zip(
                unsupported,
                _employee_ids(frame, [index for index, _ in unsupported]),
            )
        )
        allowed = ", ".join(repr(pair) for pair in TARGET_PAIR_WORKSTREAMS)
        raise ValueError(
            "Unsupported target pair for Pre-Approvals IP Elective Dubai rows: "
            f"{details}. Allowed pairs: {allowed}"
        )

    return workstreams.eq(IP_ELECTIVE), workstreams.eq(ER_IP_APPROVAL)


def _workstreams_from_combined_source(
    frame: pd.DataFrame,
    combined_count: pd.Series,
    rejection_target: pd.Series,
    turnaround_target: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Validate the combined count and classify it from the target pair."""
    if combined_count.isna().any():
        ids = ", ".join(_employee_ids(frame, frame.index[combined_count.isna()])[:10])
        raise ValueError(f"Approval turnaround count is missing for employees: {ids}")
    return _workstreams_from_target_pair(frame, rejection_target, turnaround_target)


def _require_positive_denominator(
    frame: pd.DataFrame,
    values: pd.Series,
    field_name: str,
    indexes: pd.Index,
) -> None:
    invalid = indexes[values.loc[indexes].isna() | values.loc[indexes].le(0)]
    if len(invalid):
        ids = ", ".join(_employee_ids(frame, invalid)[:10])
        raise ValueError(
            f"Cannot calculate {field_name}; positive denominator is required for employees: {ids}"
        )


def process_preapprovals_ip_elective_dubai(file_source) -> pd.DataFrame:
    """Load, validate, and enrich the combined IP Elective/ER sheet."""
    # The production workbook has a KPI title row above the employee header.
    # Accept a normal row-1 header too, because dry-runs and API callers may
    # provide a normalized sheet without the presentation block.
    frame = _read_sheet(file_source, header=1)
    if not _has_employee_identifiers(frame):
        frame = _read_sheet(file_source, header=0)
    frame = clean_sheet_data(frame.copy(), sheet_name=SHEET_NAME)
    frame.columns = frame.columns.astype(str).str.replace(r"\s+", "", regex=True)

    required_identifiers = {"HRID", "AgentName"}
    missing_identifiers = sorted(required_identifiers - set(frame.columns))
    if missing_identifiers:
        raise ValueError(
            f"{SHEET_NAME} is missing required identifier columns: {', '.join(missing_identifiers)}"
        )

    excluded = _excluded_mask(frame)
    frame = frame.loc[~excluded].copy()
    if frame.empty:
        logger.info("Processed %s: no active measurable rows remain after exclusions", SHEET_NAME)
        return frame

    assigned_column = _first_column(frame, "AssignedRequests", "AssignedRequest")
    approved_column = _first_column(frame, "ApprovedRequests", "ApprovedRequest")
    rejected_column = _first_column(frame, "RejectedRequests", "RejectedRequest")
    assigned = _numbers(frame, assigned_column) if assigned_column else pd.Series(float("nan"), index=frame.index)
    approved = _numbers(frame, approved_column) if approved_column else pd.Series(float("nan"), index=frame.index)
    rejected = _numbers(frame, rejected_column) if rejected_column else pd.Series(float("nan"), index=frame.index)
    within_48_column = _first_column(frame, "ApprovalWithin48HR")
    within_1_5_column = _first_column(frame, "ApprovalWithin1.5HR")
    combined_turnaround_column = _first_column(
        frame,
        "ApprovalWithin48HR/1.5HR",
        "ApprovalWithin48HRor1.5HR",
    )
    rejection_target_source = _numbers(frame, "T.InitialRejection%")
    turnaround_target_source = _numbers(
        frame,
        "T.%OfApprovalwithin48HR/1.5HR",
    )
    target_pair_present = (
        "T.InitialRejection%" in frame.columns
        or "T.%OfApprovalwithin48HR/1.5HR" in frame.columns
    )

    if within_48_column or within_1_5_column:
        within_48 = _numbers(frame, within_48_column) if within_48_column else pd.Series(float("nan"), index=frame.index)
        within_1_5 = _numbers(frame, within_1_5_column) if within_1_5_column else pd.Series(float("nan"), index=frame.index)
        has_48_hours = within_48.notna()
        has_1_5_hours = within_1_5.notna()
        _raise_for_invalid_workstream_rows(frame, has_48_hours, has_1_5_hours)
        if target_pair_present:
            target_48_hours, target_1_5_hours = _workstreams_from_target_pair(
                frame,
                rejection_target_source,
                turnaround_target_source,
            )
            if not (has_48_hours == target_48_hours).all() or not (
                has_1_5_hours == target_1_5_hours
            ).all():
                ids = ", ".join(_employee_ids(frame, frame.index[:10]))
                raise ValueError(
                    "Turnaround numerator does not match the target pair for "
                    f"Pre-Approvals IP Elective Dubai employees: {ids}"
                )
    elif combined_turnaround_column:
        combined_turnaround = _numbers(frame, combined_turnaround_column)
        has_48_hours, has_1_5_hours = _workstreams_from_combined_source(
            frame,
            combined_turnaround,
            rejection_target_source,
            turnaround_target_source,
        )
        within_48 = combined_turnaround.where(has_48_hours)
        within_1_5 = combined_turnaround.where(has_1_5_hours)
    else:
        raise ValueError(
            f"{SHEET_NAME} is missing a turnaround count column: expected Approval Within 48 HR, "
            "Approval Within 1.5 HR, or the combined Approval Within 48 HR/1.5 HR column"
        )

    # Every selected KPI needs both volume denominators.  Failing with IDs is
    # safer than turning a missing denominator into a misleading zero score.
    _require_positive_denominator(frame, assigned, "initial rejection rate", frame.index)
    _require_positive_denominator(frame, approved, "approval turnaround rate", frame.index)
    rejected_missing = frame.index[rejected.isna()]
    if len(rejected_missing):
        ids = ", ".join(_employee_ids(frame, rejected_missing)[:10])
        raise ValueError(f"Rejected Requests is missing for employees: {ids}")

    rejection_rate = _safe_ratio(rejected, assigned)
    # Canonical source names keep the same aggregation metadata working for
    # both the legacy plural headers and the current singular workbook header.
    frame["AssignedRequests"] = assigned
    frame["ApprovedRequests"] = approved
    frame["RejectedRequests"] = rejected
    frame["ApprovalWithin48HR"] = within_48
    frame["ApprovalWithin1.5HR"] = within_1_5
    frame["A.IPInitialRejectionRate"] = rejection_rate
    frame["A.ERInitialRejectionRate"] = rejection_rate
    frame["T.IPInitialRejectionRate"] = rejection_target_source.where(
        has_48_hours,
        IP_REJECTION_TARGET,
    ).fillna(IP_REJECTION_TARGET)
    frame["T.ERInitialRejectionRate"] = rejection_target_source.where(
        has_1_5_hours,
        ER_REJECTION_TARGET,
    ).fillna(ER_REJECTION_TARGET)
    frame["A.ApprovalWithin48HoursRate"] = _safe_ratio(within_48, approved)
    frame["T.ApprovalWithin48HoursRate"] = turnaround_target_source.where(
        has_48_hours,
        TURNAROUND_48_TARGET,
    ).fillna(TURNAROUND_48_TARGET)
    frame["A.ApprovalWithin1.5HoursRate"] = _safe_ratio(within_1_5, approved)
    frame["T.ApprovalWithin1.5HoursRate"] = turnaround_target_source.where(
        has_1_5_hours,
        TURNAROUND_1_5_TARGET,
    ).fillna(TURNAROUND_1_5_TARGET)
    frame["Position"] = IP_ELECTIVE
    frame.loc[has_1_5_hours, "Position"] = ER_IP_APPROVAL
    frame["Workstream"] = frame["Position"]
    frame["Region"] = "UAE"

    logger.info(
        "Processed %s rows by workstream: %s",
        len(frame),
        frame["Position"].value_counts().to_dict(),
    )
    return frame
