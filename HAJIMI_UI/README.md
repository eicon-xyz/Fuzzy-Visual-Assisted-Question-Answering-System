# HAJIMI 智能桌面助手

> **根项目 AI 接手**：请先读 [`HANDOFF.md`](HANDOFF.md) → [`docs/AI-操作指南.md`](docs/AI-操作指南.md)

PyQt5 原生 UI + FastAPI 后端。默认运行 **Native UI**（`ui/native/`）。

## 运行模式

| 模式 | 命令 | 需要 |
|------|------|------|
| **UI 壳演示** | `set HAJIMI_MOCK_ONLY=1` 后 `python main.py` | 仅 [`requirements.txt`](requirements.txt) |
| **本地联调** | `launchers\start_all.bat` 或分步启动 A/OmniParser | `server/.env` + OmniParser 权重 |
| **校园 GPU** | 根目录 **`启动HAJIMI.bat`**（首次自动配环境） | VPN，见 [`docs/校园GPU-B端联调清单_v2.md`](docs/校园GPU-B端联调清单_v2.md) |

组员首次 clone：**双击仓库根目录 `启动HAJIMI.bat`**。开发者入口见 [`launchers/README.txt`](../launchers/README.txt)。

## 快速启动（UI 壳）

```powershell
scripts\setup.bat
set HAJIMI_MOCK_ONLY=1
python main.py
```

或使用 `scripts\start_ui.bat`（等价于 `python main.py`，自动解析 PATH 中的 Python）。

## 本地完整联调

```powershell
copy server\.env.example server\.env
# 编辑 server\.env 填入 LLM_API_KEY 等
scripts\setup_server_env.bat
launchers\start_all.bat
```

默认 A 端端口：**8010**（`HAJIMI_PORT` / `config.py`）。

## UI 观感预览

```bash
python -m ui.style_preview_demo
```

详见 [`docs/design-spec.md`](docs/design-spec.md)。

## 平台说明

- **官方支持**：Windows 10+（无边框窗口、系统托盘、服务启停脚本）
- **Linux/macOS**：可尝试 `python main.py`；`.bat` 与服务管理脚本不可用
