from flask import Flask, request, jsonify, session, Blueprint
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
from datetime import datetime, timedelta

# Import config and models
# Since they are in the same package (backend), we can import directly if we run from backend folder
# But if we run from root, we need to adjust path. 
# We will assume running from backend folder or adding it to path.
try:
    from config import Config
    from models import db, User, UserIdentity, Canteen, Window, Dish, EvaluationMain, EvaluationDish, SystemConfig, SafetyCert, Note
    from admin_routes import admin_bp
except ImportError:
    # For relative import if needed
    from .config import Config
    from .models import db, User, UserIdentity, Canteen, Window, Dish, EvaluationMain, EvaluationDish, SystemConfig, SafetyCert, Note
    from .admin_routes import admin_bp

app = Flask(__name__)
app.config.from_object(Config)

# Register Admin Blueprint
# app.register_blueprint(admin_bp) # 移除原有的注册，改为在 app.py 中直接实现蓝图逻辑以减少文件分散

from admin_routes import admin_bp as admin_routes_bp
app.register_blueprint(admin_routes_bp)

# ==========================================
# 新增管理端蓝图 (Admin Blueprint) - 修复冲突，修改前缀
# ==========================================
admin_bp = Blueprint('admin_dashboard', __name__, url_prefix='/api/admin_dashboard')

# --- 1. 运营数据看板 ---
@admin_bp.route('/dashboard/data', methods=['GET'])
def get_dashboard_data():
    """
    获取运营数据看板
    Method: GET
    Return: {
        'today_eval_count': int,
        'week_avg_score': float,
        'bad_review_count': int,
        'top_dishes': list
    }
    """
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    
    # 今日评价数
    today_count = EvaluationMain.query.filter(
        db.func.date(EvaluationMain.create_time) == today
    ).count()
    
    # 本周平均分 (基于所有菜品评分的平均值)
    # 这里简化计算，实际可能需要更复杂的聚合
    week_evals = EvaluationDish.query.join(EvaluationMain).filter(
        EvaluationMain.create_time >= week_start
    ).all()
    
    total_score = 0
    score_count = 0
    for ed in week_evals:
        scores = json.loads(ed.food_scores) if ed.food_scores else {}
        for v in scores.values():
            try:
                total_score += float(v)
                score_count += 1
            except: pass
            
    week_avg = round(total_score / score_count, 1) if score_count > 0 else 0
    
    # 差评数 (假设评分<3为差评)
    # 简化逻辑：只要有一个维度<3即视为差评
    bad_count = 0
    for ed in week_evals:
        scores = json.loads(ed.food_scores) if ed.food_scores else {}
        if any(float(v) < 3 for v in scores.values()):
            bad_count += 1
            
    # 热门菜品 Top 10
    # 简化：按评价数量排序
    top_dishes = db.session.query(
        EvaluationDish.dish_name, 
        db.func.count(EvaluationDish.id).label('count')
    ).group_by(EvaluationDish.dish_name).order_by(db.text('count DESC')).limit(10).all()
    
    return success_response({
        'today_eval_count': today_count,
        'week_avg_score': week_avg,
        'bad_review_count': bad_count,
        'top_dishes': [{'name': t[0], 'count': t[1]} for t in top_dishes]
    })

# --- 2. 食安公示管理 ---
@admin_bp.route('/food_safety', methods=['GET'])
def get_safety_list():
    """获取食安证书列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('limit', 10, type=int)
    canteen_id = request.args.get('canteen_id', type=int)
    
    query = SafetyCert.query
    if canteen_id:
        query = query.filter_by(canteen_id=canteen_id)
        
    pagination = query.order_by(SafetyCert.create_time.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return success_response({
        'list': [c.to_dict() for c in pagination.items],
        'total': pagination.total
    })

@admin_bp.route('/food_safety', methods=['POST'])
def add_safety_cert():
    """新增食安证书"""
    data = request.json
    try:
        cert = SafetyCert(
            canteen_id=data['canteen_id'],
            title=data['title'],
            cert_type=data.get('cert_type', '其它'),
            file_url=data['file_url'],
            valid_start=datetime.strptime(data['valid_start'], '%Y-%m-%d') if data.get('valid_start') else None,
            valid_end=datetime.strptime(data['valid_end'], '%Y-%m-%d') if data.get('valid_end') else None
        )
        db.session.add(cert)
        db.session.commit()
        return success_response(cert.to_dict(), "添加成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"添加失败: {str(e)}")

@admin_bp.route('/food_safety/<int:id>', methods=['PUT'])
def update_safety_cert(id):
    """更新食安证书"""
    cert = SafetyCert.query.get(id)
    if not cert:
        return error_response("证书不存在")
        
    data = request.json
    try:
        if 'title' in data: cert.title = data['title']
        if 'cert_type' in data: cert.cert_type = data['cert_type']
        if 'file_url' in data: cert.file_url = data['file_url']
        if 'valid_start' in data: 
            cert.valid_start = datetime.strptime(data['valid_start'], '%Y-%m-%d') if data['valid_start'] else None
        if 'valid_end' in data: 
            cert.valid_end = datetime.strptime(data['valid_end'], '%Y-%m-%d') if data['valid_end'] else None
            
        db.session.commit()
        return success_response(None, "更新成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"更新失败: {str(e)}")

@admin_bp.route('/food_safety/<int:id>', methods=['DELETE'])
def delete_safety_cert(id):
    """删除食安证书"""
    cert = SafetyCert.query.get(id)
    if not cert:
        return error_response("证书不存在")
    try:
        db.session.delete(cert)
        db.session.commit()
        return success_response(None, "删除成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"删除失败: {str(e)}")

# --- 3. 用户管理 ---
@admin_bp.route('/users', methods=['GET'])
def get_users_list():
    """获取用户列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('limit', 10, type=int)
    keyword = request.args.get('keyword')
    role_id = request.args.get('role_id', type=int)
    
    query = User.query
    if keyword:
        query = query.filter(User.username.like(f'%{keyword}%') | User.nickname.like(f'%{keyword}%'))
    if role_id:
        query = query.filter_by(identity_id=role_id)
        
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return success_response({
        'list': [u.to_dict() for u in pagination.items],
        'total': pagination.total
    })

