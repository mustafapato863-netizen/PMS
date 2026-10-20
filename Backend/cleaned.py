import logging

import pandas as pd

from services.outbound_period_basis import is_outbound_sheet, is_productivity_column
from utils import convert_aht_to_minutes, convert_percentage


logger = logging.getLogger(__name__)

_PRESERVED_OUTBOUND_UTILIZATION_COLUMNS = frozenset(
    {
        "a.utilization%",
        "t.utilization%",
        "utilization%ach",
        "utilization%ach%",
    }
)

_IGNORED_OUTBOUND_RAW_COLUMNS = frozenset(
    {
        "utliztion%",
    }
)


def _compact_header(name) -> str:
    return "".join(ch for ch in str(name or "").strip().casefold() if not ch.isspace())


def _is_preserved_post_grade_column(column) -> bool:
    return is_productivity_column(column) or (
        _compact_header(column) in _PRESERVED_OUTBOUND_UTILIZATION_COLUMNS
    )


def drop_ignored_outbound_columns(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    """Drop legacy unused/misspelled Outbound columns (such as 'Utliztion %') so they are ignored."""
    if not is_outbound_sheet(sheet_name):
        return df
    ignored = [col for col in df.columns if _compact_header(col) in _IGNORED_OUTBOUND_RAW_COLUMNS]
    if not ignored:
        return df
    attrs = dict(getattr(df, "attrs", {}) or {})
    cleaned = df.drop(columns=ignored)
    cleaned.attrs.update(attrs)
    return cleaned


def preserve_productivity_columns(df, column_name="Performance Grade"):
    """Keep known productivity/utilization aliases that sit after the crop column.

    The crop is exact. A junk column after the grade stays dropped. Available
    time is not a productivity alias, so it is not reattached.
    """
    if column_name not in df.columns:
        return df
    col_index = df.columns.get_loc(column_name)
    preserved = {
        column: df[column].copy()
        for column in df.columns
        if _is_preserved_post_grade_column(column) and df.columns.get_loc(column) > col_index
    }
    cropped = df.iloc[:, : col_index + 1].copy()
    for column, series in preserved.items():
        cropped[column] = series
    return cropped


def clean_sheet_data(df, sheet_name, column_name="Performance Grade"):
    """
    Apply the shared legacy cleaning process without writing to stdout.

    Upload processing runs in Windows services and test shells where the console
    encoding may not support decorative Unicode characters, so diagnostics use
    structured logging only.
    """
    from services.upload_header_notices import attach_header_notices

    logger.debug("Processing sheet: %s", sheet_name)
    source_headers = list(df.columns)
    header_notices = attach_header_notices(df, sheet_name, source_headers)

    df.columns = [str(col).strip() for col in df.columns]

    if column_name in df.columns:
        df = preserve_productivity_columns(df, column_name)
        logger.debug("Cropped %s to %s columns", sheet_name, df.shape[1])

    df = drop_ignored_outbound_columns(df, sheet_name)

    for col in df.columns:
        if col == "AHT":
            df["AHT_Minutes"] = df[col].apply(convert_aht_to_minutes)
        elif "%" in col:
            df[col] = df[col].apply(convert_percentage)
        elif col == "Performance Score":
            df[col] = pd.to_numeric(df[col], errors="coerce")
        elif col == "Date":
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")

    if "Status" in df.columns:
        df["Is_Inactive"] = df["Status"].str.lower().str.contains("inactive", na=False)
        df["Is_New"] = df["Status"].str.lower().str.contains("new", na=False)
    else:
        df["Is_New"] = False

    # Cropping can replace the frame. Keep the pre-crop header notice on the
    # frame that callers score, without putting dropped columns back.
    df.attrs["column_warnings"] = header_notices
    df.attrs["source_header_names"] = [
        str(column) for column in source_headers if str(column).strip()
    ]
    return df
