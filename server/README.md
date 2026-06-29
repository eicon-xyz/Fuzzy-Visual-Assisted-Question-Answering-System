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
2. Demo 阶段任务状态保存在内存中，服务重启后清空。
3. DeepSeek 为文本模型，UI 元素坐标由规则生成，步骤文案由 LLM 生成。
4. 如果 LLM 调用失败，会自动降级为预设 Mock 步骤。
