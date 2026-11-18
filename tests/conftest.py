"""Shared fixtures for the unit and integration tests."""

import pytest

from guardrails.pipeline import reset_oos_tracker
from guardrails import layer2_classifier
from serve import circuit_breaker, redis_client, vllm_client
from serve.routes import chat


class FakeRedis:
    """In-memory stand-in for redis.asyncio.Redis covering the calls serve/ makes."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.lists: dict[str, list[str]] = {}
        self.fail_ping = False
        self.closed = False

    async def ping(self):
        if self.fail_ping:
            raise ConnectionError("redis down")
        return True

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttls[key] = ttl

    async def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    async def ltrim(self, key, start, stop):
        self.lists[key] = self.lists.get(key, [])[start:stop + 1]

    async def aclose(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _clean_global_state(monkeypatch):
    """Every test starts with no shared state leaking from the last one."""
    reset_oos_tracker()
    layer2_classifier.set_domain_centroids({})          # keyword-only classifier, no model download
    monkeypatch.setattr(circuit_breaker, "_breaker", circuit_breaker.CircuitBreaker())
    monkeypatch.setattr(chat, "_pipeline", None)
    monkeypatch.setattr(redis_client, "_redis", None)
    monkeypatch.setattr(vllm_client, "_client", None)
    yield
    layer2_classifier.set_domain_centroids({})
    reset_oos_tracker()


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(redis_client, "_redis", fake)
    return fake
