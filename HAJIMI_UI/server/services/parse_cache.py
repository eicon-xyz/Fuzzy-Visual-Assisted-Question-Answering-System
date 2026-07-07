"""In-memory parse result cache keyed by screen fingerprint (Demo TTL cache)."""
from __future__ import annotations

import time
from typing import Optional

from server.services.omniparser_client import ParseResult

_TTL_SEC = 30.0
_cache: dict[str, tuple[float, ParseResult]] = {}


def get_cached_parse(fingerprint: Optional[str]) -> Optional[ParseResult]:
    if not fingerprint:
        return None
    entry = _cache.get(fingerprint)
    if not entry:
        return None
    ts, result = entry
    if time.time() - ts > _TTL_SEC:
        _cache.pop(fingerprint, None)
        return None
    return result


def put_cached_parse(fingerprint: Optional[str], result: ParseResult) -> None:
    if fingerprint and result.elements:
        _cache[fingerprint] = (time.time(), result)
