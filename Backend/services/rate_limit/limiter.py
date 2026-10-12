"""Fixed-window rate limiter with a Redis store, an in-process fallback and a circuit breaker.

Counters are keyed by rule, a SHA-256 digest of the subject, and the window
start, so no raw address, user id or username is stored. Every counter key is
written with a TTL in the same transaction as its increment.

One check is one store call, however many rules it covers. After a primary
failure the primary is skipped until a cool-down has passed, so a black-holed
Redis costs one timeout per cool-down rather than one per request. The limiter
never raises into the request path: a failing primary falls back to
process-local counters, and a failing fallback allows the request.
"""

from __future__ import annotations

import hashlib
import logging
import math
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

KEY_PREFIX = "pms:rl"
STORE_WARNING_INTERVAL_SECONDS = 60.0


@dataclass(frozen=True)
class RateRule:
    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class RuleDecision:
    rule: RateRule
    subject_digest: str
    count: int
    reset_seconds: int

    @property
    def allowed(self) -> bool:
        return self.count <= self.rule.limit

    @property
    def remaining(self) -> int:
        return max(0, self.rule.limit - self.count)


def subject_digest(subject: str) -> str:
    return hashlib.sha256(subject.encode("utf-8")).hexdigest()[:24]


def counter_key(rule: RateRule, digest: str, window_start: int) -> str:
    return f"{KEY_PREFIX}:{rule.name}:{digest}:{window_start}"


class CounterStore(Protocol):
    def increment_many(self, items: Sequence[tuple[str, float]], now: float) -> list[int]:
        """Increment each (key, expires_at) and return the new counts, in order."""
        ...


class RedisCounterStore:
    """Every counter of one check in a single MULTI transaction: INCR, then EXPIRE NX so the first increment sets the TTL.

    Takes any client with a redis-py style ``pipeline(transaction=True)``, such as ``redis.Redis``.
    """

    def __init__(self, client) -> None:
        self._client = client

    def increment_many(self, items: Sequence[tuple[str, float]], now: float) -> list[int]:
        if not items:
            return []
        pipeline = self._client.pipeline(transaction=True)
        for key, expires_at in items:
            pipeline.incr(key)
            pipeline.expire(key, max(1, math.ceil(expires_at - now)), nx=True)
        results = pipeline.execute()
        return [int(count) for count in results[0::2]]


class _Window:
    __slots__ = ("count", "expires_at")

    def __init__(self, expires_at: float) -> None:
        self.count = 0
        self.expires_at = expires_at


class InProcessCounterStore:
    """Thread-safe, bounded counters. Expired windows are pruned from the oldest end, so no request scans every key."""

    def __init__(self, *, max_keys: int, prune_every: int = 256) -> None:
        if max_keys <= 0 or prune_every <= 0:
            raise ValueError("max_keys and prune_every must be greater than zero.")
        self._max_keys = max_keys
        self._prune_every = prune_every
        self._windows: dict[str, _Window] = {}
        self._operations = 0
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._windows)

    def increment_many(self, items: Sequence[tuple[str, float]], now: float) -> list[int]:
        counts: list[int] = []
        with self._lock:
            for key, expires_at in items:
                self._operations += 1
                if self._operations % self._prune_every == 0:
                    self._prune(now)
                counts.append(self._increment_locked(key, expires_at, now))
        return counts

    def _increment_locked(self, key: str, expires_at: float, now: float) -> int:
        window = self._windows.get(key)
        if window is not None and window.expires_at > now:
            window.count += 1
            return window.count
        if window is not None:
            del self._windows[key]
        while len(self._windows) >= self._max_keys:
            self._windows.pop(next(iter(self._windows)))
        window = _Window(expires_at)
        window.count = 1
        self._windows[key] = window
        return 1

    def _prune(self, now: float) -> None:
        while self._windows:
            oldest = next(iter(self._windows))
            if self._windows[oldest].expires_at > now:
                return
            del self._windows[oldest]


class RateLimiter:
    def __init__(
        self,
        *,
        fallback: InProcessCounterStore,
        clock: Callable[[], float],
        primary: CounterStore | None = None,
        cool_down_seconds: float = 30.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if cool_down_seconds < 0:
            raise ValueError("cool_down_seconds cannot be negative.")
        self._fallback = fallback
        self._primary = primary
        self._clock = clock
        self._cool_down_seconds = float(cool_down_seconds)
        self._monotonic = monotonic
        self._reopen_at = float("-inf")
        self._breaker_lock = threading.Lock()
        self._last_store_warning = float("-inf")
        self._warning_lock = threading.Lock()

    def check(self, checks: Sequence[tuple[RateRule, str]]) -> tuple[RuleDecision, ...]:
        """Count one request against each (rule, subject) pair in one store call. Never raises."""
        if not checks:
            return ()
        now = self._clock()
        planned = []
        for rule, subject in checks:
            window_start = int(now // rule.window_seconds) * rule.window_seconds
            expires_at = float(window_start + rule.window_seconds)
            digest = subject_digest(subject)
            planned.append((rule, digest, expires_at, counter_key(rule, digest, window_start)))
        counts = self._increment_many([(key, expires_at) for _, _, expires_at, key in planned], now)
        return tuple(
            RuleDecision(
                rule=rule,
                subject_digest=digest,
                count=count,
                reset_seconds=max(1, math.ceil(expires_at - now)),
            )
            for (rule, digest, expires_at, _), count in zip(planned, counts)
        )

    def _increment_many(self, items: Sequence[tuple[str, float]], now: float) -> list[int]:
        if self._primary is not None and self._primary_available():
            try:
                return list(self._primary.increment_many(items, now))
            except Exception as exc:
                self._open_breaker(exc)
        try:
            return list(self._fallback.increment_many(items, now))
        except Exception:
            logger.exception("Rate limit fallback counter failed; allowing the request")
            return [0] * len(items)

    def _primary_available(self) -> bool:
        """Closed, or open but past its cool-down, in which case one attempt is made."""
        with self._breaker_lock:
            return self._monotonic() >= self._reopen_at

    def _open_breaker(self, exc: Exception) -> None:
        with self._breaker_lock:
            self._reopen_at = self._monotonic() + self._cool_down_seconds
        self._warn_store_unavailable(exc)

    def _warn_store_unavailable(self, exc: Exception) -> None:
        with self._warning_lock:
            now = self._monotonic()
            if now - self._last_store_warning < STORE_WARNING_INTERVAL_SECONDS:
                return
            self._last_store_warning = now
        # The exception class only: connection errors can carry host details.
        logger.warning("Rate limit Redis store unavailable (%s); using in-process counters", type(exc).__name__)
