# frp 实验配置（方案三）

公网 VPS 与 GPU 容器各一份配置。详细步骤见 [GPU-API远程接入手册.md](../GPU-API远程接入手册.md) 方案三。

## 快速步骤

1. 公网 VPS 安全组放行 `7000`、`9800`、（可选）`7500`
2. VPS：`wget` frp v0.61.0 linux_amd64 → 复制 `frps.example.toml` 为 `frps.toml` 并改 token/密码 → `./frps -c frps.toml`
3. GPU 容器：`frpc.example.toml` 中 `serverAddr` 改为 VPS 公网 IP，token 与 frps 一致 → `./frpc -c frpc.toml`
4. 本机（可不在校园网）：`curl http://FRP_PUBLIC_IP:9800/health`

## 文件

| 文件 | 部署位置 |
|------|----------|
| `frps.example.toml` | 公网 VPS |
| `frpc.example.toml` | GPU 容器 `10.246.2.7` |
