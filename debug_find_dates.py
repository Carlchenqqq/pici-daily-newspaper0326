from data_processor import DataProcessor
from pathlib import Path
from datetime import datetime, timedelta

# 创建处理器实例
data_root = Path('C:\\Users\\chenq\\Documents\\trae_projects\\pici_daily_newspaper')
processor = DataProcessor(data_root)

batch_id = '魏德曼二分场四线洪河桥一育肥猪20251218'

# 手动模拟 find_all_dates_for_batch 方法的执行过程
print('=== 调试 find_all_dates_for_batch 方法 ===')

# 获取批次信息
batch = processor.get_batch_info(batch_id)
print(f'批次信息: {batch}')

# 检查批次目录
data_dir = data_root / batch_id
print(f'批次目录: {data_dir}')
print(f'批次目录是否存在: {data_dir.exists()}')

# 扫描文件
dates = set()
print('\n扫描文件:')
for f in data_dir.iterdir():
    print(f'文件: {f.name}')
    if not f.is_file() or f.name.startswith('~'):
        print(f'  跳过: 不是文件或以~开头')
        continue
    
    # 检查是否包含"至"
    if '至' in f.name:
        print(f'  包含"至"，解析日期范围')
        date_range = processor.parse_date_range_from_filename(f.name)
        print(f'  解析出的日期范围: {date_range}')
        if date_range:
            start, end = date_range
            print(f'  开始日期: {start}, 结束日期: {end}')
            try:
                s = datetime.strptime(start, '%Y-%m-%d')
                e = datetime.strptime(end, '%Y-%m-%d')
                print(f'  开始日期对象: {s}, 结束日期对象: {e}')
                current = s
                day_count = 0
                while current <= e:
                    date_str = current.strftime('%Y-%m-%d')
                    dates.add(date_str)
                    current += timedelta(days=1)
                    day_count += 1
                print(f'  添加了 {day_count} 天')
            except Exception as e:
                print(f'  日期解析错误: {e}')
        else:
            print(f'  日期范围解析失败')
    else:
        print(f'  不包含"至"，尝试解析单个日期')
        date = processor.parse_date_from_filename(f.name)
        if date:
            dates.add(date)
            print(f'  添加日期: {date}')
        else:
            print(f'  单个日期解析失败')

print(f'\n最终日期集合: {dates}')
print(f'日期数量: {len(dates)}')
print(f'排序后的日期: {sorted(list(dates))}')
