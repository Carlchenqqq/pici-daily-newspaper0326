from data_processor import DataProcessor
from pathlib import Path

# 创建处理器实例
data_root = Path('C:\\Users\\chenq\\Documents\\trae_projects\\pici_daily_newspaper')
processor = DataProcessor(data_root)

batch_id = '魏德曼二分场四线洪河桥一育肥猪20251218'

# 获取批次信息
batch = processor.get_batch_info(batch_id)
print(f'批次信息: {batch}')
print(f'单元列表: {batch.get("units", [])}')

# 获取日期范围
dates = processor.find_all_dates_for_batch(batch_id)
print(f'\n日期数量: {len(dates)}')
if dates:
    print(f'第一个日期: {dates[0]}')
    print(f'最后一个日期: {dates[-1]}')

# 获取日期范围文件
print('\n=== 获取日期范围文件 ===')
date_range_files = processor.get_date_range_files(batch_id, dates[0], dates[-1])
print(f'日期范围文件数量: {len(date_range_files)}')

# 检查每个日期的文件
for date, files in date_range_files.items():
    env_files = files.get("environment", [])
    if env_files:
        print(f'日期 {date}: {len(env_files)} 个环境数据文件')

# 加载多日数据
print('\n=== 加载多日数据 ===')
multi_day_data = processor._load_multi_day_data(date_range_files)
print(f'多日数据日期数量: {len(multi_day_data)}')

# 检查每个日期的数据
for date, units in multi_day_data.items():
    print(f'\n日期 {date}:')
    for unit, data in units.items():
        unit_info = data.get("unit_info", None)
        if unit_info is not None:
            print(f'  单元 {unit}: {len(unit_info)} 行数据')
            print(f'  列名: {list(unit_info.columns)}')

# 计算每日汇总
print('\n=== 计算每日汇总 ===')
daily_summaries = processor._calculate_daily_summaries(multi_day_data, batch_id)
print(f'每日汇总数量: {len(daily_summaries)}')

# 检查每日汇总
for summary in daily_summaries[:5]:  # 只显示前5个
    print(f'\n日期: {summary.get("date")}')
    print(f'  温度数据: {summary.get("temperature", {})}')
    print(f'  湿度数据: {summary.get("humidity", {})}')
    print(f'  CO2数据: {summary.get("co2", {})}')
    print(f'  压差数据: {summary.get("pressure", {})}')
    print(f'  单元详情数量: {len(summary.get("unit_details", {}))}')

# 构建历史趋势
print('\n=== 构建历史趋势 ===')
trend_data = processor._build_historical_trend(daily_summaries)
print(f'趋势数据日期数量: {len(trend_data.get("dates", []))}')
print(f'温度数据: {"temperature" in trend_data}')
print(f'湿度数据: {"humidity" in trend_data}')
print(f'CO2数据: {"co2" in trend_data}')
print(f'压差数据: {"pressure" in trend_data}')
