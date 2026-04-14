from functools import wraps
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
import csv
import io
import os
import random
import shutil
import smtplib
import ssl
import uuid
from datetime import datetime, timedelta, date
import math
import json
import re
import hashlib
import base64
import binascii
from time import perf_counter
import urllib.request
import urllib.error
from email.message import EmailMessage

from flask import Flask, request, jsonify, session, render_template, redirect, url_for, send_from_directory, send_file, Response, g
from flask_cors import CORS
from sqlalchemy import text, func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

try:
    from PIL import Image
except Exception:
    Image = None

basedir = os.path.abspath(os.path.dirname(__file__))
pages_dir = os.path.join(basedir, 'pages')
from extensions import db
from models import User, Campus, Canteen, Window, Dish, EvaluationMain, EvaluationDish, SubmitGuard, Favorite, Feedback, Note, SensitiveWord, SensitiveRule, SystemConfig, NotificationConfig, BackupRecord, NotificationDispatchLog, NotificationMessage, OperatorWarning, SafetyNotice, RectificationRecord, EvaluationTemplateVersion, EvaluationTemplateItem, AdminActionLog, EvaluationRiskFlag, RectificationWorkOrder, WorkOrderActionLog, RecommendationEvent, RecommendationAbTuning, RecommendationAbTuningLog, RecommendationAbPolicy
from seed_defaults import ensure_default_admin_operator_accounts

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
app.config['SESSION_COOKIE_NAME'] = os.getenv('SESSION_COOKIE_NAME', 'campus_dining_session')
app.config['SESSION_COOKIE_PATH'] = os.getenv('SESSION_COOKIE_PATH', '/')
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
NOTIFY_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='notify-worker')
METRIC_DICTIONARY_VERSION = '2026.03.v1'
SLA_FIRST_RESPONSE_HOURS = int(os.getenv('SLA_FIRST_RESPONSE_HOURS', '24'))
SLA_ESCALATE_HOURS = int(os.getenv('SLA_ESCALATE_HOURS', '48'))
WORK_ORDER_DEFAULT_SLA_HOURS = int(os.getenv('WORK_ORDER_DEFAULT_SLA_HOURS', '48'))
PUBLIC_MIN_ACTIVE_DISHES = int(os.getenv('PUBLIC_MIN_ACTIVE_DISHES', '10'))
PUBLIC_MIN_ORDERS = int(os.getenv('PUBLIC_MIN_ORDERS', '80'))
PUBLIC_MIN_REVIEWS = int(os.getenv('PUBLIC_MIN_REVIEWS', '40'))

DISH_IMAGE_MAX_SIZE = 2 * 1024 * 1024
DISH_IMAGE_ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'webp'}
DISH_IMAGE_ALLOWED_MIME = {'image/jpeg', 'image/png', 'image/webp'}
DISH_IMAGE_UPLOAD_DIR = os.path.join(app.static_folder, 'uploads', 'dishes')
NOTE_IMAGE_MAX_SIZE = 2 * 1024 * 1024
NOTE_IMAGE_UPLOAD_DIR = os.path.join(app.static_folder, 'uploads', 'notes')


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


@app.before_request
def _track_request_start():
    g._request_start = perf_counter()


@app.after_request
def _log_request_cost(response):
    start = getattr(g, '_request_start', None)
    if start is not None and request.path.startswith('/api/'):
        cost_ms = (perf_counter() - start) * 1000
        print(
            f"[REQ] {request.method} {request.path} status={response.status_code} cost_ms={cost_ms:.1f}",
            flush=True,
        )
    return response


def _serialize_user(user):
    canteen_name = ''
    operator_canteen_id = _safe_int(getattr(user, 'operator_canteen_id', None))
    if operator_canteen_id:
        canteen = db.session.get(Canteen, operator_canteen_id)
        canteen_name = canteen.name if canteen else ''

    campus_id = _safe_int(getattr(user, 'campus_id', 1), 1) or 1
    campus = db.session.get(Campus, campus_id)

    return {
        'id': user.id,
        'username': user.username,
        'nickname': user.nickname,
        'phone': user.phone,
        'avatar': user.avatar,
        'role': user.role,
        'operator_canteen_id': operator_canteen_id,
        'operator_canteen_name': canteen_name,
        'campus_id': campus_id,
        'campus_name': campus.name if campus else '默认校区',
    }


def _serialize_campus(row):
    return {
        'id': int(row.id or 0),
        'name': row.name or '',
        'code': row.code or '',
        'is_active': bool(row.is_active),
        'sort_order': int(row.sort_order or 0),
        'create_time': row.create_time.strftime('%Y-%m-%d %H:%M:%S') if row.create_time else '-',
    }


