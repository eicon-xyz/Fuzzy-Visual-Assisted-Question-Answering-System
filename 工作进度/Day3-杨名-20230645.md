# HAJIMI 第三天工作进度 — 角色 A（后端/AI核心）

**姓名**：[请填写姓名]  
**学号**：[请填写学号]  
**日期**：2026年7月1日  
**角色**：A（后端 / AI核心）

---

## 一、完成任务

### 1. P0 元素感知 — OmniParser 真实检测集成 ✅

**核心改造**：将 process 管线从「写死 bbox 模板」升级为「OmniParser 真实检测 + LLM 语义绑定」。

**涉及文件**：

| 文件 | 改动 | 说明 |
|------|------|------|
| `server/services/perception/serializer.py` | 新建 | `serialize_elements()` — 将 `List[UIElement]` 序列化为 LLM prompt 文本（Top 25 按置信度排序） |
| `server/services/llm/prompt.py` | 新建 | `SYSTEM_PROMPT` 迁移改造 — 增加 `{element_list}` 占位符 + 输出 `target_element_id` + 3 条匹配规则 + 3 个 few-shot 示例；`REPLAN_PROMPT` 用于动态重规划 |
| `server/services/llm/client.py` | 新建 | `call_deepseek(query, elements)` — 迁移自 `llm_ai.py`，增加 elements 参数，`max_tokens` 调至 1500 |
| `server/services/planning/router.py` | 新建 | `generate_steps()` + `process_query()` 新实现 — 语义绑定 `target_element_id`（`element_by_id` 字典查找 + 幻觉 ID 安全 fallback） |

**管线升级前 vs 后**：
```
Upgrade Before:
  query → classify_intent → SCENARIO_ELEMENTS[scenario]（写死） → DeepSeek（不看图）
  → elements[i % len(elements)]（机械循环）

Upgrade After:
  query + image → OmniParser detect() → serialize_elements(elements)
  → SYSTEM_PROMPT.format(element_list=...) → DeepSeek（看图+看元素）
  → element_by_id[target_element_id]（语义匹配）
```

**元素序列化示例**：
```
  ~1: button "下一步" (置信度:0.95)
  ~2: icon "微信图标" (置信度:0.92)
  ~3: text "安装" (置信度:0.88)
  ...
```

### 2. P2 动态重规划 ✅

**背景**：当步骤没有 `target_element_id`（如"等待下载完成"这类概念性步骤），用户移动到新界面后需要重新定位元素。

**涉及文件**：

- `server/models/schemas.py:StepRequest` — 新增可选 `image` 字段（Base64 新截图），向后兼容
- `server/services/planning/replanner.py` — 新建：
  - `REPLAN_PROMPT`：含 `{original_query}`、`{element_list}`、`{upcoming_steps}` 占位符
  - `_serialize_steps_for_replan()`：未绑定步骤序列化
  - `replan_steps()`：筛选未绑定步骤 → 调用 LLM 重规划 → 合并绑定 → LLM 失败返回原步骤不崩溃
- `server/routes/demo.py:/step` — `advance` 分支后插入动态重规划分支：next_step 无 `target_element_id` 且前端传了 `image` → 自动触发

### 3. P3 蓝图状态机补完（7 状态全覆盖）✅

**文件**：`server/services/planning/blueprint_engine.py`（从 `blueprint.py` 迁移并扩展）

**新增迁移路径**：

| 当前状态 | 触发 | 目标状态 | 说明 |
|----------|------|----------|------|
| `suspended` | advance | `executing` | 从挂起恢复执行，当前步骤 active |
| `executing` | suspend | `suspended` | 外部触发挂起（如指纹不匹配） |
| `suspended` | terminate | `terminated` | 挂起中取消任务 |
| `rolling_back` | advance | `executing` | 回退后重新推进 |

**完整 7 状态迁移表**：

| 当前状态 \ 动作 | advance | rollback | skip | terminate | suspend |
|----------------|---------|----------|------|-----------|---------|
| `pending_confirm` | → executing | — | — | → terminated | — |
| `executing` | → executing / completed | → rolling_back | → executing / completed | → terminated | → suspended |
| `suspended` | → executing | — | — | → terminated | — |
| `rolling_back` | → executing | → rolling_back | — | → terminated | — |
| `completed` | — | — | — | — | — |
| `terminated` | — | — | — | — | — |

