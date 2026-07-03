# OpenGuider 参考改造方案 — A 端（Server）

> 基于 OpenGuider v0.3.5 完整源码与 HAJIMI A 端 `server/` 代码的逐文件对比
> 原则：最小改动、基于现有代码、每项独立可交付
> 日期：2026-07-03

---

## 源码结构对照

| OpenGuider v0.3.5 | HAJIMI A 端对应 | 对比结论 |
|---|---|---|
| `src/agent/task-orchestrator.js` (1320行) | `server/services/planning/router.py` + `demo.py` step路由 | OG 是统一编排器，HAJIMI 分散在各处 |
| `src/agent/planner-chain.js` | `server/services/llm/prompt.py` → `call_deepseek()` | OG 用 LangChain structured chain；HAJIMI 用裸 prompt |
| `src/agent/evaluator-chain.js` | **缺失** | OG 有步骤完成度评估器，HAJIMI 没有 |
| `src/agent/replanner-chain.js` | `server/services/planning/replanner.py` | 两者都有，但 OG 与 Evaluator 联动 |
| `src/core/intent-router.js` | `server/services/intent/setfit_classifier.py` | OG 路由到插件，HAJIMI 仅分类意图 |
| `src/core/execution-engine.js` | `server/services/planning/blueprint_engine.py` | OG 有审批循环，HAJIMI 自动推进 |
| `src/core/trust-manager.js` | **缺失** | HAJIMI 没有风险评估 |
| `src/core/step-queue.js` | **缺失** | HAJIMI 步骤是同步列表，无队列抽象 |
| `src/plugins/plugin-interface.js` | **缺失** | |
| `src/ai/index.js` (478行) | `server/services/llm/client.py` (156行) | OG 6 个 provider 各有独立 streaming 实现 |
| `src/agent/interaction-pipeline.js` | **缺失** | OG 有完整的 pre/post 处理管道 |
| `src/validation/semantic-verifier.js` | **缺失** | OG 有双层的坐标语义校验 |
| `src/session/session-manager.js` | `server/storage/memory.py` + `server/database/` | OG 内存+磁盘持久化，HAJIMI 内存+SQLite |

---

## 改造 1：LLM 步骤完成度评估器（Evaluator Chain）[新增 P1 · 5h]

### OpenGuider 做法

`src/agent/evaluator-chain.js` 是一个独立的 LangChain structured chain：
- **System Prompt**: 要求保守评估，"截图不能明确证明成功则判 not_done/uncertain"
- **Template**: 注入 goal/stepTitle/instruction/successCriteria/userNote
- **输出**: `{status: done|not_done|blocked|uncertain, confidence, rationale, suggestedAction: repeat_guidance|advance|replan, assistantResponse}`
- **触发时机**: 用户标记"完成"或发送新消息时，先截图再评估

`task-orchestrator.js:924-978` 中的 `evaluateCurrentStep()` 完整流程：
```
截图 → evaluateStep() → 4种结果:
  done/advance → completeCurrentStep → guideCurrentStep (下一步)
  blocked/replan → replanGoal → guideCurrentStep
  uncertain → assistantResponse + 等待用户
  LLM 抛异常 → manualConfirmation 模式
```

### HAJIMI 现状

`demo.py:/step` 路由中 `advance` 操作直接推进步骤指针，**不验证用户是否真正完成了该步**。唯一的验证是 `strict_fingerprint` 模式下的 SHA256 比对（`blueprint_engine.py:61-71`），且默认关闭。

### 改动方案

**新增文件**: `server/services/planning/evaluator.py`

```python
"""
步骤完成度评估器（参考 OpenGuider evaluator-chain.js）
在 /step advance 时，可选地先截图评估用户是否真的完成了当前步骤
"""

EVALUATOR_SYSTEM_PROMPT = (
    "你评估用户是否已完成当前 UI 操作步骤。"
    "保守判断：截图不能明确证明成功则判 not_done 或 uncertain。"
    "仅当明显偏离流程或卡住时才建议 replan。"
)

EVALUATOR_TEMPLATE = """
目标: {goal}
步骤标题: {step_title}
步骤指引: {instruction}
成功标准: {success_criteria}
用户备注: {user_note}

返回 JSON:
{{
  "status": "done|not_done|blocked|uncertain",
  "confidence": 0.0,
  "rationale": "简短理由",
  "suggested_action": "advance|repeat_guidance|replan",
  "assistant_response": "给用户的反馈"
}}
"""

class StepEvaluator:
    @staticmethod
    def evaluate(state, screenshot_base64=None, user_note="") -> dict:
        """返回评估结果 dict，失败时默认返回 done（不阻塞用户）"""
        ...
```

