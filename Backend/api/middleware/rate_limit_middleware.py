"""Rate limiting middleware.

Two enforcement points:
- RateLimitPreAuthMiddleware runs before AuthMiddleware. It applies the address
  rules to every /api request, so unauthenticated 401s count too.
- RateLimitPostAuthMiddleware runs after AuthMiddleware. It applies the per-user
  rules from request.state.user, which only exists once the token is valid.

Login's per-username rule runs inside the login route, because it needs the
parsed body, and it is not a middleware.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from services.rate_limit.enforcement import (
    apply_rate_limit_headers,
    client_address_for,
    evaluate,
    rate_limited_response,
)
from services.rate_limit.policy import (
    get_runtime,
    is_api_path,
    is_exempt,
    post_auth_check,
    pre_auth_checks,
    pre_auth_label,
)


class RateLimitPreAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        runtime = get_runtime()
        if runtime.mode == "off":
            return await call_next(request)

        method = request.method
        path = request.url.path
        address = client_address_for(request, runtime)
        checks = pre_auth_checks(method, path, address, runtime.rules)
        if not checks:
            return await call_next(request)

        verdict = await evaluate(runtime, request, checks, pre_auth_label(method, path))
        if verdict.blocked and runtime.mode == "enforce":
            return rate_limited_response(request, verdict)

        response = await call_next(request)
        # Set as a default so a per-user decision from the inner middleware is not overwritten.
        apply_rate_limit_headers(response, verdict, keep_existing=True)
        return response


class RateLimitPostAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        runtime = get_runtime()
        if runtime.mode == "off":
            return await call_next(request)

        user = getattr(request.state, "user", None)
        if not isinstance(user, dict) or user.get("legacy_unscoped") or not user.get("user_id"):
            return await call_next(request)

        method = request.method
        path = request.url.path
        if not is_api_path(path) or is_exempt(method, path):
            return await call_next(request)
        check = post_auth_check(method, path, str(user["user_id"]), runtime.rules)
        if check is None:
            return await call_next(request)

        rule, subject, label = check
        verdict = await evaluate(runtime, request, [(rule, subject)], label)
        if verdict.blocked and runtime.mode == "enforce":
            return rate_limited_response(request, verdict)

        response = await call_next(request)
        apply_rate_limit_headers(response, verdict)
        return response
