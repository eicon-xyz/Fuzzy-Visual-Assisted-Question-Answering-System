# ABC 完整调试距离与分工清单

> **读者**：A / B / C 三端负责人  
> **更新**：L5 外接 new_JIMI（方案 B 双 URL）实施后  
> **索引**：分项细节见 [A端指南](A端-ABC整合改动指南.md)、[C端指南](C端-ABC整合对齐指南.md)、[HANDOFF](../HANDOFF.md)、[**repo 外改动登记**](repo外改动与边界登记.md)

---

## 1. 「完整调试」定义

| 级别 | 含义 | 验收 |
|------|------|------|
| **P0 主线** | 本机 Windows：Omni + **8010** + **8011** + B UI；L3/L4 指引 + L5 自动执行各 1 条 | `verify_all --require-a` 绿 |
| **P1 集成** | B↔C 语音/审计 + C→A audit/config P0 | `audit_e2e_test` |
| **P2 管理面** | web-admin 连 8010 admin | 面板无 404 |
| **非目标** | Linux 全功能、删 8010 deprecated L5、全弹窗主题 | — |

---

## 2. 架构（定案）

```
B 端 PyQt5
  ├─ L3/L4/inspect/step → canonical A 端 :8010  (HAJIMI_UI/server)
  └─ L5 execute/stream/cancel → new_JIMI Sidecar :8011

OmniParser (:8002 或隧道 :9800) ← 8010 与 8011 共用
```

| 端口 | 仓库 | 维护者 |
|------|------|--------|
| **8010** | `HAJIMI_UI/server/` | B（L3/L4/audit）+ A（若共管 server） |
| **8011** | `new_JIMI/HAJIMI_UI/server/` | **A（L5 唯一源码）** |

---

## 3. 当前完成度矩阵

| 模块 | 状态 | 负责 | 阻塞 |
|------|------|------|------|
| L3/L4 指引 (8010) | 已接线 | B+A | LLM/Omni 环境 |
| L5 B 端 UI/worker | 已改连 **8011** | B | Sidecar 需运行 |
| L5 Sidecar (8011) | 代码在 new_JIMI | A | venv + `.env` |
| audit/config P0 (8010) | 已注册 | A | C 联调 |
| B↔C 信号桥 | B 已完成 | C | bind 时序 |
| verify_all | 8010 + 8011 串联 | B | 双端需启动 |
| 8010 本地 L5 路由 | deprecated 保留 | B | 远期删除 |
| C L5 metrics | 未做 | C | 见 issue 模板 |

---

## 4. 离完整还有几层

| 阶段 | 内容 | 预估 |
|------|------|------|
| ✅ 计划 | 方案 B、双 URL、独立 .env | 已完成 |
| **PR 代码** | B 改 8011、启动脚本、verify | 2–4 人天 |
| **环境** | A 建 new_JIMI venv/.env | 0.5–1 天 |
| **冒烟** | `verify_all --require-a` | 0.5 天 |
| **E2E** | 手动 L5 真点屏、取消 | 1–2 天 |
| **BC+A** | audit P0、语音信号 | 1–2 天 |
| **Polish** | pytest 5 fail、Dialog 主题、C L5 metrics | 可选 |

**L5 外接主线完成** ≈ PR + 环境 + 冒烟 + E2E。  
**ABC 整项目 P0** ≈ 再加 BC+A 联调。

---

## 5. A 同学待办

**主仓库（L5）**：`new_JIMI/HAJIMI_UI/server/`

| 优先级 | 任务 | 验收 |
|--------|------|------|
| P0 | 创建 `server/.venv`（`setup_server_env.bat`） | uvicorn :8011 能起 |
| P0 | 复制 [`server/.env.example`](../../new_JIMI/HAJIMI_UI/server/.env.example) → `.env`，填 LLM + **与 8010 相同** `OMNIPARSER_URL` | `GET :8011/health/live` OK |
| P0 | 不改业务代码；pull 后 restart 8011 | B `verify_l5 --require-a` |
| P1 | 8010 canonical audit/config P0（若 A 管 server） | C audit_e2e |
| P1 | admin P1 与 web-admin 对齐 | C 面板 |
| 持续 | `git pull` → restart 8011 | — |
| **不做** | 等 B merge executor；改包名 | — |

