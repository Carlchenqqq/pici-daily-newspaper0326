from data_processor import DataProcessor
import pandas as pd
from datetime import datetime

dp = DataProcessor('.')

batch_id = '盱眙育肥二扬州一育肥20250815'
date = '2025-08-15'

date_range_files = dp.get_date_range_files(batch_id, date, date)

if date in date_range_files:
    files = date_range_files[date]
    env_files = files.get("environment", [])

    for f in env_files:
        if f['unit'] == '保育6-1':
            env_path = f["path"]
            print(f"使用文件: {env_path}")

            # 模拟 _load_multi_day_data 的调用方式 (带 usecols)
            needed_columns = [
                '时间', '单元类型', '目标温度(℃)', '目标湿度(%)', '通风模式',
                '舍内温度(℃)', '舍内湿度(%)', '二氧化碳均值(ppm)', '压差均值(pa)',
                '栋舍', '单元', '装猪数量',
                '场区', '猪只体重(Kg)', '日龄', '通风季节', '工作模式', '通风等级'
            ]
            cache_key_with_usecols = f"file_{env_path}"
            print(f"\n[方式1] 带 usecols 调用 _load_sheet")
            unit_info_1 = dp._load_sheet(env_path, '单元信息', usecols=needed_columns)
            print(f"缓存key: {cache_key_with_usecols}")
            print(f"行数: {len(unit_info_1)}")
            if '目标温度(℃)' in unit_info_1.columns:
                print(f"目标温度列前5个值: {unit_info_1['目标温度(℃)'].head().tolist()}")

            # 清除缓存
            dp._sheet_cache.clear()

            # 模拟 _calculate_daily_summaries 的调用方式 (不带 usecols)
            print(f"\n[方式2] 不带 usecols 调用 _load_sheet")
            unit_info_2 = dp._load_sheet(env_path, '单元信息')
            print(f"缓存key: {cache_key_with_usecols}")
            print(f"行数: {len(unit_info_2)}")
            if '目标温度(℃)' in unit_info_2.columns:
                print(f"目标温度列前5个值: {unit_info_2['目标温度(℃)'].head().tolist()}")
            else:
                print("目标温度列不存在!")
                print(f"可用列: {unit_info_2.columns.tolist()}")