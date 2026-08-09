import pandas as pd
import numpy as np
from cleaned import clean_sheet_data
from utils import add_computed_columns


def process_inbound(file_path):
    # --- 1. Load and Clean Data ---
    sheet_name = "Inbound"
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    df = clean_sheet_data(df, sheet_name=sheet_name)
    
    # Standardize column names by removing ALL hidden whitespaces
    df.columns = df.columns.str.replace(r'\s+', '', regex=True)
    
    # --- 2. Dynamic Column Selection (For Trend Raw Volume Sum Only) ---
    start_booking_idx = df.columns.get_loc('Dubai_Booking')
    start_attend_idx = df.columns.get_loc('Dubai_Attend')
    
    booking_cols = df.columns[start_booking_idx : start_booking_idx + 4]
    attend_cols = df.columns[start_attend_idx : start_attend_idx + 4]
    
    # Trend Columns: Summing the raw volumes
    df['Total_Booking_Trend'] = df[booking_cols].sum(axis=1)
    df['Total_Attend_Trend'] = df[attend_cols].sum(axis=1)
    
    # --- 3. Performance Calculation (Using Cleaned Ach% Columns) ---
    # Static Weights
    W_ATTEND = 0.70   # 70%
    W_BOOKING = 0.10  # 10%
    W_AHT = 0.05      # 5%
    
    # Dynamic weights for Quality and UTZ/Abandon for June 2026 only
    is_june_26 = (df['Date'].dt.month == 6) & (df['Date'].dt.year == 2026)
    w_quality = np.where(is_june_26, 0.0, 0.05)
    w_dynamic = np.where(is_june_26, 0.15, 0.10)
    
    # Fetch clean column names and immediately fill NaNs with 0 to secure calculation
    attend_cr = df['Attend%Ach%'].fillna(0) if 'Attend%Ach%' in df.columns else 0
    booking_cr = df['Booking%Ach%'].fillna(0) if 'Booking%Ach%' in df.columns else 0
    quality_score = df['QualityTargetAch%'].fillna(0) if 'QualityTargetAch%' in df.columns else 0
    aht_score = df['AHTAch%'].fillna(0) if 'AHTAch%' in df.columns else 0
    
    # Prepare the two swappable KPI columns
    utz_series = df['UTZ%Ach%'] if 'UTZ%Ach%' in df.columns else pd.Series(np.nan, index=df.index)
    abandon_series = df['AbandonRate%Ach%'] if 'AbandonRate%Ach%' in df.columns else pd.Series(np.nan, index=df.index)
    
    # NEW LOGIC: If UTZ is NaN/Empty -> Use Abandon. Otherwise -> Use UTZ.
    # We also apply .fillna(0) at the end just in case BOTH are empty for a row.
    dynamic_kpi = np.where(
        utz_series.isna(), 
        abandon_series, 
        utz_series
    )
    dynamic_kpi = pd.Series(dynamic_kpi, index=df.index).fillna(0)
    
    # Apply Final Weights Formula
    df['Performance'] = (
        (attend_cr * W_ATTEND) +
        (booking_cr * W_BOOKING) +
        (quality_score * w_quality) +
        (aht_score * W_AHT) +
        (dynamic_kpi * w_dynamic)
    )
    
    df = add_computed_columns(df)
    return df

# --- 4. Execution and Testing Block ---
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    try:
        df_result = process_inbound(r"D:\Trend\PMS_Trend_All.xlsx")
        print("✅ KPIs and Automatic Performance Swapping calculated successfully!")
        
        # Preview results
        preview_cols = ['Attend%Ach%', 'Booking%Ach%', 'Performance', 'Total_Booking_Trend']
        print("\n--- Previewing Cleaned Results ---")
        print(df_result[preview_cols].head())
        
    except KeyError as e:
        print(f"❌ Testing Failed! Could not find column: {e}")