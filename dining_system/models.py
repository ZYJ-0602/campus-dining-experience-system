from datetime import datetime
from extensions import db

class User(db.Model):
    """
    用户表 (user)
    """
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False, comment='用户名')
    password = db.Column(db.String(120), nullable=False, comment='密码')
    role = db.Column(db.String(20), default='student', comment='角色')
    nickname = db.Column(db.String(80), comment='昵称')
    phone = db.Column(db.String(20), comment='手机号')
    avatar = db.Column(db.String(255), comment='头像URL')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    
    # 关联关系
    evaluations = db.relationship('EvaluationMain', backref='user', lazy=True)

class Canteen(db.Model):
    """
    食堂表 (canteen)
    """
    __tablename__ = 'canteen'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False, comment='食堂名称')
    address = db.Column(db.String(200), nullable=False, comment='位置')
    business_hours = db.Column(db.String(100), default='07:00-21:00', comment='营业时间')
    is_active = db.Column(db.Boolean, default=True, comment='状态')
    
    # 关联关系
    windows = db.relationship('Window', backref='canteen', lazy=True)
    evaluations = db.relationship('EvaluationMain', backref='canteen', lazy=True)

class Window(db.Model):
    """
    窗口表 (window)
    """
    __tablename__ = 'window'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    canteen_id = db.Column(db.Integer, db.ForeignKey('canteen.id'), nullable=False, comment='关联食堂id')
    name = db.Column(db.String(100), nullable=False, comment='窗口名称')
    
    # 关联关系
    dishes = db.relationship('Dish', backref='window', lazy=True)
    evaluations = db.relationship('EvaluationMain', backref='window', lazy=True)

class Dish(db.Model):
    """
    菜品表 (dish)
    """
    __tablename__ = 'dish'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    window_id = db.Column(db.Integer, db.ForeignKey('window.id'), nullable=False, comment='关联窗口id')
    name = db.Column(db.String(100), nullable=False, comment='菜品名称')
    img_url = db.Column(db.String(255), comment='图片路径')
    
    price = db.Column(db.Float, default=0.0, comment='价格')
    category = db.Column(db.String(50), default='其他', comment='分类')
    tags_json = db.Column(db.JSON, comment='标签列表JSON')
    portion = db.Column(db.String(50), default='常规', comment='分量')
    review_count = db.Column(db.Integer, default=0, comment='评价次数')
    average_score = db.Column(db.Float, default=0.0, comment='平均分')
    is_active = db.Column(db.Boolean, default=True, nullable=False, comment='是否上架')
    
    # 关联关系
    evaluation_dishes = db.relationship('EvaluationDish', backref='dish', lazy=True)

class EvaluationMain(db.Model):
    """
    评价主表 (evaluation_main)
    """
    __tablename__ = 'evaluation_main'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, comment='关联用户id')
    canteen_id = db.Column(db.Integer, db.ForeignKey('canteen.id'), nullable=False, comment='关联食堂id')
    window_id = db.Column(db.Integer, db.ForeignKey('window.id'), nullable=False, comment='关联窗口id')
    
    buy_time = db.Column(db.DateTime, nullable=False, comment='购买时间')
    identity_type = db.Column(db.String(50), nullable=False, comment='用户身份')
    grade = db.Column(db.String(50), comment='年级')
    age = db.Column(db.Integer, comment='年龄')
    dining_years = db.Column(db.Integer, comment='就餐年限')
    
    env_scores = db.Column(db.JSON, comment='环境评分JSON')
    service_scores = db.Column(db.JSON, comment='服务评分JSON')
    safety_scores = db.Column(db.JSON, comment='食安评分JSON')
    service_comment = db.Column(db.Text, comment='服务评价文字')
    service_images = db.Column(db.JSON, comment='服务评价图片JSON')
    env_comment = db.Column(db.Text, comment='环境评价文字')
    env_images = db.Column(db.JSON, comment='环境评价图片JSON')
    safety_comment = db.Column(db.Text, comment='食安评价文字')
    safety_images = db.Column(db.JSON, comment='食安评价图片JSON')
    comprehensive_score = db.Column(db.Float, default=0.0, comment='综合评分')
    images = db.Column(db.JSON, comment='评价图片JSON')
    remark = db.Column(db.Text, comment='整体备注')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    
    # 关联关系
    dish_evaluations = db.relationship('EvaluationDish', backref='evaluation_main', lazy=True, cascade="all, delete-orphan")

