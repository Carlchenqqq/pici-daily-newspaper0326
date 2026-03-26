from data_processor import DataProcessor
import json
from datetime import datetime

dp = DataProcessor('.')

batch_ids = [
    '盱眙育肥二扬州一育肥20250815',
    '盱眙育肥二扬州一育肥20250819'
]

end_date = datetime.now().strftime('%Y-%m-%d')

for batch_id in batch_ids:
    print(f'\n{"="*60}')
    print(f'正在生成批次: {batch_id}')
    print(f'{"="*60}')
    
    batch_info = dp.get_batch_info(batch_id)
    if not batch_info:
        print(f'错误: 找不到批次 {batch_id}')
        continue
    
    print(f'批次信息:')
    print(f'  - 入栏日期: {batch_info.get("entry_date", "N/A")}')
    print(f'  - 单元列表: {batch_info.get("units", [])}')
    print(f'  - 单元类型: {batch_info.get("unit_types", {})}')
    
    all_dates = dp.find_all_dates_for_batch(batch_id)
    if all_dates:
        print(f'  - 数据日期范围: {all_dates[0]} 至 {all_dates[-1]}')
        print(f'  - 数据天数: {len(all_dates)}')
    
    print(f'\n正在生成历史分析报告...')
    report = dp.generate_historical_report(batch_id, end_date)
    
    if 'error' in report:
        print(f'错误: {report["error"]}')
        continue
    
    date_range = report.get('date_range', {})
    print(f'\n报告生成完成:')
    print(f'  - 分析日期范围: {date_range.get("start_date")} 至 {date_range.get("end_date")}')
    print(f'  - 总天数: {date_range.get("total_days", 0)}')
    
    period_stats = report.get('period_statistics', {})
    if period_stats:
        print(f'\n周期统计数据:')
        temp_stats = period_stats.get('temperature', {})
        if temp_stats:
            print(f'  温度:')
            print(f'    - 平均: {temp_stats.get("avg", "N/A")}°C')
            print(f'    - 最高: {temp_stats.get("max", "N/A")}°C')
            print(f'    - 最低: {temp_stats.get("min", "N/A")}°C')
        
        humi_stats = period_stats.get('humidity', {})
        if humi_stats:
            print(f'  湿度:')
            print(f'    - 平均: {humi_stats.get("avg", "N/A")}%')
            print(f'    - 最高: {humi_stats.get("max", "N/A")}%')
            print(f'    - 最低: {humi_stats.get("min", "N/A")}%')
        
        co2_stats = period_stats.get('co2', {})
        if co2_stats:
            print(f'  CO2:')
            print(f'    - 平均: {co2_stats.get("avg", "N/A")} ppm')
            print(f'    - 最高: {co2_stats.get("max", "N/A")} ppm')
    
    daily_summaries = report.get('daily_summaries', [])
    print(f'\n每日汇总数量: {len(daily_summaries)}')
    
    if daily_summaries:
        print(f'前5天数据预览:')
        for i, day in enumerate(daily_summaries[:5]):
            date = day.get('date', 'N/A')
            unit_count = day.get('unit_count', 0)
            temp = day.get('temperature', {}).get('avg', 'N/A')
            humi = day.get('humidity', {}).get('avg', 'N/A')
            print(f'  {date}: {unit_count}个单元, 温度={temp}°C, 湿度={humi}%')
    
    death_analysis = report.get('death_analysis', {})
    if death_analysis:
        print(f'\n死亡淘汰分析:')
        print(f'  - 总死亡数: {death_analysis.get("total_deaths", 0)}')
        print(f'  - 总淘汰数: {death_analysis.get("total_culling", 0)}')
    
    unit_comparison = report.get('unit_comparison', {})
    if unit_comparison and isinstance(unit_comparison, dict):
        print(f'\n单元对比分析:')
        units_data = unit_comparison.get('units', {})
        if units_data:
            for unit, stats in units_data.items():
                if isinstance(stats, dict):
                    print(f'  {unit}:')
                    temp_stats = stats.get('temperature', {})
                    if temp_stats and isinstance(temp_stats, dict):
                        print(f'    温度: 平均={temp_stats.get("avg", "N/A")}°C, 达标率={temp_stats.get("within_target_rate", "N/A")}%')
    
    output_file = f'historical_report_{batch_id}.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f'\n报告已保存到: {output_file}')

print(f'\n{"="*60}')
print('所有批次历史分析完成!')
print(f'{"="*60}')
