"""
Intent router — decides whether a task goes to a plugin or guide mode.

Python equivalent of OpenGuider's core/intent-router.js.

Uses a lightweight LLM call (or fast keyword heuristic) to classify
whether the user's request should be handled by:
- Guide mode (default): step-by-step screen annotations
- Browser plugin: web automation via Playwright
- CLI plugin: terminal command execution
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Quick heuristic patterns ──────────────────────────────────────────────────

BROWSER_KEYWORDS = [
    r"\b(?:打开|访问|浏览|登录|注册|填写|提交|下载|上传)\b.*\b(?:网页|网站|页面|网址|链接|浏览器)\b",
    r"\b(?:浏览器|网页|网站|在线|登录.*账号|注册.*账号)\b",
    r"\b(?:open|visit|browse|navigate|go to|login|sign in|register|fill|submit)\b.*\b(?:website|page|url|link|web|browser|http)\b",
    r"\b(?:淘宝|京东|微博|知乎|百度|谷歌|github|gmail|outlook)\b",
    r"\b(?:网购|下单|比价|查.*快递|订.*票)\b",
]

CLI_KEYWORDS = [
    r"\b(?:运行|执行|命令行|终端|cmd|powershell|bash|shell|脚本|script)\b",
    r"\b(?:run|execute|terminal|command line|shell)\b.*\b(?:command|script|pip|npm|git|docker)\b",
    r"\b(?:安装|卸载|更新)\b.*\b(?:包|依赖|软件|驱动)\b",
    r"\b(?:pip install|npm install|apt get|brew install|git clone|git push)\b",
]

GENERAL_QA_PATTERNS = [
    r"^(?:what|who|when|where|why|how|什么是|谁|什么时候|哪里|为什么|怎么|如何|解释|说明|介绍)",
    r"\b(?:定义|含义|概念|原理|历史|背景)\b",
    r"\?\s*$",  # Ends with question mark
]


# ── Route result ──────────────────────────────────────────────────────────────


class RouteResult:
    """Result of intent routing."""
    def __init__(
        self,
        plugin_id: Optional[str] = None,
        goal: str = "",
        trust: str = "balanced",
        reason: str = "",
    ):
        self.plugin_id = plugin_id  # None = guide mode, "browser", "cli", etc.
        self.goal = goal
        self.trust = trust
        self.reason = reason

    @property
    def is_guide_mode(self) -> bool:
        return self.plugin_id is None

    def to_dict(self) -> dict:
        return {
            "plugin_id": self.plugin_id,
            "goal": self.goal,
            "trust": self.trust,
            "reason": self.reason,
        }


# ── Fast routing ──────────────────────────────────────────────────────────────


def route_intent_fast(text: str) -> RouteResult:
    """Fast keyword-based routing, no LLM call.

    Maps to OpenGuider's intent-router.js heuristic checks.

    Returns:
        RouteResult with plugin_id or None for guide mode
    """
    if not text:
        return RouteResult(plugin_id=None, reason="empty query")

    # Check general QA (always guide mode, no plugin)
    for pattern in GENERAL_QA_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return RouteResult(
                plugin_id=None,
                goal=text,
                trust="balanced",
                reason="general Q&A - guide mode",
            )

    # Check browser tasks
    for pattern in BROWSER_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return RouteResult(
                plugin_id="browser",
                goal=text,
                trust="balanced",
                reason="browser keyword match",
            )

    # Check CLI tasks
    for pattern in CLI_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return RouteResult(
                plugin_id="cli",
                goal=text,
                trust="paranoid",
                reason="CLI keyword match",
            )

    # Default: guide mode
    return RouteResult(plugin_id=None, goal=text, trust="balanced", reason="default guide mode")


# ── LLM-based routing ────────────────────────────────────────────────────────


async def route_intent_llm(
    text: str,
    image_count: int = 0,
    available_plugins: Optional[List[str]] = None,
    settings: Any = None,
    signal: Any = None,
) -> RouteResult:
    """Route intent using a lightweight LLM call.

    Maps to OpenGuider's intent-router.js route().

    Falls back to route_intent_fast() if LLM is unavailable.
    """
    if not text:
        return route_intent_fast(text)

    available_plugins = available_plugins or []

    try:
        from server_v2.services.llm.client import call_llm

        system_prompt = """You are a task router. Classify the user's request into one of these categories:
- "guide": Desktop guidance — showing where to click, step-by-step (default)
- "browser": Web browser automation — opening websites, filling forms, online tasks
- "cli": Command-line tasks — running terminal commands, scripts
- "none": General Q&A, no action needed

Return ONLY a JSON object:
{"plugin": "guide", "goal": "restated goal", "trust": "balanced"}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]

        result = await call_llm(
            messages=messages,
            settings=settings,
            max_tokens=200,
            temperature=0.0,
        )

        # Parse JSON from response
        import json
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            # Try to find JSON in the response
            match = re.search(r"\{[^}]+\}", result)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError("No JSON in LLM response")

        plugin_id = data.get("plugin", "guide")
        if plugin_id == "none" or plugin_id == "guide":
            plugin_id = None
        elif plugin_id not in available_plugins:
            plugin_id = None

        return RouteResult(
            plugin_id=plugin_id,
            goal=data.get("goal", text),
            trust=data.get("trust", "balanced"),
            reason=f"LLM routed to {plugin_id or 'guide'}",
        )

    except Exception as e:
        logger.warning(f"LLM intent routing failed: {e}. Using fast routing.")
        return route_intent_fast(text)


# ── Main routing function ─────────────────────────────────────────────────────


async def route(
    text: str,
    images: Optional[List[Dict]] = None,
    available_plugins: Optional[List[str]] = None,
    settings: Any = None,
    signal: Any = None,
    use_llm: bool = False,
) -> RouteResult:
    """Route a user request to the appropriate execution mode.

    Maps to OpenGuider's intent-router.js exported route().

    Args:
        text: User's query text
        images: Optional list of screenshot dicts (not used in routing)
        available_plugins: List of available plugin IDs
        settings: LLM settings for LLM-based routing
        signal: Cancellation signal
        use_llm: If True, use LLM-based routing (slower but more accurate)

    Returns:
        RouteResult indicating which plugin (or None for guide mode)
    """
    if use_llm and settings:
        return await route_intent_llm(
            text=text,
            image_count=len(images) if images else 0,
            available_plugins=available_plugins,
            settings=settings,
            signal=signal,
        )
    else:
        return route_intent_fast(text)
