"""
Pydantic models for chain outputs (structured LLM responses).

Python equivalent of OpenGuider's agent/schemas.js (Zod schemas).

Each chain returns a validated Pydantic model. The models enforce
coordinate ranges (0-1000), required fields, and enum constraints.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal


# ── Planner chain output ──────────────────────────────────────────────────────


class PlanStepDef(BaseModel):
    """A single step in the generated plan."""
    id: str = Field(..., description="Step identifier (e.g., 'step_1')")
    title: str = Field(..., description="Short action title")
    instruction: str = Field(..., description="Detailed instruction")
    success_criteria: str = Field(
        default="",
        description="How to know this step is complete",
    )
    guidance_mode: Literal["point_and_explain", "explain_only"] = Field(
        default="point_and_explain",
        description="Whether to show a pointer on screen",
    )
    requires_screenshot_check: bool = Field(
        default=True,
        description="Whether to verify with a new screenshot after this step",
    )
    can_user_mark_done: bool = Field(
        default=True,
        description="Whether user can manually mark this step as done",
    )
    fallback_hints: List[str] = Field(
        default_factory=list,
        description="Alternative descriptions if element not found",
    )


class PlannerOutput(BaseModel):
    """Complete planner chain output."""
    goal: str = Field(..., description="Restated user goal")
    assistant_response: str = Field(
        default="",
        description="Natural language response to the user",
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description="Assumptions made about the user's context",
    )
    steps: List[PlanStepDef] = Field(
        ...,
        description="Ordered execution steps",
        min_length=1,
    )


# ── Executor/Locator chain output ──────────────────────────────────────────────


class NormalizedCoordinate(BaseModel):
    """Coordinate in 0-1000 normalized range."""
    x: float = Field(..., ge=0, le=1000, description="X in 0-1000 range")
    y: float = Field(..., ge=0, le=1000, description="Y in 0-1000 range")


class StepPointerOutput(BaseModel):
    """Executor chain output — where to point on screen."""
    coordinate: Optional[NormalizedCoordinate] = Field(
        default=None,
        description="Normalized coordinate of target element, or null if not found",
    )
    label: Optional[str] = Field(
        default=None,
        description="Name of the target element for verification",
    )
    explanation: str = Field(
        default="",
        description="Explanation of what was found",
    )
    should_point: bool = Field(
        default=False,
        description="Whether to show a pointer on screen",
    )

    @field_validator("label", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "":
            return None
        return v


# ── Evaluator chain output ────────────────────────────────────────────────────


class EvaluationOutput(BaseModel):
    """Evaluator chain output — did the user complete the step?"""
    status: Literal["done", "not_done", "blocked", "uncertain"] = Field(
        ...,
        description="Current step completion status",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in the evaluation (0-1)",
    )
    rationale: str = Field(
        default="",
        description="Reasoning behind the evaluation",
    )
    suggested_action: Literal["advance", "repeat_guidance", "replan"] = Field(
        default="advance",
        description="Recommended next action",
    )
    assistant_response: str = Field(
        default="",
        description="Natural language feedback to the user",
    )


# ── Replanner chain output ────────────────────────────────────────────────────


class ReplannerOutput(BaseModel):
    """Replanner chain output — revised plan when stuck."""
    assistant_response: str = Field(
        default="",
        description="Explanation of plan changes",
    )
    goal: str = Field(..., description="Restated goal (unchanged)")
    steps: List[PlanStepDef] = Field(
        ...,
        description="Revised remaining steps",
        min_length=1,
    )


# ── Utility: JSON extraction ──────────────────────────────────────────────────


def extract_json_object(raw_text: str) -> dict:
    """Extract JSON object from LLM response text.

    Handles:
    - Markdown code blocks (```json ... ```)
    - Raw JSON objects
    - [POINT:x,y:label] tags embedded in text

    Maps to OpenGuider's schemas.js extractJSONObject().
    """
    import json
    import re

    if not raw_text:
        raise ValueError("Empty response text")

    text = raw_text.strip()

    # Try markdown code block first
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if code_block_match:
        text = code_block_match.group(1).strip()

    # Find JSON object boundaries
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and start < end:
        json_str = text[start : end + 1]
        return json.loads(json_str)

    # Last resort: try to parse the whole text
    raise ValueError("No JSON object found in response")


def parse_structured_json(
    raw_text: str,
    schema_class,
    is_locator: bool = False,
) -> BaseModel:
    """Parse raw LLM text into a validated Pydantic model.

    Maps to OpenGuider's schemas.js parseStructuredJSON().

    For locator chains, also searches for [POINT:x,y:label] tags
    as a fallback extraction method.

    Args:
        raw_text: Raw LLM response text
        schema_class: Pydantic model class to validate against
        is_locator: If True, also search for [POINT] tags

    Returns:
        Validated Pydantic model instance

    Raises:
        ValueError: If parsing or validation fails
    """
    import re

    data = extract_json_object(raw_text)

    # For locator chains, also try to find [POINT:x,y:label] tags
    if is_locator:
        point_match = re.search(
            r"\[POINT:\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*:?\s*([^\]]*?)\]",
            raw_text,
        )
        if point_match and not data.get("coordinate"):
            data["coordinate"] = {
                "x": float(point_match.group(1)),
                "y": float(point_match.group(2)),
            }
            if point_match.group(3).strip():
                data["label"] = point_match.group(3).strip()
            data["should_point"] = True

    # Validate
    return schema_class(**data)


def format_user_error(error: Exception) -> str:
    """Format a structured chain error into a user-friendly message.

    Maps to OpenGuider's structured.js formatStructuredUserError().
    """
    error_str = str(error).lower()

    if "401" in error_str or "403" in error_str or "unauthorized" in error_str:
        return "AI 服务认证失败，请检查 API Key 配置。"
    if "429" in error_str or "rate limit" in error_str:
        return "AI 服务请求过于频繁，请稍后再试。"
    if "402" in error_str or "insufficient" in error_str:
        return "AI 服务额度不足，请检查账户余额。"
    if "500" in error_str or "server error" in error_str:
        return "AI 服务暂时不可用，请稍后重试。"
    if "json" in error_str or "parse" in error_str:
        return "AI 返回了无法解析的响应，请重试。"
    if "timeout" in error_str:
        return "AI 服务响应超时，请检查网络连接。"
    return f"AI 服务异常: {str(error)[:100]}"
