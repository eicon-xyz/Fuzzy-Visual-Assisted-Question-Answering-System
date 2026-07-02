# HAJIMI A–C 接口契约

> **版本**：1.0.0
> **用途**：A（后端/AI 核心）与 C（集成/管理端/语音）之间的接口对齐
> **通信方式**：HTTP REST（C 作为 HTTP 客户端，A 作为 HTTP 服务端）
> **覆盖范围**：审计上报、配置管理、管理控制台全部 15 个数据接口、健康检查

---

## 一、架构概述

A 提供 FastAPI 服务端，C 通过 HTTP 调用 A 的接口。C 包含两个客户端角色：

```
┌──────────────────────────┐      HTTP       ┌──────────────────────────┐
│  C (集成/管理端/语音)      │ ◄────────────► │  A (后端/AI 核心)          │
│                          │                 │                          │
│  ┌─ 审计代理 (AuditAgent)│──POST /audit──►│  FastAPI Server           │
│  ├─ 配置轮询 (ConfigPoller)│──GET /config──►│  ├─ /api/audit/*          │
│  ├─ Web 管理面板 (Vue3)  │──GET /admin/*─►│  ├─ /api/admin/*          │
│  └─ 心跳检测             │──GET /health──►│
│                          │                 │  └─ /api/config/*         │
└──────────────────────────┘                 └──────────────────────────┘
```

---

## 二、接口总览

### 2.1 接口矩阵

| # | 分类 | 方法 | 路径 | C 调用方 | 用途 |
|---|------|------|------|----------|------|
| **审计** |
| 1 | Audit | POST | `/api/audit/report` | 审计代理 | 批量上报脱敏后的审计日志 |
| 2 | Audit | POST | `/api/audit/feedback` | 审计代理 | 上报用户反馈（有用/无用/中立） |
| **配置** |
| 3 | Config | GET | `/api/config/pull` | 配置轮询器 | 客户端拉取最新配置（ETag） |
| 4 | Config | GET | `/api/admin/config/current` | Web 管理面板 | 获取当前全部配置 |
| 5 | Config | POST | `/api/admin/config/deploy` | Web 管理面板 | 热部署配置下发 |
| **管理控制台 — 总览** |
| 6 | Admin | GET | `/api/admin/stats/overview` | Web 管理面板 | KPI 卡片数据 |
| 7 | Admin | GET | `/api/admin/stats/trend` | Web 管理面板 | 24h 趋势图数据 |
| 8 | Admin | GET | `/api/admin/stats/feedback` | Web 管理面板 | 反馈分布 + L2/L3 占比 |
| 9 | Admin | GET | `/api/admin/stats/top-tasks` | Web 管理面板 | 高频任务 TOP N |
| 10 | Admin | GET | `/api/admin/stats/redline` | Web 管理面板 | 红线拦截统计 |
| **管理控制台 — 失败归因** |
| 11 | Admin | GET | `/api/admin/failures/stats` | Web 管理面板 | 失败类型分布 + 趋势 |
| 12 | Admin | GET | `/api/admin/failures/list` | Web 管理面板 | 失败详情列表（游标分页） |
| 13 | Admin | GET | `/api/admin/failures/detail/{task_id}` | Web 管理面板 | 单条失败详情（含 LLM 快照） |
| **管理控制台 — 数据流监控** |
| 14 | Admin | GET | `/api/admin/flow/topology` | Web 管理面板 | 数据流拓扑实时数据 |
| 15 | Admin | GET | `/api/admin/flow/metrics` | Web 管理面板 | 接口 QPS/成功率 |
| 16 | Admin | GET | `/api/admin/flow/versions` | Web 管理面板 | 客户端版本分布 |
| **管理控制台 — 健康监控** |
| 17 | Admin | GET | `/api/admin/monitor/health` | Web 管理面板 | 组件健康状态 |
| 18 | Admin | GET | `/api/admin/monitor/alerts` | Web 管理面板 | 告警列表 |
| **系统** |
| 22 | System | GET | `/api/health` | 心跳检测 | 服务健康检查 |
| 23 | System | POST | `/api/auth/login` | Web 管理面板 | 管理员登录 |

---

## 三、接口详情

