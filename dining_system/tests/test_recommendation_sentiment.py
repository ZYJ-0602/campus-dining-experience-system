from werkzeug.security import generate_password_hash

from app import app, db
from models import User


def test_public_sentiment_analyze_returns_negative_label(client):
    resp = client.post(
        '/api/public/sentiment/analyze',
        json={'text': '今天的菜有异味，吃完有点拉肚子，服务态度也很差'},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['code'] == 200
    assert body['data']['label'] == 'negative'
    assert body['data']['risk_level'] in ('medium', 'high')
    assert body['data']['risk_score'] > 0


def test_public_recommendations_contains_sentiment_explanation(client):
    resp = client.get('/api/public/recommendations?limit=3&page=user_center')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['code'] == 200
    items = body['data']['list']
    assert isinstance(items, list)
    assert len(items) >= 1
    first = items[0]
    assert 'explanation' in first
    assert 'sentiment_penalty' in first['explanation']
    assert 'sentiment_negative_ratio' in first['explanation']


def test_admin_sentiment_overview_has_summary_and_trend(client):
    client.post('/api/login', json={'username': 'tester', 'password': '123456'})
    save_resp = client.post(
        '/api/evaluation/save',
        json={
            'canteen_id': 1,
            'window_id': 1,
            'buy_time': '2026-04-14T12:00',
            'identity_type': 'student',
            'remark': '菜有异物，感觉不卫生，态度差',
            'dishes': [{'dish_id': 1, 'dish_name': '测试菜品', 'food_scores': {'taste': 2}}],
            'env_scores': {'clean': 2},
            'service_scores': {'attitude': 2},
            'safety_scores': {'fresh': 2},
        },
    )
    assert save_resp.status_code == 200

    with app.app_context():
        admin = User(username='sentiment_admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    client.post('/api/login', json={'username': 'sentiment_admin', 'password': '123456'})
    resp = client.get('/api/admin/sentiment_overview?days=7&limit=10')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['code'] == 200
    assert 'summary' in body['data']
    assert 'trend' in body['data']
    assert 'high_risk_samples' in body['data']
    assert body['data']['summary']['negative'] >= 1


def test_admin_sentiment_report_downloads_markdown(client):
    with app.app_context():
        admin = User(username='report_admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    client.post('/api/login', json={'username': 'report_admin', 'password': '123456'})
    resp = client.get('/api/admin/sentiment_report?days=7&format=md')
    assert resp.status_code == 200
    assert 'text/markdown' in (resp.content_type or '')
    text = resp.get_data(as_text=True)
    assert '舆情监控报告' in text


def test_sentiment_monitor_page_accessible_when_logged_in(client):
    with app.app_context():
        admin = User(username='page_admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    client.post('/api/login', json={'username': 'page_admin', 'password': '123456'})
    resp = client.get('/pages/b-admin/admin_sentiment_monitor.html')
    assert resp.status_code == 200
    assert '舆情监控中心' in resp.get_data(as_text=True)
