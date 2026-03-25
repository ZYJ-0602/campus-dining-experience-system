from functools import wraps
import csv
import io
import os
import random
import shutil
import smtplib
import ssl
from datetime import datetime, timedelta, date
import math
import json
import urllib.request
import urllib.error
from email.message import EmailMessage

from flask import Flask, request, jsonify, session, render_template, redirect, url_for, send_from_directory, send_file, Response
from flask_cors import CORS
from sqlalchemy import text, func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

basedir = os.path.abspath(os.path.dirname(__file__))
pages_dir = os.path.join(basedir, 'pages')
from extensions import db
from models import User, Canteen, Window, Dish, EvaluationMain, EvaluationDish, SubmitGuard, Favorite, Feedback, Note, SensitiveWord, SensitiveRule, SystemConfig, NotificationConfig, BackupRecord, NotificationDispatchLog, NotificationMessage, OperatorWarning, SafetyNotice, RectificationRecord

app = Flask(
    __name__,
    template_folder=os.path.join(basedir, 'templates'),
    static_folder=os.path.join(basedir, 'static'),
)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'dining_system.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JSON_AS_ASCII'] = False
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'campus-dining-dev-secret')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', '0') == '1'
app.config['PERMANENT_SESSION_LIFETIME'] = 60 * 60 * 24

PUBLIC_PAGE_PATHS = {
    'b-admin/admin_login.html',
}

# 允许跨域请求（开发环境可通过 ALLOWED_ORIGINS 覆盖）
allowed_origins = os.getenv('ALLOWED_ORIGINS', '*')
CORS(
    app,
    supports_credentials=True,
    resources={r"/api/*": {"origins": [o.strip() for o in allowed_origins.split(',')] if allowed_origins != '*' else '*'}},
)

db.init_app(app)

SUBMIT_GUARD_SECONDS = int(os.getenv('SUBMIT_GUARD_SECONDS', '30'))
BACKUP_DIR = os.path.join(basedir, 'database', 'backups')
SMTP_HOST = os.getenv('SMTP_HOST', '').strip()
SMTP_PORT = int(os.getenv('SMTP_PORT', '465'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '').strip()
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '').strip()
SMTP_FROM = os.getenv('SMTP_FROM', SMTP_USERNAME or '').strip()
SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', '0') == '1'
SMS_GATEWAY_URL = os.getenv('SMS_GATEWAY_URL', '').strip()
SMS_GATEWAY_TOKEN = os.getenv('SMS_GATEWAY_TOKEN', '').strip()
SMS_GATEWAY_TIMEOUT = float(os.getenv('SMS_GATEWAY_TIMEOUT', '5'))
SMS_SENDER = os.getenv('SMS_SENDER', 'campus-dining').strip()


@app.route('/')
def root_redirect():
    if session.get('user_id'):
        return redirect(url_for('client_page', filename='c-client/index.html'))
    return redirect(url_for('login_page'))


@app.route('/login')
def login_page():
    return render_template('login-only.html')


@app.route('/register')
def register_page():
    return render_template('register-only.html')


@app.route('/admin')
@app.route('/admin/login')
@app.route('/admin/login.html')
def admin_login_page():
    return redirect(url_for('client_page', filename='b-admin/admin_login.html'))


@app.route('/pages/<path:filename>')
def client_page(filename):
    if filename in PUBLIC_PAGE_PATHS:
        return send_from_directory(pages_dir, filename)
    if not session.get('user_id'):
        return redirect(url_for('login_page'))
    return send_from_directory(pages_dir, filename)

def api_success(data=None, msg='success', code=200, http_status=200):
    return jsonify({'code': code, 'msg': msg, 'data': data if data is not None else {}}), http_status


def api_error(msg='error', code=400, http_status=400, data=None):
    return jsonify({'code': code, 'msg': msg, 'data': data if data is not None else {}}), http_status


def _serialize_user(user):
    return {
        'id': user.id,
        'username': user.username,
        'nickname': user.nickname,
        'phone': user.phone,
        'avatar': user.avatar,
        'role': user.role,
    }


def _verify_password(stored_password, plain_password):
    if not stored_password:
        return False
    try:
        if check_password_hash(stored_password, plain_password):
            return True
    except Exception:
        pass
    return stored_password == plain_password


def _safe_number(value):
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError):
        pass
    return None


def _normalize_images(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (TypeError, ValueError):
            return []
    return []


def _safe_scores(score_obj):
    return score_obj if isinstance(score_obj, dict) else {}


def _safe_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_score_pack(data, prefix, keys):
    nested = _safe_scores(data.get(f'{prefix}_scores', {}))
    if nested:
        return nested

    result = {}
    for key in keys:
        val = _safe_number(data.get(f'{prefix}_{key}'))
        if val is not None:
            result[key] = val
    return result


def _normalize_dish_payload(item):
    if not isinstance(item, dict):
        return None

    dish_id = _safe_int(item.get('dish_id'))
    if dish_id is None:
        dish_id = _safe_int(item.get('id'), 0)

    dish_name = (item.get('dish_name') or item.get('name') or '').strip()
    food_scores = _safe_scores(item.get('food_scores', {}))
    if not food_scores:
        key_mapping = {
            'color_score': 'color',
            'aroma_score': 'aroma',
            'taste_score': 'taste',
            'shape_score': 'shape',
            'portion_score': 'portion',
            'price_score': 'price',
            'speed_score': 'speed',
        }
        for old_key, new_key in key_mapping.items():
            val = _safe_number(item.get(old_key))
            if val is not None:
                food_scores[new_key] = val

    return {
        'dish_id': dish_id or 0,
        'dish_name': dish_name,
        'food_scores': food_scores,
        'remark': (item.get('remark') or '').strip(),
        'images': _normalize_images(item.get('images')),
    }


def _public_parse_range(raw_value):
    now = datetime.now()
    key = (raw_value or 'month').strip().lower()

    if key in ('today', 'day', '今日'):
        start = datetime(now.year, now.month, now.day)
        return 'today', start, now
    if key in ('week', '本周'):
        start = datetime(now.year, now.month, now.day) - timedelta(days=now.weekday())
        return 'week', start, now
    if key in ('near30', '30d', '30days', 'last30', '近30天'):
        start = datetime(now.year, now.month, now.day) - timedelta(days=29)
        return 'near30', start, now

    start = datetime(now.year, now.month, 1)
    return 'month', start, now


def _public_seed_required():
    active_dishes = Dish.query.filter(Dish.is_active.is_(True)).count()
    order_count = EvaluationMain.query.count()
    review_count = EvaluationDish.query.count()
    return active_dishes == 0 or order_count == 0 or review_count == 0


def _public_get_or_create_seed_user():
    user = User.query.filter_by(username='public_seed_user').first()
    if user:
        return user

    user = User(
        username='public_seed_user',
        password=generate_password_hash('123456'),
        role='student',
        nickname='公共数据种子用户',
    )
    db.session.add(user)
    db.session.flush()
    return user


def _public_ensure_base_canteens_windows():
    canteen_names = ['北区食堂', '南区食堂', '西区食堂']
    window_names = ['一号窗口', '二号窗口', '风味窗口', '面食窗口', '快餐窗口']

    canteens = Canteen.query.all()
    if not canteens:
        for idx, name in enumerate(canteen_names, start=1):
            db.session.add(Canteen(name=name, address=f'校园{idx}号生活区', is_active=True))
        db.session.flush()
        canteens = Canteen.query.all()

    windows = Window.query.all()
    if not windows:
        for canteen in canteens:
            for idx in range(2):
                db.session.add(Window(canteen_id=canteen.id, name=f'{canteen.name}{window_names[idx]}'))
        db.session.flush()
        windows = Window.query.all()

    return canteens, windows


def _public_ensure_dishes(windows):
    dish_pool = [
        '红烧肉', '番茄炒蛋', '宫保鸡丁', '鱼香肉丝', '麻婆豆腐',
        '糖醋里脊', '青椒肉丝', '香菇滑鸡', '清炒时蔬', '土豆炖牛腩',
        '蒜香排骨', '鸡蛋炒饭', '西红柿牛腩', '椒盐鸡柳', '香辣鸡腿堡',
    ]

    dishes = Dish.query.filter(Dish.is_active.is_(True)).all()
    if len(dishes) >= 15:
        return dishes

    existing_names = {d.name for d in Dish.query.all()}
    for idx, name in enumerate(dish_pool):
        if name in existing_names:
            continue
        target_window = windows[idx % len(windows)]
        db.session.add(
            Dish(
                window_id=target_window.id,
                name=name,
                price=round(8 + random.random() * 14, 2),
                category='热菜',
                tags_json=['热销', '校园'],
                portion='常规',
                is_active=True,
            )
        )
        if Dish.query.filter(Dish.is_active.is_(True)).count() + 1 >= 15:
            break

    db.session.flush()
    return Dish.query.filter(Dish.is_active.is_(True)).all()


def _public_pick_peak_hour():
    # 午高峰与晚高峰权重更高
    ranges = [
        (7, 9, 0.15),
        (9, 11, 0.10),
        (11, 13, 0.35),
        (13, 17, 0.10),
        (17, 19, 0.25),
        (19, 22, 0.05),
    ]
    r = random.random()
    acc = 0
    for start, end, weight in ranges:
        acc += weight
        if r <= acc:
            return random.randint(start, end - 1)
    return random.randint(11, 12)


def _public_seed_dashboard_data():
    user = _public_get_or_create_seed_user()
    canteens, windows = _public_ensure_base_canteens_windows()
    dishes = _public_ensure_dishes(windows)

    if not dishes:
        return False

    good_review_texts = [
        '口味不错，分量足，值得推荐。',
        '菜品新鲜，搭配合理，整体满意。',
        '出餐速度快，菜温合适。',
        '窗口服务热情，体验很好。',
        '味道稳定，价格实惠。',
    ]
    bad_review_texts = [
        '今天偏咸，体验一般。',
        '菜品温度偏低，口感不佳。',
        '高峰期等待较久，希望改进。',
        '分量偏少，不太满意。',
        '服务响应较慢，需优化。',
    ]

    # 500条就餐订单
    order_rows = []
    now = datetime.now()
    for _ in range(500):
        dish = random.choice(dishes)
        offset_day = random.randint(0, 29)
        target_day = now - timedelta(days=offset_day)
        hour = _public_pick_peak_hour()
        minute = random.randint(0, 59)
        buy_time = datetime(target_day.year, target_day.month, target_day.day, hour, minute)

        order_rows.append(
            EvaluationMain(
                user_id=user.id,
                canteen_id=dish.window.canteen_id if dish.window else canteens[0].id,
                window_id=dish.window_id,
                buy_time=buy_time,
                identity_type=random.choice(['student', 'teacher', 'visitor', 'operator']),
                grade=random.choice(['大一', '大二', '大三', '大四']),
                age=random.randint(18, 55),
                dining_years=random.randint(1, 6),
                env_scores={},
                service_scores={},
                safety_scores={},
                comprehensive_score=0,
                remark='公共看板种子订单',
                create_time=buy_time,
            )
        )

    db.session.add_all(order_rows)
    db.session.flush()

    # 100条评价：80好评 + 20差评
    reviewed_indexes = random.sample(range(len(order_rows)), 100)
    bad_indexes = set(reviewed_indexes[:20])
    dish_score_map = {}

    for idx in reviewed_indexes:
        main = order_rows[idx]
        dish_candidates = [d for d in dishes if d.window_id == main.window_id]
        dish = random.choice(dish_candidates or dishes)

        if idx in bad_indexes:
            base_score = round(random.uniform(1.0, 2.0), 1)
            text = random.choice(bad_review_texts)
        else:
            base_score = round(random.uniform(7.0, 10.0), 1)
            text = random.choice(good_review_texts)

        env = max(1.0, min(10.0, round(base_score + random.uniform(-0.8, 0.8), 1)))
        service = max(1.0, min(10.0, round(base_score + random.uniform(-0.8, 0.8), 1)))
        safety = max(1.0, min(10.0, round(base_score + random.uniform(-0.5, 0.5), 1)))

        main.env_scores = {'cleanliness': env}
        main.service_scores = {'attitude': service}
        main.safety_scores = {'hygiene': safety}
        main.comprehensive_score = round((base_score + env + service + safety) / 4, 1)
        main.remark = text
        main.env_comment = random.choice(good_review_texts if idx not in bad_indexes else bad_review_texts)
        main.service_comment = random.choice(good_review_texts if idx not in bad_indexes else bad_review_texts)
        main.safety_comment = random.choice(good_review_texts if idx not in bad_indexes else bad_review_texts)

        db.session.add(
            EvaluationDish(
                evaluation_id=main.id,
                dish_id=dish.id,
                dish_name=dish.name,
                food_scores={'taste': base_score, 'portion': max(1.0, min(10.0, round(base_score + random.uniform(-1, 1), 1)))},
                remark=text,
            )
        )

        bucket = dish_score_map.setdefault(dish.id, [])
        bucket.append(base_score)

    for dish in dishes:
        score_list = dish_score_map.get(dish.id, [])
        dish.review_count = len(score_list)
        dish.average_score = round(sum(score_list) / len(score_list), 1) if score_list else 0.0

    # 食安公示最小示例
    if SafetyNotice.query.count() == 0:
        db.session.add(
            SafetyNotice(
                title='校园食堂食品安全抽检公示',
                notice_type='检测报告',
                expire_date=(datetime.now() + timedelta(days=180)).date(),
                status='published',
                files_json=[{'name': 'report.pdf', 'url': '/uploads/report.pdf'}],
                content='本月抽检结果均合格。',
            )
        )

    db.session.commit()
    return True


def _public_ensure_seed_data_if_needed():
    if _public_seed_required():
        return _public_seed_dashboard_data()
    return False


def _legacy_comment_images(score_obj):
    score_dict = score_obj if isinstance(score_obj, dict) else {}
    return (score_dict.get('_comment') or '').strip(), _normalize_images(score_dict.get('_images'))


def _pick_comment_images(primary_comment, primary_images, legacy_score_obj):
    comment = (primary_comment or '').strip()
    images = _normalize_images(primary_images)
    if comment or images:
        return comment, images
    return _legacy_comment_images(legacy_score_obj)


def _ensure_schema_columns():
    db.create_all()
    existing = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(evaluation_main)')).fetchall()
    }

    migration_sql = {
        'service_comment': 'ALTER TABLE evaluation_main ADD COLUMN service_comment TEXT',
        'service_images': 'ALTER TABLE evaluation_main ADD COLUMN service_images TEXT',
        'env_comment': 'ALTER TABLE evaluation_main ADD COLUMN env_comment TEXT',
        'env_images': 'ALTER TABLE evaluation_main ADD COLUMN env_images TEXT',
        'safety_comment': 'ALTER TABLE evaluation_main ADD COLUMN safety_comment TEXT',
        'safety_images': 'ALTER TABLE evaluation_main ADD COLUMN safety_images TEXT',
    }

    submit_guard_migration_sql = {
        'block_count': 'ALTER TABLE submit_guard ADD COLUMN block_count INTEGER DEFAULT 0',
        'last_block_time': 'ALTER TABLE submit_guard ADD COLUMN last_block_time DATETIME',
    }

    dish_existing = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(dish)')).fetchall()
    }
    dish_migration_sql = {
        'is_active': 'ALTER TABLE dish ADD COLUMN is_active BOOLEAN DEFAULT 1',
        'tags_json': 'ALTER TABLE dish ADD COLUMN tags_json TEXT',
    }

    user_existing = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(user)')).fetchall()
    }
    user_migration_sql = {
        'nickname': 'ALTER TABLE user ADD COLUMN nickname VARCHAR(80)',
        'phone': 'ALTER TABLE user ADD COLUMN phone VARCHAR(20)',
        'avatar': 'ALTER TABLE user ADD COLUMN avatar VARCHAR(255)',
    }

    changed = False
    for col_name, sql in migration_sql.items():
        if col_name not in existing:
            db.session.execute(text(sql))
            changed = True
    for col_name, sql in user_migration_sql.items():
        if col_name not in user_existing:
            db.session.execute(text(sql))
            changed = True
    for col_name, sql in dish_migration_sql.items():
        if col_name not in dish_existing:
            db.session.execute(text(sql))
            changed = True
    if changed:
        db.session.commit()

    submit_guard_exists = db.session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='submit_guard'")
    ).fetchone()
    if submit_guard_exists:
        submit_guard_cols = {
            row[1]
            for row in db.session.execute(text('PRAGMA table_info(submit_guard)')).fetchall()
        }
        changed_guard = False
        for col_name, sql in submit_guard_migration_sql.items():
            if col_name not in submit_guard_cols:
                db.session.execute(text(sql))
                changed_guard = True
        if changed_guard:
            db.session.commit()

    # 兼容层：满足 canteens/windows/dishes/evaluations 表结构要求。
    db.session.execute(
        text(
            '''
            CREATE TABLE IF NOT EXISTS canteens (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL
            )
            '''
        )
    )
    db.session.execute(
        text(
            '''
            CREATE TABLE IF NOT EXISTS windows (
                id INTEGER PRIMARY KEY,
                canteen_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                FOREIGN KEY(canteen_id) REFERENCES canteens(id)
            )
            '''
        )
    )
    db.session.execute(
        text(
            '''
            CREATE TABLE IF NOT EXISTS dishes (
                id INTEGER PRIMARY KEY,
                window_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                FOREIGN KEY(window_id) REFERENCES windows(id)
            )
            '''
        )
    )
    db.session.execute(
        text(
            '''
            CREATE TABLE IF NOT EXISTS evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evaluation_main_id INTEGER,
                user_id INTEGER,
                canteen_id INTEGER,
                window_id INTEGER,
                dish_id INTEGER,
                score FLOAT DEFAULT 0,
                remark TEXT,
                images TEXT,
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(canteen_id) REFERENCES canteens(id),
                FOREIGN KEY(window_id) REFERENCES windows(id),
                FOREIGN KEY(dish_id) REFERENCES dishes(id)
            )
            '''
        )
    )

    eval_cols = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(evaluations)')).fetchall()
    }
    eval_migration_sql = {
        'canteen_id': 'ALTER TABLE evaluations ADD COLUMN canteen_id INTEGER',
        'window_id': 'ALTER TABLE evaluations ADD COLUMN window_id INTEGER',
        'dish_id': 'ALTER TABLE evaluations ADD COLUMN dish_id INTEGER',
    }
    for col_name, sql in eval_migration_sql.items():
        if col_name not in eval_cols:
            db.session.execute(text(sql))

    db.session.execute(
        text(
            '''
            CREATE TABLE IF NOT EXISTS food_safety_notices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canteen_id INTEGER NOT NULL,
                title VARCHAR(200) NOT NULL,
                type VARCHAR(50) DEFAULT '检测报告',
                valid_from DATE,
                valid_until DATE,
                file_url VARCHAR(255) DEFAULT '',
                content TEXT DEFAULT '',
                expire_date DATE,
                status VARCHAR(20) DEFAULT 'published',
                image_url VARCHAR(255) DEFAULT '',
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(canteen_id) REFERENCES canteens(id)
            )
            '''
        )
    )

    fs_cols = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(food_safety_notices)')).fetchall()
    }
    fs_migration_sql = {
        'type': "ALTER TABLE food_safety_notices ADD COLUMN type VARCHAR(50) DEFAULT '检测报告'",
        'valid_from': 'ALTER TABLE food_safety_notices ADD COLUMN valid_from DATE',
        'valid_until': 'ALTER TABLE food_safety_notices ADD COLUMN valid_until DATE',
        'file_url': "ALTER TABLE food_safety_notices ADD COLUMN file_url VARCHAR(255) DEFAULT ''",
    }
    for col_name, sql in fs_migration_sql.items():
        if col_name not in fs_cols:
            db.session.execute(text(sql))
    db.session.execute(
        text(
            '''
            CREATE TABLE IF NOT EXISTS user_shares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canteen_id INTEGER NOT NULL,
                user_id INTEGER,
                username VARCHAR(80) DEFAULT '校园用户',
                content TEXT NOT NULL,
                image_url VARCHAR(255) DEFAULT '',
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(canteen_id) REFERENCES canteens(id)
            )
            '''
        )
    )

    canteen_cols = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(canteen)')).fetchall()
    }
    if 'business_hours' not in canteen_cols:
        db.session.execute(text("ALTER TABLE canteen ADD COLUMN business_hours VARCHAR(100) DEFAULT '07:00-21:00'"))

    # 与主业务表做镜像同步，确保级联查询与外键数据可用。
    db.session.execute(text('DELETE FROM canteens'))
    db.session.execute(text('INSERT INTO canteens(id, name) SELECT id, name FROM canteen'))
    db.session.execute(text('DELETE FROM windows'))
    db.session.execute(text('INSERT INTO windows(id, canteen_id, name) SELECT id, canteen_id, name FROM window'))
    db.session.execute(text('DELETE FROM dishes'))
    db.session.execute(text('INSERT INTO dishes(id, window_id, name) SELECT id, window_id, name FROM dish'))
    db.session.commit()

    _ensure_canteen_detail_seed_data()


