import os
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

# --- 1. 开发环境配置 ---
# 获取当前脚本所在目录
basedir = os.path.abspath(os.path.dirname(__file__))
# 数据库文件路径：canteen_evaluation.db
db_path = os.path.join(basedir, 'canteen_evaluation.db')

app = Flask(__name__)
# 配置数据库URI，使用SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化SQLAlchemy实例
db = SQLAlchemy(app)

# --- 2. 数据库模型定义 (ORM) ---

class User(db.Model):
    """
    匿名用户表：用于记录评价者信息，防止刷单
    """
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='自增主键')
    device_id = db.Column(db.String(50), unique=True, nullable=False, comment='设备标识（如device_123456）')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='首次记录时间')

    # 关联关系：一个用户可以有多条评价
    evaluations = db.relationship('Evaluation', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.device_id}>'


class Window(db.Model):
    """
    窗口表：记录食堂窗口的基础信息
    """
    __tablename__ = 'window'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='自增主键（URL传参用）')
    name = db.Column(db.String(50), nullable=False, comment='窗口名称（如1号窗口）')
    canteen_name = db.Column(db.String(50), nullable=False, comment='所属食堂（如北区食堂）')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    # onupdate=datetime.now 确保每次更新记录时自动更新此字段
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 关联关系：
    # 1. 一个窗口对应多个菜品
    dishes = db.relationship('Dish', backref='window', lazy=True)
    # 2. 一个窗口对应多条评价
    evaluations = db.relationship('Evaluation', backref='window', lazy=True)
    # 3. 一个窗口对应多条食安公示
    food_safeties = db.relationship('FoodSafety', backref='window', lazy=True)

    def __repr__(self):
        return f'<Window {self.canteen_name}-{self.name}>'


class Dish(db.Model):
    """
    菜品表：关联窗口，用于评价时选择具体菜品
    """
    __tablename__ = 'dish'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='自增主键')
    name = db.Column(db.String(50), nullable=False, comment='菜品名称（如番茄炒蛋）')
    window_id = db.Column(db.Integer, db.ForeignKey('window.id'), nullable=False, comment='关联窗口ID')
    price = db.Column(db.Numeric(5, 2), nullable=False, comment='菜品价格（保留2位小数）')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='录入时间')
    is_valid = db.Column(db.SmallInteger, default=1, comment='1=有效，0=下架')

    # 关联关系：一个菜品可能出现在多条评价中（虽然Evaluation表dish_id可空，但有关联）
    evaluations = db.relationship('Evaluation', backref='dish', lazy=True)

    def __repr__(self):
        return f'<Dish {self.name}>'


class Evaluation(db.Model):
    """
    评价核心表：存储所有维度的评价数据
    """
    __tablename__ = 'evaluation'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='自增主键')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, comment='关联用户ID')
    window_id = db.Column(db.Integer, db.ForeignKey('window.id'), nullable=False, comment='关联窗口ID')
    dish_id = db.Column(db.Integer, db.ForeignKey('dish.id'), nullable=True, comment='关联菜品ID（可空）')
    
    # --- 食品评价 ---
    food_score = db.Column(db.Numeric(3, 1), nullable=False, comment='食品总评分（1-10分）')
    food_detail_score = db.Column(db.String(100), nullable=True, comment='食品详细评分（格式：色:8,香:9...）')
    food_tags = db.Column(db.String(200), nullable=True, comment='食品标签（逗号分隔）')
    food_content = db.Column(db.String(200), nullable=True, comment='食品文字描述')
    food_image_paths = db.Column(db.String(500), nullable=True, comment='食品图片路径（逗号分隔）')
    
    # --- 服务评价 ---
    service_score = db.Column(db.Numeric(3, 1), nullable=False, comment='服务总评分')
    service_detail_score = db.Column(db.String(100), nullable=True, comment='服务详细评分')
    service_type = db.Column(db.String(100), nullable=False, comment='服务人员类型（逗号分隔）')
    service_tags = db.Column(db.String(200), nullable=True, comment='服务标签')
    service_content = db.Column(db.String(200), nullable=True, comment='服务文字描述')
    service_image_paths = db.Column(db.String(500), nullable=True, comment='服务图片路径')
    
    # --- 环境评价 ---
    environment_score = db.Column(db.Numeric(3, 1), nullable=False, comment='环境总评分')
    environment_detail_score = db.Column(db.String(100), nullable=True, comment='环境详细评分')
    environment_tags = db.Column(db.String(200), nullable=True, comment='环境标签')
    environment_content = db.Column(db.String(200), nullable=True, comment='环境文字描述')
    environment_image_paths = db.Column(db.String(500), nullable=True, comment='环境图片路径')
    
    # --- 食安评价 ---
    food_safety_score = db.Column(db.Numeric(3, 1), nullable=False, comment='食安总评分')
    food_safety_detail_score = db.Column(db.String(100), nullable=True, comment='食安详细评分')
    food_safety_tags = db.Column(db.String(200), nullable=True, comment='食安标签')
    food_safety_content = db.Column(db.String(200), nullable=True, comment='食安文字描述')
    food_safety_image_paths = db.Column(db.String(500), nullable=True, comment='食安图片路径')
    
    # --- 提交状态 ---
    submit_time = db.Column(db.DateTime, default=datetime.now, comment='提交时间')
    is_submitted = db.Column(db.SmallInteger, default=0, comment='0=仅保存，1=已提交')

    def __repr__(self):
        return f'<Evaluation ID:{self.id} User:{self.user_id}>'