**修改文件**: `server/routes/demo.py`

在 `/step` 的 `advance` 分支中**可选**插入评估（通过环境变量 `HAJIMI_EVALUATE_STEPS=1` 启用）：

```python
# 在 advance 推进前（约第 179 行），可选评估当前步骤
if settings.EVALUATE_STEPS and request.image:
    eval_result = StepEvaluator.evaluate(state, request.image)
    if eval_result["suggested_action"] == "replan":
        # 触发 replan 而非推进
        ...
    elif eval_result["suggested_action"] == "repeat_guidance":
        # 不推进，返回当前步骤让用户重试
        return StepResponse(action="advance", next_step=current_step,
                           message=eval_result["assistant_response"])
```

**新增配置**: `server/config.py`

```python
EVALUATE_STEPS: bool = os.getenv("HAJIMI_EVALUATE_STEPS", "0") == "1"
```

---

## 改造 2：Intervention Pipeline（Pre/Post 处理管道）[新增 P2 · 6h]

### OpenGuider 做法

`src/agent/interaction-pipeline.js` 在每个 LLM 调用前后插入双层处理：

**Preprocess (`_preprocess`)**: 
1. Tesseract OCR → 文字词列表
2. Windows UIA PowerShell 枚举 → 可见窗口+光标位置
3. Embedding 语义匹配 (`all-MiniLM-L6-v2`) → 找到与 step instruction 最相关的 OCR 词
4. Context distillation — 用**快速文本模型**（不传图）将原始数据蒸馏成一段摘要文本，追加到 LLM prompt

**Postprocess (`_postprocess`)**:
1. `bounds-validator.js` — 坐标是否在屏幕范围内，clamp 修正
2. `ui-scanner.js` → `snapToNearestElement()` — 将坐标吸附到最近的 UIA 元素
3. `semantic-verifier.js` → `verifyCoordinateWithElements()` — 双层验证：
   - **字符串相似度**: Levenshtein + substring + 子串包含
   - **Embedding 余弦相似度**: label vs 附近元素的 name/text
   - 阈值 ≥ 0.6 才通过
4. Fallback 坐标 — 置信度 < 0.4 时使用上次有效坐标

**task-orchestrator.js:226-343** 中的 `guideCurrentStep()` 完整 pre/post 流程：
```
preprocess(OCR+UIA+embedding) → locateStepTarget(LLM) → 
postprocess(bounds+snap+semantic) → ensurePointerForStep(最终回退)
```

### HAJIMI 现状

`router.py:process_query()` 中 OmniParser → LLM 直接串行，中间没有 pre/post 处理。坐标后处理为零——LLM 返回的 `target_element_id` 直接作为标注坐标使用。

### 改动方案

**新增文件**: `server/services/perception/enricher.py`

```python
"""
Pre-LLM 上下文富化（参考 OpenGuider interaction-pipeline.js preprocess）
纯文本提炼，不引入新模型
"""

def enrich_context(query: str, elements: list[UIElement], window_title: str = "") -> str:
    """
    将 OmniParser 元素列表 + 窗口信息提炼为 LLM prompt 附录。
    不做 OCR（OmniParser 已做），不做 embedding（太重），仅结构化整理。
    """
    lines = []
    if window_title:
        lines.append(f"当前窗口: {window_title}")
    
    # 按类型分组元素，突出关键项
    by_type = {}
    for e in elements:
        by_type.setdefault(e.element_type, []).append(e)
    
    for etype, items in by_type.items():
        names = ", ".join(f"{e.element_id}({e.text or '?'})" for e in items[:10])
        lines.append(f"[{etype}] {names}")
    
    return "\n".join(lines)
```

