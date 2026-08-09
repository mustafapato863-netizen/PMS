import pandas as pd
import numpy as np
from cleaned import clean_sheet_data
from utils import add_computed_columns


def process_sales(file_path):
    # --- 1. Load and Clean Data ---
    sheet_name = "Sales"
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    df = clean_sheet_data(df, sheet_name=sheet_name)
    
    # Standardize column names by removing ALL hidden whitespaces
    df.columns = df.columns.str.replace(r'\s+', '', regex=True)
    
    # --- 2. Helper to Parse Percentages Safely to 0-100 Scale ---
    def parse_percentage_col(col_name):
        # Fallback to search for closest matching column name if exact not found
        if col_name not in df.columns:
            matched = [c for c in df.columns if col_name.replace('%', '') in c]
            if matched:
                col_name = matched[0]
            else:
                return pd.Series(0.0, index=df.index)
        
        series = df[col_name].fillna(0)
        if series.dtype == object:
            series = series.astype(str).str.rstrip('%').str.replace(',', '')
            series = pd.to_numeric(series, errors='coerce').fillna(0)
        else:
            series = pd.to_numeric(series, errors='coerce').fillna(0)
            # If already fraction format (e.g. 0.94 instead of 94), scale up to 100
            if series.max() <= 2.0 and (series > 0).any():
                series = series * 100.0
        return series

    # --- 3. Dynamic Activity Engine Calculation ---
    # Keywords for the 4 core activity components
    activity_keywords = ['ClinicActivity', 'CorporateActivity', 'CBDTour', 'Visits']
    
    # Extract all matching activity columns (excluding Ach% columns)
    all_act_cols = [c for c in df.columns if any(k in c for k in activity_keywords) and 'Ach%' not in c]
    
    # Separate Targets (T.) and Actuals (A.) dynamically
    if any(c.startswith('T.') for c in all_act_cols) or any(c.startswith('A.') for c in all_act_cols):
        t_act_cols = [c for c in all_act_cols if c.startswith('T.')]
        a_act_cols = [c for c in all_act_cols if c.startswith('A.')]
    else:
        # Fallback if pandas auto-appended suffixes for duplicate columns (e.g. .1, .2)
        t_act_cols = [c for c in all_act_cols if not c.endswith('.1') and not c.endswith('.2')]
        a_act_cols = [c for c in all_act_cols if c.endswith('.1') or c.endswith('.2')]
        
        # Safe split half-half if lengths mismatch
        if len(t_act_cols) != len(a_act_cols):
            half = len(all_act_cols) // 2
            t_act_cols = all_act_cols[:half]
            a_act_cols = all_act_cols[half:]

    # Ensure columns are numeric before calculation
    for col in t_act_cols + a_act_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # Calculate Sums
    sum_actual_activity = df[a_act_cols].sum(axis=1)
    sum_target_activity = df[t_act_cols].sum(axis=1)
    
    # Safe division to get the activity achievement ratio
    activity_ratio = np.where(
        sum_target_activity > 0,
        sum_actual_activity / sum_target_activity,
        0.0
    )
    
    # Apply formula: MIN(10 points, ratio * 10 points) which matches MIN(0.1, ratio * 0.1) on a 100 scale
    activity_score = np.minimum(10.0, activity_ratio * 10.0)

    # Standardize column names by removing ALL hidden whitespaces
    df.columns = df.columns.str.replace(r'\s+', '', regex=True)

    # Update activities achievement columns with the calculated ratio
    for col in ['SalesActivtiesAch%', 'SalesActivitiesAch%']:
        if col in df.columns:
            df[col] = activity_ratio

    # --- 4. Performance Calculation (Using Defined Weights and Dynamic Ratios) ---
    W_OP_Cencus = 0.10    # 10%
    W_OP_Revenue = 0.10   # 10%
    W_IP_Cencus = 0.25    # 25%
    W_IP_Revenue = 0.45   # 45%
    
    # Dynamic achievement calculation: actuals / targets
    def calculate_kpi_ach(a_col, t_col, ach_col):
        if a_col in df.columns and t_col in df.columns:
            a_series = pd.to_numeric(df[a_col], errors='coerce').fillna(0)
            t_series = pd.to_numeric(df[t_col], errors='coerce').fillna(0)
            ratio = np.where(t_series > 0, a_series / t_series, 0.0)
            df[ach_col] = ratio
            return ratio * 100.0
        else:
            return parse_percentage_col(ach_col)

    op_census_ach = calculate_kpi_ach('A.OPCensus', 'T.OPCensus', 'OPCensusAch%')
    op_revenue_ach = calculate_kpi_ach('A.OPRevenue', 'T.OPRevenue', 'OPRevenueAch%')
    ip_census_ach = calculate_kpi_ach('A.IPCensus', 'T.IPCensus', 'IPCensusAch%')
    ip_revenue_ach = calculate_kpi_ach('A.IPRevenue', 'T.IPRevenue', 'IPRevenueAch%')
    
    # Final Weighted Performance Formula (Score out of 100)
    df['Performance'] = (
        (op_census_ach * W_OP_Cencus) +
        (op_revenue_ach * W_OP_Revenue) +
        (ip_census_ach * W_IP_Cencus) +
        (ip_revenue_ach * W_IP_Revenue) +
        activity_score
    )
    
    # Map back to standard system columns for downstream processing
    for target_score_col in ['PerformanceScore', 'Performance_Score']:
        if target_score_col in df.columns:
            df[target_score_col] = df['Performance']
            
    # Apply grade/class generation mapping rules
    df = add_computed_columns(df)
    return df


# --- 5. Execution and Testing Block ---
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    try:
        # Adjusted to call process_sales directly
        df_result = process_sales(r"D:\Trend\PMS_Trend_All.xlsx")
        print("✅ Sales KPIs and Dynamic Activity Scores calculated successfully!")
        
        # Dynamically select preview columns that exist in the dataframe
        available_cols = [c for c in ['OPCensusAch%', 'OPRevenueAch%', 'Performance', 'Class'] if c in df_result.columns]
        
        print("\n--- Previewing Cleaned Sales Results ---")
        print(df_result[available_cols].head())
        
    except Exception as e:
        print(f"❌ Testing Failed! Error detail: {e}")