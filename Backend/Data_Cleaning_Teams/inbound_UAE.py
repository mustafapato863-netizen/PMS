import pandas as pd
import numpy as np
from cleaned import clean_sheet_data

def process_inbound_uae(file_path):
    # --- 1. Load and Clean Data ---
    sheet_name = "Inbound UAE"
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
    W_BOOKING = 0.20  # 20%
    W_ABANDON = 0.10  # 10%
    
    # Fetch clean column names and immediately fill NaNs with 0 to secure calculation
    attend_cr = df['AttendC.RAch%'].fillna(0) if 'AttendC.RAch%' in df.columns else 0
    booking_cr = df['BookingC.RAch%'].fillna(0) if 'BookingC.RAch%' in df.columns else 0
    abandon_score = df['AbandonRateAch%'].fillna(0) if 'AbandonRateAch%' in df.columns else 0
    
    # Apply Final Weights Formula
    df['Performance'] = (
        (attend_cr * W_ATTEND) +
        (booking_cr * W_BOOKING) +
        (abandon_score * W_ABANDON)
    )
    
    return df

# --- 4. Execution and Testing Block ---
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    try:
        df_result = process_inbound_uae(r"D:\Trend\PMS_Trend_All.xlsx")
        print("✅ KPIs and Automatic Performance Swapping calculated successfully!")
        
        # Preview results
        preview_cols = ['AttendC.RAch%', 'BookingC.RAch%', 'Performance', 'Total_Booking_Trend']
        print("\n--- Previewing Cleaned Results ---")
        print(df_result[preview_cols].head())
        
    except KeyError as e:
        print(f"❌ Testing Failed! Could not find column: {e}")