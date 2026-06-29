# HAJIMI B–C 接口契约

> **版本**：1.0.0  
> **用途**：B（前端/桌面应用）与 C（集成/语音/管理端）之间的接口对齐  
> **通信方式**：进程内 PyQt5 信号/插槽 + C 管理的 HTTP 端点  
> **覆盖范围**：语音交互（ASR/TTS）、审计上报、配置拉取、健康检测

---

## 一、架构概述

B 与 C 运行在同一个 Python 进程中（PyQt5 桌面应用），通过 **Qt 信号/插槽机制** 通信。C 同时负责对服务端的 HTTP 通信（审计上报、配置拉取）。

```
┌─────────────────────────────────────────────────────┐
│                  PyQt5 桌面应用进程                    │
│                                                     │
│  ┌──────────────┐    信号/插槽     ┌──────────────┐ │
│  │  B (前端)    │ ◄────────────► │  C (集成)    │ │
│  │              │                 │              │ │
│  │ • 桌面挂件   │  mic_button     │ • ASR 引擎   │ │
│  │ • 屏幕覆盖层 │  tts_trigger    │ • TTS 引擎   │ │
│  │ • 步骤渲染   │  audit_data    │ • 审计代理   │ │
│  │ • 控制栏     │  config_updated│ • 配置拉取   │ │
│  └──────────────┘                 └──────┬───────┘ │
│                                          │          │
└──────────────────────────────────────────┼──────────┘
                                           │ HTTP
                                           ▼
                                   ┌──────────────┐
                                   │  A (后端/Svr) │
                                   └──────────────┘
```

---

## 二、接口总览

| # | 接口名 | 方向 | 通信方式 | 用途 |
|---|--------|------|----------|------|
| 1 | **ASR 录音控制** | B → C | Qt 信号 | 麦克风按下/松开 → 启停录音 |
| 2 | **ASR 转写结果** | C → B | Qt 信号 | 语音转文字结果回传 |
| 3 | **TTS 播报触发** | B → C | Qt 信号 | 步骤指引文字 → 入队语音播报 |
| 4 | **TTS 状态回传** | C → B | Qt 信号 | 播报开始/完成/错误 |
| 5 | **语音设置同步** | B → C | 共享状态 | 开关/语速/引擎选择 |
| 6 | **审计数据提交** | B → C | Qt 信号 | 事务完成 → 入队异步上报 |
| 7 | **审计上报状态** | C → B | Qt 信号 | 上报成功/失败/队列深度 |
| 8 | **配置拉取通知** | C → B | Qt 信号 | 服务端配置变更 → B 应用 |
| 9 | **心跳/健康检测** | B → C | 方法调用 | B 检测 C 各子模块是否正常 |

---

## 三、信号/插槽详细定义

### 接口 1：ASR 录音控制

**信号名**：`asr_start` / `asr_stop`

**方向**：B → C

**触发时机**：
- `asr_start`：用户按下麦克风按钮
- `asr_stop`：用户松开按钮 或 静默 2 秒自动触发

**Python 绑定示例**：

```python
# B 侧（PyQt5 按钮）
mic_button.pressed.connect(asr_start_signal.emit)
mic_button.released.connect(asr_stop_signal.emit)

# C 侧
asr_start_signal.connect(asr_client.start_recording)
asr_stop_signal.connect(asr_client.stop_and_transcribe)
```

| 信号 | 参数 | 类型 | 说明 |
|------|------|------|------|
| `asr_start` | 无 | — | 启动录音 |
| `asr_stop` | 无 | — | 停止录音并开始转写 |

---

### 接口 2：ASR 转写结果

**信号名**：`asr_result`

**方向**：C → B

**触发时机**：录音停止后，C 完成语音转文字

```python
# C 侧
asr_result_signal.emit(transcript, confidence, engine)
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `transcript` | string | ✅ | 转写文字结果 |
| `confidence` | float | ❌ | 识别置信度 0~1 |
| `engine` | string | ❌ | 使用的引擎：`vosk` / `baidu` / `google` |
| `error` | string \| null | ❌ | 错误信息，成功时为 null |

**B 侧处理**：
1. 收到 `transcript` → 自动填入输入框
2. 若 `confidence` < 0.6 → 输入框文字用浅色显示，提示"识别置信度较低"
3. 若 `error` 不为 null → 弹出 Toast 提示"语音识别失败：{error}"
4. 填入后自动触发发送（`handleUserSubmit`）

```json
{
  "transcript": "怎么安装微信",
  "confidence": 0.92,
  "engine": "vosk",
  "error": null
}
```

---

### 接口 3：TTS 播报触发

**信号名**：`tts_enqueue`

**方向**：B → C

**触发时机**：文字指引生成完毕（每步开始时）、系统主动预警

```python
# B 侧
tts_enqueue_signal.emit(text, priority, interrupt_current)
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `text` | string | ✅ | — | 待播报文本 |
| `priority` | int | ❌ | 0 | 优先级：0=普通步骤 / 1=预警 / 2=紧急 |
| `interrupt_current` | bool | ❌ | false | 是否打断当前正在播放的语音 |