class EvaluationDish(db.Model):
    """
    评价-菜品关联表 (evaluation_dish)
    """
    __tablename__ = 'evaluation_dish'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey('evaluation_main.id'), nullable=False, comment='关联评价主表id')
    dish_id = db.Column(db.Integer, db.ForeignKey('dish.id'), default=0, comment='关联菜品id，自定义菜品则存0')
    dish_name = db.Column(db.String(100), nullable=False, comment='菜品名称，兼容自定义')
    dish_img_url = db.Column(db.String(255), comment='菜品图片路径')
    
    food_scores = db.Column(db.JSON, comment='食品评分JSON：口味/色泽/品相/价格/分量/出餐速度')
    remark = db.Column(db.Text, comment='备注')


class SubmitGuard(db.Model):
    """
    提交限流记录表 (submit_guard)
    用于跨进程/重启后仍保持防重复提交能力。
    """
    __tablename__ = 'submit_guard'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'window_id', name='uq_submit_guard_user_window'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False, comment='用户ID')
    window_id = db.Column(db.Integer, nullable=False, comment='窗口ID')
    last_submit_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='最近提交时间')
    block_count = db.Column(db.Integer, default=0, nullable=False, comment='命中限流次数')
    last_block_time = db.Column(db.DateTime, comment='最近一次限流时间')


class Favorite(db.Model):
    """
    收藏表 (favorite)
    """
    __tablename__ = 'favorite'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'fav_type', 'ref_id', name='uq_favorite_user_type_ref'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, comment='用户ID')
    fav_type = db.Column(db.String(30), nullable=False, comment='收藏类型：note/evaluation/dish/canteen')
    ref_id = db.Column(db.Integer, nullable=False, comment='关联业务ID')
    title = db.Column(db.String(200), nullable=False, comment='展示标题')
    created_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='收藏时间')


class Feedback(db.Model):
    """
    意见反馈表 (feedback)
    """
    __tablename__ = 'feedback'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, comment='用户ID')
    content = db.Column(db.Text, nullable=False, comment='反馈内容')
    contact = db.Column(db.String(120), comment='联系方式')
    status = db.Column(db.String(20), default='pending', nullable=False, comment='状态')
    created_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')


class SensitiveWord(db.Model):
    """
    敏感词表 (sensitive_word)
    """
    __tablename__ = 'sensitive_word'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    word = db.Column(db.String(60), unique=True, nullable=False, comment='敏感词')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')


class SensitiveRule(db.Model):
    """
    敏感词规则表 (sensitive_rule)
    单行配置：block(拦截) / replace(替换)
    """
    __tablename__ = 'sensitive_rule'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    rule = db.Column(db.String(20), default='block', nullable=False, comment='处理规则')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')


class Note(db.Model):
    """
    用户笔记表 (note)
    """
    __tablename__ = 'note'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, comment='用户ID')
    title = db.Column(db.String(200), nullable=False, comment='标题')
    content = db.Column(db.Text, nullable=False, comment='内容')
    status = db.Column(db.String(20), default='published', nullable=False, comment='状态')
    like_count = db.Column(db.Integer, default=0, nullable=False, comment='点赞数')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')


class SystemConfig(db.Model):
    """
    系统配置表 (system_config)
    单行配置：评价参数、内容发布参数
    """
    __tablename__ = 'system_config'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    repeat_submit_minutes = db.Column(db.Integer, default=5, nullable=False, comment='防重复提交时间(分钟)')
    score_min = db.Column(db.Integer, default=1, nullable=False, comment='评分最小值')
    score_max = db.Column(db.Integer, default=10, nullable=False, comment='评分最大值')
    audit_enabled = db.Column(db.Boolean, default=True, nullable=False, comment='开启内容审核')
    image_limit = db.Column(db.Integer, default=9, nullable=False, comment='单次上传图片上限')
    file_size_limit_mb = db.Column(db.Integer, default=10, nullable=False, comment='单文件大小限制MB')
    allow_jpg = db.Column(db.Boolean, default=True, nullable=False, comment='允许JPG/JPEG')
    allow_png = db.Column(db.Boolean, default=True, nullable=False, comment='允许PNG')
    allow_pdf = db.Column(db.Boolean, default=False, nullable=False, comment='允许PDF')
    bad_review_threshold = db.Column(db.Float, default=4.0, nullable=False, comment='差评阈值')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')


class NotificationConfig(db.Model):
    """
    通知配置表 (notification_config)
    单行配置：差评提醒、待审核提醒、频率限制
    """
    __tablename__ = 'notification_config'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bad_review_site = db.Column(db.Boolean, default=True, nullable=False, comment='差评站内信')
    bad_review_email = db.Column(db.Boolean, default=False, nullable=False, comment='差评邮件')
    bad_review_sms = db.Column(db.Boolean, default=False, nullable=False, comment='差评短信')
    pending_audit_site = db.Column(db.Boolean, default=True, nullable=False, comment='待审核站内信')
    pending_audit_email = db.Column(db.Boolean, default=True, nullable=False, comment='待审核邮件')
    pending_audit_sms = db.Column(db.Boolean, default=False, nullable=False, comment='待审核短信')
    frequency = db.Column(db.String(20), default='realtime', nullable=False, comment='频率 realtime/hourly/daily')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')


