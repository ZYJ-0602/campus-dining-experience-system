# 评价系统接口变更文档

## 1. 提交评价接口 (`/api/submit_evaluation`)

### 1.1 接口说明
*   **路径**: `/api/submit_evaluation`
*   **方法**: `POST`
*   **描述**: 提交包含菜品、服务、环境、食品安全的综合评价。

### 1.2 新增与变更字段
为了支持评价维度的拆分和图文混排，`Request Body` (JSON) 进行了如下变更：

| 字段名 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `service_comment` | String | 否 | 服务评价文字备注（自适应高度文本框输入） |
| `service_images` | Array | 否 | 服务评价图片URL/Base64数组，最多6张 |
| `env_comment` | String | 否 | 环境评价文字备注 |
| `env_images` | Array | 否 | 环境评价图片URL/Base64数组，最多6张 |
| `safety_comment` | String | 否 | 食品安全评价文字备注 |
| `safety_images` | Array | 否 | 食品安全评价图片URL/Base64数组，最多6张 |

### 1.3 移除或修改的逻辑
*   **频率限制 (Anti-spam)**:
    *   **移除**: 移除“每日最多评价 3 次”以及“同一天同一窗口限制”。
    *   **新增**: 增加 30 秒防刷限制，即同一用户在 30 秒内不能连续调用提交接口。

### 1.4 错误码变更
| 错误码 | HTTP状态码 | 提示信息 | 触发条件 |
| :--- | :--- | :--- | :--- |
| 400 | 200 (业务报错) | `提交过于频繁，请30秒后再试` | 用户距离上一次成功提交不足30秒 |

---

## 2. 数据库结构变更 (`models.py`)

表名: `evaluation_main`

**新增字段:**
*   `service_comment` (Text): 服务评价文字
*   `service_images` (Text): 服务评价图片JSON
*   `env_comment` (Text): 环境评价文字
*   `env_images` (Text): 环境评价图片JSON
*   `safety_comment` (Text): 食安评价文字
*   `safety_images` (Text): 食安评价图片JSON