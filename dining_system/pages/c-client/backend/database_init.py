import os
import sys
import uuid
from werkzeug.security import generate_password_hash

# Adjust path to import app and models
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app import app, db
from models import UserIdentity, User, Canteen, Window, Dish, SensitiveWord

def init_db():
    with app.app_context():
        # Ensure database directory exists
        db_dir = os.path.dirname(app.config['DB_PATH'])
        os.makedirs(db_dir, exist_ok=True)

        # Create all tables
        db.create_all()
        print("All tables created.")
        
        # 1. Insert System Roles
        if not UserIdentity.query.first():
            roles = [
                {'name': 'admin', 'display_name': '管理员'},
                {'name': 'student', 'display_name': '学生'},
                {'name': 'teacher', 'display_name': '教师'},
                {'name': 'staff', 'display_name': '员工'},
                {'name': 'visitor', 'display_name': '游客'}
            ]
            for role in roles:
                db.session.add(UserIdentity(**role))
            db.session.commit()
            print("Roles inserted.")

        # 2. Insert Admin Account
        admin_role = UserIdentity.query.filter_by(name='admin').first()
        if admin_role and not User.query.filter_by(username='admin').first():
            admin_user = User(
                username='admin',
                password=generate_password_hash('123456'),
                nickname='系统管理员',
                identity_id=admin_role.id
            )
            db.session.add(admin_user)
            db.session.commit()
            print("Admin account inserted.")

        # 3. Insert Initial Canteens
        if not Canteen.query.first():
            canteens = [
                Canteen(name='第一食堂', location='东区', opening_hours='06:30-22:00'),
                Canteen(name='第二食堂', location='西区', opening_hours='06:30-22:00')
            ]
            db.session.add_all(canteens)
            db.session.commit()
            print("Canteens inserted.")

        # 4. Insert Initial Windows
        if not Window.query.first():
            canteen1 = Canteen.query.filter_by(name='第一食堂').first()
            canteen2 = Canteen.query.filter_by(name='第二食堂').first()
            windows = [
                Window(canteen_id=canteen1.id, name='特色面食'),
                Window(canteen_id=canteen1.id, name='自选快餐'),
                Window(canteen_id=canteen2.id, name='麻辣香锅'),
                Window(canteen_id=canteen2.id, name='风味小吃')
            ]
            db.session.add_all(windows)
            db.session.commit()
            print("Windows inserted.")

        # 5. Insert Initial Dishes
        if not Dish.query.first():
            window1 = Window.query.filter_by(name='特色面食').first()
            window2 = Window.query.filter_by(name='自选快餐').first()
            dishes = [
                Dish(id=str(uuid.uuid4()), canteen_id=window1.canteen_id, window_id=window1.id, name='牛肉面', price=12.0, category='面食'),
                Dish(id=str(uuid.uuid4()), canteen_id=window1.canteen_id, window_id=window1.id, name='鸡蛋面', price=8.0, category='面食'),
                Dish(id=str(uuid.uuid4()), canteen_id=window2.canteen_id, window_id=window2.id, name='红烧肉盖饭', price=15.0, category='快餐'),
                Dish(id=str(uuid.uuid4()), canteen_id=window2.canteen_id, window_id=window2.id, name='番茄炒蛋盖饭', price=10.0, category='快餐')
            ]
            db.session.add_all(dishes)
            db.session.commit()
            print("Dishes inserted.")

        # 6. Insert Initial Sensitive Words
        if not SensitiveWord.query.first():
            words = [
                SensitiveWord(word='垃圾', level=2),
                SensitiveWord(word='脏', level=1),
                SensitiveWord(word='恶心', level=3),
                SensitiveWord(word='难吃', level=1)
            ]
            db.session.add_all(words)
            db.session.commit()
            print("Sensitive words inserted.")

        print("Database initialization completed successfully.")

if __name__ == '__main__':
    init_db()
