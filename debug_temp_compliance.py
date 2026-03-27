from data_processor import DataProcessor
import json
from datetime import datetime

dp = DataProcessor('.')

batch_id = '盱眙育肥二扬州一育肥20250815'
end_date = datetime.now().strftime('%Y-%m-%d')

print(f'正在分析批次: {batch_id}')
print(f'当前日期: {end_date}')

batch_info = dp.get_batch_info(batch_id)
if not batch_info:
    print(f'错误: 找不到批次 {batch_id}')
    exit(1)

print(f'\n批次信息:')
print(f'  - 入栏日期: {batch_info.get("entry_date", "N/A")}')
print(f'  - 单元列表: {batch_info.get("units", [])}')
print(f'  - 单元类型: {batch_info.get("unit_types", {})}')

all_dates = dp.find_all_dates_for_batch(batch_id)
if all_dates:
    print(f'  - 数据日期范围: {all_dates[0]} 至 {all_dates[-1]}')
    print(f'  - 数据天数: {len(all_dates)}')

report = dp.generate_historical_report(batch_id, end_date)

if 'error' in report:
    print(f'错误: {report["error"]}')
    exit(1)

print(f'\n===== 温度达标率分析 =====')

unit_evaluation = report.get('unit_evaluation', {})
if unit_evaluation:
    units = unit_evaluation.get('units', [])
    for u in units:
        unit = u.get('unit')
        metrics = u.get('metrics', {})
        temp_compliance = metrics.get('temp_compliance_rate', 0)
        temp_avg = metrics.get('temp_avg', 0)
        data_days = u.get('data_days', 0)
        print(f'\n单元: {unit}')
        print(f'  温度达标率: {temp_compliance}%')
        print(f'  温度平均: {temp_avg}°C')
        print(f'  数据天数: {data_days}')

print(f'\n===== 每日温度达标率详情 =====')
daily_summaries = report.get('daily_summaries', [])
for day in daily_summaries:
    date = day.get('date')
    unit_details = day.get('unit_details', {})
    temps_in_target = 0
    total_units = 0
    for unit_name, detail in unit_details.items():
        temp_data = detail.get('temperature', {})
        if temp_data.get('avg') is not None:
            total_units += 1
            within_pct = temp_data.get('within_target_pct', 0)
            temps_in_target += within_pct
            if within_pct < 50:
                target = temp_data.get('target', 0)
                avg = temp_data.get('avg', 0)
                print(f'  {date} {unit_name}: 温度{avg}°C, 目标{target}°C, 达标率{within_pct}%')
    if total_units > 0:
        daily_rate = temps_in_target / total_units
        if daily_rate < 50:
            print(f'  >> {date} 整体达标率: {daily_rate*100:.1f}%')