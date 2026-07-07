# HAJIMI 文件分级地图

> **用途**：根项目 AI / 新成员快速判断「该读哪、该改哪、该跑哪」。  
> **策略**：不物理删除遗留文件；归档建议见 [`ARCHIVE-MANIFEST.md`](ARCHIVE-MANIFEST.md)。

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
| `main.py` | B 端入口，PyQt5 桌面应用 |
| `config.py` | B 端运行时配置（API URL、Mock、超时） |
| `core/defaults.py` | 默认端口/URL 单源（8010 / 8002 / 9800） |
| `core/api_client.py` | B→A HTTP 客户端（process / inspect / step / relocate） |
| `core/user_settings.py` | 用户设置持久化、`save_settings_fragment()` |
| `core/env_sync.py` | B 设置 ↔ `server/.env` 同步 |
| `core/task_worker.py` | 提问 / process 工作线程 |
| `core/step_advance_worker.py` | 步骤推进 |
| `core/relocate_worker.py` | 手动重定位 |
| `core/service_manager.py` | 本地 A/Omni 启停 |
| `core/screen_utils.py` | 截图 |
| `core/mock_backend.py` | Mock 数据（`HAJIMI_MOCK_ONLY`） |
| `ui/main_widget.py` | 主窗口、模式切换、设置保存 handler |
| `ui/app_controller.py` | 业务控制器、步骤/检验/标注 |
| `ui/chat_bubble.py` | 聊天气泡 |
| `ui/step_list.py` | 步骤列表 |
| `ui/overlay_anno.py` | 全屏标注层 |
| `ui/native/medium_panel.py` | 中窗口、设置页、导航 |
| `ui/native/compact_bar.py` | 小窗口胶囊 |
| `ui/native/settings_widgets.py` | 设置页控件、`ModelSettingsGroup` |
| `ui/native/theme_manager.py` | 主题加载与应用 |
| `ui/native/shell_appearance.py` | 五配色方案、外观 dataclass |
| `ui/native/shell_renderer.py` | 壳层绘制 |
| `ui/native/theme.qss` | 全局 QSS |
| `ui/native/orange_cat/` | 橘猫主题生产实现 |
| `ui/native/luxury/` | 黑金主题生产实现 |
| `ui/native/themes/current/` | 默认蓝 / 典雅黑 QSS 包 |
| `ui/native/layout/` | 顶栏等布局逻辑 |
| `ui/native/layout_tokens.py` | 布局尺寸 token |
| `assets/themes/orange_cat/` | 橘猫静态资源 |

---

## A 端 — 生产核心 `[PRODUCTION]`

| 路径 | 说明 |
|------|------|
| `server/main.py` | FastAPI 入口 |
| `server/config.py` | A 端配置（读 `server/.env`） |
| `server/.env.example` | 环境变量模板 |
| `server/routes/demo.py` | Demo API（/health, /process, /inspect, …） |
| `server/routes/admin.py` | Admin API（给 C 端管理面板） |
| `server/models/schemas.py` | 请求/响应模型 |
| `server/services/planning/` | 路由、规划 |
| `server/services/l4/` | L4 Vision 快路径 |
| `server/services/assist/` | UIA / 混合定位辅助 |
| `server/services/perception/` | OmniParser 调用 |
| `server/services/ui_detector.py` | 检测后端 auto 链 |

---

## 契约与配置 `[PRODUCTION]` / `[DOC-PRIMARY]`

| 路径 | 标签 | 说明 |
|------|------|------|
| `docs/api-contract-demo_v2.yaml` | PRODUCTION + DOC | B→A Demo OpenAPI（权威） |
| `docs/B端接口总结-对A与对C_v2.md` | DOC-PRIMARY | AB/BC 人类可读总结 |
| `docs/b-c-api-contract.md` | DOC-PRIMARY | B↔C Qt 信号契约（C 未接入） |
| `core/defaults.py` | PRODUCTION | URL/端口默认值 |

---

## 验收脚本 `[VERIFY]`

