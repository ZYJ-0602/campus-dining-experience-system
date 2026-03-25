import os

# 基础配置
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# 数据库文件路径 (上一级目录的database文件夹)
DB_PATH = os.path.join(os.path.dirname(BASE_DIR), 'database', 'canteen.db')

class Config:
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DB_PATH}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'dev-secret-key'
