"""Playwright browser launch — system Edge/Chrome first, bundled Chromium fallback."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BROWSER_LAUNCH_ERROR = (
    "Could not start a browser for L5 web automation. "
    "Install or update Microsoft Edge or Google Chrome, "
    "or set PLAYWRIGHT_CHANNEL=chromium and run: playwright install chromium"
)


def resolve_launch_channels() -> list[str | None]:
    """Channel names to try in order. None = Playwright bundled Chromium."""
    env = (os.environ.get("PLAYWRIGHT_CHANNEL") or "").strip().lower()
    if env == "chromium":
        return [None]
    if env in ("msedge", "chrome"):
        return [env, None]
    if env:
        return [env, None]
    return ["msedge", "chrome", None]


async def launch_chromium(
    playwright: Any,
    *,
    headless: bool,
    user_data_dir: str | None,
    launch_args: list[str],
) -> tuple[Any | None, Any | None, Any, str]:
    """Launch browser; return (browser, context, page, channel_label)."""
    last_err: Exception | None = None
    for channel in resolve_launch_channels():
        label = channel or "chromium"
        kwargs: dict[str, Any] = {
            "headless": headless,
            "args": launch_args,
        }
        if channel:
            kwargs["channel"] = channel
        try:
            if user_data_dir:
                Path(user_data_dir).mkdir(parents=True, exist_ok=True)
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    **kwargs,
                )
                pages = context.pages
                page = pages[0] if pages else await context.new_page()
                return None, context, page, label
            browser = await playwright.chromium.launch(**kwargs)
            page = await browser.new_page()
            return browser, None, page, label
        except Exception as exc:
            last_err = exc
            logger.warning(
                "Playwright launch failed (channel=%s): %s",
                label,
                str(exc)[:200],
            )
    raise RuntimeError(f"{BROWSER_LAUNCH_ERROR} Last error: {last_err}") from last_err


def browser_available_for_e2e() -> bool:
    """True if playwright is installed and some browser channel can launch."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False

    import importlib

    try:
        mod = importlib.import_module("playwright.sync_api")
    except Exception:
        return False

    try:
        with mod.sync_playwright() as pw:
            for channel in resolve_launch_channels():
                label = channel or "chromium"
                kwargs: dict[str, Any] = {"headless": True}
                if channel:
                    kwargs["channel"] = channel
                try:
                    browser = pw.chromium.launch(**kwargs)
                    browser.close()
                    logger.debug("E2E browser probe succeeded (channel=%s)", label)
                    return True
                except Exception:
                    continue
    except Exception:
        return False
    return False
