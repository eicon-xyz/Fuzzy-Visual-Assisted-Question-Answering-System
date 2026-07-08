# Agent Loop Execution Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace one-shot LLM planning with a two-phase Planning→Execution Agent loop where LLM references element_id never coordinates.

**Architecture:** Planning Agent (text-only structured output) → Execution Agent (tool-calling loop) where each step runs: get_screen_info → LLM decides tool → execute via element_id → verify → mark done/failed. Coordinates resolved in tool layer only.

**Tech Stack:** FastAPI, pydantic, httpx, pyautogui/pydirectinput, OmniParser HTTP API, OpenAI-compatible LLM API

## Global Constraints

- LLM never outputs coordinates — only `element_id` strings
- element_id format: integer strings without `~` prefix (e.g. `"1"`, `"2"`)
- `element_map` invalidated on every `get_screen_info()` call
- Safety gate Yellow zone = block (LLM must choose alternative), Red zone = block (LLM must fail step)
- `MAX_TOOL_CALL_ROUNDS` = 15, `STEP_RETRY_LIMIT` = 1
- Clipboard save/restore in type_text with 0.3s post-paste delay
- SSE events: step_start, tool_called, tool_result, screenshot_updated, step_done, step_failed, task_done, task_failed, task_cancelled
- Keep existing launcher, safety, clicker, OmniParser client intact; enhance, don't replace

---

### Task 1: Data Model Changes

**Files:**
- Modify: `server/models/schemas.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `UIElement` with 4 new fields: `left_elem_ids: list[str]`, `right_elem_ids: list[str]`, `top_elem_ids: list[str]`, `bottom_elem_ids: list[str]`
  - `PlanningStep` new class: `step_index: int`, `instruction: str`
  - `ExecutedStep` new class: `step_index: int`, `instruction: str`, `action: str | None`, `target_element_id: str | None`, `params: dict | None`, `action_summary: str | None`, `status: str`
  - `Blueprint` simplified: state pattern loses `pending_confirm`, `suspended`, `rolling_back`
  - `ProcessResponse` loses `reference_resolution`, `constraints`; gains `goal: str`
  - `RedlineInfo` added to `ProcessResponse`

- [ ] **Step 1: Write failing tests for new models**

```python
# tests/test_schemas.py
import pytest
from server.models.schemas import UIElement, PlanningStep, ExecutedStep, Blueprint, ProcessResponse

def test_uielement_has_spatial_relations():
    el = UIElement(
        element_id="5", bbox=[100,200,300,400], element_type="button",
        text="search", confidence=0.95, center=[200,300],
        left_elem_ids=["3","4"], right_elem_ids=["6"],
        top_elem_ids=["1"], bottom_elem_ids=["8","9"]
    )
    assert el.left_elem_ids == ["3","4"]
    assert el.right_elem_ids == ["6"]
    assert el.top_elem_ids == ["1"]
    assert el.bottom_elem_ids == ["8","9"]

def test_uielement_spatial_defaults_empty():
    el = UIElement(
        element_id="1", bbox=[0,0,10,10], element_type="text",
        text="", confidence=0.5, center=[5,5]
    )
    assert el.left_elem_ids == []
    assert el.right_elem_ids == []
    assert el.top_elem_ids == []
    assert el.bottom_elem_ids == []

def test_planning_step():
    ps = PlanningStep(step_index=1, instruction="open the app")
    assert ps.step_index == 1
    assert ps.instruction == "open the app"

def test_executed_step_defaults():
    es = ExecutedStep(step_index=2, instruction="click search")
    assert es.action is None
    assert es.target_element_id is None
    assert es.params is None
    assert es.action_summary is None
    assert es.status == "pending"

def test_blueprint_states_no_pending_confirm():
    bp = Blueprint(name="test", total_steps=3, current_step=1, state="executing")
    assert bp.state == "executing"
    # Verify invalid states are rejected
    with pytest.raises(ValueError):
        Blueprint(name="x", total_steps=1, current_step=1, state="pending_confirm")

def test_process_response_has_goal_no_reference_resolution():
    from server.models.schemas import Intent
    intent = Intent(category="operation_guide", summary="test", reference_type="explicit", confidence=1.0, needs_clarification=False)
    pr = ProcessResponse(task_id="t1", success=True, goal="do the thing", intent=intent, steps=[], ui_elements=[])
    assert pr.goal == "do the thing"
    assert not hasattr(pr, "reference_resolution")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_schemas.py -v`
Expected: FAIL — old models don't have new fields

- [ ] **Step 3: Update schemas.py**

```python
# server/models/schemas.py — changes only; keep all existing models
# that are NOT listed below as-is

class UIElement(BaseModel):
    """截图中识别到的 UI 元素"""
    element_id: str = Field(..., description="ID without prefix, e.g. '5'")
    bbox: List[float] = Field(..., min_length=4, max_length=4)
    element_type: str = Field(
        ...,
        pattern="^(button|input|icon|menu|checkbox|dropdown|text|other)$",
    )
    text: Optional[str] = ""
    confidence: float = Field(..., ge=0.0, le=1.0)
    center: Optional[List[int]] = Field(None, min_length=2, max_length=2)
    # NEW: spatial relations
    left_elem_ids: List[str] = Field(default_factory=list)
    right_elem_ids: List[str] = Field(default_factory=list)
    top_elem_ids: List[str] = Field(default_factory=list)
    bottom_elem_ids: List[str] = Field(default_factory=list)


class PlanningStep(BaseModel):
    """Planner output — intent only, no coordinates"""
    step_index: int = Field(..., ge=1)
    instruction: str


class ExecutedStep(BaseModel):
    """Execution record — filled by Execution Agent at runtime"""
    step_index: int = Field(..., ge=1)
    instruction: str
    action: Optional[str] = None
    target_element_id: Optional[str] = None
    params: Optional[dict] = None
    action_summary: Optional[str] = None
    status: str = Field("pending", pattern="^(pending|executing|done|failed)$")


class Blueprint(BaseModel):
    """任务蓝图 — simplified states"""
    name: str
    total_steps: int = Field(..., ge=1)
    current_step: int = Field(..., ge=1)
    state: str = Field(
        ...,
        pattern="^(generated|executing|completed|terminated)$",
    )


class ProcessResponse(BaseModel):
    """核心流程响应"""
    task_id: str
    success: bool
    goal: str = ""                          # NEW: from Planning Agent
    intent: Intent
    ui_elements: List[UIElement]
    annotated_image: Optional[str] = Field(None)
    blueprint: Blueprint
    steps: List[ExecutedStep]
    redline: Optional[RedlineInfo] = None
    detection_meta: Optional[dict] = Field(None)
```

Keep all other existing models unchanged (`ChatTurn`, `Intent`, `Annotation`, `ErrorDetail`, `ErrorResponse`, `RedlineInfo`, `ProcessRequest`, `CancelRequest`, `StepRequest`, `StepResponse`, `ClarifyRequest`, `ClarifyResponse`, `ReportRequest`, `ReportResponse`, `HealthResponse`, `RelocateRequest`, `RelocateResponse`, `InspectRequest`, `InspectResponse`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_schemas.py server/models/schemas.py
git commit -m "feat: add spatial relations to UIElement, PlanningStep/ExecutedStep, simplify Blueprint"
```

---

### Task 2: Spatial Relation Computation in OmniParser Client

**Files:**
- Modify: `server/services/omniparser_client.py`

**Interfaces:**
- Consumes: `UIElement` with new fields (Task 1)
- Produces: `parse_screenshot_full()` returns elements with `left_elem_ids/right_elem_ids/top_elem_ids/bottom_elem_ids` populated; element_id loses `~` prefix

