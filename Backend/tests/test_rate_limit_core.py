"""Limiter core on the Redis store and the in-process fallback. Time is always injected.

The breaker tests inject a second, monotonic clock for the cool-down, so they never sleep.
"""

import logging

import pytest
import redis

from services.rate_limit.limiter import (
    InProcessCounterStore,
    RateLimiter,
    RateRule,
    RedisCounterStore,
    subject_digest,
)
from tests.rate_limit_support import FakeClock, FakeRedis

LIMIT = 3
WINDOW = 60
COOL_DOWN = 30.0
RULE = RateRule("probe", LIMIT, WINDOW)
OTHER_RULE = RateRule("other", LIMIT, WINDOW)


class RecordingFallback(InProcessCounterStore):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.keys: list[str] = []
        self.calls = 0

    def increment_many(self, items, now):
        self.calls += 1
        self.keys.extend(key for key, _ in items)
        return super().increment_many(items, now)


def _limiter(backend: str, clock: FakeClock):
    if backend == "redis":
        fake = FakeRedis(clock)
        limiter = RateLimiter(
            primary=RedisCounterStore(fake),
            fallback=InProcessCounterStore(max_keys=1000),
            clock=clock,
            monotonic=FakeClock(0.0),
            cool_down_seconds=COOL_DOWN,
        )
        return limiter, fake
    fallback = RecordingFallback(max_keys=1000)
    return RateLimiter(fallback=fallback, clock=clock), fallback


@pytest.fixture(params=["redis", "memory"])
def backend(request):
    return request.param


def _hit(limiter, subject: str, rule: RateRule = RULE):
    (decision,) = limiter.check([(rule, subject)])
    return decision


def test_allows_up_to_the_limit_and_rejects_the_next(backend):
    clock = FakeClock()
    limiter, _ = _limiter(backend, clock)
    decisions = [_hit(limiter, "client-a") for _ in range(LIMIT + 1)]
    assert [decision.allowed for decision in decisions] == [True] * LIMIT + [False]
    assert decisions[-1].count == LIMIT + 1
    assert decisions[-1].remaining == 0


def test_reset_seconds_describe_the_time_to_the_window_boundary(backend):
    clock = FakeClock(now=1_000.0)
    limiter, _ = _limiter(backend, clock)
    decision = _hit(limiter, "client-a")
    # The window containing 1000 starts at 960 and ends at 1020.
    assert decision.reset_seconds == 20


def test_resets_at_the_window_boundary(backend):
    clock = FakeClock(now=1_000.0)
    limiter, _ = _limiter(backend, clock)
    for _ in range(LIMIT + 1):
        _hit(limiter, "client-a")
    assert _hit(limiter, "client-a").allowed is False

    clock.now = 1_019.9
    assert _hit(limiter, "client-a").allowed is False

    clock.now = 1_020.0
    assert _hit(limiter, "client-a").count == 1
    assert _hit(limiter, "client-a").allowed is True


def test_subjects_are_independent(backend):
    clock = FakeClock()
    limiter, _ = _limiter(backend, clock)
    for _ in range(LIMIT + 1):
        _hit(limiter, "client-a")
    assert _hit(limiter, "client-a").allowed is False
    assert _hit(limiter, "client-b").allowed is True


def test_rules_are_independent_for_the_same_subject(backend):
    clock = FakeClock()
    limiter, _ = _limiter(backend, clock)
    for _ in range(LIMIT + 1):
        _hit(limiter, "client-a", RULE)
    assert _hit(limiter, "client-a", RULE).allowed is False
    assert _hit(limiter, "client-a", OTHER_RULE).allowed is True


def test_one_check_with_several_rules_reports_each_and_the_verdict_is_per_rule(backend):
    clock = FakeClock()
    limiter, _ = _limiter(backend, clock)
    tight = RateRule("tight", 1, WINDOW)
    loose = RateRule("loose", 10, WINDOW)
    first = limiter.check([(tight, "client-a"), (loose, "client-a")])
    second = limiter.check([(tight, "client-a"), (loose, "client-a")])
    assert [decision.allowed for decision in first] == [True, True]
    assert [decision.allowed for decision in second] == [False, True]


def test_an_empty_check_counts_nothing_and_touches_no_store():
    clock = FakeClock()
    fake = FakeRedis(clock)
    limiter = RateLimiter(primary=RedisCounterStore(fake), fallback=InProcessCounterStore(max_keys=10), clock=clock)
    assert limiter.check([]) == ()
    assert fake.attempts == 0


