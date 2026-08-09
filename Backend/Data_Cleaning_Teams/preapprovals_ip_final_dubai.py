"""Cleaner for the Pre-Approvals IP Final Dubai employee sheet."""

from __future__ import annotations

import logging

import pandas as pd

from cleaned import clean_sheet_data


logger = logging.getLogger(__name__)

SHEET_NAME = "Pre-Approvals IP Final Dubai"
COMBINED = "Combined"
IP_APPROVAL = "IP Approval"
IP_DISCHARGE = "IP Discharge"
BASELINE = 0.8


def _numbers(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(float("nan"), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    result = pd.Series(0.0, index=denominator.index, dtype="float64")
    valid = denominator.notna() & denominator.gt(0)
    result.loc[valid] = numerator.fillna(0.0).loc[valid] / denominator.loc[valid]
    return result


def _baseline_achievement(actual: pd.Series, target: pd.Series) -> pd.Series:
    result = pd.Series(0.0, index=actual.index, dtype="float64")
    denominator = target - BASELINE
    valid = actual.notna() & target.notna() & denominator.ne(0)
    result.loc[valid] = ((actual.loc[valid] - BASELINE) / denominator.loc[valid]).clip(lower=0.0, upper=1.0)
    return result


def _derive_positions(
    frame: pd.DataFrame,
    assigned: pd.Series,
    discharge_requests: pd.Series,
    acceptance_achievement: pd.Series,
    submission_achievement: pd.Series,
    discharge_achievement: pd.Series,
) -> pd.Series:
    approval_available = assigned.notna() & assigned.gt(0)
    discharge_available = discharge_requests.notna() & discharge_requests.gt(0)
    positions = pd.Series(pd.NA, index=assigned.index, dtype="object")
    positions.loc[approval_available & discharge_available] = COMBINED
    positions.loc[approval_available & ~discharge_available] = IP_APPROVAL
    positions.loc[~approval_available & discharge_available] = IP_DISCHARGE

    source_score = _numbers(frame, "PerformanceScore")
    candidates = pd.DataFrame({
        COMBINED: acceptance_achievement * 0.5 + submission_achievement * 0.3 + discharge_achievement * 0.2,
        IP_APPROVAL: acceptance_achievement * 0.6 + submission_achievement * 0.4,
        IP_DISCHARGE: discharge_achievement,
    })
    candidates.loc[~(approval_available & discharge_available), COMBINED] = float("nan")
    candidates.loc[~approval_available, IP_APPROVAL] = float("nan")
    candidates.loc[~discharge_available, IP_DISCHARGE] = float("nan")
    for index in frame.index[source_score.notna()]:
        differences = (candidates.loc[index] - source_score.loc[index]).abs().dropna()
        if not differences.empty and differences.min() <= 0.01:
            positions.loc[index] = differences.idxmin()
    return positions


def process_preapprovals_ip_final_dubai(file_source) -> pd.DataFrame:
    """Load the sheet and calculate canonical actual, target, and achievement values."""
    frame = pd.read_excel(file_source, sheet_name=SHEET_NAME)
    frame = clean_sheet_data(frame, sheet_name=SHEET_NAME)
    frame.columns = frame.columns.str.replace(r"\s+", "", regex=True)

    if "Status" in frame.columns:
        excluded = frame["Status"].astype(str).str.strip().str.casefold().isin({"leave", "new staff"})
        frame = frame.loc[~excluded].copy()

    frame["Region"] = "UAE"
    assigned = _numbers(frame, "AssignedRequest")
    approved = _numbers(frame, "ApprovedRequests")
    submitted = _numbers(frame, "SubmittedWithinMonth(Untill3rdofnextmonth)")
    discharge_requests = _numbers(frame, "DischargeRequests")
    discharge_within_hour = _numbers(frame, "DischargeWithinHour")

    frame["AcceptanceRate"] = _safe_ratio(approved, assigned)
    frame["SubmissionWithinMonth%"] = _safe_ratio(submitted, assigned)
    frame["Discharge%Within1Hour"] = _safe_ratio(discharge_within_hour, discharge_requests)

    acceptance_target = _numbers(frame, "A.AcceptanceRate").fillna(0.0)
    submission_target = _numbers(frame, "A.SubmissionWithinMonth%").fillna(0.0)
    discharge_target = _numbers(frame, "A.Discharge%Within1Hour").fillna(0.0)
    frame["A.AcceptanceRate"] = acceptance_target
    frame["A.SubmissionWithinMonth%"] = submission_target
    frame["A.Discharge%Within1Hour"] = discharge_target
    frame["T.AcceptanceRate%"] = _baseline_achievement(frame["AcceptanceRate"], acceptance_target)
    frame["T.%ofSubmissionWithinDuedate"] = _baseline_achievement(frame["SubmissionWithinMonth%"], submission_target)
    frame["T.Discharge%Within1Hour"] = _baseline_achievement(frame["Discharge%Within1Hour"], discharge_target)
    frame["Position"] = _derive_positions(
        frame,
        assigned,
        discharge_requests,
        frame["T.AcceptanceRate%"],
        frame["T.%ofSubmissionWithinDuedate"],
        frame["T.Discharge%Within1Hour"],
    )
    missing_position = frame["Position"].isna()
    if missing_position.any():
        ids = frame.loc[missing_position, "HRID"].astype(str).tolist() if "HRID" in frame else []
        raise ValueError("Cannot determine Pre-Approvals IP Final Dubai activity for rows: " + ", ".join(ids[:10]))

    logger.info("Processed %s rows by activity: %s", len(frame), frame["Position"].value_counts().to_dict())
    return frame
