from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class UserIdentity(db.Model):
    """
    用户身份表
    """
    __tablename__ = 'user_identity'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), unique=True, nullable=False, comment='身份名称：teacher, student, staff, visitor')
    display_name = db.Column(db.String(50), nullable=False, comment='显示名称：教师, 学生, 员工, 游客')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'display_name': self.display_name
        }

class User(db.Model):
    """
    用户表
    """
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False, comment='账号/手机号')
    password = db.Column(db.String(120), nullable=False, comment='加密密码')
    nickname = db.Column(db.String(80), comment='昵称')
    avatar = db.Column(db.String(255), default='https://ui-avatars.com/api/?name=User&background=random', comment='头像')
    identity_id = db.Column(db.Integer, db.ForeignKey('user_identity.id'), default=2, comment='身份ID，默认学生') # 假设2是学生
    create_time = db.Column(db.DateTime, default=datetime.now, comment='注册时间')
    
    identity = db.relationship('UserIdentity', backref='users')
    evaluations = db.relationship('EvaluationMain', backref='user', lazy=True)

    # 新增字段
    gender = db.Column(db.String(10), comment='性别')
    department = db.Column(db.String(100), comment='专业/部门')
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'nickname': self.nickname,
            'avatar': self.avatar,
            'identity_id': self.identity_id,
            'gender': self.gender,
            'department': self.department,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M') if self.create_time else ''
        }

class Canteen(db.Model):
    """
    食堂表
    """
    __tablename__ = 'canteen'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False, comment='食堂名称')
    location = db.Column(db.String(200), comment='位置')
    opening_hours = db.Column(db.String(100), comment='营业时间')
    
    windows = db.relationship('Window', backref='canteen', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'location': self.location,
            'opening_hours': self.opening_hours
        }

class Window(db.Model):
    """
    窗口表
    """
    __tablename__ = 'window'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    canteen_id = db.Column(db.Integer, db.ForeignKey('canteen.id'), nullable=False, comment='所属食堂ID')
    name = db.Column(db.String(100), nullable=False, comment='窗口名称')
    
    dishes = db.relationship('Dish', backref='window', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'canteen_id': self.canteen_id,
            'name': self.name,
            'canteen_name': self.canteen.name if self.canteen else ''
        }

class Dish(db.Model):
    """
    菜品表
    """
    __tablename__ = 'dish'
    
    # 按照需求更新的字段
    id = db.Column(db.String(36), primary_key=True, comment='菜品ID(UUID)')
    canteen_id = db.Column(db.Integer, db.ForeignKey('canteen.id'), nullable=False, comment='所属食堂ID(外键)')
    window_id = db.Column(db.Integer, db.ForeignKey('window.id'), nullable=True, comment='所属窗口ID')
    name = db.Column(db.String(30), nullable=False, comment='菜品名称(限30字符)')
    price = db.Column(db.Float, nullable=False, comment='价格(精确到分，单位：元)')
    portion = db.Column(db.String(50), default='常规', comment='分量(克/毫升/份，支持双单位)')
    description = db.Column(db.String(500), comment='详细描述(富文本，限500字)')
    img_url = db.Column(db.Text, comment='菜品图片(多张，JSON格式，压缩后≤500 KB/张)')
    tags = db.Column(db.String(255), comment='营养标签(JSON数组，如低糖、低盐、素食)')
    status = db.Column(db.Boolean, default=True, comment='上下架状态')
    
    creator = db.Column(db.String(80), comment='创建人')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updater = db.Column(db.String(80), comment='最后修改人')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='最后修改时间')
    
    # 统计字段 (保留原有)
    total_sales = db.Column(db.Integer, default=0, comment='总销量')
    monthly_sales = db.Column(db.Integer, default=0, comment='月销量')
    category = db.Column(db.String(50), default='其他', comment='菜品分类')
    review_count = db.Column(db.Integer, default=0, comment='评价次数')
    average_score = db.Column(db.Float, default=0.0, comment='平均分')
    
    eval_records = db.relationship('EvaluationDish', backref='dish', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'canteen_id': self.canteen_id,
            'window_id': self.window_id,
            'window_name': self.window.name if self.window else '',
            'name': self.name,
            'price': self.price,
            'category': self.category,
            'portion': self.portion,
            'review_count': self.review_count,
            'average_score': self.average_score,
            'img_url': json.loads(self.img_url) if self.img_url and self.img_url.startswith('[') else [self.img_url] if self.img_url else [],
            'description': self.description,
            'tags': json.loads(self.tags) if self.tags else [],
            'status': self.status,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M') if self.create_time else '',
            'update_time': self.update_time.strftime('%Y-%m-%d %H:%M') if self.update_time else '',
            'total_sales': self.total_sales,
            'monthly_sales': self.monthly_sales
        }

