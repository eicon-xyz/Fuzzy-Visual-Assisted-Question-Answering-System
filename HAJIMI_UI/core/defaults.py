"""Shared default URLs/ports for B-end and A-end (single source of truth).

Bat scripts cannot import this module; keep scripts\\start_*.bat in sync manually.
See docs/P1-可移植性改动与使用指南.md.
"""

DEFAULT_A_HOST = "127.0.0.1"
DEFAULT_A_PORT = 8010
DEFAULT_A_URL = f"http://{DEFAULT_A_HOST}:{DEFAULT_A_PORT}"
DEFAULT_OMNI_LOCAL_URL = "http://127.0.0.1:8002"
DEFAULT_OMNI_GPU_URL = ""  # campus GPU: set in server/.env or settings page
DEFAULT_DEMO_KEY = "hajimi-demo-2026"
