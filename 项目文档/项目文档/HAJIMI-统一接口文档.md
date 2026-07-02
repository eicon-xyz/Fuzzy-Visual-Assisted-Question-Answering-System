# HAJIMI 统一接口文档

> **版本**：1.0.0
> **日期**：2026-07-02
> **维护**：全体成员
> **语言约定**：中文行文，英文标识符（JSON 键名、端点路径、信号名称、枚举值保持英文）

---

## I. 版本与维护信息

### 1.1 文档定位

本文档是 HAJIMI 项目 **A↔B↔C 三组件间所有接口的唯一权威规范**，基于当前代码实际行为编写，取代以下旧文档：

| 被取代的文档 | 原因 |
|-------------|------|
| `api-contract-demo.md`（根目录 + 项目文档/） | 缺 `/inspect`、`/relocate`，`image` 仍标记为可选，health 响应字段不全 |
| `server/README.md` | 端点表不完整，缺关键环境变量 |
| `HAJIMI_UI/server/README.md` | 旧项目结构布局，端口号错误（8001 vs 8010） |

### 1.2 与现有文档的关系

| 文档 | 关系 |
|------|------|
| `b-c-api-contract.md` | **互补** — 本文档 IV 章为精简版，完整设计细节见该文档 |
| `a-c-api-contract.md` | **互补** — 本文档 V 章为摘要，完整 18 端点规范见该文档 |
| `B端接口总结-对A与对C.md` | **被取代** — B 端视角总结，内容已合并入本文档 |
| `CLAUDE.md` | **互补** — 项目指南，非接口规范 |
| `设计文档V2.md` | **互补** — 总体设计，非接口规范 |

### 1.3 不涵盖的范围

- OmniParser 内部 API（`:9800`，A 内部调用）
- DeepSeek API（`api.deepseek.com`，A 内部调用）
- Web 管理控制台前端 UI 细节
- 数据库 Schema 细节

---

## II. 架构概述

### 2.1 三组件关系

```
                        HTTP REST (JSON + Base64)
       ┌──────────┐  ───────────────────────────►  ┌──────────┐
       │ B 桌面端  │                                 │ A 后端   │
       │ PyQt5    │  ◄───────────────────────────  │ FastAPI  │
       │ Windows  │      ProcessResponse 等          │ :8000    │
       └────┬─────┘                                 └────┬─────┘
            │                                            │
            │ Qt 信号/槽（同进程）                         │ HTTP REST
            ▼                                            ▼
       ┌──────────┐                                ┌──────────┐
       │ C 集成层  │ ────── HTTP ──────────────────►│ A 后端   │
       │ (未构建)  │  审计上报 / 配置拉取              │ :8000    │
       └──────────┘                                └──────────┘
```

- **A ↔ B**：HTTP REST，B 作为客户端调用 A
- **B ↔ C**：进程内 PyQt5 信号/槽 + 共享状态字典，C 与 B 同进程
- **A ↔ C**：HTTP REST，C 作为客户端调用 A 的管理/审计接口

### 2.2 两种部署拓扑

| 拓扑 | A 端位置 | 端口 | B 连接地址 | 适用场景 |
|------|---------|------|-----------|---------|
| 独立 A | `server/` 直接启动 | `:8000` | `http://127.0.0.1:8000` | 开发调试 |
| 嵌入 A | B 的 `HAJIMI_UI/server/` | `:8010` | `http://127.0.0.1:8010` | 生产部署（`start_all.bat`） |

B 端默认通过 `HAJIMI_API_URL` 环境变量连接 A，默认值为 `http://127.0.0.1:8010`（嵌入 A）。

### 2.3 接口定义的关键源文件

| 组件 | 文件 | 角色 |
|------|------|------|
| A | `server/routes/demo.py` | 7 个 demo 端点实现 |
| A | `server/routes/admin.py` | 9 个 admin 端点实现 |
| A | `server/models/schemas.py` | **规范源** — Pydantic 请求/响应模型 |
| B | `HAJIMI_UI/core/api_client.py` | HTTP 客户端实现 |
| B | `HAJIMI_UI/server/models/schemas.py` | B 嵌入服务器的 Pydantic 模型（含差异字段） |
| B | `HAJIMI_UI/ui/app_controller.py` | 步骤状态机、覆盖层控制 |
| B | `HAJIMI_UI/ui/main_widget.py` | UI 组件连接、worker 管理 |
| B→C | `项目文档/b-c-api-contract.md` | B-C 信号契约设计 |
| A→C | `项目文档/a-c-api-contract.md` | A-C 管理 API 契约设计 |

---

## III. A-B 接口（HTTP REST）

### 3.1 基本连接信息

| 项目 | 值 |
|------|-----|
| **Base URL** | `http://127.0.0.1:8010`（B 默认）或 `http://127.0.0.1:8000`（独立 A） |
| **Content-Type** | `application/json` |
| **认证 Header** | `X-Demo-Key: hajimi-demo-2026` |
| **认证失败** | HTTP 401 `{"error":{"code":"AUTH_FAILED","message":"X-Demo-Key 无效"}}` |
| **B 端实现** | `HAJIMI_UI/core/api_client.py` — 原生 `urllib.request`，无第三方 HTTP 库 |

### 3.2 接口总览

| # | 方法 | 路径 | 认证 | B 端调用函数 | 超时 | 用途 |
|---|------|------|------|-------------|------|------|
| 1 | GET | `/api/demo/health` | 无 | `check_health()` / `fetch_health()` | 2s | 健康检查 + OmniParser 探测 |
| 2 | POST | `/api/demo/process` | X-Demo-Key | `process()` | 360s | **核心**：截图+问题→意图+元素+步骤+标注 |
| 3 | POST | `/api/demo/inspect` | X-Demo-Key | `inspect()` | 360s | 仅检测 UI 元素，不生成任务 |
| 4 | POST | `/api/demo/step` | X-Demo-Key | `advance_step()` | 30s | 推进/回退/跳过/终止步骤 |
| 5 | POST | `/api/demo/relocate` | X-Demo-Key | `relocate_step()` | 360s | 新截图重新定位目标元素 |
| 6 | POST | `/api/demo/clarify` | X-Demo-Key | （待接 UI） | 30s | 澄清不够明确的意图 |
| 7 | POST | `/api/demo/report` | X-Demo-Key | （Demo 由 C 代报） | 30s | 任务结果与反馈上报 |

### 3.3 端点详细定义

---

#### 3.3.1 `GET /api/demo/health` — 健康检查

- **认证**：不需要
- **B 端用途**：启动时轮询探测（延迟 12s，间隔 4s，最多 6 次）；每次 `/process`、`/inspect` 前预检

**请求**：无