class EvaluationMain(db.Model):
    """
    评价主表
    """
    __tablename__ = 'evaluation_main'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, comment='用户ID')
    canteen_id = db.Column(db.Integer, db.ForeignKey('canteen.id'), nullable=False, comment='食堂ID')
    window_id = db.Column(db.Integer, db.ForeignKey('window.id'), nullable=False, comment='窗口ID')
    
    buy_time = db.Column(db.DateTime, nullable=False, comment='购买时间')
    identity_type = db.Column(db.String(50), comment='提交时的身份') # 冗余存储，防止用户身份变更影响历史数据
    
    # 学生扩展信息
    grade = db.Column(db.String(50), comment='年级')
    age = db.Column(db.Integer, comment='年龄')
    dining_years = db.Column(db.Integer, comment='就餐年限')
    
    # 独立评分字段 (1-10分)
    service_attitude = db.Column(db.Integer, comment='服务态度评分')
    service_speed = db.Column(db.Integer, comment='服务速度评分')
    service_dress = db.Column(db.Integer, comment='人员着装评分')
    service_comment = db.Column(db.Text, comment='服务评价文字')
    service_images = db.Column(db.Text, comment='服务评价图片JSON')
    
    env_clean = db.Column(db.Integer, comment='桌面清洁评分')
    env_air = db.Column(db.Integer, comment='空气气味评分')
    env_hygiene = db.Column(db.Integer, comment='餐具卫生评分')
    env_comment = db.Column(db.Text, comment='环境评价文字')
    env_images = db.Column(db.Text, comment='环境评价图片JSON')
    
    safety_fresh = db.Column(db.Integer, comment='食材新鲜度评分')
    safety_info = db.Column(db.Integer, comment='食品标签信息评分')
    safety_comment = db.Column(db.Text, comment='食安评价文字')
    safety_images = db.Column(db.Text, comment='食安评价图片JSON')
    
    comprehensive_score = db.Column(db.Float, default=0.0, comment='综合评分') # 新增：综合评分
    images = db.Column(db.Text, comment='评价图片JSON数组') # 新增：图片 (Checklist 4)
    remark = db.Column(db.Text, comment='整体备注') # 新增：备注 (Checklist 4)
    
    create_time = db.Column(db.DateTime, default=datetime.now, comment='提交时间')
    
    dish_evaluations = db.relationship('EvaluationDish', backref='evaluation_main', lazy=True, cascade="all, delete-orphan")
    
    # 关联对象
    canteen = db.relationship('Canteen', backref='evaluations')
    window = db.relationship('Window', backref='evaluations')
    
    # Audit status: 0=Pending, 1=Approved, 2=Rejected
    audit_status = db.Column(db.Integer, default=0, comment='审核状态：0待审核, 1通过, 2驳回')
    audit_remark = db.Column(db.String(255), comment='审核备注')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_nickname': self.user.nickname if self.user else '未知用户',
            'user_avatar': self.user.avatar if self.user else '',
            'canteen_id': self.canteen_id,
            'canteen_name': self.canteen.name if self.canteen else '',
            'window_id': self.window_id,
            'window_name': self.window.name if self.window else '',
            'buy_time': self.buy_time.strftime('%Y-%m-%d %H:%M'),
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M'),
            'identity_type': self.identity_type,
            'service_attitude': self.service_attitude,
            'service_speed': self.service_speed,
            'service_dress': self.service_dress,
            'service_comment': self.service_comment,
            'service_images': json.loads(self.service_images) if self.service_images else [],
            'env_clean': self.env_clean,
            'env_air': self.env_air,
            'env_hygiene': self.env_hygiene,
            'env_comment': self.env_comment,
            'env_images': json.loads(self.env_images) if self.env_images else [],
            'safety_fresh': self.safety_fresh,
            'safety_info': self.safety_info,
            'safety_comment': self.safety_comment,
            'safety_images': json.loads(self.safety_images) if self.safety_images else [],
            'comprehensive_score': self.comprehensive_score,
            'images': json.loads(self.images) if self.images else [],
            'remark': self.remark,
            'dishes': [d.to_dict() for d in self.dish_evaluations],
            'audit_status': self.audit_status,
            'audit_remark': self.audit_remark
        }

class EvaluationDish(db.Model):
    """
    评价菜品关联表
    """
    __tablename__ = 'evaluation_dish'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey('evaluation_main.id'), nullable=False, comment='评价ID')
    dish_id = db.Column(db.String(36), db.ForeignKey('dish.id'), nullable=False, comment='菜品ID')
    dish_name = db.Column(db.String(100), nullable=False, comment='菜品名称(冗余)')
    price = db.Column(db.Float, comment='当时价格(用于CPI计算)')
    
    # 菜品6维度评分 (1-10分)
    color_score = db.Column(db.Integer, comment='色泽评分')
    aroma_score = db.Column(db.Integer, comment='香气评分')
    taste_score = db.Column(db.Integer, comment='味道评分')
    shape_score = db.Column(db.Integer, comment='外观形状评分')
    portion_score = db.Column(db.Integer, comment='分量评分')
    price_score = db.Column(db.Integer, comment='价格合理性评分')
    
    remark = db.Column(db.String(500), comment='菜品评价内容')
    # 新增字段
    is_negative = db.Column(db.Boolean, default=False, comment='是否包含负面反馈')
    negative_tags = db.Column(db.String(255), comment='负面标签(JSON数组)')
    
    # evaluation = db.relationship('EvaluationMain', backref='dish_evaluations') # Removed duplicate backref
    # dish = db.relationship('Dish', backref='eval_records') # Removed duplicate backref

    def to_dict(self):
        return {
            'id': self.id,
            'evaluation_id': self.evaluation_id,
            'dish_id': self.dish_id,
            'dish_name': self.dish_name,
            'price': self.price,
            'color_score': self.color_score,
            'aroma_score': self.aroma_score,
            'taste_score': self.taste_score,
            'shape_score': self.shape_score,
            'portion_score': self.portion_score,
            'price_score': self.price_score,
            'remark': self.remark,
            'is_negative': self.is_negative,
            'negative_tags': json.loads(self.negative_tags) if self.negative_tags else []
        }

