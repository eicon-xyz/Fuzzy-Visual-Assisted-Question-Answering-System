"""Assist 数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from server.models.schemas import Annotation


@dataclass
class CandidateElement:
    name: str
    bbox: List[int]
    confidence: float = 0.0
    source: str = "unknown"
    element_type: str = "unknown"
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssistContext:
    bundle: dict
    capture_size: Optional[List[int]] = None
    upload_size: Optional[List[int]] = None
    screen_metrics: Optional[dict] = None
    candidates: List[CandidateElement] = field(default_factory=list)
    prompt_hints: str = ""

    @property
    def scene_hint(self) -> str:
        screen = self.bundle.get("screen") or {}
        return screen.get("scene_hint") or "unknown"

    @property
    def foreground(self) -> dict:
        return self.bundle.get("foreground") or {}


@dataclass
class HybridLocateResult:
    hit: bool = False
    annotation: Optional[Annotation] = None
    reference_resolution: Optional[List[int]] = None
    source: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
