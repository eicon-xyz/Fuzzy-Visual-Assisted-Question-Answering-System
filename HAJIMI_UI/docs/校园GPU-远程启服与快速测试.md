# 校园 GPU — 远程启服与快速测试

> **读者**：Windows B 端同学  
> **本组示例**：group2 @ `10.246.2.7`，SSH `-p 12202`  
> **关联**：[校园GPU-B端联调清单_v2.md](校园GPU-B端联调清单_v2.md)、[校园gpu使用.template.md](校园gpu使用.template.md)、[GPU-API远程接入手册.md](GPU-API远程接入手册.md)（OmniParser API `:9800`）

---

## 端口对照（勿混用）

| 服务 | 端口 | 健康检查 | 谁用 | 本文是否覆盖 |
|------|------|----------|------|--------------|
| **A 端 FastAPI** | **8010** | `GET /api/demo/health` | B 端 UI 联调（**主路径**） | ✅ SSH `-L 8010` |
| **OmniParser 原生** | **8002** | `GET /probe/` | GPU 容器内 A 端调用；绑定 `127.0.0.1` | 远程启服，不直连 |
| **OmniParser GPU API** | **9800** | `GET /health` | A 端本地开发直调 OmniParser | 见 [GPU-API远程接入手册.md](GPU-API远程接入手册.md) |

- **B 端联调**：隧道 **8010** → 本机 `http://127.0.0.1:8010`；不必在 Windows 安装 OmniParser 权重。
- **A 端本地 + GPU OmniParser**：配置 `OMNIPARSER_URL` 指向 `:9800`（直连或 `ssh -L 9800`），见 GPU-API 手册。

---

## 术语：「远程开机」指什么

学校 GPU 实训平台已为每组分配 **独立 Docker 容器 + GPU**，一般**不需要**远程给物理显卡通电。

在 Windows B 端说的「远程开机」= **通过 SSH 远程启动容器内的服务**：

| 服务 | 端口 | 说明 |
|------|------|------|
| OmniParser | `8002` | GPU 视觉检测（cuda） |
| A 端 FastAPI | `8010` | B 端 HTTP 联调入口 |

B 端通过 **SSH 隧道** 访问：`ssh -L 8010:127.0.0.1:8010 ...` → 本机 `http://127.0.0.1:8010`

---

## 前置条件

- [ ] 已连接 **校园网或 VPN**（`ping 10.246.2.7` 通）
- [ ] 在项目根目录操作：`cd /d E:\University\greed3-2\Shixun\HAJIMI_UI`
- [ ] 已安装：`pip install paramiko`（或 `pip install -r requirements-dev.txt`）
- [ ] SSH 密码见根目录 `校园gpu使用.md`（gitignore），或设置环境变量：

```powershell
$env:HAJIMI_GPU_SSH_PASSWORD="你的group2密码"
# 其他小组可覆盖：
# $env:HAJIMI_GPU_HOST="10.246.2.7"
# $env:HAJIMI_GPU_SSH_PORT="12202"
```

---

## Step 0 — 实训平台「打开主机」（必做）

学校 GPU 实训平台为每组分配 **独立 Docker 容器**。在 Windows 上 `ping` / SSH 之前，须先在平台侧启动实例，否则会出现 `ping 10.246.2.7` 超时、`ssh` 连接超时、`gpu_group2_remote.py` 报 `TimeoutError`。

### 操作步骤

1. 连接 **校园网或 VPN**。
2. 浏览器打开学校 **GPU 实训 / 容器训练平台**（地址以老师/组内文档为准）。
3. 登录后找到本组实例（group2）→ 点击 **「打开主机」/「启动」/「运行」**（各平台文案可能不同）。
4. 等待容器就绪（通常 1–3 分钟；Jupyter 可用往往表示容器已起来）。

### 连通性自检（Windows）

**PowerShell：**

```powershell
ping 10.246.2.7
Test-NetConnection 10.246.2.7 -Port 12202
ssh student@10.246.2.7 -p 12202
```

**CMD（无 `Test-NetConnection` 时）：**

```bat
ping 10.246.2.7
curl http://10.246.2.7:28888/lab
```

| 结果 | 含义 |
|------|------|
| `ping` 通 + SSH 12202 通 | 可继续 Step 1 远程启服 |
| `ping` 超时 | 未连校园网，或平台未「打开主机」 |
| `ping` 通但 SSH 超时 | 容器未启动或 SSH 端口不对；确认 group2 与 `-p 12202` |
| Jupyter `28888` 可开 | 容器多半已运行，再试 SSH |

密码见根目录 `校园gpu使用.md`（gitignore）。

---

## 一、Windows 远程启服（三步）

### Step 1 — 探测容器与服务状态

```powershell
cd /d E:\University\greed3-2\Shixun\HAJIMI_UI
python scripts/gpu_group2_remote.py phase0
python scripts/gpu_group2_remote.py services
```

