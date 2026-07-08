# Agent Loop Execution Mode — Design Spec

**Date:** 2026-07-05
**Reference:** page-eyes-agent architecture
**Problem:** Complex multi-step operations fail due to inaccurate coordinates — LLM outputs `bbox_center` directly, introducing offsets.

---

## 1. Architecture Overview

### Current (One-shot Planning)
```
Screenshot + User Query
    ↓
OmniParser → element list (flat text)
    ↓
Single LLM call → all steps (with coordinates)
    ↓
Sequential execution (no feedback, no adjustment)
```

### Target (Agent Loop)
```
User Query
    ↓
[Planning Agent] ← text-only LLM call
    ↓ structured steps (intent only, no coordinates)

For each step loop:
    ↓
Screenshot → OmniParser → element list (with spatial relations)
    ↓
[Execution Agent] ← LLM sees current screen elements as tool-accessible data
    ↓ decides: click element_id=X / type text / wait / report failure
    ↓
Tool layer: element_id → lookup bbox → compute coordinates → execute
    ↓
Verify → success → next step, fail → retry / replan
```

### Key Principle: LLM never touches coordinates

LLM references `element_id` only. The tool layer handles `element_id → bbox → pixel coordinates`. This eliminates coordinate drift entirely.

---

## 2. Data Model Changes

### 2.1 UIElement (enhanced)

Add spatial relation fields. element_id format: integer strings without prefix (`"1"`, `"2"`, ...). The OmniParser client strips the `~` prefix during parsing.

```python
class UIElement(BaseModel):
    element_id: str          # "1", "2", ... (no prefix, stripped from OmniParser "~N")
    bbox: list[float]        # [x1, y1, x2, y2] pixel coords — HIDDEN from LLM
    center: list[int]        # [cx, cy] precomputed center — HIDDEN from LLM
    content: str             # OCR text / icon description
    element_type: str        # "text" | "icon"

    # NEW: spatial relations (computed in client after parsing)
    left_elem_ids: list[str]   # elements to the left in same row (max 5, sorted by distance)
    right_elem_ids: list[str]  # elements to the right in same row (max 5, sorted by distance)
    top_elem_ids: list[str]    # elements above with y-overlap (max 3, sorted by distance)
    bottom_elem_ids: list[str] # elements below with y-overlap (max 3, sorted by distance)
```

**LLM-visible fields only:** `id` (aliased from `element_id`), `content`, `left_ids`, `right_ids`, `top_ids`, `bottom_ids`.
`element_id`, `bbox`, `center`, `score`, `element_type` are filtered before sending to LLM.

### 2.2 Spatial Relation Algorithm

Computed in `server/services/omniparser_client.py` after parsing:

```
Same row definition: two elements are in the same row if their bbox y-axis IoU ≥ 0.3.

left_elem_ids:  all elements in same row where e.x2 ≤ current.x1,
                sorted by (current.x1 - e.x2) ascending, capped at 5.

right_elem_ids: all elements in same row where e.x1 ≥ current.x2,
                sorted by (e.x1 - current.x2) ascending, capped at 5.

top_elem_ids:   elements where y-axis overlap ≥ 0.1 AND e.y2 ≤ current.y1,
                sorted by (current.y1 - e.y2) ascending, capped at 3.

bottom_elem_ids: elements where y-axis overlap ≥ 0.1 AND e.y1 ≥ current.y2,
                 sorted by (e.y1 - current.y2) ascending, capped at 3.
```

### 2.3 Step (refactored)

Split into planning output vs execution record:

```python
class PlanningStep(BaseModel):
    step_index: int
    instruction: str          # WHAT to achieve, e.g. "click the search box"

class ExecutedStep(BaseModel):
    step_index: int
    instruction: str
    action: str | None        # click | double_click | type_text | press_key | wait | ...
    target_element_id: str | None  # filled by Execution Agent at runtime
    params: dict | None       # e.g. {"text": "周杰伦"}
    action_summary: str | None # e.g. "clicked element '搜索框'", "typed '周杰伦' into '搜索框'"
    status: str = "pending"   # pending → executing → done | failed
```

