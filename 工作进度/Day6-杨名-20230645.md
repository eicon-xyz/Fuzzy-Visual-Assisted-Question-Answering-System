# HAJIMI 第六天工作进度 — 角色 A（后端/AI核心）

**姓名**：[请填写姓名]  
**学号**：[请填写学号]  
**日期**：2026年7月4日  
**角色**：A（后端 / AI核心）

---

## 一、完成任务

### 1. 全系统最终验收 ✅

**联合验收清单**（A+B+C 三端）：

| 场景 | 路径 | 验收结果 |
|------|------|----------|
| 文本提问 | 输入"怎么安装微信？" → A `/process` → 返回步骤+标注 → B 桌面挂件展示 → B 覆盖层红框 | ✅ |
| 逐步推进 | 点击"下一步" × 4 → A `/step` 推进蓝图 → B 步骤高亮更新 → 标注跟随 | ✅ |
| 语音提问 | B 麦克风按钮 → C ASR 录音 → 文字入 B 输入框 → A `/process` → TTS 播报 | ✅ |
| 检验模式 | B 系统设置"立即检测" → A `/inspect` → 全量元素+SoM 图 → B 覆盖层全屏标注 | ✅ |
| 重定位 | B 手动操作后 → A `/relocate` → 重截图+匹配 → 更新标注 | ✅ |
| 红线拦截 | 输入"帮我自动抢票" → A 红线检测 → 拒绝+安全提示 → B 显示拒答 | ✅ |
| 主动澄清 | 输入模糊意图 → A `/clarify` → 二选一问题 → B 弹窗 → 回答→更新意图 | ✅ |
| 蓝图挂起 | 模拟指纹不匹配 → A 挂起 → B "挂起"状态提示 → 选择跳过/回退/终止 | ✅ |
| 任务完成 | 全部步骤完成 → A `/report` → 审计写入 → C 管理面板可见 | ✅ |
| 管理面板 | 登录 → Dashboard 数据正确 → 失败归因下钻 → 配置热部署 → 健康监控 | ✅ |
| 断网降级 | A 离线 → B/C 降级正常 → A 恢复 → 审计补传 | ✅ |

**端口与启动顺序**：

| 组件 | 端口 | 启动命令 |
|------|------|----------|
| OmniParser | `9800` | `scripts\start_omniparser.bat` |
| **A 端 Server** | `8000` | `python -m uvicorn server.main:app --host 127.0.0.1 --port 8000` |
| B 端桌面挂件 | — | `python main.py` |
| C 端 Web 管理面板 | `5173` | `cd web-admin && npm run dev` |

### 2. A 端全测试矩阵 ✅

| 层次 | 测试 | 项数 | 结果 |
|------|------|------|------|
| P0 元素感知 | `test_perception.py` | 6 | ✅ |
| P1 意图分类 | `test_intent.py` | 12 | ✅ |
| P2 动态重规划 | `test_replanner.py` | 5 | ✅ |
| P3 蓝图状态机 | `test_blueprint.py` | 4 | ✅ |
| P4 约束提取 | `test_constraint.py` | 6 | ✅ |
| 红线检测 | `test_redline.py` | 8 | ✅ |
| 老代码快照 | `test_legacy.py` | 8 | ✅ |
| HTTP E2E | `test_api.py` | 12 | ✅ |
| **A 端总计** | | **61** | **61/61 ✅** |
| C 端跨端联调 | `real_api_test.py` | 16 | ✅ |
| B 端联调验收 | `verify_integration.py` | 12 | ✅ |

### 3. 端点完整性确认 ✅

| 契约文档 | 端点/信号数 | A 端实现 |
|----------|-----------|----------|
| A-C 接口契约 | 26 端点 | 26 端点全部实现 ✅ |
| A-B 接口契约（demo） | 7 端点 | 7 端点全部实现 ✅ |
| HAJIMI-统一接口文档 | 26 端点 | 全部对齐 ✅ |

**A 端 26 个端点完整清单**：

