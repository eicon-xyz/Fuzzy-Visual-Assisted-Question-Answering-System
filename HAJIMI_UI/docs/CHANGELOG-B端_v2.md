# HAJIMI B 端改动记录（v2）

## 接口约定（与 api-contract-demo_v2.yaml 对齐）

| 依赖 A 端 | B 端用法 |
|-----------|----------|
| `POST /process` | `core/api_client.process()`；读 `reference_resolution`、 `ui_elements` |
| `POST /inspect` | `core/api_client.inspect()`；检验模式全量框选 |

**坐标**：A 端返回的 bbox 已是截图物理像素；B 端 `ref_size == screen_size` 时不再做 1920 缩放。

---

## A 端前置条件

- `/api/demo/inspect` 已部署
- A 端配置 `REPLICATE_API_TOKEN`
- `python scripts/verify_integration.py` health 通过

---

## 已完成

- [2026-06-29] 检验模式：`InspectWorkerThread` + Settings「立即检测当前屏幕」
- [2026-06-30] **指示框坐标修复**：截图物理像素 → Qt 逻辑坐标（HiDPI 1.5x）；`core/overlay_coords.py`
- [2026-06-30] **分步手动定位**：当前画面无目标元素时弹出「请先完成这一步」→「我已完成，重新定位」→ `POST /api/demo/relocate` 对新截图标注（绕过 Windows 上 :8001 僵尸监听）；`start_server.bat` 启动前自动 `kill_port`、去掉 `--reload`；`start_all` 先 `stop_all` 再启动
- [2026-06-30] `/process` 预检：旧版或多开 A 端时提示 `stop_all.bat` + 设置页启动按钮
- [2026-06-29] Overlay 青色全量框 `inspect_box`；指引红框与检验框分离
- [2026-06-29] `reference_resolution` / `ui_elements` lookup 对接
- 涉及：`inspect_worker.py`, `api_client.py`, `annotation_mapper.py`, `overlay_anno.py`, `app_controller.py`, `main_widget.py`, `medium_panel.py`, `task_worker.py`

---

## UI 实验与回退（native v2）

- **设计母版**：`ui/web/index.html`（本轮不修改样式）
- **Native 实现**：`ui/native/design_tokens.py` + `theme.qss`，对照 `docs/design-spec.md`
- **回退 WebEngine UI**：`set HAJIMI_NATIVE_UI=0` 后 `python main.py`
- **浏览器对照**：`python -m ui.web_preview`
- **校验 tokens**：`python scripts/sync_design_tokens.py`
- **校验回退路径**：`scripts\verify_web_ui_fallback.bat`

- [2026-06-30] **Native UI v2**：面板 480×520、168px overlay drawer + backdrop、SVG 导航、stage hint、processing 禁用输入、PrepareStep banner、DialogCard、overlay 色对齐 HTML `--danger`

- [2026-06-30] **水晶玻璃一体式背景 + Resize + OmniParser 路径**：`paint_crystal_glass`（α=165）；壳/Card QSS 透明；气泡与 InputFloat 保持独立样式；按钮 QSS 不改。详见 [`Resize指示条与OmniParser路径-技术说明.md`](Resize指示条与OmniParser路径-技术说明.md)

---

- `HAJIMI_MOCK_ONLY=1`：process 仍走本地 Mock；**检验模式不可用**（需 A 端 `/inspect`）
- `HAJIMI_MOCK_FALLBACK=1`：A 端不可达时 process 回退 Mock

---

## 验收清单

1. 启动 A 端 + B 端 `python main.py`
2. 设置 →「立即检测当前屏幕」→ 桌面出现青色 `~N` 框
3. 输入任务 → 红框来自真实检测坐标（非固定模板）
4. `python scripts/verify_integration.py`

---

## 待 A/B 端联调

- 真实桌面截图下 OmniParser 元素数量与框位置人工验收
- 内网 GPU 部署见 A 端 [`server/docs/A端-学校GPU部署与联调指南_v2.md`](../server/docs/A端-学校GPU部署与联调指南_v2.md)

---

## [2026-07-01] 系统设置：部署模式 + API 配置

- **持久化**：`%LOCALAPPDATA%/HAJIMI/user_settings.json`（`core/user_settings.py`）
- **系统设置页**（Native）：部署模式「本地启动 / 内网 API」、A 端地址、Demo Key、DeepSeek LLM、OmniParser URL/GPU URL
- **保存并应用** / 表单内 **Enter** 提交；本地模式合并写入 `server/.env`（`core/env_sync.py`）
- **预检**：内网模式仅查远程 `/health`；本地模式显示 GPU/CPU 状态（读 A 端 `detector_device`）
- **启动时**：`main.py` 最早 `apply_user_settings(load_user_settings())`
- 涉及：`core/user_settings.py`, `core/env_sync.py`, `ui/native/settings_widgets.py`, `ui/native/medium_panel.py`, `ui/main_widget.py`, `config.py`, `core/api_client.py`

### 文档 v2 批次（DAY3）

- 全部联调文档升版为 `_v2` 后缀，索引见 [`DAY3-工作内容_v2.md`](DAY3-工作内容_v2.md) §五
- API 契约：[`api-contract-demo_v2.yaml`](../api-contract-demo_v2.yaml)（health 扩展字段）
- A 端 runbook：[`server/docs/A端-学校GPU部署与联调指南_v2.md`](../server/docs/A端-学校GPU部署与联调指南_v2.md)
