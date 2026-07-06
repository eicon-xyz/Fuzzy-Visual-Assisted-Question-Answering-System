# HAJIMI 自动操作助手 — API 接口契约 v1.0

> B 端 UI 开发参考文档 | 2026-07-04 | MVP

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
| `POST` | `/api/demo/execute` | 提交任务，返回 task_id | 需要 |
| `GET` | `/api/demo/stream/{task_id}` | SSE 实时推送执行进度 | 无(同上) |
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

### 3.2 提交任务

```
POST /api/demo/execute
X-Demo-Key: hajimi-demo-2026
Content-Type: application/json
```

**请求体**：
```json
{
  "query": "帮我把微信安装到D盘",
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
    "goal": "安装微信到D盘",
    "total_steps": 5,
    "steps": [
      {
        "step_index": 1,
        "action": "click",
        "description": "双击桌面上的浏览器图标",
        "target_element_id": "~3",
        "element_type": "icon",
        "bbox": [120, 340, 180, 410],
        "bbox_center": [150, 375],
        "params": null,
        "status": "pending"
      },
      {
        "step_index": 2,
        "action": "type",
        "description": "在地址栏输入微信官网",
        "target_element_id": "~7",
        "element_type": "input",
        "bbox": [200, 50, 800, 90],
        "bbox_center": [500, 70],
        "params": "weixin.qq.com",
        "status": "pending"
      },
      {
        "step_index": 3,
        "action": "click",
        "description": "点击下载按钮",
        "target_element_id": "~12",
        "element_type": "button",
        "bbox": [400, 500, 560, 550],
        "bbox_center": [480, 525],
        "params": null,
        "status": "pending"
      },
      {
        "step_index": 4,
        "action": "double_click",
        "description": "双击下载的安装程序",
        "target_element_id": "~5",
        "element_type": "icon",
        "bbox": [100, 600, 160, 660],
        "bbox_center": [130, 630],
        "params": null,
        "status": "pending"
      },
      {
        "step_index": 5,
        "action": "click",
        "description": "安装向导中点击下一步",
        "target_element_id": "~18",
        "element_type": "button",
        "bbox": [700, 500, 800, 540],
        "bbox_center": [750, 520],
        "params": null,
        "status": "pending"
      }
    ]
  },
  "screenshot_base64": "data:image/jpeg;base64,...",
  "reference_resolution": [1920, 1080],
  "detection_meta": {
    "element_count": 24,
    "latency_ms": 3200,
    "backend": "local_omniparser"
  }
}
```

**Step action 取值**：
| action | 含义 | params |
|--------|------|--------|
| `click` | 鼠标左键单击 | null |
| `double_click` | 鼠标左键双击 | null |
| `right_click` | 鼠标右键 | null |
| `type` | 键盘输入文字 | 要输入的字符串 |
| `press_key` | 按组合键 | "ctrl+c" / "alt+tab" / "enter" |
| `scroll` | 滚轮滚动 | 正数向上，负数向下 |
| `wait` | 等待 | 等待秒数 |
| `drag` | 拖拽 | [start_x, start_y, end_x, end_y] |

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
| `NO_ELEMENTS` | 截图未检测到 UI 元素 |
| `LLM_FAILED` | LLM 规划失败 |
| `OMNIPARSER_FAILED` | OmniParser 不可达 |

---

### 3.3 SSE 事件流

```
GET /api/demo/stream/{task_id}
Accept: text/event-stream
```

**连接建立后**，A 端持续推送以下事件：

#### 事件类型一览

| event | 时机 | 含义 |
|-------|------|------|
| `plan_ready` | 执行开始 | 执行计划已生成 |
| `step_start` | 每步开始 | 即将执行某步骤 |
| `step_executing` | 执行中 | 正在执行操作 |
| `step_done` | 每步结束 | 步骤成功完成 |
| `step_failed` | 步骤失败 | 步骤执行失败 |
| `step_retry` | 重试 | 正在降级重试 |
| `step_blocked` | 拦截 | 安全红线拦截 |
| `log` | 任意时刻 | 日志信息 |
| `screenshot` | 每步验证后 | 新截图 |
| `task_done` | 全部完成 | 任务结束 |
| `task_error` | 任务失败 | 任务级错误 |
| `heartbeat` | 每5秒 | 保活 |

#### 事件详细格式

**`plan_ready`**
```
event: plan_ready
data: {"task_id": "a1b2...", "goal": "安装微信到D盘", "total_steps": 5, "steps": [...]}
```
data 结构与 3.2 中的 `plan.steps` 相同。

**`step_start`**
```
event: step_start
data: {"step_index": 1, "action": "click", "description": "双击桌面上的浏览器图标", "bbox_center": [150, 375]}
```

**`step_executing`**
```
event: step_executing
data: {"step_index": 1, "detail": "移动鼠标到 (150,375)"}
```

**`step_done`**
```
event: step_done
data: {"step_index": 1, "duration_ms": 2300, "verified": true}
```

**`step_failed`**
```
event: step_failed
data: {"step_index": 1, "error": "坐标超出屏幕范围", "will_retry": true}
```

**`step_retry`**
```
event: step_retry
data: {"step_index": 1, "attempt": 2, "method": "坐标降级重试"}
```

**`step_blocked`**
```
event: step_blocked
data: {"step_index": 3, "reason": "检测到涉及密码输入操作", "category": "high_risk"}
```

**`log`**
```
event: log
data: {"level": "info", "message": "正在截图验证步骤 2 的执行结果...", "timestamp": "2026-07-04T20:30:00"}
```

level 取值: `"info"` | `"warn"` | `"error"` | `"debug"`

**`screenshot`**
```
event: screenshot
data: {"image_base64": "data:image/jpeg;base64,/9j/...", "width": 1920, "height": 1080}
```
⚠️ JPEG 格式，质量 70%，最长边 1024px。B 端用 QPixmap 加载即可。

**`task_done`**
```
event: task_done
data: {"task_id": "a1b2...", "success": true, "total_duration_ms": 18300, "steps_completed": 5, "steps_failed": 0}
```

**`task_error`**
```
event: task_error
data: {"task_id": "a1b2...", "error": "LLM 规划超时"}
```

**`heartbeat`**
```
event: heartbeat
data: {"timestamp": "..."}
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

## 4. B 端 UI 数据流建议

```
1. GET /health → 确认服务可用
2. 用户输入指令 → POST /execute → 获取 task_id + plan
3. UI 展示 plan.steps 列表（全部 pending 状态）
4. 启动 EventSource GET /stream/{task_id}
5. SSE 事件驱动 UI 更新:
   - step_start → 该步骤高亮，状态→active
   - screenshot → 更新截图预览
   - step_done → 该步骤打勾✅，状态→done
   - step_failed → 该步骤标红❌
   - task_done → 全部完成，显示汇总
6. 用户点暂停/停止 → POST /cancel
```

---

## 5. CORS

A 端已配置全放通 (`allow_origins=["*"]`)，B 端直接用 `QNetworkAccessManager` 或 `urllib` 发请求即可，无需跨域处理。

---

## 6. 超时参考

| 操作 | 典型耗时 | 超时 |
|------|---------|------|
| OmniParser 检测 | 3–8s | 30s |
| LLM 规划 | 5–15s | 60s |
| 单步执行(点击) | 0.5–1s | 5s |
| 单步执行(打字) | 1–3s | 10s |
| 截图验证 | 3–8s | 30s |
| 完整任务(5步) | 20–60s | 120s |
