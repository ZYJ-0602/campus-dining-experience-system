# 前端项目目录结构说明

为了适应毕业设计展示和系统化管理，我们将项目文件进行标准化分类。以下是推荐的目录结构：

```
campus-dining-system/
│
├── pages/                          # HTML 页面文件
│   ├── c-client/                   # C端用户界面 (移动端优先)
│   │   ├── index.html              # 系统首页 (瀑布流)
│   │   ├── login.html              # 登录/注册页
│   │   ├── forget_password.html    # 忘记密码页
│   │   ├── user_center.html        # 个人中心页
│   │   ├── evaluation_scan.html    # 扫码快速评价页
│   │   ├── post_publish.html       # 图文笔记发布页
│   │   ├── post_detail.html        # 笔记详情页
│   │   ├── canteen_detail.html     # 食堂详情页
│   │   ├── dish_detail.html        # 菜品详情页
│   │   ├── safety_list.html        # 食安公示汇总页
│   │   └── rank_list.html          # 多维可视化榜单页
│   │
│   ├── b-admin/                    # B端管理界面 (PC端适配)
│   │   ├── admin_index.html        # 管理后台首页 (仪表盘)
│   │   ├── admin_user.html         # 用户管理页
│   │   ├── admin_audit.html        # 内容审核页
│   │   ├── admin_settings.html     # 系统设置页
│   │   └── dish_evaluation_admin.html # 菜品评价管理页 (食堂端)
│   │
│   └── common/                     # 通用/公共页面
│       └── error_page.html         # 404/500错误页
│
├── static/                         # 静态资源文件
│   ├── css/
│   │   ├── bootstrap.min.css       # Bootstrap 5 核心样式
│   │   └── common.css              # 项目通用样式 (自研)
│   │
│   ├── js/
│   │   ├── bootstrap.bundle.min.js # Bootstrap 5 核心脚本
│   │   ├── echarts.min.js          # ECharts 图表库
│   │   └── common.js               # 项目通用脚本 (自研)
│   │
│   └── img/                        # 图片资源
│       ├── logo.png                # 系统Logo
│       ├── avatar-default.png      # 默认头像
│       ├── 404.svg                 # 错误页插画
│       └── ... (其他演示图片)
│
└── README.md                       # 项目说明文档
```

---

### 资源引入规范

由于页面被分到了不同的子目录（`pages/c-client/` 和 `pages/b-admin/`），在引入 `static` 资源时需要注意路径层级。

**1. C端页面 (pages/c-client/*.html)**
需要向上两级找到 `static` 目录：
```html
<link href="../../static/css/bootstrap.min.css" rel="stylesheet">
<link href="../../static/css/common.css" rel="stylesheet">
<script src="../../static/js/common.js"></script>
```

**2. B端页面 (pages/b-admin/*.html)**
同样需要向上两级：
```html
<link href="../../static/css/bootstrap.min.css" rel="stylesheet">
<link href="../../static/css/common.css" rel="stylesheet">
<script src="../../static/js/common.js"></script>
```

**3. 公共页面 (pages/common/*.html)**
同样向上两级：
```html
<link href="../../static/css/common.css" rel="stylesheet">
```

### 注意事项
- 所有页面跳转建议使用 `common.js` 中的 `jumpToPage()` 函数，或者使用相对路径（如 `../c-client/index.html`）。
- 图片资源引用也需遵循相对路径规则，例如在 HTML 中使用 `<img src="../../static/img/logo.png">`。