### 2.4 Blueprint (simplified)

Removed `pending_confirm` — the new flow does not require per-step human confirmation. Confirmation happens only at the plan level before execution starts. The cancel mechanism handles mid-execution abort.

```python
class Blueprint(BaseModel):
    name: str
    total_steps: int
    current_step: int
    state: str  # generated → executing → completed | terminated
```

### 2.5 ProcessResponse (updated)

Removed `reference_resolution` (unused in new flow). Added `goal` from Planning Agent.

```python
class ProcessResponse(BaseModel):
    task_id: str
    success: bool
    goal: str                    # from Planning Agent
    intent: Intent
    steps: list[ExecutedStep]    # planning steps (initially all pending)
    annotated_image: str | None  # SoM image (first screenshot for display)
    detection_meta: dict | None  # OmniParser timing info
```

---

## 3. Planning Agent

### 3.1 Responsibility

Pure text LLM call. Does NOT see screenshots. Decomposes user query into atomic steps.

**Trade-off acknowledged:** Because the Planner cannot see the screen, it may generate steps whose preconditions are already satisfied (e.g. "open the app" when the app is already open). This is handled by the Execution Agent — see §4.10.

### 3.2 Input
```
User query: "打开网易云音乐，搜索周杰伦，播放第一首"
```

### 3.3 Output (structured JSON)
```json
{
  "goal": "打开网易云音乐并播放周杰伦的歌",
  "steps": [
    {"step_index": 1, "instruction": "打开网易云音乐应用"},
    {"step_index": 2, "instruction": "在搜索框中搜索'周杰伦'"},
    {"step_index": 3, "instruction": "点击播放第一首歌曲"}
  ]
}
```

Steps describe intent only — no coordinates, no element IDs, no concrete action types.

### 3.4 System Prompt

```
你是桌面操作规划专家。将用户的自然语言指令分解为原子操作步骤。

## 步骤粒度原则
- 一个步骤对应一个用户可感知的界面状态变化
- "输入文字 + 按回车搜索" 可合并为一步（如"在搜索框中搜索'xxx'"）
- "打开应用" 必须独立一步（涉及等待加载和上下文切换）
- 不要为隐含操作生成独立步骤（"等待加载"由执行Agent自行处理，你不需要写）

## 规则
1. 每个步骤只做一件用户可感知的事
2. 保留用户原始指令中的所有信息（应用名、搜索词、文件名等）
3. 按操作的自然顺序排列步骤
4. 步骤只描述"要达成什么目标"，不描述"如何操作"
5. 如果指令涉及特定应用，第一步必须是打开该应用

## 示例
输入："打开微信，给张三发'明天见'"
输出：
  step 1: 打开微信应用
  step 2: 找到张三的聊天并发送消息'明天见'

输入："打开浏览器，搜索天气"
输出：
  step 1: 打开浏览器应用
  step 2: 在搜索框中搜索'天气'
```

### 3.5 Implementation

- File: `server/services/planning/planner.py`
- Function: `plan_steps(query: str) -> PlanningResult`
- Uses `call_llm()` with `response_format: json_object` (or structured output)
- No screenshot, no OmniParser
- Cacheable per query

---

## 4. Execution Agent (Core Change)

### 4.1 Concept

Each step runs inside an **Agent loop**: LLM observes the current screen via tool calls, decides what to do, calls tools, verifies, and marks completion or failure.

```
Current step: "在搜索框中搜索'周杰伦'"
                  ↓
┌─────────────────────────────────────────┐
│  Execution Agent Loop (LLM-driven)       │
│                                          │
│  1. LLM calls get_screen_info()          │
│     → returns elements: 1:搜索框, 2:取消...│
│                                          │
│  2. LLM identifies element 1 as search   │
│     → calls type_text("1", "周杰伦")     │
│     → tool layer: lookup bbox of 1 →     │
│       click to focus → paste via clipboard│
│                                          │
│  3. LLM presses Enter to search          │
│     → calls press_key("enter")           │
│                                          │
│  4. LLM verifies search results appeared │
│     → calls get_screen_info()            │
│     → sees result elements on screen     │
│                                          │
│  5. LLM judges step complete             │
│     → calls mark_step_done()             │
└─────────────────────────────────────────┘
                  ↓
             Next step
```

