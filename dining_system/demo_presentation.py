import os
import time
from datetime import datetime, timedelta
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

# ==========================================
# 1. 演示环境初始化
# ==========================================
print("\n>>> [系统初始化] 正在加载数据库配置...")

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'canteen_evaluation.db')

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 引入模型（需确保 database_setup.py 在同一目录）
from database_setup import User, Window, Dish, Evaluation, FoodSafety
from db_manager import DBManager

print(f">>> [系统初始化] 数据库连接成功: {db_path}")

# ==========================================
# 2. 核心功能演示
# ==========================================

def demo_query_dishes(window_id):
    """演示：查询窗口菜品"""
    print(f"\n--- [功能演示 1] 查询窗口 {window_id} 的有效菜品 ---")
    dishes = DBManager.get_window_dishes(window_id)
    if dishes:
        print(f"查询成功，共找到 {len(dishes)} 个菜品：")
        for d in dishes:
            print(f"  * ID:{d['id']} {d['name']} (￥{d['price']})")
    else:
        print("未找到菜品或窗口不存在。")

def demo_submit_evaluation(device_id, window_id):
    """演示：提交评价（含自动注册用户）"""
    print(f"\n--- [功能演示 2] 设备 {device_id} 提交评价 ---")
    
    # 构造模拟数据
    eval_data = {
        'device_id': device_id,
        'window_id': window_id,
        'dish_id': 1, # 假设选择红烧肉
        'food_score': 9.8,
        'service_score': 9.5,
        'environment_score': 9.0,
        'food_safety_score': 10.0,
        'service_type': '打菜人员',
        'food_content': '演示代码自动提交的评价',
        'is_submitted': 1 # 正式提交
    }
    
    success, msg, eid = DBManager.submit_evaluation(eval_data)
    if success:
        print(f"✅ 提交成功！评价ID: {eid}")
        print(f"   返回信息: {msg}")
    else:
        print(f"❌ 提交失败: {msg}")

def demo_stats(window_id):
    """演示：统计评价数据"""
    print(f"\n--- [功能演示 3] 统计窗口 {window_id} 的评分数据 ---")
    stats = DBManager.get_evaluation_stats(window_id)
    if stats:
        print(f"窗口 {window_id} 累计收到 {stats['count']} 条评价：")
        print(f"  - 食品均分: {stats['avg_food']}")
        print(f"  - 服务均分: {stats['avg_service']}")
        print(f"  - 环境均分: {stats['avg_env']}")
        print(f"  - 食安均分: {stats['avg_safety']}")
    else:
        print("暂无统计数据。")

# ==========================================
# 3. 异常场景演示
# ==========================================

def demo_error_repeat_submit(device_id, window_id):
    """演示：重复提交拦截"""
    print(f"\n--- [异常演示 1] 设备 {device_id} 尝试重复提交 ---")
    print("说明：该设备刚刚已提交过评价，5分钟内再次提交应被拦截。")
    
    eval_data = {
        'device_id': device_id,
        'window_id': window_id,
        'service_type': '测试',
        'is_submitted': 1
    }
    
    success, msg, _ = DBManager.submit_evaluation(eval_data)
    if not success:
        print(f"✅ 拦截成功（符合预期）：{msg}")
    else:
        print(f"❌ 拦截失败：{msg}")

def demo_error_invalid_window():
    """演示：提交给不存在的窗口"""
    print(f"\n--- [异常演示 2] 提交给不存在的窗口 (ID: 999) ---")
    
    eval_data = {
        'device_id': 'device_test_err',
        'window_id': 999, # 不存在的ID
        'service_type': '测试',
        'is_submitted': 1
    }
    
    success, msg, _ = DBManager.submit_evaluation(eval_data)
    if not success:
        print(f"✅ 拦截成功（符合预期）：{msg}")
    else:
        print(f"❌ 拦截失败：{msg}")

# ==========================================
# 主程序入口
# ==========================================
if __name__ == '__main__':
    with app.app_context():
        # 演示用的参数
        TEST_WINDOW_ID = 1
        TEST_DEVICE_ID = f"demo_device_{int(time.time())}" # 生成唯一设备ID
        
        # 1. 基础功能
        demo_query_dishes(TEST_WINDOW_ID)
        demo_submit_evaluation(TEST_DEVICE_ID, TEST_WINDOW_ID)
        demo_stats(TEST_WINDOW_ID)
        
        # 2. 异常处理
        demo_error_repeat_submit(TEST_DEVICE_ID, TEST_WINDOW_ID)
        demo_error_invalid_window()
        
        print("\n" + "="*40)
        print("所有演示用例执行完毕！")
        print("="*40)
