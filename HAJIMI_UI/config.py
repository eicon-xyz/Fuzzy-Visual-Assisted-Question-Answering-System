import os

API_BASE_URL = os.environ.get("HAJIMI_API_URL", "http://localhost:8000")
DEMO_KEY = os.environ.get("HAJIMI_DEMO_KEY", "hajimi-demo-2026")
USE_MOCK_ONLY = os.environ.get("HAJIMI_MOCK_ONLY", "").lower() in ("1", "true", "yes")
FRAMED_WINDOW = os.environ.get("HAJIMI_FRAMED", "").lower() in ("1", "true", "yes")

MEDIUM_WIDTH = 420
MEDIUM_HEIGHT = 520
COMPACT_WIDTH = 320
COMPACT_HEIGHT = 52
