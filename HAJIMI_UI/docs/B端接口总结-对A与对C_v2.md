# B 端接口总结（对 A / 对 C）（v2）

> **维护人**：B 端（前端 / 桌面应用）  
> **版本**：1.1.0  
> **依据**：[`设计文档V2.md`](../设计文档V2.md) 第九章分工、[`b-c-api-contract.md`](../b-c-api-contract.md)、[`api-contract-demo_v2.yaml`](../api-contract-demo_v2.yaml)、[`CHANGELOG-B端_v2.md`](CHANGELOG-B端_v2.md)、[`server/docs/CHANGELOG-A端_v2.md`](../server/docs/CHANGELOG-A端_v2.md)  
> **最后更新**：2026-07-01 · **文档版本**：v2

---

## 一、架构与职责边界

| 成员 | 定位 | 与 B 的关系 |
|------|------|-------------|
| **A** | 后端 / AI 核心 | B 作为 **HTTP 客户端** 调用 A 的 REST API；B **不向 A 暴露** 服务端接口 |
| **B** | 前端 / 桌面应用 | 负责截图、UI 渲染、覆盖层标注；向 C **暴露 Qt 信号/共享状态** |
| **C** | 集成 / 语音 / 管理端 | 与 B **同进程**，绑定 B 的信号；代 B 向 A 发审计/配置类 HTTP |

```
                    HTTP (B 调用 A)
  ┌─────────┐  ──────────────────────►  ┌─────────┐
  │ B 桌面端 │                           │ A 后端  │
  │ PyQt5   │  ◄──────────────────────  │ FastAPI │
  └────┬────┘      JSON + Base64 截图    └─────────┘
       │
       │ Qt 信号 / 共享状态（同进程）
       ▼
  ┌─────────┐
  │ C 集成  │ ──HTTP──► A（审计 / 配置，Demo 后启用）
  └─────────┘
```

---

## 二、B 对 C 暴露的接口（进程内）

> 详细定义见 [`b-c-api-contract.md`](../b-c-api-contract.md)。B 与 C 约定 **9 个交互点**，耦合极低，可独立 Mock。

### 2.1 总览

| # | 接口名 | 方向 | 通信方式 | B 侧职责 |
|---|--------|------|----------|----------|
| 1 | ASR 录音控制 | B → C | 信号 `asr_start` / `asr_stop` | 控制栏麦克风按钮 pressed/released |
| 2 | ASR 转写结果 | C → B | 信号 `asr_result` | 填入输入框并触发提交 |
| 3 | TTS 播报触发 | B → C | 信号 `tts_enqueue` | 步骤切换时 emit 步骤描述文本 |
| 4 | TTS 状态回传 | C → B | 信号 `tts_status` | 更新喇叭图标动画 |
| 5 | 语音设置同步 | B → C | 共享状态 `voice_settings` | 设置面板 Toggle/Slider/下拉 |
| 6 | 审计数据提交 | B → C | 信号 `audit_submit` | 任务结束 emit `AuditRecord` |
| 7 | 审计上报状态 | C → B | 信号 `audit_status` | 状态栏显示队列积压 |
| 8 | 配置拉取通知 | C → B | 信号 `config_updated` | 热加载路由规则等 |
| 9 | 心跳/健康检测 | B → C | 方法 `c_health_check()` | 启动时探测 C 子模块 |

### 2.2 B 需预留的 UI 挂载点（给 C 联调）

| 挂载点 | 位置 | 说明 |
|--------|------|------|
| 麦克风按钮 | 控制栏 | `pressed` → `asr_start`，`released` → `asr_stop` |
| 喇叭图标 | 控制栏 | 随 `tts_status.playing` 显示声波动画 |
| 语音开关 / 语速 | 设置面板 | 绑定 `voice_settings.tts_enabled`、`tts_speed` 等 |
| 任务结束钩子 | `app_controller` | 构造并 emit `audit_submit` |
| 步骤切换钩子 | 步骤推进逻辑 | emit `tts_enqueue(text, priority)` |

### 2.3 设计文档中的最小约定（语音模块）

[`设计文档V2.md`](../设计文档V2.md) 原约定：**2 个信号 + 2 个状态变量** 即可启动 C 端独立开发：

| 接口点 | B 提供 | C 调用 |
|--------|--------|--------|
| 麦克风按钮 | PyQt5 按钮 + 点击信号 | 绑定 → 启动 ASR |
| TTS 播报 | 文字指引完成后 emit（含文本） | 入队 TTS |
| 语音开关/语速 | Toggle/Slider + 状态变量 | 读取后控制行为 |