**新增文件**: `server/services/planning/coordinate_validator.py`

```python
"""
Post-LLM 坐标校验（参考 OpenGuider semantic-verifier.js）
双层验证：边界检查 + 元素语义匹配
纯 Python，不引入 embedding 模型
"""

from typing import Optional

def validate_coordinate(coord, elements, label="", tolerance=100) -> dict:
    """
    校验 LLM 输出的坐标是否合理。

    Returns: {valid: bool, confidence: float, reason: str, corrected_coord}
    """
    # 1) 边界检查
    if coord[0] < 0 or coord[1] < 0:
        return {"valid": False, "confidence": 0.0, "reason": "坐标越界"}
    
    # 2) 元素临近检查（用 bbox 中心点距离，不用 embedding）
    nearby = []
    for e in elements:
        cx, cy = e.center or ((e.bbox[0]+e.bbox[2])//2, (e.bbox[1]+e.bbox[3])//2)
        dist = ((coord[0]-cx)**2 + (coord[1]-cy)**2)**0.5
        if dist <= tolerance:
            nearby.append((e, dist))
    
    if not nearby:
        return {"valid": True, "confidence": 0.6, "reason": "坐标附近无已知元素"}
    
    # 3) 标签文本匹配（Levenshtein 替代 embedding）
    if label:
        best = None
        for e, dist in sorted(nearby, key=lambda x: x[1]):
            text = (e.text or "").lower()
            l = label.lower()
            # 子串匹配
            if l in text or text in l:
                return {"valid": True, "confidence": 0.95, "reason": f"标签匹配: {e.text}"}
            # Levenshtein
            sim = _string_similarity(l, text)
            if best is None or sim > best[0]:
                best = (sim, e)
        if best and best[0] >= 0.6:
            return {"valid": True, "confidence": 0.8, "reason": f"模糊匹配: {best[1].text}"}
    
    return {"valid": True, "confidence": 0.7, "reason": "坐标在元素附近"}

def _string_similarity(a: str, b: str) -> float:
    """简化版字符串相似度（不依赖 embedding）"""
    if a == b: return 1.0
    if a in b or b in a: return 0.9
    # 简单 Jaccard on bigrams
    a_set = set(a[i:i+2] for i in range(len(a)-1))
    b_set = set(b[i:i+2] for i in range(len(b)-1))
    if not a_set or not b_set: return 0.0
    return len(a_set & b_set) / len(a_set | b_set)
```

---

## 改造 3：Multi-Provider LLM & Streaming [P2 · 5h]

### OpenGuider 做法

`src/ai/index.js` 中每个 Provider 是**独立的 streaming 函数**，直接拼 HTTP：

| Provider | 函数 | 特点 | Vision 兼容 |
|----------|------|------|------------|
| **Claude** | `streamClaude()` | `/v1/messages`, SSE, `x-api-key` header | ✅ native |
| **OpenAI** | `streamOpenAI()` | `/chat/completions`, SSE, `image_url` 格式 | ✅ |
| **OpenRouter** | `streamOpenRouter()` | `/chat/completions`, **402 信用不足时自动降 token 重试**（分 50%→25%→128→64→32） | ✅ |
| **Gemini** | `streamGemini()` | `streamGenerateContent?alt=sse`, `inlineData` 格式 | ✅ |
| **Groq** | `streamGroq()` | OpenAI-compatible, 超快推理 | ✅ vision models |
| **Ollama** | `streamOllama()` | `/api/chat`, `images` 数组（非标准格式） | ⚠️ 视模型 |

`src/ai/structured.js:36-92` 的 `invokeStructuredResponse()` 是统一入口——包装 streaming 并做**错误格式化**（401→鉴权失败提示 / 429→速率限制 / 402→信用不足 / 500→临时错误 / JSON parse→无效响应）。每个 LLM 调用都带上 `operationName` 用于日志追踪。

关键设计：
- **POINT 坐标格式**: `[POINT:x,y:label:screenN]`，x/y 是 **0-1000 归一化坐标**，不是绝对像素
- **parsePointTag()** 不仅解析 POINT 标签，还有 **fallback 正则** `(x, y)` 匹配模型不遵循格式的情况
- **DEFAULT_SYSTEM_PROMPT** 中写明坐标规则（top-left=0,0 / bottom-right=1000,1000）

