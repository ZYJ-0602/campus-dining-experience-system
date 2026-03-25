import requests
import json
import time

BASE_URL = "http://127.0.0.1:5000"

def test_get_dishes():
    print("\n[Testing] GET /api/dishes")
    try:
        resp = requests.get(f"{BASE_URL}/api/dishes")
        print(f"Status Code: {resp.status_code}")
        # print("Response:", json.dumps(resp.json(), ensure_ascii=False, indent=2))
        if resp.status_code == 200:
            print("Success: Retrieved dishes")
        else:
            print("Failed to retrieve dishes")
    except Exception as e:
        print(f"Error: {e}")

def test_submit_evaluation():
    print("\n[Testing] POST /api/submit_evaluation")
    data = {
        "user_id": 1,
        "canteen_id": "1",
        "window_id": "101",
        "buy_time": "2023-10-05T12:30",
        "identity_type": "student",
        "grade": "大三",
        "age": 21,
        "dining_years": 3,
        "env_scores": {"comfort": "5", "temp": "4"},
        "service_scores": {"attitude": "5"},
        "dishes": [
            {
                "dish_name": "麻婆豆腐",
                "remark": "好吃",
                "food_scores": {"taste": "5"}
            }
        ]
    }
    try:
        resp = requests.post(f"{BASE_URL}/api/submit_evaluation", json=data)
        print(f"Status Code: {resp.status_code}")
        print("Response:", json.dumps(resp.json(), ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"Error: {e}")

def test_get_my_evaluations():
    print("\n[Testing] GET /api/get_my_evaluations")
    try:
        resp = requests.get(f"{BASE_URL}/api/get_my_evaluations?user_id=1")
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            print("Success: Retrieved my evaluations")
            # print("Response:", json.dumps(resp.json(), ensure_ascii=False, indent=2))
        else:
            print("Failed")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # 等待服务启动
    time.sleep(2)
    test_get_dishes()
    test_submit_evaluation()
    test_get_my_evaluations()
