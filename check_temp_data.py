import pandas as pd
from datetime import datetime

file_path = r'c:\Users\chenq\Documents\trae_projects\pici_daily_newspaper\魏德曼二分场四线洪河桥一育肥猪20251218\临泉第一育肥场二分场保育舍4-1单元 2025-12-18 00_00_00 至 2026-02-05 23_59_59 环境数据.xlsx'

df = pd.read_excel(file_path, sheet_name='单元信息')

print('=== 列名 ===')
print(df.columns.tolist())
print()

print('=== 前5行数据 ===')
print(df.head())
print()

if '时间' in df.columns:
    df['时间'] = pd.to_datetime(df['时间'], errors='coerce')
    print('=== 时间范围 ===')
    print(f'开始时间: {df["时间"].min()}')
    print(f'结束时间: {df["时间"].max()}')
    print()
    
    target_date = datetime(2025, 12, 18).date()
    df['date'] = df['时间'].dt.date
    day_df = df[df['date'] == target_date]
    
    print(f'=== 2025-12-18 数据行数: {len(day_df)} ===')
    print()
    
    if '舍内温度(℃)' in day_df.columns:
        temps = pd.to_numeric(day_df['舍内温度(℃)'], errors='coerce')
        print('=== 舍内温度统计 ===')
        print(f'平均温度: {round(temps.mean(), 1)}')
        print(f'最高温度: {round(temps.max(), 1)}')
        print(f'最低温度: {round(temps.min(), 1)}')
        print(f'有效数据点: {temps.notna().sum()}')
        print()
        print('前20个温度值:')
        print(temps.head(20).tolist())
        print()
        print('温度分布:')
        print(f'Min: {temps.min()}, Max: {temps.max()}')
        print(f'25%: {temps.quantile(0.25)}, 50%: {temps.quantile(0.5)}, 75%: {temps.quantile(0.75)}')