class FoodSafety(db.Model):
    """
    食安公示表：用于展示窗口的食品安全证书等信息
    """
    __tablename__ = 'food_safety'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='自增主键')
    window_id = db.Column(db.Integer, db.ForeignKey('window.id'), nullable=False, comment='关联窗口ID')
    certificate_name = db.Column(db.String(100), nullable=False, comment='证书名称（如食品经营许可证）')
    certificate_no = db.Column(db.String(50), nullable=False, comment='证书编号')
    valid_start = db.Column(db.Date, nullable=False, comment='生效日期')
    valid_end = db.Column(db.Date, nullable=False, comment='失效日期')
    upload_path = db.Column(db.String(200), nullable=True, comment='证书图片路径')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='录入时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def __repr__(self):
        return f'<FoodSafety {self.certificate_name}>'


# --- 3. 数据库初始化与测试数据 ---

def init_db():
    """初始化数据库：创建表结构"""
    try:
        with app.app_context():
            # 检查数据库文件是否存在，若存在则提示
            if os.path.exists(db_path):
                print(f"检测到数据库已存在: {db_path}")
                # 生产环境通常使用Flask-Migrate进行迁移，这里为了演示方便，
                # 若需重建可手动删除db文件或取消注释下行代码
                # db.drop_all() 
                # print("已删除旧表...")
            
            # 创建所有表
            db.create_all()
            print("数据库表结构创建成功！")
            
            # 检查是否有数据，若无则插入测试数据
            if not Window.query.first():
                seed_data()
            else:
                print("数据库中已存在数据，跳过测试数据插入。")
    except Exception as e:
        print(f"数据库初始化失败: {e}")

def seed_data():
    """插入测试数据"""
    try:
        print("正在插入测试数据...")
        
        # 1. 插入窗口数据
        window1 = Window(name='1号窗口', canteen_name='北区食堂')
        window2 = Window(name='特色小炒', canteen_name='南区食堂')
        db.session.add_all([window1, window2])
        db.session.commit() # 提交以获取ID
        
        # 2. 插入菜品数据
        dish1 = Dish(name='红烧肉', window_id=window1.id, price=12.5)
        dish2 = Dish(name='番茄炒蛋', window_id=window1.id, price=5.0)
        dish3 = Dish(name='宫保鸡丁', window_id=window2.id, price=15.0)
        db.session.add_all([dish1, dish2, dish3])
        
        # 3. 插入用户数据
        user1 = User(device_id='device_test_001')
        db.session.add(user1)
        db.session.commit()
        
        # 4. 插入评价数据 (模拟一条完整评价)
        eval1 = Evaluation(
            user_id=user1.id,
            window_id=window1.id,
            dish_id=dish1.id,
            # 食品
            food_score=9.0,
            food_detail_score='色:9,香:9,味:8,形:9',
            food_tags='色泽诱人,口感极佳',
            food_content='今天的红烧肉非常入味，推荐！',
            # 服务
            service_score=8.5,
            service_detail_score='着装:9,态度:8,响应:8',
            service_type='打菜人员,收银人员',
            service_tags='态度热情',
            # 环境
            environment_score=8.0,
            environment_detail_score='整洁度:8,通风性:8,舒适度:8',
            environment_tags='干净整洁',
            # 食安
            food_safety_score=10.0,
            food_safety_detail_score='合规度:10',
            food_safety_tags='食材新鲜',
            # 状态
            is_submitted=1
        )
        db.session.add(eval1)
        
        # 5. 插入食安公示数据
        safety1 = FoodSafety(
            window_id=window1.id,
            certificate_name='食品经营许可证',
            certificate_no='JY12345678901234',
            valid_start=datetime.strptime('2023-01-01', '%Y-%m-%d').date(),
            valid_end=datetime.strptime('2026-01-01', '%Y-%m-%d').date(),
            upload_path='/static/upload/safety/cert_001.jpg'
        )
        db.session.add(safety1)
        
        db.session.commit()
        print("测试数据插入成功！")
        
    except Exception as e:
        db.session.rollback()
        print(f"插入测试数据失败: {e}")

if __name__ == '__main__':
    # 运行初始化
    init_db()
    print(f"数据库文件位置: {db_path}")
