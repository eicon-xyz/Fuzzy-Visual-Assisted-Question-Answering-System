# B端 — OmniParser GPU API 部署与操作文档

> **版本**：2.0.0  
> **日期**：2026-07-02  
> **维护**：B端 (GPU 节点)  
> **适用环境**：学校 GPU 实训平台 (NVIDIA A800 80GB)  
> **前置阅读**：[OmniParser GPU 环境交接文档](OmniParser%20GPU%20环境交接文档.md)、[HAJIMI 统一接口文档](HAJIMI-统一接口文档.md)

---

## 一、B端 定位与职责

在 HAJIMI 三端架构中，**B端 = GPU OmniParser 推理服务**，职责如下：

```
                    HTTP REST (JSON + Base64)
       ┌──────────┐  ───────────────────────►  ┌──────────────┐
       │ A端 后端  │                              │ B端 GPU API   │
       │ FastAPI  │  ◄───────────────────────  │ OmniParser    │
       │ :8000    │     SoM标注图 + UI元素        │ :9800         │
       └──────────┘                              └──────────────┘
```

| 职责　　　　　　　　| 说明　　　　　　　　　　　　　　　　　　　　　　|
| ---------------------| -------------------------------------------------|
| **接收截图**　　　　| A端 通过 HTTP POST 发送 Base64 编码的截图　　　 |
| **UI 元素检测**　　 | 运行 YOLO + PaddleOCR + Florence-2 三模型流水线 |
| **返回结构化数据**　| 每个元素的 bbox、类型、文字、置信度　　　　　　 |
| **返回 SoM 标注图** | 带编号标注框的可视化截图 (Set-of-Mark)　　　　　|
| **健康报告**　　　　| 提供 GPU 状态、模型就绪情况　　　　　　　　　　 |

**B端 不负责**：
- 意图理解 / 蓝图规划 / 步骤生成 → A端
- 截图采集 / 桌面覆盖层渲染 → A端 调用方
- 语音 / 审计 / 配置管理 → C端

---

## 二、启动前检查清单

在首次部署或重启后，逐项确认：

### 2.1 硬件与环境

```bash
# GPU 是否可见
nvidia-smi
# 预期输出: NVIDIA A800-SXM4-80GB, Driver 535.309.01, CUDA 12.2

# Python 版本
python3 --version
# 预期: Python 3.10.12

# PyTorch CUDA
python3 -c "import torch; print(torch.cuda.is_available())"
# 预期: True

python3 -c "import torch; print(torch.cuda.get_device_name(0))"
# 预期: NVIDIA A800-SXM4-80GB
```

### 2.2 模型权重

```bash
ls /workspace/models/OmniParser-v2.0/
# 应有 icon_detect/ 等目录

ls /workspace/models/Florence-2-large/
# 应有 model.safetensors 或 pytorch_model.bin

# 软链接检查
ls -l /workspace/code/OmniParser/weights/
# icon_detect -> /workspace/models/OmniParser-v2.0/icon_detect
# icon_caption_florence -> /workspace/models/Florence-2-large
```

### 2.3 依赖环境

```bash
# 激活虚拟环境
source /workspace/code/omniparser_api/.venv/bin/activate

# 关键库版本
pip list 2>/dev/null | grep -E "torch|transformers|paddleocr|fastapi"
# torch==2.7.1+cu118
# transformers==4.43.4
# paddleocr==2.8.1
# paddlepaddle-gpu==2.6.1
# fastapi (any recent)
```

### 2.4 源码修改（必须）

根据 [GPU 环境交接文档](OmniParser%20GPU%20环境交接文档.md) 第 4 节，确认以下 4 处修改已生效：

| # | 文件 | 修改内容 |
|---|------|---------|
| 1 | `transformers/dynamic_module_utils.py` | 注释 `raise ImportError` |
| 2 | `modeling_florence2.py` | 强制 `is_flash_attn_2_available() → False` |
| 3 | `gradio_client/utils.py` | `isinstance(schema, dict)` 判断 |
| 4 | `OmniParser/util/utils.py` | OCR 空值 + 排序类型修复 |

### 2.5 网络可达性

```bash
# 确认端口未被占用
lsof -i :9800 || echo "端口 9800 空闲 ✓"

# 确认校园网其他节点可访问本机 (在 A端 所在机器执行)
# curl http://<GPU_SERVER_IP>:9800/health
```

---

## 三、启动与停止

### 3.1 一键启动

```bash
cd /workspace/code/omniparser_api

# GPU 模式 (默认)
./start.sh

# CPU 模式 (不推荐，仅调试用)
./start.sh --cpu

# 指定端口
./start.sh --port 8080
```