**响应** `HealthResponse`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | `string` | 固定 `"ok"` |
| `version` | `string` | 服务版本号，如 `"1.0.0"` |
| `detector_backend` | `string?` | 检测后端类型：`"local_omniparser"`；缺失表示旧版/多开 A |
| `omniparser_ready` | `bool?` | OmniParser 是否可达（A 内部探测 `:9800`，超时 3s）；`false` 表示未就绪 |

```json
{
  "status": "ok",
  "version": "1.0.0",
  "detector_backend": "local_omniparser",
  "omniparser_ready": true
}
```

**B 端预检逻辑**（`check_process_preflight()` / `check_inspect_preflight()`）：
- `detector_backend` 为 `None` → 阻止，提示"旧版 A 端或多开实例"
- `omniparser_ready` 为 `false` → 阻止，提示"先启动 OmniParser"
- `omniparser_ready` 为 `None` → 阻止，提示"旧版 A 端"

---

#### 3.3.2 `POST /api/demo/process` — 核心流程入口

- **认证**：需要 `X-Demo-Key`
- **超时**：B 端 `PROCESS_TIMEOUT` = 360s（CPU OmniParser 需 2–4 分钟）

**请求** `ProcessRequest`：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| `query` | `string` | ✅ | 1–500 字符 | 用户自然语言问题 |
| `image` | `string` | ✅(实际) | Base64，可带 `data:image/png;base64,` 前缀 | 截图；代码中 `REQUIRE_IMAGE=true` |
| `window_title` | `string` | ❌ | max 256 | 当前活动窗口标题，辅助意图理解 |
| `context` | `ChatTurn[]` | ❌ | max 3 项 | 多轮对话历史，每项 `{role, content}` |

```json
{
  "query": "怎么安装微信？",
  "image": "data:image/png;base64,iVBORw0KGgo...",
  "window_title": "桌面",
  "context": []
}
```

**处理流程**（`server/services/planning/router.py`）：

```
query + image
    │
    ▼
① 红线检测 (redline_service) ──触发──→ 返回 success=false, redline={...}
    │ 未触发
    ▼
② 意图分类 (SetFit → keyword fallback)
    │
    ▼
③ 复杂度评分 → L2 (< 30: 模板匹配) / L3 (≥ 30: DeepSeek LLM)
    │
    ▼
④ OmniParser 解析截图 (POST :9800/parse)
    │
    ▼
⑤ L2: 正则模板匹配步骤   L3: DeepSeek 生成步骤 + 元素绑定
    │
    ▼
⑥ 构建标注 (第一步 arrow_highlight，后续 highlight_only)
    │
    ▼
⑦ 内存存储 + SQLite 双写
    │
    ▼
  返回 ProcessResponse
```

**响应** `ProcessResponse`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | `string` | UUID v4，后续 step/relocate/clarify/report 必须携带 |
| `success` | `bool` | 红线触发时为 `false` |
| `intent` | `Intent` | 意图分类结果 |
| `ui_elements` | `UIElement[]` | 截图中识别到的全部 UI 元素 |
| `annotated_image` | `string?` | SoM 标注后的截图 Base64，OmniParser 不返回时为 null |
| `blueprint` | `Blueprint` | 任务蓝图元信息 |
| `steps` | `Step[]` | 操作步骤列表 |
| `constraints` | `dict?` | 提取的用户约束（如安装路径），P4 功能 |
| `reference_resolution` | `[int, int]?` | 截图物理像素 `[w, h]`，B 端坐标映射的依据 |
| `detection_meta` | `dict?` | `{latency_ms, element_count, backend, route, complexity}` |
| `redline` | `RedlineInfo?` | 红线触发时非 null：`{triggered, category, message, action}` |

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "intent": {
    "category": "operation_guide",
    "summary": "安装微信",
    "reference_type": "explicit",
    "confidence": 0.92,
    "needs_clarification": false
  },
  "ui_elements": [
    {
      "element_id": "~1",
      "bbox": [120, 340, 200, 380],
      "element_type": "button",
      "text": "开始",
      "confidence": 0.95,
      "center": [160, 360]
    }
  ],
  "annotated_image": "data:image/png;base64,...",
  "blueprint": {
    "name": "安装微信",
    "total_steps": 3,
    "current_step": 1,
    "state": "executing"
  },
  "steps": [
    {
      "step_index": 1,
      "action": "click",
      "description": "点击「开始」按钮",
      "target_element_id": "~1",
      "status": "active",
      "annotation": {
        "type": "arrow_highlight",
        "arrow_from": [400, 360],
        "arrow_to": [160, 360],
        "highlight_bbox": [120, 340, 200, 380],
        "label_text": "① 点击这里"
      }
    }
  ],
  "reference_resolution": [2560, 1600],
  "detection_meta": {
    "latency_ms": 4200,
    "element_count": 47,
    "backend": "local_omniparser",
    "route": "L3",
    "complexity": 38
  }
}
```

---

#### 3.3.3 `POST /api/demo/inspect` — 检验模式（仅检测）

- **认证**：需要 `X-Demo-Key`
- **超时**：B 端 `INSPECT_TIMEOUT` = 360s
- **特点**：不创建 task，不生成 steps，仅返回 UI 元素和 SoM 图

**请求** `InspectRequest`：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `image` | `string` | ✅ | Base64 截图 |
| `screen_width` | `int?` | ❌ | 屏幕物理宽度 |
| `screen_height` | `int?` | ❌ | 屏幕物理高度 |

**响应** `InspectResponse`（A 端规范版，不含 `success` 包装）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ui_elements` | `UIElement[]` | 全部检测到的 UI 元素 |
| `annotated_image` | `string?` | SoM 标注截图 |
| `reference_resolution` | `[int, int]?` | 截图物理像素 |
| `detection_meta` | `dict?` | `{latency_ms, element_count, backend}` |

> **注意**：B 端嵌入服务器的 `InspectResponse` 增加了 `success: bool` 字段和 `reference_resolution` 改为必填 `List[int]`。B 端 `api_client.py` 的 `inspect()` 函数检查 `data.get("success")` 后才返回。

---

#### 3.3.4 `POST /api/demo/step` — 推进蓝图步骤

- **认证**：需要 `X-Demo-Key`
- **超时**：B 端 `API_TIMEOUT` = 30s

