"""Verdicts, the 429 response, rejection logging, and the route-level login rule.

The response body names the action plainly and never carries a rule name, a
counter key, an address or a username. Rejections are logged as warnings with
the hashed subject only. They are not written to the ErrorLog table, because a
429 is a client condition rather than a server error.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from services.rate_limit.client_ip import client_address
from services.rate_limit.limiter import RateRule, RuleDecision
from services.rate_limit.policy import (
    WINDOW_SECONDS,
    RateLimitRuntime,
    get_runtime,
    login_username_subject,
)

logger = logging.getLogger(__name__)

RATE_LIMIT_HEADERS = ("Retry-After", "RateLimit-Limit", "RateLimit-Remaining", "RateLimit-Reset")


@dataclass(frozen=True)
class Verdict:
    decisions: tuple[RuleDecision, ...]

    @property
    def blocked(self) -> bool:
        return any(not decision.allowed for decision in self.decisions)

    @property
    def retry_after_seconds(self) -> int:
        exceeded = [decision.reset_seconds for decision in self.decisions if not decision.allowed]
        return max(exceeded, default=1)

    @property
    def headline(self) -> RuleDecision | None:
        """The decision the RateLimit headers describe: the exceeded rule with the longest wait, else the tightest rule."""
        if not self.decisions:
            return None
        if self.blocked:
            return max(
                (decision for decision in self.decisions if not decision.allowed),
                key=lambda decision: decision.reset_seconds,
            )
        return min(self.decisions, key=lambda decision: decision.remaining)


class RateLimitExceeded(Exception):
    """Raised from inside a route, such as the login username rule, and answered by a registered handler."""

    def __init__(self, verdict: Verdict) -> None:
        super().__init__("rate limited")
        self.verdict = verdict


def client_address_for(request: Request, runtime: RateLimitRuntime) -> str:
    peer = request.client.host if request.client else None
    return client_address(peer, request.headers.get("x-forwarded-for"), runtime.trusted_networks)


def request_id_for(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _rule_name(rule: RateRule) -> str:
    return rule.name


def log_rejection(runtime: RateLimitRuntime, verdict: Verdict, request: Request, route_label: str) -> None:
    decision = verdict.headline
    if decision is None:
        return
    outcome = "rejected" if runtime.mode == "enforce" else "would be rejected"
    logger.warning(
        "Rate limit %s rule=%s route=%s method=%s request_id=%s subject=%s retry_after=%s",
        outcome,
        _rule_name(decision.rule),
        route_label,
        request.method,
        request_id_for(request),
        decision.subject_digest,
        verdict.retry_after_seconds,
    )


async def evaluate(
    runtime: RateLimitRuntime,
    request: Request,
    checks: Sequence[tuple[RateRule, str]],
    route_label: str,
) -> Verdict:
    # The store round trip is blocking I/O. It runs in the threadpool so that one slow Redis
    # cannot stall the event loop, which serves every request in this single-process deployment.
    verdict = Verdict(await run_in_threadpool(runtime.limiter.check, checks))
    if verdict.blocked:
        log_rejection(runtime, verdict, request, route_label)
    return verdict


def apply_rate_limit_headers(response, verdict: Verdict, *, keep_existing: bool = False) -> None:
    headline = verdict.headline
    if headline is None:
        return
    values = {
        "RateLimit-Limit": str(headline.rule.limit),
        "RateLimit-Remaining": str(headline.remaining),
        "RateLimit-Reset": str(headline.reset_seconds),
    }
    if verdict.blocked:
        values["Retry-After"] = str(verdict.retry_after_seconds)
    for name, value in values.items():
        if keep_existing:
            response.headers.setdefault(name, value)
        else:
            response.headers[name] = value


def rate_limited_response(request: Request, verdict: Verdict) -> JSONResponse:
    retry_after = verdict.retry_after_seconds
    unit = "second" if retry_after == 1 else "seconds"
    message = f"Too many requests. Try again in {retry_after} {unit}."
    response = JSONResponse(
        status_code=429,
        content={
            "success": False,
            "message": message,
            "detail": message,
            "request_id": request_id_for(request),
            "code": "rate_limited",
            "retry_after_seconds": retry_after,
        },
    )
    apply_rate_limit_headers(response, verdict)
    return response


async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return rate_limited_response(request, exc.verdict)


async def enforce_login_username_limit(request: Request, username: str) -> None:
    """Per (address, username) rule for login. Called from the route after validation and before any credential check.

    Raises RateLimitExceeded only in enforce mode. Report mode logs and continues.
    """
    runtime = get_runtime()
    if runtime.mode == "off":
        return
    address = client_address_for(request, runtime)
    checks = [(runtime.rules.login_username, login_username_subject(address, username))]
    verdict = await evaluate(runtime, request, checks, "POST /api/auth/login")
    if verdict.blocked and runtime.mode == "enforce":
        raise RateLimitExceeded(verdict)


# Route-level per-user rule for GET /api/performance/summary-records: a full
# response can be tens of thousands of resolved rows, so it gets its own budget
# on top of the global read rule. Same store, mode and 429 response as above.
SUMMARY_RECORDS_PER_MINUTE = 30
SUMMARY_RECORDS_RULE = RateRule("summary_records_user", SUMMARY_RECORDS_PER_MINUTE, WINDOW_SECONDS)


def enforce_user_route_limit(request: Request, rule: RateRule, route_label: str) -> None:
    """Synchronous per-user check for ``def`` routes (already in the threadpool).

    Raises RateLimitExceeded only in enforce mode; report mode logs and continues.
    """
    runtime = get_runtime()
    if runtime.mode == "off":
        return
    user = getattr(request.state, "user", None)
    user_id = str(user.get("user_id") or "") if isinstance(user, dict) else ""
    if not user_id:
        return
    verdict = Verdict(runtime.limiter.check([(rule, f"user:{user_id}")]))
    if verdict.blocked:
        log_rejection(runtime, verdict, request, route_label)
        if runtime.mode == "enforce":
            raise RateLimitExceeded(verdict)
