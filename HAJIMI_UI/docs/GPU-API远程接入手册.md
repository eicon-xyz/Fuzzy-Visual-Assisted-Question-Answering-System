# GPU OmniParser API 远程接入手册

> **适用场景**：本地 Windows/Mac/Linux PC 需要访问校园网 GPU 服务器上的 OmniParser API (:9800)
> **前置条件**：GPU 服务器上 OmniParser API 已启动 (`./start.sh`，验证 `curl http://127.0.0.1:9800/health`)
> **关联**：[校园GPU-远程启服与快速测试.md](校园GPU-远程启服与快速测试.md)（B 端联调 A 端 `:8010`）、[GPU-API接入指南-配置修改.md](GPU-API接入指南-配置修改.md)

---

## 端口对照（勿混用）

| 服务 | 端口 | 健康检查 | 典型角色 | 远程接入文档 |
|------|------|----------|----------|--------------|
| **OmniParser GPU API**（`omniparser_api`） | **9800** | `GET /health` | A 端 `OMNIPARSER_URL`；直调测试 | **本文** |
| **OmniParser 原生**（`omniparserserver`） | **8002** | `GET /probe/` | 容器内 A 端调用；绑定 `127.0.0.1` 时**不可校园网直连** | [校园GPU-远程启服与快速测试.md](校园GPU-远程启服与快速测试.md) |
| **A 端 FastAPI** | **8010** | `GET /api/demo/health` | B 端 UI 联调入口 | [校园GPU-B端联调清单_v2.md](校园GPU-B端联调清单_v2.md) |

- **本文三种方案**针对 **:9800**（本地 PC → GPU OmniParser API）。
- **B 端跑 UI** 通常隧道 **:8010**（`ssh -L 8010:127.0.0.1:8010`），见校园 GPU 文档；OmniParser 由 GPU 上 A 端经 `:8002` 间接调用。

---

## 目录

