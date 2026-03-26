import urllib.request
import urllib.parse
import json

batch_id = "魏德曼二分场四线洪河桥一育肥猪20251218"
params = urllib.parse.urlencode({"batch_id": batch_id, "_t": 12345})
url = f"http://127.0.0.1:5000/api/historical-report?{params}"
print("Requesting API...")
with urllib.request.urlopen(url) as response:
    d = json.loads(response.read())

data = d.get('data', {})
trend_data = data.get('trend_data', {})
temp_data = trend_data.get('temperature', {})

dates = trend_data.get('dates', [])
outdoor_temps = temp_data.get('outdoor', [])

print("=== 舍外温度数据验证 ===")
print(f"总天数: {len(dates)}")
print()

print("前10天的舍外温度:")
for i in range(min(10, len(dates))):
    print(f"{dates[i]}: {outdoor_temps[i]}")
print()

print("=== 验证12月18日 ===")
if '2025-12-18' in dates:
    idx = dates.index('2025-12-18')
    print(f"日期: {dates[idx]}")
    print(f"舍外温度: {outdoor_temps[idx]}")
    print(f"预期值: 10.4")
    print(f"是否正确: {'✅' if outdoor_temps[idx] == 10.4 else '❌'}")
