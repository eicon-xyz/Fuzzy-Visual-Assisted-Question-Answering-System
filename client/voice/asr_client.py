"""
HAJIMI Client — 语音识别 (ASR) 模块
======================================
离线优先：Vosk 中文小模型
在线降级：Google Web Speech API
兜底方案：Mock 模拟模式（无麦克风时自测用）

用法::

    from client.voice.asr_client import ASRClient

    asr = ASRClient(result_callback=lambda text, conf, eng: print(f"识别: {text}"))
    asr.start_recording()
    # ... 用户说话 ...
    transcript = asr.stop_and_transcribe()
"""

import os
import threading
import queue
import time
from dataclasses import dataclass
from typing import Callable, Optional
from enum import Enum


class ASREngine(str, Enum):
    VOSK = "vosk"
    GOOGLE = "google"
    MOCK = "mock"


@dataclass
class ASRResult:
    """语音识别结果"""
    transcript: str
    confidence: float = 0.0
    engine: str = ASREngine.MOCK
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and len(self.transcript) > 0


# 回调类型
ASRCallback = Callable[[ASRResult], None]


class ASRClient:
    """ASR 语音识别客户端

    - 默认离线 Vosk 优先，在线 Google 降级
    - 录音最长 60 秒自动停止
    - 可通过 ``result_callback`` 设置结果回调
    """

    MAX_RECORD_SECONDS = 60
    DEFAULT_SILENCE_SEC = 5.0
    DEFAULT_START_TIMEOUT_SEC = 10.0

    def __init__(
        self,
        result_callback: Optional[ASRCallback] = None,
        engine: str = ASREngine.VOSK,
        language: str = "zh-CN",
        vosk_model_path: str = "models/vosk-model-small-cn-0.22",
        microphone_index: Optional[int] = None,
        silence_sec: Optional[float] = None,
        start_timeout_sec: Optional[float] = None,
    ):
        """初始化 ASR 客户端

        Args:
            result_callback: 识别结果回调
            engine: 首选引擎 (vosk/google/mock)
            language: 识别语言
            vosk_model_path: Vosk 模型目录路径（相对于项目根目录或绝对路径）
            microphone_index: 指定麦克风设备索引，None 则使用系统默认
        """
        self._callback = result_callback
        self._engine = engine
        self._language = language
        self._vosk_model_path = vosk_model_path
        self._microphone_index = microphone_index  # None = 系统默认
        self._silence_sec = float(
            silence_sec
            if silence_sec is not None
            else os.environ.get("HAJIMI_ASR_SILENCE_SEC", self.DEFAULT_SILENCE_SEC)
        )
        self._start_timeout_sec = float(
            start_timeout_sec
            if start_timeout_sec is not None
            else os.environ.get(
                "HAJIMI_ASR_START_TIMEOUT_SEC", self.DEFAULT_START_TIMEOUT_SEC
            )
        )

        # 运行时状态
        self._recording = False
        self._recording_thread: Optional[threading.Thread] = None
        self._audio_data: list = []           # 缓存音频帧（Mock 模式）
        self._start_time: float = 0.0
        self._finalized = False
        self._last_result: Optional[ASRResult] = None
        self._finalize_lock = threading.Lock()
        self._stop_reason: Optional[str] = None  # manual / wait_timeout / none

        # 引擎就绪检测
        self._vosk_available = self._check_vosk()
        self._google_available = self._check_google()
        self._pyaudio_available = self._check_pyaudio()

        # 实际使用的引擎
        self._active_engine = self._resolve_engine()

    # ────────────────────────── 公开 API ──────────────────────────

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def active_engine(self) -> str:
        return self._active_engine

    def start_recording(self) -> None:
        """开始录音（非阻塞，在独立线程中运行）"""
        if self._recording:
            return
        if (
            self._active_engine != ASREngine.MOCK
            and not self._pyaudio_available
        ):
            result = ASRResult(
                transcript="",
                confidence=0.0,
                engine=self._active_engine,
                error="未安装 PyAudio，无法录音。请运行: pip install pyaudio",
            )
            self._emit_result(result)
            return
        if self._microphone_index is not None and not self._validate_microphone_index(
            self._microphone_index
        ):
            result = ASRResult(
                transcript="",
                confidence=0.0,
                engine=self._active_engine,
                error="所选麦克风不可用，请在设置中换设备或选「系统默认」",
            )
            self._emit_result(result)
            return
        self._recording = True
        self._finalized = False
        self._last_result = None
        self._stop_reason = None
        self._audio_data.clear()
        self._start_time = time.time()
        self._recording_thread = threading.Thread(
            target=self._record_loop, daemon=True, name="asr-record"
        )
        self._recording_thread.start()

    def stop_and_transcribe(self) -> ASRResult:
        """停止录音并执行语音转文字（幂等，可重复调用）"""
        self._recording = False
        if self._stop_reason is None:
            self._stop_reason = "manual"
        return self._finalize_recording()

    def _record_join_timeout_sec(self) -> float:
        """等待录音线程结束的最长秒数（ambient + 开说等待 + 静音结束 + 缓冲）"""
        return self._start_timeout_sec + self._silence_sec + 1.5

    def _empty_audio_error(self) -> str:
        if self._stop_reason == "wait_timeout":
            sec = int(self._start_timeout_sec)
            return (
                f"开说等待超时（{sec} 秒），请点击麦克风后尽快说话"
            )
        if self._stop_reason == "manual":
            return (
                "未检测到语音：请说话后再点击结束，"
                "或说完后保持静音 {:.0f} 秒自动结束".format(self._silence_sec)
            )
        return "未捕获到音频，请检查麦克风设备与系统权限"

    def _finalize_recording(self) -> ASRResult:
        """结束录音并转写；listen 自然结束或 asr_stop 时共用。"""
        with self._finalize_lock:
            if self._finalized:
                return self._last_result or ASRResult(
                    transcript="",
                    confidence=0.0,
                    engine=self._active_engine,
                    error=self._empty_audio_error(),
                )
            self._finalized = True
            self._recording = False
            thread = self._recording_thread
            is_worker = threading.current_thread() is thread

        if thread and thread.is_alive() and not is_worker:
            thread.join(timeout=self._record_join_timeout_sec())

        with self._finalize_lock:
            if self._last_result is None:
                self._last_result = self._transcribe()
            result = self._last_result

        self._emit_result(result)
        return result

    def cancel(self) -> None:
        """取消当前录音（不转写）"""
        self._recording = False
        self._audio_data.clear()

    @property
    def engine_status(self) -> dict:
        """返回各引擎可用状态"""
        mic_ok = self._active_engine == ASREngine.MOCK or self._pyaudio_available
        return {
            "vosk_available": self._vosk_available,
            "google_available": self._google_available,
            "pyaudio_available": self._pyaudio_available,
            "mic_available": mic_ok,
            "active_engine": self._active_engine,
            "vosk_model_path": self._vosk_model_path,
        }

    @staticmethod
    def list_microphones() -> list[dict]:
        """列出所有可用的麦克风设备

        Returns:
            [{"index": 0, "name": "Microphone (Realtek Audio)"}, ...]

        需要 PyAudio 支持。如果没有 PyAudio，返回空列表。
        """
        devices = []
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    devices.append({
                        "index": i,
                        "name": info.get("name", f"Device {i}"),
                        "channels": info.get("maxInputChannels", 0),
                        "default_sample_rate": int(info.get("defaultSampleRate", 16000)),
                    })
            p.terminate()
        except ImportError:
            pass
        return devices

    # ────────────────────────── 内部实现 ──────────────────────────

    def _resolve_engine(self) -> str:
        """按优先级解析实际使用的引擎

        优先尊重用户显式指定的引擎；若指定引擎不可用则自动降级。
        """
        # 用户显式指定 MOCK → 直接使用
        if self._engine == ASREngine.MOCK:
            return ASREngine.MOCK

        # 用户指定 VOSK → 检查可用性
        if self._engine == ASREngine.VOSK:
            if self._vosk_available:
                return ASREngine.VOSK
            if self._google_available:
                return ASREngine.GOOGLE
            return ASREngine.MOCK

        # 用户指定 GOOGLE → 检查可用性
        if self._engine == ASREngine.GOOGLE:
            if self._google_available:
                return ASREngine.GOOGLE
            if self._vosk_available:
                return ASREngine.VOSK
            return ASREngine.MOCK

        return ASREngine.MOCK

    def _check_vosk(self) -> bool:
        """检测 Vosk 模型是否可用"""
        try:
            import vosk
            import os
            # 检查模型目录是否存在（含 AM 子目录）
            model_path = self._vosk_model_path
            if not os.path.isabs(model_path):
                # 相对路径：相对于项目根目录
                model_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    model_path,
                )
                self._vosk_model_path = model_path  # 更新为绝对路径
            if os.path.isdir(model_path) and os.path.isdir(os.path.join(model_path, "am")):
                return True
            # vosk 库可导入但模型未下载
            return False
        except ImportError:
            return False
        except Exception:
            return False

    def _check_google(self) -> bool:
        """检测 Google Web Speech 是否可用"""
        try:
            import speech_recognition as sr
            return True
        except ImportError:
            return False

    @staticmethod
    def _check_pyaudio() -> bool:
        """检测 PyAudio 是否可用（SpeechRecognition 录音必需）"""
        try:
            import pyaudio  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _validate_microphone_index(index: int) -> bool:
        """检查指定麦克风索引是否存在且可输入"""
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            try:
                if index < 0 or index >= p.get_device_count():
                    return False
                info = p.get_device_info_by_index(index)
                return info.get("maxInputChannels", 0) > 0
            finally:
                p.terminate()
        except Exception:
            return False

    def _record_loop(self) -> None:
        """录音循环（在独立线程中运行）"""
        try:
            if self._active_engine == ASREngine.MOCK:
                self._mock_record()
                self._finalize_recording()
            elif self._active_engine in (ASREngine.VOSK, ASREngine.GOOGLE):
                self._speech_recognition_record()
        except Exception as e:
            self._last_result = ASRResult(
                transcript="",
                confidence=0.0,
                engine=self._active_engine,
                error=str(e),
            )
            self._finalize_recording()

    def _mock_record(self) -> None:
        """Mock 录音模式（用于无麦克风环境自测）"""
        # 模拟录音：等待 stop 信号
        while self._recording:
            elapsed = time.time() - self._start_time
            if elapsed > self.MAX_RECORD_SECONDS:
                break
            time.sleep(0.1)

    def _speech_recognition_record(self) -> None:
        """使用 speech_recognition 库录音"""
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            recognizer.pause_threshold = self._silence_sec

            # 选择麦克风设备
            mic_kwargs = {}
            if self._microphone_index is not None:
                mic_kwargs["device_index"] = self._microphone_index

            with sr.Microphone(**mic_kwargs) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                try:
                    audio = recognizer.listen(
                        source,
                        timeout=self._start_timeout_sec,
                        phrase_time_limit=self.MAX_RECORD_SECONDS,
                    )
                    self._audio_data.append(audio)
                except sr.WaitTimeoutError:
                    if self._stop_reason is None:
                        self._stop_reason = "wait_timeout"
        except Exception as e:
            self._last_result = ASRResult(
                transcript="",
                confidence=0.0,
                engine=self._active_engine,
                error=f"录音失败: {e}",
            )
            self._finalize_recording()
            return
        self._finalize_recording()

    @staticmethod
    def _is_network_error(exc: BaseException) -> bool:
        name = type(exc).__name__
        text = str(exc).lower()
        if name in ("ConnectionError", "TimeoutError", "URLError", "RequestError"):
            return True
        markers = (
            "10054",
            "10060",
            "10061",
            "forcibly",
            "connection reset",
            "connection refused",
            "timed out",
            "network is unreachable",
            "getaddrinfo",
            "ssl",
            "proxy",
        )
        return any(m in text for m in markers)

    def _recognize_google(self, audio) -> str:
        """调用 Google Web Speech（HTTPS，便于代理穿透）。"""
        import speech_recognition as sr

        recognizer = sr.Recognizer()
        kwargs = {"language": self._language}
        try:
            return recognizer.recognize_google(
                audio,
                endpoint="https://www.google.com/speech-api/v2/recognize",
                **kwargs,
            )
        except TypeError:
            # 旧版 SpeechRecognition 无 endpoint 参数
            return recognizer.recognize_google(audio, **kwargs)

    def _fallback_vosk(self, audio) -> Optional[ASRResult]:
        if not self._vosk_available:
            return None
        return self._transcribe_vosk(audio)

    def _transcribe(self) -> ASRResult:
        """执行转写

        优先用户选定引擎；Google 网络失败或无法识别时降级 Vosk。
        """
        if self._active_engine == ASREngine.MOCK:
            return self._mock_transcribe()

        if not self._audio_data:
            return ASRResult(
                transcript="",
                confidence=0.0,
                engine=self._active_engine,
                error=self._empty_audio_error(),
            )

        audio = self._audio_data[0]

        # 首选 Vosk
        if self._active_engine == ASREngine.VOSK and self._vosk_available:
            vosk_result = self._transcribe_vosk(audio)
            if vosk_result is not None:
                return vosk_result

        # Google（用户首选或 Vosk 不可用时的备用）
        google_err: Optional[str] = None
        try:
            text = self._recognize_google(audio)
            return ASRResult(
                transcript=text,
                confidence=0.85,
                engine=ASREngine.GOOGLE,
            )
        except ImportError:
            pass
        except Exception as e:
            err_name = type(e).__name__
            if "UnknownValue" in err_name:
                google_err = "Google 无法识别语音内容"
            elif self._is_network_error(e):
                google_err = (
                    "Google 网络不可用（需在模型设置启用代理或使用 VPN）。"
                    f" 详情: {e}"
                )
            else:
                google_err = f"Google 语音服务不可用: {e}"

        # Google 失败 → 降级 Vosk（同段音频）
        if google_err and self._vosk_available:
            vosk_fb = self._fallback_vosk(audio)
            if vosk_fb is not None and vosk_fb.success:
                return vosk_fb
            if vosk_fb is not None and vosk_fb.error:
                google_err = f"{google_err} 已尝试 Vosk：{vosk_fb.error}"
            else:
                google_err = f"{google_err} 已尝试 Vosk 离线仍失败。"

        if google_err:
            if not self._vosk_available:
                google_err += " 且未安装 Vosk 模型；可在设置改用 vosk。"
            return ASRResult(
                transcript="",
                confidence=0.0,
                engine=ASREngine.GOOGLE,
                error=google_err,
            )

        return ASRResult(
            transcript="",
            confidence=0.0,
            engine=self._active_engine,
            error="所有引擎均转写失败",
        )

    def _transcribe_vosk(self, audio) -> Optional[ASRResult]:
        """使用 Vosk 库直接转写

        不依赖 speech_recognition 的 recognize_vosk 封装，
        直接通过 vosk.Model + KaldiRecognizer 完成转写。
        模型路径在初始化时通过 ``vosk_model_path`` 指定。
        """
        try:
            import vosk
            import json
            import os as _os

            model_path = self._vosk_model_path
            if not _os.path.isdir(model_path):
                return None

            # speech_recognition AudioData → 16kHz 16-bit PCM
            sample_rate = getattr(audio, "sample_rate", 16000)
            raw_data = audio.get_raw_data(
                convert_rate=16000,
                convert_width=2,
            )

            model = vosk.Model(model_path)
            rec = vosk.KaldiRecognizer(model, 16000.0)
            rec.AcceptWaveform(raw_data)

            result_json = rec.FinalResult()
            result_dict = json.loads(result_json)

            transcript = result_dict.get("text", "").strip()
            if not transcript:
                return ASRResult(
                    transcript="",
                    confidence=0.0,
                    engine=ASREngine.VOSK,
                    error="Vosk 未能识别语音内容",
                )

            return ASRResult(
                transcript=transcript,
                confidence=0.80,
                engine=ASREngine.VOSK,
            )
        except ImportError:
            return None
        except Exception:
            return None

    def _mock_transcribe(self) -> ASRResult:
        """Mock 转写：返回模拟结果"""
        mock_texts = [
            "怎么安装微信",
            "帮我打开浏览器",
            "如何截屏保存",
            "这个按钮是什么意思",
        ]
        import random
        transcript = random.choice(mock_texts)
        return ASRResult(
            transcript=transcript,
            confidence=0.92,
            engine=ASREngine.MOCK,
        )

    def _emit_result(self, result: ASRResult) -> None:
        """安全地调用回调"""
        if self._callback:
            try:
                self._callback(result)
            except Exception:
                pass  # 静默吞掉回调异常，不打断主流程
