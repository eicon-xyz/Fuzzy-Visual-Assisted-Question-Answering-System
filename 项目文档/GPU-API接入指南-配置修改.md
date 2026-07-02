# GPU OmniParser API 接入指南 — A端 / B端 配置修改

> **适用对象**：A端 (后端/AI核心) 和 B端 (桌面应用) 开发者
> **前提**：GPU 服务器上 OmniParser API 已启动并可通过校园网访问
> **原则**：本文只列出需要修改的配置文件和具体位置，**不在本文中执行任何改动**。

---

## 零、确认 GPU 服务可达

在修改任何代码之前，先在本地 PC 上测试连通性：

```bash
# 替换 <GPU_SERVER_IP> 为实际 IP (如 10.0.0.5)
curl http://<GPU_SERVER_IP>:9800/health

# 预期输出:
# {"status":"ok","version":"2.0.0","ready":true,"device":"cuda","cuda_available":true,...}
```

---

## 一、A端 配置修改 (server/server/config.py)

A端 有两套代码，互为备份。核心修改在 `server/server/config.py`。

### 修改位置

**文件**: `server/server/config.py`  
**找到第 30-33 行**:

```python
# Local OmniParser V2 API (deployed at D:\ominprester)
OMNIPARSER_URL: str = os.getenv(
    "OMNIPARSER_URL", "http://127.0.0.1:9800"
)
OMNIPARSER_TIMEOUT: int = int(os.getenv("OMNIPARSER_TIMEOUT", "30"))
```

### 修改方案 (推荐：环境变量)

在 `server/.env` 文件中添加 (如果不存在则创建):

```bash
# GPU 服务器地址
OMNIPARSER_URL=http://<GPU_SERVER_IP>:9800

# GPU 模式 30s 足够；CPU fallback 改为 360
OMNIPARSER_TIMEOUT=30
```

### 注意

当前 A端的 `omniparser_client.py` 发送的请求格式是:

```python
# server/server/services/omniparser_client.py 第 79-81 行
url = f"{_OMNIPARSER_URL}/parse"     # ← 没有尾部斜杠
payload = {"image": payload_base64}  # ← 字段名是 image
```

而 B端的 `ui_detector.py` 发送的是:

```python
# HAJIMI_UI/server/services/ui_detector.py 第 126 行
resp = client.post(
    f"{base_url}/parse/",            # ← 有尾部斜杠
    json={"base64_image": b64},      # ← 字段名是 base64_image
)
```

**当前 GPU API server.py 已兼容两种格式** — 同时接受 `image` 和 `base64_image`，路径 `/parse` 和 `/parse/` 均可。

---

## 二、B端 配置修改 (HAJIMI_UI/server/config.py)

B端 desktop 应用中嵌入了一个 A 端服务器，它通过 `ui_detector.py` 的 `_detect_local_omniparser()` 直接调用 OmniParser。

### 修改位置

**文件**: `HAJIMI_UI/server/config.py`  
**找到第 52-57 行**:

```python
OMNIPARSER_LOCAL_URL: str = os.getenv(
    "OMNIPARSER_LOCAL_URL", "http://127.0.0.1:8000"
)
OMNIPARSER_LOCAL_TIMEOUT: int = int(
    os.getenv("OMNIPARSER_LOCAL_TIMEOUT", "360")
)
```

### 修改方案 (推荐：环境变量)

在 `HAJIMI_UI/server/.env.example` (或 `.env`) 中添加:

```bash
# GPU 服务器地址 (注意: 这是 OmniParser API，不是 A端的 8000 端口!)
OMNIPARSER_LOCAL_URL=http://<GPU_SERVER_IP>:9800

# 超时: GPU 模式 60s 足够
OMNIPARSER_LOCAL_TIMEOUT=60

# 不缩放图片 (A800 80GB 显存可以处理大图)
OMNIPARSER_LOCAL_MAX_SIDE=3200
```

**关键**: 默认值是 `http://127.0.0.1:8000`，这是指向本地 A端 而非 OmniParser！必须改为 `http://<GPU_IP>:9800`。

---

## 三、客户端测试 (本地 PC)

在本地开发机上:

```bash
# 1. 安装依赖 (仅截图需要)
pip install pillow mss

# 2. 下载测试脚本 (从 GPU 服务器复制或自己创建)
# test_parse_local.py 已在 /workspace/code/omniparser_api/ 中

# 3. 运行测试
export OMNIPARSER_URL=http://<GPU_SERVER_IP>:9800
python test_parse_local.py screenshot.png

# 4. 自动截屏测试
python test_parse_local.py
```

预期输出:
```
  OmniParser GPU API — 本地 PC 端测试
  GPU 服务器: http://10.0.0.5:9800

[1/4] 检查 GPU 服务器连接...
  状态:     ok
  就绪:     True
  GPU:      NVIDIA A800-SXM4-80GB
  CUDA:     True
  OCR引擎:  paddle

[2/4] 准备图片...
  截取当前屏幕...
  Base64 大小: 8192 KB

[3/4] 调用 GPU API (http://10.0.0.5:9800/parse/) ...
  ✅ 解析完成
  网络往返: 4.2s | 服务端推理: 3100ms (3.1s)

[4/4] 处理结果...
  图片尺寸: {'width': 2560, 'height': 1600}
  检测元素: 47 个
  后端:     local_omniparser_paddle
  设备:     cuda
  ...
```

---

## 四、服务器端测试 (GPU 节点)

在 GPU 服务器上:

```bash
cd /workspace/code/omniparser_api
source .venv/bin/activate
python test_parse_gpu.py /workspace/code/OmniParser/test2.jpg
```

---

## 五、请求/响应兼容性说明

GPU API (`server.py`) 响应同时包含**两组字段**以兼容两种客户端:

| 字段名 | 消费者 | 说明 |
|--------|--------|------|
| `parsed_content_list` | B端 HAJIMI_UI embedded server | UI 元素列表 |
| `som_image_base64` | B端 HAJIMI_UI embedded server | SoM 标注图 |
| `elements` | A端 `server/server/services/omniparser_client.py` | 同上 (复制) |
| `annotated_image` | A端 `server/server/services/omniparser_client.py` | 同上 (复制) |
| `width` / `height` | A端 | 图片分辨率 |

请求也同时接受 `image` 和 `base64_image` 两种字段名。

---

## 六、目录对照

```
GPU 服务器 (/workspace)                    本地 PC (Fuzzy-Visual-Assisted-Question-Answering-System/)
──────────────────────────────────────     ──────────────────────────────────────────────────────────
code/omniparser_api/server.py              ← HTTP 调用 →
code/omniparser_api/client.py              → 复制到 server/server/services/omniparser_client.py  (可选替换)
code/omniparser_api/test_parse_gpu.py     (GPU 节点自测用)
code/omniparser_api/test_parse_local.py   → 复制到本地任意目录 (PC 测试用)
项目文档/B端-OmniParser-GPU-API部署文档.md  (本文档)
                                           server/server/config.py  ← 改 OMNIPARSER_URL
                                           HAJIMI_UI/server/config.py ← 改 OMNIPARSER_LOCAL_URL
```