### 3.1 审计上报

#### `POST /api/audit/report`

C 的审计代理批量上报脱敏后的审计日志。

**请求**：
```http
POST /api/audit/report
X-Demo-Key: hajimi-demo-2026
Content-Type: application/json
```

```json
{
  "client_id": "desktop-7f3a2b1c",
  "batch": [
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
      "fingerprint_mismatches": 0,
      "redline_triggered": false,
      "timestamp": "2026-06-29T14:32:15+08:00"
    }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `client_id` | string | ✅ | 客户端唯一标识 |
| `batch` | array | ✅ | 审计记录列表，1~100 条 |
| `batch[].task_id` | uuid | ✅ | 任务 ID |
| `batch[].query` | string | ✅ | 脱敏后用户提问 |
| `batch[].intent_category` | string | ✅ | 九大意图域 |
| `batch[].route` | string | ✅ | `L2` / `L3` |
| `batch[].result` | string | ✅ | `success` / `fail` / `cancel` / `redirect` / `rejected` |

**响应 200**：
```json
{
  "received": 10,
  "server_queue_depth": 45
}
```

C 的处理：`received` 确认后从本地 SQLite 删除对应记录；若 `server_queue_depth > 100` 则减缓上报频率。

---

#### `POST /api/audit/feedback`

上报用户对某次任务的反馈（与审计日志解耦，可单独发送）。

**请求**：
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "feedback_type": "useful",
  "comment": "指引很清晰，步骤准确"
}
```

**响应 200**：
```json
{
  "received": true
}
```

---

### 3.2 配置管理

#### `GET /api/config/pull`

C 的配置轮询器定时拉取配置。支持 ETag 条件请求。

```http
GET /api/config/pull
X-Demo-Key: hajimi-demo-2026
X-Client-Version: v2.1.0
If-None-Match: "a1b2c3d4e5f6"
```

**响应 200（有更新）**：
```json
{
  "has_update": true,
  "config": {
    "version": "v2.1.3",
    "confidence_threshold": 80,
    "llm_api_endpoint": "https://api.openai.com/v1",
    "llm_model": "gpt-4o",
    "template_similarity_threshold": 90,
    "max_blueprint_steps": 15,
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
}
```

**响应 304**：配置未变更，空 body。

---

#### `GET /api/admin/config/current`

Web 管理面板 — 系统配置页初始化时获取当前所有配置。

**响应 200**：同上 `config` 对象，外加 `deployed_at`（上次部署时间）和 `deployed_by`（部署管理员）。

```json
{
  "config": { "...同 config/pull 的 config 对象..." },
  "deployed_at": "2026-06-29T11:00:00Z",
  "deployed_by": "admin@hajimi.local"
}
```

---

#### `POST /api/admin/config/deploy`

Web 管理面板 — 热部署配置到所有在线客户端。

**请求**（JWT Bearer Token 认证）：
```json
{
  "config": {
    "confidence_threshold": 85,
    "llm_model": "gpt-4o",
    "routing_rules": { "...": "..." }
  }
}
```

| 规则 | 说明 |
|------|------|
| 仅发送要变更的字段（部分更新） | 未传字段保持原值 |
| `routing_rules` 整体替换 | 非深度 merge |

**响应 200**：
```json
{
  "deployed": true,
  "version": "v2.1.4",
  "affected_clients": 42,
  "deployed_at": "2026-06-29T14:35:00Z"
}
```

> A 收到部署请求后更新配置版本号并持久化。客户端下次 `GET /api/config/pull` 时检测到新版本后拉取。

---

### 3.3 管理控制台 — 总览

#### `GET /api/admin/stats/overview`

总览页 5 张 KPI 卡片数据。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `range` | string | `24h` | 时间范围：`1h` / `24h` / `7d` / `30d` |

**响应 200**：
```json
{
  "today_volume": 1247,
  "volume_change_pct": 12,
  "online_clients": 42,
  "overall_useful_rate": 0.89,
  "overall_fail_rate": 0.032,
  "monthly_api_cost_usd": 96.50
}
```

---

#### `GET /api/admin/stats/trend`

