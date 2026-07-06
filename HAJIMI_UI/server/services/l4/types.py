"""L4 数据类型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from server.models.schemas import Annotation


@dataclass
class L4ScreenContext:
    """B 端传入的屏幕上下文，用于校准与 Prompt 增强。"""

    capture_size: Optional[List[int]] = None  # 原始截图 [w,h]
    upload_size: Optional[List[int]] = None  # 实际上传图 [w,h]
    screen_metrics: Optional[Dict[str, Any]] = None
    window_title: Optional[str] = None
    screen_hints: str = ""

    @property
    def reference_resolution(self) -> Optional[List[int]]:
        """坐标参考分辨率：优先原始 capture，否则 upload。"""
        if self.capture_size and len(self.capture_size) >= 2:
            return [int(self.capture_size[0]), int(self.capture_size[1])]
        if self.upload_size and len(self.upload_size) >= 2:
            return [int(self.upload_size[0]), int(self.upload_size[1])]
        return None


@dataclass
class L4LocateResult:
    annotation: Optional[Annotation] = None
    reference_resolution: Optional[List[int]] = None
    llm_meta: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0


@dataclass
class L4ProcessResult:
    raw_steps: List[dict]
    constraints: Optional[dict]
    llm_meta: Dict[str, Any]
    reference_resolution: Optional[List[int]]
    first_step_annotation: Optional[Annotation] = None