启动过程：
1. 环境预检 (Python、CUDA、模型权重)
2. 激活虚拟环境
3. 加载 YOLO (约 3s) → Florence-2 (约 5s) → PaddleOCR (约 2s)
4. 启动 FastAPI uvicorn 并监听
5. 轮询 `/health` 等待就绪 (最多 120s)

**预期启动时间**：首次约 10-20 秒 (模型加载)

### 3.2 停止

```bash
./stop.sh

# 或手动
kill $(cat omniparser.pid)
```

### 3.3 使用 systemd (推荐生产环境)

```bash
# 复制 service 文件
sudo cp omniparser.service /etc/systemd/system/

# 重载配置
sudo systemctl daemon-reload

# 启动并设为开机自启
sudo systemctl enable --now omniparser

# 查看状态
sudo systemctl status omniparser

# 查看日志
sudo journalctl -u omniparser -f
```

### 3.4 查看日志

```bash
# 实时日志
tail -f logs/server_*.log

# 错误日志
grep -i error logs/server_*.log

# 最近 50 行
tail -50 logs/server_*.log
```

---

## 四、API 接口规范

### 4.1 接口总览

| 端点 | 方法 | 认证 | 超时 (建议) | 说明 |
|------|------|------|------------|------|
| `/health` | GET | 无 | 5s | 健康检查 (A端 预检用) |
| `/probe/` | GET | 无 | 5s | 详细探测 (含 GPU 显存详情) |
| `/parse/` | POST | 无 | 360s | **核心解析** (截图 → 元素 + SoM 图) |

### 4.2 `GET /health`

A端 启动时调用，检测 OmniParser 是否就绪。

**响应 200**：

```json
{
  "status": "ok",
  "version": "2.0.0",
  "ready": true,
  "device": "cuda",
  "cuda_available": true,
  "gpu_name": "NVIDIA A800-SXM4-80GB",
  "vram_gb": 80.0,
  "model_load_time_s": 12.3,
  "ocr_engine": "paddle",
  "uptime": "see /probe/"
}
```

**关键字段**：
| 字段 | 类型 | A端 使用方式 |
|------|------|-------------|
| `ready` | bool | `false` → 阻止 parse/inspect 调用 |
| `cuda_available` | bool | `false` → 性能警告 |
| `gpu_name` | string | 展示在管理面板 |
| `ocr_engine` | string | `paddle` 或 `easyocr` |

**A端 预检逻辑**：
```python
health = requests.get("http://GPU_IP:9800/health", timeout=5)
if not health.json()["ready"]:
    raise Exception("OmniParser 未就绪，请等待模型加载或检查 GPU 状态")
```

### 4.3 `GET /probe/`

详细探测，用于调试和监控。

**响应 200**：

```json
{
  "status": "ok",
  "ready": true,
  "device": "cuda",
  "cuda_available": true,
  "pytorch_version": "2.7.1+cu118",
  "python_version": "3.10.12",
  "gpu": {
    "name": "NVIDIA A800-SXM4-80GB",
    "count": 1,
    "vram_total_gb": 80.0,
    "vram_allocated_gb": 4.52,
    "vram_reserved_gb": 6.10
  },
  "models": {
    "yolo_loaded": true,
    "florence2_loaded": true,
    "ocr_engine": "paddle"
  },
  "config": {
    "box_threshold": 0.05
  },
  "model_load_time_s": 12.3
}
```

### 4.4 `POST /parse/` — 核心解析

**请求** `Content-Type: application/json`：

```json
{
  "base64_image": "iVBORw0KGgoAAAANSUhEUgAA..."
}
```

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| `base64_image` | string | ✅ | 1–50MB (编码后) | 截图的 Base64，可带 `data:image/png;base64,` 前缀 |

**处理流水线**：

```
Base64 图片
    │
    ▼
① 解码 → PIL Image (RGB)
    │
    ▼
② PaddleOCR / EasyOCR ──→ 文字 + bbox 列表
    │
    ▼
③ YOLO 检测 ──→ 图标/按钮 bbox 列表
    │
    ▼
④ 去重合并 (remove_overlap_new)
    │
    ▼
⑤ Florence-2 为每个图标生成语义描述 (batch_size=128)
    │
    ▼
⑥ 绘制 SoM 标注图 (绿框=图标, 红框=文字)
    │
    ▼
返回 JSON
```

**响应 200**：

