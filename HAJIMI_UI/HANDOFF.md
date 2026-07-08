# HAJIMI 交接索引（根项目 AI 请先读本文）

> **仓库**：HAJIMI_UI = **B 端 PyQt5 桌面** + **内嵌 A 端 FastAPI**（`server/`）。  
> **C 端**：契约已写，代码未接入 → [`docs/b-c-api-contract.md`](docs/b-c-api-contract.md)

---

## 1. 本仓库是什么

| 端 | 路径 | 入口 |
|----|------|------|
| B 桌面 | `main.py`, `ui/`, `core/` | `python main.py` |
| A 后端 L3/L4 | `server/` | `scripts\start_server.bat` → :**8010** |
| A 后端 L5 Sidecar | `../server_A/server/` | `scripts\start_l5_sidecar.bat` → :**8011** |
| C 集成 | （根项目实现） | Qt 信号挂到 B，HTTP 调 A admin |

---

## 2. 30 秒启动

```powershell
# 仅 UI（无 A 端）
scripts\setup.bat
set HAJIMI_MOCK_ONLY=1
python main.py

# 全栈（需 server\.env + 远程 GPU Omni + server_A L5 Sidecar）
# 推荐：仓库根目录 启动本地.bat
copy server\.env.example server\.env
scripts\start_local_one_click.bat

# L4 仅 LLM（无 Omni）
scripts\start_l4_demo.bat
```

默认 A 端端口：**8010**（[`core/defaults.py`](core/defaults.py)）

---

## 3. 必读文档（按顺序）

| # | 文档 | 用途 |
|---|------|------|
| 1 | [`docs/AI-操作指南.md`](docs/AI-操作指南.md) | **详细手册**：API、env、启动矩阵、协作规范 |
| 2 | [`docs/FILE-MAP.md`](docs/FILE-MAP.md) | 文件分级 `[PRODUCTION]` / `[VERIFY]` / `[LEGACY]` |
| 3 | [`docs/ARCHIVE-MANIFEST.md`](docs/ARCHIVE-MANIFEST.md) | 勿参考项、打包忽略、归档记录 |
| 4 | [`docs/B端接口总结-对A与对C_v2.md`](docs/B端接口总结-对A与对C_v2.md) | AB/BC 契约 |
| 5 | [`docs/ABC-完整调试距离与分工清单.md`](docs/ABC-完整调试距离与分工清单.md) | **三端进度 / 谁干什么 / 离完整多远** |
| 6 | [`docs/repo外改动与边界登记.md`](docs/repo外改动与边界登记.md) | **server_A / repo 外改动登记** |
| 7 | [`docs/DAY7-工作内容_v2.md`](docs/DAY7-工作内容_v2.md) | 最新 B 端功能（双保存、五方案主题） |

---

## 4. 交接必跑验收 `[VERIFY]`

**一键验收（推荐）** — 在 `HAJIMI_UI` 目录下：

```powershell
scripts\verify_all.bat
# 或
python scripts\verify_all.py
```

全栈（A 端 :8010 + L5 Sidecar :8011 必须已启动）：

```powershell
scripts\verify_all.bat --require-a
```

也可逐项运行：

```powershell
python scripts\verify_integration.py       # 需 A 端 :8010
python scripts\verify_theme_apply.py
python scripts\verify_settings_fragment.py
python scripts\verify_bc_signals.py        # B↔C 信号桥（可选 client/）
python scripts\verify_l4.py                # canonical :8010
python scripts\verify_l5.py --require-a   # server_A Sidecar :8011 + LLM
```

**L5 自动执行**（默认指引路由）：
- **L5 Sidecar** 本机 `:8011`（`server_A/`，A 维护）；**L3/L4** 仍走 `:8010`
- B 端 `L5_API_URL` 默认 `http://127.0.0.1:8011`（开发者 env，无普通设置 UI）
- OmniParser 与 8010 **共用** `OMNIPARSER_URL`（:9800 隧道或 :8002 本地）
- pyautogui 必须在用户本机（8011 不可整包部署在远程 GPU 容器）
- Mock 模式（`HAJIMI_MOCK_ONLY=1`）不支持 L5
- 8010 上 `/execute` 等路由 **deprecated**，B 客户端不再调用
- 遗留未挂载：`ui/agent_panel.py` `[LEGACY/unused]`

**C 端集成**：默认 `HAJIMI_C_ENABLED=1`；根项目需存在 `client/` 目录。禁用：`set HAJIMI_C_ENABLED=0`。仓库根路径：`HAJIMI_REPO_ROOT`（默认 HAJIMI_UI 的上级目录）。

依赖自检：`python scripts\check_ui_env.py`

---

## 5. 勿改 / 勿参考

| 类型 | 示例 | 请看 |
|------|------|------|
| 橘猫原型 | `ui/demo/maodiao/` | `ui/native/orange_cat/` |
| 旧契约 | `docs/api-contract-demo.yaml` | `api-contract-demo_v2.yaml` |
| 早期手测 | `docs/test_*.py` | `scripts/verify_*.py` |
| 完整清单 | — | [`docs/ARCHIVE-MANIFEST.md`](docs/ARCHIVE-MANIFEST.md) |

**未物理删除任何文件**；仅文档标记。

---

## 6. 根 AI 职责边界

- **做**：配置 A URL / 部署模式、启动 GPU 隧道、挂载 C 模块、跑 verify 脚本、协调根项目 CI
- **改 B UI 前**：读 [`docs/UI协作规范.md`](docs/UI协作规范.md)（Layout vs Style 分离）
- **改设置保存逻辑时**：保持模型/主题 **双 save**（`save_settings_fragment`），勿合并为单 save
- **不做**：把 `ui/demo/` 当生产代码；修改 DAY1–6 历史日志

---

## 7. 打包到根项目

- **含**：`main.py`, `core/`, `ui/native/`, `server/`, `scripts/`, `docs/`, `assets/`, `HANDOFF.md`
- **不含**：`.venv/`, `server/.env`, `__pycache__/`, 凭证文件 — 见 ARCHIVE-MANIFEST §3

---

## 8. 一键帮助

| 需求 | 命令 / 文件 |
|------|-------------|
| 组员 onboarding | [`docs/B端-组员快速启动.md`](docs/B端-组员快速启动.md) |
| OpenAPI | [`docs/api-contract-demo_v2.yaml`](docs/api-contract-demo_v2.yaml) |
| GPU 联调 | [`docs/校园GPU-B端联调清单_v2.md`](docs/校园GPU-B端联调清单_v2.md) |
| 停止服务 | `scripts\stop_all.bat`（8010 + **8011** + Omni） |
| ABC 分工总览 | [`docs/ABC-完整调试距离与分工清单.md`](docs/ABC-完整调试距离与分工清单.md) |
| repo 外 / new_JIMI 边界 | [`docs/repo外改动与边界登记.md`](docs/repo外改动与边界登记.md) |
