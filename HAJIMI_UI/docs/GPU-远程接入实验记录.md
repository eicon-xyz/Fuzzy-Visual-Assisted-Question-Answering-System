# GPU 远程接入 — 实验记录

> **目标主机**：group2 @ `10.246.2.7`，SSH `-p 12202`  
> **本机环境**：Windows，`E:\University\greed3-2\Shixun\HAJIMI_UI`  
> **参考**：[GPU-API远程接入手册.md](GPU-API远程接入手册.md)、[校园GPU-远程启服与快速测试.md](校园GPU-远程启服与快速测试.md)

---

## 结果总表

| 阶段 | 8010 (A 端 / B 联调) | 9800 (OmniParser API) | 结论 |
|------|----------------------|------------------------|------|
| Phase 0（2026-07-04 上午，校外） | ❌ SSH 不可达 | ❌ | 非校园网阻塞 |
| Phase 0（**2026-07-04 重试，校内**） | ✅ 容器内 OK | ✅ 容器内 OK | CUDA True，同学已启服 |
| 实验1 校园网直连 | ❌ 连接被拒绝 | ❌ 连接被拒绝 | 平台未映射 8010/9800 到外网 |
| 实验2 SSH `-L` | ✅ e2e `check_health=True` | ⏸ 未单独测 `-L 9800` | **B 端主路径可用** |
| 实验3 frp | — | ⏸ 配置演练 | 待公网 VPS |

**结论（校内联调）**：用 **`ssh -L 8010`** 或 **`python scripts/b_group2_e2e_verify.py`**；不要指望直连 `10.246.2.7:8010`。容器内 **8002 + 8010 + 9800** 均已就绪。

---

## 连通重试 — 2026-07-04（校内）

### 第一轮：本机探测

| 检查 | 结果 |
|------|------|
| `ping 10.246.2.7` | ✅ 3–10ms，0% 丢失 |
| `gpu_connectivity_probe` SSH `:12202` | ✅ OK |
| 直连 `http://10.246.2.7:8010/api/demo/health` | ❌ WinError 10061 连接被拒绝 |
| 直连 `http://10.246.2.7:9800/health` | ❌ WinError 10061 连接被拒绝 |

### 第二轮：远程脚本

```text
python scripts/gpu_group2_remote.py phase0   # exit 0
  NVIDIA A800-SXM4-80GB, CUDA: True, WORKSPACE_OK

python scripts/gpu_group2_remote.py services   # exit 0，未跑 start-all（同学已启服）
  8002/probe/: {"ready":true,"device":"cuda",...}
  8010/api/demo/health: {"status":"ok","omniparser_ready":true,"detector_device":"cuda",...}
```

容器内 9800（SSH 执行）：

```json
{"status":"ok","version":"2.0.0","ready":true,"device":"cuda","gpu_name":"NVIDIA A800-SXM4-80GB",...}
```

### 第三轮：实验 1 / 2

**实验 1 — 直连**：8010、9800 从 Windows **均不可达**（平台仅暴露 SSH/Jupyter，属预期）。

**实验 2 — SSH 隧道**：

```text
python scripts/b_group2_e2e_verify.py   # exit 0
  [e2e] tunnel localhost:8010 -> 127.0.0.1:8010
  [e2e] check_health=True
  [e2e] status: A 端在线 (GPU/cuda) http://127.0.0.1:8010
  [OK] 基础联调检查通过
```

inspect/process 对 1×1 测试图 SKIP 属正常。

---

## Phase 0 — 打开主机 + GPU 服务就绪

- [x] `phase0` → `CUDA: True`
- [x] `services` → `8002/probe/` 含 `"device":"cuda"`
- [x] `services` → `8010/api/demo/health` 含 `"omniparser_ready":true`
- [x] 容器内 `curl http://127.0.0.1:9800/health` → ok

---

## 实验 1 — 方案一：校园网直连

| 目标 | 本机直连 | 结果 |
|------|----------|------|
| A 端 `:8010` | `WinError 10061` | ❌ 端口未对外映射 |
| OmniParser API `:9800` | `WinError 10061` | ❌ 同上 |

**说明**：ping 与 SSH 通，但 **8010/9800 不能直连** → 本组应使用 **实验 2 隧道**，而非方案一。

---

## 实验 2 — 方案二：SSH 本地转发（`-L`）

### 2A — B 端 `:8010`

| 步骤 | 结果 |
|------|------|
| `python scripts/b_group2_e2e_verify.py`（paramiko 隧道） | ✅ |
| 手动 `ssh -L 8010:127.0.0.1:8010 student@10.246.2.7 -p 12202` | 推荐日常；隧道窗口需保持 |

**UI 联调**：

```bat
rem 终端 1
ssh -L 8010:127.0.0.1:8010 student@10.246.2.7 -p 12202

rem 终端 2 — 不要 HAJIMI_MOCK_ONLY
python main.py
```

内网 API = `http://127.0.0.1:8010`

### 2B — A 端/直调 `:9800`

| 步骤 | 结果 |
|------|------|
| 容器内 9800 | ✅ 已部署且 cuda |
| 本机直连 9800 | ❌ 需 `ssh -L 9800:127.0.0.1:9800 ...` 后再 curl `127.0.0.1:9800` |

---

## 实验 3 — frp

⏸ 配置模板见 [docs/frp/](frp/)；待公网 VPS 后补测。

---

## 本地 GPU API 模式（Bat 一键）

架构：**本地 A 端 :8010** + **SSH `-L 9800`** → GPU `omniparser_api`（非内网 API 8010 模式）。

| 脚本 | 作用 |
|------|------|
| `scripts/start_tunnel_9800.bat` | 终端1：隧道 |
| `scripts/start_gpu_api_demo.bat` | 终端2：配置 + A 端 + UI |
| `scripts/run_test_parse_local.bat` | 仅测 API（根目录 `test_parse_local.py`） |
| `scripts/setup_gpu_api_mode.py` | 写 `OMNIPARSER_URL=http://127.0.0.1:9800` |
| `gpu_group2_remote.py start-9800` | 远程启 GPU API |

详见 [OmniParser GPU API 本地开发接入指南（SSH 隧道版最终最终版）.md](OmniParser%20GPU%20API%20本地开发接入指南（SSH%20隧道版最终最终版）.md) §9。

---

## 工具与命令速查

| 脚本 | 用途 |
|------|------|
| `scripts/gpu_connectivity_probe.py` | ping 级替代：SSH + 直连 8010/9800 |
| `scripts/check_gpu_api_tunnel.py` | 隧道 9800 health |
| `scripts/start_gpu_api_demo.bat` | GPU API 完整 UI 模式 |
| `scripts/gpu_group2_remote.py services` | 容器内 health |
| `scripts/b_group2_e2e_verify.py` | 内网 8010 隧道 + verify |

```bat
cd /d E:\University\greed3-2\Shixun\HAJIMI_UI
python scripts\gpu_connectivity_probe.py
python scripts\gpu_group2_remote.py services
python scripts\b_group2_e2e_verify.py
```

---

## 备注

- 默认 SSH 密码 `group2-ssh-123`；与 `HAJIMI_GPU_SSH_PASSWORD` 未设时脚本行为一致。
- 实验 2 用 **`-L`**，勿用 `-R`。
- 早先校外失败原因为未进 `10.246.x.x` 网段；校内 ping/SSH 通即可联调。
