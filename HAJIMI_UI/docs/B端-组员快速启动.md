# B 端 — 组员快速启动

> 5 分钟内跑通 **L5 自动执行全栈**（Sidecar :8011 + B 端 UI）。
> L4 指引模式 / OmniParser / A 端 :8010 / 内网联调 / Mock 演示已整体移除，唯一模式 = L5。

## 首次推荐（clone 后在仓库根目录）

| 命令 | 说明 |
|------|------|
| **`安装全栈.bat`** | 首次安装：创建 2 个 venv（B 端 `HAJIMI_UI\.venv` + L5 Sidecar `server_A\server\.venv`），初始化 `server_A\server\.env` |
| **`启动全栈.bat`** | 一键启动：**L5 Sidecar（:8011）窗口 + B 端窗口** 两个窗口（内部 `scripts\start_release_fullstack.bat`） |
| **`启动本地.bat`** | 开发备用：同样拉起 Sidecar + B 端，日志落盘 `scripts\local_vision_run.log` |
| `stop_all.bat` | 停止服务（只停 :8011） |
| `验收.bat` | 全栈验收（`verify_all.py --require-l5`） |

安装后首次使用：在 `server_A\server\.env` 填入 `DEEPSEEK_API_KEY`（或 B 端设置页保存，自动同步并重启 Sidecar）。

**开发者/高级入口** 见 [`scripts/dev/README.txt`](../scripts/dev/README.txt)（check_deploy、固定坐标冒烟、bat 括号检查等）。`launchers/` 为兼容重定向壳。

---

## 我该用哪个脚本？（在 HAJIMI_UI 目录内）

| 你想做什么 | 命令 |
|------------|------|
| **一键全栈**（Sidecar + B 端） | 根目录 `启动全栈.bat`（或本目录 `scripts\start_release_fullstack.bat`） |
| **开发模式全栈**（日志落盘） | 根目录 `启动本地.bat` → `scripts\start_local_vision.bat` |
| **只启动 L5 Sidecar（:8011）** | `scripts\start_l5_sidecar.bat` |
| **只启动 B 端 UI**（Sidecar 已在跑，或让 UI 自动拉起） | `scripts\start_client.bat` / `scripts\start_ui.bat` / `python main.py` |
| **只检查环境/链路** | `scripts\dev\check_deploy.bat` |

**端口**：仅 `:8011` L5 Sidecar · B 端 UI = `main.py`（不再有 :8010 / :9800 / :8002）。

---

## L5 UI 执行时间线

L5 自动执行时「步骤列表」页展示：

- 上层：规划步骤（来自 `/execute` plan）
- 下层：**执行时间线**（当前步自动展开）— log、截屏缩略图、step_done/failed/blocked

操作方式：「操作指引」页输入指令 → **L5 知情确认** → 自动执行；全局快捷键 `H` 批准 / `P` 暂停 / `J` 停止。

设置 → **L5 自动执行** → 「L5 桌面标注」可开关执行过程中的桌面高亮。

工具级明细（`tool_called` / `tool_result`）需：

```bat
set HAJIMI_L5_TOOL_SSE=1
```

并重启 8011 Sidecar。详见 [`L5-SSE-契约扩展.md`](L5-SSE-契约扩展.md)。

Compact 小窗 L5 时显示一行状态 + 停止按钮。

### L5 网页自动化（browser_* 工具）

Sidecar 首次配置（`server_A\scripts\setup_server_env.bat`）**不再自动下载** Playwright 自带的 Chromium（约 150–300MB）。

L5 任务里涉及 `browser_navigate` / `browser_click` 等网页工具时，会使用本机已安装的 **Microsoft Edge 或 Google Chrome**（Playwright channel 模式，与用户日常浏览器版本独立、不会覆盖安装）。

| 情况 | 行为 |
|------|------|
| 本机有 Edge/Chrome | 自动优先 Edge → Chrome |
| 都没有或版本过旧 | 报错并提示安装/更新浏览器 |
| 必须用 bundled Chromium | 手动：`server\.venv\Scripts\python.exe -m playwright install chromium`，并可选 `set PLAYWRIGHT_CHANNEL=chromium` |

不用 L5 网页自动化、只做桌面点击/截图时，**无需**额外安装浏览器。

---

## 固定坐标点击冒烟（验证 8011 键鼠层）

**不需要** LLM / B 端 UI。用于确认 pyautogui 能否在本机动鼠标。

### Tier 1 — 直接脚本（最快）

```powershell
scripts\dev\test_click_fixed.bat
```

3 秒后鼠标移到屏幕中心 `(960, 540)` 并单击。自定义坐标：