**启动**：

```powershell
cd new_JIMI\HAJIMI_UI
set HAJIMI_PORT=8011
scripts\start_server.bat
# 或从 B 端：HAJIMI_UI\scripts\start_l5_sidecar.bat
```

---

## 6. B 同学待办

**主仓库**：`HAJIMI_UI/`（B UI + 8010 + 脚本）

| 优先级 | 任务 | 位置 |
|--------|------|------|
| P0 | L5 改连 `L5_API_URL`（默认 :8011） | `core/api_client.py`, `execute_worker.py` |
| P0 | Sidecar auto-launch | `core/l5_sidecar_launcher.py` |
| P0 | `start_l5_sidecar.bat` + `start_all` / `stop_all` | `scripts/` |
| P0 | `verify_l5` / `verify_all` 双端 | `scripts/verify_*.py` |
| P1 | 8010 L5 标 deprecated，不删 | `server/routes/demo.py` |
| P2 | 其他 Dialog 主题 | `ui/native/` |

**环境变量（开发者，无普通 UI）**：

| 变量 | 默认 |
|------|------|
| `HAJIMI_API_URL` | `http://127.0.0.1:8010` |
| `L5_API_URL` | `http://127.0.0.1:8011` |
| `HAJIMI_L5_ROOT` | 空 → `../new_JIMI/HAJIMI_UI` |
| `HAJIMI_AUTO_LAUNCH_L5` | `1` |

---

## 7. C 同学待办

| 优先级 | 任务 | 验收 |
|--------|------|------|
| P0 | `server_url` 统一 **8010** | 无路径错 |
| P0 | audit DB → `%LOCALAPPDATA%/HAJIMI/` | B 启动正常 |
| P0 | 修复 `bind_to` / `start` 时序 | 麦克风/TTS |
| P0 | 对接 A P0 audit/config | audit_e2e |
| P1 | web-admin admin API | 无 404 |
| **知悉** | **L5 数据在 8011**，8010 dashboard 暂无 L5 统计 | 本文 §2 |
| P2（issue） | 可选只读 `L5_API_URL` metrics | 本期不做 |

---

## 8. 推荐联调顺序

1. B：`scripts\start_all.bat`（Omni + 8010 + 8011 + UI）  
2. A：确认 new_JIMI `.env` 与 Omni 可用  
3. B：`python scripts\verify_all.py --require-a`  
4. B：L4 指引 1 条（8010）  
5. B：L5 简单任务 + 取消（8011，真 pyautogui）  
6. A+C：8010 audit/config  
7. B+C：语音/审计信号  
8. （可选）内网：8010 远程 + **8011 仍本机** + Omni 隧道  

---

## 9. 一键验收

```powershell
cd HAJIMI_UI
scripts\start_all.bat
python scripts\verify_all.py --require-a

curl http://127.0.0.1:8010/api/demo/health/live
curl http://127.0.0.1:8011/api/demo/health/live
python scripts\verify_l5.py --require-a
pytest server/tests/ -q
```

---

## 10. 风险与依赖

| 风险 | 缓解 |
|------|------|
| 8011 venv 未建 | A 跑 `setup_server_env.bat` |
| Omni CPU 慢 | 隧道 :9800 |
| pyautogui 必须本机 | 8011 不得放远程 GPU |
| 两边 `.env` 不同步 | 文档约定；Omni URL 手动一致 |
| API 漂移 | `verify_l5` + a-c-api-contract |

---

## 11. 文档维护

- **Owner**：B 端  
- **更新时机**：PR 合并、ABC 联调里程碑后  
- **HANDOFF**：§3 必读表已索引本文  