### 4.2 element_map Lifecycle (Critical)

**Rule: Each `get_screen_info()` call produces a new `element_map` that completely replaces the previous one. All old element IDs are immediately invalid.**

This means:
- LLM gets elements `["1", "2", "3"]` from `get_screen_info()` call #1
- LLM calls `click("2")` → OK (same map)
- LLM calls `get_screen_info()` again → map is rebuilt, old `["1","2","3"]` invalidated
- LLM must now use IDs from call #2's result
- If LLM tries `click("2")` referencing call #1's ID after call #2, the tool returns: `{"success": false, "error": "element_id '2' not found in current screen. Please call get_screen_info() again."}`

**LLM constraint (in system prompt):** "调用 get_screen_info 后，所有之前的 element_id 立即失效。你必须基于最新一次返回的元素列表选择目标。不得引用之前调用的 element_id。"

**Tool layer defense:** If `element_id` not in `element_map`, return a clear error message telling LLM to re-scan.

### 4.3 Tools Exposed to LLM

| Tool | Parameters | Description |
|------|-----------|-------------|
| `launch_app` | `app_name: str` | Start an application via Win+Search (deterministic, no OmniParser needed). Use for "打开XX应用" steps. |
| `get_screen_info` | none | Screenshot → OmniParser → return element list (spatial relations included, coordinates hidden). Rebuilds element_map. |
| `click` | `element_id: str` | Click element center. Uses current element_map. |
| `double_click` | `element_id: str` | Double-click element center. Use for desktop icons/files. |
| `type_text` | `element_id: str, text: str` | Click element to focus, then paste via clipboard (CJK-safe). Saves/restores clipboard. |
| `press_key` | `keys: str` | Key combo, e.g. `"ctrl+v"`, `"enter"`, `"win"` |
| `scroll` | `direction: str, amount: int` | Scroll up/down |
| `wait` | `seconds: float` | Wait for page to respond |
| `mark_step_done` | `reason: str` | Current step completed. Use `"precondition already satisfied"` if step needs no action. |
| `mark_step_failed` | `reason: str` | Current step failed with reason |

**Critical:** `click`, `double_click`, and `type_text` accept `element_id` only, never coordinates. Coordinate resolution is entirely internal to the tool layer.

### 4.4 LLM-Visible Element Format

```json
{
  "id": "3",
  "content": "搜索",
  "left_ids": ["2"],
  "right_ids": ["5"],
  "top_ids": [],
  "bottom_ids": ["8"]
}
```

Note: The field name visible to LLM is `id` (aliased from `element_id`). No `~` prefix — stripped in OmniParser client.

Fields excluded from LLM context: `element_id`, `bbox`, `center`, `score`, `element_type`, `confidence`.

### 4.5 Step Execution Protocol

```
For each step in plan.steps:
    1. Check cancel_event.is_set() → if true, push task_cancelled SSE, return
    2. Reset tool-call counter, clear element_map
    3. Build system prompt with goal, current step.instruction, and previous_steps context
    4. Loop (max 15 tool-call rounds):
        a. Check cancel_event.is_set() → if true, abort loop
        b. LLM decides which tool to call
        c. Execute tool → record result + action_summary in context
        d. Push SSE: tool_called (tool name + params), tool_result (success/fail)
        e. If get_screen_info was called → push screenshot_updated SSE with new SoM image
        f. If mark_step_done → break, advance to next step
        g. If mark_step_failed → step failed, either skip or terminate plan
        h. Else continue (LLM sees tool return value, decides next)
    5. Push SSE: step_done / step_failed
```

