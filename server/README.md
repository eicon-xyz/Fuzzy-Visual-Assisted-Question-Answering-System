# HAJIMI Demo Server

HAJIMI 智能桌面指引助手 Demo 后端服务。

## 快速启动

```bash
# 1. 进入项目根目录
cd D:\HAJIMI\Fuzzy-Visual-Assisted-Question-Answering-System

# 2. 创建虚拟环境（首次）
python -m venv server/.venv

# 3. 激活虚拟环境
# Windows:
server\.venv\Scripts\activate
# macOS/Linux:
# source server/.venv/bin/activate

# 4. 安装依赖
pip install -r server/requirements.txt

# 5. 配置环境变量
# 复制 server/.env.example 为 server/.env，填入 API Key
copy server\.env.example server\.env

# 6. 启动服务（从项目根目录运行）
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000

# 或者进入 server 目录运行
# cd server && python main.py
```

服务启动后访问：

- API 文档：http://localhost:8000/docs
- Redoc：http://localhost:8000/redoc
- 健康检查：http://localhost:8000/api/demo/health

## 环境变量

### LLM 配置（推荐）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | SiliconCloud / LLM API Key | （必填） |
| `LLM_MODEL` | 模型名称，推荐多模态模型 | `Qwen/Qwen3.6-35B-A3B` |
| `LLM_BASE_URL` | LLM API 地址 | `https://api.siliconflow.cn/v1` |
| `LLM_TIMEOUT` | LLM 调用超时（秒） | `60` |

> **多模态支持**：当前使用 SiliconCloud 的 Qwen3.6-35B-A3B，传入 SoM 标注截图让模型看图规划步骤。图片通过 OpenAI Vision 兼容格式（`image_url` content 块 + data URI）传递。

### DeepSeek（兼容保留）

`LLM_*` 变量为空时自动 fallback 到以下配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key | （必填，仅 fallback 时） |
| `DEEPSEEK_MODEL` | 模型名称 | `deepseek-v4-flash` |
| `DEEPSEEK_TIMEOUT` | 调用超时（秒） | `30` |

> **注意**：DeepSeek V4 Flash 是纯文本模型，不支持图片输入。如果用 DeepSeek，LLM 只能看到元素列表文本而看不到截图。

### 服务与认证

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HAJIMI_DEMO_KEY` | Demo 认证 Key | `hajimi-demo-2026` |
| `HAJIMI_HOST` | 服务监听地址 | `0.0.0.0` |
| `HAJIMI_PORT` | 服务端口 | `8000` |
| `HAJIMI_DEBUG` | 调试模式 | `true` |

### Demo 开关

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `USE_REAL_LLM` | 是否调用真实 LLM | `true` |
| `STRICT_FINGERPRINT` | 是否严格校验屏幕指纹 | `false` |

### OmniParser 视觉检测

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OMNIPARSER_URL` | OmniParser V2 服务地址 | `http://127.0.0.1:9800` |
| `OMNIPARSER_TIMEOUT` | 调用超时（秒） | `360` |

### SetFit 意图分类

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `INTENT_MODEL_PATH` | SetFit 模型路径 | `server/services/intent/model` |

## API 端点

### Demo 核心端点（7 个）