| # | 方法 | 路径 | 认证 | 分组 |
|---|------|------|------|------|
| 1 | GET | `/api/demo/health` | 无 | Demo |
| 2 | POST | `/api/demo/process` | X-Demo-Key | Demo |
| 3 | POST | `/api/demo/inspect` | X-Demo-Key | Demo |
| 4 | POST | `/api/demo/step` | X-Demo-Key | Demo |
| 5 | POST | `/api/demo/relocate` | X-Demo-Key | Demo |
| 6 | POST | `/api/demo/clarify` | X-Demo-Key | Demo |
| 7 | POST | `/api/demo/report` | X-Demo-Key | Demo |
| 8 | POST | `/api/audit/report` | X-Demo-Key | 审计 |
| 9 | POST | `/api/audit/feedback` | X-Demo-Key | 审计 |
| 10 | GET | `/api/config/pull` | X-Demo-Key | 配置 |
| 11 | POST | `/api/auth/login` | 无 | 认证 |
| 12 | GET | `/api/admin/stats/overview` | X-Admin-Key | Admin 统计 |
| 13 | GET | `/api/admin/stats/top-tasks` | X-Admin-Key | Admin 统计 |
| 14 | GET | `/api/admin/stats/trend` | X-Admin-Key | Admin 统计 |
| 15 | GET | `/api/admin/stats/redline` | X-Admin-Key | Admin 统计 |
| 16 | GET | `/api/admin/stats/feedback` | X-Admin-Key | Admin 统计 |
| 17 | GET | `/api/admin/failures/list` | X-Admin-Key | Admin 失败 |
| 18 | GET | `/api/admin/failures/detail/{task_id}` | X-Admin-Key | Admin 失败 |
| 19 | GET | `/api/admin/config/current` | X-Admin-Key | Admin 配置 |
| 20 | POST | `/api/admin/config/deploy` | X-Admin-Key | Admin 配置 |
| 21 | GET | `/api/admin/flow/topology` | X-Admin-Key | Admin 数据流 |
| 22 | GET | `/api/admin/flow/metrics` | X-Admin-Key | Admin 数据流 |
| 23 | GET | `/api/admin/flow/versions` | X-Admin-Key | Admin 数据流 |
| 24 | GET | `/api/admin/monitor/health` | X-Admin-Key | Admin 监控 |
| 25 | GET | `/api/admin/monitor/alerts` | X-Admin-Key | Admin 监控 |
| 26 | POST | `/api/admin/monitor/alerts/read-all` | X-Admin-Key | Admin 监控 |

### 4. 文档最终整理 ✅

| 文档 | 路径 | 内容 |
|------|------|------|
| A 端 README | `server/README.md` | 26 端点表 + 模块描述 + 环境变量表 + 启动步骤 + 常见问题 |
| A 端 CHANGELOG | `项目文档/CHANGELOG-A端.md` | 8 个阶段全部改动记录 |
| A 端实施记录 | `server/A_实现优先级.md` | P0-P4 全部完成 + 遗留清单 |
| `.env.example` | `server/.env.example` | 全部环境变量文档化（含新增 LLM_PROVIDER 等） |
| API 契约 YAML | `项目文档/a-c-api-contract.yaml` | 26 端点 OpenAPI 3.0 规范 |
| 统一接口文档 | `项目文档/HAJIMI-统一接口文档.md` | A-B-C 全部接口最新版本 |
| SeeClick/YOLO 评估 | `项目文档/SeeClick-YOLO-评估报告.md` | 评估结论：优先 GroundingDINO |
| 六天工作进度 | `工作进度/Day1-6-[A姓名]-[学号].md` | A 端六天全部工作记录（本文档系列） |

### 5. 演示场景数据填充 ✅

| 场景 | 演示方式 | 预置数据 |
|------|----------|----------|
| L3 复杂任务 | "怎么安装微信？" | 4 步蓝图 + OmniParser 元素检测 + SoM 标注图 |
| L2 简单任务 | "怎么保存文档？" | 模板匹配 < 3s 响应 |
| 红线拦截 | "帮我自动抢票" | 红线规则命中 → 引导拒绝 |
| 语音提问 | 麦克风 → ASR → 意图 → TTS | C 端语音链路 |
| 管理面板总览 | Dashboard KPI | 模拟 100+ 事务、20+ 失败 |
| 失败归因 | 失败列表 → 详情 | LLM 快照 + 指纹对比 |
| 配置热部署 | 修改置信度阈值 → 保存 | 部署日志 + 客户端通知 |
| 健康监控 | 组件状态指示灯 | psutil 实时数据 |

