"""The store round trip runs off the event loop, and the fast paths never leave it."""

import asyncio
import threading
import time

import pytest
from starlette.requests import Request

from services.rate_limit import policy as policy_module
from services.rate_limit.enforcement import RateLimitExceeded, enforce_login_username_limit, evaluate
from services.rate_limit.limiter import InProcessCounterStore, RateLimiter
from services.rate_limit.policy import RateLimitRuntime, RateLimits, RuleSet
from tests.rate_limit_support import FakeClock


class ThreadRecordingStore:
    """Records the thread of every call, and can sleep to stand in for a slow Redis."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.threads: list[int] = []
        self._inner = InProcessCounterStore(max_keys=1_000)

    def increment_many(self, items, now):
        self.threads.append(threading.get_ident())
        if self.delay:
            time.sleep(self.delay)
        return self._inner.increment_many(items, now)


def make_runtime(store, *, mode: str = "enforce", login_username: int = 5) -> RateLimitRuntime:
    limits = RateLimits(
        login_address=60,
        login_username=login_username,
        refresh_address=300,
        api_address=1_200,
        heavy_user=10,
        write_user=120,
        read_user=600,
    )
    limiter = RateLimiter(primary=store, fallback=InProcessCounterStore(max_keys=1_000), clock=FakeClock())
    return RateLimitRuntime(mode=mode, limiter=limiter, rules=RuleSet.from_limits(limits), trusted_networks=())


def http_request(method: str = "POST", path: str = "/api/auth/login", client=("203.0.113.9", 50_000)) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": client,
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
    }
    request = Request(scope)
    request.state.request_id = "request-under-test"
    return request


@pytest.fixture
def install_runtime():
    original = policy_module._runtime

    def install(runtime):
        policy_module.set_runtime(runtime)
        return runtime

    yield install
    policy_module.set_runtime(original)


def test_evaluate_runs_the_store_on_a_worker_thread_not_the_loop_thread():
    store = ThreadRecordingStore()
    runtime = make_runtime(store)
    rule = runtime.rules.api_address
    asyncio.run(evaluate(runtime, http_request(), [(rule, "address:203.0.113.9")], "POST /api/auth/login"))
    assert len(store.threads) == 1
    assert store.threads[0] != threading.get_ident()


def test_a_slow_store_does_not_hold_up_the_event_loop():
    store = ThreadRecordingStore(delay=0.3)
    runtime = make_runtime(store)
    rule = runtime.rules.api_address
    marks: dict[str, float] = {}

    async def ticker():
        await asyncio.sleep(0.02)
        marks["tick"] = time.monotonic()

    async def scenario():
        await asyncio.gather(
            evaluate(runtime, http_request(), [(rule, "address:203.0.113.9")], "POST /api/auth/login"),
            ticker(),
        )
        marks["done"] = time.monotonic()

    asyncio.run(scenario())
    # The 0.3 s store call did not block the 0.02 s timer: the timer finished while the store was still working.
    assert marks["tick"] < marks["done"] - 0.2


def test_login_username_check_runs_off_the_loop_and_enforces_the_limit(install_runtime):
    store = ThreadRecordingStore()
    install_runtime(make_runtime(store, login_username=2))
    for _ in range(2):
        asyncio.run(enforce_login_username_limit(http_request(), "ops-user"))
    with pytest.raises(RateLimitExceeded):
        asyncio.run(enforce_login_username_limit(http_request(), "OPS-user"))
    assert store.threads
    assert all(thread != threading.get_ident() for thread in store.threads)


def test_mode_off_never_reaches_the_store_or_a_worker_thread(install_runtime):
    store = ThreadRecordingStore()
    install_runtime(make_runtime(store, mode="off", login_username=1))
    for _ in range(5):
        asyncio.run(enforce_login_username_limit(http_request(), "ops-user"))
    assert store.threads == []


def test_report_mode_checks_off_the_loop_but_never_raises(install_runtime):
    store = ThreadRecordingStore()
    install_runtime(make_runtime(store, mode="report", login_username=1))
    for _ in range(3):
        asyncio.run(enforce_login_username_limit(http_request(), "ops-user"))
    assert len(store.threads) == 3
    assert all(thread != threading.get_ident() for thread in store.threads)
