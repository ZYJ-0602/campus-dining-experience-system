def test_admin_batch_import_requires_login(client):
    resp = client.post(
        '/api/admin/dishes/batch_import',
        json=[{'window_id': 1, 'name': '测试菜品', 'price': 9.99}],
    )
    body = resp.get_json()
    assert resp.status_code == 401
    assert body['code'] == 401