- [ ] **Step 1: Write failing tests for spatial relation computation**

```python
# tests/test_spatial_relations.py
from server.services.omniparser_client import _compute_spatial_relations
from server.models.schemas import UIElement

def make_el(eid, x1, y1, x2, y2):
    return UIElement(element_id=str(eid), bbox=[x1,y1,x2,y2],
                     element_type="text", text=f"el{eid}", confidence=0.9,
                     center=[(x1+x2)//2, (y1+y2)//2])

def test_same_row_detection():
    """Two elements on the same y-band should be mutual left/right neighbors."""
    e1 = make_el(1, 100, 100, 200, 150)  # y: 100-150
    e2 = make_el(2, 250, 105, 350, 155)  # y: 105-155, high y-overlap = same row
    _compute_spatial_relations([e1, e2])
    assert e1.right_elem_ids == ["2"]
    assert e2.left_elem_ids == ["1"]

def test_different_rows_no_horizontal_rel():
    """Elements far apart vertically should NOT be left/right neighbors."""
    e1 = make_el(1, 100, 100, 200, 150)
    e2 = make_el(2, 250, 500, 350, 550)  # completely different row
    _compute_spatial_relations([e1, e2])
    assert e1.right_elem_ids == []
    assert e2.left_elem_ids == []

def test_top_bottom_relations():
    """Elements with y-overlap should get top/bottom relations."""
    e1 = make_el(1, 100, 50, 300, 120)
    e2 = make_el(2, 150, 150, 250, 250)
    _compute_spatial_relations([e1, e2])
    assert "2" in e1.bottom_elem_ids
    assert "1" in e2.top_elem_ids

def test_capped_neighbors():
    """Neighbor lists should be capped at specified limits."""
    elements = []
    for i in range(10):
        elements.append(make_el(i, i*80, 100, i*80+60, 150))
    _compute_spatial_relations(elements)
    for el in elements:
        assert len(el.left_elem_ids) <= 5
        assert len(el.right_elem_ids) <= 5

def test_element_id_strips_tilde():
    """parse_screenshot_full should strip ~ prefix from element IDs."""
    # This test requires mocking the HTTP call — see integration tests.
    pass  # placeholder for Task 9 integration test
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_spatial_relations.py -v`
Expected: FAIL — `_compute_spatial_relations` not defined

- [ ] **Step 3: Implement spatial relation computation in omniparser_client.py**

```python
# Add to server/services/omniparser_client.py after the existing imports

def _compute_spatial_relations(elements: List[UIElement]) -> None:
    """Compute left/right/top/bottom neighbor relations for all elements.
    Mutates elements in-place, populating their *_elem_ids fields.

    Same row: y-axis IoU >= 0.3
    Top/bottom: y-axis overlap >= 0.1 (more lenient — elements can span rows)
    """
    n = len(elements)
    if n == 0:
        return

    for i in range(n):
        el = elements[i]
        el.left_elem_ids = []
        el.right_elem_ids = []
        el.top_elem_ids = []
        el.bottom_elem_ids = []

    for i in range(n):
        a = elements[i]
        ay1, ay2 = a.bbox[1], a.bbox[3]
        ah = ay2 - ay1
        if ah <= 0:
            continue

        left_candidates = []
        right_candidates = []
        top_candidates = []
        bottom_candidates = []

        for j in range(n):
            if i == j:
                continue
            b = elements[j]
            by1, by2 = b.bbox[1], b.bbox[3]
            bh = by2 - by1
            if bh <= 0:
                continue

            # y-axis IoU
            overlap = max(0, min(ay2, by2) - max(ay1, by1))
            union = max(ay2, by2) - min(ay1, by1)
            y_iou = overlap / union if union > 0 else 0

            # Same row for left/right: y_iou >= 0.3
            if y_iou >= 0.3:
                if b.bbox[2] <= a.bbox[0]:  # b is to the left of a
                    left_candidates.append((j, a.bbox[0] - b.bbox[2]))
                elif b.bbox[0] >= a.bbox[2]:  # b is to the right of a
                    right_candidates.append((j, b.bbox[0] - a.bbox[2]))

            # Top/bottom: y overlap >= 0.1 (using iou proxy)
            if y_iou >= 0.1:
                if by2 <= ay1:  # b is above a
                    top_candidates.append((j, ay1 - by2))
                elif by1 >= ay2:  # b is below a
                    bottom_candidates.append((j, by1 - ay2))

        # Sort by distance (ascending) and cap
        left_candidates.sort(key=lambda x: x[1])
        right_candidates.sort(key=lambda x: x[1])
        top_candidates.sort(key=lambda x: x[1])
        bottom_candidates.sort(key=lambda x: x[1])

        a.left_elem_ids = [elements[k].element_id for k, _ in left_candidates[:5]]
        a.right_elem_ids = [elements[k].element_id for k, _ in right_candidates[:5]]
        a.top_elem_ids = [elements[k].element_id for k, _ in top_candidates[:3]]
        a.bottom_elem_ids = [elements[k].element_id for k, _ in bottom_candidates[:3]]
```

Then modify the element_id assignment in `parse_screenshot_full()` to strip the `~` prefix:

```python
# In parse_screenshot_full(), replace the element_id assignment block:
        raw_id = item.get("id")
        if raw_id is not None:
            element_id = str(raw_id)             # was: f"~{raw_id}"
        elif all_none:
            element_id = str(seq)                # was: f"~{seq}"
            seq += 1
        else:
            element_id = "?"
```

And call `_compute_spatial_relations(elements)` before returning:

```python
    # After the elements loop, before the SoM image extraction:
    _compute_spatial_relations(elements)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_spatial_relations.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_spatial_relations.py server/services/omniparser_client.py
git commit -m "feat: add spatial relation computation and strip ~ prefix from element IDs"
```

---

### Task 3: LLM-Visible Element Filter

**Files:**
- Modify: `server/services/omniparser_client.py` (add filter function)

**Interfaces:**
- Consumes: `UIElement` with spatial relations (Task 2)
- Produces: `_filter_elements_for_llm(elements: list[UIElement]) -> list[dict]` — returns only `id`, `content`, `left_ids`, `right_ids`, `top_ids`, `bottom_ids`

- [ ] **Step 1: Write failing test**

```python
# tests/test_llm_element_filter.py
from server.services.omniparser_client import _filter_elements_for_llm
from server.models.schemas import UIElement

def test_llm_filter_hides_coordinates():
    el = UIElement(element_id="3", bbox=[100,200,300,400], element_type="icon",
                   text="search", confidence=0.95, center=[200,300],
                   left_elem_ids=["2"], right_elem_ids=["5"],
                   top_elem_ids=[], bottom_elem_ids=["8"])
    result = _filter_elements_for_llm([el])
    assert len(result) == 1
    r = result[0]
    assert r["id"] == "3"
    assert r["content"] == "search"
    assert r["left_ids"] == ["2"]
    assert r["right_ids"] == ["5"]
    assert r["top_ids"] == []
    assert r["bottom_ids"] == ["8"]
    # MUST NOT contain:
    assert "bbox" not in r
    assert "center" not in r
    assert "element_id" not in r
    assert "score" not in r
    assert "confidence" not in r
    assert "element_type" not in r
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_element_filter.py -v`
Expected: FAIL

- [ ] **Step 3: Implement _filter_elements_for_llm**