### HAJIMI 现状

`server/services/llm/client.py` 仅支持单个 Provider（DeepSeek），同步 HTTP，无 streaming，统一定时 30s。无错误分类，无 fallback。

### 改动方案

**修改 `server/services/llm/client.py`**:
- 将 `call_deepseek()` 保留为别名，新增 `call_llm()` 统一入口
- 按 `LLM_PROVIDER` 环境变量分发到不同函数
- 增加 streaming 支持（`stream=True` + SSE 迭代）
- 增加 OpenRouter 402 降 token 重试

**修改 `server/config.py`**:
```python
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "deepseek")  # deepseek|openai|claude|openrouter
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
# 保留 DEEPSEEK_* 向后兼容
```

---

## 改造 4：步骤风险评分 [P0 · 2h]

### OpenGuider 做法

`src/core/trust-manager.js` 三级预设 + `shouldAutoApprove()` 决策 + 插件级 `getRiskScore()`：

```javascript
// trust-manager.js 核心逻辑
TRUST_PRESETS = {
  paranoid:   { autoApproveBelow: 0 },  // 永不自动
  balanced:   { autoApproveBelow: 2 },  // 低风险自动
  autopilot:  { autoApproveBelow: 5 },  // 全自动
}

function shouldAutoApprove(step, trustLevel, plugin) {
    const riskScore = plugin.getRiskScore(step);  // 插件负责评分
    return riskScore <= TRUST_PRESETS[trustLevel].autoApproveBelow;
}
```

`src/plugins/browser/index.js:190` 中每个 action type 有明确分数：
- navigate/scroll/wait → 2（安全）
- click/type/send_keys → 3（中等）
- submit/upload/download/delete/purchase → 4（高风险）

`src/plugins/browser/risk-scorer.js` 是独立模块，**同步调用**（热路径，不能卡）。

### HAJIMI 现状

完全缺失。蓝图状态机（`blueprint_engine.py`）对所有步骤一视同仁。

### 改动方案

**新增文件**: `server/services/planning/risk_scorer.py`（约 40 行）

```python
"""步骤风险评分 1-5"""
_HIGH_RISK = {"删除","卸载","格式化","支付","购买","退出登录"}
_LOW_RISK = {"找到","查看","等待","确认","观察","浏览"}

def score_step(action: str, description: str) -> int:
    text = f"{action} {description}".lower()
    if any(kw in text for kw in _HIGH_RISK): return 4
    if any(kw in text for kw in _LOW_RISK): return 1
    return 2  # 默认低风险
```

**修改 `server/models/schemas.py`**: `Step` 增加 `risk_score: Optional[int] = Field(None, ge=1, le=5)`

**修改 `server/services/planning/router.py`**: 步骤构建循环中调用 `score_step()`

---

## 改造 5：插件接口定义 [P0 · 3h]

### OpenGuider 做法

`src/plugins/plugin-interface.js` 定义了纯抽象基类 `OpenGuiderPlugin`：

**身份属性**: `id`, `name`, `version`, `capabilities[]`（均为 getter，必须 override）

**生命周期**: `async initialize(config)` → `async shutdown()`（3 秒超时强制终止）

**执行方法**: `async executeStep(step) → StepResult`, `async runGoal(goal, {trustLevel, onSubStep, signal}) → GoalResult`

**控制**: `async pause()`, `async resume()`, `async abort()`

**同步辅助**（热路径）: `getRiskScore(step) → int`, `describeStep(step) → string`

`src/core/plugin-registry.js` 是单例注册中心：
- `register(plugin)` — 验证所有 getter 非空，capabilities 非空数组，无重复 id
- `initializeAll(configs)` — 逐个初始化，单个失败不阻塞其他
- `shutdownAll()` — 3 秒超时

**Browser Plugin 的 Sidecar 模式** (`src/plugins/browser/sidecar.js`)：
- 自动分配可用端口（`net.createServer` → listen(0) → 获取 port）
- 健康轮询（300ms 起 × 指数退避，15s 截止）
- 崩溃检测 → emit `crashed` → 调用方决定处理
- 优雅关闭：POST /abort → SIGTERM → 3s 超时 → SIGKILL