class SafetyCert(db.Model):
    """
    食安证书表
    """
    __tablename__ = 'safety_cert'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    canteen_id = db.Column(db.Integer, db.ForeignKey('canteen.id'), nullable=False, comment='所属食堂ID')
    # 新增字段以匹配需求
    title = db.Column(db.String(100), nullable=False, comment='证书标题')
    cert_type = db.Column(db.String(50), comment='证书类型')
    file_url = db.Column(db.String(255), nullable=False, comment='文件路径') # 原 img_url 改为 file_url 以匹配需求
    valid_start = db.Column(db.DateTime, comment='有效期开始')
    valid_end = db.Column(db.DateTime, comment='有效期结束') # 原 expire_date
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    
    canteen = db.relationship('Canteen', backref='safety_certs')

    def to_dict(self):
        return {
            'id': self.id,
            'canteen_id': self.canteen_id,
            'canteen_name': self.canteen.name if self.canteen else '',
            'title': self.title,
            'cert_type': self.cert_type,
            'file_url': self.file_url,
            'valid_start': self.valid_start.strftime('%Y-%m-%d') if self.valid_start else '',
            'valid_end': self.valid_end.strftime('%Y-%m-%d') if self.valid_end else '',
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M')
        }

class SystemConfig(db.Model):
    """
    系统配置表
    """
    __tablename__ = 'system_config'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    config_key = db.Column(db.String(50), unique=True, nullable=False, comment='配置键名')
    config_value = db.Column(db.String(255), nullable=False, comment='配置值')
    description = db.Column(db.String(255), comment='配置说明')

class AuditLog(db.Model):
    """
    审计日志表
    """
    __tablename__ = 'audit_log'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    operator = db.Column(db.String(80), nullable=False, comment='操作人')
    operate_time = db.Column(db.DateTime, default=datetime.now, comment='操作时间')
    action = db.Column(db.String(50), nullable=False, comment='操作类型(新增/编辑/删除/批量导入)')
    target_type = db.Column(db.String(50), nullable=False, comment='目标类型(如 Dish)')
    target_id = db.Column(db.String(50), comment='目标ID')
    before_data = db.Column(db.Text, comment='变动前JSON')
    after_data = db.Column(db.Text, comment='变动后JSON')
    ip_address = db.Column(db.String(50), comment='操作IP')

class Note(db.Model):
    """
    社区笔记表
    """
    __tablename__ = 'note'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, comment='用户ID')
    title = db.Column(db.String(100), nullable=False, comment='笔记标题')
    content = db.Column(db.Text, nullable=False, comment='笔记内容')
    images = db.Column(db.Text, comment='图片列表(JSON格式)')
    tags = db.Column(db.String(255), comment='标签(JSON格式)')
    view_count = db.Column(db.Integer, default=0, comment='浏览量')
    like_count = db.Column(db.Integer, default=0, comment='点赞数')
    status = db.Column(db.Integer, default=0, comment='状态：0审核中, 1已发布, 2被隐藏/驳回')
    is_anonymous = db.Column(db.Boolean, default=False, comment='是否匿名发布')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    user = db.relationship('User', backref=db.backref('notes', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_nickname': '匿名用户' if self.is_anonymous else (self.user.nickname if self.user else '未知用户'),
            'user_avatar': '' if self.is_anonymous else (self.user.avatar if self.user else ''),
            'title': self.title,
            'content': self.content,
            'images': json.loads(self.images) if self.images else [],
            'tags': json.loads(self.tags) if self.tags else [],
            'view_count': self.view_count,
            'like_count': self.like_count,
            'status': self.status,
            'is_anonymous': self.is_anonymous,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else '',
            'update_time': self.update_time.strftime('%Y-%m-%d %H:%M:%S') if self.update_time else ''
        }

class SensitiveWord(db.Model):
    """
    敏感词表
    """
    __tablename__ = 'sensitive_word'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    word = db.Column(db.String(100), unique=True, nullable=False, comment='敏感词')
    level = db.Column(db.Integer, default=1, comment='敏感级别(1低, 2中, 3高)')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')

    def to_dict(self):
        return {
            'id': self.id,
            'word': self.word,
            'level': self.level,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else ''
        }

