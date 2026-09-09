# A 端 — GPU 容器部署详细指南（group2 · v2）

> **读者**：A 端同学（在 group2 GPU 容器内部署与运维）  
> **本组**：宿主机 `10.246.2.7`，SSH `-p 12202`，用户 `student`  
> **密码 / Token**：见组内 [`校园gpu使用.md`](../../校园gpu使用.md)（B 端维护，**勿提交 Git**）  
> **部署完成后**：填写 [§8 交接表](#8-交付-b-端交接表) 私发 B 端 → B 按 [`校园GPU-B端联调清单_v2.md`](../../docs/校园GPU-B端联调清单_v2.md) 联调  
> **关联**：[OmniParser GPU 环境交接文档.md](../../docs/OmniParser%20GPU%20环境交接文档.md) · [A端-学校GPU部署与联调指南_v2.md](A端-学校GPU部署与联调指南_v2.md)

---

## 0. 交付目标

| 服务 | 端口 | 监听 | 验证 |
|------|------|------|------|
| OmniParser GPU | `8002` | `127.0.0.1` | `curl http://127.0.0.1:8002/probe/` → `device=cuda` |
| HAJIMI A FastAPI | `8010` | `0.0.0.0` | `curl http://127.0.0.1:8010/api/demo/health` |

B 端 **不装 CUDA**，只 HTTP 访问你的 `8010`（通常经 SSH 隧道 `http://127.0.0.1:8010`）。

### 0.1 本组当前状态（2026-07-01）

| 项 | 状态 |
|----|------|
| GPU / CUDA | A800 80GB，已验证 |
| OmniParser 环境 | `/workspace/code/OmniParser` + `omniparser_api/.venv` 已就绪 |
| HAJIMI 代码 | `/workspace/code/HAJIMI_UI` 已由 B 端脚本上传 |
| 服务 | 可用 `gpu_group2_container_services.sh` 启停 |
| 网络方案 | **B — SSH 隧道**（B 端建立） |

若服务 DOWN，优先执行 [§7 日常运维](#7-日常运维)。

### 0.2 B 端可代你执行的远程部署（可选）

B 端同学在 **Windows 项目根目录** 可运行（需本组 SSH 密码，已配置在脚本默认参数）：

```powershell
python scripts/gpu_group2_deploy.py --all
```

等价于：上传 HAJIMI  tarball → `server/.venv` + `pip install` → 上传 `server/.env` → 尝试启动服务。  
**OmniParser 环境仍需在容器内按 §3 维护**（权重、4 处补丁等）。

---

## 1. 阶段 0 — 接入验证

### 1.1 登录

```bash
ssh student@10.246.2.7 -p 12202
```

或 JupyterLab `http://10.246.2.7:28888/lab` / VS Code `http://10.246.2.7:28080`（凭据见组内 md）。

### 1.2 Checklist

- [x] `nvidia-smi` → 1× GPU，驱动 ~535.x，~80GB 显存
- [x] `/workspace/code`、`/workspace/models` 可写
- [x] Python 自检：

```python
import torch
print("CUDA available:", torch.cuda.is_available())
```

期望 `True`。

- [x] Demo Key 与 B 端一致：`hajimi-demo-2026`
- [x] 网络方案：**B（SSH 隧道）**

---

## 2. 阶段 1 — 代码路径

**本组固定路径**：

| 路径 | 用途 |
|------|------|
| `/workspace/code/HAJIMI_UI` | A FastAPI（`server/`） |
| `/workspace/code/OmniParser` | OmniParser + weights 链接 |
| `/workspace/code/omniparser_api/.venv` | OmniParser 专用 venv |
| `/workspace/code/HAJIMI_UI/server/.venv` | A 端 server venv |
| `/workspace/models` | HF 权重 |

首次克隆（若目录不存在）：

```bash
mkdir -p /workspace/code /workspace/models
cd /workspace/code
git clone <仓库URL> HAJIMI_UI
git clone https://github.com/microsoft/OmniParser.git   # 或使用组内已验证版本
```

- [x] 目录已存在
- [x] `HAJIMI_UI/server/requirements.txt` 存在

---

## 3. 阶段 2 — OmniParser GPU 环境

> 完整细节：[OmniParser GPU 环境交接文档.md](../../docs/OmniParser%20GPU%20环境交接文档.md)

### 3.1 本组状态

- [x] venv：`/workspace/code/omniparser_api/.venv`
- [x] PyTorch **cu118**（禁止 cu130）
- [x] 权重 + `weights/` 软链接
- [x] **4 处源码补丁**（flash_attn、Florence-2、gradio_client、util/utils.py）
- [x] `test_complete.py` 已通过（历史）

### 3.2 启动 OmniParser（GPU）

**推荐 — 统一脚本**（nohup，无 tmux 依赖）：

```bash
bash /workspace/code/HAJIMI_UI/scripts/gpu_group2_container_services.sh start-omni
# 或同时启 A 端：
bash /workspace/code/HAJIMI_UI/scripts/gpu_group2_container_services.sh start-all
```

**手动**：

```bash
cd /workspace/code/OmniParser/omnitool/omniparserserver
source /workspace/code/omniparser_api/.venv/bin/activate
python -m omniparserserver \
  --som_model_path ../../weights/icon_detect/model.pt \
  --caption_model_name florence2 \
  --caption_model_path ../../weights/icon_caption_florence \
  --device cuda --host 127.0.0.1 --port 8002
```

验证：

```bash
curl -s http://127.0.0.1:8002/probe/ | python3 -m json.tool
# 期望: "device": "cuda", "ready": true
```

日志：`/workspace/code/HAJIMI_UI/logs/omniparser.log`

- [x] OmniParser 运行中，`device=cuda`

---

## 4. 阶段 3 — A FastAPI

### 4.1 server venv（勿与 OmniParser venv 混用）

```bash
cd /workspace/code/HAJIMI_UI/server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- [x] 已完成（可由 `gpu_group2_deploy.py` 执行）

### 4.2 server/.env（必填 `DEEPSEEK_API_KEY`）

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

DETECTOR_BACKEND=auto
OMNIPARSER_LOCAL_URL=http://127.0.0.1:8002
OMNIPARSER_LOCAL_TIMEOUT=120
OMNIPARSER_PROBE_TIMEOUT=3

HAJIMI_DEMO_KEY=hajimi-demo-2026
HAJIMI_HOST=0.0.0.0
HAJIMI_PORT=8010
REQUIRE_IMAGE=true
ALLOW_DETECTOR_FALLBACK=false
```

- [x] `.env` 已配置（含 DeepSeek Key）

### 4.3 启动 A 端

```bash
bash /workspace/code/HAJIMI_UI/scripts/gpu_group2_container_services.sh start-a
```

或：

```bash
cd /workspace/code/HAJIMI_UI
source server/.venv/bin/activate
python -m uvicorn server.main:app --host 0.0.0.0 --port 8010
```

验证：

```bash
curl -s http://127.0.0.1:8010/api/demo/health | python3 -m json.tool
```

期望 `detector_device: "cuda"`，`omniparser_ready: true`。

日志：`/workspace/code/HAJIMI_UI/logs/a_end.log`

- [x] A 端运行中

---

## 5. 阶段 4 — B 端如何访问 :8010

本组选用 **方案 B — SSH 隧道**（由 **B 端 Windows** 建立，A 端无需额外端口映射）。

B 端执行：

```powershell
ssh -L 8010:127.0.0.1:8010 student@10.246.2.7 -p 12202
```

B 端系统设置 A 端地址：`http://127.0.0.1:8010`

- [x] 方案 B 已确认
- [x] B 端浏览器 health 已成功

**方案 A（备选）**：教师映射容器 8010 → 宿主机 `{PORT}`，则 B 填 `http://10.246.2.7:{PORT}`，无需隧道。

---

## 6. 阶段 5 — 自验收 Checklist

- [x] 6.1 `nvidia-smi` 正常
- [x] 6.2 `/probe/` → `device=cuda`
- [x] 6.3 `/health` → `omniparser_ready=true`，`detector_device=cuda`
- [ ] 6.4 真实桌面 `/inspect` → `ui_elements` 非空，< 30s（建议 B 端 `main.py` 测）
- [ ] 6.5 真实桌面 `/process` → 含 `steps`（建议 B 端测）
- [x] 6.6 B 电脑 health 可达（隧道下）
- [x] 6.7 §8 交接表已同步 B 端（见 [`校园gpu使用.md`](../../校园gpu使用.md) §5）

---

## 7. 日常运维

### 7.1 重启顺序

1. OmniParser → 2. A FastAPI → 3. 通知 B 重试 health

### 7.2 常用命令

```bash
# 状态
bash /workspace/code/HAJIMI_UI/scripts/gpu_group2_container_services.sh status

# 启动全部
bash /workspace/code/HAJIMI_UI/scripts/gpu_group2_container_services.sh start-all

# 看日志
tail -f /workspace/code/HAJIMI_UI/logs/omniparser.log
tail -f /workspace/code/HAJIMI_UI/logs/a_end.log

nvidia-smi
```

B 端远程查状态（无需登录容器）：

```powershell
python scripts/gpu_group2_remote.py services
```

### 7.3 排错

| 现象 | 处理 |
|------|------|
| `502 DETECTOR_FAILED` | OmniParser 未启 / 8002 占用 / 上次 parse 未结束 |
| `omniparser_ready=false` | `start-omni`；查 `OMNIPARSER_LOCAL_URL` |
| `CUDA available: False` | 重装 PyTorch **cu118**，禁 cu130 |
| `401` | B 端 Demo Key ≠ `HAJIMI_DEMO_KEY` |
| 显存占满 | `nvidia-smi` 查 PID，避免重复起 omniparser |

### 7.4 禁止

- 无版本升级 transformers / paddleocr 大版本  
- 改 NVIDIA 驱动、`sudo rm -rf` 乱删  

---

## 8. 交付 B 端交接表

**本组已填写示例**（同步于 [`校园gpu使用.md`](../../校园gpu使用.md) §5）：

| 交接项 | 值 |
|--------|-----|
| 网络方案 | **B**（SSH 隧道） |
| **A 端 Base URL** | `http://127.0.0.1:8010` |
| Demo Key | `hajimi-demo-2026` |
| health | `detector_device=cuda`，`omniparser_ready=true` |
| inspect 耗时（GPU 真实桌面） | 约数秒～十几秒 |
| OmniParser 重启 | `bash .../gpu_group2_container_services.sh start-omni` |
| A 端重启 | `bash .../gpu_group2_container_services.sh start-a` |
| 日志 | `/workspace/code/HAJIMI_UI/logs/` |
| 已知限制 | B 须保持 SSH 隧道；容器重建后可能需重建 venv |

B 端下一步：[`校园GPU-B端联调清单_v2.md`](../../docs/校园GPU-B端联调清单_v2.md) §二。

---

## 9. 附录

### 9.1 与 B 端配置对应

| A 端 | B 端 |
|------|------|
| `HAJIMI_DEMO_KEY` | 系统设置 Demo Key → `X-Demo-Key` |
| `DETECTOR_BACKEND=auto` | health 显示 GPU/CPU |
| `:8010` 经隧道可达 | 「内网 API」模式 process/inspect |

### 9.2 首次从零安装 OmniParser（摘要）

仅当 `/workspace/code/OmniParser` 不存在或环境损坏时执行，详见交接文档：

1. `python3 -m venv /workspace/code/omniparser_api/.venv`
2. `pip install torch==2.7.1+cu118 ...`（上交镜像 cu118）
3. `hf download` OmniParser-v2.0 + Florence-2-large → `/workspace/models`
4. `weights/` 软链接 + 4 处补丁
5. `python test_complete.py`

### 9.3 API 契约

[`api-contract-demo_v2.yaml`](../../api-contract-demo_v2.yaml)

---

*文档版本：v2 · group2 · 2026-07-01*
