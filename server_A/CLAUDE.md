# server_A — L5 Sidecar 上下文速览

> **唯一权威开发指南 = 仓库根 [`AGENTS.md`](../AGENTS.md)**；本文件只补 server_A 内部事实。**与代码冲突时，以代码为准。**
> 动执行链（`server/services/executor/`）前必读：根目录《调研报告_L5-Agent架构对标开源.md》§四（含 P0 实施状态列）与《审查台账_L5执行链全流程质疑与决策.md》（当前问题队列与 P0.5 批次）。
>
> ⚠️ 本文件在 2026-09-03 前是 L4 时代旧稿（描述 :8010 A 端 / OmniParser / 截图多模态管线——均已删除），因会被工具自动注入为 agent 指令、构成误导源，已按实况重写。

## 现状

- FastAPI 后端，**唯一端口 :8011**：`python3 -m uvicorn server.main:app --port 8011`（工作目录 = `server_A/`）。
- **:8010 旧 A 端 / OmniParser / GPU 隧道 / 内网联调 / Mock 已整体删除，禁止复活。** L4 史料归档于 `server/docs/archive/legacy-L4/`，只可查阅、禁止照做。
- 模型 key 唯一存放 `server/.env`（安装脚本创建；B 端设置页经 env_sync 同步写入），不入 git。
- 分支口径：`master` = PyQt B 端（`HAJIMI_UI/`）；`front` = 并行的 Electron B 端（`desktop/`，验收后切换）——**master 上不存在 desktop/ 目录与红线只读评估端点（`/api/demo/redline/evaluate`，front 独有）**，跨端契约变更需两分支同步。
- `server_A` 顶层的 `core/`、`ui/`、`main.py` 是 L4 死 fork（台账 R5 待清理），勿新增引用、勿当作运行时代码阅读。

## 路由（server/routes/）

| 文件 | 内容 |
|---|---|
| `demo.py` | L5 核心：`POST /api/demo/execute`、`GET /api/demo/stream/{task_id}`(SSE)、`/cancel`、`/health*`、`/debug/click` |
| `admin.py` | 管理统计 + `/users/*`（web-admin 后端） |
| `audit.py` `auth.py` `flow.py` `monitor.py` `config_client.py` | 审计 / 鉴权 / 流程 / 监控 / C 端配置拉取 |

除 health 外 `/api/demo/*` 需头 `X-Demo-Key`（默认 `hajimi-demo-2026`）。

## 执行链（server/services/executor/）— P0/P0.5 改造落点

- `engine.py` — `run_plan_agent_loop`：步骤循环 + SSE 事件队列 + 崩溃保护壳（异常统一转 task_failed 事件并落遥测）+ Transaction 统计回写。
- `agent.py` — `ExecutionAgent`，每步 ≤50 轮 LLM 工具循环（deepseek-chat，纯文本 function-calling）：
  - 统一错误契约 `{ok, error_code, message, hint}`（`dispatch_tool` 包装，工具异常不再掀翻整步）；
  - 证据账本 + `mark_step_done` gate（无独立证据拒收一次）+ `report_infeasible` / `ask_user` 终止动作（engine 跳过盲重试，ask_user→`step_blocked` 事件）；
  - `_LoopDetector` 卡死检测（动作哈希滑窗 5/8/12 三级 + 观测内容指纹停滞 + 连续失败 REPLAN 提示）；
  - `_strip_for_llm`：截图 base64 只走 SSE 给 B 端渲染，进 LLM messages 前剥离。
- `uia_bridge.py` — UIA 四件套：投影快照（10 类 ControlType 白名单，`_last_projection` + `_last_meta` 缓存 patterns）→ `_check_actionable` 前置谓词（可见/启用/稳定/可点；等待条件不等待时间）→ `_CLICK_PATTERN_TABLE` 决策表选模式 + **fail-closed 执行**（无自动坐标回退；`via="coordinate"` 显式声明是唯一坐标通道）→ 动作后 `verify` + 属性 diff + `wait_for_text`(expect 后置断言)。
- `safety.py` — 执行层红线（绿/黄/红，`check_query/check_step`）；`clicker.py` — 键鼠封装。
- 记忆 `services/memory/`（成功/失败轨迹抽取→检索注入 system prompt）；浏览器 `services/browser/`（Playwright DOM，`browser_*` 工具）。
- 评测：`server/services/eval_telemetry.py`（步/任务遥测→`server_A/data/eval/runs.jsonl`）+ `server_A/eval/`（回归任务集/oracle 判分/runner/report；**未校准任务不计 KPI**，Windows 跑分手册 `server_A/eval/HOWTO_WINDOWS.md`）。

**契约纪律**：工具参数、错误码、SSE 事件字段（`evidence`/`error_code`/`step_blocked.question`…）任何改动必须同步两个 B 端（`HAJIMI_UI`，及 front 上的 `desktop/`）。

## 测试

- `server/tests/`（pytest，标记配置在 `server_A/pyproject.toml`）。executor 回归 = `test_executor_p0.py` + `test_uia_bridge.py`（Linux 可全跑：文件头「缺啥补啥」注入 pyautogui/uiautomation 桩，勿改成依赖真件）。
- 部分模块在 Linux 收集失败属预存环境问题（缺 pytest_asyncio/playwright）——基线口径 = 全量 failed/error 集合「零新增」。
- B 端门：`cd ../HAJIMI_UI && QT_QPA_PLATFORM=offscreen python3 -m pytest tests -q`（基线 35 passed / 6 个环境预存失败）。
- 端到端冒烟（Linux 只能验到路由/SSE/规划层）：起 uvicorn :8011 → `python3 HAJIMI_UI/scripts/verify_l5.py --require-l5`。真实 UIA 执行仅 Windows 有效。

## 数据

- SQLAlchemy ORM：`server/database/`，SQLite 默认 `server_A/data/hajimi.db`（环境变量 `HAJIMI_DATABASE_URL` 可覆盖）。
- 任务/步骤运行态：`server/storage/memory.py` 内存存储，重启丢失（演示期设计）。
- 审计队列等运行产物落 `server_A/data/`（gitignore）。
