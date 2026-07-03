"""Session state management layer."""

from .session_manager import SessionManager, STATUS_IDLE, STATUS_PLANNING, STATUS_EXECUTING, STATUS_EVALUATING, STATUS_WAITING_USER
from .session_schema import create_empty_session, normalize_plan, normalize_step, get_current_step, normalize_browser_execution, normalize_browser_substep

__all__ = [
    "SessionManager",
    "STATUS_IDLE",
    "STATUS_PLANNING",
    "STATUS_EXECUTING",
    "STATUS_EVALUATING",
    "STATUS_WAITING_USER",
    "create_empty_session",
    "normalize_plan",
    "normalize_step",
    "get_current_step",
    "normalize_browser_execution",
    "normalize_browser_substep",
]
