from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, Boolean, ForeignKey, Table, UniqueConstraint, Index
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime

# 定义数据库文件路径
DB_URI = 'sqlite:///canteen_evaluation.db'

# 创建基类
Base = declarative_base()

# 定义基础模型 Mixin，包含通用字段
class BaseModel:
    """所有表的基类，包含通用字段"""
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    create_time = Column(DateTime, default=datetime.now, nullable=False, comment='创建时间')
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')
    is_active = Column(Boolean, default=True, nullable=False, comment='是否启用(1=启用,0=禁用)')

# 3. 用户角色关联表 (多对多)
user_role_association = Table(
    'user_role',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('user.id'), primary_key=True, comment='用户ID'),
    Column('role_id', Integer, ForeignKey('role.id'), primary_key=True, comment='角色ID')
)

# 1. 角色表
class Role(BaseModel, Base):
    __tablename__ = 'role'
    __table_args__ = {'comment': '角色表'}

    name = Column(String(50), unique=True, nullable=False, comment='角色名称(如:管理员,普通用户)')
    code = Column(String(50), unique=True, nullable=False, comment='角色编码(如:admin,user)')
    description = Column(String(200), comment='角色描述')

    # 关联关系
    users = relationship('User', secondary=user_role_association, back_populates='roles')

# 2. 用户表
class User(BaseModel, Base):
    __tablename__ = 'user'
    __table_args__ = (
        Index('idx_user_username', 'username'),
        Index('idx_user_phone', 'phone'),
        {'comment': '用户表'}
    )

    username = Column(String(50), nullable=False, unique=True, comment='用户名')
    password_hash = Column(String(128), nullable=False, comment='加密密码')
    phone = Column(String(20), unique=True, comment='手机号')
    nickname = Column(String(50), comment='昵称')
    avatar_url = Column(String(255), comment='头像URL')
    
    # 关联关系
    roles = relationship('Role', secondary=user_role_association, back_populates='users')
    evaluations = relationship('Evaluation', back_populates='user')
    posts = relationship('Post', back_populates='user')

# 4. 食堂表
class Canteen(BaseModel, Base):
    __tablename__ = 'canteen'
    __table_args__ = {'comment': '食堂表'}

    name = Column(String(100), nullable=False, unique=True, comment='食堂名称')
    location = Column(String(200), comment='地理位置')
    opening_hours = Column(String(100), comment='营业时间')
    description = Column(Text, comment='食堂简介')
    cover_url = Column(String(255), comment='封面图URL')

    # 关联关系
    windows = relationship('Window', back_populates='canteen')
    posts = relationship('Post', back_populates='canteen')
    safety_notices = relationship('SafetyNotice', back_populates='canteen')

# 5. 窗口表
class Window(BaseModel, Base):
    __tablename__ = 'window'
    __table_args__ = {'comment': '食堂窗口表'}

    canteen_id = Column(Integer, ForeignKey('canteen.id'), nullable=False, comment='归属食堂ID')
    name = Column(String(100), nullable=False, comment='窗口名称')
    floor = Column(Integer, default=1, comment='所在楼层')
    category = Column(String(50), comment='经营品类(如:面食,快餐)')
    manager_name = Column(String(50), comment='负责人姓名')
    
    # 关联关系
    canteen = relationship('Canteen', back_populates='windows')
    dishes = relationship('Dish', back_populates='window')
    evaluations = relationship('Evaluation', back_populates='window')

# 6. 菜品表
class Dish(BaseModel, Base):
    __tablename__ = 'dish'
    __table_args__ = {'comment': '菜品表'}

    window_id = Column(Integer, ForeignKey('window.id'), nullable=False, comment='归属窗口ID')
    name = Column(String(100), nullable=False, comment='菜品名称')
    price = Column(Float, nullable=False, comment='价格')
    description = Column(String(255), comment='菜品描述')
    image_url = Column(String(255), comment='菜品图片URL')
    is_recommend = Column(Boolean, default=False, comment='是否推荐')

    # 关联关系
    window = relationship('Window', back_populates='dishes')
    evaluations = relationship('Evaluation', back_populates='dish')
    posts = relationship('Post', back_populates='dish')

