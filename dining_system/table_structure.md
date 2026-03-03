# 校园食堂用餐体验点评系统 - 数据库表结构设计

## 一、设计概述
本数据库设计采用 **SQLite + SQLAlchemy** 技术栈，专为校园食堂点评系统打造。设计遵循第三范式（3NF），包含 **10张核心表**，涵盖了用户权限、食堂运营、评价交互、社区内容及系统管理等全场景需求。

### 核心设计思路
1. **RBAC权限模型**：通过 `user`、`role`、`user_role` 三张表实现灵活的用户权限管理（管理员/运营/普通用户）。
2. **层级化食堂管理**：采用 `canteen` -> `window` -> `dish` 的三级结构，清晰表达食堂、窗口与菜品的从属关系。
3. **多维评价体系**：`evaluation` 表独立设计了食品、环境、服务、食安四个维度的评分字段，支持更精细的数据分析。
4. **内容安全风控**：引入 `sensitive_word` 表和 `post` 表的审核状态字段，构建内容安全防线。

---

## 二、表结构关系图 (ER Diagram)

```mermaid
erDiagram
    User ||--o{ UserRole : has
    Role ||--o{ UserRole : assigned_to
    User ||--o{ Evaluation : writes
    User ||--o{ Post : publishes
    
    Canteen ||--o{ Window : contains
    Canteen ||--o{ SafetyNotice : owns
    Canteen ||--o{ Post : tagged_in
    
    Window ||--o{ Dish : serves
    Window ||--o{ Evaluation : receives
    
    Dish ||--o{ Evaluation : receives
    Dish ||--o{ Post : tagged_in
    
    Evaluation }o--|| User : from
    Evaluation }o--|| Window : to
    Evaluation }o--|| Dish : to
```

---

## 三、详细表结构说明

### 1. 角色表 (role)
| 字段名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| id | Integer | 是 | 主键ID，自增 |
| name | String(50) | 是 | 角色名称（如：管理员、普通用户） |
| code | String(50) | 是 | 角色编码（如：admin, user），唯一 |
| description | String(200) | 否 | 角色描述 |
| create_time | DateTime | 是 | 创建时间 |
| update_time | DateTime | 是 | 更新时间 |
| is_active | Boolean | 是 | 是否启用 |

### 2. 用户表 (user)
| 字段名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| id | Integer | 是 | 主键ID，自增 |
| username | String(50) | 是 | 用户名，唯一索引 |
| password_hash | String(128) | 是 | 加密后的密码 |
| phone | String(20) | 否 | 手机号，唯一索引 |
| nickname | String(50) | 否 | 用户昵称 |
| avatar_url | String(255) | 否 | 头像链接 |
| ... | ... | ... | (基础字段同上) |

### 3. 用户角色关联表 (user_role)
| 字段名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| user_id | Integer | 是 | 外键，关联 user.id |
| role_id | Integer | 是 | 外键，关联 role.id |

### 4. 食堂表 (canteen)
| 字段名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| id | Integer | 是 | 主键ID |
| name | String(100) | 是 | 食堂名称（如：北区食堂） |
| location | String(200) | 否 | 地理位置 |
| opening_hours | String(100) | 否 | 营业时间 |
| cover_url | String(255) | 否 | 封面图 |
| ... | ... | ... | (基础字段同上) |

### 5. 窗口表 (window)
| 字段名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| id | Integer | 是 | 主键ID |
| canteen_id | Integer | 是 | 外键，归属食堂 |
| name | String(100) | 是 | 窗口名称（如：1号麻辣烫） |
| floor | Integer | 否 | 所在楼层 |
| category | String(50) | 否 | 经营品类 |
| manager_name | String(50) | 否 | 负责人姓名 |
| ... | ... | ... | (基础字段同上) |

### 6. 菜品表 (dish)
| 字段名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| id | Integer | 是 | 主键ID |
| window_id | Integer | 是 | 外键，归属窗口 |
| name | String(100) | 是 | 菜品名称 |
| price | Float | 是 | 价格 |
| is_recommend | Boolean | 否 | 是否为推荐菜 |
| ... | ... | ... | (基础字段同上) |

### 7. 评价表 (evaluation)
*设计思路：将评分拆分为四个维度，便于食堂针对性改进。*

| 字段名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| id | Integer | 是 | 主键ID |
| user_id | Integer | 是 | 外键，评价用户 |
| window_id | Integer | 是 | 外键，被评窗口 |
| dish_id | Integer | 否 | 外键，关联具体菜品（可选） |
| score_food | Float | 是 | 口味评分 (1-10) |
| score_environment | Float | 是 | 环境评分 (1-10) |
| score_service | Float | 是 | 服务评分 (1-10) |
| score_safety | Float | 是 | 食安评分 (1-10) |
| tags | String(500) | 否 | 评价标签（JSON格式存储） |
| images | Text | 否 | 评价图片（JSON数组） |
| reply_content | Text | 否 | 商家回复 |
| ... | ... | ... | (基础字段同上) |

### 8. 笔记表 (post)
| 字段名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| id | Integer | 是 | 主键ID |
| user_id | Integer | 是 | 发布者 |
| canteen_id | Integer | 否 | 关联食堂 |
| title | String(100) | 是 | 标题 |
| content | Text | 是 | 正文内容 |
| status | Integer | 是 | 审核状态 (0=待审核, 1=通过, 2=驳回) |
| like_count | Integer | 否 | 点赞数 |
| ... | ... | ... | (基础字段同上) |

### 9. 食安公示表 (safety_notice)
| 字段名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| id | Integer | 是 | 主键ID |
| canteen_id | Integer | 是 | 归属食堂 |
| title | String(100) | 是 | 证书标题 |
| type | String(50) | 是 | 类型（certificate/report） |
| image_url | String(255) | 是 | 证书图片地址 |
| expire_date | DateTime | 否 | 有效期截止 |
| ... | ... | ... | (基础字段同上) |

### 10. 敏感词表 (sensitive_word)
| 字段名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| id | Integer | 是 | 主键ID |
| word | String(50) | 是 | 敏感词内容 |
| action_type | String(20) | 是 | 处理动作（block=拦截, replace=替换） |
| replace_to | String(50) | 否 | 替换字符（默认***） |
| ... | ... | ... | (基础字段同上) |

---

## 四、运行说明

### 1. 环境准备
确保已安装 Python 环境及 SQLAlchemy 库：
```bash
pip install sqlalchemy
```

### 2. 执行脚本
在项目目录下运行生成的 Python 脚本：
```bash
python create_tables.py
```

### 3. 结果验证
脚本执行成功后，会在当前目录生成 `canteen_evaluation.db` 文件。您可以使用 DB Browser for SQLite 或 VS Code 插件查看生成的表结构。
