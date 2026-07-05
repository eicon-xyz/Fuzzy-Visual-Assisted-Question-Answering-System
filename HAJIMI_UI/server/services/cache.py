"""
Screenshot cache — TTL-based caching with concurrent call deduplication.

Matches OpenGuider's src/screenshot.js caching pattern.
"""
from __future__ import annotations
import time
import hashlib
import threading
from typing import Optional


class ScreenshotCache:
    """Thread-safe screenshot cache with 900ms TTL (by default).

    In multi-step tasks the same screenshot is often reused immediately.
    This avoids redundant base64 decode/encode cycles.
    """

    def __init__(self, ttl_ms: int = 900):
        self._ttl_ms = ttl_ms
        self._cache: dict[str, tuple[float, str]] = {}  # fingerprint → (timestamp, image_b64)
        self._lock = threading.Lock()
        self._inflight: dict[str, threading.Event] = {}  # Dedup in-flight requests

    def _fingerprint(self, image_base64: str) -> str:
        """Compute a quick SHA-256 fingerprint from the image data."""
        if "," in image_base64 and image_base64.startswith("data:"):
            payload = image_base64.split(",", 1)[1]
        else:
            payload = image_base64
        # Use first 4KB for fast fingerprinting
        return hashlib.sha256(payload[:4096].encode()).hexdigest()

    def get_or_store(self, image_base64: Optional[str]) -> Optional[str]:
        """Return cached image if valid, otherwise store and return new image.

        Args:
            image_base64: New screenshot (None = try to get cached)

        Returns:
            Cached or new image, or None if no cache available
        """
        if not image_base64:
            # Try to return the most recently cached image
            with self._lock:
                if not self._cache:
                    return None
                # Return the newest entry
                newest_key = max(self._cache, key=lambda k: self._cache[k][0])
                ts, img = self._cache[newest_key]
                now_ms = time.time() * 1000
                if now_ms - ts <= self._ttl_ms:
                    return img
                return None

        # Store new image
        fp = self._fingerprint(image_base64)
        now_ms = time.time() * 1000
        with self._lock:
            self._cache[fp] = (now_ms, image_base64)
            # Clean old entries
            expired = [k for k, (ts, _) in self._cache.items() if now_ms - ts > self._ttl_ms * 5]
            for k in expired:
                del self._cache[k]

        return image_base64

    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._inflight.clear()


# Global singleton
screenshot_cache = ScreenshotCache()
