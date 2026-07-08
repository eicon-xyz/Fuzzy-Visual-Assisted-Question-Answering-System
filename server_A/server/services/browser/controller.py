"""
Browser Controller — Playwright/CDP browser automation.

Provides DOM-level browser control as tools for the Execution Agent.
Unlike visual (OmniParser) interaction, DOM operations are precise:
- click(selector) hits the exact element, no coordinate drift
- get_snapshot() returns structured interactive elements, not raw HTML
- type(selector, text) fills inputs directly, no clipboard dance

Architecture:
    ExecutionAgent.dispatch_tool("browser_click", {"selector": "..."})
        → self.browser.click("...")
        → BrowserController._page.click("...")
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Snapshot size guard ──
MAX_SNAPSHOT_ELEMENTS = 80  # drop elements beyond this to avoid token explosion
MAX_TEXT_LENGTH = 120        # truncate visible text per element


class BrowserController:
    """Playwright-based browser automation controller.

    Lifecycle:
        browser = BrowserController()
        await browser.start()       # launches Chromium
        await browser.navigate("https://example.com")
        snapshot = await browser.get_snapshot()
        await browser.click("#btn")
        await browser.close()       # clean shutdown
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._page = None
        self._started = False
        self._context = None  # persistent browser context (when using user_data_dir)

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def start(self, headless: bool = False, user_data_dir: str | None = None) -> None:
        """Launch Chromium via Playwright.

        Args:
            headless: Run without UI. Default False so humans can watch.
            user_data_dir: Persistent profile directory for cookies/login state.
        """
        if self._started:
            logger.info("BrowserController already started, reusing")
            return

        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright not installed. Run: pip install playwright && playwright install chromium"
            ) from exc

        logger.info(
            "Starting Playwright Chromium (headless=%s, profile=%s)...",
            headless, user_data_dir or "(fresh)",
        )
        self._playwright = await async_playwright().start()

        launch_args = [
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-background-networking",
        ]

        if user_data_dir:
            from pathlib import Path
            Path(user_data_dir).mkdir(parents=True, exist_ok=True)
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=headless,
                args=launch_args,
            )
            self._browser = None
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
        else:
            self._browser = await self._playwright.chromium.launch(
                headless=headless,
                args=launch_args,
            )
            self._context = None
            self._page = await self._browser.new_page()

        self._started = True
        logger.info("BrowserController started successfully")

    async def close(self) -> None:
        """Close browser and stop Playwright. Safe to call multiple times."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.warning("Error closing browser: %s", e)
            self._browser = None

        if self._context:
            try:
                await self._context.close()
            except Exception as e:
                logger.warning("Error closing context: %s", e)
            self._context = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.warning("Error stopping playwright: %s", e)
            self._playwright = None

        self._page = None
        self._started = False
        logger.info("BrowserController closed")

    @property
    def is_started(self) -> bool:
        return self._started and self._page is not None

    # ── Page actions ─────────────────────────────────────────────────────

    async def navigate(self, url: str) -> dict:
        """Navigate to a URL with tiered wait_until fallback.

        Strategy:
          1. "commit"     — fastest: waits only for network response (≈0.3s)
          2. "load"       — waits for page load event (≈2s)
          3. "domcontentloaded" — most patient: waits for DOM complete + scripts (≈5s)

        Each tier has an independent timeout.  If one tier times out,
        we fall back to the next one rather than failing immediately.
        The final tier distributes its timeout across sub-phases
        (domcontentloaded → networkidle) for stubborn SPAs.
        """
        self._ensure_started()
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        logger.info("Browser navigating to: %s", url)

        tiers = [
            ("commit", 8_000),
            ("load", 15_000),
            ("domcontentloaded", 20_000),
        ]

        response = None
        last_error = None

        for i, (wait_until, timeout_ms) in enumerate(tiers):
            try:
                logger.info(
                    "Navigation tier %d/%d: wait_until=%s timeout=%dms",
                    i + 1, len(tiers), wait_until, timeout_ms,
                )
                response = await self._page.goto(
                    url, wait_until=wait_until, timeout=timeout_ms
                )
                break  # success — don't try slower tiers
            except Exception as e:
                last_error = e
                logger.warning(
                    "Navigation tier %d ('%s') failed: %s — falling back",
                    i + 1, wait_until, str(e)[:120],
                )
                continue  # try next tier

        # All tiers exhausted — last resort: networkidle with generous timeout
        if response is None:
            logger.warning(
                "All navigation tiers failed (%s); trying networkidle as last resort",
                last_error,
            )
            try:
                response = await self._page.goto(
                    url, wait_until="networkidle", timeout=45_000
                )
            except Exception as e:
                last_error = e
                logger.error("Last-resort networkidle navigation also failed: %s", e)

        # If still nothing, check if the page partially loaded anyway
        if response is None:
            current_url = self._page.url
            if current_url != "about:blank" and url.rstrip("/") in current_url:
                logger.info(
                    "Navigation appears to have partially succeeded: %s", current_url
                )
                title = await self._page.title()
                return {
                    "success": True,
                    "url": current_url,
                    "title": title,
                    "status": None,
                    "wait_until": "partial",
                    "warning": f"Page may not be fully loaded: {last_error}",
                    "action_summary": f"partially navigated to '{title}' ({current_url})",
                }
            return {
                "success": False,
                "url": url,
                "error": f"Navigation failed after all tiers: {last_error}",
                "action_summary": f"navigation to {url} failed",
            }

        title = await self._page.title()
        return {
            "success": True,
            "url": self._page.url,
            "title": title,
            "status": response.status if response else None,
            "wait_until": wait_until,
            "action_summary": f"navigated to '{title}' ({url})",
        }

    async def click(self, selector: str) -> dict:
        """Click an element by CSS selector or text, with retry for detached elements.

        Supports:
            - CSS: "#id", ".class", "button", "a[href='/login']"
            - Text: "text=登录" or ":text('Login')"
            - Role: "button[name='submit']"

        Uses force=True to bypass Playwright actionability checks
        (visibility, obscured, etc.) — matches the expectation of
        "click this element" even when off-screen or covered.

        Retries once after 500ms if the element is detached between snapshot and click.
        """
        self._ensure_started()
        last_error = None
        for attempt in range(2):
            try:
                elem = self._page.locator(selector).first
                tag = await elem.evaluate("el => el.tagName.toLowerCase()")
                text = await elem.text_content() or ""
                text = text.strip()[:80]
                await elem.click(timeout=10_000, force=True)
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

    async def type(self, selector: str, text: str) -> dict:
        """Type text into an input/textarea element, with retry for detached elements.

        Uses JavaScript to set value directly (bypasses actionability
        checks), then dispatches input/change events so frameworks
        like React/Angular detect the change.

        Retries once after 500ms if the element is detached.
        """
        self._ensure_started()
        last_error = None
        for attempt in range(2):
            try:
                elem = self._page.locator(selector).first
                # Set value via JS to bypass visibility/stable checks
                escaped = text.replace("\\", "\\\\").replace("'", "\\'")
                await elem.evaluate(
                    f"""el => {{
                        el.value = '{escaped}';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}"""
                )
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

    async def get_snapshot(self) -> dict:
        """Return a compact DOM snapshot listing interactive elements.

        NOT raw HTML — only interactive elements (links, buttons, inputs, selects)
        with their selector, tag, visible text, and input state.
        Capped at MAX_SNAPSHOT_ELEMENTS to prevent token explosion.
        """
        self._ensure_started()
        try:
            title = await self._page.title()
        except Exception:
            title = "(page closed)"
        try:
            url = self._page.url
        except Exception:
            url = "(unavailable)"

        # Extract interactive elements via JS
        try:
            elements = await self._page.evaluate("""() => {
            const interactive = 'a,button,input,select,textarea,[role="button"],[role="link"],[role="textbox"],[role="combobox"],[role="searchbox"],[role="checkbox"],[role="radio"],[contenteditable="true"],[onclick]';
            const els = document.querySelectorAll(interactive);
            const results = [];
            for (const el of els) {
                if (results.length >= %d) break;

                const rect = el.getBoundingClientRect();
                // Skip off-screen / invisible elements
                if (rect.width === 0 || rect.height === 0) continue;
                if (rect.bottom < 0 || rect.top > window.innerHeight) continue;

                const tag = el.tagName.toLowerCase();
                let text = '';
                if (tag === 'input' || tag === 'textarea') {
                    text = el.value || el.placeholder || el.getAttribute('aria-label') || el.name || '';
                } else {
                    text = (el.textContent || '').trim().replace(/\\s+/g, ' ');
                    if (text.length > %d) text = text.slice(0, %d) + '…';
                }
                // Only include elements with visible text or special attributes
                if (!text && tag !== 'input' && tag !== 'textarea' && tag !== 'select' && tag !== 'button') continue;

                // Build a CSS-escaped selector
                const cssEscape = (s) => CSS.escape(s);
                let sel = tag;
                if (el.id) { sel = '#' + cssEscape(el.id); }
                else if (el.className && typeof el.className === 'string') {
                    const cls = el.className.trim().split(/\\s+/).slice(0, 2).map(cssEscape).join('.');
                    if (cls) sel = tag + '.' + cls;
                }

                results.push({
                    tag: tag,
                    text: text,
                    selector: sel,
                    href: tag === 'a' ? (el.href || '') : '',
                    type: el.type || '',
                    name: el.name || '',
                    id: el.id || '',
                });
            }
            return results;
        }""" % (MAX_SNAPSHOT_ELEMENTS, MAX_TEXT_LENGTH, MAX_TEXT_LENGTH))
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

        # Build compact text representation
        lines = [
            f"## Browser Snapshot",
            f"Title: {title}",
            f"URL: {url}",
            f"Interactive elements ({len(elements)} shown):",
            "",
        ]
        for i, el in enumerate(elements):
            tag_label = el["tag"]
            if el.get("type"):
                tag_label += f"[type={el['type']}]"
            text_str = el["text"] or "(no text)"
            sel_str = el["selector"]
            href = f" → {el['href']}" if el.get("href") else ""
            lines.append(f"  {i}  <{tag_label}> \"{text_str}\"  [{sel_str}]{href}")

        snapshot_text = "\n".join(lines)
        logger.info("Browser snapshot: %d elements, %d chars", len(elements), len(snapshot_text))
        return {
            "success": True,
            "title": title,
            "url": url,
            "elements": elements,
            "snapshot_text": snapshot_text,
            "action_summary": f"snapshot: {len(elements)} elements on '{title}'",
        }

    async def scroll(self, direction: str, amount: int = 300) -> dict:
        """Scroll the page up or down by pixel amount."""
        self._ensure_started()
        delta = amount if direction == "down" else -amount
        await self._page.evaluate(f"window.scrollBy(0, {delta})")
        logger.info("Browser scrolled %s %dpx", direction, amount)
        return {
            "success": True,
            "direction": direction,
            "amount": amount,
            "action_summary": f"scrolled {direction} {amount}px",
        }

    async def screenshot(self) -> dict:
        """Take a viewport screenshot, return as base64 JPEG.

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

    # ── Helpers ───────────────────────────────────────────────────────────

    def _ensure_started(self) -> None:
        if not self._started or not self._page:
            raise RuntimeError(
                "BrowserController not started. Call await browser.start() first."
            )

    @staticmethod
    def _error(action: str, selector: str, exc: Exception) -> dict:
        msg = str(exc)[:200]
        logger.warning("Browser %s('%s') failed: %s", action, selector, msg)
        return {
            "success": False,
            "action": action,
            "selector": selector,
            "error": msg,
            "action_summary": f"{action} failed: {msg}",
        }
