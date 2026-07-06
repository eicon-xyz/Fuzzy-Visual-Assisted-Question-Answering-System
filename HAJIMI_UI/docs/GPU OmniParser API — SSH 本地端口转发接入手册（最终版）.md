# GPU OmniParser API — SSH 本地端口转发接入手册（最终版）

> **适用对象**：需要从本地 PC（Windows/macOS/Linux）通过 SSH 隧道安全访问校园网 GPU 服务器上的 OmniParser API 的开发者。
>
> **核心方案**：SSH 本地端口转发（`-L`），将 GPU 服务器上的 `127.0.0.1:9800` 映射到本地 `127.0.0.1:9800`，实现安全、加密的远程调用。

---

## 1. 前置条件

| 项目 | 说明 |
|------|------|
| **网络** | 本地 PC 已连接校园网或学校 VPN，能 `ping 10.246.2.7` |
| **SSH 工具** | Windows 10/11 内置 OpenSSH（或 MobaXterm / PuTTY）；macOS/Linux 自带 `ssh` |
| **GPU 服务器** | OmniParser API 已在容器内启动并监听 `127.0.0.1:9800` |
| **认证信息** | 见下表（以 Group 2 为例） |

### 认证信息（Group 2）

| 项目 | 值 |
|------|------|
| 宿主机 IP | `10.246.2.7` |
| SSH 端口 | `12202` |
| SSH 用户名 | `student` |
| SSH 密码 | `group2-ssh-123` |
| OmniParser API 端口 | `9800`（容器内） |
| 本地映射端口 | `9800`（可自定义） |

---

## 2. 核心原理

```
本地 PC (127.0.0.1:9800)  ◄═══════════════════════════►  GPU 容器 (127.0.0.1:9800)
                                 SSH 本地转发 (-L)
                        所有到本地 9800 的连接
                        通过 SSH 加密隧道转发到
                        远程容器的 127.0.0.1:9800
```

使用 `ssh -L` 本地端口转发，在本地监听一个端口，所有发往该端口的流量都会通过 SSH 隧道加密转发到远程服务器的指定端口。**优点**：无需在 GPU 服务器上额外开放防火墙端口（只需 SSH 端口 `12202` 可达），通信全程加密。

---

## 3. Windows 操作步骤

### 3.1 建立 SSH 隧道（前台模式，推荐调试）

打开 **PowerShell** 或 **CMD**，执行：

```powershell
ssh -L 9800:127.0.0.1:9800 student@10.246.2.7 -p 12202
```

系统提示输入密码：`group2-ssh-123`（输入时不会显示）。

**保持该终端窗口打开**，不要关闭。隧道建立后，所有到本地 `127.0.0.1:9800` 的连接都会被转发到 GPU 容器的 `127.0.0.1:9800`。

### 3.2 验证隧道是否生效

打开 **另一个新的 PowerShell / CMD** 窗口，执行：

```powershell
curl.exe -v http://127.0.0.1:9800/health
```

正常应返回：

```
HTTP/1.1 200 OK
{"status":"ok","version":"2.0.0","ready":true,"device":"cuda",...}
```

如果看到 `Connection refused`，说明隧道未建立成功，请检查 SSH 窗口是否有报错。

### 3.3 运行测试程序

在验证通过后，运行 `test_parse_local.py`（默认连接 `127.0.0.1:9800`）：

```powershell
python test_parse_local.py
# 或指定图片
python test_parse_local.py screenshot.png
```

脚本会自动调用 GPU 上的 OmniParser API 进行解析，并生成本地 SoM 标注图。

### 3.4 后台运行隧道（无需一直开着窗口）

如果不想一直保留终端窗口，可以使用 `-fN` 让 SSH 进入后台：

```powershell
ssh -fN -L 9800:127.0.0.1:9800 student@10.246.2.7 -p 12202
```

输入密码后进程即进入后台。之后可直接运行测试脚本。

**关闭后台隧道**：

```powershell
# 查找占用 9800 端口的进程 PID
netstat -ano | findstr :9800

# 记下 PID，然后终止
taskkill /PID <PID> /F
```

---

## 4. macOS / Linux 操作步骤

### 4.1 建立 SSH 隧道

打开终端，执行：

```bash
ssh -L 9800:127.0.0.1:9800 student@10.246.2.7 -p 12202
```

输入密码 `group2-ssh-123`，保持窗口打开。

### 4.2 验证隧道

打开另一个终端：

