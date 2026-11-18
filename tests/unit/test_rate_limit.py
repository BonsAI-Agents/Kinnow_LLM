"""Refusal rate limiters: the in-process one (bounded) and the Redis-backed one (shared across pods)."""

import time

import pytest

from guardrails import rate_limit
from guardrails.rate_limit import InMemoryRateLimiter
from serve.rate_limiter import RedisRateLimiter
from tests.conftest import FakeRedis


async def trip(limiter, user, times):
    results = [await limiter.record(user) for _ in range(times)]
    return results


class TestInMemoryRateLimiter:
    async def test_not_limited_until_the_threshold(self):
        limiter = InMemoryRateLimiter(threshold=3)
        assert await trip(limiter, "u", 2) == [False, False]
        assert await limiter.is_limited("u") is False

    async def test_threshold_trips_the_limit_and_reports_it_once(self):
        limiter = InMemoryRateLimiter(threshold=3)
        assert await trip(limiter, "u", 3) == [False, False, True]
        assert await limiter.is_limited("u") is True

    async def test_users_are_independent(self):
        limiter = InMemoryRateLimiter(threshold=2)
        await trip(limiter, "a", 2)
        assert await limiter.is_limited("a") is True
        assert await limiter.is_limited("b") is False

    async def test_events_outside_the_window_do_not_count(self, monkeypatch):
        limiter = InMemoryRateLimiter(window_seconds=60, threshold=3)
        now = time.time()
        monkeypatch.setattr(rate_limit.time, "time", lambda: now)
        await trip(limiter, "u", 2)
        monkeypatch.setattr(rate_limit.time, "time", lambda: now + 61)
        assert await limiter.record("u") is False           # the two old events expired
        assert await limiter.is_limited("u") is False

    async def test_the_limit_lifts_after_the_cooldown(self, monkeypatch):
        limiter = InMemoryRateLimiter(threshold=2, cooldown_seconds=600)
        now = time.time()
        monkeypatch.setattr(rate_limit.time, "time", lambda: now)
        await trip(limiter, "u", 2)
        assert await limiter.is_limited("u") is True
        monkeypatch.setattr(rate_limit.time, "time", lambda: now + 601)
        assert await limiter.is_limited("u") is False
        assert "u" not in limiter._limited_until            # expired entries are forgotten

    async def test_checking_a_limit_never_creates_state(self):
        limiter = InMemoryRateLimiter()
        for i in range(500):
            await limiter.is_limited(f"probe-{i}")
        assert limiter._events == {} and limiter._limited_until == {}

    async def test_memory_is_bounded_when_ids_are_attacker_chosen(self):
        limiter = InMemoryRateLimiter(threshold=100, max_tracked=50)
        for i in range(500):
            await limiter.record(f"random-session-{i}")
        assert len(limiter._events) <= 50

    async def test_limited_users_are_bounded_too(self):
        limiter = InMemoryRateLimiter(threshold=1, max_tracked=20)
        for i in range(200):
            await limiter.record(f"user-{i}")
        assert len(limiter._limited_until) <= 20

    async def test_reset_clears_everything(self):
        limiter = InMemoryRateLimiter(threshold=1)
        await limiter.record("u")
        limiter.reset()
        assert await limiter.is_limited("u") is False


class TestRedisRateLimiter:
    def make(self, fake, **kwargs):
        return RedisRateLimiter(lambda: fake, **kwargs)

    async def test_threshold_trips_the_limit(self):
        limiter = self.make(FakeRedis(), threshold=3)
        assert await trip(limiter, "u", 3) == [False, False, True]
        assert await limiter.is_limited("u") is True

    async def test_the_counter_expires_with_the_window(self):
        fake = FakeRedis()
        limiter = self.make(fake, window_seconds=300, threshold=5)
        await limiter.record("u")
        assert fake.ttls["rl:oos:count:u"] == 300

    async def test_the_limit_flag_expires_with_the_cooldown(self):
        fake = FakeRedis()
        limiter = self.make(fake, threshold=1, cooldown_seconds=600)
        await limiter.record("u")
        assert fake.ttls["rl:oos:limited:u"] == 600
        assert "rl:oos:count:u" not in fake.store           # counter is cleared once limited

    async def test_two_replicas_share_one_counter(self):
        """The bug: with per-pod counters each of two pods allowed 10 attempts. Now it is 10 in total."""
        shared = FakeRedis()
        pod_a, pod_b = self.make(shared, threshold=10), self.make(shared, threshold=10)
        for _ in range(5):
            await pod_a.record("u")
            await pod_b.record("u")
        assert await pod_a.is_limited("u") is True
        assert await pod_b.is_limited("u") is True

    async def test_users_are_independent(self):
        limiter = self.make(FakeRedis(), threshold=2)
        await trip(limiter, "a", 2)
        assert await limiter.is_limited("b") is False

    async def test_every_key_has_a_ttl_so_random_ids_cannot_grow_storage_forever(self):
        fake = FakeRedis()
        limiter = self.make(fake, threshold=100)
        for i in range(100):
            await limiter.record(f"random-{i}")
        counters = [k for k in fake.store if k.startswith("rl:oos:count:")]
        assert len(counters) == 100 and all(k in fake.ttls for k in counters)

    async def test_falls_back_to_the_in_process_limiter_when_redis_errors(self, capsys):
        fake = FakeRedis()
        fake.fail_incr = True
        limiter = self.make(fake, threshold=2)
        assert await limiter.record("u") is False
        assert await limiter.record("u") is True             # counted in memory instead
        assert await limiter.is_limited("u") is True
        assert "using the in-process limiter" in capsys.readouterr().err

    async def test_redis_that_is_not_initialised_also_falls_back(self):
        def not_ready():
            raise RuntimeError("Redis not initialized")

        limiter = RedisRateLimiter(not_ready, threshold=1)
        assert await limiter.record("u") is True
        assert await limiter.is_limited("u") is True


@pytest.mark.parametrize("name", ["OOS_WINDOW_SECONDS", "OOS_BLOCK_THRESHOLD", "RATE_LIMIT_DURATION", "MAX_TRACKED_USERS"])
def test_defaults_match_the_plan(name):
    expected = {"OOS_WINDOW_SECONDS": 300, "OOS_BLOCK_THRESHOLD": 10, "RATE_LIMIT_DURATION": 600, "MAX_TRACKED_USERS": 10_000}
    assert getattr(rate_limit, name) == expected[name]