@admin_bp.route('/users', methods=['POST'])
def create_user():
    """新增用户"""
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return error_response("用户已存在")
        
    try:
        user = User(
            username=data['username'],
            password=generate_password_hash(data.get('password', '123456')),
            nickname=data.get('nickname', f"用户{data['username'][-4:]}"),
            identity_id=data.get('role_id', 2)
        )
        db.session.add(user)
        db.session.commit()
        return success_response(user.to_dict(), "创建成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"创建失败: {str(e)}")

@admin_bp.route('/users/<int:id>', methods=['PUT'])
def update_user_perm(id):
    """更新用户权限/密码"""
    user = User.query.get(id)
    if not user: return error_response("用户不存在")
    
    data = request.json
    try:
        if 'role_id' in data: user.identity_id = data['role_id']
        if 'password' in data: user.password = generate_password_hash(data['password'])
        # 禁用功能需在 User 模型添加 status 字段支持，此处仅演示
        
        db.session.commit()
        return success_response(None, "更新成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"更新失败: {str(e)}")

@admin_bp.route('/users/<int:id>', methods=['DELETE'])
def delete_user(id):
    """删除/禁用用户"""
    user = User.query.get(id)
    if not user: return error_response("用户不存在")
    try:
        db.session.delete(user)
        db.session.commit()
        return success_response(None, "删除成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"删除失败: {str(e)}")

# --- 4. 内容审核 ---
@admin_bp.route('/audit/list', methods=['GET'])
def get_audit_evaluations():
    """获取审核列表"""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    status = request.args.get('audit_status', type=int) # 0, 1, 2
    
    query = EvaluationMain.query
    if status is not None:
        query = query.filter_by(audit_status=status)
        
    pagination = query.order_by(EvaluationMain.create_time.desc()).paginate(page=page, per_page=limit, error_out=False)
    
    return success_response({
        'list': [e.to_dict() for e in pagination.items],
        'total': pagination.total
    })

@admin_bp.route('/audit/list', methods=['PUT'])
def audit_operation():
    """执行审核操作"""
    data = request.json
    id = data.get('id')
    status = data.get('audit_status') # 1:Pass, 2:Reject
    remark = data.get('audit_remark')
    
    eval_main = EvaluationMain.query.get(id)
    if not eval_main: return error_response("评价不存在")
    
    try:
        eval_main.audit_status = status
        eval_main.audit_remark = remark
        db.session.commit()
        return success_response(None, "审核完成")
    except Exception as e:
        db.session.rollback()
        return error_response(f"操作失败: {str(e)}")

# --- 5. 系统设置 ---
@admin_bp.route('/settings', methods=['GET'])
def get_sys_settings():
    """获取所有系统配置"""
    configs = SystemConfig.query.all()
    return success_response({c.key: c.value for c in configs})

@admin_bp.route('/settings', methods=['POST'])
def update_sys_settings():
    """批量更新系统配置"""
    data = request.json # {'key1': 'val1', 'key2': 'val2'}
    try:
        for k, v in data.items():
            conf = SystemConfig.query.get(k)
            if conf:
                conf.value = str(v)
            else:
                db.session.add(SystemConfig(key=k, value=str(v)))
        db.session.commit()
        return success_response(None, "配置已保存")
    except Exception as e:
        db.session.rollback()
        return error_response(f"保存失败: {str(e)}")

# 注册蓝图
app.register_blueprint(admin_bp)

# ==========================================
# 新增数据分析 API (Analytics API)
# ==========================================
analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')

def get_date_range(time_dimension):
    """根据时间维度获取开始时间"""
    today = datetime.now()
    if time_dimension == 'day':
        return today - timedelta(days=1)
    elif time_dimension == 'week':
        return today - timedelta(weeks=1)
    elif time_dimension == 'month':
        return today - timedelta(days=30)
    elif time_dimension == 'quarter':
        return today - timedelta(days=90)
    elif time_dimension == 'year':
        return today - timedelta(days=365)
    return today - timedelta(days=30) # default month

@analytics_bp.route('/basic_stats', methods=['GET'])
def get_basic_stats():
    """基础统计指标：最高价、最低价、平均价"""
    # 真实场景应基于 Order 表，此处基于 EvaluationDish.price
    prices = [r[0] for r in db.session.query(EvaluationDish.price).filter(EvaluationDish.price > 0).all()]
    
    if not prices:
        return success_response({
            'max_price': 0, 'min_price': 0, 'avg_price': 0,
            'median': 0, 'mode': 0, 'std_dev': 0
        })
        
    import statistics
    from collections import Counter
    
    return success_response({
        'max_price': max(prices),
        'min_price': min(prices),
        'avg_price': round(statistics.mean(prices), 2),
        'median': round(statistics.median(prices), 2),
        'mode': Counter(prices).most_common(1)[0][0],
        'std_dev': round(statistics.stdev(prices) if len(prices) > 1 else 0, 2)
    })

@analytics_bp.route('/advanced_stats', methods=['GET'])
def get_advanced_stats():
    """多维度筛选分析"""
    category = request.args.get('category')
    identity = request.args.get('identity')
    
    query = db.session.query(EvaluationDish).join(EvaluationMain).join(User)
    
    if category:
        query = query.join(Dish).filter(Dish.category == category)
        
    if identity:
        # identity is name like 'student'
        query = query.join(UserIdentity).filter(UserIdentity.name == identity)
        
    # 计算筛选后的均价和评分
    results = query.all()
    if not results:
        return success_response({'avg_price': 0, 'avg_score': 0})
        
    total_price = 0
    total_score = 0
    count = 0
    
    for ed in results:
        if ed.price:
            total_price += ed.price
        
        scores = json.loads(ed.food_scores) if ed.food_scores else {}
        if scores:
            avg = sum(float(v) for v in scores.values()) / len(scores)
            total_score += avg
        count += 1
        
    return success_response({
        'avg_price': round(total_price / count, 2) if count else 0,
        'avg_score': round(total_score / count, 1) if count else 0,
        'sample_count': count
    })

@analytics_bp.route('/overview', methods=['GET'])
def get_overview():
    """核心数据概览 (含同比环比)"""
    time_dim = request.args.get('time_dimension', 'month')
    
    end_date = datetime.now()
    start_date = get_date_range(time_dim)
    
    # 环比周期
    delta = end_date - start_date
    prev_start = start_date - delta
    
    # 1. 总销量
    # 实际应从 Order 表统计，此处用 EvaluationDish 数量模拟销量
    curr_sales = EvaluationDish.query.join(EvaluationMain).filter(
        EvaluationMain.create_time >= start_date
    ).count()
    
    prev_sales = EvaluationDish.query.join(EvaluationMain).filter(
        EvaluationMain.create_time >= prev_start,
        EvaluationMain.create_time < start_date
    ).count()
    
    sales_mom = ((curr_sales - prev_sales) / prev_sales * 100) if prev_sales > 0 else 0
    
    # 2. 差评率 (评分<3分)
    # 简化逻辑：取 food_scores 中任意项 < 3
    # 实际 SQL 查询较复杂，这里先取所有记录再过滤 (数据量大时需优化)
    evals = EvaluationDish.query.join(EvaluationMain).filter(
        EvaluationMain.create_time >= start_date
    ).all()
    
    bad_count = 0
    total_score_items = 0
    weighted_price_sum = 0 # for CPI
    
    for ed in evals:
        scores = {
            'color': ed.color_score,
            'aroma': ed.aroma_score,
            'taste': ed.taste_score,
            'shape': ed.shape_score,
            'portion': ed.portion_score,
            'price': ed.price_score
        }
        is_bad = False
        for k, v in scores.items():
            if v is not None and v < 3: is_bad = True
        if is_bad: bad_count += 1
        
        # CPI 计算: 价格 * (评分/5) 作为加权? 或者简单平均价格
        price = ed.price or 0
        
        # 简单使用口味评分作为代表性分数
        score = ed.taste_score or 0
        total_score_items += score
        
        # CPI 简易算法：销量/均价
        weighted_price_sum += price
            
    bad_rate = (bad_count / len(evals) * 100) if evals else 0
    
    # 3. CPI (食堂消费价格指数)
    # 简单模拟：当前平均价格 / 基准价格(设为10) * 100
    avg_price = (weighted_price_sum / total_score_items) if total_score_items else 0
    base_price = 12.0 # 假设基准均价
    cpi = (avg_price / base_price) * 100
    
    return success_response({
        'total_sales': curr_sales,
        'sales_mom': round(sales_mom, 2),
        'bad_rate': round(bad_rate, 2),
        'cpi_index': round(cpi, 1)
    })

@analytics_bp.route('/rank', methods=['GET'])
def get_rank():
    """排行柱状图数据"""
    time_dim = request.args.get('time_dimension', 'month')
    metric = request.args.get('metric', 'sales') # sales, bad_review
    
    start_date = get_date_range(time_dim)
    
    if metric == 'sales':
        # 按销量(评价数)排行
        results = db.session.query(
            EvaluationDish.dish_name, 
            db.func.count(EvaluationDish.id).label('count')
        ).join(EvaluationMain).filter(
            EvaluationMain.create_time >= start_date
        ).group_by(EvaluationDish.dish_name).order_by(db.text('count DESC')).limit(10).all()
        
    elif metric == 'bad_review':
        # 按差评数排行 (需复杂SQL，此处简化为负面标签统计)
        results = db.session.query(
            EvaluationDish.dish_name, 
            db.func.sum(db.case((EvaluationDish.is_negative == True, 1), else_=0)).label('count')
        ).join(EvaluationMain).filter(
            EvaluationMain.create_time >= start_date
        ).group_by(EvaluationDish.dish_name).order_by(db.text('count DESC')).limit(10).all()
        
    else:
        results = []

    return success_response({
        'categories': [r[0] for r in results],
        'values': [r[1] for r in results]
    })

@analytics_bp.route('/trend', methods=['GET'])
def get_trend():
    """趋势折线图数据 (近6个周期)"""
    time_dim = request.args.get('time_dimension', 'month')
    metric = request.args.get('metric', 'sales')
    
    # 生成最近6个时间点
    labels = []
    data = []
    
    today = datetime.now()
    for i in range(5, -1, -1):
        if time_dim == 'day':
            date = today - timedelta(days=i)
            labels.append(date.strftime('%m-%d'))
            # 查询该日数据...
        elif time_dim == 'month':
            # 简化：只生成模拟趋势数据，真实查询需按月聚合 SQL
            date = today - timedelta(days=i*30)
            labels.append(date.strftime('%Y-%m'))
    
    # 模拟数据 (真实环境需根据 labels 循环查询或 Group By)
    import random
    base = 100 if metric == 'sales' else 10
    data = [base + random.randint(-20, 50) for _ in range(6)]
    
    return success_response({
        'labels': labels,
        'values': data
    })

@analytics_bp.route('/negative', methods=['GET'])
def get_negative_dist():
    """负面反馈分布"""
    evals = EvaluationDish.query.all()
    
    # 这里为了简便，假设 1-3分为负面反馈，根据各个维度来判定
    # 可以将食安、环境、服务等作为标签
    tag_counts = {
        '食品安全': 0,
        '环境卫生': 0,
        '服务态度': 0,
        '菜品口味': 0,
        '价格分量': 0
    }
    
    for ed in evals:
        # 菜品维度
        if ed.taste_score is not None and ed.taste_score <= 3:
            tag_counts['菜品口味'] += 1
        if ed.price_score is not None and ed.price_score <= 3:
            tag_counts['价格分量'] += 1
        
        main_eval = EvaluationMain.query.get(ed.evaluation_id)
        if main_eval:
            if main_eval.safety_fresh is not None and main_eval.safety_fresh <= 3:
                tag_counts['食品安全'] += 1
            if main_eval.env_clean is not None and main_eval.env_clean <= 3:
                tag_counts['环境卫生'] += 1
            if main_eval.service_attitude is not None and main_eval.service_attitude <= 3:
                tag_counts['服务态度'] += 1

    result = [{'name': k, 'value': v} for k, v in tag_counts.items() if v > 0]
    # 如果没有差评，给点模拟数据避免图表为空
    if not result:
         result = [
             {'name': '菜品口味', 'value': 2},
             {'name': '服务态度', 'value': 1}
         ]
         
    return success_response(result)

@analytics_bp.route('/negative/count', methods=['POST'])
def add_negative_count():
    """负面反馈点击计数 (模拟)"""
    # 真实场景应更新对应评价的 tags 或 计数表
    return success_response(None, "计数 +1")

@analytics_bp.route('/heatmap', methods=['GET'])
def get_heatmap():
    """热力图/饼图展示数据"""
    # 饼图数据 (热门窗口分布)
    pie_results = db.session.query(
        Window.name,
        db.func.count(EvaluationMain.id).label('count')
    ).join(EvaluationMain).group_by(Window.name).all()
    
    pie_data = [{'name': r[0], 'value': r[1]} for r in pie_results]
    
    # 模拟真实热力图数据 (星期 vs 时间段)
    # ECharts 热力图需要格式: [[x, y, value], ...]
    days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    hours = ['早餐', '午餐', '晚餐', '夜宵']
    import random
    heatmap_data = []
    for i in range(len(days)):
        for j in range(len(hours)):
            # x(days), y(hours), value
            heatmap_data.append([i, j, random.randint(10, 100)])
            
    return success_response({
        'pieData': pie_data,
        'heatmapData': heatmap_data,
        'xAxis': days,
        'yAxis': hours
    })

@analytics_bp.route('/prediction', methods=['GET'])
def get_prediction():
    """趋势预测 (简单线性回归)"""
    # 简化：获取过去7天的日销量
    today = datetime.now().date()
    data = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        count = EvaluationDish.query.join(EvaluationMain).filter(
            db.func.date(EvaluationMain.create_time) == day
        ).count()
        data.append({'date': day.strftime('%m-%d'), 'value': count})
        
    # 简单预测未来3天 (线性回归)
    n = len(data)
    predictions = []
    
    if n > 1:
        sum_x = sum(range(n))
        sum_y = sum(d['value'] for d in data)
        sum_xy = sum(i * data[i]['value'] for i in range(n))
        sum_xx = sum(i * i for i in range(n))
        
        # y = kx + b
        denominator = n * sum_xx - sum_x * sum_x
        if denominator != 0:
            k = (n * sum_xy - sum_x * sum_y) / denominator
            b = (sum_y - k * sum_x) / n
            
            for i in range(1, 4):
                val = k * (n - 1 + i) + b
                day = today + timedelta(days=i)
                predictions.append({'date': day.strftime('%m-%d'), 'value': max(0, round(val))})
        else:
            avg = sum_y / n
            for i in range(1, 4):
                day = today + timedelta(days=i)
                predictions.append({'date': day.strftime('%m-%d'), 'value': round(avg)})
    else:
        val = data[0]['value'] if data else 0
        for i in range(1, 4):
            day = today + timedelta(days=i)
            predictions.append({'date': day.strftime('%m-%d'), 'value': val})
        
    return success_response({
        'history': data,
        'forecast': predictions
    })

app.register_blueprint(analytics_bp)

# Enable CORS for all routes
# 修复：允许跨域并支持 Credentials，解决前端 fetch 无法发送 cookie 的问题
# 注意：当 supports_credentials=True 时，origins 不能为 *，必须指定具体域名
# 但由于前端是本地文件或动态端口，这里我们暂时关闭 supports_credentials，
# 因为登录状态是通过 localStorage 维护的，不依赖 Cookie。
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=False)

# 显式处理 OPTIONS 请求，确保预检成功
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = app.make_default_options_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
        response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS,PUT,DELETE")
        return response

db.init_app(app)

# --- Helper Functions ---
def success_response(data=None, msg="操作成功"):
    return jsonify({'code': 200, 'msg': msg, 'data': data})

def error_response(msg="操作失败", code=400):
    return jsonify({'code': code, 'msg': msg})

# --- Auth Routes ---

@app.route('/api/upload_image', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return error_response("没有文件")
    file = request.files['file']
    if file.filename == '':
        return error_response("未选择文件")
        
    if file:
        # 简化：保存到 static/uploads
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        path = os.path.join(app.root_path, '../../static/uploads', filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file.save(path)
        return success_response({'url': f'/static/uploads/{filename}'})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    # 支持匿名登录
    if data.get('anonymous'):
        return success_response({
            'id': 0, 
            'username': 'anonymous', 
            'nickname': '匿名用户', 
            'identity_id': 0
        }, "匿名登录成功")
        
    # 修复：接收前端发送的 username 字段，与前端 login.js 保持一致
    username = data.get('username') or data.get('account') 
    password = data.get('password')
    
    if not username or not password:
        return error_response("请输入账号和密码")
    
    # Check if user exists
    user = User.query.filter_by(username=username).first()
    
    if user and check_password_hash(user.password, password):
        # Login success
        session['user_id'] = user.id
        session.permanent = True
        app.permanent_session_lifetime = timedelta(hours=24)
        
        # Include role/identity in response
        user_data = user.to_dict()
        user_data['identity_id'] = user.identity_id
        
        return success_response(user_data, "登录成功")
    else:
        return error_response("账号或密码错误")

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    phone = data.get('phone')
    password = data.get('password')
    # captcha = data.get('captcha') # 验证码已移除
    
    if not phone or not password:
        return error_response("请输入手机号和密码")
    
    if User.query.filter_by(username=phone).first():
        return error_response("该手机号已注册")
        
    try:
        # Default identity: Student (id=2) or Visitor if not set
        # We will assume ID 2 is student based on initialization
        new_user = User(
            username=phone,
            password=generate_password_hash(password),
            nickname=f"用户{phone[-4:]}",
            identity_id=2 # Default Student
        )
        db.session.add(new_user)
        db.session.commit()
        
        # Auto login
        session['user_id'] = new_user.id
        return success_response(new_user.to_dict(), "注册成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"注册失败: {str(e)}")

@app.route('/api/user/profile', methods=['GET'])
def get_user_profile():
    user_id = session.get('user_id')
    if not user_id:
        return error_response("请先登录", 401)
        
    user = User.query.get(user_id)
    if not user:
        return error_response("用户不存在")
        
    data = user.to_dict()
    # 补充身份信息
    data['identity_name'] = user.identity.name if user.identity else 'visitor'
    data['identity_display'] = user.identity.display_name if user.identity else '游客'
    return success_response(data)

@app.route('/api/user/profile', methods=['POST'])
def update_user_profile():
    user_id = session.get('user_id')
    if not user_id:
        return error_response("请先登录", 401)
        
    user = User.query.get(user_id)
    if not user:
        return error_response("用户不存在")
        
    data = request.json
    try:
        if 'nickname' in data: user.nickname = data['nickname']
        if 'gender' in data: user.gender = data['gender']
        if 'department' in data: user.department = data['department']
        if 'avatar' in data: user.avatar = data['avatar']
        
        db.session.commit()
        return success_response(user.to_dict(), "个人信息更新成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"更新失败: {str(e)}")

# --- Password Reset Routes ---

# Store verification codes in memory for simplicity (in production use Redis)
verification_codes = {}

@app.route('/api/send_sms', methods=['POST'])
def send_sms():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return error_response("请输入手机号")
    
    # Check if user exists
    user = User.query.filter_by(username=phone).first()
    if not user:
        return error_response("该手机号未注册")
        
    # Generate mock code (fixed for testing)
    code = "123456"
    verification_codes[phone] = code
    
    # In a real app, send SMS here
    print(f"SMS Code for {phone}: {code}")
    
    return success_response(None, "验证码已发送")

@app.route('/api/reset_password', methods=['POST'])
def reset_password():
    data = request.json
    phone = data.get('phone')
    code = data.get('code')
    new_password = data.get('password')
    
    if not all([phone, code, new_password]):
        return error_response("请填写所有字段")
        
    # Verify code
    if verification_codes.get(phone) != code:
        return error_response("验证码错误")
        
    # Reset password
    user = User.query.filter_by(username=phone).first()
    if not user:
        return error_response("用户不存在")
        
    try:
        user.password = generate_password_hash(new_password)
        db.session.commit()
        
        # Clear code
        if phone in verification_codes:
            del verification_codes[phone]
            
        return success_response(None, "密码重置成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"重置失败: {str(e)}")

# --- Data Routes ---

@app.route('/api/canteens', methods=['GET'])
def get_canteens():
    canteens = Canteen.query.all()
    return success_response([c.to_dict() for c in canteens])

@app.route('/api/windows', methods=['GET'])
def get_windows():
    canteen_id = request.args.get('canteen_id')
    query = Window.query
    if canteen_id:
        query = query.filter_by(canteen_id=canteen_id)
    windows = query.all()
    return success_response([w.to_dict() for w in windows])

@app.route('/api/dishes', methods=['GET'])
def get_dishes():
    window_id = request.args.get('window_id')
    category = request.args.get('category')
    
    query = Dish.query
    if window_id:
        query = query.filter_by(window_id=window_id)
    if category:
        query = query.filter_by(category=category)
        
    dishes = query.all()
    return success_response([d.to_dict() for d in dishes])

@app.route('/api/dishes', methods=['POST'])
def add_dish():
    data = request.json
    try:
        new_dish = Dish(
            window_id=data['window_id'],
            name=data['name'],
            price=data['price'],
            category=data.get('category', '其他'),
            description=data.get('description', ''),
            img_url=data.get('img_url', ''),
            tags=json.dumps(data.get('tags', []))
        )
        db.session.add(new_dish)
        db.session.commit()
        return success_response(new_dish.to_dict(), "菜品添加成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"添加失败: {str(e)}")

@app.route('/api/dishes/<int:id>', methods=['PUT'])
def update_dish(id):
    dish = Dish.query.get(id)
    if not dish:
        return error_response("菜品不存在")
        
    data = request.json
    try:
        if 'name' in data: dish.name = data['name']
        if 'price' in data: dish.price = data['price']
        if 'category' in data: dish.category = data['category']
        if 'description' in data: dish.description = data['description']
        if 'img_url' in data: dish.img_url = data['img_url']
        if 'tags' in data: dish.tags = json.dumps(data['tags'])
        
        db.session.commit()
        return success_response(dish.to_dict(), "更新成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"更新失败: {str(e)}")

@app.route('/api/dishes/<int:id>', methods=['DELETE'])
def delete_dish(id):
    dish = Dish.query.get(id)
    if not dish:
        return error_response("菜品不存在")
    try:
        db.session.delete(dish)
        db.session.commit()
        return success_response(None, "删除成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"删除失败: {str(e)}")

# --- Evaluation Routes ---

@app.route('/api/submit_evaluation', methods=['POST'])
def submit_evaluation():
    data = request.json
    user_id = session.get('user_id')
    if not user_id:
        return error_response("请先登录", 401)
        
    # 防刷校验 (同一用户 30 秒内不能重复提交)
    thirty_seconds_ago = datetime.now() - timedelta(seconds=30)
    recent_eval = EvaluationMain.query.filter(
        EvaluationMain.user_id == user_id,
        EvaluationMain.create_time >= thirty_seconds_ago
    ).first()
    if recent_eval:
        return error_response("提交过于频繁，请30秒后再试")

    # 敏感词过滤
    sensitive_words = ['垃圾', '脏', '恶心', '难吃'] # 示例库，实际应从数据库加载
    remark = data.get('remark', '')
    for word in sensitive_words:
        if word in remark:
            # 自动转入人工审核或直接拦截
            # 这里演示拦截
            # return error_response("包含敏感词汇，请修改")
            # 或者标记为待审核
            pass
            
    try:
        def get_int(val, default=0):
            try:
                return int(val)
            except (TypeError, ValueError):
                return default

        # 获取独立的维度评分
        service_attitude = get_int(data.get('service_attitude', 0))
        service_speed = get_int(data.get('service_speed', 0))
        service_dress = get_int(data.get('service_dress', 0))

        env_clean = get_int(data.get('env_clean', 0))
        env_air = get_int(data.get('env_air', 0))
        env_hygiene = get_int(data.get('env_hygiene', 0))

        safety_fresh = get_int(data.get('safety_fresh', 0))
        safety_info = get_int(data.get('safety_info', 0))

        def calc_dim_avg(*scores):
            valid_scores = [s for s in scores if s > 0]
            return sum(valid_scores) / len(valid_scores) if valid_scores else 0

        # 计算各维度平均分
        service_avg = calc_dim_avg(service_attitude, service_speed, service_dress)
        env_avg = calc_dim_avg(env_clean, env_air, env_hygiene)
        safety_avg = calc_dim_avg(safety_fresh, safety_info)
        
        dishes_data = data.get('dishes', [])
        dish_avg_total = 0
        dish_count = 0
        
        for d in dishes_data:
            # 获取菜品独立的6维度评分
            color = get_int(d.get('color_score', 0))
            aroma = get_int(d.get('aroma_score', 0))
            taste = get_int(d.get('taste_score', 0))
            shape = get_int(d.get('shape_score', 0))
            portion = get_int(d.get('portion_score', 0))
            price_score = get_int(d.get('price_score', 0))
            
            d_avg = calc_dim_avg(color, aroma, taste, shape, portion, price_score)
            if d_avg > 0:
                dish_avg_total += d_avg
                dish_count += 1
                
        food_avg = dish_avg_total / dish_count if dish_count > 0 else 0
        
        # 综合评分：40% dish_avg, 20% service, 20% env, 20% safety
        # 这里考虑有些维度可能完全没有打分的情况进行权重归一化
        total_weight = 0
        comprehensive_score = 0
        if food_avg > 0:
            comprehensive_score += food_avg * 0.4
            total_weight += 0.4
        if service_avg > 0:
            comprehensive_score += service_avg * 0.2
            total_weight += 0.2
        if env_avg > 0:
            comprehensive_score += env_avg * 0.2
            total_weight += 0.2
        if safety_avg > 0:
            comprehensive_score += safety_avg * 0.2
            total_weight += 0.2
            
        if total_weight > 0:
            comprehensive_score = comprehensive_score / total_weight
        else:
            comprehensive_score = 0
        
        # 主评价
        eval_main = EvaluationMain(
            user_id=user_id,
            canteen_id=data['canteen_id'],
            window_id=data['window_id'],
            buy_time=datetime.strptime(data['buy_time'], '%Y-%m-%dT%H:%M') if 'buy_time' in data else datetime.now(),
            identity_type=data.get('identity_type'),
            grade=data.get('grade'),
            age=data.get('age'),
            dining_years=data.get('dining_years'),
            service_attitude=service_attitude,
            service_speed=service_speed,
            service_dress=service_dress,
            service_comment=data.get('service_comment', ''),
            service_images=json.dumps(data.get('service_images', [])),
            env_clean=env_clean,
            env_air=env_air,
            env_hygiene=env_hygiene,
            env_comment=data.get('env_comment', ''),
            env_images=json.dumps(data.get('env_images', [])),
            safety_fresh=safety_fresh,
            safety_info=safety_info,
            safety_comment=data.get('safety_comment', ''),
            safety_images=json.dumps(data.get('safety_images', [])),
            comprehensive_score=round(comprehensive_score, 2),
            images=json.dumps(data.get('images', [])),
            remark=data.get('remark', ''),
            audit_status=0 # 默认待审核
        )
        db.session.add(eval_main)
        db.session.flush() # 获取ID
        
        # 菜品评价
        for dish_data in dishes_data:
            color = get_int(dish_data.get('color_score', 0))
            aroma = get_int(dish_data.get('aroma_score', 0))
            taste = get_int(dish_data.get('taste_score', 0))
            shape = get_int(dish_data.get('shape_score', 0))
            portion = get_int(dish_data.get('portion_score', 0))
            price_score = get_int(dish_data.get('price_score', 0))
            
            eval_dish = EvaluationDish(
                evaluation_id=eval_main.id,
                dish_id=dish_data['id'],
                dish_name=dish_data['name'],
                price=dish_data.get('price'),
                color_score=color,
                aroma_score=aroma,
                taste_score=taste,
                shape_score=shape,
                portion_score=portion,
                price_score=price_score,
                remark=dish_data.get('remark', ''),
                is_negative=dish_data.get('is_negative', False),
                negative_tags=json.dumps(dish_data.get('tags', []))
            )
            db.session.add(eval_dish)
            
            # 更新菜品销量和评分
            dish = Dish.query.get(dish_data['id'])
            if dish:
                dish.total_sales += 1
                dish.monthly_sales += 1
                
                # 计算新平均分
                current_dish_avg = calc_dim_avg(color, aroma, taste, shape, portion, price_score)
                if current_dish_avg > 0:
                    total_score = dish.average_score * dish.review_count
                    dish.review_count += 1
                    dish.average_score = round((total_score + current_dish_avg) / dish.review_count, 2)
            
        db.session.commit()
        return success_response(None, "评价提交成功，待审核")
    except Exception as e:
        db.session.rollback()
        return error_response(f"提交失败: {str(e)}")

@app.route('/api/my_evaluations', methods=['GET'])
def get_my_evaluations():
    user_id = session.get('user_id')
    if not user_id:
        return error_response("请先登录", 401)
        
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    
    # 模拟购买记录分析（基于评价）
    # 真实场景应查询 Order 表
    pagination = EvaluationMain.query.filter_by(user_id=user_id)\
        .order_by(EvaluationMain.create_time.desc())\
        .paginate(page=page, per_page=limit, error_out=False)
        
    return success_response({
        'list': [e.to_dict() for e in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages
    })

@app.route('/api/purchase/stats', methods=['GET'])
def get_purchase_stats():
    user_id = session.get('user_id')
    if not user_id:
        return error_response("请先登录", 401)
        
    # 统计逻辑：基于评价记录
    total_spend = 0
    dish_counts = {}
    canteen_counts = {}
    
    evals = EvaluationMain.query.filter_by(user_id=user_id).all()
    for e in evals:
        for d in e.dish_evaluations:
            # 假设每次消费包含评价的菜品
            price = d.price or 0
            total_spend += price
            
            dish_name = d.dish_name
            dish_counts[dish_name] = dish_counts.get(dish_name, 0) + 1
            
        c_name = e.canteen.name if e.canteen else '未知食堂'
        canteen_counts[c_name] = canteen_counts.get(c_name, 0) + 1
        
    # Top 3 菜品
    top_dishes = sorted(dish_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    
    return success_response({
        'total_orders': len(evals),
        'total_spend': round(total_spend, 2),
        'top_dishes': [{'name': k, 'count': v} for k, v in top_dishes],
        'canteen_dist': canteen_counts
    })

@app.route('/api/dish_evaluations', methods=['GET'])
def get_dish_evaluations():
    dish_id = request.args.get('dish_id')
    if not dish_id:
        return error_response("缺少菜品ID")
        
    evals = EvaluationDish.query.filter_by(dish_id=dish_id).all()
    
    reviews = []
    stats = {'count': 0, 'scores': {}}
    
    for e in evals:
        main = e.evaluation_main
        scores = json.loads(e.food_scores) if e.food_scores else {}
        
        # Add to stats
        stats['count'] += 1
        for k, v in scores.items():
            if k not in stats['scores']: stats['scores'][k] = 0
            try: stats['scores'][k] += float(v)
            except: pass
            
        reviews.append({
            'id': e.id,
            'user_identity': main.identity_type if main else '匿名',
            'create_time': main.create_time.strftime('%Y-%m-%d'),
            'remark': e.remark,
            'scores': scores
        })
        
    # Calculate averages
    avg_scores = {}
    if stats['count'] > 0:
        for k, v in stats['scores'].items():
            avg_scores[k] = round(v / stats['count'], 1)
            
    return success_response({'list': reviews, 'stats': {'total_count': stats['count'], 'avg_scores': avg_scores}})

@app.route('/api/canteen_detail', methods=['GET'])
def get_canteen_detail():
    # This is a bit complex as it needs aggregation
    canteen_id = request.args.get('canteen_id')
    # Simplified implementation
    canteen = Canteen.query.get(canteen_id)
    if not canteen:
        return error_response("食堂不存在")
        
    # Mock stats or calculate real ones
    # For now return canteen info and windows
    windows = Window.query.filter_by(canteen_id=canteen.id).all()
    
    return success_response({
        'info': canteen.to_dict(),
        'windows': [w.to_dict() for w in windows]
    })

@app.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    """基于用户偏好的推荐算法"""
    user_id = session.get('user_id')
    if not user_id:
        # 游客模式：返回销量Top5
        top_dishes = Dish.query.order_by(Dish.total_sales.desc()).limit(5).all()
        return success_response([d.to_dict() for d in top_dishes])
        
    # 用户模式：分析历史评价的高分菜品类别
    user_evals = EvaluationMain.query.filter_by(user_id=user_id).all()
    fav_categories = []
    for e in user_evals:
        for ed in e.dish_evaluations:
            # 简化：假设评分>4为喜欢
            scores = json.loads(ed.food_scores) if ed.food_scores else {}
            if any(float(v) > 4 for v in scores.values()):
                if ed.dish and ed.dish.category:
                    fav_categories.append(ed.dish.category)
                    
    from collections import Counter
    if fav_categories:
        most_common_cat = Counter(fav_categories).most_common(1)[0][0]
        # 推荐该类别的其他热门菜品
        recs = Dish.query.filter_by(category=most_common_cat)\
            .order_by(Dish.total_sales.desc()).limit(5).all()
        return success_response([d.to_dict() for d in recs])
    else:
        # 无偏好数据，返回总榜
        top_dishes = Dish.query.order_by(Dish.total_sales.desc()).limit(5).all()
        return success_response([d.to_dict() for d in top_dishes])

# --- Note Routes ---

@app.route('/api/notes', methods=['GET'])
def get_notes():
    """获取笔记列表 (瀑布流，仅已审核通过)"""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    
    # status=1 为已发布/审核通过
    pagination = Note.query.filter_by(status=1)\
        .order_by(Note.create_time.desc())\
        .paginate(page=page, per_page=limit, error_out=False)
        
    return success_response({
        'list': [note.to_dict() for note in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages
    })

@app.route('/api/notes', methods=['POST'])
def publish_note():
    """发布笔记 (默认待审核 status=0)"""
    data = request.json
    user_id = session.get('user_id') or data.get('user_id')
    if not user_id:
        return error_response("请先登录", 401)
        
    title = data.get('title')
    content = data.get('content')
    
    if not title or not content:
        return error_response("标题和内容不能为空")
        
    try:
        new_note = Note(
            user_id=user_id,
            title=title,
            content=content,
            images=json.dumps(data.get('images', [])),
            tags=json.dumps(data.get('tags', [])),
            is_anonymous=data.get('is_anonymous', False),
            status=0 # 默认待审核
        )
        db.session.add(new_note)
        db.session.commit()
        return success_response(new_note.to_dict(), "发布成功，等待审核")
    except Exception as e:
        db.session.rollback()
        return error_response(f"发布失败: {str(e)}")

@app.route('/api/notes/<int:note_id>/like', methods=['POST'])
def like_note(note_id):
    """点赞笔记"""
    note = Note.query.get(note_id)
    if not note:
        return error_response("笔记不存在", 404)
        
    try:
        note.like_count += 1
        db.session.commit()
        return success_response({'like_count': note.like_count}, "点赞成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"点赞失败: {str(e)}")

# --- Init DB Command ---
@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database initialized.")

# ------------------------------------------------------------
# 新增功能模块 (请粘贴到 app.py 文件末尾)
# ------------------------------------------------------------

import sqlite3

def get_db_connection():
    """获取数据库连接 (canteen.db)"""
    # 这里的路径根据实际运行目录可能需要调整，建议用绝对路径
    # 假设 canteen.db 和 app.py 在同一级或者上级目录，这里用当前工作目录
    conn = sqlite3.connect('canteen.db')
    conn.row_factory = sqlite3.Row # 让查询结果可以通过列名访问
    return conn

# 1. 获取菜品列表接口 (供学生评价页读取菜品)
@app.route('/api/dish_list', methods=['GET'])
def get_dish_list():
    conn = get_db_connection()
    dishes = conn.execute('SELECT * FROM dish').fetchall()
    conn.close()
    
    # 转换为列表字典
    dish_list = []
    for dish in dishes:
        dish_list.append({
            'id': dish['id'],
            'name': dish['name'],
            'price': dish['price'],
            'weight': dish['weight'],
            'window_id': dish['window_id']
        })
        
    return jsonify({
        'code': 200,
        'message': '成功',
        'data': dish_list
    })

# 2. 导入菜品接口 (供管理员页存入菜品数据)
@app.route('/api/import_dish', methods=['POST'])
def import_dish():
    data = request.json
    name = data.get('name')
    weight = data.get('weight')
    price = data.get('price')
    window_id = data.get('window_id')
    
    if not name or not price:
        return jsonify({'code': 400, 'message': '菜品名和价格必填', 'data': None})
        
    conn = get_db_connection()
    conn.execute('INSERT INTO dish (name, weight, price, window_id) VALUES (?, ?, ?, ?)',
                 (name, weight, price, window_id))
    conn.commit()
    conn.close()
    
    return jsonify({
        'code': 200,
        'message': '菜品导入成功',
        'data': None
    })

# 3. 提交点评接口 (供学生页存入点评数据)
@app.route('/api/submit_comment', methods=['POST'])
def submit_comment():
    data = request.json
    dish_id = data.get('dish_id')
    identity = data.get('identity')
    grade = data.get('grade')
    dining_years = data.get('dining_years')
    taste_score = data.get('taste_score')
    env_score = data.get('env_score')
    service_score = data.get('service_score')
    create_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO evaluation (dish_id, identity, grade, dining_years, taste_score, env_score, service_score, create_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (dish_id, identity, grade, dining_years, taste_score, env_score, service_score, create_time))
    conn.commit()
    conn.close()
    
    return jsonify({
        'code': 200,
        'message': '点评提交成功',
        'data': None
    })

# 4. 数据分析接口 (供排行榜页计算同比/环比/CPI/趋势)
@app.route('/api/analysis_data', methods=['GET'])
def get_analysis_data():
    conn = get_db_connection()
    
    # 简单模拟数据分析逻辑
    # 1. 销量/点评趋势 (按天统计)
    trend_data = conn.execute('''
        SELECT date(create_time) as day, COUNT(*) as count 
        FROM evaluation 
        GROUP BY day 
        ORDER BY day DESC 
        LIMIT 7
    ''').fetchall()
    
    # 2. 菜品评分排行 (Top 5)
    rank_data = conn.execute('''
        SELECT d.name, AVG(e.taste_score) as avg_score
        FROM evaluation e
        JOIN dish d ON e.dish_id = d.id
        GROUP BY d.name
        ORDER BY avg_score DESC
        LIMIT 5
    ''').fetchall()
    
    conn.close()
    
    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': {
            'trend': [{'date': row['day'], 'count': row['count']} for row in trend_data],
            'rank': [{'name': row['name'], 'score': round(row['avg_score'], 1)} for row in rank_data]
        }
    })

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # 修复：监听所有网络接口，避免 localhost 和 127.0.0.1 的连接问题，使用 5001 端口避开可能的 5000 占用
    app.run(host='0.0.0.0', debug=True, port=5001)
