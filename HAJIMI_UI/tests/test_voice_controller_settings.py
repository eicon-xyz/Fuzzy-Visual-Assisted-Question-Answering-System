"""VoiceIntegrationController voice_settings wiring (B-C P0)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from client.integration.controller import VoiceIntegrationController


def test_start_uses_google_engine_from_voice_settings():
    ctrl = VoiceIntegrationController(
        voice_settings={
            "asr_engine": "google",
            "asr_language": "zh-CN",
            "microphone_index": None,
            "vosk_model_path": "models/vosk-model-small-cn-0.22",
            "asr_silence_sec": 5.0,
            "asr_start_timeout_sec": 10.0,
        }
    )
    ctrl.start()
    try:
        health = ctrl.health_check()
        assert health.asr_engine == "google"
        assert ctrl._asr_client is not None
        assert ctrl._asr_client.active_engine == "google"
    finally:
        ctrl.shutdown()


def test_apply_voice_settings_rebuilds_asr_client():
    ctrl = VoiceIntegrationController(voice_settings={"asr_engine": "vosk"})
    ctrl.start()
    try:
        ctrl.apply_voice_settings({"asr_engine": "google"})
        assert ctrl.health_check().asr_engine == "google"
    finally:
        ctrl.shutdown()


def test_parse_microphone_index():
    assert VoiceIntegrationController._parse_microphone_index(None) is None
    assert VoiceIntegrationController._parse_microphone_index(2) == 2
    assert VoiceIntegrationController._parse_microphone_index(-1) is None
