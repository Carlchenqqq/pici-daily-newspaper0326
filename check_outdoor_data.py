import pandas as pd
from datetime import datetime

file_path = r'c:\Users\chenq\Documents\trae_projects\pici_daily_newspaper\魏德曼二分场四线洪河桥一育肥猪20251218\临泉第一育肥场二分场保育舍4-1单元 2025-12-18 00_00_00 至 2026-02-05 23_59_59 环境数据.xlsx'

# 读取室外数据sheet
df = pd.read_excel(file_path, sheet_name='室外数据')

print('=== 室外数据列名 ===')
print(df.columns.tolist())
print()

print('=== 前10行数据 ===')
print(df.head(10))
print()

print('=== 数据类型 ===')
print(df.dtypes)
print()

print('=== 数据行数 ===')
print(f'Total rows: {len(df)}')
print()

# 检查第6列（F列，索引为5）
if len(df.columns) > 5:
    print('=== 第6列（F列）数据 ===')
    col_data = df.iloc[:, 5]
    print(f'Column name: {df.columns[5]}')
    print(f'First 10 values: {col_data.head(10).tolist()}')
    print()
    
    # 计算整个文件的平均值
    vals = pd.to_numeric(col_data, errors='coerce')
    print(f'整个文件平均值: {round(vals.mean(), 1)}')
    print(f'有效数据点: {vals.notna().sum()}')
    print()

# 检查是否有时间列
if '时间' in df.columns:
    print('=== 检测到时间列 ===')
    df['时间'] = pd.to_datetime(df['时间'], errors='coerce')
    print(f'开始时间: {df["时间"].min()}')
    print(f'结束时间: {df["时间"].max()}')
    print()
    
    # 筛选12月18日的数据
    target_date = datetime(2025, 12, 18).date()
    df['date'] = df['时间'].dt.date
    day_df = df[df['date'] == target_date]
    
    print(f'=== 2025-12-18 数据行数: {len(day_df)} ===')
    
    if len(df.columns) > 5:
        day_vals = pd.to_numeric(day_df.iloc[:, 5], errors='coerce')
        print(f'12月18日平均值: {round(day_vals.mean(), 1)}')
        print(f'有效数据点: {day_vals.notna().sum()}')