**Cancel mechanism:** A `threading.Event` (`cancel_event`) is created per task and stored in `TaskStore`. The `/api/demo/cancel` endpoint sets this event. The Execution Agent loop checks it at the start of each step and before each tool call. On cancel: push `task_cancelled` SSE, clean up state.

**SSE event types for real-time observability:**

| SSE Event | Payload | When |
|-----------|---------|------|
| `step_start` | `{step_index, instruction}` | Before entering the agent loop for a step |
| `tool_called` | `{step_index, tool, params}` | Before executing a tool call |
| `tool_result` | `{step_index, tool, result}` | After tool execution completes |
| `screenshot_updated` | `{annotated_image_b64, elements_count}` | After each `get_screen_info()` call |
| `step_done` | `{step_index, action_summary}` | Step completed successfully |
| `step_failed` | `{step_index, reason}` | Step failed |
| `task_done` | `{goal, total_steps, completed_steps}` | All steps completed |
| `task_failed` | `{reason, failed_step}` | Plan terminated due to failure |
| `task_cancelled` | `{}` | User cancelled mid-execution |

This allows the frontend to render an animated "observe → think → act → verify" loop similar to Claude Computer Use, rather than a static spinner.

### 4.6 Attached Context Per LLM Call

Each LLM call in the loop receives:

```json
{
  "goal": "打开网易云音乐并播放周杰伦的歌",
  "current_step": {
    "index": 3,
    "instruction": "在搜索框中搜索'周杰伦'"
  },
  "previous_steps": [
    {
      "index": 1,
      "instruction": "打开网易云音乐应用",
      "status": "done",
      "action_summary": "launched app '网易云音乐' via Win+Search"
    },
    {
      "index": 2,
      "instruction": "在搜索框中搜索'周杰伦'",
      "status": "done",
      "action_summary": "typed '周杰伦' into element '搜索框' and pressed Enter"
    }
  ]
}
```

The `action_summary` field gives the Execution Agent awareness of what was already done, reducing redundant actions and improving cross-step coherence.

**action_summary generation:** Generated by the **Tool layer** automatically when each action tool completes successfully. Every tool return value includes an `action_summary` string (e.g., `click` returns `"clicked element '搜索框'"`, `type_text` returns `"typed '周杰伦' into '搜索框'"`, `launch_app` returns `"launched app '网易云音乐' via Win+Search"`). The Agent loop accumulates these into `previous_steps` context. This avoids burdening the LLM with summarizing its own actions, keeping `mark_step_done`'s interface simple (`reason` only).

### 4.7 Execution Agent System Prompt

