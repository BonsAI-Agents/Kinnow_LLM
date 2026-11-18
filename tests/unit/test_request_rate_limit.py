"""Per-user request rate limit (serve/rate_limit.py): 20 a minute, 500 a day, counted in Redis."""

import pytest

from serve import rate_limit
from serve.rate_limit import RequestRateLimiter, get_request_limiter, set_request_limiter
from tests.conftest import FakeRedis

NOW = 1_800_000_000.0        # a fixed instant, 20 seconds into a minute? checked in the tests below
MINUTE_START = NOW - (NOW % 60)


def make(fake=None, **kwargs):
    store = fake if fake is not None else FakeRedis()      # one shared Redis per limiter
    return RequestRateLimiter(lambda: store, **kwargs)


async def hit(limiter, n, user="u", owner="o", now=MINUTE_START + 10):
    return [await limiter.check(owner, user, now=now) for _ in range(n)]


class TestPerMinute:
    async def test_the_first_twenty_requests_in_a_minute_are_allowed(self):
        results = await hit(make(), 20)
        assert all(r.allowed for r in results)

    async def test_the_twenty_first_is_rejected_with_the_minute_scope(self):
        results = await hit(make(), 21)
        assert results[-1].allowed is False and results[-1].scope == "minute"

    async def test_retry_after_is_the_time_left_in_the_minute(self):
        results = await hit(make(), 21, now=MINUTE_START + 45)
        assert results[-1].retry_after == 15

    async def test_the_limit_resets_in_the_next_minute(self):
        limiter = make()
        await hit(limiter, 21, now=MINUTE_START + 10)
        assert (await limiter.check("o", "u", now=MINUTE_START + 61)).allowed is True

    async def test_limit_is_configurable(self):
        results = await hit(make(per_minute=3), 4)
        assert [r.allowed for r in results] == [True, True, True, False]

    async def test_limit_can_come_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
        monkeypatch.setenv("RATE_LIMIT_PER_DAY", "7")
        limiter = make()
        assert (limiter.per_minute, limiter.per_day) == (2, 7)


class TestPerDay:
    async def test_the_daily_limit_applies_across_minutes(self):
        limiter = make(per_minute=100, per_day=5)
        results = []
        for minute in range(7):
            results.append(await limiter.check("o", "u", now=MINUTE_START + 60 * minute + 5))
        assert [r.allowed for r in results] == [True] * 5 + [False] * 2
        assert results[-1].scope == "day"

    async def test_retry_after_for_the_daily_limit_is_the_time_to_utc_midnight(self):
        midnight = NOW - (NOW % 86400)
        limiter = make(per_minute=100, per_day=1)
        await limiter.check("o", "u", now=midnight + 3600)
        rejected = await limiter.check("o", "u", now=midnight + 3600)
        assert rejected.scope == "day" and rejected.retry_after == 86400 - 3600

    async def test_a_new_utc_day_starts_a_new_count(self):
        midnight = NOW - (NOW % 86400)
        limiter = make(per_minute=100, per_day=1)
        await limiter.check("o", "u", now=midnight + 100)
        assert (await limiter.check("o", "u", now=midnight + 86400 + 100)).allowed is True

    async def test_a_request_rejected_by_the_minute_limit_does_not_use_up_the_daily_quota(self):
        limiter = make(per_minute=1, per_day=2)
        await limiter.check("o", "u", now=MINUTE_START + 5)                         # day count 1
        for _ in range(5):
            await limiter.check("o", "u", now=MINUTE_START + 6)                      # all rejected by minute
        assert (await limiter.check("o", "u", now=MINUTE_START + 70)).allowed is True   # day count 2, still within 2


class TestScoping:
    async def test_users_are_limited_independently(self):
        limiter = make(per_minute=1)
        await hit(limiter, 2, user="heavy")
        assert (await limiter.check("o", "light", now=MINUTE_START + 10)).allowed is True

    async def test_the_same_user_id_under_two_api_keys_is_two_different_users(self):
        limiter = make(per_minute=1)
        await hit(limiter, 2, owner="client-a")
        assert (await limiter.check("client-b", "u", now=MINUTE_START + 10)).allowed is True

    async def test_two_replicas_share_the_same_counters(self):
        shared = FakeRedis()
        pod_a, pod_b = make(shared, per_minute=10), make(shared, per_minute=10)
        for _ in range(5):
            await pod_a.check("o", "u", now=MINUTE_START + 10)
            await pod_b.check("o", "u", now=MINUTE_START + 10)
        assert (await pod_a.check("o", "u", now=MINUTE_START + 10)).allowed is False


class TestStorage:
    async def test_counters_expire_so_user_ids_cannot_grow_storage_forever(self):
        fake = FakeRedis()
        limiter = make(fake)
        for i in range(50):
            await limiter.check("o", f"random-user-{i}", now=MINUTE_START + 10)
        assert fake.store and all(key in fake.ttls for key in fake.store)

    async def test_ttls_cover_the_window(self):
        fake = FakeRedis()
        await make(fake).check("o", "u", now=MINUTE_START + 10)
        minute_ttl = [t for k, t in fake.ttls.items() if ":min:" in k]
        day_ttl = [t for k, t in fake.ttls.items() if ":day:" in k]
        assert minute_ttl == [60] and day_ttl == [86400]


class TestRedisFailure:
    async def test_requests_are_allowed_and_a_warning_is_printed_when_redis_errors(self, capsys):
        fake = FakeRedis()
        fake.fail_incr = True
        result = await make(fake).check("o", "u", now=MINUTE_START + 10)
        assert result.allowed is True
        assert "allowing the request" in capsys.readouterr().err

    async def test_uninitialised_redis_also_fails_open(self):
        def not_ready():
            raise RuntimeError("Redis not initialized")

        assert (await RequestRateLimiter(not_ready).check("o", "u")).allowed is True


class TestHolder:
    def test_get_before_set_raises(self):
        set_request_limiter(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_request_limiter()

    def test_set_then_get(self):
        limiter = make()
        set_request_limiter(limiter)
        assert get_request_limiter() is limiter
        set_request_limiter(None)


def test_defaults_match_the_plan():
    assert (rate_limit.DEFAULT_PER_MINUTE, rate_limit.DEFAULT_PER_DAY) == (20, 500)