def _serialize_canteen(row, metrics=None):
    campus = db.session.get(Campus, _safe_int(getattr(row, 'campus_id', 1), 1) or 1)
    metrics = metrics or {}
    canteen_id = int(row.id or 0)
    return {
        'id': canteen_id,
        'campus_id': int(_safe_int(getattr(row, 'campus_id', 1), 1) or 1),
        'campus_name': campus.name if campus else '默认校区',
        'name': row.name or '',
        'address': row.address or '',
        'business_hours': row.business_hours or '07:00-21:00',
        'is_active': bool(getattr(row, 'is_active', True)),
        'window_count': int(metrics.get('window_count', 0) or 0),
        'dish_count': int(metrics.get('dish_count', 0) or 0),
        'evaluation_count': int(metrics.get('evaluation_count', 0) or 0),
        'operator_count': int(metrics.get('operator_count', 0) or 0),
        'create_time': '-',
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


def _extract_images_from_text(text):
    raw_text = str(text or '')
    images = []
    for pattern in (
        r'!\[[^\]]*\]\((https?://[^\s)]+\.(?:png|jpe?g|gif|webp)(?:\?[^\s)]*)?)\)',
        r'!\[[^\]]*\]\((/[^\s)]+\.(?:png|jpe?g|gif|webp)(?:\?[^\s)]*)?)\)',
        r'(https?://[^\s"\'<>]+\.(?:png|jpe?g|gif|webp)(?:\?[^\s"\'<>]*)?)',
        r'(/[^\s"\'<>]+\.(?:png|jpe?g|gif|webp)(?:\?[^\s"\'<>]*)?)',
        r'(data:image/(?:png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=]+)',
    ):
        matches = re.findall(pattern, raw_text, flags=re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                match = next((part for part in match if part), '')
            match = str(match).strip()
            if match and match not in images:
                images.append(match)
    return images


def _strip_images_from_text(text):
    raw_text = str(text or '')
    if 'data:image/' in raw_text and len(raw_text) > 20000:
        # 快速剔除超长 data URI，避免正则在超大文本中退化。
        chunks = []
        i = 0
        marker = 'data:image/'
        n = len(raw_text)
        stop_chars = set(' \t\r\n)"\'<>')
        while i < n:
            pos = raw_text.find(marker, i)
            if pos < 0:
                chunks.append(raw_text[i:])
                break
            chunks.append(raw_text[i:pos])
            j = pos
            while j < n and raw_text[j] not in stop_chars:
                j += 1
            chunks.append('[图片已省略]')
            i = j
        raw_text = ''.join(chunks)

    cleaned = re.sub(r'!\[[^\]]*\]\([^\s)]+\)', '', raw_text, flags=re.IGNORECASE)
    cleaned = re.sub(r'https?://[^\s"\'<>]+\.(?:png|jpe?g|gif|webp)(?:\?[^\s"\'<>]*)?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'/[^\s"\'<>]+\.(?:png|jpe?g|gif|webp)(?:\?[^\s"\'<>]*)?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'data:image/(?:png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=]+', '', cleaned, flags=re.IGNORECASE)
    lines = [line.rstrip() for line in cleaned.splitlines()]
    return '\n'.join(line for line in lines if line.strip()).strip()


def _safe_scores(score_obj):
    return score_obj if isinstance(score_obj, dict) else {}


def _safe_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_local_upload_url(url):
    prefix = '/static/uploads/dishes/'
    value = (url or '').strip()
    if not value.startswith(prefix):
        return ''
    filename = os.path.basename(value)
    if not filename:
        return ''
    return os.path.join(DISH_IMAGE_UPLOAD_DIR, filename)


def _delete_dish_image_file(image_url):
    file_path = _normalize_local_upload_url(image_url)
    if not file_path:
        return
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass


def _safe_image_extension(filename):
    safe_name = secure_filename(filename or '')
    ext = safe_name.rsplit('.', 1)[-1].lower() if '.' in safe_name else ''
    if ext == 'jpeg':
        ext = 'jpg'
    return ext


def _compress_dish_image(file_bytes, src_ext):
    if Image is None:
        return None, '服务器缺少图片处理依赖，请安装 Pillow'

    try:
        image = Image.open(io.BytesIO(file_bytes))
    except Exception:
        return None, '图片文件损坏或格式不正确'

    ext = src_ext if src_ext in {'jpg', 'png', 'webp'} else 'jpg'
    max_side = 1920
    try:
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    except Exception:
        image.thumbnail((max_side, max_side))

    if ext in {'jpg', 'webp'} and image.mode not in ('RGB', 'L'):
        image = image.convert('RGB')

    if ext == 'jpg':
        output = io.BytesIO()
        quality = 90
        while quality >= 55:
            output.seek(0)
            output.truncate(0)
            image.save(output, format='JPEG', quality=quality, optimize=True)
            if output.tell() <= DISH_IMAGE_MAX_SIZE:
                return output.getvalue(), None
            quality -= 10
        return None, '图片压缩后仍超过 2MB，请上传分辨率更小的图片'

    if ext == 'webp':
        output = io.BytesIO()
        quality = 90
        while quality >= 55:
            output.seek(0)
            output.truncate(0)
            image.save(output, format='WEBP', quality=quality, method=6)
            if output.tell() <= DISH_IMAGE_MAX_SIZE:
                return output.getvalue(), None
            quality -= 10
        return None, '图片压缩后仍超过 2MB，请上传分辨率更小的图片'

    output = io.BytesIO()
    try:
        image.save(output, format='PNG', optimize=True)
    except Exception:
        try:
            output.seek(0)
            output.truncate(0)
            image.save(output, format='PNG')
        except Exception:
            return None, 'PNG 图片处理失败'
    if output.tell() > DISH_IMAGE_MAX_SIZE:
        return None, '图片压缩后仍超过 2MB，请上传分辨率更小的图片'
    return output.getvalue(), None


def _save_dish_image_file(dish_id, image_bytes, ext):
    os.makedirs(DISH_IMAGE_UPLOAD_DIR, exist_ok=True)
    file_name = f'dish_{int(dish_id)}_{datetime.now().strftime("%Y%m%d%H%M%S")}_{uuid.uuid4().hex[:8]}.{ext}'
    file_path = os.path.join(DISH_IMAGE_UPLOAD_DIR, file_name)
    with open(file_path, 'wb') as file_obj:
        file_obj.write(image_bytes)
    return f'/static/uploads/dishes/{file_name}'


def _save_note_data_image(data_uri):
    value = str(data_uri or '').strip()
    match = re.match(r'^data:image/(png|jpe?g|webp);base64,', value, flags=re.IGNORECASE)
    if not match:
        return ''

    ext = match.group(1).lower()
    if ext == 'jpeg':
        ext = 'jpg'

    payload = value.split(',', 1)[1] if ',' in value else ''
    if not payload:
        return ''

    try:
        raw = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error):
        return ''

    if not raw or len(raw) > NOTE_IMAGE_MAX_SIZE:
        return ''

    os.makedirs(NOTE_IMAGE_UPLOAD_DIR, exist_ok=True)
    file_name = f'note_{datetime.now().strftime("%Y%m%d%H%M%S")}_{uuid.uuid4().hex[:8]}.{ext}'
    file_path = os.path.join(NOTE_IMAGE_UPLOAD_DIR, file_name)
    try:
        with open(file_path, 'wb') as file_obj:
            file_obj.write(raw)
    except Exception:
        return ''
    return f'/static/uploads/notes/{file_name}'


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


def _public_seed_required(campus_id=None):
    campus_id = _safe_int(campus_id) or _current_campus_id()
    active_dishes = (
        Dish.query.join(Window, Window.id == Dish.window_id)
        .join(Canteen, Canteen.id == Window.canteen_id)
        .filter(Dish.is_active.is_(True), Canteen.campus_id == campus_id)
        .count()
    )
    order_count = EvaluationMain.query.filter(EvaluationMain.campus_id == campus_id).count()
    review_count = (
        EvaluationDish.query.join(EvaluationMain, EvaluationMain.id == EvaluationDish.evaluation_id)
        .filter(EvaluationMain.campus_id == campus_id)
        .count()
    )
    return (
        active_dishes < PUBLIC_MIN_ACTIVE_DISHES
        or order_count < PUBLIC_MIN_ORDERS
        or review_count < PUBLIC_MIN_REVIEWS
    )


def _public_get_or_create_seed_user(campus_id=1):
    user = User.query.filter_by(username='public_seed_user').first()
    if user:
        return user

    user = User(
        username='public_seed_user',
        password=generate_password_hash('123456'),
        role='student',
        nickname='公共数据种子用户',
        campus_id=campus_id,
    )
    db.session.add(user)
    db.session.flush()
    return user


def _public_ensure_base_canteens_windows(campus_id=1):
    canteen_names = ['北区食堂', '南区食堂', '西区食堂']
    window_names = ['一号窗口', '二号窗口', '风味窗口', '面食窗口', '快餐窗口']

    canteens = Canteen.query.filter(Canteen.campus_id == campus_id).all()
    if not canteens:
        for idx, name in enumerate(canteen_names, start=1):
            db.session.add(Canteen(name=name, address=f'校园{idx}号生活区', campus_id=campus_id, is_active=True))
        db.session.flush()
        canteens = Canteen.query.filter(Canteen.campus_id == campus_id).all()

    windows = Window.query.join(Canteen, Canteen.id == Window.canteen_id).filter(Canteen.campus_id == campus_id).all()
    if not windows:
        for canteen in canteens:
            for idx in range(2):
                db.session.add(Window(canteen_id=canteen.id, name=f'{canteen.name}{window_names[idx]}'))
        db.session.flush()
        windows = Window.query.join(Canteen, Canteen.id == Window.canteen_id).filter(Canteen.campus_id == campus_id).all()

    return canteens, windows


def _public_ensure_dishes(windows, campus_id=1):
    dish_pool = [
        '红烧肉', '番茄炒蛋', '宫保鸡丁', '鱼香肉丝', '麻婆豆腐',
        '糖醋里脊', '青椒肉丝', '香菇滑鸡', '清炒时蔬', '土豆炖牛腩',
        '蒜香排骨', '鸡蛋炒饭', '西红柿牛腩', '椒盐鸡柳', '香辣鸡腿堡',
    ]

    dishes = (
        Dish.query.join(Window, Window.id == Dish.window_id)
        .join(Canteen, Canteen.id == Window.canteen_id)
        .filter(Dish.is_active.is_(True), Canteen.campus_id == campus_id)
        .all()
    )
    if len(dishes) >= 15:
        return dishes

    existing_names = {d.name for d in dishes}
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
        if len(dishes) + 1 >= 15:
            break

    db.session.flush()
    return (
        Dish.query.join(Window, Window.id == Dish.window_id)
        .join(Canteen, Canteen.id == Window.canteen_id)
        .filter(Dish.is_active.is_(True), Canteen.campus_id == campus_id)
        .all()
    )


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


def _public_seed_dashboard_data(campus_id=1):
    user = _public_get_or_create_seed_user(campus_id)
    canteens, windows = _public_ensure_base_canteens_windows(campus_id)
    dishes = _public_ensure_dishes(windows, campus_id)

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
                campus_id=campus_id,
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


def _public_ensure_seed_data_if_needed(campus_id=None):
    campus_id = _safe_int(campus_id) or _current_campus_id()
    if _public_seed_required(campus_id):
        return _public_seed_dashboard_data(campus_id)
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
    campus_exists = db.session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='campus'")
    ).fetchone()
    if not campus_exists:
        db.session.execute(
            text(
                '''
                CREATE TABLE IF NOT EXISTS campus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    code VARCHAR(50) NOT NULL UNIQUE,
                    is_active BOOLEAN DEFAULT 1,
                    sort_order INTEGER DEFAULT 0,
                    create_time DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )
        )
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
        'template_version': 'ALTER TABLE evaluation_main ADD COLUMN template_version INTEGER',
        'campus_id': 'ALTER TABLE evaluation_main ADD COLUMN campus_id INTEGER DEFAULT 1',
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
        'operator_canteen_id': 'ALTER TABLE user ADD COLUMN operator_canteen_id INTEGER',
        'campus_id': 'ALTER TABLE user ADD COLUMN campus_id INTEGER DEFAULT 1',
    }

    note_existing = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(note)')).fetchall()
    }
    note_migration_sql = {
        'campus_id': 'ALTER TABLE note ADD COLUMN campus_id INTEGER DEFAULT 1',
    }

    canteen_existing_cols = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(canteen)')).fetchall()
    }
    canteen_migration_sql = {
        'campus_id': 'ALTER TABLE canteen ADD COLUMN campus_id INTEGER DEFAULT 1',
    }

    warning_exists = db.session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='operator_warning'")
    ).fetchone()
    warning_existing = set()
    if warning_exists:
        warning_existing = {
            row[1]
            for row in db.session.execute(text('PRAGMA table_info(operator_warning)')).fetchall()
        }

    rectification_exists = db.session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='rectification_record'")
    ).fetchone()
    rectification_existing = set()
    if rectification_exists:
        rectification_existing = {
            row[1]
            for row in db.session.execute(text('PRAGMA table_info(rectification_record)')).fetchall()
        }

    action_log_exists = db.session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='admin_action_log'")
    ).fetchone()
    if action_log_exists:
        action_log_cols = {
            row[1]
            for row in db.session.execute(text('PRAGMA table_info(admin_action_log)')).fetchall()
        }
        action_log_migration_sql = {
            'before_data': "ALTER TABLE admin_action_log ADD COLUMN before_data TEXT DEFAULT ''",
            'after_data': "ALTER TABLE admin_action_log ADD COLUMN after_data TEXT DEFAULT ''",
        }
        changed_action_log = False
        for col_name, sql in action_log_migration_sql.items():
            if col_name not in action_log_cols:
                db.session.execute(text(sql))
                changed_action_log = True
        if changed_action_log:
            db.session.commit()

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
    for col_name, sql in note_migration_sql.items():
        if col_name not in note_existing:
            db.session.execute(text(sql))
            changed = True
    for col_name, sql in canteen_migration_sql.items():
        if col_name not in canteen_existing_cols:
            db.session.execute(text(sql))
            changed = True
    if warning_exists and 'campus_id' not in warning_existing:
        db.session.execute(text('ALTER TABLE operator_warning ADD COLUMN campus_id INTEGER DEFAULT 1'))
        changed = True
    if rectification_exists and 'campus_id' not in rectification_existing:
        db.session.execute(text('ALTER TABLE rectification_record ADD COLUMN campus_id INTEGER DEFAULT 1'))
        changed = True
    if changed:
        db.session.commit()

    db.session.execute(text('UPDATE user SET campus_id = 1 WHERE campus_id IS NULL OR campus_id = 0'))
    db.session.execute(text('UPDATE canteen SET campus_id = 1 WHERE campus_id IS NULL OR campus_id = 0'))
    db.session.execute(text('UPDATE note SET campus_id = 1 WHERE campus_id IS NULL OR campus_id = 0'))
    db.session.execute(text('UPDATE evaluation_main SET campus_id = 1 WHERE campus_id IS NULL OR campus_id = 0'))
    if warning_exists:
        db.session.execute(text('UPDATE operator_warning SET campus_id = 1 WHERE campus_id IS NULL OR campus_id = 0'))
    if rectification_exists:
        db.session.execute(text('UPDATE rectification_record SET campus_id = 1 WHERE campus_id IS NULL OR campus_id = 0'))
    db.session.commit()

    _ensure_default_campuses()

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
            CREATE TABLE IF NOT EXISTS recommendation_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id VARCHAR(64) DEFAULT '',
                event_type VARCHAR(20) DEFAULT 'exposure',
                variant VARCHAR(10) DEFAULT 'A',
                strategy VARCHAR(30) DEFAULT 'baseline',
                user_id INTEGER,
                campus_id INTEGER DEFAULT 1,
                canteen_id INTEGER,
                dish_id INTEGER NOT NULL,
                position INTEGER DEFAULT 0,
                page VARCHAR(30) DEFAULT 'unknown',
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP
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

    _ensure_default_template()

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


def _current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.session.get(User, user_id)


def _current_campus_id(default=1):
    session_campus_id = _safe_int(session.get('campus_id'))
    if session_campus_id:
        return session_campus_id
    user = _current_user()
    if not user:
        return default
    return _safe_int(getattr(user, 'campus_id', default), default) or default


def _resolve_campus_scope(requested_campus_id=None):
    user = _current_user()
    if not user:
        return _safe_int(requested_campus_id) or _current_campus_id(), None

    if user.role == 'admin':
        campus_id = _safe_int(requested_campus_id)
        return campus_id or None, None

    campus_id = _current_campus_id()
    if requested_campus_id and _safe_int(requested_campus_id) != campus_id:
        return None, api_error('无权访问其他校区数据', code=403, http_status=403)
    return campus_id, None


def _ensure_default_campuses():
    defaults = [
        {'name': '默认校区', 'code': 'campus-1', 'sort_order': 1},
        {'name': '南区校区', 'code': 'campus-2', 'sort_order': 2},
        {'name': '北区校区', 'code': 'campus-3', 'sort_order': 3},
    ]
    changed = False
    for item in defaults:
        row = Campus.query.filter((Campus.code == item['code']) | (Campus.name == item['name'])).first()
        if not row:
            db.session.add(
                Campus(
                    name=item['name'],
                    code=item['code'],
                    is_active=True,
                    sort_order=item['sort_order'],
                )
            )
            changed = True
    if changed:
        db.session.commit()


def _active_campus_name(campus_id=None):
    campus = db.session.get(Campus, _safe_int(campus_id, _current_campus_id()) or _current_campus_id())
    return campus.name if campus else '默认校区'


@app.route('/api/admin/campuses', methods=['GET'])
@admin_login_required
def admin_get_campuses():
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    _ensure_default_campuses()
    rows = Campus.query.order_by(Campus.sort_order.asc(), Campus.id.asc()).all()
    campus_ids = [int(row.id or 0) for row in rows if int(row.id or 0) > 0]
    canteen_count_map = {}
    canteen_name_map = {}
    if campus_ids:
        canteen_rows = (
            db.session.query(Canteen.campus_id, func.count(Canteen.id))
            .filter(Canteen.campus_id.in_(campus_ids))
            .group_by(Canteen.campus_id)
            .all()
        )
        canteen_name_rows = (
            Canteen.query
            .filter(Canteen.campus_id.in_(campus_ids))
            .order_by(Canteen.campus_id.asc(), Canteen.id.asc())
            .all()
        )
        for campus_id, count_value in canteen_rows:
            canteen_count_map[int(campus_id or 0)] = int(count_value or 0)
        for canteen in canteen_name_rows:
            key = int(canteen.campus_id or 0)
            canteen_name_map.setdefault(key, []).append(canteen.name or '')

    payload = []
    for row in rows:
        item = _serialize_campus(row)
        key = int(row.id or 0)
        canteen_names = [name for name in canteen_name_map.get(key, []) if name]
        item['canteen_count'] = int(canteen_count_map.get(key, 0))
        item['canteen_names'] = canteen_names
        item['canteen_preview'] = canteen_names[:3]
        item['canteen_preview_overflow'] = max(0, len(canteen_names) - len(item['canteen_preview']))
        payload.append(item)
    return api_success({'list': payload}, msg='查询成功')


@app.route('/api/public/campuses', methods=['GET'])
def public_get_campuses():
    _ensure_default_campuses()
    rows = Campus.query.filter(Campus.is_active.is_(True)).order_by(Campus.sort_order.asc(), Campus.id.asc()).all()
    return api_success(
        {
            'list': [_serialize_campus(row) for row in rows],
            'current_campus_id': _current_campus_id(),
            'current_campus_name': _active_campus_name(),
        },
        msg='查询成功',
    )


@app.route('/api/admin/campuses', methods=['POST'])
@admin_login_required
def admin_create_campus():
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    code = (data.get('code') or '').strip()
    if not name:
        return api_error('校区名称不能为空')
    if not code:
        return api_error('校区编码不能为空')
    if Campus.query.filter((Campus.name == name) | (Campus.code == code)).first():
        return api_error('校区名称或编码已存在')

    row = Campus(
        name=name[:100],
        code=code[:50],
        is_active=_to_bool(data.get('is_active'), True),
        sort_order=_safe_int(data.get('sort_order'), 0) or 0,
    )
    db.session.add(row)
    db.session.commit()
    return api_success(_serialize_campus(row), msg='创建成功')


@app.route('/api/admin/campuses/<int:campus_id>', methods=['PUT'])
@admin_login_required
def admin_update_campus(campus_id):
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    row = db.session.get(Campus, campus_id)
    if not row:
        return api_error('校区不存在', code=404, http_status=404)

    data = request.get_json(silent=True) or {}
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return api_error('校区名称不能为空')
        duplicate = Campus.query.filter(Campus.name == name, Campus.id != campus_id).first()
        if duplicate:
            return api_error('校区名称已存在')
        row.name = name[:100]
    if 'code' in data:
        code = (data.get('code') or '').strip()
        if not code:
            return api_error('校区编码不能为空')
        duplicate = Campus.query.filter(Campus.code == code, Campus.id != campus_id).first()
        if duplicate:
            return api_error('校区编码已存在')
        row.code = code[:50]
    if 'is_active' in data:
        row.is_active = _to_bool(data.get('is_active'), row.is_active)
    if 'sort_order' in data:
        row.sort_order = _safe_int(data.get('sort_order'), row.sort_order) or 0

    db.session.commit()
    return api_success(_serialize_campus(row), msg='更新成功')


@app.route('/api/admin/campuses/<int:campus_id>', methods=['DELETE'])
@admin_login_required
def admin_delete_campus(campus_id):
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    row = db.session.get(Campus, campus_id)
    if not row:
        return api_error('校区不存在', code=404, http_status=404)
    if campus_id == 1:
        return api_error('默认校区不允许删除')

    used = (
        db.session.query(User.id)
        .filter(User.campus_id == campus_id)
        .first()
    )
    if used:
        return api_error('该校区下还有用户，不能删除')

    db.session.delete(row)
    db.session.commit()
    return api_success(msg='删除成功')


@app.route('/api/admin/canteens', methods=['GET'])
@admin_login_required
def admin_get_canteens():
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    query = Canteen.query
    campus_id = _safe_int(request.args.get('campus_id'))
    if campus_id:
        query = query.filter(Canteen.campus_id == campus_id)

    status = (request.args.get('status') or '').strip().lower()
    if status == 'active':
        query = query.filter(Canteen.is_active.is_(True))
    elif status == 'inactive':
        query = query.filter(Canteen.is_active.is_(False))

    keyword = (request.args.get('keyword') or '').strip()
    if keyword:
        like_text = f'%{keyword}%'
        query = query.filter(
            db.or_(
                Canteen.name.ilike(like_text),
                Canteen.address.ilike(like_text),
                Canteen.business_hours.ilike(like_text),
            )
        )

    rows = query.order_by(Canteen.campus_id.asc(), Canteen.id.asc()).all()

    canteen_ids = [int(row.id or 0) for row in rows if int(row.id or 0) > 0]
    metrics_by_canteen = {}
    if canteen_ids:
        window_rows = (
            db.session.query(Window.canteen_id, func.count(Window.id))
            .filter(Window.canteen_id.in_(canteen_ids))
            .group_by(Window.canteen_id)
            .all()
        )
        dish_rows = (
            db.session.query(Window.canteen_id, func.count(Dish.id))
            .join(Dish, Dish.window_id == Window.id)
            .filter(Window.canteen_id.in_(canteen_ids))
            .group_by(Window.canteen_id)
            .all()
        )
        evaluation_rows = (
            db.session.query(EvaluationMain.canteen_id, func.count(EvaluationMain.id))
            .filter(EvaluationMain.canteen_id.in_(canteen_ids))
            .group_by(EvaluationMain.canteen_id)
            .all()
        )
        operator_rows = (
            db.session.query(User.operator_canteen_id, func.count(User.id))
            .filter(User.operator_canteen_id.in_(canteen_ids))
            .group_by(User.operator_canteen_id)
            .all()
        )

        for canteen_id, count_value in window_rows:
            key = int(canteen_id or 0)
            metrics_by_canteen.setdefault(key, {})['window_count'] = int(count_value or 0)
        for canteen_id, count_value in dish_rows:
            key = int(canteen_id or 0)
            metrics_by_canteen.setdefault(key, {})['dish_count'] = int(count_value or 0)
        for canteen_id, count_value in evaluation_rows:
            key = int(canteen_id or 0)
            metrics_by_canteen.setdefault(key, {})['evaluation_count'] = int(count_value or 0)
        for canteen_id, count_value in operator_rows:
            key = int(canteen_id or 0)
            metrics_by_canteen.setdefault(key, {})['operator_count'] = int(count_value or 0)

    data = [_serialize_canteen(row, metrics_by_canteen.get(int(row.id or 0), {})) for row in rows]
    return api_success({'list': data, 'total': len(data)}, msg='查询成功')


@app.route('/api/admin/canteens', methods=['POST'])
@admin_login_required
def admin_create_canteen():
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    address = (data.get('address') or '').strip()
    business_hours = (data.get('business_hours') or '').strip() or '07:00-21:00'
    campus_id = _safe_int(data.get('campus_id')) or 1

    if not name:
        return api_error('食堂名称不能为空')
    if not address:
        return api_error('食堂地址不能为空')
    campus = db.session.get(Campus, campus_id)
    if not campus:
        return api_error('所属校区不存在')

    duplicate = Canteen.query.filter(Canteen.campus_id == campus_id, Canteen.name == name).first()
    if duplicate:
        return api_error('同校区下食堂名称已存在')

    row = Canteen(
        campus_id=campus_id,
        name=name[:100],
        address=address[:200],
        business_hours=business_hours[:100],
        is_active=_to_bool(data.get('is_active'), True),
    )
    db.session.add(row)
    db.session.commit()
    return api_success(_serialize_canteen(row), msg='创建成功')


@app.route('/api/admin/canteens/<int:canteen_id>', methods=['PUT'])
@admin_login_required
def admin_update_canteen(canteen_id):
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    row = db.session.get(Canteen, canteen_id)
    if not row:
        return api_error('食堂不存在', code=404, http_status=404)

    data = request.get_json(silent=True) or {}
    old_campus_id = int(_safe_int(row.campus_id, 1) or 1)

    if 'campus_id' in data:
        campus_id = _safe_int(data.get('campus_id'))
        if not campus_id:
            return api_error('所属校区不能为空')
        campus = db.session.get(Campus, campus_id)
        if not campus:
            return api_error('所属校区不存在')
        row.campus_id = campus_id

    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return api_error('食堂名称不能为空')
        duplicate = Canteen.query.filter(
            Canteen.campus_id == row.campus_id,
            Canteen.name == name,
            Canteen.id != canteen_id,
        ).first()
        if duplicate:
            return api_error('同校区下食堂名称已存在')
        row.name = name[:100]

    if 'address' in data:
        address = (data.get('address') or '').strip()
        if not address:
            return api_error('食堂地址不能为空')
        row.address = address[:200]

    if 'business_hours' in data:
        business_hours = (data.get('business_hours') or '').strip() or '07:00-21:00'
        row.business_hours = business_hours[:100]

    if 'is_active' in data:
        row.is_active = _to_bool(data.get('is_active'), row.is_active)

    updated_user_count = 0
    if int(_safe_int(row.campus_id, 1) or 1) != old_campus_id:
        updated_user_count = User.query.filter(User.operator_canteen_id == row.id).update(
            {'campus_id': int(_safe_int(row.campus_id, 1) or 1)}, synchronize_session=False
        )

    db.session.commit()
    payload = _serialize_canteen(row)
    payload['updated_user_count'] = int(updated_user_count or 0)
    return api_success(payload, msg='更新成功')


def _resolve_canteen_scope(requested_canteen_id=None):
    user = _current_user()
    if not user:
        return requested_canteen_id, None

    if user.role != 'operator':
        return requested_canteen_id, None

    bound_canteen_id = _safe_int(getattr(user, 'operator_canteen_id', None))
    if not bound_canteen_id:
        return None, api_error('当前运营账号未绑定食堂，请联系管理员配置', code=403, http_status=403)

    if requested_canteen_id and requested_canteen_id != bound_canteen_id:
        return None, api_error('无权访问其他食堂数据', code=403, http_status=403)

    return bound_canteen_id, None


def _risk_level_by_score(score):
    score_value = _safe_int(score, 0) or 0
    if score_value >= 85:
        return 'critical'
    if score_value >= 70:
        return 'high'
    if score_value >= 45:
        return 'medium'
    return 'low'


def _calc_eval_risk(evaluation):
    if not evaluation:
        return 0, []

    score = 0
    reasons = []
    current_time = evaluation.create_time or datetime.now()

    recent_rows = (
        EvaluationMain.query.filter(EvaluationMain.user_id == evaluation.user_id)
        .order_by(EvaluationMain.create_time.desc(), EvaluationMain.id.desc())
        .limit(12)
        .all()
    )

    within_10m = [
        row for row in recent_rows
        if row.create_time and abs((current_time - row.create_time).total_seconds()) <= 10 * 60
    ]
    if len(within_10m) >= 3:
        score += 35
        reasons.append({'rule': 'freq_10m', 'weight': 35, 'detail': f'10分钟内提交{len(within_10m)}次'})

    if len(recent_rows) >= 2 and recent_rows[1].create_time:
        diff_seconds = abs((current_time - recent_rows[1].create_time).total_seconds())
        if diff_seconds <= 120:
            score += 20
            reasons.append({'rule': 'short_interval', 'weight': 20, 'detail': f'与上一条间隔{int(diff_seconds)}秒'})

    current_remark = (evaluation.remark or '').strip()
    if current_remark:
        max_similarity = 0.0
        for row in recent_rows[1:6]:
            prev_remark = (row.remark or '').strip()
            if not prev_remark:
                continue
            sim = SequenceMatcher(None, current_remark, prev_remark).ratio()
            max_similarity = max(max_similarity, sim)
        if max_similarity >= 0.85:
            score += 25
            reasons.append({'rule': 'text_similarity', 'weight': 25, 'detail': f'文本相似度{max_similarity:.2f}'})

    last5_scores = [float(row.comprehensive_score or 0) for row in recent_rows[:5] if row.comprehensive_score is not None]
    if len(last5_scores) >= 5:
        extreme_count = sum(1 for value in last5_scores if value <= 2.5 or value >= 9.0)
        ratio = extreme_count / len(last5_scores)
        if ratio >= 0.8:
            score += 20
            reasons.append({'rule': 'extreme_score_bias', 'weight': 20, 'detail': f'近5次极端评分占比{ratio:.0%}'})

    if evaluation.buy_time and (evaluation.buy_time.hour < 6 or evaluation.buy_time.hour >= 23):
        score += 10
        reasons.append({'rule': 'off_hours', 'weight': 10, 'detail': '非典型时段提交'})

    return min(100, score), reasons


def _upsert_eval_risk_flag(evaluation):
    if not evaluation:
        return None
    risk_score, reasons = _calc_eval_risk(evaluation)
    row = EvaluationRiskFlag.query.filter_by(evaluation_id=evaluation.id).first()
    if not row:
        row = EvaluationRiskFlag(
            campus_id=_safe_int(getattr(evaluation, 'campus_id', 1), 1) or 1,
            evaluation_id=evaluation.id,
            user_id=evaluation.user_id,
            canteen_id=evaluation.canteen_id,
            window_id=evaluation.window_id,
        )
        db.session.add(row)
    row.risk_score = risk_score
    row.risk_level = _risk_level_by_score(risk_score)
    row.rule_hits = reasons
    row.update_time = datetime.now()
    return row


def _serialize_risk_flag(row):
    evaluation = db.session.get(EvaluationMain, row.evaluation_id) if row.evaluation_id else None
    user = db.session.get(User, row.user_id) if row.user_id else None
    canteen = db.session.get(Canteen, row.canteen_id) if row.canteen_id else None
    window = db.session.get(Window, row.window_id) if row.window_id else None
    reviewer = db.session.get(User, row.reviewer_id) if row.reviewer_id else None
    return {
        'id': row.id,
        'evaluation_id': int(row.evaluation_id or 0),
        'campus_id': int(row.campus_id or 1),
        'risk_score': int(row.risk_score or 0),
        'risk_level': row.risk_level or 'low',
        'status': row.status or 'pending',
        'rule_hits': row.rule_hits if isinstance(row.rule_hits, list) else [],
        'user_id': int(row.user_id or 0),
        'username': (user.nickname if user else '') or (user.username if user else '用户'),
        'canteen_id': int(row.canteen_id or 0),
        'canteen_name': canteen.name if canteen else '-',
        'window_id': int(row.window_id or 0),
        'window_name': window.name if window else '-',
        'remark': (evaluation.remark if evaluation else '') or '',
        'comprehensive_score': float((evaluation.comprehensive_score if evaluation else 0) or 0),
        'reviewer': reviewer.username if reviewer else '',
        'review_note': row.review_note or '',
        'reviewed_time': row.reviewed_time.strftime('%Y-%m-%d %H:%M:%S') if row.reviewed_time else '',
        'create_time': row.create_time.strftime('%Y-%m-%d %H:%M:%S') if row.create_time else '-',
    }


def _serialize_work_order(row):
    canteen = db.session.get(Canteen, row.canteen_id) if row.canteen_id else None
    window = db.session.get(Window, row.window_id) if row.window_id else None
    assignee = db.session.get(User, row.assignee_id) if row.assignee_id else None
    creator = db.session.get(User, row.created_by) if row.created_by else None
    return {
        'id': row.id,
        'campus_id': int(row.campus_id or 1),
        'source_type': row.source_type,
        'source_id': int(row.source_id or 0),
        'canteen_id': int(row.canteen_id or 0),
        'canteen_name': canteen.name if canteen else '-',
        'window_id': int(row.window_id or 0),
        'window_name': window.name if window else '-',
        'title': row.title or '',
        'issue_desc': row.issue_desc or '',
        'priority': row.priority or 'medium',
        'status': row.status or 'pending',
        'assignee_id': int(row.assignee_id or 0),
        'assignee_name': (assignee.nickname if assignee else '') or (assignee.username if assignee else ''),
        'created_by': int(row.created_by or 0),
        'creator_name': (creator.nickname if creator else '') or (creator.username if creator else ''),
        'is_overdue': bool(row.is_overdue),
        'due_time': row.due_time.strftime('%Y-%m-%d %H:%M:%S') if row.due_time else '',
        'started_time': row.started_time.strftime('%Y-%m-%d %H:%M:%S') if row.started_time else '',
        'review_time': row.review_time.strftime('%Y-%m-%d %H:%M:%S') if row.review_time else '',
        'completed_time': row.completed_time.strftime('%Y-%m-%d %H:%M:%S') if row.completed_time else '',
        'archived_time': row.archived_time.strftime('%Y-%m-%d %H:%M:%S') if row.archived_time else '',
        'create_time': row.create_time.strftime('%Y-%m-%d %H:%M:%S') if row.create_time else '-',
    }


def _append_work_order_log(row, action, from_status, to_status, note=''):
    actor = _current_user()
    db.session.add(
        WorkOrderActionLog(
            work_order_id=row.id,
            campus_id=_safe_int(row.campus_id, 1) or 1,
            actor_id=actor.id if actor else None,
            action=action,
            from_status=(from_status or '')[:20],
            to_status=(to_status or '')[:20],
            note=(note or '')[:1000],
        )
    )


def _scan_work_order_sla(scoped_canteen_id=None):
    now = datetime.now()
    query = RectificationWorkOrder.query.filter(RectificationWorkOrder.status.in_(['pending', 'processing', 'review']))
    query = query.filter(RectificationWorkOrder.campus_id == _current_campus_id())
    if scoped_canteen_id:
        query = query.filter(RectificationWorkOrder.canteen_id == scoped_canteen_id)

    touched = 0
    for row in query.all():
        is_overdue = bool(row.due_time and row.due_time < now and row.status not in ('completed', 'archived'))
        if row.is_overdue != is_overdue:
            row.is_overdue = is_overdue
            row.update_time = now
            touched += 1
        if is_overdue and row.priority in ('low', 'medium'):
            row.priority = 'high'
            touched += 1
    if touched:
        db.session.commit()
    return touched


def _ensure_resource_canteen_access(resource_canteen_id):
    scoped_canteen_id, scope_error = _resolve_canteen_scope(resource_canteen_id)
    if scope_error:
        return scope_error
    if scoped_canteen_id and resource_canteen_id and scoped_canteen_id != resource_canteen_id:
        return api_error('无权操作其他食堂数据', code=403, http_status=403)
    return None


def _ensure_admin_only():
    user = _current_user()
    if not user or user.role != 'admin':
        return api_error('仅系统管理员可执行该操作', code=403, http_status=403)
    return None


def _to_json_text(payload):
    if payload is None:
        return ''
    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return json.dumps({'raw': str(payload)}, ensure_ascii=False)


def _audit_log(action, target_type='', target_id=0, detail=None, before_data=None, after_data=None):
    actor = _current_user()
    if not actor:
        return

    db.session.add(
        AdminActionLog(
            actor_id=actor.id,
            actor_role=(actor.role or '')[:20],
            action=(action or '')[:60],
            target_type=(target_type or '')[:40],
            target_id=_safe_int(target_id, 0) or 0,
            before_data=_to_json_text(before_data)[:4000],
            after_data=_to_json_text(after_data)[:4000],
            detail=_to_json_text(detail)[:4000],
        )
    )


def _serialize_action_log(row):
    actor = db.session.get(User, row.actor_id) if row.actor_id else None
    detail_obj = row.detail or ''
    if row.detail:
        try:
            detail_obj = json.loads(row.detail)
        except Exception:
            detail_obj = row.detail

    before_obj = row.before_data or ''
    if row.before_data:
        try:
            before_obj = json.loads(row.before_data)
        except Exception:
            before_obj = row.before_data

    after_obj = row.after_data or ''
    if row.after_data:
        try:
            after_obj = json.loads(row.after_data)
        except Exception:
            after_obj = row.after_data

    return {
        'id': row.id,
        'actor_id': int(row.actor_id or 0),
        'actor_name': actor.username if actor else '',
        'actor_role': row.actor_role or '',
        'action': row.action or '',
        'target_type': row.target_type or '',
        'target_id': int(row.target_id or 0),
        'before_data': before_obj,
        'after_data': after_obj,
        'detail': detail_obj,
        'create_time': row.create_time.strftime('%Y-%m-%d %H:%M:%S') if row.create_time else '-',
    }


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


def _metric_dictionary_payload(scope='all'):
    definitions = [
        {
            'metric_key': 'today_evaluation_count',
            'metric_name': '今日评价数',
            'scope': 'operation',
            'formula': '当天 create_time 计数',
            'time_window': 'day',
            'dimensions': ['canteen_id'],
            'empty_value': 0,
        },
        {
            'metric_key': 'week_avg_score',
            'metric_name': '本周平均分',
            'scope': 'operation',
            'formula': '近7天 comprehensive_score 均值',
            'time_window': 'rolling_7d',
            'dimensions': ['canteen_id'],
            'empty_value': 0.0,
        },
        {
            'metric_key': 'month_evaluation_count',
            'metric_name': '本月评价数',
            'scope': 'operation',
            'formula': '本月内 create_time 计数',
            'time_window': 'month',
            'dimensions': ['canteen_id'],
            'empty_value': 0,
        },
        {
            'metric_key': 'month_count_mom_pct',
            'metric_name': '本月评价数环比',
            'scope': 'operation',
            'formula': '(本月累计-上月同期)/上月同期*100%',
            'time_window': 'month_vs_prev_same_period',
            'dimensions': ['canteen_id'],
            'empty_value': 0.0,
        },
        {
            'metric_key': 'month_count_yoy_pct',
            'metric_name': '本月评价数同比',
            'scope': 'operation',
            'formula': '(本月累计-去年同月同期)/去年同月同期*100%',
            'time_window': 'month_vs_last_year_same_period',
            'dimensions': ['canteen_id'],
            'empty_value': 0.0,
        },
        {
            'metric_key': 'avg_score',
            'metric_name': '综合平均分',
            'scope': 'public',
            'formula': '时间范围内 comprehensive_score 均值(>0)',
            'time_window': 'range_param',
            'dimensions': ['range', 'canteen_id'],
            'empty_value': 0.0,
        },
        {
            'metric_key': 'bad_review_count',
            'metric_name': '低分评价数',
            'scope': 'public',
            'formula': 'comprehensive_score <= 2 的计数',
            'time_window': 'range_param',
            'dimensions': ['range', 'canteen_id'],
            'empty_value': 0,
        },
    ]

    if scope in ('operation', 'public'):
        definitions = [item for item in definitions if item['scope'] == scope]

    return {
        'version': METRIC_DICTIONARY_VERSION,
        'scope': scope,
        'definitions': definitions,
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


def _dispatch_event_notifications_async(event_type, ref_id, target_role, channels, title, content):
    with app.app_context():
        try:
            _dispatch_event_notifications(event_type, ref_id, target_role, channels, title, content)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning('notify_async_failed event=%s ref_id=%s err=%s', event_type, ref_id, exc)


def _enqueue_event_notifications(event_type, ref_id, target_role, channels, title, content):
    if not channels:
        return
    NOTIFY_EXECUTOR.submit(
        _dispatch_event_notifications_async,
        event_type,
        int(ref_id or 0),
        target_role,
        list(channels),
        title,
        content,
    )


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
    _enqueue_event_notifications('bad_review', evaluation.id, 'operator', channels, title, content)


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
    _enqueue_event_notifications('pending_audit', note.id, 'admin', channels, title, content)


def _warning_elapsed_hours(row, now=None):
    now_value = now or datetime.now()
    if not row or not row.create_time:
        return 0.0
    return max(0.0, (now_value - row.create_time).total_seconds() / 3600.0)


def _sla_level_by_elapsed_hours(hours_value):
    if hours_value >= float(SLA_ESCALATE_HOURS):
        return 'escalated'
    if hours_value >= float(SLA_FIRST_RESPONSE_HOURS):
        return 'overdue'
    return 'normal'


def _scan_warning_sla_and_notify(scoped_canteen_id=None):
    pending_query = OperatorWarning.query.filter(OperatorWarning.status == 'pending')
    if scoped_canteen_id:
        pending_query = pending_query.filter(OperatorWarning.canteen_id == scoped_canteen_id)
    rows = pending_query.all()

    now = datetime.now()
    for row in rows:
        elapsed = _warning_elapsed_hours(row, now=now)
        level = _sla_level_by_elapsed_hours(elapsed)
        if level == 'normal':
            continue

        channels = ['site']
        if level == 'overdue':
            title = 'SLA提醒：差评预警超时未处理'
            content = f'预警ID {row.id} 已超过 {SLA_FIRST_RESPONSE_HOURS} 小时未处理，请尽快响应。'
            _enqueue_event_notifications('warning_sla_overdue', row.id, 'operator', channels, title, content)
        else:
            title = 'SLA升级：差评预警严重超时'
            content = f'预警ID {row.id} 已超过 {SLA_ESCALATE_HOURS} 小时未处理，已升级管理员关注。'
            _enqueue_event_notifications('warning_sla_escalated', row.id, 'admin', channels, title, content)


def _parse_date_text(text_value):
    text_raw = (text_value or '').strip()
    if not text_raw:
        return None
    try:
        return datetime.strptime(text_raw, '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_datetime_text(text_value):
    text_raw = (text_value or '').strip()
    if not text_raw:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'):
        try:
            return datetime.strptime(text_raw, fmt)
        except ValueError:
            continue
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


SENTIMENT_POSITIVE_WORDS = {
    '好吃', '满意', '新鲜', '干净', '推荐', '喜欢', '稳定', '不错', '划算', '热情', '卫生',
    'friendly', 'clean', 'fresh', 'great', 'good', 'nice',
}

SENTIMENT_NEGATIVE_WORDS = {
    '难吃', '咸', '淡', '油', '慢', '冷', '差', '失望', '脏', '异味', '变质', '虫', '头发',
    '拉肚子', '吐', '不新鲜', '态度差', '贵', '踩雷',
    'bad', 'dirty', 'stale', 'slow', 'awful', 'disappointing',
}

SENTIMENT_SAFETY_RISK_WORDS = {
    '食安', '食品安全', '变质', '发霉', '异物', '虫', '头发', '未熟', '腹泻', '拉肚子', '呕吐', '发臭',
    '中毒', '过期', '不卫生', '卫生差',
}


def _clip_float(value, lower=0.0, upper=1.0):
    return max(lower, min(upper, float(value)))


def _sentiment_hit_words(text, lexicon):
    content = str(text or '').strip().lower()
    if not content:
        return []
    hits = []
    for word in lexicon:
        if word and str(word).lower() in content:
            hits.append(word)
    return hits


def _sentiment_label(score):
    if score <= 0.40:
        return 'negative'
    if score >= 0.62:
        return 'positive'
    return 'neutral'


def _sentiment_risk_level(risk_score):
    if risk_score >= 0.75:
        return 'high'
    if risk_score >= 0.45:
        return 'medium'
    return 'low'


def _analyze_sentiment_text(text):
    content = str(text or '').strip()
    if not content:
        return {
            'text_length': 0,
            'sentiment_score': 0.5,
            'label': 'neutral',
            'confidence': 0.0,
            'risk_score': 0.0,
            'risk_level': 'low',
            'keyword_hits': {'positive': [], 'negative': [], 'safety_risk': []},
        }

    positive_hits = _sentiment_hit_words(content, SENTIMENT_POSITIVE_WORDS)
    negative_hits = _sentiment_hit_words(content, SENTIMENT_NEGATIVE_WORDS)
    safety_hits = _sentiment_hit_words(content, SENTIMENT_SAFETY_RISK_WORDS)

    raw_score = 0.5 + len(positive_hits) * 0.09 - len(negative_hits) * 0.12
    if '!' in content or '！' in content:
        raw_score -= 0.03 * len(negative_hits)
        raw_score += 0.02 * len(positive_hits)

    sentiment_score = _clip_float(raw_score)
    label = _sentiment_label(sentiment_score)
    confidence = _clip_float(0.35 + 0.1 * (len(positive_hits) + len(negative_hits) + len(safety_hits)), 0.0, 0.95)

    risk_score = _clip_float(0.18 * len(safety_hits) + 0.08 * len(negative_hits))
    if label == 'negative':
        risk_score = _clip_float(risk_score + 0.15)

    return {
        'text_length': len(content),
        'sentiment_score': round(float(sentiment_score), 4),
        'label': label,
        'confidence': round(float(confidence), 4),
        'risk_score': round(float(risk_score), 4),
        'risk_level': _sentiment_risk_level(risk_score),
        'keyword_hits': {
            'positive': positive_hits[:8],
            'negative': negative_hits[:8],
            'safety_risk': safety_hits[:8],
        },
    }


def _compose_evaluation_sentiment_text(evaluation):
    if not evaluation:
        return ''

    text_blocks = [
        evaluation.remark,
        evaluation.service_comment,
        evaluation.env_comment,
        evaluation.safety_comment,
    ]
    for row in evaluation.dish_evaluations or []:
        text_blocks.append(row.remark)

    return ' '.join((str(item or '').strip() for item in text_blocks if str(item or '').strip())).strip()


def _analyze_evaluation_sentiment(evaluation):
    summary = _analyze_sentiment_text(_compose_evaluation_sentiment_text(evaluation))
    comp_score = float(getattr(evaluation, 'comprehensive_score', 0.0) or 0.0)

    if comp_score > 0:
        normalized_comp = _clip_float(comp_score / 10.0)
        summary['sentiment_score'] = round(float(_clip_float(summary['sentiment_score'] * 0.7 + normalized_comp * 0.3)), 4)
        summary['label'] = _sentiment_label(summary['sentiment_score'])
        if comp_score <= 4.0:
            summary['risk_score'] = round(float(_clip_float(summary['risk_score'] + 0.2)), 4)
            summary['risk_level'] = _sentiment_risk_level(summary['risk_score'])

    summary['comprehensive_score'] = round(comp_score, 2)
    return summary


def _build_dish_sentiment_penalty_map(campus_id, dish_ids, days=30):
    safe_dish_ids = [int(item) for item in (dish_ids or []) if _safe_int(item)]
    if not safe_dish_ids:
        return {}, {}

    start_time = datetime.now() - timedelta(days=max(3, min(90, int(days or 30))))
    rows = (
        db.session.query(EvaluationDish.dish_id, EvaluationDish.remark, EvaluationMain.remark, EvaluationMain.comprehensive_score)
        .join(EvaluationMain, EvaluationMain.id == EvaluationDish.evaluation_id)
        .filter(
            EvaluationMain.campus_id == campus_id,
            EvaluationMain.create_time >= start_time,
            EvaluationDish.dish_id.in_(safe_dish_ids),
        )
        .all()
    )

    stat_map = {}
    for dish_id, dish_remark, eval_remark, comprehensive_score in rows:
        did = int(dish_id or 0)
        if not did:
            continue
        text_payload = _first_non_empty_text(dish_remark, eval_remark)
        sentiment = _analyze_sentiment_text(text_payload)
        slot = stat_map.setdefault(did, {'total': 0, 'neg': 0, 'risk': 0.0, 'score_sum': 0.0, 'score_cnt': 0})
        slot['total'] += 1
        if sentiment['label'] == 'negative':
            slot['neg'] += 1
        slot['risk'] += float(sentiment['risk_score'] or 0.0)
        score_num = _safe_number(comprehensive_score)
        if score_num is not None:
            slot['score_sum'] += float(score_num)
            slot['score_cnt'] += 1

    penalty_map = {}
    neg_ratio_map = {}
    for dish_id in safe_dish_ids:
        item = stat_map.get(dish_id)
        if not item or item['total'] <= 0:
            continue

        neg_ratio = float(item['neg']) / float(item['total'])
        avg_risk = float(item['risk']) / float(item['total'])
        avg_score = (float(item['score_sum']) / float(item['score_cnt'])) if item['score_cnt'] else 0.0

        penalty = 0.0
        if neg_ratio > 0.35:
            penalty += (neg_ratio - 0.35) * 6.0
        penalty += max(0.0, avg_risk - 0.40) * 3.0
        if item['score_cnt'] >= 3 and avg_score < 6.0:
            penalty += (6.0 - avg_score) * 0.4

        penalty_map[dish_id] = round(float(max(0.0, penalty)), 4)
        neg_ratio_map[dish_id] = round(float(neg_ratio), 4)

    return penalty_map, neg_ratio_map


def _template_default_items():
    return [
        {'category': 'food', 'item_key': 'taste', 'item_label': '口味', 'sort_order': 10},
        {'category': 'food', 'item_key': 'color', 'item_label': '色泽', 'sort_order': 20},
        {'category': 'food', 'item_key': 'appearance', 'item_label': '品相', 'sort_order': 30},
        {'category': 'food', 'item_key': 'price', 'item_label': '价格合理', 'sort_order': 40},
        {'category': 'food', 'item_key': 'portion', 'item_label': '分量', 'sort_order': 50},
        {'category': 'food', 'item_key': 'speed', 'item_label': '出餐速度', 'sort_order': 60},
        {'category': 'service', 'item_key': 'attitude', 'item_label': '服务态度', 'sort_order': 10},
        {'category': 'service', 'item_key': 'speed', 'item_label': '响应速度', 'sort_order': 20},
        {'category': 'service', 'item_key': 'dress', 'item_label': '着装规范', 'sort_order': 30},
        {'category': 'env', 'item_key': 'clean', 'item_label': '桌面卫生', 'sort_order': 10},
        {'category': 'env', 'item_key': 'air', 'item_label': '通风空调', 'sort_order': 20},
        {'category': 'env', 'item_key': 'hygiene', 'item_label': '整体环境', 'sort_order': 30},
        {'category': 'safety', 'item_key': 'fresh', 'item_label': '食材新鲜', 'sort_order': 10},
        {'category': 'safety', 'item_key': 'info', 'item_label': '信息公示', 'sort_order': 20},
    ]


def _serialize_template(version_row):
    if not version_row:
        return {}
    items = (
        EvaluationTemplateItem.query.filter_by(version_id=version_row.id)
        .order_by(EvaluationTemplateItem.category.asc(), EvaluationTemplateItem.sort_order.asc(), EvaluationTemplateItem.id.asc())
        .all()
    )
    grouped = {'food': [], 'service': [], 'env': [], 'safety': []}
    for item in items:
        grouped.setdefault(item.category, []).append(
            {
                'id': item.id,
                'category': item.category,
                'item_key': item.item_key,
                'item_label': item.item_label,
                'sort_order': int(item.sort_order or 0),
                'score_min': int(item.score_min or 1),
                'score_max': int(item.score_max or 10),
                'enabled': bool(item.enabled),
            }
        )
    return {
        'id': version_row.id,
        'version_no': int(version_row.version_no or 1),
        'name': version_row.name,
        'status': version_row.status,
        'create_time': version_row.create_time.strftime('%Y-%m-%d %H:%M:%S') if version_row.create_time else '-',
        'publish_time': version_row.publish_time.strftime('%Y-%m-%d %H:%M:%S') if version_row.publish_time else '',
        'items': grouped,
    }


def _ensure_default_template():
    active = EvaluationTemplateVersion.query.filter_by(status='active').order_by(EvaluationTemplateVersion.version_no.desc()).first()
    if active:
        return active

    last_version = EvaluationTemplateVersion.query.order_by(EvaluationTemplateVersion.version_no.desc()).first()
    if last_version:
        last_version.status = 'active'
        last_version.publish_time = datetime.now()
        db.session.commit()
        return last_version

    row = EvaluationTemplateVersion(version_no=1, name='默认模板 v1', status='active', publish_time=datetime.now())
    db.session.add(row)
    db.session.flush()
    for item in _template_default_items():
        db.session.add(
            EvaluationTemplateItem(
                version_id=row.id,
                category=item['category'],
                item_key=item['item_key'],
                item_label=item['item_label'],
                sort_order=item['sort_order'],
                score_min=1,
                score_max=10,
                enabled=True,
            )
        )
    db.session.commit()
    return row


def _active_template_id():
    row = _ensure_default_template()
    return row.id if row else None


def _create_evaluation_from_payload(payload, user_id, enforce_repeat_guard=True):
    data = payload if isinstance(payload, dict) else {}
    canteen_id = _safe_int(data.get('canteen_id'))
    window_id = _safe_int(data.get('window_id'))
    buy_time_str = data.get('buy_time')
    identity_type = (data.get('identity_type') or '').strip() or 'student'

    if not buy_time_str:
        buy_time_str = datetime.now().strftime('%Y-%m-%dT%H:%M')

    if not all([canteen_id, window_id, buy_time_str]):
        return None, api_error('缺少必填字段')

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
        return None, api_error('请至少选择一个菜品')

    try:
        buy_time = datetime.strptime(buy_time_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        return None, api_error('时间格式错误')

    now = datetime.now()
    if enforce_repeat_guard:
        cfg = _get_or_create_system_config()
        guard_seconds = max(1, int(cfg.repeat_submit_minutes or 1)) * 60
        allow_submit, retry_after = _acquire_submit_slot(user_id, window_id, now, guard_seconds)
        if not allow_submit:
            db.session.commit()
            return None, api_error(f'提交过于频繁，请{retry_after}秒后再试', code=429, http_status=429, data={})

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
    template_version = _safe_int(data.get('template_version')) or _active_template_id()
    user_obj = db.session.get(User, user_id)
    campus_id = _safe_int(getattr(user_obj, 'campus_id', None), _current_campus_id()) or _current_campus_id()

    eval_main = EvaluationMain(
        campus_id=campus_id,
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
        remark=remark,
        template_version=template_version,
    )
    db.session.add(eval_main)
    db.session.flush()

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

    for d in dishes:
        dish_id = _safe_int(d.get('dish_id'), 0) or 0
        dish_name = (d.get('dish_name') or '').strip()
        dish_obj = db.session.get(Dish, dish_id) if dish_id else None
        if not dish_name and dish_obj:
            dish_name = dish_obj.name

        eval_dish = EvaluationDish(
            evaluation_id=eval_main.id,
            dish_id=dish_id,
            dish_name=dish_name or '未命名菜品',
            food_scores=_safe_scores(d.get('food_scores', {})),
            remark=(d.get('remark') or '').strip(),
        )
        db.session.add(eval_dish)

        if dish_obj:
            dish_obj.review_count = (dish_obj.review_count or 0) + 1

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

    _upsert_eval_risk_flag(eval_main)

    db.session.commit()
    try:
        _trigger_bad_review_notifications(eval_main.id)
    except Exception as notify_exc:
        db.session.rollback()
        app.logger.warning('bad_review_notification_failed evaluation_id=%s err=%s', eval_main.id, notify_exc)

    return {'evaluation_id': eval_main.id, 'comprehensive_score': comprehensive_score}, None


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


def _build_operation_dashboard_payload(canteen_id=None, campus_id=None):
    _sync_operator_warnings()

    now = datetime.now()
    today = now.date()
    week_begin = datetime.combine(today - timedelta(days=6), datetime.min.time())

    def _period_aggregate(begin, end):
        query = db.session.query(
            func.count(EvaluationMain.id).label('cnt'),
            func.avg(EvaluationMain.comprehensive_score).label('avg_score'),
        ).filter(EvaluationMain.create_time >= begin, EvaluationMain.create_time <= end)
        if canteen_id:
            query = query.filter(EvaluationMain.canteen_id == canteen_id)
        if campus_id:
            query = query.filter(EvaluationMain.campus_id == campus_id)
        row = query.first()
        return int((row.cnt if row else 0) or 0), float((row.avg_score if row else 0.0) or 0.0)

    def _month_bounds(year, month):
        begin = datetime(year, month, 1)
        if month == 12:
            next_begin = datetime(year + 1, 1, 1)
        else:
            next_begin = datetime(year, month + 1, 1)
        return begin, next_begin - timedelta(seconds=1)

    def _pct_change(current_value, base_value):
        base = float(base_value or 0.0)
        current = float(current_value or 0.0)
        if abs(base) < 1e-6:
            return 100.0 if current > 0 else 0.0
        return round((current - base) / base * 100, 2)

    today_query = EvaluationMain.query.filter(func.date(EvaluationMain.create_time) == str(today))
    if canteen_id:
        today_query = today_query.filter(EvaluationMain.canteen_id == canteen_id)
    if campus_id:
        today_query = today_query.filter(EvaluationMain.campus_id == campus_id)
    today_evaluation_count = today_query.count()

    week_query = db.session.query(func.avg(EvaluationMain.comprehensive_score)).filter(
        EvaluationMain.create_time >= week_begin,
        EvaluationMain.create_time <= now,
    )
    if canteen_id:
        week_query = week_query.filter(EvaluationMain.canteen_id == canteen_id)
    if campus_id:
        week_query = week_query.filter(EvaluationMain.campus_id == campus_id)
    week_avg_value = week_query.scalar()
    week_avg_score = round(float(week_avg_value or 0.0), 2)

    bad_pairs_query = (
        db.session.query(OperatorWarning, EvaluationMain)
        .join(EvaluationMain, EvaluationMain.id == OperatorWarning.evaluation_id)
        .filter(OperatorWarning.status == 'pending', func.coalesce(EvaluationMain.comprehensive_score, 0) <= 2)
        .order_by(OperatorWarning.create_time.desc())
    )
    if canteen_id:
        bad_pairs_query = bad_pairs_query.filter(OperatorWarning.canteen_id == canteen_id)
    if campus_id:
        bad_pairs_query = bad_pairs_query.filter(OperatorWarning.campus_id == campus_id)
    bad_pairs = bad_pairs_query.all()
    bad_review_count = len(bad_pairs)

    dish_name_query = Dish.query.with_entities(Dish.name)
    if canteen_id:
        dish_name_query = dish_name_query.join(Window, Window.id == Dish.window_id).filter(Window.canteen_id == canteen_id)
    if campus_id:
        dish_name_query = dish_name_query.join(Window, Window.id == Dish.window_id).join(Canteen, Canteen.id == Window.canteen_id).filter(Canteen.campus_id == campus_id)
    dish_name_list = [item.name for item in dish_name_query.all()]
    note_mention_count = _calc_note_mention_count(dish_name_list)

    current_month_begin, current_month_end = _month_bounds(now.year, now.month)
    current_month_count, current_month_avg = _period_aggregate(current_month_begin, now)

    if now.month == 1:
        prev_year, prev_month = now.year - 1, 12
    else:
        prev_year, prev_month = now.year, now.month - 1
    prev_month_begin, prev_month_end = _month_bounds(prev_year, prev_month)
    elapsed_days = (now - current_month_begin).days + 1
    prev_same_end = min(prev_month_begin + timedelta(days=elapsed_days) - timedelta(seconds=1), prev_month_end)
    prev_same_count, prev_same_avg = _period_aggregate(prev_month_begin, prev_same_end)

    yoy_begin, yoy_end_of_month = _month_bounds(now.year - 1, now.month)
    yoy_same_end = min(yoy_begin + timedelta(days=elapsed_days) - timedelta(seconds=1), yoy_end_of_month)
    yoy_same_count, yoy_same_avg = _period_aggregate(yoy_begin, yoy_same_end)

    trend_rows = []
    for offset in range(30):
        day = today - timedelta(days=29 - offset)
        begin = datetime.combine(day, datetime.min.time())
        end = datetime.combine(day, datetime.max.time())
        mains_query = EvaluationMain.query.filter(EvaluationMain.create_time >= begin, EvaluationMain.create_time <= end)
        if canteen_id:
            mains_query = mains_query.filter(EvaluationMain.canteen_id == canteen_id)
        if campus_id:
            mains_query = mains_query.filter(EvaluationMain.campus_id == campus_id)
        mains = mains_query.all()

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

    hot_query = (
        db.session.query(EvaluationDish.dish_id, func.count(EvaluationDish.id).label('eval_count'))
        .join(EvaluationMain, EvaluationMain.id == EvaluationDish.evaluation_id)
        .filter(EvaluationDish.dish_id > 0)
    )
    if canteen_id:
        hot_query = hot_query.filter(EvaluationMain.canteen_id == canteen_id)
    if campus_id:
        hot_query = hot_query.filter(EvaluationMain.campus_id == campus_id)
    hot_raw = (
        hot_query.group_by(EvaluationDish.dish_id)
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
        'metric_dictionary_version': METRIC_DICTIONARY_VERSION,
        'today_evaluation_count': int(today_evaluation_count),
        'week_avg_score': week_avg_score,
        'month_evaluation_count': int(current_month_count),
        'month_avg_score': round(current_month_avg, 2),
        'month_count_mom_pct': _pct_change(current_month_count, prev_same_count),
        'month_count_yoy_pct': _pct_change(current_month_count, yoy_same_count),
        'month_avg_mom_delta': round(current_month_avg - prev_same_avg, 2),
        'month_avg_yoy_delta': round(current_month_avg - yoy_same_avg, 2),
        'bad_review_count': int(bad_review_count),
        'note_mention_count': int(note_mention_count),
        '30day_score_trend': trend_rows,
        'hot_dishes_top10': hot_dishes_top10,
        'bad_review_list': bad_review_list,
        'canteen_id': canteen_id or 0,
        'campus_id': campus_id or 0,
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
    elapsed = _warning_elapsed_hours(row)
    sla_level = _sla_level_by_elapsed_hours(elapsed) if row.status == 'pending' else 'normal'
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
        'sla_elapsed_hours': round(elapsed, 2),
        'sla_level': sla_level,
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
    session['campus_id'] = _safe_int(getattr(user, 'campus_id', 1), 1) or 1
    session['login_nonce'] = f"{user.id}-{int(datetime.now().timestamp())}-{random.randint(1000, 9999)}"
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
    session['campus_id'] = _safe_int(getattr(user, 'campus_id', 1), 1) or 1
    session['login_nonce'] = f"{user.id}-{int(datetime.now().timestamp())}-{random.randint(1000, 9999)}"
    return api_success(_serialize_user(user), msg='登录成功')


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return api_success(msg='已退出登录')


@app.route('/api/auth/me', methods=['GET'])
@login_required()
def auth_me():
    user = db.session.get(User, session['user_id'])
    data = _serialize_user(user)
    data['session_nonce'] = session.get('login_nonce') or ''
    return api_success(data)


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
    requested_campus_id = _safe_int(request.args.get('campus_id'))
    current_user = _current_user()
    if current_user and current_user.role == 'admin':
        if requested_campus_id:
            rows = Canteen.query.filter(Canteen.campus_id == requested_campus_id).order_by(Canteen.id.asc()).all()
        else:
            rows = Canteen.query.order_by(Canteen.campus_id.asc(), Canteen.id.asc()).all()
    else:
        campus_id = _current_campus_id()
        if requested_campus_id and requested_campus_id != campus_id:
            return api_error('无权访问其他校区食堂', code=403, http_status=403)
        rows = Canteen.query.filter(Canteen.campus_id == campus_id).order_by(Canteen.id.asc()).all()
    data = [{'id': row.id, 'name': row.name} for row in rows]
    return api_success(data, msg='查询成功')


@app.route('/api/public/canteens', methods=['GET'])
def public_get_canteens():
    campus_id = _safe_int(request.args.get('campus_id')) or _current_campus_id()
    rows = Canteen.query.filter(Canteen.campus_id == campus_id, Canteen.is_active.is_(True)).order_by(Canteen.id.asc()).all()
    data = [{'id': row.id, 'name': row.name, 'campus_id': int(row.campus_id or 0)} for row in rows]
    return api_success({'list': data, 'campus_id': campus_id}, msg='查询成功')


@app.route('/api/canteens/detail', methods=['GET'])
def get_canteen_detail_by_name():
    _ensure_canteen_detail_seed_data()
    name = (request.args.get('name') or '').strip()
    campus_id = _safe_int(request.args.get('campus_id')) or _current_campus_id()
    if not name:
        return api_error('缺少食堂名称参数 name')

    row = db.session.execute(
        text(
            '''
            SELECT id, name, COALESCE(address, '') AS address,
                   COALESCE(business_hours, '07:00-21:00') AS business_hours
            FROM canteen
            WHERE name = :name AND campus_id = :campus_id
            LIMIT 1
            '''
        ),
        {'name': name, 'campus_id': campus_id},
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
                'img_url': row.img_url or '',
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
    campus_id = _safe_int(request.args.get('campus_id')) or _current_campus_id()
    seeded = _public_ensure_seed_data_if_needed(campus_id)
    canteen_id = _safe_int(request.args.get('canteen_id'))
    range_key, start_time, end_time = _public_parse_range(
        request.args.get('range') or request.args.get('period') or request.args.get('time_dimension')
    )

    base_filter = [
        EvaluationMain.buy_time >= start_time,
        EvaluationMain.buy_time <= end_time,
        EvaluationMain.campus_id == campus_id,
    ]
    if canteen_id:
        base_filter.append(EvaluationMain.canteen_id == canteen_id)
    scored_filter = base_filter + [EvaluationMain.comprehensive_score > 0]

    total_visits = db.session.query(func.count(EvaluationMain.id)).filter(*base_filter).scalar() or 0
    avg_score = db.session.query(func.avg(EvaluationMain.comprehensive_score)).filter(*scored_filter).scalar() or 0
    bad_review_count = (
        db.session.query(func.count(EvaluationMain.id))
        .filter(*scored_filter, EvaluationMain.comprehensive_score <= 2)
        .scalar()
        or 0
    )
    active_dish_count = (
        Dish.query.join(Window, Window.id == Dish.window_id)
        .join(Canteen, Canteen.id == Window.canteen_id)
        .filter(Dish.is_active.is_(True), Canteen.campus_id == campus_id)
        .count()
    )

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

    if not ranking:
        fallback_ranking_rows = (
            db.session.query(
                Canteen.id.label('canteen_id'),
                Canteen.name.label('canteen_name'),
                func.avg(Dish.average_score).label('avg_score'),
                func.sum(Dish.review_count).label('eval_count'),
            )
            .join(Window, Window.canteen_id == Canteen.id)
            .join(Dish, Dish.window_id == Window.id)
            .filter(Canteen.campus_id == campus_id, Dish.is_active.is_(True))
        )
        if canteen_id:
            fallback_ranking_rows = fallback_ranking_rows.filter(Canteen.id == canteen_id)
        ranking = [
            {
                'canteen_id': row.canteen_id,
                'canteen_name': row.canteen_name,
                'avg_score': round(float(row.avg_score or 0), 1),
                'eval_count': int(row.eval_count or 0),
            }
            for row in fallback_ranking_rows.group_by(Canteen.id, Canteen.name).order_by(func.avg(Dish.average_score).desc(), func.sum(Dish.review_count).desc()).limit(10).all()
        ]

    latest_update = db.session.query(func.max(EvaluationMain.create_time)).scalar()

    return api_success(
        {
            'metric_dictionary_version': METRIC_DICTIONARY_VERSION,
            'range': range_key,
            'campus_id': campus_id,
            'canteen_id': canteen_id or 0,
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


@app.route('/api/admin/metric_dictionary', methods=['GET'])
@admin_login_required
def admin_metric_dictionary():
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    scope = (request.args.get('scope') or 'all').strip().lower()
    if scope not in ('all', 'operation', 'public'):
        return api_error('scope 参数无效')
    return api_success(_metric_dictionary_payload(scope), msg='查询成功')


@app.route('/api/public/trend', methods=['GET'])
def public_dashboard_trend():
    campus_id = _safe_int(request.args.get('campus_id')) or _current_campus_id()
    _public_ensure_seed_data_if_needed(campus_id)
    canteen_id = _safe_int(request.args.get('canteen_id'))
    range_key, start_time, end_time = _public_parse_range(
        request.args.get('range') or request.args.get('period') or request.args.get('time_dimension')
    )

    query = EvaluationMain.query.filter(EvaluationMain.buy_time >= start_time, EvaluationMain.buy_time <= end_time, EvaluationMain.campus_id == campus_id)
    if canteen_id:
        query = query.filter(EvaluationMain.canteen_id == canteen_id)
    rows = query.order_by(EvaluationMain.buy_time.asc()).all()

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

    return api_success({'labels': labels, 'values': values, 'range': range_key, 'campus_id': campus_id, 'canteen_id': canteen_id or 0}, msg='查询成功')


@app.route('/api/public/top-dishes', methods=['GET'])
def public_dashboard_top_dishes():
    campus_id = _safe_int(request.args.get('campus_id')) or _current_campus_id()
    _public_ensure_seed_data_if_needed(campus_id)
    canteen_id = _safe_int(request.args.get('canteen_id'))
    _, start_time, end_time = _public_parse_range(
        request.args.get('range') or request.args.get('period') or request.args.get('time_dimension')
    )

    query = (
        db.session.query(
            Dish.id.label('dish_id'),
            Dish.name.label('dish_name'),
            func.count(EvaluationDish.id).label('value'),
        )
        .join(EvaluationDish, EvaluationDish.dish_id == Dish.id)
        .join(EvaluationMain, EvaluationMain.id == EvaluationDish.evaluation_id)
        .join(Window, Window.id == Dish.window_id)
        .filter(EvaluationMain.buy_time >= start_time, EvaluationMain.buy_time <= end_time, EvaluationMain.campus_id == campus_id)
    )
    if canteen_id:
        query = query.filter(Window.canteen_id == canteen_id)
    rows = (
        query.group_by(Dish.id, Dish.name)
        .order_by(func.count(EvaluationDish.id).desc(), Dish.id.asc())
        .limit(10)
        .all()
    )

    if not rows:
        fallback_query = (
            db.session.query(
                Dish.id.label('dish_id'),
                Dish.name.label('dish_name'),
                Dish.average_score.label('value'),
            )
            .join(Window, Window.id == Dish.window_id)
            .join(Canteen, Canteen.id == Window.canteen_id)
            .filter(Dish.is_active.is_(True), Canteen.campus_id == campus_id)
        )
        if canteen_id:
            fallback_query = fallback_query.filter(Canteen.id == canteen_id)
        rows = (
            fallback_query.order_by(Dish.average_score.desc(), Dish.review_count.desc(), Dish.id.asc())
            .limit(10)
            .all()
        )

    data = [{'dish_id': row.dish_id, 'name': row.dish_name, 'value': int(row.value or 0)} for row in rows]
    return api_success({'list': data, 'campus_id': campus_id, 'canteen_id': canteen_id or 0}, msg='查询成功')


@app.route('/api/public/peak-time', methods=['GET'])
def public_dashboard_peak_time():
    campus_id = _safe_int(request.args.get('campus_id')) or _current_campus_id()
    _public_ensure_seed_data_if_needed(campus_id)
    canteen_id = _safe_int(request.args.get('canteen_id'))
    _, start_time, end_time = _public_parse_range(
        request.args.get('range') or request.args.get('period') or request.args.get('time_dimension')
    )

    query = EvaluationMain.query.filter(EvaluationMain.buy_time >= start_time, EvaluationMain.buy_time <= end_time, EvaluationMain.campus_id == campus_id)
    if canteen_id:
        query = query.filter(EvaluationMain.canteen_id == canteen_id)
    rows = query.all()
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

    return api_success({'list': data, 'campus_id': campus_id, 'canteen_id': canteen_id or 0}, msg='查询成功')


def _recommendation_image_url(dish):
    if dish.img_url:
        return dish.img_url
    cover_pool = [
        '/static/img/food-hero.jpg',
        '/static/img/hero-bg.jpg',
        '/static/img/note-cover-1.svg',
        '/static/img/note-cover-2.svg',
        '/static/img/note-cover-3.svg',
        '/static/img/note-cover-4.svg',
    ]
    return cover_pool[int(dish.id or 0) % len(cover_pool)]


def _build_recommendation_profile(user):
    profile = {
        'favorite_dish_ids': set(),
        'favorite_canteen_ids': set(),
        'category_weights': {},
        'tag_weights': {},
        'canteen_weights': {},
    }
    if not user:
        return profile

    favorites = Favorite.query.filter_by(user_id=user.id).all()
    for item in favorites:
        ref_id = _safe_int(item.ref_id, 0) or 0
        if item.fav_type == 'dish' and ref_id:
            profile['favorite_dish_ids'].add(ref_id)
        elif item.fav_type == 'canteen' and ref_id:
            profile['favorite_canteen_ids'].add(ref_id)

    recent_evals = (
        EvaluationMain.query.filter_by(user_id=user.id)
        .order_by(EvaluationMain.create_time.desc(), EvaluationMain.id.desc())
        .limit(20)
        .all()
    )
    for index, evaluation in enumerate(recent_evals):
        score = float(evaluation.comprehensive_score or 0)
        if score <= 0:
            continue

        recency_factor = max(0.45, 1.0 - index * 0.04)
        delta = max(-1.5, min(2.0, (score - 5.0) / 2.0)) * recency_factor
        if not delta:
            continue

        if evaluation.canteen_id:
            profile['canteen_weights'][evaluation.canteen_id] = profile['canteen_weights'].get(evaluation.canteen_id, 0.0) + delta

        for dish_eval in evaluation.dish_evaluations:
            dish = dish_eval.dish
            if not dish:
                continue
            category_key = (dish.category or '其他').strip()
            profile['category_weights'][category_key] = profile['category_weights'].get(category_key, 0.0) + delta
            for tag in _safe_tag_list(dish.tags_json):
                profile['tag_weights'][tag] = profile['tag_weights'].get(tag, 0.0) + delta

    return profile


def _summarize_recommendation_reasons(reasons, fallback='校园热度推荐'):
    cleaned = []
    for item in reasons or []:
        text = str(item or '').strip()
        if text and text not in cleaned:
            cleaned.append(text)
    if not cleaned:
        cleaned = [fallback]
    return ' · '.join(cleaned[:2])


def _recommendation_variant_seed(user):
    user_part = str(getattr(user, 'id', 0) or 0)
    ua_part = str(getattr(request.user_agent, 'string', '') or '')[:120]
    ip_part = str(request.headers.get('X-Forwarded-For') or request.remote_addr or '')[:60]
    return f'{user_part}|{ip_part}|{ua_part}'


def _recommendation_user_segment(user):
    if not user:
        return 'anonymous'
    create_time = getattr(user, 'create_time', None)
    if create_time and (datetime.now() - create_time).days <= 14:
        return 'new'
    return 'returning'


def _normalize_recommendation_weights(policy):
    keys = ('weight_ctr', 'weight_satisfaction', 'weight_safety', 'weight_diversity')
    raw = [max(0.0, float(policy.get(key, 0.0) or 0.0)) for key in keys]
    total = sum(raw)
    if total <= 0:
        return {
            'weight_ctr': 0.4,
            'weight_satisfaction': 0.3,
            'weight_safety': 0.2,
            'weight_diversity': 0.1,
        }
    return {key: raw[index] / total for index, key in enumerate(keys)}


def _recommendation_bandit_variant(campus_id, page, user_segment, policy):
    _ensure_recommendation_event_table()
    start_time = datetime.now() - timedelta(days=30)
    query = RecommendationEvent.query.filter(
        RecommendationEvent.campus_id == campus_id,
        RecommendationEvent.create_time >= start_time,
        RecommendationEvent.page == page,
        RecommendationEvent.user_segment == user_segment,
    )
    rows = query.all()
    exposure = {'A': 0, 'B': 0}
    click = {'A': 0, 'B': 0}
    for row in rows:
        variant = (row.variant or 'A').upper()
        if variant not in ('A', 'B'):
            variant = 'A'
        if row.event_type == 'click':
            click[variant] += 1
        else:
            exposure[variant] += 1

    alpha = max(0.1, float(policy.get('bandit_alpha', 1.0) or 1.0))
    beta = max(0.1, float(policy.get('bandit_beta', 1.0) or 1.0))
    sample_a = random.betavariate(alpha + click['A'], beta + max(0, exposure['A'] - click['A']))
    sample_b = random.betavariate(alpha + click['B'], beta + max(0, exposure['B'] - click['B']))
    variant = 'A' if sample_a >= sample_b else 'B'

    # 通过蒙特卡洛近似记录策略概率，供反事实估计使用。
    wins_a = 0
    wins_b = 0
    for _ in range(40):
        draw_a = random.betavariate(alpha + click['A'], beta + max(0, exposure['A'] - click['A']))
        draw_b = random.betavariate(alpha + click['B'], beta + max(0, exposure['B'] - click['B']))
        if draw_a >= draw_b:
            wins_a += 1
        else:
            wins_b += 1
    propensity_a = wins_a / 40.0
    propensity_b = wins_b / 40.0
    propensity = propensity_a if variant == 'A' else propensity_b
    propensity = max(0.05, min(0.95, propensity))

    return variant, propensity, {
        'sample_a': round(float(sample_a), 4),
        'sample_b': round(float(sample_b), 4),
        'exposure_a': exposure['A'],
        'exposure_b': exposure['B'],
        'click_a': click['A'],
        'click_b': click['B'],
    }


def _recommendation_ab_variant(user, campus_id=None, page='unknown', policy=None):
    policy_data = policy or _default_recommendation_ab_policy()
    optimize_mode = str(policy_data.get('optimize_mode', 'ab') or 'ab').strip().lower()
    if optimize_mode == 'bandit':
        safe_campus_id = _safe_int(campus_id) or _current_campus_id()
        safe_page = (page or 'unknown').strip().lower()[:30] or 'unknown'
        user_segment = _recommendation_user_segment(user)
        variant, propensity, bandit_debug = _recommendation_bandit_variant(safe_campus_id, safe_page, user_segment, policy_data)
        return variant, propensity, user_segment, bandit_debug

    cached = session.get('recommendation_ab_variant')
    if cached in ('A', 'B'):
        return cached, 0.5, _recommendation_user_segment(user), {}

    digest = hashlib.md5(_recommendation_variant_seed(user).encode('utf-8')).hexdigest()
    value = int(digest[:8], 16)
    variant = 'A' if value % 2 == 0 else 'B'
    session['recommendation_ab_variant'] = variant
    return variant, 0.5, _recommendation_user_segment(user), {}


def _recommendation_strategy_from_variant(variant):
    return 'baseline' if variant == 'A' else 'explore'


def _extract_safety_score(safety_scores):
    score_obj = safety_scores if isinstance(safety_scores, dict) else {}
    values = []
    for _, value in score_obj.items():
        score = _safe_number(value)
        if score is not None:
            values.append(float(score))
    if not values:
        return None
    return sum(values) / len(values)


def _build_recommendation_objective_maps(campus_id, dish_ids):
    dish_ids = [int(item) for item in (dish_ids or []) if _safe_int(item)]
    if not dish_ids:
        return {}, {}, {}, {}

    start_time = datetime.now() - timedelta(days=30)
    eval_rows = (
        db.session.query(EvaluationDish.dish_id, EvaluationMain.comprehensive_score, EvaluationMain.safety_scores)
        .join(EvaluationMain, EvaluationMain.id == EvaluationDish.evaluation_id)
        .filter(
            EvaluationDish.dish_id.in_(dish_ids),
            EvaluationMain.campus_id == campus_id,
            EvaluationMain.create_time >= start_time,
        )
        .all()
    )
    sat_acc = {}
    safety_acc = {}
    for dish_id, comprehensive_score, safety_scores in eval_rows:
        did = int(dish_id or 0)
        if not did:
            continue
        sat_acc.setdefault(did, []).append(float(comprehensive_score or 0.0))
        safety_value = _extract_safety_score(safety_scores)
        if safety_value is not None:
            safety_acc.setdefault(did, []).append(float(safety_value))

    satisfaction_map = {did: max(0.0, min(1.0, (sum(values) / len(values)) / 10.0)) for did, values in sat_acc.items() if values}
    safety_map = {did: max(0.0, min(1.0, (sum(values) / len(values)) / 10.0)) for did, values in safety_acc.items() if values}

    exposure_rows = (
        db.session.query(RecommendationEvent.dish_id, func.count(RecommendationEvent.id))
        .filter(
            RecommendationEvent.campus_id == campus_id,
            RecommendationEvent.event_type == 'exposure',
            RecommendationEvent.create_time >= (datetime.now() - timedelta(days=14)),
            RecommendationEvent.dish_id.in_(dish_ids),
        )
        .group_by(RecommendationEvent.dish_id)
        .all()
    )
    exposure_map = {int(did or 0): int(cnt or 0) for did, cnt in exposure_rows}
    max_exposure = max(exposure_map.values()) if exposure_map else 1
    diversity_map = {}
    for did in dish_ids:
        exp_count = exposure_map.get(did, 0)
        diversity_map[did] = max(0.0, min(1.0, 1.0 - (exp_count / max_exposure if max_exposure > 0 else 0.0)))

    canteen_rows = (
        db.session.query(RecommendationEvent.canteen_id, func.count(RecommendationEvent.id))
        .filter(
            RecommendationEvent.campus_id == campus_id,
            RecommendationEvent.event_type == 'exposure',
            RecommendationEvent.create_time >= (datetime.now() - timedelta(days=14)),
        )
        .group_by(RecommendationEvent.canteen_id)
        .all()
    )
    total_exposure = sum(int(cnt or 0) for _, cnt in canteen_rows)
    canteen_share_map = {}
    if total_exposure > 0:
        for cid, cnt in canteen_rows:
            if cid:
                canteen_share_map[int(cid)] = float(cnt or 0) / total_exposure

    return satisfaction_map, safety_map, diversity_map, canteen_share_map


def _recommendation_segmented_significance(rows, segment_by='page'):
    segment_by = (segment_by or 'page').strip().lower()
    if segment_by not in ('page', 'user_segment', 'canteen'):
        segment_by = 'page'

    bucket = {}
    for row in rows or []:
        variant = (row.variant or 'A').upper()
        if variant not in ('A', 'B'):
            variant = 'A'
        if segment_by == 'user_segment':
            key = (row.user_segment or ('returning' if row.user_id else 'anonymous')).strip().lower() or 'unknown'
        elif segment_by == 'canteen':
            key = str(_safe_int(row.canteen_id, 0) or 0)
        else:
            key = (row.page or 'unknown').strip().lower() or 'unknown'

        if key not in bucket:
            bucket[key] = {
                'A': {'exposure': 0, 'click': 0},
                'B': {'exposure': 0, 'click': 0},
            }
        if row.event_type == 'click':
            bucket[key][variant]['click'] += 1
        else:
            bucket[key][variant]['exposure'] += 1

    result = []
    for key, pair in bucket.items():
        a_exp = int(pair['A']['exposure'])
        b_exp = int(pair['B']['exposure'])
        a_clk = int(pair['A']['click'])
        b_clk = int(pair['B']['click'])
        significance = _recommendation_ctr_significance(a_clk, a_exp, b_clk, b_exp)
        result.append(
            {
                'segment': key,
                'variant_a': {'exposure': a_exp, 'click': a_clk, 'ctr': round((a_clk * 100.0 / a_exp), 2) if a_exp else 0.0},
                'variant_b': {'exposure': b_exp, 'click': b_clk, 'ctr': round((b_clk * 100.0 / b_exp), 2) if b_exp else 0.0},
                'significance': significance,
            }
        )
    result.sort(key=lambda item: (item['variant_a']['exposure'] + item['variant_b']['exposure']), reverse=True)
    return result


def _recommendation_counterfactual_ips_dr(campus_id, days=7, page='', target_strategy='explore'):
    _ensure_recommendation_event_table()
    start_time = datetime.now() - timedelta(days=max(1, min(60, int(days))))
    target_strategy = 'baseline' if str(target_strategy or '').strip().lower() == 'baseline' else 'explore'

    query = RecommendationEvent.query.filter(
        RecommendationEvent.campus_id == campus_id,
        RecommendationEvent.create_time >= start_time,
        RecommendationEvent.event_type == 'exposure',
    )
    if page:
        query = query.filter(RecommendationEvent.page == page)
    exposures = query.all()

    if not exposures:
        return {
            'sample_size': 0,
            'target_strategy': target_strategy,
            'ips': 0.0,
            'dr': 0.0,
            'baseline_reward_model': {'baseline': 0.0, 'explore': 0.0},
            'note': '样本不足',
        }

    click_rows = RecommendationEvent.query.filter(
        RecommendationEvent.campus_id == campus_id,
        RecommendationEvent.create_time >= start_time,
        RecommendationEvent.event_type == 'click',
    )
    if page:
        click_rows = click_rows.filter(RecommendationEvent.page == page)
    click_rows = click_rows.all()
    click_set = set()
    for row in click_rows:
        click_set.add(
            (
                row.request_id or '',
                int(row.dish_id or 0),
                int(row.user_id or 0),
                (row.page or 'unknown').strip().lower(),
            )
        )

    reward_sum = {'baseline': 0.0, 'explore': 0.0}
    reward_cnt = {'baseline': 0, 'explore': 0}
    for row in exposures:
        strategy = (row.strategy or _recommendation_strategy_from_variant((row.variant or 'A').upper())).strip().lower()
        strategy = 'baseline' if strategy == 'baseline' else 'explore'
        reward = 1.0 if (
            (
                row.request_id or '',
                int(row.dish_id or 0),
                int(row.user_id or 0),
                (row.page or 'unknown').strip().lower(),
            ) in click_set
        ) else 0.0
        reward_sum[strategy] += reward
        reward_cnt[strategy] += 1

    q_hat = {
        'baseline': (reward_sum['baseline'] / reward_cnt['baseline']) if reward_cnt['baseline'] else 0.0,
        'explore': (reward_sum['explore'] / reward_cnt['explore']) if reward_cnt['explore'] else 0.0,
    }

    ips_sum = 0.0
    dr_sum = 0.0
    for row in exposures:
        strategy = (row.strategy or _recommendation_strategy_from_variant((row.variant or 'A').upper())).strip().lower()
        strategy = 'baseline' if strategy == 'baseline' else 'explore'
        propensity = max(0.05, min(0.95, float(_safe_number(getattr(row, 'propensity', 0.5)) if _safe_number(getattr(row, 'propensity', 0.5)) is not None else 0.5)))
        reward = 1.0 if (
            (
                row.request_id or '',
                int(row.dish_id or 0),
                int(row.user_id or 0),
                (row.page or 'unknown').strip().lower(),
            ) in click_set
        ) else 0.0
        indicator = 1.0 if strategy == target_strategy else 0.0
        ips_sum += indicator * reward / propensity
        dr_sum += q_hat[target_strategy] + indicator * (reward - q_hat[strategy]) / propensity

    sample_size = len(exposures)
    return {
        'sample_size': sample_size,
        'target_strategy': target_strategy,
        'ips': round(float(ips_sum / sample_size), 6),
        'dr': round(float(dr_sum / sample_size), 6),
        'baseline_reward_model': {
            'baseline': round(float(q_hat['baseline']), 6),
            'explore': round(float(q_hat['explore']), 6),
        },
        'note': '采用日志概率(propensity)进行IPS/DR估计',
    }


def _recommendation_request_id(user, campus_id):
    user_id = _safe_int(getattr(user, 'id', 0), 0) or 0
    now_key = datetime.now().strftime('%Y%m%d%H%M%S%f')
    raw = f'{now_key}|{campus_id}|{user_id}|{random.randint(1000, 9999)}'
    return hashlib.md5(raw.encode('utf-8')).hexdigest()[:24]


def _ensure_recommendation_event_table():
    db.session.execute(
        text(
            '''
            CREATE TABLE IF NOT EXISTS recommendation_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id VARCHAR(64) DEFAULT '',
                event_type VARCHAR(20) DEFAULT 'exposure',
                variant VARCHAR(10) DEFAULT 'A',
                strategy VARCHAR(30) DEFAULT 'baseline',
                user_id INTEGER,
                campus_id INTEGER DEFAULT 1,
                canteen_id INTEGER,
                dish_id INTEGER NOT NULL,
                position INTEGER DEFAULT 0,
                page VARCHAR(30) DEFAULT 'unknown',
                user_segment VARCHAR(20) DEFAULT 'anonymous',
                propensity FLOAT DEFAULT 0.5,
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
    )
    existing_cols = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(recommendation_event)')).fetchall()
    }
    migration_sql = {
        'user_segment': "ALTER TABLE recommendation_event ADD COLUMN user_segment VARCHAR(20) DEFAULT 'anonymous'",
        'propensity': 'ALTER TABLE recommendation_event ADD COLUMN propensity FLOAT DEFAULT 0.5',
    }
    changed = False
    for col_name, sql in migration_sql.items():
        if col_name not in existing_cols:
            db.session.execute(text(sql))
            changed = True
    if changed:
        db.session.commit()
    db.session.commit()


def _ensure_recommendation_tuning_table():
    db.session.execute(
        text(
            '''
            CREATE TABLE IF NOT EXISTS recommendation_ab_tuning (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campus_id INTEGER NOT NULL UNIQUE,
                explore_multiplier FLOAT DEFAULT 1.0,
                updated_by INTEGER,
                update_note VARCHAR(255) DEFAULT '',
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
    )
    db.session.commit()


def _ensure_recommendation_tuning_log_table():
    db.session.execute(
        text(
            '''
            CREATE TABLE IF NOT EXISTS recommendation_ab_tuning_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campus_id INTEGER NOT NULL,
                before_multiplier FLOAT DEFAULT 1.0,
                after_multiplier FLOAT DEFAULT 1.0,
                trigger_type VARCHAR(20) DEFAULT 'manual',
                reason VARCHAR(255) DEFAULT '',
                actor_id INTEGER,
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
    )
    db.session.commit()


def _ensure_recommendation_policy_table():
    db.session.execute(
        text(
            '''
            CREATE TABLE IF NOT EXISTS recommendation_ab_policy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campus_id INTEGER NOT NULL UNIQUE,
                min_exposure INTEGER DEFAULT 30,
                ctr_delta_threshold FLOAT DEFAULT 1.0,
                step_up FLOAT DEFAULT 0.05,
                step_down FLOAT DEFAULT 0.10,
                min_multiplier FLOAT DEFAULT 0.40,
                max_multiplier FLOAT DEFAULT 2.00,
                guard_enabled BOOLEAN DEFAULT 1,
                guard_pvalue_threshold FLOAT DEFAULT 0.10,
                guard_ctr_drop_threshold FLOAT DEFAULT 0.80,
                guard_consecutive_limit INTEGER DEFAULT 2,
                optimize_mode VARCHAR(20) DEFAULT 'ab',
                bandit_alpha FLOAT DEFAULT 1.0,
                bandit_beta FLOAT DEFAULT 1.0,
                weight_ctr FLOAT DEFAULT 0.40,
                weight_satisfaction FLOAT DEFAULT 0.30,
                weight_safety FLOAT DEFAULT 0.20,
                weight_diversity FLOAT DEFAULT 0.10,
                fairness_lambda FLOAT DEFAULT 0.20,
                fairness_top_share_limit FLOAT DEFAULT 0.35,
                updated_by INTEGER,
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
    )
    existing_cols = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(recommendation_ab_policy)')).fetchall()
    }
    migration_sql = {
        'guard_enabled': 'ALTER TABLE recommendation_ab_policy ADD COLUMN guard_enabled BOOLEAN DEFAULT 1',
        'guard_pvalue_threshold': 'ALTER TABLE recommendation_ab_policy ADD COLUMN guard_pvalue_threshold FLOAT DEFAULT 0.10',
        'guard_ctr_drop_threshold': 'ALTER TABLE recommendation_ab_policy ADD COLUMN guard_ctr_drop_threshold FLOAT DEFAULT 0.80',
        'guard_consecutive_limit': 'ALTER TABLE recommendation_ab_policy ADD COLUMN guard_consecutive_limit INTEGER DEFAULT 2',
        'optimize_mode': "ALTER TABLE recommendation_ab_policy ADD COLUMN optimize_mode VARCHAR(20) DEFAULT 'ab'",
        'bandit_alpha': 'ALTER TABLE recommendation_ab_policy ADD COLUMN bandit_alpha FLOAT DEFAULT 1.0',
        'bandit_beta': 'ALTER TABLE recommendation_ab_policy ADD COLUMN bandit_beta FLOAT DEFAULT 1.0',
        'weight_ctr': 'ALTER TABLE recommendation_ab_policy ADD COLUMN weight_ctr FLOAT DEFAULT 0.40',
        'weight_satisfaction': 'ALTER TABLE recommendation_ab_policy ADD COLUMN weight_satisfaction FLOAT DEFAULT 0.30',
        'weight_safety': 'ALTER TABLE recommendation_ab_policy ADD COLUMN weight_safety FLOAT DEFAULT 0.20',
        'weight_diversity': 'ALTER TABLE recommendation_ab_policy ADD COLUMN weight_diversity FLOAT DEFAULT 0.10',
        'fairness_lambda': 'ALTER TABLE recommendation_ab_policy ADD COLUMN fairness_lambda FLOAT DEFAULT 0.20',
        'fairness_top_share_limit': 'ALTER TABLE recommendation_ab_policy ADD COLUMN fairness_top_share_limit FLOAT DEFAULT 0.35',
    }
    changed = False
    for col_name, sql in migration_sql.items():
        if col_name not in existing_cols:
            db.session.execute(text(sql))
            changed = True
    if changed:
        db.session.commit()
    db.session.commit()


def _default_recommendation_ab_policy():
    return {
        'min_exposure': 30,
        'ctr_delta_threshold': 1.0,
        'step_up': 0.05,
        'step_down': 0.10,
        'min_multiplier': 0.40,
        'max_multiplier': 2.00,
        'guard_enabled': True,
        'guard_pvalue_threshold': 0.10,
        'guard_ctr_drop_threshold': 0.80,
        'guard_consecutive_limit': 2,
        'optimize_mode': 'ab',
        'bandit_alpha': 1.0,
        'bandit_beta': 1.0,
        'weight_ctr': 0.40,
        'weight_satisfaction': 0.30,
        'weight_safety': 0.20,
        'weight_diversity': 0.10,
        'fairness_lambda': 0.20,
        'fairness_top_share_limit': 0.35,
    }


def _get_recommendation_ab_policy(campus_id):
    _ensure_recommendation_policy_table()
    defaults = _default_recommendation_ab_policy()
    row = RecommendationAbPolicy.query.filter_by(campus_id=campus_id).first()
    if not row:
        return dict(defaults)
    optimize_mode = str(getattr(row, 'optimize_mode', defaults['optimize_mode']) or defaults['optimize_mode']).strip().lower()
    if optimize_mode not in ('ab', 'bandit'):
        optimize_mode = 'ab'
    guard_enabled_raw = str(getattr(row, 'guard_enabled', 1)).strip().lower()
    guard_enabled = guard_enabled_raw in ('1', 'true', 'yes', 'on')
    return {
        'min_exposure': max(10, int(_safe_int(getattr(row, 'min_exposure', defaults['min_exposure']), defaults['min_exposure']) or defaults['min_exposure'])),
        'ctr_delta_threshold': max(0.1, float(_safe_number(getattr(row, 'ctr_delta_threshold', defaults['ctr_delta_threshold'])) if _safe_number(getattr(row, 'ctr_delta_threshold', defaults['ctr_delta_threshold'])) is not None else defaults['ctr_delta_threshold'])),
        'step_up': max(0.01, float(_safe_number(getattr(row, 'step_up', defaults['step_up'])) if _safe_number(getattr(row, 'step_up', defaults['step_up'])) is not None else defaults['step_up'])),
        'step_down': max(0.01, float(_safe_number(getattr(row, 'step_down', defaults['step_down'])) if _safe_number(getattr(row, 'step_down', defaults['step_down'])) is not None else defaults['step_down'])),
        'min_multiplier': max(0.10, float(_safe_number(getattr(row, 'min_multiplier', defaults['min_multiplier'])) if _safe_number(getattr(row, 'min_multiplier', defaults['min_multiplier'])) is not None else defaults['min_multiplier'])),
        'max_multiplier': max(0.20, float(_safe_number(getattr(row, 'max_multiplier', defaults['max_multiplier'])) if _safe_number(getattr(row, 'max_multiplier', defaults['max_multiplier'])) is not None else defaults['max_multiplier'])),
        'guard_enabled': guard_enabled,
        'guard_pvalue_threshold': max(0.01, min(0.5, float(_safe_number(getattr(row, 'guard_pvalue_threshold', defaults['guard_pvalue_threshold'])) if _safe_number(getattr(row, 'guard_pvalue_threshold', defaults['guard_pvalue_threshold'])) is not None else defaults['guard_pvalue_threshold']))),
        'guard_ctr_drop_threshold': max(0.1, float(_safe_number(getattr(row, 'guard_ctr_drop_threshold', defaults['guard_ctr_drop_threshold'])) if _safe_number(getattr(row, 'guard_ctr_drop_threshold', defaults['guard_ctr_drop_threshold'])) is not None else defaults['guard_ctr_drop_threshold'])),
        'guard_consecutive_limit': max(1, min(10, int(_safe_int(getattr(row, 'guard_consecutive_limit', defaults['guard_consecutive_limit']), defaults['guard_consecutive_limit']) or defaults['guard_consecutive_limit']))),
        'optimize_mode': optimize_mode,
        'bandit_alpha': max(0.1, float(_safe_number(getattr(row, 'bandit_alpha', defaults['bandit_alpha'])) if _safe_number(getattr(row, 'bandit_alpha', defaults['bandit_alpha'])) is not None else defaults['bandit_alpha'])),
        'bandit_beta': max(0.1, float(_safe_number(getattr(row, 'bandit_beta', defaults['bandit_beta'])) if _safe_number(getattr(row, 'bandit_beta', defaults['bandit_beta'])) is not None else defaults['bandit_beta'])),
        'weight_ctr': max(0.0, float(_safe_number(getattr(row, 'weight_ctr', defaults['weight_ctr'])) if _safe_number(getattr(row, 'weight_ctr', defaults['weight_ctr'])) is not None else defaults['weight_ctr'])),
        'weight_satisfaction': max(0.0, float(_safe_number(getattr(row, 'weight_satisfaction', defaults['weight_satisfaction'])) if _safe_number(getattr(row, 'weight_satisfaction', defaults['weight_satisfaction'])) is not None else defaults['weight_satisfaction'])),
        'weight_safety': max(0.0, float(_safe_number(getattr(row, 'weight_safety', defaults['weight_safety'])) if _safe_number(getattr(row, 'weight_safety', defaults['weight_safety'])) is not None else defaults['weight_safety'])),
        'weight_diversity': max(0.0, float(_safe_number(getattr(row, 'weight_diversity', defaults['weight_diversity'])) if _safe_number(getattr(row, 'weight_diversity', defaults['weight_diversity'])) is not None else defaults['weight_diversity'])),
        'fairness_lambda': max(0.0, float(_safe_number(getattr(row, 'fairness_lambda', defaults['fairness_lambda'])) if _safe_number(getattr(row, 'fairness_lambda', defaults['fairness_lambda'])) is not None else defaults['fairness_lambda'])),
        'fairness_top_share_limit': max(0.05, min(0.95, float(_safe_number(getattr(row, 'fairness_top_share_limit', defaults['fairness_top_share_limit'])) if _safe_number(getattr(row, 'fairness_top_share_limit', defaults['fairness_top_share_limit'])) is not None else defaults['fairness_top_share_limit']))),
    }


def _set_recommendation_ab_policy(campus_id, payload, actor_id=None):
    _ensure_recommendation_policy_table()
    defaults = _default_recommendation_ab_policy()
    old_policy = _get_recommendation_ab_policy(campus_id)
    row = RecommendationAbPolicy.query.filter_by(campus_id=campus_id).first()
    if not row:
        row = RecommendationAbPolicy(campus_id=campus_id)
        db.session.add(row)

    row.min_exposure = max(10, _safe_int(payload.get('min_exposure'), defaults['min_exposure']) or defaults['min_exposure'])
    row.ctr_delta_threshold = max(0.1, float(_safe_number(payload.get('ctr_delta_threshold')) if _safe_number(payload.get('ctr_delta_threshold')) is not None else defaults['ctr_delta_threshold']))
    row.step_up = max(0.01, float(_safe_number(payload.get('step_up')) if _safe_number(payload.get('step_up')) is not None else defaults['step_up']))
    row.step_down = max(0.01, float(_safe_number(payload.get('step_down')) if _safe_number(payload.get('step_down')) is not None else defaults['step_down']))
    row.min_multiplier = max(0.10, float(_safe_number(payload.get('min_multiplier')) if _safe_number(payload.get('min_multiplier')) is not None else defaults['min_multiplier']))
    row.max_multiplier = max(0.20, float(_safe_number(payload.get('max_multiplier')) if _safe_number(payload.get('max_multiplier')) is not None else defaults['max_multiplier']))
    row.guard_enabled = str(payload.get('guard_enabled', defaults['guard_enabled'])).strip().lower() in ('1', 'true', 'yes', 'on')
    row.guard_pvalue_threshold = max(0.01, min(0.5, float(_safe_number(payload.get('guard_pvalue_threshold')) if _safe_number(payload.get('guard_pvalue_threshold')) is not None else defaults['guard_pvalue_threshold'])))
    row.guard_ctr_drop_threshold = max(0.1, float(_safe_number(payload.get('guard_ctr_drop_threshold')) if _safe_number(payload.get('guard_ctr_drop_threshold')) is not None else defaults['guard_ctr_drop_threshold']))
    row.guard_consecutive_limit = max(1, min(10, _safe_int(payload.get('guard_consecutive_limit'), defaults['guard_consecutive_limit']) or defaults['guard_consecutive_limit']))
    optimize_mode = str(payload.get('optimize_mode') or defaults['optimize_mode']).strip().lower()
    row.optimize_mode = optimize_mode if optimize_mode in ('ab', 'bandit') else defaults['optimize_mode']
    row.bandit_alpha = max(0.1, float(_safe_number(payload.get('bandit_alpha')) if _safe_number(payload.get('bandit_alpha')) is not None else defaults['bandit_alpha']))
    row.bandit_beta = max(0.1, float(_safe_number(payload.get('bandit_beta')) if _safe_number(payload.get('bandit_beta')) is not None else defaults['bandit_beta']))
    row.weight_ctr = max(0.0, float(_safe_number(payload.get('weight_ctr')) if _safe_number(payload.get('weight_ctr')) is not None else defaults['weight_ctr']))
    row.weight_satisfaction = max(0.0, float(_safe_number(payload.get('weight_satisfaction')) if _safe_number(payload.get('weight_satisfaction')) is not None else defaults['weight_satisfaction']))
    row.weight_safety = max(0.0, float(_safe_number(payload.get('weight_safety')) if _safe_number(payload.get('weight_safety')) is not None else defaults['weight_safety']))
    row.weight_diversity = max(0.0, float(_safe_number(payload.get('weight_diversity')) if _safe_number(payload.get('weight_diversity')) is not None else defaults['weight_diversity']))
    row.fairness_lambda = max(0.0, float(_safe_number(payload.get('fairness_lambda')) if _safe_number(payload.get('fairness_lambda')) is not None else defaults['fairness_lambda']))
    row.fairness_top_share_limit = max(0.05, min(0.95, float(_safe_number(payload.get('fairness_top_share_limit')) if _safe_number(payload.get('fairness_top_share_limit')) is not None else defaults['fairness_top_share_limit'])))
    if row.max_multiplier < row.min_multiplier:
        row.max_multiplier = row.min_multiplier
    row.updated_by = actor_id
    row.update_time = datetime.now()
    db.session.commit()
    return old_policy, _get_recommendation_ab_policy(campus_id)


def _recommendation_ctr_significance(a_click, a_exposure, b_click, b_exposure):
    a_click = max(0, int(a_click or 0))
    b_click = max(0, int(b_click or 0))
    a_exposure = max(0, int(a_exposure or 0))
    b_exposure = max(0, int(b_exposure or 0))
    if a_exposure <= 0 or b_exposure <= 0:
        return {'z_score': 0.0, 'p_value': 1.0, 'significant': False, 'method': 'two_proportion_z_test'}

    p1 = a_click / a_exposure
    p2 = b_click / b_exposure
    pooled = (a_click + b_click) / (a_exposure + b_exposure)
    variance = pooled * (1 - pooled) * ((1 / a_exposure) + (1 / b_exposure))
    if variance <= 0:
        return {'z_score': 0.0, 'p_value': 1.0, 'significant': False, 'method': 'two_proportion_z_test'}
    z = (p2 - p1) / math.sqrt(variance)
    p_value = max(0.0, min(1.0, math.erfc(abs(z) / math.sqrt(2))))
    return {
        'z_score': round(float(z), 4),
        'p_value': round(float(p_value), 6),
        'significant': bool(p_value < 0.05),
        'method': 'two_proportion_z_test',
    }


def _get_recommendation_explore_multiplier(campus_id):
    _ensure_recommendation_tuning_table()
    policy = _get_recommendation_ab_policy(campus_id)
    row = RecommendationAbTuning.query.filter_by(campus_id=campus_id).first()
    if not row:
        return 1.0
    value = _safe_number(getattr(row, 'explore_multiplier', 1.0))
    return max(policy['min_multiplier'], min(policy['max_multiplier'], float(value if value is not None else 1.0)))


def _set_recommendation_explore_multiplier(campus_id, multiplier, actor_id=None, note='', trigger_type='manual'):
    _ensure_recommendation_tuning_table()
    _ensure_recommendation_tuning_log_table()
    policy = _get_recommendation_ab_policy(campus_id)
    safe_value = max(policy['min_multiplier'], min(policy['max_multiplier'], float(_safe_number(multiplier) if _safe_number(multiplier) is not None else 1.0)))
    row = RecommendationAbTuning.query.filter_by(campus_id=campus_id).first()
    before_value = 1.0
    if not row:
        row = RecommendationAbTuning(campus_id=campus_id)
        db.session.add(row)
    else:
        before_value = max(policy['min_multiplier'], min(policy['max_multiplier'], float(_safe_number(getattr(row, 'explore_multiplier', 1.0)) if _safe_number(getattr(row, 'explore_multiplier', 1.0)) is not None else 1.0)))
    row.explore_multiplier = safe_value
    row.updated_by = actor_id
    row.update_note = (note or '').strip()[:255]
    row.update_time = datetime.now()
    db.session.add(
        RecommendationAbTuningLog(
            campus_id=campus_id,
            before_multiplier=before_value,
            after_multiplier=safe_value,
            trigger_type=(trigger_type or 'manual')[:20],
            reason=(note or '').strip()[:255],
            actor_id=actor_id,
        )
    )
    db.session.commit()
    return safe_value


def _serialize_recommendation_tuning_log(row):
    return {
        'id': int(row.id or 0),
        'campus_id': int(row.campus_id or 0),
        'before_multiplier': round(float(row.before_multiplier or 1.0), 2),
        'after_multiplier': round(float(row.after_multiplier or 1.0), 2),
        'trigger_type': row.trigger_type or 'manual',
        'reason': row.reason or '',
        'actor_id': _safe_int(row.actor_id, 0) or 0,
        'create_time': row.create_time.strftime('%Y-%m-%d %H:%M:%S') if row.create_time else '-',
    }


def _recommendation_ab_summary(campus_id, days=7, page=''):
    _ensure_recommendation_event_table()
    start_time = datetime.now() - timedelta(days=max(1, min(60, int(days))))
    query = RecommendationEvent.query.filter(
        RecommendationEvent.create_time >= start_time,
        RecommendationEvent.campus_id == campus_id,
    )
    if page:
        query = query.filter(RecommendationEvent.page == page)
    rows = query.all()
    bucket = {
        'A': {'exposure': 0, 'click': 0},
        'B': {'exposure': 0, 'click': 0},
    }
    for row in rows:
        key = 'A' if (row.variant or 'A').upper() not in ('A', 'B') else row.variant.upper()
        if row.event_type == 'click':
            bucket[key]['click'] += 1
        else:
            bucket[key]['exposure'] += 1

    summary = []
    for key in ('A', 'B'):
        expo = bucket[key]['exposure']
        click = bucket[key]['click']
        ctr = round((click * 100.0 / expo), 2) if expo else 0.0
        summary.append({'variant': key, 'exposure': expo, 'click': click, 'ctr': ctr})
    return summary, rows


def _recommendation_guard_evaluation(campus_id, policy, summary, significance):
    by_variant = {item['variant']: item for item in (summary or [])}
    a_row = by_variant.get('A', {'exposure': 0, 'ctr': 0.0})
    b_row = by_variant.get('B', {'exposure': 0, 'ctr': 0.0})
    b_exposure = int(b_row.get('exposure', 0) or 0)
    delta_ctr = float(b_row.get('ctr', 0.0) or 0.0) - float(a_row.get('ctr', 0.0) or 0.0)
    p_value = float(significance.get('p_value', 1.0) or 1.0)

    degrade = (
        b_exposure >= int(policy['min_exposure'])
        and delta_ctr <= -float(policy['guard_ctr_drop_threshold'])
        and p_value <= float(policy['guard_pvalue_threshold'])
    )
    return {
        'degrade': degrade,
        'delta_ctr': round(float(delta_ctr), 4),
        'b_exposure': b_exposure,
        'p_value': round(float(p_value), 6),
    }


def _recommendation_guard_streak(campus_id):
    _ensure_recommendation_tuning_log_table()
    logs = (
        RecommendationAbTuningLog.query.filter(RecommendationAbTuningLog.campus_id == campus_id)
        .order_by(RecommendationAbTuningLog.id.desc())
        .limit(20)
        .all()
    )
    streak = 0
    oldest_degrade_log = None
    for row in logs:
        if (row.trigger_type or '') != 'auto':
            continue
        reason = (row.reason or '').strip()
        if '[guard_degrade=1]' in reason:
            streak += 1
            oldest_degrade_log = row
            continue
        break
    return streak, oldest_degrade_log


def _build_recommendation_ab_report(campus_id, days=7, page=''):
    summary, rows = _recommendation_ab_summary(campus_id, days=days, page=page)
    by_variant = {item['variant']: item for item in summary}
    significance = _recommendation_ctr_significance(
        by_variant.get('A', {}).get('click', 0),
        by_variant.get('A', {}).get('exposure', 0),
        by_variant.get('B', {}).get('click', 0),
        by_variant.get('B', {}).get('exposure', 0),
    )
    policy = _get_recommendation_ab_policy(campus_id)
    guard_eval = _recommendation_guard_evaluation(campus_id, policy, summary, significance)
    guard_streak, _ = _recommendation_guard_streak(campus_id)

    logs = (
        RecommendationAbTuningLog.query.filter(RecommendationAbTuningLog.campus_id == campus_id)
        .order_by(RecommendationAbTuningLog.id.desc())
        .limit(30)
        .all()
    )
    segmented_by_page = _recommendation_segmented_significance(rows, segment_by='page')
    segmented_by_user = _recommendation_segmented_significance(rows, segment_by='user_segment')
    counterfactual = _recommendation_counterfactual_ips_dr(campus_id, days=days, page=page, target_strategy='explore')

    return {
        'meta': {
            'campus_id': campus_id,
            'days': days,
            'page': page or 'all',
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
        'summary': summary,
        'significance': significance,
        'policy': policy,
        'guard': {
            **guard_eval,
            'consecutive_degrade': guard_streak,
            'consecutive_limit': int(policy.get('guard_consecutive_limit', 2) or 2),
        },
        'segmented': {
            'page': segmented_by_page,
            'user_segment': segmented_by_user,
        },
        'counterfactual': counterfactual,
        'tuning_logs': [_serialize_recommendation_tuning_log(item) for item in logs],
    }


def _recommendation_report_to_markdown(report):
    meta = report.get('meta', {})
    lines = [
        '# 推荐实验报告',
        '',
        f"- 生成时间: {meta.get('generated_at', '-')}",
        f"- 校区ID: {meta.get('campus_id', 0)}",
        f"- 统计窗口: 近{meta.get('days', 7)}天",
        f"- 页面范围: {meta.get('page', 'all')}",
        '',
        '## 总体A/B',
    ]
    for row in report.get('summary', []):
        lines.append(f"- {row.get('variant', '-')}组: 曝光 {row.get('exposure', 0)} / 点击 {row.get('click', 0)} / CTR {row.get('ctr', 0)}%")
    sg = report.get('significance', {})
    lines.extend([
        '',
        f"- 显著性: z={sg.get('z_score', 0)}, p={sg.get('p_value', 1)}, significant={sg.get('significant', False)}",
        '',
        '## 分层显著性（按页面）',
    ])
    for item in report.get('segmented', {}).get('page', [])[:10]:
        lines.append(
            f"- {item.get('segment', 'unknown')}: A CTR {item.get('variant_a', {}).get('ctr', 0)}% / B CTR {item.get('variant_b', {}).get('ctr', 0)}% / p={item.get('significance', {}).get('p_value', 1)}"
        )
    lines.extend(['', '## 反事实评估（IPS/DR）'])
    cf = report.get('counterfactual', {})
    lines.append(f"- 样本量: {cf.get('sample_size', 0)}")
    lines.append(f"- IPS: {cf.get('ips', 0)}")
    lines.append(f"- DR: {cf.get('dr', 0)}")
    return '\n'.join(lines)


@app.route('/api/public/recommendations', methods=['GET'])
def public_recommendations():
    campus_id = _safe_int(request.args.get('campus_id')) or _current_campus_id()
    _public_ensure_seed_data_if_needed(campus_id)
    canteen_id = _safe_int(request.args.get('canteen_id'))
    limit = max(3, min(12, _safe_int(request.args.get('limit'), 6) or 6))
    page = (request.args.get('page') or 'unknown').strip().lower()[:30] or 'unknown'

    user = _current_user()
    policy = _get_recommendation_ab_policy(campus_id)
    normalized_weights = _normalize_recommendation_weights(policy)
    ab_variant, propensity, user_segment, bandit_debug = _recommendation_ab_variant(user, campus_id=campus_id, page=page, policy=policy)
    ab_strategy = _recommendation_strategy_from_variant(ab_variant)
    request_id = _recommendation_request_id(user, campus_id)
    explore_multiplier = _get_recommendation_explore_multiplier(campus_id)
    profile = _build_recommendation_profile(user)

    query = (
        db.session.query(
            Dish,
            Window.name.label('window_name'),
            Canteen.id.label('canteen_id'),
            Canteen.name.label('canteen_name'),
        )
        .join(Window, Window.id == Dish.window_id)
        .join(Canteen, Canteen.id == Window.canteen_id)
        .filter(Dish.is_active.is_(True), Canteen.is_active.is_(True), Canteen.campus_id == campus_id)
    )
    if canteen_id:
        query = query.filter(Canteen.id == canteen_id)

    rows = (
        query.order_by(Dish.average_score.desc(), Dish.review_count.desc(), Dish.id.asc())
        .limit(200)
        .all()
    )
    dish_ids = [int(dish.id or 0) for dish, _, _, _ in rows if _safe_int(getattr(dish, 'id', 0))]
    satisfaction_map, safety_map, diversity_map, canteen_share_map = _build_recommendation_objective_maps(campus_id, dish_ids)
    sentiment_penalty_map, sentiment_negative_ratio_map = _build_dish_sentiment_penalty_map(campus_id, dish_ids)

    scored_rows = []
    for dish, window_name, row_canteen_id, row_canteen_name in rows:
        tags = _safe_tag_list(dish.tags_json)
        dish_id = int(dish.id or 0)
        review_count = int(dish.review_count or 0)
        avg_score = float(dish.average_score or 0)
        score = avg_score * 8.0 + math.log1p(review_count) * 2.0
        reasons = []

        if dish_id in profile['favorite_dish_ids']:
            score += 6.0
            reasons.append('你收藏过')

        if row_canteen_id in profile['favorite_canteen_ids']:
            score += 2.5
            reasons.append('你常去的食堂')

        category_weight = profile['category_weights'].get((dish.category or '其他').strip(), 0.0)
        if category_weight > 0:
            score += category_weight * 2.0
            reasons.append(f'偏好{dish.category or "该类"}')
        elif category_weight < 0:
            score += category_weight * 0.6

        matched_tags = []
        tag_boost = 0.0
        for tag in tags:
            tag_weight = profile['tag_weights'].get(tag, 0.0)
            if tag_weight > 0:
                matched_tags.append(tag)
            tag_boost += tag_weight * 0.9
        score += tag_boost
        if matched_tags:
            reasons.append('匹配' + '、'.join(matched_tags[:2]))

        canteen_weight = profile['canteen_weights'].get(row_canteen_id, 0.0)
        if canteen_weight:
            score += canteen_weight * 1.4

        if ab_variant == 'B':
            # B组偏探索：适当提升中低曝光菜品权重，观察长期点击与复访提升。
            explore_boost = max(0.0, 8.0 - min(float(review_count), 8.0)) * 0.35 * explore_multiplier
            if avg_score >= 8.0:
                explore_boost += 0.5 * explore_multiplier
            score += explore_boost
            if explore_boost >= 1.2:
                reasons.append('探索新菜')

        ctr_proxy = max(0.0, min(1.0, math.log1p(review_count) / math.log1p(50.0)))
        satisfaction_score = satisfaction_map.get(dish_id, max(0.0, min(1.0, avg_score / 10.0)))
        safety_score = safety_map.get(dish_id, satisfaction_score)
        diversity_score = diversity_map.get(dish_id, 1.0)
        multi_objective_score = (
            normalized_weights['weight_ctr'] * ctr_proxy
            + normalized_weights['weight_satisfaction'] * satisfaction_score
            + normalized_weights['weight_safety'] * safety_score
            + normalized_weights['weight_diversity'] * diversity_score
        )
        score += multi_objective_score * 8.0

        canteen_share = canteen_share_map.get(int(row_canteen_id or 0), 0.0)
        fairness_penalty = 0.0
        if canteen_share > policy['fairness_top_share_limit']:
            fairness_penalty = (canteen_share - policy['fairness_top_share_limit']) * 10.0 * policy['fairness_lambda']
            score -= fairness_penalty
            reasons.append('公平曝光校正')

        sentiment_penalty = sentiment_penalty_map.get(dish_id, 0.0)
        sentiment_negative_ratio = sentiment_negative_ratio_map.get(dish_id, 0.0)
        if sentiment_penalty > 0:
            score -= sentiment_penalty
            reasons.append('负面反馈抑制')

        if review_count == 0:
            score += 0.4
            reasons.append('新品尝鲜')
        elif review_count >= 20:
            reasons.append('热度较高')

        if avg_score >= 8.5:
            reasons.append('高分推荐')

        if safety_score >= 0.85:
            reasons.append('食安表现稳定')

        if diversity_score >= 0.8:
            reasons.append('丰富度补位')

        if not reasons:
            reasons.append('校园热门')

        if len(reasons) > 3:
            reasons = reasons[:3]

        scored_rows.append(
            {
                'dish_id': dish_id,
                'dish_name': dish.name,
                'img_url': _recommendation_image_url(dish),
                'price': float(dish.price or 0),
                'category': dish.category or '',
                'tags': tags,
                'review_count': review_count,
                'average_score': round(avg_score, 1),
                'canteen_id': int(row_canteen_id or 0),
                'canteen_name': row_canteen_name or '-',
                'window_name': window_name or '-',
                'score': round(score, 2),
                'reasons': reasons,
                'reason_summary': _summarize_recommendation_reasons(reasons),
                'explanation': {
                    'strategy': ab_strategy,
                    'objective_components': {
                        'ctr_proxy': round(float(ctr_proxy), 4),
                        'satisfaction': round(float(satisfaction_score), 4),
                        'safety': round(float(safety_score), 4),
                        'diversity': round(float(diversity_score), 4),
                    },
                    'weights': {k: round(float(v), 4) for k, v in normalized_weights.items()},
                    'fairness_penalty': round(float(fairness_penalty), 4),
                    'sentiment_penalty': round(float(sentiment_penalty), 4),
                    'sentiment_negative_ratio': round(float(sentiment_negative_ratio), 4),
                },
            }
        )

    scored_rows.sort(key=lambda item: (item['score'], item['average_score'], item['review_count']), reverse=True)

    selected = []
    selected_ids = set()
    canteen_counts = {}
    max_per_canteen = max(1, int(math.ceil(limit * max(0.05, min(0.95, float(policy['fairness_top_share_limit']))))))
    for item in scored_rows:
        canteen_cnt = canteen_counts.get(item['canteen_id'], 0)
        if canteen_cnt >= max_per_canteen:
            continue
        selected.append(item)
        selected_ids.add(item['dish_id'])
        canteen_counts[item['canteen_id']] = canteen_cnt + 1
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        for item in scored_rows:
            if item['dish_id'] in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(item['dish_id'])
            if len(selected) >= limit:
                break

    return api_success(
        {
            'list': selected[:limit],
            'campus_id': campus_id,
            'canteen_id': canteen_id or 0,
            'personalized': bool(user),
            'reason': 'personalized' if user else 'popular',
            'ab_variant': ab_variant,
            'ab_strategy': ab_strategy,
            'request_id': request_id,
            'explore_multiplier': round(float(explore_multiplier), 2),
            'page': page,
            'user_segment': user_segment,
            'propensity': round(float(propensity), 4),
            'optimize_mode': policy.get('optimize_mode', 'ab'),
            'bandit_debug': bandit_debug,
        },
        msg='查询成功',
    )


@app.route('/api/public/recommendations/track', methods=['POST'])
def public_track_recommendations():
    _ensure_recommendation_event_table()
    data = request.get_json(silent=True) or {}
    event_type = (data.get('event_type') or '').strip().lower()
    if event_type not in ('exposure', 'click'):
        return api_error('event_type 仅支持 exposure/click')

    campus_id = _safe_int(data.get('campus_id')) or _current_campus_id()
    request_id = (data.get('request_id') or '').strip()[:64]
    variant = (data.get('ab_variant') or 'A').strip().upper()
    if variant not in ('A', 'B'):
        variant = 'A'
    strategy = (data.get('ab_strategy') or _recommendation_strategy_from_variant(variant)).strip().lower()[:30]
    page = (data.get('page') or 'unknown').strip().lower()[:30]
    user = _current_user()
    user_id = int(user.id) if user else None
    user_segment = (data.get('user_segment') or _recommendation_user_segment(user)).strip().lower()[:20] or 'anonymous'
    if user_segment not in ('anonymous', 'new', 'returning'):
        user_segment = 'anonymous'
    propensity = max(0.05, min(0.95, float(_safe_number(data.get('propensity')) if _safe_number(data.get('propensity')) is not None else 0.5)))

    rows = []
    if event_type == 'exposure':
        items = data.get('items') if isinstance(data.get('items'), list) else []
        for idx, item in enumerate(items[:20], start=1):
            if not isinstance(item, dict):
                continue
            dish_id = _safe_int(item.get('dish_id'))
            if not dish_id:
                continue
            rows.append(
                RecommendationEvent(
                    request_id=request_id,
                    event_type='exposure',
                    variant=variant,
                    strategy=strategy or 'baseline',
                    user_id=user_id,
                    campus_id=campus_id,
                    canteen_id=_safe_int(item.get('canteen_id')),
                    dish_id=dish_id,
                    position=_safe_int(item.get('position'), idx) or idx,
                    page=page,
                    user_segment=user_segment,
                    propensity=propensity,
                )
            )
    else:
        dish_id = _safe_int(data.get('dish_id'))
        if not dish_id:
            return api_error('click 事件缺少 dish_id')
        click_query = RecommendationEvent.query.filter(
            RecommendationEvent.event_type == 'click',
            RecommendationEvent.request_id == request_id,
            RecommendationEvent.dish_id == dish_id,
            RecommendationEvent.page == page,
        )
        if user_id is None:
            click_query = click_query.filter(RecommendationEvent.user_id.is_(None))
        else:
            click_query = click_query.filter(RecommendationEvent.user_id == user_id)
        existed_click = click_query.first()
        if existed_click:
            return api_success({'accepted': 0, 'deduplicated': True}, msg='上报成功')

        rows.append(
            RecommendationEvent(
                request_id=request_id,
                event_type='click',
                variant=variant,
                strategy=strategy or 'baseline',
                user_id=user_id,
                campus_id=campus_id,
                canteen_id=_safe_int(data.get('canteen_id')),
                dish_id=dish_id,
                position=_safe_int(data.get('position'), 0) or 0,
                page=page,
                user_segment=user_segment,
                propensity=propensity,
            )
        )

    if rows:
        db.session.add_all(rows)
        db.session.commit()

    return api_success({'accepted': len(rows)}, msg='上报成功')


@app.route('/api/public/sentiment/analyze', methods=['POST'])
def public_sentiment_analyze():
    data = request.get_json(silent=True) or {}
    text_value = (data.get('text') or '').strip()
    if not text_value:
        return api_error('text 不能为空')

    result = _analyze_sentiment_text(text_value)
    return api_success(
        {
            'text': text_value[:300],
            **result,
        },
        msg='分析成功',
    )


@app.route('/api/admin/sentiment_overview', methods=['GET'])
@admin_login_required
def admin_sentiment_overview():
    days = max(1, min(60, _safe_int(request.args.get('days'), 7) or 7))
    requested_campus_id = _safe_int(request.args.get('campus_id'))
    scoped_campus_id, scope_error = _resolve_campus_scope(requested_campus_id)
    if scope_error:
        return scope_error

    campus_id = scoped_campus_id or _current_campus_id()
    canteen_id = _safe_int(request.args.get('canteen_id'))
    limit = max(5, min(50, _safe_int(request.args.get('limit'), 20) or 20))
    payload = _build_sentiment_overview(campus_id, days=days, canteen_id=canteen_id, limit=limit)
    return api_success(payload, msg='查询成功')


def _build_sentiment_overview(campus_id, days=7, canteen_id=0, limit=20):
    days = max(1, min(60, int(days or 7)))
    limit = max(1, min(100, int(limit or 20)))
    start_time = datetime.now() - timedelta(days=days)

    query = EvaluationMain.query.filter(
        EvaluationMain.campus_id == campus_id,
        EvaluationMain.create_time >= start_time,
    )
    if canteen_id:
        query = query.filter(EvaluationMain.canteen_id == canteen_id)

    rows = query.order_by(EvaluationMain.create_time.desc(), EvaluationMain.id.desc()).limit(1000).all()

    bucket = {'positive': 0, 'neutral': 0, 'negative': 0}
    risk_bucket = {'low': 0, 'medium': 0, 'high': 0}
    trend_map = {}
    negatives = []

    for row in rows:
        sentiment = _analyze_evaluation_sentiment(row)
        label = sentiment.get('label', 'neutral')
        risk_level = sentiment.get('risk_level', 'low')

        bucket[label] = int(bucket.get(label, 0)) + 1
        risk_bucket[risk_level] = int(risk_bucket.get(risk_level, 0)) + 1

        day_key = row.create_time.strftime('%Y-%m-%d') if row.create_time else datetime.now().strftime('%Y-%m-%d')
        day_slot = trend_map.setdefault(day_key, {'date': day_key, 'total': 0, 'negative': 0, 'risk_high': 0})
        day_slot['total'] += 1
        if label == 'negative':
            day_slot['negative'] += 1
        if risk_level == 'high':
            day_slot['risk_high'] += 1

        if label == 'negative' or risk_level == 'high':
            canteen = db.session.get(Canteen, row.canteen_id) if row.canteen_id else None
            window = db.session.get(Window, row.window_id) if row.window_id else None
            negatives.append(
                {
                    'evaluation_id': int(row.id or 0),
                    'create_time': row.create_time.strftime('%Y-%m-%d %H:%M:%S') if row.create_time else '-',
                    'canteen_id': int(row.canteen_id or 0),
                    'canteen_name': canteen.name if canteen else '-',
                    'window_id': int(row.window_id or 0),
                    'window_name': window.name if window else '-',
                    'comprehensive_score': round(float(row.comprehensive_score or 0.0), 2),
                    'sentiment_score': float(sentiment['sentiment_score']),
                    'risk_score': float(sentiment['risk_score']),
                    'risk_level': risk_level,
                    'label': label,
                    'remark_excerpt': (str(row.remark or '').strip()[:60] or '-'),
                    'keyword_hits': sentiment.get('keyword_hits', {}),
                }
            )

    trend_list = [trend_map[key] for key in sorted(trend_map.keys())]
    negatives.sort(key=lambda item: (item['risk_score'], 1 - item['sentiment_score'], -item['comprehensive_score']), reverse=True)

    total = len(rows)
    return {
        'campus_id': campus_id,
        'canteen_id': canteen_id or 0,
        'days': days,
        'total': total,
        'summary': {
            'positive': bucket['positive'],
            'neutral': bucket['neutral'],
            'negative': bucket['negative'],
            'negative_ratio': round(float(bucket['negative'] / total), 4) if total else 0.0,
            'risk': risk_bucket,
        },
        'trend': trend_list,
        'high_risk_samples': negatives[:limit],
    }


def _render_sentiment_overview_markdown(report):
    summary = report.get('summary', {})
    lines = [
        '# 舆情监控报告',
        '',
        f"- 校区ID: {report.get('campus_id', 0)}",
        f"- 食堂ID: {report.get('canteen_id', 0)}",
        f"- 统计窗口: 近{report.get('days', 7)}天",
        f"- 总样本量: {report.get('total', 0)}",
        '',
        '## 统计摘要',
        f"- 正面: {summary.get('positive', 0)}",
        f"- 中性: {summary.get('neutral', 0)}",
        f"- 负面: {summary.get('negative', 0)}",
        f"- 负面占比: {float(summary.get('negative_ratio', 0.0)) * 100:.2f}%",
        f"- 低/中/高风险: {summary.get('risk', {}).get('low', 0)} / {summary.get('risk', {}).get('medium', 0)} / {summary.get('risk', {}).get('high', 0)}",
        '',
        '## 日趋势',
    ]
    for row in report.get('trend', []):
        total = int(row.get('total', 0) or 0)
        negative = int(row.get('negative', 0) or 0)
        high = int(row.get('risk_high', 0) or 0)
        lines.append(
            f"- {row.get('date', '-')}: 总量 {total} / 负面 {negative} / 高风险 {high}"
        )

    lines.extend(['', '## 高风险样本'])
    for row in report.get('high_risk_samples', [])[:10]:
        lines.append(
            f"- #{row.get('evaluation_id', 0)} {row.get('canteen_name', '-')} / {row.get('window_name', '-')} 风险{row.get('risk_level', 'low')} 备注: {row.get('remark_excerpt', '-') }"
        )
    return '\n'.join(lines)


@app.route('/api/admin/sentiment_report', methods=['GET'])
@admin_login_required
def admin_sentiment_report():
    days = max(1, min(60, _safe_int(request.args.get('days'), 7) or 7))
    requested_campus_id = _safe_int(request.args.get('campus_id'))
    scoped_campus_id, scope_error = _resolve_campus_scope(requested_campus_id)
    if scope_error:
        return scope_error

    campus_id = scoped_campus_id or _current_campus_id()
    canteen_id = _safe_int(request.args.get('canteen_id'))
    limit = max(5, min(50, _safe_int(request.args.get('limit'), 20) or 20))
    export_format = (request.args.get('format') or 'md').strip().lower()

    report = _build_sentiment_overview(campus_id, days=days, canteen_id=canteen_id, limit=limit)
    filename_base = f"sentiment_report_c{campus_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if export_format == 'json':
        return api_success(report, msg='查询成功')

    if export_format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['date', 'total', 'negative', 'risk_high'])
        for row in report.get('trend', []):
            writer.writerow([
                row.get('date', '-'),
                row.get('total', 0),
                row.get('negative', 0),
                row.get('risk_high', 0),
            ])
        response = Response(output.getvalue(), mimetype='text/csv; charset=utf-8')
        response.headers['Content-Disposition'] = f'attachment; filename={filename_base}.csv'
        return response

    markdown = _render_sentiment_overview_markdown(report)
    return Response(
        markdown,
        mimetype='text/markdown; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={filename_base}.md'},
    )


@app.route('/api/admin/recommendation_ab_metrics', methods=['GET'])
@admin_login_required
def admin_recommendation_ab_metrics():
    _ensure_recommendation_event_table()
    days = max(1, min(60, _safe_int(request.args.get('days'), 7) or 7))
    page = (request.args.get('page') or '').strip().lower()
    campus_id = _safe_int(request.args.get('campus_id')) or _current_campus_id()
    summary, rows = _recommendation_ab_summary(campus_id, days=days, page=page)
    explore_multiplier = _get_recommendation_explore_multiplier(campus_id)
    policy = _get_recommendation_ab_policy(campus_id)
    by_variant = {item['variant']: item for item in summary}
    significance = _recommendation_ctr_significance(
        by_variant.get('A', {}).get('click', 0),
        by_variant.get('A', {}).get('exposure', 0),
        by_variant.get('B', {}).get('click', 0),
        by_variant.get('B', {}).get('exposure', 0),
    )
    segmented_by_page = _recommendation_segmented_significance(rows, segment_by='page')
    segmented_by_user = _recommendation_segmented_significance(rows, segment_by='user_segment')
    guard_eval = _recommendation_guard_evaluation(campus_id, policy, summary, significance)
    guard_streak, _ = _recommendation_guard_streak(campus_id)

    return api_success(
        {
            'campus_id': campus_id,
            'days': days,
            'page': page or 'all',
            'summary': summary,
            'total_events': len(rows),
            'explore_multiplier': round(float(explore_multiplier), 2),
            'policy': policy,
            'significance': significance,
            'segments': {
                'page': segmented_by_page,
                'user_segment': segmented_by_user,
            },
            'guard': {
                **guard_eval,
                'consecutive_degrade': guard_streak,
                'consecutive_limit': int(policy.get('guard_consecutive_limit', 2) or 2),
            },
        },
        msg='查询成功',
    )


@app.route('/api/admin/recommendation_ab_segments', methods=['GET'])
@admin_login_required
def admin_recommendation_ab_segments():
    _ensure_recommendation_event_table()
    days = max(1, min(60, _safe_int(request.args.get('days'), 7) or 7))
    page = (request.args.get('page') or '').strip().lower()
    segment_by = (request.args.get('segment_by') or 'page').strip().lower()
    campus_id = _safe_int(request.args.get('campus_id')) or _current_campus_id()
    _, rows = _recommendation_ab_summary(campus_id, days=days, page=page)
    segments = _recommendation_segmented_significance(rows, segment_by=segment_by)
    return api_success({'campus_id': campus_id, 'days': days, 'page': page or 'all', 'segment_by': segment_by, 'list': segments}, msg='查询成功')


@app.route('/api/admin/recommendation_counterfactual_eval', methods=['GET'])
@admin_login_required
def admin_recommendation_counterfactual_eval():
    _ensure_recommendation_event_table()
    days = max(1, min(60, _safe_int(request.args.get('days'), 7) or 7))
    page = (request.args.get('page') or '').strip().lower()
    target_strategy = (request.args.get('target_strategy') or 'explore').strip().lower()
    campus_id = _safe_int(request.args.get('campus_id')) or _current_campus_id()
    result = _recommendation_counterfactual_ips_dr(campus_id, days=days, page=page, target_strategy=target_strategy)
    return api_success({'campus_id': campus_id, 'days': days, 'page': page or 'all', **result}, msg='查询成功')


@app.route('/api/admin/recommendation_ab_report', methods=['GET'])
@admin_login_required
def admin_recommendation_ab_report():
    _ensure_recommendation_event_table()
    days = max(1, min(60, _safe_int(request.args.get('days'), 7) or 7))
    page = (request.args.get('page') or '').strip().lower()
    export_format = (request.args.get('format') or 'json').strip().lower()
    campus_id = _safe_int(request.args.get('campus_id')) or _current_campus_id()
    report = _build_recommendation_ab_report(campus_id, days=days, page=page)

    filename_base = f"recommendation_ab_report_c{campus_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if export_format == 'md':
        markdown = _recommendation_report_to_markdown(report)
        return Response(
            markdown,
            mimetype='text/markdown; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename={filename_base}.md'},
        )
    if export_format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['campus_id', 'days', 'page', 'variant', 'exposure', 'click', 'ctr'])
        for row in report.get('summary', []):
            writer.writerow([
                report.get('meta', {}).get('campus_id', 0),
                report.get('meta', {}).get('days', 7),
                report.get('meta', {}).get('page', 'all'),
                row.get('variant', '-'),
                row.get('exposure', 0),
                row.get('click', 0),
                row.get('ctr', 0.0),
            ])
        writer.writerow([])
        writer.writerow(['segment_by_page', 'segment', 'a_exposure', 'a_click', 'a_ctr', 'b_exposure', 'b_click', 'b_ctr', 'p_value'])
        for row in report.get('segmented', {}).get('page', []):
            writer.writerow([
                'page',
                row.get('segment', 'unknown'),
                row.get('variant_a', {}).get('exposure', 0),
                row.get('variant_a', {}).get('click', 0),
                row.get('variant_a', {}).get('ctr', 0.0),
                row.get('variant_b', {}).get('exposure', 0),
                row.get('variant_b', {}).get('click', 0),
                row.get('variant_b', {}).get('ctr', 0.0),
                row.get('significance', {}).get('p_value', 1.0),
            ])
        response = Response(output.getvalue(), mimetype='text/csv; charset=utf-8')
        response.headers['Content-Disposition'] = f'attachment; filename={filename_base}.csv'
        return response

    return api_success(report, msg='查询成功')


@app.route('/api/admin/recommendation_guard_check', methods=['POST'])
@admin_login_required
def admin_recommendation_guard_check():
    _ensure_recommendation_tuning_log_table()
    data = request.get_json(silent=True) or {}
    requested_campus_id = _safe_int(data.get('campus_id'))
    scoped_campus_id, scope_error = _resolve_campus_scope(requested_campus_id)
    if scope_error:
        return scope_error
    campus_id = scoped_campus_id or _current_campus_id()
    days = max(1, min(60, _safe_int(data.get('days'), 7) or 7))
    page = (data.get('page') or '').strip().lower()

    summary, _ = _recommendation_ab_summary(campus_id, days=days, page=page)
    by_variant = {item['variant']: item for item in summary}
    significance = _recommendation_ctr_significance(
        by_variant.get('A', {}).get('click', 0),
        by_variant.get('A', {}).get('exposure', 0),
        by_variant.get('B', {}).get('click', 0),
        by_variant.get('B', {}).get('exposure', 0),
    )
    policy = _get_recommendation_ab_policy(campus_id)
    guard_eval = _recommendation_guard_evaluation(campus_id, policy, summary, significance)
    streak, oldest = _recommendation_guard_streak(campus_id)

    triggered = False
    restored_multiplier = _get_recommendation_explore_multiplier(campus_id)
    detail_msg = '未触发保护回滚'
    if bool(policy.get('guard_enabled')) and guard_eval['degrade'] and streak >= int(policy.get('guard_consecutive_limit', 2) or 2):
        actor = _current_user()
        restore_to = oldest.before_multiplier if oldest else restored_multiplier
        restored_multiplier = _set_recommendation_explore_multiplier(
            campus_id,
            restore_to,
            actor_id=actor.id if actor else None,
            note=f'guard_rollback: 连续{streak}次显著劣化触发保护回滚',
            trigger_type='guard_rollback',
        )
        triggered = True
        detail_msg = f'已触发保护回滚，恢复探索系数到 {restored_multiplier:.2f}'

    return api_success(
        {
            'campus_id': campus_id,
            'days': days,
            'page': page or 'all',
            'triggered': triggered,
            'restored_multiplier': round(float(restored_multiplier), 2),
            'guard': {
                **guard_eval,
                'consecutive_degrade': streak,
                'consecutive_limit': int(policy.get('guard_consecutive_limit', 2) or 2),
                'enabled': bool(policy.get('guard_enabled')),
            },
            'summary': summary,
            'significance': significance,
            'policy': policy,
            'message': detail_msg,
        },
        msg='检测完成',
    )


@app.route('/api/admin/recommendation_ab_tune', methods=['POST'])
@admin_login_required
def admin_recommendation_ab_tune():
    _ensure_recommendation_tuning_table()
    data = request.get_json(silent=True) or {}
    requested_campus_id = _safe_int(data.get('campus_id'))
    scoped_campus_id, scope_error = _resolve_campus_scope(requested_campus_id)
    if scope_error:
        return scope_error

    campus_id = scoped_campus_id or _current_campus_id()
    days = max(1, min(60, _safe_int(data.get('days'), 7) or 7))
    policy = _get_recommendation_ab_policy(campus_id)
    min_exposure = max(10, min(500, _safe_int(data.get('min_exposure'), policy['min_exposure']) or policy['min_exposure']))
    page = (data.get('page') or '').strip().lower()

    summary, _ = _recommendation_ab_summary(campus_id, days=days, page=page)
    by_variant = {item['variant']: item for item in summary}
    a_row = by_variant.get('A', {'exposure': 0, 'ctr': 0.0})
    b_row = by_variant.get('B', {'exposure': 0, 'ctr': 0.0})
    significance = _recommendation_ctr_significance(
        by_variant.get('A', {}).get('click', 0),
        by_variant.get('A', {}).get('exposure', 0),
        by_variant.get('B', {}).get('click', 0),
        by_variant.get('B', {}).get('exposure', 0),
    )
    guard_eval = _recommendation_guard_evaluation(campus_id, policy, summary, significance)

    current_multiplier = _get_recommendation_explore_multiplier(campus_id)
    next_multiplier = current_multiplier
    reason = '样本不足，维持当前探索强度'

    if int(b_row.get('exposure', 0) or 0) < min_exposure:
        next_multiplier = min(policy['max_multiplier'], current_multiplier + policy['step_down'])
        reason = f'B组曝光不足({b_row.get("exposure", 0)}<{min_exposure})，提高探索强度收集样本'
    else:
        delta_ctr = float(b_row.get('ctr', 0.0) or 0.0) - float(a_row.get('ctr', 0.0) or 0.0)
        if delta_ctr <= -policy['ctr_delta_threshold']:
            next_multiplier = max(policy['min_multiplier'], current_multiplier - policy['step_down'])
            reason = f'B组CTR低于A组({delta_ctr:.2f}%)，降低探索强度'
        elif delta_ctr >= policy['ctr_delta_threshold']:
            next_multiplier = min(policy['max_multiplier'], current_multiplier + policy['step_up'])
            reason = f'B组CTR高于A组({delta_ctr:.2f}%)，适度提高探索强度'
        else:
            reason = f'A/B CTR差异较小({delta_ctr:.2f}%)，维持当前探索强度'

    actor = _current_user()
    guard_tag = '[guard_degrade=1]' if guard_eval['degrade'] else '[guard_degrade=0]'
    saved_multiplier = _set_recommendation_explore_multiplier(
        campus_id,
        next_multiplier,
        actor_id=actor.id if actor else None,
        note=f'auto_tune: {reason} {guard_tag}',
        trigger_type='auto',
    )

    streak, oldest = _recommendation_guard_streak(campus_id)
    guard_triggered = False
    guard_restore_to = None
    if bool(policy.get('guard_enabled')) and guard_eval['degrade'] and streak >= int(policy.get('guard_consecutive_limit', 2) or 2):
        guard_restore_to = oldest.before_multiplier if oldest else current_multiplier
        saved_multiplier = _set_recommendation_explore_multiplier(
            campus_id,
            guard_restore_to,
            actor_id=actor.id if actor else None,
            note=f'guard_rollback(auto): 连续{streak}次显著劣化触发保护回滚',
            trigger_type='guard_rollback',
        )
        guard_triggered = True

    return api_success(
        {
            'campus_id': campus_id,
            'days': days,
            'page': page or 'all',
            'min_exposure': min_exposure,
            'before_multiplier': round(float(current_multiplier), 2),
            'after_multiplier': round(float(saved_multiplier), 2),
            'summary': summary,
            'reason': reason,
            'policy': policy,
            'significance': significance,
            'guard': {
                **guard_eval,
                'consecutive_degrade': streak,
                'consecutive_limit': int(policy.get('guard_consecutive_limit', 2) or 2),
                'triggered': guard_triggered,
            },
        },
        msg='调参完成',
    )


@app.route('/api/admin/recommendation_ab_tune_logs', methods=['GET'])
@admin_login_required
def admin_recommendation_ab_tune_logs():
    _ensure_recommendation_tuning_log_table()
    requested_campus_id = _safe_int(request.args.get('campus_id'))
    scoped_campus_id, scope_error = _resolve_campus_scope(requested_campus_id)
    if scope_error:
        return scope_error
    campus_id = scoped_campus_id or _current_campus_id()
    limit = max(5, min(100, _safe_int(request.args.get('limit'), 20) or 20))

    rows = (
        RecommendationAbTuningLog.query.filter(RecommendationAbTuningLog.campus_id == campus_id)
        .order_by(RecommendationAbTuningLog.id.desc())
        .limit(limit)
        .all()
    )
    return api_success({'campus_id': campus_id, 'list': [_serialize_recommendation_tuning_log(row) for row in rows]}, msg='查询成功')


@app.route('/api/admin/recommendation_ab_policy', methods=['GET'])
@admin_login_required
def admin_get_recommendation_ab_policy():
    requested_campus_id = _safe_int(request.args.get('campus_id'))
    scoped_campus_id, scope_error = _resolve_campus_scope(requested_campus_id)
    if scope_error:
        return scope_error
    campus_id = scoped_campus_id or _current_campus_id()
    return api_success({'campus_id': campus_id, 'policy': _get_recommendation_ab_policy(campus_id)}, msg='查询成功')


@app.route('/api/admin/recommendation_ab_policy', methods=['POST'])
@admin_login_required
def admin_update_recommendation_ab_policy():
    data = request.get_json(silent=True) or {}
    requested_campus_id = _safe_int(data.get('campus_id'))
    scoped_campus_id, scope_error = _resolve_campus_scope(requested_campus_id)
    if scope_error:
        return scope_error
    campus_id = scoped_campus_id or _current_campus_id()
    actor = _current_user()
    old_policy, new_policy = _set_recommendation_ab_policy(campus_id, data, actor_id=actor.id if actor else None)
    return api_success({'campus_id': campus_id, 'before_policy': old_policy, 'policy': new_policy}, msg='更新成功')


@app.route('/api/admin/recommendation_ab_tune_rollback', methods=['POST'])
@admin_login_required
def admin_recommendation_ab_tune_rollback():
    _ensure_recommendation_tuning_log_table()
    data = request.get_json(silent=True) or {}
    requested_campus_id = _safe_int(data.get('campus_id'))
    scoped_campus_id, scope_error = _resolve_campus_scope(requested_campus_id)
    if scope_error:
        return scope_error
    campus_id = scoped_campus_id or _current_campus_id()

    latest_row = (
        RecommendationAbTuningLog.query.filter(RecommendationAbTuningLog.campus_id == campus_id)
        .order_by(RecommendationAbTuningLog.id.desc())
        .first()
    )
    if not latest_row:
        return api_error('暂无可回滚记录')

    actor = _current_user()
    restored = _set_recommendation_explore_multiplier(
        campus_id,
        latest_row.before_multiplier,
        actor_id=actor.id if actor else None,
        note=f'rollback: 回滚到日志#{latest_row.id}前值',
        trigger_type='rollback',
    )
    return api_success(
        {
            'campus_id': campus_id,
            'rolled_back_log_id': int(latest_row.id or 0),
            'restored_multiplier': round(float(restored), 2),
        },
        msg='回滚成功',
    )

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
        payload = request.get_json(silent=True) or {}
        result, api_err = _create_evaluation_from_payload(payload, session.get('user_id'), enforce_repeat_guard=enforce_repeat_guard)
        if api_err:
            return api_err
        if enforce_repeat_guard:
            app.logger.info(
                'submit_success user_id=%s window_id=%s evaluation_id=%s',
                session.get('user_id'),
                _safe_int(payload.get('window_id')),
                result.get('evaluation_id'),
            )
        return api_success(result, msg='评价提交成功')

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


@app.route('/api/guest/evaluations', methods=['POST'])
def guest_submit_evaluation():
    return api_error('游客提交已关闭，请登录后进行评价', code=403, http_status=403)


@app.route('/api/guest/evaluations/<int:submission_id>/status', methods=['GET'])
def guest_evaluation_status(submission_id):
    return api_error('游客状态查询已关闭，请使用登录账号查看评价记录', code=403, http_status=403)


def _guest_feature_disabled():
    return api_error('游客审核功能已下线', code=410, http_status=410)


@app.route('/api/admin/guest_evaluations', methods=['GET'])
@admin_login_required
def admin_get_guest_evaluations():
    return _guest_feature_disabled()


@app.route('/api/admin/guest_evaluations/<int:submission_id>/approve', methods=['POST'])
@admin_login_required
def admin_approve_guest_evaluation(submission_id):
    return _guest_feature_disabled()


@app.route('/api/admin/guest_evaluations/<int:submission_id>/reject', methods=['POST'])
@admin_login_required
def admin_reject_guest_evaluation(submission_id):
    return _guest_feature_disabled()


@app.route('/api/admin/guest_evaluations/batch_review', methods=['POST'])
@admin_login_required
def admin_batch_review_guest_evaluations():
    return _guest_feature_disabled()


@app.route('/api/evaluation/template/current', methods=['GET'])
def get_current_evaluation_template():
    version = _ensure_default_template()
    return api_success(_serialize_template(version), msg='查询成功')


@app.route('/api/admin/evaluation_templates', methods=['GET'])
@admin_login_required
def admin_get_evaluation_templates():
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    rows = EvaluationTemplateVersion.query.order_by(EvaluationTemplateVersion.version_no.desc()).all()
    data = [_serialize_template(row) for row in rows]
    return api_success({'list': data, 'total': len(data)}, msg='查询成功')


@app.route('/api/admin/evaluation_templates', methods=['POST'])
@admin_login_required
def admin_create_evaluation_template():
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip() or f"评价模板 {datetime.now().strftime('%Y%m%d%H%M')}"
    items = data.get('items') if isinstance(data.get('items'), list) else []

    max_version = db.session.query(func.max(EvaluationTemplateVersion.version_no)).scalar() or 0
    version = EvaluationTemplateVersion(
        version_no=int(max_version) + 1,
        name=name[:100],
        status='draft',
        created_by=session.get('user_id'),
    )
    db.session.add(version)
    db.session.flush()

    if not items:
        active = EvaluationTemplateVersion.query.filter_by(status='active').order_by(EvaluationTemplateVersion.version_no.desc()).first()
        if active:
            base_items = EvaluationTemplateItem.query.filter_by(version_id=active.id).all()
            for item in base_items:
                db.session.add(
                    EvaluationTemplateItem(
                        version_id=version.id,
                        category=item.category,
                        item_key=item.item_key,
                        item_label=item.item_label,
                        sort_order=item.sort_order,
                        score_min=item.score_min,
                        score_max=item.score_max,
                        enabled=item.enabled,
                    )
                )
        else:
            for item in _template_default_items():
                db.session.add(
                    EvaluationTemplateItem(
                        version_id=version.id,
                        category=item['category'],
                        item_key=item['item_key'],
                        item_label=item['item_label'],
                        sort_order=item['sort_order'],
                        score_min=1,
                        score_max=10,
                        enabled=True,
                    )
                )
    else:
        for idx, item in enumerate(items, start=1):
            category = (item.get('category') or '').strip().lower()
            item_key = (item.get('item_key') or '').strip()
            item_label = (item.get('item_label') or '').strip()
            if category not in ('food', 'service', 'env', 'safety') or not item_key or not item_label:
                continue
            db.session.add(
                EvaluationTemplateItem(
                    version_id=version.id,
                    category=category,
                    item_key=item_key[:60],
                    item_label=item_label[:120],
                    sort_order=_safe_int(item.get('sort_order'), idx) or idx,
                    score_min=_to_int(item.get('score_min'), 1, 0, 100),
                    score_max=_to_int(item.get('score_max'), 10, 1, 100),
                    enabled=_to_bool(item.get('enabled'), True),
                )
            )

    _audit_log(
        'template_create',
        target_type='evaluation_template',
        target_id=version.id,
        detail={'version_no': version.version_no, 'item_count': len(items) if items else 0, 'status': 'draft'},
    )
    db.session.commit()
    return api_success(_serialize_template(version), msg='创建成功')


@app.route('/api/admin/evaluation_templates/<int:version_id>/publish', methods=['POST'])
@admin_login_required
def admin_publish_evaluation_template(version_id):
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    target = db.session.get(EvaluationTemplateVersion, version_id)
    if not target:
        return api_error('模板版本不存在', code=404, http_status=404)

    if not EvaluationTemplateItem.query.filter_by(version_id=target.id).first():
        return api_error('模板细项不能为空')

    EvaluationTemplateVersion.query.update({EvaluationTemplateVersion.status: 'archived'}, synchronize_session=False)
    target.status = 'active'
    target.publish_time = datetime.now()
    _audit_log(
        'template_publish',
        target_type='evaluation_template',
        target_id=target.id,
        detail={'version_no': target.version_no, 'status': target.status},
    )
    db.session.commit()
    return api_success(_serialize_template(target), msg='发布成功')


@app.route('/api/admin/evaluation_templates/<int:version_id>', methods=['PUT'])
@admin_login_required
def admin_update_evaluation_template(version_id):
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    target = db.session.get(EvaluationTemplateVersion, version_id)
    if not target:
        return api_error('模板版本不存在', code=404, http_status=404)
    if target.status == 'active':
        return api_error('生效中的模板不允许直接修改，请先新建草稿模板')

    data = request.get_json(silent=True) or {}
    before_snapshot = {
        'name': target.name,
        'status': target.status,
        'items_count': EvaluationTemplateItem.query.filter_by(version_id=target.id).count(),
    }
    if 'name' in data:
        target.name = ((data.get('name') or '').strip() or target.name)[:100]

    items = data.get('items') if isinstance(data.get('items'), list) else None
    if items is not None:
        EvaluationTemplateItem.query.filter_by(version_id=target.id).delete(synchronize_session=False)
        for idx, item in enumerate(items, start=1):
            category = (item.get('category') or '').strip().lower()
            item_key = (item.get('item_key') or '').strip()
            item_label = (item.get('item_label') or '').strip()
            if category not in ('food', 'service', 'env', 'safety') or not item_key or not item_label:
                continue
            db.session.add(
                EvaluationTemplateItem(
                    version_id=target.id,
                    category=category,
                    item_key=item_key[:60],
                    item_label=item_label[:120],
                    sort_order=_safe_int(item.get('sort_order'), idx) or idx,
                    score_min=_to_int(item.get('score_min'), 1, 0, 100),
                    score_max=_to_int(item.get('score_max'), 10, 1, 100),
                    enabled=_to_bool(item.get('enabled'), True),
                )
            )

    _audit_log(
        'template_update',
        target_type='evaluation_template',
        target_id=target.id,
        detail={
            'version_no': target.version_no,
            'name': target.name,
            'items_updated': len(items) if items is not None else 0,
        },
        before_data=before_snapshot,
        after_data={
            'name': target.name,
            'status': target.status,
            'items_count': EvaluationTemplateItem.query.filter_by(version_id=target.id).count(),
        },
    )
    db.session.commit()
    return api_success(_serialize_template(target), msg='更新成功')


@app.route('/api/admin/action_logs', methods=['GET'])
@admin_login_required
def admin_get_action_logs():
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    page = max(1, _safe_int(request.args.get('page'), 1) or 1)
    limit = max(1, min(100, _safe_int(request.args.get('limit'), 20) or 20))
    action = (request.args.get('action') or '').strip()
    actor_id = _safe_int(request.args.get('actor_id'))
    start_time = _parse_datetime_text(request.args.get('start_time'))
    end_time = _parse_datetime_text(request.args.get('end_time'))

    query = AdminActionLog.query
    if action:
        query = query.filter(AdminActionLog.action == action)
    if actor_id:
        query = query.filter(AdminActionLog.actor_id == actor_id)
    if start_time:
        query = query.filter(AdminActionLog.create_time >= start_time)
    if end_time:
        query = query.filter(AdminActionLog.create_time <= end_time)

    total = query.count()
    rows = query.order_by(AdminActionLog.id.desc()).offset((page - 1) * limit).limit(limit).all()
    return api_success(
        {
            'list': [_serialize_action_log(row) for row in rows],
            'total': total,
            'page': page,
            'limit': limit,
            'pages': math.ceil(total / limit) if total else 0,
        },
        msg='查询成功',
    )


@app.route('/api/admin/action_logs/export', methods=['GET'])
@admin_login_required
def admin_export_action_logs():
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    action = (request.args.get('action') or '').strip()
    actor_id = _safe_int(request.args.get('actor_id'))
    start_time = _parse_datetime_text(request.args.get('start_time'))
    end_time = _parse_datetime_text(request.args.get('end_time'))

    query = AdminActionLog.query
    if action:
        query = query.filter(AdminActionLog.action == action)
    if actor_id:
        query = query.filter(AdminActionLog.actor_id == actor_id)
    if start_time:
        query = query.filter(AdminActionLog.create_time >= start_time)
    if end_time:
        query = query.filter(AdminActionLog.create_time <= end_time)

    rows = query.order_by(AdminActionLog.id.desc()).limit(2000).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'time', 'actor_id', 'actor_role', 'action', 'target_type', 'target_id', 'detail'])
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.create_time.strftime('%Y-%m-%d %H:%M:%S') if row.create_time else '-',
                row.actor_id,
                row.actor_role,
                row.action,
                row.target_type,
                row.target_id,
                row.detail,
            ]
        )

    content = output.getvalue()
    output.close()
    filename = f"action_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content,
        mimetype='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
        },
    )


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
    with_pagination = (request.args.get('with_pagination') or '').strip() in ('1', 'true', 'True')
    page = max(1, _safe_int(request.args.get('page'), 1) or 1)
    limit = max(1, min(50, _safe_int(request.args.get('limit'), 10) or 10))
    governance_filter = (request.args.get('governance_status') or '').strip().lower()
    
    evals = EvaluationMain.query.filter_by(user_id=user_id).order_by(EvaluationMain.create_time.desc()).all()
    
    result = []
    for e in evals:
        warning = OperatorWarning.query.filter_by(evaluation_id=e.id).first()
        rect_rows = []
        if warning:
            rect_rows = RectificationRecord.query.filter_by(warning_id=warning.id).order_by(RectificationRecord.id.desc()).all()

        governance_status = 'normal'
        governance_text = '正常'
        if warning and warning.status == 'pending':
            governance_status = 'pending'
            governance_text = '待处理'
        elif warning and warning.status == 'handled':
            governance_status = 'handled'
            governance_text = '已处理'

        latest_rect = rect_rows[0] if rect_rows else None
        timeline = [
            {
                'type': 'evaluation_submitted',
                'title': '评价已提交',
                'time': e.create_time.strftime('%Y-%m-%d %H:%M:%S') if e.create_time else '-',
                'status': 'done',
            }
        ]
        if warning:
            timeline.append(
                {
                    'type': 'warning_created',
                    'title': '系统触发预警',
                    'time': warning.create_time.strftime('%Y-%m-%d %H:%M:%S') if warning.create_time else '-',
                    'status': 'done',
                }
            )
            if warning.status == 'handled':
                timeline.append(
                    {
                        'type': 'warning_handled',
                        'title': '运营已处理',
                        'time': warning.handled_time.strftime('%Y-%m-%d %H:%M:%S') if warning.handled_time else '-',
                        'status': 'done',
                    }
                )
            else:
                timeline.append(
                    {
                        'type': 'warning_pending',
                        'title': '待运营处理',
                        'time': '-',
                        'status': 'pending',
                    }
                )

        for item in sorted(rect_rows, key=lambda x: x.id):
            timeline.append(
                {
                    'type': 'rectification',
                    'title': item.title or '整改记录',
                    'time': item.update_time.strftime('%Y-%m-%d %H:%M:%S') if item.update_time else '-',
                    'status': 'done' if item.is_public else 'processing',
                    'is_public': bool(item.is_public),
                }
            )

        rectification_list = []
        for item in rect_rows:
            images = item.images_json if isinstance(item.images_json, list) else []
            rectification_list.append(
                {
                    'id': item.id,
                    'title': item.title or '整改记录',
                    'issue_desc': item.issue_desc or '',
                    'action_detail': item.action_detail or '',
                    'images': images,
                    'is_public': bool(item.is_public),
                    'update_time': item.update_time.strftime('%Y-%m-%d %H:%M:%S') if item.update_time else '-',
                }
            )

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
            'governance_status': governance_status,
            'governance_text': governance_text,
            'warning_id': int(warning.id) if warning else 0,
            'rectification_count': len(rect_rows),
            'latest_rectification_title': latest_rect.title if latest_rect else '',
            'latest_rectification_time': latest_rect.update_time.strftime('%Y-%m-%d %H:%M:%S') if latest_rect and latest_rect.update_time else '',
            'latest_rectification_public': bool(latest_rect.is_public) if latest_rect else False,
            'governance_timeline': timeline,
            'rectifications': rectification_list,
        })
        
    if governance_filter in ('pending', 'handled', 'normal'):
        result = [item for item in result if (item.get('governance_status') or '') == governance_filter]

    if with_pagination:
        total = len(result)
        start = (page - 1) * limit
        end = start + limit
        return api_success(
            {
                'list': result[start:end],
                'total': total,
                'page': page,
                'limit': limit,
                'pages': math.ceil(total / limit) if total else 0,
            },
            msg='查询成功',
        )

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
    page = max(1, _safe_int(request.args.get('page'), 1) or 1)
    limit = max(1, min(50, _safe_int(request.args.get('limit'), 20) or 20))

    query = Note.query.filter_by(user_id=user_id)
    total = query.count()
    rows = query.order_by(Note.create_time.desc()).offset((page - 1) * limit).limit(limit).all()
    result = []
    for n in rows:
        raw_content = str(n.content or '')
        has_inline_data_image = 'data:image/' in raw_content
        images = [] if has_inline_data_image else _extract_images_from_text(raw_content)
        display_content = '' if has_inline_data_image else _strip_images_from_text(raw_content)
        safe_raw_content = '' if has_inline_data_image else raw_content
        result.append(
            {
                'id': n.id,
                'title': n.title,
                'content': display_content,
                'raw_content': safe_raw_content,
                'images': images,
                'status': '已发布' if n.status == 'published' else n.status,
                'like_count': int(n.like_count or 0),
                'create_time': n.create_time.strftime('%Y-%m-%d %H:%M:%S'),
                'update_time': n.update_time.strftime('%Y-%m-%d %H:%M:%S'),
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


@app.route('/api/my_notes', methods=['POST'])
@login_required()
def create_my_note():
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    canteen_id = _safe_int(data.get('canteen_id'))
    window_id = _safe_int(data.get('window_id'))
    note_tags = _safe_tag_list(data.get('tags'))
    note_images = _normalize_images(data.get('images'))

    safe_note_images = []
    for src in note_images:
        value = str(src or '').strip()
        if not value:
            continue
        if value.lower().startswith('data:image/'):
            saved_url = _save_note_data_image(value)
            if saved_url:
                safe_note_images.append(saved_url)
            continue
        if value.startswith('/') or value.startswith('http://') or value.startswith('https://'):
            safe_note_images.append(value[:1000])

    if len(title) < 2:
        return api_error('标题至少2个字')
    if len(title) > 200:
        return api_error('标题最多200个字')
    if len(content) < 5:
        return api_error('内容至少5个字')
    if len(content) > 5000:
        return api_error('内容最多5000个字')
    if 'data:image/' in content.lower():
        return api_error('正文不支持内嵌base64图片，请先上传图片后再发布')

    canteen = None
    if canteen_id:
        canteen = db.session.get(Canteen, canteen_id)
        if not canteen:
            return api_error('所选食堂不存在')
        if _safe_int(canteen.campus_id, 0) != _current_campus_id():
            return api_error('无权关联其他校区食堂', code=403, http_status=403)
        if window_id:
            window = db.session.get(Window, window_id)
            if not window or _safe_int(window.canteen_id, 0) != canteen_id:
                return api_error('所选窗口不属于该食堂')

    cfg = _get_or_create_system_config()
    note_status = 'pending' if cfg.audit_enabled else 'published'
    metadata_lines = []
    if note_tags:
        metadata_lines.append('标签：' + '、'.join(note_tags[:8]))
    if safe_note_images:
        metadata_lines.append(f'配图：{len(safe_note_images)}张')
    normalized_content = content
    image_markdown_lines = [f'![配图{i + 1}]({src})' for i, src in enumerate(safe_note_images[:9])]
    if metadata_lines or image_markdown_lines:
        normalized_content = content + '\n\n' + '\n'.join(metadata_lines + image_markdown_lines)

    row = Note(user_id=user_id, title=title, content=normalized_content, status=note_status)
    db.session.add(row)
    db.session.commit()

    if canteen:
        user = db.session.get(User, user_id)
        username = (user.nickname if user else '') or (user.username if user else '校园用户')
        share_content = f"{title}\n{content}".strip()
        share_image = safe_note_images[0] if safe_note_images else ''
        db.session.execute(
            text(
                '''
                INSERT INTO user_shares(canteen_id, user_id, username, content, image_url, create_time)
                VALUES(:canteen_id, :user_id, :username, :content, :image_url, :create_time)
                '''
            ),
            {
                'canteen_id': canteen_id,
                'user_id': user_id,
                'username': username,
                'content': share_content,
                'image_url': share_image,
                'create_time': datetime.now(),
            },
        )
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
    note_tags = _safe_tag_list(data.get('tags'))
    note_images = _normalize_images(data.get('images'))

    safe_note_images = []
    for src in note_images:
        value = str(src or '').strip()
        if not value:
            continue
        if value.lower().startswith('data:image/'):
            saved_url = _save_note_data_image(value)
            if saved_url:
                safe_note_images.append(saved_url)
            continue
        if value.startswith('/') or value.startswith('http://') or value.startswith('https://'):
            safe_note_images.append(value[:1000])

    if len(title) < 2:
        return api_error('标题至少2个字')
    if len(title) > 200:
        return api_error('标题最多200个字')
    if len(content) < 5:
        return api_error('内容至少5个字')
    if len(content) > 5000:
        return api_error('内容最多5000个字')
    if 'data:image/' in content.lower():
        return api_error('正文不支持内嵌base64图片，请先上传图片后再保存')

    metadata_lines = []
    if note_tags:
        metadata_lines.append('标签：' + '、'.join(note_tags[:8]))
    if safe_note_images:
        metadata_lines.append(f'配图：{len(safe_note_images)}张')

    image_markdown_lines = [f'![配图{i + 1}]({src})' for i, src in enumerate(safe_note_images[:9])]
    normalized_content = content
    if metadata_lines or image_markdown_lines:
        normalized_content = content + '\n\n' + '\n'.join(metadata_lines + image_markdown_lines)

    row.title = title
    row.content = normalized_content
    db.session.commit()
    return api_success({'id': row.id}, msg='更新成功')


@app.route('/api/my_notes/<int:note_id>', methods=['GET'])
@login_required()
def get_my_note_detail(note_id):
    user_id = session.get('user_id')
    row = Note.query.filter_by(id=note_id, user_id=user_id).first()
    if not row:
        return api_error('笔记不存在', code=404, http_status=404)

    raw_content = str(row.content or '')
    has_inline_data_image = 'data:image/' in raw_content
    images = [] if has_inline_data_image else _extract_images_from_text(raw_content)
    return api_success(
        {
            'id': row.id,
            'title': row.title,
            'content': '' if has_inline_data_image else _strip_images_from_text(raw_content),
            'raw_content': '' if has_inline_data_image else raw_content,
            'images': images,
            'status': '已发布' if row.status == 'published' else row.status,
            'like_count': int(row.like_count or 0),
            'create_time': row.create_time.strftime('%Y-%m-%d %H:%M:%S') if row.create_time else '-',
            'update_time': row.update_time.strftime('%Y-%m-%d %H:%M:%S') if row.update_time else '-',
        },
        msg='查询成功',
    )


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
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    try:
        page = max(1, int(request.args.get('page', 1)))
        limit = max(1, min(50, int(request.args.get('limit', 10))))
    except (TypeError, ValueError):
        return api_error('分页参数不合法')

    requested_campus_id = _safe_int(request.args.get('campus_id'))
    scoped_campus_id, scope_error = _resolve_campus_scope(requested_campus_id)
    if scope_error:
        return scope_error

    keyword = (request.args.get('keyword') or '').strip()

    query = User.query
    if scoped_campus_id:
        query = query.filter(User.campus_id == scoped_campus_id)
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
        canteen = db.session.get(Canteen, _safe_int(getattr(item, 'operator_canteen_id', None))) if getattr(item, 'operator_canteen_id', None) else None
        campus = db.session.get(Campus, _safe_int(getattr(item, 'campus_id', 1), 1) or 1)
        data.append(
            {
                'id': item.id,
                'username': item.username,
                'nickname': item.nickname,
                'phone': item.phone,
                'role': item.role,
                'role_name': _role_code_to_name(item.role),
                'campus_id': _safe_int(getattr(item, 'campus_id', 1), 1) or 1,
                'campus_name': campus.name if campus else '默认校区',
                'operator_canteen_id': _safe_int(getattr(item, 'operator_canteen_id', None)),
                'operator_canteen_name': canteen.name if canteen else '',
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
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '123456').strip()
    nickname = (data.get('nickname') or '').strip()
    phone = (data.get('phone') or '').strip()
    role = _normalize_role(data.get('role_id'), data.get('role'))
    operator_canteen_id = _safe_int(data.get('operator_canteen_id') or data.get('canteen_id'))
    campus_id = _safe_int(data.get('campus_id'), 1) or 1

    if len(username) < 2 or len(username) > 20:
        return api_error('用户名长度需在2-20位之间')
    if len(password) < 6:
        return api_error('密码长度至少6位')
    if phone and (not phone.isdigit() or len(phone) != 11):
        return api_error('手机号需为11位数字')
    if User.query.filter_by(username=username).first():
        return api_error('用户名已存在', code=409, http_status=409)

    campus = db.session.get(Campus, campus_id)
    if not campus:
        return api_error('所属校区不存在', code=404, http_status=404)

    if role == 'operator':
        if not operator_canteen_id:
            return api_error('食堂运营账号必须绑定食堂')
        canteen = db.session.get(Canteen, operator_canteen_id)
        if not canteen:
            return api_error('绑定食堂不存在', code=404, http_status=404)
        campus_id = _safe_int(getattr(canteen, 'campus_id', campus_id), campus_id) or campus_id
    else:
        operator_canteen_id = None

    user = User(
        username=username,
        password=generate_password_hash(password),
        nickname=nickname or None,
        phone=phone or None,
        role=role,
        campus_id=campus_id,
        operator_canteen_id=operator_canteen_id,
    )
    db.session.add(user)
    db.session.commit()
    return api_success({'id': user.id}, msg='新增成功')


@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@admin_login_required
def admin_update_user(user_id):
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    user = db.session.get(User, user_id)
    if not user:
        return api_error('用户不存在', code=404, http_status=404)

    data = request.get_json(silent=True) or {}
    password = (data.get('password') or '').strip()
    nickname = (data.get('nickname') or '').strip()
    phone = (data.get('phone') or '').strip()
    role = _normalize_role(data.get('role_id'), data.get('role')) if ('role_id' in data or 'role' in data) else None
    operator_canteen_id = _safe_int(data.get('operator_canteen_id') or data.get('canteen_id')) if ('operator_canteen_id' in data or 'canteen_id' in data) else None
    campus_id = _safe_int(data.get('campus_id'), _safe_int(getattr(user, 'campus_id', 1), 1) or 1) or _safe_int(getattr(user, 'campus_id', 1), 1) or 1

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

    if 'campus_id' in data:
        campus = db.session.get(Campus, campus_id)
        if not campus:
            return api_error('所属校区不存在', code=404, http_status=404)
        user.campus_id = campus_id

    target_role = role if role is not None else user.role
    if target_role == 'operator':
        bound_canteen_id = operator_canteen_id if operator_canteen_id is not None else _safe_int(getattr(user, 'operator_canteen_id', None))
        if not bound_canteen_id:
            return api_error('食堂运营账号必须绑定食堂')
        canteen = db.session.get(Canteen, bound_canteen_id)
        if not canteen:
            return api_error('绑定食堂不存在', code=404, http_status=404)
        if 'campus_id' in data and _safe_int(getattr(canteen, 'campus_id', campus_id), campus_id) != campus_id:
            return api_error('运营账号所属校区必须与绑定食堂一致')
        user.campus_id = _safe_int(getattr(canteen, 'campus_id', user.campus_id), user.campus_id) or user.campus_id
        user.operator_canteen_id = bound_canteen_id
    elif role is not None:
        user.operator_canteen_id = None

    db.session.commit()
    return api_success(msg='更新成功')


@app.route('/api/admin/users/<int:user_id>', methods=['GET'])
@admin_login_required
def admin_get_user_detail(user_id):
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

    user = db.session.get(User, user_id)
    if not user:
        return api_error('用户不存在', code=404, http_status=404)
    canteen = db.session.get(Canteen, _safe_int(getattr(user, 'operator_canteen_id', None))) if getattr(user, 'operator_canteen_id', None) else None
    campus = db.session.get(Campus, _safe_int(getattr(user, 'campus_id', 1), 1) or 1)
    return api_success(
        {
            'id': user.id,
            'username': user.username,
            'nickname': user.nickname,
            'phone': user.phone,
            'role': user.role,
            'campus_id': _safe_int(getattr(user, 'campus_id', 1), 1) or 1,
            'campus_name': campus.name if campus else '默认校区',
            'operator_canteen_id': _safe_int(getattr(user, 'operator_canteen_id', None)),
            'operator_canteen_name': canteen.name if canteen else '',
            'create_time': user.create_time.strftime('%Y-%m-%d %H:%M:%S') if user.create_time else '-',
        },
        msg='查询成功',
    )


@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_login_required
def admin_delete_user(user_id):
    admin_only_error = _ensure_admin_only()
    if admin_only_error:
        return admin_only_error

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
        images = _extract_images_from_text(item.content)
        result.append(
            {
                'id': item.id,
                'title': item.title,
                'content': _strip_images_from_text(item.content),
                'raw_content': item.content,
                'status': _note_status_to_code(item.status),
                'images': images,
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
    images = _extract_images_from_text(item.content)
    return api_success(
        {
            'id': item.id,
            'title': item.title,
            'content': _strip_images_from_text(item.content),
            'raw_content': item.content,
            'status': _note_status_to_code(item.status),
            'images': images,
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
    requested_canteen_id = _safe_int(request.args.get('canteen_id'))
    scoped_canteen_id, scope_error = _resolve_canteen_scope(requested_canteen_id)
    if scope_error:
        return scope_error

    payload = _build_operation_dashboard_payload(scoped_canteen_id)
    trend = payload.get('30day_score_trend', [])
    warnings = payload.get('bad_review_list', [])
    hot_dishes = payload.get('hot_dishes_top10', [])

    return api_success(
        {
            'stats': {
                'today_eval_count': payload.get('today_evaluation_count', 0),
                'week_avg_score': payload.get('week_avg_score', 0.0),
                'month_eval_count': payload.get('month_evaluation_count', 0),
                'month_avg_score': payload.get('month_avg_score', 0.0),
                'month_count_mom_pct': payload.get('month_count_mom_pct', 0.0),
                'month_count_yoy_pct': payload.get('month_count_yoy_pct', 0.0),
                'month_avg_mom_delta': payload.get('month_avg_mom_delta', 0.0),
                'month_avg_yoy_delta': payload.get('month_avg_yoy_delta', 0.0),
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
    requested_canteen_id = _safe_int(request.args.get('canteen_id'))
    scoped_canteen_id, scope_error = _resolve_canteen_scope(requested_canteen_id)
    if scope_error:
        return scope_error
    _scan_warning_sla_and_notify(scoped_canteen_id)
    return api_success(_build_operation_dashboard_payload(scoped_canteen_id), msg='查询成功')


@app.route('/api/admin/sla/todos', methods=['GET'])
@admin_login_required
def admin_sla_todos():
    requested_canteen_id = _safe_int(request.args.get('canteen_id'))
    scoped_canteen_id, scope_error = _resolve_canteen_scope(requested_canteen_id)
    if scope_error:
        return scope_error

    _scan_warning_sla_and_notify(scoped_canteen_id)

    query = OperatorWarning.query.filter(OperatorWarning.status == 'pending')
    if scoped_canteen_id:
        query = query.filter(OperatorWarning.canteen_id == scoped_canteen_id)
    rows = query.order_by(OperatorWarning.create_time.asc()).all()

    overdue_rows = []
    escalated_rows = []
    normal_rows = []
    for row in rows:
        item = _serialize_warning(row)
        if item['sla_level'] == 'escalated':
            escalated_rows.append(item)
        elif item['sla_level'] == 'overdue':
            overdue_rows.append(item)
        else:
            normal_rows.append(item)

    return api_success(
        {
            'canteen_id': scoped_canteen_id or 0,
            'summary': {
                'pending_total': len(rows),
                'overdue_count': len(overdue_rows),
                'escalated_count': len(escalated_rows),
            },
            'todo_list': escalated_rows + overdue_rows + normal_rows,
            'sla_config': {
                'first_response_hours': SLA_FIRST_RESPONSE_HOURS,
                'escalate_hours': SLA_ESCALATE_HOURS,
            },
        },
        msg='查询成功',
    )


@app.route('/api/operation/bad_reviews/<int:warning_id>/handle', methods=['POST'])
@admin_login_required
def operation_handle_bad_review(warning_id):
    row = db.session.get(OperatorWarning, warning_id)
    if not row:
        return api_error('差评预警不存在', code=404, http_status=404)
    access_error = _ensure_resource_canteen_access(row.canteen_id)
    if access_error:
        return access_error
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
    requested_canteen_id = _safe_int(request.args.get('canteen_id'))
    scoped_canteen_id, scope_error = _resolve_canteen_scope(requested_canteen_id)
    if scope_error:
        return scope_error

    query = OperatorWarning.query
    if scoped_canteen_id:
        query = query.filter(OperatorWarning.canteen_id == scoped_canteen_id)
    rows = query.order_by(OperatorWarning.create_time.desc()).all()
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
    access_error = _ensure_resource_canteen_access(row.canteen_id)
    if access_error:
        return access_error

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

    requested_canteen_id = _safe_int(request.args.get('canteen_id'))
    scoped_canteen_id, scope_error = _resolve_canteen_scope(requested_canteen_id)
    if scope_error:
        return scope_error

    query = Dish.query
    if scoped_canteen_id:
        query = query.join(Window, Window.id == Dish.window_id).filter(Window.canteen_id == scoped_canteen_id)
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
                'canteen_id': dish.window.canteen_id if dish.window else 0,
                'canteen_name': dish.window.canteen.name if dish.window and dish.window.canteen else '-',
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
    access_error = _ensure_resource_canteen_access(window.canteen_id)
    if access_error:
        return access_error

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


@app.route('/api/admin/dishes/<int:dish_id>/image', methods=['POST'])
@admin_login_required
def admin_upload_dish_image(dish_id):
    row = db.session.get(Dish, dish_id)
    if not row:
        return api_error('菜品不存在', code=404, http_status=404)

    access_error = _ensure_resource_canteen_access(row.window.canteen_id if row.window else None)
    if access_error:
        return access_error

    upload = request.files.get('file')
    if not upload:
        return api_error('请上传图片文件')

    ext = _safe_image_extension(upload.filename or '')
    if ext not in {'jpg', 'png', 'webp'}:
        return api_error('仅支持 jpg/png/webp 格式图片')

    file_bytes = upload.read()
    if not file_bytes:
        return api_error('上传文件为空')
    if len(file_bytes) > DISH_IMAGE_MAX_SIZE:
        return api_error('图片大小不能超过 2MB')

    compressed_bytes, compress_error = _compress_dish_image(file_bytes, ext)
    if compress_error:
        return api_error(compress_error)

    old_url = row.img_url or ''
    new_url = _save_dish_image_file(row.id, compressed_bytes, ext)
    row.img_url = new_url
    db.session.commit()

    if old_url and old_url != new_url:
        _delete_dish_image_file(old_url)

    return api_success({'dish_id': row.id, 'img_url': new_url}, msg='上传成功')


@app.route('/api/admin/dishes/<int:dish_id>/image', methods=['DELETE'])
@admin_login_required
def admin_delete_dish_image(dish_id):
    row = db.session.get(Dish, dish_id)
    if not row:
        return api_error('菜品不存在', code=404, http_status=404)

    access_error = _ensure_resource_canteen_access(row.window.canteen_id if row.window else None)
    if access_error:
        return access_error

    old_url = row.img_url or ''
    row.img_url = None
    db.session.commit()
    if old_url:
        _delete_dish_image_file(old_url)
    return api_success(msg='图片已删除')


@app.route('/api/admin/dishes/<int:dish_id>', methods=['PUT'])
@admin_login_required
def admin_update_dish(dish_id):
    row = db.session.get(Dish, dish_id)
    if not row:
        return api_error('菜品不存在', code=404, http_status=404)
    access_error = _ensure_resource_canteen_access(row.window.canteen_id if row.window else None)
    if access_error:
        return access_error

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
    old_img_url = row.img_url or ''
    if 'img_url' in data:
        row.img_url = (data.get('img_url') or '').strip() or None
    if 'is_active' in data:
        row.is_active = _to_bool(data.get('is_active'), row.is_active)

    db.session.commit()
    if old_img_url and old_img_url != (row.img_url or ''):
        _delete_dish_image_file(old_img_url)
    return api_success(msg='更新成功')


@app.route('/api/admin/dishes/<int:dish_id>', methods=['DELETE'])
@admin_login_required
def admin_delete_dish(dish_id):
    row = db.session.get(Dish, dish_id)
    if not row:
        return api_error('菜品不存在', code=404, http_status=404)
    access_error = _ensure_resource_canteen_access(row.window.canteen_id if row.window else None)
    if access_error:
        return access_error
    old_img_url = row.img_url or ''
    db.session.delete(row)
    db.session.commit()
    if old_img_url:
        _delete_dish_image_file(old_img_url)
    return api_success(msg='删除成功')


@app.route('/api/admin/dishes/<int:dish_id>/toggle', methods=['POST'])
@admin_login_required
def admin_toggle_dish_status(dish_id):
    row = db.session.get(Dish, dish_id)
    if not row:
        return api_error('菜品不存在', code=404, http_status=404)
    access_error = _ensure_resource_canteen_access(row.window.canteen_id if row.window else None)
    if access_error:
        return access_error
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
            access_error = _ensure_resource_canteen_access(window.canteen_id)
            if access_error:
                errors.append(f'第{idx}行: 无权导入到该窗口')
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

    requested_canteen_id = _safe_int(request.args.get('canteen_id'))
    scoped_canteen_id, scope_error = _resolve_canteen_scope(requested_canteen_id)
    if scope_error:
        return scope_error

    dish_ids = db.session.query(EvaluationDish.dish_id).filter(EvaluationDish.dish_id > 0).group_by(EvaluationDish.dish_id).all()
    all_items = []
    for (dish_id,) in dish_ids:
        dish = db.session.get(Dish, dish_id)
        if not dish:
            continue
        if scoped_canteen_id and (not dish.window or dish.window.canteen_id != scoped_canteen_id):
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
    access_error = _ensure_resource_canteen_access(dish.window.canteen_id if dish.window else None)
    if access_error:
        return access_error

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
    dish_id = _safe_int(request.args.get('dish_id'))
    if not dish_id:
        return api_error('缺少dish_id')
    dish = db.session.get(Dish, dish_id)
    campus_id = _safe_int(request.args.get('campus_id'))
        
    # 查询关联表
    dish_query = EvaluationDish.query.filter(EvaluationDish.dish_id == dish_id)
    if campus_id:
        dish_query = dish_query.join(EvaluationMain, EvaluationMain.id == EvaluationDish.evaluation_id).filter(EvaluationMain.campus_id == campus_id)
    dish_evals = dish_query.all()
    
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
            'dish': {
                'id': int(dish.id or 0) if dish else dish_id,
                'name': dish.name if dish else '',
                'price': float(dish.price or 0) if dish else 0,
                'img_url': dish.img_url or '' if dish else '',
            },
            'stats': {
                'avg_scores': avg_scores,
                'total_count': count
            }
        })


@app.route('/api/admin/risk_evaluations', methods=['GET'])
@admin_login_required
def admin_get_risk_evaluations():
    status = (request.args.get('status') or '').strip().lower()
    min_score = max(0, min(100, _safe_int(request.args.get('min_score'), 0) or 0))
    page = max(1, _safe_int(request.args.get('page'), 1) or 1)
    limit = max(1, min(50, _safe_int(request.args.get('limit'), 20) or 20))
    requested_canteen_id = _safe_int(request.args.get('canteen_id'))
    scoped_canteen_id, scope_error = _resolve_canteen_scope(requested_canteen_id)
    if scope_error:
        return scope_error

    query = EvaluationRiskFlag.query.filter(EvaluationRiskFlag.campus_id == _current_campus_id())
    if status in ('pending', 'approved', 'rejected', 'watch'):
        query = query.filter(EvaluationRiskFlag.status == status)
    if min_score:
        query = query.filter(EvaluationRiskFlag.risk_score >= min_score)
    if scoped_canteen_id:
        query = query.filter(EvaluationRiskFlag.canteen_id == scoped_canteen_id)

    total = query.count()
    rows = query.order_by(EvaluationRiskFlag.risk_score.desc(), EvaluationRiskFlag.id.desc()).offset((page - 1) * limit).limit(limit).all()
    return api_success(
        {
            'list': [_serialize_risk_flag(row) for row in rows],
            'total': total,
            'page': page,
            'limit': limit,
            'pages': math.ceil(total / limit) if total else 0,
        },
        msg='查询成功',
    )


@app.route('/api/admin/risk_evaluations/scan', methods=['POST'])
@admin_login_required
def admin_scan_risk_evaluations():
    requested_canteen_id = _safe_int((request.get_json(silent=True) or {}).get('canteen_id'))
    scoped_canteen_id, scope_error = _resolve_canteen_scope(requested_canteen_id)
    if scope_error:
        return scope_error

    query = EvaluationMain.query.filter(EvaluationMain.campus_id == _current_campus_id())
    if scoped_canteen_id:
        query = query.filter(EvaluationMain.canteen_id == scoped_canteen_id)
    rows = query.order_by(EvaluationMain.id.desc()).limit(300).all()

    touched = 0
    for row in rows:
        _upsert_eval_risk_flag(row)
        touched += 1
    db.session.commit()
    return api_success({'scanned': touched}, msg='异常评分扫描完成')


@app.route('/api/admin/risk_evaluations/<int:risk_id>/review', methods=['POST'])
@admin_login_required
def admin_review_risk_evaluation(risk_id):
    row = db.session.get(EvaluationRiskFlag, risk_id)
    if not row or row.campus_id != _current_campus_id():
        return api_error('风险记录不存在', code=404, http_status=404)
    access_error = _ensure_resource_canteen_access(row.canteen_id)
    if access_error:
        return access_error

    data = request.get_json(silent=True) or {}
    decision = (data.get('decision') or '').strip().lower()
    if decision not in ('approved', 'rejected', 'watch'):
        return api_error('无效处理动作')

    row.status = decision
    row.review_note = (data.get('note') or '').strip()[:500]
    reviewer = _current_user()
    row.reviewer_id = reviewer.id if reviewer else None
    row.reviewed_time = datetime.now()
    row.update_time = datetime.now()
    db.session.commit()
    return api_success(_serialize_risk_flag(row), msg='复核完成')


@app.route('/api/admin/risk_evaluations/<int:risk_id>/work_order', methods=['POST'])
@admin_login_required
def admin_create_work_order_from_risk(risk_id):
    risk = db.session.get(EvaluationRiskFlag, risk_id)
    if not risk or risk.campus_id != _current_campus_id():
        return api_error('风险记录不存在', code=404, http_status=404)
    access_error = _ensure_resource_canteen_access(risk.canteen_id)
    if access_error:
        return access_error

    data = request.get_json(silent=True) or {}
    due_time = _parse_datetime_text(data.get('due_time') or '')
    if not due_time:
        due_time = datetime.now() + timedelta(hours=WORK_ORDER_DEFAULT_SLA_HOURS)

    actor = _current_user()
    order = RectificationWorkOrder(
        campus_id=risk.campus_id,
        source_type='risk_flag',
        source_id=risk.id,
        canteen_id=risk.canteen_id,
        window_id=risk.window_id,
        title=(data.get('title') or f'异常评价整改#{risk.id}').strip()[:200],
        issue_desc=(data.get('issue_desc') or '来自异常评价检测，请核查窗口服务与评分真实性。').strip(),
        priority=(data.get('priority') or ('high' if (risk.risk_score or 0) >= 70 else 'medium')).strip().lower(),
        status='pending',
        assignee_id=_safe_int(data.get('assignee_id')),
        due_time=due_time,
        created_by=actor.id if actor else None,
    )
    db.session.add(order)
    db.session.flush()
    _append_work_order_log(order, 'create', '', 'pending', '由异常评价自动建单')
    db.session.commit()
    return api_success(_serialize_work_order(order), msg='工单创建成功')


@app.route('/api/admin/work_orders', methods=['GET'])
@admin_login_required
def admin_get_work_orders():
    status = (request.args.get('status') or '').strip().lower()
    page = max(1, _safe_int(request.args.get('page'), 1) or 1)
    limit = max(1, min(50, _safe_int(request.args.get('limit'), 20) or 20))
    overdue = (request.args.get('overdue') or '').strip().lower()
    requested_canteen_id = _safe_int(request.args.get('canteen_id'))
    scoped_canteen_id, scope_error = _resolve_canteen_scope(requested_canteen_id)
    if scope_error:
        return scope_error

    query = RectificationWorkOrder.query.filter(RectificationWorkOrder.campus_id == _current_campus_id())
    if status in ('pending', 'processing', 'review', 'completed', 'archived'):
        query = query.filter(RectificationWorkOrder.status == status)
    if overdue in ('1', 'true', 'yes'):
        query = query.filter(RectificationWorkOrder.is_overdue == True)
    if scoped_canteen_id:
        query = query.filter(RectificationWorkOrder.canteen_id == scoped_canteen_id)

    total = query.count()
    rows = query.order_by(RectificationWorkOrder.is_overdue.desc(), RectificationWorkOrder.id.desc()).offset((page - 1) * limit).limit(limit).all()
    return api_success(
        {
            'list': [_serialize_work_order(row) for row in rows],
            'total': total,
            'page': page,
            'limit': limit,
            'pages': math.ceil(total / limit) if total else 0,
        },
        msg='查询成功',
    )


@app.route('/api/admin/work_orders', methods=['POST'])
@admin_login_required
def admin_create_work_order():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return api_error('工单标题不能为空')

    canteen_id = _safe_int(data.get('canteen_id'))
    window_id = _safe_int(data.get('window_id'))
    access_error = _ensure_resource_canteen_access(canteen_id)
    if access_error:
        return access_error

    due_time = _parse_datetime_text(data.get('due_time') or '')
    if not due_time:
        due_time = datetime.now() + timedelta(hours=WORK_ORDER_DEFAULT_SLA_HOURS)

    actor = _current_user()
    row = RectificationWorkOrder(
        campus_id=_current_campus_id(),
        source_type=(data.get('source_type') or 'manual').strip()[:30],
        source_id=_safe_int(data.get('source_id'), 0) or 0,
        canteen_id=canteen_id,
        window_id=window_id,
        title=title[:200],
        issue_desc=(data.get('issue_desc') or '').strip(),
        priority=(data.get('priority') or 'medium').strip().lower(),
        status='pending',
        assignee_id=_safe_int(data.get('assignee_id')),
        due_time=due_time,
        created_by=actor.id if actor else None,
    )
    db.session.add(row)
    db.session.flush()
    _append_work_order_log(row, 'create', '', 'pending', '手工创建工单')
    db.session.commit()
    return api_success(_serialize_work_order(row), msg='工单创建成功')


@app.route('/api/admin/work_orders/<int:order_id>/transition', methods=['POST'])
@admin_login_required
def admin_transition_work_order(order_id):
    row = db.session.get(RectificationWorkOrder, order_id)
    if not row or row.campus_id != _current_campus_id():
        return api_error('工单不存在', code=404, http_status=404)
    access_error = _ensure_resource_canteen_access(row.canteen_id)
    if access_error:
        return access_error

    data = request.get_json(silent=True) or {}
    action = (data.get('action') or '').strip().lower()
    note = (data.get('note') or '').strip()[:500]
    from_status = row.status
    now = datetime.now()
    transition_map = {
        'accept': 'processing',
        'start': 'processing',
        'to_review': 'review',
        'complete': 'completed',
        'archive': 'archived',
        'reopen': 'processing',
    }
    if action not in transition_map:
        return api_error('无效流转动作')

    to_status = transition_map[action]
    row.status = to_status
    row.update_time = now
    if to_status == 'processing' and not row.started_time:
        row.started_time = now
    if to_status == 'review':
        row.review_time = now
    if to_status == 'completed':
        row.completed_time = now
    if to_status == 'archived':
        row.archived_time = now

    assignee_id = _safe_int(data.get('assignee_id'))
    if assignee_id:
        row.assignee_id = assignee_id

    _append_work_order_log(row, action, from_status, to_status, note)
    db.session.commit()
    return api_success(_serialize_work_order(row), msg='流转成功')


@app.route('/api/admin/work_orders/stats', methods=['GET'])
@admin_login_required
def admin_work_order_stats():
    requested_canteen_id = _safe_int(request.args.get('canteen_id'))
    scoped_canteen_id, scope_error = _resolve_canteen_scope(requested_canteen_id)
    if scope_error:
        return scope_error

    _scan_work_order_sla(scoped_canteen_id)
    query = RectificationWorkOrder.query.filter(RectificationWorkOrder.campus_id == _current_campus_id())
    if scoped_canteen_id:
        query = query.filter(RectificationWorkOrder.canteen_id == scoped_canteen_id)

    rows = query.all()
    status_counter = {'pending': 0, 'processing': 0, 'review': 0, 'completed': 0, 'archived': 0}
    overdue = 0
    for row in rows:
        status_key = row.status if row.status in status_counter else 'pending'
        status_counter[status_key] += 1
        if row.is_overdue:
            overdue += 1

    return api_success(
        {
            'total': len(rows),
            'overdue': overdue,
            'status_counter': status_counter,
        },
        msg='查询成功',
    )


@app.route('/api/admin/work_orders/sla_scan', methods=['POST'])
@admin_login_required
def admin_work_order_sla_scan():
    requested_canteen_id = _safe_int((request.get_json(silent=True) or {}).get('canteen_id'))
    scoped_canteen_id, scope_error = _resolve_canteen_scope(requested_canteen_id)
    if scope_error:
        return scope_error
    touched = _scan_work_order_sla(scoped_canteen_id)
    return api_success({'touched': touched}, msg='SLA扫描完成')


@app.route('/api/notes', methods=['GET'])
def get_notes():
    fallback_images = [
        '/static/img/note-cover-1.svg',
        '/static/img/note-cover-2.svg',
        '/static/img/note-cover-3.svg',
        '/static/img/note-cover-4.svg',
        '/static/img/food-hero.jpg',
        '/static/img/hero-bg.jpg',
    ]

    notes = (
        Note.query.filter(Note.status == 'published', Note.campus_id == _current_campus_id()).order_by(Note.create_time.desc())
        .limit(20)
        .all()
    )
    result = []
    for n in notes:
        user = db.session.get(User, n.user_id)
        raw_content = str(n.content or '')
        # 避免 data URI 大体积内容触发高成本正则，首页列表仅需要封面图。
        if 'data:image/' in raw_content:
            images = []
        else:
            images = _extract_images_from_text(raw_content)
        if not images:
            images = [fallback_images[n.id % len(fallback_images)]]
        result.append(
            {
                'id': n.id,
                'title': n.title,
                'images': images,
                'is_anonymous': False,
                'user_id': n.user_id,
                'username': user.username if user else '用户',
                'like_count': int(n.like_count or 0),
                'remark': '',
                'create_time': n.create_time.strftime('%Y-%m-%d %H:%M:%S'),
            }
        )
    return api_success({'list': result}, msg='查询成功')


@app.route('/api/notes/<int:note_id>', methods=['GET'])
def get_note_detail(note_id):
    item = (
        Note.query.filter(
            Note.id == note_id,
            Note.status == 'published',
            Note.campus_id == _current_campus_id(),
        )
        .first()
    )
    if not item:
        return api_error('笔记不存在', code=404, http_status=404)

    user = db.session.get(User, item.user_id)
    raw_content = str(item.content or '')
    if 'data:image/' in raw_content:
        images = []
    else:
        images = _extract_images_from_text(raw_content)

    return api_success(
        {
            'id': item.id,
            'title': item.title,
            'content': _strip_images_from_text(raw_content),
            'raw_content': '' if 'data:image/' in raw_content else raw_content,
            'images': images,
            'is_anonymous': False,
            'user_id': item.user_id,
            'username': user.username if user else '用户',
            'like_count': int(item.like_count or 0),
            'star_count': 0,
            'comment_count': 0,
            'create_time': item.create_time.strftime('%Y-%m-%d %H:%M:%S') if item.create_time else '-',
        },
        msg='查询成功',
    )

# --- 初始化命令 ---
@app.cli.command("init-db")
def init_db_command():
    _ensure_schema_columns()
    ensure_default_admin_operator_accounts()
    print("数据库表结构已创建")

if __name__ == '__main__':
    with app.app_context():
        _ensure_schema_columns()
        ensure_default_admin_operator_accounts()
    app.run(debug=True, port=5000)