| 端点 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/api/demo/health` | GET | 无 | 健康检查（含 `detector_backend`、`omniparser_ready`） |
| `/api/demo/process` | POST | X-Demo-Key | **核心流程**：OmniParser 识别 + LLM 多模态看图规划 + 元素语义绑定 |
| `/api/demo/inspect` | POST | X-Demo-Key | 仅检测 UI 元素 + SoM 标注图，不生成任务（供 B 端 Settings 校验） |
| `/api/demo/step` | POST | X-Demo-Key | 推进/回退/跳过/终止蓝图步骤（含动态重规划） |
| `/api/demo/relocate` | POST | X-Demo-Key | PrepareStep：手动操作后重新截屏定位目标元素（LLM 匹配 + 文本 fallback） |
| `/api/demo/clarify` | POST | X-Demo-Key | 主动澄清应答 |
| `/api/demo/report` | POST | X-Demo-Key | 审计与反馈上报（日志 + 数据库双写） |

### Admin 管理端点（9 个）

| 端点 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/api/admin/stats/overview` | GET | X-Admin-Key | 仪表盘 KPI 总览 |
| `/api/admin/stats/top-tasks` | GET | X-Admin-Key | 高频任务 TOP 10 |
| `/api/admin/stats/trend` | GET | X-Admin-Key | 24h 事务趋势 |
| `/api/admin/stats/redline` | GET | X-Admin-Key | 红线拦截统计 |
| `/api/admin/stats/feedback` | GET | X-Admin-Key | 用户反馈分布 |
| `/api/admin/failures/list` | GET | X-Admin-Key | 失败记录列表 |
| `/api/admin/failures/detail/{task_id}` | GET | X-Admin-Key | 单条失败详情 |
| `/api/admin/config/current` | GET | X-Admin-Key | 获取全部系统配置 |
| `/api/admin/config/deploy` | POST | X-Admin-Key | 热部署配置 |

> **注**：统一接口文档中定义的审计上报、配置拉取、数据流拓扑、健康监控等端点（`/api/audit/*`、`/api/config/pull`、`/api/admin/flow/*`、`/api/admin/monitor/*`）尚未实现，为 P2 级别长期任务。

## 测试命令

```bash
# 健康检查
curl http://localhost:8000/api/demo/health

# 完整测试套件（需先安装 pytest）
pip install pytest
pytest server/tests/ -v

# 核心流程测试
python -c "
import httpx
r = httpx.post('http://localhost:8000/api/demo/process',
    headers={'X-Demo-Key': 'hajimi-demo-2026'},
    json={'query': '怎么安装微信？'})
print(r.json())
"
```

## 项目结构

```
server/
├── main.py                      # FastAPI 入口 + CORS + 全局异常 + 数据库初始化
├── config.py                    # 配置（LLM_* 优先，DEEPSEEK_* fallback）
├── requirements.txt             # Python 依赖（fastapi, uvicorn, httpx, pydantic…）
├── .env                         # 环境变量（不要提交到 Git）
├── .env.example                 # 环境变量模板
│
├── models/
│   └── schemas.py               # Pydantic 模型（Process/Step/Relocate/Inspect/Blueprint/Intent…）
│
├── routes/
│   ├── demo.py                  # Demo API 路由（7 个端点：health/process/inspect/step/relocate/clarify/report）
│   └── admin.py                 # Admin API 路由（9 个端点：stats×5 + failures×2 + config×2）
│
├── services/
│   ├── llm_ai.py                # ⚠️ DEPRECATED 兼容入口 — 所有实现已迁移到子模块（perception/llm/planning/intent/）
│   ├── omniparser_client.py     # 本地 OmniParser V2 HTTP 客户端（调用 :9800 检测 UI 元素 + SoM 渲染）
│   ├── redline_service.py       # 红线检测（物理操作/隐私/动态内容，触发时 ProcessResponse 含 redline 字段）
│   │
│   ├── perception/
│   │   └── serializer.py        # UI 元素序列化为 LLM prompt 文本（按置信度排序，最多 25 个）
│   │
│   ├── llm/
│   │   ├── client.py            # LLM 统一客户端（支持多模态 OpenAI Vision 格式 + 纯文本，LLM_*/DEEPSEEK_* 优先级）
│   │   └── prompt.py            # SYSTEM_PROMPT（含 SoM 标注规则 + 元素匹配规则 + WPS/Office 菜单栏 few-shot）
│   │
│   ├── planning/
│   │   ├── router.py            # 步骤生成 + 约束提取 + 重定位匹配（全部走 call_deepseek 统一 LLM 客户端）
│   │   ├── replanner.py         # 动态重规划（基于新截图为未绑定步骤补全 target_element_id）
│   │   ├── blueprint_engine.py  # 蓝图状态机（7 状态全覆盖：generated→pending_confirm→executing→completed/terminated + suspended/rolling_back）
│   │   ├── annotation.py        # 屏幕标注构建（arrow_highlight / highlight_only）
│   │   └── complexity_router.py # L2/L3 复杂度路由 + 场景模板匹配
│   │
│   └── intent/
│       ├── setfit_classifier.py # SetFit 意图分类器（9 类意图 + keywords fallback）
│       └── train_intent.py      # SetFit 训练脚本
│
├── storage/
│   └── memory.py                # 内存任务存储（Demo 阶段，重启清空）
│
├── database/
│   ├── models.py                # SQLAlchemy ORM（7 表：Transaction/Redline/Feedback/Failure/Config…）
│   └── repository.py            # 数据仓库层（TaskRepository/RedlineRepository/FeedbackRepository/…）
│
└── tests/
    ├── conftest.py              # 共享 fixtures
    ├── test_legacy.py           # 老代码快照测试
    ├── test_perception.py       # P0：元素感知（6 条用例）
    ├── test_replanner.py        # P2：动态重规划（5 条用例）
    ├── test_blueprint.py        # P3：蓝图状态机迁移（4 条用例）
    ├── test_intent.py           # P1：SetFit 意图分类
    ├── test_constraint.py       # P4：约束条件提取（6 条用例）
    └── test_redline.py          # 红线检测
```

