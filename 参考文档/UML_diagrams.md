# HAJIMI 自动操作助手 — 图表与 UML 描述 V2.0

> **版本**：V2.0 | **日期**：2026-07-06  
> 本文档配合概要设计文档使用，提供全部架构图、流程图、ER 图的 Mermaid/PlantUML 描述。  
> **注意**：V2.0 起系统从"桌面指引"升级为"自动操作助手"——可直接代为点击/输入/双击。

---

## 图1 项目定位图

### 文字描述

- **顶部**：标题 "HAJIMI 自动操作助手"
- **左侧**：三类目标用户（新手/老年/视障）及其核心痛点
- **中间**：系统核心能力链 —— 屏幕感知 → 意图理解 → 自动执行（点击/输入/双击）
- **右侧**：安全边界 —— 风险评分 + 红线检测 + 信任级别
- **底部**：价值主张 —— 降低操作门槛、实时上下文、自动完成任务

```mermaid
mindmap
  root((HAJIMI<br/>自动操作助手))
    目标用户
      新手用户
        "不会复杂操作"
      老年用户
        "看不清找不着"
      视障用户
        "屏幕朗读器不够用"
    核心能力
      屏幕感知
        OmniParser 元素检测
        多模态 LLM 看图
      意图理解
        9大意图域分类
        5种指代消解
      自动执行
        点击 click
        输入 type
        双击 double_click
        快捷键 hotkey
        拖拽 drag
        滚动 scroll
    安全边界
      风险评分(1-5)
      红线关键词拦截
      信任级别(balanced)
```

---

## 图2 核心业务时序图

```mermaid
sequenceDiagram
    participant U as 用户
    participant B as B端(PyQt5)
    participant A as A端(FastAPI)
    participant O as OmniParser
    participant E as 执行引擎

    U->>B: 语音/文本:"把微信安装到D盘"
    B->>B: 截取全屏(mss)
    B->>A: POST /execute(query+截图)
    A->>O: POST /parse(截图)
    O-->>A: 元素列表+SoM标注图
    A->>A: 风险评分+红线检测
    A->>A: LLM规划步骤(action+bbox)
    A-->>B: SSE /stream/{task_id} 实时推送
    B->>E: 自动执行(click/type/dblclick)
    E-->>B: 执行完成
    B->>A: POST /audit/report
```

---

## 图3 系统功能模块结构图

```mermaid
graph TB
    subgraph 客户端[B端+C端 桌面应用]
        B1[屏幕截取 mss+PIL]
        B2[执行引擎 pyautogui]
        B3[PyQt5 UI 面板]
        C1[ASR语音识别]
        C2[TTS语音合成]
        C3[审计代理 SQLite]
        C4[配置轮询 ETag]
    end

    subgraph 服务端[A端 FastAPI :8010]
        A1[demo路由 /execute /stream /cancel]
        A2[admin路由 统计/故障/配置]
        A3[audit路由 审计上报]
        A4[auth路由 JWT签发]
        A5[flow路由 拓扑/QPS/版本]
        A6[monitor路由 健康/告警]
        A7[LLM规划 意图+步骤+坐标]
    end

    subgraph AI服务
        O1[OmniParser :9800]
        O2[多模态LLM qwen/gpt/deepseek]
    end

    subgraph 管理端
        W1[Web面板 Vue3+ECharts]
        W2[6页面:总览/失败/流/配置/健康]
    end

    B1 --> A1
    A1 --> O1
    A1 --> O2
    A1 --> B2
    B1 --> B3
    C3 --> A3
    C4 --> A1
```

---

## 图4 E-R 实体结构图

```mermaid
erDiagram
    User {
        string user_id PK
        string username UK
        string password_hash
        string role
        json preferences
    }
    Transaction {
        string task_id PK
        string user_id FK
        datetime timestamp
        string intent_category
        string user_query
        string intent_summary
        string plan_type "L2/L3"
        int complexity_score
        json blueprint_json
        string result "success/fail/cancel"
        int duration_ms
        bool redline_triggered
    }
    StepLog {
        string log_id PK
        string task_id FK
        int step_index
        string action "click/type/dblclick/drag/hotkey"
        string target_element_id
        json target_bbox
        string status "pending/active/done/failed"
        string error_code
    }
    Feedback {
        string feedback_id PK
        string task_id FK
        string feedback_type "useful/useless/neutral"
        text comment
    }
    Failure {
        string failure_id PK
        string task_id FK
        string failure_type
        int step_index
        text error_detail
    }
    SystemConfig {
        string config_id PK
        string config_key UK
        json config_value
    }
    RedlineLog {
        string log_id PK
        string query
        string category
        string action "reject"
        string message
    }

    User ||--o{ Transaction : "发起"
    Transaction ||--o{ StepLog : "包含"
    Transaction ||--o{ Feedback : "收到"
    Transaction ||--o{ Failure : "触发"
```

---

## 图5 系统四层逻辑架构图

