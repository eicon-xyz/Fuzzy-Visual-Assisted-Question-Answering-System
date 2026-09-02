# HAJIMI — AI 驱动的桌面自动化助手

## 一句话概述
用户用自然语言描述任务，HAJIMI 的 L5 Sidecar 用 LLM 理解意图并生成操作计划，随后通过 UIA 控件绑定 / Playwright DOM 自动执行点击、输入、按键等操作，SSE 实时回传进度。

## 架构：B 端 + L5 Sidecar（L5 自动执行，唯一模式）

```
用户输入指令 → B端(PyQt5) 红线归一化 → L5 Sidecar(FastAPI :8011) LLM规划 + UIA/Playwright执行 → SSE推送进度 → B端步骤时间线
```

- **B 端** (本目录)：PyQt5 桌面应用，负责指令输入、知情确认、进度展示、设置管理，并拉起/守护 Sidecar
- **L5 Sidecar** (`../server_A/server/`)：FastAPI 后端，运行在 `127.0.0.1:8011`，UIA 绑定执行 + Playwright DOM
- L4 指引模式（截屏 OmniParser + 红框覆盖层）、旧 A 端 (:8010)、Mock 演示后端已整体移除

## 目录结构要点

| 路径 | 用途 |
|------|------|
| `main.py` | B 端入口 (PyQt5 UI)，启动时自动拉起/复用 L5 Sidecar |
| `config.py` | B 端全局配置（L5 后端 URL/端口/超时等，env → 模块属性） |
| `core/` | B 端核心（L5 子集）：`api_client`(execute_task/cancel_task/check_l5_health/get_api_status_message)、`execute_worker`(提交+SSE)、`l5_sidecar_launcher`、`l5_query_normalize`(红线归一化)、`sidecar_modules`(从 server_A 动态加载红线规则)、`env_sync`(仅 `sync_l5_sidecar_env` → server_A/server/.env)、`service_manager`(仅管 :8011)、`user_settings`、`auth_session`、`backend_health_worker`、`bc_signals`、`defaults` |
| `ui/` | B 端 UI：主界面（操作指引聊天 / 步骤列表 L5 时间线 / 提醒通知 / 系统设置）、聊天气泡、登录框、主题 |
| `../server_A/server/main.py` | L5 Sidecar 入口 (FastAPI :8011) |
| `../server_A/server/config.py` | Sidecar 配置（读 `server_A/server/.env`） |
| `../server_A/server/database/` | SQLAlchemy ORM (SQLite `data/hajimi.db`) |
| `../server_A/server/models/schemas.py` | Pydantic 请求/响应模型 |
| `../server_A/server/routes/demo.py` | 核心 API (`/api/demo/*`) |
| `../server_A/server/routes/admin.py` 等 | 管理/审计/鉴权/流程/监控 API (`/api/admin/*`、users 等) |
| `../server_A/server/services/` | 所有核心业务逻辑（见下文） |
| `../server_A/server/storage/memory.py` | 运行时内存任务存储 |
| `scripts/` | L5 启动链：`start_release_fullstack.bat` / `start_local_vision.bat` / `start_l5_sidecar.bat` / `stop_all.bat` / `verify_all.py` / `apply_l5_settings.py` 等 |
| `docs/` | 设计文档和 spec |

## 核心处理管线（L5 自动执行）

```
用户指令（B端操作指引页）
  → L5 知情确认弹窗
  → B端红线归一化 (core/l5_query_normalize，规则经 sidecar_modules 从 server_A 加载)
  → POST /api/demo/execute (:8011, X-Demo-Key)
  → Sidecar 规划 (planning/router.py → LLM) + 红线复检 (redline_service.py / executor/safety.py)
  → 执行引擎 (executor/engine.py → agent.py，UIA 绑定 uia_bridge / Playwright DOM)
  → SSE /api/demo/stream/{task_id}：step_start / step_done / step_blocked / step_failed / task_done
  → B端步骤列表（L5 时间线）实时渲染；快捷键 H 批准 / P 暂停 / J 停止
  → 反馈收集 (t_feedback / t_failures)
```

红线为双层：B 端 `l5_query_normalize` 归一化 + Sidecar `redline_service`/`executor/safety` 服务端复检。

## 关键服务模块（均位于 `../server_A/server/services/`）

### Agent 编排 (`services/agent/`)
- **orchestrator.py** — TaskOrchestrator 状态机：process_query → plan+locate → evaluate → advance/replan。单例。
- **chains.py** — 6 个 LLM 链：plan_and_locate, plan_goal, locate_step_target, evaluate_step, replan_goal, fast_mode_chat
- **prompts.py** — Planner/Locator/Evaluator/Replanner 的 System+User prompt 模板