### 6. 一键启动脚本 ✅

```bash
# === A 端启动 ===
cd E:\Fuzzy-Visual-Assisted-Question-Answering-System
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000

# === A 端健康检查 ===
curl http://localhost:8000/api/demo/health

# === A 端全量测试 ===
pytest server/tests/
python server/test_api.py

# === 三端全栈（需 OmniParser 先启动）===
# 1. OmniParser (port 9800)
scripts\start_omniparser.bat
# 2. A 端 (port 8000)
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
# 3. B 端桌面挂件
cd HAJIMI_UI && python main.py
# 4. C 端 Web 面板
cd web-admin && npm run dev
```

---

## 二、A 端六天总交付物

### 核心服务模块（7 个路由，26 个端点）

| 路由 | 文件 | 端点数 | 行数 |
|------|------|--------|------|
| Demo 核心 | `server/routes/demo.py` | 7 | ~300 |
| Admin 管理 | `server/routes/admin.py` | 9 | ~250 |
| 审计代理 | `server/routes/audit.py` | 2 | ~130 |
| 配置拉取 | `server/routes/config_client.py` | 1 | ~100 |
| 认证 | `server/routes/auth.py` | 1 | ~80 |
| 数据流 | `server/routes/flow.py` | 3 | ~120 |
| 健康监控 | `server/routes/monitor.py` | 5 | ~150 |

### AI/逻辑模块（6 个子目录，15 个核心文件）

| 模块 | 文件 | 行数 | 功能 |
|------|------|------|------|
| LLM 客户端 | `services/llm/client.py` | ~200 | 5 provider 多模态 LLM 调用 |
| LLM Prompt | `services/llm/prompt.py` | ~120 | SYSTEM_PROMPT + REPLAN_PROMPT |
| 元素感知 | `services/perception/serializer.py` | ~30 | UI 元素 → LLM 文本 |
| 规划路由 | `services/planning/router.py` | ~400 | 步骤生成 + 约束提取 + 重定位 |
| 动态重规划 | `services/planning/replanner.py` | ~100 | 未绑定步骤自动重规划 |
| 蓝图状态机 | `services/planning/blueprint_engine.py` | ~200 | 7 状态全覆盖 |
| 标注构建 | `services/planning/annotation.py` | ~120 | 屏幕红框/箭头/标签 |
| 复杂度路由 | `services/planning/complexity_router.py` | ~80 | L2/L3 路由 |
| 步骤评估 | `services/planning/evaluator.py` | ~90 | 步骤执行后评估 |
| 风险评分 | `services/planning/risk_scorer.py` | ~60 | 步骤风险 1-5 级 |
| 坐标校验 | `services/planning/coordinate_validator.py` | ~70 | bbox 合法性校验 |
| 意图分类 | `services/intent/setfit_classifier.py` | ~100 | SetFit 9 类 + keywords fallback |
| 红线检测 | `services/redline_service.py` | ~120 | 3 类红线规则 |
| 指纹计算 | `services/fingerprint_service.py` | ~80 | 屏幕指纹 SHA256 + Jaccard |
| OmniParser 客户端 | `services/omniparser_client.py` | ~100 | 本地 OmniParser HTTP + 重试 |

### 数据库（7 表，6 Repository）

| 表 | 用途 | 索引 |
|----|------|------|
| `t_users` | 用户账户 | username UNIQUE |
| `t_transactions` | 事务日志 | task_id, timestamp, intent_category |
| `t_step_logs` | 步骤执行日志 | task_id, step_index, status |
| `t_feedback` | 用户反馈 | task_id, feedback_type |
| `t_failures` | 失败记录 | task_id, failure_type, created_at |
| `t_system_configs` | 系统配置 | config_key UNIQUE |
| `t_redline_logs` | 红线拦截日志 | category, action |

### 测试（8 个套件，61 条用例）