1. [方案一：校园网直连](#方案一校园网直连)
2. [方案二：SSH 本地转发隧道](#方案二ssh-本地转发隧道)
3. [方案三：frp 内网穿透](#方案三frp-内网穿透)
4. [方案对比速查表](#方案对比速查表)
5. [验证与排障](#验证与排障)

---

## 前置步骤：获取 GPU 服务器地址

在 GPU 服务器上执行：

```bash
# 查看所有 IP 地址
hostname -I

# 或者只查看主要 IP
ip route get 1.2.3.4 | awk '{print $7}'

# 示例输出: 10.0.0.5  172.17.0.1
# 校园网通常用 10.x.x.x 或 192.168.x.x
```

记下 IP（例如 `10.0.0.5`），后续会用到。

---

## 方案一：校园网直连

### 适用条件

- ✅ 本地 PC 和 GPU 服务器在**同一个校园网**内
- ✅ GPU 服务器防火墙允许 9800 端口入站
- ✅ 网络延迟 < 5ms（局域网内）

### 步骤

#### 1. GPU 服务器端：确认监听地址

```bash
# 确认服务监听 0.0.0.0（接受外部连接）
curl -s http://127.0.0.1:9800/health | python3 -m json.tool

# 如果不是 0.0.0.0，重启指定 host:
# cd /workspace/code/omniparser_api
# python server.py --host 0.0.0.0 --port 9800
```

#### 2. GPU 服务器端：放行防火墙 (如有)

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 9800/tcp
sudo ufw status

# CentOS/RHEL (firewalld)
sudo firewall-cmd --add-port=9800/tcp --permanent
sudo firewall-cmd --reload

# Docker 容器 (通常不需要)
# 如果是在 docker run 时启动的容器，确保已映射端口: -p 9800:9800
```

#### 3. 本地 PC：测试连通性

```bash
# 替换 10.0.0.5 为实际 GPU 服务器 IP
curl -s http://10.0.0.5:9800/health | python3 -m json.tool

# 预期输出:
# {
#     "status": "ok",
#     "ready": true,
#     "gpu_name": "NVIDIA A800-SXM4-80GB",
#     ...
# }
```

如果 `curl` 输出为空或报 `Connection refused`，跳到 [排障](#验证与排障)。

#### 4. 本地 PC：使用 test_parse_local.py

```bash
# 安装截图依赖 (可选)
pip install pillow mss

# 下载 test_parse_local.py 到本地
# (从 /workspace/code/omniparser_api/test_parse_local.py 复制)

# 方式 A: 传图片文件
python test_parse_local.py --url http://10.0.0.5:9800 screenshot.png

# 方式 B: 自动截屏
python test_parse_local.py --url http://10.0.0.5:9800

# 方式 C: 环境变量
export OMNIPARSER_URL=http://10.0.0.5:9800
python test_parse_local.py screenshot.png
```

#### 5. A端 / B端 项目集成

修改对应的 `.env` 或配置文件：

```bash
# A端 (server/.env)
OMNIPARSER_URL=http://10.0.0.5:9800
OMNIPARSER_TIMEOUT=30

# B端 (HAJIMI_UI/server/.env)
OMNIPARSER_LOCAL_URL=http://10.0.0.5:9800
OMNIPARSER_LOCAL_TIMEOUT=60
```

---

## 方案二：SSH 本地转发隧道

### 适用条件

- ✅ 你能 SSH 登录 GPU 服务器
- ✅ 适用于跨网段、防火墙不开放 9800、或仅需临时测试
- ⚠️ 不需要 GPU 服务器额外开放 9800（仅需 SSH，如 group2 的 `:12202`）

### 原理

```
本地 PC                            GPU 服务器
───────     SSH 连接      ──────────
:9800  ───────────────────► :9800 (API 服务)
        SSH -L 9800:127.0.0.1:9800
```

SSH **本地转发** (`-L`)：在**本地 PC** 监听 9800，流量经 SSH 转发到 GPU 容器内的 `127.0.0.1:9800`。本地访问 `http://127.0.0.1:9800/health` 即访问远程 OmniParser API。

> **勿与 `-R` 混淆**：`-R` 是在**远程**监听、转发到本地，用于把本机服务暴露给 GPU；**本地访问 GPU API 请用 `-L`**。B 端联调 A 端 `:8010` 同样用 `-L`（见 [校园GPU-远程启服与快速测试.md](校园GPU-远程启服与快速测试.md)）。

### 步骤

#### 1. 建立隧道 (前台模式，方便调试)

```bash
# 在本地 PC 上执行（group2 示例加 -p 12202）
ssh -L 9800:127.0.0.1:9800 student@10.0.0.5

# 参数说明:
#   -L 9800             本地 PC 监听 9800
#   127.0.0.1:9800      转发到 GPU 服务器上的 127.0.0.1:9800
#   student@10.0.0.5    GPU 服务器登录
```

#### 2. 验证隧道

打开另一个终端：

```bash
# 在本地 PC 执行
curl -s http://127.0.0.1:9800/health | python3 -m json.tool

# 应该看到 GPU 服务器的健康检查结果
```

#### 3. 后台长期运行

```bash
# Linux/Mac
ssh -fN -L 9800:127.0.0.1:9800 student@10.0.0.5

# 参数说明:
#   -f  后台运行
#   -N  不执行远程命令 (仅转发)

# 查看是否在运行
ps aux | grep "ssh.*-L.*9800"

# 终止
kill $(pgrep -f "ssh.*-L.*9800")
```

#### 4. Windows (PowerShell)

```powershell
# Windows 10+ 自带 OpenSSH（group2: -p 12202）
ssh -L 9800:127.0.0.1:9800 student@10.0.0.5

# 或使用 PuTTY:
# Connection → SSH → Tunnels
#   Source port: 9800
#   Destination: 127.0.0.1:9800
#   选择 "Local"（本地转发）
#   点击 "Add"
```

#### 5. 自动重连 (可选)

隧道断开后自动重连：

```bash
# Linux/Mac — 使用 autossh
sudo apt install autossh

autossh -M 0 -fN \
    -o "ServerAliveInterval=30" \
    -o "ServerAliveCountMax=3" \
    -o "ExitOnForwardFailure=yes" \
    -L 9800:127.0.0.1:9800 \
    student@10.0.0.5

# 添加到 systemd 服务 (Linux)
cat << 'EOF' | sudo tee /etc/systemd/system/omniparser-tunnel.service
[Unit]
Description=SSH Tunnel to GPU OmniParser
After=network.target

[Service]
Type=simple
User=$USER
ExecStart=/usr/bin/autossh -M 0 -N \
    -o "ServerAliveInterval=30" \
    -o "ServerAliveCountMax=3" \
    -o "ExitOnForwardFailure=yes" \
    -L 9800:127.0.0.1:9800 \
    student@10.0.0.5
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now omniparser-tunnel
```

#### 6. 本地集成

```bash
# 隧道建立后，本地访问就是:
OMNIPARSER_URL=http://127.0.0.1:9800

# 所有工具正常使用:
python test_parse_local.py --url http://127.0.0.1:9800 screenshot.png
```

---

## 方案三：frp 内网穿透

### 适用条件

- ✅ 长期生产使用
- ✅ 需要公网访问（非校园网环境也能调）
- ✅ 需要 Dashboard 监控隧道状态
- ⚠️ 需要一台有公网 IP 的中转服务器

### 原理

```
本地 PC                   公网服务器               GPU 服务器
───────                  ──────────              ──────────
curl frp.xxx.com:9800 → frps (:7000)  ←─────── frpc → :9800
                         (frp server)           (frp client)
```

frp 由两部分组成：
- **frps**（server）：部署在公网服务器，负责接收外部请求
- **frpc**（client）：部署在 GPU 服务器，负责把本地服务暴露出去

### 步骤

#### 1. 公网服务器上部署 frps

```bash
# 下载 frp (以 0.61.0 为例)
cd /tmp
wget https://github.com/fatedier/frp/releases/download/v0.61.0/frp_0.61.0_linux_amd64.tar.gz
tar xzf frp_0.61.0_linux_amd64.tar.gz
cd frp_0.61.0_linux_amd64

# 编辑 frps.toml
cat > frps.toml << 'EOF'
bindPort = 7000

# Dashboard (可选)
webServer.port = 7500
webServer.addr = "0.0.0.0"
webServer.user = "admin"
webServer.password = "your_password_here"

# Token 认证
auth.token = "your_secret_token_here"
EOF

# 启动
./frps -c frps.toml &

# 放行防火墙
sudo ufw allow 7000/tcp
sudo ufw allow 9800/tcp
sudo ufw allow 7500/tcp   # Dashboard
```

#### 2. GPU 服务器上部署 frpc

```bash
# 下载 frp
cd /tmp
wget https://github.com/fatedier/frp/releases/download/v0.61.0/frp_0.61.0_linux_amd64.tar.gz
tar xzf frp_0.61.0_linux_amd64.tar.gz
cd frp_0.61.0_linux_amd64

# 编辑 frpc.toml
cat > frpc.toml << 'EOF'
serverAddr = "<公网服务器IP>"
serverPort = 7000
auth.token = "your_secret_token_here"

[[proxies]]
name = "omniparser"
type = "tcp"
localIP = "127.0.0.1"
localPort = 9800
remotePort = 9800
EOF

# 启动
./frpc -c frpc.toml &

# 持久化: 添加到 systemd
cat << 'EOF' | sudo tee /etc/systemd/system/frpc.service
[Unit]
Description=frp client for OmniParser
After=network.target

[Service]
Type=simple
ExecStart=/tmp/frp_0.61.0_linux_amd64/frpc -c /tmp/frp_0.61.0_linux_amd64/frpc.toml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now frpc
```

#### 3. 本地 PC 使用

```bash
# 通过公网服务器访问
OMNIPARSER_URL=http://<公网服务器IP>:9800

curl -s http://<公网服务器IP>:9800/health
python test_parse_local.py --url http://<公网服务器IP>:9800 screenshot.png
```

#### 4. Dashboard 监控

浏览器打开 `http://<公网服务器IP>:7500`，可以看到：
- 隧道连接状态
- 实时流量
- 在线/离线状态

---

## 方案对比速查表

| 维度 | 直连 | SSH 本地转发 | frp 内网穿透 |
|------|------|-------------|-------------|
| **复杂度** | ⭐ (最低) | ⭐⭐ | ⭐⭐⭐ |
| **需要公网服务器** | ❌ | ❌ | ✅ 必须 |
| **需要 GPU 端开端口** | ✅ (9800) | ❌ (仅 SSH 22) | ❌ (仅 frps 7000) |
| **适用网络** | 同局域网 | 任意（能 SSH 即可） | 任意 |
| **延迟** | < 5ms | + 5-10ms | + 10-50ms |
| **稳定性** | 高 | 中（需 autossh） | 高 |
| **安全性** | 依赖防火墙 | SSH 加密 | Token 认证 |
| **带宽** | 直连 (最高) | 受 SSH 限制 | 受公网带宽限制 |
| **推荐场景** | 日常开发 | 临时测试/VPN | 生产部署 |
| **维护成本** | 无 | 低 | 中 |

### 选择建议

```
你能直接 ping 通 GPU 服务器 IP？
  ├─ 是 → 方案一 (直连) ← 最推荐
  └─ 否
      ├─ 能 SSH 登录 GPU 服务器？
      │   └─ 是 → 方案二 (SSH 本地转发 `-L`) ← 快速临时方案
      └─ 需要长期生产使用？
          └─ 方案三 (frp) ← 最稳定
```

---

## 验证与排障

### 连通性诊断脚本

在**本地 PC** 上运行：

```bash
#!/bin/bash
# save as: check_connectivity.sh
GPU_IP="${1:-10.0.0.5}"
GPU_PORT="${2:-9800}"

echo "=== OmniParser 连通性诊断 ==="
echo "目标: ${GPU_IP}:${GPU_PORT}"
echo ""

# 1. ping
echo "[1/4] ping 测试..."
ping -c 3 -W 3 "$GPU_IP" && echo "  ✅ 可达" || echo "  ❌ 不可达 (可能不在同一网络)"

# 2. TCP 端口
echo "[2/4] TCP 端口测试..."
timeout 5 bash -c "echo > /dev/tcp/${GPU_IP}/${GPU_PORT}" 2>/dev/null && echo "  ✅ 端口开放" || echo "  ❌ 端口不通"

# 3. HTTP 健康检查
echo "[3/4] HTTP 健康检查..."
RESULT=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://${GPU_IP}:${GPU_PORT}/health" 2>/dev/null)
[ "$RESULT" = "200" ] && echo "  ✅ HTTP 200 — 服务正常" || echo "  ❌ HTTP $RESULT — 服务异常"

# 4. 完整响应
echo "[4/4] 响应详情..."
curl -s --max-time 5 "http://${GPU_IP}:${GPU_PORT}/health" | python3 -m json.tool 2>/dev/null || echo "  ❌ 无法获取响应"

echo ""
echo "=== 诊断完成 ==="
```

### 常见问题

#### Q1: `curl: Connection refused`

```
原因: GPU 服务未启动或未监听外部连接
解决:
  1. GPU 服务器上确认进程: ps aux | grep server.py
  2. 确认监听地址: curl 127.0.0.1:9800/health
  3. 重启指定 --host 0.0.0.0
```

#### Q2: `curl: Connection timed out`

```
原因: 防火墙拦截
解决:
  1. GPU 服务器: sudo ufw allow 9800/tcp
  2. 检查安全组规则 (云服务器)
  3. 如果无法改防火墙 → 用方案二 (SSH 隧道)
```

#### Q3: SSH 隧道建立后 `curl 127.0.0.1:9800` 没反应

```
常见原因:
  1. 误用了 -R（反向隧道）而非 -L — 本地访问 GPU 必须用 -L
  2. GPU 上 OmniParser 未启动 — 容器内 curl 127.0.0.1:9800/health
  3. SSH 禁用了转发 — GPU 上 /etc/ssh/sshd_config 需 AllowTcpForwarding yes
  4. 本地 9800 已被占用 — 换端口: ssh -L 19800:127.0.0.1:9800 ... 然后访问 :19800
```

#### Q4: SSH 隧道频繁断开

```
解决: 使用 autossh + ServerAliveInterval
  autossh -M 0 -fN \
      -o "ServerAliveInterval=30" \
      -o "ServerAliveCountMax=3" \
      -L 9800:127.0.0.1:9800 student@GPU_IP
```

#### Q5: frp 隧道建立成功但本地访问超时

```
原因: 公网服务器防火墙未开放 remotePort
解决: 公网服务器上 sudo ufw allow 9800/tcp
```

---

## 安全建议

| 措施 | 优先级 | 说明 |
|------|--------|------|
| **API Key 认证** | 🔴 高 | 当前无认证，生产建议加 Bearer Token |
| **防火墙白名单** | 🔴 高 | GPU 服务器 9800 端口仅允许 A/B 端 IP |
| **SSH Key 登录** | 🟡 中 | 禁用密码登录，仅用 SSH Key |
| **frp Token** | 🟡 中 | 设置强随机 Token |
| **HTTPS/TLS** | 🟢 低 | Demo 阶段可暂缓，生产必须 |

### 快速加 API Key (Nginx 反向代理)

```bash
# GPU 服务器上
sudo apt install nginx apache2-utils

# 生成密码文件
sudo htpasswd -c /etc/nginx/.htpasswd hajimi_api_user

# Nginx 配置
cat << 'EOF' | sudo tee /etc/nginx/sites-available/omniparser
server {
    listen 9801;
    location / {
        auth_basic "OmniParser API";
        auth_basic_user_file /etc/nginx/.htpasswd;
        proxy_pass http://127.0.0.1:9800;
        client_max_body_size 50m;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/omniparser /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 使用: curl -u hajimi_api_user:password http://GPU_IP:9801/health
```
