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

    def __init__(
        self,
        result_callback: Optional[ASRCallback] = None,
        engine: str = ASREngine.VOSK,
        language: str = "zh-CN",
        vosk_model_path: str = "models/vosk-model-small-cn-0.22",
        microphone_index: Optional[int] = None,
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

        # 运行时状态
        self._recording = False
        self._recording_thread: Optional[threading.Thread] = None
        self._audio_data: list = []           # 缓存音频帧（Mock 模式）
        self._start_time: float = 0.0

        # 引擎就绪检测
        self._vosk_available = self._check_vosk()
        self._google_available = self._check_google()

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
        self._recording = True
        self._audio_data.clear()
        self._start_time = time.time()
        self._recording_thread = threading.Thread(
            target=self._record_loop, daemon=True, name="asr-record"
        )
        self._recording_thread.start()

    def stop_and_transcribe(self) -> ASRResult:
        """停止录音并执行语音转文字"""
        self._recording = False
        if self._recording_thread and self._recording_thread.is_alive():
            self._recording_thread.join(timeout=3.0)
        return self._transcribe()

    def cancel(self) -> None:
        """取消当前录音（不转写）"""
        self._recording = False
        self._audio_data.clear()

    @property
    def engine_status(self) -> dict:
        """返回各引擎可用状态"""
        return {
            "vosk_available": self._vosk_available,
            "google_available": self._google_available,
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

    def _record_loop(self) -> None:
        """录音循环（在独立线程中运行）"""
        try:
            if self._active_engine == ASREngine.MOCK:
                self._mock_record()
            elif self._active_engine in (ASREngine.VOSK, ASREngine.GOOGLE):
                self._speech_recognition_record()
        except Exception as e:
            if self._callback:
                self._callback(ASRResult(
                    transcript="",
                    confidence=0.0,
                    engine=self._active_engine,
                    error=str(e),
                ))

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

            # 选择麦克风设备
            mic_kwargs = {}
            if self._microphone_index is not None:
                mic_kwargs["device_index"] = self._microphone_index

            with sr.Microphone(**mic_kwargs) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                try:
                    audio = recognizer.listen(
                        source,
                        timeout=self.MAX_RECORD_SECONDS,
                        phrase_time_limit=self.MAX_RECORD_SECONDS,
                    )
                    self._audio_data.append(audio)
                except sr.WaitTimeoutError:
                    pass
        except Exception as e:
            if self._callback:
                self._callback(ASRResult(
                    transcript="",
                    confidence=0.0,
                    engine=self._active_engine,
                    error=f"录音失败: {e}",
                ))

    def _transcribe(self) -> ASRResult:
        """执行转写

        引擎选择链: Vosk 离线(直接调用 vosk 库) → Google 在线 → 错误返回
        """
        if self._active_engine == ASREngine.MOCK:
            return self._mock_transcribe()

        if not self._audio_data:
            return ASRResult(
                transcript="",
                confidence=0.0,
                engine=self._active_engine,
                error="未捕获到音频数据",
            )

        audio = self._audio_data[0]

        # ── Vosk 离线识别（直接调用 vosk 库，不经过 speech_recognition 封装）──
        if self._active_engine == ASREngine.VOSK and self._vosk_available:
            vosk_result = self._transcribe_vosk(audio)
            if vosk_result is not None:
                self._emit_result(vosk_result)
                return vosk_result

        # ── Google 在线降级 ──
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            text = recognizer.recognize_google(audio, language=self._language)
            result = ASRResult(
                transcript=text,
                confidence=0.85,
                engine=ASREngine.GOOGLE,
            )
            self._emit_result(result)
            return result
        except ImportError:
            pass
        except Exception as e:
            err_name = type(e).__name__
            if "UnknownValue" in err_name:
                return ASRResult(
                    transcript="",
                    confidence=0.0,
                    engine=ASREngine.GOOGLE,
                    error="Google 无法识别语音内容",
                )
            return ASRResult(
                transcript="",
                confidence=0.0,
                engine=ASREngine.GOOGLE,
                error=f"Google 语音服务不可用: {e}",
            )

        # 全部失败
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
        result = ASRResult(
            transcript=transcript,
            confidence=0.92,
            engine=ASREngine.MOCK,
        )
        self._emit_result(result)
        return result

    def _emit_result(self, result: ASRResult) -> None:
        """安全地调用回调"""
        if self._callback:
            try:
                self._callback(result)
            except Exception:
                pass  # 静默吞掉回调异常，不打断主流程
