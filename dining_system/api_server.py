from flask import Blueprint, request, jsonify
from database_setup import app
from db_manager import DBManager

# --- 1. 创建蓝图 (Blueprint) ---
# 定义一个名为 'api' 的蓝图，所有路由前缀为 '/api'
api_bp = Blueprint('api', __name__, url_prefix='/api')

# --- 2. 辅助函数 ---
def make_response(code, msg, data=None):
    """统一响应格式封装"""
    return jsonify({
        "code": code,
        "msg": msg,
        "data": data if data is not None else {}
    })

# --- 3. 接口定义 ---

@api_bp.route('/window/<int:window_id>/dishes', methods=['GET'])
def get_window_dishes(window_id):
    """
    (1) 查询指定窗口的有效菜品
    URL: /api/window/<window_id>/dishes
    Method: GET
    """
    try:
        # 调用 DBManager 获取数据
        dishes = DBManager.get_window_dishes(window_id)
        return make_response(200, "查询成功", dishes)
    except Exception as e:
        return make_response(500, f"服务器内部错误: {str(e)}")

@api_bp.route('/window/<int:window_id>/safety', methods=['GET'])
def get_window_safety(window_id):
    """
    (2) 查询指定窗口的食安公示
    URL: /api/window/<window_id>/safety
    Method: GET
    """
    try:
        safety_info = DBManager.get_window_safety_info(window_id)
        return make_response(200, "查询成功", safety_info)
    except Exception as e:
        return make_response(500, f"服务器内部错误: {str(e)}")

@api_bp.route('/evaluation/save', methods=['POST'])
def save_evaluation():
    """
    (3) 保存评价（仅临时存储，is_submitted=0）
    URL: /api/evaluation/save
    Method: POST
    Body: JSON数据
    """
    try:
        data = request.json
        if not data:
            return make_response(400, "请求参数缺失")
        
        # 强制设置 is_submitted = 0
        data['is_submitted'] = 0
        
        success, msg, eval_id = DBManager.submit_evaluation(data)
        if success:
            return make_response(200, msg, {"id": eval_id})
        else:
            return make_response(400, msg)
    except Exception as e:
        return make_response(500, f"保存失败: {str(e)}")

@api_bp.route('/evaluation/submit', methods=['POST'])
def submit_evaluation():
    """
    (4) 提交评价（最终提交，is_submitted=1，校验重复提交）
    URL: /api/evaluation/submit
    Method: POST
    Body: JSON数据
    """
    try:
        data = request.json
        if not data:
            return make_response(400, "请求参数缺失")
        
        # 强制设置 is_submitted = 1
        data['is_submitted'] = 1
        
        success, msg, eval_id = DBManager.submit_evaluation(data)
        if success:
            return make_response(200, msg, {"id": eval_id})
        else:
            # 可能是重复提交或其他业务错误
            return make_response(400, msg)
    except Exception as e:
        return make_response(500, f"提交失败: {str(e)}")

@api_bp.route('/evaluation/stats/<int:window_id>', methods=['GET'])
def get_evaluation_stats(window_id):
    """
    (5) 查询指定窗口的评价统计
    URL: /api/evaluation/stats/<window_id>
    Method: GET
    """
    try:
        stats = DBManager.get_evaluation_stats(window_id)
        if stats:
            return make_response(200, "查询成功", stats)
        else:
            return make_response(200, "暂无数据", {})
    except Exception as e:
        return make_response(500, f"查询失败: {str(e)}")

# --- 4. 注册蓝图并启动应用 ---
# 将蓝图注册到 Flask 应用实例中
app.register_blueprint(api_bp)

if __name__ == '__main__':
    print("正在启动 API 服务...")
    print("访问地址: http://127.0.0.1:5001/api/...")
    # 注意：这里使用 5001 端口，避免与之前的 app.py (5000) 冲突
    app.run(debug=True, port=5001)
