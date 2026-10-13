import pandas as pd
import numpy as np  # Imported numpy for row-by-row conditional logic
from cleaned import clean_sheet_data
from services.preapprovals_offshore_scoring import (
    DERIVED_RAW_KEYS,
    RAW_COUNT_COLUMNS,
    TARGET_APPROVAL_WITHIN_48H,
    TARGET_CONTROLLABLE_REJECTION_RATE,
    TARGET_ERROR_RATE,
    OffshoreDataError,
    counts_from_mapping,
    derived_raw_values,
    reporting_period_from_row,
    score_counts,
    uses_new_method,
)
from services.upload_header_notices import publish_header_notices

SHEET_NAME = "Pre-Approvals IP Offshore"

# Workbook columns that older uploads carried as pre-computed values. The
# June 2026 method never reads them. They are only compared, for a warning.
PRECOMPUTED_ACHIEVEMENT_COLUMNS = {
    "Rejection": "RejectionRate",
    "InitialError": "InitialError%",
    "Submission": "%ofSubmissionWithinDuedate",
}
PRECOMPUTED_TARGET_COLUMNS = {
    "Rejection": ("T.Rejection%", TARGET_CONTROLLABLE_REJECTION_RATE),
    "InitialError": ("T.InitialError%", TARGET_ERROR_RATE),
    "Submission": ("T.Submission%", TARGET_APPROVAL_WITHIN_48H),
}
ACHIEVEMENT_TOLERANCE = 0.005
TARGET_TOLERANCE = 0.0005
DISAGREEMENT_CODE = "offshore_precomputed_disagrees"
TARGET_CODE = "offshore_fixed_target_applied"
MAX_ROW_ERRORS_SHOWN = 25


