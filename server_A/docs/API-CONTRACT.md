# HAJIMI 自动操作助手 — API 接口契约 v2.0

> B 端 UI 开发参考文档 | 2026-07-06 | Agent Loop Execution Mode

---

## 1. 服务信息

| 项目 | 值 |
|------|-----|
| A 端地址 | `http://127.0.0.1:8010` |
| OmniParser | `http://127.0.0.1:9800` |
| 认证方式 | Header: `X-Demo-Key: hajimi-demo-2026` |
| Content-Type | `application/json` |

---

## 2. 接口清单

| 方法 | 路径 | 用途 | 认证 |
|------|------|------|------|
| `GET` | `/api/demo/health` | 健康检查 | 无 |
| `POST` | `/api/demo/execute` | 提交任务，返回 task_id + plan | 需要 |
| `GET` | `/api/demo/stream/{task_id}` | SSE 实时推送执行进度 | 无 |
| `POST` | `/api/demo/cancel` | 取消/暂停任务 | 需要 |

---

## 3. 接口详情

### 3.1 健康检查

```
GET /api/demo/health
```

**响应 200**：
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

**响应 503** (OmniParser 不可用)：
```json
{
  "status": "degraded",
  "omniparser_ready": false,
  "message": "OmniParser 远程服务不可达"
}
```

---

### 3.2 提交任务 (Planning + Execution)

```
POST /api/demo/execute
X-Demo-Key: hajimi-demo-2026
Content-Type: application/json
```