```powershell
cd HAJIMI_UI
..\server_A\server\.venv\Scripts\python.exe scripts\test_click_fixed.py --x 80 --y 80 --delay 3
```

### Tier 2 — HTTP（验证 Sidecar 路由）

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

前置：`:8011` L5 Sidecar + B 端 UI；设置中开启 **L5 自动执行**（首次提交会弹知情确认）。

| 测试指令 | 定位方式 | 预期 |
|----------|-----------|------|
| `打开记事本` | launch_app | 记事本弹出 |
| `打开计算器` | launch_app | calc.exe 启动 |
| `双击桌面回收站` | UIA/坐标兜底 | 回收站窗口打开 |

操作注意：

1. 发指令前 **最小化 HAJIMI**，露出桌面（回收站测试必须）
2. 同意 L5 自动执行知情确认弹窗
3. 观察 8011 Sidecar 窗口：`launch_app` / `double_click` / `step_done`

---

## 手动配置（可选 / 离线场景）

一键脚本会自动配置环境。仅离线或高级场景需手动：

```powershell
git clone <仓库地址>
# 根目录
安装全栈.bat
# 或分步：
cd HAJIMI_UI && scripts\ensure_ui_env.bat          # B 端 venv（仅 PyQt5）
cd HAJIMI_UI && scripts\ensure_l5_sidecar_env.bat  # L5 Sidecar venv + 初始化 .env
cd HAJIMI_UI && python scripts\apply_l5_settings.py  # 写 OMNIPARSER_ENABLED=false / ROUTING_MODE=l5
# 编辑 server_A\server\.env 填入 DEEPSEEK_API_KEY / LLM_*
```

## 平台说明

- **官方支持**：Windows 10+（无边框、托盘、`.bat` 服务脚本、UIA 执行）
- **Linux/macOS**：可尝试 `python main.py`；`.bat` 与 Sidecar 服务管理不可用  
- 详见 [`README.md`](../README.md) §平台说明

## 常见问题

| 现象 | 处理 |
|------|------|
| 双击 bat 窗口闪退 | 用根目录 **`启动全栈.bat`** / **`启动本地.bat`**（失败会 pause）；或 `scripts\dev\check_deploy.bat` |
| `Missing server deps`（L5 窗口） | 8011 用 **server_A\server\.venv**；重跑根目录 `安装全栈.bat` 会自动配 |
| `cannot import name 'PYDANTIC_V2' from 'fastapi._compat'` / L5 venv verification failed | `cd server_A` → `scripts\repair_l5_venv.bat`；或 `set HAJIMI_RECREATE_VENV=1` 后重跑 `scripts\ensure_l5_sidecar_env.bat` |
| B 端提示后端未启动 | 看 HAJIMI-L5-Sidecar 窗口 traceback；手动 `scripts\start_l5_sidecar.bat` 后 `curl http://127.0.0.1:8011/api/demo/health` |
| pip 安装失败 | 关 Clash/V2Ray 或检查 IE 代理；重跑 `安装全栈.bat` |
| L5 提交报未配置 key | 编辑 `server_A\server\.env`（`DEEPSEEK_API_KEY` / `LLM_API_KEY`）后重启 Sidecar，或 B 端设置页保存 |
| 导航/托盘图标空白 | 缺 QtSvg：`pip install --force-reinstall PyQt5` |
| `.bat` 报「此时不应有 …」 | echo 里含未转义括号：`python HAJIMI_UI\scripts\dev\check_bat_parens.py` 定位 |

## 环境变量速查

| 变量 | 用途 |
|------|------|
| `L5_API_URL` | Sidecar 地址，默认 `http://127.0.0.1:8011` |
| `L5_API_HOST` / `L5_API_PORT` | 分拆配置 host/端口（默认 `127.0.0.1` / `8011`） |
| `HAJIMI_L5_ROOT` | L5 Sidecar 路径（默认仓库根 `server_A/`） |
| `HAJIMI_AUTO_LAUNCH_L5` | B 端启动时自动拉起 Sidecar（默认 1） |
| `HAJIMI_L5_TOOL_SSE` | `=1` 开启工具级 SSE 事件 |
| `HAJIMI_DEMO_KEY` | `X-Demo-Key` 值（默认 `hajimi-demo-2026`） |

## 相关文档

- [`README.md`](../README.md) — 项目总览  
- [`L5-SSE-契约扩展.md`](L5-SSE-契约扩展.md) — L5 SSE 事件契约  
- [`UI协作规范.md`](UI协作规范.md) — 改 UI 时的 layout/style 边界  
- 根目录 `启动指南.md` / `项目结构速查.md` — 启动链与目录说明
