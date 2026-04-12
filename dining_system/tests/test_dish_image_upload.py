import io
import os

from werkzeug.security import generate_password_hash

import app as app_module
from app import app, db
from models import Canteen, Dish, User, Window


def _jpg_bytes():
    buf = io.BytesIO()
    image = app_module.Image.new('RGB', (8, 8), color=(120, 80, 40))
    image.save(buf, format='JPEG')
    return buf.getvalue()


def _login(client, username, password='123456'):
    resp = client.post('/api/login', json={'username': username, 'password': password})
    assert resp.status_code == 200
    assert resp.get_json()['code'] == 200


def test_admin_upload_dish_image_and_delete_success(client, tmp_path, monkeypatch):
    if app_module.Image is None:
        return

    monkeypatch.setattr(app_module, 'DISH_IMAGE_UPLOAD_DIR', str(tmp_path))

    with app.app_context():
        admin = User(username='img_admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    _login(client, 'img_admin')

    upload_resp = client.post(
        '/api/admin/dishes/1/image',
        data={'file': (io.BytesIO(_jpg_bytes()), 'dish.jpg', 'image/jpeg')},
        content_type='multipart/form-data',
    )
    assert upload_resp.status_code == 200, upload_resp.get_json()
    upload_body = upload_resp.get_json()
    assert upload_body['code'] == 200
    url = upload_body['data']['img_url']
    assert url.startswith('/static/uploads/dishes/')

    with app.app_context():
        dish = db.session.get(Dish, 1)
        assert dish is not None
        assert dish.img_url == url
        saved = os.path.join(str(tmp_path), os.path.basename(url))
        assert os.path.exists(saved)

    delete_resp = client.delete('/api/admin/dishes/1/image')
    assert delete_resp.status_code == 200
    assert delete_resp.get_json()['code'] == 200

    with app.app_context():
        dish = db.session.get(Dish, 1)
        assert dish is not None
        assert not dish.img_url
        saved = os.path.join(str(tmp_path), os.path.basename(url))
        assert not os.path.exists(saved)


def test_upload_dish_image_rejects_invalid_ext(client):
    with app.app_context():
        admin = User(username='img_admin2', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    _login(client, 'img_admin2')

    resp = client.post(
        '/api/admin/dishes/1/image',
        data={'file': (io.BytesIO(b'not-image'), 'dish.gif', 'image/gif')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 400
    assert 'jpg/png/webp' in resp.get_json()['msg']


def test_upload_dish_image_rejects_over_2mb(client):
    with app.app_context():
        admin = User(username='img_admin3', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    _login(client, 'img_admin3')

    too_large = b'a' * (2 * 1024 * 1024 + 1)
    resp = client.post(
        '/api/admin/dishes/1/image',
        data={'file': (io.BytesIO(too_large), 'dish.png', 'image/png')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 400
    assert '2MB' in resp.get_json()['msg']


def test_operator_cannot_upload_other_canteen_dish_image(client):
    with app.app_context():
        canteen2 = Canteen(name='第二食堂', address='A区', is_active=True)
        db.session.add(canteen2)
        db.session.flush()
        window2 = Window(canteen_id=canteen2.id, name='二号窗口')
        db.session.add(window2)
        db.session.flush()
        dish2 = Dish(window_id=window2.id, name='跨食堂菜品', price=12)
        db.session.add(dish2)

        operator = User(
            username='op_bind_c1',
            password=generate_password_hash('123456'),
            role='operator',
            operator_canteen_id=1,
        )
        db.session.add(operator)
        db.session.commit()
        dish2_id = dish2.id

    _login(client, 'op_bind_c1')

    resp = client.post(
        f'/api/admin/dishes/{dish2_id}/image',
        data={'file': (io.BytesIO(_jpg_bytes()), 'dish.jpg', 'image/jpeg')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 403
    assert resp.get_json()['code'] == 403


def test_delete_dish_removes_local_image_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, 'DISH_IMAGE_UPLOAD_DIR', str(tmp_path))

    with app.app_context():
        admin = User(username='img_admin4', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        db.session.commit()

    _login(client, 'img_admin4')

    file_name = 'dish_1_manual.jpg'
    file_path = tmp_path / file_name
    file_path.write_bytes(_jpg_bytes())

    with app.app_context():
        dish = db.session.get(Dish, 1)
        dish.img_url = f'/static/uploads/dishes/{file_name}'
        db.session.commit()

    delete_resp = client.delete('/api/admin/dishes/1')
    assert delete_resp.status_code == 200
    assert delete_resp.get_json()['code'] == 200
    assert not file_path.exists()
