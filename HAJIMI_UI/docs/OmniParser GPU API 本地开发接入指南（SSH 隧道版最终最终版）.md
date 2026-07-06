# OmniParser GPU API 本地开发接入指南（SSH 隧道版）

> **日常开发默认路径**：只用 **GPU API（`http://127.0.0.1:9800`）**，inspect 约 **2–30 秒**。  
> **「2–4 分钟」仅指离线备用** `local` 模式 + 本机 `:8002` CPU OmniParser，**不是** GPU API 的耗时。

> **版本**：2.0  
> **适用场景**：在本地 Windows/macOS/Linux 电脑上，通过 SSH 本地端口转发安全调用校园网 GPU 容器内的 OmniParser API，并进行截图解析测试与项目集成。

---

## 1. 概述

本指南提供完整的操作链路：

1. **GPU 服务器端**：启动 OmniParser API 服务（端口 `9800`）。
2. **本地端**：建立 SSH 本地转发隧道（`-L`），将远程 `127.0.0.1:9800` 映射到本地 `127.0.0.1:9800`。
3. **本地测试**：使用 `test_parse_local.py` 脚本调用 API，解析本地截图，输出 SoM 标注图和结构化 JSON。
4. **项目集成**：在 A/B 端配置环境变量，指向本地隧道地址。

所有通信经过 SSH 加密，无需额外开放防火墙端口。

---

## 2. 前置条件

| 项目 | 说明 |
|------|------|
| **网络** | 本地 PC 已连接校园网或学校 VPN，能 `ping 10.246.2.7` |
| **SSH 客户端** | Windows 10/11 内置 OpenSSH（或 MobaXterm）；macOS/Linux 自带 `ssh` |
| **GPU 容器** | OmniParser 环境已配置，模型权重已下载（参考环境交接文档） |
| **认证信息** | 宿主机 IP、SSH 端口、用户名、密码（以 Group 2 为例） |

### 认证信息（示例）

| 项目 | 值 |
|------|------|
| 宿主机 IP | `10.246.2.7` |
| SSH 端口 | `12202` |
| SSH 用户名 | `student` |
| SSH 密码 | `group2-ssh-123` |
| OmniParser API 端口 | `9800`（容器内） |

---

## 3. GPU 服务器端：启动 OmniParser API

首先 SSH 登录到 GPU 容器（或直接在容器终端中操作）：

```bash
ssh student@10.246.2.7 -p 12202
# 输入密码
```

进入 API 项目目录并启动服务：

```bash
cd /workspace/code/omniparser_api
./start.sh
```

等待服务启动（约 10–20 秒），确认健康检查通过：

```bash
curl -s http://127.0.0.1:9800/health | python3 -m json.tool
```

预期输出：
```json
{
  "status": "ok",
  "version": "2.0.0",
  "ready": true,
  "device": "cuda",
  "gpu_name": "NVIDIA A800-SXM4-80GB",
  ...
}
```

**保持服务运行**，不要退出终端。若需要后台运行，可使用 `nohup ./start.sh &` 或 systemd。

---

## 4. 本地建立 SSH 隧道

### 4.1 前台隧道（推荐调试）

在本地打开一个终端（PowerShell / CMD / bash），执行：

```bash
ssh -L 9800:127.0.0.1:9800 student@10.246.2.7 -p 12202
```

输入密码 `group2-ssh-123`，**保持窗口打开**。该窗口会显示 SSH 登录后的 shell，不要关闭。

### 4.2 验证隧道

打开另一个终端，执行：

```bash
curl -v http://127.0.0.1:9800/health
```

应返回 HTTP 200 和 JSON 健康信息。如果连接拒绝，请检查 SSH 窗口是否有报错（如 `bind: Address already in use`），可尝试更换本地端口（如 `-L 9801:127.0.0.1:9800`，并相应修改后续地址）。

### 4.3 后台运行（可选）

若想让隧道在后台运行，使用 `-fN`：

```bash
ssh -fN -L 9800:127.0.0.1:9800 student@10.246.2.7 -p 12202
```

之后仍可通过 `curl` 验证。关闭后台隧道需找到进程 PID 并 kill（见附录）。

---

## 5. 本地测试脚本配置与运行

### 5.1 获取测试脚本

从 GPU 服务器复制 `test_parse_local.py` 到本地项目目录（或直接在本地创建）。该脚本位于 `/workspace/code/omniparser_api/test_parse_local.py`。

