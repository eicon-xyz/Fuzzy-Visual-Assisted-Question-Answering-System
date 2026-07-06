# HAJIMI AI 操作指南（根项目 / 接手 AI 专用）

> **读者**：根项目 AI、负责串联 A/B/C 端的集成 AI。  
> **仓库角色**：`HAJIMI_UI` = **B 端桌面应用（PyQt5）+ 内嵌 A 端（FastAPI）**；C 端契约已文档化，**代码未接入**。  
> **快速索引**：先看根目录 [`HANDOFF.md`](../HANDOFF.md)，再看 [`FILE-MAP.md`](FILE-MAP.md)。

---

## 一、架构与 ABC 边界

```
                    HTTP (B 调用 A)
  ┌─────────┐  ──────────────────────►  ┌─────────┐
  │ B 桌面端 │  JSON + Base64 截图       │ A 后端  │
  │ main.py │  ◄──────────────────────  │ server/ │
  └────┬────┘                           └─────────┘
       │
       │ Qt 信号 / 同进程（未实现）
       ▼
  ┌─────────┐  ──HTTP admin/audit──► A
  │ C 集成  │  语音 / 审计 / 管理面板
  └─────────┘
```

| 成员 | 目录 | 职责 | 与根 AI 关系 |
|------|------|------|--------------|
| **A** | `server/` | 规划、L4/L3、OmniParser、红线 | 根 AI 部署/配置 A，保证 `/health` 可用 |
| **B** | `main.py`, `ui/`, `core/` | 桌面 UI、截图、标注、设置 | 本仓库主体；改 UI 遵守 [`UI协作规范.md`](UI协作规范.md) |
| **C** | （无代码） | ASR/TTS、审计队列、管理 Web | 根 AI 按 [`b-c-api-contract.md`](b-c-api-contract.md) 接入 B 的信号 |

**根 AI 典型职责**：在根项目中配置 A 端 URL、启动顺序、GPU 隧道；将 C 模块挂到 B 的 Qt 信号；**不要**把 B 的生产路径与 `ui/demo/` 原型混淆。

---

## 二、30 秒 / 5 分钟启动

### 2.1 仅 UI 壳（无 A 端，最快）

```powershell
cd HAJIMI_UI
scripts\setup.bat
set HAJIMI_MOCK_ONLY=1
python main.py
```

### 2.2 本地全栈（CPU OmniParser + A + B）

```powershell
copy server\.env.example server\.env
# 编辑 server\.env：至少填入 LLM_API_KEY
scripts\setup_server_env.bat
scripts\setup_omniparser.bat   # 首次需要，耗时长
scripts\start_all.bat
```

### 2.3 L4 快路径（仅 LLM + A，无 OmniParser）

```powershell
scripts\start_l4_demo.bat
# 设置页选「L4 Vision 快路径」
```

### 2.4 停止

```powershell
scripts\stop_all.bat
```

---

## 三、启动方式矩阵

| 场景 | 命令 | 端口 | 依赖 |
|------|------|------|------|
| UI Mock | `HAJIMI_MOCK_ONLY=1 python main.py` | — | B venv |
| 本地 CPU 全栈 | `scripts\start_all.bat` | A **8010**, Omni **8002** | `server/.env`, OmniParser 权重 |
| L4 快路径 | `scripts\start_l4_demo.bat` | A **8010** | LLM API |
| GPU API | 先 `:9800` 隧道，再 `start_gpu_api_demo.bat` | A **8010**, Omni **9800** | SSH/VPN |
| 内网 API | 设置页「内网 API」+ 远程 A URL | 远程 **8010** | 校园网 |
| 仅 A 端 | `scripts\start_server.bat` | **8010** | `server/.venv` |
| 仅 B 端 | `scripts\start_ui.bat` | — | 需 A 已运行或 Mock |
| Web UI 回退 | `set HAJIMI_NATIVE_UI=0` + `main.py` | — | PyQtWebEngine |

