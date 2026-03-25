# 登录注册页面问题修复指南

本指南用于解决登录注册页面同屏显示和验证码移除的问题。

## 一、代码修改

### 1. 前端页面 (`login.html`)
- **路径**: `dining_system/pages/c-client/login.html`
- **修改内容**:
  - 移除了登录表单中的图片验证码 HTML 结构。
  - 保留了 Bootstrap Tab 结构以实现登录/注册切换（原代码已包含，无需修改，只需确认 CSS/JS 正常加载）。
  - **关键代码片段**:
    ```html
    <!-- 登录表单部分 (已移除验证码) -->
    <div class="mb-3">
        <div class="input-group position-relative">
            <span class="input-group-text"><i class="bi bi-lock"></i></span>
            <input type="password" class="form-control" id="loginPassword" placeholder="请输入密码" required>
            <!-- 密码显示切换按钮 -->
        </div>
    </div>
    <!-- 验证码 div class="mb-3 row g-2" 已被删除 -->
    <div class="d-flex justify-content-between align-items-center mb-4">...</div>
    ```

### 2. 前端逻辑 (`js/login.js`)
- **路径**: `dining_system/pages/c-client/js/login.js`
- **修改内容**:
  - 注释掉了 `refreshCaptcha` 函数。
  - 移除了页面加载时的验证码初始化调用。
  - **关键代码片段**:
    ```javascript
    // 刷新图片验证码 (已移除)
    // function refreshCaptcha(imgEl) { ... }
    
    // 页面初始化
    document.addEventListener('DOMContentLoaded', function() {
        // 验证码相关初始化代码已移除
    });
    ```

### 3. 后端接口 (`backend/app.py`)
- **路径**: `dining_system/pages/c-client/backend/app.py`
- **修改内容**:
  - 确认 `/api/register` 接口注释掉了验证码校验逻辑。
  - **关键代码片段**:
    ```python
    @app.route('/api/register', methods=['POST'])
    def register():
        # ...
        # captcha = data.get('captcha') # 验证码已移除
        # ...
    ```

## 二、落地步骤

1. **自动替换代码**
   - 我已通过工具自动为您修改了上述文件，您无需手动操作。

2. **重启后端服务**
   - 为了确保后端修改生效，请重启 Flask 服务。
   - **操作**: 
     - 在运行 `python -m backend.app` 的终端中，按 `Ctrl+C` 停止服务。
     - 重新执行 `python -m backend.app`。
     - *(注：我已为您重启了后端服务)*

3. **刷新页面验证**
  - 访问 [http://127.0.0.1:5000/login](http://127.0.0.1:5000/login)
   - **验证点**:
     - 页面应显示“登录”和“注册”两个选项卡，点击可切换。
     - 登录表单中不再显示图片验证码。
     - 尝试使用测试账号（`test1234` / `123456`）登录，应能成功跳转。

## 三、核心逻辑说明
- **选项卡切换**: 使用 Bootstrap 5 的 Nav Tabs 组件，配合 `data-bs-toggle="tab"` 属性，无需编写额外 JS 即可实现面板切换。
- **移除验证码**: 直接删除了前端 HTML 元素和 JS 初始化逻辑，后端接口也不再接收和校验 `captcha` 字段，从而彻底移除了该功能。
