# HAJIMI Demo Server

HAJIMI 智能桌面指引助手 Demo 后端服务。

## 快速启动

```bash
# 1. 进入项目根目录
cd D:\模糊视觉辅助问答系统

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
# 复制 server/.env.example 为 server/.env，填入 DeepSeek API Key
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

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key | （必填） |
| `DEEPSEEK_MODEL` | 模型名称 | `deepseek-chat` |
| `DEEPSEEK_TIMEOUT` | LLM 调用超时（秒） | `30` |
| `HAJIMI_DEMO_KEY` | Demo 认证 Key | `hajimi-demo-2026` |
| `HAJIMI_HOST` | 服务监听地址 | `0.0.0.0` |
| `HAJIMI_PORT` | 服务端口 | `8000` |
| `USE_REAL_LLM` | 是否调用真实 LLM（DeepSeek） | `true` |
| `STRICT_FINGERPRINT` | 是否严格校验屏幕指纹 | `false` |
| `OMNIPARSER_URL` | OmniParser V2 服务地址 | `http://127.0.0.1:9800` |
| `OMNIPARSER_TIMEOUT` | OmniParser 超时（秒） | `30` |
| `INTENT_MODEL_PATH` | SetFit 意图分类模型路径 | `server/services/intent/model` |

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/demo/health` | GET | 健康检查（含 `detector_backend`、`omniparser_ready`） |
| `/api/demo/process` | POST | 核心流程：OmniParser 真实识图 + 步骤生成 + 元素标注 |
| `/api/demo/step` | POST | 推进/回退/跳过/终止蓝图步骤 |
| `/api/demo/relocate` | POST | 手动完成一步后重新截屏定位目标元素 |
| `/api/demo/clarify` | POST | 主动澄清应答 |
| `/api/demo/report` | POST | 审计与反馈上报 |

## 测试命令

```bash
# 健康检查
curl http://localhost:8000/api/demo/health

# 核心流程（Windows PowerShell 用 Invoke-WebRequest 或直接用 Python）
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
├── config.py                    # 配置（环境变量）
├── requirements.txt             # Python 依赖
├── .env                         # 环境变量（不要提交到 Git）
├── .env.example                 # 环境变量模板
├── models/
│   └── schemas.py               # Pydantic 模型（含 Process/Step/Relocate 等）
├── routes/
│   └── demo.py                  # API 路由（7 个端点）
├── services/
│   ├── llm_ai.py                # 兼容入口层（路由到各子模块）
│   ├── omniparser_client.py     # 本地 OmniParser V2 HTTP 客户端
│   ├── perception/
│   │   └── serializer.py        # UI 元素序列化为 LLM prompt 文本
│   ├── llm/
│   │   ├── client.py            # DeepSeek HTTP 客户端
│   │   └── prompt.py            # SYSTEM_PROMPT + REPLAN_PROMPT
│   ├── planning/
│   │   ├── router.py            # 步骤生成 + 约束提取 + 重定位匹配
│   │   ├── replanner.py         # 动态重规划
│   │   └── blueprint_engine.py  # 蓝图状态机（7 状态全覆盖）
│   └── intent/
│       ├── setfit_classifier.py # SetFit 意图分类器（含 keywords fallback）
│       └── train_intent.py      # SetFit 训练脚本
├── storage/
│   └── memory.py                # 内存任务存储
└── tests/
    ├── conftest.py              # 共享 fixtures
    ├── test_legacy.py           # 老代码快照
    ├── test_perception.py       # P0：元素感知
    ├── test_replanner.py        # P2：动态重规划
    ├── test_blueprint.py        # P3：状态机迁移
    ├── test_intent.py           # P1：意图分类
    └── test_constraint.py       # P4：约束条件提取
```

## 注意事项

1. `.env` 文件包含 API Key，已加入 `.gitignore`，请勿提交。
2. Demo 阶段任务状态保存在内存中，服务重启后清空。
3. UI 元素坐标来自 OmniParser V2 真实屏幕检测，步骤与元素绑定由 DeepSeek LLM 语义匹配完成。
4. 如果 DeepSeek 调用失败，会自动降级为预设 Mock 步骤（场景模板）。
5. `/api/demo/relocate` 供 B 端在当前画面找不到目标元素时使用：用户手动完成步骤后重新截图上传，A 端对新截图重新定位目标元素。