```json
{
  "som_image_base64": "iVBORw0KGgo...",
  "parsed_content_list": [
    {
      "element_id": "~0",
      "bbox": [120, 340, 200, 380],
      "element_type": "button",
      "text": "开始菜单",
      "confidence": 1.0,
      "center": [160, 360],
      "source": "box_yolo_content_yolo"
    },
    {
      "element_id": "~1",
      "bbox": [500, 200, 650, 240],
      "element_type": "text",
      "text": "搜索",
      "confidence": 1.0,
      "center": [575, 220],
      "source": "box_ocr_content_ocr"
    }
  ],
  "latency_ms": 3100,
  "image_size": {"width": 2560, "height": 1600},
  "element_count": 47,
  "backend": "local_omniparser_paddle",
  "device": "cuda"
}
```

**性能参考** (GPU 模式, A800)：

| 分辨率 | 检测时间 |
|--------|---------|
| 1920×1080 | 1–3 秒 |
| 2560×1600 | 2–5 秒 |
| 3840×2160 (4K) | 5–10 秒 |

**错误码**：

| HTTP | code | 触发条件 |
|------|------|---------|
| 400 | `INVALID_IMAGE` | Base64 解码失败 / 图片格式损坏 |
| 502 | `DETECTOR_FAILED` | 模型推理异常 (GPU OOM / 模型未加载) |

---

## 五、A端 集成方法

### 5.1 安装客户端 SDK

将以下文件复制到 A端 项目目录：

```
server/services/omniparser_client.py   ← 即本项目 code/omniparser_api/client.py
```

A端 无额外 pip 依赖 — `client.py` 仅使用 Python 标准库 (`urllib`, `json`, `base64`)。

### 5.2 A端 环境变量

在 A端 的 `server/.env` 中添加：

```bash
# OmniParser GPU API 地址 (B端)
OMNIPARSER_URL=http://<GPU_SERVER_IP>:9800
OMNIPARSER_TIMEOUT=30        # GPU 模式 30s 足够；CPU 模式需 360s
OMNIPARSER_RETRY=1           # 失败重试 1 次
OMNIPARSER_RETRY_DELAY=3.0   # 重试间隔 3s
```

### 5.3 A端 调用示例

#### 方式一：使用客户端类 (推荐)

```python
from server.services.omniparser_client import OmniParserClient

client = OmniParserClient(base_url="http://<GPU_IP>:9800")

# 预检
if not client.check_ready():
    raise RuntimeError("OmniParser GPU 服务未就绪")

# 解析
with open("screenshot.png", "rb") as f:
    import base64
    b64 = base64.b64encode(f.read()).decode()

result = client.parse(b64)

# 使用结果
elements = result["parsed_content_list"]
som_img_b64 = result["som_image_base64"]

for elem in elements:
    print(f"  {elem['element_id']}: {elem['text']} @ {elem['bbox']}")
```

#### 方式二：便捷函数

```python
from server.services.omniparser_client import parse_image, health_check

# 快速健康检查
health = health_check("http://<GPU_IP>:9800")
print(f"GPU: {health.get('gpu_name')}, Ready: {health.get('ready')}")

# 快速解析
result = parse_image(image_base64_string)
print(f"检测到 {result['element_count']} 个元素, 耗时 {result['latency_ms']}ms")
```

### 5.4 替换 A端 现有 OmniParser 调用

A端 当前在 `server/services/detection/omniparser.py` 中直接调用本地 `:9800`。替换步骤：

```python
# 旧代码 (直接 HTTP)
# response = requests.post(f"{OMNIPARSER_URL}/parse/", json={"base64_image": img_b64})

# 新代码 (使用 SDK)
from server.services.omniparser_client import get_client

client = get_client()  # 自动读取 OMNIPARSER_URL 环境变量
result = client.parse(img_b64)
elements = result["parsed_content_list"]
som_image = result["som_image_base64"]
```

### 5.5 预检集成

在 A端 `demo.py` 的 `/process` 和 `/inspect` 路由中：

```python
from server.services.omniparser_client import get_client

@app.post("/api/demo/process")
async def process(req: ProcessRequest):
    client = get_client()

    # preflight 检查
    preflight = client.check_preflight()
    if not preflight["ok"]:
        raise HTTPException(status_code=502, detail={
            "code": "DETECTOR_FAILED",
            "message": f"OmniParser 不可用: {preflight['message']}"
        })

    # 调用解析
    result = client.parse(req.image)
    # ... 后续意图理解、蓝图规划
```

---

## 六、C端 集成 (管理面板监控)

C端 的 Web 管理面板可调用 B端 `/probe/` 获取 GPU 实时状态展示在"健康监控"页：

