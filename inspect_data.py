import pandas as pd
import sys

file_path = r"c:\Users\chenq\Documents\trae_projects\pici_daily_newspaper\20251218\临泉第一育肥场二分场保育舍4-1单元 2025-12-18 00_00_00 至 2026-02-05 23_59_59 环境数据.xlsx"

df = pd.read_excel(file_path, sheet_name='单元信息')
print(f"Total rows: {len(df)}")

cols = df.columns.tolist()
temp_cols = [c for c in cols if '温度' in str(c) or '湿度' in str(c) or '目标' in str(c)]
print(f"Temperature/humidity columns: {temp_cols}")

print("\nFirst 5 rows of these columns:")
print(df[temp_cols].head(5).to_string())

print("\n\nLast 5 rows of these columns:")
print(df[temp_cols].tail(5).to_string())

print("\n\nUnique target temperatures:")
print(df['目标温度(℃)'].unique()[:10])

print("\n\nUnique target humidities:")
print(df['目标湿度(%)'].unique()[:10])