> **当前实现状态**：契约已文档化（`b-c-api-contract.md`），代码中 C 模块尚未接入，B 端 UI 预留位待 C 联调（Day 10–11 里程碑）。

---

## 三、B 对 A 的接口（HTTP 客户端契约）

B 不对外提供 HTTP 服务；本节描述 **B 如何调用 A**，以及 **B 向 A 提交的数据格式与预检逻辑**，供 A 联调与验收。

### 3.1 连接与认证

| 配置项 | 环境变量 / 持久化 | 默认值 | 说明 |
|--------|-------------------|--------|------|
| A 端地址 | `HAJIMI_API_URL` / 设置页 | `http://127.0.0.1:8010` | 与 A 端 uvicorn 端口一致 |
| Demo Key | `HAJIMI_DEMO_KEY` / 设置页 | `hajimi-demo-2026` | 请求头 `X-Demo-Key` |
| 部署模式 | `HAJIMI_DEPLOYMENT_MODE` / 设置页 | `local` | `local` 本机启服务；`intranet` 仅连远程 A |
| 用户设置文件 | `%LOCALAPPDATA%/HAJIMI/user_settings.json` | — | 启动时加载；保存并应用写入 |
| 纯 Mock | `HAJIMI_MOCK_ONLY=1` | 关 | 不走 A，检验模式不可用 |
| Mock 降级 | `HAJIMI_MOCK_FALLBACK=1` | 关 | A 不可达时 process 回退本地 Mock |

**系统设置页**（Native → 系统设置）：部署模式、A 端地址、Demo Key、DeepSeek LLM、OmniParser URL/GPU URL；**保存并应用**或表单内 **Enter** 提交。本地模式会将 LLM/OmniParser 合并写入 `server/.env`（`core/env_sync.py`）。

**B 端实现入口**：`core/api_client.py`、`core/user_settings.py`

### 3.2 A 端 API 总览（含 A 成员改动汇总）

| 端点 | 方法 | 认证 | B 端调用函数 | 说明 |
|------|------|------|--------------|------|
| `/api/demo/health` | GET | 无 | `check_health()` / `fetch_health()` | 启动探测 + 预检 |
| `/api/demo/process` | POST | `X-Demo-Key` | `process()` | **必填 image**；识图 + 步骤 + 标注 |
| `/api/demo/inspect` | POST | `X-Demo-Key` | `inspect()` | 检验模式；全量 `ui_elements` + SoM 图 |
| `/api/demo/relocate` | POST | `X-Demo-Key` | `relocate_step()` | **A 新增**；手动完成一步后重新定位 |
| `/api/demo/step` | POST | `X-Demo-Key` | `advance_step()` | 推进 / 回退 / 跳过 / 终止 |
| `/api/demo/clarify` | POST | `X-Demo-Key` | （待接 UI） | 澄清应答 |
| `/api/demo/report` | POST | `X-Demo-Key` | （Demo 由 C 代报） | 审计上报 |

> **契约文件**：[`api-contract-demo_v2.yaml`](../api-contract-demo_v2.yaml)（含 `/inspect`、`/relocate` 与扩展 health 字段；v1 见 `api-contract-demo.yaml`）。

### 3.3 A 端改动汇入（B 联调必读）

以下汇总自 [`server/docs/CHANGELOG-A端_v2.md`](../server/docs/CHANGELOG-A端_v2.md)，是 B 端对接 A 时必须知晓的**行为变更**。

#### 3.3.1 `/process` 行为变更

| 项目 | 改前（Demo 初版） | 改后（当前） |
|------|-------------------|--------------|
| `image` 字段 | 可选，实际被忽略 | **必填**（`REQUIRE_IMAGE=true`） |
| UI 元素来源 | 写死 `SCENARIO_ELEMENTS`（1920×1080 模板） | OmniParser 真实检测 |
| 步骤-元素绑定 | `elements[i % N]` 轮询 | DeepSeek 选 `target_element_id` + fallback |
| `annotated_image` | 恒 `None` | SoM Base64 |
| 坐标系 | 隐含 1920×1080 | **截图物理像素** + `reference_resolution` |

**B 端请求体**（`process()`）：

```json
{
  "query": "怎么安装微信？",
  "image": "data:image/png;base64,...",
  "window_title": "桌面",
  "context": []
}
```

