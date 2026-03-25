import pytest
from werkzeug.security import generate_password_hash

from app import app, db
from models import User, Canteen, Window, Dish, EvaluationMain, SubmitGuard


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
        user = User(username='tester', password=generate_password_hash('123456'), role='student')
        canteen = Canteen(name='测试食堂', address='测试地址', is_active=True)
        db.session.add(canteen)
        db.session.flush()

        window = Window(canteen_id=canteen.id, name='测试窗口')
        db.session.add(window)
        db.session.flush()

        dish = Dish(window_id=window.id, name='测试菜品', price=10.0)
        db.session.add_all([user, dish])
        db.session.commit()

    with app.test_client() as test_client:
        yield test_client


def test_register_success(client):
    resp = client.post('/api/register', json={'username': 'new_user', 'password': '123456'})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body['code'] == 200
    assert body['data']['username'] == 'new_user'


def test_login_and_auth_me(client):
    login_resp = client.post('/api/login', json={'username': 'tester', 'password': '123456'})
    login_body = login_resp.get_json()
    assert login_resp.status_code == 200
    assert login_body['code'] == 200

    me_resp = client.get('/api/auth/me')
    me_body = me_resp.get_json()
    assert me_resp.status_code == 200
    assert me_body['data']['username'] == 'tester'


def test_unauthorized_submit(client):
    resp = client.post('/api/submit_evaluation', json={})
    body = resp.get_json()
    assert resp.status_code == 401
    assert body['code'] == 401


def test_notes_endpoint_shape(client):
    resp = client.get('/api/notes')
    body = resp.get_json()
    assert resp.status_code == 200
    assert body['code'] == 200
    assert 'list' in body['data']


def test_duplicate_submit_blocked_within_window(client):
    client.post('/api/login', json={'username': 'tester', 'password': '123456'})

    payload = {
        'canteen_id': 1,
        'window_id': 1,
        'buy_time': '2026-03-22T12:00',
        'identity_type': 'student',
        'dishes': [
            {
                'dish_id': 1,
                'dish_name': '测试菜品',
                'food_scores': {'taste': 8},
            }
        ],
        'env_scores': {'cleanliness': 8},
        'service_scores': {'attitude': 8},
        'safety_scores': {'hygiene': 8},
    }

    first = client.post('/api/submit_evaluation', json=payload)
    second = client.post('/api/submit_evaluation', json=payload)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.get_json()['code'] == 429

    with app.app_context():
        guard = SubmitGuard.query.filter_by(user_id=1, window_id=1).first()
        assert guard is not None
        assert guard.block_count >= 1
        assert guard.last_block_time is not None


def test_save_endpoint_allows_repeated_save(client):
    client.post('/api/login', json={'username': 'tester', 'password': '123456'})

    payload = {
        'canteen_id': 1,
        'window_id': 1,
        'buy_time': '2026-03-22T12:30',
        'identity_type': 'student',
        'dishes': [
            {
                'dish_id': 1,
                'dish_name': '测试菜品',
                'food_scores': {'taste': 8},
            }
        ],
    }

    first = client.post('/api/evaluation/save', json=payload)
    second = client.post('/api/evaluation/save', json=payload)

    assert first.status_code == 200
    assert second.status_code == 200


def test_submit_not_blocked_after_save_only(client):
    client.post('/api/login', json={'username': 'tester', 'password': '123456'})

    payload = {
        'canteen_id': 1,
        'window_id': 1,
        'buy_time': '2026-03-22T12:40',
        'identity_type': 'student',
        'dishes': [
            {
                'dish_id': 1,
                'dish_name': '测试菜品',
                'food_scores': {'taste': 8},
            }
        ],
    }

    save_resp = client.post('/api/evaluation/save', json=payload)
    submit_resp = client.post('/api/submit_evaluation', json=payload)

    assert save_resp.status_code == 200
    assert submit_resp.status_code == 200


def test_submit_supports_dimension_comments_and_images(client):
    client.post('/api/login', json={'username': 'tester', 'password': '123456'})

    payload = {
        'canteen_id': 1,
        'window_id': 1,
        'buy_time': '2026-03-22T13:00',
        'identity_type': 'student',
        'dishes': [
            {
                'dish_id': 1,
                'dish_name': '测试菜品',
                'food_scores': {'taste': 8, 'appearance': 7},
            }
        ],
        'env_scores': {'cleanliness': 9},
        'service_scores': {'attitude': 8},
        'safety_scores': {'hygiene': 9},
        'service_comment': '服务整体不错',
        'service_images': ['https://img.test/service1.png'],
        'env_comment': '环境干净',
        'env_images': ['https://img.test/env1.png'],
        'safety_comment': '后厨公示齐全',
        'safety_images': ['https://img.test/safety1.png'],
    }

    submit_resp = client.post('/api/submit_evaluation', json=payload)
    assert submit_resp.status_code == 200
    body = submit_resp.get_json()
    assert body['data']['comprehensive_score'] > 0

    my_eval_resp = client.get('/api/my_evaluations')
    assert my_eval_resp.status_code == 200
    first = my_eval_resp.get_json()['data'][0]
    assert first['service_comment'] == '服务整体不错'
    assert first['service_images'] == ['https://img.test/service1.png']
    assert first['env_comment'] == '环境干净'
    assert first['safety_comment'] == '后厨公示齐全'

    with app.app_context():
        latest = EvaluationMain.query.order_by(EvaluationMain.id.desc()).first()
        assert latest is not None
        assert latest.service_comment == '服务整体不错'
        assert latest.service_images == ['https://img.test/service1.png']
        assert latest.env_comment == '环境干净'
        assert latest.env_images == ['https://img.test/env1.png']
        assert latest.safety_comment == '后厨公示齐全'
        assert latest.safety_images == ['https://img.test/safety1.png']
