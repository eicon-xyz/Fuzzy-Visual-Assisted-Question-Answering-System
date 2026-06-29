"""
HAJIMI Client — 语音合成 (TTS) 模块
======================================
离线优先：pyttsx3 (Windows SAPI5 / macOS NSSpeech / Linux eSpeak)
线程安全 FIFO 播报队列，支持优先级打断
在线降级：预留 Azure/百度 TTS API 接口

用法::

    from client.voice.tts_engine import TTSEngine

    tts = TTSEngine(status_callback=lambda status: print(f"TTS: {status}"))
    tts.enqueue("请点击桌面上的浏览器图标")
    tts.enqueue("警告：操作已超时", priority=1, interrupt_current=True)
"""

import threading
import queue
import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from enum import Enum


class TTSStatus(str, Enum):
    PLAYING = "playing"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    QUEUE_EMPTY = "queue_empty"


class TTSPriority(int):
    NORMAL = 0
    WARNING = 1
    EMERGENCY = 2


@dataclass(order=True)
class TTSItem:
    """TTS 播报队列项（按优先级排序，同优先级 FIFO）"""
    priority: int
    text: str = field(compare=False)
    interrupt_current: bool = field(default=False, compare=False)
    enqueue_time: float = field(default_factory=time.monotonic, compare=True)


# 回调类型
TTSCallback = Callable[[TTSStatus, str, int], None]
# 参数: (status, current_text, queue_depth)


