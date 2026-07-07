"""
Browser task routing — detect web/browser intents and return DOM-oriented plans
without OmniParser visual grounding (OpenGuider browser-use plugin pattern).
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from server.config import settings

_BROWSER_KEYWORDS = [
    "浏览器", "网页", "网站", "google", "百度", "bing", "搜索网页",
    "打开网址", "访问", "http", "https", "www.", ".com", ".cn",
    "登录网站", "填表", "表单", "checkout", "sign in", "sign up",
    "browser", "website", "web page", "online",
]

_BROWSER_PATTERNS = [
    re.compile(r"在.{0,12}(浏览器|网页|网站)", re.I),
    re.compile(r"(搜索|查找).{0,8}(网页|网上|在线)", re.I),
    re.compile(r"https?://", re.I),
    re.compile(r"www\.\w+", re.I),
]


def is_browser_task(query: str) -> bool:
    q = (query or "").lower()
    if any(kw.lower() in q for kw in _BROWSER_KEYWORDS):
        return True
    return any(p.search(query or "") for p in _BROWSER_PATTERNS)


def browser_route_available() -> bool:
    return bool(getattr(settings, "BROWSER_PLUGIN_ENABLED", True))


def generate_browser_plan(query: str) -> Tuple[List[dict], Optional[dict], dict]:
    """
    Return a browser-oriented step plan (no OmniParser).
    Steps use interaction=browser for B-end / future Playwright hook.
    """
    steps = [
        {
            "action": "打开浏览器",
            "description": "打开默认浏览器（Chrome / Edge），准备访问目标网站。",
            "target_element_id": "",
            "interaction": "browser",
        },
        {
            "action": "导航到目标页面",
            "description": f"在地址栏输入目标网址或搜索关键词，完成：{query}",
            "target_element_id": "",
            "interaction": "browser",
        },
        {
            "action": "完成网页操作",
            "description": "根据页面提示继续操作；涉及登录或支付时请手动确认。",
            "target_element_id": "",
            "interaction": "browser",
        },
    ]
    meta = {
        "llm_called": False,
        "parse_skipped": True,
        "browser_plugin": True,
        "route": "BROWSER",
    }
    return steps, {"browser_automation": True, "original_query": query}, meta
