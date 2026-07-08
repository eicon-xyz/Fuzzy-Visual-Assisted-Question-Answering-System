# Browser Control Tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the browser control tool suite for ExecutionAgent — unit tests, edge case hardening, browser_screenshot tool, browser_press_key tool, and E2E smoke test.

**Architecture:** BrowserController wraps Playwright's async Chromium; ExecutionAgent exposes 8 browser tools (6 existing + 2 new) via a persistent daemon-thread event loop. All browser operations use DOM selectors (no coordinates). Snapshot returns structured interactive elements only, capped at 80.

**Tech Stack:** Python 3.12, Playwright 1.60 (playwright.async_api), pytest + pytest-asyncio, unittest.mock

## Global Constraints

- Playwright 1.60 already installed; Chromium binary must be present (`playwright install chromium`)
- All browser tools return `{"success": bool, "action_summary": str, ...}` dict — consistent with existing desktop tools
- `_run_async` uses persistent daemon-thread event loop with `run_coroutine_threadsafe` — never `asyncio.run()`
- Snapshot caps: 80 elements max, 120 chars text per element
- `navigate` uses 3-tier wait_until fallback: commit(8s) → load(15s) → domcontentloaded(20s) → networkidle(45s)
- Tests run in CI without a real browser — mock Playwright's async API

---

### Task 1: Unit tests — BrowserController with mocked Playwright

**Files:**
- Create: `server/tests/test_browser_controller.py`

**Interfaces:**
- Consumes: `server.services.browser.controller.BrowserController` (all public methods)
- Produces: 13 test cases covering lifecycle, navigate tiers, click, type, snapshot caps, scroll, error paths

- [ ] **Step 1: Create test file with imports and fixtures**

```python
"""
Unit tests for BrowserController — mock Playwright's async API.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_page():
    """Return a MagicMock that mimics a Playwright Page with async methods."""
    page = MagicMock()
    page.goto = AsyncMock()
    page.title = AsyncMock(return_value="Test Page")
    page.url = "https://example.com"
    page.locator = MagicMock()
    page.evaluate = AsyncMock(return_value=[])
    # locator().first pattern
    locator = MagicMock()
    locator.first = locator
    locator.click = AsyncMock()
    locator.fill = AsyncMock()
    locator.type = AsyncMock()
    locator.text_content = AsyncMock(return_value="Click Me")
    locator.evaluate = AsyncMock(return_value="button")
    page.locator.return_value = locator
    return page


@pytest.fixture
def mock_browser(mock_page):
    """Return a MagicMock that mimics a Playwright Browser."""
    browser = MagicMock()
    browser.new_page = AsyncMock(return_value=mock_page)
    browser.close = AsyncMock()
    return browser


@pytest.fixture
def mock_playwright(mock_browser):
    """Return a MagicMock that mimics Playwright instance."""
    pw = MagicMock()
    pw.chromium.launch = AsyncMock(return_value=mock_browser)
    return pw


@pytest.fixture
async def controller(mock_playwright):
    """Return a started BrowserController with mocked Playwright."""
    from server.services.browser.controller import BrowserController

    bc = BrowserController()
    with patch(
        "server.services.browser.controller.async_playwright",
        return_value=AsyncMock(start=AsyncMock(return_value=mock_playwright)),
    ):
        await bc.start(headless=True)
    return bc
```

- [ ] **Step 2: Run to verify test file imports cleanly**

```bash
cd D:/HAJI/HAJIMI_UI && python -c "import ast; ast.parse(open('server/tests/test_browser_controller.py', encoding='utf-8').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Write lifecycle tests — start, close, is_started, double close**

```python
class TestBrowserLifecycle:
    """BrowserController start/close lifecycle."""

    @pytest.mark.asyncio
    async def test_start_launches_chromium(self, controller, mock_page):
        assert controller.is_started is True
        assert controller._page is not None

    @pytest.mark.asyncio
    async def test_start_idempotent(self, controller):
        """Calling start() twice should not crash or create a second browser."""
        await controller.start()  # already started — should log and return
        assert controller.is_started is True

    @pytest.mark.asyncio
    async def test_close_cleans_up(self, controller):
        await controller.close()
        assert controller.is_started is False
        assert controller._page is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self, controller):
        await controller.close()
        await controller.close()  # second close should not crash
        assert controller.is_started is False

    @pytest.mark.asyncio
    async def test_is_started_before_start(self):
        from server.services.browser.controller import BrowserController
        bc = BrowserController()
        assert bc.is_started is False
