"""Rate limiting through the real application stack.

The database is in-memory SQLite and Redis is a fake, both behind injected doubles.
Each test installs its own runtime (mode, limits, trusted proxies, fake clock) and
restores the previous one afterwards.
"""

import logging
import re
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import app as application
from config import settings
from config.database import Base, get_db
from models.models import ErrorLog
from services.auth_service import AuthenticationService
from services.rate_limit import policy as policy_module
from services.rate_limit.client_ip import parse_trusted_networks
from services.rate_limit.limiter import InProcessCounterStore, RateLimiter, RedisCounterStore
from services.rate_limit.policy import RateLimitRuntime, RateLimits, RuleSet
from tests.rate_limit_support import FakeClock, FakeRedis

PASSWORD = "SecurePassword123!"
WRONG_PASSWORD = "WrongPassword123!"
ORIGIN = settings.CORS_ORIGINS[0]
GATEWAY = "10.218.10.5"
# The tests own their limits. They do not read the settings defaults, so changing a default never changes these tests.
TEST_LIMITS = RateLimits(
    login_address=10,
    login_username=5,
    refresh_address=30,
    api_address=1200,
    heavy_user=10,
    write_user=120,
    read_user=600,
)
RETRY_MESSAGE = re.compile(r"^Too many requests\. Try again in [1-9]\d* seconds?\.$")


def make_runtime(mode="enforce", *, limits=TEST_LIMITS, trusted=(), clock=None):
    clock = clock or FakeClock()
    fake = FakeRedis(clock)
    limiter = RateLimiter(
        primary=RedisCounterStore(fake),
        fallback=InProcessCounterStore(max_keys=10_000),
        clock=clock,
    )
    return RateLimitRuntime(
        mode=mode,
        limiter=limiter,
        rules=RuleSet.from_limits(limits),
        trusted_networks=parse_trusted_networks(trusted),
    )


@pytest.fixture
def install_runtime():
    original = policy_module._runtime

    def install(runtime):
        policy_module.set_runtime(runtime)
        return runtime

    yield install
    policy_module.set_runtime(original)


@pytest.fixture
def world():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()

    def override_db():
        yield session

    # When Socket.IO wraps the app, the FastAPI instance (and its overrides) sits one level down.
    fastapi_app = getattr(application, "other_asgi_app", application)
    fastapi_app.dependency_overrides[get_db] = override_db
    for username in ("rl-alice", "rl-bob"):
        AuthenticationService.create_user(session, username, f"{username}@example.invalid", PASSWORD, "Admin")
    try:
        yield SimpleNamespace(db=session, client=TestClient(application))
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)
        session.close()
        engine.dispose()


def token_for(db, username):
    return AuthenticationService.authenticate_user(db, username, PASSWORD)


def post_login(client, username, headers=None, peer_client=None):
    target = peer_client or client
    return target.post(
        "/api/auth/login",
        json={"username": username, "password": WRONG_PASSWORD},
        headers=headers or {},
    )


def assert_standard_rate_limit_body(response, code="rate_limited"):
    body = response.json()
    assert body["success"] is False
    assert body["code"] == code
    assert RETRY_MESSAGE.match(body["message"]), body["message"]
    assert body["detail"] == body["message"]
    assert isinstance(body["retry_after_seconds"], int) and body["retry_after_seconds"] >= 1
    assert body["request_id"]
    # Nothing internal leaks: no rule name, counter key, address or subject digest.
    serialized = str(body)
    for internal in ("login_address", "pms:rl", "testclient", "address:", "user:"):
        assert internal not in serialized
    return body


def test_eleventh_login_in_a_minute_is_rejected_with_retry_after_and_standard_body(world, install_runtime):
    install_runtime(make_runtime())
    for index in range(10):
        assert post_login(world.client, f"user-{index:03d}").status_code == 401

    response = post_login(world.client, "user-010", headers={"Origin": ORIGIN})
    assert response.status_code == 429
    body = assert_standard_rate_limit_body(response)
    assert response.headers["retry-after"] == str(body["retry_after_seconds"])
    assert response.headers["ratelimit-limit"] == "10"
    assert response.headers["ratelimit-remaining"] == "0"
    assert int(response.headers["ratelimit-reset"]) >= 1
    assert response.headers["x-request-id"] == body["request_id"]
    # CORS still applies to the rejection, and the budget headers are readable by the browser.
    assert response.headers["access-control-allow-origin"] == ORIGIN
    exposed = response.headers["access-control-expose-headers"].lower()
    for header in ("retry-after", "ratelimit-limit", "ratelimit-remaining", "ratelimit-reset"):
        assert header in exposed


def test_limited_class_responses_carry_budget_headers_even_when_allowed(world, install_runtime):
    install_runtime(make_runtime())
    response = post_login(world.client, "user-allowed")
    assert response.status_code == 401
    assert response.headers["ratelimit-limit"] == "10"
    assert response.headers["ratelimit-remaining"] == "9"
    assert "retry-after" not in response.headers


