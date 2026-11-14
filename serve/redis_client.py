"""
Redis client — session cache and rate-limit state.
Singleton initialized at app startup.
"""

import os
import json
import redis.asyncio as aioredis

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialized. Call init_redis() at startup.")
    return _redis


async def init_redis():
    global _redis
    url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    _redis = aioredis.from_url(url, decode_responses=True)
    await _redis.ping()


async def close_redis():
    if _redis:
        await _redis.aclose()


async def cache_get(key: str) -> dict | None:
    r = get_redis()
    val = await r.get(key)
    if val is None:
        return None
    return json.loads(val)


async def cache_set(key: str, value: dict, ttl_seconds: int = 300):
    r = get_redis()
    await r.setex(key, ttl_seconds, json.dumps(value))


async def session_get(session_id: str) -> list[dict]:
    """Retrieve conversation history for a session."""
    r = get_redis()
    raw = await r.get(f'session:{session_id}')
    if raw is None:
        return []
    return json.loads(raw)


async def session_set(session_id: str, history: list[dict], ttl_seconds: int = 3600):
    """Persist conversation history for a session (1-hour TTL)."""
    r = get_redis()
    await r.setex(f'session:{session_id}', ttl_seconds, json.dumps(history))


async def feedback_push(user_id: str, query: str, response: str, rating: str):
    """Push a thumbs-down feedback event to a Redis list for human review."""
    r = get_redis()
    event = json.dumps({
        'user_id': user_id,
        'query': query,
        'response': response,
        'rating': rating,
    })
    await r.lpush('feedback:queue', event)
    await r.ltrim('feedback:queue', 0, 9999)  # keep last 10K