```javascript
// 管理面板前端示例
fetch('http://<GPU_IP>:9800/probe/')
  .then(r => r.json())
  .then(data => {
    document.getElementById('gpu-name').textContent = data.gpu.name;
    document.getElementById('vram-usage').textContent =
      `${data.gpu.vram_allocated_gb} / ${data.gpu.vram_total_gb} GB`;
  });
```

---

## 七、日常运维

### 7.1 监控命令

```bash
# 服务状态
curl -s http://127.0.0.1:9800/health | python3 -m json.tool

# GPU 使用情况
nvidia-smi

# 进程确认
ps aux | grep server.py

# 显存使用
python3 -c "
import torch
print(f'Allocated: {torch.cuda.memory_allocated(0)/1024**3:.1f} GB')
print(f'Reserved:  {torch.cuda.memory_reserved(0)/1024**3:.1f} GB')
"

# 最近推理请求
grep '解析完成' logs/server_*.log | tail -20
```

### 7.2 重启流程

```bash
cd /workspace/code/omniparser_api
./stop.sh
# 等待进程退出 (约 3s)
./start.sh
```

### 7.3 性能调优

| 场景 | 调整项 | 方法 |
|------|--------|------|
| 显存不足 (OOM) | 减小 batch_size | `server.py` 中 `get_som_labeled_img(batch_size=64)` |
| 检测过多误报 | 提高 box_threshold | `BOX_TRESHOLD=0.1` 在 `.env` 中 |
| CPU 模式 | 增加超时 | A端 设置 `OMNIPARSER_TIMEOUT=360` |
| OCR 太慢 | 切换到 EasyOCR | `.env` 中 `OMNIPARSER_OCR=easyocr` (但精度略低) |

### 7.4 常见问题

#### 服务无法启动 — `model.pt not found`

```
原因: 模型权重未下载或软链接失效
解决:
  cd /workspace/code/OmniParser/weights
  ls -l  # 确认 icon_detect/ 和 icon_caption_florence/ 存在
  # 若不存在，参考 GPU环境交接文档 第3节重新建立软链接
```

#### A端 调用超时

```
原因1: GPU 模式下图片过大 (4K)
  解决: A端 对截图进行缩放预处理 (max 2560px)

原因2: 网络不通
  解决: 在 A端 机器上执行 ping <GPU_IP> 和 curl <GPU_IP>:9800/health

原因3: CPU fallback (CUDA 不可用)
  解决: GPU 节点上运行 nvidia-smi，重启服务
```

#### 返回 502 DETECTOR_FAILED

```
原因: Florence-2 或 YOLO 推理异常
排查:
  1. 查看 GPU 节点日志: tail -100 logs/server_*.log
  2. 检查显存: nvidia-smi
  3. 运行: python /workspace/code/OmniParser/test_complete.py 验证本地推理
```

---

## 八、安全注意事项

| 项目 | 建议 |
|------|------|
| **网络隔离** | 仅开放 9800 端口给校园网内 A端 IP，不对外暴露 |
| **认证** | Demo 阶段无认证；生产环境建议加 API Key 或 mTLS |
| **速率限制** | 当前无限制；建议加 nginx rate-limiting (单 IP 10 req/min) |
| **Base64 大小** | 限制 50MB (4K 截图约 8MB) |
| **日志脱敏** | 不记录用户截图内容到日志 |

---

## 九、文件清单

```
code/omniparser_api/
├── server.py              # 主服务程序 (FastAPI)
├── client.py              # A端 客户端 SDK
├── start.sh               # 一键启动脚本
├── stop.sh                # 停止脚本
├── test_api.sh            # 连通性测试
├── omniparser.service     # systemd 服务文件
├── requirements.txt       # Python 依赖 (严格锁定版本)
├── .env.example           # 环境变量模板
├── .env                   # 环境变量 (实际使用)
└── logs/                  # 运行日志目录
    └── server_*.log
```

---

## 十、启动顺序（全系统）

HAJIMI 完整启动顺序：

```
① B端 OmniParser GPU API (:9800)
      │
      ├── 加载 YOLO + Florence-2 + PaddleOCR 到 GPU (~15s)
      │
      ▼
② A端 后端 (:8000 或 :8010)
      │
      ├── 启动时轮询 B端 /health (延迟 12s, 间隔 4s, 最多 6 次)
      │
      ▼
③ C端 集成 (与 A端 同进程)
```

**B端 启动命令**：
```bash
cd /workspace/code/omniparser_api
./start.sh
# 看到 "✅ 服务已就绪!" 后 → A端 可以启动
```

---

*文档生成日期：2026-07-02*  
*适用环境：学校 GPU 实训平台 (A800 80GB)*  
*维护：B端*
