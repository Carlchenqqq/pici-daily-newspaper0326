from data_processor import DataProcessor
import pandas as pd
from pathlib import Path

dp = DataProcessor('.')

# 使用保育6-1单元的CSV文件
env_path = r"d:\trae_projects\pici_daily_newspaper-0323稳定版\盱眙育肥二扬州一育肥20250815\盱眙二场保育舍6-1单元 2025-08-15 00_00_00 至 2025-09-28 23_59_59 环境数据_单元信息.csv"

print(f"读取文件: {env_path}")
print(f"文件是否存在: {Path(env_path).exists()}")

needed_columns = [
    '时间', '单元类型', '目标温度(℃)', '目标湿度(%)', '通风模式',
    '舍内温度(℃)', '舍内湿度(%)', '二氧化碳均值(ppm)', '压差均值(pa)',
    '栋舍', '单元', '装猪数量',
    '场区', '猪只体重(Kg)', '日龄', '通风季节', '工作模式', '通风等级'
]

# 直接用pandas读取，不走缓存
df = pd.read_csv(env_path, encoding='utf-8-sig')
print(f"\n=== CSV原始列名 ===")
print(df.columns.tolist())

print(f"\n=== 检查关键列是否存在 ===")
for col in needed_columns:
    exists = col in df.columns
    print(f"  '{col}': {exists}")

print(f"\n=== 目标温度列数据 ===")
if '目标温度(℃)' in df.columns:
    print(df['目标温度(℃)'].head(10))
else:
    print("列不存在!")

# 用 _load_sheet 读取
print(f"\n=== 用 _load_sheet 读取 (usecols=needed_columns) ===")
df2 = dp._load_sheet(env_path, '单元信息', usecols=needed_columns)
print(f"列名: {df2.columns.tolist()}")
print(f"行数: {len(df2)}")
if '目标温度(℃)' in df2.columns:
    print(f"目标温度列数据前10行:\n{df2['目标温度(℃)'].head(10)}")
else:
    print("目标温度列不存在!")

# 不用usecols读取
print(f"\n=== 用 _load_sheet 读取 (无usecols) ===")
df3 = dp._load_sheet(env_path, '单元信息')
print(f"列名: {df3.columns.tolist()}")
print(f"行数: {len(df3)}")
if '目标温度(℃)' in df3.columns:
    print(f"目标温度列数据前10行:\n{df3['目标温度(℃)'].head(10)}")
else:
    print("目标温度列不存在!")