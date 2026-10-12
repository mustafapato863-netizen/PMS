"""Path classes, the exempt list, and the middleware order. Changing any of them should fail here first."""

import pytest

from app import app as application
from services.rate_limit.policy import (
    RouteClass,
    classify_user_route,
    is_exempt,
    post_auth_check,
    RuleSet,
    RateLimits,
)

HEAVY_CASES = [
    ("POST", "/api/uploads/pms"),
    ("POST", "/api/uploads/pms/"),
    ("POST", "/api/performance/balanced-scorecard/template/upload"),
    ("POST", "/api/settings/corrective-actions/import"),
    ("GET", "/api/settings/corrective-actions/export"),
    ("GET", "/api/performance/export"),
    ("POST", "/api/reports/preview"),
    ("POST", "/api/reports/generate"),
    ("POST", "/api/reports/story/drafts/d1/generate"),
    ("POST", "/api/reports/story/drafts/d1/narratives/regenerate"),
    ("GET", "/api/reports/r1/download"),
    ("POST", "/api/settings/evaluation/drafts/v1/impact-preview"),
    ("POST", "/api/settings/evaluation/apply"),
    ("POST", "/api/settings/evaluation/apply-jobs"),
    ("POST", "/api/settings/evaluation/apply-jobs/j1/cancel"),
    ("POST", "/api/settings/evaluation/apply-jobs/j1/retry"),
    ("POST", "/api/settings/evaluation/apply-jobs/j1/recover"),
    ("POST", "/api/settings/evaluation/revisions/r1/rollback"),
    ("GET", "/api/settings/evaluation/versions/v1/export"),
]

NOT_HEAVY_CASES = [
    # Reads of cheap, stored data. A static template file is served, not generated.
    ("GET", "/api/performance/balanced-scorecard/template/download", RouteClass.READ),
    ("GET", "/api/reports/story/drafts/d1", RouteClass.READ),
    ("GET", "/api/reports/center", RouteClass.READ),
    ("GET", "/api/apply-jobs-anything", RouteClass.READ),
    ("GET", "/api/settings/evaluation/apply-jobs", RouteClass.READ),
    ("GET", "/api/settings/evaluation/apply-jobs/j1", RouteClass.READ),
    ("GET", "/api/uploads/", RouteClass.READ),
    # Writes that are not heavy.
    ("POST", "/api/settings/evaluation/drafts/v1/preview", RouteClass.WRITE),
    ("POST", "/api/settings/evaluation/jobs/v1/preview", RouteClass.WRITE),
    ("POST", "/api/uploads/batch-delete", RouteClass.WRITE),
    ("POST", "/api/reports/story/drafts", RouteClass.WRITE),
    ("PUT", "/api/reports/story/drafts/d1", RouteClass.WRITE),
    ("PATCH", "/api/settings/evaluation/drafts/v1", RouteClass.WRITE),
    ("DELETE", "/api/uploads/u1", RouteClass.WRITE),
    ("POST", "/api/auth/logout", RouteClass.WRITE),
]


@pytest.mark.parametrize(("method", "path"), HEAVY_CASES)
def test_listed_heavy_paths_are_heavy(method, path):
    route_class, label = classify_user_route(method, path)
    assert route_class is RouteClass.HEAVY, (method, path, label)


@pytest.mark.parametrize(("method", "path", "expected"), NOT_HEAVY_CASES)
def test_other_paths_are_read_or_write(method, path, expected):
    route_class, _ = classify_user_route(method, path)
    assert route_class is expected


def test_post_auth_rule_follows_the_class():
    rules = RuleSet.from_limits(RateLimits(
        login_address=10, login_username=5, refresh_address=30, api_address=1200,
        heavy_user=10, write_user=120, read_user=600,
    ))
    assert post_auth_check("POST", "/api/uploads/pms", "u1", rules)[0] is rules.heavy_user
    assert post_auth_check("POST", "/api/uploads/batch-delete", "u1", rules)[0] is rules.write_user
    assert post_auth_check("GET", "/api/auth/me", "u1", rules)[0] is rules.read_user
    assert post_auth_check("GET", "/api/health", "u1", rules) is None
    assert post_auth_check("OPTIONS", "/api/auth/me", "u1", rules) is None
    assert post_auth_check("GET", "/not-api", "u1", rules) is None


@pytest.mark.parametrize(("method", "path"), [
    ("OPTIONS", "/api/auth/login"),
    ("GET", "/api/health"),
    ("GET", "/api/health/readiness"),
    ("GET", "/docs"),
    ("GET", "/openapi.json"),
    ("GET", "/"),
])
def test_exempt_paths(method, path):
    assert is_exempt(method, path) is True


def test_api_paths_that_only_look_like_health_are_not_exempt():
    assert is_exempt("GET", "/api/healthcheck-report") is False
    assert is_exempt("POST", "/api/auth/login") is False


def test_middleware_order_is_cors_gzip_errors_preauth_auth_security_postauth():
    fastapi_app = getattr(application, "other_asgi_app", application)
    order = [middleware.cls.__name__ for middleware in fastapi_app.user_middleware]
    assert order == [
        "CORSMiddleware",
        "GZipMiddleware",
        "ErrorHandlingMiddleware",
        "RateLimitPreAuthMiddleware",
        "AuthMiddleware",
        "BaseHTTPMiddleware",
        "RateLimitPostAuthMiddleware",
    ]
