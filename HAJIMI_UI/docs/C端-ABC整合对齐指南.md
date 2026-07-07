# C 端 ABC 整合对齐指南（给 C 负责人）

> **读者**：负责根项目 `client/` 与 `web-admin/` 的成员  
> **背景**：B 端（`HAJIMI_UI`）已在 `main_widget._init_c_integration()` 中加载 `VoiceIntegrationController` 并绑定 `BCIntegrationSignals`。  
> **契约**：[`docs/b-c-api-contract.md`](b-c-api-contract.md)  
> **L5 说明**：L5 自动执行走 **new_JIMI Sidecar :8011**；web-admin 默认连 **:8010**，**暂无 L5 任务统计**（远期 issue：只读 `L5_API_URL` metrics）。详见 [`ABC-完整调试距离与分工清单.md`](ABC-完整调试距离与分工清单.md)。

---

## B 端已完成的挂载（C 只需对齐下列项）

| B 侧 | 行为 |
|------|------|
| `BCIntegrationSignals` | `core/bc_signals.py` — 九信号 + `health_result` |
| 启动 | `start()` → `bind_to(bc_signals, shared_state)` |
| 麦克风 | `mic_pressed` → `asr_start`；`mic_released` → `asr_stop` |
| 审计 | `AppController._emit_audit()` → `audit_submit` |
| TTS | 步骤切换 → `tts_enqueue` |
| 语音设置 | `user_settings.json` 的 `voice` 块 + 设置页第三块 save |
| 关闭 | `MainWidget.closeEvent` → `VoiceIntegrationController.shutdown()` |

环境变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `HAJIMI_C_ENABLED` | `1` | `0` 时 B 不加载 C |
| `HAJIMI_REPO_ROOT` | HAJIMI_UI 上级目录 | 供 `import client` |

---

## C 端必须对齐的改动

### 1. 路径与配置

| 项 | 现状 | 建议 |
|----|------|------|
| `server_url` | 部分文档写 `:8000` | 统一 **8010**；B 传入 `API_BASE_URL` |
| `audit_queue.db` | 相对路径 `client/audit/audit_queue.db` | 改为 `%LOCALAPPDATA%/HAJIMI/audit_queue.db` |
| Vosk 模型 | 相对 `models/` | 文档说明与 B 启动 cwd 无关 |

### 2. 信号时序

B 调用顺序：`VoiceIntegrationController.start()` → `bind_to()`。

若 `bind_to()` 在 `start()` 之前调用，C 的 `_bind_qt_signals()` 因 `_started=False` 会跳过绑定 — **建议在 C 侧修复**：`bind_to()` 末尾若已 `start()` 则立即 `_bind_qt_signals()`，或 `start()` 后重新 bind。

### 3. 信号签名

| 信号 | 约定 |
|------|------|
| `asr_result` | C emit 单 `dict`（B 已按 dict 解析） |
| `health_result` | C emit `HealthStatus` 对象（B `_on_c_health_result` 已支持） |
| `tts_enqueue` | `(text, priority, interrupt_current)` |

### 4. C→A HTTP

| 模块 | 依赖 A 端 |
|------|-----------|
| `client/audit/audit_agent.py` | P0 `POST /api/audit/report` |
| `client/config/config_poller.py` | P0 `GET /api/config/pull` |
| `web-admin` | P1 `/api/admin/*` 形状对齐 |

---

## C 自测命令（根项目）

```powershell
python client/voice_setup.py
python client/bc_integration_test.py    # 36 项 B-C 仿真
python client/audit_e2e_test.py         # 需 A 端 audit 路由
```

B 端验收：

```powershell
cd HAJIMI_UI
python scripts/verify_bc_signals.py
```

---

## Web 管理面板

- Vite dev proxy → `http://127.0.0.1:8010`
- `/api/auth/login`：A 未实现前保持前端 Mock 登录
