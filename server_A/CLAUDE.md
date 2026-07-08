# HAJIMI — AI 驱动的桌面自动化助手

## 一句话概述
用户用自然语言描述任务，HAJIMI 截屏 → 用多模态 LLM 理解屏幕 → 生成操作计划 → 自动执行点击/输入/按键等操作。

## 架构：A/B 双端分离

```
用户输入 → B端(PyQt5) 截图(mss) → A端(FastAPI) LLM推理/计划 → B端覆盖层渲染 → SSE推送执行
```

- **A 端** (`server/`)：FastAPI 后端，运行在 `127.0.0.1:8010`
- **B 端** (根目录)：PyQt5 桌面应用，负责截屏、覆盖层渲染、用户交互

## 目录结构要点

| 路径 | 用途 |
|------|------|
| `main.py` | B 端入口 (PyQt5 UI) |
| `config.py` | B 端全局配置 |
| `core/` | B 端核心：截屏、API通信、用户设置、服务管理 |
| `ui/` | B 端 UI：主界面、聊天气泡、覆盖层、Web 桥接 |
| `server/main.py` | A 端入口 (FastAPI) |
| `server/config.py` | A 端配置 (.env) |
| `server/database/` | SQLAlchemy ORM (SQLite `data/hajimi.db`) |
| `server/models/schemas.py` | Pydantic 请求/响应模型 |
| `server/routes/demo.py` | 核心 API (`/api/demo/*`) |
| `server/routes/admin.py` | 管理 API (`/api/admin/*`) |
| `server/services/` | 所有核心业务逻辑（见下文） |
| `server/storage/memory.py` | 运行时内存任务存储 |
| `docs/` | 设计文档和 spec |

## 核心处理管线

```
用户查询
  → 红线检测 (redline_service.py) — 拒绝危险操作
  → 意图分类 (setfit_classifier.py) — 9 类别
  → 复杂度路由 (complexity_router.py) — L2 模板 vs L3 LLM
  → [并行] Planning Agent + OmniParser 检测
  → 步骤↔元素绑定 → ProcessResponse
  → [可选] 执行引擎 (executor/engine.py → agent.py)
  → 反馈收集 (t_feedback / t_failures)
```

同时存在一个更新的 Agent 管线 (`agent/orchestrator.py`)：
```
用户查询 → plan_and_locate() [单次LLM调用] → 用户操作 → evaluate_step() → advance/replan
```

## 关键服务模块

### Agent 编排 (`services/agent/`)
- **orchestrator.py** — TaskOrchestrator 状态机：process_query → plan+locate → evaluate → advance/replan。单例。
- **chains.py** — 6 个 LLM 链：plan_and_locate, plan_goal, locate_step_target, evaluate_step, replan_goal, fast_mode_chat
- **prompts.py** — Planner/Locator/Evaluator/Replanner 的 System+User prompt 模板

### LLM 客户端 (`services/llm/`)
- **providers.py** — 统一多供应商客户端，支持 openai/claude/gemini/groq/openrouter/ollama/qwen/glm/deepseek。包含 `[POINT:x,y:label]` 标签解析器、JSON 修复、自适应 token 重试。
- **client.py** — 旧版 `call_deepseek()` 兼容层

### 执行引擎 (`services/executor/`)
- **engine.py** — `run_plan_agent_loop()` 主循环，SSE 事件队列推送到前端
- **agent.py** — LLM 驱动的工具调用循环，17 个工具：launch_app/get_screen_info/click/type_text/scroll/browser_* 等。每步最多 15 轮。
- **safety.py** — 三层安全分类（绿/黄/红），23 条红线 + 12 条黄线

### 规划 (`services/planning/`)
- **router.py** — 旧版管线主入口：红线→意图→并行(Planning+OmniParser)
- **blueprint_engine.py** — 蓝图状态机：advance/rollback/skip/terminate
- **complexity_router.py** — L2/L3 复杂度分级

### 意图 (`services/intent/`)
- **setfit_classifier.py** — SetFit + 关键词回退，9 类别中文意图分类
- **train_intent.py** — 手动训练脚本（非运行时）

### 其他
- **session/manager.py** — SessionManager 单例：消息历史(80条)、计划状态、评估历史(40条)
- **context/distiller.py** — 快速纯文本 LLM 预调用，减少主调用 token
- **context/embedding_matcher.py** — all-MiniLM-L6-v2 语义匹配 (384维余弦相似度)
- **omniparser_client.py** — 远程 GPU OmniParser HTTP 客户端
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

- A 端 `.env` 配置：`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `OMNIPARSER_URL`, `INTENT_MODEL_PATH`
- B 端用户设置：`%LOCALAPPDATA%/HAJIMI/user_settings.json`（部署模式、主题、字体、透明度）
- `DISTILLATION_ENABLED` 控制语境蒸馏开关
- `EVALUATOR_ENABLED` 控制步骤评估开关

## 关键约定

- 坐标系统：归一化 0-1000 比例，通过 `validation/coords.py` 转为绝对像素
- 指针格式：`[POINT:x,y:label]` 标签
- 安全：输入查询通过 `redline_service.py`，执行步骤通过 `executor/safety.py`
- 单例模式：TaskOrchestrator、SessionManager、SetFitIntentClassifier
- 意图类别：operation_guide, element_cognition, error_diagnosis, ui_navigation, content_cognition, file_management, proactive_alert, tutorial_generation, emotion_comfort

## 当前局限性

- `User.preferences` 字段已定义但未使用
- 反馈已收集但未形成闭环（无自动微调/个性化）
- 无用户行为学习系统
- 运行时状态仅内存存储，重启丢失
- 中英文混合场景较多（应用名映射、提示词等）
