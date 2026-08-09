"""Cleaner for the Pre-Approvals IP Final SHJ/AJM worksheet.

Sharjah and Ajman share one IP scorecard.  The source ``Team`` value is
retained as the branch dimension while the score is calculated from the two
documented 80% baseline formulas.
"""

from __future__ import annotations

import io
import logging
from typing import Iterable

import pandas as pd

from cleaned import clean_sheet_data


logger = logging.getLogger(__name__)

SHEET_NAME = "Pre-Approvals IP Final SHJAJM"
POSITION = "IP Final"
BASELINE = 0.80
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


def _baseline_achievement(actual: pd.Series, target: pd.Series) -> pd.Series:
    denominator = target - BASELINE
    result = pd.Series(float("nan"), index=actual.index, dtype="float64")
    valid = actual.notna() & target.notna() & denominator.ne(0)
    # The scorecard floors below-baseline achievement at zero and caps the
    # resulting KPI achievement at 100% under the global product rule.
    result.loc[valid] = ((actual.loc[valid] - BASELINE) / denominator.loc[valid]).clip(lower=0.0, upper=1.0)
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


def _require_baseline_targets(
    frame: pd.DataFrame,
    target: pd.Series,
    label: str,
    indexes: pd.Index,
) -> None:
    invalid = indexes[target.loc[indexes].isna() | target.loc[indexes].le(BASELINE)]
    if len(invalid):
        ids = ", ".join(_employee_ids(frame, invalid)[:10])
        raise ValueError(
            f"{label} must be greater than the 80% baseline for employees: {ids}"
        )


def process_preapprovals_ip_final_shj_ajm(file_source) -> pd.DataFrame:
    """Load and enrich the IP SHJ/AJM employee sheet."""
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

    assigned_column = _first_column(frame, "AssignedRequest", "AssignedRequests")
    approved_column = _first_column(frame, "ApprovedRequests", "ApprovedRequest")
    submitted_column = _first_column(
        frame,
        "SubmittedWithinMonth(Untill3rdofnextmonth)",
        "SubmittedWithinMonth(Untill3rdofnextmonth)",
    )
    acceptance_target_column = _first_column(
        frame,
        "T.AcceptanceRate",
        "T.AcceptanceRate%",
    )
    submission_target_column = _first_column(
        frame,
        "T.SubmissionWithinMonth%",
        "T.%ofSubmissionWithinDuedate",
    )
    required_measurements = {
        "Assigned Request": assigned_column,
        "Approved Requests": approved_column,
        "Submitted Within Month": submitted_column,
        "T.Acceptance Rate": acceptance_target_column,
        "T.Submission Within Month %": submission_target_column,
    }
    missing_measurements = [label for label, column in required_measurements.items() if column is None]
    if missing_measurements:
        raise ValueError(
            f"{SHEET_NAME} is missing required measurement columns: {', '.join(missing_measurements)}"
        )

    assigned = _numbers(frame, assigned_column)
    approved = _numbers(frame, approved_column)
    submitted = _numbers(frame, submitted_column)
    acceptance_target = _numbers(frame, acceptance_target_column)
    submission_target = _numbers(frame, submission_target_column)
    _require_positive(frame, assigned, "acceptance rate denominator", frame.index)
    missing_approved = frame.index[approved.isna()]
    missing_submitted = frame.index[submitted.isna()]
    if len(missing_approved) or len(missing_submitted):
        invalid = missing_approved.union(missing_submitted)
        ids = ", ".join(_employee_ids(frame, invalid)[:10])
        raise ValueError(f"Approved Requests and Submitted Within Month are required for employees: {ids}")
    _require_baseline_targets(frame, acceptance_target, "Acceptance targets", frame.index)
    _require_baseline_targets(frame, submission_target, "Submission Within Month targets", frame.index)

    frame["AssignedRequest"] = assigned
    frame["ApprovedRequests"] = approved
    frame["SubmittedWithinMonth(Untill3rdofnextmonth)"] = submitted
    frame["AcceptanceRate"] = _safe_ratio(approved, assigned)
    frame["SubmissionWithinMonth%"] = _safe_ratio(submitted, assigned)
    frame["T.AcceptanceRate"] = acceptance_target
    frame["T.SubmissionWithinMonth%"] = submission_target
    frame["AcceptanceRateAchievement"] = _baseline_achievement(
        frame["AcceptanceRate"], acceptance_target
    )
    frame["SubmissionWithinMonthAchievement"] = _baseline_achievement(
        frame["SubmissionWithinMonth%"], submission_target
    )
    frame["Region"] = "UAE"
    frame["Position"] = POSITION
    frame["Workstream"] = POSITION

    logger.info(
        "Processed %s rows by branch: %s",
        len(frame),
        frame.get("Team", pd.Series(dtype="object")).value_counts().to_dict(),
    )
    return frame