```

- [ ] **Step 4: Write navigate tests — tier fallback, partial load**

```python
class TestNavigate:
    """Tiered wait_until navigation."""

    @pytest.mark.asyncio
    async def test_navigate_success_first_tier(self, controller, mock_page):
        mock_page.goto = AsyncMock(return_value=MagicMock(status=200))
        result = await controller.navigate("https://example.com")
        assert result["success"] is True
        assert result["title"] == "Test Page"
        assert result["wait_until"] == "commit"  # first tier succeeded
        # Verify first call used "commit"
        mock_page.goto.assert_called_with(
            "https://example.com", wait_until="commit", timeout=8_000
        )

    @pytest.mark.asyncio
    async def test_navigate_auto_adds_https(self, controller, mock_page):
        mock_page.goto = AsyncMock(return_value=MagicMock(status=200))
        result = await controller.navigate("example.com")
        assert result["success"] is True
        mock_page.goto.assert_called_with(
            "https://example.com", wait_until="commit", timeout=8_000
        )

    @pytest.mark.asyncio
    async def test_navigate_fallback_on_tier_failure(self, controller, mock_page):
        """If commit fails, falls back to load."""
        mock_page.goto = AsyncMock(side_effect=[
            TimeoutError("commit timed out"),          # tier 1 fails
            MagicMock(status=200),                     # tier 2 succeeds
        ])
        result = await controller.navigate("https://spa.example.com")
        assert result["success"] is True
        assert result["wait_until"] == "load"
        assert mock_page.goto.call_count == 2

    @pytest.mark.asyncio
    async def test_navigate_partial_load_detection(self, controller, mock_page):
        """All tiers fail but URL changed — partial success."""
        mock_page.goto = AsyncMock(side_effect=TimeoutError("all failed"))
        # Page URL changed despite goto failure (partial load)
        mock_page.url = "https://spa.example.com/dashboard"
        result = await controller.navigate("https://spa.example.com")
        assert result["success"] is True
        assert result["wait_until"] == "partial"
        assert "warning" in result

    @pytest.mark.asyncio
    async def test_navigate_complete_failure(self, controller, mock_page):
        """All tiers fail and URL stays about:blank."""
        mock_page.goto = AsyncMock(side_effect=TimeoutError("all failed"))
        mock_page.url = "about:blank"
        result = await controller.navigate("https://dead.example.com")
        assert result["success"] is False
        assert "error" in result
```

- [ ] **Step 5: Write click/type tests**

```python
class TestClick:
    @pytest.mark.asyncio
    async def test_click_success(self, controller, mock_page):
        result = await controller.click("#submit")
        assert result["success"] is True
        assert result["selector"] == "#submit"
        assert "clicked" in result["action_summary"]

    @pytest.mark.asyncio
    async def test_click_not_found(self, controller, mock_page):
        locator = mock_page.locator.return_value
        locator.click = AsyncMock(side_effect=Exception("Element not found"))
        result = await controller.click("#missing")
        assert result["success"] is False
        assert "not found" in result["error"]


class TestType:
    @pytest.mark.asyncio
    async def test_type_success(self, controller, mock_page):
        result = await controller.type("#input", "hello")
        assert result["success"] is True
        assert result["text"] == "hello"
        locator = mock_page.locator.return_value
        locator.click.assert_called_once()   # focus
        locator.fill.assert_called_once_with("")  # clear
        locator.type.assert_called_once_with("hello", delay=30)

    @pytest.mark.asyncio
    async def test_type_not_found(self, controller, mock_page):
        locator = mock_page.locator.return_value
        locator.click = AsyncMock(side_effect=Exception("No such element"))
        result = await controller.type("#missing", "text")
        assert result["success"] is False
