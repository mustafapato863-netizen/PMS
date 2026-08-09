"""
Re-Submission Team Data Cleaner

Config-first cleaner for the Employee-level Re-Submission team.
"""

import logging
from typing import Any, Dict

import numpy as np
import pandas as pd

from data_cleaning.standard_mappings import calculate_grade

logger = logging.getLogger(__name__)


def _normalize_grade_value(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def _should_exclude_row(df: pd.DataFrame) -> pd.Series:
    grade_columns = [col for col in df.columns if col.lower().replace(" ", "") == "performancegrade"]
    if not grade_columns:
        return pd.Series([False] * len(df), index=df.index)
    excluded_grades = {"-", "new staff", "leave"}
    normalized = df[grade_columns[0]].apply(_normalize_grade_value)
    return normalized.isin(excluded_grades)


def _parse_numeric(value: Any) -> float:
    if pd.isna(value):
        return np.nan
    if isinstance(value, str):
        value = value.replace(",", "").replace("%", "").strip()
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.replace(r"\s+", "", regex=True)
    return df


def _resolve_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    wanted = {alias.lower().replace(" ", "") for alias in aliases}
    for column in df.columns:
        normalized = str(column).lower().replace(" ", "")
        if normalized in wanted:
            return column
    return None


def _require_column(df: pd.DataFrame, aliases: list[str], *, team: str, kpi: str, field: str) -> str:
    column = _resolve_column(df, aliases)
    if column:
        return column
    expected = ", ".join(aliases)
    raise ValueError(f"{team} / {kpi}: missing source column for {field}. Expected one of: {expected}")


def _safe_ratio(numerator: float, denominator: float) -> float:
    if not np.isfinite(numerator) or not np.isfinite(denominator) or denominator <= 0:
        return np.nan
    return float(numerator / denominator)


def process_re_submission(file_path: str, team_config: Dict[str, Any] = None) -> pd.DataFrame:
    from cleaned import clean_sheet_data
    from utils import add_computed_columns

    team_name = "Re-Submission"
    sheet_name = "Re-Submission"
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    df = clean_sheet_data(df, sheet_name=sheet_name)
    df = df.loc[~_should_exclude_row(df)].copy()
    df = _normalize_headers(df)

    allocated_col = _require_column(
        df,
        ["AllocatedClaims", "AllocatedClaim", "G"],
        team=team_name,
        kpi="tat",
        field="allocated_claims",
    )
    quality_samples_col = _require_column(
        df,
        ["QualitySamples", "QualitySample", "J"],
        team=team_name,
        kpi="quality_errors_rate",
        field="quality_samples",
    )
    final_errors_col = _require_column(
        df,
        ["FinalErrorsClaimsraisedbyQualityinthesamemonth", "FinalErrorsClaims", "K"],
        team=team_name,
        kpi="quality_errors_rate",
        field="final_errors_claims",
    )
    within_tat_col = _require_column(
        df,
        ["TotalSubmittedWithinTAT", "SubmittedWithinTAT", "L"],
        team=team_name,
        kpi="tat",
        field="total_submitted_within_tat",
    )
    remittance_col = _require_column(
        df,
        ["RemittanceAmount", "Remittance", "O"],
        team=team_name,
        kpi="rejection_rate_after_resubmission",
        field="remittance_amount",
    )
    rejected_col = _require_column(
        df,
        ["RejectedClaimsfromtheprevious3monthsbyinsurance", "RejectedClaimsPrevious3Months", "Q"],
        team=team_name,
        kpi="rejection_rate_after_resubmission",
        field="rejected_claims_previous_3_months",
    )

    allocated = df[allocated_col].apply(_parse_numeric)
    quality_samples = df[quality_samples_col].apply(_parse_numeric)
    final_errors = df[final_errors_col].apply(_parse_numeric)
    within_tat = df[within_tat_col].apply(_parse_numeric)
    remittance = df[remittance_col].apply(_parse_numeric)
    rejected = df[rejected_col].apply(_parse_numeric)

    df["A.QualityErrorsRate"] = [_safe_ratio(errors, samples) for errors, samples in zip(final_errors, quality_samples)]
    df["T.QualityErrorsRate"] = 0.05
    df["QualityErrorsRateAch%"] = [
        1.0
        if np.isfinite(samples) and samples > 0 and np.isfinite(errors) and errors == 0
        else min(1.0, 0.05 / actual)
        if np.isfinite(actual) and actual > 0
        else np.nan
        for actual, errors, samples in zip(df["A.QualityErrorsRate"], final_errors, quality_samples)
    ]

    df["A.RejectionRateAfterResubmission"] = [_safe_ratio(value, base) for value, base in zip(rejected, remittance)]
    df["T.RejectionRateAfterResubmission"] = 0.60
    df["RejectionRateAfterResubmissionAch%"] = [
        min(1.0, 0.60 / actual)
        if np.isfinite(actual) and actual > 0
        else np.nan
        for actual in df["A.RejectionRateAfterResubmission"]
    ]

    df["A.TAT"] = [_safe_ratio(done, allocated_claims) for done, allocated_claims in zip(within_tat, allocated)]
    df["T.TAT"] = 1.0
    df["TATAch%"] = [
        min(1.0, actual)
        if np.isfinite(actual)
        else np.nan
        for actual in df["A.TAT"]
    ]

    performance = (
        np.nan_to_num(df["QualityErrorsRateAch%"], nan=0.0) * 20.0
        + np.nan_to_num(df["RejectionRateAfterResubmissionAch%"], nan=0.0) * 50.0
        + np.nan_to_num(df["TATAch%"], nan=0.0) * 30.0
    )
    df["Performance"] = np.minimum(performance, 100.0)
    df["Grade"] = df["Performance"].apply(calculate_grade)
    df = add_computed_columns(df)

    logger.info("Processed Re-Submission data with %s rows", len(df))
    return df
