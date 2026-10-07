# HAJIMI 智能桌面助手（B 端）

> **AI 接手**：先读仓库根的 [`CLAUDE.md`](../CLAUDE.md) / [`AGENTS.md`](../AGENTS.md)，或 [`docs/FILE-MAP.md`](docs/FILE-MAP.md)

PyQt5 原生 UI（`ui/native/`）。本目录是 **B 端**（桌面客户端）；唯一后端是 **L5 Sidecar**（[`../server_A/server/`](../server_A/server)，FastAPI `:8011`）。L4 指引模式、旧 A 端 (:8010)、OmniParser、Mock 演示均已移除。

## 快速开始（推荐：仓库根一键链）

在**仓库根目录**双击：

| 命令 | 说明 |
|------|------|
| **`安装全栈.bat`** | 首次：建 2 个 venv（B 端 `HAJIMI_UI/.venv` + Sidecar `server_A/server/.venv`，含 torch，约 10–30 分钟）并初始化 `server_A/server/.env` |
| **`启动全栈.bat`** | 拉起 **L5 Sidecar :8011** + **B 端** 两个窗口 |
| **`启动本地.bat`** | 同上（`scripts/start_local_vision.bat`，L5-only） |
| **`stop_all.bat`** | 停止 :8011 |
| **`验收.bat`** | `scripts/verify_all.py --require-l5` |

组员 5 分钟跑通见 [`docs/B端-组员快速启动.md`](docs/B端-组员快速启动.md)。

## 模型 Key

唯一存放处：[`../server_A/server/.env`](../server_A/server/.env)（`DEEPSEEK_API_KEY` / `LLM_*`）。
B 端设置页保存后由 `core/env_sync.py` 同步写入该文件并重启 Sidecar。
`OMNIPARSER_ENABLED=false`、`ROUTING_MODE=l5` 由 `scripts/apply_l5_settings.py` 写入。

## 单独运行 B 端

```powershell
scripts\setup.bat            :: 建 .venv 并装 PyQt5
python main.py               :: Sidecar 未起时 B 端会自动拉起 scripts\start_l5_sidecar.bat
```

或 `scripts\start_ui.bat`。环境变量（`L5_API_URL` / `L5_API_PORT` / `HAJIMI_L5_ROOT` / `HAJIMI_AUTO_LAUNCH_L5`）见根 `CLAUDE.md`。

## 使用方式（L5 自动执行）

1. 在「操作指引」页输入自然语言指令（如「打开记事本并输入你好」）。
2. 首次弹出 L5 知情确认。
3. Sidecar 规划步骤并经 UIA 绑定 / Playwright DOM 自动执行，进度在「步骤列表」时间线实时回显（SSE）。
4. 桌面快捷键：**H** 批准高风险步骤 / **J** 停止 / **P** 暂停（待 Sidecar pause API）。

红线双层：B 端 `l5_query_normalize` 归一化 + Sidecar `redline_service`/`executor/safety` 复检。

## 平台说明

- **官方支持**：Windows 10+（无边框窗口、系统托盘、UIA 执行、`.bat` 服务脚本）。
- **Linux/macOS**：可 `python main.py`（offscreen 可跑 UI/测试）；`.bat`、UIA、pyautogui 执行不可用。
