#!/usr/bin/env python3
"""
Script to inspect Excel files for ICAP and TDA data.
This helps understand the structure before creating ETL loaders.
"""
import pandas as pd
import sys
import os

def inspect_icap():
    """Inspect ICAP_Bancos.xlsx structure."""
    file_path = "/home/jazielflo/Proyects/octavios-chat-bajaware_invex/plugins/bank-advisor-private/data/raw/ICAP_Bancos.xlsx"

    print("=" * 80)
    print("INSPECTING: ICAP_Bancos.xlsx")
    print("=" * 80)

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    try:
        # Get sheet names
        xl_file = pd.ExcelFile(file_path)
        print(f"\n📋 Sheet Names: {xl_file.sheet_names}")

        # Read first sheet
        df = pd.read_excel(file_path, sheet_name=0)

        print(f"\n📊 Shape: {df.shape} (rows, columns)")
        print(f"\n📝 Columns:\n{df.columns.tolist()}")
        print(f"\n🔍 First 10 rows:")
        print(df.head(10))
        print(f"\n📈 Data types:")
        print(df.dtypes)
        print(f"\n📉 Sample values for key columns:")

        # Try to identify date and bank columns
        for col in df.columns:
            col_lower = str(col).lower()
            if 'fecha' in col_lower or 'date' in col_lower or 'periodo' in col_lower:
                print(f"\n  {col}: {df[col].unique()[:5]}")
            if 'banco' in col_lower or 'institucion' in col_lower or 'bank' in col_lower:
                print(f"\n  {col}: {df[col].unique()[:5]}")
            if 'icap' in col_lower or 'cap' in col_lower:
                print(f"\n  {col}: {df[col].describe()}")

    except Exception as e:
        print(f"❌ Error reading ICAP file: {e}")

def inspect_tda():
    """Inspect TDA.xlsx structure."""
    file_path = "/home/jazielflo/Proyects/octavios-chat-bajaware_invex/plugins/bank-advisor-private/data/raw/TDA.xlsx"

    print("\n" + "=" * 80)
    print("INSPECTING: TDA.xlsx")
    print("=" * 80)

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    try:
        # Get sheet names
        xl_file = pd.ExcelFile(file_path)
        print(f"\n📋 Sheet Names: {xl_file.sheet_names}")

        # Read first sheet
        df = pd.read_excel(file_path, sheet_name=0)

        print(f"\n📊 Shape: {df.shape} (rows, columns)")
        print(f"\n📝 Columns:\n{df.columns.tolist()}")
        print(f"\n🔍 First 10 rows:")
        print(df.head(10))
        print(f"\n📈 Data types:")
        print(df.dtypes)
        print(f"\n📉 Sample values for key columns:")

        # Try to identify date and bank columns
        for col in df.columns:
            col_lower = str(col).lower()
            if 'fecha' in col_lower or 'date' in col_lower or 'periodo' in col_lower:
                print(f"\n  {col}: {df[col].unique()[:5]}")
            if 'banco' in col_lower or 'institucion' in col_lower or 'bank' in col_lower:
                print(f"\n  {col}: {df[col].unique()[:5]}")
            if 'tda' in col_lower or 'deterioro' in col_lower:
                print(f"\n  {col}: {df[col].describe()}")

    except Exception as e:
        print(f"❌ Error reading TDA file: {e}")

def inspect_csv_sample():
    """Inspect CorporateLoan_CNBVDB.csv structure (first 100 rows)."""
    file_path = "/home/jazielflo/Proyects/octavios-chat-bajaware_invex/plugins/bank-advisor-private/data/raw/CorporateLoan_CNBVDB.csv"

    print("\n" + "=" * 80)
    print("INSPECTING: CorporateLoan_CNBVDB.csv (sample)")
    print("=" * 80)

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    try:
        # Read only first 100 rows
        df = pd.read_csv(file_path, nrows=100)

        print(f"\n📊 Shape (sample): {df.shape} (rows, columns)")
        print(f"\n📝 Columns:\n{df.columns.tolist()}")
        print(f"\n🔍 First 5 rows:")
        print(df.head(5))
        print(f"\n📈 Data types:")
        print(df.dtypes)

        # Look for INVEX data
        print(f"\n🔎 Searching for INVEX data...")
        if 'Institution' in df.columns:
            invex_rows = df[df['Institution'].str.contains('INVEX', case=False, na=False)]
            print(f"  Found {len(invex_rows)} INVEX rows in sample")
            if len(invex_rows) > 0:
                print(f"\n  Sample INVEX data:")
                print(invex_rows.head())

        # Look for rate columns
        print(f"\n📊 Rate-related columns:")
        for col in df.columns:
            col_lower = str(col).lower()
            if 'rate' in col_lower or 'tasa' in col_lower:
                print(f"  {col}: {df[col].describe()}")

        # Currency info
        if 'Currency' in df.columns or 'Currency type' in df.columns:
            currency_col = 'Currency type' if 'Currency type' in df.columns else 'Currency'
            print(f"\n💱 Currency values: {df[currency_col].unique()}")

    except Exception as e:
        print(f"❌ Error reading CSV file: {e}")

if __name__ == "__main__":
    inspect_icap()
    inspect_tda()
    inspect_csv_sample()
    print("\n✅ Inspection complete!")
