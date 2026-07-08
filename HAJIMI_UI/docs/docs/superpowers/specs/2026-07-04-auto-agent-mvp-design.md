# HAJIMI 自动操作助手 — MVP 设计文档

> 4 天冲刺，3 人协作，12 人日

## 目标

将 HAJIMI 从「桌面指引助手」改为「自动操作助手」。用户输入自然语言指令，AI 自动操控电脑完成。

## 核心数据流

```
用户输入指令
    │
    ▼
截图(mss) → OmniParser :9800 → 元素列表 [{bbox, type, text, confidence}]
    │
    ▼
LLM 生成执行计划 [{step, action, bbox_center, params}]
    │
    ▼
逐步执行: pyautogui 点击坐标 → 等待 → 截图验证(LLM看图判断)
    │
    ▼
SSE 推送实时状态 → B端UI
```

## 技术选型

- 执行: pyautogui + pydirectinput（纯坐标模拟）
- 截图: mss（已有）
- 元素检测: 远程 GPU OmniParser :9800
- 通信: SSE（FastAPI StreamingResponse）
- UI: PyQt5，简单面板

## 文件结构

```
新增:
  server/services/executor/
  ├── __init__.py
  ├── engine.py          # 主循环
  ├── clicker.py         # pyautogui 封装
  └── safety.py          # 红线拦截

修改:
  server/config.py       # 恢复 OmniParser 配置
  server/routes/demo.py  # SSE 端点 + 恢复 OmniParser
  server/services/planning/router.py  # prompt 改为执行计划
  server/services/llm_ai.py           # 验证函数
  ui/agent_panel.py      # 新建: 简单监控面板
  ui/main_widget.py      # 集成新面板
```

## 4 天里程碑

| Day | 目标 |
|-----|------|
| 1 | OmniParser 返回元素 + pyautogui 能点击 + SSE 推送 |
| 2 | 端到端跑通一次简单任务（打开记事本） |
| 3 | 安全拦截 + 验证循环 + UI 实时状态 |
| 4 | 联调修 bug，可用的项目 |