24 小时事务量/响应时长趋势。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `metric` | string | `volume` | `volume`（事务量）或 `latency`（响应时长） |
| `range` | string | `24h` | 时间范围 |

**响应 200（metric=volume）**：
```json
{
  "metric": "volume",
  "granularity": "1h",
  "data": [
    {"hour": "00:00", "value": 12},
    {"hour": "01:00", "value": 8},
    {"hour": "12:00", "value": 110, "peak": true}
  ],
  "peak": {"hour": "12:00", "value": 110}
}
```

**响应 200（metric=latency）**：
```json
{
  "metric": "latency",
  "granularity": "1h",
  "unit": "seconds",
  "data": [
    {"hour": "00:00", "value": 2.1}
  ],
  "baselines": {
    "l2_threshold_s": 3.0,
    "l3_threshold_s": 10.0
  }
}
```

---

#### `GET /api/admin/stats/feedback`

反馈分布 + L2/L3 处理路径占比（用于双饼图）。

**响应 200**：
```json
{
  "feedback_distribution": {
    "useful": 89,
    "useless": 6,
    "neutral": 5
  },
  "route_distribution": {
    "l2": 70,
    "l3": 30
  },
  "total_feedback_count": 1247
}
```

---

#### `GET /api/admin/stats/top-tasks`

高频操作任务 TOP N。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | int | 10 | 返回条数 |
| `range` | string | `7d` | 统计范围 |

**响应 200**：
```json
{
  "tasks": [
    {"rank": 1, "name": "VSCode 编辑文件", "count": 245, "route_l2_pct": 78},
    {"rank": 2, "name": "Chrome 浏览网页", "count": 198, "route_l2_pct": 92}
  ]
}
```

---

#### `GET /api/admin/stats/redline`

红线拦截统计 TOP N。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | int | 5 | 返回条数 |

**响应 200**：
```json
{
  "redlines": [
    {"type": "自动点击请求", "count": 67, "last_triggered": "2026-06-29T14:20:00Z"},
    {"type": "扫描硬盘请求", "count": 45, "last_triggered": "2026-06-29T13:15:00Z"},
    {"type": "系统命令注入", "count": 32, "last_triggered": "2026-06-29T12:40:00Z"}
  ]
}
```

---

### 3.4 管理控制台 — 失败归因

#### `GET /api/admin/failures/stats`

失败类型分布柱状图 + 失败趋势折线图数据。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `start` | string | ❌ | 开始时间 ISO 8601 |
| `end` | string | ❌ | 结束时间 ISO 8601 |
| `type` | string | ❌ | 失败类型筛选：`blueprint_mismatch` / `llm_timeout` / `parse_error` / `redline_blocked` / `user_abort` |

**响应 200**：
```json
{
  "distribution": [
    {"type": "blueprint_mismatch", "label": "蓝图不匹配", "count": 48},
    {"type": "llm_timeout", "label": "LLM 超时", "count": 32},
    {"type": "parse_error", "label": "解析错误", "count": 28},
    {"type": "redline_blocked", "label": "红线拦截", "count": 25},
    {"type": "user_abort", "label": "用户中止", "count": 23}
  ],
  "trend": [
    {"hour": "09:00", "count": 18},
    {"hour": "10:00", "count": 22},
    {"hour": "14:00", "count": 23}
  ],
  "total": 156
}
```

---

#### `GET /api/admin/failures/list`

失败详情列表（游标分页，无限滚动）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `start` | string | ❌ | 时间范围起始 |
| `end` | string | ❌ | 时间范围结束 |
| `type` | string | ❌ | 失败类型筛选 |
| `cursor` | string | ❌ | 游标（上一页最后一条的 ID） |
| `limit` | int | ❌ | 每页条数，默认 20 |

**响应 200**：
```json
{
  "items": [
    {
      "id": "fail_001",
      "task_id": "550e8400-...",
      "timestamp": "2026-06-29T14:22:10Z",
      "task_name": "打开 VSCode 编辑文件",
      "failed_step": 2,
      "failed_step_name": "指纹匹配",
      "error_summary": "蓝图 verb 不匹配",
      "error_type": "blueprint_mismatch",
      "route": "L3"
    }
  ],
  "next_cursor": "fail_021",
  "has_more": true,
  "total": 156
}
```