### 5.2 修改脚本（修复打印格式错误）

原脚本在打印元素列表时可能因 `element_id` 为 `None` 导致 `TypeError`。打开 `test_parse_local.py`，找到 `print_elements` 函数，将获取 `eid` 的部分改为：

```python
# 原代码可能为：
# eid = elem.get("element_id") or "~?"
# 改为：
eid = str(elem.get("element_id", "~?"))
```

同时确保 `etype` 和 `text` 也是字符串：

```python
etype = elem.get("element_type") or "other"
text = elem.get("text") or elem.get("content") or ""
```

完整的 `print_elements` 函数修改建议：

```python
def print_elements(elements: list):
    if not elements:
        print("  (无元素)")
        return

    types_count = {}
    for e in elements:
        t = e.get("element_type", "other")
        types_count[t] = types_count.get(t, 0) + 1

    print(f"\n{'='*70}")
    print(f"  UI 元素 (共 {len(elements)} 个)")
    print(f"{'='*70}")
    print(f"  类型分布: {json.dumps(types_count, ensure_ascii=False)}")
    print()

    print(f"  {'ID':<8} {'类型':<14} {'文字/描述':<36} {'bbox'}")
    print(f"  {'-'*8} {'-'*14} {'-'*36} {'-'*24}")

    for elem in elements:
        eid = str(elem.get("element_id", "~?"))
        etype = elem.get("element_type") or "other"
        text = elem.get("text") or elem.get("content") or ""
        text = text[:34]   # 截断显示
        bbox = elem.get("bbox", [])
        bbox_str = f"[{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}]" if len(bbox) == 4 else str(bbox)
        print(f"  {eid:<8} {etype:<14} {text:<36} {bbox_str}")
```

保存修改。

### 5.3 设置环境变量（指定 API 地址）

在运行脚本的终端中，设置环境变量 `OMNIPARSER_URL` 指向本地隧道地址：

**Windows CMD**：
```cmd
set OMNIPARSER_URL=http://127.0.0.1:9800
python test_parse_local.py
```

**Windows PowerShell**：
```powershell
$env:OMNIPARSER_URL="http://127.0.0.1:9800"
python test_parse_local.py
```

**macOS/Linux**：
```bash
export OMNIPARSER_URL=http://127.0.0.1:9800
python test_parse_local.py
```

脚本默认会使用该环境变量，如果未设置则使用代码中的硬编码默认值（我们已改为 `http://127.0.0.1:9800` 以匹配隧道）。

### 5.4 运行测试

执行脚本后，将自动截取当前屏幕（或指定图片路径），调用 GPU API 解析，输出元素列表，并生成以下文件：

- `output_som_local.png`：SoM 标注图
- `output_elements_local.json`：完整解析结果 JSON

示例输出：
```
  OmniParser GPU API — 本地 PC 端测试
  GPU 服务器: http://127.0.0.1:9800

[1/4] 检查 GPU 服务器连接...
  状态: ok
  就绪: True
  GPU: NVIDIA A800-SXM4-80GB
  CUDA: True
  OCR引擎: paddle

[2/4] 准备图片...
  截取当前屏幕...
  Base64 大小: 255 KB

[3/4] 调用 GPU API (http://127.0.0.1:9800/parse/) ...
  ✅ 解析完成
  网络往返: 1.2s | 服务端推理: 818ms

[4/4] 处理结果...
  图片尺寸: {'width': 1920, 'height': 1080}
  检测元素: 105 个
  后端: local_omniparser_paddle
  设备: cuda
```

---

## 6. 在项目中的集成

隧道建立后，A/B 端项目只需将 OmniParser API 地址配置为 `http://127.0.0.1:9800`（前提是隧道保持运行）。

- **A端（server/.env）**：
  ```bash
  OMNIPARSER_URL=http://127.0.0.1:9800
  OMNIPARSER_TIMEOUT=30
  ```

- **B端（HAJIMI_UI/server/.env）**：
  ```bash
  OMNIPARSER_LOCAL_URL=http://127.0.0.1:9800
  OMNIPARSER_LOCAL_TIMEOUT=60
  ```

之后启动 A/B 端应用时，所有解析请求都会通过 SSH 隧道发送到 GPU 容器。

---

## 7. 常见问题