### LLM 客户端 (`services/llm/`)
- **providers.py** — 统一多供应商客户端，支持 openai/claude/gemini/groq/openrouter/ollama/qwen/glm/deepseek。包含 `[POINT:x,y:label]` 标签解析器、JSON 修复、自适应 token 重试。
- **client.py** — 旧版 `call_deepseek()` 兼容层

### 执行引擎 (`services/executor/`) — L5 核心
- **engine.py** — `run_plan_agent_loop()` 主循环，SSE 事件队列推送到 B 端
- **agent.py** — LLM 驱动的工具调用循环，17 个工具：launch_app/get_screen_info/click/type_text/scroll/browser_* 等。每步最多 15 轮。
- **uia_bridge.py** — UIA 控件绑定定位/点击（L5 主定位方式）
- **safety.py** — 三层安全分类（绿/黄/红），23 条红线 + 12 条黄线

### 规划 (`services/planning/`)
- **router.py** — 管线主入口：红线→意图→L5 UIA 执行路线规划
- **blueprint_engine.py** — 蓝图状态机：advance/rollback/skip/terminate
- **complexity_router.py** — L2/L3 复杂度分级

### 意图 (`services/intent/`)
- **setfit_classifier.py** — SetFit + 关键词回退，9 类别中文意图分类
- **train_intent.py** — 手动训练脚本（非运行时）

### 其他
- **browser/** — Playwright DOM 自动化（网页类任务）
- **session/manager.py** — SessionManager 单例：消息历史(80条)、计划状态、评估历史(40条)
- **context/distiller.py** — 快速纯文本 LLM 预调用，减少主调用 token
- **context/embedding_matcher.py** — all-MiniLM-L6-v2 语义匹配 (384维余弦相似度)
- **fingerprint_service.py** — SHA-256 屏幕指纹 + Jaccard 相似度
- **cache.py** — 截图缓存 (900ms TTL)
- **redline_service.py** — 18 条红线正则规则
- **launcher.py** — Win+搜索应用启动 + 中英文名称映射

## 数据库 (7 张表)

| 表 | 类 | 说明 |
|----|-----|------|
| `t_users` | User | 用户，preferences(JSON, 空壳), role |
| `t_transactions` | Transaction | 任务记录，intent/complexity/result/duration |
| `t_step_logs` | StepLog | 步骤日志，action/status/fingerprint |
| `t_feedback` | Feedback | 反馈 (useful/useless/neutral) |
| `t_failures` | Failure | 失败记录，llm_snapshot |
| `t_system_configs` | SystemConfig | 系统配置 KV |
| `t_redline_logs` | RedlineLog | 红线拦截日志 |

## 配置要点

- 模型 key 唯一存放处：`server_A/server/.env`（`DEEPSEEK_API_KEY` / `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`INTENT_MODEL_PATH`）；`OMNIPARSER_ENABLED=false`、`ROUTING_MODE=l5` 由 `scripts/apply_l5_settings.py` 写入
- B 端设置页保存后：`core/env_sync.sync_l5_sidecar_env()` 同步写入上述 .env 并重启 Sidecar
- B 端用户设置：`%LOCALAPPDATA%/HAJIMI/user_settings.json`（主题、字体、透明度、模型 key；已无 deployment_mode/a_end_url 字段）
- `DISTILLATION_ENABLED` 控制语境蒸馏开关
- `EVALUATOR_ENABLED` 控制步骤评估开关

## 关键约定

- L5 定位方式：UIA 控件树 / Playwright DOM 选择器（不再依赖视觉坐标标注）
- 安全双层：提交前 B 端 `l5_query_normalize` + Sidecar `redline_service.py`，执行步骤再过 `executor/safety.py`
- 单例模式：TaskOrchestrator、SessionManager、SetFitIntentClassifier
- 意图类别：operation_guide, element_cognition, error_diagnosis, ui_navigation, content_cognition, file_management, proactive_alert, tutorial_generation, emotion_comfort
- `.bat` 脚本：GBK 或纯 ASCII + CRLF；禁止在 if/for 括号块内 echo 未转义括号（`scripts/dev/check_bat_parens.py` 可检查）

## 当前局限性

- `User.preferences` 字段已定义但未使用
- 反馈已收集但未形成闭环（无自动微调/个性化）
- 无用户行为学习系统
- 运行时状态仅内存存储，重启丢失
- 中英文混合场景较多（应用名映射、提示词等）