**B 端依赖的响应扩展字段**：

```json
{
  "reference_resolution": [2560, 1600],
  "detection_meta": {
    "latency_ms": 4200,
    "element_count": 47,
    "backend": "local_omniparser"
  }
}
```

#### 3.3.2 新增 `POST /api/demo/inspect`

- **用途**：Settings「立即检测当前屏幕」；仅检测，不生成 task/steps
- **B 请求**：`{ "image", "screen_width", "screen_height" }`
- **B 响应使用**：`ui_elements` → 青色全量框；`reference_resolution` → 坐标映射
- **超时**：B 端 `HAJIMI_INSPECT_TIMEOUT` 默认 **360s**（CPU OmniParser 约 2–4 分钟）

#### 3.3.3 新增 `POST /api/demo/relocate`

- **用途**：当前画面找不到目标元素时，用户手动完成操作后重新截图定位
- **B 请求**：

```json
{
  "task_id": "550e8400-...",
  "step_index": 2,
  "image": "data:image/png;base64,..."
}
```

- **B 响应使用**：更新当前步 `annotation`、`target_element_id`、`ui_elements`
- **B 实现**：`core/relocate_worker.py` + `ui/main_widget.py` PrepareStep banner

#### 3.3.4 `/health` 扩展字段

A 端在 Demo 契约基础上新增（B 预检依赖）：

```json
{
  "status": "ok",
  "version": "1.0.0",
  "detector_backend": "auto",
  "detector_active": "local_omniparser",
  "detector_device": "cuda",
  "omniparser_url": "http://127.0.0.1:8002",
  "omniparser_ready": true
}
```

| 字段 | B 端用途 |
|------|----------|
| `detector_backend` | 配置值；缺失 → 判定旧版/多开 A 端 |
| `detector_active` | 实际使用的后端（auto 模式下解析结果） |
| `detector_device` | `cuda` / `cpu` / `cloud`；状态栏文案「GPU/cuda」「CPU/cpu」 |
| `omniparser_url` | 当前探测到的 OmniParser 基址 |
| `omniparser_ready` | `false` → 本地模式阻止 inspect/process；内网模式仅告警 |

**部署模式与预检**：

| `deployment_mode` | 预检行为 |
|-------------------|----------|
| `local` | A health + `omniparser_ready`（backend 为 `local_omniparser` 或 `auto`） |
| `intranet` | 仅 `/health` 可达；不要求本机 OmniParser |

**B 预检函数**：`check_inspect_preflight()`、`check_process_preflight()`

#### 3.3.5 坐标系约定（2026-06-29 起）

- `bbox`、`annotation.highlight_bbox`：截图**左上角**原点，**物理像素**
- B 端 `core/overlay_coords.py`：物理像素 → Qt 逻辑坐标（HiDPI）
- 当 `reference_resolution == screen_size` 时，**不再**做 1920×1080 缩放

#### 3.3.6 错误码（A 返回，B 需识别）

| HTTP | code | B 端处理 |
|------|------|----------|
| 400 | `MISSING_IMAGE` | 提示用户截图失败 |
| 400 | `INVALID_IMAGE` | Base64 解码失败 |
| 401 | `AUTH_FAILED` | 检查 `HAJIMI_DEMO_KEY` |
| 404 | `NOT_FOUND` | task_id 不存在 |
| 422 | `NO_ELEMENTS_DETECTED` | 换含可见控件的截图 |
| 502 | `DETECTOR_FAILED` | OmniParser 不可用/内部错误；B 显示中文友好提示 |

#### 3.3.7 A 端检测后端（B 无代码改动即可切换）

| 后端 | 配置 | B 端影响 |
|------|------|----------|
| Replicate OmniParser V2 | `DETECTOR_BACKEND=replicate_omniparser` | 需 `REPLICATE_API_TOKEN` |
| 本地 OmniParser | `DETECTOR_BACKEND=local_omniparser` | 需先 `start_omniparser.bat`；health 看 `omniparser_ready` |
| **auto（推荐）** | `DETECTOR_BACKEND=auto` | 优先 GPU URL → 本地 URL → Replicate；health 含 `detector_device` |
| **学校 A800 GPU 容器** | A 端容器内 `auto` + B 端「内网 API」 | 见 [`A端-学校GPU部署与联调指南_v2.md`](../server/docs/A端-学校GPU部署与联调指南_v2.md) |

**启动顺序（B 文档约定）**：① OmniParser → ② A 端 → ③ `python main.py`

