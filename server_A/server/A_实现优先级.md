# A — 服务端实现优先级

> 面向成员 A（后端 / AI 核心），基于当前 `server/` 代码实际状态，将三份设计文档（设计文档V2、优先级路线图、元素感知实施计划）映射为可逐条执行的具体改动清单。
>
> 外部依赖标注：凡涉及 `HAJIMI_UI/` 的改动，标注 **「需 B/C 配合」**，不在本文档范围内。

---

## 完成状态（2026-07-01）

| 批次 | 任务 | 状态 | 合并提交 |
|------|------|------|----------|
| 0 | 测试护栏 + 模块骨架 | ✅ 已完成 | `d353aa31` |
| 1 | P0 元素感知 | ✅ 已完成并合并 | `38d0c645` |
| 2 | P2 动态重规划 | ✅ 已完成并合并 | `b5c14139` |
| 3 | P3 蓝图状态机补完 | ✅ 已完成并合并 | `7c945388` |
| 4 | P1 SetFit 意图分类 | ✅ 已完成并合并 | `1535489a` |
| 5 | P4 约束条件提取 | ✅ 已完成并合并 | `0c6a7ed7` |
| 6 | 全量切换 + 旧代码清理 | ✅ 已完成 | `3b2838db` |

**说明**：所有 feature flags（`USE_ELEMENT_PERCEPTION`、`USE_DYNAMIC_REPLANNING`、`USE_SETFIT_INTENT`、`USE_CONSTRAINT_EXTRACTION`）已移除，旧 `_legacy_*` 逻辑与 `services/blueprint.py` 已删除。已推送至 `origin/main`（2026-07-01）。

---

## 当前代码实际状态（2026-07-01 审查）

### 已实现文件清单

```
server/
├── main.py                         # FastAPI 入口 + CORS + 全局异常
├── config.py                       # 配置（无 feature flags，仅 USE_REAL_LLM / STRICT_FINGERPRINT / INTENT_MODEL_PATH）
├── models/schemas.py               # Pydantic 模型（含 constraints 字段）
├── routes/demo.py                  # 5 个路由：health / process / step / clarify / report
├── services/
│   ├── llm_ai.py                   # 兼容入口，所有实现已迁移到子模块
│   ├── omniparser_client.py        # 本地 OmniParser HTTP 客户端
│   ├── perception/serializer.py    # UI 元素序列化
│   ├── llm/
│   │   ├── client.py               # DeepSeek 调用（支持 elements 参数）
│   │   └── prompt.py               # SYSTEM_PROMPT + REPLAN_PROMPT
│   ├── planning/
│   │   ├── router.py               # 步骤生成 + 约束提取 + ProcessResponse 组装
│   │   ├── replanner.py            # 动态重规划
│   │   └── blueprint_engine.py     # 蓝图状态机（7 状态全覆盖）
│   └── intent/
│       ├── setfit_classifier.py    # SetFit 意图分类器（含 keywords fallback）
│       └── train_intent.py         # 训练脚本
├── storage/memory.py               # 内存任务存储
└── tests/
    ├── conftest.py                 # 共享 fixtures
    ├── test_legacy.py              # 老代码快照
    ├── test_perception.py          # P0：元素感知（6 条用例）
    ├── test_replanner.py           # P2：动态重规划（5 条用例）
    ├── test_blueprint.py           # P3：状态迁移（4 条用例）
    ├── test_intent.py              # P1：意图分类
    └── test_constraint.py          # P4：约束提取（6 条用例）
```

### 已删除文件

| 文件 | 说明 |
|------|------|
| `services/blueprint.py` | 迁移至 `services/planning/blueprint_engine.py` |
| `llm_ai.py` 中所有 `_legacy_*` 函数 | 旧实现已清除 |
| `config.py` 中 4 个 `USE_*` feature flags | 已移除 |

---

## 十五、A 未完成任务清单

> 基于 2026-07-01 对 `server/` 代码与 `项目文档/` 的交叉审查。

### 🔴 P0 紧急 — 缺失端点

#### 15.1 `POST /api/demo/relocate` 端点未实现

**来源**：[B端接口总结-对A与对C.md](../项目文档/B端接口总结-对A与对C.md) §3.2 将 `/relocate` 列为 A 端已有端点，B 端已实现 `core/relocate_worker.py` 并预期此端点可用。

**当前状态**：`server/routes/demo.py` 仅有 5 个路由（health/process/step/clarify/report），无 relocate。

**B 端期望请求**：
```json
{
  "task_id": "550e8400-...",
  "step_index": 2,
  "image": "data:image/png;base64,..."
}
```

**B 端期望响应**：更新当前步的 `annotation`、`target_element_id`、`ui_elements`。

**影响**：B 端的「我已完成，重新定位」PrepareStep banner 功能无法工作。

**预估工时**：2-3h

**涉及文件**：
- `models/schemas.py` — 新增 `RelocateRequest` / `RelocateResponse`
- `routes/demo.py` — 新增 `/relocate` 路由
- `services/planning/` — 新增定位逻辑（调用 OmniParser + LLM 绑定）

---

### 🟡 P1 高 — 文档与接口债务

#### 15.2 `server/README.md` 全面过时

| 行 | 当前过时内容 | 应更新为 |
|----|-------------|---------|
| 93 | `services/llm_ai.py` — 描述为"AI 推理服务" | 说明实际已迁移到 `perception/`、`llm/`、`planning/`、`intent/` |
| 94 | `services/blueprint.py` | 已删除，替换为 `planning/blueprint_engine.py` |
| 103 | "UI 元素坐标由规则生成，步骤文案由 LLM 生成" | OmniParser 真实检测 + LLM 语义绑定 |
| 端点表 | 仅列 5 个端点 | 补充 `/inspect`（待实现） |
| 环境变量表 | 缺少 `OMNIPARSER_URL`、`INTENT_MODEL_PATH` 等 | 与 `config.py` 和 `.env.example` 对齐 |