默认端口单源：[`core/defaults.py`](../core/defaults.py)。

---

## 四、接口契约

### 4.1 权威文档

| 文档 | 内容 |
|------|------|
| [`docs/api-contract-demo_v2.yaml`](api-contract-demo_v2.yaml) | B→A Demo OpenAPI |
| [`docs/B端接口总结-对A与对C_v2.md`](B端接口总结-对A与对C_v2.md) | 人类可读 AB/BC 总结 |
| [`docs/b-c-api-contract.md`](b-c-api-contract.md) | B↔C 九个 Qt 交互点 |

### 4.2 B→A Demo API（摘要）

| 方法 | 路径 | 认证 | B 端实现 |
|------|------|------|----------|
| GET | `/api/demo/health` | 无 | `core/api_client.py` → `check_health()` |
| GET | `/api/demo/health/live` | 无 | 仅 A 存活 |
| POST | `/api/demo/process` | `X-Demo-Key` | `process()` — **必填 image** |
| POST | `/api/demo/inspect` | `X-Demo-Key` | `inspect()` |
| POST | `/api/demo/step` | `X-Demo-Key` | `advance_step()` |
| POST | `/api/demo/locate` | `X-Demo-Key` | 逐步 Vision 定位 |
| POST | `/api/demo/relocate` | `X-Demo-Key` | 手动完成后重定位 |
| POST | `/api/demo/clarify` | `X-Demo-Key` | 澄清（UI 待完整接入） |
| POST | `/api/demo/report` | `X-Demo-Key` | 审计（通常由 C 代报） |

A 端路由实现：[`server/routes/demo.py`](../server/routes/demo.py)

### 4.3 B→A Admin API（给 C 端）

前缀 `/api/admin`，认证 `X-Admin-Key`（默认同 Demo Key）。  
实现：[`server/routes/admin.py`](../server/routes/admin.py)  
含 stats、failures、config deploy 等。

### 4.4 B→C（进程内，未实现）

| # | 接口 | 方向 |
|---|------|------|
| 1–2 | ASR 录音 / 转写 | B↔C 信号 |
| 3–4 | TTS 播报 / 状态 | B→C / C→B |
| 5 | 语音设置 | 共享状态 |
| 6–7 | 审计提交 / 状态 | B→C / C→B |
| 8–9 | 配置拉取 / 健康 | C→B / B→C |

B 端需在 `app_controller`、设置页麦克风等处预留挂载点（见 b-c-api-contract）。

---

## 五、环境变量

### 5.1 B 端（`config.py` / 设置页 / `%LOCALAPPDATA%\HAJIMI\user_settings.json`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `HAJIMI_API_URL` | `http://127.0.0.1:8010` | A 端地址 |
| `HAJIMI_DEMO_KEY` | `hajimi-demo-2026` | 请求头 `X-Demo-Key` |
| `HAJIMI_DEPLOYMENT_MODE` | `gpu_api` | `local` / `intranet` / `gpu_api` |
| `HAJIMI_MOCK_ONLY` | 关 | `1` = 纯 Mock，不调 A |
| `HAJIMI_MOCK_FALLBACK` | 关 | A 失败时回退 Mock |
| `HAJIMI_NATIVE_UI` | `1` | `0` = WebEngine 回退 |
| `HAJIMI_STOP_SERVICES_ON_EXIT` | `1` | 退出时停 A/Omni |
| `ROUTING_MODE` | 来自设置 | fast/balanced/precision/auto |

设置持久化：[`core/user_settings.py`](../core/user_settings.py)  
启动最早加载：[`main.py`](../main.py) → `apply_user_settings()`

### 5.2 A 端（`server/.env`，模板见 `server/.env.example`）

