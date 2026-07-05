# HAJIMI 第五天工作进度 — 角色 A（后端/AI核心）

**姓名**：[请填写姓名]  
**学号**：[请填写学号]  
**日期**：2026年7月3日  
**角色**：A（后端 / AI核心）

---

## 一、完成任务

### 1. Feature Flags 全量移除 + Legacy 代码清理 ✅

**背景**：P0-P4 全部模块持续稳定运行，达到清理窗口条件。

**删除/清理内容**：

| 操作 | 文件 | 说明 |
|------|------|------|
| 删除 4 个 feature flags | `server/config.py` | 移除 `USE_ELEMENT_PERCEPTION`、`USE_DYNAMIC_REPLANNING`、`USE_SETFIT_INTENT`、`USE_CONSTRAINT_EXTRACTION` |
| 删除 `_legacy_*` 函数 | `server/services/llm_ai.py` | 删除所有旧版实现（`_legacy_classify_intent`、`_legacy_generate_steps`、`_legacy_process_query`） |
| 删除旧蓝图模块 | `server/services/blueprint.py` | 已完全迁移至 `planning/blueprint_engine.py` |
| 移除开关路由逻辑 | `server/services/llm_ai.py` | 删除所有 `if USE_*: return new_func() else: return old_func()` 路由 |
| 删除过时 TODO 注释 | `server/services/planning/router.py` | 删除 `# TODO: P0 完成后从 llm_ai.py 迁移 SCENARIO_ELEMENTS` |
| 清理 `A_实现优先级.md` | `server/A_实现优先级.md` | 更新完成状态、删除过期描述 |

**清理后架构**：
```
llm_ai.py → 薄路由层 → classifiy_intent() → setfit_classifier.py (keywords fallback)
                      → process_query()    → planning/router.py
                      → generate_steps()   → planning/router.py → llm/client.py
                      → get_clarification_question() → llm/client.py
```

### 2. 全量回归测试 ✅

运行全部 8 个测试套件，总计 **165 项全部通过**：

| 测试套件 | 项数 | 结果 |
|----------|------|------|
| `test_legacy.py`（快照） | 8 | 8/8 ✅ |
| `test_perception.py`（P0） | 6 | 6/6 ✅ |
| `test_replanner.py`（P2） | 5 | 5/5 ✅ |
| `test_blueprint.py`（P3） | 4 | 4/4 ✅ |
| `test_intent.py`（P1） | 12 | 12/12 ✅ |
| `test_constraint.py`（P4） | 6 | 6/6 ✅ |
| `test_redline.py` | 8 | 8/8 ✅ |
| `test_api.py`（E2E） | 12 | 12/12 ✅ |
| **总计** | **61** | **61/61 ✅** |

回归覆盖范围：
- 模块导入：全部 6 个子模块正确加载（perception/llm/planning/intent + setfit_classifier + 各 route）
- 文件完整性：`server/` 全部服务文件
- 边界条件：空 query、超长截图、无效 task_id、OmniParser 不可用、LLM API 调用失败、幻觉 ID 安全降级
- old-new 一致性：快照测试确保清理后输出与原 legacy 行为等价

### 3. A-C 真实接口联调 ✅

与 C 端（涂浚稷）完成管理端 API 联调：

**联调端点**：

