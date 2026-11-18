"""Unit tests for serve/redis_client.py using an in-memory fake."""

import json

import pytest

from serve import redis_client
from tests.conftest import FakeRedis


class TestInitialisation:
    def test_get_redis_before_init_raises(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            redis_client.get_redis()

    async def test_init_redis_connects_with_env_url_and_pings(self, monkeypatch):
        fake = FakeRedis()
        seen = {}

        def fake_from_url(url, decode_responses):
            seen["url"] = url
            seen["decode"] = decode_responses
            return fake

        monkeypatch.setenv("REDIS_URL", "redis://example:6380/2")
        monkeypatch.setattr(redis_client.aioredis, "from_url", fake_from_url)
        await redis_client.init_redis()
        assert seen == {"url": "redis://example:6380/2", "decode": True}
        assert redis_client.get_redis() is fake

    async def test_init_redis_fails_loudly_when_ping_fails(self, monkeypatch):
        fake = FakeRedis()
        fake.fail_ping = True
        monkeypatch.setattr(redis_client.aioredis, "from_url", lambda url, decode_responses: fake)
        with pytest.raises(ConnectionError):
            await redis_client.init_redis()

    async def test_close_redis_closes_the_connection(self, fake_redis):
        await redis_client.close_redis()
        assert fake_redis.closed is True

    async def test_close_redis_without_connection_is_a_noop(self):
        await redis_client.close_redis()


class TestSessions:
    async def test_unknown_session_has_empty_history(self, fake_redis):
        assert await redis_client.session_get("nobody") == []

    async def test_session_roundtrip(self, fake_redis):
        history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        await redis_client.session_set("s1", history)
        assert await redis_client.session_get("s1") == history

    async def test_sessions_are_isolated_and_expire_after_an_hour(self, fake_redis):
        await redis_client.session_set("a", [{"role": "user", "content": "A"}])
        await redis_client.session_set("b", [{"role": "user", "content": "B"}])
        assert (await redis_client.session_get("a"))[0]["content"] == "A"
        assert (await redis_client.session_get("b"))[0]["content"] == "B"
        assert fake_redis.ttls["session:a"] == 3600

    async def test_custom_ttl_is_respected(self, fake_redis):
        await redis_client.session_set("a", [], ttl_seconds=60)
        assert fake_redis.ttls["session:a"] == 60

    async def test_hindi_content_survives_serialisation(self, fake_redis):
        history = [{"role": "user", "content": "GST दर क्या है?"}]
        await redis_client.session_set("hi", history)
        assert await redis_client.session_get("hi") == history


class TestCache:
    async def test_miss_returns_none(self, fake_redis):
        assert await redis_client.cache_get("k") is None

    async def test_roundtrip_with_default_five_minute_ttl(self, fake_redis):
        await redis_client.cache_set("k", {"answer": 42})
        assert await redis_client.cache_get("k") == {"answer": 42}
        assert fake_redis.ttls["k"] == 300


class TestFeedbackQueue:
    async def test_event_is_pushed_as_json(self, fake_redis):
        await redis_client.feedback_push("u1", "q", "r", "down")
        [raw] = fake_redis.lists["feedback:queue"]
        assert json.loads(raw) == {"user_id": "u1", "query": "q", "response": "r", "rating": "down"}

    async def test_newest_event_is_first(self, fake_redis):
        await redis_client.feedback_push("u1", "first", "r", "down")
        await redis_client.feedback_push("u1", "second", "r", "down")
        assert json.loads(fake_redis.lists["feedback:queue"][0])["query"] == "second"

    async def test_queue_is_capped_at_10000_events(self, fake_redis):
        for i in range(10_005):
            await redis_client.feedback_push("u", f"q{i}", "r", "down")
        queue = fake_redis.lists["feedback:queue"]
        assert len(queue) == 10_000
        assert json.loads(queue[0])["query"] == "q10004"   # newest kept, oldest dropped
