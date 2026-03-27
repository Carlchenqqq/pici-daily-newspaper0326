from data_processor import DataProcessor
import pandas as pd
from datetime import datetime
import numpy as np

dp = DataProcessor('.')

batch_id = '盱眙育肥二扬州一育肥20250815'
date = '2025-08-15'

# 清除所有缓存，确保从头开始
dp._sheet_cache.clear()
dp._daily_summaries_cache.clear()

date_range_files = dp.get_date_range_files(batch_id, date, date)

# 模拟 _load_multi_day_data (带 usecols)
needed_columns = [
    '时间', '单元类型', '目标温度(℃)', '目标湿度(%)', '通风模式',
    '舍内温度(℃)', '舍内湿度(%)', '二氧化碳均值(ppm)', '压差均值(pa)',
    '栋舍', '单元', '装猪数量',
    '场区', '猪只体重(Kg)', '日龄', '通风季节', '工作模式', '通风等级'
]

multi_day_data = {}
for date, files in date_range_files.items():
    multi_day_data[date] = {}
    for env_file in files.get("environment", []):
        unit = env_file["unit"]
        env_path = env_file["path"]
        cache_key = f"file_{env_path}"
        data = {
            "unit_info": dp._load_sheet(env_path, '单元信息', usecols=needed_columns),
            "_env_path": env_path
        }
        multi_day_data[date][unit] = data

print("=== _load_multi_day_data 完成 ===")
print(f"multi_day_data 包含的日期: {list(multi_day_data.keys())}")

# 模拟 _calculate_daily_summaries
for date in sorted(multi_day_data.keys()):
    date_data = multi_day_data[date]
    print(f"\n处理日期: {date}")

    for unit, data in date_data.items():
        unit_info = data.get("unit_info", pd.DataFrame())
        print(f"\n  单元: {unit}")
        print(f"  unit_info 行数: {len(unit_info)}")
        print(f"  unit_info 列数: {len(unit_info.columns)}")
        print(f"  '目标温度(℃)' in columns: {'目标温度(℃)' in unit_info.columns}")
        print(f"  '舍内温度(℃)' in columns: {'舍内温度(℃)' in unit_info.columns}")

        target_temp = 26
        target_humidity = 60

        if not unit_info.empty:
            row0 = unit_info.iloc[0]
            print(f"  row0['目标温度(℃)']: {row0.get('目标温度(℃)')}")

            if '时间' in unit_info.columns and '目标温度(℃)' in unit_info.columns:
                unit_info = unit_info.copy()
                unit_info['时间'] = pd.to_datetime(unit_info['时间'], errors='coerce')
                unit_info['date'] = unit_info['时间'].dt.date
                target_date = datetime.strptime(date, '%Y-%m-%d').date()
                day_unit_info = unit_info[unit_info['date'] == target_date]
                print(f"  筛选后 day_unit_info 行数: {len(day_unit_info)}")

                if not day_unit_info.empty:
                    target_temps = pd.to_numeric(day_unit_info['目标温度(℃)'], errors='coerce').dropna()
                    print(f"  target_temps 非空数量: {len(target_temps)}")
                    if len(target_temps) > 0:
                        target_temp = round(float(target_temps.mean()), 1)
                        print(f"  计算得到 target_temp: {target_temp}")

        print(f"  最终 target_temp: {target_temp}")

        # 计算 day_df (用于温度达标率)
        day_df = pd.DataFrame()
        if not unit_info.empty and '时间' in unit_info.columns:
            unit_info = unit_info.copy()
            unit_info['时间'] = pd.to_datetime(unit_info['时间'], errors='coerce')
            unit_info['date'] = unit_info['时间'].dt.date
            day_df = unit_info[unit_info['date'] == datetime.strptime(date, '%Y-%m-%d').date()]

        print(f"  day_df 行数: {len(day_df)}")
        print(f"  '目标温度(℃)' in day_df.columns: {'目标温度(℃)' in day_df.columns}")
        print(f"  '舍内温度(℃)' in day_df.columns: {'舍内温度(℃)' in day_df.columns}")

        temp_col = '舍内温度(℃)'
        target_temp_col = '目标温度(℃)'

        if temp_col in day_df.columns and target_temp_col in day_df.columns:
            temps = pd.to_numeric(day_df[temp_col], errors='coerce')
            target_temps = pd.to_numeric(day_df[target_temp_col], errors='coerce')
            print(f"  temps 数量: {len(temps.dropna())}")
            print(f"  target_temps 数量: {len(target_temps.dropna())}")

            if len(temps) > 0:
                valid_mask = ~(temps.isna() | target_temps.isna())
                print(f"  valid_mask 中 True 的数量: {valid_mask.sum()}")

                if valid_mask.sum() > 0:
                    temps_valid = temps[valid_mask].values
                    target_temps_valid = target_temps[valid_mask].values

                    above_mask = temps_valid > (target_temps_valid + 3)
                    below_mask = temps_valid < (target_temps_valid - 3)
                    within_target = ~(above_mask | below_mask)
                    within_target_pct = round(float(within_target.mean()) * 100, 1)
                    print(f"  温度达标率 (动态目标): {within_target_pct}%")

                    temps_mean = float(temps.mean())
                    print(f"  平均温度: {temps_mean}°C")
                    print(f"  目标温度范围 (target_temp={target_temp}): {target_temp-3} ~ {target_temp+3}")
        else:
            print("  跳过温度达标率计算 (列不存在)")