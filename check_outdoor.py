import urllib.request
import urllib.parse
import json

batch_id = "魏德曼二分场四线洪河桥一育肥猪20251218"
params = urllib.parse.urlencode({"batch_id": batch_id, "_t": 1})
url = f"http://127.0.0.1:5000/api/historical-report?{params}"
with urllib.request.urlopen(url) as response:
    d = json.loads(response.read())

td = d.get('data', {}).get('trend_data', {})
outdoor = td.get('temperature', {}).get('outdoor', [])
print('Outdoor temps:', outdoor[:20])
print('Valid count:', len([x for x in outdoor if x is not None]))
