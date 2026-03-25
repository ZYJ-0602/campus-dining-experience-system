import requests

urls = [
    'http://127.0.0.1:5001/api/analytics/overview',
    'http://127.0.0.1:5001/api/analytics/trend',
    'http://127.0.0.1:5001/api/analytics/rank',
    'http://127.0.0.1:5001/api/analytics/negative',
    'http://127.0.0.1:5001/api/analytics/heatmap',
    'http://127.0.0.1:5001/api/canteens'
]
for u in urls:
    try:
        r = requests.get(u)
        print(u, r.status_code, r.text[:50])
    except Exception as e:
        print(u, e)