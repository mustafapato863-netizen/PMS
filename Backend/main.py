import sys
import io
import pandas as pd
import numpy as np

# Import team-specific processing functions
from Data_Cleaning_Teams.inbound import process_inbound
from Data_Cleaning_Teams.outbound import process_outbound
from Data_Cleaning_Teams.inbound_UAE import process_inbound_uae
from Data_Cleaning_Teams.preapprovals_offshore import process_preapprovals_offshore
from Data_Cleaning_Teams.sales import process_sales

# Force UTF-8 encoding for console output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

file_path = r"D:\Trend\PMS_Trend_All.xlsx"
cropped_sheets = {}

# ============================================
# RUN PROCESSING FOR ALL TEAMS
# ============================================
cropped_sheets["Inbound"] = process_inbound(file_path)
cropped_sheets["Outbound"] = process_outbound(file_path)
cropped_sheets["Inbound UAE"] = process_inbound_uae(file_path)
cropped_sheets["Pre-Approvals IP Offshore"] = process_preapprovals_offshore(file_path)
cropped_sheets["Sales"] = process_sales(file_path)

print("\n" + "="*50)
print("✓ All sheets processed successfully")
print("="*50)

# ============================================
# OPTIONAL: Show summary of each sheet
# ============================================
if __name__ == "__main__":
    print("\n📊 DATA TYPES SUMMARY:")
    print("="*50)
    for sheet_name, df in cropped_sheets.items():
        print(f"\n📁 {sheet_name}:")
        print(f"   Rows: {len(df)}")
        print(f"   Columns: {len(df.columns)}")
        
        # Show numeric columns
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if numeric_cols:
            print(f"   Numeric columns: {numeric_cols[:5]}..." if len(numeric_cols) > 5 else f"   Numeric columns: {numeric_cols}")
        
        # Show percentage columns
        pct_cols = [col for col in df.columns if '%' in col]
        if pct_cols:
            print(f"   Percentage columns: {pct_cols}")