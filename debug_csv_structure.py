"""检查 CSV 文件结构和数据"""
import pandas as pd
from pathlib import Path

batch_folder = Path('盱眙育肥二扬州一育肥20250815')

# 找到一个单元信息 CSV 文件
for f in batch_folder.iterdir():
    if '单元信息.csv' in f.name:
        print(f"\n检查文件：{f.name}")
        print(f"文件大小：{f.stat().st_size / 1024:.1f} KB")
        
        # 读取前几行查看结构
        df = pd.read_csv(f, encoding='utf-8-sig', nrows=10)
        print(f"\n列名:")
        for col in df.columns:
            print(f"  - '{col}'")
        
        print(f"\n前 3 行数据:")
        print(df.head(3))
        
        print(f"\n数据类型:")
        print(df.dtypes)
        
        print(f"\n总行数：{len(df)}")
        
        # 检查需要的列
        needed_columns = [
            '时间', '单元类型', '目标温度 (℃)', '目标湿度 (%)', '通风模式',
            '舍内温度 (℃)', '舍内湿度 (%)', '二氧化碳均值 (ppm)', '压差均值 (pa)',
            '栋舍', '单元', '装猪数量'
        ]
        
        print(f"\n需要的列检查:")
        for col in needed_columns:
            exists = col in df.columns
            print(f"  {col}: {'✓' if exists else '✗'}")
        
        break