```python
# Add to server/services/omniparser_client.py

def _filter_elements_for_llm(elements: List[UIElement]) -> List[dict]:
    """Return LLM-visible element data — no coordinates, no scores."""
    result = []
    for el in elements:
        result.append({
            "id": el.element_id,
            "content": el.text or "",
            "left_ids": el.left_elem_ids,
            "right_ids": el.right_elem_ids,
            "top_ids": el.top_elem_ids,
            "bottom_ids": el.bottom_elem_ids,
        })
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_llm_element_filter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_llm_element_filter.py server/services/omniparser_client.py
git commit -m "feat: add _filter_elements_for_llm — hides bbox/center from LLM context"
```

---

### Task 4: Planning Agent

**Files:**
- Create: `server/services/planning/planner.py`

**Interfaces:**
- Consumes: `call_llm` from `server.services.llm.providers` (already exists)
- Produces: `plan_steps(query: str) -> PlanningResult` where `PlanningResult` is a dataclass: `goal: str, steps: list[PlanningStep]`

- [ ] **Step 1: Write failing test**

```python
# tests/test_planner.py
import pytest
from unittest.mock import patch, MagicMock
from server.services.planning.planner import plan_steps, PlanningResult

MOCK_LLM_RESPONSE = '''```json
{
  "goal": "打开网易云音乐并播放周杰伦的歌",
  "steps": [
    {"step_index": 1, "instruction": "打开网易云音乐应用"},
    {"step_index": 2, "instruction": "在搜索框中搜索'周杰伦'"},
    {"step_index": 3, "instruction": "点击播放第一首歌曲"}
  ]
}
```'''

def test_plan_steps_returns_structured_output():
    with patch("server.services.planning.planner.call_llm", return_value=MOCK_LLM_RESPONSE):
        result = plan_steps("打开网易云音乐，搜索周杰伦，播放第一首")
    
    assert isinstance(result, PlanningResult)
    assert result.goal == "打开网易云音乐并播放周杰伦的歌"
    assert len(result.steps) == 3
    assert result.steps[0].step_index == 1
    assert result.steps[0].instruction == "打开网易云音乐应用"
    assert result.steps[1].instruction == "在搜索框中搜索'周杰伦'"
    assert result.steps[2].instruction == "点击播放第一首歌曲"

def test_plan_steps_retries_on_malformed_json():
    bad_response = "not json at all {"
    with patch("server.services.planning.planner.call_llm") as mock_llm:
        mock_llm.side_effect = [bad_response, MOCK_LLM_RESPONSE]
        result = plan_steps("open calculator")
    assert mock_llm.call_count == 2
    assert len(result.steps) > 0

def test_plan_steps_fails_after_two_retries():
    with patch("server.services.planning.planner.call_llm", return_value="garbage {{{"):
        with pytest.raises(ValueError, match="Planning Agent"):
            plan_steps("do something")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planner.py -v`
Expected: FAIL — `plan_steps` not defined

- [ ] **Step 3: Implement planner.py**

```python
# server/services/planning/planner.py
"""
Planning Agent — text-only LLM call that decomposes a user query
into atomic operation steps. No screenshots, no OmniParser.
"""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from typing import List

from server.services.llm.providers import call_llm, extract_json_object
from server.models.schemas import PlanningStep

logger = logging.getLogger(__name__)

PLANNING_SYSTEM_PROMPT = """你是桌面操作规划专家。将用户的自然语言指令分解为原子操作步骤。

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

## 输出格式
输出纯JSON（无markdown代码块标记）：
{"goal": "一句话概括任务目标", "steps": [{"step_index": 1, "instruction": "..."}, ...]}

## 示例
输入："打开微信，给张三发'明天见'"
输出：{"goal": "打开微信并给张三发消息", "steps": [{"step_index": 1, "instruction": "打开微信应用"}, {"step_index": 2, "instruction": "找到张三的聊天并发送消息'明天见'"}]}

输入："打开浏览器，搜索天气"
输出：{"goal": "打开浏览器搜索天气", "steps": [{"step_index": 1, "instruction": "打开浏览器应用"}, {"step_index": 2, "instruction": "在搜索框中搜索'天气'"}]}"""


@dataclass
class PlanningResult:
    goal: str
    steps: List[PlanningStep] = field(default_factory=list)


def plan_steps(query: str, max_retries: int = 2) -> PlanningResult:
    """Decompose a user query into atomic steps using Planning Agent LLM.

    Args:
        query: Natural language user instruction
        max_retries: Max retries on JSON parse failure (default 2 = 3 total attempts)

    Returns:
        PlanningResult with goal string and list of PlanningStep

    Raises:
        ValueError: if Planning Agent fails after all retries
    """
    user_text = f'用户指令：「{query}」\n\n请将这条指令分解为操作步骤。只输出JSON。'

    for attempt in range(max_retries + 1):
        try:
            raw = call_llm(
                user_text=user_text,
                system_prompt=PLANNING_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=1024,
                timeout=60,
            )
            data = extract_json_object(raw)

            goal = data.get("goal", query)
            raw_steps = data.get("steps", [])
            if not raw_steps:
                # Fallback: single step = the whole query
                raw_steps = [{"step_index": 1, "instruction": query}]

            steps = []
            for s in raw_steps:
                if isinstance(s, str):
                    steps.append(PlanningStep(
                        step_index=len(steps) + 1,
                        instruction=s,
                    ))
                elif isinstance(s, dict):
                    steps.append(PlanningStep(
                        step_index=s.get("step_index", len(steps) + 1),
                        instruction=s.get("instruction", str(s)),
                    ))

            if not steps:
                raise ValueError("Planning Agent returned empty steps")

            logger.info(f"Planning: {goal} ({len(steps)} steps)")
            return PlanningResult(goal=goal, steps=steps)

        except Exception as e:
            logger.warning(f"Planning Agent attempt {attempt+1}/{max_retries+1} failed: {e}")
            if attempt >= max_retries:
                raise ValueError(f"Planning Agent failed after {max_retries+1} attempts: {e}") from e
            continue

    # Unreachable but type-checker safe
    raise ValueError("Planning Agent failed")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_planner.py server/services/planning/planner.py
git commit -m "feat: add Planning Agent — text-only structured step decomposition"
```

---

### Task 5: Execution Agent Core + Tool Definitions

**Files:**
- Create: `server/services/executor/agent.py`

**Interfaces:**
- Consumes:
  - `UIElement` from models (Task 1)
  - `_filter_elements_for_llm` from omniparser_client (Task 3)
  - `launch_app` from services/launcher (existing)
  - `safety.check` from services/executor/safety (existing)
  - `pyautogui`, `pyperclip`, `pydirectinput` (existing deps)
  - `call_llm` from services/llm/providers (existing)
- Produces:
  - `ExecutionAgent` class with `execute_step(step, goal, previous_steps, cancel_event) -> ExecutedStep`
  - All tool functions: `get_screen_info`, `click`, `double_click`, `type_text`, `press_key`, `scroll`, `wait`, `launch_app_tool`, `mark_step_done`, `mark_step_failed`
  - `EXECUTION_SYSTEM_PROMPT` constant

- [ ] **Step 1: Write failing tests for tool functions**

