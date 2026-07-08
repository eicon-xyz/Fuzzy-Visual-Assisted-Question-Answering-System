# repo 外改动与边界登记（L5 外接 server_A）

> **读者**：A / B / C 三端；合并 PR 或联调前必读  
> **原则**：B 端改造集中在 [`HAJIMI_UI/`](../)；**不修改** `server_A` 业务代码；repo 外变更在本文件登记。  
> **关联**：[ABC 完整调试距离与分工清单](ABC-完整调试距离与分工清单.md) · [HANDOFF](../HANDOFF.md)

---

## 1. git 改动清单（HAJIMI_UI 以外）

截至 L5 方案 B（双 URL）实施，`git status` 中 **HAJIMI_UI 外仅下列文件与 L5 外接直接相关**：

| 路径 | 类型 | 维护者 | 说明 |
|------|------|--------|------|
| [`server_A/server/.env.example`](../../server_A/server/.env.example) | **B 新增模板** | A 复制使用 | L5 Sidecar `:8011` 的 LLM/Omni/Demo-Key 占位；**非**业务代码 |

> 过渡期：若仓库仍含 `new_JIMI/HAJIMI_UI`，B 端 `resolve_l5_root()` 会 fallback 并警告。

### 明确未改（A 零改业务代码）

| 路径 | 说明 |
|------|------|
| `server_A/server/**/*.py` | executor / agent / routes — **无 B 端 diff** |
| `server_A/scripts/` | A 侧启动脚本 — B 不覆盖 |
| `client/` | C 端 — 无 L5 外接代码变更 |
| `web-admin/` | 仍默认连 **8010** admin |
| `参考文档/` | 未同步 L5 双 URL（见 §4 陈旧文档表） |

---

## 2. server_A 目录角色（A 主责）

```
repo 根/
├── HAJIMI_UI/              ← B 主仓库：8010 canonical + B UI + 启动 Sidecar 的 bat
└── server_A/               ← A L5 源码：8011 Sidecar（一层；非 server_A/server_A）
    ├── server/
    │   ├── .env.example
    │   ├── .env            ← A 本地创建，**不入 git**
    │   └── .venv/          ← A 本地 setup_server_env，**不入 git**
    └── scripts/
```

| 项 | 约定 |
|----|------|
| **端口** | `HAJIMI_PORT=8011`（本地 Sidecar）；联调时 L5 走队友 **8010** |
| **API** | `/api/demo/execute` · `/stream/{id}` · `/cancel` |
| **Omni** | `OMNIPARSER_URL` 与 8010 **手动对齐**（如 campus `:9800` 隧道） |
| **B 启动** | [`HAJIMI_UI/scripts/start_l5_sidecar.bat`](../scripts/start_l5_sidecar.bat) 薄封装 call `server_A/.../start_server.bat` |
| **路径覆盖** | 环境变量 `HAJIMI_L5_ROOT`；默认 `core/paths.resolve_l5_root()` → `server_A/` |

---

## 3. B 端对 repo 外的「运行时依赖」（非 git 改文件）

| B 端组件 | 行为 |
|----------|------|
| `config.L5_API_URL` | 默认 `http://127.0.0.1:8011` |
| `core/api_client.execute_task` | POST Sidecar，非 8010 |
| `core/execute_worker` | SSE 连 Sidecar |
| `core/l5_sidecar_launcher` | 可选 auto-launch 8011 |
| `scripts/start_all.bat` / `start_gpu_api_demo.bat` | 启 8010 + 8011 |
| `scripts/stop_all.bat` | kill 8010 + **8011** |
| `env_sync` | **仅写** `HAJIMI_UI/server/.env`，**不写** server_A |

8010 上 `/execute` 等路由标 **DEPRECATED**，B 客户端不再调用。

---

## 4. 仓库内陈旧文档（未改、勿当真）

以下路径 **未** 随 L5 外接更新；联调以 **HAJIMI_UI/docs/** 为准。

| 路径 | 问题 | 应以何为准 |
|------|------|------------|
| [`工作进度/测试指南.md`](../../工作进度/测试指南.md) | 写 A 在 new_JIMI `:8010` | 8010 = `HAJIMI_UI/server`；8011 = `server_A/` |
| [`参考文档/HAJIMI-统一接口文档.md`](../../参考文档/HAJIMI-统一接口文档.md) | 仅单 URL `:8010` | [`B端接口总结-对A与对C_v2.md`](B端接口总结-对A与对C_v2.md) + 本文 |
| [`参考文档/环境配置问题记录.md`](../../参考文档/环境配置问题记录.md) | 启动顺序无 8011 | [HANDOFF](../HANDOFF.md) · [校园GPU-B端联调清单_v2.md](校园GPU-B端联调清单_v2.md) |
| `.cursor/plans/a端跨目录集成策略_*.plan.md` | 早期 merge 进 canonical | 已采用 **方案 B 双 URL**，见 ABC 清单 |

---

## 5. C 端 / 根项目（无代码改动）

| 组件 | L5 外接影响 |
|------|-------------|
| `client/` | 仍通过 B 信号桥；HTTP 仍 **8010** audit/config |
| `web-admin/` | 仍 **8010**；L5 任务/metrics 在 8011，**本期不接入** |
| C 必读 | [C端-ABC整合对齐指南.md](C端-ABC整合对齐指南.md) |

---

## 6. A 同学首装 checklist（repo 外操作）

```powershell
cd server_A
scripts\setup_server_env.bat
copy server\.env.example server\.env
# 编辑 server\.env：LLM_API_KEY、OMNIPARSER_URL（与 8010 一致，指向 GPU）
set HAJIMI_PORT=8011
scripts\start_server.bat
curl http://127.0.0.1:8011/api/demo/health/live
```

或由 B 一键：`根目录\启动本地.bat` 或 `HAJIMI_UI\scripts\start_l5_sidecar.bat`

---

## 7. 文档维护

- **Owner**：B 端（与 ABC 清单同步）
- **何时更新**：server_A 侧新增 B 可见文件；或 repo 外文档与架构再次分叉时
