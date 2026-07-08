# Page-Eyes-Agent 架构分析文档

> 来源: D:\page-eyes-agent\page-eyes-agent
> 目的: 为 HAJIMI_UI Agent Loop 优化提供参考

---

## 1. 整体架构: 两阶段 Planning → Execution

系统采用严格的两阶段分离:

### Phase 1 — PlanningAgent

文件: `src/page_eyes/agent.py`, lines 72-88

```python
class PlanningAgent:
    async def run(self, prompt: str) -> AgentRunResult[PlanningOutputType]:
        agent = Agent(
            model=model,
            system_prompt=PLANNING_SYSTEM_PROMPT,
            output_type=PlanningOutputType,  # 结构化输出
            model_settings=default_settings.model_settings,
        )
        return await agent.run(prompt.strip(), deps=self.deps)
```

**单次 LLM 调用**，返回 `PlanningOutputType`，包含 `steps: list[PlanningStep]`。

每个 `PlanningStep` 只有 `instruction: str`——不含坐标、元素ID、具体操作。

### Phase 2 — UiAgent

文件: `src/page_eyes/agent.py`, lines 96-322

```python
for step, planning in enumerate(planning_steps, start=1):
    self.deps.context.add_step_info(StepInfo(...))
    if planning.instruction != "结束任务":
        result = await self._sub_agent_run(planning, usage)
    else:
        await self.deps.tool.tear_down(ctx, ...)
    if not self.deps.context.current_step.is_success:
        break
```

末尾追加哨兵步骤 `PlanningStep(instruction="结束任务")` 用于清理。

关键: **每一步是全新对话, 消息不跨步累积**。

---

## 2. Agent 循环

使用 **pydantic_ai 的 `Agent.iter()`** 内置状态机:

```
UserPromptNode → ModelRequestNode → CallToolsNode → ModelRequestNode → ... → End
```

结束条件 (任一):
1. LLM 返回纯文本 (无 tool call) → 作为步骤最终结果
2. 重试次数超过 `max_result_retries` (默认2)
3. API 调用次数超过 `request_limit` (100次/步)
4. `UnexpectedModelBehavior` 异常逃逸

### 如何处理 LLM 返回文本而非工具调用

pydantic_ai 内置 `CallToolsNode._run_stream()` 中的优先级:
- **工具调用优先**: 如果 LLM 同时返回文本+工具调用, 先执行工具
- **纯文本 = 完成**: 因为 page-eyes 的 Execution Agent 没有设置 `output_type`, 默认 `str`, 所以纯文本响应被当作步骤的最终输出
- **空响应 = 重试**: 连续空响应触发重试计数器, 超过 `max_result_retries` 则 abort

---

## 3. 消息管理

**每步全新对话** — `agent.iter()` 不传入 `message_history`:

```python
async with self.agent.iter(
    user_prompt=planning.instruction,  # fresh prompt
    deps=self.deps,
    usage=usage,
    usage_limits=UsageLimits(request_limit=100)
) as agent_run:
```

步内消息累积由 pydantic_ai 的 `GraphAgentState.message_history` 自动管理。

`history_processor` 被注释掉了 (line 163: `# history_processors=[cls.history_processor],`)，所以截图清理逻辑不生效。

---

## 4. 死循环防护

| 机制 | 位置 | 效果 |
|---|---|---|
| 重试计数器 | `GraphAgentState.increment_retries()` | 连续失败 → `UnexpectedModelBehavior` |
| Usage 限制 | `UsageLimits(request_limit=100)` | 每步最多 100 次 API 调用 |
| 并行工具检测 | `ToolHandler.pre_handle()` | 检测到并行调用则 `ModelRetry` |
| max_tokens=500 | `config.py` | 限制输出长度 |
| temperature=0.2 | `config.py` | 低温度保证确定性 |

**没有显式的死循环检测** — 不跟踪连续相同的工具调用，但 prompt 中告知 LLM 调用 `mark_failed` 停止。

---

## 5. 工具执行与错误处理

### 工具注册 (动态发现)

文件: `src/page_eyes/tools/_base.py`, lines 135-150

