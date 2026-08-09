"""Cleaner for the position-scoped Pre-Approvals OP Dubai sheet."""

from __future__ import annotations

import logging

import pandas as pd

from cleaned import clean_sheet_data


logger = logging.getLogger(__name__)

SHEET_NAME = "Pre-Approvals OP Dubai"
INITIAL_SUBMISSION = "Initial Submission"
FINAL_SUBMISSION = "Final Submission"
CALLS = "Calls"


def _numbers(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    valid = denominator.notna() & denominator.ne(0)
    result = pd.Series(0.0, index=denominator.index, dtype="float64")
    result.loc[valid] = numerator.fillna(0.0).loc[valid] / denominator.loc[valid]
    return result


def _target(frame: pd.DataFrame, column: str) -> pd.Series:
    return _numbers(frame, column).fillna(0.0)


def _derive_positions(frame: pd.DataFrame) -> pd.Series:
    total_calls = _numbers(frame, "TotalNumberOfCallsperDay")
    submitted_within_day = _numbers(frame, "SubmittedWithinDay")
    submitted_within_hour = _numbers(frame, "SubmittedWithinHour")
    submitted_requests = _numbers(frame, "SubmittedRequests")

    positions = pd.Series(pd.NA, index=frame.index, dtype="object")
    positions.loc[submitted_requests.notna() | submitted_within_hour.notna()] = INITIAL_SUBMISSION
    positions.loc[submitted_within_day.notna()] = FINAL_SUBMISSION
    positions.loc[total_calls.notna()] = CALLS
    return positions


def process_preapprovals_op_dubai(file_source) -> pd.DataFrame:
    """Load the source sheet, derive its workstream, and calculate canonical KPI actuals."""
    frame = pd.read_excel(file_source, sheet_name=SHEET_NAME)
    frame = clean_sheet_data(frame, sheet_name=SHEET_NAME)
    frame.columns = frame.columns.str.replace(r"\s+", "", regex=True)

    if "Status" in frame.columns:
        leave_rows = frame["Status"].astype(str).str.strip().str.casefold().eq("leave")
        frame = frame.loc[~leave_rows].copy()

    frame["Position"] = _derive_positions(frame)
    missing_position = frame["Position"].isna()
    if missing_position.any():
        employee_ids = frame.loc[missing_position, "HRID"].astype(str).tolist() if "HRID" in frame else []
        raise ValueError(
            "Cannot determine Pre-Approvals OP Dubai workstream for rows: "
            + ", ".join(employee_ids[:10])
        )

    assigned = _numbers(frame, "AssignedRequest")
    submitted = _numbers(frame, "SubmittedRequests")
    within_day = _numbers(frame, "SubmittedWithinDay")
    within_hour = _numbers(frame, "SubmittedWithinHour")
    rejected = _numbers(frame, "RejectedRequests")
    total_calls = _numbers(frame, "TotalNumberOfCallsperDay")
    attended_calls = _numbers(frame, "TotalAttendedCallsPerDay")
    abandoned_calls = _numbers(frame, "TotalAbandonedCallsPerDay")

    frame["A.InitialRejectionRate"] = _safe_ratio(rejected, submitted)
    frame["T.InitialRejectionRate"] = _target(frame, "T.InitialRejection")
    frame["A.SubmissionWithinHourRate"] = _safe_ratio(within_hour, submitted)
    frame["T.SubmissionWithinHourRate"] = _target(frame, "T.SubmissionWithinHour%")
    frame["A.SubmissionWithinDueDateRate"] = _safe_ratio(within_day, assigned)
    frame["T.SubmissionWithinDueDateRate"] = _target(frame, "T.SubmissionWithinHour%")
    frame["A.AbandonedCallsRate"] = _safe_ratio(abandoned_calls, total_calls)
    frame["T.AbandonedCallsRate"] = _target(frame, "T.%AbandonedCalls")
    frame["A.AttendedCallsRate"] = _safe_ratio(attended_calls, total_calls)
    frame["T.AttendedCallsRate"] = _target(frame, "T.%ofAttendedCalls")

    logger.info(
        "Processed %s rows by workstream: %s",
        len(frame),
        frame["Position"].value_counts().to_dict(),
    )
    return frame