# 7. 评价表
class Evaluation(BaseModel, Base):
    __tablename__ = 'evaluation'
    __table_args__ = (
        Index('idx_eval_window', 'window_id'),
        {'comment': '评价表'}
    )

    user_id = Column(Integer, ForeignKey('user.id'), nullable=False, comment='用户ID')
    window_id = Column(Integer, ForeignKey('window.id'), nullable=False, comment='窗口ID')
    dish_id = Column(Integer, ForeignKey('dish.id'), nullable=True, comment='关联菜品ID(可选)')
    
    # 四维评分
    score_food = Column(Float, nullable=False, comment='口味评分(1-10)')
    score_environment = Column(Float, nullable=False, comment='环境评分(1-10)')
    score_service = Column(Float, nullable=False, comment='服务评分(1-10)')
    score_safety = Column(Float, nullable=False, comment='食安评分(1-10)')
    
    tags = Column(String(500), comment='评价标签(JSON或逗号分隔)')
    content = Column(Text, comment='评价内容')
    images = Column(Text, comment='评价图片(JSON数组)')
    reply_content = Column(Text, comment='商家回复内容')
    reply_time = Column(DateTime, comment='回复时间')

    # 关联关系
    user = relationship('User', back_populates='evaluations')
    window = relationship('Window', back_populates='evaluations')
    dish = relationship('Dish', back_populates='evaluations')

# 8. 笔记表
class Post(BaseModel, Base):
    __tablename__ = 'post'
    __table_args__ = {'comment': '社区笔记表'}

    user_id = Column(Integer, ForeignKey('user.id'), nullable=False, comment='发布者ID')
    canteen_id = Column(Integer, ForeignKey('canteen.id'), nullable=True, comment='关联食堂ID')
    dish_id = Column(Integer, ForeignKey('dish.id'), nullable=True, comment='关联菜品ID')
    
    title = Column(String(100), nullable=False, comment='笔记标题')
    content = Column(Text, nullable=False, comment='笔记正文')
    images = Column(Text, comment='图片列表(JSON数组)')
    tags = Column(String(200), comment='话题标签')
    
    view_count = Column(Integer, default=0, comment='浏览量')
    like_count = Column(Integer, default=0, comment='点赞量')
    status = Column(Integer, default=0, comment='状态(0=待审核,1=通过,2=驳回)')
    reject_reason = Column(String(200), comment='驳回原因')

    # 关联关系
    user = relationship('User', back_populates='posts')
    canteen = relationship('Canteen', back_populates='posts')
    dish = relationship('Dish', back_populates='posts')

# 9. 食安公示表
class SafetyNotice(BaseModel, Base):
    __tablename__ = 'safety_notice'
    __table_args__ = {'comment': '食安公示表'}

    canteen_id = Column(Integer, ForeignKey('canteen.id'), nullable=False, comment='归属食堂ID')
    title = Column(String(100), nullable=False, comment='公示标题(如:食品经营许可证)')
    type = Column(String(50), nullable=False, comment='类型(certificate=证书, report=检测报告)')
    image_url = Column(String(255), nullable=False, comment='证书/报告图片URL')
    expire_date = Column(DateTime, nullable=True, comment='有效期截止')
    
    # 关联关系
    canteen = relationship('Canteen', back_populates='safety_notices')

# 10. 敏感词表
class SensitiveWord(BaseModel, Base):
    __tablename__ = 'sensitive_word'
    __table_args__ = {'comment': '敏感词表'}

    word = Column(String(50), unique=True, nullable=False, comment='敏感词汇')
    action_type = Column(String(20), default='block', comment='处理方式(block=拦截, replace=替换)')
    replace_to = Column(String(50), default='***', comment='替换后的字符')

def init_db():
    """初始化数据库并创建表"""
    engine = create_engine(DB_URI, echo=True)  # echo=True 会打印生成的 SQL 语句
    
    print(">>> 开始创建数据库表结构...")
    Base.metadata.create_all(engine)
    print(">>> 所有表创建成功！")
    print(f">>> 数据库文件已生成: {DB_URI}")

if __name__ == '__main__':
    init_db()
