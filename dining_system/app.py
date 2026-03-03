from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-123'  # 用于加密session，随便写
# 数据库配置：直接使用当前目录下的 sqlite 文件，无需安装 MySQL
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'dining.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- 数据库模型 (Model) ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='student')  # student 或 admin

class Dish(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(200), default='img/default_dish.jpg')
    reviews = db.relationship('Review', backref='dish', lazy=True)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5分
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    dish_id = db.Column(db.Integer, db.ForeignKey('dish.id'), nullable=False)
    user = db.relationship('User', backref='reviews')

# --- 路由 (Controller) ---

@app.route('/')
def index():
    dishes = Dish.query.all()
    return render_template('index.html', dishes=dishes)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            flash('登录成功！', 'success')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'warning')
        else:
            new_user = User(username=username, password_hash=generate_password_hash(password))
            db.session.add(new_user)
            db.session.commit()
            flash('注册成功，请登录', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dish/<int:dish_id>', methods=['GET', 'POST'])
def dish_detail(dish_id):
    dish = Dish.query.get_or_404(dish_id)
    if request.method == 'POST':
        if 'user_id' not in session:
            flash('请先登录后再评论', 'warning')
            return redirect(url_for('login'))
        
        content = request.form['content']
        rating = int(request.form['rating'])
        new_review = Review(content=content, rating=rating, user_id=session['user_id'], dish_id=dish_id)
        db.session.add(new_review)
        db.session.commit()
        flash('评论发布成功！', 'success')
        return redirect(url_for('dish_detail', dish_id=dish_id))
        
    return render_template('dish_detail.html', dish=dish)

# --- 初始化数据库命令 ---
@app.cli.command("init-db")
def init_db():
    db.create_all()
    # 创建测试数据
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password_hash=generate_password_hash('admin'), role='admin')
        db.session.add(admin)
    
    if Dish.query.count() == 0:
        d1 = Dish(name='红烧肉', price=12.5, description='肥而不腻，食堂招牌')
        d2 = Dish(name='番茄炒蛋', price=5.0, description='酸甜可口，经典搭配')
        db.session.add_all([d1, d2])
    
    db.session.commit()
    print("数据库初始化完成！")

if __name__ == '__main__':
    app.run(debug=True)
