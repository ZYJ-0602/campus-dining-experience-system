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
    campus_id = db.Column(db.Integer, default=1, nullable=False, comment='校区/租户ID')
    operator_canteen_id = db.Column(db.Integer, db.ForeignKey('canteen.id'), nullable=True, comment='运营账号绑定食堂ID')
    nickname = db.Column(db.String(80), comment='昵称')
    phone = db.Column(db.String(20), comment='手机号')
    avatar = db.Column(db.String(255), comment='头像URL')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    
    # 关联关系
    evaluations = db.relationship('EvaluationMain', backref='user', lazy=True)


class Campus(db.Model):
    """
    校区/租户表 (campus)
    """
    __tablename__ = 'campus'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False, unique=True, comment='校区名称')
    code = db.Column(db.String(50), nullable=False, unique=True, comment='校区编码')
    is_active = db.Column(db.Boolean, default=True, nullable=False, comment='是否启用')
    sort_order = db.Column(db.Integer, default=0, nullable=False, comment='排序')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')

class Canteen(db.Model):
    """
    食堂表 (canteen)
    """
    __tablename__ = 'canteen'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    campus_id = db.Column(db.Integer, default=1, nullable=False, comment='校区/租户ID')
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
    campus_id = db.Column(db.Integer, default=1, nullable=False, comment='校区/租户ID')
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
    template_version = db.Column(db.Integer, comment='评价模板版本ID')
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
    campus_id = db.Column(db.Integer, default=1, nullable=False, comment='校区/租户ID')
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
    campus_id = db.Column(db.Integer, default=1, nullable=False, comment='校区/租户ID')
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
    campus_id = db.Column(db.Integer, default=1, nullable=False, comment='校区/租户ID')
    warning_id = db.Column(db.Integer, db.ForeignKey('operator_warning.id'), nullable=True, comment='关联预警ID')
    title = db.Column(db.String(200), nullable=False, comment='整改标题')
    issue_desc = db.Column(db.Text, default='', nullable=False, comment='问题描述')
    action_detail = db.Column(db.Text, default='', nullable=False, comment='整改措施')
    images_json = db.Column(db.JSON, comment='整改图片JSON')
    is_public = db.Column(db.Boolean, default=False, nullable=False, comment='是否已公示')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')


class GuestEvaluationSubmission(db.Model):
    """
    游客评价提交表 (guest_evaluation_submission)
    游客提交先入待审核，管理员通过后再写入正式评价表。
    """
    __tablename__ = 'guest_evaluation_submission'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    canteen_id = db.Column(db.Integer, db.ForeignKey('canteen.id'), nullable=False, comment='食堂ID')
    window_id = db.Column(db.Integer, db.ForeignKey('window.id'), nullable=False, comment='窗口ID')
    buy_time = db.Column(db.DateTime, nullable=False, comment='购买时间')
    identity_type = db.Column(db.String(50), default='visitor', nullable=False, comment='身份类型')
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
    dishes_json = db.Column(db.JSON, comment='菜品评价JSON')
    template_version = db.Column(db.Integer, comment='评价模板版本ID')
    status = db.Column(db.String(20), default='pending', nullable=False, comment='状态 pending/approved/rejected')
    reject_reason = db.Column(db.String(255), default='', nullable=False, comment='驳回原因')
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'), comment='审核人ID')
    reviewed_time = db.Column(db.DateTime, comment='审核时间')
    submit_ip = db.Column(db.String(64), default='', nullable=False, comment='提交IP')
    user_agent = db.Column(db.String(255), default='', nullable=False, comment='提交UA')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='提交时间')


class EvaluationTemplateVersion(db.Model):
    """
    评价模板版本表 (evaluation_template_version)
    """
    __tablename__ = 'evaluation_template_version'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    version_no = db.Column(db.Integer, nullable=False, unique=True, comment='模板版本号')
    name = db.Column(db.String(100), nullable=False, comment='模板名称')
    status = db.Column(db.String(20), default='draft', nullable=False, comment='状态 draft/active/archived')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), comment='创建人ID')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    publish_time = db.Column(db.DateTime, comment='发布时间')


class EvaluationTemplateItem(db.Model):
    """
    评价模板细项表 (evaluation_template_item)
    """
    __tablename__ = 'evaluation_template_item'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    version_id = db.Column(db.Integer, db.ForeignKey('evaluation_template_version.id'), nullable=False, comment='模板版本ID')
    category = db.Column(db.String(30), nullable=False, comment='维度类别 food/service/env/safety')
    item_key = db.Column(db.String(60), nullable=False, comment='细项编码')
    item_label = db.Column(db.String(120), nullable=False, comment='细项名称')
    sort_order = db.Column(db.Integer, default=0, nullable=False, comment='排序')
    score_min = db.Column(db.Integer, default=1, nullable=False, comment='最小分')
    score_max = db.Column(db.Integer, default=10, nullable=False, comment='最大分')
    enabled = db.Column(db.Boolean, default=True, nullable=False, comment='是否启用')


