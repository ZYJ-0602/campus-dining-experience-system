import requests
import json
import time

# 配置 API 基础地址（统一主入口 5000）
BASE_URL = "http://127.0.0.1:5000/api"
SESSION = requests.Session()

def print_result(name, resp):
    """辅助函数：打印测试结果"""
    print(f"\n>>> [测试] {name}")
    print(f"状态码: {resp.status_code}")
    try:
        print(f"响应内容: {json.dumps(resp.json(), indent=2, ensure_ascii=False)}")
    except:
        print(f"响应内容: {resp.text}")

def test_get_dishes(window_id=1):
    resp = SESSION.get(f"{BASE_URL}/window/{window_id}/dishes")
    print_result(f"获取窗口 {window_id} 菜品", resp)

def test_get_safety(window_id=1):
    resp = SESSION.get(f"{BASE_URL}/window/{window_id}/safety")
    print_result(f"获取窗口 {window_id} 食安公示", resp)

def test_auth_flow():
    username = f"u{int(time.time())}"[-18:]
    password = "123456"

    register_resp = SESSION.post(
        f"{BASE_URL}/register",
        json={"username": username, "password": password}
    )
    print_result("注册测试账号", register_resp)

    # 重置会话后测试登录
    SESSION.cookies.clear()
    login_resp = SESSION.post(
        f"{BASE_URL}/login",
        json={"username": username, "password": password}
    )
    print_result("登录测试账号", login_resp)

    me_resp = SESSION.get(f"{BASE_URL}/auth/me")
    print_result("获取当前会话用户", me_resp)

def test_save_evaluation():
    now_str = time.strftime('%Y-%m-%dT%H:%M')
    data = {
        "canteen_id": 1,
        "window_id": 1,
        "buy_time": now_str,
        "identity_type": "student",
        "dishes": [
            {
                "dish_id": 1,
                "dish_name": "测试菜品",
                "food_scores": {"taste": 8, "price": 8}
            }
        ],
        "env_scores": {"cleanliness": 8},
        "service_scores": {"attitude": 8},
        "safety_scores": {"hygiene": 8},
        "remark": "API测试保存"
    }
    resp = SESSION.post(f"{BASE_URL}/evaluation/save", json=data)
    print_result("保存评价 (临时存储)", resp)

def test_submit_evaluation():
    now_str = time.strftime('%Y-%m-%dT%H:%M')
    
    data = {
        "canteen_id": 1,
        "window_id": 1,
        "buy_time": now_str,
        "identity_type": "student",
        "dishes": [
            {
                "dish_id": 1,
                "dish_name": "测试菜品",
                "food_scores": {"taste": 9.5, "price": 9.5}
            }
        ],
        "env_scores": {"cleanliness": 9.5},
        "service_scores": {"attitude": 9.5},
        "safety_scores": {"hygiene": 9.5},
        "remark": "API测试正式提交"
    }
    
    # 第一次提交
    resp = SESSION.post(f"{BASE_URL}/evaluation/submit", json=data)
    print_result("提交评价 (首次提交)", resp)
    
    # 立即重复提交（测试拦截）
    resp_repeat = SESSION.post(f"{BASE_URL}/evaluation/submit", json=data)
    print_result("重复提交 (应被拦截)", resp_repeat)

def test_get_stats(window_id=1):
    resp = SESSION.get(f"{BASE_URL}/evaluation/stats/{window_id}")
    print_result(f"获取窗口 {window_id} 统计信息", resp)

if __name__ == "__main__":
    print("开始 API 接口自动化测试...")
    print(f"目标服务器: {BASE_URL}")
    
    try:
        # 1. 测试菜品接口
        test_get_dishes()

        # 2. 测试登录鉴权
        test_auth_flow()
        
        # 3. 测试食安接口
        test_get_safety()
        
        # 4. 测试保存接口
        test_save_evaluation()
        
        # 5. 测试提交接口（含防重）
        test_submit_evaluation()
        
        # 6. 测试统计接口
        test_get_stats()
        
        print("\n所有测试执行完毕！")
    except requests.exceptions.ConnectionError:
        print("\n[错误] 无法连接到服务器，请确认 app.py 已启动且端口为 5000")
    except Exception as e:
        print(f"\n[错误] 测试过程中发生异常: {e}")
