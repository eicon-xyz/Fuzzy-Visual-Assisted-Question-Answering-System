"""Write user_settings for local_vision mode: 无 OmniParser + L4 视觉 + UIA 执行。

替代已删除的 apply_local_gpu_settings.py：
  - deployment_mode = local_vision（env_sync 不再写 :9800 / 本地 :8002）
  - routing_mode     = fast（L4 视觉，跳过 L3/OmniParser）
  - llm 置空（保留 server/.env 中已有 LLM_API_KEY / DEEPSEEK_API_KEY）
随后调用 sync_backend_env 同步两端 .env（A端 8010 + L5 8011）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.defaults import DEFAULT_A_PORT, DEFAULT_DEMO_KEY
from core.user_settings import apply_user_settings, save_settings_fragment


def main() -> int:
    base = f"http://127.0.0.1:{DEFAULT_A_PORT}"
    merged = save_settings_fragment(
        {
            "deployment_mode": "local_vision",
            "a_end_url": base,
            "demo_key": DEFAULT_DEMO_KEY,
            "routing_mode": "fast",
            "llm_speed_mode": "fast",
            # 留空 = 使用 server/.env 中的现有 key/模型（deepseek-chat 已验证）
            "llm": {"base_url": "", "api_key": "", "model": "deepseek-chat"},
            # L4 规划/定位：文本 deepseek（无视觉 key 时不启用定位）
            "l4": {
                "planner_model": "deepseek-chat",
                "locator_model": "deepseek-chat",
                "planner_use_vision": False,
                "strict_locate": False,
                "pipeline_enabled": True,
            },
        }
    )
    apply_user_settings(merged)

    # 同步两端 .env（A端 8010 / L5 8011），写入 local_vision 相关项
    try:
        from core.env_sync import sync_backend_env

        l5_path, a_path = sync_backend_env(merged)
        print(f"[vision] synced L5 env -> {l5_path}")
        print(f"[vision] synced A-end env -> {a_path}")
    except Exception as exc:  # pragma: no cover
        print(f"[vision] WARN env sync failed: {exc}")

    from core.user_settings import _settings_path

    print(f"[vision] settings -> {_settings_path()}")
    print(
        "[vision] deployment_mode=local_vision  routing_mode=fast  "
        "(无 :9800 / 无本地 OmniParser)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
