"""
Trust manager — controls automatic step approval based on risk level.

Python equivalent of OpenGuider's core/trust-manager.js.

Three presets determine whether a step can auto-execute without
waiting for explicit user confirmation.
"""

from typing import Optional, Any


# ── Trust presets ─────────────────────────────────────────────────────────────

TRUST_PRESETS = {
    "paranoid": {
        "auto_approve_below": 0,  # Never auto-approve
        "description": "每步都需要确认",
    },
    "balanced": {
        "auto_approve_below": 3,  # Auto-approve risk 1-2
        "description": "低风险步骤自动执行",
    },
    "autopilot": {
        "auto_approve_below": 6,  # Auto-approve all (risk 1-5)
        "description": "全自动执行",
    },
}

VALID_TRUST_LEVELS = set(TRUST_PRESETS.keys())


def should_auto_approve(
    risk_score: int = 3,
    trust_level: str = "balanced",
    plugin_requires_review: bool = False,
) -> bool:
    """Determine if a step should auto-execute without user confirmation.

    Maps to OpenGuider's trust-manager.js shouldAutoApprove().

    Args:
        risk_score: Step risk score (1-5, or higher for plugin-specific risks)
        trust_level: One of 'paranoid', 'balanced', 'autopilot'
        plugin_requires_review: If the plugin explicitly requests human review

    Returns:
        True if the step can auto-execute
    """
    # Plugin override: if plugin requires review, always wait
    if plugin_requires_review:
        return False

    # Validate trust level
    if trust_level not in TRUST_PRESETS:
        trust_level = "balanced"

    preset = TRUST_PRESETS[trust_level]
    threshold = preset["auto_approve_below"]

    return risk_score < threshold


def get_trust_preset(trust_level: str) -> Optional[dict]:
    """Get the full preset config for a trust level."""
    return TRUST_PRESETS.get(trust_level)


def validate_trust_level(level: str) -> str:
    """Normalize a trust level string, defaulting to 'balanced'."""
    level = level.lower().strip() if level else "balanced"
    if level not in VALID_TRUST_LEVELS:
        return "balanced"
    return level