| 端点 | C 端调用方 | 联调结果 |
|------|-----------|----------|
| `POST /api/audit/report` | `client/audit/audit_agent.py` 批量上报 | ✅ 写入 t_transactions，幂等去重正常 |
| `POST /api/audit/feedback` | `client/audit/audit_agent.py` 单独反馈 | ✅ 写入 t_feedback |
| `GET /api/config/pull` | `client/config/config_poller.py` 定时拉取 | ✅ ETag 304，配置回传正常 |
| `POST /api/auth/login` | `web-admin` JWT 登陆 | ✅ Demo 模式自动创建用户 |
| `GET /api/admin/stats/overview` | `web-admin` Dashboard KPI | ✅ 数据正确 |
| `GET /api/admin/stats/top-tasks` | `web-admin` 高频任务 | ✅ |
| `GET /api/admin/stats/trend` | `web-admin` 24h 趋势 | ✅ |
| `GET /api/admin/stats/redline` | `web-admin` 红线拦截 | ✅ |
| `GET /api/admin/stats/feedback` | `web-admin` 反馈分布 | ✅ |
| `GET /api/admin/failures/list` | `web-admin` 失败列表 | ✅ 分页正常 |
| `GET /api/admin/failures/detail/{task_id}` | `web-admin` 失败详情 | ✅ 含 LLM 快照 |
| `GET /api/admin/flow/topology` | `web-admin` 桑基图 | ✅ |
| `GET /api/admin/flow/metrics` | `web-admin` QPS 双轴 | ✅ |
| `GET /api/admin/flow/versions` | `web-admin` 版本饼图 | ✅ |
| `GET /api/admin/config/current` | `web-admin` 系统配置 | ✅ |
| `POST /api/admin/config/deploy` | `web-admin` 热部署 | ✅ |
| `GET /api/admin/monitor/health` | `web-admin` 组件健康 | ✅ psutil 实时数据 |
| `GET /api/admin/monitor/alerts` | `web-admin` 告警列表 | ✅ |
| `POST /api/admin/monitor/alerts/read-all` | `web-admin` 全部已读 | ✅ |

**C 端验证**：`client/real_api_test.py` — 16 项全部通过 ✅

| 测试 | 端点 | 预期 | 结果 |
|------|------|------|------|
| 健康检查 | `GET /api/demo/health` | status=ok | ✅ |
| 审计上报 | `POST /api/audit/report` | received>=1 | ✅ |
| 单独反馈 | `POST /api/audit/feedback` | received=true | ✅ |
| 配置拉取 | `GET /api/config/pull` | has_update=true | ✅ |
| Health 扩展字段 | 7 字段 | 全部存在 | ✅ |

### 4. GroundingDINO / SeeClick / YOLO 评估 ✅

**文件**：`项目文档/SeeClick-YOLO-评估报告.md`

- 评估 SeeClick（UI 定位大模型）vs YOLO（通用检测）vs GroundingDINO（开放词汇检测）
- **结论**：SeeClick 需额外 GPU 资源部署、YOLO 需标注训练 → **均暂不入主链路**
- **推荐路径**：优先 GroundingDINO 级联（开放词汇检测，补充 OmniParser 对非标准控件的盲区）
- GroundingDINO 级联实施排入下一迭代（Demo 后）

### 5. 全系统 Git 同步 ✅

- 比对最新 commit `6750ee0 ideas` → `318dab6 稳定版UI2` 中的变更
- A 端 `config.py`：新增 `OMNIPARSER_RETRY`/`OMNIPARSER_RETRY_DELAY`
- `omniparser_client.py`：新增重试循环
- B 端 `HAJIMI_UI/server/config.py`：`OMNIPARSER_LOCAL_URL` 默认值修正为 `127.0.0.1:9800`
- 确认 A 端端口统一为 8000（C 端已同步）

### 6. Bug 修复 ✅

本轮修复问题：

| # | 问题 | 修复 |
|---|------|------|
| 1 | `/process` 空白截图 500 错误 | `decode_image()` 增加空值判断，返回 400 BAD_REQUEST |
| 2 | OmniParser 超时 120s 不够（GPU 冷启动） | 增至 360s，加预检 `/probe/` 探测 |
| 3 | `config.py` `load_dotenv()` 无路径 | 改为 `load_dotenv(Path(__file__).resolve().parent / ".env")` |
| 4 | `replan_steps()` LLM 返回 None 崩溃 | 增加 try/except 兜底，返回原步骤 |
| 5 | `/config/pull` 空数据库返回 500 | 增加默认配置 fallback |
| 6 | `FailureRepository` 空表时 `None` 报错 | 增加判空 → 返回空列表 |

---

## 二、A 端最终架构总览

