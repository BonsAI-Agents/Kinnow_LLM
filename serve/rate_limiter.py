"""
Redis-backed refusal rate limiter, shared by every API replica.

The in-process limiter keeps one counter per pod, so with two replicas the effective limit is
twice as loose and depends on which pod the load balancer picks. This one keeps the counters in
Redis. Every key has a TTL, so client-supplied ids cannot grow storage without bound.

The counter is a fixed window that starts at a user's first off-topic query (INCR + EXPIRE), a
little coarser than the in-process sliding window. If Redis errors, it falls back to the
in-process limiter rather than failing the request.
"""

import sys

from guardrails.rate_limit import (
    InMemoryRateLimiter, OOS_BLOCK_THRESHOLD, OOS_WINDOW_SECONDS, RATE_LIMIT_DURATION,
)


class RedisRateLimiter:
    def __init__(self, redis_getter, fallback: InMemoryRateLimiter | None = None,
                 window_seconds: int = OOS_WINDOW_SECONDS, threshold: int = OOS_BLOCK_THRESHOLD,
                 cooldown_seconds: int = RATE_LIMIT_DURATION):
        self._redis = redis_getter
        self._fallback = fallback or InMemoryRateLimiter(window_seconds, threshold, cooldown_seconds)
        self.window = window_seconds
        self.threshold = threshold
        self.cooldown = cooldown_seconds

    @staticmethod
    def _count_key(user_id: str) -> str:
        return f'rl:oos:count:{user_id}'

    @staticmethod
    def _limited_key(user_id: str) -> str:
        return f'rl:oos:limited:{user_id}'

    async def is_limited(self, user_id: str) -> bool:
        try:
            return bool(await self._redis().exists(self._limited_key(user_id)))
        except Exception as exc:
            self._warn('is_limited', exc)
            return await self._fallback.is_limited(user_id)

    async def record(self, user_id: str) -> bool:
        try:
            r = self._redis()
            count_key = self._count_key(user_id)
            count = await r.incr(count_key)
            if count == 1:
                await r.expire(count_key, self.window)
            if count >= self.threshold:
                await r.setex(self._limited_key(user_id), self.cooldown, '1')
                await r.delete(count_key)
                return True
            return False
        except Exception as exc:
            self._warn('record', exc)
            return await self._fallback.record(user_id)

    @staticmethod
    def _warn(operation: str, exc: Exception) -> None:
        print(f'rate limiter: Redis {operation} failed ({exc}); using the in-process limiter', file=sys.stderr)
