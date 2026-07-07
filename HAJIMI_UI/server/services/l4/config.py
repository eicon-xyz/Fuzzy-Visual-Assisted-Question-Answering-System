"""L4 专用配置（读取 server/.env，不修改 L3/OmniParser 配置项）。"""
from __future__ import annotations

from dataclasses import dataclass

from server.config import settings


@dataclass(frozen=True)
class L4Settings:
    planner_model: str
    locator_model: str
    planner_use_vision: bool
    pipeline_enabled: bool
    strict_locate: bool
    screen_hints: bool
    planner_max_tokens: int
    locator_max_tokens: int
    planner_timeout: float
    locator_timeout: float


def get_l4_settings() -> L4Settings:
    pk = settings.LLM_API_KEY or settings.DEEPSEEK_API_KEY or ""
    default_text = settings.DEEPSEEK_MODEL or settings.LLM_MODEL or "deepseek-chat"
    default_vision = settings.LLM_MODEL or default_text

    return L4Settings(
        planner_model=settings.L4_PLANNER_MODEL or default_text,
        locator_model=settings.L4_LOCATOR_MODEL or default_vision,
        planner_use_vision=settings.L4_PLANNER_USE_VISION.lower()
        in ("1", "true", "yes"),
        pipeline_enabled=settings.L4_PIPELINE_ENABLED.lower()
        not in ("0", "false", "no"),
        strict_locate=settings.L4_STRICT_LOCATE.lower()
        not in ("0", "false", "no"),
        screen_hints=settings.L4_SCREEN_HINTS.lower()
        not in ("0", "false", "no"),
        planner_max_tokens=settings.L4_PLANNER_MAX_TOKENS,
        locator_max_tokens=settings.L4_LOCATOR_MAX_TOKENS,
        planner_timeout=settings.L4_PLANNER_TIMEOUT,
        locator_timeout=float(
            settings.L4_LOCATOR_TIMEOUT or settings.LLM_VISION_ATTEMPT_TIMEOUT or 45
        ),
    )


def l4_api_credentials() -> tuple[str, str]:
    api_key = settings.LLM_API_KEY or settings.DEEPSEEK_API_KEY or ""
    base_url = (settings.LLM_BASE_URL or settings.DEEPSEEK_BASE_URL or "").rstrip("/")
    return api_key, base_url