**请求** `StepRequest`：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | `string` | ✅ | process 返回的 UUID |
| `action` | `string` | ✅ | `"advance"` / `"rollback"` / `"skip"` / `"terminate"` |
| `step_index` | `int?` | ❌ | 当前步骤编号（≥1），B 端传 `current_step_index + 1` |
| `fingerprint` | `string?` | ❌ | 屏幕指纹 SHA256，严格模式下用于挂起检测 |
| `image` | `string?` | ❌ | 新截图 Base64；**动态重规划**：当前步骤无 `target_element_id` 时传入 |

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "action": "advance",
  "step_index": 1,
  "fingerprint": "abc123...",
  "image": "data:image/png;base64,..."
}
```

**响应** `StepResponse`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | `string` | 原 task_id |
| `action` | `string` | 实际执行的动作：`"advance"` / `"rollback"` / `"skip"` / `"suspended"` / `"complete"` / `"terminated"` |
| `current_step` | `int` | 执行后的当前步骤编号（≥1） |
| `blueprint_state` | `string` | 蓝图状态 |
| `next_step` | `Step?` | 下一步详情；挂起/终止/完成时为 null |
| `message` | `string?` | 人类可读的状态消息 |

**B 端处理逻辑**（`app_controller.py:_handle_step_response()`）：

| 响应 action | B 端行为 |
|------------|---------|
| `"suspended"` | 弹出 SuspensionDialog，用户选择 skip/rollback/abort |
| `"terminated"` | 显示"任务已终止"，清除覆盖层，状态回 idle |
| `"rollback"` | 步骤指针减 1，刷新前端步骤列表和覆盖层 |
| `"advance"` / `"skip"` | 步骤指针推进；若新步骤 `locate_deferred` 或无 `highlight_bbox`，触发 PrepareStep 流程 |
| `"complete"` | 调用 `_finish_task()`：显示"任务已结束"，清除覆盖层，切回 compact 模式 |

**动态重规划**（A 端 `demo.py` step 路由）：
当 `action == "advance"` 且 B 端传了 `image` 且推进后步骤无 `target_element_id` 时，A 端调用 DeepSeek 对新截图重新解析并绑定元素。

---

#### 3.3.5 `POST /api/demo/relocate` — 重新定位元素

- **认证**：需要 `X-Demo-Key`
- **超时**：B 端 `PROCESS_TIMEOUT` = 360s
- **触发场景**：PrepareStep 流程 — 当前画面找不到目标元素，用户手动操作后上传新截图

**请求** `RelocateRequest`：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | `string` | ✅ | 任务 UUID |
| `step_index` | `int` | ✅ | 需重定位的步骤编号（≥1） |
| `image` | `string` | ✅ | 新截图 Base64 |

**响应** `RelocateResponse`（A 端规范版）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | `string` | 原 task_id |
| `step_index` | `int` | 步骤编号 |
| `target_element_id` | `string?` | 匹配到的元素 ID，未找到为 null |
| `annotation` | `Annotation?` | 更新后的标注 |
| `ui_elements` | `UIElement[]` | 新截图的全部 UI 元素 |

**A 端处理流程**：
1. 对新截图调用 OmniParser 解析
2. 尝试 DeepSeek LLM 匹配目标元素（`_RELOCATE_PROMPT`）
3. LLM 失败则降级为文本关键词匹配
4. 更新步骤的 `target_element_id`、`annotation`，status 设为 `"active"`
5. 持久化到内存存储

**B 端实现**：`core/relocate_worker.py` + `ui/native/prepare_step_dialog.py`

---

#### 3.3.6 `POST /api/demo/clarify` — 主动澄清

- **认证**：需要 `X-Demo-Key`
- **触发场景**：process 返回 `intent.needs_clarification == true` 时

**请求** `ClarifyRequest`：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| `task_id` | `string` | ✅ | — | 任务 UUID |
| `answer` | `string` | ✅ | 1–500 | 用户对澄清问题的回答 |

**响应** `ClarifyResponse`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | `string` | 原 task_id |
| `confidence` | `float` | 更新后的置信度 0.0–1.0 |
| `needs_clarification` | `bool` | 是否仍需进一步澄清 |
| `question` | `string?` | 下一轮澄清问题（仅当 needs_clarification=true） |
| `updated_intent` | `Intent?` | 更新后的意图对象 |

> **Demo 简化**：当前仅将置信度 +0.1（上限 0.95），低于 0.80 则继续追问。未做真正的指代消解。

---

#### 3.3.7 `POST /api/demo/report` — 审计与反馈上报

- **认证**：需要 `X-Demo-Key`
- **调用时机**：任务结束后异步上报（Demo 阶段计划由 C 的审计代理调用）

**请求** `ReportRequest`：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| `task_id` | `string` | ✅ | — | 任务 UUID |
| `result` | `string?` | ❌ | `"success"` / `"fail"` / `"cancel"` / `"redirect"` | 任务结果 |
| `feedback_type` | `string?` | ❌ | `"useful"` / `"useless"` / `"neutral"` | 用户反馈类型 |
| `duration_ms` | `int?` | ❌ | ≥0 | 任务总耗时 |
| `comment` | `string?` | ❌ | — | 用户评语 |

**响应** `ReportResponse`：

```json
{ "received": true }
```

**A 端行为**：loguru 日志记录 + SQLite `t_feedback` 写入 + `t_transactions` 更新 result/duration_ms。

---

### 3.4 核心数据模型

#### UIElement — UI 元素

| 字段 | 类型 | 说明 |
|------|------|------|
| `element_id` | `string` | SoM 编号，如 `"~1"` |
| `bbox` | `[int×4]` | 边界框 `[x1, y1, x2, y2]`，**物理像素**，原点为截图左上角 |
| `element_type` | `string` | 枚举：`button` / `input` / `icon` / `menu` / `checkbox` / `dropdown` / `text` / `other` |
| `text` | `string?` | 元素上的文字 |
| `confidence` | `float` | 检测置信度 0.0–1.0 |
| `center` | `[int×2]?` | 元素中心点 `[cx, cy]` |

#### Annotation — 屏幕标注

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | `string` | 枚举：`arrow_highlight` / `highlight_only` / `arrow_only` / `label_only` / `none` |
| `arrow_from` | `[int×2]?` | 箭头起点（通常为面板侧） |
| `arrow_to` | `[int×2]?` | 箭头终点（目标元素 center） |
| `highlight_bbox` | `[int×4]?` | 高亮框，物理像素 |
| `label_position` | `[int×2]?` | 标签位置 |
| `label_text` | `string?` | 标签文字，如 `"① 点击这里"` |

#### Step — 操作步骤

| 字段 | 类型 | 说明 |
|------|------|------|
| `step_index` | `int` | 步骤编号（从 1 开始） |
| `action` | `string` | 操作类型：`click` / `input` / `select` 等 |
| `description` | `string` | 人类可读的步骤描述 |
| `target_element_id` | `string?` | 绑定的 UI 元素 ID |
| `status` | `string` | 枚举：`pending` → `active` → `done` / `skipped` / `failed` |
| `annotation` | `Annotation?` | 该步骤的屏幕标注 |

**B 端扩展字段**（仅 B 嵌入服务器 schemas，不在 A 规范中）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `locate_deferred` | `bool` | 当前画面无法定位目标，需用户手动操作后重新截图 |
| `prepare_hint` | `string?` | 手动操作提示，如 `"请打开开始菜单搜索 GitHub"` |

#### Blueprint — 任务蓝图

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `string` | 蓝图名称 |
| `total_steps` | `int` | 总步骤数（≥1） |
| `current_step` | `int` | 当前步骤编号（≥1） |
| `state` | `string` | 7 状态枚举：`generated` → `pending_confirm` → `executing`（可分支到 `suspended` / `rolling_back` / `completed` / `terminated`） |

#### Intent — 用户意图

| 字段 | 类型 | 说明 |
|------|------|------|
| `category` | `string` | 9 大意图域：`operation_guide` / `element_cognition` / `error_diagnosis` / `ui_navigation` / `content_cognition` / `file_management` / `proactive_alert` / `tutorial_generation` / `emotion_comfort` |
| `summary` | `string` | 意图摘要，如 `"安装微信"` |
| `reference_type` | `string?` | 指代类型：`explicit` / `visual` / `deictic` / `fuzzy` / `context` |
| `confidence` | `float` | 置信度 0.0–1.0 |
| `needs_clarification` | `bool` | 是否需要向用户澄清 |

### 3.5 统一错误响应格式

所有 A 端 API 错误遵循统一格式：

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "人类可读的错误描述",
    "details": {}
  }
}
```