### 4. `/inspect` 检验端点实现 ✅

**文件**：`server/routes/demo.py`、`server/models/schemas.py`

- `POST /api/demo/inspect`：接收截图 → 调用 OmniParser 全量检测 → 返回 `InspectResponse`（全量 `ui_elements` + SoM 标注图 `annotated_image`）
- 不创建任务（区别于 `/process`）
- B 端用于「立即检测当前屏幕」和设置页预检
- 超时 360s（兼容 GPU 容器大图检测）

### 5. `/relocate` 重定位端点实现 ✅

**文件**：`server/routes/demo.py`（路由）、`server/services/planning/router.py`（`relocate_step` 函数）、`server/models/schemas.py`（`RelocateRequest`/`RelocateResponse`）

- `POST /api/demo/relocate`：用户手动操作后重截图 → OmniParser 解析 → LLM 匹配目标元素 → 更新步骤的 `target_element_id` + `annotation`
- LLM 失败降级为文本关键词匹配（`_RELOCATE_KEYWORD_FALLBACK`）
- B 端「我已完成，重新定位」PrepareStep 功能依赖此端点

### 6. Demo API 全端点就位 ✅

Demo 路由 `/api/demo/*` 全部 7 个端点实现完毕：

| # | 端点 | 说明 | 状态 |
|---|------|------|------|
| 1 | GET `/api/demo/health` | 健康检查 + OmniParser 探测 | ✅ |
| 2 | POST `/api/demo/process` | 核心流程（意图+检测+规划+标注） | ✅ 真实管线 |
| 3 | POST `/api/demo/inspect` | 仅检测 UI 元素 | ✅ 新增 |
| 4 | POST `/api/demo/step` | 步骤推进/回退/跳过/终止 + 重规划 | ✅ 完整状态机 |
| 5 | POST `/api/demo/relocate` | 重定位目标元素 | ✅ 新增 |
| 6 | POST `/api/demo/clarify` | 澄清应答 | ✅ Mock→真实 |
| 7 | POST `/api/demo/report` | 审计/反馈上报 | ✅ 对接数据库 |

### 7. 代码重构 — Strangler Fig 路由 ✅

**文件**：`server/services/llm_ai.py`

采用绞杀榕（Strangler Fig）模式保证不破坏旧逻辑：

```python
# feature flags 路由（config.py）
USE_ELEMENT_PERCEPTION = true   # P0 元素感知
USE_DYNAMIC_REPLANNING = false  # P2（灰度开启）
USE_SETFIT_INTENT = false       # P1（待 Day 4）
USE_CONSTRAINT_EXTRACTION = false  # P4（待 Day 4）
```

- 新模块独立在 `services/perception/`、`services/llm/`、`services/planning/` 下
- `llm_ai.py` 入口只做路由转发，旧 `_legacy_*` 函数保留不动
- P0/P2/P3 测试全部通过后逐步关闭 feature flags → 切换为新逻辑

### 8. Service API 扩展 — 审计/配置/认证端点 ✅

按 a-c-api-contract.md 实现 A-C 接口端点：

**审计端点**（`server/routes/audit.py`）：
- `POST /api/audit/report`：批量审计上报（`{client_id, batch: [AuditRecord]}`）→ 写入 `t_transactions` → 幂等去重（已存在 task_id 跳过）
- `POST /api/audit/feedback`：用户反馈上报（`{task_id, feedback_type, comment}`）→ 写入 `t_feedback`

**配置端点**（`server/routes/config_client.py`）：
- `GET /api/config/pull`：客户端配置拉取 → ETag 304 支持 → 默认配置为空时返回预设值

**认证端点**（`server/routes/auth.py`）：
- `POST /api/auth/login`：Demo 模式 JWT 签发（base64 编码，非标准 JWS）→ 首次登录自动创建用户

---

## 二、新增/变更文件