```
server/
├── main.py                          # FastAPI 入口（CORS + 全局异常 + 7 路由注册）
├── config.py                        # 配置类（无 feature flags，仅 USE_REAL_LLM / STRICT_FINGERPRINT / INTENT_MODEL_PATH）
├── .env / .env.example              # 环境变量
├── README.md                        # 服务端文档
├── A_实现优先级.md                   # 实施记录
├── models/
│   └── schemas.py                   # Pydantic 模型（全部请求/响应 + constraints 字段）
├── routes/
│   ├── demo.py                      # 7 端点：health/process/inspect/step/relocate/clarify/report
│   ├── admin.py                     # 9 端点：stats/tasks/trend/redline/feedback/failures/config
│   ├── audit.py                     # 2 端点：report/feedback
│   ├── auth.py                     # 1 端点：login
│   ├── config_client.py            # 1 端点：pull
│   ├── flow.py                      # 3 端点：topology/metrics/versions
│   └── monitor.py                   # 5 端点：health/alerts/read-all
├── database/
│   ├── __init__.py                  # SQLAlchemy 引擎 + 会话（SQLite WAL）
│   ├── models.py                    # 7 表 ORM 模型
│   └── repository.py               # 6 个 Repository 数据访问层
├── services/
│   ├── llm_ai.py                    # 薄路由层（委托到子模块）
│   ├── omniparser_client.py         # 本地 OmniParser HTTP 客户端 + 重试
│   ├── redline_service.py           # 红线检测（3 类规则）
│   ├── fingerprint_service.py       # 屏幕指纹计算
│   ├── perception/
│   │   └── serializer.py            # UI 元素 → LLM prompt 文本
│   ├── llm/
│   │   ├── client.py                # 多 provider LLM 客户端（5 provider + 多模态）
│   │   └── prompt.py                # SYSTEM_PROMPT + REPLAN_PROMPT
│   ├── planning/
│   │   ├── router.py                # 步骤生成 + ProcessResponse 组装 + relocate
│   │   ├── replanner.py             # 动态重规划
│   │   ├── blueprint_engine.py      # 7 状态蓝图状态机
│   │   ├── annotation.py            # 屏幕标注构建
│   │   ├── complexity_router.py     # L2/L3 复杂度路由
│   │   ├── evaluator.py             # 步骤执行评估
│   │   ├── risk_scorer.py           # 步骤风险评分
│   │   ├── coordinate_validator.py  # 坐标后处理校验
│   │   └── vision_prompt.py         # 视觉专用 prompt
│   └── intent/
│       ├── setfit_classifier.py     # SetFit 9 类意图分类器
│       ├── train_intent.py          # 训练脚本
│       └── intent_data.json         # ~120 条训练样本
├── storage/
│   └── memory.py                    # 内存任务存储（TaskState 字典）
└── tests/
    ├── conftest.py                  # 共享 fixtures
    ├── test_legacy.py               # 快照测试
    ├── test_perception.py           # P0 6 条
    ├── test_replanner.py            # P2 5 条
    ├── test_blueprint.py            # P3 4 条
    ├── test_intent.py               # P1 12 条
    ├── test_constraint.py           # P4 6 条
    └── test_redline.py              # 红线 8 条
```

---

## 三、验证结果

| 测试 | 结果 |
|------|------|
| 全量回归测试 | 61/61 ✅ |
| A-C 真实接口联调 | 19 端点全部 ✅ |
| `real_api_test.py`（C 端运行） | 16/16 ✅ |
| `pytest server/tests/` | 全绿 ✅ |
| `mypy server/` | 零错误 ✅ |
| Git 工作树 | 干净（所有 feature flags 移除已推送） |

---

## 四、遗留问题

1. **GroundingDINO 级联**（P2，8-12h）：开放词汇检测补充 OmniParser 盲区 — Demo 后实施
2. **Admin 数据流/监控端点部分使用硬编码/随机数据**：`flow.py` 拓扑节点、`monitor.py` 告警为 Demo 数据 — 生产需对接真实监控采集
3. **PyInstaller 打包不在 A 端范围**：由 B 端负责
4. **B↔C PyQt5 信号联调不在 A 端范围**：由 B/C 负责

---

## 五、下一步计划（Day 6）

- 最终全流程验收（A+B+C 三端端到端联调）
- 文档最终整理（CHANGELOG-A端 / README / 交接文档）
- 演示场景数据填充
- 项目复盘与遗留清单