def test_per_username_rule_is_enforced_inside_the_login_route(world, install_runtime):
    install_runtime(make_runtime())
    for _ in range(5):
        assert post_login(world.client, "ghost-user").status_code == 401

    # Same username, different case: the same counter, and the sixth attempt is refused by the route.
    sixth = post_login(world.client, "GHOST-user")
    assert sixth.status_code == 429
    assert_standard_rate_limit_body(sixth)
    assert sixth.headers["retry-after"]
    assert sixth.headers["ratelimit-remaining"] == "0"

    # A different username from the same address is not affected by that counter.
    assert post_login(world.client, "other-user").status_code == 401


def test_username_rule_runs_before_any_credential_check_and_is_not_a_500(world, install_runtime):
    install_runtime(make_runtime())
    for _ in range(5):
        post_login(world.client, "ghost-user")
    response = post_login(world.client, "ghost-user")
    assert response.status_code == 429
    assert response.status_code != 500


def test_refresh_is_limited_to_thirty_per_minute_per_address(world, install_runtime):
    install_runtime(make_runtime())
    statuses = [world.client.post("/api/auth/refresh").status_code for _ in range(30)]
    assert 429 not in statuses
    response = world.client.post("/api/auth/refresh")
    assert response.status_code == 429
    assert_standard_rate_limit_body(response)


def test_exempt_paths_are_never_limited_and_do_not_use_the_budget(world, install_runtime):
    install_runtime(make_runtime(limits=replace(TEST_LIMITS, api_address=2)))
    for _ in range(5):
        assert world.client.get("/api/health").status_code != 429
        assert world.client.get("/").status_code != 429
        assert world.client.options("/api/auth/login").status_code != 429
    # The budget of two is still intact for ordinary API traffic.
    assert world.client.get("/api/auth/me").status_code == 401
    assert world.client.get("/api/auth/me").status_code == 401
    assert world.client.get("/api/auth/me").status_code == 429


def test_unauthenticated_401s_count_against_the_address_ceiling(world, install_runtime):
    install_runtime(make_runtime(limits=replace(TEST_LIMITS, api_address=3)))
    assert [world.client.get("/api/auth/me").status_code for _ in range(3)] == [401, 401, 401]
    response = world.client.get("/api/auth/me")
    assert response.status_code == 429
    assert_standard_rate_limit_body(response)


def test_authenticated_read_write_and_heavy_classes_are_limited_per_user_and_isolated(world, install_runtime):
    limits = replace(TEST_LIMITS, read_user=3, write_user=2, heavy_user=1)
    install_runtime(make_runtime(limits=limits))
    alice = {"Authorization": f"Bearer {token_for(world.db, 'rl-alice')}"}
    bob = {"Authorization": f"Bearer {token_for(world.db, 'rl-bob')}"}

    reads = [world.client.get("/api/auth/me", headers=alice).status_code for _ in range(3)]
    assert 429 not in reads
    limited_read = world.client.get("/api/auth/me", headers=alice)
    assert limited_read.status_code == 429
    assert_standard_rate_limit_body(limited_read)
    assert world.client.get("/api/auth/me", headers=bob).status_code != 429

    writes = [world.client.post("/api/users/notifications/read-all", headers=alice).status_code for _ in range(2)]
    assert 429 not in writes
    assert world.client.post("/api/users/notifications/read-all", headers=alice).status_code == 429
    # Reads do not spend the write budget, and writes do not spend the read budget.
    assert world.client.post("/api/users/notifications/read-all", headers=bob).status_code != 429

    assert world.client.post("/api/uploads/pms", headers=alice).status_code != 429
    limited_heavy = world.client.post("/api/uploads/pms", headers=alice)
    assert limited_heavy.status_code == 429
    assert_standard_rate_limit_body(limited_heavy)
    assert world.client.post("/api/uploads/pms", headers=bob).status_code != 429


def test_a_429_never_creates_an_error_log_row(world, install_runtime):
    install_runtime(make_runtime())
    for index in range(12):
        post_login(world.client, f"log-user-{index:03d}")
    responses = [post_login(world.client, "log-user-final") for _ in range(2)]
    assert all(response.status_code == 429 for response in responses)
    assert world.db.query(ErrorLog).count() == 0


def test_off_mode_never_limits_and_adds_no_budget_headers(world, install_runtime):
    install_runtime(make_runtime(mode="off"))
    statuses = [post_login(world.client, f"off-user-{index:03d}").status_code for index in range(15)]
    assert 429 not in statuses
    response = post_login(world.client, "off-user-final")
    assert "ratelimit-limit" not in response.headers