### 3.4 B 向 A 提交的数据格式

| 字段 | 来源 | 格式要求 |
|------|------|----------|
| `image` | `mss` 全屏截图 | PNG/JPEG Base64 或 `data:image/png;base64,...` |
| `window_title` | Win32 活动窗口 | 字符串，供意图上下文 |
| `screen_width/height` | 截图尺寸 | inspect 请求附带，与物理像素一致 |
| `fingerprint` | B 端屏幕指纹 | SHA256，step 推进时携带 |
| `task_id` | process 响应 | UUID，后续 step/clarify/relocate/report 必带 |

### 3.5 B 端 Mock / 降级策略

| 模式 | 环境变量 | process | inspect | step |
|------|----------|---------|---------|------|
| 纯 Mock | `HAJIMI_MOCK_ONLY=1` | 本地 Mock | **不可用** | 本地 Mock |
| 降级 Mock | `HAJIMI_MOCK_FALLBACK=1` | A 失败时回退 | 仍须 A | step 失败时回退 |

---

## 四、B 端已实现模块与接口映射

| B 模块 | 文件 | 对接接口 |
|--------|------|----------|
| API 客户端 | `core/api_client.py` | A：health/process/inspect/relocate/step |
| 检验 Worker | `core/inspect_worker.py` | A：`/inspect` |
| 重定位 Worker | `core/relocate_worker.py` | A：`/relocate` |
| 任务 Worker | `core/task_worker.py` | A：`/process` |
| 坐标映射 | `core/overlay_coords.py` | A：`reference_resolution` + bbox |
| 标注映射 | `core/annotation_mapper.py` | A：`ui_elements` lookup |
| 覆盖层 | `ui/overlay_anno.py` | 红框指引 + 青色检验框 |
| 主控 | `ui/app_controller.py` | 步骤状态机 + relocate 回调 |
| 设置/服务 | `ui/main_widget.py`, `ui/native/medium_panel.py`, `core/user_settings.py`, `core/env_sync.py`, `core/service_manager.py` | 系统设置、health 预检、启停 A/OmniParser |

---

## 五、联调检查清单

### B ↔ A

- [ ] `curl {API_BASE_URL}/api/demo/health` 含 `detector_backend` 与 `omniparser_ready=true`
- [ ] 输入任务 → 红框坐标与桌面元素对齐（HiDPI 下）
- [ ] Settings「立即检测当前屏幕」→ 青色 `~N` 全量框
- [ ] PrepareStep →「我已完成，重新定位」→ `/relocate` 更新红框
- [ ] `python scripts/verify_integration.py` 通过

### B ↔ C（待 C 接入）

- [ ] 麦克风按下/松开 → ASR 文字填入输入框
- [ ] 步骤切换 → TTS 播报 → 喇叭动画
- [ ] 任务结束 → `audit_submit` → C SQLite 队列
- [ ] 断网 → 审计队列积压提示

---

## 六、相关文档索引

| 文档 | 路径 |
|------|------|
| 团队分工 | [`设计文档V2.md`](../设计文档V2.md) §九 |
| Demo API 契约（YAML v2） | [`api-contract-demo_v2.yaml`](../api-contract-demo_v2.yaml) |
| Demo API 契约（YAML v1） | [`api-contract-demo.yaml`](../api-contract-demo.yaml) |
| B–C 详细契约 | [`b-c-api-contract.md`](../b-c-api-contract.md) |
| A 端改动全记录 | [`server/docs/CHANGELOG-A端_v2.md`](../server/docs/CHANGELOG-A端_v2.md) |
| B 端改动全记录 | [`CHANGELOG-B端_v2.md`](CHANGELOG-B端_v2.md) |
| DAY2 工作计划 | [`DAY2-工作内容.md`](DAY2-工作内容.md) |
| DAY3 工作总结 | [`DAY3-工作内容_v2.md`](DAY3-工作内容_v2.md) |
| 校园 GPU / OmniParser 速查 | [`校园GPU与OmniParser环境速查_v2.md`](校园GPU与OmniParser环境速查_v2.md) |
| A 端 GPU 部署 runbook | [`server/docs/A端-学校GPU部署与联调指南_v2.md`](../server/docs/A端-学校GPU部署与联调指南_v2.md) |
| OmniParser GPU 交接（完整版） | [`OmniParser GPU 环境交接文档.md`](../OmniParser%20GPU%20环境交接文档.md) |
