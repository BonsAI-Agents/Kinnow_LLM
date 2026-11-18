"""Unit tests for the circuit breaker (plan section 23)."""

import asyncio
import gc
import time
import warnings

import pytest

from serve import circuit_breaker
from serve.circuit_breaker import CircuitBreaker, State, FAILURE_THRESHOLD, COOLDOWN_SECONDS


async def ok(value="ok"):
    return value


async def boom():
    raise ValueError("model failed")


async def fail_n_times(cb: CircuitBreaker, n: int):
    for _ in range(n):
        with pytest.raises(ValueError):
            await cb.call(boom())


class TestClosedState:
    async def test_passes_results_through(self):
        cb = CircuitBreaker()
        assert await cb.call(ok("hello")) == "hello"
        assert cb.state == State.CLOSED
        assert cb.is_open is False

    async def test_failures_below_threshold_stay_closed(self):
        cb = CircuitBreaker()
        await fail_n_times(cb, FAILURE_THRESHOLD - 1)
        assert cb.state == State.CLOSED

    async def test_original_exception_is_reraised(self):
        cb = CircuitBreaker()
        with pytest.raises(ValueError, match="model failed"):
            await cb.call(boom())

    async def test_threshold_failures_open_the_circuit(self):
        cb = CircuitBreaker()
        await fail_n_times(cb, FAILURE_THRESHOLD)
        assert cb.state == State.OPEN
        assert cb.is_open is True

    async def test_a_success_resets_the_failure_count(self):
        """5 failures must be consecutive: sporadic errors over time must not trip the breaker."""
        cb = CircuitBreaker()
        await fail_n_times(cb, FAILURE_THRESHOLD - 1)
        await cb.call(ok())
        await fail_n_times(cb, 1)
        assert cb.state == State.CLOSED


class TestOpenState:
    async def _open(self) -> CircuitBreaker:
        cb = CircuitBreaker()
        await fail_n_times(cb, FAILURE_THRESHOLD)
        return cb

    async def test_rejects_calls_without_running_them(self):
        cb = await self._open()
        ran = []

        async def should_not_run():
            ran.append(True)

        with pytest.raises(RuntimeError, match="circuit_open"):
            await cb.call(should_not_run())
        assert ran == []

    async def test_error_message_reports_remaining_cooldown(self):
        cb = await self._open()
        with pytest.raises(RuntimeError) as exc:
            await cb.call(ok())
        assert "retry in" in str(exc.value)

    async def test_rejected_coroutine_is_closed_not_leaked(self):
        """A rejected call must not leave a 'coroutine was never awaited' warning behind."""
        cb = await self._open()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with pytest.raises(RuntimeError):
                await cb.call(ok())
            gc.collect()
        assert not [w for w in caught if "never awaited" in str(w.message)]


class TestHalfOpen:
    async def _expired(self) -> CircuitBreaker:
        cb = CircuitBreaker()
        await fail_n_times(cb, FAILURE_THRESHOLD)
        cb._opened_at = time.time() - COOLDOWN_SECONDS - 1
        return cb

    async def test_success_after_cooldown_closes_the_circuit(self):
        cb = await self._expired()
        assert await cb.call(ok("recovered")) == "recovered"
        assert cb.state == State.CLOSED
        assert cb._failures == 0

    async def test_failure_in_half_open_reopens_immediately(self):
        cb = await self._expired()
        with pytest.raises(ValueError):
            await cb.call(boom())
        assert cb.state == State.OPEN

    async def test_only_one_probe_is_allowed_at_a_time(self):
        cb = await self._expired()
        release = asyncio.Event()

        async def slow_probe():
            await release.wait()
            return "probe"

        probe = asyncio.create_task(cb.call(slow_probe()))
        await asyncio.sleep(0)  # let the probe enter HALF_OPEN and start waiting
        with pytest.raises(RuntimeError, match="probe already in-flight"):
            await cb.call(ok())
        release.set()
        assert await probe == "probe"
        assert cb.state == State.CLOSED


def test_get_circuit_breaker_returns_the_shared_instance():
    assert circuit_breaker.get_circuit_breaker() is circuit_breaker.get_circuit_breaker()