def _text(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return "" if text.lower() == "nan" else text


def _is_data_row(row):
    """Same identity rule seeding uses (HRID, AgentName), not a totals row."""
    emp_id = _text(row.get("HRID")) or _text(row.get("EmployeeID"))
    name = _text(row.get("AgentName")) or _text(row.get("EmployeeName"))
    return bool(emp_id) and bool(name) and name.lower() != "total"


def _legacy_performance(df):
    """The formula used before June 2026. Kept unchanged for earlier periods."""
    submitted_claims_col = 'SubmittedClaims' if 'SubmittedClaims' in df.columns else 'SubmittedClaims'

    rejection_score = df['RejectionRate'].fillna(0) if 'RejectionRate' in df.columns else 0
    initial_error_score = df['InitialError%'].fillna(0) if 'InitialError%' in df.columns else 0
    sub_score = df[f'%ofSubmissionWithinDuedate'].fillna(0) if f'%ofSubmissionWithinDuedate' in df.columns else 0

    # Condition: Check row-by-row if Submitted Claims is equal to 0 (or empty/NaN)
    is_claims_zero = (df[submitted_claims_col].fillna(0) == 0)

    # Dynamic Rejection Weight: 60% if claims == 0, else 50%
    weight_rejection = np.where(is_claims_zero, 0.60, 0.50)

    # Dynamic Initial Error Weight: 0% if claims == 0, else 20%
    weight_initial_error = np.where(is_claims_zero, 0.00, 0.20)

    # Dynamic Submission Weight: 40% if claims == 0, else 30%
    weight_submission = np.where(is_claims_zero, 0.40, 0.30)

    return (
        (rejection_score * weight_rejection) +
        (initial_error_score * weight_initial_error) +
        (sub_score * weight_submission)
    )


def _as_ratio(value):
    number = float(value)
    return number / 100.0 if number > 2.0 else number


def _precomputed_notices(records, new_rows, results):
    """Warn when a workbook's pre-computed achievement or target columns disagree."""
    notices = []
    for kpi_key, column in PRECOMPUTED_ACHIEVEMENT_COLUMNS.items():
        if not any(column in record for record in records):
            continue
        disagreeing = 0
        for index in new_rows:
            value = records[index].get(column)
            achievement = results[index].achievements[kpi_key]
            if achievement is None or value is None or pd.isna(value):
                continue
            if abs(_as_ratio(value) - achievement) > ACHIEVEMENT_TOLERANCE:
                disagreeing += 1
        if disagreeing:
            notices.append({"sheet": SHEET_NAME, "code": DISAGREEMENT_CODE, "headers": [column], "truncated": False})

    for kpi_key, (column, fixed_target) in PRECOMPUTED_TARGET_COLUMNS.items():
        if not any(column in record for record in records):
            continue
        differing = 0
        for index in new_rows:
            value = records[index].get(column)
            if value is None or pd.isna(value):
                continue
            if abs(_as_ratio(value) - fixed_target) > TARGET_TOLERANCE:
                differing += 1
        if differing:
            notices.append({"sheet": SHEET_NAME, "code": TARGET_CODE, "headers": [column], "truncated": False})
    return notices


def process_preapprovals_offshore(file_path, team_config=None):
    # --- 1. Load and Clean Data ---
    df = pd.read_excel(file_path, sheet_name=SHEET_NAME)
    df = clean_sheet_data(df, sheet_name=SHEET_NAME).reset_index(drop=True)

    # Standardize column names by removing ALL hidden whitespaces
    df.columns = df.columns.str.replace(r'\s+', '', regex=True)

    # --- 2. Decide each data row's method from its own reporting period ---
    records = df.to_dict("records")
    new_rows = []
    period_errors = []
    for index, record in enumerate(records):
        if not _is_data_row(record):
            continue  # totals and blank rows are not scored, as before
        period = reporting_period_from_row(record)
        if period is None:
            period_errors.append(f"data row {index + 1}: reporting period cannot be determined from Date or Month")
            continue
        if uses_new_method(*period):
            new_rows.append(index)

    # --- 3. Required raw columns, only when a row needs the June 2026 method ---
    if new_rows:
        missing = [column for column in RAW_COUNT_COLUMNS if column not in df.columns]
        if missing:
            raise ValueError(
                f"{SHEET_NAME}: missing required column(s) for rows from June 2026: {', '.join(missing)}"
            )

    # --- 4. Score the June 2026 rows from raw counts ---
    results = {}
    row_errors = list(period_errors)
    for index in new_rows:
        try:
            results[index] = score_counts(counts_from_mapping(records[index]))
        except OffshoreDataError as error:
            row_errors.append(f"data row {index + 1}: {error}")
    if row_errors:
        shown = "; ".join(row_errors[:MAX_ROW_ERRORS_SHOWN])
        more = len(row_errors) - MAX_ROW_ERRORS_SHOWN
        suffix = f" (and {more} more)" if more > 0 else ""
        raise ValueError(f"{SHEET_NAME}: import stopped, {len(row_errors)} row(s) cannot be scored. {shown}{suffix}")

    # --- 5. Earlier periods keep today's formula, untouched ---
    performance = pd.Series(_legacy_performance(df), index=df.index, dtype="float64")
    for index, result in results.items():
        performance.iloc[index] = round(result.score / 100.0, 6)
    df['Performance'] = performance

    if new_rows:
        for key in DERIVED_RAW_KEYS:
            df[key] = None
        for index, result in results.items():
            for key, value in derived_raw_values(result).items():
                df.iat[index, df.columns.get_loc(key)] = value

    # --- 6. Warn, never fail, when workbook pre-computed columns disagree ---
    notices = _precomputed_notices(records, new_rows, results) if new_rows else []
    if notices:
        existing = [dict(item) for item in list(df.attrs.get("column_warnings") or [])]
        df.attrs["column_warnings"] = existing + notices
        publish_header_notices(notices)

    return df

# --- 4. Execution and Testing Block ---
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    try:
        df_result = process_preapprovals_offshore(r"D:\Trend\PMS_Trend_All.xlsx")
        print("✅ Pre-Approvals KPIs with dynamic weight conditions calculated successfully!")

        # Fixed Preview Columns to match this specific sheet (Pre-Approvals)
        preview_cols = ['SubmittedClaims', 'RejectionRate', 'InitialError%', '%ofSubmissionWithinDuedate', 'Performance']
        # Double check if these columns exist in the print block to avoid KeyError during test
        available_preview = [c for c in preview_cols if c in df_result.columns]

        print("\n--- Previewing Cleaned Results ---")
        print(df_result[available_preview].head(10))  # Showing 10 rows to see the difference

    except KeyError as e:
        print(f"❌ Testing Failed! Could not find column: {e}")
