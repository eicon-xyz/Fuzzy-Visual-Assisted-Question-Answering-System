# [VERIFY] B↔C 信号桥验收 — 见 docs/FILE-MAP.md
# 用途: BCIntegrationSignals 九信号 + C 控制器 bind_to 不崩溃
# 运行: python scripts/verify_bc_signals.py
"""Verify B-C integration signal bus and optional VoiceIntegrationController bind."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt5.QtWidgets import QApplication

from core.bc_signals import AuditRecordBuilder, BCIntegrationSignals
from core.repo_paths import resolve_repo_root


REQUIRED_SIGNALS = (
    "asr_start",
    "asr_stop",
    "asr_result",
    "tts_enqueue",
    "tts_status",
    "audit_submit",
    "audit_status",
    "config_updated",
    "health_check_request",
    "health_result",
)


def _check_signal_bus() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    bus = BCIntegrationSignals()
    for name in REQUIRED_SIGNALS:
        assert hasattr(bus, name), f"missing signal: {name}"
    bus.parent()  # keep reference
    del bus
    assert app is not None


def _check_audit_builder() -> None:
    record = AuditRecordBuilder.build(
        task_id="test-id",
        query="怎么安装微信",
        intent={"category": "operation_guide", "complexity_score": 20},
        route="L3",
        steps=[{"description": "step1"}],
        completed_steps=1,
        result="success",
        started_at=None,
    )
    assert record["task_id"] == "test-id"
    assert record["result"] == "success"
    assert record["intent_category"] == "operation_guide"


def _check_c_bind_optional() -> None:
    root = resolve_repo_root()
    client_dir = root / "client"
    if not client_dir.is_dir():
        print("[verify_bc_signals] SKIP C bind — client/ not found")
        return
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    try:
        from client.integration.controller import VoiceIntegrationController
    except ImportError as exc:
        print(f"[verify_bc_signals] SKIP C bind — import failed: {exc}")
        return

    app = QApplication.instance() or QApplication(sys.argv)
    bus = BCIntegrationSignals()
    shared = {"voice_settings": {"tts_enabled": True, "asr_enabled": True}}
    ctrl = VoiceIntegrationController(server_url="http://127.0.0.1:8010")
    ctrl.start()
    ctrl.bind_to(bus, shared)

    # 方法调用健康检查
    health = ctrl.health_check()
    assert hasattr(health, "overall")

    # 信号往返：health_check_request → health_result（修复 _has_pyqt_signals 后必须通）
    received = []

    def _on_health(h):
        received.append(h)

    bus.health_result.connect(_on_health)
    bus.health_check_request.emit()
    app.processEvents()
    assert received, "health_result not emitted after health_check_request (signals not bound?)"
    h = received[0]
    asr_ok = h.asr_available if hasattr(h, "asr_available") else h.get("asr_available")
    assert asr_ok, f"expected asr_available=True, got {h!r}"

    ctrl.shutdown()
    print("[verify_bc_signals] C bind_to OK (health signal roundtrip OK)")
    assert app is not None


def main() -> int:
    _check_signal_bus()
    _check_audit_builder()
    os.environ.setdefault("HAJIMI_C_ENABLED", "1")
    _check_c_bind_optional()
    print("verify_bc_signals: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
