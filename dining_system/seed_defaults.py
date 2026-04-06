from werkzeug.security import generate_password_hash

from extensions import db
from models import Campus, Canteen, User


DEFAULT_LOGIN_PASSWORD = '123456'
DEFAULT_ADMIN_USERNAME = 'admin'
DEFAULT_OPERATOR_USERNAME = 'operator'


def _get_or_create_default_campus():
    campus = Campus.query.order_by(Campus.id.asc()).first()
    if campus:
        return campus, False

    campus = Campus(name='默认校区', code='campus-1', is_active=True, sort_order=1)
    db.session.add(campus)
    db.session.flush()
    return campus, True


def _get_or_create_operator_canteen(preferred_canteen_id=None):
    if preferred_canteen_id:
        canteen = db.session.get(Canteen, preferred_canteen_id)
        if canteen:
            return canteen, False

    canteen = Canteen.query.order_by(Canteen.id.asc()).first()
    if canteen:
        return canteen, False

    campus, campus_created = _get_or_create_default_campus()
    canteen = Canteen(
        campus_id=campus.id,
        name='第一食堂',
        address='校园北区',
        business_hours='07:00-21:00',
        is_active=True,
    )
    db.session.add(canteen)
    db.session.flush()
    return canteen, True or campus_created


def _upsert_user(username, role, nickname, campus_id, password, operator_canteen_id=None):
    row = User.query.filter_by(username=username).first()
    if not row:
        db.session.add(
            User(
                username=username,
                password=generate_password_hash(password),
                role=role,
                campus_id=campus_id,
                operator_canteen_id=operator_canteen_id,
                nickname=nickname,
            )
        )
        return True

    changed = False
    if row.role != role:
        row.role = role
        changed = True
    if row.campus_id != campus_id:
        row.campus_id = campus_id
        changed = True
    if (row.nickname or '') != nickname:
        row.nickname = nickname
        changed = True
    target_operator_canteen_id = operator_canteen_id if role == 'operator' else None
    if getattr(row, 'operator_canteen_id', None) != target_operator_canteen_id:
        row.operator_canteen_id = target_operator_canteen_id
        changed = True
    return changed


def ensure_default_admin_operator_accounts(preferred_operator_canteen_id=None):
    campus, campus_created = _get_or_create_default_campus()
    canteen, canteen_created = _get_or_create_operator_canteen(preferred_operator_canteen_id)

    changed = campus_created or canteen_created
    changed |= _upsert_user(
        DEFAULT_ADMIN_USERNAME,
        'admin',
        '系统管理员',
        campus.id,
        DEFAULT_LOGIN_PASSWORD,
    )
    changed |= _upsert_user(
        DEFAULT_OPERATOR_USERNAME,
        'operator',
        '食堂运营',
        campus.id,
        DEFAULT_LOGIN_PASSWORD,
        operator_canteen_id=canteen.id,
    )

    if changed:
        db.session.commit()

    return {
        'admin_username': DEFAULT_ADMIN_USERNAME,
        'operator_username': DEFAULT_OPERATOR_USERNAME,
        'password': DEFAULT_LOGIN_PASSWORD,
        'operator_canteen_name': canteen.name,
    }
