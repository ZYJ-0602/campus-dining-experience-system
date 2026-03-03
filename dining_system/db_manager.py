import os
from datetime import datetime, timedelta
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, desc

# 引入之前的模型定义（假设 database_setup.py 在同一目录下）
# 为了确保代码独立运行，这里我们直接引用 database_setup.py 中的 app 和 db 对象
# 以及所有模型类
from database_setup import app, db, User, Window, Dish, Evaluation, FoodSafety

class DBManager:
    """
    数据库管理工具类：封装所有核心业务逻辑
    """
    
    @staticmethod
    def get_window_dishes(window_id):
        """
        1. 根据窗口ID查询有效菜品（is_valid=1）
        :param window_id: 窗口ID
        :return: 菜品字典列表，若无则返回空列表
        """
        try:
            # 查询指定窗口且状态为有效的菜品
            dishes = Dish.query.filter_by(window_id=window_id, is_valid=1).all()
            
            result = []
            for dish in dishes:
                result.append({
                    'id': dish.id,
                    'name': dish.name,
                    'price': float(dish.price),
                    'create_time': dish.create_time.strftime('%Y-%m-%d %H:%M:%S')
                })
            return result
        except Exception as e:
            print(f"查询菜品失败: {e}")
            return []

    @staticmethod
    def check_repeat_evaluation(device_id, window_id, minutes=5):
        """
        3. 检查同一设备指定时间内是否重复提交同一窗口评价
        :param device_id: 设备标识
        :param window_id: 窗口ID
        :param minutes: 时间限制（分钟），默认5分钟
        :return: True=重复提交，False=允许提交
        """
        try:
            # 1. 先找到对应的用户
            user = User.query.filter_by(device_id=device_id).first()
            if not user:
                return False  # 用户不存在，肯定没提交过
            
            # 2. 计算时间阈值
            time_threshold = datetime.now() - timedelta(minutes=minutes)
            
            # 3. 查询是否有最近的已提交记录
            exists = Evaluation.query.filter(
                Evaluation.user_id == user.id,
                Evaluation.window_id == window_id,
                Evaluation.is_submitted == 1,
                Evaluation.submit_time >= time_threshold
            ).first()
            
            return True if exists else False
            
        except Exception as e:
            print(f"检查重复提交失败: {e}")
            return True # 出错时保守起见阻止提交，或根据业务需求改为False

    @staticmethod
    def submit_evaluation(eval_data):
        """
        2. 提交评价
        :param eval_data: 评价数据字典
        :return: (success: bool, message: str, eval_id: int)
        """
        try:
            device_id = eval_data.get('device_id')
            window_id = eval_data.get('window_id')
            
            if not device_id or not window_id:
                return False, "缺少必要参数", None

            # 1. 检查窗口是否存在
            window = Window.query.get(window_id)
            if not window:
                return False, "窗口不存在", None

            # 2. 处理用户（查找或创建）
            user = User.query.filter_by(device_id=device_id).first()
            if not user:
                user = User(device_id=device_id)
                db.session.add(user)
                db.session.commit() # 提交以获取user.id
            
            # 3. 检查重复提交（如果是正式提交）
            is_submitted = eval_data.get('is_submitted', 0)
            if is_submitted == 1:
                if DBManager.check_repeat_evaluation(device_id, window_id):
                    return False, "您已提交过评价，请勿重复提交", None

            # 4. 创建评价记录
            new_eval = Evaluation(
                user_id=user.id,
                window_id=window_id,
                dish_id=eval_data.get('dish_id'), # 可空
                
                # 食品评价
                food_score=eval_data.get('food_score', 0),
                food_detail_score=eval_data.get('food_detail_score'),
                food_tags=eval_data.get('food_tags'),
                food_content=eval_data.get('food_content'),
                food_image_paths=eval_data.get('food_image_paths'),
                
                # 服务评价
                service_score=eval_data.get('service_score', 0),
                service_detail_score=eval_data.get('service_detail_score'),
                service_type=eval_data.get('service_type', ''), # 非空
                service_tags=eval_data.get('service_tags'),
                service_content=eval_data.get('service_content'),
                service_image_paths=eval_data.get('service_image_paths'),
                
                # 环境评价
                environment_score=eval_data.get('environment_score', 0),
                environment_detail_score=eval_data.get('environment_detail_score'),
                environment_tags=eval_data.get('environment_tags'),
                environment_content=eval_data.get('environment_content'),
                environment_image_paths=eval_data.get('environment_image_paths'),
                
                # 食安评价
                food_safety_score=eval_data.get('food_safety_score', 0),
                food_safety_detail_score=eval_data.get('food_safety_detail_score'),
                food_safety_tags=eval_data.get('food_safety_tags'),
                food_safety_content=eval_data.get('food_safety_content'),
                food_safety_image_paths=eval_data.get('food_safety_image_paths'),
                
                # 状态
                is_submitted=is_submitted,
                submit_time=datetime.now()
            )
            
            db.session.add(new_eval)
            db.session.commit()
            
            action = "提交" if is_submitted == 1 else "保存"
            return True, f"{action}成功", new_eval.id
            
        except Exception as e:
            db.session.rollback()
            print(f"提交评价失败: {e}")
            return False, f"系统错误: {str(e)}", None

    @staticmethod
    def get_window_safety_info(window_id):
        """
        4. 根据窗口ID查询食安公示信息
        :param window_id: 窗口ID
        :return: 证书列表
        """
        try:
            safeties = FoodSafety.query.filter_by(window_id=window_id).all()
            
            result = []
            for s in safeties:
                result.append({
                    'id': s.id,
                    'name': s.certificate_name,
                    'no': s.certificate_no,
                    'valid_period': f"{s.valid_start} 至 {s.valid_end}",
                    'image': s.upload_path
                })
            return result
        except Exception as e:
            print(f"查询食安信息失败: {e}")
            return []

    @staticmethod
    def get_evaluation_stats(window_id):
        """
        5. 统计某窗口的评价平均分
        :param window_id: 窗口ID
        :return: 统计字典
        """
        try:
            # 仅统计已提交的评价 (is_submitted=1)
            stats = db.session.query(
                func.count(Evaluation.id).label('count'),
                func.avg(Evaluation.food_score).label('avg_food'),
                func.avg(Evaluation.service_score).label('avg_service'),
                func.avg(Evaluation.environment_score).label('avg_env'),
                func.avg(Evaluation.food_safety_score).label('avg_safety')
            ).filter(
                Evaluation.window_id == window_id,
                Evaluation.is_submitted == 1
            ).first()
            
            if not stats or stats.count == 0:
                return {
                    'count': 0,
                    'avg_food': 0.0,
                    'avg_service': 0.0,
                    'avg_env': 0.0,
                    'avg_safety': 0.0
                }
            
            return {
                'count': stats.count,
                'avg_food': round(float(stats.avg_food or 0), 1),
                'avg_service': round(float(stats.avg_service or 0), 1),
                'avg_env': round(float(stats.avg_env or 0), 1),
                'avg_safety': round(float(stats.avg_safety or 0), 1)
            }
            
        except Exception as e:
            print(f"统计评价失败: {e}")
            return None


