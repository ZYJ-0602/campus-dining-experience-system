from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime
import os
import sys

# Ensure current directory is in path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import db, Review, ReviewDish
from config import Config

app = Flask(__name__, static_folder='../frontend')
app.config.from_object(Config)
db.init_app(app)

# 确保数据库存在
with app.app_context():
    db.create_all()

# --- 路由 ---

@app.route('/')
def index():
    """返回前端页面"""
    return send_from_directory(app.static_folder, 'evaluation.html')

@app.route('/<path:path>')
def static_files(path):
    """返回静态资源"""
    return send_from_directory(app.static_folder, path)

@app.route('/api/dishes', methods=['GET'])
def get_dishes():
    """获取可选菜品列表 (模拟数据)"""
    dishes = [
        {"id": 1, "name": "番茄炒蛋"},
        {"id": 2, "name": "红烧肉"},
        {"id": 3, "name": "麻婆豆腐"},
        {"id": 4, "name": "宫保鸡丁"},
        {"id": 5, "name": "清蒸鱼"},
        {"id": 6, "name": "酸辣土豆丝"},
        {"id": 7, "name": "青椒肉丝"},
        {"id": 8, "name": "玉米排骨汤"}
    ]
    return jsonify(dishes)

@app.route('/api/submit_review', methods=['POST'])
def submit_review():
    """提交评价接口"""
    data = request.json
    
    # 1. 基础校验
    try:
        # 必填项校验
        if not data.get('purchase_time'):
            return jsonify({"error": "请选择购买时间"}), 400
        if not data.get('user_identity'):
            return jsonify({"error": "请选择用户身份"}), 400
            
        # 学生身份校验
        if data['user_identity'] == 'student':
            if not all([data.get('student_grade'), data.get('student_age'), data.get('dining_years')]):
                return jsonify({"error": "学生身份需填写年级、年龄和就餐年限"}), 400
        
        # 评分有效性校验 (至少填写一项评分)
        has_score = False
        
        # 检查环境/服务评分
        env_keys = ['env_comfort', 'env_temp', 'env_layout']
        svc_keys = ['svc_attire', 'svc_attitude', 'svc_hygiene']
        
        for k in env_keys + svc_keys:
            if int(data.get(k, 0)) > 0:
                has_score = True
                break
                
        # 检查菜品评分
        if not has_score and data.get('dishes'):
            for dish in data['dishes']:
                food_keys = ['taste', 'color', 'appearance', 'price', 'portion', 'speed']
                for fk in food_keys:
                    if int(dish.get(fk, 0)) > 0:
                        has_score = True
                        break
                if has_score: break
        
        if not has_score:
            return jsonify({"error": "请至少对一项内容进行评分"}), 400

        # 2. 数据入库
        # 创建主表记录
        review = Review(
            purchase_time=datetime.strptime(data['purchase_time'], '%Y-%m-%dT%H:%M'),
            user_identity=data['user_identity'],
            student_grade=data.get('student_grade'),
            student_age=data.get('student_age'),
            dining_years=data.get('dining_years'),
            
            env_comfort=int(data.get('env_comfort', 0)),
            env_temp=int(data.get('env_temp', 0)),
            env_layout=int(data.get('env_layout', 0)),
            env_comment=data.get('env_comment'),
            
            svc_attire=int(data.get('svc_attire', 0)),
            svc_attitude=int(data.get('svc_attitude', 0)),
            svc_hygiene=int(data.get('svc_hygiene', 0)),
            svc_comment=data.get('svc_comment'),
            svc_personnel=','.join(data.get('svc_personnel', []))
        )
        
        db.session.add(review)
        db.session.flush() # 获取 review.id
        
        # 创建菜品关联记录
        if data.get('dishes'):
            for d in data['dishes']:
                dish_review = ReviewDish(
                    review_id=review.id,
                    dish_name=d['name'],
                    taste=int(d.get('taste', 0)),
                    color=int(d.get('color', 0)),
                    appearance=int(d.get('appearance', 0)),
                    price=int(d.get('price', 0)),
                    portion=int(d.get('portion', 0)),
                    speed=int(d.get('speed', 0)),
                    comment=d.get('comment')
                )
                db.session.add(dish_review)
        
        db.session.commit()
        return jsonify({"message": "评价提交成功！", "review_id": review.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