| HTTP | code | 触发条件 | B 端处理 |
|------|------|---------|---------|
| 400 | `MISSING_IMAGE` | `/process` 缺少 image 字段 | 提示用户截图失败 |
| 400 | `INVALID_IMAGE` | Base64 解码失败 | 提示重新截图 |
| 400 | `INVALID_REQUEST` | step action 值不合法 | 显示错误信息 |
| 400 | `INVALID_STEP_INDEX` | relocate step_index 超出范围 | 显示步骤范围错误 |
| 401 | `AUTH_FAILED` | X-Demo-Key 缺失或无效 | 提示"检查 HAJIMI_DEMO_KEY" |
| 404 | `NOT_FOUND` | task_id 不存在 | 提示任务已过期 |
| 422 | — | Pydantic 请求验证失败（FastAPI 自动生成） | 显示验证错误详情 |
| 422 | `NO_ELEMENTS_DETECTED` | OmniParser 未检测到任何元素 | 提示"换含可见控件的截图" |
| 502 | `DETECTOR_FAILED` | OmniParser 不可用或内部错误 | 显示中文友好提示（含 OmniParser 启动指引） |
| 500 | `INTERNAL_ERROR` | 服务端未处理异常 | 显示错误详情 |

> **注意**：422 是 FastAPI 自动验证响应，格式为 `{"detail": [...]}`，不是上述 `{"error": {...}}` 格式。B 端 `_read_http_error()` 兼容两种格式。

### 3.6 Pydantic 模型差异说明

A 端规范（`server/models/schemas.py`）与 B 嵌入服务器（`HAJIMI_UI/server/models/schemas.py`）存在以下差异：

| 差异项 | A 规范 | B 嵌入服务器 | 影响 |
|--------|--------|-------------|------|
| `Step.locate_deferred` | 不存在 | `bool`（默认 False） | B 端用于标识需要 PrepareStep 的步骤 |
| `Step.prepare_hint` | 不存在 | `Optional[str]` | B 端用于显示手动操作提示文字 |
| `InspectResponse.success` | 不存在 | `bool` | B 端 `inspect()` 检查此字段 |
| `InspectResponse.reference_resolution` | `Optional[List[int]]` | `List[int]`（必填 2 项） | B 端需要非空分辨率 |
| `RelocateResponse.success` | 不存在 | `bool` | B 端 `relocate_step()` 检查此字段 |
| `RelocateResponse.reference_resolution` | 不存在 | `List[int]`（必填 2 项） | B 端 relocate 后需要新分辨率 |
| `RelocateResponse.message` | 不存在 | `Optional[str]` | B 端用于显示 relocate 结果消息 |
| `RelocateResponse.detection_meta` | 不存在 | `Optional[dict]` | B 端用于日志/调试 |
| `ProcessResponse.redline` | 存在 | 不存在 | A 端红线功能 |
| `ProcessResponse.constraints` | 存在 | 不存在 | A 端 P4 约束提取 |
| `StepRequest.image` | 存在 | 不存在 | A 端动态重规划 |

> **原则**：以 A 端 `server/models/schemas.py` 为规范源。B 嵌入服务器的额外字段是前端层注入的，不影响 A-B 之间的线上契约。

---

## IV. B-C 接口（Qt 信号）

### 4.1 通信模型

- B 和 C 运行在**同一个 PyQt5 进程**中
- 通信方式：**Qt 信号/槽** + **共享状态字典**
- C 同时作为 HTTP 客户端独立调用 A（审计上报、配置拉取）
- 耦合极低：B 和 C 可独立 Mock 测试

### 4.2 接口总览

| # | 接口名 | 方向 | 通信方式 | 用途 |
|---|--------|------|----------|------|
| 1 | ASR 录音控制 | B → C | 信号 `asr_start` / `asr_stop` | 麦克风按下/松开 → 启停录音 |
| 2 | ASR 转写结果 | C → B | 信号 `asr_result` | 语音→文字结果回传 |
| 3 | TTS 播报触发 | B → C | 信号 `tts_enqueue` | 步骤指引文字 → 语音播报 |
| 4 | TTS 状态回传 | C → B | 信号 `tts_status` | 播报开始/完成/错误 |
| 5 | 语音设置同步 | B → C | 共享状态 `voice_settings` | 开关/语速/引擎选择 |
| 6 | 审计数据提交 | B → C | 信号 `audit_submit` | 任务完成 → 入队异步上报 |
| 7 | 审计上报状态 | C → B | 信号 `audit_status` | 上报成功/失败/队列深度 |
| 8 | 配置拉取通知 | C → B | 信号 `config_updated` | 服务端配置变更 → B 热加载 |
| 9 | 心跳/健康检测 | B → C | 方法调用 `c_health_check()` | B 探测 C 各子模块是否正常 |

> 完整定义见 `项目文档/b-c-api-contract.md`。以下为精简版。

### 4.3 信号详细定义

#### 接口 1：ASR 录音控制

| 信号 | 方向 | 参数 | 触发时机 |
|------|------|------|---------|
| `asr_start` | B → C | 无 | 用户按下麦克风按钮 |
| `asr_stop` | B → C | 无 | 用户松开按钮 或 静默 2s 自动触发 |