# --- 测试代码 ---
if __name__ == '__main__':
    with app.app_context():
        print("="*30)
        print("开始测试 DBManager 功能")
        print("="*30)
        
        # 假设 database_setup.py 已经运行过，数据库中有 id=1 的窗口
        WINDOW_ID = 1
        DEVICE_ID = 'device_test_new_001'
        
        # 1. 测试查询菜品
        print(f"\n[测试1] 查询窗口 {WINDOW_ID} 的菜品:")
        dishes = DBManager.get_window_dishes(WINDOW_ID)
        for d in dishes:
            print(f"  - {d['name']} (￥{d['price']})")
            
        # 2. 测试查询食安信息
        print(f"\n[测试2] 查询窗口 {WINDOW_ID} 的食安公示:")
        safeties = DBManager.get_window_safety_info(WINDOW_ID)
        for s in safeties:
            print(f"  - {s['name']} ({s['no']}) 有效期: {s['valid_period']}")
            
        # 3. 测试提交评价
        print(f"\n[测试3] 提交新评价:")
        eval_data = {
            'device_id': DEVICE_ID,
            'window_id': WINDOW_ID,
            'dish_id': dishes[0]['id'] if dishes else None,
            'food_score': 9.5,
            'service_score': 9.0,
            'environment_score': 8.5,
            'food_safety_score': 10.0,
            'service_type': '前台人员',
            'food_content': 'DBManager测试提交',
            'is_submitted': 1
        }
        success, msg, eid = DBManager.submit_evaluation(eval_data)
        print(f"  结果: {msg}, ID: {eid}")
        
        # 4. 测试重复提交拦截
        print(f"\n[测试4] 5分钟内重复提交测试:")
        success_repeat, msg_repeat, _ = DBManager.submit_evaluation(eval_data)
        print(f"  结果: {msg_repeat} (预期应失败)")
        
        # 5. 测试统计数据
        print(f"\n[测试5] 窗口 {WINDOW_ID} 评价统计:")
        stats = DBManager.get_evaluation_stats(WINDOW_ID)
        if stats:
            print(f"  总评价数: {stats['count']}")
            print(f"  食品均分: {stats['avg_food']}")
            print(f"  服务均分: {stats['avg_service']}")
            print(f"  环境均分: {stats['avg_env']}")
            print(f"  食安均分: {stats['avg_safety']}")
            
        print("\n测试完成!")
