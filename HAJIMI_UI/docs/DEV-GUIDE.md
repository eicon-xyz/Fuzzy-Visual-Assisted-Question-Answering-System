# HAJIMI 自动操作助手 — 开发环境搭建指南

> 3人协作 | 2026-07-04

---

## 项目结构速览

```
HAJIMI_UI/
├── main.py                  # B 端入口（PyQt5 UI）
├── config.py                # B 端配置（API地址、超时等）
├── core/
│   ├── api_client.py        # A 端 HTTP 调用封装
│   ├── a_end_launcher.py    # 自动启动 A 端
│   ├── screen_utils.py      # 截图(mss)、坐标、指纹
│   ├── task_worker.py       # B 端后台任务线程（会被简化）
│   └── service_manager.py   # 后端进程管理
├── ui/
│   ├── main_widget.py       # B 端主窗口（需要改）
│   ├── agent_panel.py       # 🆕 自动操作面板（Day 1 新建）
│   ├── app_controller.py    # 业务控制器（需要改）
│   └── native/              # 原生 UI 组件
├── server/                  # A 端（FastAPI）
│   ├── main.py              # 入口：uvicorn server.main:app
│   ├── config.py            # A 端配置
│   ├── routes/demo.py       # API 路由（需要改）
│   ├── models/schemas.py    # Pydantic 数据模型
│   ├── services/
│   │   ├── omniparser_client.py  # OmniParser HTTP 客户端 ✅ 已完整
│   │   ├── ui_detector.py        # UI 元素检测器 ✅ 已完整
│   │   ├── executor/             # 🆕 执行引擎（Day 1 新建）
│   │   ├── planning/router.py    # LLM 规划（需要改 prompt）
│   │   └── llm/                  # LLM 客户端 ✅ 已完整
│   └── database/             # SQLite 持久化
├── OmniParser/              # 远程 GPU 上已部署，本地无需运行
├── scripts/                 # bat 启动脚本
└── docs/                    # 文档
```

---

## 环境准备（3人统一）

### 1. Python 环境

**A 端**（server/ 目录下运行）：
```bash
cd D:\HAJI\HAJIMI_UI

# 创建 venv
python -m venv server\.venv

# 激活
server\.venv\Scripts\activate

# 安装依赖
pip install -r server/requirements.txt
pip install httpx fastapi uvicorn pydantic python-dotenv loguru
pip install mss pyautogui pydirectinput Pillow

# 🆕 执行引擎新依赖
pip install pyautogui pydirectinput
```

**B 端**（项目根目录运行）：
```bash
cd D:\HAJI\HAJIMI_UI
pip install PyQt5 mss Pillow
```

### 2. server/.env 配置

确保文件存在且包含：

```env
# ── OmniParser（远程 GPU :9800）──
OMNIPARSER_URL=http://127.0.0.1:9800
OMNIPARSER_TIMEOUT=30

# ── LLM ──
LLM_API_KEY=sk-你的key
LLM_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=Qwen/Qwen3.6-35B-A3B
LLM_PROVIDER=qwen

# ── 服务 ──
HAJIMI_DEMO_KEY=hajimi-demo-2026
HAJIMI_HOST=0.0.0.0
HAJIMI_PORT=8010
HAJIMI_DEBUG=true
```

### 3. 确认远程 OmniParser 可达

```bash
curl http://127.0.0.1:9800/probe/
# 预期响应: {"ready": true, "device": "cuda"}
```

---

## 启动方式

### A 端

```bash
cd D:\HAJI\HAJIMI_UI
# 方式1: 直接启动
server\.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8010

# 方式2: bat 脚本
scripts\start_server.bat
```

**验证**：
```bash
curl http://127.0.0.1:8010/api/demo/health
# {"status":"ok", "omniparser_ready":true, ...}
```

### B 端

```bash
cd D:\HAJI\HAJIMI_UI
python main.py
```