def _ensure_canteen_detail_seed_data():
    north = Canteen.query.filter(Canteen.name == '北区食堂').first()
    if not north:
        north = Canteen(name='北区食堂', address='北区生活区一层', is_active=True)
        db.session.add(north)
        db.session.flush()

    if not north.address:
        north.address = '北区生活区一层'

    db.session.execute(
        text('UPDATE canteen SET business_hours = :hours WHERE id = :id'),
        {'hours': '06:30-21:30', 'id': north.id},
    )

    must_windows = ['北区一号窗口', '北区二号窗口']
    existed_window_names = {
        row.name for row in Window.query.filter(Window.canteen_id == north.id).all()
    }
    for name in must_windows:
        if name not in existed_window_names:
            db.session.add(Window(canteen_id=north.id, name=name))
    db.session.flush()

    north_windows = Window.query.filter(Window.canteen_id == north.id).order_by(Window.id.asc()).all()
    if not north_windows:
        return

    dish_count = Dish.query.join(Window, Dish.window_id == Window.id).filter(Window.canteen_id == north.id).count()
    if dish_count == 0:
        seed_dishes = [
            ('红烧肉套餐', north_windows[0].id),
            ('番茄牛腩饭', north_windows[0].id),
            ('鸡排盖浇饭', north_windows[min(1, len(north_windows) - 1)].id),
        ]
        for dish_name, win_id in seed_dishes:
            db.session.add(
                Dish(
                    window_id=win_id,
                    name=dish_name,
                    price=16.0,
                    category='快餐',
                    portion='常规',
                    is_active=True,
                )
            )
        db.session.flush()

    north_dishes = (
        Dish.query.join(Window, Dish.window_id == Window.id)
        .filter(Window.canteen_id == north.id)
        .order_by(Dish.id.asc())
        .all()
    )
    first_dish_id = north_dishes[0].id if north_dishes else 0
    first_window_id = north_windows[0].id

    south = Canteen.query.filter(Canteen.name == '南区食堂').first()
    if not south:
        south = Canteen(name='南区食堂', address='南区生活区二层', is_active=True)
        db.session.add(south)
        db.session.flush()

    notice_count = db.session.execute(text('SELECT COUNT(1) FROM food_safety_notices')).scalar() or 0
    if notice_count < 3:
        payloads = [
            {
                'canteen_id': north.id,
                'title': '北区食堂月度食材抽检报告',
                'type': '检测报告',
                'valid_from': '2026-01-01',
                'valid_until': '2099-12-31',
                'status': 'active',
                'file_url': '/api/files/preview/1',
                'content': '本月抽检结果全部合格。',
                'image_url': '/static/img/safety_report.png',
            },
            {
                'canteen_id': north.id,
                'title': '北区食堂从业人员健康证公示',
                'type': '资质证书',
                'valid_from': '2026-01-15',
                'valid_until': '2099-09-30',
                'status': 'active',
                'file_url': '/api/files/preview/2',
                'content': '从业人员健康证均在有效期内。',
                'image_url': '/static/img/health_cert.png',
            },
            {
                'canteen_id': south.id,
                'title': '南区食堂季度食材检测报告',
                'type': '检测报告',
                'valid_from': '2024-01-01',
                'valid_until': '2024-12-31',
                'status': 'expired',
                'file_url': '/api/files/preview/3',
                'content': '历史检测报告留档。',
                'image_url': '/static/img/safety_report_old.png',
            },
        ]

        existing_titles = {
            row['title']
            for row in db.session.execute(text('SELECT title FROM food_safety_notices')).mappings().all()
        }
        for item in payloads:
            if item['title'] in existing_titles:
                continue
            db.session.execute(
                text(
                    '''
                    INSERT INTO food_safety_notices(
                        canteen_id, title, type, valid_from, valid_until, file_url, content, expire_date, status, image_url, create_time
                    ) VALUES (
                        :canteen_id, :title, :type, :valid_from, :valid_until, :file_url, :content, :valid_until, :status, :image_url, :create_time
                    )
                    '''
                ),
                {
                    'canteen_id': item['canteen_id'],
                    'title': item['title'],
                    'type': item['type'],
                    'valid_from': item['valid_from'],
                    'valid_until': item['valid_until'],
                    'file_url': item['file_url'],
                    'content': item['content'],
                    'status': item['status'],
                    'image_url': item['image_url'],
                    'create_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                },
            )

    eval_count = db.session.execute(
        text('SELECT COUNT(1) FROM evaluations WHERE canteen_id = :canteen_id'),
        {'canteen_id': north.id},
    ).scalar() or 0
    if eval_count < 5:
        comments = [
            '今天口味不错，出餐也很快。',
            '环境整洁，整体满意。',
            '分量充足，性价比高。',
            '高峰期排队稍久，但菜品质量稳定。',
            '服务态度很好，会继续来。',
        ]
        for idx in range(eval_count, 5):
            score = round(7.6 + (idx % 3) * 0.5, 1)
            db.session.execute(
                text(
                    '''
                    INSERT INTO evaluations(user_id, canteen_id, window_id, dish_id, score, remark, images, create_time)
                    VALUES (:user_id, :canteen_id, :window_id, :dish_id, :score, :remark, :images, :create_time)
                    '''
                ),
                {
                    'user_id': 1,
                    'canteen_id': north.id,
                    'window_id': first_window_id,
                    'dish_id': first_dish_id,
                    'score': score,
                    'remark': comments[idx],
                    'images': '[]',
                    'create_time': (datetime.now() - timedelta(days=idx)).strftime('%Y-%m-%d %H:%M:%S'),
                },
            )

    share_count = db.session.execute(
        text('SELECT COUNT(1) FROM user_shares WHERE canteen_id = :canteen_id'),
        {'canteen_id': north.id},
    ).scalar() or 0
    if share_count < 3:
        shares = [
            ('小林', '北区一号窗口的红烧肉套餐很稳，午餐首选。', '/static/img/share_1.png'),
            ('阿白', '今天二号窗口鸡排饭不错，配菜也新鲜。', '/static/img/share_2.png'),
            ('圆圆', '晚餐人少时来北区食堂体验更好。', '/static/img/share_3.png'),
        ]
        for idx in range(share_count, 3):
            username, content, image_url = shares[idx]
            db.session.execute(
                text(
                    '''
                    INSERT INTO user_shares(canteen_id, user_id, username, content, image_url, create_time)
                    VALUES (:canteen_id, :user_id, :username, :content, :image_url, :create_time)
                    '''
                ),
                {
                    'canteen_id': north.id,
                    'user_id': 1,
                    'username': username,
                    'content': content,
                    'image_url': image_url,
                    'create_time': (datetime.now() - timedelta(hours=idx * 3)).strftime('%Y-%m-%d %H:%M:%S'),
                },
            )

    db.session.execute(text('DELETE FROM canteens'))
    db.session.execute(text('INSERT INTO canteens(id, name) SELECT id, name FROM canteen'))
    db.session.execute(text('DELETE FROM windows'))
    db.session.execute(text('INSERT INTO windows(id, canteen_id, name) SELECT id, canteen_id, name FROM window'))
    db.session.execute(text('DELETE FROM dishes'))
    db.session.execute(text('INSERT INTO dishes(id, window_id, name) SELECT id, window_id, name FROM dish'))
    db.session.commit()


def _acquire_submit_slot(user_id, window_id, now, guard_seconds):
    guard = SubmitGuard.query.filter_by(user_id=user_id, window_id=window_id).first()

    if guard:
        passed_seconds = (now - guard.last_submit_time).total_seconds()
        if passed_seconds < guard_seconds:
            guard.block_count = (guard.block_count or 0) + 1
            guard.last_block_time = now
            retry_after = max(1, int(math.ceil(guard_seconds - passed_seconds)))
            return False, retry_after

        guard.last_submit_time = now
        return True, 0

    db.session.add(SubmitGuard(user_id=user_id, window_id=window_id, last_submit_time=now))
    try:
        db.session.flush()
        return True, 0
    except IntegrityError:
        # 并发首提时可能触发唯一约束冲突，回滚后按已存在记录重新判定。
        db.session.rollback()
        current = SubmitGuard.query.filter_by(user_id=user_id, window_id=window_id).first()
        if not current:
            db.session.add(SubmitGuard(user_id=user_id, window_id=window_id, last_submit_time=now))
            db.session.flush()
            return True, 0

        passed_seconds = (now - current.last_submit_time).total_seconds()
        if passed_seconds < guard_seconds:
            current.block_count = (current.block_count or 0) + 1
            current.last_block_time = now
            retry_after = max(1, int(math.ceil(guard_seconds - passed_seconds)))
            return False, retry_after

        current.last_submit_time = now
        return True, 0


def _calc_comprehensive_score(dishes, env_scores, service_scores, safety_scores):
    bucket = []

    for dish in dishes:
        scores = dish.get('food_scores') if isinstance(dish, dict) else {}
        if not isinstance(scores, dict):
            continue
        for value in scores.values():
            number = _safe_number(value)
            if number is not None and 0 <= number <= 10:
                bucket.append(number)

    for score_pack in (env_scores, service_scores, safety_scores):
        if not isinstance(score_pack, dict):
            continue
        for key, value in score_pack.items():
            if str(key).startswith('_'):
                continue
            number = _safe_number(value)
            if number is not None and 0 <= number <= 10:
                bucket.append(number)

    if not bucket:
        return 0.0
    return round(sum(bucket) / len(bucket), 1)


def login_required(role=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user_id = session.get('user_id')
            if not user_id:
                return api_error('请先登录', code=401, http_status=401)

            user = db.session.get(User, user_id)
            if not user:
                session.clear()
                return api_error('登录状态失效，请重新登录', code=401, http_status=401)

            if role and user.role != role:
                return api_error('权限不足', code=403, http_status=403)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def admin_login_required(func):
    @wraps(func)
    @login_required()
    def wrapper(*args, **kwargs):
        user = db.session.get(User, session.get('user_id'))
        if not user or user.role not in ('admin', 'operator'):
            return api_error('权限不足', code=403, http_status=403)
        return func(*args, **kwargs)

    return wrapper


def _role_code_to_name(role_code):
    mapping = {
        'admin': '管理员',
        'operator': '食堂运营',
        'student': '普通用户',
        'teacher': '教师',
    }
    return mapping.get(role_code, role_code or '未知')


def _normalize_role(role_id=None, role_text=''):
    text = str(role_text or '').strip().lower()
    if role_id is not None:
        try:
            role_num = int(role_id)
            if role_num == 1:
                return 'admin'
            if role_num == 3:
                return 'operator'
            if role_num == 4:
                return 'teacher'
            return 'student'
        except (TypeError, ValueError):
            pass

    mapping = {
        '管理员': 'admin',
        'admin': 'admin',
        '食堂运营': 'operator',
        'operator': 'operator',
        '教师': 'teacher',
        'teacher': 'teacher',
        '普通用户': 'student',
        '普通用户(学生)': 'student',
        'student': 'student',
    }
    return mapping.get(text, 'student')


def _note_status_to_code(status):
    status_text = str(status or '').strip().lower()
    if status_text in ('pending', 'draft', '0'):
        return 0
    if status_text in ('rejected', 'reject', '2'):
        return 2
    return 1


def _code_to_note_status(code):
    try:
        value = int(code)
    except (TypeError, ValueError):
        return 'published'

    if value == 0:
        return 'pending'
    if value == 2:
        return 'rejected'
    return 'published'


def _to_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ('1', 'true', 'yes', 'on'):
        return True
    if text in ('0', 'false', 'no', 'off'):
        return False
    return default


def _to_int(value, default, min_value=None, max_value=None):
    try:
        num = int(value)
    except (TypeError, ValueError):
        num = default
    if min_value is not None:
        num = max(min_value, num)
    if max_value is not None:
        num = min(max_value, num)
    return num


def _human_file_size(size_bytes):
    size = float(size_bytes or 0)
    if size < 1024:
        return f'{int(size)}B'
    if size < 1024 * 1024:
        return f'{size / 1024:.1f}KB'
    return f'{size / (1024 * 1024):.1f}MB'


def _extract_channels(value):
    if isinstance(value, list):
        source = value
    elif isinstance(value, str):
        source = [item.strip() for item in value.split(',') if item.strip()]
    elif value is None:
        source = []
    else:
        source = [str(value).strip()]

    channels = []
    for item in source:
        text = str(item).strip().lower()
        if text in ('site', 'email', 'sms') and text not in channels:
            channels.append(text)
    return channels


def _split_csv(value):
    return [item.strip() for item in str(value or '').split(',') if item.strip()]


def _notification_receivers_for_role(role):
    role_upper = str(role or '').strip().upper()
    emails = _split_csv(os.getenv(f'NOTIFY_EMAIL_{role_upper}_TO', ''))
    phones = _split_csv(os.getenv(f'NOTIFY_SMS_{role_upper}_TO', ''))

    if not emails:
        emails = _split_csv(os.getenv('NOTIFY_EMAIL_TO', ''))
    if not phones:
        phones = _split_csv(os.getenv('NOTIFY_SMS_TO', ''))

    return emails, phones


def _send_smtp_mail(receivers, subject, content):
    if not SMTP_HOST or not SMTP_FROM:
        return False, 'SMTP 未配置（缺少 SMTP_HOST/SMTP_FROM）'
    if not receivers:
        return False, '未配置邮件接收人'

    message = EmailMessage()
    message['From'] = SMTP_FROM
    message['To'] = ', '.join(receivers)
    message['Subject'] = subject
    message.set_content(content)

    try:
        if SMTP_USE_TLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls(context=ssl.create_default_context())
                if SMTP_USERNAME:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                if SMTP_USERNAME:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)
    except Exception as exc:
        return False, f'SMTP 发送失败: {exc}'

    return True, '邮件发送成功'


def _send_sms_by_gateway(receivers, title, content, event_type='generic'):
    if not SMS_GATEWAY_URL:
        return False, '短信网关未配置（缺少 SMS_GATEWAY_URL）'
    if not receivers:
        return False, '未配置短信接收人'

    payload = {
        'sender': SMS_SENDER,
        'event_type': event_type,
        'title': title,
        'content': content,
        'receivers': receivers,
    }

    req = urllib.request.Request(
        SMS_GATEWAY_URL,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            **({'Authorization': f'Bearer {SMS_GATEWAY_TOKEN}'} if SMS_GATEWAY_TOKEN else {}),
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=SMS_GATEWAY_TIMEOUT) as resp:
            status = int(getattr(resp, 'status', 200))
            if status >= 400:
                return False, f'短信网关返回状态码 {status}'
            return True, '短信发送成功'
    except urllib.error.HTTPError as exc:
        return False, f'短信网关错误: HTTP {exc.code}'
    except Exception as exc:
        return False, f'短信发送失败: {exc}'


def _get_or_create_system_config():
    row = SystemConfig.query.order_by(SystemConfig.id.asc()).first()
    if not row:
        row = SystemConfig()
        db.session.add(row)
        db.session.commit()
    return row


def _get_or_create_notification_config():
    row = NotificationConfig.query.order_by(NotificationConfig.id.asc()).first()
    if not row:
        row = NotificationConfig()
        db.session.add(row)
        db.session.commit()
    return row


def _serialize_backup_records(limit=10):
    rows = BackupRecord.query.order_by(BackupRecord.create_time.desc()).limit(limit).all()
    return [
        {
            'id': item.id,
            'file_name': item.file_name,
            'time': item.create_time.strftime('%Y-%m-%d %H:%M:%S') if item.create_time else '-',
            'size': _human_file_size(item.file_size),
            'type': '自动备份' if item.backup_type == 'auto' else '手动备份',
        }
        for item in rows
    ]


def _serialize_settings_payload():
    cfg = _get_or_create_system_config()
    notify = _get_or_create_notification_config()

    notify_bad_review = []
    if notify.bad_review_site:
        notify_bad_review.append('site')
    if notify.bad_review_email:
        notify_bad_review.append('email')
    if notify.bad_review_sms:
        notify_bad_review.append('sms')

    notify_audit = []
    if notify.pending_audit_site:
        notify_audit.append('site')
    if notify.pending_audit_email:
        notify_audit.append('email')
    if notify.pending_audit_sms:
        notify_audit.append('sms')

    return {
        'repeatTime': cfg.repeat_submit_minutes,
        'scoreMin': cfg.score_min,
        'scoreMax': cfg.score_max,
        'auditEnabled': bool(cfg.audit_enabled),
        'imgLimit': cfg.image_limit,
        'fileSize': cfg.file_size_limit_mb,
        'allowPDF': bool(cfg.allow_pdf),
        'badReviewThreshold': float(cfg.bad_review_threshold or 4.0),
        'notifyBadReview': notify_bad_review,
        'notifyAudit': notify_audit,
        'notifyFreq': notify.frequency,
        'backups': _serialize_backup_records(limit=10),
    }


def _notification_window_seconds(freq):
    if freq == 'hourly':
        return 3600
    if freq == 'daily':
        return 86400
    return 0


def _allow_dispatch(event_type, channel, target_role, ref_id):
    config = _get_or_create_notification_config()
    window_seconds = _notification_window_seconds(config.frequency)
    now = datetime.now()

    row = NotificationDispatchLog.query.filter_by(
        event_type=event_type,
        channel=channel,
        target_role=target_role,
    ).first()
    if not row:
        row = NotificationDispatchLog(
            event_type=event_type,
            channel=channel,
            target_role=target_role,
            last_ref_id=int(ref_id or 0),
            send_count=1,
            last_send_time=now,
        )
        db.session.add(row)
        return True

    if int(row.last_ref_id or 0) == int(ref_id or 0):
        return False
    if window_seconds > 0 and row.last_send_time and (now - row.last_send_time).total_seconds() < window_seconds:
        return False

    row.last_ref_id = int(ref_id or 0)
    row.send_count = int(row.send_count or 0) + 1
    row.last_send_time = now
    return True


def _push_site_notification(target_role, event_type, title, content):
    users = User.query.filter_by(role=target_role).all()
    for user in users:
        db.session.add(
            NotificationMessage(
                user_id=user.id,
                event_type=event_type,
                title=title,
                content=content,
            )
        )


def _dispatch_event_notifications(event_type, ref_id, target_role, channels, title, content):
    role_emails, role_phones = _notification_receivers_for_role(target_role)
    for channel in channels:
        if not _allow_dispatch(event_type, channel, target_role, ref_id):
            continue
        if channel == 'site':
            _push_site_notification(target_role, event_type, title, content)
            continue

        if channel == 'email':
            ok, msg = _send_smtp_mail(role_emails, title, content)
            if not ok:
                app.logger.warning('notify_email_failed target_role=%s event=%s err=%s', target_role, event_type, msg)
            else:
                app.logger.info('notify_email_ok target_role=%s event=%s', target_role, event_type)
            continue

        if channel == 'sms':
            ok, msg = _send_sms_by_gateway(role_phones, title, content, event_type=event_type)
            if not ok:
                app.logger.warning('notify_sms_failed target_role=%s event=%s err=%s', target_role, event_type, msg)
            else:
                app.logger.info('notify_sms_ok target_role=%s event=%s', target_role, event_type)


def _trigger_bad_review_notifications(evaluation_id):
    evaluation = db.session.get(EvaluationMain, evaluation_id)
    if not evaluation:
        return

    cfg = _get_or_create_system_config()
    threshold = float(cfg.bad_review_threshold or 4.0)
    score = float(evaluation.comprehensive_score or 0)
    if score > threshold:
        return

    notify = _get_or_create_notification_config()
    channels = []
    if notify.bad_review_site:
        channels.append('site')
    if notify.bad_review_email:
        channels.append('email')
    if notify.bad_review_sms:
        channels.append('sms')
    if not channels:
        return

    canteen_name = evaluation.canteen.name if evaluation.canteen else '未知食堂'
    window_name = evaluation.window.name if evaluation.window else '未知窗口'
    title = f'差评预警：{canteen_name}-{window_name}'
    content = f'检测到低分评价（综合分 {score:.1f}），请运营人员尽快处理。评价ID：{evaluation.id}'
    _dispatch_event_notifications('bad_review', evaluation.id, 'operator', channels, title, content)
    db.session.commit()


def _trigger_pending_audit_notifications(note_id):
    note = db.session.get(Note, note_id)
    if not note:
        return

    notify = _get_or_create_notification_config()
    channels = []
    if notify.pending_audit_site:
        channels.append('site')
    if notify.pending_audit_email:
        channels.append('email')
    if notify.pending_audit_sms:
        channels.append('sms')
    if not channels:
        return

    author = db.session.get(User, note.user_id)
    author_name = (author.nickname if author else '') or (author.username if author else '未知用户')
    title = f'新笔记待审核：{note.title}'
    content = f'用户 {author_name} 发布了待审核笔记，笔记ID：{note.id}。'
    _dispatch_event_notifications('pending_audit', note.id, 'admin', channels, title, content)
    db.session.commit()


def _parse_date_text(text_value):
    text_raw = (text_value or '').strip()
    if not text_raw:
        return None
    try:
        return datetime.strptime(text_raw, '%Y-%m-%d').date()
    except ValueError:
        return None


def _avg_dict_numeric(score_obj):
    if not isinstance(score_obj, dict):
        return 0.0
    bucket = []
    for key, value in score_obj.items():
        if str(key).startswith('_'):
            continue
        num = _safe_number(value)
        if num is not None:
            bucket.append(num)
    if not bucket:
        return 0.0
    return round(sum(bucket) / len(bucket), 2)


def _first_non_empty_text(*values):
    for item in values:
        text_value = (item or '').strip()
        if text_value:
            return text_value
    return ''


def _score_from_key_or_avg(score_obj, prefer_key='taste'):
    if not isinstance(score_obj, dict):
        return 0.0
    key_num = _safe_number(score_obj.get(prefer_key))
    if key_num is not None:
        return float(key_num)
    return _avg_dict_numeric(score_obj)


def _safe_tag_list(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        items = [seg.strip() for seg in value.replace('，', ',').split(',')]
        return [item for item in items if item]
    return []


def _calc_note_mention_count(dish_names):
    if not dish_names:
        return 0
    total = 0
    notes = Note.query.all()
    for note in notes:
        text_blob = f"{note.title or ''}\n{note.content or ''}"
        for dish_name in dish_names:
            if dish_name and dish_name in text_blob:
                total += 1
    return total


def _serialize_bad_warning(row, evaluation):
    dish_name = '-'
    if row.dish_id:
        dish = db.session.get(Dish, row.dish_id)
        if dish:
            dish_name = dish.name
    if dish_name == '-' and evaluation and evaluation.dish_evaluations:
        dish_name = evaluation.dish_evaluations[0].dish_name or '-'

    content = _first_non_empty_text(
        evaluation.remark if evaluation else '',
        evaluation.service_comment if evaluation else '',
        evaluation.env_comment if evaluation else '',
        evaluation.safety_comment if evaluation else '',
        evaluation.dish_evaluations[0].remark if evaluation and evaluation.dish_evaluations else '',
        row.summary,
    )
    return {
        'bad_id': row.id,
        'dish_name': dish_name,
        'content': content,
        'create_time': (evaluation.create_time if evaluation and evaluation.create_time else row.create_time).strftime('%Y-%m-%d %H:%M:%S') if (evaluation and evaluation.create_time) or row.create_time else '-',
        'status': '已处理' if row.status == 'handled' else '未处理',
        'score': float(evaluation.comprehensive_score or 0) if evaluation else float(row.score or 0),
    }


def _build_operation_dashboard_payload():
    _sync_operator_warnings()

    now = datetime.now()
    today = now.date()
    thirty_days_ago = now - timedelta(days=29)
    week_begin = datetime.combine(today - timedelta(days=6), datetime.min.time())

    today_evaluation_count = EvaluationMain.query.filter(func.date(EvaluationMain.create_time) == str(today)).count()

    week_avg_value = db.session.query(func.avg(EvaluationMain.comprehensive_score)).filter(EvaluationMain.create_time >= week_begin, EvaluationMain.create_time <= now).scalar()
    week_avg_score = round(float(week_avg_value or 0.0), 2)

    bad_pairs = (
        db.session.query(OperatorWarning, EvaluationMain)
        .join(EvaluationMain, OperatorWarning.evaluation_id == EvaluationMain.id)
        .filter(OperatorWarning.status == 'pending', func.coalesce(EvaluationMain.comprehensive_score, 0) <= 2)
        .order_by(OperatorWarning.create_time.desc())
        .all()
    )
    bad_review_count = len(bad_pairs)

    dish_name_list = [item.name for item in Dish.query.with_entities(Dish.name).all()]
    note_mention_count = _calc_note_mention_count(dish_name_list)

    trend_rows = []
    for offset in range(30):
        day = today - timedelta(days=29 - offset)
        begin = datetime.combine(day, datetime.min.time())
        end = datetime.combine(day, datetime.max.time())
        mains = EvaluationMain.query.filter(EvaluationMain.create_time >= begin, EvaluationMain.create_time <= end).all()

        env_values = []
        service_values = []
        taste_values = []
        for main in mains:
            env_values.append(_avg_dict_numeric(main.env_scores))
            service_values.append(_avg_dict_numeric(main.service_scores))
            for dish_eval in main.dish_evaluations:
                taste_values.append(_score_from_key_or_avg(dish_eval.food_scores, 'taste'))

        trend_rows.append(
            {
                'date': day.strftime('%Y-%m-%d'),
                'taste_avg': round(sum(taste_values) / len(taste_values), 2) if taste_values else 0.0,
                'env_avg': round(sum(env_values) / len(env_values), 2) if env_values else 0.0,
                'service_avg': round(sum(service_values) / len(service_values), 2) if service_values else 0.0,
            }
        )

    hot_raw = (
        db.session.query(EvaluationDish.dish_id, func.count(EvaluationDish.id).label('eval_count'))
        .filter(EvaluationDish.dish_id > 0)
        .group_by(EvaluationDish.dish_id)
        .order_by(func.count(EvaluationDish.id).desc())
        .limit(10)
        .all()
    )
    hot_dishes_top10 = []
    for row in hot_raw:
        dish = db.session.get(Dish, row.dish_id)
        if not dish:
            continue
        eval_rows = EvaluationDish.query.filter_by(dish_id=dish.id).all()
        score_list = [_avg_dict_numeric(item.food_scores) for item in eval_rows]
        hot_dishes_top10.append(
            {
                'dish_id': dish.id,
                'dish_name': dish.name,
                'evaluation_count': int(row.eval_count or 0),
                'avg_score': round(sum(score_list) / len(score_list), 2) if score_list else 0.0,
            }
        )

    bad_review_list = [_serialize_bad_warning(warning, evaluation) for warning, evaluation in bad_pairs]

    return {
        'today_evaluation_count': int(today_evaluation_count),
        'week_avg_score': week_avg_score,
        'bad_review_count': int(bad_review_count),
        'note_mention_count': int(note_mention_count),
        '30day_score_trend': trend_rows,
        'hot_dishes_top10': hot_dishes_top10,
        'bad_review_list': bad_review_list,
        'last_refresh_time': now.strftime('%Y-%m-%d %H:%M:%S'),
    }


def _sync_operator_warnings():
    cfg = _get_or_create_system_config()
    threshold = float(cfg.bad_review_threshold or 4.0)
    rows = EvaluationMain.query.filter(EvaluationMain.comprehensive_score <= threshold).all()
    for row in rows:
        existed = OperatorWarning.query.filter_by(evaluation_id=row.id).first()
        if existed:
            continue
        first_dish_eval = row.dish_evaluations[0] if row.dish_evaluations else None
        summary = _first_non_empty_text(
            row.remark,
            row.service_comment,
            row.env_comment,
            row.safety_comment,
            first_dish_eval.remark if first_dish_eval else '',
            '检测到低分评价，请尽快复核。',
        )
        db.session.add(
            OperatorWarning(
                evaluation_id=row.id,
                canteen_id=row.canteen_id,
                window_id=row.window_id,
                dish_id=first_dish_eval.dish_id if first_dish_eval and first_dish_eval.dish_id else None,
                score=float(row.comprehensive_score or 0),
                summary=summary[:255],
                status='pending',
            )
        )
    db.session.commit()


def _serialize_warning(row):
    evaluation = db.session.get(EvaluationMain, row.evaluation_id) if row.evaluation_id else None
    canteen = db.session.get(Canteen, row.canteen_id) if row.canteen_id else None
    window = db.session.get(Window, row.window_id) if row.window_id else None
    dish = db.session.get(Dish, row.dish_id) if row.dish_id else None
    return {
        'id': row.id,
        'evaluation_id': row.evaluation_id,
        'score': float(row.score or 0),
        'summary': row.summary or '',
        'status': row.status,
        'handle_note': row.handle_note or '',
        'canteen_name': canteen.name if canteen else '-',
        'window_name': window.name if window else '-',
        'dish_name': dish.name if dish else '-',
        'user_identity': evaluation.identity_type if evaluation else '-',
        'create_time': row.create_time.strftime('%Y-%m-%d %H:%M:%S') if row.create_time else '-',
        'handled_time': row.handled_time.strftime('%Y-%m-%d %H:%M:%S') if row.handled_time else '',
    }


# --- API 接口 ---

@app.route('/api/health', methods=['GET'])
def api_health():
    try:
        db.session.execute(text('SELECT 1'))
        return api_success({'status': 'ok', 'db': 'ok'}, msg='服务健康')
    except Exception as exc:
        return api_error(f'服务异常: {str(exc)}', code=500, http_status=500)


@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return api_error('用户名和密码不能为空')
    if len(username) < 2 or len(username) > 20:
        return api_error('用户名长度需在2-20位之间')
    if len(password) < 6:
        return api_error('密码长度至少6位')

    existed = User.query.filter_by(username=username).first()
    if existed:
        return api_error('用户名已存在', code=409, http_status=409)

    user = User(username=username, password=generate_password_hash(password), role='student')
    db.session.add(user)
    db.session.commit()

    session.permanent = True
    session['user_id'] = user.id
    session['role'] = user.role
    return api_success(_serialize_user(user), msg='注册成功')


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return api_error('用户名和密码不能为空')

    user = User.query.filter_by(username=username).first()
    if not user or not _verify_password(user.password, password):
        return api_error('用户名或密码错误', code=401, http_status=401)

    session.permanent = True
    session['user_id'] = user.id
    session['role'] = user.role
    return api_success(_serialize_user(user), msg='登录成功')


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return api_success(msg='已退出登录')


@app.route('/api/auth/me', methods=['GET'])
@login_required()
def auth_me():
    user = db.session.get(User, session['user_id'])
    return api_success(_serialize_user(user))


@app.route('/api/user/profile', methods=['GET'])
@login_required()
def get_user_profile():
    user = db.session.get(User, session['user_id'])
    return api_success(_serialize_user(user), msg='查询成功')


@app.route('/api/user/profile', methods=['POST'])
@login_required()
def update_user_profile():
    data = request.get_json(silent=True) or {}
    nickname = (data.get('nickname') or '').strip()
    phone = (data.get('phone') or '').strip()
    avatar = (data.get('avatar') or '').strip()

    if phone and not phone.isdigit():
        return api_error('手机号格式不正确')
    if phone and len(phone) != 11:
        return api_error('手机号需为11位')
    if len(nickname) > 40:
        return api_error('昵称长度不能超过40个字符')
    if len(avatar) > 255:
        return api_error('头像地址长度不能超过255个字符')

    user = db.session.get(User, session['user_id'])
    user.nickname = nickname or user.nickname
    user.phone = phone or user.phone
    user.avatar = avatar or user.avatar
    db.session.commit()
    return api_success(_serialize_user(user), msg='资料更新成功')


@app.route('/api/canteens', methods=['GET'])
def get_canteens():
    rows = Canteen.query.order_by(Canteen.id.asc()).all()
    data = [{'id': row.id, 'name': row.name} for row in rows]
    return api_success(data, msg='查询成功')


@app.route('/api/canteens/detail', methods=['GET'])
def get_canteen_detail_by_name():
    _ensure_canteen_detail_seed_data()
    name = (request.args.get('name') or '').strip()
    if not name:
        return api_error('缺少食堂名称参数 name')

    row = db.session.execute(
        text(
            '''
            SELECT id, name, COALESCE(address, '') AS address,
                   COALESCE(business_hours, '07:00-21:00') AS business_hours
            FROM canteen
            WHERE name = :name
            LIMIT 1
            '''
        ),
        {'name': name},
    ).mappings().first()
    if not row:
        return api_error('食堂不存在', code=404, http_status=404)

    return api_success(
        {
            'id': int(row['id']),
            'name': row['name'],
            'address': row['address'] or '未知地址',
            'business_hours': row['business_hours'] or '--',
        },
        msg='查询成功',
    )


@app.route('/api/windows', methods=['GET'])
def get_windows():
    _ensure_canteen_detail_seed_data()
    canteen_id = _safe_int(request.args.get('canteen_id'))
    query = Window.query
    if canteen_id:
        query = query.filter(Window.canteen_id == canteen_id)
    rows = query.order_by(Window.id.asc()).all()
    data = [{'id': row.id, 'name': row.name, 'canteen_id': row.canteen_id} for row in rows]
    return api_success(data, msg='查询成功')


@app.route('/api/food-safety/notices', methods=['GET'])
def get_food_safety_notices():
    _ensure_canteen_detail_seed_data()
    canteen_id = _safe_int(request.args.get('canteen_id'))
    notice_type = (request.args.get('type') or '').strip()
    status = (request.args.get('status') or '').strip().lower()
    page = max(1, _safe_int(request.args.get('page'), 1) or 1)
    page_size = max(1, min(50, _safe_int(request.args.get('page_size'), 10) or 10))

    where_sql = ['1=1']
    params = {}
    if canteen_id:
        where_sql.append('n.canteen_id = :canteen_id')
        params['canteen_id'] = canteen_id
    if notice_type and notice_type not in ('全部', 'all'):
        where_sql.append('n.type = :notice_type')
        params['notice_type'] = notice_type

    if status in ('active', '生效中', 'valid'):
        where_sql.append("date(COALESCE(n.valid_until, n.expire_date)) >= date('now')")
    elif status in ('expired', '已过期'):
        where_sql.append("date(COALESCE(n.valid_until, n.expire_date)) < date('now')")

    where_clause = ' AND '.join(where_sql)

    total = db.session.execute(
        text(
            f'''
            SELECT COUNT(1)
            FROM food_safety_notices n
            WHERE {where_clause}
            '''
        ),
        params,
    ).scalar() or 0

    offset = (page - 1) * page_size
    rows = db.session.execute(
        text(
            f'''
            SELECT n.id, n.canteen_id, c.name AS canteen_name, n.title, n.type,
                   n.valid_from, COALESCE(n.valid_until, n.expire_date) AS valid_until,
                   n.file_url, n.status, n.content, n.image_url, n.create_time
            FROM food_safety_notices n
            LEFT JOIN canteen c ON c.id = n.canteen_id
            WHERE {where_clause}
            ORDER BY n.create_time DESC, n.id DESC
            LIMIT :limit OFFSET :offset
            '''
        ),
        {**params, 'limit': page_size, 'offset': offset},
    ).mappings().all()

    list_data = []
    for row in rows:
        valid_until = str(row['valid_until']) if row['valid_until'] else ''
        is_expired = False
        try:
            if valid_until:
                is_expired = datetime.strptime(valid_until, '%Y-%m-%d').date() < date.today()
        except ValueError:
            is_expired = False

        list_data.append(
            {
                'id': int(row['id']),
                'canteen_id': int(row['canteen_id']),
                'canteen_name': row['canteen_name'] or '未知食堂',
                'title': row['title'],
                'type': row['type'] or '检测报告',
                'valid_from': str(row['valid_from']) if row['valid_from'] else '',
                'valid_until': valid_until,
                'file_url': row['file_url'] or '',
                'status': 'expired' if is_expired else 'active',
                'status_text': '已过期' if is_expired else '生效中',
                'content': row['content'] or '',
                'image_url': row['image_url'] or '',
                'create_time': str(row['create_time']) if row['create_time'] else '',
            }
        )

    # 兼容旧调用：只传 canteen_id 时返回纯数组，避免影响已上线页面。
    has_advanced_params = any(request.args.get(k) for k in ('type', 'status', 'page', 'page_size'))
    if canteen_id and not has_advanced_params:
        return api_success(list_data, msg='查询成功')

    total_pages = max(1, math.ceil(total / page_size))
    return api_success(
        {
            'list': list_data,
            'total': int(total),
            'page': int(page),
            'page_size': int(page_size),
            'total_pages': int(total_pages),
        },
        msg='查询成功',
    )


def _build_notice_pdf_bytes(title, body):
    safe_title = (title or '食品安全公示').replace('(', '').replace(')', '')
    safe_body = (body or '无').replace('(', '').replace(')', '')
    lines = [
        'BT',
        '/F1 20 Tf',
        '72 760 Td',
        f'({safe_title}) Tj',
        '/F1 12 Tf',
        '0 -32 Td',
        f'({safe_body}) Tj',
        '0 -28 Td',
        f'(Generated at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}) Tj',
        'ET',
    ]
    stream = '\n'.join(lines)
    stream_bytes = stream.encode('latin-1', errors='ignore')

    objects = []
    objects.append(b'1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n')
    objects.append(b'2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n')
    objects.append(b'3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n')
    objects.append(b'4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n')
    objects.append(
        b'5 0 obj << /Length ' + str(len(stream_bytes)).encode('ascii') + b' >> stream\n' + stream_bytes + b'\nendstream endobj\n'
    )

    pdf = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_pos = len(pdf)
    pdf.extend(f'xref\n0 {len(offsets)}\n'.encode('ascii'))
    pdf.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        pdf.extend(f'{offset:010d} 00000 n \n'.encode('ascii'))
    pdf.extend(
        (
            f'trailer << /Size {len(offsets)} /Root 1 0 R >>\n'
            f'startxref\n{xref_pos}\n%%EOF'
        ).encode('ascii')
    )
    return bytes(pdf)


@app.route('/api/files/preview/<int:notice_id>', methods=['GET'])
def preview_notice_file(notice_id):
    row = db.session.execute(
        text(
            '''
            SELECT title, content
            FROM food_safety_notices
            WHERE id = :id
            LIMIT 1
            '''
        ),
        {'id': notice_id},
    ).mappings().first()
    if not row:
        return api_error('公示不存在', code=404, http_status=404)

    pdf_bytes = _build_notice_pdf_bytes(row['title'], row['content'])
    return Response(pdf_bytes, mimetype='application/pdf')


@app.route('/api/files/download/<int:notice_id>', methods=['GET'])
def download_notice_file(notice_id):
    row = db.session.execute(
        text(
            '''
            SELECT title, content
            FROM food_safety_notices
            WHERE id = :id
            LIMIT 1
            '''
        ),
        {'id': notice_id},
    ).mappings().first()
    if not row:
        return api_error('公示不存在', code=404, http_status=404)

    pdf_bytes = _build_notice_pdf_bytes(row['title'], row['content'])
    filename = f'notice_{notice_id}.pdf'
    headers = {'Content-Disposition': f'attachment; filename={filename}'}
    return Response(pdf_bytes, mimetype='application/pdf', headers=headers)


@app.route('/api/evaluations', methods=['GET'])
def get_canteen_evaluations():
    _ensure_canteen_detail_seed_data()
    canteen_id = _safe_int(request.args.get('canteen_id'))
    if not canteen_id:
        return api_error('缺少 canteen_id 参数')

    rows = db.session.execute(
        text(
            '''
            SELECT e.id, e.canteen_id, e.window_id, e.dish_id, e.score, e.remark, e.images, e.create_time,
                   COALESCE(u.username, '校园用户') AS username
            FROM evaluations e
            LEFT JOIN user u ON u.id = e.user_id
            WHERE e.canteen_id = :canteen_id
            ORDER BY e.create_time DESC, e.id DESC
            '''
        ),
        {'canteen_id': canteen_id},
    ).mappings().all()

    data = [
        {
            'id': int(row['id']),
            'canteen_id': int(row['canteen_id']),
            'window_id': _safe_int(row['window_id'], 0),
            'dish_id': _safe_int(row['dish_id'], 0),
            'score': float(row['score'] or 0),
            'content': row['remark'] or '',
            'create_time': str(row['create_time']) if row['create_time'] else '',
            'username': row['username'] or '校园用户',
        }
        for row in rows
    ]
    return api_success(data, msg='查询成功')


@app.route('/api/user-shares', methods=['GET'])
def get_user_shares():
    _ensure_canteen_detail_seed_data()
    canteen_id = _safe_int(request.args.get('canteen_id'))
    if not canteen_id:
        return api_error('缺少 canteen_id 参数')

    rows = db.session.execute(
        text(
            '''
            SELECT id, canteen_id, user_id, username, content, image_url, create_time
            FROM user_shares
            WHERE canteen_id = :canteen_id
            ORDER BY create_time DESC, id DESC
            '''
        ),
        {'canteen_id': canteen_id},
    ).mappings().all()

    data = [
        {
            'id': int(row['id']),
            'canteen_id': int(row['canteen_id']),
            'user_id': _safe_int(row['user_id'], 0),
            'username': row['username'] or '校园用户',
            'content': row['content'] or '',
            'image_url': row['image_url'] or '',
            'create_time': str(row['create_time']) if row['create_time'] else '',
        }
        for row in rows
    ]
    return api_success(data, msg='查询成功')

@app.route('/api/dishes', methods=['GET'])
def get_dishes():
    window_id = _safe_int(request.args.get('window_id'))
    query = Dish.query
    if window_id:
        query = query.filter(Dish.window_id == window_id)
    rows = query.order_by(Dish.id.asc()).all()
    return api_success(
        [
            {
                'id': row.id,
                'name': row.name,
                'window_id': row.window_id,
                'price': float(row.price or 0),
            }
            for row in rows
        ],
        msg='查询成功',
    )


@app.route('/api/window/<int:window_id>/dishes', methods=['GET'])
def get_window_dishes(window_id):
    dishes = Dish.query.filter_by(window_id=window_id).all()
    result = [
        {
            'id': d.id,
            'name': d.name,
            'price': float(d.price or 0),
            'review_count': d.review_count or 0,
            'average_score': float(d.average_score or 0),
        }
        for d in dishes
    ]
    return api_success(result, msg='查询成功')


@app.route('/api/window/<int:window_id>/safety', methods=['GET'])
def get_window_safety(window_id):
    _ = window_id
    return api_success([], msg='查询成功')


@app.route('/api/public/dashboard', methods=['GET'])
def public_dashboard_overview():
    seeded = _public_ensure_seed_data_if_needed()
    range_key, start_time, end_time = _public_parse_range(
        request.args.get('range') or request.args.get('period') or request.args.get('time_dimension')
    )

    base_filter = [
        EvaluationMain.buy_time >= start_time,
        EvaluationMain.buy_time <= end_time,
    ]
    scored_filter = base_filter + [EvaluationMain.comprehensive_score > 0]

    total_visits = db.session.query(func.count(EvaluationMain.id)).filter(*base_filter).scalar() or 0
    avg_score = db.session.query(func.avg(EvaluationMain.comprehensive_score)).filter(*scored_filter).scalar() or 0
    bad_review_count = (
        db.session.query(func.count(EvaluationMain.id))
        .filter(*scored_filter, EvaluationMain.comprehensive_score <= 2)
        .scalar()
        or 0
    )
    active_dish_count = Dish.query.filter(Dish.is_active.is_(True)).count()

    ranking_rows = (
        db.session.query(
            Canteen.id.label('canteen_id'),
            Canteen.name.label('canteen_name'),
            func.avg(EvaluationMain.comprehensive_score).label('avg_score'),
            func.count(EvaluationMain.id).label('eval_count'),
        )
        .join(EvaluationMain, EvaluationMain.canteen_id == Canteen.id)
        .filter(*scored_filter)
        .group_by(Canteen.id, Canteen.name)
        .order_by(func.avg(EvaluationMain.comprehensive_score).desc(), func.count(EvaluationMain.id).desc())
        .limit(10)
        .all()
    )

    ranking = [
        {
            'canteen_id': row.canteen_id,
            'canteen_name': row.canteen_name,
            'avg_score': round(float(row.avg_score or 0), 1),
            'eval_count': int(row.eval_count or 0),
        }
        for row in ranking_rows
    ]

    latest_update = db.session.query(func.max(EvaluationMain.create_time)).scalar()

    return api_success(
        {
            'range': range_key,
            'total_visits': int(total_visits),
            'avg_score': round(float(avg_score), 1),
            'bad_review_count': int(bad_review_count),
            'active_dish_count': int(active_dish_count),
            'canteen_ranking': ranking,
            'safety_notice_url': '/pages/c-client/safety_list.html',
            'update_time': latest_update.strftime('%Y-%m-%d %H:%M:%S') if latest_update else datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'seeded': bool(seeded),
        },
        msg='查询成功',
    )


@app.route('/api/public/trend', methods=['GET'])
def public_dashboard_trend():
    _public_ensure_seed_data_if_needed()
    range_key, start_time, end_time = _public_parse_range(
        request.args.get('range') or request.args.get('period') or request.args.get('time_dimension')
    )

    rows = (
        EvaluationMain.query.filter(EvaluationMain.buy_time >= start_time, EvaluationMain.buy_time <= end_time)
        .order_by(EvaluationMain.buy_time.asc())
        .all()
    )

    labels = []
    values = []

    if range_key == 'today':
        buckets = {h: 0 for h in range(24)}
        for row in rows:
            if row.buy_time:
                buckets[row.buy_time.hour] += 1
        labels = [f'{h:02d}:00' for h in range(24)]
        values = [buckets[h] for h in range(24)]
    else:
        days = 7 if range_key == 'week' else 30
        day_start = datetime(end_time.year, end_time.month, end_time.day) - timedelta(days=days - 1)
        buckets = {(day_start + timedelta(days=i)).date(): 0 for i in range(days)}
        for row in rows:
            if row.buy_time:
                d = row.buy_time.date()
                if d in buckets:
                    buckets[d] += 1
        labels = [d.strftime('%m-%d') for d in buckets.keys()]
        values = [buckets[d] for d in buckets.keys()]

    return api_success({'labels': labels, 'values': values, 'range': range_key}, msg='查询成功')


@app.route('/api/public/top-dishes', methods=['GET'])
def public_dashboard_top_dishes():
    _public_ensure_seed_data_if_needed()
    _, start_time, end_time = _public_parse_range(
        request.args.get('range') or request.args.get('period') or request.args.get('time_dimension')
    )

    rows = (
        db.session.query(
            Dish.id.label('dish_id'),
            Dish.name.label('dish_name'),
            func.count(EvaluationDish.id).label('value'),
        )
        .join(EvaluationDish, EvaluationDish.dish_id == Dish.id)
        .join(EvaluationMain, EvaluationMain.id == EvaluationDish.evaluation_id)
        .filter(EvaluationMain.buy_time >= start_time, EvaluationMain.buy_time <= end_time)
        .group_by(Dish.id, Dish.name)
        .order_by(func.count(EvaluationDish.id).desc(), Dish.id.asc())
        .limit(10)
        .all()
    )

    data = [{'dish_id': row.dish_id, 'name': row.dish_name, 'value': int(row.value or 0)} for row in rows]
    return api_success({'list': data}, msg='查询成功')


@app.route('/api/public/peak-time', methods=['GET'])
def public_dashboard_peak_time():
    _public_ensure_seed_data_if_needed()
    _, start_time, end_time = _public_parse_range(
        request.args.get('range') or request.args.get('period') or request.args.get('time_dimension')
    )

    rows = EvaluationMain.query.filter(EvaluationMain.buy_time >= start_time, EvaluationMain.buy_time <= end_time).all()
    buckets = [
        ('7:00-9:00', 7, 9),
        ('9:00-11:00', 9, 11),
        ('11:00-13:00', 11, 13),
        ('13:00-17:00', 13, 17),
        ('17:00-19:00', 17, 19),
        ('19:00-22:00', 19, 22),
    ]

    counter = {name: 0 for name, _, _ in buckets}
    for row in rows:
        if not row.buy_time:
            continue
        hour = row.buy_time.hour
        for name, start_h, end_h in buckets:
            if start_h <= hour < end_h:
                counter[name] += 1
                break

    total = sum(counter.values()) or 1
    data = [
        {
            'name': name,
            'value': int(counter[name]),
            'percent': round(counter[name] * 100.0 / total, 1),
        }
        for name, _, _ in buckets
    ]

    return api_success({'list': data}, msg='查询成功')

@app.route('/api/submit_evaluation', methods=['POST'])
@login_required()
def submit_evaluation():
    return _submit_evaluation(enforce_repeat_guard=True)


@app.route('/api/evaluate', methods=['POST'])
@login_required()
def submit_evaluation_alias():
    return _submit_evaluation(enforce_repeat_guard=True)


def _submit_evaluation(enforce_repeat_guard=True):
    try:
        data = request.get_json(silent=True) or {}

        # 1. 基础校验
        # 注意：前端传过来的字段名可能与数据库模型不完全一致，需在此处映射
        user_id = session.get('user_id')
        canteen_id = _safe_int(data.get('canteen_id'))
        window_id = _safe_int(data.get('window_id'))
        buy_time_str = data.get('buy_time')
        identity_type = (data.get('identity_type') or '').strip() or 'student'

        if not buy_time_str:
            buy_time_str = datetime.now().strftime('%Y-%m-%dT%H:%M')

        if not all([canteen_id, window_id, buy_time_str]):
            return api_error('缺少必填字段')

        # 校验：至少选1个菜品
        dishes = data.get('dishes', [])
        if (not dishes) and _safe_int(data.get('dish_id')):
            dishes = [
                {
                    'dish_id': _safe_int(data.get('dish_id')),
                    'dish_name': data.get('dish_name') or '',
                    'food_scores': _safe_scores(data.get('food_scores', {})),
                    'remark': data.get('remark') or '',
                    'images': _normalize_images(data.get('images')),
                }
            ]

        normalized_dishes = []
        for raw_item in dishes:
            normalized = _normalize_dish_payload(raw_item)
            if normalized and (normalized['dish_id'] or normalized['dish_name']):
                normalized_dishes.append(normalized)

        dishes = normalized_dishes
        if not dishes:
            return api_error('请至少选择一个菜品')
            
        # 2. 数据入库
        try:
            buy_time = datetime.strptime(buy_time_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            return api_error('时间格式错误')

        now = datetime.now()
        if enforce_repeat_guard:
            cfg = _get_or_create_system_config()
            guard_seconds = max(1, int(cfg.repeat_submit_minutes or 1)) * 60
            allow_submit, retry_after = _acquire_submit_slot(user_id, window_id, now, guard_seconds)
            if not allow_submit:
                db.session.commit()
                app.logger.warning(
                    'submit_blocked user_id=%s window_id=%s retry_after=%s',
                    user_id,
                    window_id,
                    retry_after,
                )
                return api_error(
                    f'提交过于频繁，请{retry_after}秒后再试',
                    code=429,
                    http_status=429,
                    data={},
                )

        # 提取评分 JSON，并将图文拆分到独立列
        env_scores = _extract_score_pack(data, 'env', ['clean', 'air', 'hygiene'])
        service_scores = _extract_score_pack(data, 'service', ['attitude', 'speed', 'dress'])
        safety_scores = _extract_score_pack(data, 'safety', ['fresh', 'info'])
        service_comment = (data.get('service_comment') or '').strip()
        service_images = _normalize_images(data.get('service_images'))
        env_comment = (data.get('env_comment') or '').strip()
        env_images = _normalize_images(data.get('env_images'))
        safety_comment = (data.get('safety_comment') or '').strip()
        safety_images = _normalize_images(data.get('safety_images'))
        images = data.get('images', [])
        remark = data.get('remark', '')
        comprehensive_score = _calc_comprehensive_score(dishes, env_scores, service_scores, safety_scores)

        # 创建评价主表
        eval_main = EvaluationMain(
            user_id=user_id,
            canteen_id=canteen_id,
            window_id=window_id,
            buy_time=buy_time,
            identity_type=identity_type,
            grade=data.get('grade'),
            age=data.get('age'),
            dining_years=data.get('dining_years'),
            env_scores=env_scores,
            service_scores=service_scores,
            safety_scores=safety_scores,
            service_comment=service_comment,
            service_images=service_images,
            env_comment=env_comment,
            env_images=env_images,
            safety_comment=safety_comment,
            safety_images=safety_images,
            comprehensive_score=comprehensive_score,
            images=images,
            remark=remark
        )
        db.session.add(eval_main)
        db.session.flush() # 获取ID

        db.session.execute(
            text(
                '''
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evaluation_main_id INTEGER,
                    user_id INTEGER,
                    canteen_id INTEGER,
                    window_id INTEGER,
                    dish_id INTEGER,
                    score FLOAT DEFAULT 0,
                    remark TEXT,
                    images TEXT,
                    create_time DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )
        )
        eval_cols = {
            row[1]
            for row in db.session.execute(text('PRAGMA table_info(evaluations)')).fetchall()
        }
        for col_name, sql in {
            'canteen_id': 'ALTER TABLE evaluations ADD COLUMN canteen_id INTEGER',
            'window_id': 'ALTER TABLE evaluations ADD COLUMN window_id INTEGER',
            'dish_id': 'ALTER TABLE evaluations ADD COLUMN dish_id INTEGER',
        }.items():
            if col_name not in eval_cols:
                db.session.execute(text(sql))
        
        # 创建评价-菜品关联表
        for d in dishes:
            dish_id = _safe_int(d.get('dish_id'), 0) or 0
            dish_name = (d.get('dish_name') or '').strip()
            dish_obj = db.session.get(Dish, dish_id) if dish_id else None
            if not dish_name and dish_obj:
                dish_name = dish_obj.name

            eval_dish = EvaluationDish(
                evaluation_id=eval_main.id,
                dish_id=dish_id, # 0为自定义
                dish_name=dish_name or '未命名菜品',
                # dish_img_url 暂不处理
                food_scores=_safe_scores(d.get('food_scores', {})),
                remark=(d.get('remark') or '').strip()
            )
            db.session.add(eval_dish)

            dish = dish_obj
            if dish:
                dish.review_count = (dish.review_count or 0) + 1

            db.session.execute(
                text(
                    '''
                    INSERT INTO evaluations(
                        evaluation_main_id, user_id, canteen_id, window_id, dish_id, score, remark, images, create_time
                    ) VALUES (
                        :evaluation_main_id, :user_id, :canteen_id, :window_id, :dish_id, :score, :remark, :images, :create_time
                    )
                    '''
                ),
                {
                    'evaluation_main_id': eval_main.id,
                    'user_id': user_id,
                    'canteen_id': canteen_id,
                    'window_id': window_id,
                    'dish_id': dish_id,
                    'score': comprehensive_score,
                    'remark': (d.get('remark') or '').strip() or remark,
                    'images': json.dumps(d.get('images') or [], ensure_ascii=False),
                    'create_time': now.strftime('%Y-%m-%d %H:%M:%S'),
                },
            )
                
        db.session.commit()
        try:
            _trigger_bad_review_notifications(eval_main.id)
        except Exception as notify_exc:
            db.session.rollback()
            app.logger.warning('bad_review_notification_failed evaluation_id=%s err=%s', eval_main.id, notify_exc)
        if enforce_repeat_guard:
            app.logger.info('submit_success user_id=%s window_id=%s evaluation_id=%s', user_id, window_id, eval_main.id)
        return api_success({'evaluation_id': eval_main.id, 'comprehensive_score': comprehensive_score}, msg='评价提交成功')

    except Exception as e:
        db.session.rollback()
        return api_error(str(e), code=500, http_status=500)


@app.route('/api/evaluation/save', methods=['POST'])
@login_required()
def save_evaluation_compat():
    return _submit_evaluation(enforce_repeat_guard=False)


@app.route('/api/evaluation/submit', methods=['POST'])
@login_required()
def submit_evaluation_compat():
    return _submit_evaluation(enforce_repeat_guard=True)


@app.route('/api/evaluation/stats/<int:window_id>', methods=['GET'])
def get_evaluation_stats(window_id):
    rows = EvaluationMain.query.filter_by(window_id=window_id).all()
    if not rows:
        return api_success({'count': 0, 'avg_score': 0.0}, msg='暂无数据')

    total = sum(float(r.comprehensive_score or 0) for r in rows)
    avg_score = round(total / len(rows), 1)
    return api_success({'count': len(rows), 'avg_score': avg_score}, msg='查询成功')

@app.route('/api/get_my_evaluations', methods=['GET'])
@app.route('/api/my_evaluations', methods=['GET'])
@login_required()
def get_my_evaluations():
    user_id = session.get('user_id')
    
    evals = EvaluationMain.query.filter_by(user_id=user_id).order_by(EvaluationMain.create_time.desc()).all()
    
    result = []
    for e in evals:
        # 获取关联的菜品信息
        dish_list = []
        for ed in e.dish_evaluations:
            dish_list.append({
                'dish_name': ed.dish_name,
                'food_scores': ed.food_scores
            })
            
        service_comment, service_images = _pick_comment_images(
            e.service_comment,
            e.service_images,
            e.service_scores,
        )
        env_comment, env_images = _pick_comment_images(
            e.env_comment,
            e.env_images,
            e.env_scores,
        )
        safety_comment, safety_images = _pick_comment_images(
            e.safety_comment,
            e.safety_images,
            e.safety_scores,
        )

        result.append({
            'id': e.id,
            'canteen_name': e.canteen.name if e.canteen else '未知食堂',
            'window_name': e.window.name if e.window else '未知窗口',
            'buy_time': e.buy_time.strftime('%Y-%m-%d %H:%M'),
            'create_time': e.create_time.strftime('%Y-%m-%d %H:%M:%S'),
            'dishes': dish_list,
            'env_scores': e.env_scores,
            'service_scores': e.service_scores
            ,
            'safety_scores': e.safety_scores,
            'comprehensive_score': float(e.comprehensive_score or 0),
            'service_comment': service_comment,
            'service_images': service_images,
            'env_comment': env_comment,
            'env_images': env_images,
            'safety_comment': safety_comment,
            'safety_images': safety_images,
        })
        
    return api_success(result)


@app.route('/api/my_evaluations/<int:evaluation_id>', methods=['DELETE'])
@login_required()
def delete_my_evaluation(evaluation_id):
    user_id = session.get('user_id')
    row = EvaluationMain.query.filter_by(id=evaluation_id, user_id=user_id).first()
    if not row:
        return api_error('评价不存在', code=404, http_status=404)

    db.session.delete(row)
    db.session.commit()
    return api_success(msg='删除成功')


@app.route('/api/my_notes', methods=['GET'])
@login_required()
def get_my_notes():
    user_id = session.get('user_id')
    rows = Note.query.filter_by(user_id=user_id).order_by(Note.create_time.desc()).all()
    result = [
        {
            'id': n.id,
            'title': n.title,
            'content': n.content,
            'status': '已发布' if n.status == 'published' else n.status,
            'like_count': int(n.like_count or 0),
            'create_time': n.create_time.strftime('%Y-%m-%d %H:%M:%S'),
            'update_time': n.update_time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        for n in rows
    ]
    return api_success(result, msg='查询成功')


@app.route('/api/my_notes', methods=['POST'])
@login_required()
def create_my_note():
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()

    if len(title) < 2:
        return api_error('标题至少2个字')
    if len(title) > 200:
        return api_error('标题最多200个字')
    if len(content) < 5:
        return api_error('内容至少5个字')
    if len(content) > 5000:
        return api_error('内容最多5000个字')

    cfg = _get_or_create_system_config()
    note_status = 'pending' if cfg.audit_enabled else 'published'
    row = Note(user_id=user_id, title=title, content=content, status=note_status)
    db.session.add(row)
    db.session.commit()
    if note_status == 'pending':
        try:
            _trigger_pending_audit_notifications(row.id)
        except Exception as notify_exc:
            db.session.rollback()
            app.logger.warning('pending_audit_notification_failed note_id=%s err=%s', row.id, notify_exc)
        return api_success({'id': row.id, 'status': 'pending'}, msg='发布成功，待审核')
    return api_success({'id': row.id, 'status': 'published'}, msg='发布成功')


@app.route('/api/my_notes/<int:note_id>', methods=['PUT'])
@login_required()
def update_my_note(note_id):
    user_id = session.get('user_id')
    row = Note.query.filter_by(id=note_id, user_id=user_id).first()
    if not row:
        return api_error('笔记不存在', code=404, http_status=404)

    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()

    if len(title) < 2:
        return api_error('标题至少2个字')
    if len(title) > 200:
        return api_error('标题最多200个字')
    if len(content) < 5:
        return api_error('内容至少5个字')
    if len(content) > 5000:
        return api_error('内容最多5000个字')

    row.title = title
    row.content = content
    db.session.commit()
    return api_success({'id': row.id}, msg='更新成功')


@app.route('/api/my_notes/<int:note_id>', methods=['DELETE'])
@login_required()
def delete_my_note(note_id):
    user_id = session.get('user_id')
    row = Note.query.filter_by(id=note_id, user_id=user_id).first()
    if not row:
        return api_error('笔记不存在', code=404, http_status=404)

    db.session.delete(row)
    db.session.commit()
    return api_success(msg='删除成功')


@app.route('/api/favorites', methods=['GET'])
@login_required()
def get_my_favorites():
    user_id = session.get('user_id')
    rows = Favorite.query.filter_by(user_id=user_id).order_by(Favorite.created_time.desc()).all()
    return api_success(
        [
            {
                'id': r.id,
                'fav_type': r.fav_type,
                'ref_id': r.ref_id,
                'title': r.title,
                'created_time': r.created_time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            for r in rows
        ],
        msg='查询成功',
    )


@app.route('/api/favorites', methods=['POST'])
@login_required()
def create_favorite():
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    fav_type = (data.get('fav_type') or '').strip()
    title = (data.get('title') or '').strip()
    ref_id = data.get('ref_id')

    if not fav_type or not title or ref_id is None:
        return api_error('缺少必要参数')
    try:
        ref_id = int(ref_id)
    except (TypeError, ValueError):
        return api_error('ref_id 必须为数字')

    existed = Favorite.query.filter_by(user_id=user_id, fav_type=fav_type, ref_id=ref_id).first()
    if existed:
        return api_success(
            {
                'id': existed.id,
                'fav_type': existed.fav_type,
                'ref_id': existed.ref_id,
                'title': existed.title,
                'created_time': existed.created_time.strftime('%Y-%m-%d %H:%M:%S'),
            },
            msg='已收藏',
        )

    row = Favorite(user_id=user_id, fav_type=fav_type, ref_id=ref_id, title=title)
    db.session.add(row)
    db.session.commit()
    return api_success({'id': row.id}, msg='收藏成功')


@app.route('/api/favorites/<int:favorite_id>', methods=['DELETE'])
@login_required()
def delete_favorite(favorite_id):
    user_id = session.get('user_id')
    row = Favorite.query.filter_by(id=favorite_id, user_id=user_id).first()
    if not row:
        return api_error('收藏不存在', code=404, http_status=404)

    db.session.delete(row)
    db.session.commit()
    return api_success(msg='取消收藏成功')


@app.route('/api/feedback', methods=['GET'])
@login_required()
def get_my_feedbacks():
    user_id = session.get('user_id')
    rows = Feedback.query.filter_by(user_id=user_id).order_by(Feedback.created_time.desc()).all()
    return api_success(
        [
            {
                'id': r.id,
                'content': r.content,
                'contact': r.contact,
                'status': r.status,
                'created_time': r.created_time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            for r in rows
        ],
        msg='查询成功',
    )


@app.route('/api/feedback', methods=['POST'])
@login_required()
def create_feedback():
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    contact = (data.get('contact') or '').strip()

    if len(content) < 5:
        return api_error('反馈内容至少5个字')
    if len(content) > 1000:
        return api_error('反馈内容不能超过1000字')
    if len(contact) > 120:
        return api_error('联系方式长度不能超过120')

    row = Feedback(user_id=user_id, content=content, contact=contact)
    db.session.add(row)
    db.session.commit()
    return api_success({'id': row.id}, msg='反馈提交成功')


@app.route('/api/admin/settings', methods=['GET'])
@admin_login_required
def admin_get_settings():
    return api_success(_serialize_settings_payload(), msg='查询成功')


@app.route('/api/admin/settings', methods=['POST'])
@admin_login_required
def admin_save_settings():
    data = request.get_json(silent=True) or {}

    cfg = _get_or_create_system_config()
    notify = _get_or_create_notification_config()

    cfg.repeat_submit_minutes = _to_int(data.get('repeatTime'), cfg.repeat_submit_minutes, 1, 60)
    cfg.score_min = _to_int(data.get('scoreMin'), cfg.score_min, 1, 10)
    cfg.score_max = _to_int(data.get('scoreMax'), cfg.score_max, cfg.score_min, 10)
    cfg.audit_enabled = _to_bool(data.get('auditEnabled'), cfg.audit_enabled)
    cfg.image_limit = _to_int(data.get('imgLimit'), cfg.image_limit, 1, 20)
    cfg.file_size_limit_mb = _to_int(data.get('fileSize'), cfg.file_size_limit_mb, 1, 100)
    cfg.allow_pdf = _to_bool(data.get('allowPDF'), cfg.allow_pdf)

    threshold = data.get('badReviewThreshold', cfg.bad_review_threshold)
    try:
        cfg.bad_review_threshold = min(10.0, max(0.0, float(threshold)))
    except (TypeError, ValueError):
        pass

    notify_bad_review = _extract_channels(data.get('notifyBadReview'))
    notify_audit = _extract_channels(data.get('notifyAudit'))

    notify.bad_review_site = 'site' in notify_bad_review
    notify.bad_review_email = 'email' in notify_bad_review
    notify.bad_review_sms = 'sms' in notify_bad_review
    notify.pending_audit_site = 'site' in notify_audit
    notify.pending_audit_email = 'email' in notify_audit
    notify.pending_audit_sms = 'sms' in notify_audit

    frequency = str(data.get('notifyFreq') or '').strip().lower()
    notify.frequency = frequency if frequency in ('realtime', 'hourly', 'daily') else 'realtime'

    db.session.commit()
    return api_success(_serialize_settings_payload(), msg='保存成功')


@app.route('/api/admin/settings/backups', methods=['GET'])
@admin_login_required
def admin_get_backup_list():
    return api_success({'list': _serialize_backup_records(limit=20)}, msg='查询成功')


@app.route('/api/admin/settings/notification', methods=['GET'])
@admin_login_required
def admin_get_notification_settings():
    payload = _serialize_settings_payload()
    return api_success(
        {
            'notifyBadReview': payload.get('notifyBadReview', []),
            'notifyAudit': payload.get('notifyAudit', []),
            'notifyFreq': payload.get('notifyFreq', 'realtime'),
        },
        msg='查询成功',
    )


@app.route('/api/admin/settings/notification', methods=['POST'])
@admin_login_required
def admin_save_notification_settings():
    data = request.get_json(silent=True) or {}
    notify = _get_or_create_notification_config()

    notify_bad_review = _extract_channels(data.get('notifyBadReview'))
    notify_audit = _extract_channels(data.get('notifyAudit'))
    notify.bad_review_site = 'site' in notify_bad_review
    notify.bad_review_email = 'email' in notify_bad_review
    notify.bad_review_sms = 'sms' in notify_bad_review
    notify.pending_audit_site = 'site' in notify_audit
    notify.pending_audit_email = 'email' in notify_audit
    notify.pending_audit_sms = 'sms' in notify_audit

    frequency = str(data.get('notifyFreq') or '').strip().lower()
    notify.frequency = frequency if frequency in ('realtime', 'hourly', 'daily') else notify.frequency
    db.session.commit()
    return api_success(msg='保存成功')


@app.route('/api/admin/settings/backup', methods=['POST'])
@admin_login_required
def admin_create_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    src = os.path.join(basedir, 'dining_system.db')
    if not os.path.exists(src):
        return api_error('数据库文件不存在', code=404, http_status=404)

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_name = f'dining_system_backup_{stamp}.db'
    target = os.path.join(BACKUP_DIR, file_name)
    shutil.copy2(src, target)

    size = os.path.getsize(target)
    record = BackupRecord(file_name=file_name, file_path=target, file_size=size, backup_type='manual')
    db.session.add(record)
    db.session.commit()

    return api_success(
        {
            'id': record.id,
            'file_name': record.file_name,
            'time': record.create_time.strftime('%Y-%m-%d %H:%M:%S'),
            'size': _human_file_size(record.file_size),
            'type': '手动备份',
        },
        msg='备份成功',
    )


@app.route('/api/admin/settings/repair', methods=['POST'])
@admin_login_required
def admin_repair_data():
    check_row = db.session.execute(text('PRAGMA integrity_check')).fetchone()
    integrity_text = str(check_row[0]) if check_row else 'unknown'
    if integrity_text.lower() != 'ok':
        return api_error(f'数据库完整性检查失败: {integrity_text}', code=500, http_status=500)

    db.session.execute(text('ANALYZE'))
    db.session.commit()
    return api_success({'integrity': integrity_text}, msg='检测完成，未发现异常并已优化统计信息')


@app.route('/api/admin/settings/backup/<int:backup_id>/download', methods=['GET'])
@admin_login_required
def admin_download_backup(backup_id):
    row = db.session.get(BackupRecord, backup_id)
    if not row:
        return api_error('备份记录不存在', code=404, http_status=404)
    if not os.path.exists(row.file_path):
        return api_error('备份文件不存在', code=404, http_status=404)

    return send_file(row.file_path, as_attachment=True, download_name=row.file_name)


@app.route('/api/admin/settings/test-email', methods=['POST'])
@admin_login_required
def admin_send_test_email():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip()
    if not email:
        return api_error('请填写测试邮箱')

    ok, msg = _send_smtp_mail([email], '系统设置测试邮件', '这是一封来自校园食堂点评系统的测试邮件。')
    if not ok:
        return api_error(msg)
    return api_success({'email': email}, msg=msg)


@app.route('/api/admin/settings/test-sms', methods=['POST'])
@admin_login_required
def admin_send_test_sms():
    data = request.get_json(silent=True) or {}
    phone = (data.get('phone') or '').strip()
    if not phone:
        return api_error('请填写测试手机号')

    ok, msg = _send_sms_by_gateway([phone], '系统设置测试短信', '【校园食堂点评】测试短信发送成功。', event_type='test_sms')
    if not ok:
        return api_error(msg)
    return api_success({'phone': phone}, msg=msg)


@app.route('/api/admin/notifications', methods=['GET'])
@admin_login_required
def admin_get_notifications():
    try:
        page = max(1, int(request.args.get('page', 1)))
        limit = max(1, min(100, int(request.args.get('limit', 20))))
    except (TypeError, ValueError):
        return api_error('分页参数不合法')

    keyword = (request.args.get('keyword') or '').strip()
    event_type = (request.args.get('event_type') or '').strip()
    role = (request.args.get('role') or '').strip()
    is_read_text = (request.args.get('is_read') or '').strip().lower()

    query = db.session.query(NotificationMessage, User).join(User, NotificationMessage.user_id == User.id)
    if keyword:
        fuzzy = f'%{keyword}%'
        query = query.filter(
            NotificationMessage.title.ilike(fuzzy)
            | NotificationMessage.content.ilike(fuzzy)
            | User.username.ilike(fuzzy)
            | User.nickname.ilike(fuzzy)
        )
    if event_type:
        query = query.filter(NotificationMessage.event_type == event_type)
    if role:
        query = query.filter(User.role == role)
    if is_read_text in ('0', '1', 'true', 'false'):
        query = query.filter(NotificationMessage.is_read == (is_read_text in ('1', 'true')))

    total = query.count()
    rows = (
        query.order_by(NotificationMessage.create_time.desc(), NotificationMessage.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    unread_count = db.session.query(NotificationMessage).filter(NotificationMessage.is_read == False).count()
    data = []
    for message, user in rows:
        data.append(
            {
                'id': message.id,
                'user_id': user.id,
                'username': user.username,
                'nickname': user.nickname,
                'role': user.role,
                'role_name': _role_code_to_name(user.role),
                'event_type': message.event_type,
                'channel': 'site',
                'title': message.title,
                'content': message.content,
                'is_read': bool(message.is_read),
                'create_time': message.create_time.strftime('%Y-%m-%d %H:%M:%S') if message.create_time else '-',
            }
        )

    return api_success(
        {
            'list': data,
            'total': total,
            'unread_count': unread_count,
            'page': page,
            'limit': limit,
            'pages': math.ceil(total / limit) if total else 0,
        },
        msg='查询成功',
    )


@app.route('/api/admin/notifications/<int:message_id>/read', methods=['POST'])
@admin_login_required
def admin_mark_notification_read(message_id):
    row = db.session.get(NotificationMessage, message_id)
    if not row:
        return api_error('消息不存在', code=404, http_status=404)
    row.is_read = True
    db.session.commit()
    return api_success(msg='标记成功')


@app.route('/api/admin/notifications/read_all', methods=['POST'])
@admin_login_required
def admin_mark_notification_read_all():
    role = (request.get_json(silent=True) or {}).get('role')

    query = db.session.query(NotificationMessage)
    if role:
        query = query.filter(
            NotificationMessage.user_id.in_(
                db.session.query(User.id).filter(User.role == role)
            )
        )
    updated = query.update({NotificationMessage.is_read: True}, synchronize_session=False)
    db.session.commit()
    return api_success({'updated': int(updated)}, msg='全部已读')


@app.route('/api/admin/users', methods=['GET'])
@admin_login_required
def admin_get_users():
    try:
        page = max(1, int(request.args.get('page', 1)))
        limit = max(1, min(50, int(request.args.get('limit', 10))))
    except (TypeError, ValueError):
        return api_error('分页参数不合法')

    keyword = (request.args.get('keyword') or '').strip()

    query = User.query
    if keyword:
        fuzzy = f'%{keyword}%'
        query = query.filter(
            User.username.ilike(fuzzy)
            | User.nickname.ilike(fuzzy)
            | User.phone.ilike(fuzzy)
        )

    total = query.count()
    rows = (
        query.order_by(User.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    data = []
    for item in rows:
        data.append(
            {
                'id': item.id,
                'username': item.username,
                'nickname': item.nickname,
                'phone': item.phone,
                'role': item.role,
                'role_name': _role_code_to_name(item.role),
                'create_time': item.create_time.strftime('%Y-%m-%d %H:%M:%S') if item.create_time else '-',
                'status': '启用',
            }
        )

    return api_success(
        {
            'list': data,
            'total': total,
            'page': page,
            'limit': limit,
            'pages': math.ceil(total / limit) if total else 0,
        },
        msg='查询成功',
    )


@app.route('/api/admin/users', methods=['POST'])
@admin_login_required
def admin_create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '123456').strip()
    nickname = (data.get('nickname') or '').strip()
    phone = (data.get('phone') or '').strip()
    role = _normalize_role(data.get('role_id'), data.get('role'))

    if len(username) < 2 or len(username) > 20:
        return api_error('用户名长度需在2-20位之间')
    if len(password) < 6:
        return api_error('密码长度至少6位')
    if phone and (not phone.isdigit() or len(phone) != 11):
        return api_error('手机号需为11位数字')
    if User.query.filter_by(username=username).first():
        return api_error('用户名已存在', code=409, http_status=409)

    user = User(
        username=username,
        password=generate_password_hash(password),
        nickname=nickname or None,
        phone=phone or None,
        role=role,
    )
    db.session.add(user)
    db.session.commit()
    return api_success({'id': user.id}, msg='新增成功')


@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@admin_login_required
def admin_update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return api_error('用户不存在', code=404, http_status=404)

    data = request.get_json(silent=True) or {}
    password = (data.get('password') or '').strip()
    nickname = (data.get('nickname') or '').strip()
    phone = (data.get('phone') or '').strip()
    role = _normalize_role(data.get('role_id'), data.get('role')) if ('role_id' in data or 'role' in data) else None

    if password:
        if len(password) < 6:
            return api_error('密码长度至少6位')
        user.password = generate_password_hash(password)
    if 'nickname' in data:
        if len(nickname) > 80:
            return api_error('昵称长度不能超过80个字符')
        user.nickname = nickname or None
    if 'phone' in data:
        if phone and (not phone.isdigit() or len(phone) != 11):
            return api_error('手机号需为11位数字')
        user.phone = phone or None
    if role is not None:
        user.role = role

    db.session.commit()
    return api_success(msg='更新成功')


@app.route('/api/admin/users/<int:user_id>', methods=['GET'])
@admin_login_required
def admin_get_user_detail(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return api_error('用户不存在', code=404, http_status=404)
    return api_success(
        {
            'id': user.id,
            'username': user.username,
            'nickname': user.nickname,
            'phone': user.phone,
            'role': user.role,
            'create_time': user.create_time.strftime('%Y-%m-%d %H:%M:%S') if user.create_time else '-',
        },
        msg='查询成功',
    )


@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_login_required
def admin_delete_user(user_id):
    current_user_id = session.get('user_id')
    if current_user_id == user_id:
        return api_error('不能删除当前登录账号')

    user = db.session.get(User, user_id)
    if not user:
        return api_error('用户不存在', code=404, http_status=404)

    db.session.delete(user)
    db.session.commit()
    return api_success(msg='删除成功')


@app.route('/api/admin/audit/notes', methods=['GET'])
@admin_login_required
def admin_get_audit_notes():
    try:
        page = max(1, int(request.args.get('page', 1)))
        limit = max(1, min(50, int(request.args.get('limit', 10))))
    except (TypeError, ValueError):
        return api_error('分页参数不合法')

    query = Note.query
    if request.args.get('status') not in (None, ''):
        status_text = _code_to_note_status(request.args.get('status'))
        query = query.filter(Note.status == status_text)

    total = query.count()
    rows = (
        query.order_by(Note.create_time.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    result = []
    for item in rows:
        user = db.session.get(User, item.user_id)
        result.append(
            {
                'id': item.id,
                'title': item.title,
                'content': item.content,
                'status': _note_status_to_code(item.status),
                'images': json.dumps([], ensure_ascii=False),
                'tags': json.dumps([], ensure_ascii=False),
                'user_id': item.user_id,
                'user_nickname': (user.nickname if user else '') or (user.username if user else '未知用户'),
                'create_time': item.create_time.strftime('%Y-%m-%d %H:%M:%S') if item.create_time else '-',
            }
        )

    return api_success(
        {
            'list': result,
            'total': total,
            'page': page,
            'limit': limit,
            'pages': math.ceil(total / limit) if total else 0,
        },
        msg='查询成功',
    )


@app.route('/api/admin/audit/notes/<int:note_id>', methods=['GET'])
@admin_login_required
def admin_get_audit_note_detail(note_id):
    item = db.session.get(Note, note_id)
    if not item:
        return api_error('笔记不存在', code=404, http_status=404)
    user = db.session.get(User, item.user_id)
    return api_success(
        {
            'id': item.id,
            'title': item.title,
            'content': item.content,
            'status': _note_status_to_code(item.status),
            'images': [],
            'tags': [],
            'user_id': item.user_id,
            'user_nickname': (user.nickname if user else '') or (user.username if user else '未知用户'),
            'create_time': item.create_time.strftime('%Y-%m-%d %H:%M:%S') if item.create_time else '-',
        },
        msg='查询成功',
    )


def _set_note_audit_status(note_id, status_text):
    item = db.session.get(Note, note_id)
    if not item:
        return api_error('笔记不存在', code=404, http_status=404)

    if status_text not in ('pending', 'published', 'rejected'):
        return api_error('审核状态不合法')

    item.status = status_text
    db.session.commit()
    return api_success({'id': item.id, 'status': _note_status_to_code(item.status)}, msg='审核成功')


@app.route('/api/admin/audit/notes/<int:note_id>', methods=['POST'])
@admin_login_required
def admin_update_audit_note(note_id):
    data = request.get_json(silent=True) or {}
    status_text = _code_to_note_status(data.get('status'))
    return _set_note_audit_status(note_id, status_text)


@app.route('/api/admin/audit/notes/<int:note_id>/detail', methods=['GET'])
@admin_login_required
def admin_get_audit_note_detail_alias(note_id):
    return admin_get_audit_note_detail(note_id)


@app.route('/api/admin/audit/notes/<int:note_id>/pass', methods=['POST'])
@admin_login_required
def admin_audit_note_pass(note_id):
    return _set_note_audit_status(note_id, 'published')


@app.route('/api/admin/audit/notes/<int:note_id>/reject', methods=['POST'])
@admin_login_required
def admin_audit_note_reject(note_id):
    return _set_note_audit_status(note_id, 'rejected')


@app.route('/api/admin/sensitive_words', methods=['GET'])
@admin_login_required
def admin_get_sensitive_words():
    words = SensitiveWord.query.order_by(SensitiveWord.id.asc()).all()
    rule_row = SensitiveRule.query.order_by(SensitiveRule.id.asc()).first()
    if not rule_row:
        rule_row = SensitiveRule(rule='block')
        db.session.add(rule_row)
        db.session.commit()

    return api_success(
        {
            'rule': rule_row.rule,
            'list': [
                {
                    'id': w.id,
                    'word': w.word,
                    'create_time': w.create_time.strftime('%Y-%m-%d %H:%M:%S') if w.create_time else '-',
                }
                for w in words
            ],
        },
        msg='查询成功',
    )


@app.route('/api/admin/sensitive_words', methods=['POST'])
@admin_login_required
def admin_create_sensitive_words():
    data = request.get_json(silent=True) or {}
    words = data.get('words')
    if not isinstance(words, list):
        single_word = (data.get('word') or '').strip()
        words = [single_word] if single_word else []

    cleaned_words = []
    for item in words:
        value = str(item or '').strip()
        if value and value not in cleaned_words and len(value) <= 60:
            cleaned_words.append(value)

    if not cleaned_words:
        return api_error('请提供有效敏感词')

    created = 0
    for word in cleaned_words:
        existed = SensitiveWord.query.filter_by(word=word).first()
        if existed:
            continue
        db.session.add(SensitiveWord(word=word))
        created += 1

    db.session.commit()
    return api_success({'created': created}, msg='新增成功')


@app.route('/api/admin/sensitive_words/add', methods=['POST'])
@admin_login_required
def admin_create_sensitive_words_alias():
    return admin_create_sensitive_words()


@app.route('/api/admin/sensitive_words/<int:word_id>', methods=['DELETE'])
@admin_login_required
def admin_delete_sensitive_word(word_id):
    row = db.session.get(SensitiveWord, word_id)
    if not row:
        return api_error('敏感词不存在', code=404, http_status=404)
    db.session.delete(row)
    db.session.commit()
    return api_success(msg='删除成功')


@app.route('/api/admin/sensitive_words/delete/<int:word_id>', methods=['DELETE'])
@admin_login_required
def admin_delete_sensitive_word_alias(word_id):
    return admin_delete_sensitive_word(word_id)


@app.route('/api/admin/sensitive_rule', methods=['POST'])
@admin_login_required
def admin_update_sensitive_rule():
    data = request.get_json(silent=True) or {}
    rule = (data.get('rule') or '').strip()
    if rule not in ('block', 'replace'):
        return api_error('处理规则不合法')

    row = SensitiveRule.query.order_by(SensitiveRule.id.asc()).first()
    if not row:
        row = SensitiveRule(rule=rule)
        db.session.add(row)
    else:
        row.rule = rule
    db.session.commit()
    return api_success(msg='保存成功')


@app.route('/api/admin/sensitive_config', methods=['POST'])
@admin_login_required
def admin_update_sensitive_config_alias():
    return admin_update_sensitive_rule()


@app.route('/api/admin/operator/dashboard', methods=['GET'])
@admin_login_required
def admin_operator_dashboard():
    payload = _build_operation_dashboard_payload()
    trend = payload.get('30day_score_trend', [])
    warnings = payload.get('bad_review_list', [])
    hot_dishes = payload.get('hot_dishes_top10', [])

    return api_success(
        {
            'stats': {
                'today_eval_count': payload.get('today_evaluation_count', 0),
                'week_avg_score': payload.get('week_avg_score', 0.0),
                'bad_review_count': payload.get('bad_review_count', 0),
                'note_mention_count': payload.get('note_mention_count', 0),
            },
            'trend': {
                'dates': [item.get('date', '')[5:] for item in trend],
                'food': [item.get('taste_avg', 0.0) for item in trend],
                'env': [item.get('env_avg', 0.0) for item in trend],
                'service': [item.get('service_avg', 0.0) for item in trend],
            },
            'hot_dishes': [
                {
                    'dish_id': item.get('dish_id'),
                    'dish_name': item.get('dish_name', ''),
                    'eval_count': item.get('evaluation_count', 0),
                    'avg_score': item.get('avg_score', 0.0),
                }
                for item in hot_dishes
            ],
            'warnings': [
                {
                    'id': item.get('bad_id'),
                    'score': item.get('score', 0.0),
                    'summary': item.get('content', ''),
                    'status': 'pending' if item.get('status') == '未处理' else 'handled',
                    'dish_name': item.get('dish_name', '-'),
                    'create_time': item.get('create_time', '-'),
                }
                for item in warnings
            ],
            'last_refresh_time': payload.get('last_refresh_time', '-'),
        },
        msg='查询成功',
    )


@app.route('/api/operation/dashboard', methods=['GET'])
@admin_login_required
def operation_dashboard():
    return api_success(_build_operation_dashboard_payload(), msg='查询成功')


@app.route('/api/operation/bad_reviews/<int:warning_id>/handle', methods=['POST'])
@admin_login_required
def operation_handle_bad_review(warning_id):
    row = db.session.get(OperatorWarning, warning_id)
    if not row:
        return api_error('差评预警不存在', code=404, http_status=404)
    row.status = 'handled'
    row.handler_id = session.get('user_id')
    row.handled_time = datetime.now()
    data = request.get_json(silent=True) or {}
    row.handle_note = (data.get('handle_note') or '').strip()
    db.session.commit()
    evaluation = db.session.get(EvaluationMain, row.evaluation_id) if row.evaluation_id else None
    return api_success(_serialize_bad_warning(row, evaluation), msg='处理完成')


@app.route('/api/admin/operator/dashboard/export', methods=['GET'])
@admin_login_required
def admin_operator_dashboard_export():
    _sync_operator_warnings()
    rows = OperatorWarning.query.order_by(OperatorWarning.create_time.desc()).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['预警ID', '评分', '食堂', '窗口', '菜品', '问题摘要', '状态', '创建时间', '处理时间'])
    for row in rows:
        item = _serialize_warning(row)
        writer.writerow([
            item['id'],
            item['score'],
            item['canteen_name'],
            item['window_name'],
            item['dish_name'],
            item['summary'],
            '已处理' if item['status'] == 'handled' else '待处理',
            item['create_time'],
            item['handled_time'],
        ])
    csv_content = buffer.getvalue()
    filename = f"operator_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_content,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


@app.route('/api/admin/operator/warnings/<int:warning_id>/handle', methods=['POST'])
@admin_login_required
def admin_handle_warning(warning_id):
    row = db.session.get(OperatorWarning, warning_id)
    if not row:
        return api_error('预警记录不存在', code=404, http_status=404)

    data = request.get_json(silent=True) or {}
    row.status = 'handled'
    row.handle_note = (data.get('handle_note') or '').strip()
    row.handler_id = session.get('user_id')
    row.handled_time = datetime.now()
    db.session.commit()
    return api_success(_serialize_warning(row), msg='处理完成')


@app.route('/api/admin/dishes', methods=['GET'])
@admin_login_required
def admin_get_dishes():
    try:
        page = max(1, int(request.args.get('page', 1)))
        limit = max(1, min(100, int(request.args.get('limit', 10))))
    except (TypeError, ValueError):
        return api_error('分页参数不合法')

    keyword = (request.args.get('keyword') or '').strip()
    window_id = request.args.get('window_id')
    status = (request.args.get('status') or '').strip().lower()

    query = Dish.query
    if keyword:
        fuzzy = f'%{keyword}%'
        query = query.filter(Dish.name.ilike(fuzzy))
    if window_id:
        try:
            query = query.filter(Dish.window_id == int(window_id))
        except (TypeError, ValueError):
            return api_error('window_id 参数不合法')
    if status in ('active', 'inactive'):
        query = query.filter(Dish.is_active == (status == 'active'))

    total = query.count()
    rows = query.order_by(Dish.id.desc()).offset((page - 1) * limit).limit(limit).all()
    data = []
    for dish in rows:
        eval_rows = EvaluationDish.query.filter_by(dish_id=dish.id).all()
        score_list = [_avg_dict_numeric(item.food_scores) for item in eval_rows]
        avg_score = round(sum(score_list) / len(score_list), 2) if score_list else 0.0
        dish.average_score = avg_score
        dish.review_count = len(eval_rows)
        data.append(
            {
                'id': dish.id,
                'name': dish.name,
                'window_id': dish.window_id,
                'window_name': dish.window.name if dish.window else '-',
                'price': float(dish.price or 0),
                'category': dish.category or '',
                'tags': _safe_tag_list(dish.tags_json),
                'portion': dish.portion or '',
                'img_url': dish.img_url or '',
                'is_active': bool(dish.is_active),
                'avg_score': avg_score,
                'eval_count': int(dish.review_count or 0),
                'post_count': 0,
            }
        )
    db.session.commit()

    return api_success(
        {
            'list': data,
            'total': total,
            'page': page,
            'limit': limit,
            'pages': math.ceil(total / limit) if total else 0,
        },
        msg='查询成功',
    )


@app.route('/api/admin/dishes', methods=['POST'])
@admin_login_required
def admin_create_dish():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if len(name) < 2:
        return api_error('菜品名称至少2个字')

    try:
        window_id = int(data.get('window_id'))
    except (TypeError, ValueError):
        return api_error('window_id 参数不合法')

    window = db.session.get(Window, window_id)
    if not window:
        return api_error('窗口不存在', code=404, http_status=404)

    row = Dish(
        window_id=window_id,
        name=name,
        price=float(data.get('price') or 0),
        category=(data.get('category') or '其他').strip() or '其他',
        tags_json=_safe_tag_list(data.get('tags')),
        portion=(data.get('portion') or '常规').strip() or '常规',
        img_url=(data.get('img_url') or '').strip() or None,
        is_active=_to_bool(data.get('is_active'), True),
    )
    db.session.add(row)
    db.session.commit()
    return api_success({'id': row.id}, msg='新增成功')


@app.route('/api/admin/dishes/<int:dish_id>', methods=['PUT'])
@admin_login_required
def admin_update_dish(dish_id):
    row = db.session.get(Dish, dish_id)
    if not row:
        return api_error('菜品不存在', code=404, http_status=404)

    data = request.get_json(silent=True) or {}
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if len(name) < 2:
            return api_error('菜品名称至少2个字')
        row.name = name
    if 'price' in data:
        try:
            row.price = float(data.get('price') or 0)
        except (TypeError, ValueError):
            return api_error('价格格式不正确')
    if 'category' in data:
        row.category = (data.get('category') or '').strip() or '其他'
    if 'tags' in data:
        row.tags_json = _safe_tag_list(data.get('tags'))
    if 'portion' in data:
        row.portion = (data.get('portion') or '').strip() or '常规'
    if 'img_url' in data:
        row.img_url = (data.get('img_url') or '').strip() or None
    if 'is_active' in data:
        row.is_active = _to_bool(data.get('is_active'), row.is_active)

    db.session.commit()
    return api_success(msg='更新成功')


@app.route('/api/admin/dishes/<int:dish_id>', methods=['DELETE'])
@admin_login_required
def admin_delete_dish(dish_id):
    row = db.session.get(Dish, dish_id)
    if not row:
        return api_error('菜品不存在', code=404, http_status=404)
    db.session.delete(row)
    db.session.commit()
    return api_success(msg='删除成功')


@app.route('/api/admin/dishes/<int:dish_id>/toggle', methods=['POST'])
@admin_login_required
def admin_toggle_dish_status(dish_id):
    row = db.session.get(Dish, dish_id)
    if not row:
        return api_error('菜品不存在', code=404, http_status=404)
    data = request.get_json(silent=True) or {}
    target = _to_bool(data.get('is_active'), not bool(row.is_active))
    row.is_active = target
    db.session.commit()
    return api_success({'is_active': bool(row.is_active)}, msg='状态更新成功')


@app.route('/api/admin/dishes/batch_import', methods=['POST'])
@admin_login_required
def admin_batch_import_dishes():
    rows = []
    if request.files and request.files.get('file'):
        upload = request.files['file']
        filename = (upload.filename or '').lower()
        content = upload.read().decode('utf-8-sig', errors='ignore')
        if filename.endswith('.csv'):
            reader = csv.DictReader(io.StringIO(content))
            rows = list(reader)
        elif filename.endswith('.json'):
            try:
                parsed = json.loads(content)
            except ValueError:
                return api_error('JSON 文件格式错误')
            rows = parsed if isinstance(parsed, list) else []
        else:
            return api_error('仅支持 CSV 或 JSON 文件')
    else:
        payload = request.get_json(silent=True)
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict) and isinstance(payload.get('rows'), list):
            rows = payload.get('rows')

    if not rows:
        return api_error('未检测到可导入数据')

    success_count = 0
    errors = []
    for idx, item in enumerate(rows, start=1):
        try:
            window_id = int(item.get('window_id'))
            name = (item.get('name') or '').strip()
            if len(name) < 2:
                errors.append(f'第{idx}行: 菜品名称不合法')
                continue
            window = db.session.get(Window, window_id)
            if not window:
                errors.append(f'第{idx}行: 窗口不存在 window_id={window_id}')
                continue

            row = Dish(
                window_id=window_id,
                name=name,
                price=float(item.get('price') or 0),
                category=(item.get('category') or '其他').strip() or '其他',
                tags_json=_safe_tag_list(item.get('tags')),
                portion=(item.get('portion') or '常规').strip() or '常规',
                img_url=(item.get('img_url') or '').strip() or None,
                is_active=True,
            )
            db.session.add(row)
            success_count += 1
        except Exception as exc:
            errors.append(f'第{idx}行: {exc}')

    db.session.commit()
    return api_success({'success_count': success_count, 'errors': errors}, msg='导入完成')


@app.route('/api/admin/safety/notices', methods=['GET'])
@admin_login_required
def admin_get_safety_notices():
    try:
        page = max(1, int(request.args.get('page', 1)))
        limit = max(1, min(100, int(request.args.get('limit', 10))))
    except (TypeError, ValueError):
        return api_error('分页参数不合法')

    keyword = (request.args.get('keyword') or '').strip()
    status = (request.args.get('status') or '').strip().lower()
    query = SafetyNotice.query
    if keyword:
        query = query.filter(SafetyNotice.title.ilike(f'%{keyword}%'))
    if status in ('published', 'offline'):
        query = query.filter(SafetyNotice.status == status)

    total = query.count()
    rows = query.order_by(SafetyNotice.create_time.desc()).offset((page - 1) * limit).limit(limit).all()
    data = []
    for item in rows:
        today = date.today()
        is_expired = bool(item.expire_date and item.expire_date < today)
        data.append(
            {
                'id': item.id,
                'title': item.title,
                'notice_type': item.notice_type,
                'expire_date': item.expire_date.strftime('%Y-%m-%d') if item.expire_date else '',
                'status': item.status,
                'is_expired': is_expired,
                'files': item.files_json if isinstance(item.files_json, list) else [],
                'content': item.content or '',
                'create_time': item.create_time.strftime('%Y-%m-%d %H:%M:%S') if item.create_time else '-',
            }
        )

    return api_success(
        {
            'list': data,
            'total': total,
            'page': page,
            'limit': limit,
            'pages': math.ceil(total / limit) if total else 0,
        },
        msg='查询成功',
    )


@app.route('/api/admin/safety/notices', methods=['POST'])
@admin_login_required
def admin_create_safety_notice():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if len(title) < 2:
        return api_error('公示标题至少2个字')
    files_value = data.get('files')
    files_json = files_value if isinstance(files_value, list) else []

    row = SafetyNotice(
        title=title,
        notice_type=(data.get('notice_type') or '检测报告').strip() or '检测报告',
        expire_date=_parse_date_text(data.get('expire_date')),
        status='published',
        files_json=files_json,
        content=(data.get('content') or '').strip(),
    )
    db.session.add(row)
    db.session.commit()
    return api_success({'id': row.id}, msg='新增成功')


@app.route('/api/admin/safety/notices/<int:notice_id>', methods=['PUT'])
@admin_login_required
def admin_update_safety_notice(notice_id):
    row = db.session.get(SafetyNotice, notice_id)
    if not row:
        return api_error('公示不存在', code=404, http_status=404)
    data = request.get_json(silent=True) or {}

    if 'title' in data:
        title = (data.get('title') or '').strip()
        if len(title) < 2:
            return api_error('公示标题至少2个字')
        row.title = title
    if 'notice_type' in data:
        row.notice_type = (data.get('notice_type') or '').strip() or row.notice_type
    if 'expire_date' in data:
        row.expire_date = _parse_date_text(data.get('expire_date'))
    if 'files' in data:
        row.files_json = data.get('files') if isinstance(data.get('files'), list) else []
    if 'content' in data:
        row.content = (data.get('content') or '').strip()

    db.session.commit()
    return api_success(msg='更新成功')


@app.route('/api/admin/safety/notices/<int:notice_id>/offline', methods=['POST'])
@admin_login_required
def admin_offline_safety_notice(notice_id):
    row = db.session.get(SafetyNotice, notice_id)
    if not row:
        return api_error('公示不存在', code=404, http_status=404)
    row.status = 'offline'
    db.session.commit()
    return api_success(msg='下架成功')


@app.route('/api/admin/safety/notices/<int:notice_id>/publish', methods=['POST'])
@admin_login_required
def admin_publish_safety_notice(notice_id):
    row = db.session.get(SafetyNotice, notice_id)
    if not row:
        return api_error('公示不存在', code=404, http_status=404)
    row.status = 'published'
    db.session.commit()
    return api_success(msg='上架成功')


@app.route('/api/admin/safety/notices/<int:notice_id>', methods=['DELETE'])
@admin_login_required
def admin_delete_safety_notice(notice_id):
    row = db.session.get(SafetyNotice, notice_id)
    if not row:
        return api_error('公示不存在', code=404, http_status=404)
    db.session.delete(row)
    db.session.commit()
    return api_success(msg='删除成功')


@app.route('/api/admin/safety/rectifications', methods=['GET'])
@admin_login_required
def admin_get_rectifications():
    rows = RectificationRecord.query.order_by(RectificationRecord.create_time.desc()).all()
    data = []
    for item in rows:
        warning = db.session.get(OperatorWarning, item.warning_id) if item.warning_id else None
        data.append(
            {
                'id': item.id,
                'warning_id': item.warning_id,
                'warning_score': float(warning.score or 0) if warning else 0,
                'title': item.title,
                'issue_desc': item.issue_desc,
                'action_detail': item.action_detail,
                'images': item.images_json if isinstance(item.images_json, list) else [],
                'is_public': bool(item.is_public),
                'create_time': item.create_time.strftime('%Y-%m-%d %H:%M:%S') if item.create_time else '-',
            }
        )
    return api_success({'list': data}, msg='查询成功')


@app.route('/api/admin/safety/rectifications', methods=['POST'])
@admin_login_required
def admin_create_rectification():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if len(title) < 2:
        return api_error('整改标题至少2个字')

    warning_id = data.get('warning_id')
    warning = None
    if warning_id is not None:
        try:
            warning = db.session.get(OperatorWarning, int(warning_id))
        except (TypeError, ValueError):
            return api_error('warning_id 参数不合法')
        if not warning:
            return api_error('关联预警不存在', code=404, http_status=404)

    row = RectificationRecord(
        warning_id=warning.id if warning else None,
        title=title,
        issue_desc=(data.get('issue_desc') or '').strip(),
        action_detail=(data.get('action_detail') or '').strip(),
        images_json=data.get('images') if isinstance(data.get('images'), list) else [],
        is_public=_to_bool(data.get('is_public'), False),
    )
    db.session.add(row)
    db.session.commit()
    return api_success({'id': row.id}, msg='新增成功')


@app.route('/api/admin/safety/rectifications/<int:record_id>', methods=['PUT'])
@admin_login_required
def admin_update_rectification(record_id):
    row = db.session.get(RectificationRecord, record_id)
    if not row:
        return api_error('整改记录不存在', code=404, http_status=404)
    data = request.get_json(silent=True) or {}

    if 'title' in data:
        title = (data.get('title') or '').strip()
        if len(title) < 2:
            return api_error('整改标题至少2个字')
        row.title = title
    if 'issue_desc' in data:
        row.issue_desc = (data.get('issue_desc') or '').strip()
    if 'action_detail' in data:
        row.action_detail = (data.get('action_detail') or '').strip()
    if 'images' in data:
        row.images_json = data.get('images') if isinstance(data.get('images'), list) else []
    if 'is_public' in data:
        row.is_public = _to_bool(data.get('is_public'), row.is_public)

    db.session.commit()
    return api_success(msg='更新成功')


@app.route('/api/admin/safety/rectifications/<int:record_id>', methods=['DELETE'])
@admin_login_required
def admin_delete_rectification(record_id):
    row = db.session.get(RectificationRecord, record_id)
    if not row:
        return api_error('整改记录不存在', code=404, http_status=404)
    db.session.delete(row)
    db.session.commit()
    return api_success(msg='删除成功')


@app.route('/api/admin/dish_evaluations', methods=['GET'])
@admin_login_required
def admin_get_dish_evaluations():
    try:
        page = max(1, int(request.args.get('page', 1)))
        limit = max(1, min(100, int(request.args.get('limit', 10))))
    except (TypeError, ValueError):
        return api_error('分页参数不合法')

    keyword = (request.args.get('keyword') or '').strip().lower()
    min_score = _safe_number(request.args.get('min_score'))
    max_score = _safe_number(request.args.get('max_score'))
    date_text = (request.args.get('date') or '').strip()
    target_day = _parse_date_text(date_text)

    dish_ids = db.session.query(EvaluationDish.dish_id).filter(EvaluationDish.dish_id > 0).group_by(EvaluationDish.dish_id).all()
    all_items = []
    for (dish_id,) in dish_ids:
        dish = db.session.get(Dish, dish_id)
        if not dish:
            continue
        if keyword and keyword not in (dish.name or '').lower():
            continue

        eval_rows = EvaluationDish.query.filter_by(dish_id=dish_id).all()
        score_list = [_avg_dict_numeric(item.food_scores) for item in eval_rows]
        avg_score = round(sum(score_list) / len(score_list), 2) if score_list else 0.0
        if min_score is not None and avg_score < min_score:
            continue
        if max_score is not None and avg_score > max_score:
            continue

        if target_day:
            matched = False
            for item in eval_rows:
                main = item.evaluation_main
                if main and main.create_time and main.create_time.date() == target_day:
                    matched = True
                    break
            if not matched:
                continue

        all_items.append(
            {
                'id': dish.id,
                'name': dish.name,
                'window_name': dish.window.name if dish.window else '-',
                'avg_score': avg_score,
                'eval_count': len(eval_rows),
                'post_count': 0,
            }
        )

    total = len(all_items)
    start = (page - 1) * limit
    end = start + limit
    return api_success(
        {
            'list': all_items[start:end],
            'total': total,
            'page': page,
            'limit': limit,
            'pages': math.ceil(total / limit) if total else 0,
        },
        msg='查询成功',
    )


@app.route('/api/admin/dish_evaluations/<int:dish_id>/details', methods=['GET'])
@admin_login_required
def admin_get_dish_evaluation_details(dish_id):
    dish = db.session.get(Dish, dish_id)
    if not dish:
        return api_error('菜品不存在', code=404, http_status=404)

    eval_rows = EvaluationDish.query.filter_by(dish_id=dish_id).order_by(EvaluationDish.id.desc()).all()
    data = []
    score_distribution = {'0-2': 0, '2-4': 0, '4-6': 0, '6-8': 0, '8-10': 0}
    for item in eval_rows:
        main = item.evaluation_main
        avg = _avg_dict_numeric(item.food_scores)
        if avg < 2:
            score_distribution['0-2'] += 1
        elif avg < 4:
            score_distribution['2-4'] += 1
        elif avg < 6:
            score_distribution['4-6'] += 1
        elif avg < 8:
            score_distribution['6-8'] += 1
        else:
            score_distribution['8-10'] += 1

        data.append(
            {
                'id': item.id,
                'type': 'food',
                'avg_score': avg,
                'scores': item.food_scores if isinstance(item.food_scores, dict) else {},
                'remark': item.remark or '',
                'identity': main.identity_type if main else '-',
                'create_time': main.create_time.strftime('%Y-%m-%d %H:%M:%S') if main and main.create_time else '-',
            }
        )
        if main:
            data.append(
                {
                    'id': f'env-{main.id}',
                    'type': 'env',
                    'avg_score': _avg_dict_numeric(main.env_scores),
                    'scores': main.env_scores if isinstance(main.env_scores, dict) else {},
                    'remark': main.env_comment or '',
                    'identity': main.identity_type,
                    'create_time': main.create_time.strftime('%Y-%m-%d %H:%M:%S') if main.create_time else '-',
                }
            )
            data.append(
                {
                    'id': f'service-{main.id}',
                    'type': 'service',
                    'avg_score': _avg_dict_numeric(main.service_scores),
                    'scores': main.service_scores if isinstance(main.service_scores, dict) else {},
                    'remark': main.service_comment or '',
                    'identity': main.identity_type,
                    'create_time': main.create_time.strftime('%Y-%m-%d %H:%M:%S') if main.create_time else '-',
                }
            )

    return api_success(
        {
            'dish': {'id': dish.id, 'name': dish.name},
            'list': data,
            'score_distribution': score_distribution,
        },
        msg='查询成功',
    )


@app.route('/api/admin/operator/seed_test_data', methods=['POST'])
@admin_login_required
def admin_seed_operator_test_data():
    data = request.get_json(silent=True) or {}
    force = _to_bool(data.get('force'), False)

    if force:
        OperatorWarning.query.delete()
        RectificationRecord.query.delete()
        EvaluationDish.query.delete()
        EvaluationMain.query.delete()
        Note.query.delete()
        SafetyNotice.query.delete()
        db.session.commit()

    canteen = Canteen.query.first()
    if not canteen:
        canteen = Canteen(name='第一食堂', address='校园中心区', is_active=True)
        db.session.add(canteen)
        db.session.commit()

    windows = Window.query.filter_by(canteen_id=canteen.id).all()
    if not windows:
        for name in ['川湘窗口', '面食窗口', '轻食窗口']:
            db.session.add(Window(canteen_id=canteen.id, name=name))
        db.session.commit()
        windows = Window.query.filter_by(canteen_id=canteen.id).all()

    users = User.query.filter(User.role.in_(['student', 'teacher'])).all()
    if len(users) < 6:
        for idx in range(1, 7):
            username = f'test_user_{idx}'
            existed = User.query.filter_by(username=username).first()
            if existed:
                continue
            db.session.add(
                User(
                    username=username,
                    password=generate_password_hash('123456'),
                    role='student' if idx <= 5 else 'teacher',
                    nickname=f'测试用户{idx}',
                )
            )
        db.session.commit()
        users = User.query.filter(User.role.in_(['student', 'teacher'])).all()

    hot_dish_specs = [
        ('红烧肉', '热菜', ['家常', '高蛋白']),
        ('番茄炒蛋', '热菜', ['家常', '下饭']),
        ('宫保鸡丁', '热菜', ['川味', '微辣']),
        ('鱼香肉丝', '热菜', ['川味', '经典']),
        ('麻婆豆腐', '热菜', ['川味', '麻辣']),
        ('牛肉面', '面食', ['汤面', '现煮']),
        ('酸菜鱼', '热菜', ['酸辣', '招牌']),
        ('糖醋里脊', '热菜', ['酸甜', '儿童友好']),
        ('青椒肉丝', '热菜', ['家常', '快炒']),
        ('手撕包菜', '素菜', ['清爽', '下饭']),
    ]

    dishes = []
    for idx, spec in enumerate(hot_dish_specs):
        name, category, tags = spec
        row = Dish.query.filter_by(name=name).first()
        if not row:
            row = Dish(
                window_id=windows[idx % len(windows)].id,
                name=name,
                price=round(random.uniform(9, 25), 2),
                category=category,
                tags_json=tags,
                portion='常规',
                is_active=True,
            )
            db.session.add(row)
        else:
            row.category = category
            row.tags_json = tags
            row.is_active = True
        dishes.append(row)
    db.session.commit()

    if force:
        dishes = Dish.query.filter(Dish.name.in_([item[0] for item in hot_dish_specs])).order_by(Dish.id.asc()).all()

    comments_high = [
        '口味层次丰富，出餐稳定。',
        '菜品温度和口感都很好。',
        '分量足、环境整洁，体验不错。',
    ]
    comments_low = [
        '口味偏差，环境和服务都需改进。',
        '等待时间长，菜品口感不理想。',
        '本次体验较差，建议尽快整改。',
    ]

    current_eval_count = EvaluationMain.query.count()
    need_eval = max(0, 50 - current_eval_count)
    if force:
        need_eval = 50

    for idx in range(need_eval):
        user = users[idx % len(users)]
        dish = dishes[idx % len(dishes)]
        day_offset = idx % 30
        create_at = datetime.now() - timedelta(days=day_offset, hours=(idx % 10), minutes=(idx * 7) % 60)

        is_bad = idx < 5
        if is_bad:
            taste = round(random.uniform(1.0, 2.0), 1)
            env = round(random.uniform(1.0, 2.0), 1)
            service = round(random.uniform(1.0, 2.0), 1)
            safety = round(random.uniform(1.0, 2.0), 1)
            remark_text = comments_low[idx % len(comments_low)]
        else:
            taste = round(random.uniform(6.0, 9.8), 1)
            env = round(random.uniform(6.0, 9.8), 1)
            service = round(random.uniform(6.0, 9.8), 1)
            safety = round(random.uniform(6.0, 9.8), 1)
            remark_text = comments_high[idx % len(comments_high)]

        food_scores = {
            'taste': taste,
            'color': round(max(1.0, min(10.0, taste + random.uniform(-0.8, 0.8))), 1),
            'appearance': round(max(1.0, min(10.0, taste + random.uniform(-0.8, 0.8))), 1),
            'price': round(max(1.0, min(10.0, taste + random.uniform(-1.0, 1.0))), 1),
            'portion': round(max(1.0, min(10.0, taste + random.uniform(-1.0, 1.0))), 1),
            'speed': round(max(1.0, min(10.0, service + random.uniform(-1.0, 1.0))), 1),
        }
        env_scores = {'cleanliness': env, 'comfort': round(max(1.0, min(10.0, env + random.uniform(-0.6, 0.6))), 1)}
        service_scores = {'attitude': service, 'speed': round(max(1.0, min(10.0, service + random.uniform(-0.6, 0.6))), 1)}
        safety_scores = {'hygiene': safety}
        comprehensive = round((taste + env + service) / 3, 1)

        main = EvaluationMain(
            user_id=user.id,
            canteen_id=dish.window.canteen_id,
            window_id=dish.window_id,
            buy_time=create_at,
            identity_type=user.role,
            grade='大二' if user.role == 'student' else None,
            age=20 if user.role == 'student' else 30,
            dining_years=2,
            env_scores=env_scores,
            service_scores=service_scores,
            safety_scores=safety_scores,
            service_comment=f'服务评价：{remark_text}',
            env_comment=f'环境评价：{remark_text}',
            safety_comment=f'食安评价：{remark_text}',
            comprehensive_score=comprehensive,
            remark=remark_text,
            create_time=create_at,
        )
        db.session.add(main)
        db.session.flush()

        db.session.add(
            EvaluationDish(
                evaluation_id=main.id,
                dish_id=dish.id,
                dish_name=dish.name,
                food_scores=food_scores,
                remark=f'口味/环境/服务反馈：{remark_text}',
            )
        )
    db.session.commit()

    current_note_count = Note.query.count()
    need_note = max(0, 30 - current_note_count)
    if force:
        need_note = 30

    for idx in range(need_note):
        user = users[idx % len(users)]
        dish_a = dishes[idx % len(dishes)].name
        dish_b = dishes[(idx + 3) % len(dishes)].name
        text = f"今天在{dish_a}和{dish_b}之间做了对比，口味、环境、服务三方面整体体验有差异。"
        db.session.add(
            Note(
                user_id=user.id,
                title=f'用餐记录#{idx + 1}：{dish_a}体验',
                content=text,
                status='published',
                like_count=random.randint(0, 120),
                create_time=datetime.now() - timedelta(days=idx % 30, hours=idx % 8),
            )
        )
    db.session.commit()

    if SafetyNotice.query.count() < 2:
        db.session.add(
            SafetyNotice(
                title='2026年3月食材抽检公示',
                notice_type='检测报告',
                expire_date=date.today() + timedelta(days=90),
                status='published',
                files_json=[{'name': '抽检报告.pdf', 'url': '/static/files/mock_report_202603.pdf'}],
                content='本期抽检覆盖肉类、蔬菜、餐具，结果均达标。',
            )
        )
        db.session.add(
            SafetyNotice(
                title='餐饮服务许可证公示',
                notice_type='资质证书',
                expire_date=date.today() + timedelta(days=365),
                status='published',
                files_json=[{'name': '许可证.jpg', 'url': '/static/files/mock_license_2026.jpg'}],
                content='证照信息已完成年度复核。',
            )
        )
        db.session.commit()

    bad_mains = EvaluationMain.query.filter(EvaluationMain.comprehensive_score <= 2).order_by(EvaluationMain.create_time.desc()).limit(5).all()
    existed_warning_eval_ids = {item.evaluation_id for item in OperatorWarning.query.all()}
    for main in bad_mains:
        if main.id in existed_warning_eval_ids:
            continue
        dish_eval = main.dish_evaluations[0] if main.dish_evaluations else None
        db.session.add(
            OperatorWarning(
                evaluation_id=main.id,
                canteen_id=main.canteen_id,
                window_id=main.window_id,
                dish_id=dish_eval.dish_id if dish_eval and dish_eval.dish_id else None,
                score=float(main.comprehensive_score or 0),
                summary=_first_non_empty_text(main.remark, dish_eval.remark if dish_eval else '', '低分差评待处理'),
                status='pending',
            )
        )
    db.session.commit()

    if OperatorWarning.query.filter_by(status='pending').count() > 5:
        keep_ids = [item.id for item in OperatorWarning.query.filter_by(status='pending').order_by(OperatorWarning.create_time.desc()).limit(5).all()]
        for item in OperatorWarning.query.filter_by(status='pending').all():
            if item.id not in keep_ids:
                item.status = 'handled'
                item.handle_note = 'seed 数据裁剪自动处理'
                item.handled_time = datetime.now()
        db.session.commit()

    if RectificationRecord.query.count() < 1:
        warning = OperatorWarning.query.filter_by(status='pending').order_by(OperatorWarning.create_time.desc()).first()
        db.session.add(
            RectificationRecord(
                warning_id=warning.id if warning else None,
                title='差评问题整改跟进',
                issue_desc='针对低分评价聚焦口味偏差、环境清洁和高峰服务响应。',
                action_detail='已完成厨师复训、窗口动线优化和清洁频次提升，持续监控两周。',
                images_json=['/static/img/rectify_1.jpg'],
                is_public=True,
            )
        )
        db.session.commit()

    for dish in Dish.query.all():
        eval_rows = EvaluationDish.query.filter_by(dish_id=dish.id).all()
        score_list = [_avg_dict_numeric(item.food_scores) for item in eval_rows]
        dish.review_count = len(eval_rows)
        dish.average_score = round(sum(score_list) / len(score_list), 2) if score_list else 0.0
    db.session.commit()

    return api_success(
        {
            'dish_count': Dish.query.count(),
            'evaluation_count': EvaluationMain.query.count(),
            'note_count': Note.query.count(),
            'notice_count': SafetyNotice.query.count(),
            'rectification_count': RectificationRecord.query.count(),
            'pending_warning_count': OperatorWarning.query.filter_by(status='pending').count(),
        },
        msg='运营测试数据生成完成',
    )

@app.route('/api/get_dish_evaluations', methods=['GET'])
@app.route('/api/dish_evaluations', methods=['GET'])
def get_dish_evaluations():
    dish_id = request.args.get('dish_id')
    if not dish_id:
        return api_error('缺少dish_id')
        
    # 查询关联表
    dish_evals = EvaluationDish.query.filter_by(dish_id=dish_id).all()
    
    result = []
    total_scores = {'taste': 0, 'color': 0, 'appearance': 0, 'price': 0, 'portion': 0, 'speed': 0}
    count = 0
    
    for de in dish_evals:
        # 获取主表信息以知道用户身份
        main = de.evaluation_main
        scores = de.food_scores or {}
        
        # 累加分数用于统计
        for k in total_scores.keys():
            # 有些可能是字符串，需转 float
            val = scores.get(k, 0)
            try:
                total_scores[k] += float(val)
            except:
                pass
        count += 1
        
        result.append({
            'id': de.id,
            'user_identity': main.identity_type if main else '匿名',
            'scores': scores,
            'remark': de.remark,
            'create_time': main.create_time.strftime('%Y-%m-%d') if main else ''
        })
        
    # 计算平均分
    avg_scores = {}
    if count > 0:
        for k, v in total_scores.items():
            avg_scores[k] = round(v / count, 1)
            
    return api_success({
            'list': result,
            'stats': {
                'avg_scores': avg_scores,
                'total_count': count
            }
        })


@app.route('/api/notes', methods=['GET'])
def get_notes():
    notes = (
        Note.query.filter(Note.status == 'published').order_by(Note.create_time.desc())
        .limit(20)
        .all()
    )
    result = []
    for n in notes:
        user = db.session.get(User, n.user_id)
        result.append(
            {
                'id': n.id,
                'title': n.title,
                'images': [],
                'is_anonymous': False,
                'user_id': n.user_id,
                'username': user.username if user else '用户',
                'like_count': int(n.like_count or 0),
                'remark': n.content,
                'create_time': n.create_time.strftime('%Y-%m-%d %H:%M:%S'),
            }
        )
    return api_success({'list': result}, msg='查询成功')

# --- 初始化命令 ---
@app.cli.command("init-db")
def init_db_command():
    _ensure_schema_columns()
    print("数据库表结构已创建")

if __name__ == '__main__':
    with app.app_context():
        _ensure_schema_columns()
    app.run(debug=True, port=5000)