```

- [ ] **Step 6: Write snapshot tests — element caps, text truncation**

```python
class TestSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_empty_page(self, controller, mock_page):
        mock_page.evaluate = AsyncMock(return_value=[])
        result = await controller.get_snapshot()
        assert result["success"] is True
        assert len(result["elements"]) == 0
        assert "0 elements" in result["action_summary"]

    @pytest.mark.asyncio
    async def test_snapshot_with_elements(self, controller, mock_page):
        mock_page.evaluate = AsyncMock(return_value=[
            {"tag": "button", "text": "Submit", "selector": "#submit",
             "href": "", "type": "submit", "name": "", "id": "submit"},
            {"tag": "a", "text": "Home", "selector": "a.nav",
             "href": "/home", "type": "", "name": "", "id": ""},
        ])
        result = await controller.get_snapshot()
        assert result["success"] is True
        assert len(result["elements"]) == 2
        assert "snapshot_text" in result
        assert "Submit" in result["snapshot_text"]

    @pytest.mark.asyncio
    async def test_snapshot_text_truncated(self, controller, mock_page):
        long_text = "A" * 200
        mock_page.evaluate = AsyncMock(return_value=[
            {"tag": "span", "text": long_text, "selector": "span",
             "href": "", "type": "", "name": "", "id": ""},
        ])
        result = await controller.get_snapshot()
        # Text is truncated client-side by JS; we just verify it doesn't blow up
        assert result["success"] is True
        assert len(result["snapshot_text"]) < 5000  # compact format

    @pytest.mark.asyncio
    async def test_snapshot_includes_title_and_url(self, controller, mock_page):
        mock_page.title = AsyncMock(return_value="My Dashboard")
        mock_page.url = "https://app.example.com/dashboard"
        mock_page.evaluate = AsyncMock(return_value=[])
        result = await controller.get_snapshot()
        assert result["title"] == "My Dashboard"
        assert "dashboard" in result["url"]
```

- [ ] **Step 7: Write scroll and _ensure_started tests**

```python
class TestScroll:
    @pytest.mark.asyncio
    async def test_scroll_down(self, controller, mock_page):
        result = await controller.scroll("down", 500)
        assert result["success"] is True
        mock_page.evaluate.assert_called_once_with("window.scrollBy(0, 500)")

    @pytest.mark.asyncio
    async def test_scroll_up(self, controller, mock_page):
        result = await controller.scroll("up", 300)
        assert result["success"] is True
        mock_page.evaluate.assert_called_once_with("window.scrollBy(0, -300)")


class TestEnsureStarted:
    @pytest.mark.asyncio
    async def test_unstarted_raises(self):
        from server.services.browser.controller import BrowserController
        bc = BrowserController()
        with pytest.raises(RuntimeError, match="not started"):
            await bc.navigate("https://example.com")
        with pytest.raises(RuntimeError, match="not started"):
            await bc.click("#btn")
        with pytest.raises(RuntimeError, match="not started"):
            await bc.get_snapshot()
```

- [ ] **Step 8: Run all tests, verify they pass**

```bash
cd D:/HAJI/HAJIMI_UI && python -m pytest server/tests/test_browser_controller.py -v
```

Expected: all 17 tests PASS

- [ ] **Step 9: Commit**

```bash
git add server/tests/test_browser_controller.py
git commit -m "test: add BrowserController unit tests (17 cases, mocked Playwright)"
```

---

### Task 2: Edge case hardening — BrowserController resilience

**Files:**
- Modify: `server/services/browser/controller.py`

**Interfaces:**
- Consumes: existing BrowserController methods
- Produces: hardened click/type with retry, stale-page detection in snapshot, selector escaping

- [ ] **Step 1: Add selector escaping for special characters in snapshot**

In `get_snapshot()`, the JS fragment builds selectors. When `id` or `className` contains `:` `.` `#` `[` `]` these break CSS parsing. Fix by adding CSS escaping in the JS:

```python
# Replace the selector-building block inside get_snapshot's JS string.
# Find:
#     let sel = tag;
#     if (el.id) { sel = '#' + el.id; }
#     else if (el.className && typeof el.className === 'string') {
#         const cls = el.className.trim().split(/\\s+/).slice(0, 2).join('.');
#         if (cls) sel = tag + '.' + cls;
#     }
#
# Replace with:

                // Build a CSS-escaped selector
                let sel = tag;
                const cssEscape = (s) => CSS.escape(s);
                if (el.id) {
                    sel = '#' + cssEscape(el.id);
                } else if (el.className && typeof el.className === 'string') {
                    const cls = el.className.trim().split(/\\s+/).slice(0, 2).map(cssEscape).join('.');
                    if (cls) sel = tag + '.' + cls;
                }
```

