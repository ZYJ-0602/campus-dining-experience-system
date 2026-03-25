from backend.app import app, db
from backend.models import Review

def init_data():
    print(">>> 开始初始化测试数据...")
    with app.app_context():
        # 重新创建表
        db.drop_all()
        db.create_all()
        print("    数据库表已重置。")
        
        # 这里可以插入一些预设的评价数据，但主要是为了确保DB文件生成
        print("    (暂无预设评价数据插入，主要用于生成DB文件)")
        
    print(">>> 初始化完成！请运行 backend/app.py 启动服务。")

if __name__ == '__main__':
    init_data()