### HAJIMI 现状

无插件机制。所有能力硬编码在 `router.py`。

### 改动方案

**新增文件**: `server/plugin_interface.py`（约 100 行）

与 OpenGuider 结构完全一致，Python 化：
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

class OpenGuiderPlugin(ABC):
    @property
    @abstractmethod
    def id(self) -> str: ...
    
    @property
    @abstractmethod
    def capabilities(self) -> list[str]: ...
    
    async def initialize(self, config: dict) -> None: pass
    async def shutdown(self) -> None: pass
    async def execute_step(self, step) -> StepResult: ...
    def get_risk_score(self, step) -> int: return 3
    def describe_step(self, step) -> str: return step.action

class PluginRegistry:
    """单例注册中心"""
    def register(self, plugin): ...
    async def initialize_all(self, configs=None): ...
    async def shutdown_all(self): ...
```

纯接口文件，不修改现有代码。B 端插件面板对接此 registry。

---

## 改造 6：HITL 执行增强 [P1 · 4h]

### OpenGuider 做法

`src/core/execution-engine.js` + `src/core/step-queue.js` 实现完整的 HITL 循环：

**StepQueue**: 异步 FIFO，确保步骤串行。支持 `enqueue/pause/resume/abort/drain`。drain() 返回 Promise。

**ExecutionEngine**: 
```
_processOneStep(step):
  1. plugin.describeStep(step) + plugin.getRiskScore(step)
  2. shouldAutoApprove(step, trustLevel, plugin) → 是: 跳到 4
  3. emit "execution:step-pending" → await 用户决策(120s 超时自动 skip)
     决策: approve → 继续 / skip → 返回跳过 / abort → 中止 / edit → 修改 payload
  4. plugin.executeStep(step)
  5. emit "execution:step-complete"
```

**StepApprovalCard** (`renderer/components/step-approval/StepApprovalCard.js`):
- 全键盘操作：Enter=批准, Esc=中止, R=重规划
- 风险徽章：🟢Safe/🟡Moderate/🔴Dangerous + 颜色
- "Run remaining steps automatically" 切换 → 发射 `execution:trust-override` IPC
- 防重复提交：`_decisionSentStepId` 标记

**用户决策等待** (`task-orchestrator.js:719-762`):
```javascript
_waitForUserDecision(stepId, taskId) {
    return new Promise((resolve) => {
        // 120s 超时 → 自动 abort
        const timeout = setTimeout(() => resolve({decision: "abort"}), 120_000);
        // IPC 监听
        ipcMain.on("execution:step-decision", (event, payload) => {
            if (payload.stepId === stepId && payload.taskId === taskId) {
                clearTimeout(timeout);
                resolve(payload);
            }
        });
    });
}
```

### HAJIMI 现状

`blueprint_engine.py` 的 7 状态 FSM 没有审批暂停点。唯一的暂停是 `suspended`（指纹不匹配触发）。`demo.py:/step` 中 advance 操作 100% 自动推进。

### 改动方案

**修改 `server/services/planning/blueprint_engine.py`**:
- `advance()` 增加 `trust_level` 参数
- 新增 `should_pause()` 方法：
```python
@staticmethod
def should_pause(step, trust_level="balanced") -> bool:
    if trust_level == "paranoid": return True
    if trust_level == "autopilot": return False
    risk = getattr(step, 'risk_score', 2) or 2
    return risk >= 3  # balanced 下，风险 ≥3 暂停
