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

全部 7 个 Demo 端点 + 9 个 Admin 端点已实现：

| 端点 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/api/demo/health` | GET | 无 | 健康检查（含 `detector_backend`、`omniparser_ready`） |
| `/api/demo/process` | POST | X-Demo-Key | **核心流程**：OmniParser 识别 + LLM 看图规划 + 元素标注 |
| `/api/demo/inspect` | POST | X-Demo-Key | 仅检测 UI 元素 + SoM 标注图，不生成任务 |
| `/api/demo/step` | POST | X-Demo-Key | 推进/回退/跳过/终止蓝图步骤（含动态重规划） |
| `/api/demo/relocate` | POST | X-Demo-Key | PrepareStep：手动操作后重新截屏定位目标元素 |
| `/api/demo/clarify` | POST | X-Demo-Key | 主动澄清应答 |
| `/api/demo/report` | POST | X-Demo-Key | 审计与反馈上报 |

Admin 端点（`/api/admin/*`）：统计总览、高频任务、趋势、红线、反馈、失败列表/详情、配置管理，共 9 个端点。

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
├── main.py                      # FastAPI 入口 + CORS + 全局异常
├── config.py                    # 配置（LLM_* 优先，DEEPSEEK_* fallback）
├── requirements.txt             # Python 依赖
├── .env                         # 环境变量（不要提交到 Git）
├── .env.example                 # 环境变量模板
├── models/
│   └── schemas.py               # Pydantic 模型（含 Process/Step/Relocate 等）
├── routes/
│   ├── demo.py                  # Demo API 路由（7 个端点）
│   └── admin.py                 # Admin API 路由（9 个端点）
├── services/
│   ├── llm_ai.py                # 兼容入口层（路由到各子模块）
│   ├── omniparser_client.py     # 本地 OmniParser V2 HTTP 客户端
│   ├── redline_service.py       # 红线检测（物理操作/隐私/动态内容）
│   ├── perception/
│   │   └── serializer.py        # UI 元素序列化为 LLM prompt 文本
│   ├── llm/
│   │   ├── client.py            # LLM 客户端（支持多模态+纯文本，LLM_*/DEEPSEEK_* 优先级）
│   │   └── prompt.py            # SYSTEM_PROMPT（含 SoM 规则 + WPS few-shot）
│   ├── planning/
│   │   ├── router.py            # 步骤生成 + 约束提取 + 重定位匹配（全部走 call_deepseek）
│   │   ├── replanner.py         # 动态重规划（走 call_deepseek）
│   │   ├── blueprint_engine.py  # 蓝图状态机（7 状态全覆盖）
│   │   ├── annotation.py        # 屏幕标注构建（arrow_highlight/highlight_only）
│   │   └── complexity_router.py # L2/L3 复杂度路由 + 模板匹配
│   └── intent/
│       ├── setfit_classifier.py # SetFit 意图分类器（含 keywords fallback）
│       └── train_intent.py      # SetFit 训练脚本
├── storage/
│   └── memory.py                # 内存任务存储
├── database/
│   ├── models.py                # SQLAlchemy ORM（7 表）
│   └── repository.py            # 数据仓库层
└── tests/
    ├── conftest.py              # 共享 fixtures
    ├── test_legacy.py           # 老代码快照
    ├── test_perception.py       # P0：元素感知
    ├── test_replanner.py        # P2：动态重规划
    ├── test_blueprint.py        # P3：状态机迁移
    ├── test_intent.py           # P1：意图分类
    ├── test_constraint.py       # P4：约束条件提取
    └── test_redline.py          # 红线检测
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
