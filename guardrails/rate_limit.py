"""
Refusal anomaly tracker (plan section 21f): rate-limit users who repeatedly probe off-topic topics.

A limiter has two async methods, so the pipeline can use an in-process implementation or the
Redis-backed one in serve/rate_limiter.py without caring which:

    await limiter.is_limited(user_id) -> bool
    await limiter.record(user_id)     -> bool   # one more off-topic event; True if it tripped the limit
"""

import time

OOS_WINDOW_SECONDS = 300        # 5-minute window
OOS_BLOCK_THRESHOLD = 10        # limit after 10 off-topic queries in the window
RATE_LIMIT_DURATION = 600       # 10-minute cooldown once limited
MAX_TRACKED_USERS = 10_000      # in-memory bound: ids are client-supplied, so memory must not grow with them


class InMemoryRateLimiter:
    """Per-process limiter. Bounded; used by default and as the fallback when Redis is unavailable."""

    def __init__(self, window_seconds: int = OOS_WINDOW_SECONDS, threshold: int = OOS_BLOCK_THRESHOLD,
                 cooldown_seconds: int = RATE_LIMIT_DURATION, max_tracked: int = MAX_TRACKED_USERS):
        self.window = window_seconds
        self.threshold = threshold
        self.cooldown = cooldown_seconds
        self.max_tracked = max_tracked
        self._events: dict[str, list[float]] = {}
        self._limited_until: dict[str, float] = {}

    async def is_limited(self, user_id: str) -> bool:
        until = self._limited_until.get(user_id)
        if until is None:
            return False
        if time.time() < until:
            return True
        del self._limited_until[user_id]        # cooldown over: forget it
        return False

    async def record(self, user_id: str) -> bool:
        now = time.time()
        events = [t for t in self._events.get(user_id, []) if now - t <= self.window]
        events.append(now)
        tripped = len(events) >= self.threshold
        if tripped:
            self._limited_until[user_id] = now + self.cooldown
            self._events.pop(user_id, None)
        else:
            self._events[user_id] = events
        self._enforce_bounds(now)
        return tripped

    def _enforce_bounds(self, now: float) -> None:
        if len(self._events) > self.max_tracked:
            for user in [u for u, ev in self._events.items() if not ev or now - ev[-1] > self.window]:
                del self._events[user]
            while len(self._events) > self.max_tracked:        # still too many: drop the oldest ids
                self._events.pop(next(iter(self._events)))
        if len(self._limited_until) > self.max_tracked:
            for user in [u for u, t in self._limited_until.items() if t <= now]:
                del self._limited_until[user]
            while len(self._limited_until) > self.max_tracked:
                self._limited_until.pop(next(iter(self._limited_until)))

    def reset(self) -> None:
        """Clear all state (tests)."""
        self._events.clear()
        self._limited_until.clear()
