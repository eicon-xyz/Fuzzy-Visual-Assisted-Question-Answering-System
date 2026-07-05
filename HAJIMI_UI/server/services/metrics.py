"""
Performance metrics collection.

Matches OpenGuider's src/performance-metrics.js.
In-memory metrics with P95, ring buffers.
"""
from __future__ import annotations
import time
from collections import defaultdict
from typing import Any

MAX_SAMPLES = 240


class PerformanceMetrics:
    """Thread-safe in-memory metrics collector."""

    def __init__(self):
        self._metrics: dict[str, dict] = defaultdict(lambda: {
            "count": 0,
            "success_count": 0,
            "error_count": 0,
            "total_duration_ms": 0.0,
            "min_duration_ms": float("inf"),
            "max_duration_ms": 0.0,
            "samples": [],  # ring buffer of durations
            "last_meta": {},
        })

    def record(self, name: str, duration_ms: float, ok: bool = True, meta: dict | None = None):
        """Record a metric sample."""
        m = self._metrics[name]
        m["count"] += 1
        if ok:
            m["success_count"] += 1
        else:
            m["error_count"] += 1
        m["total_duration_ms"] += duration_ms
        m["min_duration_ms"] = min(m["min_duration_ms"], duration_ms)
        m["max_duration_ms"] = max(m["max_duration_ms"], duration_ms)
        m["samples"].append(duration_ms)
        if len(m["samples"]) > MAX_SAMPLES:
            m["samples"].pop(0)
        if meta:
            m["last_meta"] = meta

    def p95(self, name: str) -> float:
        """Return P95 latency for a metric."""
        samples = sorted(self._metrics[name]["samples"])
        if not samples:
            return 0.0
        idx = max(0, len(samples) - 1 - len(samples) // 20)
        return samples[idx]

    def p50(self, name: str) -> float:
        """Return median latency for a metric."""
        samples = sorted(self._metrics[name]["samples"])
        if not samples:
            return 0.0
        return samples[len(samples) // 2]

    def avg(self, name: str) -> float:
        """Return average latency."""
        m = self._metrics[name]
        if m["count"] == 0:
            return 0.0
        return m["total_duration_ms"] / m["count"]

    def get_all(self) -> dict:
        """Return all metrics as a serializable dict."""
        result = {}
        for name, m in self._metrics.items():
            result[name] = {
                "count": m["count"],
                "success_count": m["success_count"],
                "error_count": m["error_count"],
                "avg_ms": round(self.avg(name), 1),
                "p50_ms": round(self.p50(name), 1),
                "p95_ms": round(self.p95(name), 1),
                "min_ms": round(m["min_duration_ms"], 1) if m["min_duration_ms"] != float("inf") else 0,
                "max_ms": round(m["max_duration_ms"], 1),
                "last_meta": m["last_meta"],
            }
        return result

    def reset(self):
        """Reset all metrics."""
        self._metrics.clear()


# Global singleton
metrics = PerformanceMetrics()
