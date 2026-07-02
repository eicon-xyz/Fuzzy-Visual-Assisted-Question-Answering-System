# 本组 GPU 环境记录（模板 · 可提交 Git）

> **用法**：复制本文件为项目根目录 [`校园gpu使用.md`](../校园gpu使用.md)，填入真实 Token/密码。  
> **`校园gpu使用.md` 已在 `.gitignore` 中忽略，切勿把密码提交仓库。**

---

## 0. 组内文档一览

| 文件 | 读者 | 用途 |
|------|------|------|
| `校园gpu使用.md`（根目录，私密） | 全组 | 凭据 + 进度 + 交接表 |
| **本文档** | 全组 | 无密码模板 |
| [`校园GPU-B端联调清单_v2.md`](校园GPU-B端联调清单_v2.md) | B 端 | Windows 联调手册 |
| [`../server/docs/A端-GPU容器部署详细指南-group2_v2.md`](../server/docs/A端-GPU容器部署详细指南-group2_v2.md) | A 端 | 容器部署手册 |

---

## 1. 平台接入（填写本组信息）

| 项 | 填写 |
|----|------|
| 小组 | group__（如 group2） |
| 宿主机 IP | `10.246.2.__` |
| JupyterLab | `http://{IP}:____/lab` |
| Jupyter Token | （私密，勿提交 Git） |
| VS Code Server | `http://{IP}:____` |
| VS Code 密码 | （私密） |
| SSH | `ssh student@{IP} -p ____` |
| SSH 密码 | （私密） |

**端口规律**：group1→18888/18080/12201，group2→28888/28080/12202，… 见 [`校园GPU与OmniParser环境速查_v2.md`](校园GPU与OmniParser环境速查_v2.md)。

---

## 2. HAJIMI 接口（部署后填写）

| 项 | 填写 |
|----|------|
| 网络方案 | A 端口映射 / **B SSH 隧道** / C VS Code 转发 |
| **A 端 Base URL**（B 系统设置） | 例：`http://127.0.0.1:8010` 或 `http://{IP}:{PORT}` |
| Demo Key | 默认 `hajimi-demo-2026` |
| health 是否正常 | 是 / 否 |
| detector_device | 期望 `cuda` |

### B 端隧道命令模板（方案 B）

```powershell
ssh -L 8010:127.0.0.1:8010 student@{IP} -p {SSH端口}
```

### HTTP 接口（Base = 上表 A 端地址）

| 用途 | URL |
|------|-----|
| health | `{Base}/api/demo/health` |
| process | `{Base}/api/demo/process` |
| inspect | `{Base}/api/demo/inspect` |
| relocate | `{Base}/api/demo/relocate` |

---

## 3. 容器内路径（A 端默认）

| 路径 | 用途 |
|------|------|
| `/workspace/code/HAJIMI_UI` | A FastAPI |
| `/workspace/code/OmniParser` | OmniParser |
| `/workspace/code/omniparser_api/.venv` | OmniParser venv |
| `/workspace/models` | 模型权重 |

---

## 4. 部署进度（勾选）

### A 端

- [ ] 阶段 0：nvidia-smi / CUDA OK
- [ ] 阶段 1：代码已上传
- [ ] 阶段 2：OmniParser `:8002` cuda
- [ ] 阶段 3：A FastAPI `:8010` + `.env`
- [ ] 阶段 4：B 能访问 health
- [ ] 阶段 6：自验收 + 交接表已发 B

### B 端

- [ ] 校园网/VPN
- [ ] SSH 隧道
- [ ] health OK
- [ ] 系统设置「内网 API」已保存
- [ ] 真实桌面 inspect / process 通过

---

## 5. A → B 交接表（A 填完复制到私密 md）

| 交接项 | 值 |
|--------|-----|
| 网络方案 | |
| A 端 Base URL | |
| Demo Key | |
| detector_device | |
| 重启命令 / 日志路径 | |
| 已知问题 | |

---

## 6. 自动化脚本（group2 示例）

```powershell
python scripts/gpu_group2_deploy.py --all      # B 端远程部署 A
python scripts/b_group2_intranet_setup.py       # B 端隧道 + 设置
python scripts/b_group2_e2e_verify.py           # B 端联调验收
python scripts/gpu_group2_remote.py services      # 查远程服务
```

其他小组可将脚本中的 `10.246.2.7` / `12202` 改为本组 IP/端口，或通过环境变量 `HAJIMI_GPU_HOST`、`HAJIMI_GPU_SSH_PORT` 覆盖。