```python
@property
def tools(self) -> list:
    for item in dir(self):
        value = getattr(self, item)
        if callable(value) and hasattr(value, 'is_tool'):
            # 按 model_type 过滤 (LLM vs VLM)
            result.append(Tool(value, name=value.__name__.removesuffix('_vl')))
    return result
```

### 工具错误恢复

`@tool` 装饰器捕获异常并抛出 `ModelRetry`:

```python
except Exception as e:
    raise ModelRetry(f"Error occurred, try call '{func.__name__}' again")
```

pydantic_ai 将 `ModelRetry` 转换为 `RetryPromptPart` 发送回 LLM, LLM 看到 "Error occurred, try call 'click' again"。

### ToolHandler — pre/post hooks

```
pre_handle: 记录 action/params 到 step info, 检测并行调用
post_handle: 将 tool_result.is_success 同步到 step.is_success
```

---

## 6. 步骤完成信号

**当 pydantic_ai `iter()` 循环结束时, 步骤完成。** 触发条件:
- LLM 返回纯文本 (无 tool call) → `text_processor` 处理 → `End` 节点
- `mark_failed` 工具调用 → 显式设置 `is_success=False`
- `UnexpectedModelBehavior` → 跳到下个步骤, 标记失败

---

## 7. 节流/防过载

| 机制 | 代码位置 | 效果 |
|---|---|---|
| 只允许串行 | `_base.py` line 68 | 检测到并行则 `ModelRetry` |
| 系统提示 | `prompt.py` | "每次仅调用一个工具" |
| before_delay | `@tool` 装饰器 | 可配置的工具前延迟 (如 `@tool(before_delay=2)`) |
| after_delay | `@tool` 装饰器 | 工具后延迟, 页面稳定 (如 `@tool(after_delay=2)`) |
| max_tokens=500 | `config.py` | 限制输出长度, 阻止模型废话 |
| temperature=0.2 | `config.py` | 低温度, 确定性工具选择 |
| Thinking disabled | `config.py` | `extra_body={"thinking": {"type": "disabled"}}` 阻止扩展思考 |

---

## 8. 与 HAJIMI 的关键差异

| 维度 | page-eyes-agent | HAJIMI 当前 |
|------|----------------|-------------|
| Agent 框架 | pydantic_ai Agent.iter() | 手动 for 循环 |
| 消息管理 | 框架自动累积 | 手动拼接 messages |
| 每步对话 | 全新, 不跨步累积 | 跨步也可累积 |
| 重试机制 | 框架内置 retry + ModelRetry | 手动 consecutive_empty 计数 |
| 工具定义 | @tool 装饰器 | 手动 dispatch_tool |
| 完成信号 | LLM 返回文本 = done | 手动 mark_step_done 工具 |
| 死循环防护 | usage_limit + retries | consecutive_empty >= 3 |
| 元素数量 | 只传 id/content/spatial (6字段) | 同 |
| LLM 调用 | 温度0.2, tokens 500 | 温度0.2, tokens 512 |
| 工具错误 | ModelRetry → LLM 自动重试 | 返回 error dict, LLM 手动决定 |

---

## 9. 关键文件清单

| 文件 | 用途 |
|------|------|
| `src/page_eyes/agent.py` | 主 Agent: PlanningAgent + UiAgent, step 循环 |
| `src/page_eyes/config.py` | 配置: model, model_settings, 存储, browser, OmniParser |
| `src/page_eyes/prompt.py` | 系统提示 (PLANNING + EXECUTION, LLM + VLM 变体) |
| `src/page_eyes/deps.py` | 全部数据模型: AgentDeps, AgentContext, StepInfo, 工具参数, PlanningStep |
| `src/page_eyes/tools/_base.py` | AgentTool 基类, @tool 装饰器, ToolHandler, 工具发现 |
| `src/page_eyes/tools/web.py` | WebAgentTool (Playwright) |
| `src/page_eyes/tools/_mobile.py` | MobileAgentTool (Android/Harmony/iOS 共享) |
| `src/page_eyes/device.py` | 设备抽象: Web, Android, Harmony, iOS, Electron |
| `src/page_eyes/util/storage.py` | 图片存储: COS, MinIO, Base64 |
| OmniParser2/ 目录 | OmniParser 服务端 (OCR+YOLO+Florence2+Overlay) |