#### 接口 2：ASR 转写结果

| 信号 | 方向 | 参数 |
|------|------|------|
| `asr_result` | C → B | `transcript: str`, `confidence: float`, `engine: str`, `error: str\|null` |

B 侧处理：填入输入框 → 若 confidence < 0.6 显示浅色文字 → 自动触发发送。

#### 接口 3：TTS 播报触发

| 信号 | 方向 | 参数 |
|------|------|------|
| `tts_enqueue` | B → C | `text: str`, `priority: int=0`, `interrupt_current: bool=false` |

C 侧队列逻辑：高优先级打断当前播放并清空队列；否则追加到队尾 FIFO 出队。

#### 接口 4：TTS 状态回传

| 信号 | 方向 | 参数 |
|------|------|------|
| `tts_status` | C → B | `status: str`（`playing`/`paused`/`completed`/`error`/`queue_empty`）, `text: str`, `queue_depth: int` |

B 侧处理：`playing` → 喇叭声波动画；其他 → 动画停止；`error` → Toast 提示。

#### 接口 5：语音设置同步

共享状态字典（非信号），B 写入，C 读取：

```python
voice_settings = {
    "tts_enabled": True,
    "tts_speed": 0.85,        # 0.5–1.5
    "tts_engine": "pyttsx3",  # pyttsx3 / azure / baidu
    "asr_enabled": True,
    "asr_engine": "vosk",     # vosk / baidu / google
    "asr_language": "zh-CN"
}
```

#### 接口 6：审计数据提交

| 信号 | 方向 | 参数 |
|------|------|------|
| `audit_submit` | B → C | `record: AuditRecord`（14 字段，详见 4.5） |

C 侧处理：隐私脱敏 → 写入本地 SQLite WAL → 累积 10 条或空闲 5 分钟 → 批量 POST `/api/audit/report`。

#### 接口 7：审计上报状态

| 信号 | 方向 | 参数 |
|------|------|------|
| `audit_status` | C → B | `status: str`（`success`/`failed`/`queued`）, `batch_size: int`, `queue_depth: int`, `error: str\|null` |

B 侧处理：`queue_depth > 50` → 状态栏显示积压警告。

#### 接口 8：配置拉取通知

| 信号 | 方向 | 参数 |
|------|------|------|
| `config_updated` | C → B | `config: ClientConfig`（11 字段，详见 4.5） |

C 定时轮询 `GET /api/config/pull`（默认 30 分钟），ETag 变化时 emit。

#### 接口 9：心跳/健康检测

| 方法 | 方向 | 返回值 |
|------|------|--------|
| `c_health_check()` | B → C（同步调用） | `HealthStatus`（8 字段，详见 4.5） |

### 4.4 C 端信号注册总表

```python
class VoiceIntegrationController:
    def __init__(self, b_signals, shared_state):
        # ASR
        b_signals.asr_start.connect(self.asr_client.start_recording)
        b_signals.asr_stop.connect(self.asr_client.stop_and_transcribe)
        self.asr_client.result_ready.connect(b_signals.asr_result.emit)
        # TTS
        b_signals.tts_enqueue.connect(self.tts_engine.enqueue)
        self.tts_engine.status_changed.connect(b_signals.tts_status.emit)
        # 语音设置
        self.voice_settings = shared_state["voice_settings"]
        # 审计
        b_signals.audit_submit.connect(self.audit_agent.enqueue)
        self.audit_agent.batch_result.connect(b_signals.audit_status.emit)
        # 配置
        self.config_poller.config_changed.connect(b_signals.config_updated.emit)
        # 健康
        b_signals.health_check_request.connect(self._handle_health_check)
```

### 4.5 数据模型

#### AuditRecord

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | `string` | ✅ | 任务 UUID |
| `query` | `string` | ✅ | 脱敏后的用户提问 |
| `intent_category` | `string` | ✅ | 九大意图域之一 |
| `complexity_score` | `int` | ✅ | 复杂度打分 |
| `route` | `string` | ✅ | `"L2"` / `"L3"` |
| `total_steps` | `int` | ✅ | 蓝图总步数 |
| `completed_steps` | `int` | ✅ | 实际完成步数 |
| `result` | `string` | ✅ | `"success"` / `"fail"` / `"cancel"` / `"redirect"` / `"rejected"` |
| `duration_ms` | `int` | ✅ | 任务总耗时（毫秒） |
| `feedback_type` | `string` | ❌ | `"useful"` / `"useless"` / `"neutral"` |
| `comment` | `string` | ❌ | 用户评语 |
| `fingerprint_mismatches` | `int` | ❌ | 指纹不匹配次数 |
| `redline_triggered` | `bool` | ❌ | 是否触发红线拦截 |
| `timestamp` | `string` | ✅ | ISO 8601 时间戳 |

#### HealthStatus

| 字段 | 类型 | 说明 |
|------|------|------|
| `asr_available` | `bool` | Vosk 模型是否可用 |
| `asr_engine` | `string` | 当前 ASR 引擎 |
| `tts_available` | `bool` | TTS 引擎是否可用 |
| `tts_engine` | `string` | 当前 TTS 引擎 |
| `audit_db_ok` | `bool` | 本地 SQLite 是否正常 |
| `server_reachable` | `bool` | A 端是否可达 |
| `queue_depth` | `int` | 离线审计队列深度 |
| `overall` | `string` | `"healthy"` / `"degraded"` / `"unhealthy"` |

#### ClientConfig

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `version` | `string` | ✅ | 配置版本号 |
| `confidence_threshold` | `int` | ✅ | 置信度阈值 50–100 |
| `llm_api_endpoint` | `string` | ✅ | LLM API 端点 |
| `llm_model` | `string` | ✅ | LLM 模型名称 |
| `max_blueprint_steps` | `int` | ✅ | 最大蓝图步骤数 |
| `token_limit` | `int` | ✅ | Token 超限阈值 |
| `config_pull_interval_min` | `int` | ✅ | 配置拉取间隔（分钟），最小 5 |
| `audit_batch_size` | `int` | ✅ | 审计上报批量大小 |
| `offline_tts_engine` | `string` | ✅ | 离线 TTS 引擎 |
| `routing_rules` | `object` | ✅ | L2/L3 路由规则 JSON |
| `updated_at` | `string` | ✅ | 更新时间 ISO 8601 |

### 4.6 当前实现状态

> ⚠️ **C 组件尚未构建**。以下为代码实际状态：

