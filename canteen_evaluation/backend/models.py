from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Review(db.Model):
    """评价主表：包含基础信息、环境评价、服务评价"""
    __tablename__ = 'reviews'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # --- 基础信息 (必填) ---
    purchase_time = db.Column(db.DateTime, nullable=False) # 购买时间
    user_identity = db.Column(db.String(20), nullable=False) # 身份：teacher, staff, student, visitor
    
    # --- 学生扩展信息 (仅学生必填) ---
    student_grade = db.Column(db.String(20)) # 年级
    student_age = db.Column(db.Integer)      # 年龄
    dining_years = db.Column(db.Integer)     # 就餐年限
    
    # --- 环境维度 (非必填) ---
    env_comfort = db.Column(db.Integer, default=0) # 整体舒适度
    env_temp = db.Column(db.Integer, default=0)    # 温湿度
    env_layout = db.Column(db.Integer, default=0)  # 桌椅整洁
    env_comment = db.Column(db.Text)               # 定性备注
    
    # --- 服务维度 (非必填) ---
    svc_attire = db.Column(db.Integer, default=0)   # 着装
    svc_attitude = db.Column(db.Integer, default=0) # 态度
    svc_hygiene = db.Column(db.Integer, default=0)  # 卫生
    svc_comment = db.Column(db.Text)                # 定性备注
    svc_personnel = db.Column(db.String(100))       # 人员类型 (逗号分隔)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # 关联菜品评价
    dish_ratings = db.relationship('ReviewDish', backref='review', lazy=True, cascade="all, delete-orphan")

class ReviewDish(db.Model):
    """菜品评价子表：每个菜品的独立评分"""
    __tablename__ = 'review_dishes'
    
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('reviews.id'), nullable=False)
    dish_name = db.Column(db.String(100), nullable=False)
    
    # --- 食品维度 (非必填) ---
    taste = db.Column(db.Integer, default=0)       # 口味
    color = db.Column(db.Integer, default=0)       # 色泽
    appearance = db.Column(db.Integer, default=0)  # 品相
    price = db.Column(db.Integer, default=0)       # 价格
    portion = db.Column(db.Integer, default=0)     # 分量
    speed = db.Column(db.Integer, default=0)       # 出餐速度
    comment = db.Column(db.Text)                   # 定性备注
