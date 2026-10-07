# HAJIMI 后端 API 接口文档

> 基地址: `http://<你的IP>:8010`
> 所有 `/api/demo/*` 接口需在 Header 带 `X-Demo-Key`
> Demo Key: `hajimi-demo-2026`
> 在线 Swagger 文档: `http://<你的IP>:8010/docs`

---

## 认证方式

所有 `/api/demo/*` 接口请求头必须携带：

```
X-Demo-Key: hajimi-demo-2026
```

---

## 一、Demo 核心接口 `/api/demo`

### 1. 健康检查

```
GET /api/demo/health
```

**无需认证**

**响应 200:**
```json
{
  "status": "ok",
  "version": "2.0.0",
  "detector_backend": "local_omniparser",
  "detector_active": "local_omniparser",
  "detector_device": "cuda",
  "omniparser_url": "http://127.0.0.1:9800",
  "omniparser_ready": true
}
```

**响应 503（OmniParser 不可达）:**
```json
{
  "status": "degraded",
  "version": "2.0.0",
  "omniparser_ready": false,
  "omniparser_url": "http://127.0.0.1:9800",
  "message": "OmniParser 远程服务不可达"
}
```

---

### 2. 提交执行任务（规划 + 自动执行）

```
POST /api/demo/execute
X-Demo-Key: hajimi-demo-2026
Content-Type: application/json
```

**请求体:**
```json
{
  "query": "帮我把这个文档保存为PDF",
  "image": "data:image/png;base64,iVBORw0KGgo...",
  "window_title": "新建 Microsoft Word 文档.docx - Word",
  "context": [
    {"role": "user", "content": "我想导出PDF"},
    {"role": "assistant", "content": "请问你想导出哪个文档？"}
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | ✅ | 用户指令，1-500字 |
| image | string | ❌ | Base64 截图，可带 `data:image/png;base64,` 前缀 |
| window_title | string | ❌ | 当前窗口标题 |
| context | array | ❌ | 多轮对话上下文，最多3轮 |

**响应 200（规划成功，后台开始执行）:**
```json
{
  "task_id": "abc123-456",
  "success": true,
  "plan": {
    "goal": "将Word文档另存为PDF",
    "total_steps": 3,
    "steps": [
      {"step_index": 1, "instruction": "点击 文件 菜单"},
      {"step_index": 2, "instruction": "点击 另存为"},
      {"step_index": 3, "instruction": "选择 PDF 格式并点击保存"}
    ]
  },
  "screenshot_base64": "data:image/png;base64,...",
  "detection_meta": {
    "latency_ms": 1234,
    "element_count": 45,
    "backend": "local_omniparser"
  }
}
```

**响应 200（红线拦截）:**
```json
{
  "success": false,
  "error": {
    "code": "REDLINE",
    "message": "检测到危险操作: 删除系统文件"
  }
}
```

**响应 200（规划失败）:**
```json
{
  "success": false,
  "error": {
    "code": "PLANNING_FAILED",
    "message": "LLM调用超时"
  }
}
```

---

### 3. SSE 执行进度推送

```
GET /api/demo/stream/{task_id}
```

**无需认证（但 task_id 需有效）**

这是一个 **Server-Sent Events** 端点，用于实时接收执行进度。前端应使用 `EventSource` 连接。

**SSE 事件类型:**

| event | data 内容 | 说明 |
|-------|-----------|------|
| `heartbeat` | `{"timestamp":"...", "task_id":"..."}` | 连接保活，30s一次 |
| `step_start` | `{"step_index":1,"instruction":"点击文件菜单","step_index":1}` | 步骤开始执行 |
| `screenshot_update` | `{"step_index":1,"annotated_image":"base64..."}` | 执行过程中的截图更新 |
| `step_done` | `{"step_index":1,"instruction":"点击文件菜单","step_index":1,"action_summary":"已点击文件菜单"}` | 步骤执行成功 |
| `step_failed` | `{"step_index":1,"error":"元素未找到"}` | 步骤执行失败 |
| `task_done` | `{"task_id":"abc123","goal":"...","total_steps":3}` | 全部步骤执行完毕 |
| `task_failed` | `{"task_id":"abc123","error":"..."}` | 任务级别失败 |
| `task_cancelled` | `{}` | 任务被取消 |

---

### 4. 取消任务

```
POST /api/demo/cancel
X-Demo-Key: hajimi-demo-2026
Content-Type: application/json
```

**请求体:**
```json
{
  "task_id": "abc123-456"
}
```

**响应:**
```json
{
  "success": true,
  "message": "任务已取消",
  "task_id": "abc123-456"
}
```

---

### 5. 仅规划（兼容旧版，不自动执行）

```
POST /api/demo/process
X-Demo-Key: hajimi-demo-2026
Content-Type: application/json
```

请求体与 `/execute` 相同，但只返回规划结果不执行。

---

## 二、管理接口 `/api/admin`

所有接口需携带 Header: `X-Admin-Key: hajimi-demo-2026`

### 统计总览
```
GET /api/admin/stats/overview
```
返回事务总量、成功率、L2/L3占比等 KPI。

### 高频任务 TOP10
```
GET /api/admin/stats/top-tasks?limit=10
```

### 24h 趋势
```
GET /api/admin/stats/trend
```

### 红线拦截统计
```
GET /api/admin/stats/redline
```

### 反馈分布
```
GET /api/admin/stats/feedback
```

### 失败记录列表
```
GET /api/admin/failures/list?limit=20&offset=0
```

### 单条失败详情
```
GET /api/admin/failures/detail/{task_id}
```

### 系统配置
```
GET /api/admin/config/current
```

### 性能指标
```
GET /api/admin/metrics
```

### 会话状态
```
GET /api/admin/session/status
```

---

## 三、完整调用流程

```
前端                             后端
 │                                │
 ├─ GET /api/demo/health ────────→│ 检查服务状态
 │←──── 200 ok ──────────────────┤
 │                                │
 ├─ POST /api/demo/execute ──────→│ 提交截图+指令
 │    {query, image}              │ 红线检测 → 规划 → 生成步骤
 │←──── 200 {task_id, plan} ─────┤ 返回任务ID和计划
 │                                │ 后台启动Agent执行循环
 │                                │
 ├─ GET /api/demo/stream/{id} ──→│ 连接SSE
 │←──── event: step_start ───────┤
 │←──── event: step_done ────────┤
 │←──── event: step_start ───────┤
 │←──── event: step_done ────────┤
 │←──── event: task_done ────────┤ 执行完毕
 │                                │
 │  (中途可取消)                   │
 ├─ POST /api/demo/cancel ───────→│
 │←──── 200 ─────────────────────┤
```

---

## 四、错误码汇总

| code | HTTP状态 | 说明 |
|------|----------|------|
| AUTH_FAILED | 401 | X-Demo-Key 无效 |
| REDLINE | 200 | 红线拦截，拒绝执行 |
| PLANNING_FAILED | 200 | LLM 规划失败 |
| NO_PLAN | 200 | 无法生成执行计划 |
| INTERNAL_ERROR | 500 | 服务器内部错误 |
| NOT_FOUND | 404 | 记录不存在 |
