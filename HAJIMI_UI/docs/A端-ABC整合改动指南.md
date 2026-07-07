# A 端 ABC 整合改动指南（给 A 负责人）

> **读者**：负责 `HAJIMI_UI/server/`（**8010 L3/L4**）与/或 `new_JIMI/HAJIMI_UI/server/`（**8011 L5**）的后端成员  
> **L5 外接**：B 端 L5 已改连 **:8011 Sidecar**；请在 `new_JIMI/` 维护 executor，**勿**等 B merge 进 canonical。  
> **Sidecar 环境模板**：[`new_JIMI/HAJIMI_UI/server/.env.example`](../../new_JIMI/HAJIMI_UI/server/.env.example)  
> **三端总览**：[`ABC-完整调试距离与分工清单.md`](ABC-完整调试距离与分工清单.md)  
> **契约**：[`参考文档/a-c-api-contract.md`](../../参考文档/a-c-api-contract.md)

---

## L5 Sidecar（8011）— A 主责

| 项 | 说明 |
|----|------|
| 目录 | `new_JIMI/HAJIMI_UI/server/` |
| 端口 | `HAJIMI_PORT=8011` |
| venv | `new_JIMI/HAJIMI_UI/server/.venv`（独立，A 自维护） |
| .env | 从 `.env.example` 复制；**OMNIPARSER_URL 与 8010 一致** |
| 更新 | `git pull` → restart 8011 或 B `start_l5_sidecar.bat` |
| B 启动 | `HAJIMI_UI/scripts/start_l5_sidecar.bat`（薄封装 call 本目录 `start_server.bat`） |

---

## P0 — C 联调阻塞（8010 canonical，优先实现）

### 1. `POST /api/audit/report`

| 项 | 说明 |
|----|------|
| 文件 | 新建 `server/routes/audit.py` |
| 认证 | `X-Demo-Key` |
| 请求体 | `{ "client_id": string, "batch": AuditRecord[] }`，1~100 条 |
| 响应 200 | `{ "received": int, "server_queue_depth": int }` |
| 持久化 | 写入现有 ORM（Task / Feedback 或专用 audit 表） |
| 注册 | `server/main.py` → `app.include_router(audit_router)` |

### 2. `GET /api/config/pull`

| 项 | 说明 |
|----|------|
| 文件 | 新建 `server/routes/config_client.py` |
| 认证 | `X-Demo-Key`；请求头 `X-Client-Version` |
| ETag | 支持 `If-None-Match` → 304 空 body |
| 响应 200 | `{ "has_update": true, "config": ClientConfig }` |
| 数据源 | `ConfigRepository.get_all()` 聚合为 ClientConfig 形状 |

**自测**：

```powershell
curl -X POST http://127.0.0.1:8010/api/audit/report -H "X-Demo-Key: hajimi-demo-2026" -H "Content-Type: application/json" -d "{\"client_id\":\"test\",\"batch\":[]}"
curl http://127.0.0.1:8010/api/config/pull -H "X-Demo-Key: hajimi-demo-2026"
```

根项目：`python client/audit_e2e_test.py`（需真实 A 端，非 Mock 18900）

---

## P1 — Web 管理面板对齐

| 端点 | 说明 |
|------|------|
| `POST /api/audit/feedback` | 单条用户反馈 |
| `GET /api/admin/failures/stats` | 失败分布 + 趋势 |
| `GET /api/admin/flow/topology` | 数据流拓扑（可先 Mock，字段对齐 web-admin） |
| `GET /api/admin/flow/metrics` | QPS / 成功率 |
| `GET /api/admin/flow/versions` | 客户端版本分布 |
| `GET /api/admin/monitor/health` | 组件健康 |
| `GET /api/admin/monitor/alerts` | 告警列表 |
| `POST /api/admin/config/deploy` | **改为 JSON body** `{ "key", "value", "description?" }`（当前为 query params，与 web-admin 不一致） |
| `POST /api/auth/login` | 管理面板 JWT（Demo 阶段 web-admin 可继续 Mock） |

参考前端期望：根项目 `web-admin/src/api/admin.js`

---

## P2 — Demo 契约与行为同步

| 项 | 动作 |
|----|------|
| `docs/api-contract-demo_v2.yaml` | 补 `/health/live`、`/locate`、`/relocate`、L4/redline/assist 字段；默认端口 **8010** |
| `POST /api/demo/clarify` | 使用 `request.answer` 更新 intent（当前仅 +0.1 confidence） |
| `POST /api/demo/report` | 文档改为「写 DB」（与实现一致） |

**回归**：`pytest server/tests/` + B 端 `python scripts/verify_integration.py`

---

## 当前已实现（无需重复）

Demo 9 端点（含 locate/relocate/health/live）见 `server/routes/demo.py`；Admin 9 端点见 `server/routes/admin.py`。
