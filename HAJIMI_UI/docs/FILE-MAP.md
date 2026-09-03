# HAJIMI 文件分级地图

> **用途**：根项目 AI / 新成员快速判断「该读哪、该改哪、该跑哪」。  
> **策略**：2026-09 重构已**物理删除** L4 指引模式全部文件（`HAJIMI_UI/server/`、`OmniParser/` 子模块、L4 worker/overlay/标注/Mock/联调脚本等），唯一模式 = **L5 自动执行**（后端 `../server_A` Sidecar :8011）。历史归档说明见 [`ARCHIVE-MANIFEST.md`](ARCHIVE-MANIFEST.md)。

---

## 标签说明

| 标签 | 含义 |
|------|------|
| `[PRODUCTION]` | 生产路径，改功能时优先读/改 |
| `[VERIFY]` | 验收/回归脚本，交接或 CI 必跑 |
| `[DIAGNOSE]` | 联调排障，非日常 |
| `[TEST]` | pytest 单元测试 |
| `[DEMO]` | 视觉/原型演示，非 `main.py` 入口 |
| `[LEGACY]` | 已被替代，勿作为实现参考 |
| `[DOC-PRIMARY]` | 权威文档，新 AI 必读 |
| `[DOC-REF]` | 参考文档，按需查阅 |
| `[DOC-HISTORY]` | DAY 日志，只读不改 |
| `[IGNORE]` | 打包/交接时排除 |

---

## B 端 — 生产核心 `[PRODUCTION]`

| 路径 | 说明 |
|------|------|
| `main.py` | B 端入口，PyQt5 桌面应用（启动时自动拉起/复用 L5 Sidecar） |
| `config.py` | B 端运行时配置（L5 API URL、超时、UI 参数；无 Mock/部署模式） |
| `requirements.txt` | B 端依赖：仅 PyQt5 |
| `core/defaults.py` | 默认端口/URL 单源（L5 `:8011`、Demo Key、语音默认） |
| `core/api_client.py` | B→Sidecar HTTP 客户端（L5 子集：`execute_task` / `cancel_task` / `check_l5_health` / `get_api_status_message`） |
| `core/execute_worker.py` | L5 提交 + SSE 进度工作线程 |
| `core/l5_sidecar_launcher.py` | Sidecar（:8011）确保运行/自动拉起 |
| `core/l5_query_normalize.py` | 提交前红线归一化（B 端第一层） |
| `core/sidecar_modules.py` | 从 `../server_A` 动态加载红线规则 |
| `core/user_settings.py` | 用户设置持久化、`save_settings_fragment()`（无 deployment_mode/a_end_url 字段） |
| `core/env_sync.py` | B 设置 → `server_A/server/.env`（仅 `sync_l5_sidecar_env`） |
| `core/service_manager.py` | Sidecar 进程/端口管理（仅 :8011） |
| `core/auth_session.py` | 用户登录会话 |
| `core/backend_health_worker.py` | 后台 Sidecar 健康轮询 |
| `core/bc_signals.py` | B↔C 信号总线 |
| `core/paths.py` / `core/repo_paths.py` | 仓库/Sidecar 根路径解析（`HAJIMI_L5_ROOT`） |
| `ui/main_widget.py` | 主窗口、页面导航（操作指引/步骤列表/提醒通知/系统设置）、设置保存 handler |
| `ui/app_controller.py` | 业务控制器（仅 L5：execute + SSE 事件分发） |
| `ui/chat_bubble.py` | 聊天气泡 |
| `ui/step_list.py` | 步骤列表 |
| `ui/native/medium_panel.py` | 中窗口、设置页、导航、L5 知情确认 |
| `ui/native/compact_bar.py` | 小窗口胶囊 |
| `ui/native/l5_timeline.py` / `l5_step_row.py` | L5 执行时间线渲染 |
| `ui/native/login_dialog.py` | 用户登录框 |
| `ui/native/settings_widgets.py` | 设置页控件（`ModelSettingsGroup`、`L5ExecutionGroup`） |
| `ui/native/theme_manager.py` | 主题加载与应用 |
| `ui/native/shell_appearance.py` | 配色方案、外观 dataclass |
| `ui/native/shell_renderer.py` | 壳层绘制 |
| `ui/native/theme.qss` | 全局 QSS |
| `ui/native/orange_cat/` | 橘猫主题生产实现 |
| `ui/native/luxury/` | 黑金主题生产实现 |
| `ui/native/themes/current/` | 默认蓝 / 典雅黑 QSS 包 |
| `ui/native/layout/` | 顶栏等布局逻辑 |
| `ui/native/layout_tokens.py` | 布局尺寸 token |
| `assets/themes/orange_cat/` | 橘猫静态资源 |

