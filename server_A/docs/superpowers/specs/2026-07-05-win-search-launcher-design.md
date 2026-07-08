# 应用启动通道 — 设计文档

## 目标

用 **三层降级策略** 替代单一的 Win+Search 通道，在可靠性 ≥80% 的前提下将常见应用的启动成功率提升到接近 100%。

## 架构

```
launch_app("记事本")
    │
    ├─ Layer 1: 映射表命中？
    │   └─ APP_EXECUTABLE_MAP["记事本"] → "notepad.exe"
    │      → subprocess.Popen / os.startfile  ✅ 100% 可靠
    │
    ├─ Layer 2: shutil.which() 在 PATH 找到？
    │   └─ shutil.which("chrome") → "C:\...\chrome.exe"
    │      → subprocess.Popen  ✅ 90%+ 可靠
    │
    └─ Layer 3: Win+Search 兜底
        ├─ pyautogui.keyDown("win") → keyUp("win")
        ├─ sleep(0.5)
        ├─ pyperclip.copy(app_name) → hotkey("ctrl", "v")
        ├─ sleep(0.8)
        ├─ press("enter") + sleep(0.5)
        └─ press("esc")  ⚠️ ~80% 可靠（RDP 下下降到 ~60%）
```

## 设计决策

| 决策 | 理由 |
|------|------|
| Layer 1 映射表在 launcher.py 而非 agent.py | 单一职责：launcher 负责启动，agent 负责工具调度 |
| 不做 UIA 搜索框检测（方案 B） | 不同 Windows 版本 ClassName 不同，维护成本高 |
| Layer 3 用 pyautogui keyDown/keyUp 而非 pydirectinput hotkey | 实测 pydirectinput 在某些机器上无法触发 Win 键 |
| 映射表同时包含中英文 key | 用户可能用中文或英文指令 |
| `os.startfile` 用于绝对路径的 .exe | 通过 Windows shell 关联启动，更可靠 |

## 映射表覆盖范围

`server/services/launcher.py` → `APP_EXECUTABLE_MAP`

| 类别 | 示例 |
|------|------|
| 系统应用 | 计算器/记事本/画图/截图/任务管理器/控制面板/资源管理器/cmd/PowerShell |
| 浏览器 | Chrome/Edge/Firefox |
| 通讯 | 微信/QQ/钉钉/飞书/企业微信/Teams |
| 办公 | Word/Excel/PowerPoint/Outlook/WPS |
| 开发 | VSCode/Terminal/Git Bash |
| 音乐 | 网易云音乐/QQ音乐/Spotify/VLC |
| 其他 | Steam/Telegram/Discord/Notion/Obsidian |

新增应用只需在 `APP_EXECUTABLE_MAP` 加一行。

## 验收标准

1. `launch_app("记事本")` → Tier 1, notepad.exe 启动
2. `launch_app("notepad")` → Tier 1, notepad.exe 启动
3. `launch_app("计算器")` → Tier 1, calc.exe 启动
4. `launch_app("chrome")` → Tier 1 (mapping) 或 Tier 2 (PATH), Chrome 启动
5. `launch_app("FakeApp123")` → Tier 3 Win+Search 兜底（若失败返回 error）
6. 44 tests passed

## 相关文件

| 文件 | 角色 |
|------|------|
| `server/services/launcher.py` | 三层降级 + 映射表 + 前台聚焦 |
| `server/services/executor/agent.py` | 引用 `APP_EXECUTABLE_MAP` 做中文名映射后调用 `launch_app()` |
| `server/services/executor/clicker.py` | 键鼠封装（press_keys, type_text 等） |
