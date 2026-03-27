from data_processor import DataProcessor
import pandas as pd
from datetime import datetime

dp = DataProcessor('.')

batch_id = '盱眙育肥二扬州一育肥20250815'
date = '2025-08-15'

# 找到该批次的文件
date_range_files = dp.get_date_range_files(batch_id, date, date)
print(f"日期范围文件: {date_range_files}")

if date in date_range_files:
    files = date_range_files[date]
    env_files = files.get("environment", [])
    print(f"\n环境数据文件: {len(env_files)}")
    for f in env_files:
        print(f"  - {f['unit']}: {f['filename']}")

    # 加载保育6-1的数据
    for f in env_files:
        if f['unit'] == '保育6-1':
            env_path = f["path"]
            print(f"\n使用文件: {env_path}")

            needed_columns = [
                '时间', '单元类型', '目标温度(℃)', '目标湿度(%)', '通风模式',
                '舍内温度(℃)', '舍内湿度(%)', '二氧化碳均值(ppm)', '压差均值(pa)',
                '栋舍', '单元', '装猪数量',
                '场区', '猪只体重(Kg)', '日龄', '通风季节', '工作模式', '通风等级'
            ]

            unit_info = dp._load_sheet(env_path, '单元信息', usecols=needed_columns)
            print(f"原始数据行数: {len(unit_info)}")

            # 模拟 _calculate_daily_summaries 的逻辑
            row0 = unit_info.iloc[0]
            unit_type = str(row0.get('单元类型', '')).strip().lower()
            vent_mode = str(row0.get('通风模式', '')).strip().lower()

            print(f"\nrow0 目标温度: {row0.get('目标温度(℃)')}")

            # 计算当天的平均目标温度
            target_temp = 26
            if '时间' in unit_info.columns and '目标温度(℃)' in unit_info.columns:
                unit_info = unit_info.copy()
                unit_info['时间'] = pd.to_datetime(unit_info['时间'], errors='coerce')
                unit_info['date'] = unit_info['时间'].dt.date
                target_date = datetime.strptime(date, '%Y-%m-%d').date()
                print(f"目标日期: {target_date}")
                print(f"数据中的日期类型: {type(unit_info['date'].iloc[0])}")
                print(f"数据中的日期示例: {unit_info['date'].iloc[0]}")

                day_unit_info = unit_info[unit_info['date'] == target_date]
                print(f"\n筛选后行数: {len(day_unit_info)}")

                if not day_unit_info.empty:
                    target_temps = pd.to_numeric(day_unit_info['目标温度(℃)'], errors='coerce').dropna()
                    print(f"目标温度非空数量: {len(target_temps)}")
                    if len(target_temps) > 0:
                        target_temp = round(float(target_temps.mean()), 1)
                        print(f"计算的 target_temp: {target_temp}")
                else:
                    print("day_unit_info 为空，使用 row0")
                    target_temp = float(row0.get('目标温度(℃)', 26))
                    print(f"从 row0 获取的 target_temp: {target_temp}")

            print(f"\n最终 target_temp: {target_temp}")
            print(f"temp_min: {target_temp - 3}, temp_max: {target_temp + 3}")

            # 计算温度达标率
            temp_col = '舍内温度(℃)'
            if temp_col in unit_info.columns:
                temp_data = pd.to_numeric(day_unit_info[temp_col], errors='coerce').dropna()
                print(f"\n当天温度数据数量: {len(temp_data)}")
                print(f"温度范围: {temp_data.min()} ~ {temp_data.max()}")

                temp_min = target_temp - 3
                temp_max = target_temp + 3
                within_target = (temp_data >= temp_min) & (temp_data <= temp_max)
                within_rate = round(float(within_target.mean()) * 100, 1)
                print(f"达标率 (target_temp={target_temp}): {within_rate}%")

                # 重新用目标温度=28.86计算
                temp_min_28 = 28.86 - 3
                temp_max_28 = 28.86 + 3
                within_target_28 = (temp_data >= temp_min_28) & (temp_data <= temp_max_28)
                within_rate_28 = round(float(within_target_28.mean()) * 100, 1)
                print(f"达标率 (target_temp=28.86): {within_rate_28}%")