| 类别 | 关键变量 |
|------|----------|
| 服务 | `HAJIMI_HOST`, `HAJIMI_PORT`, `HAJIMI_DEMO_KEY` |
| LLM | `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` |
| OmniParser | `OMNIPARSER_URL`, `OMNIPARSER_LOCAL_URL`, `OMNIPARSER_GPU_URL` |
| 路由 | `ROUTING_MODE`, `PER_STEP_LOCATE`, `SCREENSHOT_MAX_SIDE` |
| L4 | `L4_PLANNER_MODEL`, `L4_LOCATOR_MODEL`, `L4_PIPELINE_ENABLED` |
| Assist | `ASSIST_ENABLED`, `ASSIST_UIA_ENABLED`, … |

B 端「模型设置」保存后，本地/GPU 模式会通过 [`core/env_sync.py`](../core/env_sync.py) 写入 `server/.env` 并重启 A 端。

### 5.3 DAY7 双保存（勿合并回单 save）

| 按钮 | Handler | 写盘 | 副作用 |
|------|---------|------|--------|
| 模型设置「保存并应用」 | `_on_model_settings_saved` | `save_settings_fragment(模型字段)` | `apply_user_settings` + 条件重启 A |
| 主题外观「保存并应用」 | `_on_appearance_settings_saved` | `save_settings_fragment(外观字段)` | `_apply_native_appearance`，**不重启 A** |
| 主题控件变更 | `_apply_appearance_preview` | **不写盘** | 仅预览 UI |

实现：[`core/user_settings.py`](../core/user_settings.py) `save_settings_fragment()`  
信号：[`ui/native/medium_panel.py`](../ui/native/medium_panel.py) `model_settings_saved` / `appearance_settings_saved`

---

## 六、重要文件（按任务）

| 任务 | 先看 |
|------|------|
| 改设置页 | `ui/native/settings_widgets.py`, `medium_panel.py`, `core/user_settings.py` |
| 改主题 / 五方案 | `shell_appearance.py`, `theme_manager.py`, `settings_widgets.py` |
| 改橘猫 | `ui/native/orange_cat/`, `image_pool.py` |
| 改 B↔A 请求 | `core/api_client.py`, `server/models/schemas.py` |
| 改 A 规划 / 路由 | `server/services/planning/router.py` |
| 改 L4 | `server/services/l4/` |
| 改标注 / 截图 | `ui/overlay_anno.py`, `core/screen_utils.py` |
| GPU 部署 | [`校园GPU-B端联调清单_v2.md`](校园GPU-B端联调清单_v2.md) |
| 接 C 端 | [`b-c-api-contract.md`](b-c-api-contract.md), `ui/app_controller.py` |

完整分级：[`FILE-MAP.md`](FILE-MAP.md)

---

## 七、验收与测试

### 7.1 交接必跑 `[VERIFY]`

```powershell
python scripts/verify_integration.py      # 需 A 端已启动
python scripts/verify_theme_apply.py        # 无头 Qt，主题链
python scripts/verify_settings_fragment.py  # 分块保存 / 解耦
python scripts/verify_l4.py                 # L4 路径（可 --smoke）
python scripts/check_ui_env.py              # 依赖自检
```

### 7.2 单元测试 `[TEST]`

```powershell
cd server
python -m pytest tests/test_intent.py tests/test_redline.py tests/test_blueprint.py
cd ..
python -m pytest core/tests/
```

### 7.3 勿当作 pytest 的遗留脚本

见 [`ARCHIVE-MANIFEST.md`](ARCHIVE-MANIFEST.md)：`docs/test_*.py` 为早期手测。

---

## 八、协作规范（摘要）

完整版：[`UI协作规范.md`](UI协作规范.md)