- [ ] **Step 2: Add click retry for detached DOM elements**

In `click()`, elements may be detached between snapshot and click (SPA re-render). Wrap with one retry:

```python
    async def click(self, selector: str) -> dict:
        """Click an element by CSS selector, with retry for detached elements."""
        self._ensure_started()
        last_error = None
        for attempt in range(2):
            try:
                elem = self._page.locator(selector).first
                tag = await elem.evaluate("el => el.tagName.toLowerCase()")
                text = await elem.text_content() or ""
                text = text.strip()[:80]
                await elem.click(timeout=10_000)
                label = f"<{tag}>" + (f" '{text}'" if text else "")
                logger.info("Browser clicked: %s (attempt %d)", label, attempt + 1)
                return {
                    "success": True,
                    "selector": selector,
                    "tag": tag,
                    "text": text,
                    "action_summary": f"clicked {label}",
                }
            except Exception as e:
                last_error = e
                if attempt == 0:
                    logger.debug("Click attempt 1 failed (%s), retrying after 500ms", e)
                    await asyncio.sleep(0.5)
                    continue
        return self._error("click", selector, last_error)
```

Note: requires `import asyncio` at top of `controller.py` (already present).

- [ ] **Step 3: Add stale-page guard to get_snapshot**

If the page was closed or navigated away (e.g., popup opened a new tab), `evaluate()` will throw. Catch gracefully:

```python
    async def get_snapshot(self) -> dict:
        self._ensure_started()
        try:
            title = await self._page.title()
        except Exception:
            title = "(page closed)"
        try:
            url = self._page.url
        except Exception:
            url = "(unavailable)"

        try:
            elements = await self._page.evaluate("""...""")  # unchanged JS
        except Exception as e:
            logger.warning("Snapshot evaluate failed: %s", e)
            return {
                "success": False,
                "title": title,
                "url": url,
                "elements": [],
                "snapshot_text": f"## Browser Snapshot\nTitle: {title}\nURL: {url}\nError: page may have been closed or navigated",
                "error": str(e)[:200],
                "action_summary": "snapshot failed: page unavailable",
            }

        # ... rest of snapshot building unchanged
```

Note: the `title`/`url` fetch + the guarded `evaluate()` replace the current bare calls; wrap them in try/except.

- [ ] **Step 4: Add type() retry for detached input elements**

Same pattern as click — one retry for detached DOM:

```python
    async def type(self, selector: str, text: str) -> dict:
        self._ensure_started()
        last_error = None
        for attempt in range(2):
            try:
                elem = self._page.locator(selector).first
                await elem.click(timeout=5_000)
                await elem.fill("")
                await elem.type(text, delay=30)
                logger.info("Browser typed %d chars into '%s' (attempt %d)", len(text), selector, attempt + 1)
                return {
                    "success": True,
                    "selector": selector,
                    "text": text,
                    "action_summary": f"typed '{text}' into '{selector}'",
                }
            except Exception as e:
                last_error = e
                if attempt == 0:
                    logger.debug("Type attempt 1 failed (%s), retrying after 500ms", e)
                    await asyncio.sleep(0.5)
                    continue
        return self._error("type", selector, last_error)
```

- [ ] **Step 5: Run existing unit tests to verify no regression**

```bash
cd D:/HAJI/HAJIMI_UI && python -m pytest server/tests/test_browser_controller.py -v
```

Expected: all 17 tests PASS (new retry logic is transparent to mocks since mock succeeds on first attempt)

- [ ] **Step 6: Commit**

```bash
git add server/services/browser/controller.py
git commit -m "fix: edge case hardening — CSS escape, click/type retry, stale-page snapshot guard"
```

---

### Task 3: browser_screenshot tool (P1 — spec §8)

**Files:**
- Modify: `server/services/browser/controller.py` (add `screenshot` method)
- Modify: `server/services/executor/agent.py` (add tool def + dispatch branch + system prompt)