| 脚本 | 用途 | 何时跑 |
|------|------|--------|
| `scripts/verify_integration.py` | B↔A：health / process / inspect / step | **联调交接必跑** |
| `scripts/verify_theme_apply.py` | 主题 QSS / 壳层 / 五方案 / 橘猫 | UI 主题改动后 |
| `scripts/verify_settings_fragment.py` | 模型/主题分块保存、avatar、解耦 | 设置页改动后 |
| `scripts/verify_l4.py` | L4 Vision 路径 | L4 / 路由改动后 |
| `scripts/check_ui_env.py` | B 端依赖自检 | 首次 `setup.bat` 后 |
| `scripts/verify_web_ui_fallback.bat` | WebEngine 回退（`HAJIMI_NATIVE_UI=0`） | 非 Native 路径时 |

```powershell
python scripts/verify_integration.py
python scripts/verify_theme_apply.py
python scripts/verify_settings_fragment.py
python scripts/verify_l4.py
```

---

## 排障脚本 `[DIAGNOSE]`

| 脚本 | 用途 |
|------|------|
| `scripts/diagnose_inspect.py` | inspect / GPU API / A 端全链路 |
| `scripts/diagnose_l4_locate.py` | L4 Vision 真实屏幕定位 |
| `scripts/check_gpu_api_tunnel.py` | SSH 隧道 :9800 探测 |
| `scripts/check_port.py` | 端口占用 |
| `scripts/kill_port.py` | 释放端口（Windows） |
| `scripts/b_group2_e2e_verify.py` | 校园 GPU group2 E2E |
| `test_parse_local.py`（根） | GPU OmniParser API 隧道测试 |

---

## 启动脚本 `[PRODUCTION]` 辅助

| 脚本 | 用途 |
|------|------|
| `scripts/setup.bat` | B 端 venv + pip + check_ui_env |
| `scripts/setup_server_env.bat` | A 端 server/.venv |
| `scripts/setup_omniparser.bat` | OmniParser conda 环境 |
| `scripts/start_ui.bat` / `start_client.bat` | 仅 B 端 |
| `scripts/start_server.bat` | 仅 A 端（8010） |
| `scripts/start_all.bat` | OmniParser + A + B 全栈 |
| `scripts/start_l4_demo.bat` | A + B（L4，无 Omni 隧道） |
| `scripts/start_gpu_api_demo.bat` | GPU API 模式 A + B |
| `scripts/start_gpu_one_click.bat` | 远程 GPU 一键 |
| `scripts/start_tunnel_9800.bat` | SSH :9800 隧道 |
| `scripts/stop_all.bat` | 停止 A + Omni |
| `start_all.bat` / `stop_all.bat`（根） | 转发到 scripts/ |

---

## 单元测试 `[TEST]`

| 路径 | 说明 |
|------|------|
| `server/tests/` | A 端 pytest（intent, redline, blueprint, l4, routing, …） |
| `core/tests/` | B 端 pytest（overlay_coords, assist_gather, …） |
| `.github/workflows/ci.yml` | CI 跑部分 server tests + B 端 import smoke |

```powershell
cd server && python -m pytest tests/test_intent.py tests/test_redline.py tests/test_blueprint.py
python -m pytest core/tests/
```

---

## 演示 / 原型 `[DEMO]`

| 路径 | 说明 |
|------|------|
| `ui/style_preview_demo.py` | 主题五方案预览（`python -m ui.style_preview_demo`） |
| `ui/glass_demo.py` | 水晶玻璃视觉 demo |
| `ui/glass_demo_pro.py` | 水晶玻璃增强 demo |
| `ui/web_preview.py` | Web UI 预览 |

---

## 遗留 / 勿参考 `[LEGACY]`

