## 背景

HAJIMI 的 Execution Agent 目前只能通过 OmniParser 视觉定位 + pyautogui 坐标点击来操作桌面。操作网页时坐标点击不精确，且无法读取页面结构做智能决策。

借鉴 Page-eyes-agent 的浏览器操控思路，为 agent 新增 8 个 `browser_` 工具，通过 Playwright/CDP 直接操作 DOM — 点击、输入、截图、按键全部基于 CSS selector，不依赖坐标。

## 方案

### 架构决策

在现有 `ExecutionAgent` 中直接添加 `browser_` 前缀工具，LLM 在同一个 agent loop 中无缝切换桌面操作和浏览器操作。

| 文件 | 变更 |
|------|------|
| `server/services/browser/controller.py` | **新建** — BrowserController，封装 playwright.async_api Chromium |
| `server/services/executor/agent.py` | +8 工具定义、dispatch 分支、持久 event loop、系统提示 |
| `server/services/executor/engine.py` | cleanup 中 close_browser() |
| `server/tests/test_browser_controller.py` | **新建** — 24 个单元测试（mock Playwright） |
| `server/tests/test_browser_e2e.py` | **新建** — 3 个 E2E 冒烟测试（真实 Chromium） |

### 8 个浏览器工具

| Tool | 功能 |
|------|------|
| `browser_navigate` | 导航到 URL（4 级 wait_until 降级：commit→load→domcontentloaded→networkidle） |
| `browser_snapshot` | 获取页面可交互元素列表（非 HTML，上限 80 个，防 Token 爆炸） |
| `browser_click` | CSS selector 点击（force=true 跳过可见性检查 + detached DOM 重试） |
| `browser_type` | 输入框填文字（JS 直接设值 + dispatchEvent，绕过 actionability 检查） |
| `browser_scroll` | 滚轮滚动 |
| `browser_screenshot` | 视口截图（base64 JPEG 供前端展示） |
| `browser_press_key` | 键盘按键（Enter/Escape/Tab） |
| `browser_close` | 关闭浏览器（幂等安全） |

### 关键技术点

- **持久 event loop：** 专用 daemon 线程跑 `asyncio.new_event_loop()`，所有 browser 协程通过 `run_coroutine_threadsafe` 投递
- **持久化 profile：** `user_data_dir` 参数支持持久化浏览器 profile，cookie/登录状态跨 session 保留
- **CSS escape：** snapshot JS 中用 `CSS.escape()` 处理含特殊字符的 id/className
- **click(force=true)：** 跳过 Playwright 可见性检查（百度/SPA 页面部分元素 CSS-hidden）
- **type() JS 直接设值：** `el.value = text + dispatchEvent('input')`，不依赖键盘输入

## 验证

### 单元测试（24 passed，全部 mock Playwright，无需真实浏览器）

```bash
python -m pytest server/tests/test_browser_controller.py -v
```

| 测试类 | 数量 | 覆盖 |
|--------|------|------|
| TestBrowserLifecycle | 5 | start / close / idempotent / unstarted |
| TestNavigate | 5 | 一级成功 / 自动补 https / 分级降级 / 部分加载 / 完全失败 |
| TestClick | 2 | 成功 / element not found |
| TestType | 2 | 成功 / not found |
| TestSnapshot | 4 | 空页面 / 有元素 / 文本截断 / title+url |
| TestScroll | 2 | up / down |
| TestEnsureStarted | 1 | RuntimeError |
| TestScreenshot | 1 | base64 data-URI |
| TestPressKey | 2 | Enter / Control+a |

### E2E 测试（3 passed，真实 Chromium）

```bash
python -m pytest server/tests/test_browser_e2e.py -v -m e2e
```

- `test_navigate_and_snapshot` — 导航到 example.com → snapshot ≥1 个 a 标签
- `test_screenshot_returns_image` — 截图返回 ≥500 字符 base64
- `test_scroll_changes_viewport` — 真实页面滚动不抛异常

### 真实场景验证（DeepSeek Chat 端到端）

1. 打开 DeepSeek 官网 → 2. 点击"开始对话" → 3. 输入消息 → 4. 发送 → 5. 收到回复

```
[OK] Navigate: DeepSeek
[OK] Type: True
[OK] Pressed Enter
[OK] 回复: 17 元素
```

### 工具完整性

```
Total: 18 tools (10 desktop + 8 browser)
Browser: browser_navigate, browser_snapshot, browser_click, browser_type,
         browser_scroll, browser_close, browser_screenshot, browser_press_key
```
