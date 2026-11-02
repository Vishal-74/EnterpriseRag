"""In-process sliding-window rate limiter.

A single API process is the deployment target. A shared store would be required
before running more than one instance.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from app.core.errors import RateLimitError


class SlidingWindowLimiter:
    """Count events per key inside a rolling time window."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def check(self, key: str, limit: int, window_seconds: float) -> None:
        """Record one hit or raise when the window is full."""
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            raise RateLimitError()
        hits.append(now)

    def reset(self) -> None:
        """Drop all counters. Used by tests."""
        self._hits.clear()