---

## L5 Sidecar — 生产核心 `[PRODUCTION]`（位于仓库根 `../server_A/server/`）

| 路径 | 说明 |
|------|------|
| `../server_A/server/main.py` | FastAPI 入口（:8011，挂载 demo/admin/audit/auth/flow/monitor/config） |
| `../server_A/server/config.py` | Sidecar 配置（读 `server/.env`；`OMNIPARSER_ENABLED=false`、`ROUTING_MODE=l5`） |
| `../server_A/server/.env.example` | 环境变量模板（模型 key 唯一存放处为 `.env`，打包排除） |
| `../server_A/server/routes/demo.py` | L5 Demo API（`/health`、`/execute`、`/stream/{id}` SSE、`/cancel`、`/debug/click`） |
| `../server_A/server/routes/admin.py` | Admin + `/users/*`（给 web-admin） |
| `../server_A/server/models/schemas.py` | 请求/响应模型 |
| `../server_A/server/services/planning/` | 规划（文本 LLM，供 L5） |
| `../server_A/server/services/executor/` | L5 执行引擎（engine/agent/uia_bridge/clicker/safety） |
| `../server_A/server/services/browser/` | Playwright DOM 自动化 |
| `../server_A/server/services/agent/` | 编排器（plan→evaluate→advance） |

---

## 契约与配置 `[PRODUCTION]` / `[DOC-PRIMARY]`

| 路径 | 标签 | 说明 |
|------|------|------|
| `docs/L5-SSE-契约扩展.md` | DOC-PRIMARY | L5 SSE 事件契约（step_*/task_*/tool_*） |
| `docs/api-auth.md` | DOC-PRIMARY | Demo Key / Auth 说明 |
| `docs/api-contract-demo_v2.yaml` | LEGACY + DOC | ⚠️ 仍描述旧 A 端 process/inspect 端点，**待按 L5 重写**；以 `../server_A/server/routes/demo.py` + Swagger `:8011/docs` 为准 |
| `docs/B端接口总结-对A与对C_v2.md` | DOC-REF | 历史 AB/BC 总结（L4 部分已过时） |
| `core/defaults.py` | PRODUCTION | URL/端口默认值 |

---

## 验收脚本 `[VERIFY]`

| 脚本 | 用途 | 何时跑 |
|------|------|--------|
| `scripts/verify_all.py`（`verify_all.bat` / 根目录 `验收.bat`） | 一键聚合验收；`--require-l5` 为全栈模式 | **交接/CI 必跑** |
| `scripts/verify_l5.py` | L5 Sidecar（:8011）execute/stream/cancel/health | L5 / Sidecar 改动后 |
| `scripts/verify_bc_signals.py` | B↔C 信号 | bc 改动后 |
| `scripts/verify_theme_apply.py` | 主题 QSS / 壳层 / 五方案 / 橘猫 | UI 主题改动后 |
| `scripts/verify_settings_fragment.py` | 模型/主题分块保存、解耦 | 设置页改动后 |
| `scripts/check_ui_env.py` | B 端依赖自检 | 首次 `setup.bat` 后 |

```powershell
python scripts/verify_all.py --require-l5   # 需先 启动全栈.bat
```

