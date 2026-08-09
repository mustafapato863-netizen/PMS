"""Cleaner for the Pre-Approvals OP Final SHJ/AJM worksheet.

The worksheet contains one employee KPI set for both Sharjah (SHJ) and
Ajman (AJM).  Branch is retained in the source ``Team`` column; it is not a
second scoring configuration.  The source's calculated columns are rebuilt
from the volume counters so imported scores cannot depend on stale Excel
formulas or cached values.
"""

from __future__ import annotations

import io
import logging
from typing import Iterable

import pandas as pd

from cleaned import clean_sheet_data


logger = logging.getLogger(__name__)

SHEET_NAME = "Pre-Approvals OP Final SHJAJM"
EXCLUDED_VALUES = {"-", "leave", "new staff"}


def _numbers(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if not column or column not in frame.columns:
        return pd.Series(float("nan"), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _first_column(frame: pd.DataFrame, *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in frame.columns), None)


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    result = pd.Series(float("nan"), index=denominator.index, dtype="float64")
    valid = numerator.notna() & denominator.notna() & denominator.gt(0)
    result.loc[valid] = numerator.loc[valid] / denominator.loc[valid]
    return result


def _normalised_values(series: pd.Series) -> pd.Series:
    return series.map(lambda value: "" if pd.isna(value) else str(value).strip().casefold())


def _employee_ids(frame: pd.DataFrame, indexes: Iterable) -> list[str]:
    if "HRID" in frame.columns:
        return [str(value).strip() for value in frame.loc[list(indexes), "HRID"].tolist()]
    return [str(index) for index in indexes]


def _require_positive(
    frame: pd.DataFrame,
    values: pd.Series,
    label: str,
    indexes: pd.Index,
) -> None:
    invalid = indexes[values.loc[indexes].isna() | values.loc[indexes].le(0)]
    if len(invalid):
        ids = ", ".join(_employee_ids(frame, invalid)[:10])
        raise ValueError(f"Cannot calculate {label}; positive value is required for employees: {ids}")


def process_preapprovals_op_final_shj_ajm(file_source) -> pd.DataFrame:
    """Load, validate, and enrich the SHJ/AJM OP Final employee sheet."""
    source = io.BytesIO(file_source) if isinstance(file_source, (bytes, bytearray)) else file_source
    frame = pd.read_excel(source, sheet_name=SHEET_NAME)
    frame = clean_sheet_data(frame.copy(), sheet_name=SHEET_NAME)
    frame.columns = frame.columns.astype(str).str.replace(r"\s+", "", regex=True)

    required_identifiers = {"HRID", "AgentName"}
    missing_identifiers = sorted(required_identifiers - set(frame.columns))
    if missing_identifiers:
        raise ValueError(
            f"{SHEET_NAME} is missing required identifier columns: {', '.join(missing_identifiers)}"
        )

    # Presentation rows and non-measurable statuses must never become
    # employees.  Blank identifiers also remove trailing formatted rows.
    excluded = pd.Series(False, index=frame.index)
    for column in ("Status", "PerformanceGrade"):
        if column in frame.columns:
            excluded |= _normalised_values(frame[column]).isin(EXCLUDED_VALUES)
    identifiers_present = frame["HRID"].notna() & frame["AgentName"].notna()
    identifiers_present &= frame["HRID"].astype(str).str.strip().ne("")
    identifiers_present &= frame["AgentName"].astype(str).str.strip().ne("")
    frame = frame.loc[~excluded & identifiers_present].copy()
    if frame.empty:
        logger.info("Processed %s: no active measurable rows remain after exclusions", SHEET_NAME)
        return frame

    submitted_column = _first_column(frame, "SubmittedRequests", "SubmittedRequest")
    manual_column = _first_column(frame, "ManualRequest", "ManualRequests")
    within_hour_column = _first_column(
        frame,
        "SubmittedWithinHour",
        "SubmittedWithinHours",
        "SubmittedWithinHourCount",
    )
    rejected_column = _first_column(frame, "RejectedRequests", "RejectedRequest")
    rejection_target_column = _first_column(frame, "T.InitialRejection", "T.InitialRejection%")
    tat_target_column = _first_column(
        frame,
        "T.SubmissionWithinHour%",
        "T.SubmissionWithinTAT%",
    )

    required_measurement_columns = {
        "Submitted Requests": submitted_column,
        "Manual Request": manual_column,
        "Submitted Within Hour": within_hour_column,
        "Rejected Requests": rejected_column,
        "T.Initial Rejection": rejection_target_column,
        "T.Submission Within Hour %": tat_target_column,
    }
    missing_measurements = [
        label for label, column in required_measurement_columns.items() if column is None
    ]
    if missing_measurements:
        raise ValueError(
            f"{SHEET_NAME} is missing required measurement columns: {', '.join(missing_measurements)}"
        )

    submitted = _numbers(frame, submitted_column)
    manual = _numbers(frame, manual_column).fillna(0.0)
    submitted_within_hour = _numbers(frame, within_hour_column)
    rejected = _numbers(frame, rejected_column)
    rejection_target = _numbers(frame, rejection_target_column)
    tat_target = _numbers(frame, tat_target_column)

    _require_positive(frame, submitted, "initial rejection rate denominator", frame.index)
    missing_rejected = frame.index[rejected.isna()]
    if len(missing_rejected):
        ids = ", ".join(_employee_ids(frame, missing_rejected)[:10])
        raise ValueError(f"Rejected Requests is missing for employees: {ids}")
    missing_targets = frame.index[rejection_target.isna() | tat_target.isna()]
    if len(missing_targets):
        ids = ", ".join(_employee_ids(frame, missing_targets)[:10])
        raise ValueError(f"Both SHJ/AJM target columns are required for employees: {ids}")

    submitted_excluding_manual = submitted - manual
    tat_available = (
        submitted_within_hour.notna()
        & submitted_excluding_manual.notna()
        & submitted_excluding_manual.gt(0)
    )

    frame["SubmittedRequests"] = submitted
    frame["ManualRequest"] = manual
    frame["SubmittedWithinHour"] = submitted_within_hour
    frame["RejectedRequests"] = rejected
    frame["SubmittedRequestsExcludingManual"] = submitted_excluding_manual
    frame["A.InitialRejectionRate"] = _safe_ratio(rejected, submitted)
    frame["T.InitialRejectionRate"] = rejection_target
    frame["A.SubmissionWithinTATRate"] = _safe_ratio(
        submitted_within_hour,
        submitted_excluding_manual,
    )
    frame["T.SubmissionWithinTATRate"] = tat_target
    frame["SubmissionWithinTATAvailable"] = tat_available
    frame["Position"] = "OP Final"
    frame["Workstream"] = "OP Final"
    frame["Region"] = "UAE"

    logger.info(
        "Processed %s rows by branch: %s (TAT unavailable: %s)",
        len(frame),
        frame.get("Team", pd.Series(dtype="object")).value_counts().to_dict(),
        int((~tat_available).sum()),
    )
    return frame
