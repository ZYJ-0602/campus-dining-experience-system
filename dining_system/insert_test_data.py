from app import app
from extensions import db
from models import User, Canteen, Window, Dish, EvaluationMain, EvaluationDish
from datetime import datetime
from werkzeug.security import generate_password_hash

def insert_data():
    with app.app_context():
        print("正在重建数据库...")
        db.drop_all()
        db.create_all()
        
        # 1. 用户
        print("插入用户...")
        u1 = User(username='student1', password=generate_password_hash('123456'), role='student')
        u2 = User(username='teacher1', password=generate_password_hash('123456'), role='teacher')
        db.session.add_all([u1, u2])
        db.session.commit()
        
        # 2. 食堂
        print("插入食堂...")
        c1 = Canteen(name='第一食堂', address='校园北区', is_active=True)
        c2 = Canteen(name='第二食堂', address='校园南区', is_active=True)
        db.session.add_all([c1, c2])
        db.session.commit()
        
        # 3. 窗口
        print("插入窗口...")
        w1 = Window(canteen_id=c1.id, name='川菜窗口')
        w2 = Window(canteen_id=c1.id, name='面食窗口')
        w3 = Window(canteen_id=c2.id, name='自选窗口')
        db.session.add_all([w1, w2, w3])
        db.session.commit()
        
        # 4. 菜品
        print("插入菜品...")
        d1 = Dish(window_id=w1.id, name='麻婆豆腐', img_url='mapo.jpg')
        d2 = Dish(window_id=w1.id, name='回锅肉', img_url='huiguo.jpg')
        d3 = Dish(window_id=w2.id, name='牛肉面', img_url='beef_noodle.jpg')
        d4 = Dish(window_id=w3.id, name='红烧排骨', img_url='ribs.jpg')
        db.session.add_all([d1, d2, d3, d4])
        db.session.commit()
        
        # 5. 评价数据
        print("插入评价数据...")
        # 评价1：学生评价川菜窗口
        e1 = EvaluationMain(
            user_id=u1.id,
            canteen_id=c1.id,
            window_id=w1.id,
            buy_time=datetime.strptime('2023-10-01 12:00', '%Y-%m-%d %H:%M'),
            identity_type='student',
            grade='大二',
            age=20,
            dining_years=2,
            env_scores={'comfort': 4, 'cleanliness': 5},
            service_scores={'attitude': 5, 'speed': 4}
        )
        db.session.add(e1)
        db.session.flush()
        
        ed1 = EvaluationDish(
            evaluation_id=e1.id,
            dish_id=d1.id,
            dish_name=d1.name,
            food_scores={'taste': 5, 'color': 4, 'price': 5},
            remark='味道很正宗，价格便宜'
        )
        ed2 = EvaluationDish(
            evaluation_id=e1.id,
            dish_id=d2.id,
            dish_name=d2.name,
            food_scores={'taste': 4, 'color': 5, 'portion': 3},
            remark='肉有点少'
        )
        db.session.add_all([ed1, ed2])
        
        # 评价2：老师评价面食窗口
        e2 = EvaluationMain(
            user_id=u2.id,
            canteen_id=c1.id,
            window_id=w2.id,
            buy_time=datetime.strptime('2023-10-02 11:30', '%Y-%m-%d %H:%M'),
            identity_type='teacher',
            env_scores={'comfort': 3, 'cleanliness': 4},
            service_scores={'attitude': 4, 'speed': 5}
        )
        db.session.add(e2)
        db.session.flush()
        
        ed3 = EvaluationDish(
            evaluation_id=e2.id,
            dish_id=d3.id,
            dish_name=d3.name,
            food_scores={'taste': 5, 'price': 4, 'speed': 5},
            remark='面条劲道，汤头鲜美'
        )
        db.session.add(ed3)
        
        db.session.commit()
        print("测试数据插入完成！")

if __name__ == '__main__':
    insert_data()