### 核心数据流

```
用户截图 + 问题
    │
    ▼
POST /api/demo/process
    │
    ├─→ omniparser_client.parse_screenshot_full()  # ① 调用本地 OmniParser (:9800) 检测 UI 元素 + SoM 渲染
    │
    ├─→ intent/classify_intent()                   # ② SetFit 意图分类（9 类，keywords fallback）
    │
    ├─→ redline_service.check_redline()            # ③ 红线检测（物理操作/隐私/动态内容）
    │
    ├─→ llm/client.call_deepseek()                 # ④ LLM 多模态规划（Qwen3.6，SoM 图 + 元素列表 → 步骤 + 约束）
    │   ├─ 有图：OpenAI Vision 格式（image_url + 元素文本）
    │   └─ 无图：纯文本模式
    │
    └─→ ProcessResponse                            # ⑤ 组装响应（steps + target_element_id + annotation + SoM 图）
        │
        ▼
    POST /api/demo/step (advance)
        │
        ├─→ blueprint_engine.advance()             # ⑥ 状态机推进
        ├─→ replanner.replan_steps()               # ⑦ 当前步无 target_element_id 时触发动态重规划
        └─→ StepResponse
```

## 注意事项

1. **`.env` 文件包含 API Key，已加入 `.gitignore`，请勿提交。**
2. **LLM 优先级**：`LLM_API_KEY` > `DEEPSEEK_API_KEY`。配置了 `LLM_*` 就只用硅基流动，没配置才 fallback 到 DeepSeek。
3. **多模态支持**：当前 LLM（Qwen3.6）能收到 SoM 标注截图，看图理解元素编号和布局。DeepSeek V4 Flash 不支持图片输入。
4. Demo 阶段任务状态保存在内存中，服务重启后清空。
5. UI 元素坐标来自 OmniParser V2 真实屏幕检测，步骤与元素绑定由 LLM 语义匹配完成。
6. 如果 LLM 调用失败，会自动降级为预设 Mock 步骤（场景模板）。
7. `/api/demo/relocate` 供 B 端在当前画面找不到目标元素时使用：用户手动完成步骤后重新截图上传，A 端对新截图重新定位目标元素。
8. 启动顺序：① OmniParser (`:9800`) → ② A 端 (`:8000`) → ③ B 端。
