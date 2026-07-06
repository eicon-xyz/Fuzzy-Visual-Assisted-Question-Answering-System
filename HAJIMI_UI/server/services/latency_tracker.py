"""
Pipeline latency breakdown — records per-phase timings for detection_meta.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class LatencyBreakdown:
    """Structured timing for process / locate / step flows."""

    route: str = ""
    intent_ms: int = 0
    route_select_ms: int = 0
    screenshot_decode_ms: int = 0
    parse_ms: int = 0
    plan_ms: int = 0
    locate_ms: int = 0
    llm_ms: int = 0
    bind_ms: int = 0
    total_ms: int = 0
    parse_skipped: bool = False
    parse_cache_hit: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    def mark_parse(self, ms: int, *, skipped: bool = False, cache_hit: bool = False) -> None:
        self.parse_ms = ms
        self.parse_skipped = skipped
        self.parse_cache_hit = cache_hit

    def mark_plan(self, ms: int) -> None:
        self.plan_ms = ms
        self.llm_ms = self.llm_ms + ms

    def mark_locate(self, ms: int) -> None:
        self.locate_ms = ms
        self.llm_ms = self.llm_ms + ms

    def finalize(self, started_at: float) -> None:
        self.total_ms = int((time.perf_counter() - started_at) * 1000)

    def to_meta(self) -> Dict[str, Any]:
        return {
            "route": self.route,
            "latency_breakdown": {
                "intent_ms": self.intent_ms,
                "route_select_ms": self.route_select_ms,
                "screenshot_decode_ms": self.screenshot_decode_ms,
                "parse_ms": self.parse_ms,
                "plan_ms": self.plan_ms,
                "locate_ms": self.locate_ms,
                "llm_ms": self.llm_ms,
                "bind_ms": self.bind_ms,
                "total_ms": self.total_ms,
            },
            "parse_latency_ms": self.parse_ms,
            "parse_skipped": self.parse_skipped,
            "parse_cache_hit": self.parse_cache_hit,
            **self.extra,
        }


class PhaseTimer:
    """Context manager for a single phase."""

    def __init__(self) -> None:
        self.ms: int = 0
        self._t0: float = 0.0

    def __enter__(self) -> "PhaseTimer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self.ms = int((time.perf_counter() - self._t0) * 1000)