**请求体**：
```json
{
  "query": "打开记事本，输入Hello,world!",
  "image": "data:image/png;base64,iVBORw0KGgo..."
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 用户自然语言指令，1–500 字符 |
| `image` | string | ✅ | 当前屏幕截图，base64 格式（含 data URI 前缀） |

**响应 200**：
```json
{
  "task_id": "a1b2c3d4-...",
  "success": true,
  "plan": {
    "goal": "打开记事本并输入Hello,world!",
    "total_steps": 2,
    "steps": [
      {
        "step_index": 1,
        "instruction": "打开记事本应用"
      },
      {
        "step_index": 2,
        "instruction": "在记事本中输入'Hello,world!'"
      }
    ]
  },
  "screenshot_base64": "data:image/jpeg;base64,...",
  "detection_meta": {
    "element_count": 24,
    "latency_ms": 3200,
    "backend": "omniparser"
  }
}
```

**注意**：Plan 中的 step 只有 `step_index` 和 `instruction`，不包含坐标/元素 ID。
Execution Agent 在运行时通过 tool-calling loop 自行决定每一步如何操作。

**错误响应**：
```json
{
  "success": false,
  "error": {
    "code": "REDLINE",
    "message": "检测到违规操作请求"
  }
}
```

**错误码**：

| code | 说明 |
|------|------|
| `REDLINE` | 红线拦截（安全违规） |
| `PLANNING_FAILED` | Planning Agent 规划失败 |
| `NO_PLAN` | 无法生成执行计划 |

---

### 3.3 SSE 事件流

```
GET /api/demo/stream/{task_id}
Accept: text/event-stream
```

SSE 格式：每行 `event: <type>\ndata: <json>\n\n`

#### 事件类型一览

| event | 时机 | data 字段 |
|-------|------|-----------|
| `heartbeat` | 连接建立 + 每 30s | `{"timestamp": "...", "task_id": "..."}` |
| `step_start` | 每步开始 | `{"step_index": N, "instruction": "..."}` |
| `tool_called` | LLM 调用工具 | `{"tool": "...", "args": {...}}` |
| `tool_result` | 工具返回结果 | `{"tool": "...", "success": true/false, ...}` |
| `screenshot_updated` | `get_screen_info` 调用后 | `{"step_index": N, "annotated_image": "data:image/jpeg;base64,..."}` |
| `step_done` | 步骤完成 | `{"step_index": N, "action_summary": "..."}` |
| `step_failed` | 步骤失败 | `{"step_index": N, "reason": "..."}` |
| `log` | 任意时刻 | `{"level": "info/warn/error", "message": "..."}` |
| `task_done` | 全部完成 | `{"task_id": "...", "goal": "...", "total_steps": N, "completed_steps": N}` |
| `task_failed` | 任务失败 | `{"reason": "...", "failed_step": N}` |
| `task_cancelled` | 用户取消 | `{}` |

#### 事件详细格式

**`step_start`**
```
event: step_start
data: {"step_index": 1, "instruction": "打开记事本应用"}
```

**`screenshot_updated`**
```
event: screenshot_updated
data: {"step_index": 1, "annotated_image": "data:image/jpeg;base64,/9j/..."}
```
⚠️ JPEG 格式，质量 70%，含 OmniParser 标注框。每次 `get_screen_info` 调用后推送。

**`step_done`**
```
event: step_done
data: {"step_index": 1, "action_summary": "launched app '记事本' (tier 1)"}
```

**`step_failed`**
```
event: step_failed
data: {"step_index": 2, "reason": "step failed after retries"}
```

**`log`**
```
event: log
data: {"level": "warn", "message": "步骤 2 失败，重试 1/1..."}
```

level 取值: `"info"` | `"warn"` | `"error"`

**`task_done`**
```
event: task_done
data: {"task_id": "a1b2...", "goal": "打开记事本并输入Hello,world!", "total_steps": 2, "completed_steps": 2}
```

**`task_failed`**
```
event: task_failed
data: {"reason": "step execution failed or cancelled", "failed_step": 2}
```

**`task_cancelled`**
```
event: task_cancelled
data: {}
```

**`heartbeat`**
```
event: heartbeat
data: {"timestamp": "2026-07-06T20:30:00", "task_id": "a1b2..."}
```

---

### 3.4 取消任务

```
POST /api/demo/cancel
X-Demo-Key: hajimi-demo-2026
Content-Type: application/json
```

**请求体**：
```json
{
  "task_id": "a1b2c3d4-..."
}
```

**响应 200**：
```json
{
  "success": true,
  "message": "任务已取消",
  "task_id": "a1b2c3d4-..."
}
```

---

## 4. B 端 UI 数据流

```
1. GET /health → 确认服务可用
2. 用户输入指令 → POST /execute → 获取 task_id + plan
3. UI 展示 plan.steps 列表（全部 pending 状态）
4. 启动 EventSource GET /stream/{task_id}
5. SSE 事件驱动 UI 更新:
   - step_start → 该步骤高亮，状态 → active
   - screenshot_updated → 解码 base64 → QPixmap → 更新截图预览
   - step_done → 该步骤打勾 ✅，状态 → done
   - step_failed → 该步骤标红 ❌
   - task_done → 全部完成，显示汇总
   - task_cancelled → 用户手动停止
6. 用户点停止 → POST /cancel
```

---

## 5. CORS

A 端已配置全放通 (`allow_origins=["*"]`)，B 端直接用 `QNetworkAccessManager` 或 `urllib` 发请求即可。

---

## 6. 超时参考

| 操作 | 典型耗时 | 超时 |
|------|---------|------|
| OmniParser 检测 | 3–8s | 30s |
| Planning Agent 规划 | 2–5s | 60s |
| 单步执行 (launch_app) | 3–5s | 30s |
| 单步执行 (get_screen_info + click) | 5–15s | 60s |
| 完整任务 (2步) | 10–30s | 120s |

---

## 7. 架构变化 (v1 → v2)

| 方面 | v1 (已废弃) | v2 (当前) |
|------|------------|----------|
| 规划方式 | LLM 一次性生成坐标+操作 | Planning Agent 文本规划 + Execution Agent tool-calling |
| Step 结构 | `{action, bbox, target_element_id, params}` | `{step_index, instruction}` |
| 坐标处理 | LLM 直接输出坐标 | LLM 只用 element_id，坐标由工具层解析 |
| SSE 事件 | `plan_ready, step_executing, screenshot` | `step_start, screenshot_updated, tool_called, tool_result` |
| 应用启动 | Win+Search 单一通道 | 三层降级（映射表 → PATH → Win+Search） |