def test_report_mode_logs_would_be_rejections_and_answers_normally(world, install_runtime, caplog):
    install_runtime(make_runtime(mode="report"))
    with caplog.at_level(logging.WARNING, logger="services.rate_limit.enforcement"):
        statuses = [post_login(world.client, f"report-user-{index:03d}").status_code for index in range(12)]
    assert 429 not in statuses
    assert statuses == [401] * 12
    warnings = [record.getMessage() for record in caplog.records if "would be rejected" in record.getMessage()]
    assert warnings, "report mode did not log the would-be rejection"
    assert "rule=login_address" in warnings[0]


def test_logs_never_contain_the_raw_address_or_username(world, install_runtime, caplog):
    install_runtime(make_runtime())
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            post_login(world.client, "secret-operator")
        post_login(world.client, "secret-operator")
        for index in range(11):
            post_login(world.client, f"flood-{index:03d}")
    messages = [record.getMessage() for record in caplog.records if "Rate limit" in record.getMessage()]
    assert messages, "no rejection was logged"
    joined = "\n".join(messages)
    assert "rule=" in joined and "subject=" in joined
    assert "secret-operator" not in joined
    assert "testclient" not in joined


def test_forwarded_for_is_honored_only_from_a_trusted_gateway(world, install_runtime):
    install_runtime(make_runtime(trusted=["10.218.10.0/24"]))
    gateway = TestClient(application, client=(GATEWAY, 40000))
    # Distinct real clients behind the gateway each get their own budget.
    for index in range(11):
        response = post_login(gateway, f"behind-gateway-{index:03d}", headers={"X-Forwarded-For": f"203.0.113.{index + 1}"})
        assert response.status_code == 401, index
    # One real client sending many requests is limited, whatever the spoofed left-most value.
    statuses = []
    for index in range(11):
        spoofed = f"198.18.0.{index + 1}, 203.0.113.200"
        statuses.append(post_login(gateway, f"one-client-{index:03d}", headers={"X-Forwarded-For": spoofed}).status_code)
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429


def test_forwarded_for_from_an_untrusted_peer_is_ignored(world, install_runtime):
    install_runtime(make_runtime(trusted=["10.218.10.0/24"]))
    outsider = TestClient(application, client=("198.51.100.7", 40001))
    statuses = []
    for index in range(11):
        headers = {"X-Forwarded-For": f"203.0.113.{index + 1}"}
        statuses.append(post_login(outsider, f"outsider-{index:03d}", headers=headers).status_code)
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429


def test_no_trusted_proxies_configured_means_the_peer_is_always_the_subject(world, install_runtime):
    install_runtime(make_runtime(trusted=[]))
    gateway = TestClient(application, client=(GATEWAY, 40002))
    statuses = [
        post_login(gateway, f"no-trust-{index:03d}", headers={"X-Forwarded-For": f"203.0.113.{index + 1}"}).status_code
        for index in range(11)
    ]
    assert statuses[10] == 429


def test_the_test_profile_defaults_to_off_so_the_existing_suite_is_unaffected():
    assert settings.APP_ENV == "test"
    assert settings.PMS_RATE_LIMIT_MODE == "off"


class CountingStore:
    """Counts store calls, to show that off mode and exempt paths never reach the store."""

    def __init__(self, clock) -> None:
        self.calls = 0
        self._inner = FakeRedis(clock)
        self._counting = RedisCounterStore(self._inner)

    def increment_many(self, items, now):
        self.calls += 1
        return self._counting.increment_many(items, now)


def make_counting_runtime(mode="enforce", *, limits=TEST_LIMITS):
    clock = FakeClock()
    store = CountingStore(clock)
    limiter = RateLimiter(primary=store, fallback=InProcessCounterStore(max_keys=10_000), clock=clock)
    runtime = RateLimitRuntime(
        mode=mode,
        limiter=limiter,
        rules=RuleSet.from_limits(limits),
        trusted_networks=parse_trusted_networks([]),
    )
    return runtime, store


def test_off_mode_and_exempt_paths_never_reach_the_store(world, install_runtime):
    runtime, store = make_counting_runtime(mode="off")
    install_runtime(runtime)
    for index in range(3):
        post_login(world.client, f"off-store-{index}")
    assert store.calls == 0

    runtime, store = make_counting_runtime(mode="enforce")
    install_runtime(runtime)
    for _ in range(3):
        world.client.get("/api/health")
        world.client.get("/")
        world.client.options("/api/auth/login")
    assert store.calls == 0


def test_each_check_is_one_store_round_trip_regardless_of_how_many_rules_it_covers(world, install_runtime):
    runtime, store = make_counting_runtime(mode="enforce")
    install_runtime(runtime)
    # A non-login API request is one check: the address ceiling, in a single round trip.
    world.client.get("/api/auth/me")
    assert store.calls == 1
    # A login is two checks. The address rules run in the middleware, and the per-username rule runs in
    # the route, because it needs the parsed body. Each check is still one round trip.
    store.calls = 0
    post_login(world.client, "one-call-user")
    assert store.calls == 2
