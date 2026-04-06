import requests


URLS = [
    'http://127.0.0.1:5001/api/analytics/overview',
    'http://127.0.0.1:5001/api/analytics/trend',
    'http://127.0.0.1:5001/api/analytics/rank',
    'http://127.0.0.1:5001/api/analytics/negative',
    'http://127.0.0.1:5001/api/analytics/heatmap',
    'http://127.0.0.1:5001/api/canteens',
]


if __name__ == '__main__':
    for url in URLS:
        try:
            response = requests.get(url)
            print(url, response.status_code, response.text[:50])
        except Exception as exc:
            print(url, exc)