| 路径 | 生产替代 |
|------|----------|
| `ui/demo/maodiao/` | `ui/native/orange_cat/` |
| `ui/demo/luxury_*.py` | `ui/native/luxury/` |
| `ui/web/` + `ui/bridge_web.py` | `ui/native/`（Web 回退：`HAJIMI_NATIVE_UI=0`） |
| `docs/api-contract-demo.yaml` | `docs/api-contract-demo_v2.yaml` |
| `docs/test_*.py` | `scripts/verify_*.py` + pytest |
| `docs/test_parse_local.py` | 根目录 `test_parse_local.py` 或 verify 脚本 |
| `server/README.md`（若与 README_v2 重复） | `server/docs/CHANGELOG-A端_v2.md` |
| `ui/native/themes/variant_b/`、`variant_c/` | 已删除；迁移逻辑在 `shell_appearance.py` |

---

## 文档索引

### `[DOC-PRIMARY]` 必读

| 文档 | 说明 |
|------|------|
| [`HANDOFF.md`](../HANDOFF.md) | 根 AI 5 分钟索引 |
| [`AI-操作指南.md`](AI-操作指南.md) | 详细操作手册 |
| [`FILE-MAP.md`](FILE-MAP.md) | 本文档 |
| [`B端-组员快速启动.md`](B端-组员快速启动.md) | 组员 onboarding |
| [`项目结构.md`](项目结构.md) | 目录地图 |
| [`P1-可移植性改动与使用指南.md`](P1-可移植性改动与使用指南.md) | 三种运行模式 |
| [`UI协作规范.md`](UI协作规范.md) | Layout / Style 边界 |
| [`B端接口总结-对A与对C_v2.md`](B端接口总结-对A与对C_v2.md) | API 契约 |
| [`b-c-api-contract.md`](b-c-api-contract.md) | C 端接入时读 |
| [`design-spec.md`](design-spec.md) | 视觉 spec |

### `[DOC-REF]` 按需

| 文档 | 说明 |
|------|------|
| [`校园GPU-B端联调清单_v2.md`](校园GPU-B端联调清单_v2.md) | **GPU 主读** |
| [`校园GPU与OmniParser环境速查_v2.md`](校园GPU与OmniParser环境速查_v2.md) | 环境速查 |
| [`B端-OmniParser-GPU-API部署文档.md`](B端-OmniParser-GPU-API部署文档.md) | GPU API 部署 |
| [`GPU-API远程接入手册.md`](GPU-API远程接入手册.md) | 远程接入 |
| [`L4-Vision快路径-技术说明.md`](L4-Vision快路径-技术说明.md) | L4 架构 |
| [`L4-真实环境运行指南.md`](L4-真实环境运行指南.md) | L4 运行 |
| `server/docs/A端-GPU容器部署详细指南-group2_v2.md` | A 端 GPU 容器 |
| 其他 GPU SSH 多版手册 | 补充参考，以联调清单为准 |

### `[DOC-HISTORY]` 日志（只读）

| 文档 | 说明 |
|------|------|
| `docs/DAY1-潘振喆-20230383.md` … `DAY6-工作内容_v2.md` | 历史 sprint |
| [`DAY7-工作内容_v2.md`](DAY7-工作内容_v2.md) | **最新 B 端功能**（双保存、五方案、avatar） |
| [`CHANGELOG-B端_v2.md`](CHANGELOG-B端_v2.md) | B 端变更史 |
| `server/docs/CHANGELOG-A端_v2.md` | A 端变更史 |

---

## 打包排除 `[IGNORE]`

| 路径 | 原因 |
|------|------|
| `.venv/`, `server/.venv/` | 本地重建 |
| `__pycache__/`, `.pytest_cache/` | 缓存 |
| `server/.env` | 密钥，用 `.env.example` |
| `docs/校园gpu使用.md` | 含凭证（gitignore） |
| `OmniParser.zip` | 与 `OmniParser/` 重复 |
| macOS 垃圾 / `Royal TSX.app` 等 | 非项目文件 |
| `%LOCALAPPDATA%/HAJIMI/user_settings.json` | 用户本地设置 |

---

## 快速 grep

```powershell
# 找所有验收脚本
rg "\[VERIFY\]" scripts/

# 找生产 API 客户端
rg "def process\(" core/api_client.py
```
