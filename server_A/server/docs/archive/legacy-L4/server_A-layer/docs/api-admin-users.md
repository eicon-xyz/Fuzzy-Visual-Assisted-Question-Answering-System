# HAJIMI 管理员用户管理 API

> Base: `http://<host>:8010/api/admin/users`
> 认证方式：`X-Admin-Key: hajimi-demo-2026` **或** `Authorization: Bearer <admin-jwt>`
> 两种认证任选其一即可。JWT 方式要求 role=admin。

---

## 1. GET /api/admin/users/list — 用户列表

分页查询，支持按用户名模糊搜索。返回每个用户的简要信息和任务数量。

**Query 参数:**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| page | int | 1 | 页码，从 1 开始 |
| page_size | int | 20 | 每页条数 |
| search | string | — | 按 username 模糊匹配，空则返回全部 |

**curl:**
```bash
# 用 X-Admin-Key
curl "http://127.0.0.1:8010/api/admin/users/list?page=1&page_size=20" \
  -H "X-Admin-Key: hajimi-demo-2026"

# 搜索
curl "http://127.0.0.1:8010/api/admin/users/list?page=1&page_size=20&search=zhang" \
  -H "X-Admin-Key: hajimi-demo-2026"

# 用 JWT
curl "http://127.0.0.1:8010/api/admin/users/list?page=1" \
  -H "Authorization: Bearer eyJhbG..."
```

**响应 200:**
```json
{
  "success": true,
  "data": {
    "total": 150,
    "items": [
      {
        "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "username": "zhangsan",
        "role": "user",
        "is_active": true,
        "task_count": 42,
        "last_login_at": "2026-07-08T10:00:00Z",
        "created_at": "2026-07-01T08:00:00Z"
      }
    ]
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| total | int | 符合条件的用户总数 |
| items[].user_id | string | UUID |
| items[].username | string | 用户名 |
| items[].role | string | `"user"` 或 `"admin"` |
| items[].is_active | bool | 账号是否启用 |
| items[].task_count | int | 该用户的任务总数 |
| items[].last_login_at | string/null | 最后登录时间 (ISO 8601) |
| items[].created_at | string/null | 注册时间 (ISO 8601) |

---

## 2. GET /api/admin/users/stats/{user_id} — 用户任务统计

获取指定用户的详细任务统计数据。

**curl:**
```bash
curl http://127.0.0.1:8010/api/admin/users/stats/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "X-Admin-Key: hajimi-demo-2026"
```

**响应 200:**
```json
{
  "success": true,
  "data": {
    "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "username": "zhangsan",
    "total_tasks": 42,
    "success_rate": 0.857,
    "total_failures": 5,
    "total_feedback": 30,
    "last_active_at": "2026-07-08T11:00:00Z"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| total_tasks | int | 总任务数 |
| success_rate | float | 成功率 (0.0-1.0) |
| total_failures | int | 失败任务数 |
| total_feedback | int | 反馈总数 |
| last_active_at | string/null | 最后一次任务时间 |

**响应 404:**
```json
{
  "success": false,
  "error": {
    "code": "USER_NOT_FOUND",
    "message": "用户不存在"
  }
}
```

---

## 3. POST /api/admin/users/reset-password — 重置密码

管理员为指定用户设置新密码。

**curl:**
```bash
curl -X POST http://127.0.0.1:8010/api/admin/users/reset-password \
  -H "X-Admin-Key: hajimi-demo-2026" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"a1b2c3d4-e5f6-7890-abcd-ef1234567890","new_password":"newpass456"}'
```

**请求体:**
```json
{
  "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "new_password": "newpass456"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | ✅ | 目标用户 ID |
| new_password | string | ✅ | 新密码，6-128 字符 |

**响应 200:**
```json
{
  "success": true,
  "data": {
    "message": "密码已重置"
  }
}
```

**响应 400（不能重置自己）:**
```json
{
  "success": false,
  "error": {
    "code": "CANNOT_DELETE_SELF",
    "message": "不能通过此接口重置自己的密码"
  }
}
```

---

## 4. DELETE /api/admin/users/{user_id} — 删除用户

删除用户账号。该用户的历史任务和反馈数据**保留**，但 `user_id` 字段会被置空。

**curl:**
```bash
curl -X DELETE http://127.0.0.1:8010/api/admin/users/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "X-Admin-Key: hajimi-demo-2026"
```

**响应 200:**
```json
{
  "success": true,
  "data": {
    "message": "用户已删除"
  }
}
```

**响应 400（不能删除自己）:**
```json
{
  "success": false,
  "error": {
    "code": "CANNOT_DELETE_SELF",
    "message": "不能删除自己"
  }
}
```

---

## 5. 错误码汇总

| code | HTTP | 说明 |
|------|------|------|
| AUTH_FAILED | 401 | X-Admin-Key 无效或 JWT 无效/非管理员 |
| USER_NOT_FOUND | 404 | 用户不存在 |
| CANNOT_DELETE_SELF | 400 | 不能删除或重置自己的密码 |

> **注意**: CANNOT_DELETE_SELF 仅在 JWT 认证时生效（可以识别当前用户身份）。X-Admin-Key 认证时不会触发此限制。