```
你是桌面自动化执行专家。你的任务是完成当前步骤。你可以调用工具来观察屏幕和执行操作。

## 可用工具
- launch_app(app_name): 通过系统级命令启动应用（Win+搜索）。当步骤为打开应用时，优先使用此工具。
- get_screen_info(): 获取当前屏幕的元素列表（返回 id, content, left_ids, right_ids, top_ids, bottom_ids）
- click(element_id): 单击指定元素
- double_click(element_id): 双击指定元素。桌面图标、文件通常需要双击打开。
- type_text(element_id, text): 点击元素后输入文本
- press_key(keys): 按键盘组合键，如 "enter", "ctrl+v", "win"
- scroll(direction, amount): 滚轮滚动
- wait(seconds): 等待指定秒数，让界面响应
- mark_step_done(reason): 标记当前步骤已完成。如果步骤的前置条件已满足（如应用已打开、搜索框已聚焦），直接调用此工具并说明 reason="precondition already satisfied"。
- mark_step_failed(reason): 标记步骤失败并说明原因

## 工作流程
1. 如果当前步骤是打开某个应用，直接调用 launch_app(app_name)，不需要先 get_screen_info
2. 否则，首先调用 get_screen_info 观察当前屏幕
3. 如果当前步骤的前置条件已满足（参考 previous_steps 中的 action_summary），直接调用 mark_step_done
4. 在元素列表中定位目标（匹配 content 文本）
5. 调用 click / double_click / type_text 等执行操作
6. 验证操作结果（见下方验证标准）
7. 确认完成后调用 mark_step_done

## 警告：element_id 生命周期
调用 get_screen_info 后，所有之前的 element_id 立即失效。你必须基于最新一次返回的元素列表选择目标。不得引用之前调用的 element_id。如果工具返回 "element_id not found in current screen"，你必须重新调用 get_screen_info。

## 元素定位策略
- 优先精确匹配 content 文本
- 匹配不唯一时，利用空间关系：如"搜索框右边的按钮" → 找 left_ids 包含搜索框 id 的元素
- 内容可能部分匹配（如搜索框显示"搜"而非"搜索"）
- 找不到时，先 wait(2) 再重新 get_screen_info

## 验证标准
- type_text 后验证：再次 get_screen_info，目标元素的 content 应包含或反映输入文本
- click 后验证：观察屏幕元素列表是否有变化（新元素出现、元素消失、content 变化）
- 如果连续 2 次 get_screen_info 结果完全相同，说明上一步操作可能无效，应尝试替代方案
- 桌面图标、文件操作使用 double_click 而非 click

## 异常处理
- 点击后无反应 → wait(1) 后重试
- 元素始终找不到 → 尝试 press_key("tab") 切换焦点再试
- 意外弹窗 → 优先点击关闭/取消按钮（content 为 "关闭"/"取消"/"跳过"/"×" 的元素）
- 多次重试无效 → mark_step_failed
- 弹窗遮挡目标元素 → 先关闭弹窗再继续

## 禁止事项
- 禁止假设屏幕上看不到的元素存在
- 禁止在一次响应中调用多个工具（串行调用，每次只调一个）
- 禁止跳过 get_screen_info 直接操作（除非只是按键等待）
- 禁止在 get_screen_info 之后引用之前的 element_id
```

### 4.8 Tool Implementation Detail

**Screenshot + OmniParser integration:**
```python
async def get_screen_info():
    image_base64 = await take_screenshot()
    parse_result = await omniparser_client.parse_screenshot_full(image_base64)
    self.element_map = {e.element_id: e for e in parse_result.elements}
    self.screen_elements = _filter_for_llm(parse_result.elements)
    return {"elements": self.screen_elements}
```

**click(element_id):**
```python
async def click(element_id: str):
    element = element_map.get(element_id)
    if element is None:
        return {"success": False, "error": f"element_id '{element_id}' not found in current screen. Please call get_screen_info() again."}
    cx, cy = element.center
    result = safety.check(cx, cy)
    if result.blocked:
        # Red zone: hard block
        if result.zone == "red":
            return {"success": False, "error": f"action blocked (zone: red): {result.reason}"}
        # Yellow zone: warn but allow LLM to decide
        if result.zone == "yellow":
            return {"success": False, "error": f"action requires confirmation (zone: yellow): {result.reason}. Choose a different target or proceed with caution."}
    pyautogui.click(cx, cy)
    return {"success": True, "clicked": element_id, "content": element.content, "action_summary": f"clicked element '{element.content}'"}
```

**type_text(element_id, text):**
```python
async def type_text(element_id: str, text: str):
    element = element_map.get(element_id)
    if element is None:
        return {"success": False, "error": f"element_id '{element_id}' not found in current screen. Please call get_screen_info() again."}
    cx, cy = element.center
    old_clipboard = pyperclip.paste()  # save user's clipboard
    try:
        pyautogui.click(cx, cy)         # focus the element
        await asyncio.sleep(0.2)
        pyperclip.copy(text)            # CJK-safe via clipboard
        pyautogui.hotkey("ctrl", "v")
        await asyncio.sleep(0.3)        # ensure paste completes (Electron/VM apps may be slow)
    finally:
        pyperclip.copy(old_clipboard)   # restore user's clipboard
    return {"success": True, "typed": text, "into": element_id, "action_summary": f"typed '{text}' into '{element.content}'"}
```

