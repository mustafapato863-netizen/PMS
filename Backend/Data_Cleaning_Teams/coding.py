"""
Coding Team Data Cleaner

Handles Coding team data standardization and KPI calculation.
All 3 KPIs are inverse (lower is better).
Each achievement is capped at 100% before weighting.
Performance score = MIN(100%, Σ(capped_achievement_i × weight_i))
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, Optional
from data_cleaning.standard_mappings import calculate_achievement, calculate_grade

logger = logging.getLogger(__name__)


def parse_numeric(value: Any) -> float:
    """
    Parse numeric value from various formats.
    
    Args:
        value: Value to parse
        
    Returns:
        Float value
    """
    if pd.isna(value):
        return 0.0
    
    if isinstance(value, str):
        # Remove commas and convert
        value = value.replace(',', '').strip()
        try:
            return float(value)
        except (ValueError, AttributeError):
            logger.warning(f"Could not parse numeric value: {value}")
            return 0.0
    else:
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse numeric value: {value}")
            return 0.0


def process_coding(file_path: str, team_config: Dict[str, Any] = None) -> pd.DataFrame:
    """
    Process Coding team Excel data.
    
    Performs:
    1. Data standardization (column names, data types)
    2. Numeric parsing
    3. KPI achievement calculations (all 3 inverse KPIs, capped at 100%)
    4. Performance score calculation (capped at 100%)
    5. Grade assignment
    
    Args:
        file_path: Path to Excel file
        team_config: Optional team configuration dict with KPI definitions
        
    Returns:
        DataFrame with calculated KPI values and performance score
    """
    from cleaned import clean_sheet_data
    from utils import add_computed_columns
    
    # Load and clean basic data
    sheet_name = "Coding"
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    df = clean_sheet_data(df, sheet_name=sheet_name)
    
    # Standardize column names: remove all whitespace
    df.columns = df.columns.str.replace(r'\s+', '', regex=True)
    
    logger.info(f"Loaded Coding data with {len(df)} rows and columns: {list(df.columns)}")
    
    # KPI Definitions and Weights (Coding: all inverse, all capped at 100%)
    kpis = {
        'QualityErrors': {
            'actual_col': 'A.QualityErrorsRate',
            'target_col': 'T.QualityErrorsRate',
            'is_inverse': True,
            'weight': 0.20,
            'cap': True,
        },
        'Rejection': {
            'actual_col': 'A.RejectionRate',
            'target_col': 'T.RejectionRate',
            'is_inverse': True,
            'weight': 0.50,
            'cap': True,
        },
        'TAT': {
            'actual_col': 'A.TAT',
            'target_col': 'T.TAT',
            'is_inverse': True,
            'weight': 0.30,
            'cap': True,
        },
    }
    
    # Grade thresholds
    thresholds = {
        'A': 95,
        'B': 85,
        'C': 75,
        'D': 65,
    }
    
    # Calculate achievements for each KPI
    achievement_cols = {}
    
    for kpi_key, kpi_def in kpis.items():
        actual_col = kpi_def['actual_col']
        target_col = kpi_def['target_col']
        
        # Find columns (case insensitive)
        actual_found = None
        target_found = None
        
        for col in df.columns:
            if col.lower() == actual_col.lower():
                actual_found = col
            if col.lower() == target_col.lower():
                target_found = col
        
        if actual_found and target_found:
            # Parse actual and target values
            actuals = df[actual_found].apply(parse_numeric)
            targets = df[target_found].apply(parse_numeric)
            
            # Calculate achievements (capped at 100%)
            achievements = np.array([
                calculate_achievement(
                    actuals.iloc[i],
                    targets.iloc[i],
                    is_inverse=kpi_def['is_inverse'],
                    cap_at_100=kpi_def['cap']
                )
                for i in range(len(df))
            ])
            
            achievement_cols[kpi_key] = achievements
            df[f'{kpi_key}_Achievement'] = achievements
            logger.info(f"Calculated {kpi_key} achievement (inverse={kpi_def['is_inverse']}, capped)")
        else:
            logger.warning(f"Could not find columns for {kpi_key}: actual={actual_col}, target={target_col}")
            achievement_cols[kpi_key] = np.zeros(len(df))
            df[f'{kpi_key}_Achievement'] = 0.0
    
    # Calculate performance score: MIN(100%, Σ(achievement_i × weight_i))
    performance_scores = np.zeros(len(df))
    
    for kpi_key, achievement in achievement_cols.items():
        weight = kpis[kpi_key]['weight']
        performance_scores += achievement * weight
    
    # Cap final score at 100%
    performance_scores = np.minimum(performance_scores, 100.0)
    
    df['Performance'] = performance_scores
    
    df['Grade'] = df['Performance'].apply(lambda score: calculate_grade(score, thresholds))
    
    # Map to standard system columns
    for col in ['PerformanceScore', 'Performance_Score']:
        if col in df.columns:
            df[col] = df['Performance']
    
    # Apply standard computed columns
    df = add_computed_columns(df)
    
    logger.info(f"Coding processing complete. Performance scores range: {df['Performance'].min():.2f} - {df['Performance'].max():.2f}")
    
    return df


if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    try:
        df_result = process_coding(r"D:\Projects\Coding_Data.xlsx")
        print("✅ Coding KPIs calculated successfully!")
        
        preview_cols = [c for c in ['QualityErrors_Achievement', 'Rejection_Achievement', 'TAT_Achievement', 'Performance', 'Grade'] if c in df_result.columns]
        print("\n--- Previewing Cleaned Coding Results ---")
        print(df_result[preview_cols].head())
        
    except Exception as e:
        print(f"❌ Testing Failed! Error: {e}")
        import traceback
        traceback.print_exc()