| 问题 | 可能原因 | 解决办法 |
|------|----------|----------|
| **SSH 连接超时** | 未连接校园网 / IP 错误 | 检查网络，`ping 10.246.2.7` |
| **Permission denied** | 密码错误 | 确认密码 `group2-ssh-123` |
| **隧道建立后 curl 无响应** | 隧道未正确绑定或远程服务未启动 | 检查 SSH 窗口是否有 `bind: Address already in use`；远程执行 `curl 127.0.0.1:9800/health` |
| **测试脚本连接拒绝** | 环境变量未设置或端口不匹配 | 确认 `OMNIPARSER_URL` 指向 `http://127.0.0.1:9800` |
| **打印 TypeError** | 脚本未修复 | 按照第 5.2 节修改 `print_elements` |
| **隧道频繁断开** | 网络不稳定 | 使用 `autossh` 自动重连（见附录） |

---

## 8. 附录

### 8.1 一键启动隧道（Windows 批处理）

创建 `tunnel.bat`：
```batch
@echo off
ssh -L 9800:127.0.0.1:9800 student@10.246.2.7 -p 12202
pause
```

### 8.2 后台隧道关闭方法

**Windows**：
```powershell
netstat -ano | findstr :9800
taskkill /PID <PID> /F
```

**macOS/Linux**：
```bash
ps aux | grep "ssh.*-L.*9800"
kill <PID>
```

### 8.3 使用 autossh 自动重连

安装 autossh 后：
```bash
autossh -M 0 -fN -o "ServerAliveInterval=30" -o "ServerAliveCountMax=3" -L 9800:127.0.0.1:9800 student@10.246.2.7 -p 12202
```

---

## 9. 一键 Bat（HAJIMI_UI 仓库）

### 终端分工（重要）

| 位置 | 做什么 | 不需要做什么 |
|------|--------|--------------|
| **GPU 容器内** | 启动 `omniparser_api`（`:9800`） | — |
| **本机终端 1** | 只开 SSH 隧道 `start_tunnel_9800.bat` | **不要**在本机跑 `./start.sh` |
| **本机终端 2** | `start_gpu_api_demo.bat` 启 A 端 + UI | — |

GPU 上的服务（**远程容器内**，不是 Windows 终端 1）：

```bat
python scripts\gpu_group2_remote.py start-9800
```

或 SSH 进容器：`cd /workspace/code/omniparser_api && ./start.sh`

已看到 `[9800] already up` 时不必重复启动；终端 1 只需保持隧道。

### A 端接口对齐

GPU API v2：`POST /parse/` + **`base64_image`** → 响应 **`parsed_content_list`** / **`som_image_base64`**。经 SSH 隧道建议 `OMNIPARSER_TIMEOUT=120` 以上。

| 脚本 | 用途 |
|------|------|
| `scripts\start_gpu_one_click.bat` | **一键**：远程 start.sh → 隧道 → A 端 → UI（免输密码） |
| `scripts\start_tunnel_9800.bat` | 仅隧道（paramiko 自动密码，保持打开） |
| `scripts\run_test_parse_local.bat` | 检查隧道 + 运行根目录 `test_parse_local.py` |
| `scripts\start_gpu_api_demo.bat` | **终端2**：写配置 → 启本地 A 端 → 启 UI |
| `python scripts\setup_gpu_api_mode.py` | 仅写入 user_settings + `server/.env` |
| `python scripts\check_gpu_api_tunnel.py` | 检查 `http://127.0.0.1:9800/health` |
| `python scripts\gpu_group2_remote.py start-9800` | **远程**启 GPU 上 `omniparser_api` |

**最简一键（推荐）：**

```bat
scripts\start_gpu_one_click.bat
```

**分步联调：**

```bat
rem 终端 1 — 仅隧道
scripts\start_tunnel_9800.bat

rem 终端 2 — 9800 未就绪时才需要
python scripts\gpu_group2_remote.py start-9800

rem 终端 2
scripts\start_gpu_api_demo.bat
```

**不要**使用 `start_all.bat` / `start_omniparser.bat`（GPU API 模式下不需要本地 CPU OmniParser）。

**B 端 UI 设置**：系统设置 → 部署模式选 **「GPU API（推荐）」**（默认），OmniParser 地址 `http://127.0.0.1:9800`；可点 **「一键 GPU」** 自动远程启服 + 隧道 + A 端。

测试脚本 canonical 路径：仓库根目录 [`test_parse_local.py`](../test_parse_local.py)。

---

*文档完成日期：2026-07-04*  
*适用于 Group 2 环境，其他小组请替换 IP 和端口。*