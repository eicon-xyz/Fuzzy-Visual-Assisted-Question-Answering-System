"""L4 设置与 env 同步测试。"""
from core.env_sync import _settings_to_env_updates
from core.l4_settings import merge_l4_for_display


def test_env_sync_l4_keys():
    updates = _settings_to_env_updates(
        {
            "deployment_mode": "gpu_api",
            "llm_speed_mode": "fast",
            "demo_key": "k",
            "l4": {
                "planner_model": "deepseek-chat",
                "locator_model": "gpt-4o",
                "planner_use_vision": False,
                "strict_locate": True,
                "pipeline_enabled": True,
            },
        }
    )
    assert updates["ROUTING_MODE"] == "fast"
    assert updates["L4_PLANNER_MODEL"] == "deepseek-chat"
    assert updates["L4_LOCATOR_MODEL"] == "gpt-4o"
    assert updates["L4_STRICT_LOCATE"] == "true"
    assert updates["L4_PLANNER_USE_VISION"] == "false"


def test_merge_l4_user_overrides_env(monkeypatch):
    monkeypatch.setattr(
        "core.l4_settings.read_l4_from_server_env",
        lambda: {
            "planner_model": "from-env",
            "locator_model": "",
            "planner_use_vision": False,
            "strict_locate": True,
            "pipeline_enabled": True,
        },
    )
    merged = merge_l4_for_display({"locator_model": "gpt-4o"})
    assert merged["planner_model"] == "from-env"
    assert merged["locator_model"] == "gpt-4o"
