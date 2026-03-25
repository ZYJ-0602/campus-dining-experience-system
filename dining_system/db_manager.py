from sqlalchemy import func

from app import app
from extensions import db
from models import Dish, EvaluationMain


class DBManager:
    """兼容层：历史调用统一转发到主模型与主数据库。"""

    @staticmethod
    def get_window_dishes(window_id):
        dishes = Dish.query.filter_by(window_id=window_id).all()
        return [
            {
                'id': dish.id,
                'name': dish.name,
                'price': float(dish.price or 0),
                'create_time': '',
            }
            for dish in dishes
        ]

    @staticmethod
    def get_window_safety_info(window_id):
        # 当前主模型暂未定义食安证照表，先返回空列表以保持接口可用。
        _ = window_id
        return []

    @staticmethod
    def get_evaluation_stats(window_id):
        stats = db.session.query(
            func.count(EvaluationMain.id).label('count'),
            func.avg(EvaluationMain.comprehensive_score).label('avg_score'),
        ).filter(EvaluationMain.window_id == window_id).first()

        if not stats or int(stats.count or 0) == 0:
            return {
                'count': 0,
                'avg_score': 0.0,
            }

        return {
            'count': int(stats.count or 0),
            'avg_score': round(float(stats.avg_score or 0), 1),
        }


if __name__ == '__main__':
    with app.app_context():
        print('DBManager 已收敛到主应用模型。')
