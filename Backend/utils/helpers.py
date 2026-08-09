import datetime
import math
import numpy as np
import pandas as pd

def convert_aht_to_minutes(aht_value) -> float:
    """Convert AHT from HH:MM:SS or excel time/float to minutes (float)."""
    if pd.isna(aht_value):
        return 0.0
    try:
        if isinstance(aht_value, str):
            parts = aht_value.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                return float(hours * 60 + minutes + seconds / 60)
            elif len(parts) == 2:
                minutes = int(parts[0])
                seconds = int(parts[1])
                return float(minutes + seconds / 60)
        elif isinstance(aht_value, (int, float)):
            # If Excel time fraction
            if aht_value < 1:
                return float(aht_value * 24 * 60)
            else:
                return float(aht_value / 60)
        elif isinstance(aht_value, datetime.time):
            return float(aht_value.hour * 60 + aht_value.minute + aht_value.second / 60)
    except Exception:
        pass
    return 0.0

def convert_percentage(col_value) -> float:
    """Convert percentage (string with % or decimal) to float (0-1 range)."""
    if pd.isna(col_value):
        return np.nan
    try:
        if isinstance(col_value, str):
            col_value = col_value.replace('%', '').strip()
            val = float(col_value)
            if val > 2.0:
                return val / 100.0
            return val
        elif isinstance(col_value, (int, float)):
            if col_value > 2.0:
                return float(col_value / 100.0)
            return float(col_value)
    except Exception:
        pass
    return np.nan

def safe_value(val):
    """Convert a pandas/numpy value to a JSON-serializable Python type."""
    if val is None:
        return None
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        v = float(val)
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(val, (np.bool_, bool)):
        return bool(val)
    if isinstance(val, (pd.Timestamp, datetime.datetime)):
        return val.isoformat()
    if isinstance(val, datetime.date):
        return val.isoformat()
    if isinstance(val, datetime.time):
        return val.strftime("%H:%M:%S")
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    return val

def df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame to a list of JSON-safe dictionaries."""
    records = []
    for _, row in df.iterrows():
        record = {str(col): safe_value(row[col]) for col in df.columns}
        records.append(record)
    return records

def format_minutes_to_hhmmss(minutes: float) -> str:
    """Convert minutes (float) to HH:MM:SS string format."""
    if not minutes or minutes <= 0 or math.isnan(minutes):
        return "00:00:00"
    try:
        total_secs = int(round(minutes * 60))
        h, rem = divmod(total_secs, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    except Exception:
        return "00:00:00"

def add_computed_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add computed columns:
    - Performance Grade (based on score: >=0.9 = "Exceeds", >=0.8 = "Meet", >=0.7 = "Average", else "Below")
    - Suggested Action (simple logic: score>=0.9="Reward", score<0.7="PIP", else="Monitor")
    """
    if 'Performance' in df.columns:
        scores = df['Performance'].copy()
        
        # If scores are on a 0-100 scale (values > 2.0), scale down to 0-1 for grading
        if scores.max() > 2.0:
            scores = scores / 100.0
            
        # Calculate Performance Grade
        conditions_grade = [
            scores >= 0.9,
            scores >= 0.8,
            scores >= 0.7
        ]
        choices_grade = ["Exceeds", "Meet", "Average"]
        df['PerformanceGrade'] = np.select(conditions_grade, choices_grade, default="Below")
        
        # Calculate Suggested Action
        conditions_action = [
            scores >= 0.9,
            scores < 0.7
        ]
        choices_action = ["Reward", "PIP"]
        df['SuggestedAction'] = np.select(conditions_action, choices_action, default="Monitor")
        
    return df

