# B 端 — 组员快速启动

> 5 分钟内跑通 **UI 窗口**；完整 AI 联调见下文可选步骤。

## 从仓库根目录（无需 cd HAJIMI_UI）

在 clone 后的 **repo 根** 直接运行：

| 命令 | 说明 |
|------|------|
| `start_gpu_one_click.bat` | 校园 GPU 一键（隧道 + 8010 + 8011 + UI） |
| `start_all.bat` | 本机 / gpu_api 全栈 |
| `start_ui.bat` | 仅 B 端 UI（后端已开好） |
| `start_mock.bat` | Mock 演示（无 OmniParser） |
| `stop_all.bat` | 停止 8010 / 8011 / OmniParser 等 |

等价于进入 `HAJIMI_UI\` 后执行同名或 `scripts\` 下脚本。

## 我该用哪个脚本？（在 HAJIMI_UI 目录内）

| 你想做什么 | 命令 |
|------------|------|
| **校园 GPU 一键**（远程启服 + 隧道 + 8010 + 8011 + UI） | `scripts\start_gpu_one_click.bat` |
| **只看 UI**（不连后端） | `set HAJIMI_MOCK_ONLY=1` + `scripts\start_client.bat` |
| **后端已开好，只开界面** | `scripts\start_client.bat` |
| **本机 CPU 全栈**（OmniParser :8002 + 8010 + 8011 + UI） | `scripts\start_all.bat`（`deployment_mode=local`） |
| **L4 专项**（8010 + UI，不等 OmniParser） | `scripts\start_l4_demo.bat` |
| **分步单服务** | `start_server` / `start_l5_sidecar` / `start_omniparser` |

**端口**：`:9800` 隧道 Omni · `:8010` L3/L4 · `:8011` L5 Sidecar · B UI = `main.py`

---

## 1. 克隆与依赖

```powershell
git clone <仓库地址>
cd HAJIMI_UI
scripts\setup.bat
```

或手动：

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/check_ui_env.py
```

若 `check_ui_env.py` 报错，按提示安装缺失包后重试。

## 2. 只看 UI（推荐首次验证）

```powershell
set HAJIMI_MOCK_ONLY=1
python main.py
```

或：

```powershell
scripts\start_ui.bat
```

**说明**：此模式不连接 A 端 / OmniParser，用于确认 PyQt 界面能正常显示。首条提示为灰色 system 消息「UI 演示模式」，属正常现象。

## 3. 本地联调（可选）

需要本机 OmniParser + A 端 FastAPI：

```powershell
copy server\.env.example server\.env
# 编辑 server\.env：LLM_API_KEY、OMNIPARSER_URL 等
scripts\setup_server_env.bat
scripts\start_all.bat
```

或分步：

| 步骤 | 命令 |
|------|------|
| OmniParser | `scripts\start_omniparser.bat`（需 `OmniParser/` 目录与权重） |
| A 端 | `scripts\start_server.bat` |
| B 端 UI | `scripts\start_client.bat` 或 `python main.py` |
| CPU 慢速演示 | `scripts\start_local_demo.bat`（`OMNI_FORCE_CPU=1` + 全套） |

默认 A 端地址：`http://127.0.0.1:8010`（OmniParser 本地默认 `:8002`）

## 4. 校园 GPU（可选）

1. 连接校园网 / VPN  
2. 建立 SSH 隧道（见 [`校园GPU-B端联调清单_v2.md`](校园GPU-B端联调清单_v2.md)）  
3. 系统设置 → **内网 API** → A 端地址 `http://127.0.0.1:8010` → 保存  

## 平台说明

- **官方支持**：Windows 10+（无边框、托盘、`.bat` 服务脚本）
- **Linux/macOS**：可尝试 `python main.py`；`.bat` 与服务管理不可用  
- 详见 [`README.md`](../README.md) §平台说明

## 常见问题

| 现象 | 处理 |
|------|------|
| 一键脚本 `TIMEOUT: A-end not ready` | 看 `HAJIMI-A-end-GPU-API` 窗口 traceback；确认 `:9800` 隧道 OK；**重启 A-end**（旧进程可能因 IE 代理导致 `omniparser_ready=false`） |
| 一键脚本卡住后无 UI | 看是否打印 `TIMEOUT`；看 `HAJIMI-B-end` 是否 PyQt5 报错；手动试 `scripts\start_client.bat` |
| `start_client.bat` 找不到 Python | 先 `activate` videorag，或 `set VIDEO_RAG_PY=...` |
| 满屏「A 端未启动」红色 | 使用 `HAJIMI_MOCK_ONLY=1` 只看 UI，或 `start_server.bat` |
| 「内网 A 端不可达」 | 检查 VPN + SSH 隧道，或改回「本地启动」 |
| OmniParser 找不到 | 设置 `OMNI_ROOT` 或运行 `scripts\setup_omniparser.bat` |
| 导航/托盘图标空白 | 缺 QtSvg：`pip install --force-reinstall PyQt5` |

## 环境变量速查

| 变量 | 用途 |
|------|------|
| `HAJIMI_MOCK_ONLY=1` | 纯 UI / Mock，不连 A 端 |
| `HAJIMI_PORT` | A 端端口，默认 8010 |
| `HAJIMI_API_URL` | B 端连接的 A 端地址 |
| `VIDEO_RAG_PY` / `OMNI_PY` | 可选，指定 Python 路径 |
| `OMNI_ROOT` | OmniParser 安装目录 |

## 相关文档

- [`README.md`](../README.md) — 项目总览  
- [`P1-可移植性改动与使用指南.md`](P1-可移植性改动与使用指南.md) — P0/P1 改动详情  
- [`UI协作规范.md`](UI协作规范.md) — 改 UI 时的 layout/style 边界  
- [`项目结构.md`](项目结构.md) — 目录说明  
