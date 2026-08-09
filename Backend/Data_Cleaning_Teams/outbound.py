import pandas as pd
import numpy as np
from cleaned import clean_sheet_data
from utils import add_computed_columns

def process_outbound(file_path):
    # --- 1. Load and Clean Data ---
    sheet_name = "Outbound"
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    df = clean_sheet_data(df, sheet_name=sheet_name)
      
    # Standardize column names by removing ALL hidden whitespaces
    df.columns = df.columns.str.replace(r'\s+', '', regex=True)
    
    # --- 2. Dynamic Column Selection (For Trend Raw Volume Sum Only) ---
    start_booking_idx = df.columns.get_loc('Dubai_Booking') if 'Dubai_Booking' in df.columns else -1
    start_attend_idx = df.columns.get_loc('Dubai_Attend') if 'Dubai_Attend' in df.columns else -1
    
    if start_booking_idx >= 0:
        booking_cols = df.columns[start_booking_idx : start_booking_idx + 4]
        df['Total_Booking_Trend'] = df[booking_cols].sum(axis=1)
    else:
        df['Total_Booking_Trend'] = 0
        
    if start_attend_idx >= 0:
        attend_cols = df.columns[start_attend_idx : start_attend_idx + 4]
        df['Total_Attend_Trend'] = df[attend_cols].sum(axis=1)
    else:
        df['Total_Attend_Trend'] = 0
    
    # --- 3. Performance Calculation (Using Cleaned Ach% Columns) ---
    # Static Weights
    W_ATTEND = 0.70   # 70%
    W_BOOKING = 0.10  # 10%
    # Dynamic June 2026 Weights Override (Quality = 0%, Reachability = 20%)
    is_june_26 = (df['Date'].dt.month == 6) & (df['Date'].dt.year == 2026) if 'Date' in df.columns else False
    
    w_quality = pd.Series(0.10, index=df.index)
    w_reachability = pd.Series(0.10, index=df.index)
    
    if isinstance(is_june_26, pd.Series):
        w_quality[is_june_26] = 0.00
        w_reachability[is_june_26] = 0.20
    
    # Fetch clean column names and immediately fill NaNs with 0 to secure calculation
    attend_cr = df['AttendC.RAch%'].fillna(0) if 'AttendC.RAch%' in df.columns else 0
    booking_cr = df['BookingC.RAch%'].fillna(0) if 'BookingC.RAch%' in df.columns else 0
    quality_score = df['QualityAch%'].fillna(0) if 'QualityAch%' in df.columns else 0
    reachability_score = df['Reachability%Ach%'].fillna(0) if 'Reachability%Ach%' in df.columns else 0
    
    # Apply Final Weights Formula
    df['Performance'] = (
        (attend_cr * W_ATTEND) +
        (booking_cr * W_BOOKING) +
        (quality_score * w_quality) +
        (reachability_score * w_reachability)
    )
    
    df = add_computed_columns(df)
    return df

# --- 4. Execution and Testing Block ---
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    try:
        df_result = process_outbound(r"D:\Trend\PMS_Trend_All.xlsx")
        print("✅ KPIs and Automatic Performance calculated successfully!")
        
        # Preview results
        preview_cols = ['AttendC.RAch%', 'BookingC.RAch%', 'Performance', 'Total_Booking_Trend', 'Total_Attend_Trend', 'QualityAch%', 'Reachability%Ach%']
        available_preview = [c for c in preview_cols if c in df_result.columns]
        print("\n--- Previewing Cleaned Results ---")
        print(df_result[available_preview].head())
        
    except KeyError as e:
        print(f"❌ Testing Failed! Could not find column: {e}")
