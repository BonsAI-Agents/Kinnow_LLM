"""
Per-user request rate limit (plan sections 11a and 17 Phase 1): 20 requests a minute and 500 a day
per user, answered with 429 and a Retry-After header.

This is separate from the off-topic limiter in serve/rate_limiter.py, which only counts
out-of-scope questions. Counters live in Redis so every replica enforces the same limit, and
they are scoped by API key as well as user id, so one client's user ids cannot collide with
another's. Each key has a TTL.

A rejected request does not count towards the daily quota. If Redis errors, requests are allowed
(fail open) and a warning is printed: the chat route needs Redis for sessions anyway.
"""

import os
import sys
import time
from dataclasses import dataclass

DEFAULT_PER_MINUTE = 20
DEFAULT_PER_DAY = 500


@dataclass
class RateLimitResult:
    allowed: bool
    scope: str | None = None          # 'minute' or 'day' when not allowed
    retry_after: int = 0              # seconds until the limit resets


class RequestRateLimiter:
    def __init__(self, redis_getter, per_minute: int | None = None, per_day: int | None = None):
        self._redis = redis_getter
        self.per_minute = per_minute if per_minute is not None else int(os.getenv('RATE_LIMIT_PER_MINUTE', DEFAULT_PER_MINUTE))
        self.per_day = per_day if per_day is not None else int(os.getenv('RATE_LIMIT_PER_DAY', DEFAULT_PER_DAY))

    async def check(self, owner: str, user_id: str, now: float | None = None) -> RateLimitResult:
        now = time.time() if now is None else now
        minute_key = f'rl:req:{owner}:{user_id}:min:{int(now // 60)}'
        day_key = f'rl:req:{owner}:{user_id}:day:{time.strftime("%Y%m%d", time.gmtime(now))}'
        try:
            r = self._redis()
            minute_count = await r.incr(minute_key)
            if minute_count == 1:
                await r.expire(minute_key, 60)
            if minute_count > self.per_minute:
                return RateLimitResult(False, 'minute', max(1, int(60 - now % 60)))

            day_count = await r.incr(day_key)
            if day_count == 1:
                await r.expire(day_key, 86400)
            if day_count > self.per_day:
                return RateLimitResult(False, 'day', max(1, int(86400 - now % 86400)))
            return RateLimitResult(True)
        except Exception as exc:
            print(f'request rate limiter: Redis failed ({exc}); allowing the request', file=sys.stderr)
            return RateLimitResult(True)


_limiter: RequestRateLimiter | None = None


def set_request_limiter(limiter: RequestRateLimiter | None) -> None:
    global _limiter
    _limiter = limiter


def get_request_limiter() -> RequestRateLimiter:
    if _limiter is None:
        raise RuntimeError("Request rate limiter not initialized")
    return _limiter
