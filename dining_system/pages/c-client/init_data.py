import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
from datetime import datetime, timedelta
from backend.app import app, db
from backend.models import User, UserIdentity, Canteen, Window, Dish, EvaluationMain, EvaluationDish, SafetyCert, SystemConfig
from werkzeug.security import generate_password_hash

def init_db():
    with app.app_context():
        print("Recreating database...")
        db.drop_all()
        db.create_all()
        
        # 1. User Identity
        print("Inserting identities...")
        identities = [
            UserIdentity(id=1, name='admin', display_name='管理员'),
            UserIdentity(id=2, name='student', display_name='学生'),
            UserIdentity(id=3, name='operator', display_name='食堂运营'),
            UserIdentity(id=4, name='teacher', display_name='教师'),
            UserIdentity(id=5, name='staff', display_name='员工'),
            UserIdentity(id=6, name='visitor', display_name='游客')
        ]
        db.session.add_all(identities)
        db.session.commit()
        
        # 2. Users
        print("Inserting users...")
        u1 = User(username='student1', password=generate_password_hash('123456'), nickname='张同学', identity_id=2, gender='男', department='计算机学院')
        u2 = User(username='admin', password=generate_password_hash('123456'), nickname='超级管理员', identity_id=1)
        u3 = User(username='operator1', password=generate_password_hash('123456'), nickname='北区食堂经理', identity_id=3)
        u4 = User(username='teacher1', password=generate_password_hash('123456'), nickname='李老师', identity_id=4, department='外语学院')
        
        db.session.add_all([u1, u2, u3, u4])
        db.session.commit()
        
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
        d1 = Dish(window_id=w1.id, name='番茄炒蛋', price=5.0, category='素菜', description='经典的家常菜', img_url='https://via.placeholder.com/100?text=Tomato', tags=json.dumps(['经典', '健康']))
        d2 = Dish(window_id=w1.id, name='红烧肉', price=12.0, category='荤菜', description='肥而不腻的红烧肉', img_url='https://via.placeholder.com/100?text=Pork', tags=json.dumps(['招牌', '热销']))
        d3 = Dish(window_id=w2.id, name='牛肉面', price=15.0, category='面食', description='正宗兰州拉面', img_url='https://via.placeholder.com/100?text=BeefNoodle', tags=json.dumps(['面食', '热销']))
        d4 = Dish(window_id=w3.id, name='宫保鸡丁盖饭', price=18.0, category='套餐', description='下饭神菜', img_url='https://via.placeholder.com/100?text=ChickenRice', tags=json.dumps(['招牌']))
        db.session.add_all([d1, d2, d3, d4])
        db.session.commit()

        # 6. EvaluationMain and EvaluationDish
        print("Inserting evaluations...")
        now = datetime.now()
        eval1 = EvaluationMain(
            user_id=u1.id,
            canteen_id=c1.id,
            window_id=w1.id,
            buy_time=now - timedelta(days=1),
            identity_type='student',
            grade='大二',
            age=20,
            dining_years=2,
            env_clean=8,
            env_air=9,
            env_hygiene=8,
            service_attitude=9,
            service_speed=8,
            service_dress=9,
            safety_fresh=9,
            safety_info=8,
            comprehensive_score=8.5,
            create_time=now - timedelta(days=1),
            audit_status=1
        )
        db.session.add(eval1)
        db.session.commit()

        eval_dish1 = EvaluationDish(
            evaluation_id=eval1.id,
            dish_id=d1.id,
            dish_name=d1.name,
            price=d1.price,
            color_score=9,
            aroma_score=8,
            taste_score=9,
            shape_score=8,
            portion_score=9,
            price_score=10,
            remark='味道很好，性价比高',
            is_negative=False
        )
        eval_dish2 = EvaluationDish(
            evaluation_id=eval1.id,
            dish_id=d2.id,
            dish_name=d2.name,
            price=d2.price,
            color_score=8,
            aroma_score=8,
            taste_score=7,
            shape_score=8,
            portion_score=8,
            price_score=8,
            remark='肉稍微有点腻，其他还好',
            is_negative=False
        )
        db.session.add_all([eval_dish1, eval_dish2])
        
        eval2 = EvaluationMain(
            user_id=u4.id,
            canteen_id=c1.id,
            window_id=w2.id,
            buy_time=now - timedelta(hours=2),
            identity_type='teacher',
            env_clean=6,
            env_air=6,
            env_hygiene=6,
            service_attitude=6,
            service_speed=5,
            service_dress=7,
            safety_fresh=6,
            safety_info=6,
            comprehensive_score=6.0,
            create_time=now - timedelta(hours=1),
            audit_status=1
        )
        db.session.add(eval2)
        db.session.commit()

        eval_dish3 = EvaluationDish(
            evaluation_id=eval2.id,
            dish_id=d3.id,
            dish_name=d3.name,
            price=d3.price,
            color_score=6,
            aroma_score=6,
            taste_score=5,
            shape_score=6,
            portion_score=6,
            price_score=6,
            remark='面条坨了，汤有点咸',
            is_negative=True,
            negative_tags=json.dumps(['太咸', '口感差'])
        )
        db.session.add(eval_dish3)
        db.session.commit()

        # 7. SafetyCerts
        print("Inserting safety certificates...")
        cert1 = SafetyCert(
            canteen_id=c1.id,
            title='食品经营许可证',
            cert_type='license',
            file_url='https://via.placeholder.com/300?text=License',
            valid_start=now - timedelta(days=365),
            valid_end=now + timedelta(days=365)
        )
        db.session.add(cert1)
        db.session.commit()

        print("Database initialization completed successfully!")

if __name__ == '__main__':
    init_db()
