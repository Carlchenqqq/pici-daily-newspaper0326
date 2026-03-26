import urllib.request
import urllib.parse
import json

batch_id = "魏德曼二分场四线洪河桥一育肥猪20251218"
params = urllib.parse.urlencode({"batch_id": batch_id})
url = f"http://127.0.0.1:5000/api/historical-report?{params}"
print("Requesting API...")
with urllib.request.urlopen(url) as response:
    d = json.loads(response.read())

data = d.get('data', {})
trend_data = data.get('trend_data', {})
temp_data = trend_data.get('temperature', {})

dates = trend_data.get('dates', [])
unit_4_1 = temp_data.get('units', {}).get('4-1', [])

print("=== Dates ===")
print(f"Total dates: {len(dates)}")
print(f"First 5 dates: {dates[:5]}")
print()

print("=== Unit 4-1 Temperature Data ===")
print(f"Total data points: {len(unit_4_1)}")
print(f"First 5 values: {unit_4_1[:5]}")
print(f"Last 5 values: {unit_4_1[-5:]}")
print()

# 找到12月18日的索引
if '2025-12-18' in dates:
    idx = dates.index('2025-12-18')
    print(f"=== 2025-12-18 (index {idx}) ===")
    print(f"Temperature: {unit_4_1[idx]}")
    print()

# 检查daily_summaries
daily_summaries = data.get('daily_summaries', [])
print("=== Daily Summaries ===")
print(f"Total days: {len(daily_summaries)}")
print()

if daily_summaries:
    first_day = daily_summaries[0]
    print("=== First Day Summary ===")
    print(f"Date: {first_day.get('date')}")
    print(f"Temperature: {first_day.get('temperature')}")
    print()
    
    unit_details = first_day.get('unit_details', {})
    if '4-1' in unit_details:
        unit_4_1_detail = unit_details['4-1']
        print("=== Unit 4-1 Detail ===")
        print(f"Temperature: {unit_4_1_detail.get('temperature')}")
        print(f"Target temp: {unit_4_1_detail.get('target_temp')}")
