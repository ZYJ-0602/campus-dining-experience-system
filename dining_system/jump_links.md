# 核心页面跳转链路说明

本文档记录了前端各页面之间的跳转关系及代码实现，方便开发调试。

## 一、C端用户流 (移动端)

### 1. 登录/注册 -> 首页
*   **场景**：用户登录成功后进入系统首页。
*   **触发**：`login.html` 中的登录按钮。
*   **代码**：
    ```javascript
    // 登录成功后
    Common.jumpTo('../c-client/index.html');
    ```

### 2. 首页 -> 功能页
*   **场景**：从首页快捷入口跳转到各功能模块。
*   **触发**：首页4宫格图标。
*   **代码**：
    ```html
    <!-- 扫码评价 -->
    <a href="evaluation_scan.html" class="shortcut-item">...</a>
    
    <!-- 食堂列表 -->
    <a href="canteen_detail.html?name=北区食堂" class="shortcut-item">...</a>
    
    <!-- 榜单排行 -->
    <a href="rank_list.html" class="shortcut-item">...</a>
    
    <!-- 食安公示 -->
    <a href="safety_list.html" class="shortcut-item">...</a>
    ```

### 3. 首页 -> 笔记详情
*   **场景**：点击瀑布流中的笔记卡片查看详情。
*   **触发**：笔记卡片 `onclick`。
*   **代码**：
    ```javascript
    // 带参数跳转
    Common.jumpTo('post_detail.html', { id: 1 });
    ```

### 4. 食堂详情 -> 菜品详情
*   **场景**：在食堂页点击推荐菜品。
*   **触发**：菜品卡片 `onclick`。
*   **代码**：
    ```javascript
    Common.jumpTo('dish_detail.html', { id: dishId });
    ```

### 5. 菜品详情 -> 去评价
*   **场景**：查看菜品后直接进行评价。
*   **触发**：底部“去评价”按钮。
*   **代码**：
    ```javascript
    // 自动带入菜品ID到评价页
    Common.jumpTo('evaluation_scan.html', { dish_id: 1, window_id: 2 });
    ```

### 6. 发布笔记 -> 首页
*   **场景**：笔记发布成功后返回首页。
*   **触发**：发布成功回调。
*   **代码**：
    ```javascript
    Common.toast('发布成功', 'success');
    setTimeout(() => {
        Common.jumpTo('index.html');
    }, 1500);
    ```

---

## 二、B端管理流 (PC端)

### 1. 登录 -> 管理后台
*   **场景**：管理员/运营账号登录后进入后台。
*   **触发**：`login.html` 判断角色。
*   **代码**：
    ```javascript
    if (role === 'admin') {
        Common.jumpTo('../b-admin/admin_index.html');
    }
    ```

### 2. 管理后台首页 -> 子管理页
*   **场景**：从仪表盘点击卡片进入具体管理页。
*   **触发**：首页卡片链接。
*   **代码**：
    ```html
    <a href="admin_user.html" class="nav-link">用户管理</a>
    <a href="admin_audit.html" class="nav-link">内容审核</a>
    <a href="dish_evaluation_admin.html" class="nav-link">菜品评价</a>
    ```

### 3. 子管理页 -> 返回首页
*   **场景**：点击顶部导航栏返回。
*   **触发**：顶部“返回首页”按钮。
*   **代码**：
    ```html
    <a href="admin_index.html" class="btn">返回首页</a>
    ```

---

## 三、通用跳转

### 1. 任意页 -> 404错误页
*   **场景**：资源加载失败或路径错误。
*   **代码**：
    ```javascript
    Common.jumpTo('../common/error_page.html?type=404');
    ```

### 2. 任意页 -> 登录页 (未登录拦截)
*   **场景**：访问需权限页面时检测到未登录。
*   **代码**：
    ```javascript
    if (!Common.isLogin()) {
        Common.toast('请先登录', 'error');
        setTimeout(() => Common.jumpTo('../c-client/login.html'), 1000);
    }
    ```