**预估工时**：0.5h

#### 15.3 `router.py:20` 过时 TODO 注释

**文件**：[server/services/planning/router.py:20](server/services/planning/router.py#L20)

```python
# TODO: P0 完成后从 llm_ai.py 迁移完整 SCENARIO_ELEMENTS
```

`llm_ai.py` 已无 `SCENARIO_ELEMENTS`，此 TODO 已完成，应删除。

**预估工时**：1 分钟

#### 15.4 CHANGELOG-A端.md 待办项（3 条未勾选）

**文件**：[项目文档/CHANGELOG-A端.md](../项目文档/CHANGELOG-A端.md#L438-L444)

- [ ] `server/README.md` 更新为 OmniParser 描述（⚠ 同 §15.2）
- [ ] SeeClick / YOLO 评估
- [ ] `ProcessResponse` 的 `reference_resolution` 写入 OpenAPI example

**预估工时**：README 0.5h + 评估 2-4h + YAML 0.5h

#### 15.5 `A_实现优先级.md` 第 21 行过期描述

"需手动 push" — 已于 2026-07-01 推送完毕，本次已修正。

---

### 🟢 P2 中 — 新功能

#### 15.6 GroundingDINO 级联补漏

**来源**：[参考方案优先级与实施路线图.md](../项目文档/参考方案优先级与实施路线图.md) P2

**问题**：当用户说"那个圆圆的像齿轮的东西"时，OmniParser 检测不到（它只识别标准 UI 控件）。GroundingDINO 能做开放词汇检测。

**改动范围**：
- 部署 GroundingDINO checkpoint
- 在 `omniparser_client.py` 中加级联：OmniParser 置信度 < 阈值 → 触发 GroundingDINO
- 元素合并去重逻辑

**风险**：中高。引入 GPU 依赖和级联复杂度。

**预估工时**：8-12h

#### 15.7 A-C 管理端 API（~18 个端点）

**来源**：[a-c-api-contract.md](../项目文档/a-c-api-contract.md)

以下端点在契约中定义但 `server/` 中**均未实现**：

| 分类 | 端点 | 数量 |
|------|------|------|
| 审计 | `/api/audit/report`、`/api/audit/feedback` | 2 |
| 配置 | `/api/config/pull`、`/api/admin/config/current`、`/api/admin/config/deploy` | 3 |
| 管理总览 | `/api/admin/stats/overview`、`/trend`、`/feedback`、`/top-tasks`、`/redline` | 5 |
| 失败归因 | `/api/admin/failures/stats`、`/list`、`/detail/{task_id}` | 3 |
| 数据流 | `/api/admin/flow/topology`、`/metrics`、`/versions` | 3 |
| 健康监控 | `/api/admin/monitor/health`、`/alerts` | 2 |
| 系统 | `/api/auth/login` | 1 |

**说明**：这些属于管理控制台后端，按 [六天冲刺计划](../项目文档/HAJIMI-六天冲刺计划.md) 原定 Day 4 完成，当前 Demo 阶段可暂缓。

**预估工时**：多天（需数据库迁移 + 全部 API + 测试）

---

### 📊 汇总

| # | 任务 | 优先级 | 工时 | 类型 |
|---|------|--------|------|------|
| 15.1 | `/relocate` 端点实现 | ✅ 已完成 | — | 已实现 + 切到 Qwen3.6 |
| 15.2 | `README.md` 更新 | ✅ 已完成 | — | 2026-07-02 全面重写 |
| 15.3 | `router.py:20` TODO 删除 | ✅ 已完成 | — | 已清理 |
| 15.4 | CHANGELOG-A端 待办项 | ✅ README+relocate 已完成，SeeClick/YOLO 评估仍待做 | — | 见下方路线图 |
| 15.5 | A_实现优先级 过期描述 | ✅ 已修正 | — | 文档 |
| 15.6 | GroundingDINO 级联补漏 | 🟢 P2 | 8-12h | 新功能 |
| 15.7 | A-C 管理端 API | 🟢 P2 | 多天 | 新功能 |
| 15.8 | LLM 管线升级 | ✅ 已完成 | — | 迁移至 Qwen3.6 多模态（SiliconCloud），3 条 LLM 调用路径全部统一 |

> **注**：P0-P4 核心 AI 功能（元素感知、意图分类、蓝图状态机、动态重规划、约束提取、旧代码清理）已全部完成并合并至 main。2026-07-02 完成 LLM 管线升级（DeepSeek → Qwen3.6 多模态，SiliconCloud），`/relocate` 端点已实现，README 和 `.env.example` 已同步更新。剩余长期工作：GroundingDINO 级联、A-C 管理端 API、SeeClick/YOLO 评估。

---

## 一、现状速查（7 个缺陷 → 设计文档对应）

| # | 缺陷 | 位置 | 对应文档 |
|---|------|------|---------|
| ① | LLM 制定计划时看不到 UI 元素列表 | `llm_ai.py:186` `call_deepseek()` 不接收 elements | 设计文档V2 §6.8；实施计划 §三 |
| ② | 步骤-元素绑定为 `elements[i % len(elements)]` 机械循环 | `llm_ai.py:325` | 实施计划 §1.2 断裂点 ② |
| ③ | `Step.target_element_id` 已存在于 Schema，但从未被 LLM 填充 | `schemas.py:70`；`llm_ai.py:336` 硬编码赋值 | 实施计划 §1.3 |
| ④ | 意图分类是 6 行 if-else 关键词匹配，置信度硬编码 | `llm_ai.py:95-113` `classify_intent()` | 优先级路线图 P1 |
| ⑤ | 蓝图状态机缺少异常迁移路径（timeout→suspended、cancel→terminated） | `blueprint.py` 仅 4 条基本路径 | 优先级路线图 P3 |
| ⑥ | `StepRequest` 缺少 `image` 字段，无法支持动态重规划 | `schemas.py:134` | 实施计划 §4.3.1 |
| ⑦ | `/step` 路由无重规划分支 | `demo.py:82-160` | 实施计划 §4.3.2 |

---

## 二、实施顺序总览（Strangler Fig + 测试优先）

> 多 Agent 并行开发的第一原则是：**不破坏、不阻塞、先验证、后删除**。
> 因此不直接拆分 `llm_ai.py`，而是采用 **Strangler Fig（绞杀榕）模式**：先新建模块，通过特性开关路由转发，等新模块单测覆盖率和集成测试都通过后再删除旧逻辑。

```
第 0 天 ── 测试护栏 + 模块骨架 (2h) ───────────────────────────────┐
│   1. 创建 server/tests/ 目录                                      │
│   2. 给 classify_intent / generate_steps / process_query 补快照测试│
│   3. 在 server/services/ 下新建 perception/ planning/ intent/    │
│   4. llm_ai.py 只加 __init__ 路由，不动旧逻辑                     │
└──────────────────────────────────────────────────────────────────┤
                                                                  │
第 1 批 ── P0 元素感知 (4h) ──────────────────────────────────────┤
│   perception/serializer.py: _serialize_elements                  │
│   llm/prompt.py: SYSTEM_PROMPT（带元素列表 + target_element_id）  │
│   llm/client.py: call_deepseek(elements=...)                     │
│   planning/router.py: generate_steps 新实现                      │
│   llm_ai.py 入口：if USE_ELEMENT_PERCEPTION: 走新逻辑             │
│   测试：6 条 P0 用例                                             │
└──────────────────────────────────────────────────────────────────┤
                                                                  │
第 2 批 ── P2 动态重规划-后端 (4h) ───────────────────────────────┤
│   schemas.py: StepRequest + image 字段                           │
│   planning/replanner.py: REPLAN_PROMPT + replan_steps()         │
│   demo.py: /step 路由增加重规划分支                               │
│   llm_ai.py 入口：if USE_DYNAMIC_REPLANNING: 走新逻辑             │
│   测试：5 条 P2 用例                                             │
└──────────────────────────────────────────────────────────────────┤
                                                                  │
第 3 批 ── 可并行 ────────────────────────────────────────────────┤
│   P3 状态机补完 (2-3h) ── planning/blueprint_engine.py ──────── │
│   P1 SetFit 意图分类 (4-6h) ── intent/setfit_classifier.py     │
│   P4 约束条件提取 (3-4h) ── planning/router.py + schemas.py    │
└──────────────────────────────────────────────────────────────────┤
                                                                  │
第 4 天 ── 切换与清理 (2h) ───────────────────────────────────────┤
│   全量开启 USE_* 开关，跑全部回归测试                             │
│   测试全绿后，删除 llm_ai.py 中的旧逻辑                           │
│   删除 USE_ELEMENT_PERCEPTION / USE_DYNAMIC_REPLANNING 开关       │
└──────────────────────────────────────────────────────────────────┘
```

| 顺序 | 任务 | 工时 | 前置 | 改动文件 |
|------|------|------|------|---------|
| **0** | 测试护栏 + 模块骨架 | 2h | 无 | `server/tests/`（新目录）、`llm_ai.py`（仅路由） |
| **1** | P0 元素感知 | 3-4h | 0 | `services/perception/`, `services/llm/`, `llm_ai.py` |
| **2** | P0 单元测试 | 1h | 1 | `server/tests/test_perception.py` |
| **3** | P2 动态重规划（后端） | 3-4h | 1 | `services/planning/replanner.py`, `schemas.py`, `demo.py` |
| **4** | P3 状态机补完 | 2-3h | 0 | `services/planning/blueprint_engine.py` |
| **5** | P1 SetFit 意图分类 | 4-6h | P0 完成后可启动 | `services/intent/`, `llm_ai.py` |
| **6** | P4 约束条件提取 | 3-4h | P1 后效果更好 | `services/planning/router.py`, `schemas.py` |
| **7** | 全量切换 + 旧代码清理 | 2h | 1-6 稳定 | `llm_ai.py`（删除旧逻辑） |
| **合计** | | **18-26h** | | |

---

## 三、P0 元素感知 — 逐函数改动清单

> 目标：LLM 在生成步骤时能看到 OmniParser 输出的 UI 元素列表，按语义而非机械循环绑定元素。

### 3.1 新增 `services/perception/serializer.py`

**文件**：`server/services/perception/serializer.py`（新建）

```python
from typing import List
from server.models.schemas import UIElement


def serialize_elements(elements: List[UIElement], max_count: int = 25) -> str:
    """将 UI 元素列表序列化为 LLM prompt 文本"""
    if not elements:
        return "（未检测到 UI 元素）"

    sorted_els = sorted(elements, key=lambda e: e.confidence, reverse=True)[:max_count]
    lines = []
    for e in sorted_els:
        text = e.text.strip() if e.text else "(无文本)"
        lines.append(
            f"  {e.element_id}: {e.element_type} \"{text}\" (置信度:{e.confidence:.2f})"
        )
    return "\n".join(lines)
```

**改动量**：约 15 行新增

### 3.2 新增 `services/llm/prompt.py`

**文件**：`server/services/llm/prompt.py`（新建）

将当前 `llm_ai.py:166-183` 的 `SYSTEM_PROMPT` 迁移至此，并改造为包含元素占位符、输出格式、匹配规则和 3 个 few-shot 示例的新 prompt。

**关键变化**：
- 增加 `{element_list}` 占位符
- 输出 JSON 增加 `target_element_id` 字段
- 增加 3 条匹配规则 + 3 个 few-shot 示例
- `max_tokens` 从 1000 调至 1500

**完整内容见**：`项目文档/LLM元素感知与动态重规划实施计划.md` §3.3

**改动量**：约 80 行新增

### 3.3 新增 `services/llm/client.py`

**文件**：`server/services/llm/client.py`（新建）

将 `llm_ai.py:186-218` 的 `call_deepseek()` 迁移至此，并增加 `elements` 参数：

```python
def call_deepseek(
    query: str,
    elements: Optional[List[UIElement]] = None,
    timeout: int = 30,
) -> Optional[List[dict]]:
    if not settings.DEEPSEEK_API_KEY:
        return None

    element_text = serialize_elements(elements)
    prompt = SYSTEM_PROMPT.format(element_list=element_text)

    # ... 原有 HTTP 调用逻辑，max_tokens 改为 1500 ...
```

**改动量**：约 35 行新增

### 3.4 新增 `services/planning/router.py`

**文件**：`server/services/planning/router.py`（新建）

实现新的 `generate_steps()` 和 `process_query()` 逻辑：
- 调用 `call_deepseek(query, elements)`
- 按 `target_element_id` 语义绑定元素
- Mock fallback 数据包含 `target_element_id`

**核心绑定逻辑**（替代 `llm_ai.py:325` 的机械循环）：

```python
element_by_id = {e.element_id: e for e in elements}

for i, raw in enumerate(raw_steps):
    step_index = i + 1
    target_id = raw.get("target_element_id", "")
    element = element_by_id.get(target_id) if target_id else None
    # 生成 annotation 或设为 None
```

**改动量**：约 80 行新增

### 3.5 `llm_ai.py` 入口改造（Strangler Fig 路由）

**文件**：`server/services/llm_ai.py`

**不删除旧逻辑**，只在入口加路由：

```python
from server.config import settings


def generate_steps(query: str, elements: Optional[List[UIElement]] = None) -> List[dict]:
    if settings.USE_ELEMENT_PERCEPTION:
        from server.services.planning.router import generate_steps as new_generate_steps
        return new_generate_steps(query, elements)
    return _legacy_generate_steps(query)


def process_query(query: str, image_base64: Optional[str] = None) -> ProcessResponse:
    if settings.USE_ELEMENT_PERCEPTION:
        from server.services.planning.router import process_query as new_process_query
        return new_process_query(query, image_base64)
    return _legacy_process_query(query, image_base64)
```

**改动量**：约 20 行新增，旧代码不动

### 3.6 P0 验收标准

在 `server/tests/test_perception.py` 中增加以下用例：

| # | 场景 | 输入 | 期望 |
|---|------|------|------|
| 1 | 语义匹配 | `"点击下载按钮"` + `SCENARIO_ELEMENTS["wechat"]` | Step 有 `target_element_id: "~2"`，annotation 非空 |
| 2 | 概念性步骤 | `"等待下载完成"`（LLM 无法绑定） | `target_element_id` 为空或 `None`，annotation 为 `None` |
| 3 | 无截图模式 | `"安装微信"`（`image=None`） | fallback 到 mock 步骤，`target_element_id` 来自 mock 数据 |
| 4 | LLM 幻觉 ID | Mock LLM 返回 `"~99"` 但仅 3 个元素 | 安全降级为 `None`，无崩溃 |
| 5 | USE_REAL_LLM=false | 环境变量关闭 LLM | 返回 mock 步骤含预定义 `target_element_id` |
| 6 | 与旧逻辑一致性 | 同一输入新旧逻辑输出步骤数相同 | 快照测试通过 |

---

## 四、P2 动态重规划（后端侧）

> 目标：当激活步骤无 `target_element_id` 时，自动使用新截图重新解析并为未绑定步骤补全绑定。
>
> 前端触发截图与上传逻辑 → **需 B/C 配合**（在 `HAJIMI_UI/ui/main_widget.py` 和 `HAJIMI_UI/core/api_client.py` 中实现）。

### 4.1 `StepRequest` 增加 `image` 字段

**文件**：`server/models/schemas.py:134-143`

**当前**：
```python
class StepRequest(BaseModel):
    task_id: str
    action: str = Field(..., pattern="^(advance|rollback|skip|terminate)$")
    step_index: Optional[int] = Field(None, ge=1)
    fingerprint: Optional[str] = None
```

**改为**：
```python
class StepRequest(BaseModel):
    task_id: str
    action: str = Field(..., pattern="^(advance|rollback|skip|terminate)$")
    step_index: Optional[int] = Field(None, ge=1)
    fingerprint: Optional[str] = None
    image: Optional[str] = Field(
        None,
        description="新截图 Base64；用于无绑定步骤的动态重规划",
    )
```

**注意**：此为向后兼容扩展，可选字段不影响现有调用。

**改动量**：3 行新增

### 4.2 新增 `services/planning/replanner.py`

**文件**：`server/services/planning/replanner.py`（新建）

**新增内容**（约 80 行）：

1. **`REPLAN_PROMPT`** 常量：包含 `{original_query}`、`{element_list}`、`{upcoming_steps}` 占位符。
2. **`_serialize_steps_for_replan()`** 辅助函数：将未绑定步骤序列化为 LLM 可读文本。
3. **`replan_steps()`** 主函数：
   - 筛选 `current_step_index` 之后 `target_element_id` 为空的步骤
   - 调用 DeepSeek，传入 `REPLAN_PROMPT`
   - 将 LLM 返回的 `target_element_id` 合并到步骤中
   - 为成功绑定的步骤生成 `annotation`
   - LLM 调用失败时返回原步骤，不崩溃

**完整代码见**：`项目文档/LLM元素感知与动态重规划实施计划.md` §4.4

**改动量**：约 80 行新增

### 4.3 `/step` 路由增加重规划分支

**文件**：`server/routes/demo.py:82-160`

在 `advance` 分支之后、步骤 4 "更新状态" 之前插入：

```python
    # === 动态重规划（位于 advance/rollback/skip/terminate 分支之后）===
    if (
        settings.USE_DYNAMIC_REPLANNING
        and request.image
        and next_step
        and not next_step.target_element_id
    ):
        from server.services.omniparser_client import parse_screenshot
        from server.services.planning.replanner import replan_steps

        new_elements = parse_screenshot(request.image)
        if new_elements:
            updated_steps = replan_steps(
                original_query=state.query,
                current_step_index=state.blueprint.current_step - 1,
                all_steps=state.steps,
                new_elements=new_elements,
            )
            for i, updated in enumerate(updated_steps):
                if state.blueprint.current_step - 1 <= i < len(state.steps):
                    state.steps[i] = updated
            next_step = state.steps[state.blueprint.current_step - 1]
```

**改动量**：约 20 行新增

### 4.4 P2 验收标准

| # | 场景 | 输入 | 期望 |
|---|------|------|------|
| 1 | 无绑定步骤触发重规划 | `POST /step` 带 `image`，next_step `target_element_id` 为空 | 返回 next_step 含新 `target_element_id` + annotation |
| 2 | 仍无匹配元素 | 新截图仍不含目标元素 | `target_element_id` 保持空，无崩溃 |
| 3 | rollback 不触发 | `action=rollback` 带 `image` | 不进入重规划分支 |
| 4 | 无 image 不触发 | `POST /step` 不带 `image` | 行为与当前一致，不崩溃 |
| 5 | OmniParser 不可用 | `parse_screenshot()` 返回空列表 | 返回原步骤，不崩溃 |

---

## 五、P3 蓝图状态机补完

> 目标：填补 `blueprint.py` 中设计文档列出的 7 状态但代码只覆盖基本路径的缺口。

### 5.1 当前状态迁移表（代码实际覆盖）

| 当前状态 | advance | rollback | skip | terminate |
|----------|---------|----------|------|-----------|
| `pending_confirm` | → `executing` | — | — | — |
| `executing` | → `executing` / `completed` | → `rolling_back` | → `executing` / `completed` | → `terminated` |
| `suspended` | **未处理** | **未处理** | **未处理** | — |
| `rolling_back` | **未处理** | **未处理** | — | — |

斜体为遗漏。

### 5.2 需新增的迁移路径

**文件**：`server/services/planning/blueprint_engine.py`（从 `blueprint.py` 迁移并扩展）

#### 5.2.1 `suspended` → `advance`（恢复执行）

在 `advance()` 开头增加：

```python
    @staticmethod
    def advance(state: TaskState, strict_fingerprint: bool = False) -> Tuple[str, Step]:
        bp = state.blueprint
        steps = state.steps

        # 从挂起状态恢复
        if bp.state == "suspended":
            bp.state = "executing"
            current_idx = bp.current_step - 1
            if 0 <= current_idx < len(steps):
                steps[current_idx].status = "active"
            return "advance", steps[current_idx]

        # ... 其余逻辑不变 ...
```

#### 5.2.2 `suspended` → `terminate`（挂起中取消）

在 `terminate()` 中无需额外改动（当前已覆盖所有状态 → terminated）。

#### 5.2.3 `executing` → `suspended`（外部触发挂起）

新增方法：

```python
    @staticmethod
    def suspend(state: TaskState) -> str:
        """挂起当前蓝图"""
        bp = state.blueprint
        if bp.state == "executing":
            bp.state = "suspended"
        return "suspended"
```

#### 5.2.4 `rolling_back` → `advance`（回退后重新推进）

在 `advance()` 中，`rolling_back` 与 `executing` 行为一致，无需额外分支。

### 5.3 验收标准

| # | 场景 | 期望 |
|---|------|------|
| 1 | `suspended` 状态 advance | 恢复为 `executing`，当前步骤 active |
| 2 | `executing` 状态 suspend | 状态变为 `suspended` |
| 3 | `suspended` 状态 terminate | 状态变为 `terminated` |
| 4 | `confirmed` 后 advance | 第一步 active，蓝图 state=`executing` |

**改动量**：约 25 行新增 + 文件迁移

---

## 六、P1 SetFit 意图分类（规划参考）

> 标注：**P0 完成后即可启动**，可与 P3 并行。
>
> 说明：此任务涉及模型集成，暂以规划描述为主，实施时根据环境确定具体路径。

### 6.1 当前状态

**文件**：`server/services/llm_ai.py:95-113`

- `classify_intent()` 为 10 行 if-else，覆盖 6 种情况
- 置信度为硬编码常量（0.92, 0.90, 0.88, ...）
- 不区分 `emotion_comfort`、`tutorial_generation` 等设计文档中的意图域

### 6.2 替换方案

| 步骤 | 文件 | 内容 |
|------|------|------|
| 1 | `server/services/intent/intent_data.json`（新增） | 为 9 类意图各准备 8-16 条中文标注样本 |
| 2 | `server/services/intent/train_intent.py`（新增） | SetFit 训练脚本：加载样本 → 训练 → 保存模型至 `server/services/intent/model/` |
| 3 | `server/services/intent/setfit_classifier.py`（新增） | 加载 SetFit 模型 → 推理 → 返回 (category, summary, confidence) |
| 4 | `server/services/llm_ai.py` | 入口路由：`if USE_SETFIT_INTENT: 走 SetFit else: 走 keywords` |
| 5 | `server/config.py` | 新增配置项 `USE_SETFIT_INTENT`、`INTENT_MODEL_PATH` |

### 6.3 接口兼容性

替换后 `classify_intent()` 签名不变：

```python
def classify_intent(query: str) -> Tuple[str, str, float]:
    """返回: (category, summary, confidence)"""
```

下游 `process_query()` 无需修改。

### 6.4 验收标准

- 9 类意图分类准确率 ≥ 85%（在留出测试集上）
- 模型文件 < 200MB
- 推理延迟 < 100ms
- 向后兼容：环境变量 `USE_SETFIT_INTENT=false` 时仍走原有关键词规则

**改动量**：新增 3 文件 + `llm_ai.py` 约 20 行改动 + `config.py` 2 行

---

## 七、P4 约束条件提取（规划参考）

> 标注：**P1 完成后做效果更好**（可与 NLU 模型共用），当前 LLM-based 方案可先行。

### 7.1 LLM-based 方案（Phase 1）

**文件**：`server/services/llm/prompt.py`

在 `SYSTEM_PROMPT` 和 `REPLAN_PROMPT` 中增加约束抽取指令：

```
## 约束条件提取
如果用户提到了限定条件（如安装位置、保存路径、目标版本），
请额外输出 "constraints" 字段：
{
  "steps": [...],
  "constraints": {"install_path": "非C盘", "version": "最新版"}
}
```

`services/planning/router.py` 中解析 `constraints` 字段，存入 `ProcessResponse`。

**注意**：`ProcessResponse` 当前无 `constraints` 字段，需在 `schemas.py` 中新增（可选字段，向后兼容）。

### 7.2 蓝图联动（Phase 2，依赖 P1）

当蓝图执行到某一步时，`BlueprintEngine.advance()` 检查约束条件：
- 从 `TaskState` 读取约束
- 若当前步骤涉及约束（如"选择安装路径"），在 `next_step.description` 中追加约束提示

### 7.3 验收标准

| # | 输入 | 期望 |
|---|------|------|
| 1 | `"安装微信，不要装在C盘"` | `constraints` 含 `install_path: "非C盘"` |
| 2 | 无约束输入 `"安装微信"` | `constraints` 为空或不存在 |
| 3 | 约束步骤执行时 | `description` 中包含约束提示（如"（注意：不要安装在 C 盘）"） |

**改动量**：Phase 1 约 25 行（prompt + schemas + router）；Phase 2 约 20 行（blueprint 联动）

---

## 八、工时与依赖汇总

```
第 0 天 (测试护栏) 2h  ── tests/ + 模块骨架 ──────────────────── 无依赖
    │
    ├─→ 第 1 批 (P0) 4h  ── perception/ + llm/ + planning/router ─ 依赖 0
    │       │
    │       ├─→ 第 2 批 (P2) 4h  ── replanner + schemas + demo.py ─ 依赖 P0
    │       │
    │       └─→ 第 3 批 (P1) 6h  ── intent/ ───────────────────── 依赖 P0
    │               │
    │               └─→ 第 3 批 (P4) 4h  ── constraints ───────── 建议 P1 后
    │
    └─→ 第 3 批 (P3) 3h  ── blueprint_engine.py ───────────────── 无依赖，可与 P2 并行
            │
            └─→ 第 4 天 (切换清理) 2h  ── 删除旧逻辑 + 删开关 ─── 依赖全部稳定
```

| 批次 | 任务 | 工时 | 依赖 | 关键文件 |
|------|------|------|------|---------|
| 0 | 测试护栏 + 模块骨架 | 2h | — | `server/tests/`, `llm_ai.py`（仅路由） |
| 1 | P0 元素感知 | 3-4h | 0 | `services/perception/`, `services/llm/`, `services/planning/router.py` |
| 2 | P0 测试 | 1h | P0 | `server/tests/test_perception.py` |
| 3 | P2 动态重规划 | 3-4h | P0 | `services/planning/replanner.py`, `schemas.py`, `demo.py` |
| 4 | P3 状态机补完 | 2-3h | — | `services/planning/blueprint_engine.py` |
| 5 | P1 SetFit 意图分类 | 4-6h | P0 | `services/intent/`, `llm_ai.py` |
| 6 | P4 约束条件提取 | 3-4h | P1 | `services/planning/router.py`, `schemas.py` |
| 7 | 全量切换 + 旧代码清理 | 2h | 1-6 稳定 | `llm_ai.py`（删除旧逻辑） |
| **合计** | | **18-26h** | | |

---

## 九、代码重构策略（Strangler Fig / 绞杀榕模式）

> 核心原则：**新建不删旧，路由转发，验证通过后再清理。**

### 9.1 为什么不直接拆分 `llm_ai.py`？

当前 `llm_ai.py` 381 行，同时是 P0/P1/P2/P4 的改动热点。如果 4 个 Agent 同时拆同一个文件，第一天就会出现严重 Git 冲突，合并时互相覆盖。

### 9.2 Strangler Fig 四步法

| 阶段 | 动作 | 文件状态 |
|------|------|---------|
| **Step 1: 冻结** | 标记 `llm_ai.py` 为重构中，禁止大改内部逻辑 | 旧代码保留 |
| **Step 2: 新建** | 在 `services/` 下新建 `perception/`, `llm/`, `planning/`, `intent/` | 新模块独立 |
| **Step 3: 路由** | `llm_ai.py` 入口函数只做 `if USE_NEW: return new_func() else: return old_func()` | 新旧并存 |
| **Step 4: 清理** | 所有新模块单测覆盖率 > 80% 且集成测试全绿后，删除旧逻辑 | 旧代码移除 |

### 9.3 入口路由示例

```python
# server/services/llm_ai.py
from server.config import settings


def classify_intent(query: str) -> Tuple[str, str, float]:
    if settings.USE_SETFIT_INTENT:
        from server.services.intent.setfit_classifier import classify_intent as new_classify
        return new_classify(query)
    return _legacy_classify_intent(query)


def generate_steps(query: str, elements=None) -> List[dict]:
    if settings.USE_ELEMENT_PERCEPTION:
        from server.services.planning.router import generate_steps as new_generate_steps
        return new_generate_steps(query, elements)
    return _legacy_generate_steps(query)


def process_query(query: str, image_base64: Optional[str] = None) -> ProcessResponse:
    if settings.USE_ELEMENT_PERCEPTION:
        from server.services.planning.router import process_query as new_process_query
        return new_process_query(query, image_base64)
    return _legacy_process_query(query, image_base64)
```

### 9.4 清理窗口

- **清理条件**：新模块稳定运行 2 周，单测覆盖率 > 80%，集成测试全绿
- **清理动作**：
  1. 删除 `llm_ai.py` 中的 `_legacy_*` 函数
  2. 删除 `USE_ELEMENT_PERCEPTION` 和 `USE_DYNAMIC_REPLANNING` 开关
  3. 删除 `blueprint.py`（迁移到 `planning/blueprint_engine.py`）

---

## 十、测试策略

> 当前 `server/` 下**没有单元测试目录**，`test_api.py` 只是 4 个 HTTP 端到端用例。并行开发前必须先补测试护栏。

### 10.1 第 0 天必做：老代码快照测试

创建 `server/tests/conftest.py` 和 `server/tests/test_legacy.py`，给以下函数补快照：

| 函数 | 输入 | 断言 |
|------|------|------|
| `classify_intent("怎么安装微信")` | 中文查询 | 返回 `("operation_guide", "安装软件", 0.92)` |
| `classify_intent("截图")` | 中文查询 | 返回 `("operation_guide", "屏幕截图", 0.90)` |
| `generate_steps("安装微信")` | `USE_REAL_LLM=false` | 返回 4 步，第一步 action="打开浏览器" |
| `process_query("安装微信")` | `image=None` | `success=true`，`steps` 长度 4，第一步 status="active" |
| `process_query("安装微信")` | `image=真实截图`（Mock OmniParser） | `ui_elements` 来自 OmniParser |
| `BlueprintEngine.advance()` | 初始状态 | 推进到第 2 步，state="executing" |
| `BlueprintEngine.rollback()` | 执行到第 2 步 | 回退到第 1 步，state="rolling_back" |
| `BlueprintEngine.terminate()` | 任意状态 | state="terminated" |

### 10.2 新模块单元测试

```
server/tests/
├── conftest.py              # 共享 fixtures
├── test_legacy.py           # 老代码快照（第 0 天）
├── test_perception.py       # P0：serialize_elements, 元素绑定
├── test_replanner.py        # P2：replan_steps
├── test_blueprint.py        # P3：状态迁移
└── test_intent.py           # P1：SetFit / keywords 双路径
```

### 10.3 集成测试

保留并扩展 `server/test_api.py`，增加：
- P0：`/process` 返回的 `steps[0].target_element_id` 非空
- P2：`/step` 带 `image` 时重规划成功
- P3：`/step` 触发 suspended 后 advance 恢复

### 10.4 合入门槛

任何 PR 合入 `main` 前必须满足：

```bash
pytest server/tests/          # 全绿
mypy server/                  # 零错误
python -m server.test_api     # 端到端通过
```

---

## 十一、特性开关过期机制

> 不加清理期限的开关会变成僵尸代码。每个 `USE_*` 开关必须标注计划移除版本和日期。

### 11.1 开关定义（含过期日期）

```python
class Config:
    # 特性开关（所有开关均标记计划移除日期）

    # TODO: remove by v2.1.0 (2026-07-15) — P0 稳定运行 2 周后移除
    USE_ELEMENT_PERCEPTION: bool = os.getenv("USE_ELEMENT_PERCEPTION", "true").lower() == "true"

    # TODO: remove by v2.1.0 (2026-07-15) — P0+P2 稳定运行 2 周后移除
    USE_DYNAMIC_REPLANNING: bool = os.getenv("USE_DYNAMIC_REPLANNING", "false").lower() == "true"

    # TODO: remove by v2.2.0 (2026-08-01) — SetFit 模型验证且准确率 ≥85% 后移除
    USE_SETFIT_INTENT: bool = os.getenv("USE_SETFIT_INTENT", "false").lower() == "true"

    # TODO: remove by v2.2.0 (2026-08-01) — P1 完成后稳定运行 2 周后移除
    USE_CONSTRAINT_EXTRACTION: bool = os.getenv("USE_CONSTRAINT_EXTRACTION", "false").lower() == "true"
```

### 11.2 开关生命周期

| 阶段 | 动作 | 责任人 |
|------|------|--------|
| 开发期 | 新功能默认 `false`，不影响旧流程 | 功能开发者 |
| 验证期 | 小范围开启，跑测试 | 功能开发者 |
| 稳定期 | 默认开启，观察 2 周 | 团队 |
| 清理期 | 删除旧逻辑和开关，提交独立 PR | 指定清理人 |

### 11.3 PR 检查项

每个涉及新增开关的 PR 必须回答：
- [ ] 此开关计划何时移除？
- [ ] 移除时会删除哪些旧代码？
- [ ] 开关关闭时是否 100% 等价于旧行为？

---

## 十二、分支协作纪律

> 不采用全量 Trunk-Based Development（基础设施不足），但采用"短生命周期分支 + 每日 rebase + 合入前全绿"纪律。

### 12.1 分支命名

```
feat/A1-element-perception
feat/A2-dynamic-replanning
feat/A3-blueprint-statemachine
feat/A4-setfit-intent
```

### 12.2 每日纪律

| 规则 | 内容 | 违反后果 |
|------|------|---------|
| **每日 rebase** | 每天至少一次 `git pull origin main --rebase` | 合并冲突自行承担 |
| **小步提交** | 每个功能点一个 commit，禁止积攒一周 | 回滚困难 |
| **先测后合** | PR 合入前 `pytest server/tests/` 必须全绿 | 禁止合入 |
| **类型检查** | PR 合入前 `mypy server/` 必须零错误 | 禁止合入 |
| **Schema 变更通知** | 修改 `server/models/schemas.py` 必须群通知 | 造成他人调用失败需回滚 |
| **Prompt 变更 Review** | 修改 `SYSTEM_PROMPT` / `REPLAN_PROMPT` 必须 code review | 未经 review 禁止合入 |
| **开关隔离** | 新功能必须可被 `USE_*=false` 完全关闭 | 阻塞 main 分支需立即修复 |

### 12.3 冲突高发区与避让规则

| 文件 | 风险等级 | 规则 |
|------|---------|------|
| `server/models/schemas.py` | 🔴 高 | 任何修改先群通知，且必须向后兼容 |
| `server/services/llm/prompt.py` | 🔴 高 | Prompt 修改需两人 review |
| `server/services/llm_ai.py` | 🟡 中 | 只加路由，禁止改内部旧逻辑 |
| `server/config.py` | 🟡 中 | 新增开关必须带 TODO 移除日期 |
| `server/routes/demo.py` | 🟡 中 | `/step` 路由改动需与 P2 负责人同步 |
| `server/tests/` | 🟢 低 | 各模块独立测试文件，冲突少 |

### 12.4 集成节奏

- **每日 18:00**：各人 rebase main，解决当天冲突
- **每周五 17:00**：全量回归测试（所有 `USE_*=true`），红的当场修
- **每两周**：一个清理窗口，删除已稳定的旧开关和旧逻辑

---

## 十三、外部依赖标注（需 B/C 配合）

| P2 前端工作 | 文件 | 内容 |
|------------|------|------|
| `advance_step()` 增加 `image` 参数 | `HAJIMI_UI/core/api_client.py` | 在请求体中携带截图 Base64 |
| 截图触发逻辑 | `HAJIMI_UI/ui/main_widget.py` | 当 `current_step.target_element_id` 为空且 `action=advance` 时，自动截图并上传 |

**A 侧接口约定**：
- `POST /api/demo/step` 已支持 `image` 字段（P2 完成后）
- 前端传 `image` 时，后端自动触发重规划
- 前端不传 `image` 时，行为与当前一致（零影响）

---

## 十四、附录：文件改动概览

| 文件 | P0 | P2 | P3 | P1 | P4 | 清理 | 总改动量 |
|------|:--:|:--:|:--:|:--:|:--:|:--:|---------|
| `services/perception/serializer.py` (新) | ✅ | — | — | — | — | — | 新文件 |
| `services/llm/prompt.py` (新) | ✅ | ✅ | — | — | ✅ | — | 新文件 |
| `services/llm/client.py` (新) | ✅ | — | — | — | — | — | 新文件 |
| `services/planning/router.py` (新) | ✅ | — | — | — | ✅ | — | 新文件 |
| `services/planning/replanner.py` (新) | — | ✅ | — | — | — | — | 新文件 |
| `services/planning/blueprint_engine.py` (新) | — | — | ✅ | — | — | — | 新文件 |
| `services/intent/` (新目录) | — | — | — | ✅ | — | — | 新目录 |
| `services/llm_ai.py` | ✅ 路由 | ✅ 路由 | — | ✅ 路由 | ✅ 路由 | ✅ 删旧 | ~40行 |
| `services/blueprint.py` | — | — | ✅ 迁移 | — | — | ✅ 删除 | ~20行 |
| `models/schemas.py` | — | ✅ 3行 | — | — | ✅ 2行 | — | ~5行 |
| `routes/demo.py` | — | ✅ 20行 | — | — | — | — | ~20行 |
| `config.py` | ✅ 2行 | ✅ 2行 | — | ✅ 2行 | ✅ 2行 | ✅ 删开关 | ~8行 |
| `server/tests/` (新目录) | ✅ | ✅ | ✅ | ✅ | ✅ | — | 新目录 |
| `test_api.py` | ✅ | ✅ | — | — | — | — | ~30行 |
