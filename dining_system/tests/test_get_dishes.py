def test_get_dishes_returns_list(client):
    resp = client.get('/api/dishes')
    body = resp.get_json()
    assert resp.status_code == 200
    assert body['code'] == 200
    assert isinstance(body['data'], list)
    target = next((item for item in body['data'] if item['name'] == '测试菜品'), None)
    assert target is not None
    assert 'img_url' in target