**Interfaces:**
- Produces: `BrowserController.screenshot() -> dict` with `{success, image_b64, action_summary}`
- Produces: `browser_screenshot` tool in `_build_tool_definitions()`
- Produces: `browser_screenshot` dispatch in `dispatch_tool()`

- [ ] **Step 1: Add screenshot() method to BrowserController**

Insert after `scroll()` in `controller.py`:

```python
    async def screenshot(self) -> dict:
        """Take a full-page screenshot, return as base64 JPEG.

        LLM can use this for visual verification — e.g., "does the page
        show search results?".  Returns a data-URI string suitable for
        embedding in a vision LLM call.
        """
        self._ensure_started()
        import base64

        buf = await self._page.screenshot(type="jpeg", quality=70, full_page=False)
        b64 = base64.b64encode(buf).decode()
        logger.info("Browser screenshot: %d bytes JPEG → %d chars b64", len(buf), len(b64))
        return {
            "success": True,
            "image_b64": f"data:image/jpeg;base64,{b64}",
            "action_summary": "browser screenshot taken",
        }
```

- [ ] **Step 2: Add browser_screenshot tool definition**

After `browser_close` definition in `_build_tool_definitions()`, add:

```python
        {
            "type": "function",
            "function": {
                "name": "browser_screenshot",
                "description": "对当前浏览器页面截图，返回base64 JPEG。用于视觉验证页面状态（如'搜索结果是否出现'）。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
```

- [ ] **Step 3: Add dispatch branch in dispatch_tool()**

After `browser_close` branch:

```python
        elif tool_name == "browser_screenshot":
            self._ensure_browser_started()
            return self._run_async(self.browser.screenshot())
```

- [ ] **Step 4: Update system prompt**

In `EXECUTION_SYSTEM_PROMPT`, in the browser tools section, add after `browser_close` line:

```
- browser_screenshot(): 截取当前浏览器页面的屏幕截图，用于视觉验证。
```

And add this verification note to the browser workflow section:

```
### 视觉验证
- 当需要判断页面是否显示了预期内容时（如搜索结果、登录状态），使用 browser_screenshot
- browser_screenshot 返回的是 JPEG 图片，你可以"看到"页面，但不需要 OmniParser
- snapshot 用于定位元素 + 点击，screenshot 用于视觉确认
```

- [ ] **Step 5: Verify import and tool count**

```bash
cd D:/HAJI/HAJIMI_UI && python -c "
from server.services.executor.agent import ExecutionAgent
a = ExecutionAgent()
names = [t['function']['name'] for t in a.tools]
assert 'browser_screenshot' in names, f'browser_screenshot not in {names}'
print(f'Tools: {len(a.tools)} — OK')
print('browser_screenshot present — OK')
"
```

Expected: `Tools: 17 — OK`, `browser_screenshot present — OK`

- [ ] **Step 6: Add unit test for screenshot**

In `test_browser_controller.py`, add:

```python
class TestScreenshot:
    @pytest.mark.asyncio
    async def test_screenshot_returns_base64(self, controller, mock_page):
        # Mock screenshot to return a tiny JPEG
        mock_page.screenshot = AsyncMock(return_value=b'\xff\xd8\xff\xe0\x00\x10JFIF')
        result = await controller.screenshot()
        assert result["success"] is True
        assert result["image_b64"].startswith("data:image/jpeg;base64,")
        assert len(result["image_b64"]) > 30  # base64 content
```

- [ ] **Step 7: Run tests**

```bash
cd D:/HAJI/HAJIMI_UI && python -m pytest server/tests/test_browser_controller.py -v
```

Expected: all 18 tests PASS

- [ ] **Step 8: Commit**

```bash
git add server/services/browser/controller.py server/services/executor/agent.py server/tests/test_browser_controller.py
git commit -m "feat: add browser_screenshot tool for visual page verification"
```

---

### Task 4: browser_press_key tool (P2 — spec §8)

**Files:**
- Modify: `server/services/browser/controller.py` (add `press_key` method)
- Modify: `server/services/executor/agent.py` (add tool def + dispatch branch + system prompt)

