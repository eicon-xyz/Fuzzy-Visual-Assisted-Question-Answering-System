# HAJIMI 第一天工作进度 — 角色 A（后端/AI核心）

**姓名**：[请填写姓名]  
**学号**：[请填写学号]  
**日期**：2026年6月29日  
**角色**：A（后端 / AI核心）

---

## 一、完成任务

### 1. FastAPI 项目框架搭建 ✅

**目录**：`server/`

- 安装依赖：`fastapi`、`uvicorn`、`sqlalchemy`、`pydantic`、`python-dotenv`、`httpx`、`loguru`
- 创建独立虚拟环境 `server/.venv`
- 编写 `server/main.py`：FastAPI 入口，注册 CORS 中间件（`allow_origins=["*"]`）+ 全局异常处理中间件
- 配置 `server/config.py`：`Config` 类从 `.env` 加载，包含 `HOST`/`PORT`/`DEBUG`/`DEMO_KEY` 等核心字段
- 启动命令：`python -m uvicorn server.main:app --host 127.0.0.1 --port 8000`
- Swagger UI 可访问 `http://localhost:8000/docs`

### 2. 数据库 Schema 设计 ✅

**文件**：`server/database/__init__.py`、`server/database/models.py`、`server/database/repository.py`

- 使用 SQLAlchemy 2.0 ORM 定义 **7 张表**：

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `t_users` | 用户账户 | user_id, username (unique), password_hash, role, preferences (JSON) |
| `t_transactions` | 事务日志 | task_id, user_query, intent_category, blueprint_json (JSON), plan_type (L2/L3), complexity_score, result, redline_triggered |
| `t_step_logs` | 步骤执行日志 | log_id, task_id (FK), step_index, action, target_element_id, status, fingerprint_before/after/match |
| `t_feedback` | 用户反馈 | feedback_id, task_id (FK), feedback_type (useful/useless/neutral), comment |
| `t_failures` | 失败/异常记录 | failure_id, task_id (FK), failure_type, step_index, fingerprint_hash, llm_snapshot, error_detail |
| `t_system_configs` | 热部署配置 | config_id, config_key (unique), config_value (JSON), description |
| `t_redline_logs` | 红线拦截日志 | log_id, query, category, action (reject/guided_reject/degrade), message |

- SQLite 引擎配置 + WAL 模式 + 外键启用
- `init_db()` 启动时自动建表（`Base.metadata.create_all`）
- 6 个 Repository 类：`TaskRepository`、`RedlineRepository`、`FeedbackRepository`、`FailureRepository`、`ConfigRepository`

### 3. 核心 API 骨架（5 个 Mock 端点）✅

**文件**：`server/routes/demo.py`

按 `api-contract-demo.yaml` 创建 5 个路由端点，均返回 Mock JSON：

| 端点 | 方法 | 认证 | Mock 返回内容 |
|------|------|------|-------------|
| `/api/demo/health` | GET | 无 | `{"status": "ok", "version": "1.0.0"}` |
| `/api/demo/process` | POST | X-Demo-Key | 4 步安装微信指引 + 硬编码 bbox 标注 |
| `/api/demo/step` | POST | X-Demo-Key | advance → 步骤推进，rollback → 回退 |
| `/api/demo/clarify` | POST | X-Demo-Key | 二选一澄清问题 |
| `/api/demo/report` | POST | X-Demo-Key | `{"received": true}` |

- `X-Demo-Key` 认证依赖：`verify_demo_key()` 校验 Header 中的 Demo Key
- Demo Key 默认值: `hajimi-demo-2026`

### 4. Pydantic 数据模型定义 ✅

**文件**：`server/models/schemas.py`

定义全部请求/响应数据结构：

- **请求模型**：`ProcessRequest`、`StepRequest`、`ClarifyRequest`、`ReportRequest`
- **响应模型**：`ProcessResponse`、`StepResponse`、`ClarifyResponse`、`ReportResponse`、`HealthResponse`
- **核心数据类**：`UIElement`（element_id/type/text/bbox/confidence）、`Step`（step_index/action/description/target_element_id/annotation/status）、`Annotation`（highlight_bbox/arrow/circle/label）、`Blueprint`（state/current_step/total_steps/fingerprint）
- **意图模型**：`Intent`（category/summary/confidence/reference_type）

### 5. LLM 初始封装 ✅

**文件**：`server/services/llm_ai.py`

- `classify_intent(query)` — 关键词规则分类（安装/截图/打开/设置/搜索/其他 → 6 种意图域），置信度硬编码
- `choose_scenario(query)` → `wechat`/`screenshot`/`default`
- `generate_steps(query)` — 调用 DeepSeek API 生成步骤文案
- `process_query(query)` — 组装 ProcessResponse（Demo 阶段 bbox 来自写死的 `SCENARIO_ELEMENTS` 模板，1920×1080）
- `call_deepseek()` — HTTP 调用 DeepSeek API（`/v1/chat/completions`，model=`deepseek-chat`）

