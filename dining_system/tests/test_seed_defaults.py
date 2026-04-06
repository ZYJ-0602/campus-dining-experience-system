from app import app, db
from models import User
from seed_defaults import ensure_default_admin_operator_accounts


def test_ensure_default_admin_operator_accounts():
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', SECRET_KEY='test-secret')

    with app.app_context():
        db.drop_all()
        db.create_all()

        result = ensure_default_admin_operator_accounts()

        admin = User.query.filter_by(username='admin').first()
        operator = User.query.filter_by(username='operator').first()

        assert result['password'] == '123456'
        assert admin is not None
        assert admin.role == 'admin'
        assert operator is not None
        assert operator.role == 'operator'
        assert operator.operator_canteen_id is not None