> 旧 `verify_l4.py` / `verify_integration.py`（B↔A:8010 process/inspect 链）已随 L4 删除。

---

## 排障脚本 `[DIAGNOSE]`

| 脚本 | 用途 |
|------|------|
| `scripts/check_deploy.py`（`check_deploy.bat`） | 环境/链路检查（L5-only） |
| `scripts/check_l5_sidecar_live.py` | Sidecar :8011 存活探测 |
| `scripts/check_port.py` | 端口占用 |
| `scripts/kill_port.py` | 释放端口（Windows） |
| `scripts/dev/check_bat_parens.py` | 扫描 .bat 括号块内未转义 `( )`（「此时不应有」崩溃防回归） |
| `scripts/test_click_fixed.py` / `test_click_http.py` | 固定坐标点击冒烟（Tier1/Tier2） |

> 旧 `diagnose_inspect.py`、`diagnose_l4_locate.py`、`check_gpu_api_tunnel.py`、`b_group2_e2e_verify.py`、`test_parse_local.py`（GPU 隧道）等已删除。

---

## 启动脚本 `[PRODUCTION]` 辅助

| 脚本 | 用途 |
|------|------|
| 根目录 `安装全栈.bat` | 首次安装：`ensure_ui_env.bat` + `ensure_l5_sidecar_env.bat` + `bootstrap_release_env.py`（2 venv + `.env` 初始化 + L5 设置） |
| 根目录 `启动全栈.bat` | 交付一键启动 → `scripts/start_release_fullstack.bat`（Sidecar :8011 + B 端两窗口） |
| 根目录 `启动本地.bat` | 开发启动 → `scripts/start_local_vision.bat`（同 L5-only，日志落盘） |
| `scripts/start_l5_sidecar.bat` | 仅启动 Sidecar（:8011，默认端口 `L5_API_PORT`） |
| `scripts/start_ui.bat` / `start_client.bat` | 仅 B 端 |
| `scripts/start_all.bat` | 转发到 release fullstack |
| `scripts/stop_all.bat`（根目录 `stop_all.bat`） | 停止服务（只停 :8011） |
| `scripts/apply_l5_settings.py` | 写 Sidecar `.env`：`OMNIPARSER_ENABLED=false` / `ROUTING_MODE=l5` / :8011 |
| `scripts/package_release.py`（根目录 `打包.bat`） | 生成交付 zip |
| `scripts/setup.bat` | B 端 venv + pip + check_ui_env |
| 根目录 `验收.bat` | 转发 `scripts/verify_all.bat --require-l5` |

> 旧 `start_server.bat`(A端:8010)、`start_omniparser.bat`、`start_l4_demo.bat`、`start_gpu_*.bat`、`start_tunnel_9800.bat`、`setup_omniparser.bat`、`setup_server_env.bat`(HAJIMI_UI 侧)、`联调启动.bat` 等已删除；Sidecar 侧安装脚本见 `../server_A/scripts/`。

---

## 单元测试 `[TEST]`

| 路径 | 说明 |
|------|------|
| `../server_A/server/tests/` | Sidecar pytest（intent, redline, blueprint, agent, api routes, …） |
| `tests/` | B 端 pytest（env_sync_l5, l5_query_normalize, l5_step_ui, auth_session, asr/voice, …） |

```powershell
python -m pytest tests/ -q
cd ../server_A/server && python -m pytest tests/ -q
```

> 旧 `HAJIMI_UI/core/tests/`（overlay_coords、assist_gather、prepare_guidance、step_advance 等 L4 用例）已随模块删除。

---

## 演示 / 原型 `[DEMO]`

| 路径 | 说明 |
|------|------|
| `ui/glass_demo.py` | 水晶玻璃视觉 demo |
| `ui/glass_demo_pro.py` | 水晶玻璃增强 demo |

---

## 遗留 / 勿参考 `[LEGACY]`

