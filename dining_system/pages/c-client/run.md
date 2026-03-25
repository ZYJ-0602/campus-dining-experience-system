# 校园食堂全维评价系统 - 新界面后端对接运行指南

本指南将指导您如何在本地启动后端服务，并连接到新版前端界面，实现真实登录、评价提交和数据展示的完整闭环。

## 目录结构
```text
dining_system/pages/c-client/
├── backend/           # 后端代码
│   ├── app.py         # Flask应用入口
│   ├── models.py      # 数据库模型
│   └── config.py      # 配置
├── database/          # 数据库文件
│   └── canteen.db     # SQLite数据库 (自动生成)
├── js/                # 前端接口对接JS
│   ├── api.js         # API配置
│   ├── login.js       # 登录逻辑
│   ├── evaluation.js  # 评价逻辑
│   └── my_evaluation.js # 我的评价逻辑
└── ... (其他HTML文件)
```

## 第一步：环境准备

确保您已安装 Python 3.x。
安装必要的依赖包：

```bash
pip install flask flask-cors flask-sqlalchemy
```

## 第二步：初始化数据库与测试数据

我们需要先创建数据库并插入测试用户和食堂数据。

1. 打开终端（Terminal/PowerShell）。
2. 进入 `dining_system/pages/c-client` 目录：
   ```bash
   cd f:\Projects\campus-dining-experience\dining_system\pages\c-client
   ```
3. 运行初始化脚本：
   ```bash
   python insert_test_data.py
   ```
   *如果看到 "Data insertion completed!" 提示，说明数据库已准备就绪。*

**测试账号信息：**
- 学生账号：`test1234` / 密码：`123456`
- 教师账号：`teacher1` / 密码：`123456`

## 第三步：启动后端服务

1. 在当前终端（或新开一个终端），确保仍在 `dining_system/pages/c-client` 目录下。
2. 运行后端服务：
   ```bash
   python -m backend.app
   ```
   *注意：这里使用模块运行方式 `-m backend.app` 以确保导入路径正确。*
   *或者直接运行 `python backend/app.py` (如果已调整路径)*
   
   **推荐方式**：
   ```bash
   # 确保在 dining_system/pages/c-client 目录下
   python -m backend.app
   ```
   *成功标志：看到 `Running on http://127.0.0.1:5000`*

## 第四步：访问前端页面

当前版本前端页面已由 Flask 同一服务托管，无需单独启动 8000 静态服务。

## 第五步：功能验证

现在，打开浏览器访问新界面进行测试。

### 1. 登录测试
- **访问地址**：[http://127.0.0.1:5000/login](http://127.0.0.1:5000/login)
- **操作**：
  - 输入账号：`test1234`，密码：`123456`。
  - 点击“登录”。
- **预期结果**：提示“登录成功”，并跳转到首页 (`index.html`)。

### 2. 提交评价 (闭环核心)
- **访问地址**：[http://127.0.0.1:5000/pages/c-client/quick_evaluation.html](http://127.0.0.1:5000/pages/c-client/quick_evaluation.html)
- **操作**：
  - 选择食堂（如：北区食堂）。
  - 选择窗口（如：1号自选快餐）。
  - 选择身份（如：学生）。
  - 勾选至少一个菜品（如：番茄炒蛋），并滑动评分条打分。
  - 填写环境/服务评分。
  - 点击“提交评价”。
- **预期结果**：提示“评价提交成功！”，并跳转到首页。

### 3. 查看个人评价
- **访问地址**：[http://127.0.0.1:5000/pages/c-client/my_evaluations.html](http://127.0.0.1:5000/pages/c-client/my_evaluations.html)
- **预期结果**：
  - 能看到刚才提交的评价记录。
  - 点击记录可展开查看详细评分。

### 4. 查看菜品/食堂详情
- **菜品详情**：[http://127.0.0.1:5000/pages/c-client/dish_detail.html?id=1](http://127.0.0.1:5000/pages/c-client/dish_detail.html?id=1)
  - 确认能看到该菜品的评分统计和评价列表。
- **食堂详情**：[http://127.0.0.1:5000/pages/c-client/canteen_detail.html?id=1](http://127.0.0.1:5000/pages/c-client/canteen_detail.html?id=1)
  - 确认能看到食堂的基本信息和窗口列表。

---

**常见问题排查**
- **404 Not Found**: 检查浏览器地址栏路径是否正确，确保前端服务在 `dining_system` 目录下启动。
- **API连接失败**: 检查后端服务（端口5000）是否正在运行。
- **跨域错误**: 建议统一通过 `http://127.0.0.1:5000` 访问页面，避免直接打开本地文件导致跨域问题。