```mermaid
graph TB
    subgraph 表示层
        P1[PyQt5 桌面面板 480x520]
        P2[透明覆盖层 箭头/高亮/编号]
        P3[Web管理面板 Vue3+ECharts 6页]
    end
    subgraph 应用层
        AP1[执行引擎 click/type/dblclick]
        AP2[步骤状态机 advance/rollback/skip]
        AP3[审计代理 脱敏+批量上报]
        AP4[配置轮询 ETag+变更通知]
    end
    subgraph 服务层
        S1[FastAPI 26端点 :8010]
        S2[LLM规划 意图+步骤+坐标]
        S3[风险评分 1-5级]
        S4[红线检测 关键词+正则]
    end
    subgraph 数据层
        D1[SQLite 7表 hajimi.db]
        D2[OmniParser 远程GPU :9800]
        D3[多模态LLM API]
    end
    表示层 --> 应用层
    应用层 --> 服务层
    服务层 --> 数据层
```

---

## 图6 网络部署架构图

```
┌─────────────────────────────────────────────┐
│  本地 PC (Windows)                          │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐  │
│  │ B端 GUI │  │ A端 :8010│  │ Web :5173  │  │
│  │ PyQt5   │  │ FastAPI  │  │ Vue3       │  │
│  └────┬────┘  └────┬─────┘  └─────┬──────┘  │
│       │            │              │          │
└───────┼────────────┼──────────────┼──────────┘
        │            │              │
   SSH隧道:9800   本地 :8010    本地 :5173
        │            │              │
┌───────┴────────────┴──────────────┴──────────┐
│  远程服务器                                  │
│  ┌──────────────┐  ┌──────────────────────┐  │
│  │ OmniParser   │  │ LLM API (云端)       │  │
│  │ :9800 (GPU)  │  │ qwen/gpt/deepseek   │  │
│  └──────────────┘  └──────────────────────┘  │
└──────────────────────────────────────────────┘
```

---

## 图7 蓝图状态机转换图

```mermaid
stateDiagram-v2
    [*] --> generated: /execute
    generated --> executing: SSE 推送开始
    executing --> completed: 全部步骤完成
    executing --> suspended: 风险评分≥4/用户取消
    executing --> rolling_back: 用户回退一步
    suspended --> executing: 用户确认继续
    suspended --> terminated: 用户终止
    terminated --> [*]
    completed --> [*]
```

---

## 图8 主界面示意图（文字描述）

桌面右下角悬浮面板（480×520px），三区域：

- **顶部标题栏**：HAJIMI + 风格切换按钮 + 折叠/关闭
- **中部对话区**：用户问题气泡 + AI 步骤卡片（每步显示 action 类型 + 风险评分圆点）
- **底部控制栏**：输入框 + 麦克风按钮 + 执行/取消按钮 + 声波动画

---

## 图9 执行动作类型（V2.0 新）

| action | 说明 | 参数 |
|--------|------|------|
| `click` | 鼠标左键单击 | bbox_center |
| `double_click` | 鼠标左键双击 | bbox_center |
| `type` | 键盘输入文本 | params: 文本内容 |
| `hotkey` | 组合快捷键 | params: "ctrl+c" |
| `drag` | 鼠标拖拽 | from→to bbox |
| `scroll` | 滚轮滚动 | params: 方向+距离 |

---

## 图10 数据库物理模型图

7张表，SQLite 存储，路径 `new_JIMI/HAJIMI_UI/data/hajimi.db`。

核心表：
- `t_transactions` — 事务主表（task_id PK，含 blueprint_json）
- `t_step_logs` — 步骤日志（外键→transaction，记录每步 action/bbox/status）
- `t_feedback` — 用户反馈（useful/useless/neutral）
- `t_failures` — 失败归因（failure_type + error_detail）
- `t_system_configs` — 系统配置（key-value）
- `t_users` — 用户
- `t_redline_logs` — 红线拦截日志

---

## 图11 二级速度保障流程

```mermaid
flowchart TD
    Q[用户问题] --> C{复杂度评分}
    C -->|score<30| L2[L2 快路径<br/>本地规则<br/><3s]
    C -->|score>=30| L3[L3 慢路径<br/>LLM规划<br/>5-10s]
    L2 --> E1[直接执行模板步骤]
    L3 --> O[OmniParser检测]
    O --> LLM[LLM生成步骤+坐标]
    LLM --> RS[风险评分]
    RS --> E2[安全确认后执行]
```

---

## 图12 意图理解 VS 自动执行（V2.0 关键变更）

| 维度 | V1.x (指引助手) | V2.0 (自动操作) |
|------|----------------|----------------|
| 输出 | 箭头/高亮/语音指引 | **自动点击/输入/双击** |
| 安全 | 只指路不操作 | **风险评分 + 红线拦截 + 用户确认** |
| API | /process + /step | **/execute + /stream(SSE) + /cancel** |
| 执行层 | ANNO 覆盖层渲染 | **pyautogui 系统级操作** |
| 速度 | L2<3s / L3 5-10s | 同左 |
| 权限 | 无系统操作权限 | **需要桌面自动化权限** |

---

*（图 13-20 的界面示意图和详细 UML 图与 V1 时代保持一致，本文档不重复。新系统增加了执行引擎 executor/ 和自动操作 API，但不改变四层架构、ER 实体、技术栈的基本结构。）*
