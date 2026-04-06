import pytest
from werkzeug.security import generate_password_hash

from app import app, db
from models import Campus, Canteen, Dish, User, Window


@pytest.fixture()
def client():
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        WTF_CSRF_ENABLED=False,
        SECRET_KEY='test-secret',
    )

    with app.app_context():
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
        yield test_client