**C 侧处理（TTS 播报队列）**：

```
收到 tts_enqueue
    │
    ▼
优先级 > 当前播放优先级？
    │
    ├─ 是 → 打断当前 + 清除队列 + 立即播放
    └─ 否 → 追加到队列末尾
              │
              ▼
         队列 FIFO 出队
              │
              ▼
         pyttsx3 / Azure TTS 播放
              │
              ▼
         播放完成 → emit tts_status
```

---

### 接口 4：TTS 状态回传

**信号名**：`tts_status`

**方向**：C → B

**触发时机**：播报开始、完成、错误、队列清空

```python
# C 侧
tts_status_signal.emit(status, text, queue_depth)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | string | `playing` / `paused` / `completed` / `error` / `queue_empty` |
| `text` | string | 当前/刚完成的播报文本 |
| `queue_depth` | int | 剩余队列深度 |

**B 侧处理**：
- `playing` → 喇叭图标显示声波动画
- `paused` / `completed` / `queue_empty` → 声波动画停止
- `error` → Toast 提示"语音播报失败"

---

### 接口 5：语音设置同步

**方式**：共享状态变量（非信号）

B 在控制栏/设置面板中维护以下状态，C 实时读取：

```python
# 共享状态（线程安全）
voice_settings = {
    "tts_enabled": True,        # TTS 开关
    "tts_speed": 0.85,          # 语速 0.5~1.5，默认 0.85
    "tts_engine": "pyttsx3",    # 引擎：pyttsx3 / azure / baidu
    "asr_enabled": True,         # ASR 开关
    "asr_engine": "vosk",       # 引擎：vosk / baidu / google
    "asr_language": "zh-CN"     # 识别语言
}
```

| 所属 UI | 控件 | 绑定状态 |
|----------|------|----------|
| 桌面挂件设置面板 | Toggle 开关 | `tts_enabled` / `asr_enabled` |
| 桌面挂件设置面板 | 滑块 | `tts_speed` |
| 桌面挂件设置面板 | 下拉选择 | `tts_engine` / `asr_engine` |
| 桌面挂件控制栏 | 麦克风按钮 | 调用 `asr_start` / `asr_stop` |
| 桌面挂件控制栏 | 喇叭图标 | 显示 `tts_status.playing` 动画 |

---

### 接口 6：审计数据提交

**信号名**：`audit_submit`

**方向**：B → C

**触发时机**：任务完成/失败/取消/红线拦截

```python
# B 侧
audit_submit_signal.emit(audit_record)
```

**数据模型**：`AuditRecord`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | string | ✅ | 任务唯一 ID |
| `query` | string | ✅ | 脱敏后的用户提问 |
| `intent_category` | string | ✅ | 九大意图域之一 |
| `complexity_score` | int | ✅ | 复杂度打分 |
| `route` | string | ✅ | `L2` / `L3` |
| `total_steps` | int | ✅ | 蓝图总步数 |
| `completed_steps` | int | ✅ | 实际完成步数 |
| `result` | string | ✅ | `success` / `fail` / `cancel` / `redirect` / `rejected` |
| `duration_ms` | int | ✅ | 任务总耗时（毫秒） |
| `feedback_type` | string | ❌ | `useful` / `useless` / `neutral` |
| `comment` | string | ❌ | 用户评语 |
| `fingerprint_mismatches` | int | ❌ | 指纹不匹配次数 |
| `redline_triggered` | bool | ❌ | 是否触发红线拦截 |
| `timestamp` | string | ✅ | ISO 8601 时间戳 |

**C 侧处理流程**（审计代理）：

```
收到 audit_submit
    │
    ▼
隐私脱敏
    - 原始截图 → 丢弃
    - 窗口标题 → 类别正则替换
    - 文件路径 → 仅保留扩展名
    - 敏感字段 → [REDACTED]
    │
    ▼
写入本地 SQLite (WAL 模式) → audit_queue 表
    │
    ▼
累积 10 条 或 网络空闲 5 分钟？
    │
    ├─ 是 → 批量 POST /api/audit/report
    │         │
    │         ├─ 成功 → DELETE FROM audit_queue
    │         │         emit audit_status(success, batch_size)
    │         │
    │         └─ 失败 → retry_count++
    │                   指数退避 1min/5min/15min/1h
    │                   超 3 次 → 写 fallback.log
    │                   emit audit_status(failed, batch_size, error)
    │
    └─ 否 → 继续等待