| 输出 | 含义 |
|------|------|
| `phase0` 超时/拒绝连接 | 未连 VPN 或容器未开 → 连校园网；仍失败联系老师 |
| `phase0` 显示 `CUDA: True` | GPU 容器正常 |
| `services` 显示 `OMNIPARSER_DOWN` / `A_END_DOWN` | 需 Step 2 启服 |
| `services` 返回 JSON | 已就绪，跳到 Step 3 |

### Step 2 — 远程启动 OmniParser + A 端

**日常启服（不上传代码）** — 任选其一：

```powershell
python scripts/gpu_group2_remote.py start-all
```

或：

```powershell
python scripts/gpu_group2_deploy.py --start-omni --start-a
```

等价于容器内：

```bash
bash /workspace/code/HAJIMI_UI/scripts/gpu_group2_container_services.sh start-all
```

启动顺序：OmniParser `:8002`（约 10–300s）→ A 端 `:8010`  
日志：`/workspace/code/HAJIMI_UI/logs/omniparser.log`、`a_end.log`

**首次部署或代码更新**才用：

```powershell
python scripts/gpu_group2_deploy.py --all
```

### Step 3 — 再次确认

```powershell
python scripts/gpu_group2_remote.py services
```

期望：

- `8002/probe/` → 含 `"device":"cuda"`
- `8010/api/demo/health` → `"status":"ok"`, `"omniparser_ready":true`

---

## 二、简单测试（约 5 分钟）

### 测试 A — 浏览器 health（需隧道）

**终端 1**（保持打开）：

```powershell
ssh -L 8010:127.0.0.1:8010 student@10.246.2.7 -p 12202
```

浏览器打开：`http://127.0.0.1:8010/api/demo/health`

期望：

```json
{
  "status": "ok",
  "detector_device": "cuda",
  "omniparser_ready": true
}
```

### 测试 B — 脚本写内网设置

```powershell
python scripts/b_group2_intranet_setup.py
```

会：建隧道 → 测 health → 写入 `%LOCALAPPDATA%\HAJIMI\user_settings.json`。

> 脚本结束后隧道会关闭；**跑 UI 时须另开终端保持 `ssh -L`**。

### 测试 C — 自动化 E2E（推荐）

```powershell
python scripts/b_group2_e2e_verify.py
```

通过标准：`check_health=True`；`verify_integration.py` health OK（1×1 测试图 SKIP 属正常）。

### 测试 D — UI 真实桌面（可选）

```powershell
# 终端 1：隧道常开
ssh -L 8010:127.0.0.1:8010 student@10.246.2.7 -p 12202

# 终端 2：不要设 HAJIMI_MOCK_ONLY
python main.py
```

系统设置 → **内网 API** → A 端 `http://127.0.0.1:8010` → 保存并应用 → 「立即检测当前屏幕」。

---

## 三、一键复制（推荐顺序）

```powershell
# Step 0: 实训平台打开 group2 主机 + 连校园网

cd /d E:\University\greed3-2\Shixun\HAJIMI_UI
pip install paramiko
$env:HAJIMI_GPU_SSH_PASSWORD="你的密码"

python scripts/gpu_group2_remote.py services
python scripts/gpu_group2_remote.py start-all
python scripts/gpu_group2_remote.py services

python scripts/b_group2_e2e_verify.py
```

---

## 四、失败速查

| 现象 | 处理 |
|------|------|
| `ping` / SSH 超时 / `TimeoutError` | **Step 0**：实训平台「打开主机」+ 连校园网/VPN；`Test-NetConnection 10.246.2.7 -Port 12202` |
| SSH 超时 / `TimeoutError`（已开主机） | 手动 `ssh student@10.246.2.7 -p 12202`；确认密码与端口 |
| `phase0` CUDA False | 容器 PyTorch 问题；见 A 端指南 §7.3 |
| `start-all` 300s 超时 | 查远程 `logs/omniparser.log`；权重路径 |
| health OK 但 UI 不可达 | 隧道窗口是否关闭；重新 `ssh -L` |
| `omniparser_ready=false` | 重跑 `start-all` 或 `--start-omni` |
| `401` | Demo Key 不一致；默认 `hajimi-demo-2026` |

---

## 五、相关脚本

| 命令 | 用途 |
|------|------|
| `gpu_group2_remote.py phase0` | GPU/CUDA/工作目录自检 |
| `gpu_group2_remote.py services` | 查远程 Omni + A health |
| `gpu_group2_remote.py start-all` | 远程启服（Omni + A） |
| `gpu_group2_deploy.py --start-omni --start-a` | 同上（deploy 子命令） |
| `b_group2_intranet_setup.py` | 隧道 + 写 user_settings |
| `b_group2_e2e_verify.py` | 隧道 + health + verify_integration |

| 文档 | 说明 |
|------|------|
| [GPU-API远程接入手册.md](GPU-API远程接入手册.md) | OmniParser `:9800` 直连 / SSH `-L` / frp |
| [校园GPU-B端联调清单_v2.md](校园GPU-B端联调清单_v2.md) | 完整 B 端联调手册 |
| [server/docs/A端-GPU容器部署详细指南-group2_v2.md](../server/docs/A端-GPU容器部署详细指南-group2_v2.md) | A 端容器部署 |
