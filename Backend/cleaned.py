import logging

import pandas as pd

from utils import convert_aht_to_minutes, convert_percentage


logger = logging.getLogger(__name__)


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
        col_index = df.columns.get_loc(column_name)
        df = df.iloc[:, :col_index + 1]
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