```

**示例**：

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "query": "怎么安装微信",
  "intent_category": "operation_guide",
  "complexity_score": 35,
  "route": "L3",
  "total_steps": 3,
  "completed_steps": 3,
  "result": "success",
  "duration_ms": 45200,
  "feedback_type": "useful",
  "comment": "指引很清晰",
  "fingerprint_mismatches": 0,
  "redline_triggered": false,
  "timestamp": "2026-06-29T14:32:15+08:00"
}
```

---

### 接口 7：审计上报状态

**信号名**：`audit_status`

**方向**：C → B

```python
# C 侧
audit_status_signal.emit(status, batch_size, queue_depth, error)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | string | `success` / `failed` / `queued` |
| `batch_size` | int | 本次上报条数 |
| `queue_depth` | int | 本地队列剩余未上报条数 |
| `error` | string \| null | 错误信息 |

**B 侧处理**：
- `queue_depth` > 50 → 状态栏显示 "⚠ 离线队列积压：{n} 条"
- `status=failed` → 仅写日志，不打断用户（异步旁路，静默失败）

---

### 接口 8：配置拉取通知

**信号名**：`config_updated`

**方向**：C → B

**触发时机**：C 定时轮询 `/api/config/pull` 发现配置变更（ETag/版本号不同）

```python
# C 侧
config_updated_signal.emit(config_dict)
```

**数据模型**：`ClientConfig`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `version` | string | ✅ | 配置版本号，如 `"v2.1.3"` |
| `confidence_threshold` | int | ✅ | 置信度阈值 50~100 |
| `llm_api_endpoint` | string | ✅ | LLM API 端点 URL |
| `llm_model` | string | ✅ | LLM 模型名称 |
| `max_blueprint_steps` | int | ✅ | 最大蓝图步骤数 |
| `token_limit` | int | ✅ | Token 超限阈值 |
| `config_pull_interval_min` | int | ✅ | 配置拉取间隔（分钟），最小 5 |
| `audit_batch_size` | int | ✅ | 审计上报批量大小 |
| `offline_tts_engine` | string | ✅ | 离线 TTS 引擎 |
| `routing_rules` | object | ✅ | L2/L3 路由复杂度评分规则 JSON |
| `updated_at` | string | ✅ | 服务端配置更新时间 ISO 8601 |

**B 侧处理**：
1. 收到 `config_updated` → 更新本地配置缓存
2. 若 `routing_rules` 变更 → 热加载新的路由规则
3. 若 `config_pull_interval_min` 变更 → 通知 C 调整轮询间隔
4. 弹 Toast："配置已更新至 {version}"

**示例**：

```json
{
  "version": "v2.1.3",
  "confidence_threshold": 80,
  "llm_api_endpoint": "https://api.openai.com/v1",
  "llm_model": "gpt-4o",
  "template_similarity_threshold": 90,
  "token_limit": 8000,
  "config_pull_interval_min": 30,
  "audit_batch_size": 10,
  "offline_tts_engine": "pyttsx3",
  "routing_rules": {
    "length_weight": 0.3,
    "verb_weight": 8,
    "cross_app_bonus": 10,
    "threshold_score": 30,
    "custom_keywords": ["安装", "配置", "设置"]
  },
  "updated_at": "2026-06-29T12:00:00Z"
}
```

**配置拉取 HTTP 端点（C 管理）**：

```
GET /api/config/pull
Header: X-Client-Version: v2.1.0
Header: X-Demo-Key: hajimi-demo-2026

Response 200 (有更新):
{
  "has_update": true,
  "config": { ...ClientConfig }
}

Response 304 (无更新):
(空 body，ETag 匹配)
```

---

### 接口 9：心跳/健康检测

**方式**：方法调用（同步，非信号）

B 启动后调用 C 的健康检测方法，确认各子模块正常。

```python
# B 侧调用
health = c_health_check()
# 返回 HealthStatus 对象

# C 侧实现
def health_check() -> HealthStatus:
    return HealthStatus(
        asr_available=check_vosk_model_exists(),
        tts_available=check_pyttsx3_engine(),
        audit_db_ok=check_sqlite_writable(),
        server_reachable=ping_server(),
        queue_depth=get_audit_queue_depth()
    )