### 4.9 Safety Gate Integration

The safety gate (`server/services/executor/safety.py`) is invoked inside every `click`, `double_click`, and `type_text` call. Response depends on zone:

| Zone | Behavior |
|------|----------|
| **Green** | Pass through, execute normally |
| **Yellow** | Return error to LLM with reason. LLM **must** choose a different element or alternative approach, or call `mark_step_failed`. Yellow zone actions are never auto-executed. LLM cannot self-confirm through yellow zones — re-invoking the same tool on the same element will return the same error. |
| **Red** | Return error to LLM with reason. LLM must choose a different approach or `mark_step_failed`. Red zone actions are never executed. |

### 4.10 Precondition Already Satisfied

Since the Planning Agent has no screen awareness, it may produce steps that are already done. The Execution Agent handles this:

- First action in each step: `get_screen_info()` to observe
- If LLM determines the step's intent is already satisfied (e.g., app already open, search box already focused, text already entered), it calls `mark_step_done(reason="precondition already satisfied")`
- This is explicitly documented in the system prompt as valid behavior — it does not count as a failure or shortcut

### 4.11 Fallback: When LLM Fails

**Trigger conditions (any of):**
- Execution Agent exhausts 10-round budget without calling `mark_step_done` or `mark_step_failed`
- LLM returns unparseable response (not a valid tool call)
- LLM response is empty or times out

**Handling:**
1. Force `mark_step_failed("agent loop exhausted / LLM error")`
2. If it's the first step failure, retry the entire step once (fresh element_map, fresh context)
3. If the same step fails twice, terminate the plan and push `task_failed` SSE

**Emergency fallback:** If the old system's hardcoded template matches the current query (e.g., "calculator", "notepad", "wechat"), offer the user the option to fall back to the template path. This is a UI-layer decision — the API returns a flag `fallback_available: true` in the error response.

### 4.12 get_screen_info Performance

Each call = screenshot capture + OmniParser HTTP request + spatial relation computation. A 5-step task with observe + verify per step = up to 10 calls. At ~1-2s per OmniParser call, total waits could reach 20s.

**Mitigations:**
- LLM is guided to minimize unnecessary `get_screen_info` calls (system prompt says "verify when uncertain", not "always verify")
- Future optimization (out of scope for this spec): add optional `region` parameter to `get_screen_info` for partial-screen analysis (e.g., `"top"`, `"center"`)
- Future optimization: `get_screen_diff()` tool returning only changed elements vs previous call

---

## 5. Integration with Existing Systems

### 5.1 What stays
- **Launcher** (`server/services/launcher.py`): Win+Search app launch remains deterministic. Used as a tool: when the first step is "打开XX应用", the Execution Agent can call it directly, or the tool layer auto-detects and delegates.
- **Safety** (`server/services/executor/safety.py`): three-color gate still applies, enriched with yellow-zone feedback to LLM (see §4.9)
- **Clicker** (`server/services/executor/clicker.py`): `execute_action()` is called by the tool layer, not by a static step loop
- **OmniParser client** (`server/services/omniparser_client.py`): enhanced to compute spatial relations and strip `~` prefix, but same HTTP API
- **SSE streaming** (`server/routes/demo.py`): same event types, enriched with agent loop events
- **Intent classification + redline**: unchanged

### 5.2 What changes
- `server/services/planning/router.py`: `process_query()` refactored — calls Planning Agent then Execution Agent
- `server/services/executor/engine.py`: `run_plan()` replaced by Agent loop
- LLM calls: from one shot → Planning (1 call) + Execution (1-5 calls per step)

### 5.3 What's removed/deprecated
- `_call_executor_llm()` inline prompt — replaced by Execution Agent system prompt
- `_serialize_elements()` — replaced by element format in tools
- Hardcoded simulation steps — kept as emergency fallback only (§4.11)
- `bbox_center` in LLM output — LLM no longer outputs coordinates
- `pending_confirm` state — no human confirmation at step level; cancel mechanism handles mid-execution abort
- `reference_resolution` field — unused in new flow