def test_one_check_is_one_store_call_however_many_rules_it_covers():
    clock = FakeClock()
    fake = FakeRedis(clock)
    fallback = RecordingFallback(max_keys=10)
    limiter = RateLimiter(primary=RedisCounterStore(fake), fallback=fallback, clock=clock)
    rules = [RateRule(f"rule-{index}", 10, WINDOW) for index in range(4)]
    limiter.check([(rule, "client-a") for rule in rules])
    assert fake.attempts == 1
    assert fake.executed_transactions == 1
    # The same check on the in-process store is one batched call too.
    fallback_only = RecordingFallback(max_keys=10)
    RateLimiter(fallback=fallback_only, clock=clock).check([(rule, "client-a") for rule in rules])
    assert fallback_only.calls == 1
    assert len(fallback_only.keys) == 4


def test_redis_keys_always_carry_a_ttl_bounded_by_the_window():
    clock = FakeClock(now=1_000.0)
    fake = FakeRedis(clock)
    limiter = RateLimiter(primary=RedisCounterStore(fake), fallback=InProcessCounterStore(max_keys=10), clock=clock)
    for _ in range(3):
        _hit(limiter, "client-a")
    assert fake.values, "the Redis store was not used"
    assert fake.keys_without_ttl() == []
    assert all(0 < deadline - clock.now <= WINDOW for deadline in fake.expiry.values())
    assert fake.executed_transactions == 3


def test_keys_never_contain_the_raw_subject(backend):
    clock = FakeClock()
    limiter, store = _limiter(backend, clock)
    subjects = ["203.0.113.9", "user:b1000000-0000-4000-8000-000000000001", "login-user:203.0.113.9|jane.doe"]
    for subject in subjects:
        _hit(limiter, subject)
    keys = list(store.values) if backend == "redis" else list(store.keys)
    assert keys, "no keys were recorded"
    for key in keys:
        for subject in subjects:
            assert subject not in key
    for subject in subjects:
        assert any(subject_digest(subject) in key for key in keys)


def test_digest_is_truncated_sha256():
    digest = subject_digest("203.0.113.9")
    assert len(digest) == 24
    assert all(character in "0123456789abcdef" for character in digest)
    assert subject_digest("203.0.113.9") == digest
    assert subject_digest("203.0.113.10") != digest


def test_redis_failure_mid_request_falls_back_without_raising_or_blocking():
    clock = FakeClock()
    fake = FakeRedis(clock)
    fake.fail_executes = 1
    limiter = RateLimiter(
        primary=RedisCounterStore(fake),
        fallback=InProcessCounterStore(max_keys=10),
        clock=clock,
        monotonic=FakeClock(0.0),
        cool_down_seconds=COOL_DOWN,
    )
    decision = _hit(limiter, "client-a")
    assert decision.allowed is True
    assert decision.count == 1


def test_redis_outage_never_turns_legitimate_traffic_into_a_block(caplog):
    clock = FakeClock()
    fake = FakeRedis(clock)
    fake.fail_executes = 10**6
    limiter = RateLimiter(
        primary=RedisCounterStore(fake),
        fallback=InProcessCounterStore(max_keys=10),
        clock=clock,
        monotonic=FakeClock(0.0),
        cool_down_seconds=COOL_DOWN,
    )
    with caplog.at_level(logging.WARNING):
        decisions = [_hit(limiter, "client-a") for _ in range(LIMIT)]
    assert all(decision.allowed for decision in decisions)
    # The warning names the exception class only, and is throttled to one per interval.
    warnings = [record for record in caplog.records if "Redis store unavailable" in record.getMessage()]
    assert len(warnings) == 1
    assert "ConnectionError" in warnings[0].getMessage()


# ── Circuit breaker ─────────────────────────────────────────────────────────

def _breaker_limiter(fake: FakeRedis, clock: FakeClock, monotonic: FakeClock, *, cool_down: float = COOL_DOWN):
    fallback = RecordingFallback(max_keys=1000)
    limiter = RateLimiter(
        primary=RedisCounterStore(fake),
        fallback=fallback,
        clock=clock,
        monotonic=monotonic,
        cool_down_seconds=cool_down,
    )
    return limiter, fallback


def test_a_primary_failure_opens_the_breaker_and_calls_during_cool_down_never_reach_the_primary():
    clock = FakeClock()
    monotonic = FakeClock(0.0)
    fake = FakeRedis(clock)
    limiter, fallback = _breaker_limiter(fake, clock, monotonic)

    fake.fail_executes = 1
    _hit(limiter, "client-a")
    assert fake.attempts == 1

    # Every check inside the cool-down is answered by the fallback, and the primary is not called at all.
    for _ in range(5):
        monotonic.advance(COOL_DOWN / 10)
        _hit(limiter, "client-a")
    assert fake.attempts == 1
    assert fallback.calls == 6
    assert _hit(limiter, "client-a").count == 7