```python
# tests/test_execution_agent.py
import pytest
from unittest.mock import patch, MagicMock
from server.services.executor.agent import (
    ExecutionAgent, EXECUTION_SYSTEM_PROMPT,
    _build_tool_definitions, _build_context_for_llm,
)
from server.models.schemas import ExecutedStep, UIElement

def make_element(eid, content, bbox, left_ids=None, right_ids=None, top_ids=None, bottom_ids=None):
    x1, y1, x2, y2 = bbox
    return UIElement(
        element_id=str(eid), bbox=bbox, element_type="text",
        text=content, confidence=0.9,
        center=[(x1+x2)//2, (y1+y2)//2],
        left_elem_ids=left_ids or [],
        right_elem_ids=right_ids or [],
        top_elem_ids=top_ids or [],
        bottom_elem_ids=bottom_ids or [],
    )

class TestElementMap:
    def test_element_map_lookup(self):
        agent = ExecutionAgent()
        el = make_element("3", "search", [100,200,300,400])
        agent.element_map = {"3": el}
        assert agent.element_map["3"].element_id == "3"
        assert agent.element_map["3"].text == "search"

    def test_clear_element_map(self):
        agent = ExecutionAgent()
        agent.element_map = {"3": make_element("3", "x", [0,0,10,10])}
        agent.clear_element_map()
        assert agent.element_map == {}

    def test_stale_element_id_returns_error(self):
        agent = ExecutionAgent()
        agent.element_map = {}
        result = agent._do_click("99")
        assert result["success"] == False
        assert "not found" in result["error"]
        assert "get_screen_info" in result["error"]

class TestContextBuilder:
    def test_context_includes_goal_and_step(self):
        ctx = _build_context_for_llm(
            goal="test goal",
            current_step={"index": 2, "instruction": "do thing"},
            previous_steps=[
                {"index": 1, "instruction": "open app", "status": "done",
                 "action_summary": "launched 'App'"},
            ]
        )
        assert "test goal" in ctx
        assert "do thing" in ctx
        assert "launched 'App'" in ctx

class TestToolDefinitions:
    def test_all_tools_have_names_and_params(self):
        tools = _build_tool_definitions()
        tool_names = {t["function"]["name"] for t in tools}
        assert "get_screen_info" in tool_names
        assert "click" in tool_names
        assert "double_click" in tool_names
        assert "type_text" in tool_names
        assert "press_key" in tool_names
        assert "launch_app" in tool_names
        assert "mark_step_done" in tool_names
        assert "mark_step_failed" in tool_names
        # Verify click takes element_id (not coordinates)
        click_tool = [t for t in tools if t["function"]["name"] == "click"][0]
        params = click_tool["function"]["parameters"]["properties"]
        assert "element_id" in params
        assert "bbox_center" not in params
        assert "x" not in params
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_execution_agent.py -v`
Expected: FAIL

- [ ] **Step 3: Implement execution/agent.py**