```bash
curl -s http://127.0.0.1:9800/health | python3 -m json.tool
```

正常应显示 GPU 健康 JSON。

### 4.3 后台运行

```bash
ssh -fN -L 9800:127.0.0.1:9800 student@10.246.2.7 -p 12202
```

**关闭后台隧道**：

```bash
# 查找进程
ps aux | grep "ssh.*-L.*9800"

# 终止
kill <PID>
```

---

## 5. 在项目中使用（A/B 端集成）

隧道建立后，在 A端 或 B端 的配置文件中，将 OmniParser API 地址设置为：

```bash
OMNIPARSER_URL=http://127.0.0.1:9800
```

例如：

- **A端** `server/.env`：`OMNIPARSER_URL=http://127.0.0.1:9800`
- **B端** `HAJIMI_UI/server/.env`：`OMNIPARSER_LOCAL_URL=http://127.0.0.1:9800`

**注意**：隧道必须保持运行，否则项目无法连接。

---

## 6. 自动重连（推荐生产使用）

SSH 隧道可能因网络波动断开，使用 `autossh` 自动重连。

### Windows（需 WSL 或 Git Bash）

```bash
autossh -M 0 -fN \
    -o "ServerAliveInterval=30" \
    -o "ServerAliveCountMax=3" \
    -o "ExitOnForwardFailure=yes" \
    -L 9800:127.0.0.1:9800 \
    student@10.246.2.7 -p 12202
```

### macOS / Linux

```bash
# 安装 autossh
brew install autossh   # macOS
sudo apt install autossh   # Ubuntu/Debian

# 启动
autossh -M 0 -fN \
    -o "ServerAliveInterval=30" \
    -o "ServerAliveCountMax=3" \
    -o "ExitOnForwardFailure=yes" \
    -L 9800:127.0.0.1:9800 \
    student@10.246.2.7 -p 12202
```

---

## 7. 一键启动脚本（Windows）

将以下内容保存为 `start_tunnel.bat`，双击运行：

```batch
@echo off
echo ========================================
echo  GPU OmniParser SSH 隧道启动器
echo  本地 9800 → GPU 10.246.2.7:9800
echo ========================================
ssh -L 9800:127.0.0.1:9800 student@10.246.2.7 -p 12202
pause
```

双击后输入密码即可建立隧道。

---

## 8. 故障排查

| 问题 | 可能原因 | 解决办法 |
|------|----------|----------|
| **`Connection refused`** | 隧道未建立 / 服务未启动 | 检查 SSH 窗口是否正常运行；在 GPU 容器内执行 `curl http://127.0.0.1:9800/health` 确认服务正常 |
| **`Permission denied (publickey,password)`** | 密码错误 | 确认密码为 `group2-ssh-123`，注意大小写 |
| **`ssh: connect to host 10.246.2.7 port 12202: Connection timed out`** | 网络不通 | 检查是否连接校园网或 VPN；`ping 10.246.2.7` |
| **`curl` 无输出但测试脚本成功** | Windows curl 管道问题 | 使用 `curl -v` 查看详细信息，或直接用测试脚本验证 |
| **隧道频繁断开** | 网络不稳定 | 使用 `autossh` 自动重连，或增加 `ServerAliveInterval=60` |

---

## 9. 快速参考

### 建立隧道（前台）
```bash
ssh -L 9800:127.0.0.1:9800 student@10.246.2.7 -p 12202
```

### 建立隧道（后台）
```bash
ssh -fN -L 9800:127.0.0.1:9800 student@10.246.2.7 -p 12202
```

### 验证健康检查
```bash
curl -s http://127.0.0.1:9800/health | python3 -m json.tool
```

### 运行测试程序
```bash
python test_parse_local.py
```

### 关闭后台隧道
```bash
# Windows
netstat -ano | findstr :9800
taskkill /PID <PID> /F

# macOS/Linux
ps aux | grep "ssh.*-L.*9800"
kill <PID>
```

---

## 10. 安全提示

- **不要将本文档中的密码上传至公开仓库或截图分享**。
- SSH 隧道通信全程加密，适合校园网等不可信网络环境。
- 离开电脑时建议关闭隧道窗口，防止未授权访问。
- 若长期使用，建议配置 SSH 公钥免密登录（`ssh-keygen` + `ssh-copy-id`），避免每次输入密码。

---

*文档版本：1.0（最终版）*  
*更新日期：2026-07-04*  
*适用环境：学校 GPU 实训平台 Group 2（10.246.2.7）*