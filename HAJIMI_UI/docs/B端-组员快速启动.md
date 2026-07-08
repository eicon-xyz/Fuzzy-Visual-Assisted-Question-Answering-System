# B 端 — 组员快速启动

> 5 分钟内跑通 **UI 窗口**；完整 AI 联调见下文可选步骤。

## 首次推荐（clone 后直接双击）

在仓库 **根目录** 双击：

| 命令 | 说明 |
|------|------|
| **`启动本地.bat`** | **本机 A+B** + **远程 GPU Omni**（SSH 隧道 `:9800` → 本机 8010 + 8011 + UI） |
| **`联调启动.bat`** | **本机 B** + **队友 A**（`:8010`）+ 远程 OP（由队友 A 连 GPU；B 只开 UI） |
| `stop_all.bat` | 停止 8010 / 8011 / 隧道等 |

首次运行会自动安装 8010 / 8011 / B UI 依赖（约 1–3 分钟），控制台会提示进度。

**开发者/高级入口** 见 [`scripts/dev/README.txt`](../scripts/dev/README.txt)（CPU 降级、Mock、check_deploy 等）。旧 `launchers/` 已重定向到 dev。

---

## 从仓库根目录

| 命令 | 说明 |
|------|------|
| **`启动本地.bat`** | 本机全栈 + 远程 GPU Omni（默认；GPU 未连也会 degraded 开 UI） |
| **`联调启动.bat`** | 热点/局域网：写内网 API + 远程 8010 L5 + 只开 UI |
| `stop_all.bat` | 停止服务 |
| `HAJIMI_UI\scripts\dev\check_deploy.bat` | **只检查**环境/链路 |
| `HAJIMI_UI\scripts\dev\start_local_cpu.bat` | **CPU 降级**（本机 `:8002`，无校园网时用） |

---

## 热点 / 局域网联调（连队友 8010）

队友开热点并在其电脑起 **8010**（`HAJIMI_HOST=0.0.0.0`）后，你只需：

```bat
联调启动.bat
```

脚本会：提示后端 IP（默认 `192.168.137.1`，回车即用）→ 预检 `/api/demo/health`（含 `omniparser_ready`）→ 写入内网 API + L5 路由 → 启动 UI。  
**无需**本机 8011 / Sidecar / GPU 隧道；L5 与 A 端同址 `http://<IP>:8010`。队友 A 端需自行连远程 OP（`OMNIPARSER_URL` 指向 GPU）。

仅检查连通、不写设置：

```bat
cd HAJIMI_UI
python scripts\setup_lan_client.py --no-prompt --check-only
```

指定 IP 非交互：

```bat
python scripts\setup_lan_client.py --host 192.168.137.1 --no-prompt
```

---

## 我该用哪个脚本？（在 HAJIMI_UI 目录内）

| 你想做什么 | 命令 |
|------------|------|
| **本机 A+B + 远程 GPU Omni**（默认） | 根目录 `启动本地.bat` |
| **热点 / 局域网 L5 联调**（本机 B + 队友 A） | 根目录 `联调启动.bat` |
| **CPU 降级全栈**（无校园网，`:8002`） | `scripts\dev\start_local_cpu.bat` |
| **只看 UI**（不连后端） | `set HAJIMI_MOCK_ONLY=1` + `scripts\start_client.bat` |
| **后端已开好，只开界面** | `scripts\start_client.bat` |
| **L4 专项**（8010 + UI，不等 OmniParser） | `scripts\start_l4_demo.bat` |
| **分步单服务** | `start_server` / `start_l5_sidecar` / `start_omniparser` |

**端口**：`:9800` 隧道 Omni · `:8010` L3/L4 · `:8011` L5 Sidecar · B UI = `main.py`

---

## 只检查环境（不启动 GPU）

```powershell
HAJIMI_UI\scripts\dev\check_deploy.bat
# 或 cd HAJIMI_UI && scripts\check_deploy.bat
```

自动 ensure venv 后输出 PASS/FAIL 表：8010/8011/UI venv、`.env`、`:9800` 隧道、A-end、L5。  
退出码：`0` 全 OK · `2` 环境 OK 但链路未连 · `1` 环境缺失。

---

## GPU 未连时的行为（降级启动）

- 默认 **`HAJIMI_DEGRADED_START=1`**：`启动本地.bat` 在远程 GPU / 隧道 / A-end 未就绪时 **仍会打开 UI**
- 控制台会打印 WARN 并在结束时 **pause**（不会闪退看不到报错）
- UI 状态栏显示「未连接」；**每 10s 自动重试**，连上后改为每 60s 保活
- 重试仅 localhost HTTP 探测，**几乎不耗 GPU/CPU**（未连时每次约 2–5s 超时）

### 典型耗时

| 阶段 | 典型 |
|------|------|
| 首次 ensure（pip） | 1–3 分钟/venv |
| 远程 GPU + 隧道 | 10–60s |
| A-end omniparser_ready | 隧道 OK 后 2–10s |
| UI 后台单次探测 | 0.1–5s（后台线程，不卡界面） |

严格模式（隧道失败即退出）：`set HAJIMI_DEGRADED_START=0` 后再运行。

---

## L5 UI 执行时间线

L5 自动执行时默认进入 **步骤列表** 侧栏，展示：

- 上层：规划步骤（来自 `/execute` plan）
- 下层：**执行时间线**（当前步自动展开）— log、截屏缩略图、step_done/failed