| 规则 | 说明 |
|------|------|
| Layout vs Style | 尺寸/树 → `layout_tokens.py`、`layout/`；颜色/QSS → `themes/`、`theme.qss` |
| `medium_panel.py` | **禁止** `setStyleSheet` |
| 主题切换 | `ThemeManager.apply()` + `user_settings.ui_theme` |
| STYLE ONLY 任务 | 只改 `.qss`，不动 layout |
| LAYOUT ONLY 任务 | 只改 layout tokens，不动 `.qss` |
| 改 A 端后 | 跑相关 `server/tests/` + `verify_integration.py` |
| 改 B UI 主题后 | 跑 `verify_theme_apply.py` |
| 改设置页后 | 跑 `verify_settings_fragment.py` |

---

## 九、文档阅读顺序

1. [`HANDOFF.md`](../HANDOFF.md)
2. **本文**（AI-操作指南）
3. [`FILE-MAP.md`](FILE-MAP.md)
4. [`ARCHIVE-MANIFEST.md`](ARCHIVE-MANIFEST.md) — 什么不要参考
5. [`B端接口总结-对A与对C_v2.md`](B端接口总结-对A与对C_v2.md)
6. [`项目结构.md`](项目结构.md) + [`P1-可移植性改动与使用指南.md`](P1-可移植性改动与使用指南.md)
7. 接 C 时：[`b-c-api-contract.md`](b-c-api-contract.md)
8. 最新功能摘要：[`DAY7-工作内容_v2.md`](DAY7-工作内容_v2.md)
9. DAY1–6：[`DOC-HISTORY`] 只读，见 FILE-MAP

GPU 文档**主读**：[`校园GPU-B端联调清单_v2.md`](校园GPU-B端联调清单_v2.md)

---

## 十、打包到根项目

### 10.1 建议包含

```
main.py, config.py, requirements*.txt
core/, ui/native/, ui/main_widget.py, ui/app_controller.py, …
server/（不含 .venv、.env）
scripts/, docs/（含本指南）
assets/
OmniParser/（或文档说明外置下载）
HANDOFF.md, README.md
```

### 10.2 建议排除 `[IGNORE]`

见 [`ARCHIVE-MANIFEST.md`](ARCHIVE-MANIFEST.md) §3：venv、cache、`.env`、凭证、`OmniParser.zip`、macOS 垃圾。

### 10.3 根项目中的定位建议

在根项目 README 中说明：

- `HAJIMI_UI/`（或实际目录名）= 桌面 B 端 + 同仓 A 端
- 根 AI 负责：环境变量、A 端部署、C 模块进程内挂载、CI 跑 verify 脚本
- 子项目 AI 负责：B Native UI / A 业务逻辑的具体 PR（遵守 UI 协作规范）

---

## 十一、常见故障

| 现象 | 排查 |
|------|------|
| B 启动报 A 不可达 | `curl http://127.0.0.1:8010/api/demo/health`；查 `HAJIMI_API_URL` |
| inspect 超时 | GPU 模式 2–5s；本地 CPU 2–4min；查 OmniParser 日志 |
| 设置保存后 A 未生效 | 模型保存才会 `sync_server_env` + 重启 A；主题保存不会 |
| 主题预览与磁盘不一致 | 预览未点「主题保存」；属预期 session 态 |
| GPU API 失败 | `scripts/check_gpu_api_tunnel.py`；`:9800` 隧道 |
| 误改 demo 代码 | 生产橘猫在 `ui/native/orange_cat/`，非 `ui/demo/maodiao/` |

---

## 十二、快速命令备忘

```powershell
# Mock
set HAJIMI_MOCK_ONLY=1 && python main.py

# 全栈
scripts\start_all.bat

# 验收四件套
python scripts\verify_integration.py
python scripts\verify_theme_apply.py
python scripts\verify_settings_fragment.py
python scripts\verify_l4.py

# 查看用户设置
python -c "from core.user_settings import load_user_settings; import json; print(json.dumps(load_user_settings(), indent=2, ensure_ascii=False))"
```

设置文件：`%LOCALAPPDATA%\HAJIMI\user_settings.json`