class BackupRecord(db.Model):
    """
    数据备份记录表 (backup_record)
    """
    __tablename__ = 'backup_record'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    file_name = db.Column(db.String(255), nullable=False, comment='备份文件名')
    file_path = db.Column(db.String(500), nullable=False, comment='备份文件路径')
    file_size = db.Column(db.Integer, default=0, nullable=False, comment='文件大小(字节)')
    backup_type = db.Column(db.String(20), default='manual', nullable=False, comment='manual/auto')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='备份时间')


class NotificationDispatchLog(db.Model):
    """
    通知发送节流日志表 (notification_dispatch_log)
    依据事件类型+渠道+角色做频率限制，避免重复发送。
    """
    __tablename__ = 'notification_dispatch_log'
    __table_args__ = (
        db.UniqueConstraint('event_type', 'channel', 'target_role', name='uq_notify_dispatch_scope'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_type = db.Column(db.String(50), nullable=False, comment='事件类型 bad_review/pending_audit')
    channel = db.Column(db.String(20), nullable=False, comment='渠道 site/email/sms')
    target_role = db.Column(db.String(20), nullable=False, comment='目标角色 operator/admin')
    last_ref_id = db.Column(db.Integer, default=0, nullable=False, comment='最近发送事件关联ID')
    send_count = db.Column(db.Integer, default=0, nullable=False, comment='发送次数')
    last_send_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='最近发送时间')


class NotificationMessage(db.Model):
    """
    站内信消息表 (notification_message)
    """
    __tablename__ = 'notification_message'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, comment='接收用户ID')
    event_type = db.Column(db.String(50), nullable=False, comment='事件类型')
    title = db.Column(db.String(200), nullable=False, comment='消息标题')
    content = db.Column(db.Text, nullable=False, comment='消息内容')
    is_read = db.Column(db.Boolean, default=False, nullable=False, comment='是否已读')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')


class OperatorWarning(db.Model):
    """
    运营差评预警表 (operator_warning)
    """
    __tablename__ = 'operator_warning'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey('evaluation_main.id'), nullable=False, unique=True, comment='关联评价ID')
    canteen_id = db.Column(db.Integer, db.ForeignKey('canteen.id'), nullable=True, comment='食堂ID')
    window_id = db.Column(db.Integer, db.ForeignKey('window.id'), nullable=True, comment='窗口ID')
    dish_id = db.Column(db.Integer, db.ForeignKey('dish.id'), nullable=True, comment='关联菜品ID')
    score = db.Column(db.Float, default=0.0, nullable=False, comment='触发评分')
    summary = db.Column(db.String(255), default='', nullable=False, comment='问题摘要')
    status = db.Column(db.String(20), default='pending', nullable=False, comment='状态 pending/handled')
    handler_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, comment='处理人')
    handle_note = db.Column(db.Text, default='', nullable=False, comment='处理说明')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    handled_time = db.Column(db.DateTime, nullable=True, comment='处理时间')


class SafetyNotice(db.Model):
    """
    食安公示表 (safety_notice)
    """
    __tablename__ = 'safety_notice'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(200), nullable=False, comment='公示标题')
    notice_type = db.Column(db.String(50), default='检测报告', nullable=False, comment='公示类型')
    expire_date = db.Column(db.Date, nullable=True, comment='有效期')
    status = db.Column(db.String(20), default='published', nullable=False, comment='状态 published/offline')
    files_json = db.Column(db.JSON, comment='附件列表JSON')
    content = db.Column(db.Text, default='', nullable=False, comment='公示内容')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')


class RectificationRecord(db.Model):
    """
    差评整改记录表 (rectification_record)
    """
    __tablename__ = 'rectification_record'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    warning_id = db.Column(db.Integer, db.ForeignKey('operator_warning.id'), nullable=True, comment='关联预警ID')
    title = db.Column(db.String(200), nullable=False, comment='整改标题')
    issue_desc = db.Column(db.Text, default='', nullable=False, comment='问题描述')
    action_detail = db.Column(db.Text, default='', nullable=False, comment='整改措施')
    images_json = db.Column(db.JSON, comment='整改图片JSON')
    is_public = db.Column(db.Boolean, default=False, nullable=False, comment='是否已公示')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')
