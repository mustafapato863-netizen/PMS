import logging

import pandas as pd

from services.outbound_period_basis import is_productivity_column
from utils import convert_aht_to_minutes, convert_percentage


logger = logging.getLogger(__name__)


def preserve_productivity_columns(df, column_name="Performance Grade"):
    """Keep known productivity aliases that sit after the crop column.

    The crop is exact. A junk column after the grade stays dropped. Available
    time is not a productivity alias, so it is not reattached.
    """
    if column_name not in df.columns:
        return df
    col_index = df.columns.get_loc(column_name)
    preserved = {
        column: df[column].copy()
        for column in df.columns
        if is_productivity_column(column) and df.columns.get_loc(column) > col_index
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
    logger.debug("Processing sheet: %s", sheet_name)

    df.columns = [str(col).strip() for col in df.columns]

    if column_name in df.columns:
        df = preserve_productivity_columns(df, column_name)
        logger.debug("Cropped %s to %s columns", sheet_name, df.shape[1])

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

    return df
