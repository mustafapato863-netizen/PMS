"""Rate-limit rules, route classes and the runtime the middleware reads per request.

Pre-auth rules are keyed by client address. Post-auth rules are keyed by the
authenticated user id. The runtime is built lazily from settings, so importing
the application never touches Redis. Tests replace it with set_runtime().
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from enum import Enum

from services.rate_limit.client_ip import IPNetwork, parse_trusted_networks
from services.rate_limit.limiter import (
    InProcessCounterStore,
    RateLimiter,
    RateRule,
    RedisCounterStore,
)

WINDOW_SECONDS = 60
MODES = frozenset({"off", "report", "enforce"})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
API_PREFIX_LABEL = "/api/*"


class RouteClass(str, Enum):
    HEAVY = "heavy"
    WRITE = "write"
    READ = "read"


@dataclass(frozen=True)
class RateLimits:
    login_address: int
    login_username: int
    refresh_address: int
    api_address: int
    heavy_user: int
    write_user: int
    read_user: int


@dataclass(frozen=True)
class RuleSet:
    login_address: RateRule
    login_username: RateRule
    refresh_address: RateRule
    api_address: RateRule
    heavy_user: RateRule
    write_user: RateRule
    read_user: RateRule

    @classmethod
    def from_limits(cls, limits: RateLimits) -> RuleSet:
        return cls(
            login_address=RateRule("login_address", limits.login_address, WINDOW_SECONDS),
            login_username=RateRule("login_username", limits.login_username, WINDOW_SECONDS),
            refresh_address=RateRule("refresh_address", limits.refresh_address, WINDOW_SECONDS),
            api_address=RateRule("api_address", limits.api_address, WINDOW_SECONDS),
            heavy_user=RateRule("heavy_user", limits.heavy_user, WINDOW_SECONDS),
            write_user=RateRule("write_user", limits.write_user, WINDOW_SECONDS),
            read_user=RateRule("read_user", limits.read_user, WINDOW_SECONDS),
        )


@dataclass(frozen=True)
class RateLimitRuntime:
    mode: str
    limiter: RateLimiter
    rules: RuleSet
    trusted_networks: tuple[IPNetwork, ...]


# Heavy operations: workbook ingestion, evaluation calculation and apply, and report
# generation or export. Matched on method plus a full path, after removing any trailing slash.
# The label is the path template written to logs.
HEAVY_ROUTES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("POST", re.compile(r"^/api/uploads/pms$"), "POST /api/uploads/pms"),
    ("POST", re.compile(r"^/api/performance/balanced-scorecard/template/upload$"), "POST /api/performance/balanced-scorecard/template/upload"),
    ("POST", re.compile(r"^/api/settings/corrective-actions/import$"), "POST /api/settings/corrective-actions/import"),
    ("GET", re.compile(r"^/api/settings/corrective-actions/export$"), "GET /api/settings/corrective-actions/export"),
    ("GET", re.compile(r"^/api/performance/export$"), "GET /api/performance/export"),
    ("GET", re.compile(r"^/api/settings/data-snapshot/export$"), "GET /api/settings/data-snapshot/export"),
    ("POST", re.compile(r"^/api/settings/data-snapshot/import$"), "POST /api/settings/data-snapshot/import"),
    ("POST", re.compile(r"^/api/settings/data-snapshot/import/dry-run$"), "POST /api/settings/data-snapshot/import/dry-run"),
    ("POST", re.compile(r"^/api/reports/preview$"), "POST /api/reports/preview"),
    ("POST", re.compile(r"^/api/reports/generate$"), "POST /api/reports/generate"),
    ("POST", re.compile(r"^/api/reports/story/drafts/[^/]+/generate$"), "POST /api/reports/story/drafts/{id}/generate"),
    ("POST", re.compile(r"^/api/reports/story/drafts/[^/]+/narratives/regenerate$"), "POST /api/reports/story/drafts/{id}/narratives/regenerate"),
    ("GET", re.compile(r"^/api/reports/[^/]+/download$"), "GET /api/reports/{id}/download"),
    ("POST", re.compile(r"^/api/settings/evaluation/drafts/[^/]+/impact-preview$"), "POST /api/settings/evaluation/drafts/{id}/impact-preview"),
    ("POST", re.compile(r"^/api/settings/evaluation/apply$"), "POST /api/settings/evaluation/apply"),
    ("POST", re.compile(r"^/api/settings/evaluation/apply-jobs$"), "POST /api/settings/evaluation/apply-jobs"),
    ("POST", re.compile(r"^/api/settings/evaluation/apply-jobs/[^/]+/(cancel|retry|recover)$"), "POST /api/settings/evaluation/apply-jobs/{id}/{action}"),
    ("POST", re.compile(r"^/api/settings/evaluation/revisions/[^/]+/rollback$"), "POST /api/settings/evaluation/revisions/{id}/rollback"),
    ("GET", re.compile(r"^/api/settings/evaluation/versions/[^/]+/export$"), "GET /api/settings/evaluation/versions/{id}/export"),
)


def normalized_path(path: str) -> str:
    return path.rstrip("/") or "/"


def is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def is_exempt(method: str, path: str) -> bool:
    """Never limited: preflight, health, the API docs and the root."""
    if method == "OPTIONS":
        return True
    if path == "/" or path in {"/docs", "/openapi.json"}:
        return True
    return path == "/api/health" or path.startswith("/api/health/")


def classify_user_route(method: str, path: str) -> tuple[RouteClass, str]:
    normalized = normalized_path(path)
    for route_method, pattern, label in HEAVY_ROUTES:
        if method == route_method and pattern.match(normalized):
            return RouteClass.HEAVY, label
    if method in WRITE_METHODS:
        return RouteClass.WRITE, f"{method} {API_PREFIX_LABEL}"
    return RouteClass.READ, f"{method} {API_PREFIX_LABEL}"


def pre_auth_checks(method: str, path: str, address: str, rules: RuleSet) -> list[tuple[RateRule, str]]:
    """Address rules for /api requests. Every request counts, authenticated or not."""
    if not is_api_path(path) or is_exempt(method, path):
        return []
    subject = f"address:{address}"
    checks = [(rules.api_address, subject)]
    normalized = normalized_path(path)
    if method == "POST" and normalized == "/api/auth/login":
        checks.append((rules.login_address, subject))
    elif method == "POST" and normalized == "/api/auth/refresh":
        checks.append((rules.refresh_address, subject))
    return checks


def pre_auth_label(method: str, path: str) -> str:
    normalized = normalized_path(path)
    if method == "POST" and normalized == "/api/auth/login":
        return "POST /api/auth/login"
    if method == "POST" and normalized == "/api/auth/refresh":
        return "POST /api/auth/refresh"
    return f"{method} {API_PREFIX_LABEL}"


def post_auth_check(method: str, path: str, user_id: str, rules: RuleSet) -> tuple[RateRule, str, str] | None:
    """Per-user rule for an authenticated /api request, as (rule, subject, route label)."""
    if not is_api_path(path) or is_exempt(method, path):
        return None
    route_class, label = classify_user_route(method, path)
    rule = {
        RouteClass.HEAVY: rules.heavy_user,
        RouteClass.WRITE: rules.write_user,
        RouteClass.READ: rules.read_user,
    }[route_class]
    return rule, f"user:{user_id}", label


def login_username_subject(address: str, username: str) -> str:
    return f"login-user:{address}|{username.strip().lower()}"


def build_runtime_from_settings() -> RateLimitRuntime:
    from config import settings
    from services.redis_provider import redis_client

    if settings.PMS_RATE_LIMIT_MODE not in MODES:
        raise ValueError("PMS_RATE_LIMIT_MODE must be off, report, or enforce.")
    limits = RateLimits(
        login_address=settings.PMS_RATE_LIMIT_LOGIN_PER_MINUTE,
        login_username=settings.PMS_RATE_LIMIT_LOGIN_USERNAME_PER_MINUTE,
        refresh_address=settings.PMS_RATE_LIMIT_REFRESH_PER_MINUTE,
        api_address=settings.PMS_RATE_LIMIT_API_PER_MINUTE,
        heavy_user=settings.PMS_RATE_LIMIT_HEAVY_PER_MINUTE,
        write_user=settings.PMS_RATE_LIMIT_WRITE_PER_MINUTE,
        read_user=settings.PMS_RATE_LIMIT_READ_PER_MINUTE,
    )
    limiter = RateLimiter(
        primary=RedisCounterStore(redis_client) if settings.REDIS_URL else None,
        fallback=InProcessCounterStore(max_keys=settings.PMS_RATE_LIMIT_FALLBACK_MAX_KEYS),
        clock=time.time,
        # After a Redis failure the primary is skipped for the same interval the Redis proxy uses to retry connecting.
        cool_down_seconds=settings.REDIS_RETRY_INTERVAL_SECONDS,
    )
    return RateLimitRuntime(
        mode=settings.PMS_RATE_LIMIT_MODE,
        limiter=limiter,
        rules=RuleSet.from_limits(limits),
        trusted_networks=parse_trusted_networks(settings.PMS_TRUSTED_PROXY_CIDRS),
    )


_runtime: RateLimitRuntime | None = None
_runtime_lock = threading.Lock()


def get_runtime() -> RateLimitRuntime:
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:
                _runtime = build_runtime_from_settings()
    return _runtime


def set_runtime(runtime: RateLimitRuntime | None) -> RateLimitRuntime | None:
    """Replace the runtime (tests). Returns the previous one so it can be restored."""
    global _runtime
    with _runtime_lock:
        previous = _runtime
        _runtime = runtime
    return previous
