import pandas as pd
import numpy as np  # Imported numpy for row-by-row conditional logic
from cleaned import clean_sheet_data

def process_preapprovals_offshore(file_path):
    # --- 1. Load and Clean Data ---
    sheet_name = "Pre-Approvals IP Offshore"
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    df = clean_sheet_data(df, sheet_name=sheet_name)
    
    # Standardize column names by removing ALL hidden whitespaces
    df.columns = df.columns.str.replace(r'\s+', '', regex=True)
    
    # --- 2. Fetch clean column names and fill NaNs with 0 ---
    # Ensure correct names after space removal (e.g., 'Submitted Claims' -> 'SubmittedClaims')
    submitted_claims_col = 'SubmittedClaims' if 'SubmittedClaims' in df.columns else 'SubmittedClaims'
    
    rejection_score = df['RejectionRate'].fillna(0) if 'RejectionRate' in df.columns else 0
    initial_error_score = df['InitialError%'].fillna(0) if 'InitialError%' in df.columns else 0
    sub_score = df[f'%ofSubmissionWithinDuedate'].fillna(0) if f'%ofSubmissionWithinDuedate' in df.columns else 0
    
    # --- 3. Dynamic Performance Weighting ---
    # Condition: Check row-by-row if Submitted Claims is equal to 0 (or empty/NaN)
    is_claims_zero = (df[submitted_claims_col].fillna(0) == 0)
    
    # Dynamic Rejection Weight: 60% if claims == 0, else 50%
    weight_rejection = np.where(is_claims_zero, 0.60, 0.50)
    
    # Dynamic Initial Error Weight: 0% if claims == 0, else 20%
    weight_initial_error = np.where(is_claims_zero, 0.00, 0.20)
    
    # Dynamic Submission Weight: 40% if claims == 0, else 30%
    weight_submission = np.where(is_claims_zero, 0.40, 0.30)
    
    # Apply Final Formula with Dynamic Weights
    df['Performance'] = (
        (rejection_score * weight_rejection) +
        (initial_error_score * weight_initial_error) +
        (sub_score * weight_submission)
    )
    
    return df

# --- 4. Execution and Testing Block ---
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    try:
        df_result = process_preapprovals_offshore(r"D:\Trend\PMS_Trend_All.xlsx")
        print("✅ Pre-Approvals KPIs with dynamic weight conditions calculated successfully!")
        
        # Fixed Preview Columns to match this specific sheet (Pre-Approvals)
        preview_cols = ['SubmittedClaims', 'RejectionRate', 'InitialError%', '%ofSubmissionWithinDuedate', 'Performance']
        # Double check if these columns exist in the print block to avoid KeyError during test
        available_preview = [c for c in preview_cols if c in df_result.columns]
        
        print("\n--- Previewing Cleaned Results ---")
        print(df_result[available_preview].head(10))  # Showing 10 rows to see the difference
        
    except KeyError as e:
        print(f"❌ Testing Failed! Could not find column: {e}")