class TTSEngine:
    """TTS 语音合成引擎

    - 默认 pyttsx3 离线引擎
    - 线程安全 FIFO 队列，支持优先级
    - 可通过 ``status_callback`` 监听播报状态
    """

    # 单条播报最长 120 秒超时
    MAX_PLAY_SECONDS = 120
    # 队列最大长度（防止内存泄漏）
    MAX_QUEUE_SIZE = 100

    def __init__(
        self,
        status_callback: Optional[TTSCallback] = None,
        engine: str = "pyttsx3",
        rate: int = 160,          # 语速，pyttsx3 默认 ~200 words/min
        volume: float = 1.0,
        voice_id: Optional[str] = None,        # 指定语音 ID，None = 自动选中文
        device_index: Optional[int] = None,    # 指定输出设备索引，None = 系统默认
    ):
        """初始化 TTS 引擎

        Args:
            status_callback: 播报状态回调
            engine: TTS 引擎名称
            rate: 语速 (50~300 words/min)
            volume: 音量 (0.0~1.0)
            voice_id: 指定语音包 ID，None 则自动匹配中文语音
            device_index: 指定音频输出设备索引，None 则使用系统默认
        """
        self._callback = status_callback
        self._engine_name = engine
        self._rate = rate
        self._volume = volume
        self._voice_id = voice_id
        self._device_index = device_index

        # 队列与同步
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._lock = threading.Lock()
        self._playing = False
        self._paused = False
        self._current_text: str = ""
        self._stop_requested = False

        # 引擎初始化
        self._tts_engine = None
        self._available = self._init_engine()

        # 后台播放线程
        self._player_thread: Optional[threading.Thread] = None
        self._start_player()

    # ────────────────────────── 公开 API ──────────────────────────

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def current_text(self) -> str:
        return self._current_text

    @property
    def engine_info(self) -> dict:
        return {
            "engine": self._engine_name,
            "available": self._available,
            "rate": self._rate,
            "volume": self._volume,
        }

    def enqueue(
        self,
        text: str,
        priority: int = TTSPriority.NORMAL,
        interrupt_current: bool = False,
    ) -> bool:
        """将文本加入播报队列

        Args:
            text: 待播报文本
            priority: 0=普通 / 1=预警 / 2=紧急
            interrupt_current: 是否打断当前播报

        Returns:
            True 如果成功入队；False 如果队列已满
        """
        if not text or not isinstance(text, str):
            return False

        text = text.strip()
        if not text:
            return False

        if self._queue.qsize() >= self.MAX_QUEUE_SIZE:
            return False

        item = TTSItem(
            priority=priority,
            text=text,
            interrupt_current=interrupt_current,
        )
        self._queue.put(item)

        # 紧急打断
        if interrupt_current and self._playing:
            self._stop_current()

        return True

    def pause(self) -> None:
        """暂停当前播报"""
        self._paused = True

    def resume(self) -> None:
        """恢复播报"""
        self._paused = False

    def skip(self) -> None:
        """跳过当前播报，播放队列中下一条"""
        self._stop_current()

    def clear_queue(self) -> None:
        """清空播报队列（不打断当前播报）"""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def stop_all(self) -> None:
        """停止所有播报并清空队列"""
        self.clear_queue()
        self._stop_current()

    def set_rate(self, rate: int) -> None:
        """动态调整语速（50~300）"""
        self._rate = max(50, min(300, rate))
        if self._tts_engine:
            try:
                self._tts_engine.setProperty("rate", self._rate)
            except Exception:
                pass

    def set_volume(self, volume: float) -> None:
        """动态调整音量（0.0~1.0）"""
        self._volume = max(0.0, min(1.0, volume))
        if self._tts_engine:
            try:
                self._tts_engine.setProperty("volume", self._volume)
            except Exception:
                pass

    def shutdown(self) -> None:
        """关闭引擎，释放资源"""
        self._stop_requested = True
        self.stop_all()
        if self._player_thread and self._player_thread.is_alive():
            self._player_thread.join(timeout=3.0)

    # ────────────────────────── 内部实现 ──────────────────────────

    def _init_engine(self) -> bool:
        """初始化 TTS 引擎"""
        try:
            import pyttsx3
            self._tts_engine = pyttsx3.init()
            self._tts_engine.setProperty("rate", self._rate)
            self._tts_engine.setProperty("volume", self._volume)

            # 设置语音
            voices = self._tts_engine.getProperty("voices")
            if self._voice_id:
                # 用户显式指定
                for voice in voices:
                    if voice.id == self._voice_id:
                        self._tts_engine.setProperty("voice", voice.id)
                        break
            else:
                # 自动匹配中文语音
                for voice in voices:
                    if "chinese" in voice.name.lower() or "zh" in voice.id.lower() \
                       or "simplified" in voice.name.lower():
                        self._tts_engine.setProperty("voice", voice.id)
                        self._voice_id = voice.id
                        break

            return True
        except ImportError:
            return False
        except Exception:
            return False

    @staticmethod
    def list_voices() -> list[dict]:
        """列出所有可用的 TTS 语音包

        Returns:
            [{"id": "HKEY_...", "name": "Microsoft Zira", "languages": ["en-US"], "gender": "female"}, ...]
        """
        voices = []
        try:
            import pyttsx3
            engine = pyttsx3.init()
            for voice in engine.getProperty("voices"):
                voices.append({
                    "id": voice.id,
                    "name": voice.name,
                    "languages": getattr(voice, "languages", []),
                    "gender": getattr(voice, "gender", "unknown"),
                    "age": getattr(voice, "age", "unknown"),
                })
            engine.stop()
        except ImportError:
            pass
        except Exception:
            pass
        return voices

    def set_voice(self, voice_id: str) -> bool:
        """动态切换语音包"""
        if not self._tts_engine:
            return False
        try:
            voices = self._tts_engine.getProperty("voices")
            for voice in voices:
                if voice.id == voice_id:
                    self._tts_engine.setProperty("voice", voice.id)
                    self._voice_id = voice_id
                    return True
            return False
        except Exception:
            return False

    def _start_player(self) -> None:
        """启动后台播放线程"""
        self._player_thread = threading.Thread(
            target=self._player_loop, daemon=True, name="tts-player"
        )
        self._player_thread.start()

    def _player_loop(self) -> None:
        """后台播放主循环"""
        while not self._stop_requested:
            try:
                # 阻塞等待队列中有新项，超时 0.5s 以便检查 stop 标志
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                if not self._playing and self._queue.empty():
                    self._playing = False
                    self._emit(TTSStatus.QUEUE_EMPTY, "", 0)
                continue

            # 等待暂停恢复
            while self._paused and not self._stop_requested:
                time.sleep(0.1)

            if self._stop_requested:
                break

            self._play_item(item)

    def _play_item(self, item: TTSItem) -> None:
        """播放单个 TTS 条目"""
        self._playing = True
        self._current_text = item.text
        self._emit(TTSStatus.PLAYING, item.text, self._queue.qsize())

        if self._available and self._tts_engine:
            try:
                self._tts_engine.say(item.text)

                # 分段运行事件循环以避免长时间阻塞
                start = time.monotonic()
                while self._tts_engine.isBusy():
                    if self._stop_requested:
                        self._tts_engine.stop()
                        break
                    if time.monotonic() - start > self.MAX_PLAY_SECONDS:
                        self._tts_engine.stop()
                        self._emit(TTSStatus.ERROR, item.text, self._queue.qsize())
                        break
                    time.sleep(0.05)
            except Exception as e:
                self._emit(TTSStatus.ERROR, item.text, self._queue.qsize())
        else:
            # Mock 模式：模拟播放延迟
            mock_duration = min(len(item.text) * 0.08, 5.0)
            time.sleep(mock_duration)

        if not self._stop_requested:
            self._emit(TTSStatus.COMPLETED, item.text, self._queue.qsize())

        self._playing = False
        self._current_text = ""

    def _stop_current(self) -> None:
        """停止当前播放（由队列线程处理）"""
        if self._available and self._tts_engine:
            try:
                self._tts_engine.stop()
            except Exception:
                pass
        # 通过标志位让播放循环感知到打断
        # tts_engine.stop() 会使 isBusy() 返回 False，循环自然退出

    def _emit(self, status: TTSStatus, text: str, depth: int) -> None:
        """安全地调用状态回调"""
        if self._callback:
            try:
                self._callback(status, text, depth)
            except Exception:
                pass