```python
# server/services/executor/agent.py
"""
Execution Agent — LLM-driven tool-calling loop for each step.

The LLM observes the screen via get_screen_info, decides which tool to call,
executes via element_id (never coordinates), verifies, and marks step done/failed.
"""
from __future__ import annotations
import asyncio
import json
import logging
import threading
import time
from typing import Callable, Optional

import pyautogui
import pyperclip

from server.config import settings
from server.models.schemas import UIElement, ExecutedStep
from server.services.omniparser_client import parse_screenshot_full, _filter_elements_for_llm
from server.services.executor.safety import check_step
from server.services.llm.providers import call_llm, extract_json_object

logger = logging.getLogger(__name__)

MAX_TOOL_CALL_ROUNDS = getattr(settings, "MAX_TOOL_CALL_ROUNDS", None) or 15
STEP_RETRY_LIMIT = getattr(settings, "STEP_RETRY_LIMIT", None) or 1

EXECUTION_SYSTEM_PROMPT = """你是桌面自动化执行专家。你的任务是完成当前步骤。你可以调用工具来观察屏幕和执行操作。

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
- 禁止在 get_screen_info 之后引用之前的 element_id"""


# ═══════════════════════════════════════════════════════════════════════════
# Tool definitions (OpenAI function-calling format)
# ═══════════════════════════════════════════════════════════════════════════

def _build_tool_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "launch_app",
                "description": "通过Win+搜索启动应用程序。当步骤为打开应用时优先使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string", "description": "要启动的应用名称，如'网易云音乐'、'Calculator'"}
                    },
                    "required": ["app_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_screen_info",
                "description": "截取当前屏幕并通过OmniParser获取元素列表。返回元素的id、content和空间关系。每次调用会刷新element_map，旧的element_id全部失效。",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "click",
                "description": "单击指定元素。传入element_id而非坐标。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "string", "description": "元素ID，来自get_screen_info返回列表中的id字段"}
                    },
                    "required": ["element_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "double_click",
                "description": "双击指定元素。桌面图标和文件通常需要双击。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "string", "description": "元素ID"}
                    },
                    "required": ["element_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "type_text",
                "description": "点击元素获取焦点后，通过剪贴板粘贴文本（支持中文输入）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "string", "description": "目标输入框的元素ID"},
                        "text": {"type": "string", "description": "要输入的文本"}
                    },
                    "required": ["element_id", "text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "press_key",
                "description": "按键盘组合键。如'enter'、'ctrl+v'、'win'。多个键用+号连接。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keys": {"type": "string", "description": "组合键字符串，如 'enter' 或 'ctrl+v'"}
                    },
                    "required": ["keys"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "scroll",
                "description": "滚轮滚动。direction: 'up'或'down'。amount: 滚动量（1=一行）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "direction": {"type": "string", "enum": ["up", "down"]},
                        "amount": {"type": "integer", "description": "滚动量，默认3"}
                    },
                    "required": ["direction"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "wait",
                "description": "等待指定秒数，让界面响应。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "seconds": {"type": "number", "description": "等待秒数"}
                    },
                    "required": ["seconds"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "mark_step_done",
                "description": "标记当前步骤已成功完成。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string", "description": "完成原因，如'操作成功'或'precondition already satisfied'"}
                    },
                    "required": ["reason"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "mark_step_failed",
                "description": "标记当前步骤失败。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string", "description": "失败原因"}
                    },
                    "required": ["reason"]
                }
            }
        },
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Context builder
# ═══════════════════════════════════════════════════════════════════════════

def _build_context_for_llm(
    goal: str,
    current_step: dict,
    previous_steps: list[dict],
) -> str:
    """Build the context string passed to the LLM each turn."""
    parts = [f"## 任务目标\n{goal}\n"]

    if previous_steps:
        parts.append("## 已完成的步骤")
        for ps in previous_steps:
            parts.append(
                f"- Step {ps['index']}: {ps['instruction']} "
                f"→ {ps.get('action_summary', 'done')}"
            )

    parts.append(f"## 当前步骤\nStep {current_step['index']}: {current_step['instruction']}")
    parts.append("\n请完成当前步骤。你可以调用工具。每次只调用一个工具。")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Execution Agent
# ═══════════════════════════════════════════════════════════════════════════

class ExecutionAgent:
    """LLM-driven execution loop for one step at a time."""

    def __init__(self):
        self.element_map: dict[str, UIElement] = {}
        self.screen_elements: list[dict] = []
        self.tools = _build_tool_definitions()

    def clear_element_map(self):
        self.element_map = {}
        self.screen_elements = []

    # ── Tool implementations ──

    def _do_get_screen_info(self) -> dict:
        """Screenshot → OmniParser → rebuild element_map."""
        try:
            from core.screen_capture import capture_to_base64
            image_b64 = capture_to_base64(exclude_self=True, fmt="JPEG")
        except Exception:
            # Fallback: use mss directly
            import mss
            from PIL import Image
            from io import BytesIO
            import base64
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                img = sct.grab(monitor)
                pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                buf = BytesIO()
                pil.save(buf, format="JPEG", quality=70)
                image_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

        parse_result = parse_screenshot_full(image_b64)
        self.element_map = {e.element_id: e for e in parse_result.elements}
        self.screen_elements = _filter_elements_for_llm(parse_result.elements)

        return {
            "success": True,
            "elements": self.screen_elements,
            "element_count": len(self.screen_elements),
            "annotated_image": parse_result.annotated_image or image_b64,
        }

    def _do_launch_app(self, app_name: str) -> dict:
        from server.services.launcher import launch_app
        result = launch_app(app_name)
        return {
            "success": result.get("success", False),
            "app_name": app_name,
            "action_summary": f"launched app '{app_name}' via Win+Search",
        }

    def _do_click(self, element_id: str, double: bool = False) -> dict:
        element = self.element_map.get(element_id)
        if element is None:
            return {
                "success": False,
                "error": f"element_id '{element_id}' not found in current screen. "
                         f"Please call get_screen_info() again."
            }

        cx, cy = element.center
        safety = check_step(f"click element {element.text}")
        if safety.level == "red":
            return {
                "success": False,
                "error": f"action blocked (zone: red): {safety.reason}"
            }
        if safety.level == "yellow":
            return {
                "success": False,
                "error": f"action requires confirmation (zone: yellow): {safety.reason}. "
                         f"Choose a different target or try an alternative approach."
            }

        pyautogui.moveTo(cx, cy, duration=0.2)
        time.sleep(0.1)
        clicks = 2 if double else 1
        pyautogui.click(clicks=clicks)

        label = "double-clicked" if double else "clicked"
        return {
            "success": True,
            "clicked": element_id,
            "content": element.text,
            "action_summary": f"{label} element '{element.text}'",
        }

    def _do_type_text(self, element_id: str, text: str) -> dict:
        element = self.element_map.get(element_id)
        if element is None:
            return {
                "success": False,
                "error": f"element_id '{element_id}' not found in current screen. "
                         f"Please call get_screen_info() again."
            }

        cx, cy = element.center
        safety = check_step(f"type '{text}' into element")
        if safety.level == "red":
            return {"success": False, "error": f"action blocked (zone: red): {safety.reason}"}
        if safety.level == "yellow":
            return {
                "success": False,
                "error": f"action requires confirmation (zone: yellow): {safety.reason}. "
                         f"Choose a different target or try an alternative approach."
            }

        old_clipboard = pyperclip.paste()
        try:
            pyautogui.click(cx, cy)
            time.sleep(0.2)
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)  # ensure paste completes (Electron/VM apps may be slow)
        finally:
            pyperclip.copy(old_clipboard)

        return {
            "success": True,
            "typed": text,
            "into": element_id,
            "action_summary": f"typed '{text}' into '{element.text}'",
        }

    def _do_press_key(self, keys: str) -> dict:
        key_list = [k.strip() for k in keys.split("+")]
        if len(key_list) == 1:
            pyautogui.press(key_list[0])
        else:
            pyautogui.hotkey(*key_list)
        return {"success": True, "keys": keys, "action_summary": f"pressed '{keys}'"}

    def _do_scroll(self, direction: str, amount: int = 3) -> dict:
        amt = amount if direction == "up" else -amount
        pyautogui.scroll(amt)
        return {"success": True, "direction": direction, "amount": amount}

    # ── Tool dispatcher ──

    def dispatch_tool(self, tool_name: str, tool_args: dict) -> dict:
        """Execute a tool call and return the result dict."""
        if tool_name == "get_screen_info":
            return self._do_get_screen_info()
        elif tool_name == "launch_app":
            return self._do_launch_app(tool_args.get("app_name", ""))
        elif tool_name == "click":
            return self._do_click(tool_args.get("element_id", ""))
        elif tool_name == "double_click":
            return self._do_click(tool_args.get("element_id", ""), double=True)
        elif tool_name == "type_text":
            return self._do_type_text(
                tool_args.get("element_id", ""),
                tool_args.get("text", ""),
            )
        elif tool_name == "press_key":
            return self._do_press_key(tool_args.get("keys", "enter"))
        elif tool_name == "scroll":
            return self._do_scroll(
                tool_args.get("direction", "down"),
                tool_args.get("amount", 3),
            )
        elif tool_name == "wait":
            time.sleep(float(tool_args.get("seconds", 1.0)))
            return {"success": True, "waited": tool_args.get("seconds", 1.0)}
        elif tool_name == "mark_step_done":
            return {"__step_complete__": True, "success": True, "reason": tool_args.get("reason", "")}
        elif tool_name == "mark_step_failed":
            return {"__step_failed__": True, "reason": tool_args.get("reason", "")}
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    # ── Single-step execution ──

    def execute_step(
        self,
        step: ExecutedStep,
        goal: str,
        previous_steps: list[dict],
        cancel_event: Optional[threading.Event] = None,
    ) -> ExecutedStep:
        """Run the agent loop for a single step.

        Args:
            step: The step to execute (instruction populated, action/target/params empty)
            goal: Overall task goal from Planning Agent
            previous_steps: List of completed step dicts with action_summary
            cancel_event: Threading event set by user cancellation

        Returns:
            ExecutedStep with action, target_element_id, params, action_summary, status filled
        """
        step.status = "executing"
        self.clear_element_map()

        current_step_info = {"index": step.step_index, "instruction": step.instruction}
        context = _build_context_for_llm(goal, current_step_info, previous_steps)

        action_summary = None
        last_get_screen_info_image = None

        for round_num in range(MAX_TOOL_CALL_ROUNDS):
            if cancel_event and cancel_event.is_set():
                step.status = "failed"
                step.action_summary = "cancelled by user"
                return step

            # Build messages for this round
            messages = [{"role": "system", "content": EXECUTION_SYSTEM_PROMPT}]
            if round_num == 0:
                messages.append({"role": "user", "content": context})
            else:
                messages.append({"role": "user", "content": context})
                # Add tool call history
                messages.append({
                    "role": "user",
                    "content": "继续。你还可以调用工具。每次只调用一个工具。"
                })

            # Call LLM with tool definitions
            try:
                raw = self._call_llm_with_tools(messages)
            except Exception as e:
                logger.error(f"LLM call failed at round {round_num}: {e}")
                step.status = "failed"
                step.action_summary = f"LLM error: {e}"
                return step

            # Parse tool call from LLM response
            tool_name, tool_args = self._parse_tool_call(raw)
            if tool_name is None:
                logger.warning(f"LLM returned non-tool response: {raw[:200]}")
                # Feed the response back as context
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": "请调用一个工具。每次只调用一个工具。可用工具: get_screen_info, click, type_text, press_key, mark_step_done, mark_step_failed 等。"
                })
                continue

            # Dispatch tool
            result = self.dispatch_tool(tool_name, tool_args)
            logger.info(f"Round {round_num}: {tool_name}({tool_args}) → success={result.get('success')}")

            # Check for step completion signals
            if result.get("__step_complete__"):
                step.status = "done"
                step.action_summary = action_summary or result.get("reason", "step completed")
                return step
            if result.get("__step_failed__"):
                step.status = "failed"
                step.action_summary = result.get("reason", "step failed")
                return step

            # Accumulate action_summary from tool returns
            if result.get("action_summary"):
                action_summary = result["action_summary"]

            # Track last screenshot for SSE
            if tool_name == "get_screen_info" and result.get("annotated_image"):
                last_get_screen_info_image = result["annotated_image"]

            # Add assistant response + tool result to conversation
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "tool",
                "tool_call_id": "call_1",
                "content": json.dumps(result, ensure_ascii=False),
            })

        # Exhausted all rounds
        logger.warning(f"Step {step.step_index} exhausted {MAX_TOOL_CALL_ROUNDS} rounds")
        step.status = "failed"
        step.action_summary = "exceeded max tool calls"
        return step

    def _call_llm_with_tools(self, messages: list[dict]) -> str:
        """Call LLM with function-calling tools. Returns raw response text."""
        pc = self._get_provider_config()
        base = pc["base_url"].rstrip("/")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {pc['api_key']}",
        }
        body = {
            "model": pc["model"],
            "messages": messages,
            "max_tokens": 512,
            "temperature": 0.2,
            "tools": self.tools,
            "tool_choice": "auto",
        }
        import httpx
        url = f"{base}/chat/completions"
        with httpx.Client(timeout=120) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]
            msg = choice["message"]
            # Check for tool_calls in response
            if msg.get("tool_calls"):
                tc = msg["tool_calls"][0]
                func = tc["function"]
                return json.dumps({
                    "__tool_call__": True,
                    "name": func["name"],
                    "arguments": json.loads(func["arguments"]) if isinstance(func["arguments"], str) else func["arguments"],
                })
            return msg.get("content", "")

    def _parse_tool_call(self, raw: str) -> tuple[Optional[str], dict]:
        """Parse tool call from LLM response. Returns (tool_name, args_dict)."""
        try:
            data = json.loads(raw)
            if data.get("__tool_call__"):
                return data["name"], data.get("arguments", {})
        except json.JSONDecodeError:
            pass
        # Fallback: try to extract function-call-like JSON from raw text
        try:
            parsed = extract_json_object(raw)
            if "name" in parsed and "arguments" in parsed:
                return parsed["name"], parsed.get("arguments", {})
            if "tool" in parsed:
                return parsed["tool"], parsed.get("args", parsed.get("params", {}))
        except Exception:
            pass
        return None, {}

    @staticmethod
    def _get_provider_config() -> dict:
        from server.services.llm.providers import _get_provider_config
        return _get_provider_config()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_execution_agent.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_execution_agent.py server/services/executor/agent.py
git commit -m "feat: add Execution Agent with tool-calling loop and element_map lifecycle"
```