| 项目 | 状态 |
|------|------|
| B-C 信号定义（9 个 pyqtSignal） | ❌ 未在 B 端代码中定义 |
| `VoiceIntegrationController` 类 | ❌ 未实现 |
| 麦克风按钮 | ✅ 已创建，但**被禁用**（`setEnabled(False)`，tooltip "语音（即将推出）"） |
| 喇叭图标 / TTS 动画 | ❌ 未实现 |
| 语音设置面板 | ❌ 未实现 |
| B 端集成钩子 | ❌ `_finish_task()` 和步骤推进逻辑中无 C 调用 |

**B 端代码中 C 的 UI 预留位**（`medium_panel.py:586-591`）：

```python
mic_btn = QPushButton()
mic_btn.setObjectName("IconBtnGhost")
mic_btn.setIcon(action_icon("mic"))
mic_btn.setFixedSize(32, 32)
mic_btn.setToolTip("语音（即将推出）")
mic_btn.setEnabled(False)  # 等 C 接入后启用
```

**B 端预期的 C 集成点**（`main_widget.py:_init_native_ui()`）：

```python
# 待 C 接入后，在此初始化 VoiceIntegrationController：
# self.voice_controller = VoiceIntegrationController(self.controller, shared_state)
```

---

## V. A-C 接口（管理端 HTTP REST）

> 本节为摘要。完整 18 端点的详细定义见 `项目文档/a-c-api-contract.md`。

### 5.1 适用范围

A-C 接口服务于管理控制台（Web 面板）和 C 的后台代理（审计上报、配置拉取）。它不是核心 Demo 流程的一部分。

### 5.2 认证方式

| 端点类别 | 认证方式 | 说明 |
|---------|---------|------|
| `/api/admin/*` | `X-Admin-Key` header | Demo 阶段与 `X-Demo-Key` 值相同 |
| `/api/audit/*` | `X-Demo-Key` header | C 的审计代理使用 |
| `/api/config/pull` | `X-Demo-Key` header | C 的配置轮询器使用 |

### 5.3 实现状态总览