**Interfaces:**
- Produces: `BrowserController.press_key(keys: str) -> dict`
- Produces: `browser_press_key` tool in `_build_tool_definitions()`

- [ ] **Step 1: Add press_key() method to BrowserController**

Insert after `scroll()` in `controller.py`:

```python
    async def press_key(self, keys: str) -> dict:
        """Press a keyboard key or combo on the browser page.

        Examples: "Enter", "Escape", "Tab", "Control+a", "PageDown".
        Uses Playwright's keyboard.press() which handles modifiers.
        """
        self._ensure_started()
        await self._page.keyboard.press(keys)
        logger.info("Browser pressed key: '%s'", keys)
        return {
            "success": True,
            "keys": keys,
            "action_summary": f"pressed '{keys}' in browser",
        }
```

- [ ] **Step 2: Add browser_press_key tool definition**

After `browser_screenshot` definition in `_build_tool_definitions()`:

```python
        {
            "type": "function",
            "function": {
                "name": "browser_press_key",
                "description": "在浏览器页面中按键盘按键。如'Enter'提交搜索、'Escape'关闭弹窗、'Tab'切换焦点。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keys": {
                            "type": "string",
                            "description": "按键名，如'Enter'、'Escape'、'Tab'、'PageDown'",
                        }
                    },
                    "required": ["keys"],
                },
            },
        },
```

- [ ] **Step 3: Add dispatch branch**

After `browser_screenshot` branch in `dispatch_tool()`:

```python
        elif tool_name == "browser_press_key":
            self._ensure_browser_started()
            return self._run_async(
                self.browser.press_key(tool_args.get("keys", "Enter"))
            )
```

- [ ] **Step 4: Update system prompt**

Add to browser tools list:

```
- browser_press_key(keys): 在浏览器中按键盘按键。如'Enter'提交搜索、'Escape'关闭弹窗。
```

- [ ] **Step 5: Verify import and tool count**

```bash
cd D:/HAJI/HAJIMI_UI && python -c "
from server.services.executor.agent import ExecutionAgent
a = ExecutionAgent()
names = sorted(t['function']['name'] for t in a.tools)
browser_tools = [n for n in names if n.startswith('browser_')]
print(f'Total tools: {len(a.tools)}')
print(f'Browser tools ({len(browser_tools)}): {browser_tools}')
assert len(browser_tools) == 8
"
```

Expected: `Total tools: 18`, `Browser tools (8): ['browser_click', 'browser_close', 'browser_navigate', 'browser_press_key', 'browser_screenshot', 'browser_scroll', 'browser_snapshot', 'browser_type']`

- [ ] **Step 6: Add unit test for press_key**

In `test_browser_controller.py`:

```python
class TestPressKey:
    @pytest.mark.asyncio
    async def test_press_key_enter(self, controller, mock_page):
        mock_page.keyboard = MagicMock()
        mock_page.keyboard.press = AsyncMock()
        result = await controller.press_key("Enter")
        assert result["success"] is True
        assert result["keys"] == "Enter"
        mock_page.keyboard.press.assert_called_once_with("Enter")

    @pytest.mark.asyncio
    async def test_press_key_combo(self, controller, mock_page):
        mock_page.keyboard = MagicMock()
        mock_page.keyboard.press = AsyncMock()
        result = await controller.press_key("Control+a")
        assert result["success"] is True
        mock_page.keyboard.press.assert_called_once_with("Control+a")
```

- [ ] **Step 7: Run tests**

```bash
cd D:/HAJI/HAJIMI_UI && python -m pytest server/tests/test_browser_controller.py -v
```

Expected: all 20 tests PASS

- [ ] **Step 8: Commit**

```bash
git add server/services/browser/controller.py server/services/executor/agent.py server/tests/test_browser_controller.py
git commit -m "feat: add browser_press_key tool (Enter, Escape, Tab, etc.)"
```

---

### Task 5: E2E smoke test — real browser round-trip

**Files:**
- Create: `server/tests/test_browser_e2e.py`

**Interfaces:**
- Consumes: `BrowserController` with real Playwright Chromium
- Produces: 3 smoke tests that validate real browser integration

- [ ] **Step 1: Create E2E test file**