### Mock 模式（不需要 A 端 + OmniParser，纯测 UI）

```bash
set HAJIMI_MOCK_ONLY=1
python main.py
```
此时 UI 使用本地 mock 数据，不连接后端。

---

## 快速验证管道

```bash
# 1. OmniParser 可用
curl http://127.0.0.1:9800/probe/

# 2. A 端健康
curl http://127.0.0.1:8010/api/demo/health

# 3. 截图 + 执行（需要实际截图 base64）
python -c "
import mss, base64
from io import BytesIO
from PIL import Image
import urllib.request, json
# 截图
with mss.mss() as sct:
    img = sct.grab(sct.monitors[1])
    pil = Image.frombytes('RGB', img.size, img.bgra, 'raw', 'BGRX')
    buf = BytesIO()
    pil.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()

# 请求
req = urllib.request.Request('http://127.0.0.1:8010/api/demo/execute',
    data=json.dumps({'query':'打开记事本','image':f'data:image/png;base64,{b64}'}).encode(),
    headers={'Content-Type':'application/json','X-Demo-Key':'hajimi-demo-2026'})
resp = json.loads(urllib.request.urlopen(req).read())
print(resp['task_id'], resp['plan']['total_steps'], 'steps')
"
```

---

## B 端开发建议

### 开发阶段分两步

**阶段 1：用 mock 数据先把 UI 画好（今天 + 明天上午）**
- `set HAJIMI_MOCK_ONLY=1` 启动
- 在 `agent_panel.py` 中硬编码假步骤数据，把布局、样式、状态切换都调通
- 不需要等 A 端写好就能并行工作

**阶段 2：对接真实 SSE（明天下午 + Day 3）**
- 关 mock，连真实 A 端
- 用 `QNetworkAccessManager` 请求 `/stream/{task_id}`
- SSE 解析用简单的行读取（`response.read()` 逐行解析 `event:` / `data:`）

### SSE 客户端简易实现

```python
import json
from PyQt5.QtCore import QThread, pyqtSignal

class SSEClient(QThread):
    event_received = pyqtSignal(str, dict)  # (event_type, data)

    def __init__(self, task_id):
        super().__init__()
        self.task_id = task_id
        self._running = True

    def run(self):
        import urllib.request
        url = f"http://127.0.0.1:8010/api/demo/stream/{self.task_id}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            event_type = ""
            data_str = ""
            for line in resp:
                if not self._running:
                    break
                line = line.decode('utf-8').strip()
                if line.startswith('event:'):
                    event_type = line[6:].strip()
                elif line.startswith('data:'):
                    data_str = line[5:].strip()
                    try:
                        data = json.loads(data_str)
                        self.event_received.emit(event_type, data)
                    except:
                        pass
                # 空行 = 一个事件结束

    def stop(self):
        self._running = False
```

---

## 配置文件同步

当前代码中 A、B 端各有独立的 config 文件，一些关键值需要对齐：

| 配置项 | B 端(config.py) | A 端(server/config.py) |
|--------|-----------------|------------------------|
| 端口 | `HAJIMI_PORT`=8010 | `HAJIMI_PORT`=8010 |
| Demo Key | `HAJIMI_DEMO_KEY`=hajimi-demo-2026 | 同 |
| OmniParser URL | 不需要(B端不直连) | `OMNIPARSER_URL`=http://127.0.0.1:9800 |

---

## 常见问题

| 问题 | 排查 |
|------|------|
| OmniParser 超时 | `curl http://127.0.0.1:9800/probe/` 确认可达 |
| A 端 401 认证失败 | Header `X-Demo-Key` 值是否匹配 `.env` 中的 `HAJIMI_DEMO_KEY` |
| B 端连不上 A 端 | 确认 A 端已启动，端口 8010 未被占用 |
| mock 模式 UI 空白 | 检查 `HAJIMI_MOCK_ONLY=1` 环境变量是否设置 |
