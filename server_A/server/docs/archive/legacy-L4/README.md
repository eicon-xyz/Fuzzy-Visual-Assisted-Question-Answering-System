# ⚠️ LEGACY-L4 史料区 — 禁止照做

本目录存放 **2026-09 已整体删除的 L4 指引模式架构** 的运行史料：

- 旧 A 端 FastAPI（`:8010`）、OmniParser 视觉解析（`:9800` GPU 隧道 / `:8002` 本地）、校园 GPU 容器部署与内网联调。
- 现行唯一后端 = **L5 Sidecar（`server_A/`，:8011）**；开发指南 = 仓库根 [`../../../../../AGENTS.md`](../../../../../AGENTS.md)。

**为何归档而非删除**：项目自定归档约定（`HAJIMI_UI/docs/ARCHIVE-MANIFEST.md`「先文档后移动」+「历史文档不改」）——保留实训/答辩史料可追溯性，同时隔离误导面。

## 一、A 端部署史料（2026-09-03 归档）

| 文件 | 内容 | 状态 |
|---|---|---|
| `A端-GPU容器部署详细指南-group2_v2.md` | GPU 容器部署 runbook | 死（无 GPU 隧道，无 :9800） |
| `A端-学校GPU部署与联调指南_v2.md` | 学校 A800 内网联调 | 死（内网联调已移除） |
| `CHANGELOG-A端_v2.md` | 旧 A 端行为变更记录 | 史（对应代码已不存在） |

## 二、server_A 文档层（2026-09-23 归档）

原路径结构保留在 `server_A-layer/` 下，便于对照追溯：

| 原路径 | 内容 | 状态 |
|---|---|---|
| `server_A/README.md` | 仓库概览（OmniParser :9800 → 计划 → 执行，A 端 :8010） | 死（两端口均已移除） |
| `server_A/server/README.md` | Demo Server 快速启动（:8010） | 死 |
| `server_A/server/README_v2.md` | Demo Server v2（:8010；其引用的 A 端联调指南已在本区） | 死 |
| `server_A/docs/DEV-GUIDE.md` | 3 人开发环境搭建（A 端 :8010 / OmniParser :9800 / Mock 模式） | 死（33 处 L4 口径） |
| `server_A/docs/API-CONTRACT.md` | 旧 Demo API 契约 | 死 |
| `server_A/docs/BACKEND-CHECKLIST.md` | 旧后端待办清单 | 死 |
| `server_A/docs/UI-SPEC.md` | 旧 UI 规格 | 死 |
| `server_A/docs/api-admin-users.md` | admin/users 接口说明（含 :8010） | 待核（路由仍在，端口口径过期） |
| `server_A/docs/api-auth.md` | 鉴权接口说明（含 :8010） | 待核（同上） |
| `server_A/docs/api-reference.md` | 接口总览（含 :8010） | 待核（同上） |

> 现行接口以 Sidecar Swagger（`http://127.0.0.1:8011/docs`）+ `server_A/server/routes/` 源码为准。

## 同批治理

- `server_A/CLAUDE.md` 原为 L4 口径旧稿且会被工具注入为 agent 指令，已按实况重写（2026-09-03）。
- `server_A/docs/docs/` 为误建嵌套副本（9 文件与父目录零内容差异、全仓零引用），2026-09-23 删除。
