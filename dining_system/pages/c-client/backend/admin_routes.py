from flask import Blueprint, request, jsonify, session
import json
import uuid
import pandas as pd
from datetime import datetime
try:
    from models import db, User, UserIdentity, SystemConfig, EvaluationMain, SafetyCert, Dish, AuditLog, Canteen, Note
except ImportError:
    from .models import db, User, UserIdentity, SystemConfig, EvaluationMain, SafetyCert, Dish, AuditLog, Canteen, Note
from werkzeug.security import generate_password_hash

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

def admin_required(f):
    """
    Decorator to check if user is admin
    For now, we check if user role is 1 (Admin)
    """
    # In a real app, use wraps from functools
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'code': 401, 'msg': '请先登录'}), 401
            
        user = User.query.get(user_id)
        if not user or user.identity_id != 1: # Assuming 1 is Admin
            return jsonify({'code': 403, 'msg': '权限不足'}), 403
            
        return f(*args, **kwargs)
    return decorated_function

def success_response(data=None, msg="操作成功"):
    return jsonify({'code': 200, 'msg': msg, 'data': data})

def error_response(msg="操作失败", code=400):
    return jsonify({'code': code, 'msg': msg})

# --- User Management ---

@admin_bp.route('/users', methods=['GET'])
# @admin_required # Temporarily disabled for easier testing
def get_users():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('limit', 10, type=int)
    role_id = request.args.get('role_id', type=int)
    keyword = request.args.get('keyword')
    
    query = User.query
    
    if role_id:
        query = query.filter_by(identity_id=role_id)
        
    if keyword:
        query = query.filter(User.nickname.like(f'%{keyword}%') | User.username.like(f'%{keyword}%'))
        
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return success_response({
        'list': [u.to_dict() for u in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages
    })

@admin_bp.route('/users', methods=['POST'])
# @admin_required
def create_user():
    data = request.json
    username = data.get('username')
    password = data.get('password', '123456')
    role_id = data.get('role_id', 2) # Default Student
    nickname = data.get('nickname')
    
    if not username:
        return error_response("请输入用户名")
        
    if User.query.filter_by(username=username).first():
        return error_response("用户名已存在")
        
    try:
        new_user = User(
            username=username,
            password=generate_password_hash(password),
            identity_id=role_id,
            nickname=nickname or f"用户{username[-4:]}"
        )
        db.session.add(new_user)
        db.session.commit()
        return success_response(new_user.to_dict(), "用户创建成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"创建失败: {str(e)}")

@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
# @admin_required
def update_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return error_response("用户不存在")
        
    data = request.json
    
    if 'role_id' in data:
        user.identity_id = data['role_id']
    if 'status' in data:
        # Assuming we might add status field later, currently just placeholder
        pass
    if 'password' in data and data['password']:
        user.password = generate_password_hash(data['password'])
        
    try:
        db.session.commit()
        return success_response(None, "更新成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"更新失败: {str(e)}")

@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
# @admin_required
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return error_response("用户不存在")
        
    try:
        db.session.delete(user)
        db.session.commit()
        return success_response(None, "删除成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"删除失败: {str(e)}")

@admin_bp.route('/dishes', methods=['GET'])
# @admin_required
def get_dishes_list():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    keyword = request.args.get('keyword')
    
    query = Dish.query
    if keyword:
        query = query.filter(Dish.name.like(f'%{keyword}%'))
        
    pagination = query.order_by(Dish.id.desc()).paginate(page=page, per_page=limit, error_out=False)
    
    # 聚合评价统计
    result_list = []
    for dish in pagination.items:
        d_dict = dish.to_dict()
        
        # 计算平均分和评价数
        eval_count = len(dish.eval_records)
        avg_score = 0
        if eval_count > 0:
            total_score = 0
            count = 0
            for r in dish.eval_records:
                scores = json.loads(r.food_scores) if r.food_scores else {}
                if scores:
                    total_score += sum(float(v) for v in scores.values()) / len(scores)
                    count += 1
            avg_score = round(total_score / count, 1) if count > 0 else 0
            
        d_dict['eval_count'] = eval_count
        d_dict['avg_score'] = avg_score
        # 简单模拟笔记提及数 (假设评价里有图就算笔记)
        d_dict['post_count'] = eval_count # 暂用总数代替
        
        result_list.append(d_dict)
    
    return success_response({
        'list': result_list,
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages
    })

@admin_bp.route('/dishes', methods=['POST'])
# @admin_required
def add_dish():
    data = request.json
    try:
        new_dish = Dish(
            window_id=data['window_id'],
            name=data['name'],
            price=data['price'],
            category=data.get('category', '其他'),
            portion=data.get('portion', '常规'),
            description=data.get('description'),
            img_url=data.get('img_url'),
            tags=json.dumps(data.get('tags', []))
        )
        db.session.add(new_dish)
        db.session.commit()
        return success_response(new_dish.to_dict(), "添加成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"添加失败: {str(e)}")

@admin_bp.route('/dishes/<int:id>', methods=['PUT'])
# @admin_required
def update_dish(id):
    dish = Dish.query.get(id)
    if not dish:
        return error_response("菜品不存在")
    
    data = request.json
    try:
        if 'name' in data: dish.name = data['name']
        if 'price' in data: dish.price = data['price']
        if 'category' in data: dish.category = data['category']
        if 'portion' in data: dish.portion = data['portion']
        if 'img_url' in data: dish.img_url = data['img_url']
        if 'description' in data: dish.description = data['description']
        
        db.session.commit()
        return success_response(dish.to_dict(), "更新成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"更新失败: {str(e)}")

@admin_bp.route('/dishes/<int:id>', methods=['DELETE'])
# @admin_required
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

@admin_bp.route('/dishes/batch_import', methods=['POST'])
# @admin_required
def batch_import_dishes():
    """
    批量导入菜品接口
    支持 JSON 数组，或接收上传的文件 (Excel/CSV，此处实现基础的 JSON 和简单文件解析逻辑)
    """
    try:
        if request.is_json:
            data_list = request.json
            if not isinstance(data_list, list):
                return error_response("JSON 格式错误，请提供对象数组")
                
            for item in data_list:
                new_dish = Dish(
                    window_id=item.get('window_id'),
                    name=item.get('name'),
                    price=item.get('price', 0.0),
                    category=item.get('category', '其他'),
                    portion=item.get('portion', '常规'),
                    description=item.get('description', ''),
                    img_url=item.get('img_url', ''),
                    tags=json.dumps(item.get('tags', []))
                )
                db.session.add(new_dish)
                
            db.session.commit()
            return success_response(None, f"成功导入 {len(data_list)} 条菜品记录")
            
        elif 'file' in request.files:
            file = request.files['file']
            filename = file.filename
            if filename.endswith('.csv'):
                import csv
                import io
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                csv_input = csv.DictReader(stream)
                count = 0
                for row in csv_input:
                    new_dish = Dish(
                        window_id=int(row.get('window_id', 0)),
                        name=row.get('name', '未命名'),
                        price=float(row.get('price', 0.0)),
                        category=row.get('category', '其他'),
                        portion=row.get('portion', '常规'),
                        description=row.get('description', '')
                    )
                    db.session.add(new_dish)
                    count += 1
                db.session.commit()
                return success_response(None, f"成功从 CSV 导入 {count} 条菜品记录")
            elif filename.endswith('.json'):
                content = file.stream.read().decode("UTF8")
                data_list = json.loads(content)
                for item in data_list:
                    new_dish = Dish(
                        window_id=item.get('window_id'),
                        name=item.get('name'),
                        price=item.get('price', 0.0),
                        category=item.get('category', '其他'),
                        description=item.get('description', '')
                    )
                    db.session.add(new_dish)
                db.session.commit()
                return success_response(None, f"成功从文件导入 {len(data_list)} 条菜品记录")
            else:
                return error_response("不支持的文件格式，请上传 .csv 或 .json")
        else:
            return error_response("无效的请求数据")
            
    except Exception as e:
        db.session.rollback()
        return error_response(f"批量导入失败: {str(e)}")

# --- System Settings ---

@admin_bp.route('/settings', methods=['GET'])
# @admin_required
def get_settings():
    configs = SystemConfig.query.all()
    settings = {c.config_key: c.config_value for c in configs}
    return success_response(settings)

@admin_bp.route('/settings', methods=['POST'])
# @admin_required
def update_settings():
    data = request.json
    try:
        for key, value in data.items():
            config = SystemConfig.query.filter_by(config_key=key).first()
            if config:
                config.config_value = str(value)
            else:
                config = SystemConfig(config_key=key, config_value=str(value))
                db.session.add(config)
        
        db.session.commit()
        return success_response(None, "设置保存成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"保存失败: {str(e)}")

# --- Content Audit ---

@admin_bp.route('/audit/evaluations', methods=['GET'])
# @admin_required
def get_audit_list():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('limit', 10, type=int)
    status = request.args.get('status', type=int) # 0: Pending, 1: Approved, 2: Rejected
    
    query = EvaluationMain.query
    
    if status is not None:
        query = query.filter_by(audit_status=status)
        
    pagination = query.order_by(EvaluationMain.create_time.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return success_response({
        'list': [e.to_dict() for e in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages
    })

@admin_bp.route('/audit/evaluations/<int:eval_id>', methods=['POST'])
# @admin_required
def audit_evaluation(eval_id):
    evaluation = EvaluationMain.query.get(eval_id)
    if not evaluation:
        return error_response("评价不存在")
        
    data = request.json
    status = data.get('status') # 1: Pass, 2: Reject
    remark = data.get('remark')
    
    if status not in [1, 2]:
        return error_response("无效的状态")
        
    try:
        evaluation.audit_status = status
        evaluation.audit_remark = remark
        db.session.commit()
        return success_response(None, "审核完成")
    except Exception as e:
        db.session.rollback()
        return error_response(f"操作失败: {str(e)}")

@admin_bp.route('/audit/notes', methods=['GET'])
# @admin_required
def get_audit_notes():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('limit', 10, type=int)
    status = request.args.get('status', type=int) # 0: Pending, 1: Approved, 2: Rejected
    
    query = Note.query
    
    if status is not None:
        query = query.filter_by(status=status)
        
    pagination = query.order_by(Note.create_time.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return success_response({
        'list': [n.to_dict() for n in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages
    })

@admin_bp.route('/audit/notes/<int:note_id>', methods=['POST'])
# @admin_required
def audit_note(note_id):
    note = Note.query.get(note_id)
    if not note:
        return error_response("笔记不存在")
        
    data = request.json
    status = data.get('status') # 1: Pass, 2: Reject
    
    if status not in [1, 2]:
        return error_response("无效的状态")
        
    try:
        note.status = status
        db.session.commit()
        return success_response(None, "审核完成")
    except Exception as e:
        db.session.rollback()
        return error_response(f"操作失败: {str(e)}")

# --- Food Safety Certificates ---

@admin_bp.route('/safety/certs', methods=['GET'])
def get_safety_certs():
    canteen_id = request.args.get('canteen_id')
    query = SafetyCert.query
    if canteen_id:
        query = query.filter_by(canteen_id=canteen_id)
        
    certs = query.all()
    return success_response([c.to_dict() for c in certs])

@admin_bp.route('/safety/certs', methods=['POST'])
# @admin_required
def add_safety_cert():
    data = request.json
    try:
        cert = SafetyCert(
            canteen_id=data['canteen_id'],
            name=data['name'],
            img_url=data['img_url'],
            expire_date=datetime.strptime(data['expire_date'], '%Y-%m-%d') if data.get('expire_date') else None
        )
        db.session.add(cert)
        db.session.commit()
        return success_response(cert.to_dict(), "添加成功")
    except Exception as e:
        db.session.rollback()
        return error_response(f"添加失败: {str(e)}")

# --- Dish Management (Operator) ---

@admin_bp.route('/food/batch-import', methods=['POST'])
def batch_import_food():
    """
    POST /api/admin/food/batch-import
    批量导入菜品，要求：
    - Excel文件上传或JSON数据
    - 数据库事务保证原子性
    - 校验规则：食堂存在、菜名唯一、价格合法等
    - 记录审计日志
    """
    operator_id = session.get('user_id', 'unknown')
    operator_user = User.query.get(operator_id) if operator_id != 'unknown' else None
    operator_name = operator_user.username if operator_user else 'system'
    
    if 'file' not in request.files:
        return error_response("未找到上传的文件")
        
    file = request.files['file']
    canteen_id = request.form.get('canteen_id')
    
    if not canteen_id:
        return error_response("必须指定所属食堂")
        
    canteen = Canteen.query.get(canteen_id)
    if not canteen:
        return error_response("食堂不存在")
        
    try:
        df = pd.read_excel(file)
        
        # 验证列名
        expected_columns = ['菜品名称', '价格', '分量', '描述', '图片链接', '标签', '状态']
        for col in expected_columns:
            if col not in df.columns:
                return error_response(f"Excel缺少必需的列: {col}")
                
        errors = []
        dishes_to_add = []
        
        # 获取该食堂现有的菜品名称
        existing_names = set([d.name for d in Dish.query.filter_by(canteen_id=canteen_id).all()])
        new_names_in_batch = set()
        
        # 遍历数据
        for index, row in df.iterrows():
            row_num = index + 2  # Excel行号通常从2开始（假设有表头）
            
            name = str(row.get('菜品名称', '')).strip()
            price_val = row.get('价格', 0)
            portion = str(row.get('分量', '常规')).strip()
            desc = str(row.get('描述', '')).strip()
            img_url = str(row.get('图片链接', '')).strip()
            tags_str = str(row.get('标签', '')).strip()
            status_val = row.get('状态', True)
            
            if not name or name == 'nan':
                errors.append(f"第{row_num}行：菜品名称不能为空")
                continue
            if len(name) > 30:
                errors.append(f"第{row_num}行：菜品名称超过30字符限制")
                continue
            if name in existing_names or name in new_names_in_batch:
                errors.append(f"第{row_num}行：菜品名称 '{name}' 已存在或重复，自动跳过")
                continue
                
            try:
                price = float(price_val)
                if price < 0 or price > 999.99:
                    errors.append(f"第{row_num}行：价格 {price} 不合法 (需0~999.99)")
                    continue
            except:
                errors.append(f"第{row_num}行：价格格式错误")
                continue
                
            if len(desc) > 500:
                errors.append(f"第{row_num}行：描述超过500字限制")
                continue
                
            tags = [t.strip() for t in tags_str.split(',')] if tags_str and tags_str != 'nan' else []
            img_urls = [i.strip() for i in img_url.split(',')] if img_url and img_url != 'nan' else []
            
            status = True
            if str(status_val).lower() in ['false', '0', '下架', '否']:
                status = False
                
            new_dish = Dish(
                id=str(uuid.uuid4()),
                canteen_id=canteen_id,
                name=name,
                price=price,
                portion=portion,
                description=desc,
                img_url=json.dumps(img_urls),
                tags=json.dumps(tags),
                status=status,
                creator=operator_name,
                updater=operator_name
            )
            
            dishes_to_add.append(new_dish)
            new_names_in_batch.add(name)
            
        if not dishes_to_add and errors:
            return error_response("导入失败，所有数据均未通过校验", data={"errors": errors})
            
        # 使用事务提交
        try:
            for d in dishes_to_add:
                db.session.add(d)
                
            # 记录审计日志
            audit = AuditLog(
                operator=operator_name,
                action='批量导入',
                target_type='Dish',
                target_id=str(canteen_id),
                before_data='',
                after_data=json.dumps([{"name": d.name, "price": d.price} for d in dishes_to_add]),
                ip_address=request.remote_addr
            )
            db.session.add(audit)
            
            db.session.commit()
            
            msg = f"成功导入 {len(dishes_to_add)} 条菜品数据"
            if errors:
                msg += f"，跳过 {len(errors)} 条错误数据"
                
            return success_response(data={"success_count": len(dishes_to_add), "errors": errors}, msg=msg)
            
        except Exception as e:
            db.session.rollback()
            return error_response(f"数据库事务提交失败: {str(e)}")
            
    except Exception as e:
        return error_response(f"处理Excel文件时出错: {str(e)}")
