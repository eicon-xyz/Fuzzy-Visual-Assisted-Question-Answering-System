"""ASRClient auto-finalize and idempotent stop (B-C voice integration)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from client.voice.asr_client import ASRClient, ASREngine, ASRResult


def test_stop_and_transcribe_is_idempotent():
    asr = ASRClient(engine=ASREngine.MOCK)
    asr.start_recording()
    asr._recording = False
    first = asr.stop_and_transcribe()
    second = asr.stop_and_transcribe()
    assert first.transcript == second.transcript
    assert asr._finalized is True


def test_silence_env_defaults():
    asr = ASRClient(engine=ASREngine.MOCK)
    assert asr._silence_sec == 5.0
    assert asr._start_timeout_sec == 10.0


def test_empty_audio_emits_callback():
    emitted = []

    def _cb(result):
        emitted.append(result)

    asr = ASRClient(engine=ASREngine.VOSK, result_callback=_cb)
    asr._audio_data.clear()
    asr._finalize_recording()
    assert len(emitted) == 1
    assert emitted[0].error or not emitted[0].transcript


def test_finalize_from_record_thread_no_deadlock():
    """Worker thread must not join itself (regression)."""
    import threading

    asr = ASRClient(engine=ASREngine.MOCK)
    asr.start_recording()
    done = threading.Event()

    def _worker_finalize():
        asr._recording = False
        asr._finalize_recording()
        done.set()

    t = asr._recording_thread
    assert t is not None
    t2 = threading.Thread(target=_worker_finalize)
    t2.start()
    t.join(timeout=2.0)
    assert done.wait(timeout=2.0)


def test_empty_audio_manual_stop_message():
    asr = ASRClient(engine=ASREngine.VOSK)
    asr._stop_reason = "manual"
    asr._audio_data.clear()
    result = asr._transcribe()
    assert result.error
    assert "请说话后再点击结束" in result.error


def test_empty_audio_wait_timeout_message():
    asr = ASRClient(engine=ASREngine.VOSK, start_timeout_sec=10.0)
    asr._stop_reason = "wait_timeout"
    asr._audio_data.clear()
    result = asr._transcribe()
    assert result.error
    assert "开说等待超时" in result.error
    assert "10" in result.error


def test_record_join_timeout_covers_listen():
    asr = ASRClient(engine=ASREngine.VOSK, start_timeout_sec=10.0, silence_sec=5.0)
    assert asr._record_join_timeout_sec() >= 16.0


def test_validate_microphone_index_invalid():
    assert ASRClient._validate_microphone_index(-1) is False


def test_google_network_error_falls_back_to_vosk():
    asr = ASRClient(engine=ASREngine.GOOGLE)
    asr._vosk_available = True
    asr._audio_data = ["fake-audio"]

    good = ASRResult(transcript="你好", confidence=0.8, engine=ASREngine.VOSK)

    with patch.object(
        ASRClient, "_recognize_google", side_effect=OSError(10054, "reset")
    ), patch.object(ASRClient, "_transcribe_vosk", return_value=good):
        result = asr._transcribe()
    assert result.success
    assert result.transcript == "你好"
    assert result.engine == ASREngine.VOSK