### 6. 蓝图状态机初版 ✅

**文件**：`server/services/blueprint.py`

- 4 条基本迁移路径：`pending_confirm → executing`、`executing → completed`、`executing → rolling_back → executing`、`executing → terminated`
- 指纹比对逻辑：`Jaccard >= 0.8` 判定匹配

### 7. 内存任务存储 ✅

**文件**：`server/storage/memory.py`

- 线程安全字典：`task_id → TaskState`
- 支持 task 的 CRUD + 状态更新

### 8. 启动脚本与工具 ✅

- `scripts/start_server.bat` — 使用 `server/.venv` 启动 A 端
- `scripts/setup_server_env.bat` — 创建 venv + 安装依赖
- `server/.env` — DeepSeek API Key 配置
- `server/requirements.txt` — 依赖清单

---

## 二、目录结构

```
server/
├── main.py                     # FastAPI 入口 + CORS + 全局异常
├── config.py                   # 配置类（环境变量加载）
├── requirements.txt            # fastapi, uvicorn, sqlalchemy, httpx, pydantic...
├── .env                        # API Key / 端口配置
├── models/
│   ├── __init__.py
│   └── schemas.py              # Pydantic 数据模型（全部请求/响应）
├── routes/
│   ├── __init__.py
│   └── demo.py                 # 5 个 Mock 端点（health/process/step/clarify/report）
├── services/
│   ├── __init__.py
│   ├── llm_ai.py               # LLM 初始封装（意图+步骤+DeepSeek调用）
│   └── blueprint.py            # 蓝图状态机初版（4 条基本路径）
├── database/
│   ├── __init__.py              # SQLAlchemy 引擎 + 会话工厂
│   ├── models.py                # 7 表 ORM 模型
│   └── repository.py            # 6 个 Repository 类
├── storage/
│   ├── __init__.py
│   └── memory.py                # 内存任务存储（TaskState 字典）
└── test_api.py                  # 4 个 HTTP 端到端用例

scripts/
├── start_server.bat             # A 端启动脚本
├── setup_server_env.bat         # 环境初始化
└── stop_server.bat              # 停止脚本
```

---

## 三、验证结果

| 模块 | 状态 | 备注 |
|------|------|------|
| FastAPI 框架 | ✅ 通过 | Uvicorn 启动成功，Swagger UI 可见 |
| 数据库建表 | ✅ 通过 | 7 表 SQLite WAL 模式，`init_db()` 自动创建 |
| `/health` | ✅ 通过 | `{"status": "ok"}` 200 |
| `/process` (Mock) | ✅ 通过 | 返回 4 步安装微信指引 + 写死 bbox |
| `/step` (Mock) | ✅ 通过 | advance/rollback/terminate 正常 |
| `/clarify` (Mock) | ✅ 通过 | 澄清问题二选一 |
| `/report` (Mock) | ✅ 通过 | `{"received": true}` |
| DeepSeek API | ✅ 通过 | `call_deepseek()` 调通，生成步骤文案 |
| 蓝图状态机 | ✅ 通过 | 4 条基本迁移路径正确 |

**启动方式**：
```bash
cd E:\Fuzzy-Visual-Assisted-Question-Answering-System
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
# 或
scripts\start_server.bat
```

**接口验证**：
```bash
curl http://localhost:8000/api/demo/health
curl -X POST http://localhost:8000/api/demo/process \
  -H "X-Demo-Key: hajimi-demo-2026" -H "Content-Type: application/json" \
  -d '{"query":"怎么安装微信","image":""}'
```

---

## 四、遗留问题

1. **UI 元素坐标写死在 `SCENARIO_ELEMENTS` 模板**（1920×1080），与用户真实桌面无关 — 需对接 OmniParser 真实检测
2. **`ProcessRequest.image` 字段已接收但未传入 `process_query`** — 截图未真正被 AI 理解
3. **DeepSeek 只负责步骤文案**，不参与元素定位 — LLM 对 UI 元素"盲视"
4. **意图分类为 10 行 if-else 关键词匹配**，置信度硬编码 — 未覆盖 9 大意图域
5. **蓝图状态机仅覆盖 4 条基本路径**，缺少 suspended/rolling_back 异常迁移
6. **端口选择**：Demo 阶段暂用 8000，后续 B 端嵌入式 A 需用 8010

---

## 五、下一步计划（Day 2）

- 意图理解服务完善（`classify_intent` 升级 + 指代消解策略）
- 蓝图规划服务完善（复杂度路由 L2/L3 + LLM 蓝图生成 + 状态机补完）
- LLM API 封装独立为 `llm_client.py`（统一适配层，支持流式输出预留）
- OmniParser 客户端对接准备（为 Day 3 真实检测做准备）
- A-B 首次接口联调（B 调用 `/process` + `/step`）