class AdminActionLog(db.Model):
    """
    管理动作审计日志表 (admin_action_log)
    记录管理员/运营关键动作，便于追踪与审计。
    """
    __tablename__ = 'admin_action_log'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, comment='操作者ID')
    actor_role = db.Column(db.String(20), default='', nullable=False, comment='操作者角色')
    action = db.Column(db.String(60), nullable=False, comment='动作编码')
    target_type = db.Column(db.String(40), default='', nullable=False, comment='目标类型')
    target_id = db.Column(db.Integer, default=0, nullable=False, comment='目标ID')
    before_data = db.Column(db.Text, default='', nullable=False, comment='变更前快照JSON')
    after_data = db.Column(db.Text, default='', nullable=False, comment='变更后快照JSON')
    detail = db.Column(db.Text, default='', nullable=False, comment='动作详情JSON')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')


class EvaluationRiskFlag(db.Model):
    """
    异常评价风险标记表 (evaluation_risk_flag)
    """
    __tablename__ = 'evaluation_risk_flag'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    campus_id = db.Column(db.Integer, default=1, nullable=False, comment='校区/租户ID')
    evaluation_id = db.Column(db.Integer, db.ForeignKey('evaluation_main.id'), nullable=False, unique=True, comment='关联评价ID')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, comment='评价用户ID')
    canteen_id = db.Column(db.Integer, db.ForeignKey('canteen.id'), nullable=True, comment='食堂ID')
    window_id = db.Column(db.Integer, db.ForeignKey('window.id'), nullable=True, comment='窗口ID')
    risk_score = db.Column(db.Integer, default=0, nullable=False, comment='风险分(0-100)')
    risk_level = db.Column(db.String(20), default='low', nullable=False, comment='风险等级 low/medium/high/critical')
    rule_hits = db.Column(db.JSON, comment='命中规则JSON')
    status = db.Column(db.String(20), default='pending', nullable=False, comment='复核状态 pending/approved/rejected/watch')
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, comment='复核人ID')
    review_note = db.Column(db.Text, default='', nullable=False, comment='复核备注')
    reviewed_time = db.Column(db.DateTime, nullable=True, comment='复核时间')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')


class RectificationWorkOrder(db.Model):
    """
    整改工单表 (rectification_work_order)
    """
    __tablename__ = 'rectification_work_order'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    campus_id = db.Column(db.Integer, default=1, nullable=False, comment='校区/租户ID')
    source_type = db.Column(db.String(30), default='risk_flag', nullable=False, comment='来源类型 risk_flag/warning/manual')
    source_id = db.Column(db.Integer, default=0, nullable=False, comment='来源业务ID')
    canteen_id = db.Column(db.Integer, db.ForeignKey('canteen.id'), nullable=True, comment='食堂ID')
    window_id = db.Column(db.Integer, db.ForeignKey('window.id'), nullable=True, comment='窗口ID')
    title = db.Column(db.String(200), nullable=False, comment='工单标题')
    issue_desc = db.Column(db.Text, default='', nullable=False, comment='问题描述')
    priority = db.Column(db.String(20), default='medium', nullable=False, comment='优先级 low/medium/high/urgent')
    status = db.Column(db.String(20), default='pending', nullable=False, comment='状态 pending/processing/review/completed/archived')
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, comment='责任人ID')
    due_time = db.Column(db.DateTime, nullable=True, comment='截止时间(SLA)')
    started_time = db.Column(db.DateTime, nullable=True, comment='开始处理时间')
    review_time = db.Column(db.DateTime, nullable=True, comment='进入复核时间')
    completed_time = db.Column(db.DateTime, nullable=True, comment='完成时间')
    archived_time = db.Column(db.DateTime, nullable=True, comment='归档时间')
    is_overdue = db.Column(db.Boolean, default=False, nullable=False, comment='是否逾期')
    overdue_notified = db.Column(db.Boolean, default=False, nullable=False, comment='是否已通知逾期')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, comment='创建人ID')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')


class WorkOrderActionLog(db.Model):
    """
    工单流转日志表 (work_order_action_log)
    """
    __tablename__ = 'work_order_action_log'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('rectification_work_order.id'), nullable=False, comment='工单ID')
    campus_id = db.Column(db.Integer, default=1, nullable=False, comment='校区/租户ID')
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, comment='操作人ID')
    action = db.Column(db.String(40), nullable=False, comment='动作编码')
    from_status = db.Column(db.String(20), default='', nullable=False, comment='原状态')
    to_status = db.Column(db.String(20), default='', nullable=False, comment='新状态')
    note = db.Column(db.Text, default='', nullable=False, comment='备注')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')


