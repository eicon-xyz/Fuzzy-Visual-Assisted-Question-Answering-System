"""B↔C 进程内信号总线与审计记录构造（见 docs/b-c-api-contract.md）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from PyQt5.QtCore import QObject, pyqtSignal


DEFAULT_VOICE_SETTINGS: Dict[str, Any] = {
    "tts_enabled": True,
    "tts_speed": 0.85,
    "tts_engine": "pyttsx3",
    "asr_enabled": True,
    "asr_engine": "vosk",
    "asr_language": "zh-CN",
    "config_pull_interval_min": 30,
}


class BCIntegrationSignals(QObject):
    """B 侧暴露给 C 的九个交互点。"""

    asr_start = pyqtSignal()
    asr_stop = pyqtSignal()
    asr_result = pyqtSignal(dict)
    tts_enqueue = pyqtSignal(str, int, bool)
    tts_status = pyqtSignal(str, str, int)
    audit_submit = pyqtSignal(dict)
    audit_status = pyqtSignal(str, int, int, object)
    config_updated = pyqtSignal(dict)
    health_check_request = pyqtSignal()
    health_result = pyqtSignal(object)


class AuditRecordBuilder:
    """从 AppController 状态组装 AuditRecord dict。"""

    @staticmethod
    def build(
        *,
        task_id: Optional[str],
        query: str,
        intent: Optional[dict],
        route: Optional[str],
        steps: list,
        completed_steps: int,
        result: str,
        started_at: Optional[float],
        feedback_type: Optional[str] = None,
        comment: Optional[str] = None,
        fingerprint_mismatches: int = 0,
        redline_triggered: bool = False,
    ) -> dict:
        import time

        duration_ms = 0
        if started_at is not None:
            duration_ms = max(0, int((time.time() - started_at) * 1000))

        intent = intent or {}
        category = intent.get("category") or "operation_guide"
        complexity = intent.get("complexity_score")
        if complexity is None:
            complexity = min(100, max(0, len(steps) * 10 + len(query) // 4))

        route_val = route or intent.get("route") or "L3"
        if route_val not in ("L2", "L3"):
            route_val = "L3" if str(route_val).upper().startswith("L3") else "L2"

        ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

        record: Dict[str, Any] = {
            "task_id": task_id or "",
            "query": query or "",
            "intent_category": category,
            "complexity_score": int(complexity),
            "route": route_val,
            "total_steps": len(steps),
            "completed_steps": max(0, min(completed_steps, len(steps))),
            "result": result,
            "duration_ms": duration_ms,
            "fingerprint_mismatches": fingerprint_mismatches,
            "redline_triggered": redline_triggered,
            "timestamp": ts,
        }
        if feedback_type:
            record["feedback_type"] = feedback_type
        if comment:
            record["comment"] = comment
        return record
