# Campus Dining Quality Evaluation System (校园餐饮质量评价系统)

[![Python CI](https://github.com/ZYJ-0602/campus-dining-experience-system/actions/workflows/python-tests.yml/badge.svg)](https://github.com/ZYJ-0602/campus-dining-experience-system/actions/workflows/python-tests.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1.0-000000?logo=flask&logoColor=white)
![License](https://img.shields.io/github/license/ZYJ-0602/campus-dining-experience-system)

这是一个面向高校的综合性餐饮服务质量评价系统。系统旨在建立学生与食堂之间的沟通桥梁，不仅关注**菜品质量**，更全面覆盖**服务态度**、**用餐环境**及**基础设施**等多维度的评价，助力校园餐饮服务水平的整体提升。

## 📖 项目背景 (Project Background)

根据校园餐饮服务质量建设任务书要求，本项目致力于构建一个全方位的评价体系。传统的订餐或点评系统往往局限于“菜品”本身，而本系统将评价维度扩展至影响用餐体验的各个环节。

## 🌟 核心功能 (Key Features)

### 1. 多维度评价体系 (Multi-dimension Evaluation)
系统支持用户对以下四大核心指标进行独立评分与反馈：
- **🥗 菜品质量 (Dishes)**：针对菜品的口味、新鲜度、分量及价格进行评价。
- **💁 服务质量 (Service)**：针对打饭窗口人员态度、响应速度、处理异议的能力进行评价。
- **🪑 设施环境 (Facilities)**：针对食堂卫生、桌椅状况、空调/通风、餐具回收设施等进行评价。
- **📝 其他反馈 (Others)**：针对营业时间、食品安全建议或其他综合性意见的反馈通道。

### 2. 菜品展示与详情
- 每日菜单实时更新，支持查看菜品高清大图、价格及详细配料信息。
- 支持按档口或类别筛选菜品。

### 3. 数据可视化 (Data Visualization)
- **排行榜**：基于综合评分生成“红榜”（好评推荐）与“黑榜”（改进建议）。
- **趋势分析**：后台可生成服务质量月度变化趋势图（管理员视图）。

### 4. 用户交互
- 实名/匿名评价切换。
- 支持上传图片凭证（如菜品实拍、环境问题随手拍）。
- 评论区互动（点赞、回复）。

## 🛠️ 技术架构 (Tech Stack)

- **后端开发**：Python 3.x, Flask 框架
- **数据存储**：SQLite (开发环境) / MySQL (生产环境), Flask-SQLAlchemy ORM
- **前端设计**：Bootstrap 5, HTML5, CSS3, JavaScript
- **版本控制**：Git

## 🚀 快速部署 (Quick Start)

### 1. 环境准备
确保本地已安装 Python 3.8+ 和 Git。

### 2. 获取代码
```bash
git clone https://github.com/ZYJ-0602/campus-dining-experience-system.git
cd campus-dining-experience/dining_system
```

### 3. 安装依赖
```bash
pip install -r requirements.txt
```

### 4. 初始化系统
```bash
# 初始化数据库表结构
python -c "from app import db, app; app.app_context().push(); db.create_all()"
```

### 5. 启动服务
```bash
python app.py
```
访问地址：`http://127.0.0.1:5000`

说明：`api_server.py` 已收敛为 `app.py` 的兼容启动代理，推荐统一使用 `app.py` 作为主入口。

## 📂 目录结构

```
dining_system/
├── app.py              # 核心应用逻辑 (Controller & Model)
├── dining.db           # 数据库文件
├── static/             # 静态资源
│   ├── css/            # 样式文件
│   ├── js/             # 脚本文件
│   └── img/            # 图片资源
├── templates/          # 前端模板
│   ├── index.html      # 首页 (综合看板)
│   ├── dish_detail.html # 评价详情页
│   └── ...
├── requirements.txt    # 项目依赖
└── README.md           # 项目说明书
```

## 📝 任务书对标 (Requirement Mapping)

| 任务书要求 | 系统实现功能 |
| :--- | :--- |
| **菜品评价** | 实现了针对单品的评分与图文评论功能 |
| **服务评价** | 增加了服务态度专属评分维度 |
| **设施评价** | 增加了环境卫生与设施状况评分维度 |
| **其他建议** | 设立了综合反馈与建议板块 |

## 📜 License

MIT License