---

#### `GET /api/admin/failures/detail/{task_id}`

单条失败详情（含 LLM 输入/输出快照）。

**响应 200**：
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user_d07f1b",
  "route": "L3",
  "timestamp": "2026-06-29T14:22:10Z",
  "expected_fingerprint": {
    "app": "vscode",
    "action": "edit_file",
    "verb": "write"
  },
  "actual_fingerprint": {
    "app": "vscode",
    "action": "edit_file",
    "verb": "delete"
  },
  "mismatch_fields": ["verb"],
  "llm_input_snapshot": {
    "model": "gpt-4-vision-preview",
    "messages": "[脱敏后] 系统提示 + 用户截图分析请求",
    "temperature": 0.7,
    "max_tokens": 4096
  },
  "llm_output_snapshot": {
    "blueprint": "[脱敏后] 返回的蓝图步骤与错误节点",
    "finish_reason": "error",
    "error_detail": "timeout waiting for element #file_list"
  }
}
```

---

### 3.5 管理控制台 — 数据流监控

#### `GET /api/admin/flow/topology`

数据流向拓扑图实时数据。

**响应 200**：
```json
{
  "nodes": [
    {"id": "c12a", "label": "客户端 #c12a", "type": "client", "online": true},
    {"id": "d07f", "label": "客户端 #d07f", "type": "client", "online": true},
    {"id": "gateway", "label": "HAJIMI API Gateway", "type": "server"},
    {"id": "postgres", "label": "PostgreSQL", "type": "database"},
    {"id": "llm", "label": "LLM API (gpt-4o)", "type": "external"}
  ],
  "links": [
    {"source": "c12a", "target": "gateway", "qps": 12, "latency_ms": 45, "status": "healthy"},
    {"source": "d07f", "target": "gateway", "qps": 8, "latency_ms": 52, "status": "healthy"},
    {"source": "gateway", "target": "postgres", "qps": 30, "latency_ms": 12, "status": "healthy"},
    {"source": "gateway", "target": "llm", "qps": 8, "latency_ms": 4200, "status": "high_load"}
  ]
}
```

`status` 编码：
- `healthy`：延迟 < 阈值
- `high_load`：延迟 > 阈值 × 1.5
- `critical`：延迟 > 阈值 × 3 或连续失败

---

#### `GET /api/admin/flow/metrics`

指定接口的 QPS 与成功率时序数据。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `api_path` | string | ✅ | 接口路径，如 `/api/audit/report` |
| `range` | string | ❌ | 默认 `1h` |

**响应 200**：
```json
{
  "api_path": "/api/audit/report",
  "granularity": "5m",
  "data": [
    {"time": "09:00", "qps": 28, "success_rate": 0.999},
    {"time": "09:05", "qps": 32, "success_rate": 0.998}
  ]
}
```

---

#### `GET /api/admin/flow/versions`

各客户端版本号占比。

**响应 200**：
```json
{
  "versions": [
    {"version": "v2.1.0", "count": 34, "pct": 80.9},
    {"version": "v2.0.5", "count": 6, "pct": 14.3},
    {"version": "v1.9.0", "count": 2, "pct": 4.8}
  ],
  "total_clients": 42,
  "pull_interval_distribution": [
    {"range": "0-5min", "count": 30},
    {"range": "5-15min", "count": 8},
    {"range": "15-30min", "count": 3},
    {"range": ">30min", "count": 1, "stale": true}
  ]
}
```

---

### 3.6 管理控制台 — 健康监控

#### `GET /api/admin/monitor/health`

组件健康状态（含资源指标）。

**响应 200**：
```json
{
  "resources": {
    "cpu_pct": 42,
    "memory_gb": 3.2,
    "disk_free_gb": 128,
    "uptime": "14d 7h 23m",
    "uptime_seconds": 1234567
  },
  "components": [
    {"name": "PostgreSQL", "status": "healthy", "detail": "连接池 8/20"},
    {"name": "Redis", "status": "healthy", "detail": "命中率 94%"},
    {"name": "LLM API", "status": "degraded", "detail": "平均延迟 4.2s（超阈值 3s）"},
    {"name": "Nginx", "status": "healthy", "detail": "QPS 120"}
  ]
}
```

---

#### `GET /api/admin/monitor/alerts`

告警列表。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | int | 20 | 返回条数 |
| `status` | string | `all` | `all` / `unread` / `read` |

**响应 200**：
```json
{
  "alerts": [
    {
      "id": "alert_001",
      "timestamp": "2026-06-29T14:20:33Z",
      "level": "warning",
      "message": "LLM API 平均延迟 4.2s 超过阈值 3s，持续 15 分钟",
      "status": "unread"
    }
  ],
  "total_unread": 1,
  "total": 5
}
```

**`POST /api/admin/monitor/alerts/read-all`** — 标记全部告警为已读：

```json
{ "marked_read": 5 }
```

---

### 3.7 系统接口

#### `GET /api/health`

C 的心跳检测 + 服务端健康检查。无需认证。

**响应 200**：
```json
{
  "status": "ok",
  "version": "1.0.0",
  "server_time": "2026-06-29T14:32:15Z",
  "uptime_seconds": 1234567
}
```

---

#### `POST /api/auth/login`

Web 管理面板登录（JWT）。

**请求**（无需 Demo Key，使用独立认证）：
```json
{
  "username": "admin@hajimi.local",
  "password": "********"
}
```

**响应 200**：
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 7200,
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

管理面板所有 `/api/admin/*` 接口需携带：
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

---

## 四、C 调用方的职责边界

| C 子模块 | 调用的 A 接口 | 调用频率 | 失败处理 |
|----------|-------------|----------|----------|
| **审计代理** | `POST /api/audit/report` | 批量（≥10条 或 5分钟） | 指数退避重试，超 3 次写 fallback.log |
| **配置轮询器** | `GET /api/config/pull` | 每 30 分钟 | 使用本地缓存继续工作 |
| **心跳检测** | `GET /api/health` | 每 5 分钟 | 状态栏显示离线，审计队列标记 pending |
| **Web 管理面板** | 全部 `/api/admin/*` | 按需 | 显示错误 Toast，允许重试 |

---

## 五、认证方案

| 接口前缀 | 认证方式 | 说明 |
|----------|----------|------|
| `/api/audit/*` | `X-Demo-Key` header | Demo 阶段固定 Key |
| `/api/config/*` | `X-Demo-Key` header | 同上 |
| `/api/health` | 无 | 公开接口 |
| `/api/auth/*` | 无（登录接口本身） | Basic 变体（JSON body） |
| `/api/admin/*` | `Authorization: Bearer <JWT>` | 管理面板登录后获取 |

---

## 六、联调检查清单

### A 自检

- [ ] FastAPI 启动，`/api/health` 返回 200
- [ ] `POST /api/audit/report` 接收批量数据并返回 received 数量
- [ ] `GET /api/config/pull` 返回配置 + 支持 ETag 304
- [ ] 全部 15 个 `/api/admin/*` 端点可访问并返回合法 JSON
- [ ] `POST /api/auth/login` 能签发 JWT
- [ ] JWT 过期（2h）后 `/api/admin/*` 返回 401
- [ ] 错误响应格式符合统一 `{"error": {"code": "...", "message": "..."}}` 规范

### C 自检

- [ ] 审计代理：脱离管理面板独立测试 `POST /api/audit/report` 成功
- [ ] 配置轮询器：定时拉取 + ETag 缓存 + 变更通知
- [ ] 管理面板：登录 → 获取 JWT → 调用全部 admin 接口 → 渲染图表
- [ ] 管理面板：失败归因页下钻交互（点击柱状图过滤 + 无限滚动）
- [ ] 管理面板：系统配置页修改 + 热部署 → 确认 `/api/config/pull` 拉取到新版本
- [ ] 管理面板：模板审核发布 → 确认状态变更

### 联调共同检查

- [ ] 时区一致：所有时间戳使用 ISO 8601 + 时区偏移
- [ ] 分页一致：游标分页的 `cursor` 透传不出错
- [ ] 认证一致：管理面板 JWT 过期后自动跳转登录页
- [ ] 图表数据一致：管理面板图表数据与 A 返回数据可对应
