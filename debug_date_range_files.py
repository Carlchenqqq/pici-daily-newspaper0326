from data_processor import DataProcessor
from pathlib import Path
from datetime import datetime, timedelta

# 创建处理器实例
data_root = Path('C:\\Users\\chenq\\Documents\\trae_projects\\pici_daily_newspaper')
processor = DataProcessor(data_root)

batch_id = '魏德曼二分场四线洪河桥一育肥猪20251218'

# 获取批次信息
batch = processor.get_batch_info(batch_id)
print(f'批次信息: {batch}')
print(f'单元列表: {batch.get("units", [])}')

# 手动模拟 get_date_range_files 方法的执行过程
print('\n=== 调试 get_date_range_files 方法 ===')

# 设定日期范围
start_date = '2025-12-18'
end_date = '2026-03-18'
print(f'指定日期范围: {start_date} 至 {end_date}')

# 解析日期范围
start = datetime.strptime(start_date, '%Y-%m-%d')
end = datetime.strptime(end_date, '%Y-%m-%d')

# 初始化结果
result = {}
current = start
while current <= end:
    date_str = current.strftime('%Y-%m-%d')
    result[date_str] = {"environment": [], "device": []}
    current += timedelta(days=1)

print(f'初始化日期范围: {len(result)} 天')

# 扫描文件并分类
data_dir = data_root / batch_id
print('\n扫描文件:')
for f in data_dir.iterdir():
    print(f'文件: {f.name}')
    if not f.is_file() or f.name.startswith('~'):
        print(f'  跳过: 不是文件或以~开头')
        continue
    
    # 解析单元号
    unit_num = processor.parse_unit_number(f.name)
    print(f'  解析出的单元号: {unit_num}')
    if not unit_num or unit_num not in batch.get("units", []):
        print(f'  跳过: 单元号不在批次列表中')
        continue
    
    # 解析日期范围
    date_range = processor.parse_date_range_from_filename(f.name)
    print(f'  解析出的日期范围: {date_range}')
    if date_range:
        start_d, end_d = date_range
        s = datetime.strptime(start_d, '%Y-%m-%d')
        e = datetime.strptime(end_d, '%Y-%m-%d')
        current_file = s
        while current_file <= e:
            date_str = current_file.strftime('%Y-%m-%d')
            if date_str in result:
                file_info = {"unit": unit_num, "path": str(f), "filename": f.name, "date": date_str}
                if "环境数据" in f.name:
                    result[date_str]["environment"].append(file_info)
                    print(f'  添加到日期 {date_str} 的环境数据')
                elif "设备数据" in f.name:
                    result[date_str]["device"].append(file_info)
                    print(f'  添加到日期 {date_str} 的设备数据')
            current_file += timedelta(days=1)
    else:
        date = processor.parse_date_from_filename(f.name)
        if date and date in result:
            file_info = {"unit": unit_num, "path": str(f), "filename": f.name, "date": date}
            if "环境数据" in f.name:
                result[date]["environment"].append(file_info)
                print(f'  添加到日期 {date} 的环境数据')
            elif "设备数据" in f.name:
                result[date]["device"].append(file_info)
                print(f'  添加到日期 {date} 的设备数据')
        else:
            print(f'  跳过: 日期不在指定范围内')

# 检查结果
environment_files_count = 0
for date, files in result.items():
    env_files = files.get("environment", [])
    environment_files_count += len(env_files)
    if env_files:
        print(f'日期 {date}: {len(env_files)} 个环境数据文件')

print(f'\n总环境数据文件数: {environment_files_count}')
print(f'有数据的日期数: {sum(1 for date, files in result.items() if files.get("environment", []))}')
