from backend.app import app, db
from backend.models import User, UserIdentity, Canteen, Window, Dish, EvaluationMain, EvaluationDish
from werkzeug.security import generate_password_hash
from datetime import datetime

def insert_data():
    with app.app_context():
        # ... (保留原有删除和创建表逻辑，如果想保留数据可以注释掉 db.drop_all)
        print("Recreating database...")
        db.drop_all()
        db.create_all()
        
        # 1. User Identity (重新定义，确保ID对应关系明确)
        # ID 1: 管理员 (Admin)
        # ID 2: 学生 (Student) / 普通用户
        # ID 3: 食堂运营 (Canteen Operator)
        print("Inserting identities...")
        identities = [
            UserIdentity(id=1, name='admin', display_name='管理员'),
            UserIdentity(id=2, name='student', display_name='学生'),
            UserIdentity(id=3, name='operator', display_name='食堂运营'),
            UserIdentity(id=4, name='teacher', display_name='教师')
        ]
        db.session.add_all(identities)
        db.session.commit()
        
        # 2. Users
        print("Inserting users...")
        # 普通用户
        u1 = User(username='test1234', password=generate_password_hash('123456'), nickname='测试学生', identity_id=2)
        # 系统管理员
        u2 = User(username='admin', password=generate_password_hash('123456'), nickname='超级管理员', identity_id=1)
        # 食堂运营者
        u3 = User(username='canteen_op', password=generate_password_hash('123456'), nickname='北区食堂经理', identity_id=3)
        
        db.session.add_all([u1, u2, u3])
        db.session.commit()
        
        # ... (后续 Canteens, Windows, Dishes 保持不变)
        
        # 3. Canteens
        print("Inserting canteens...")
        c1 = Canteen(name='北区食堂', location='校园北区', opening_hours='06:30-22:00')
        c2 = Canteen(name='南区食堂', location='校园南区', opening_hours='07:00-21:00')
        c3 = Canteen(name='西区食堂', location='校园西区', opening_hours='07:00-23:00')
        db.session.add_all([c1, c2, c3])
        db.session.commit()
        
        # 4. Windows
        print("Inserting windows...")
        w1 = Window(canteen_id=c1.id, name='1号自选快餐')
        w2 = Window(canteen_id=c1.id, name='2号特色面馆')
        w3 = Window(canteen_id=c2.id, name='1号网红盖饭')
        db.session.add_all([w1, w2, w3])
        db.session.commit()
        
        # 5. Dishes
        print("Inserting dishes...")
        dishes = [
            Dish(window_id=w1.id, name='番茄炒蛋', price=5.0, img_url='https://via.placeholder.com/100?text=Tomato'),
            Dish(window_id=w1.id, name='红烧肉', price=12.0, img_url='https://via.placeholder.com/100?text=Pork'),
            Dish(window_id=w2.id, name='牛肉面', price=15.0, img_url='https://via.placeholder.com/100?text=BeefNoodle'),
            Dish(window_id=w3.id, name='宫保鸡丁盖饭', price=18.0, img_url='https://via.placeholder.com/100?text=ChickenRice')
        ]
        db.session.add_all(dishes)
        db.session.commit()
        
        print("Data insertion completed!")

if __name__ == '__main__':
    insert_data()