---

## 6. File Changes

| File | Change |
|------|--------|
| `server/models/schemas.py` | Add spatial relation fields to UIElement; add PlanningStep/ExecutedStep; simplify Blueprint states; remove reference_resolution |
| `server/services/planning/planner.py` | **NEW** — Planning Agent (text-only structured planning) |
| `server/services/planning/router.py` | Refactor `process_query()` to orchestrate Planning + Execution |
| `server/services/executor/agent.py` | **NEW** — Execution Agent loop + tool definitions + element_map |
| `server/services/executor/engine.py` | Replace `run_plan()` with Agent loop integration + cancel_event |
| `server/services/omniparser_client.py` | Strip `~` prefix from element IDs; add spatial relation computation |
| `server/services/llm/providers.py` | Ensure tool-calling / function-calling API support |
| `server/routes/demo.py` | Adapt SSE events for agent loop; add cancel event wiring |
| `server/config.py` | New keys: `MAX_TOOL_CALL_ROUNDS` (default 15), `STEP_RETRY_LIMIT` (default 1) |

---

## 7. Error Handling

| Scenario | Handling |
|----------|----------|
| Planning Agent returns malformed JSON | Retry once; fail with clear error to user |
| Element not found on screen | LLM retries with wait + rescan; max 3 attempts per element search |
| OmniParser returns empty elements | Wait 1s, rescan; if still empty, mark_step_failed |
| Tool call exceeds max rounds (15) | Force mark_step_failed, retry step once, terminate on second failure |
| Unexpected popup/dialog | LLM detects via get_screen_info, closes it, retries step |
| Safety gate: Yellow zone | Return error to LLM with reason; LLM must choose different target or alternative approach. Cannot self-confirm. |
| Safety gate: Red zone | Return error to LLM; LLM must find alternative or mark_step_failed |
| element_id not in element_map (stale reference) | Return clear error: "element_id 'X' not found. Please call get_screen_info() again." |
| Step fails twice | Terminate plan, push task_failed SSE, return fallback flag if applicable |
| User cancels mid-execution | cancel_event.set() → loop checks before each round → push task_cancelled SSE |
| Clipboard conflict | type_text saves/restores user clipboard in try/finally |

---

## 8. Testing Strategy

### 8.1 Unit Tests
1. Planning Agent: input → structured output validation (valid JSON, steps have required fields)
2. Element filtering: verify bbox/center/type excluded from LLM context
3. Spatial relation computation: known bbox inputs → correct left/right/top/bottom IDs
4. element_id prefix stripping: OmniParser `"~5"` → internal `"5"`
5. element_map staleness: accessing stale ID returns error response
6. Clipboard save/restore in type_text
7. Safety gate integration: green/yellow/red zone responses

### 8.2 Integration Tests
8. Planning → Execution flow with mocked OmniParser + mocked LLM
9. Tool layer: element_id → coordinate resolution with real element_map
10. Cancel event: mid-step cancel triggers clean abort and SSE event
11. SSE event stream: all expected event types emitted in order

### 8.3 LLM Behavior Tests (Critical)
12. **Deterministic regression tests**: Fix a set of screen element JSON fixtures. For each fixture + step instruction pair, assert LLM selects the correct tool + element_id. Run with multiple LLM backends.
13. **Ambiguity stress tests**: Construct scenarios with multiple elements sharing the same content text. Verify LLM uses spatial relations to disambiguate.
14. **Edge case tests**: Empty element list, single-element screen, all elements with no text content. Verify LLM handles gracefully (waits, rescans, or fails with reason).
15. **Mock LLM integration tests**: Use a preset-response mock LLM to run the full Agent loop deterministically. Verify correct tool call sequence and step state transitions.

### 8.4 E2E Tests
16. Real desktop scenarios with live OmniParser: launch app, search, play media
17. Multi-step task with real LLM: "打开记事本，输入hello world，保存到桌面"
