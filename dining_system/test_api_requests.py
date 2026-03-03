import requests
import json
import time

# 配置 API 基础地址（对应 api_server.py 的端口 5001）
BASE_URL = "http://127.0.0.1:5001/api"

def print_result(name, resp):
    """辅助函数：打印测试结果"""
    print(f"\n>>> [测试] {name}")
    print(f"状态码: {resp.status_code}")
    try:
        print(f"响应内容: {json.dumps(resp.json(), indent=2, ensure_ascii=False)}")
    except:
        print(f"响应内容: {resp.text}")

def test_get_dishes(window_id=1):
    resp = requests.get(f"{BASE_URL}/window/{window_id}/dishes")
    print_result(f"获取窗口 {window_id} 菜品", resp)

def test_get_safety(window_id=1):
    resp = requests.get(f"{BASE_URL}/window/{window_id}/safety")
    print_result(f"获取窗口 {window_id} 食安公示", resp)

def test_save_evaluation():
    data = {
        "device_id": "test_device_api_001",
        "window_id": 1,
        "dish_id": 1,
        "food_score": 8.0,
        "service_score": 8.0,
        "environment_score": 8.0,
        "food_safety_score": 8.0,
        "service_type": "前台",
        "food_content": "API测试保存"
    }
    resp = requests.post(f"{BASE_URL}/evaluation/save", json=data)
    print_result("保存评价 (临时存储)", resp)

def test_submit_evaluation():
    # 使用新设备ID，避免被之前的测试数据拦截
    device_id = f"test_device_api_{int(time.time())}"
    
    data = {
        "device_id": device_id,
        "window_id": 1,
        "dish_id": 1,
        "food_score": 9.5,
        "service_score": 9.5,
        "environment_score": 9.5,
        "food_safety_score": 9.5,
        "service_type": "前台",
        "food_content": "API测试正式提交"
    }
    
    # 第一次提交
    resp = requests.post(f"{BASE_URL}/evaluation/submit", json=data)
    print_result("提交评价 (首次提交)", resp)
    
    # 立即重复提交（测试拦截）
    resp_repeat = requests.post(f"{BASE_URL}/evaluation/submit", json=data)
    print_result("重复提交 (应被拦截)", resp_repeat)

def test_get_stats(window_id=1):
    resp = requests.get(f"{BASE_URL}/evaluation/stats/{window_id}")
    print_result(f"获取窗口 {window_id} 统计信息", resp)

if __name__ == "__main__":
    print("开始 API 接口自动化测试...")
    print(f"目标服务器: {BASE_URL}")
    
    try:
        # 1. 测试菜品接口
        test_get_dishes()
        
        # 2. 测试食安接口
        test_get_safety()
        
        # 3. 测试保存接口
        test_save_evaluation()
        
        # 4. 测试提交接口（含防重）
        test_submit_evaluation()
        
        # 5. 测试统计接口
        test_get_stats()
        
        print("\n所有测试执行完毕！")
    except requests.exceptions.ConnectionError:
        print("\n[错误] 无法连接到服务器，请确认 api_server.py 已启动且端口为 5001")
    except Exception as e:
        print(f"\n[错误] 测试过程中发生异常: {e}")
