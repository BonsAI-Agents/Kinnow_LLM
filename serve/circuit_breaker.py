"""
Circuit breaker around model inference (Section 23).
States: CLOSED → (5 failures) → OPEN → (60s) → HALF-OPEN → (1 success) → CLOSED
                                                           → (1 failure)  → OPEN
"""

import time
import asyncio
from enum import Enum


class State(Enum):
    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'


FAILURE_THRESHOLD = 5       # failures before OPEN
COOLDOWN_SECONDS = 60       # time in OPEN before trying HALF-OPEN
SUCCESS_THRESHOLD = 1       # successes in HALF-OPEN before CLOSED


def _reject(coro, message: str):
    """Refuse a call: close the never-awaited coroutine so it is not leaked, then raise."""
    close = getattr(coro, 'close', None)
    if close:
        close()
    raise RuntimeError(message)


class CircuitBreaker:
    def __init__(self):
        self.state = State.CLOSED
        self._failures = 0                # consecutive failures
        self._opened_at: float = 0.0
        self._lock = asyncio.Lock()
        self._testing_half_open = False   # gates to exactly one test call in HALF_OPEN

    async def call(self, coro):
        """
        Wrap an awaitable. Raises RuntimeError with 503-style message when OPEN.
        """
        async with self._lock:
            if self.state == State.OPEN:
                elapsed = time.time() - self._opened_at
                if elapsed >= COOLDOWN_SECONDS:
                    self.state = State.HALF_OPEN
                    self._testing_half_open = False
                else:
                    _reject(coro, f"circuit_open: model unavailable, retry in "
                                  f"{int(COOLDOWN_SECONDS - elapsed)}s")
            if self.state == State.HALF_OPEN:
                if self._testing_half_open:
                    _reject(coro, "circuit_open: probe already in-flight, retry shortly")
                self._testing_half_open = True

        try:
            result = await coro
            async with self._lock:
                # Any success ends the failure streak: only consecutive failures trip the breaker.
                self._failures = 0
                if self.state == State.HALF_OPEN:
                    self.state = State.CLOSED
                    self._testing_half_open = False
            return result
        except Exception as exc:
            async with self._lock:
                self._testing_half_open = False
                self._failures += 1
                if self._failures >= FAILURE_THRESHOLD or self.state == State.HALF_OPEN:
                    self.state = State.OPEN
                    self._opened_at = time.time()
            raise exc

    @property
    def is_open(self) -> bool:
        return self.state == State.OPEN


_breaker = CircuitBreaker()


def get_circuit_breaker() -> CircuitBreaker:
    return _breaker