```

**数据模型**：`HealthStatus`

| 字段 | 类型 | 说明 |
|------|------|------|
| `asr_available` | bool | Vosk 模型是否可用 |
| `asr_engine` | string | 当前 ASR 引擎 |
| `tts_available` | bool | TTS 引擎是否可用 |
| `tts_engine` | string | 当前 TTS 引擎 |
| `audit_db_ok` | bool | 本地 SQLite 是否正常 |
| `server_reachable` | bool | 后端服务是否可达 |
| `queue_depth` | int | 离线审计队列深度 |
| `overall` | string | `healthy` / `degraded` / `unhealthy` |

**B 侧处理**：
- `overall = degraded` → 状态栏显示黄色 "⚠ 部分服务降级"
- `overall = unhealthy` → 状态栏显示红色 "❌ 服务异常"
- `server_reachable = false` → 审计队列图标闪烁，提示离线模式

---

## 四、信号注册总表

C 在初始化时注册以下信号连接：

```python
class VoiceIntegrationController:
    """C 侧初始化 —— 绑定 B 的信号与 C 的槽函数"""

    def __init__(self, b_signals, shared_state):
        # ASR 语音识别
        b_signals.asr_start.connect(self.asr_client.start_recording)
        b_signals.asr_stop.connect(self.asr_client.stop_and_transcribe)
        self.asr_client.result_ready.connect(b_signals.asr_result.emit)

        # TTS 语音合成
        b_signals.tts_enqueue.connect(self.tts_engine.enqueue)
        self.tts_engine.status_changed.connect(b_signals.tts_status.emit)

        # 语音设置（共享状态引用）
        self.voice_settings = shared_state["voice_settings"]

        # 审计代理
        b_signals.audit_submit.connect(self.audit_agent.enqueue)
        self.audit_agent.batch_result.connect(b_signals.audit_status.emit)

        # 配置拉取
        self.config_poller = ConfigPoller(
            interval_min=shared_state.get("config_pull_interval_min", 30)
        )
        self.config_poller.config_changed.connect(b_signals.config_updated.emit)

        # 健康检测
        b_signals.health_check_request.connect(self._handle_health_check)
```

---

## 五、关键约定与约束

| 约定 | 说明 |
|------|------|
| **线程安全** | TTS 播报和 ASR 录音在独立线程中运行，信号跨线程传递必须使用 `Qt.QueuedConnection` |
| **优雅降级** | ASR/TTS 不可用时不影响核心文字指引功能，B 自动隐藏麦克风按钮和喇叭图标 |
| **离线优先** | `server_reachable = false` 时，审计数据全部缓存本地，联网后自动批量补传 |
| **信号超时** | ASR 录音最长 60 秒自动停止；TTS 单条最长 120 秒超时跳过 |
| **耦合极低** | B 与 C 仅通过 9 个信号/方法交互，任一方可独立 Mock 测试 |

---

## 六、B 与 C 联调检查清单

### C 自检

- [ ] Vosk 模型文件（~50MB）已下载到 `models/vosk-model-small-cn-0.22/`
- [ ] `pyttsx3` 初始化成功，能播放测试语音
- [ ] `SpeechRecognition` 测试通过（`recognize_google` 或 `recognize_sphinx`）
- [ ] 审计上报：脱离 B 独立测试 `POST /api/audit/report` 成功
- [ ] 审计本地 SQLite 队列读写正常
- [ ] 配置轮询：独立测试 `GET /api/config/pull` 返回 200 或 304
- [ ] 健康检测方法返回正确的 `HealthStatus`

### B 自检

- [ ] 麦克风按钮 `pressed` / `released` 信号正确发射
- [ ] TTS 触发信号在步骤切换时正确发射（含步骤描述文本）
- [ ] 审计数据提交信号在任务结束时正确发射（含完整 `AuditRecord`）
- [ ] 设置面板 Toggle/slider 绑定到 `voice_settings` 共享状态
- [ ] 能接收并处理 `asr_result` → 填入输入框
- [ ] 能接收并处理 `tts_status` → 更新喇叭图标动画
- [ ] 能接收 `config_updated` → 热加载路由规则

### 联调共同检查

- [ ] 按下麦克风按钮 → C 开始录音 → 松开 → C 返回文字 → B 输入框显示文字
- [ ] 步骤切换 → C 播放 TTS → 播报完成 → B 喇叭动画停止
- [ ] 关闭 TTS 开关 → 步骤切换时不再触发 `tts_enqueue`
- [ ] 任务完成 → B 提交审计数据 → C 脱敏后进入 SQLite 队列
- [ ] 手动触发配置拉取 → C 获取最新配置 → B 收到通知并更新
- [ ] 断开网络 → 审计队列开始积压 → B 状态栏显示积压数量

---

## 七、后续扩展预留

1. **语音唤醒词**：C 可增加 `snowboy` 热词检测（如 "Hey HAJIMI"），检测到后 emit `wake_word_detected` 信号给 B，B 自动弹出挂件并聚焦输入框。
2. **多语言 TTS**：`voice_settings` 中增加 `language` 字段，C 根据语种切换 TTS 引擎。
3. **审计队列持久化加密**：本地 SQLite 中敏感字段用 AES-256-GCM 加密存储，密钥由用户主密码派生。
4. **Web 管理面板**：C 独立提供 `http://localhost:8090` 管理控制台（Vue3 + Element-Plus），B 在设置中提供"打开管理面板"快捷入口。