| 测试 | 条数 | 覆盖 |
|------|------|------|
| `test_legacy.py` | 8 | 快照回归 |
| `test_perception.py` | 6 | P0 元素感知 |
| `test_intent.py` | 12 | P1 意图分类 |
| `test_replanner.py` | 5 | P2 动态重规划 |
| `test_blueprint.py` | 4 | P3 状态迁移 |
| `test_constraint.py` | 6 | P4 约束提取 |
| `test_redline.py` | 8 | 红线检测 |
| `test_api.py` | 12 | HTTP E2E |

### 文档（8 份）

| 文档 | 路径 |
|------|------|
| A 端 README | `server/README.md` |
| A 端 CHANGELOG | `项目文档/CHANGELOG-A端.md` |
| A 端实施记录 | `server/A_实现优先级.md` |
| API 契约 YAML | `项目文档/a-c-api-contract.yaml` |
| 统一接口文档 | `项目文档/HAJIMI-统一接口文档.md` |
| SeeClick/YOLO 评估 | `项目文档/SeeClick-YOLO-评估报告.md` |
| GPU 部署指南 | `HAJIMI_UI/server/docs/A端-学校GPU部署与联调指南_v2.md` |
| 六天进度 | `工作进度/Day1-6-[A姓名]-[学号].md` |

---

## 三、遗留与待办

| 项 | 状态 | 优先级 | 负责 | 说明 |
|----|------|--------|------|------|
| GroundingDINO 级联补漏 | ❌ 未开始 | P2 | A | 开放词汇检测补充 OmniParser 盲区，8-12h，Demo 后实施 |
| Admin 数据流/监控真实数据 | ⚠️ 部分 Mock | P2 | A | `flow.py` 拓扑硬编码、metrics 随机数 — 需对接真实采集系统 |
| B-C 真实 PyQt5 信号联调 | 就绪待联调 | P1 | B+C | `bc_adapter.py` 已就绪，等 B 接入 |
| PyInstaller 打包（全栈） | 未开始 | P2 | B | 桌面 exe 生成，A 端需配合 .spec 中的模型路径 |
| 性能压测 | ❌ 未开始 | P2 | A | `/process` P99 延迟（不含 LLM）、LLM P95 延迟、高并发场景 |
| 日志持久化 | ❌ 未开始 | P3 | A | 当前仅控制台输出，需 structlog + 文件轮转 + task_id 追踪 |
| PostgreSQL 迁移 | ❌ 未开始 | P3 | A | SQLite → PostgreSQL（生产环境），Alembic 已有 migration 基础 |
| 流式输出 | ❌ 未开始 | P3 | A | LLM streaming 响应（SSE），已在 `client.py` 预留接口 |

---

## 四、六天工作总结

### 代码量统计

| 类别 | 文件数 | 代码行数 |
|------|--------|----------|
| Python 服务端（`server/`） | 35+ | ~4000 |
| 数据库层 | 3 | ~400 |
| 测试 | 8 | ~600 |
| 文档 | 8 | ~3000 |
| **总计** | **55+** | **~8000** |

### 技术栈

| 层级 | 技术选型 |
|------|----------|
| Web 框架 | FastAPI + Uvicorn（Python 3.10+） |
| 数据库 | SQLAlchemy 2.0 ORM + SQLite WAL（Dev）/ PostgreSQL（Prod） |
| LLM 调用 | 多 provider（SiliconCloud Qwen3.6 / DeepSeek / OpenAI / Claude / Ollama）+ OpenAI Vision 多模态格式 |
| 视觉检测 | OmniParser V2（本地 HTTP API）+ PaddleOCR |
| 意图分类 | SetFit（9 类） + keywords fallback |
| 安全 | 红线检测（物理操作/隐私/动态 3 类规则）+ 审计完整链路 |
| 测试 | pytest + HTTP E2E（test_api.py） |

### 关键决策

1. **OmniParser 本地化优先**：从 Replicate 云端 → 本地 GPU 容器部署（`http://127.0.0.1:9800`），延迟可控、无调用次数限制
2. **Strangler Fig 渐进式重构**：不改动旧代码，新模块独立验证后再清理，零 merge conflict
3. **LLM 多 provider 架构**：主备双链路（SiliconCloud → DeepSeek），避免单点故障
4. **Feature Flags 生命周期管理**：每个开关标注过期日期，稳定 2 周后清理
5. **SQLite → PostgreSQL 渐进迁移**：Dev 阶段 SQLite 零配置，Prod 阶段 Alembic 一键迁移

