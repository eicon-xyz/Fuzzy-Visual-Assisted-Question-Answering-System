# HAJIMI 认证 API

> Base: `http://<host>:8010/api/auth`
> 所有端点无需认证（公开接口）

---

## 1. POST /api/auth/register — 用户注册

注册新用户，注册后 role=user。

**curl:**
```bash
curl -X POST http://127.0.0.1:8010/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"zhangsan","password":"mypass123"}'
```

**请求体:**
```json
{
  "username": "zhangsan",
  "password": "mypass123"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | ✅ | 2-64 字符 |
| password | string | ✅ | 6-128 字符 |

**响应 200（成功）:**
```json
{
  "success": true,
  "data": {
    "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "username": "zhangsan",
    "created_at": "2026-07-08T12:00:00Z"
  }
}
```

**响应 409（用户名已存在）:**
```json
{
  "success": false,
  "error": {
    "code": "USERNAME_TAKEN",
    "message": "用户名 'zhangsan' 已被占用"
  }
}
```

---

## 2. POST /api/auth/login — 登录

用户名 + 密码登录，返回 JWT token pair。

**curl:**
```bash
curl -X POST http://127.0.0.1:8010/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"zhangsan","password":"mypass123"}'
```

**请求体:**
```json
{
  "username": "zhangsan",
  "password": "mypass123"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | ✅ | |
| password | string | ✅ | |

**响应 200（成功）:**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4gc3RyaW5n...",
    "token_type": "Bearer",
    "expires_in": 1800,
    "user": {
      "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "username": "zhangsan",
      "role": "user"
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| access_token | JWT，有效期 30 分钟 |
| refresh_token | 不透明字符串，有效期 7 天 |
| token_type | 固定 `"Bearer"` |
| expires_in | access_token 剩余有效秒数 (1800 = 30min) |
| user.role | `"user"` 或 `"admin"` |

**响应 401（用户名或密码错误）:**
```json
{
  "success": false,
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "用户名或密码错误"
  }
}
```

**响应 403（账号已禁用）:**
```json
{
  "success": false,
  "error": {
    "code": "USER_DISABLED",
    "message": "账号已被禁用"
  }
}
```

---

## 3. POST /api/auth/refresh — 刷新 Token

用 refresh_token 换取新的 token pair（rotation 策略：旧 refresh_token 立即失效）。

**curl:**
```bash
curl -X POST http://127.0.0.1:8010/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4gc3RyaW5n..."}'
```

**请求体:**
```json
{
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4gc3RyaW5n..."
}
```

**响应 200（成功）:**
同 login 响应，返回新的 `access_token` + `refresh_token`。

**响应 401（Token 已过期）:**
```json
{
  "success": false,
  "error": {
    "code": "TOKEN_EXPIRED",
    "message": "Token 已过期，请重新登录"
  }
}
```

**响应 401（Token 已被撤销）:**
```json
{
  "success": false,
  "error": {
    "code": "TOKEN_REVOKED",
    "message": "Token 已被撤销，请重新登录"
  }
}
```

> **注意:** 刷新成功后，旧的 refresh_token 立即失效。每次刷新都会清理该用户所有已过期的旧记录。

---

## 4. POST /api/auth/logout — 登出

撤销 refresh_token。**前端必须同时删除本地存储的 token。**

**curl:**
```bash
curl -X POST http://127.0.0.1:8010/api/auth/logout \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4gc3RyaW5n..."}'
```

**请求体:**
```json
{
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4gc3RyaW5n..."
}
```

**响应 200:**
```json
{
  "success": true,
  "data": {
    "message": "已登出"
  }
}
```

---

## 5. Token 使用方式

所有需要认证的 API，在请求头携带 access_token：

```
Authorization: Bearer <access_token>
```

### 生命周期

| Token | 有效期 | 存储位置 |
|-------|--------|----------|
| access_token | 30 分钟 | localStorage |
| refresh_token | 7 天 | localStorage |

### 前端建议流程

```
1. 登录成功 → 存 access_token + refresh_token 到 localStorage
2. 每次发 API 请求 → 读 access_token，放 Authorization header
3. 收到 401 → 用 refresh_token 调 /api/auth/refresh 换新 pair
   ├─ 成功 → 更新 localStorage，重试原请求
   └─ 失败 → 清空 localStorage，跳转登录页
4. 登出 → 调 /api/auth/logout → 清空 localStorage → 跳转登录页
```

---

## 6. 错误码汇总

| code | HTTP | 说明 |
|------|------|------|
| VALIDATION_ERROR | 422 | 参数校验失败（字段长度/格式不对） |
| USERNAME_TAKEN | 409 | 注册时用户名已被占用 |
| INVALID_CREDENTIALS | 401 | 用户名或密码错误 |
| USER_DISABLED | 403 | 账号已被管理员禁用 |
| TOKEN_EXPIRED | 401 | refresh_token 已过期 |
| TOKEN_REVOKED | 401 | refresh_token 已被撤销（重复使用旧 token） |
