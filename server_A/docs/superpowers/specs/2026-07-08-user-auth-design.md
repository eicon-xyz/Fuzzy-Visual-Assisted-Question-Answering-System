# HAJIMI 用户认证与账号管理 — 设计文档

> 日期：2026-07-08
> 涉及：A 端 FastAPI Server

---

## 1. 需求概述

| 需求 | 说明 |
|------|------|
| 用户注册（B 端） | 用户名 + 密码，注册后 role=user |
| 用户登录（B 端 + Web-admin） | 用户名 + 密码 → JWT token pair |
| 管理员登录（Web-admin） | 种子账号，.env 配置，role=admin |
| 管理员查看用户列表 | 分页 + 搜索，含任务统计 |
| 管理员查看用户统计 | 单用户任务量/成功率/反馈等 |
| 管理员重置用户密码 | 管理员设新密码 |
| 管理员删除用户 | 删用户，历史数据 user_id 置 NULL |
| Token 刷新 | rotation 策略，刷新时清理该用户过期记录 |
| 登出 | 标记 refresh_token.revoked_at |

---

## 2. 认证流程

```
注册:  POST /api/auth/register → 创建 User → 返回 user_id
登录:  POST /api/auth/login → bcrypt 验证 → 签发 access(30m) + refresh(7d) → 返回 token pair
刷新:  POST /api/auth/refresh → 验证 refresh → 旧 token revoke → 发新 pair → 清理该用户过期记录
登出:  POST /api/auth/logout → revoke refresh_token → 前端删 localStorage
```

### 后续请求

```
Authorization: Bearer <access_token>
```

### 管理员种子

启动时从 .env 读 `ADMIN_USERNAME` / `ADMIN_PASSWORD`（默认 admin/admin），不存在则写入 `t_users`（role=admin）。

---

## 3. API 路由

### 3.1 认证模块 `/api/auth`（无需认证）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/refresh` | 刷新 token |
| POST | `/api/auth/logout` | 登出 |

### 3.2 管理员用户管理 `/api/admin/users`（需 X-Admin-Key 或 JWT admin）

| 方法 | 路径 | Body | 说明 |
|------|------|------|------|
| GET | `/api/admin/users/list` | — | 用户列表（分页+搜索）. Query: `?page=1&page_size=20&search=zhang` |
| GET | `/api/admin/users/stats/{user_id}` | — | 某用户任务统计 |
| POST | `/api/admin/users/reset-password` | `{user_id, new_password}` | 管理员重置用户密码 |
| DELETE | `/api/admin/users/{user_id}` | — | 删除用户（历史数据 user_id 置 NULL） |

### 3.3 认证策略

Admin 路由同时接受 `X-Admin-Key` 和 `Authorization: Bearer <JWT>`，任一通过即可。向后兼容。

---

## 4. 数据模型变更

### 新增表：`t_refresh_tokens`

| 列 | 类型 | 说明 |
|------|------|------|
| token_id | String(64) PK | UUID4 |
| user_id | String(64) FK → t_users | |
| token_hash | String(256) UNIQUE | SHA-256 hash |
| expires_at | DateTime | 7 天 |
| revoked_at | DateTime nullable | 撤销时间 |
| created_at | DateTime | |

### 变更表：`t_users`

| 变更 | 说明 |
|------|------|
| + is_active | Boolean, default True |

### 删除用户

`t_users` 删记录；`t_transactions.user_id` 和 `t_feedback.user_id` 置 NULL（已有 nullable FK）。

---

## 5. 配置项（.env 新增）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| JWT_SECRET | `hajimi-jwt-secret-change-me` | JWT 签名密钥 |
| JWT_EXPIRE_MINUTES | 30 | access token 有效期 |
| REFRESH_EXPIRE_DAYS | 7 | refresh token 有效期 |
| ADMIN_USERNAME | admin | 管理员用户名 |
| ADMIN_PASSWORD | admin | 管理员初始密码 |

---

## 6. 统一响应格式

```json
// 成功
{ "success": true, "data": { ... } }

// 失败
{ "success": false, "error": { "code": "...", "message": "..." } }
```

### 错误码

| code | HTTP | 说明 |
|------|------|------|
| VALIDATION_ERROR | 422 | 参数校验 |
| USERNAME_TAKEN | 409 | 用户名已存在 |
| INVALID_CREDENTIALS | 401 | 用户名或密码错误 |
| USER_DISABLED | 403 | 账号已禁用 |
| TOKEN_EXPIRED | 401 | refresh_token 已过期 |
| TOKEN_REVOKED | 401 | refresh_token 已被撤销 |
| USER_NOT_FOUND | 404 | 用户不存在 |
| ADMIN_REQUIRED | 403 | 需管理员权限 |
| CANNOT_DELETE_SELF | 400 | 不能删除自己 |

---

## 7. 实现清单

| # | 文件 | 变更 |
|---|------|------|
| 1 | `server/config.py` | 新增 JWT/管理员 配置项 |
| 2 | `server/database/models.py` | 新增 RefreshToken 模型，User 加 is_active |
| 3 | `server/database/repository.py` | 新增 UserRepository、RefreshTokenRepository |
| 4 | `server/routes/auth.py` | 新建，4 个端点 |
| 5 | `server/routes/admin.py` | 新增 4 个用户管理端点 + admin JWT 认证 |
| 6 | `server/main.py` | 注册 auth router，启动时种子管理员 |
| 7 | `docs/api-auth.md` | 新建，前端对接文档 |
| 8 | `docs/api-admin-users.md` | 新建，前端对接文档 |
| 9 | `docs/api-reference.md` | 更新，补全 Auth 和 Admin Users 章节 |