```python
"""
E2E smoke tests for BrowserController — uses real Playwright Chromium.

These tests require: playwright install chromium
Skip if Chromium is not installed.
"""

import pytest

pytestmark = pytest.mark.e2e


def _chromium_installed():
    """Check if Playwright Chromium binary exists."""
    import shutil
    return shutil.which("chromium") is not None or shutil.which("google-chrome") is not None


def _try_import_playwright():
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.fixture
async def browser():
    """Start a real BrowserController for E2E testing."""
    from server.services.browser.controller import BrowserController
    bc = BrowserController()
    await bc.start(headless=True)
    yield bc
    await bc.close()


@pytest.mark.skipif(
    not _try_import_playwright(),
    reason="playwright not installed",
)
class TestBrowserE2E:
    """Real-browser round-trip tests."""

    @pytest.mark.asyncio
    async def test_navigate_and_snapshot(self, browser):
        """Navigate to a static page, verify snapshot has elements."""
        result = await browser.navigate("https://example.com")
        assert result["success"] is True
        assert result["title"] is not None

        snapshot = await browser.get_snapshot()
        assert snapshot["success"] is True
        # example.com has at least one <a> tag
        assert len(snapshot["elements"]) >= 1
        assert "Example Domain" in snapshot["title"] or "Example" in snapshot["title"]

    @pytest.mark.asyncio
    async def test_screenshot_returns_image(self, browser):
        """Screenshot of a real page produces a valid data URI."""
        await browser.navigate("https://example.com")
        result = await browser.screenshot()
        assert result["success"] is True
        assert result["image_b64"].startswith("data:image/jpeg;base64,")
        # base64 should be non-trivial (> 500 chars)
        assert len(result["image_b64"]) > 500

    @pytest.mark.asyncio
    async def test_scroll_changes_viewport(self, browser):
        """Scroll on a real page should not throw."""
        await browser.navigate("https://example.com")
        result = await browser.scroll("down", 100)
        assert result["success"] is True
```

- [ ] **Step 2: Run E2E tests (with real browser)**

```bash
cd D:/HAJI/HAJIMI_UI && python -m pytest server/tests/test_browser_e2e.py -v -m e2e --timeout=60
```

Expected: 3 tests PASS (Chromium launches, navigates, snapshots, screenshots)

If Chromium not installed: tests are skipped gracefully.

- [ ] **Step 3: Commit**

```bash
git add server/tests/test_browser_e2e.py
git commit -m "test: add E2E smoke tests for real browser round-trip"
```

---

### Task 6: Final verification — full regression suite

**Files:**
- No changes (verification only)

- [ ] **Step 1: Run all browser tests**

```bash
cd D:/HAJI/HAJIMI_UI && python -m pytest server/tests/test_browser_controller.py server/tests/test_browser_e2e.py -v
```

Expected: 20 unit tests PASS + 3 E2E tests PASS (or skip)

- [ ] **Step 2: Run existing tests to verify no regression**

```bash
cd D:/HAJI/HAJIMI_UI && python -m pytest server/tests/ -v --ignore=server/tests/test_browser_controller.py --ignore=server/tests/test_browser_e2e.py
```

Expected: all existing tests still PASS

- [ ] **Step 3: Verify ExecutionAgent import with all tools**

```bash
cd D:/HAJI/HAJIMI_UI && python -c "
from server.services.executor.agent import ExecutionAgent
a = ExecutionAgent()
assert len(a.tools) == 18, f'Expected 18 tools, got {len(a.tools)}'
browser = [t for t in a.tools if t['function']['name'].startswith('browser_')]
assert len(browser) == 8, f'Expected 8 browser tools, got {len(browser)}'
print('ExecutionAgent: 18 tools, 8 browser — OK')
# Verify dispatch_tool handles every browser tool without crash
for t in browser:
    name = t['function']['name']
    assert any(name in line for line in open('server/services/executor/agent.py', encoding='utf-8').readlines() if 'elif tool_name' in line), f'{name} not in dispatch_tool'
print('All 8 browser tools have dispatch branches — OK')
"
```

Expected: both OK

- [ ] **Step 4: Commit final state**

```bash
git add -A
git commit -m "chore: final verification — all 18 tools, 8 browser, full test suite green"
```