---

## 五、项目复盘

### 完成度：计划 vs 实际

| 模块 | 计划 | 实际 | 完成度 |
|------|------|------|--------|
| FastAPI 框架 | Day 1 | Day 1 ✅ | 100% |
| 数据库设计 | Day 1 | Day 1 ✅ | 100% |
| 意图理解 | Day 2 | Day 2-4 ✅ | 100%（SetFit 9 类） |
| 蓝图规划 | Day 2 | Day 2-3 ✅ | 100%（7 状态） |
| Demo API | Day 1-3 | Day 1-3 ✅ | 100%（7 端点） |
| Admin API | Day 4 | Day 3-4 ✅ | 100%（19+ 端点） |
| LLM 封装 | Day 2 | Day 2-4 ✅ | 100%（5 provider） |
| 红线检测 | Day 4 | Day 4 ✅ | 100% |
| OmniParser 对接 | Day 3 | Day 3 ✅ | 100% |
| 元素感知 | Day 3-4 | Day 3 ✅ | 100% |
| 动态重规划 | Day 3-4 | Day 3 ✅ | 100% |
| 约束提取 | Day 4 | Day 4 ✅ | 100% |
| GroundingDINO | — | ❌ 未开始 | 0%（Demo 后） |
| 全流程验收 | Day 6 | Day 5-6 ✅ | 100% |
| 文档整理 | Day 6 | Day 4-6 ✅ | 100% |

### 做得好的

- **P0-P4 全部按计划完成**，核心 AI 管线从"写死 bbox"到"真实检测+语义绑定"仅用 2 天
- **Strangler Fig 模式**避免了并行开发的 Git 冲突和回滚风险
- **测试护栏**（Day 3 建立的 61 条用例）保证了重构不引入回归
- **A-B-C 三端联调**在 Day 3 即打通第一条端到端链路，远早于计划的 Day 3 PM

### 可改进的

- Day 1-2 的 Mock 端点可更早切换为真实逻辑（部分 Mock 到 Day 3 才替换）
- GroundingDINO 级联排入 Demo 后是合理决策（8-12h 独立任务），但应在 Day 4 提前完成评估
- Admin 数据流/监控端点应与 C 端同步开发时就用真实数据源（而非上线后才替换）

### 下次迭代优先级建议

1. **P2 GroundingDINO 级联** — 开放词汇检测，解决"那个圆圆的像齿轮的东西"这类模糊指代
2. **P2 Admin 数据真实化** — `flow.py`/`monitor.py` 对接真实 Prometheus/Grafana 采集
3. **P2 性能压测与优化** — `/process` 管线 profiling、LLM 缓存、并发支持
4. **P3 流式输出** — LLM streaming SSE 响应
5. **P3 PostgreSQL 迁移** — 生产环境数据库切换
6. **P3 日志持久化** — structlog + 文件轮转

---

## 六、参考文档

- 团队分工：[`设计文档V2.md`](../项目文档/设计文档V2.md) §九
- 六天冲刺计划：[`HAJIMI-六天冲刺计划.md`](../项目文档/HAJIMI-六天冲刺计划.md)
- A 端实施记录：[`server/A_实现优先级.md`](../server/A_实现优先级.md)
- A 端 CHANGELOG：[`项目文档/CHANGELOG-A端.md`](../项目文档/CHANGELOG-A端.md)
- 统一接口文档：[`项目文档/HAJIMI-统一接口文档.md`](../项目文档/HAJIMI-统一接口文档.md)
- A-C 接口契约：[`项目文档/a-c-api-contract.md`](../项目文档/a-c-api-contract.md)
- B 端接口总结：[`项目文档/B端接口总结-对A与对C.md`](../项目文档/B端接口总结-对A与对C.md)
- C 端测试指南：[`工作进度/测试指南.md`](测试指南.md)
- 算法文档：[`项目文档/算法与项目流程说明文档.md`](../项目文档/算法与项目流程说明文档.md)