class RecommendationEvent(db.Model):
    """
    推荐实验事件表 (recommendation_event)
    记录曝光/点击，用于A/B实验效果评估。
    """
    __tablename__ = 'recommendation_event'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    request_id = db.Column(db.String(64), default='', nullable=False, comment='一次推荐请求ID')
    event_type = db.Column(db.String(20), default='exposure', nullable=False, comment='事件类型 exposure/click')
    variant = db.Column(db.String(10), default='A', nullable=False, comment='实验分组 A/B')
    strategy = db.Column(db.String(30), default='baseline', nullable=False, comment='策略名称')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, comment='用户ID(可空)')
    campus_id = db.Column(db.Integer, default=1, nullable=False, comment='校区ID')
    canteen_id = db.Column(db.Integer, nullable=True, comment='食堂ID')
    dish_id = db.Column(db.Integer, nullable=False, comment='菜品ID')
    position = db.Column(db.Integer, default=0, nullable=False, comment='卡片位置(从1开始)')
    page = db.Column(db.String(30), default='unknown', nullable=False, comment='页面标识 index/rank/user_center')
    user_segment = db.Column(db.String(20), default='anonymous', nullable=False, comment='用户分层 anonymous/new/returning')
    propensity = db.Column(db.Float, default=0.5, nullable=False, comment='日志策略概率(用于IPS/DR)')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')


class RecommendationAbTuning(db.Model):
    """
    推荐A/B调参配置表 (recommendation_ab_tuning)
    按校区维护探索系数。
    """
    __tablename__ = 'recommendation_ab_tuning'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    campus_id = db.Column(db.Integer, nullable=False, unique=True, comment='校区ID')
    explore_multiplier = db.Column(db.Float, default=1.0, nullable=False, comment='探索强度系数')
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, comment='最后更新人ID')
    update_note = db.Column(db.String(255), default='', nullable=False, comment='更新备注')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')


class RecommendationAbTuningLog(db.Model):
    """
    推荐A/B调参日志表 (recommendation_ab_tuning_log)
    记录每次系数变更，支持追踪与回滚。
    """
    __tablename__ = 'recommendation_ab_tuning_log'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    campus_id = db.Column(db.Integer, nullable=False, comment='校区ID')
    before_multiplier = db.Column(db.Float, default=1.0, nullable=False, comment='调整前系数')
    after_multiplier = db.Column(db.Float, default=1.0, nullable=False, comment='调整后系数')
    trigger_type = db.Column(db.String(20), default='manual', nullable=False, comment='触发类型 auto/manual/rollback')
    reason = db.Column(db.String(255), default='', nullable=False, comment='调整原因')
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, comment='操作人ID')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')


class RecommendationAbPolicy(db.Model):
    """
    推荐A/B策略参数表 (recommendation_ab_policy)
    按校区配置调参阈值与步长。
    """
    __tablename__ = 'recommendation_ab_policy'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    campus_id = db.Column(db.Integer, nullable=False, unique=True, comment='校区ID')
    min_exposure = db.Column(db.Integer, default=30, nullable=False, comment='最小曝光阈值')
    ctr_delta_threshold = db.Column(db.Float, default=1.0, nullable=False, comment='CTR差异阈值(百分点)')
    step_up = db.Column(db.Float, default=0.05, nullable=False, comment='上调步长')
    step_down = db.Column(db.Float, default=0.10, nullable=False, comment='下调步长')
    min_multiplier = db.Column(db.Float, default=0.4, nullable=False, comment='探索系数下限')
    max_multiplier = db.Column(db.Float, default=2.0, nullable=False, comment='探索系数上限')
    guard_enabled = db.Column(db.Boolean, default=True, nullable=False, comment='是否启用自动保护回滚')
    guard_pvalue_threshold = db.Column(db.Float, default=0.1, nullable=False, comment='劣化显著性阈值')
    guard_ctr_drop_threshold = db.Column(db.Float, default=0.8, nullable=False, comment='CTR劣化阈值(百分点)')
    guard_consecutive_limit = db.Column(db.Integer, default=2, nullable=False, comment='连续劣化触发次数')
    optimize_mode = db.Column(db.String(20), default='ab', nullable=False, comment='优化模式 ab/bandit')
    bandit_alpha = db.Column(db.Float, default=1.0, nullable=False, comment='Bandit先验alpha')
    bandit_beta = db.Column(db.Float, default=1.0, nullable=False, comment='Bandit先验beta')
    weight_ctr = db.Column(db.Float, default=0.4, nullable=False, comment='多目标权重-CTR代理')
    weight_satisfaction = db.Column(db.Float, default=0.3, nullable=False, comment='多目标权重-满意度')
    weight_safety = db.Column(db.Float, default=0.2, nullable=False, comment='多目标权重-食安')
    weight_diversity = db.Column(db.Float, default=0.1, nullable=False, comment='多目标权重-多样性')
    fairness_lambda = db.Column(db.Float, default=0.2, nullable=False, comment='公平约束惩罚系数')
    fairness_top_share_limit = db.Column(db.Float, default=0.35, nullable=False, comment='单食堂曝光占比上限')
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, comment='最后更新人ID')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')
