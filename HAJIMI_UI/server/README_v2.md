# HAJIMI Demo Server（v2）

HAJIMI 智能桌面指引助手 Demo 后端服务。

> **学校 GPU 容器部署**：见 [`docs/A端-学校GPU部署与联调指南_v2.md`](docs/A端-学校GPU部署与联调指南_v2.md)（阶段 0–7 可勾选清单）。

## 快速启动（推荐：独立 venv，不与 videorag/streamlit 冲突）

```bash
# 1. 进入项目根目录
cd E:\University\greed3-2\Shixun\HAJIMI_UI

# 2. 首次：创建 server 专用虚拟环境并安装依赖
scripts\setup_server_env.bat

# 3. 配置环境变量（可选）
copy server\.env.example server\.env
# 编辑 server\.env 填入 DEEPSEEK_API_KEY

# 4. 启动 A 端（默认端口 8010）
scripts\start_server.bat

# 手动指定端口（若 8010 被占用）
set HAJIMI_PORT=8011
scripts\start_server.bat
```

等价命令：

```bash
python -m uvicorn server.main:app --host 127.0.0.1 --port 8010
```

## 与 B 端（PyQt 客户端）联调

1. **终端 1** 启动 A 端（本服务）
2. **终端 2** 启动 B 端：`python main.py`
3. B 端启动时会探测 `/api/demo/health`，显示「A 端已连接」或启动指引
4. 联调验收：`python scripts/verify_integration.py`

B 端环境变量（与 A 端对齐）：

| 变量 | 说明 | 默认 |
|------|------|------|
| `HAJIMI_API_URL` | A 端地址 | `http://127.0.0.1:8010` |
| `HAJIMI_DEMO_KEY` | 认证 Key | `hajimi-demo-2026` |
| `HAJIMI_MOCK_FALLBACK` | A 端不可达时回退本地 Mock | `0`（默认关闭） |
| `HAJIMI_MOCK_ONLY` | 强制纯 Mock | `0` |

服务启动后访问：

- API 文档：http://127.0.0.1:8010/docs
- Redoc：http://127.0.0.1:8010/redoc
- 健康检查：http://127.0.0.1:8010/api/demo/health

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key | （必填） |
| `DEEPSEEK_MODEL` | 模型名称 | `deepseek-chat` |
| `DEEPSEEK_TIMEOUT` | LLM 调用超时（秒） | `30` |
| `HAJIMI_DEMO_KEY` | Demo 认证 Key | `hajimi-demo-2026` |
| `HAJIMI_HOST` | 服务监听地址 | `0.0.0.0` |
| `HAJIMI_PORT` | 服务端口 | `8010` |
| `USE_REAL_LLM` | 是否调用真实 LLM | `true` |
| `STRICT_FINGERPRINT` | 是否严格校验屏幕指纹 | `false` |

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/demo/health` | GET | 健康检查 |
| `/api/demo/process` | POST | 核心流程：识图 + 生成步骤 + 标注坐标 |
| `/api/demo/step` | POST | 推进/回退/跳过/终止蓝图步骤 |
| `/api/demo/clarify` | POST | 主动澄清应答 |
| `/api/demo/report` | POST | 审计与反馈上报 |

## 测试命令

```bash
# 健康检查
curl http://127.0.0.1:8010/api/demo/health

# 核心流程
python -c "
import httpx
r = httpx.post('http://127.0.0.1:8010/api/demo/process',
    headers={'X-Demo-Key': 'hajimi-demo-2026'},
    json={'query': '怎么安装微信？'})
print(r.json())
"
```

## 项目结构

```
server/
├── main.py              # FastAPI 入口
├── config.py            # 配置
├── requirements.txt     # 依赖
├── .env                 # 环境变量（不要提交到 Git）
├── .env.example         # 环境变量模板
├── models/
│   └── schemas.py       # Pydantic 模型
├── routes/
│   └── demo.py          # API 路由
├── services/
│   ├── llm_ai.py        # AI 推理服务（DeepSeek + Mock 降级）
│   └── blueprint.py     # 蓝图状态机
└── storage/
    └── memory.py        # 内存任务存储
```

## 注意事项

1. `.env` 文件包含 API Key，已加入 `.gitignore`，请勿提交。
2. **不要在 videorag 等共用 conda 环境里 `pip install -r server/requirements.txt`**，会与 streamlit 的 starlette 版本冲突；请用 `scripts\setup_server_env.bat`。
3. Demo 阶段任务状态保存在内存中，服务重启后清空。
3. DeepSeek 为文本模型，UI 元素坐标由规则生成，步骤文案由 LLM 生成。
4. 如果 LLM 调用失败，会自动降级为预设 Mock 步骤。
