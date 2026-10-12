"""Shared doubles for the rate-limit tests. No real Redis or database is contacted."""

from __future__ import annotations

import redis


class FakeClock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = float(now)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


class FakeRedis:
    """In-memory stand-in for the pipeline calls the limiter makes (INCR and EXPIRE NX inside MULTI).

    Keys carry an expiry on the injected clock. Expired keys read as absent, like Redis.
    `fail_executes` makes the next N transactions raise, to simulate an outage mid-request.
    """

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.values: dict[str, int] = {}
        self.expiry: dict[str, float] = {}
        self.fail_executes = 0
        # Every transaction the limiter sends, including the ones that fail. The breaker tests count these.
        self.attempts = 0
        self.executed_transactions = 0

    def pipeline(self, transaction: bool = True) -> "_FakePipeline":
        return _FakePipeline(self)

    def _expire_if_due(self, key: str) -> None:
        deadline = self.expiry.get(key)
        if deadline is not None and deadline <= self.clock.now:
            self.values.pop(key, None)
            self.expiry.pop(key, None)

    def keys_without_ttl(self) -> list[str]:
        return [key for key in self.values if key not in self.expiry]


class _FakePipeline:
    def __init__(self, store: FakeRedis) -> None:
        self._store = store
        self._operations: list[tuple] = []

    def incr(self, key: str) -> "_FakePipeline":
        self._operations.append(("incr", key))
        return self

    def expire(self, key: str, seconds: int, nx: bool = False) -> "_FakePipeline":
        self._operations.append(("expire", key, seconds, nx))
        return self

    def execute(self) -> list:
        store = self._store
        store.attempts += 1
        if store.fail_executes > 0:
            store.fail_executes -= 1
            raise redis.ConnectionError("simulated Redis outage")
        store.executed_transactions += 1
        results: list = []
        for operation in self._operations:
            if operation[0] == "incr":
                key = operation[1]
                store._expire_if_due(key)
                store.values[key] = store.values.get(key, 0) + 1
                results.append(store.values[key])
            else:
                _, key, seconds, nx = operation
                store._expire_if_due(key)
                if key not in store.values:
                    results.append(False)
                    continue
                if nx and key in store.expiry:
                    results.append(False)
                    continue
                store.expiry[key] = store.clock.now + seconds
                results.append(True)
        return results
