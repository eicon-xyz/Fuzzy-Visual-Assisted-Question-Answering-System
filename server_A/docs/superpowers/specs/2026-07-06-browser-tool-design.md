# 浏览器控制 Tool — 设计文档

**Date:** 2026-07-06
**Reference:** `docs/superpowers/specs/2026-07-05-agent-loop-execution-design.md` §4.3

---

## 1. 目标

为 Execution Agent 添加浏览器操控能力，通过 Playwright/CDP 直接操作 DOM，比 OmniParser 视觉坐标点击更精确可靠。

## 2. 架构决策

### 方案选型

| 方案 | 描述 | 结论 |
|------|------|------|
| A | 在现有 `ExecutionAgent` 中直接添加 `browser_` 前缀工具 | ✅ **采纳** |
| B | 独立 `BrowserAgent` 子代理 | ❌ 跨代理协调复杂 |
| C | 继续用 `get_screen_info` + `click` 在浏览器窗口上操作 | ❌ 坐标不精确 |

选择方案 A 的理由：单一 LLM 上下文可看到全部工具，在桌面操作和浏览器操作之间无缝切换。

### 技术栈

- **Playwright** (`playwright.async_api`) — Chromium 启动 + CDP 操控
- **headless=False** — 可见模式，方便人工观察调试
- **DOM 快照而非全量 HTML** — 只提取可交互元素（a/button/input/select/textarea），上限 80 个，避免 Token 爆炸

## 3. 文件结构

```
新增:
  server/services/browser/
  ├── __init__.py           # 导出 BrowserController
  └── controller.py         # BrowserController 类

修改:
  server/services/executor/agent.py   # +6 tool defs, +dispatch 分支, +生命周期
  server/services/executor/engine.py  # cleanup 中 close_browser()
```

## 4. BrowserController API

### 4.1 生命周期

```
browser = BrowserController()
await browser.start(headless=False)   # 启动 Chromium
await browser.navigate("https://...")  # 导航
await browser.get_snapshot()           # DOM 快照
await browser.click("#btn")            # 点击
await browser.close()                  # 释放资源
```

### 4.2 方法一览

| 方法 | 参数 | 返回 |
|------|------|------|
| `start(headless=False)` | — | — |
| `close()` | — | — |
| `navigate(url)` | `url: str` | `{success, url, title, status}` |
| `get_snapshot()` | — | `{success, title, url, elements[], snapshot_text}` |
| `click(selector)` | `selector: str` | `{success, selector, tag, text}` |
| `type(selector, text)` | `selector, text` | `{success, selector, text}` |
| `scroll(direction, amount=300)` | `direction: "up"/"down"`, `amount: int` | `{success, direction, amount}` |

### 4.3 DOM 快照设计（关键）

**不是原始 HTML**。通过 `page.evaluate()` 在浏览器中运行 JS 提取：

- 只收集可交互元素：`a, button, input, select, textarea, [role="..."], [contenteditable], [onclick]`
- 每个元素返回：`{tag, text, selector, href, type, name, id}`
- 跳过不可见/屏幕外元素
- 上限 **80 个元素**，每个文本最长 **120 字符**
- 同时生成紧凑文本格式 `snapshot_text` 供 LLM 阅读

### 4.4 Selector 策略

```
优先级:
  1. #id        → "#search-input"
  2. tag.class  → "button.submit-btn"
  3. tag        → "input"
  4. text=      → "text=登录" (Playwright text selector)
```

## 5. ExecutionAgent 集成

### 5.1 工具定义（6 个新工具）

| Tool | 参数 | 说明 |
|------|------|------|
| `browser_navigate` | `url: str` | 导航到 URL |
| `browser_snapshot` | — | 获取页面交互元素 |
| `browser_click` | `selector: str` | 点击元素 |
| `browser_type` | `selector, text` | 输入文本 |
| `browser_scroll` | `direction, amount` | 滚轮 |
| `browser_close` | — | 关闭浏览器 |

总计：原有 10 个桌面工具 + 6 个浏览器工具 = **16 个工具**。

### 5.2 Async/Sync 桥接

Execution Agent 在后台线程运行（同步），Playwright API 是异步的。

```
dispatch_tool("browser_click", ...)
  → self._run_async(self.browser.click(...))
    → asyncio.run(coro)  # 在后台线程中创建临时 event loop
```

`asyncio.run()` 每次调用创建新的 event loop。浏览器工具调用频率低（每步 1-5 次），开销可接受。

### 5.3 惰性启动

```python
@property
def browser(self) -> BrowserController:
    if self._browser is None:
        self._browser = BrowserController()
    return self._browser
```

首次 `browser_*` 调用时自动 `_ensure_browser_started()` → `browser.start(headless=False)`。

### 5.4 生命周期管理

- **启动**：首次 browser tool 调用时惰性启动
- **主动关闭**：LLM 调用 `browser_close` tool
- **被动清理**：`engine.py` 的 `_cleanup()` 中调用 `agent.close_browser()`
- **幂等安全**：`close()` 在未启动的 browser 上是 no-op

## 6. 系统提示补充

```
## 浏览器工具（browser_ 前缀）
当需要操作网页时，优先使用 browser_ 前缀的工具。它们基于 DOM 操作，比视觉点击更精确。

### 浏览器工作流程
1. 如果当前步骤涉及网页操作，先调用 browser_navigate 打开目标网址
2. 然后调用 browser_snapshot 查看页面有哪些可交互元素
3. 根据 snapshot 返回的 selector 信息，调用 browser_click / browser_type 执行操作
4. 必要时再次 browser_snapshot 验证结果
5. 步骤完成后，如果后续不再需要浏览器，调用 browser_close 释放资源
```

## 7. 安全考量

- 浏览器操作不触发 Safety Gate（safety gate 针对桌面坐标点击）
- 浏览器 sandbox 由 Chromium 自身提供
- `navigate()` 只允许 http/https URL

## 8. 后续优化项

| 项目 | 优先级 | 说明 |
|------|--------|------|
| `browser_screenshot` tool | P1 | 截图返回给 LLM 做视觉验证（与 OmniParser 无关） |
| `browser_press_key` tool | P2 | 键盘快捷键（Enter/Escape/Tab） |
| CSS selector 自动生成优化 | P2 | 当前基于 tag.className，可引入更稳定的选择器策略 |
| 多标签页支持 | P3 | 当前只操作第一个 page |
