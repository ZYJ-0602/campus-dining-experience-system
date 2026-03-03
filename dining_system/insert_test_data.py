from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import random

# 导入 create_tables.py 中定义的模型和 DB_URI
# 确保 create_tables.py 在同一目录下
from create_tables import Base, Role, User, Canteen, Window, Dish, Evaluation, Post, SafetyNotice, SensitiveWord, DB_URI, user_role_association

def generate_test_data():
    """生成并插入测试数据"""
    print(f">>> 连接数据库: {DB_URI}")
    engine = create_engine(DB_URI)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        print(">>> 开始生成测试数据...")

        # 1. 角色表 (Role)
        print("--- 插入角色数据 ---")
        roles = [
            Role(name='普通用户', code='user', description='普通学生/教职工，可评价、发笔记'),
            Role(name='食堂运营', code='operator', description='食堂/窗口管理员，可管理菜品、查看评价'),
            Role(name='系统管理员', code='admin', description='系统超级管理员，拥有所有权限')
        ]
        session.add_all(roles)
        session.commit() # 提交以获取ID
        role_user = roles[0]
        role_operator = roles[1]
        role_admin = roles[2]

        # 2. 用户表 (User)
        print("--- 插入用户数据 ---")
        users = [
            User(username='student001', password_hash='123456', phone='13800138001', nickname='干饭人小王', avatar_url='/static/avatar/1.jpg'),
            User(username='operator001', password_hash='123456', phone='13800138002', nickname='北区食堂经理', avatar_url='/static/avatar/2.jpg'),
            User(username='admin001', password_hash='123456', phone='13800138003', nickname='系统管理员', avatar_url='/static/avatar/3.jpg'),
            User(username='student002', password_hash='123456', phone='13800138004', nickname='美食探店', avatar_url='/static/avatar/4.jpg'),
            User(username='student003', password_hash='123456', phone='13800138005', nickname='吃货联盟', avatar_url='/static/avatar/5.jpg')
        ]
        session.add_all(users)
        session.commit()

        # 关联用户角色
        # student001 -> user
        session.execute(user_role_association.insert().values(user_id=users[0].id, role_id=role_user.id))
        # operator001 -> operator
        session.execute(user_role_association.insert().values(user_id=users[1].id, role_id=role_operator.id))
        # admin001 -> admin
        session.execute(user_role_association.insert().values(user_id=users[2].id, role_id=role_admin.id))
        # 其他学生 -> user
        session.execute(user_role_association.insert().values(user_id=users[3].id, role_id=role_user.id))
        session.execute(user_role_association.insert().values(user_id=users[4].id, role_id=role_user.id))
        session.commit()

        # 3. 食堂表 (Canteen)
        print("--- 插入食堂数据 ---")
        canteens = [
            Canteen(name='北区食堂', location='校园北区生活区', opening_hours='06:30-21:00', description='主打大众餐饮，价格实惠', cover_url='/static/canteen/north.jpg'),
            Canteen(name='南区食堂', location='校园南区教学区旁', opening_hours='07:00-22:00', description='特色风味窗口较多，环境优美', cover_url='/static/canteen/south.jpg'),
            Canteen(name='西区食堂', location='西区宿舍楼下', opening_hours='06:30-20:00', description='清真食堂，提供特色面食', cover_url='/static/canteen/west.jpg')
        ]
        session.add_all(canteens)
        session.commit()

        # 4. 窗口表 (Window)
        print("--- 插入窗口数据 ---")
        windows = []
        for canteen in canteens:
            for i in range(1, 4):
                windows.append(Window(
                    canteen_id=canteen.id,
                    name=f'{canteen.name}{i}号窗口',
                    floor=1 if i < 3 else 2,
                    category=random.choice(['自选快餐', '特色面食', '风味小吃', '麻辣烫', '盖浇饭']),
                    manager_name=f'经理{canteen.id}-{i}'
                ))
        session.add_all(windows)
        session.commit()

        # 5. 菜品表 (Dish)
        print("--- 插入菜品数据 ---")
        dish_names = ['番茄炒蛋', '红烧肉', '酸辣土豆丝', '宫保鸡丁', '鱼香肉丝', '糖醋排骨', '麻婆豆腐', '青椒肉丝', '红烧茄子', '清蒸鱼']
        dishes = []
        for window in windows:
            # 每个窗口随机选5个菜品
            selected_names = random.sample(dish_names, 5)
            for name in selected_names:
                dishes.append(Dish(
                    window_id=window.id,
                    name=name,
                    price=random.randint(5, 25),
                    description=f'{window.name}特色{name}，美味可口',
                    image_url=f'/static/dish/{random.randint(1,5)}.jpg',
                    is_recommend=random.choice([True, False])
                ))
        session.add_all(dishes)
        session.commit()

        # 6. 评价表 (Evaluation)
        print("--- 插入评价数据 ---")
        evaluations = []
        tags_pool = ['好吃', '分量足', '服务好', '环境干净', '性价比高', '有点咸', '排队久']
        for window in windows:
            # 每个窗口生成约3条评价
            for _ in range(3):
                user = random.choice([users[0], users[3], users[4]]) # 随机学生用户
                dish = random.choice([d for d in dishes if d.window_id == window.id]) # 该窗口下的随机菜品
                
                evaluations.append(Evaluation(
                    user_id=user.id,
                    window_id=window.id,
                    dish_id=dish.id,
                    score_food=random.randint(7, 10),
                    score_environment=random.randint(6, 9),
                    score_service=random.randint(7, 10),
                    score_safety=random.randint(8, 10),
                    tags=','.join(random.sample(tags_pool, 2)),
                    content=f'在{window.name}吃的{dish.name}，整体体验不错，推荐大家来尝尝！',
                    images='["/static/eval/1.jpg"]',
                    reply_content='感谢您的评价，我们会继续努力！' if random.random() > 0.7 else None,
                    reply_time=datetime.now() if random.random() > 0.7 else None
                ))
        session.add_all(evaluations)
        session.commit()

        # 7. 笔记表 (Post)
        print("--- 插入笔记数据 ---")
        posts = []
        post_titles = [
            "北区食堂YYDS！", "今日份红烧肉测评", "避雷！这个菜有点咸", 
            "发现宝藏窗口", "食堂阿姨手抖吗？", "西区面食一绝",
            "南区二楼环境真好", "减肥党的食堂攻略", "早餐吃什么？", "深夜放毒"
        ]
        for i in range(10):
            user = random.choice([users[0], users[3], users[4]])
            canteen = random.choice(canteens)
            posts.append(Post(
                user_id=user.id,
                canteen_id=canteen.id,
                title=post_titles[i],
                content=f"今天去{canteen.name}吃饭，味道真的惊艳到我了！大家一定要去试试...",
                images='["/static/post/1.jpg", "/static/post/2.jpg"]',
                tags="推荐,美食,校园生活",
                view_count=random.randint(100, 5000),
                like_count=random.randint(10, 500),
                status=1 # 默认审核通过
            ))
        session.add_all(posts)
        session.commit()

        # 8. 食安公示表 (SafetyNotice)
        print("--- 插入食安公示数据 ---")
        notices = []
        for canteen in canteens:
            notices.append(SafetyNotice(
                canteen_id=canteen.id,
                title=f'{canteen.name}食品经营许可证',
                type='certificate',
                image_url='/static/safety/cert.jpg',
                expire_date=datetime.now() + timedelta(days=365)
            ))
            notices.append(SafetyNotice(
                canteen_id=canteen.id,
                title=f'{canteen.name}员工健康证公示',
                type='certificate',
                image_url='/static/safety/health.jpg',
                expire_date=datetime.now() + timedelta(days=180)
            ))
            notices.append(SafetyNotice(
                canteen_id=canteen.id,
                title=f'{canteen.name}本月食材检测报告',
                type='report',
                image_url='/static/safety/report.jpg',
                expire_date=datetime.now() + timedelta(days=30)
            ))
        session.add_all(notices)
        session.commit()

        # 9. 敏感词表 (SensitiveWord)
        print("--- 插入敏感词数据 ---")
        sensitive_words = [
            SensitiveWord(word='违规词1', action_type='block'),
            SensitiveWord(word='违规词2', action_type='replace', replace_to='***'),
            SensitiveWord(word='垃圾', action_type='replace', replace_to='**'),
            SensitiveWord(word='脏话', action_type='block'),
            SensitiveWord(word='广告', action_type='block')
        ]
        session.add_all(sensitive_words)
        session.commit()

        print("\n>>> 测试数据插入成功！")
        print(f"    - 用户数: {len(users)}")
        print(f"    - 食堂数: {len(canteens)}")
        print(f"    - 窗口数: {len(windows)}")
        print(f"    - 菜品数: {len(dishes)}")
        print(f"    - 评价数: {len(evaluations)}")
        print(f"    - 笔记数: {len(posts)}")
        print(f"    - 食安公示数: {len(notices)}")
        print(f"    - 敏感词数: {len(sensitive_words)}")

    except Exception as e:
        print(f"\n>>> 插入数据失败: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == '__main__':
    generate_test_data()
