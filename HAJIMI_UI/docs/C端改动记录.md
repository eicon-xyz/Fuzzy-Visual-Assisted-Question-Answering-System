# C 端改动记录（B-C 语音集成）

> 仅记录 B 端集成过程中对 `client/` 的必要改动，便于 C 同学 review 与合并。

| 日期 | 文件 | 改动摘要 | 原因 | 负责人 |
|------|------|----------|------|--------|
| 2026-07-08 | `client/voice/asr_client.py` | 增加 `silence_sec` / `start_timeout_sec`（env：`HAJIMI_ASR_SILENCE_SEC=5`、`HAJIMI_ASR_START_TIMEOUT_SEC=10`）；`listen()` 结束后自动 `_finalize_recording()`；`stop_and_transcribe()` 幂等 | B 端改为「点击开始、静音 5s 自动结束、再次点击结束」，不能依赖按住松手 | B 端集成 |
| 2026-07-08 | `client/integration/controller.py` | `_on_asr_stop` 仅调用 `stop_and_transcribe()`，结果统一经 `result_callback` → `asr_result` | 避免自动结束与手动 stop 双路径重复 emit | B 端集成 |
| 2026-07-08 | `client/integration/controller.py` | **`_has_pyqt_signals` 改为检查 `asr_start.connect`**（原误检 `b_signals.connect` 导致 bind_to 跳过全部 Qt 信号绑定，mic 永久灰色） | 根因修复：health/asr 信号从未连接 | B 端集成 |
| 2026-07-08 | `client/voice/asr_client.py` + `requirements.txt` | 增加 `pyaudio` 检测；`mic_available` / health 需 PyAudio；`requirements.txt` 纳入 `pyaudio>=0.2.14` | SpeechRecognition 录音必需 PyAudio | B 端集成 |
| 2026-07-08 | `client/voice/asr_client.py` | `_finalize_recording` 统一 emit；错误/空音频必回调；**修复工作线程 self-join 死锁** | ASR 无反应、永驻「正在聆听」 | B 端集成 |
| 2026-07-08 | `client/integration/controller.py` | `_on_asr_result` 经 `QTimer.singleShot` 主线程 emit；新增 `asr_is_recording()` | PyQt 跨线程 signal 丢失 | B 端集成 |
| 2026-07-08 | `client/integration/controller.py` | `voice_settings` 构造注入；`_create_asr_client` / `_rebuild_asr_client`；`_handle_asr_start` 信号包装；`apply_voice_settings` 热切换 ASR 引擎/麦克风/模型/超时 | B 端设置 google/麦克风/模型生效 | B 端集成 |
| 2026-07-08 | `HAJIMI_UI/core/defaults.py` + `settings_widgets.py` | 语音设置扩展：麦克风、Vosk 模型、语言、录音超时；ASR 引擎仅 vosk/google | 演示可配置、识别质量可控 | B 端集成 |
| 2026-07-08 | `client/voice/asr_client.py` | `_stop_reason` 分级空音频错误；延长 join；麦克风校验 | 「未捕获到音频数据」误报 | B 端集成 |
| 2026-07-08 | `client/voice/asr_client.py` | Google HTTPS endpoint；网络失败降级 Vosk | WinError 10054 国内网络 | B 端集成 |
| 2026-07-09 | `HAJIMI_UI/main.py` + `core/repo_paths.py` + `client/paths.py` | 启动时 `ensure_repo_root_on_path`；审计库迁至 `%LOCALAPPDATA%/HAJIMI/audit_queue.db` | 修复 `HAJIMI_UI/client/` shadow 导致 `No module named client.integration` | B 端集成 |
| 2026-07-08 | B `main_widget` + `user_settings` + `scripts/emit_proxy_env.py` | C 懒加载；模型设置代理（默认关，仅 B 进程） | 启动加速 + Google 代理 | B 端集成 |

## 未改动的 C 模块

- `client/voice/tts_engine.py`
- A-end / Sidecar

## 回滚说明

若 C 同学提供官方 ASR 流式/VAD 实现，可替换 `asr_client.py` 中 `_speech_recognition_record` + `_finalize_recording`，**B 端信号契约不变**（`asr_start` / `asr_stop` / `asr_result`）。