```

**修改 `server/models/schemas.py`**:
- `StepRequest` 增加 `trust_level: Optional[str] = "balanced"`
- `StepResponse.action` 的 pattern 增加 `"paused"`

**修改 `server/routes/demo.py`** `/step` 路由:
- advance 前调用 `BlueprintEngine.should_pause()`
- 若 true → 返回 `action="paused"` + 当前步骤 + `requires_approval=True`
- B 端弹出审批卡后，用户选 approve → 重新调 `/step` 带 `force=true`

---

## 改造 7：Intent Router 能力路由增强 [P1 · 2h]

### OpenGuider 做法

`src/core/intent-router.js` 两阶段路由：

**Phase 1: 关键词预筛**（0 延迟，不调 LLM）
```javascript
function looksLikeBrowserTask(userMessage) {
    return /\b(open|navigate|visit|website|browser|tab|page|url|click|search|...)\b/.test(text);
}
```

**Phase 2: LLM 结构化路由**
```javascript
RouteSchema = z.object({
    plugin: z.enum(['browser','cli','desktop']).nullable(),
    goal: z.string().min(1),
    trust: z.enum(['autopilot','supervised']),
});
```
- 有截图 → 传图路由
- 无截图或 provider 不支持 vision → 纯文本路由 + 自动降级重试
- 解析失败 → fallback: `pluginId=null, goal=原始query`

### HAJIMI 现状

`complexity_router.py` 只做 L2/L3 评分，没有"任务应委托给哪个能力"的决策。

### 改动方案

**修改 `server/services/planning/complexity_router.py`**: 新增 `route_capability()` 函数

```python
from enum import Enum

class Capability(str, Enum):
    GUIDE = "guide"
    BROWSER = "browser"
    CLI = "cli"

_CAP_PATTERNS = {
    Capability.BROWSER: re.compile(r"(浏览器|网页|网站|登录.*网站|打开.*搜索)"),
    Capability.CLI: re.compile(r"(命令行|终端|cmd|powershell|pip|npm|git)"),
}

def route_capability(query: str) -> Capability:
    for cap, pat in _CAP_PATTERNS.items():
        if pat.search(query):
            return cap
    return Capability.GUIDE
```

返回值写入 `detection_meta["capability"]` 和 `ProcessResponse.constraints`。

---

## 改造顺序与工时总览

```
第 1 轮（P0 先行·5h）
  ├── #4 风险评分 (2h) — 新增 risk_scorer.py + schemas.py 加字段
  └── #5 插件接口 (3h) — 新增 plugin_interface.py，纯声明

第 2 轮（P1·11h）
  ├── #7 Intent Router 增强 (2h) — complexity_router.py 加关键词路由
  ├── #1 Evaluator Chain (5h) — 新增 evaluator.py + demo.py 插入评估
  └── #6 HITL 执行增强 (4h) — blueprint_engine.py + demo.py + schemas.py

第 3 轮（P2·11h）
  ├── #2 Pre/Post Pipeline (6h) — 新增 enricher.py + coordinate_validator.py
  └── #3 Multi-Provider LLM (5h) — client.py 重构 + config.py

总计 27 工时，全部 Server 端
```

---

## 附录：关键差异纠正

对比上一版文档，以下为基于源码阅读后的**关键修正**：

| 上一版描述 | 实际（源码确认） | 修正 |
|-----------|----------------|------|
| "OpenGuider 坐标是像素" | POINT 格式是 **0-1000 归一化坐标**，由 `normalizeCoordinate()` 转为物理像素 | 评分/路由部分描述已修正 |
| "InteractionPipeline 用 embedding 验证" | 确是两层：Levenshtein 文本相似度 **+** all-MiniLM-L6-v2 Embedding 余弦相似度，阈值 0.6 | 保持描述正确，但不建议 HAJIMI 引入 embedding |
| "Executor 是 hardcoded 循环" | 使用 **LangChain RunnableSequence** (PromptTemplate + RunnableLambda) 链式调用 | 不影响 HAJIMI 方案 |
| "Fallback 简单粗暴" | OpenRouter 402 时有**智能降 token 重试**（50%→25%→128→64→32），非常精细 | 已纳入 #3 描述 |
| "StepApprovalCard 只是弹窗" | 有**键盘快捷键**（Enter/Esc/R）、**防重复提交**（_decisionSentStepId）、**trust override toggle** | 已纳入 #6 和 B 端文档 |
| BrowserPlugin 是简单 wrapper | **Sidecar 模式**：独立端口分配、健康轮询（指数退避 300ms→2s）、崩溃检测、优雅关闭（POST /abort→SIGTERM→3s→SIGKILL） | 已纳入 #5 插件描述 |