def test_the_primary_is_retried_once_the_cool_down_has_passed():
    clock = FakeClock()
    monotonic = FakeClock(0.0)
    fake = FakeRedis(clock)
    limiter, _ = _breaker_limiter(fake, clock, monotonic)

    fake.fail_executes = 1
    _hit(limiter, "client-a")
    monotonic.advance(COOL_DOWN - 1)
    _hit(limiter, "client-a")
    assert fake.attempts == 1

    monotonic.advance(1)
    _hit(limiter, "client-a")
    assert fake.attempts == 2
    assert fake.values, "the retried primary did not store the counter"


def test_a_failed_retry_reopens_the_breaker_for_another_full_cool_down():
    clock = FakeClock()
    monotonic = FakeClock(0.0)
    fake = FakeRedis(clock)
    limiter, _ = _breaker_limiter(fake, clock, monotonic)

    fake.fail_executes = 2
    _hit(limiter, "client-a")
    monotonic.advance(COOL_DOWN)
    _hit(limiter, "client-a")
    assert fake.attempts == 2

    monotonic.advance(COOL_DOWN - 1)
    _hit(limiter, "client-a")
    assert fake.attempts == 2
    monotonic.advance(1)
    _hit(limiter, "client-a")
    assert fake.attempts == 3


def test_recovery_closes_the_breaker_and_later_checks_use_the_primary_again():
    clock = FakeClock()
    monotonic = FakeClock(0.0)
    fake = FakeRedis(clock)
    limiter, fallback = _breaker_limiter(fake, clock, monotonic)

    fake.fail_executes = 1
    _hit(limiter, "client-a")
    monotonic.advance(COOL_DOWN)
    _hit(limiter, "client-a")
    fallback_calls_at_recovery = fallback.calls

    for _ in range(3):
        _hit(limiter, "client-a")
    assert fake.attempts == 5
    assert fallback.calls == fallback_calls_at_recovery


def test_a_zero_cool_down_retries_the_primary_on_every_check():
    clock = FakeClock()
    fake = FakeRedis(clock)
    limiter, _ = _breaker_limiter(fake, clock, FakeClock(0.0), cool_down=0)
    fake.fail_executes = 2
    _hit(limiter, "client-a")
    _hit(limiter, "client-a")
    assert fake.attempts == 2
    _hit(limiter, "client-a")
    assert fake.attempts == 3


def test_a_negative_cool_down_is_rejected():
    with pytest.raises(ValueError):
        RateLimiter(fallback=InProcessCounterStore(max_keys=10), clock=FakeClock(), cool_down_seconds=-1)


def test_a_broken_redis_client_falls_back_to_in_process_counters():
    class Broken:
        def pipeline(self, transaction=True):
            raise redis.ConnectionError("down")

    limiter = RateLimiter(primary=RedisCounterStore(Broken()), fallback=InProcessCounterStore(max_keys=10), clock=FakeClock())
    assert _hit(limiter, "client-a").allowed is True


def test_a_failing_fallback_fails_open_without_raising(monkeypatch):
    clock = FakeClock()
    fallback = InProcessCounterStore(max_keys=10)

    def broken(*args, **kwargs):
        raise RuntimeError("counter store broke")

    monkeypatch.setattr(fallback, "increment_many", broken)
    limiter = RateLimiter(fallback=fallback, clock=clock)
    decision = _hit(limiter, "client-a")
    assert decision.allowed is True


# ── In-process store ─────────────────────────────────────────────────────────

def test_in_process_store_stays_bounded_under_many_distinct_subjects():
    clock = FakeClock()
    store = InProcessCounterStore(max_keys=50)
    limiter = RateLimiter(fallback=store, clock=clock)
    for index in range(5_000):
        _hit(limiter, f"client-{index}")
        assert len(store) <= 50


def test_in_process_store_prunes_expired_windows_without_scanning_every_key():
    clock = FakeClock(now=1_000.0)
    store = InProcessCounterStore(max_keys=10_000, prune_every=8)
    limiter = RateLimiter(fallback=store, clock=clock)
    for index in range(200):
        _hit(limiter, f"client-{index}")
    assert len(store) == 200
    clock.now = 1_000.0 + WINDOW * 2
    for index in range(16):
        _hit(limiter, f"fresh-{index}")
    assert len(store) == 16


def test_in_process_store_rejects_non_positive_bounds():
    with pytest.raises(ValueError):
        InProcessCounterStore(max_keys=0)
    with pytest.raises(ValueError):
        InProcessCounterStore(max_keys=10, prune_every=0)


def test_in_process_store_batch_counts_each_key_in_order_under_one_call():
    clock = FakeClock(now=1_000.0)
    store = InProcessCounterStore(max_keys=10)
    counts = store.increment_many([("a", 1_020.0), ("b", 1_020.0), ("a", 1_020.0)], 1_000.0)
    assert counts == [1, 1, 2]