#### 已实现（9 个端点，`server/routes/admin.py`）

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/api/admin/stats/overview` | 仪表盘 KPI 总览（事务量、成功率、L2/L3 占比、红线统计） |
| 2 | GET | `/api/admin/stats/top-tasks` | 高频任务 TOP N（`?limit=` 参数，默认 10） |
| 3 | GET | `/api/admin/stats/trend` | 24 小时事务趋势（按小时聚合） |
| 4 | GET | `/api/admin/stats/redline` | 红线拦截统计（总量 + 按类别） |
| 5 | GET | `/api/admin/stats/feedback` | 用户反馈分布（useful/useless/neutral 计数） |
| 6 | GET | `/api/admin/failures/list` | 失败记录列表（`?limit=&offset=` 分页） |
| 7 | GET | `/api/admin/failures/detail/{task_id}` | 单条失败详情（含 fingerprint_hash、llm_snapshot） |
| 8 | GET | `/api/admin/config/current` | 获取全部系统配置 |
| 9 | POST | `/api/admin/config/deploy` | 热部署配置（`?key=&description=`，body 为 JSON value） |

**响应示例**（`/api/admin/stats/overview`）：

```json
{
  "total_transactions": 156,
  "success_count": 142,
  "fail_count": 10,
  "rejected_count": 4,
  "success_rate": 0.91,
  "l2_count": 89,
  "l3_count": 67,
  "l2_ratio": 0.57,
  "total_redlines": 4,
  "by_category": {"privacy": 2, "physical": 1, "dynamic_content": 1}
}
```

#### 设计但未实现（9 个端点，参见 `a-c-api-contract.md`）

| # | 方法 | 路径 | 用途 |
|---|------|------|------|
| 10 | POST | `/api/audit/report` | 批量上报审计日志（C 审计代理调用） |
| 11 | POST | `/api/audit/feedback` | 上报用户反馈 |
| 12 | GET | `/api/config/pull` | 客户端配置拉取（ETag 条件请求） |
| 13 | GET | `/api/admin/failures/stats` | 失败类型分布 + 趋势 |
| 14 | GET | `/api/admin/flow/topology` | 数据流拓扑实时数据 |
| 15 | GET | `/api/admin/flow/metrics` | 接口 QPS/成功率 |
| 16 | GET | `/api/admin/flow/versions` | 客户端版本分布 |
| 17 | GET | `/api/admin/monitor/health` | 组件健康状态 |
| 18 | GET | `/api/admin/monitor/alerts` | 告警列表 |

### 5.4 与 B-C 的关系

C 的审计代理和配置轮询器内部会调用 A-C 接口：
- **审计代理** → `POST /api/audit/report`（批量上报脱敏审计日志）
- **配置轮询器** → `GET /api/config/pull`（定时拉取配置，ETag 条件请求）

这些端点在 A 端尚未实现，是下一步工作。

---

## VI. 注意事项

### 6.1 认证体系

三种认证机制，不可混用：

| 认证方式 | Header 名 | 使用范围 |
|---------|----------|---------|
| Demo Key | `X-Demo-Key: hajimi-demo-2026` | `/api/demo/*` 全部 7 个端点 |
| Admin Key | `X-Admin-Key: hajimi-demo-2026` | `/api/admin/*` 全部 9 个端点 |
| JWT（计划） | `Authorization: Bearer <token>` | 生产环境管理端 |

- A 端 `server/config.py` 中 `DEMO_KEY` 统一控制两个 Key 的值
- B 端 `HAJIMI_UI/config.py` 中 `DEMO_KEY` 环境变量必须与 A 端一致
- Admin Key 与 Demo Key 目前值相同但 header 名不同
- **Health 端点无需认证**

### 6.2 端口与多实例

| 组件 | 端口 | 启动方式 |
|------|------|---------|
| OmniParser | `9800` | `scripts/start_omniparser.bat` |
| A 独立 | `8000` | `cd server && python main.py` |
| A 嵌入 | `8010` | B 端 `start_all.bat` 自动启动 |
| C 管理面板（计划） | `8090` | 尚未实现 |

- B 端默认连接 `:8010`（嵌入 A），而非 `:8000`（独立 A）
- **启动顺序**：① OmniParser → ② A 端 → ③ B 端（或 `start_all.bat` 一键启动）
- B 端退出时可选自动停止 A 和 OmniParser（`HAJIMI_STOP_SERVICES_ON_EXIT=1`）
- 多开 A 端会导致 `detector_backend` 字段缺失，B 端预检会判定为旧版并阻止

### 6.3 坐标系约定

> ⚠️ **这是最容易出问题的环节**

- `bbox`、`annotation.highlight_bbox`、`arrow_from`、`arrow_to` 均使用**物理像素**，原点为**截图左上角**
- A 端返回 `reference_resolution: [w, h]` 告诉 B 端截图像素尺寸
- B 端 `core/overlay_coords.py` 负责：物理像素 → Qt 逻辑坐标（HiDPI 适配，处理 `devicePixelRatio`）
- 当 `reference_resolution == B端截图尺寸` 时，**不再做** 1920×1080 缩放
- B 端 `core/coordinate_mapper.py` 使用 `adapt_annotation()` 按比例缩放参考分辨率到捕获尺寸

**三种像素空间**：
1. **参考像素**（A 端）：`reference_resolution` 中的尺寸
2. **捕获像素**（B 端截图）：`mss` 实际捕获的尺寸
3. **逻辑坐标**（Qt 覆盖层）：`devicePixelRatio` 换算后的坐标

### 6.4 启动顺序

```
① OmniParser (:9800) → ② A 后端 (:8000/:8010) → ③ B 前端
```

- B 端启动后会延迟 **12 秒** 开始健康探测（`STARTUP_HEALTH_DELAY_MS`）
- 探测间隔 4 秒，最多 6 次（`STARTUP_HEALTH_RETRY_MS` × `STARTUP_HEALTH_MAX_RETRIES`）
- 若 A 端/OmniParser 未就绪，B 端显示警告但仍可进入 Mock 模式
- `start_all.bat` 自动按正确顺序启动，等待 OmniParser 初始化

### 6.5 超时设置

| 超时 | 环境变量 | 默认值 | 原因 |
|------|---------|--------|------|
| Health | `HAJIMI_HEALTH_TIMEOUT` | 2s | 快速失败探测 |
| Process | `HAJIMI_PROCESS_TIMEOUT` | **360s** | CPU OmniParser 需 2–4 分钟 |
| Inspect | `HAJIMI_INSPECT_TIMEOUT` | **360s** | 同上 |
| Step | `HAJIMI_API_TIMEOUT` | 30s | 轻量级状态变更 |
| OmniParser（A 端内部） | `OMNIPARSER_TIMEOUT` | 30s | A 到 OmniParser 的调用 |
| DeepSeek（A 端内部） | `DEEPSEEK_TIMEOUT` | 30s | A 到 LLM 的调用 |

> ⚠️ `/process` 和 `/inspect` 的超时非常长（6 分钟），这是因为 CPU 模式下 OmniParser 全屏解析需 2–4 分钟。B 端 UI 在此期间显示"处理中"动画，用户不应重复点击。

### 6.6 Mock 降级策略

| 模式 | 环境变量 | process | inspect | step |
|------|---------|---------|---------|------|
| 正常 | 默认 | A 端真实调用 | A 端真实调用 | A 端真实调用 |
| 纯 Mock | `HAJIMI_MOCK_ONLY=1` | 本地模板匹配 | **不可用** | 本地 Mock |
| 降级 Mock | `HAJIMI_MOCK_FALLBACK=1` | A 失败时回退 Mock | 仍须 A 端 | step 失败时回退 Mock |

- Mock 模式仅匹配"wechat"/安装类查询，功能有限
- 检验（inspect）模式在 Mock 下完全不可用
- B 端 `api_client.py` 的 `process()` 在 `ALLOW_MOCK_FALLBACK` 模式下：先尝试 A，失败后用 `mock_backend.process_query()`

### 6.7 image 字段现为必填

- 原 Demo 契约中 `image` 为 `Optional[str]`
- 当前代码 `REQUIRE_IMAGE=true`：`/process` 和 `/inspect` 的 `image` 字段**必须提供**
- 缺失时返回 400 `MISSING_IMAGE`
- B 端 `TaskWorkerThread` 在调用 `/process` 前自动截图并编码为 `data:image/png;base64,...`

### 6.8 Pydantic 模型差异

详见 3.6 节。核心要点：
- A 端 `server/models/schemas.py` 是**规范源**
- B 嵌入服务器的额外字段（`locate_deferred`、`prepare_hint`、`success` 包装器）不影响线上契约
- 差异来源：B 嵌入服务器在 A 响应之上增加了前端层字段
- **联调时以 A 端 schemas 为准**，B 端额外字段是 B 内部逻辑

### 6.9 环境变量一致性

**A 端和 B 端必须一致的环境变量**：

| 变量 | 必须一致原因 |
|------|-------------|
| `HAJIMI_DEMO_KEY` | 认证密钥，不一致则全部 API 调用 401 |

**A 端独有**（`server/.env`）：
`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`OMNIPARSER_URL`、`OMNIPARSER_TIMEOUT`、`USE_REAL_LLM`、`STRICT_FINGERPRINT`、`INTENT_MODEL_PATH`

**B 端独有**（`HAJIMI_UI/.env`）：
`HAJIMI_API_URL`、`HAJIMI_MOCK_ONLY`、`HAJIMI_MOCK_FALLBACK`、`HAJIMI_API_TIMEOUT`、`HAJIMI_INSPECT_TIMEOUT`、`HAJIMI_PROCESS_TIMEOUT`、`HAJIMI_STOP_SERVICES_ON_EXIT`

### 6.10 错误码处理

B 端 `api_client.py` 对各类错误的处理策略：

| 错误类型 | B 端处理 |
|---------|---------|
| HTTP 401 | 抛出 `ApiError("X-Demo-Key 不匹配")` → UI 显示红色系统消息 |
| HTTP 404 | 解析 JSON body 中的 `error.message` → UI 显示 |
| TimeoutError | 对 inspect 特殊格式化（"预计 2-4 分钟 CPU…"）；对 process 显示超时秒数 |
| ConnectionError | 提示运行 `scripts/start_server.bat` 或 `start_all.bat` |
| OmniParser 502 | 提示"OmniParser 未启动，运行 start_omniparser.bat" |
| success=false | `process()` 抛出 `ApiError("A 端处理失败：success=false")` |

### 6.11 无重试/无速率限制

- A 端：LLM 调用、OmniParser 调用、数据库操作均**无重试逻辑**，失败即返回错误
- B 端：HTTP 调用**无重试逻辑**，失败即抛出 `ApiError`
- B 端仅在**启动健康检查**时有重试（最多 6 次）
- 整个系统**无速率限制**，无请求节流
- **生产环境需增加**：指数退避重试、速率限制、熔断器

### 6.12 OmniParser 依赖

- `/process` 和 `/inspect` 完全依赖 OmniParser（`:9800`）
- A 端在 `/health` 中探测 OmniParser 并返回 `omniparser_ready` 标志
- B 端在 `/process` 和 `/inspect` 前执行 **preflight 检查**：
  - `omniparser_ready == false` → 阻止并提示启动 OmniParser
  - `omniparser_ready == null` → 阻止并提示可能是旧版 A
- OmniParser 启动需 1–2 分钟（加载模型到 GPU），此期间 `omniparser_ready` 为 false
- CPU 模式每次解析需 2–4 分钟，GPU 模式约 3–10 秒

### 6.13 指纹校验宽松模式

- 当前 `STRICT_FINGERPRINT=false`（默认）
- 宽松模式：指纹不匹配仅记录日志，不挂起蓝图
- 如果改为 `true`：指纹不匹配时 blueprint 进入 `suspended` 状态，用户需手动选择 skip/rollback/abort
- 指纹算法：B 端 `core/screen_utils.py:compute_fingerprint()` → SHA256

### 6.14 B-C 优雅降级

- B 端**完全不需要 C 即可正常工作**
- 所有语音功能（麦克风按钮、喇叭图标、语音设置）在 C 未接入时：
  - 麦克风按钮：已创建但 `setEnabled(False)`，tooltip "语音（即将推出）"
  - 喇叭图标：未创建
  - 语音设置面板：未创建
- B 端启动时健康检查不检查 C
- C 接入后：B 调用 `c_health_check()` 探测 C 子模块，按 `overall` 值决定降级策略

### 6.15 Windows 特定性

- **B 端**：Windows 专属（`mss` 截图库、`PyQt5` 覆盖层、`Win32 API` 窗口标题获取）
- **B 端不支持 Linux/macOS**：`mss` 可跨平台但覆盖层坐标映射和窗口管理依赖 Windows 行为
- **A 端**：跨平台（FastAPI + Python），但 OmniParser 需 GPU（推荐 NVIDIA，A 端在 GPU 服务器上运行）
- **C 端（计划）**：语音引擎方面，Vosk 跨平台，pyttsx3 在 Windows 上使用 SAPI5

---

## VII. 附录

### A. 环境变量速查表

#### A 端（`server/.env`）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HAJIMI_HOST` | `0.0.0.0` | 服务监听地址 |
| `HAJIMI_PORT` | `8000` | 服务监听端口 |
| `HAJIMI_DEBUG` | `true` | 调试模式 |
| `HAJIMI_DEMO_KEY` | `hajimi-demo-2026` | **认证密钥（必须与 B 端一致）** |
| `DEEPSEEK_API_KEY` | (空) | **LLM 功能必需** |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API 地址 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名称 |
| `DEEPSEEK_TIMEOUT` | `30` | LLM 调用超时（秒） |
| `OMNIPARSER_URL` | `http://127.0.0.1:9800` | OmniParser 服务地址 |
| `OMNIPARSER_TIMEOUT` | `30` | OmniParser 调用超时（秒） |
| `USE_REAL_LLM` | `true` | `false` → 使用 Mock 步骤，不调 LLM |
| `STRICT_FINGERPRINT` | `false` | `true` → 指纹不匹配时挂起蓝图 |
| `INTENT_MODEL_PATH` | `server/services/intent/model` | SetFit 模型路径 |

#### B 端（`HAJIMI_UI/` 环境变量）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HAJIMI_API_URL` | `http://127.0.0.1:8010` | **A 端地址** |
| `HAJIMI_DEMO_KEY` | `hajimi-demo-2026` | **认证密钥（必须与 A 端一致）** |
| `HAJIMI_MOCK_ONLY` | (空) | `1` → 纯 Mock，不连 A |
| `HAJIMI_MOCK_FALLBACK` | (空) | `1` → A 不可达时降级 Mock |
| `HAJIMI_API_TIMEOUT` | `30` | `/step` 超时（秒） |
| `HAJIMI_INSPECT_TIMEOUT` | `360` | `/inspect` 超时（秒） |
| `HAJIMI_PROCESS_TIMEOUT` | `360` | `/process` 超时（秒） |
| `HAJIMI_HEALTH_TIMEOUT` | `2` | `/health` 超时（秒） |
| `HAJIMI_STOP_SERVICES_ON_EXIT` | `1` | 退出时停止 A+OmniParser |
| `HAJIMI_STARTUP_HEALTH_DELAY_MS` | `12000` | 启动后延迟健康探测 |
| `HAJIMI_STARTUP_HEALTH_RETRY_MS` | `4000` | 健康探测重试间隔 |
| `HAJIMI_STARTUP_HEALTH_MAX_RETRIES` | `6` | 健康探测最大重试次数 |
| `HAJIMI_FRAMED` | (空) | `1` → 带边框窗口模式 |
| `HAJIMI_NATIVE_UI` | `1` | `0` → 回退 WebEngine UI |

### B. 端口分配总表

| 端口 | 服务 | 启动者 | 协议 |
|------|------|--------|------|
| `9800` | OmniParser V2 | `start_omniparser.bat` | HTTP |
| `8000` | A 端（独立） | `python server/main.py` | HTTP |
| `8010` | A 端（嵌入 B） | `start_all.bat` / B 端自动 | HTTP |
| `8090` | C 管理面板（计划） | 未实现 | HTTP |

### C. 文档交叉引用

| 文档 | 路径 | 内容 |
|------|------|------|
| 项目指南 | `CLAUDE.md`（根目录） | 架构、命令、gotchas |
| B-C 详细契约 | `项目文档/b-c-api-contract.md` | 9 信号完整定义、联调检查清单 |
| A-C 详细契约 | `项目文档/a-c-api-contract.md` | 18 端点完整定义、数据模型 |
| 总体设计 | `设计文档V2.md` | 四层架构、技术选型、分工 |
| 需求分类 | `用户需求分类.md` | 9 意图域 × 5 指代 × 6 交互模式 |
| A 端 CHANGELOG | `项目文档/CHANGELOG-A端.md` | A 端行为变更历史 |
| B 端 CHANGELOG | `项目文档/CHANGELOG-B端.md` | B 端行为变更历史 |
| 六天冲刺计划 | `项目文档/HAJIMI-六天冲刺计划.md` | 开发排期 |
| 管理控制台设计 | `项目文档/HAJIMI — 管理控制台设计文档 V2.1.md` | Web 面板 UI 设计 |
| UML 图表 | `项目文档/UML_diagrams.md` | 20 个 Mermaid 图 |
| 算法说明 | `项目文档/算法与项目流程说明文档.md` | 核心算法详解 |
| 环境配置问题 | `项目文档/环境配置问题记录.md` | 故障排除记录 |
| OmniParser GPU | `项目文档/OmniParser GPU 环境交接文档.md` | GPU 部署指南 |

### D. 变更历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-07-02 | 1.0.0 | 初始版本：合并 A-B、B-C、A-C 三个接口层；基于代码实际行为编写；新增 15 条注意事项；取代 `api-contract-demo.md` 和 `B端接口总结-对A与对C.md` |
