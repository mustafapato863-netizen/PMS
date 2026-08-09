"""
Submission Team Data Cleaner

Handles Submission team data standardization and KPI calculation.
KPI 1: Initial Rejection Rate (inverse, lower_better, weight 60%)
KPI 2: Submission Within Due Date (direct, higher_better, weight 40%)
Both KPI achievements are capped at 100% before weighting.
Final performance score is capped at 100%.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Any
from data_cleaning.standard_mappings import calculate_achievement, calculate_grade
from utils.helpers import convert_percentage

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


def process_submission(file_path: str, team_config: Dict[str, Any] = None) -> pd.DataFrame:
    """
    Process Submission team Excel data.
    
    Performs:
    1. Data standardization (column names, data types)
    2. Derived A.InitialRejectionRate calculation safely
    3. Percentage parsing and scaling to 0-1 range
    4. KPI achievement calculations
    5. Performance score calculation (capped contribution model)
    6. Grade assignment
    
    Args:
        file_path: Path to Excel file
        team_config: Optional team configuration dict
        
    Returns:
        DataFrame with calculated KPI values and performance score
    """
    from cleaned import clean_sheet_data
    from utils import add_computed_columns
    
    sheet_name = "Submission"
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    df = clean_sheet_data(df, sheet_name=sheet_name)
    df = df.loc[~_should_exclude_row(df)].copy()
    
    # Standardize column names: remove all whitespace
    df.columns = df.columns.str.replace(r'\s+', '', regex=True)
    
    logger.info(f"Loaded Submission data with {len(df)} rows and columns: {list(df.columns)}")
    
    # Helper to parse and scale percentage columns consistently to 0-1 range
    def parse_to_ratio(val):
        parsed = convert_percentage(val)
        if pd.isna(parsed):
            return 0.0
        return parsed

    # T.InitialRejectionRate
    target_rej_col = 'T.InitialRejectionRate'
    if target_rej_col in df.columns:
        df[target_rej_col] = df[target_rej_col].apply(parse_to_ratio)
    else:
        df[target_rej_col] = 0.0

    # Calculate derived actual rejection rate:
    # A.Initial Rejection Rate = Rejected Claims Amount 3 Month Previous / RA Claims Amount (3 Month Previous)
    num_col = 'RejectedClaimsAmount3MonthPrevious'
    den_col = 'RAClaimsAmount(3MonthPrevious)'
    
    # Case-insensitive column matching
    for col in df.columns:
        if col.lower() == 'rejectedclaimsamount3monthprevious':
            num_col = col
        elif col.lower() == 'raclaimsamount(3monthprevious)':
            den_col = col

    if num_col in df.columns and den_col in df.columns:
        numerators = pd.to_numeric(df[num_col], errors='coerce').fillna(0.0)
        denominators = pd.to_numeric(df[den_col], errors='coerce').fillna(0.0)
        
        rejection_rates = []
        for n, d in zip(numerators, denominators):
            if d == 0.0:
                rejection_rates.append(0.0)
            else:
                rejection_rates.append(float(n / d))
        df['A.InitialRejectionRate'] = rejection_rates
    else:
        df['A.InitialRejectionRate'] = 0.0

    # A.TAT48Hours
    actual_tat_col = 'A.TAT48Hours'
    if actual_tat_col in df.columns:
        df[actual_tat_col] = df[actual_tat_col].apply(parse_to_ratio)
    else:
        df[actual_tat_col] = 0.0

    # T.%ofSubmissionWithinDuedate
    target_sub_col = 'T.%ofSubmissionWithinDuedate'
    if target_sub_col in df.columns:
        df[target_sub_col] = df[target_sub_col].apply(parse_to_ratio)
    else:
        df[target_sub_col] = 0.0

    # KPI Definitions and Weights
    kpis = {
        'initial_rejection_rate': {
            'actual_col': 'A.InitialRejectionRate',
            'target_col': 'T.InitialRejectionRate',
            'is_inverse': True,
            'weight': 0.60,
            'cap': True,
        },
        'submission_within_due_date': {
            'actual_col': 'A.TAT48Hours',
            'target_col': 'T.%ofSubmissionWithinDuedate',
            'is_inverse': False,
            'weight': 0.40,
            'cap': True,
        }
    }
    
    thresholds = {
        'A': 95,
        'B': 85,
        'C': 75,
        'D': 65,
    }
    
    achievement_cols = {}
    
    for kpi_key, kpi_def in kpis.items():
        actual_col = kpi_def['actual_col']
        target_col = kpi_def['target_col']
        
        actual_found = None
        target_found = None
        
        for col in df.columns:
            if col.lower() == actual_col.lower():
                actual_found = col
            if col.lower() == target_col.lower():
                target_found = col
                
        if actual_found and target_found:
            actuals = df[actual_found]
            targets = df[target_found]
            
            achievements = np.array([
                calculate_achievement(
                    actuals.iloc[i],
                    targets.iloc[i],
                    is_inverse=kpi_def['is_inverse'],
                    cap_at_100=kpi_def['cap']
                )
                for i in range(len(df))
            ])
        else:
            logger.warning(f"Could not find columns for {kpi_key}: actual={actual_col}, target={target_col}")
            achievements = np.zeros(len(df))
            
        achievement_cols[kpi_key] = achievements
        df[f'{kpi_key}_Achievement'] = achievements
        df[f'{kpi_key}Ach%'] = achievements
        logger.info(f"Calculated {kpi_key} achievement (inverse={kpi_def['is_inverse']})")
        
    # Calculate performance score: Σ(min(achievement_i, 100) * weight_i)
    performance_scores = np.zeros(len(df))
    for kpi_key, achievement in achievement_cols.items():
        weight = kpis[kpi_key]['weight']
        performance_scores += np.minimum(achievement, 100.0) * weight
        
    performance_scores = np.minimum(performance_scores, 100.0)
    df['Performance'] = performance_scores
    df['Grade'] = df['Performance'].apply(lambda score: calculate_grade(score, thresholds))
    
    # Map to standard system columns
    for col in ['PerformanceScore', 'Performance_Score']:
        if col in df.columns:
            df[col] = df['Performance']
            
    df = add_computed_columns(df)
    
    logger.info(f"Submission processing complete. Performance scores range: {df['Performance'].min():.2f} - {df['Performance'].max():.2f}")
    
    return df


if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    try:
        df_result = process_submission(r"D:\Projects\Submission_Data.xlsx")
        print("✅ Submission KPIs calculated successfully!")
        print(df_result.head())
    except Exception as e:
        print(f"❌ Testing Failed! Error: {e}")