设置 → **L5 自动执行** → 「L5 桌面标注」可开关桌面高亮（Phase 1 占位，需 Sidecar 回传 bbox）。

工具级明细（`tool_called` / `tool_result`）需：

```bat
set HAJIMI_L5_TOOL_SSE=1
```

并重启 8011 Sidecar。详见 [`L5-SSE-契约扩展.md`](L5-SSE-契约扩展.md)。

Compact 小窗 L5 时显示一行状态 + 停止按钮。

---

## 固定坐标点击冒烟（验证 8011 键鼠层）

**不需要** OmniParser / LLM / B 端 UI。用于确认 pyautogui 能否在本机动鼠标。

### Tier 1 — 直接脚本（最快）

```powershell
scripts\dev\test_click_fixed.bat
```

3 秒后鼠标移到屏幕中心 `(960, 540)` 并单击。自定义坐标：

```powershell
cd HAJIMI_UI
..\..\server_A\server\.venv\Scripts\python.exe scripts\test_click_fixed.py --x 80 --y 80 --delay 3
```

### Tier 2 — HTTP（验证 A 端路由）

先开 8011 Sidecar，再：

```powershell
scripts\start_l5_sidecar.bat
REM 新窗口
scripts\dev\test_click_http.bat
```

调用 `POST /api/demo/debug/click`（需 `X-Demo-Key`）。Sidecar 重启后才会加载新路由。

**预期**：命令行 `success: true`；肉眼看到鼠标移动/点击。  
**注意**：pyautogui `FAILSAFE` — 鼠标甩到屏幕左上角会中断。

---

## L5 完整流程验证（链路就绪时）

前置：`:8010` A-end + `:9800` Omni + `:8011` L5 Sidecar + B 端 UI；设置 → **L5 自动执行**。

| 测试指令 | 依赖 Omni | 预期 |
|----------|-----------|------|
| `打开记事本` | 否（launch_app） | 记事本弹出 |
| `打开计算器` | 否 | calc.exe 启动 |
| `双击桌面回收站` | **是** | 回收站窗口打开 |

操作注意：

1. 发指令前 **最小化 HAJIMI**，露出桌面（回收站测试必须）
2. 同意 L5 自动执行授权弹窗
3. 观察 8011 Sidecar 窗口：`launch_app` / `double_click` / `step_done`

---

## 1. 克隆与依赖（可选 / 开发者）

一键脚本会自动配置环境。仅离线或高级场景需手动：

```powershell
git clone <仓库地址>
cd HAJIMI_UI
scripts\setup.bat          # B 端 UI
scripts\setup_server_env.bat   # 8010 A-end
cd ..\server_A
scripts\setup_server_env.bat   # 8011 L5（与 8010 是两套独立 venv）
```

## 2. 只看 UI（推荐首次验证）

```powershell
set HAJIMI_MOCK_ONLY=1
python main.py
```

或：

```powershell
scripts\dev\start_ui.bat
```

**说明**：此模式不连接 A 端 / OmniParser，用于确认 PyQt 界面能正常显示。首条提示为灰色 system 消息「UI 演示模式」，属正常现象。

## 3. 本地联调（可选）

需要本机 OmniParser + A 端 FastAPI：

```powershell
copy server\.env.example server\.env
# 编辑 server\.env：LLM_API_KEY、OMNIPARSER_URL 等
scripts\setup_server_env.bat
scripts\dev\start_all.bat
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
2. 双击根目录 **`启动本地.bat`**（自动远程启服 + 隧道 + 本机全栈）  
3. 系统设置 → **内网 API** → A 端地址 `http://127.0.0.1:8010` → 保存  

## 平台说明

- **官方支持**：Windows 10+（无边框、托盘、`.bat` 服务脚本）
- **Linux/macOS**：可尝试 `python main.py`；`.bat` 与服务管理不可用  
- 详见 [`README.md`](../README.md) §平台说明

## 常见问题

| 现象 | 处理 |
|------|------|
| 双击 bat 窗口闪退 | 请用根目录 **`启动本地.bat`** / **`联调启动.bat`**（失败会 pause）；或 `scripts\dev\check_deploy.bat` |
| GPU 未连但想先看 UI | 直接 `启动本地.bat`（降级模式默认开启）；界面每 10s 重试 |
| `Missing server deps`（L5 窗口） | 8011 用 **server_A\server\.venv**；一键会自动配 |
| 一键脚本 `TIMEOUT: A-end not ready` | 看 `HAJIMI-A-end-GPU-API` 窗口 traceback；确认 `:9800` 隧道 OK；**重启 A-end** |
| 一键脚本卡住后无 UI | 看是否打印 `TIMEOUT`；看 `HAJIMI-B-end` 是否 PyQt5 报错；手动试 `scripts\start_client.bat` |
| pip 安装失败 | 关 Clash/V2Ray 或检查 IE 代理；重跑 `启动本地.bat` |
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
| `HAJIMI_L5_ROOT` | L5 Sidecar 路径（默认 `server_A/`，fallback `new_JIMI/HAJIMI_UI`） |

## 相关文档

- [`README.md`](../README.md) — 项目总览  
- [`P1-可移植性改动与使用指南.md`](P1-可移植性改动与使用指南.md) — P0/P1 改动详情  
- [`UI协作规范.md`](UI协作规范.md) — 改 UI 时的 layout/style 边界  
- [`项目结构.md`](项目结构.md) — 目录说明  
