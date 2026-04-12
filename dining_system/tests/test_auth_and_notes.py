from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

from app import app, db
from models import User, EvaluationMain, SubmitGuard, AdminActionLog, OperatorWarning, RectificationRecord


def test_register_success(client):
    resp = client.post('/api/register', json={'username': 'new_user', 'password': '123456'})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body['code'] == 200
    assert body['data']['username'] == 'new_user'


def test_guest_status_page_offline_after_login(client):
    resp = client.get('/pages/c-client/guest_status.html')
    assert resp.status_code == 302

    client.post('/api/login', json={'username': 'tester', 'password': '123456'})
    authed_resp = client.get('/pages/c-client/guest_status.html')
    assert authed_resp.status_code == 404


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


def test_admin_create_operator_requires_canteen_binding(client):
    with app.app_context():
        admin = User(username='sys_admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    client.post('/api/login', json={'username': 'sys_admin', 'password': '123456'})

    fail_resp = client.post(
        '/api/admin/users',
        json={
            'username': 'op_without_canteen',
            'password': '123456',
            'nickname': '运营A',
            'phone': '13800138000',
            'role_id': 3,
        },
    )
    assert fail_resp.status_code == 400
    assert fail_resp.get_json()['msg'] == '食堂运营账号必须绑定食堂'

    ok_resp = client.post(
        '/api/admin/users',
        json={
            'username': 'op_with_canteen',
            'password': '123456',
            'nickname': '运营B',
            'phone': '13800138001',
            'role_id': 3,
            'operator_canteen_id': 1,
        },
    )
    assert ok_resp.status_code == 200
    assert ok_resp.get_json()['code'] == 200


def test_unbound_operator_cannot_access_operation_dashboard(client):
    with app.app_context():
        op = User(username='op_no_bind', password=generate_password_hash('123456'), role='operator')
        db.session.add(op)
        db.session.commit()

    client.post('/api/login', json={'username': 'op_no_bind', 'password': '123456'})
    resp = client.get('/api/operation/dashboard')
    assert resp.status_code == 403
    assert resp.get_json()['msg'] == '当前运营账号未绑定食堂，请联系管理员配置'


def test_guest_evaluation_submit_endpoint_disabled(client):
    payload = {
        'canteen_id': 1,
        'window_id': 1,
        'buy_time': '2026-03-22T18:00',
        'identity_type': 'visitor',
        'dishes': [{'dish_id': 1, 'dish_name': '测试菜品', 'food_scores': {'taste': 8}}],
    }
    submit_resp = client.post('/api/guest/evaluations', json=payload)
    assert submit_resp.status_code == 403
    assert submit_resp.get_json()['code'] == 403


def test_get_current_evaluation_template(client):
    resp = client.get('/api/evaluation/template/current')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['code'] == 200
    assert body['data']['id'] > 0
    assert 'items' in body['data']
    assert isinstance(body['data']['items'].get('service', []), list)


def test_admin_guest_review_endpoints_disabled(client):
    with app.app_context():
        admin = User(username='guest_closed_admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    client.post('/api/login', json={'username': 'guest_closed_admin', 'password': '123456'})

    list_resp = client.get('/api/admin/guest_evaluations?status=pending')
    assert list_resp.status_code == 410
    assert list_resp.get_json()['code'] == 410

    approve_resp = client.post('/api/admin/guest_evaluations/1/approve', json={})
    assert approve_resp.status_code == 410
    assert approve_resp.get_json()['code'] == 410

    reject_resp = client.post('/api/admin/guest_evaluations/1/reject', json={'reason': 'test'})
    assert reject_resp.status_code == 410
    assert reject_resp.get_json()['code'] == 410

    batch_resp = client.post('/api/admin/guest_evaluations/batch_review', json={'action': 'approve', 'ids': [1]})
    assert batch_resp.status_code == 410
    assert batch_resp.get_json()['code'] == 410


def test_operation_dashboard_contains_kpi_fields(client):
    with app.app_context():
        admin = User(username='kpi_admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    client.post('/api/login', json={'username': 'kpi_admin', 'password': '123456'})
    resp = client.get('/api/operation/dashboard')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['code'] == 200
    data = body['data']
    assert 'metric_dictionary_version' in data
    assert 'month_evaluation_count' in data
    assert 'month_avg_score' in data
    assert 'month_count_mom_pct' in data
    assert 'month_count_yoy_pct' in data
    assert 'month_avg_mom_delta' in data
    assert 'month_avg_yoy_delta' in data


def test_admin_metric_dictionary_endpoint(client):
    with app.app_context():
        admin = User(username='metric_admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    client.post('/api/login', json={'username': 'metric_admin', 'password': '123456'})
    resp = client.get('/api/admin/metric_dictionary?scope=operation')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['code'] == 200
    assert body['data']['scope'] == 'operation'
    assert body['data']['version']
    assert isinstance(body['data']['definitions'], list)
    keys = [item['metric_key'] for item in body['data']['definitions']]
    assert 'today_evaluation_count' in keys

    public_resp = client.get('/api/public/dashboard')
    assert public_resp.status_code == 200
    public_data = public_resp.get_json()['data']
    assert 'metric_dictionary_version' in public_data


def test_admin_sla_todos_contains_escalated_items(client):
    with app.app_context():
        admin = User(username='sla_admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    client.post('/api/login', json={'username': 'sla_admin', 'password': '123456'})
    submit_resp = client.post(
        '/api/evaluation/save',
        json={
            'canteen_id': 1,
            'window_id': 1,
            'buy_time': '2026-03-22T22:00',
            'identity_type': 'student',
            'dishes': [{'dish_id': 1, 'dish_name': '测试菜品', 'food_scores': {'taste': 2}}],
            'env_scores': {'clean': 2},
            'service_scores': {'attitude': 2},
            'safety_scores': {'fresh': 2},
        },
    )
    assert submit_resp.status_code == 200

    with app.app_context():
        latest_eval = EvaluationMain.query.order_by(EvaluationMain.id.desc()).first()
        warning = OperatorWarning(
            evaluation_id=latest_eval.id,
            canteen_id=latest_eval.canteen_id,
            window_id=latest_eval.window_id,
            score=latest_eval.comprehensive_score,
            summary='SLA测试预警',
            status='pending',
            create_time=datetime.now() - timedelta(hours=49),
        )
        db.session.add(warning)
        db.session.commit()

    resp = client.get('/api/admin/sla/todos')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['code'] == 200
    assert body['data']['summary']['escalated_count'] >= 1
    assert any(item['sla_level'] == 'escalated' for item in body['data']['todo_list'])


def test_admin_action_logs_after_template_create(client):
    with app.app_context():
        admin = User(username='audit_admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    client.post('/api/login', json={'username': 'audit_admin', 'password': '123456'})
    create_resp = client.post('/api/admin/evaluation_templates', json={'name': '审计日志模板'})
    assert create_resp.status_code == 200

    list_resp = client.get('/api/admin/action_logs?action=template_create')
    assert list_resp.status_code == 200
    body = list_resp.get_json()
    assert body['code'] == 200
    assert body['data']['total'] >= 1
    actions = [item['action'] for item in body['data']['list']]
    assert 'template_create' in actions

    with app.app_context():
        row = AdminActionLog.query.filter_by(action='template_create').order_by(AdminActionLog.id.desc()).first()
        assert row is not None
        assert row.target_type == 'evaluation_template'


def test_template_update_writes_before_after_audit(client):
    with app.app_context():
        admin = User(username='diff_admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    client.post('/api/login', json={'username': 'diff_admin', 'password': '123456'})
    create_resp = client.post('/api/admin/evaluation_templates', json={'name': '差异审计模板'})
    assert create_resp.status_code == 200
    version_id = create_resp.get_json()['data']['id']

    update_resp = client.put(
        f'/api/admin/evaluation_templates/{version_id}',
        json={'name': '差异审计模板-更新'},
    )
    assert update_resp.status_code == 200

    with app.app_context():
        row = AdminActionLog.query.filter_by(action='template_update', target_id=version_id).order_by(AdminActionLog.id.desc()).first()
        assert row is not None
        assert row.before_data
        assert row.after_data


def test_admin_action_logs_time_filter_and_export(client):
    with app.app_context():
        admin = User(username='audit_export_admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    client.post('/api/login', json={'username': 'audit_export_admin', 'password': '123456'})
    create_resp = client.post('/api/admin/evaluation_templates', json={'name': '审计导出模板'})
    assert create_resp.status_code == 200

    future_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    empty_resp = client.get('/api/admin/action_logs', query_string={'start_time': future_time})
    assert empty_resp.status_code == 200
    assert empty_resp.get_json()['data']['total'] == 0

    export_resp = client.get('/api/admin/action_logs/export', query_string={'action': 'template_create'})
    assert export_resp.status_code == 200
    assert 'text/csv' in (export_resp.content_type or '')
    text_body = export_resp.get_data(as_text=True)
    assert 'action' in text_body
    assert 'template_create' in text_body


def test_guest_status_query_endpoint_disabled(client):
    resp = client.get('/api/guest/evaluations/1/status', headers={'X-Forwarded-For': '10.0.0.9'})
    assert resp.status_code == 403
    assert resp.get_json()['code'] == 403


def test_my_evaluations_returns_governance_status(client):
    client.post('/api/login', json={'username': 'tester', 'password': '123456'})
    submit_resp = client.post(
        '/api/submit_evaluation',
        json={
            'canteen_id': 1,
            'window_id': 1,
            'buy_time': '2026-03-22T20:00',
            'identity_type': 'student',
            'dishes': [{'dish_id': 1, 'dish_name': '测试菜品', 'food_scores': {'taste': 3}}],
            'env_scores': {'clean': 3},
            'service_scores': {'attitude': 3},
            'safety_scores': {'fresh': 3},
        },
    )
    assert submit_resp.status_code == 200

    with app.app_context():
        latest = EvaluationMain.query.order_by(EvaluationMain.id.desc()).first()
        warning = OperatorWarning(
            evaluation_id=latest.id,
            canteen_id=latest.canteen_id,
            window_id=latest.window_id,
            score=latest.comprehensive_score,
            summary='测试预警',
            status='handled',
        )
        db.session.add(warning)
        db.session.flush()
        db.session.add(
            RectificationRecord(
                warning_id=warning.id,
                title='整改完成',
                issue_desc='测试问题',
                action_detail='测试措施',
                is_public=True,
            )
        )
        db.session.commit()

    my_resp = client.get('/api/my_evaluations')
    assert my_resp.status_code == 200
    body = my_resp.get_json()
    first = body['data'][0]
    assert first['governance_status'] == 'handled'
    assert first['rectification_count'] >= 1
    assert first['latest_rectification_title'] == '整改完成'
    assert isinstance(first['governance_timeline'], list)
    assert len(first['governance_timeline']) >= 3
    assert first['governance_timeline'][0]['type'] == 'evaluation_submitted'
    assert isinstance(first['rectifications'], list)
    assert first['rectifications'][0]['title'] == '整改完成'


def test_my_evaluations_with_pagination(client):
    client.post('/api/login', json={'username': 'tester', 'password': '123456'})

    for idx in range(2):
        resp = client.post(
            '/api/evaluation/save',
            json={
                'canteen_id': 1,
                'window_id': 1,
                'buy_time': f'2026-03-22T21:0{idx}',
                'identity_type': 'student',
                'dishes': [{'dish_id': 1, 'dish_name': '测试菜品', 'food_scores': {'taste': 7}}],
                'env_scores': {'clean': 7},
                'service_scores': {'attitude': 7},
                'safety_scores': {'fresh': 7},
            },
        )
        assert resp.status_code == 200

    page_resp = client.get('/api/my_evaluations?with_pagination=1&page=1&limit=1')
    assert page_resp.status_code == 200
    body = page_resp.get_json()
    assert body['code'] == 200
    assert 'list' in body['data']
    assert body['data']['limit'] == 1
    assert body['data']['total'] >= 2
    assert len(body['data']['list']) == 1


def test_admin_update_and_publish_template(client):
    with app.app_context():
        admin = User(username='template_admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    client.post('/api/login', json={'username': 'template_admin', 'password': '123456'})
    create_resp = client.post('/api/admin/evaluation_templates', json={'name': '测试模板草稿'})
    assert create_resp.status_code == 200
    version_id = create_resp.get_json()['data']['id']

    update_resp = client.put(
        f'/api/admin/evaluation_templates/{version_id}',
        json={
            'name': '测试模板草稿-更新',
            'items': [
                {'category': 'service', 'item_key': 'attitude', 'item_label': '服务态度', 'sort_order': 1, 'score_min': 1, 'score_max': 10},
                {'category': 'service', 'item_key': 'speed', 'item_label': '响应速度', 'sort_order': 2, 'score_min': 1, 'score_max': 10},
            ],
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.get_json()['data']['name'] == '测试模板草稿-更新'

    publish_resp = client.post(f'/api/admin/evaluation_templates/{version_id}/publish', json={})
    assert publish_resp.status_code == 200
    assert publish_resp.get_json()['data']['status'] == 'active'
