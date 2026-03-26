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

print("=== Temperature Data ===")
print("Dates:", trend_data.get('dates', [])[:5])
print("Units:", list(temp_data.get('units', {}).keys()) if temp_data.get('units') else 'N/A')
print("Outdoor:", temp_data.get('outdoor', [])[:10])
print("Target:", temp_data.get('target', [])[:10])

unit_4_1 = temp_data.get('units', {}).get('4-1', [])
unit_4_5 = temp_data.get('units', {}).get('4-5', [])
unit_4_6 = temp_data.get('units', {}).get('4-6', [])
unit_4_7 = temp_data.get('units', {}).get('4-7', [])
unit_4_8 = temp_data.get('units', {}).get('4-8', [])

print("\n=== Unit 4-1 Data ===")
print("Length:", len(unit_4_1))
print("First 5:", unit_4_1[:5])
print("Last 5:", unit_4_1[-5:])
print("Valid count:", len([x for x in unit_4_1 if x is not None]))

print("\n=== Unit 4-5 Data ===")
print("Length:", len(unit_4_5))
print("First 5:", unit_4_5[:5])
print("Last 5:", unit_4_5[-5:])
print("Valid count:", len([x for x in unit_4_5 if x is not None]))

print("\n=== Outdoor Data ===")
print("Length:", len(temp_data.get('outdoor', [])))
print("First 10:", temp_data.get('outdoor', [])[:10])
print("Valid count:", len([x for x in temp_data.get('outdoor', []) if x is not None]))
