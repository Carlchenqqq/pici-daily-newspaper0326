"""检查 CSV 列名的精确内容"""
import pandas as pd
from pathlib import Path

batch_folder = Path('盱眙育肥二扬州一育肥20250815')
csv_file = None
for f in batch_folder.iterdir():
    if '单元信息.csv' in f.name and '6-1' in f.name:
        csv_file = f
        break

if csv_file:
    df = pd.read_csv(csv_file, encoding='utf-8-sig', nrows=1)
    print("所有列名（repr 显示原始表示）:")
    for col in df.columns:
        print(f"  '{col}' -> repr: {repr(col)}")