| 路径 | 生产替代 |
|------|----------|
| `ui/demo/maodiao/` | `ui/native/orange_cat/` |
| `ui/demo/luxury_*.py` | `ui/native/luxury/` |
| `ui/native/themes/variant_b/`、`variant_c/` | 历史配色变体（生产用 `current`/`variant_luxury`；迁移逻辑在 `shell_appearance.py`） |
| `docs/api-contract-demo_v2.yaml` | 待重写；L5 以 `:8011/docs` Swagger + `L5-SSE-契约扩展.md` 为准 |
| `docs/OmniParser GPU API 本地开发接入指南（SSH 隧道版…）.md`、`docs/frp/` | L4/OmniParser 历史资料，仅作考古参考 |

> 已物理删除（勿再引用）：`server/`(A端:8010)、`OmniParser/`、`ui/overlay_anno.py`、`ui/web/`、`ui/bridge_web.py`、`ui/style_preview_demo.py`、`ui/web_preview.py`、`ui/agent_panel.py`、`ui/native/suspension_dialog.py`、`ui/native/prepare_step_dialog.py`、`core/` 中 L4 worker/截图/坐标/Mock 全家桶（可从删除前的 git 历史找回）。

---

## 文档索引

### `[DOC-PRIMARY]` 必读

| 文档 | 说明 |
|------|------|
| 根 `CLAUDE.md` / `AGENTS.md` | 仓库级 AI 指南（L5 架构、启动链、约束） |
| [`AI-操作指南.md`](AI-操作指南.md) | 详细操作手册 |
| [`FILE-MAP.md`](FILE-MAP.md) | 本文档 |
| [`B端-组员快速启动.md`](B端-组员快速启动.md) | 组员 onboarding |
| [`UI协作规范.md`](UI协作规范.md) | Layout / Style 边界 |
| [`L5-SSE-契约扩展.md`](L5-SSE-契约扩展.md) | L5 SSE 事件契约 |
| [`语音集成操作手册.md`](语音集成操作手册.md) | C 端语音接入 |

> 旧 `HANDOFF.md`、`项目结构.md`、`design-spec.md`、`b-c-api-contract.md` 条目指向的文件已不存在（根目录改用 `项目结构速查.md`；`UI-SPEC.md` 仍在）。

### `[DOC-REF]` 按需

| 文档 | 说明 |
|------|------|
| [`UI-SPEC.md`](UI-SPEC.md) | UI 规格 |
| [`P1-可移植性改动与使用指南.md`](P1-可移植性改动与使用指南.md) | 可移植性历史（多模式部分已过时） |
| [`api-auth.md`](api-auth.md) | 鉴权说明 |
| [`repo外改动与边界登记.md`](repo外改动与边界登记.md) | 仓外改动登记 |

### `[DOC-HISTORY]` 日志（只读）

| 文档 | 说明 |
|------|------|
| [`CHANGELOG-B端_v2.md`](CHANGELOG-B端_v2.md) | B 端变更史 |
| `../server_A/docs/`、`../server_A/server/docs/` | A 端（Sidecar）历史文档 |
| 各类校园 GPU / OmniParser 联调手册 | L4 时代资料，仅作考古 |

---

## 打包排除 `[IGNORE]`

| 路径 | 原因 |
|------|------|
| `HAJIMI_UI/.venv/`、`../server_A/server/.venv/` | 本地重建（`安装全栈.bat`） |
| `__pycache__/`, `.pytest_cache/` | 缓存 |
| `**/.env`（保留 `.env.example`） | 密钥，勿入包 |
| `web-admin/node_modules/` | npm 重建 |
| `%LOCALAPPDATA%/HAJIMI/user_settings.json` | 用户本地设置 |

---

## 快速 grep

```powershell
# 找所有验收脚本
rg "\[VERIFY\]" scripts/

# 找生产 API 客户端（L5 子集）
rg "def execute_task\(" core/api_client.py

# 找 Sidecar 路由
rg "@router" ../server_A/server/routes/demo.py
```
