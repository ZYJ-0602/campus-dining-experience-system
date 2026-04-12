import pytest
import shutil
from pathlib import Path
from werkzeug.security import generate_password_hash

from app import app, db
from models import Campus, Canteen, Dish, User, Window


@pytest.fixture()
def client(tmp_path):
    real_db_path = Path(app.root_path) / 'dining_system.db'
    real_db_backup_path = tmp_path / 'real_db_backup.db'
    if real_db_path.exists():
        shutil.copy2(real_db_path, real_db_backup_path)

    test_db = tmp_path / 'pytest_isolated.db'
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{test_db.as_posix()}",
        WTF_CSRF_ENABLED=False,
        SECRET_KEY='test-secret',
    )

    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()

        campus = Campus(name='默认校区', code='campus-1', is_active=True, sort_order=1)
        canteen = Canteen(name='测试食堂', address='测试地址', is_active=True)
        db.session.add_all([campus, canteen])
        db.session.flush()

        window = Window(canteen_id=canteen.id, name='测试窗口')
        db.session.add(window)
        db.session.flush()

        dish = Dish(window_id=window.id, name='测试菜品', price=10.0)
        user = User(username='tester', password=generate_password_hash('123456'), role='student')
        db.session.add_all([user, dish])
        db.session.commit()

    with app.test_client() as test_client:
        try:
            yield test_client
        finally:
            if real_db_backup_path.exists():
                with app.app_context():
                    db.session.remove()
                shutil.copy2(real_db_backup_path, real_db_path)