---

### Task 6: Router Refactor

**Files:**
- Modify: `server/services/planning/router.py`

**Interfaces:**
- Consumes: `plan_steps` (Task 4), `ExecutionAgent` (Task 5), `parse_screenshot_full` (Task 2), `launch_app` (existing)
- Produces: `process_query()` — calls Planning Agent, returns plan + first screenshot for display. Execution happens via `ExecutionAgent.execute_step()` called from engine.

- [ ] **Step 1: Refactor process_query in router.py**

```python
# server/services/planning/router.py — refactored process_query()

def process_query(
    query: str,
    image_base64: Optional[str] = None,
    screen_width: int = 1920,
    screen_height: int = 1080,
) -> ProcessResponse:
    """
    Planning phase: redline → intent → Planning Agent → first screenshot.
    Execution happens in engine via ExecutionAgent.
    """
    # 0. Redline check (unchanged)
    redline = check_redline(query)
    if redline.triggered:
        return ProcessResponse(
            task_id=str(uuid.uuid4()),
            success=False,
            goal="",
            intent=Intent(
                category="operation_guide",
                summary="请求被拦截",
                reference_type="explicit",
                confidence=1.0,
                needs_clarification=False,
            ),
            ui_elements=[],
            annotated_image=None,
            blueprint=Blueprint(
                name="红线拦截",
                total_steps=1,
                current_step=1,
                state="terminated",
            ),
            steps=[],
            redline=RedlineInfo(
                triggered=True,
                category=redline.category,
                message=redline.message,
                action=redline.action,
            ),
        )

    # 1. Intent classification (unchanged)
    from server.services.llm_ai import classify_intent, detect_reference_type
    category, summary, confidence = classify_intent(query)
    reference_type = detect_reference_type(query)
    intent = Intent(
        category=category,
        summary=summary,
        reference_type=reference_type,
        confidence=confidence,
        needs_clarification=confidence < 0.80,
    )

    # 2. Planning Agent — text-only structured plan
    from server.services.planning.planner import plan_steps, PlanningResult
    try:
        plan_result: PlanningResult = plan_steps(query)
    except Exception as e:
        logger.error(f"Planning Agent failed: {e}")
        # Fallback: single-step plan = the whole query
        plan_result = PlanningResult(
            goal=query,
            steps=[PlanningStep(step_index=1, instruction=query)],
        )

    goal = plan_result.goal
    planning_steps = plan_result.steps

    # 3. Convert PlanningStep → ExecutedStep (all pending)
    executed_steps: List[ExecutedStep] = []
    for ps in planning_steps:
        executed_steps.append(ExecutedStep(
            step_index=ps.step_index,
            instruction=ps.instruction,
            status="pending",
        ))

    # 4. Take initial screenshot for display (OmniParser SoM)
    ui_elements: List[UIElement] = []
    annotated_image: Optional[str] = image_base64
    detection_meta: dict = {"backend": "omniparser", "route": "L3"}

    if image_base64:
        try:
            from server.services.omniparser_client import parse_screenshot_full
            parse_result = parse_screenshot_full(image_base64)
            if parse_result.elements:
                ui_elements = parse_result.elements
                annotated_image = parse_result.annotated_image or image_base64
                detection_meta.update(parse_result.detection_meta or {})
        except Exception as e:
            logger.error(f"OmniParser initial scan failed: {e}")

    # 5. Build response
    blueprint = Blueprint(
        name=goal[:40] if goal else summary,
        total_steps=len(executed_steps),
        current_step=1,
        state="generated",
    )

    return ProcessResponse(
        task_id=str(uuid.uuid4()),
        success=True,
        goal=goal,
        intent=intent,
        ui_elements=ui_elements,
        annotated_image=annotated_image,
        blueprint=blueprint,
        steps=executed_steps,
        detection_meta=detection_meta,
    )
```

Keep `_choose_scenario`, `_MOCK_FALLBACKS`, `generate_steps` (for backward compat) unchanged. Remove `_serialize_elements`, `_call_executor_llm`, the old `process_query` inline prompts, and the Win+Search in-router logic (now handled by `launch_app` tool in Execution Agent).

- [ ] **Step 2: Commit**

```bash
git add server/services/planning/router.py
git commit -m "refactor: router uses Planning Agent; remove inline LLM prompts and coordinate output"
```

---

### Task 7: Engine Refactor — Agent Loop Integration

**Files:**
- Modify: `server/services/executor/engine.py`

**Interfaces:**
- Consumes: `ExecutionAgent` (Task 5), SSE event queue system (existing)
- Produces: `run_plan_agent_loop()` replaces `run_plan()`; pushes detailed SSE events

- [ ] **Step 1: Refactor engine.py**

Replace `run_plan()` with:

```python
# server/services/executor/engine.py — replace run_plan with:

def run_plan_agent_loop(
    task_id: str,
    goal: str,
    steps: list[dict],
    cancel_event: threading.Event,
) -> None:
    """
    Execute a plan using the Execution Agent loop.
    Pushes SSE events for real-time observability.

    Args:
        task_id: Task identifier
        goal: Overall task goal from Planning Agent
        steps: List of step dicts [{step_index, instruction, ...}]
        cancel_event: Set by /cancel endpoint
    """
    from server.services.executor.agent import ExecutionAgent
    from server.models.schemas import ExecutedStep

    q = register_task(task_id)
    agent = ExecutionAgent()
    previous_steps: list[dict] = []
    all_done = True

    for step_dict in steps:
        if cancel_event.is_set():
            _push_event(task_id, "task_cancelled", {})
            all_done = False
            break

        step_idx = step_dict["step_index"]
        instruction = step_dict["instruction"]

        _push_event(task_id, "step_start", {
            "step_index": step_idx,
            "instruction": instruction,
        })

        # Build ExecutedStep
        es = ExecutedStep(
            step_index=step_idx,
            instruction=instruction,
            status="executing",
        )

        # Run agent loop for this step
        try:
            result = agent.execute_step(
                step=es,
                goal=goal,
                previous_steps=previous_steps,
                cancel_event=cancel_event,
            )
        except Exception as e:
            logger.exception(f"Step {step_idx} execution crashed")
            result = ExecutedStep(
                step_index=step_idx,
                instruction=instruction,
                status="failed",
                action_summary=f"crash: {e}",
            )

        if result.status == "done":
            _push_event(task_id, "step_done", {
                "step_index": step_idx,
                "action_summary": result.action_summary or "",
            })
            previous_steps.append({
                "index": step_idx,
                "instruction": instruction,
                "status": "done",
                "action_summary": result.action_summary or "completed",
            })
        else:
            # Retry once
            logger.warning(f"Step {step_idx} failed, retrying once...")
            _push_event(task_id, "log", {
                "level": "warn",
                "message": f"步骤 {step_idx} 失败，重试中... ({result.action_summary})",
            })
            try:
                agent.clear_element_map()
                retry_result = agent.execute_step(
                    step=es,
                    goal=goal,
                    previous_steps=previous_steps,
                    cancel_event=cancel_event,
                )
                if retry_result.status == "done":
                    _push_event(task_id, "step_done", {
                        "step_index": step_idx,
                        "action_summary": retry_result.action_summary or "",
                    })
                    previous_steps.append({
                        "index": step_idx,
                        "instruction": instruction,
                        "status": "done",
                        "action_summary": retry_result.action_summary or "completed (retry)",
                    })
                    continue
            except Exception as e:
                logger.exception(f"Step {step_idx} retry crashed")

            _push_event(task_id, "step_failed", {
                "step_index": step_idx,
                "reason": result.action_summary or "step failed after retry",
            })
            all_done = False
            break

    if all_done:
        _push_event(task_id, "task_done", {
            "task_id": task_id,
            "goal": goal,
            "total_steps": len(steps),
            "completed_steps": len(previous_steps),
        })
    else:
        _push_event(task_id, "task_failed", {
            "reason": "step execution failed or cancelled",
            "failed_step": len(previous_steps) + 1,
        })

    # Delayed cleanup
    def _cleanup():
        time.sleep(3)
        unregister_task(task_id)

    threading.Thread(target=_cleanup, daemon=True).start()
```

Update the SSE event queue management to support `cancel_event`:

```python
# Update _cancel_flags to store threading.Event objects
_cancel_events: dict[str, threading.Event] = {}
_cancel_lock = threading.Lock()

def register_task(task_id: str) -> queue.Queue:
    q: queue.Queue = queue.Queue()
    with _queues_lock:
        _event_queues[task_id] = q
    with _cancel_lock:
        _cancel_events[task_id] = threading.Event()
    logger.info(f"[engine] registered task {task_id}")
    return q

def cancel_task(task_id: str) -> bool:
    with _cancel_lock:
        event = _cancel_events.get(task_id)
        if event:
            event.set()
            logger.info(f"[engine] cancel event set for {task_id}")
            return True
    # Also set old boolean cancel flag for backward compat
    with _cancel_lock:
        _cancel_flags[task_id] = True
    return False

def get_cancel_event(task_id: str) -> threading.Event:
    with _cancel_lock:
        return _cancel_events.get(task_id, threading.Event())

def unregister_task(task_id: str) -> None:
    with _queues_lock:
        _event_queues.pop(task_id, None)
    with _cancel_lock:
        _cancel_events.pop(task_id, None)
        _cancel_flags.pop(task_id, None)
    logger.info(f"[engine] unregistered task {task_id}")
```

- [ ] **Step 2: Commit**

```bash
git add server/services/executor/engine.py
git commit -m "refactor: engine uses ExecutionAgent loop with cancel_event and enriched SSE events"
```

---

### Task 8: API Route Adaptation

**Files:**
- Modify: `server/routes/demo.py`

**Interfaces:**
- Consumes: `process_query` (Task 6), `run_plan_agent_loop` (Task 7)
- Produces: `/execute` endpoint starts Planning + Agent loop, `/stream` delivers detailed SSE, `/cancel` sets cancel_event

- [ ] **Step 1: Update /execute endpoint in demo.py**

```python
# server/routes/demo.py — updated /execute endpoint

@router.post("/execute", summary="提交执行任务")
async def execute_task(
    request: ProcessRequest,
    demo_key: str = Depends(verify_demo_key),
):
    """
    接收截图与用户指令，生成执行计划并后台通过Agent循环执行。
    """
    from server.services.planning.router import process_query as plan_query
    from server.services.executor.engine import run_plan_agent_loop, get_cancel_event
    from server.services.executor.safety import check_query

    # 0. Redline
    safety = check_query(request.query)
    if safety.level == "red":
        return {
            "success": False,
            "error": {"code": "REDLINE", "message": safety.reason},
        }

    # 1. Planning (text-only, no OmniParser needed for planning)
    try:
        response = plan_query(
            request.query,
            request.image,
            screen_width=getattr(request, "screen_width", 1920),
            screen_height=getattr(request, "screen_height", 1080),
        )
    except Exception as e:
        return {
            "success": False,
            "error": {"code": "PLANNING_FAILED", "message": str(e)},
        }

    if not response.success:
        return {
            "success": False,
            "error": {
                "code": "NO_PLAN",
                "message": getattr(response, "redline", None) and response.redline.message or "规划失败",
            },
        }

    # 2. Save to stores
    task_store.create(response, request.query)
    TaskRepository.create_from_response(response, request.query)

    # 3. Get cancel event BEFORE starting thread
    cancel_event = get_cancel_event(response.task_id)

    # 4. Convert steps to dicts for engine
    steps_raw = [s.model_dump() for s in response.steps]

    # 5. Background Agent Loop
    thread = threading.Thread(
        target=run_plan_agent_loop,
        args=(response.task_id, response.goal, steps_raw, cancel_event),
        daemon=True,
    )
    thread.start()

    # 6. Return plan immediately
    return {
        "task_id": response.task_id,
        "success": True,
        "plan": {
            "goal": response.goal,
            "total_steps": len(response.steps),
            "steps": [
                {"step_index": s.step_index, "instruction": s.instruction}
                for s in response.steps
            ],
        },
        "screenshot_base64": response.annotated_image,
        "detection_meta": response.detection_meta,
    }
```

- [ ] **Step 2: Update /stream to handle all SSE event types**

```python
# In /stream endpoint, update the event termination condition:
    while True:
        try:
            event = q.get(timeout=30)
            yield _format_sse(event["event"], event["data"])
            if event["event"] in ("task_done", "task_failed", "task_cancelled"):
                break
        except Exception:
            yield _format_sse("heartbeat", {"timestamp": str(time.time())})
```

- [ ] **Step 3: Update /cancel endpoint**

```python
@router.post("/cancel", summary="取消/停止任务")
async def cancel_task(
    request: CancelRequest,
    demo_key: str = Depends(verify_demo_key),
):
    from server.services.executor.engine import cancel_task as engine_cancel
    ok = engine_cancel(request.task_id)

    state = task_store.get(request.task_id)
    if state:
        from server.services.planning.blueprint_engine import BlueprintEngine
        BlueprintEngine().terminate(state)
        task_store.update(state)

    return {
        "success": ok,
        "message": "任务已取消" if ok else "任务不存在或已结束",
        "task_id": request.task_id,
    }
```