```
server/
├── models/
│   └── schemas.py               # 变更：StepRequest +image, RelocateRequest/Response, InspectRequest/Response
├── routes/
│   ├── demo.py                  # 变更：+inspect +relocate +重规划分支
│   ├── audit.py                 # 新增：审计批量上报 + 反馈
│   ├── config_client.py         # 新增：客户端配置拉取
│   └── auth.py                  # 新增：JWT 登录
├── services/
│   ├── perception/
│   │   └── serializer.py        # 新增：UI 元素 → LLM prompt 序列化
│   ├── llm/
│   │   ├── prompt.py            # 新增：SYSTEM_PROMPT + REPLAN_PROMPT
│   │   └── client.py            # 新增：多 provider LLM 客户端
│   └── planning/
│       ├── router.py            # 新增：步骤生成 + ProcessResponse 组装 + relocate
│       ├── replanner.py         # 新增：动态重规划
│       └── blueprint_engine.py  # 新增：7 状态蓝图状态机（从 blueprint.py 迁移）
└── tests/
    ├── conftest.py              # 新增：共享 fixtures
    ├── test_legacy.py           # 新增：老代码快照测试
    ├── test_perception.py       # 新增：P0 6 条用例
    ├── test_replanner.py        # 新增：P2 5 条用例
    └── test_blueprint.py        # 新增：P3 4 条用例
```

---

## 三、验证结果

| 测试 | 项目数 | 结果 |
|------|--------|------|
| `test_perception.py` | 6 | 6/6 ✅ |
| `test_replanner.py` | 5 | 5/5 ✅ |
| `test_blueprint.py` | 4 | 4/4 ✅ |
| `test_legacy.py`（快照） | 8 | 8/8 ✅ |
| `test_api.py`（E2E） | 4 | 4/4 ✅ |
| Demo 端点 | 7 | 全部 ✅ |
| 审计/配置/认证端点 | 4 | 全部 ✅ |
| A-B 检验模式联调 | inspect + relocate | ✅ |

**P0 元素感知验收**：
| # | 场景 | 结果 |
|---|------|------|
| 1 | "点击下载按钮" + 含 ~1-~3 元素的截图 | Step 有 target_element_id: "~2"，annotation 非空 ✅ |
| 2 | "等待下载完成"（概念性步骤） | target_element_id 为空，无崩溃 ✅ |
| 3 | 无截图模式 | fallback mock 步骤 ✅ |
| 4 | LLM 幻觉 ID "~99" | 安全降级 None ✅ |
| 5 | USE_REAL_LLM=false | mock 步骤含预定义 target_element_id ✅ |

**P2 动态重规划验收**：
| # | 场景 | 结果 |
|---|------|------|
| 1 | next_step 无 target_element_id + 带 image | 重规划成功，新元素绑定 ✅ |
| 2 | 新截图仍无匹配 | target_element_id 保持空，不崩溃 ✅ |
| 3 | rollback 不触发重规划 | 正确跳过 ✅ |
| 4 | 不带 image 不触发 | 行为一致 ✅ |

**P3 状态机验收**：
| # | 场景 | 结果 |
|---|------|------|
| 1 | suspended → advance | 恢复 executing ✅ |
| 2 | executing → suspend | 状态变 suspended ✅ |
| 3 | suspended → terminate | 状态变 terminated ✅ |
| 4 | confirmed → advance | 第一步 active ✅ |

---

## 四、遗留问题

1. **SetFit 意图分类器待训练**（P1）：当前仍为关键词规则，9 域覆盖不全
2. **约束条件提取待实现**（P4）：LLM prompt 需增加约束抽取指令 + `ProcessResponse.constraints` 字段
3. **所有 feature flags 目前 P0/P2 已开启，P1/P4 待 Day 4 实现**：全量切换后需清理旧 legacy 逻辑
4. **Admin 统计端点待实现**：管理面板需 `/api/admin/*` 系列端点
5. **GroundingDINO 级联**未开始（P2 低优先级）
6. **B 端重定位 PrepareStep UI 依赖 `/relocate`**：端点已就绪，B 端接入后联调

---

## 五、下一步计划（Day 4）

- **P1 SetFit 意图分类**：训练脚本 + 模型集成 + keywords fallback
- **P4 约束条件提取**：LLM prompt 改造 + schemas 扩展
- **Admin API 全套端点**：统计总览/趋势/失败归因/数据流/监控/配置/告警
- **LLM 管线升级**：DeepSeek → Qwen3.6 多模态（SiliconCloud）
- **全量 feature flags 开启** + 回归测试
- A-C 联调（审计/配置端点）