- [ ] **Step 4: Commit**

```bash
git add server/routes/demo.py
git commit -m "refactor: /execute uses Agent loop, enriched SSE events, cancel via threading.Event"
```

---

### Task 9: Config Updates

**Files:**
- Modify: `server/config.py`

- [ ] **Step 1: Add new config keys**

```python
# Add to Config class in server/config.py:

    # Agent loop tuning
    MAX_TOOL_CALL_ROUNDS: int = int(os.getenv("MAX_TOOL_CALL_ROUNDS", "15"))
    STEP_RETRY_LIMIT: int = int(os.getenv("STEP_RETRY_LIMIT", "1"))
```

- [ ] **Step 2: Commit**

```bash
git add server/config.py
git commit -m "feat: add MAX_TOOL_CALL_ROUNDS and STEP_RETRY_LIMIT config keys"
```

---

### Task 10: Integration Tests

**Files:**
- Create: `tests/test_agent_loop_integration.py`

- [ ] **Step 1: Write mock-based integration test**

```python
# tests/test_agent_loop_integration.py
import json
import pytest
import threading
from unittest.mock import patch, MagicMock

from server.services.planning.planner import plan_steps, PlanningResult
from server.services.executor.agent import ExecutionAgent
from server.models.schemas import ExecutedStep, UIElement


class TestPlanningToExecution:
    """Integration: Planning output feeds into Execution Agent input."""

    @patch("server.services.planning.planner.call_llm")
    def test_plan_output_compatible_with_execution(self, mock_llm):
        mock_llm.return_value = json.dumps({
            "goal": "test goal",
            "steps": [
                {"step_index": 1, "instruction": "step one"},
                {"step_index": 2, "instruction": "step two"},
            ]
        })
        result = plan_steps("do something")
        assert len(result.steps) == 2
        # Convert to ExecutedStep
        for ps in result.steps:
            es = ExecutedStep(step_index=ps.step_index, instruction=ps.instruction)
            assert es.instruction == ps.instruction
            assert es.status == "pending"


class TestMockExecutionLoop:
    """Full agent loop with mocked LLM returning preset tool calls."""

    def make_agent_with_elements(self):
        agent = ExecutionAgent()
        el = UIElement(
            element_id="1", bbox=[100,200,300,400], element_type="text",
            text="搜索框", confidence=0.9, center=[200,300],
        )
        agent.element_map = {"1": el}
        return agent

    @patch.object(ExecutionAgent, '_call_llm_with_tools')
    def test_step_click_flow(self, mock_llm):
        """Simulate: get_screen_info → click → mark_step_done."""
        call_count = [0]
        def mock_call(messages):
            call_count[0] += 1
            if call_count[0] == 1:
                return json.dumps({
                    "__tool_call__": True,
                    "name": "get_screen_info",
                    "arguments": {},
                })
            elif call_count[0] == 2:
                return json.dumps({
                    "__tool_call__": True,
                    "name": "click",
                    "arguments": {"element_id": "1"},
                })
            else:
                return json.dumps({
                    "__tool_call__": True,
                    "name": "mark_step_done",
                    "arguments": {"reason": "click successful"},
                })
        mock_llm.side_effect = mock_call

        agent = self.make_agent_with_elements()
        step = ExecutedStep(step_index=1, instruction="点击搜索框")
        result = agent.execute_step(step, "test goal", [])

        assert result.status == "done"

    @patch.object(ExecutionAgent, '_call_llm_with_tools')
    def test_step_failure_signal(self, mock_llm):
        """Simulate: get_screen_info → mark_step_failed (element not found)."""
        call_count = [0]
        def mock_call(messages):
            call_count[0] += 1
            if call_count[0] == 1:
                return json.dumps({
                    "__tool_call__": True,
                    "name": "get_screen_info",
                    "arguments": {},
                })
            else:
                return json.dumps({
                    "__tool_call__": True,
                    "name": "mark_step_failed",
                    "arguments": {"reason": "element not found on screen"},
                })
        mock_llm.side_effect = mock_call

        agent = self.make_agent_with_elements()
        step = ExecutedStep(step_index=1, instruction="点击不存在的按钮")
        result = agent.execute_step(step, "test goal", [])

        assert result.status == "failed"

    @patch.object(ExecutionAgent, '_call_llm_with_tools')
    def test_precondition_already_satisfied(self, mock_llm):
        """Simulate: LLM immediately calls mark_step_done with precondition text."""
        mock_llm.return_value = json.dumps({
            "__tool_call__": True,
            "name": "mark_step_done",
            "arguments": {"reason": "precondition already satisfied"},
        })

        agent = ExecutionAgent()
        step = ExecutedStep(step_index=2, instruction="打开浏览器应用")
        result = agent.execute_step(
            step, "open browser and search",
            [{"index": 1, "instruction": "打开浏览器应用", "status": "done",
              "action_summary": "launched app 'Chrome' via Win+Search"}],
        )
        assert result.status == "done"

    def test_cancel_mid_step(self):
        """Cancel event set before execute_step should abort."""
        agent = ExecutionAgent()
        step = ExecutedStep(step_index=1, instruction="test")
        cancel_event = threading.Event()
        cancel_event.set()  # already cancelled
        result = agent.execute_step(step, "goal", [], cancel_event=cancel_event)
        assert result.status == "failed"
        assert "cancelled" in (result.action_summary or "").lower()

    def test_stale_element_id_after_rescan(self):
        """After second get_screen_info, old element_ids are invalid."""
        agent = ExecutionAgent()
        el = UIElement(
            element_id="1", bbox=[0,0,10,10], element_type="text",
            text="test", confidence=0.9, center=[5,5],
        )
        agent.element_map = {"1": el}
        # Simulate get_screen_info with new elements
        with patch.object(agent, '_do_get_screen_info') as mock_scan:
            mock_scan.return_value = {"success": True, "elements": [], "element_count": 0}
            agent._do_get_screen_info()
        # Old element "1" is gone
        result = agent._do_click("1")
        assert result["success"] == False
        assert "not found" in result["error"]
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_agent_loop_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_agent_loop_integration.py
git commit -m "test: add integration tests for Planning→Execution flow and mock LLM loops"
```

---

### Task 11: Final Wiring — Run All Tests

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass (or known pre-existing failures unrelated to our changes)

- [ ] **Step 2: Run existing tests to ensure no regressions**

Run: `pytest tests/ -v -k "not test_agent" --tb=short`
Expected: No new failures introduced

- [ ] **Step 3: Verify imports**

Run: `python -c "from server.services.planning.planner import plan_steps; from server.services.executor.agent import ExecutionAgent; print('All imports OK')"`
Expected: "All imports OK"

- [ ] **Step 4: Commit final check**

```bash
git add -A
git status
git commit -m "feat: complete Agent Loop Execution Mode — all pieces wired"
```

---

## Implementation Order Summary

| Task | What | Depends On |
|------|------|------------|
| 1 | Data model changes | nothing |
| 2 | Spatial relations in OmniParser client | Task 1 |
| 3 | LLM-visible element filter | Task 2 |
| 4 | Planning Agent | Task 3 (filter) |
| 5 | Execution Agent + tools | Task 2,3 |
| 6 | Router refactor | Task 4,5 |
| 7 | Engine refactor | Task 5 |
| 8 | API routes adaptation | Task 6,7 |
| 9 | Config updates | nothing |
| 10 | Integration tests | Task 5,6,7 |
| 11 | Final wiring + full test run | All above |
