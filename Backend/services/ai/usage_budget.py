"""Server-side concurrency, per-request token, and configurable UTC-day user AI budgets."""
from __future__ import annotations

import contextvars
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from services.ai.llm_client import (
    estimate_tokens,
    routing_timeout_seconds,
    synthesis_timeout_seconds,
)

logger = logging.getLogger(__name__)

_BUDGET_TTL_SECONDS = 48 * 3600  # 48 hours

_state_lock = threading.Lock()
_active_concurrent_requests = 0
_rejected_budget_requests = 0
_daily_user_requests: dict[tuple[str, str], int] = {}
_daily_user_tokens: dict[tuple[str, str], int] = {}
_request_slot_reserved: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "pms_ai_request_slot_reserved", default=False
)


class AiBudgetExceededError(RuntimeError):
    """Raised when an AI concurrency, per-request, or daily user budget is exceeded."""

    def __init__(
        self,
        reason: str,
        retry_after_seconds: int = 60,
        detail: str = "AI usage budget exceeded. Please retry later.",
    ) -> None:
        super().__init__(detail)
        self.reason = reason
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        self.detail = detail


def _read_non_negative_int(env_names: tuple[str, ...], default: int, *, minimum: int = 0, maximum: int = 10_000_000) -> int:
    for name in env_names:
        raw = os.environ.get(name, "").strip()
        if raw:
            try:
                val = int(raw)
                return max(minimum, min(val, maximum))
            except ValueError:
                break
    return default


def max_concurrent_chat_requests() -> int:
    """Maximum simultaneous /api/ai/chat turns allowed per process (default 8)."""
    return _read_non_negative_int(
        ("PMS_AI_MAX_CONCURRENT_CHAT_REQUESTS",),
        8,
        minimum=1,
        maximum=256,
    )


def daily_user_request_limit() -> int:
    """UTC-day per-user request cap. Default 0 = unconfigured / unlimited."""
    return _read_non_negative_int(("PMS_AI_DAILY_USER_REQUEST_LIMIT",), 0, minimum=0)


# Persona-tier budgets from USER_AWARE_360_SPEC §4.7. Used when the access tier
# is widened beyond admin_only, so non-Admin users get progressively smaller caps.
TIER_BUDGETS: dict[str, dict[str, int]] = {
    "global_exec": {"daily_turns": 100, "daily_tokens": 50_000},
    "scoped_manager": {"daily_turns": 50, "daily_tokens": 25_000},
    "self_only": {"daily_turns": 20, "daily_tokens": 10_000},
}


def tier_budget_for_role(role: str | None) -> dict[str, int]:
    """Return the default daily turn/token budget for a role's persona tier."""
    from services.ai.identity_service import PersonaTier, build_passport

    scope = {"role": role or "", "employee_id": None, "has_unrestricted_team_access": role in {"Admin", "General Manager", "Performance Team"}}
    passport = build_passport(scope)
    tier = passport.persona_tier.value
    return TIER_BUDGETS.get(tier, TIER_BUDGETS["self_only"])


def daily_user_token_limit() -> int:
    """UTC-day per-user token cap. Default 0 = unconfigured / unlimited."""
    return _read_non_negative_int(("PMS_AI_DAILY_USER_TOKEN_LIMIT",), 0, minimum=0)


def max_request_input_tokens() -> int:
    """Per-request input token ceiling before external HTTP execution (default 8192)."""
    return _read_non_negative_int(
        ("PMS_AI_MAX_REQUEST_INPUT_TOKENS", "PMS_AI_CONTEXT_TOKENS"),
        8192,
        minimum=1,
        maximum=65536,
    )


def router_timeout_seconds() -> float:
    return routing_timeout_seconds()


def _utc_day_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow - now).total_seconds()))


def _normalized_user_key(user_id: str | None) -> str:
    uid = str(user_id or "").strip()
    return uid if uid else "anonymous"


def _get_healthy_redis():
    try:
        from services.redis_provider import redis_client

        if redis_client:
            return redis_client
    except Exception:
        return None
    return None


def _increment_rejected_count() -> None:
    global _rejected_budget_requests
    with _state_lock:
        _rejected_budget_requests += 1


@contextmanager
def acquire_chat_concurrency_slot() -> Iterator[None]:
    """Acquire a bounded concurrency slot for /api/ai/chat or raise AiBudgetExceededError."""
    global _active_concurrent_requests
    limit = max_concurrent_chat_requests()
    acquired = False
    with _state_lock:
        if _active_concurrent_requests >= limit:
            global _rejected_budget_requests
            _rejected_budget_requests += 1
            raise AiBudgetExceededError(
                reason="concurrency_limit",
                retry_after_seconds=5,
                detail="AI assistant is handling too many concurrent requests. Please retry shortly.",
            )
        _active_concurrent_requests += 1
        acquired = True
    try:
        yield
    finally:
        _request_slot_reserved.set(False)
        if acquired:
            with _state_lock:
                _active_concurrent_requests = max(0, _active_concurrent_requests - 1)


def check_request_token_budget(estimated_input_tokens: int) -> None:
    """Reject oversized prompts before calling external providers."""
    limit = max_request_input_tokens()
    if limit > 0 and estimated_input_tokens > limit:
        _increment_rejected_count()
        raise AiBudgetExceededError(
            reason="request_token_limit",
            retry_after_seconds=60,
            detail=f"Prompt input ({estimated_input_tokens} tokens) exceeds per-request limit ({limit} tokens).",
        )


def _read_daily_counters(uid: str, day: str) -> tuple[int, int]:
    client = _get_healthy_redis()
    if client is not None:
        try:
            req_val = client.get(f"pms:ai:budget:req:{day}:{uid}")
            tok_val = client.get(f"pms:ai:budget:tok:{day}:{uid}")
            return int(req_val or 0), int(tok_val or 0)
        except Exception:
            pass
    with _state_lock:
        return (
            _daily_user_requests.get((day, uid), 0),
            _daily_user_tokens.get((day, uid), 0),
        )


def check_user_daily_budget(
    user_id: str | None,
    user_role: str | None = None,
    *,
    increment_request: bool = True,
) -> None:
    """Enforce configured (>0) UTC-day per-user request and token caps."""
    _ = user_role
    req_limit = daily_user_request_limit()
    tok_limit = daily_user_token_limit()
    if req_limit <= 0 and tok_limit <= 0 and not increment_request:
        return

    uid = _normalized_user_key(user_id)
    day = _utc_day_key()
    retry_after = _seconds_until_utc_midnight()

    _, current_tokens = _read_daily_counters(uid, day)
    if tok_limit > 0 and current_tokens >= tok_limit:
        _increment_rejected_count()
        raise AiBudgetExceededError(
            reason="daily_token_limit",
            retry_after_seconds=retry_after,
            detail="Daily AI token budget reached. Please retry after UTC midnight.",
        )

    client = _get_healthy_redis()
    if client is not None:
        try:
            req_key = f"pms:ai:budget:req:{day}:{uid}"
            if increment_request:
                new_reqs = int(client.incr(req_key))
                if new_reqs == 1:
                    client.expire(req_key, _BUDGET_TTL_SECONDS)
                if req_limit > 0 and new_reqs > req_limit:
                    client.decr(req_key)
                    _increment_rejected_count()
                    raise AiBudgetExceededError(
                        reason="daily_request_limit",
                        retry_after_seconds=retry_after,
                        detail="Daily AI request budget reached. Please retry after UTC midnight.",
                    )
                _request_slot_reserved.set(True)
            else:
                curr_reqs = int(client.get(req_key) or 0)
                exceeded = curr_reqs > req_limit if _request_slot_reserved.get() else curr_reqs >= req_limit
                if req_limit > 0 and exceeded:
                    _increment_rejected_count()
                    raise AiBudgetExceededError(
                        reason="daily_request_limit",
                        retry_after_seconds=retry_after,
                        detail="Daily AI request budget reached. Please retry after UTC midnight.",
                    )
            return
        except AiBudgetExceededError:
            raise
        except Exception:
            pass

    with _state_lock:
        curr_reqs = _daily_user_requests.get((day, uid), 0)
        if increment_request:
            if req_limit > 0 and curr_reqs >= req_limit:
                global _rejected_budget_requests
                _rejected_budget_requests += 1
                raise AiBudgetExceededError(
                    reason="daily_request_limit",
                    retry_after_seconds=retry_after,
                    detail="Daily AI request budget reached. Please retry after UTC midnight.",
                )
            _daily_user_requests[(day, uid)] = curr_reqs + 1
            _request_slot_reserved.set(True)
        else:
            exceeded = curr_reqs > req_limit if _request_slot_reserved.get() else curr_reqs >= req_limit
            if req_limit > 0 and exceeded:
                _rejected_budget_requests += 1
                raise AiBudgetExceededError(
                    reason="daily_request_limit",
                    retry_after_seconds=retry_after,
                    detail="Daily AI request budget reached. Please retry after UTC midnight.",
                )


def record_user_tokens(user_id: str | None, tokens: int) -> int:
    """Record consumed prompt + completion tokens against the user's UTC-day counter."""
    delta = max(0, int(tokens or 0))
    uid = _normalized_user_key(user_id)
    day = _utc_day_key()
    if delta <= 0:
        _, existing = _read_daily_counters(uid, day)
        return existing

    client = _get_healthy_redis()
    if client is not None:
        try:
            tok_key = f"pms:ai:budget:tok:{day}:{uid}"
            new_total = int(client.incrby(tok_key, delta))
            client.expire(tok_key, _BUDGET_TTL_SECONDS)
            return new_total
        except Exception:
            pass

    with _state_lock:
        new_total = _daily_user_tokens.get((day, uid), 0) + delta
        _daily_user_tokens[(day, uid)] = new_total
        return new_total


def is_existing_completed_replay(
    db: Any,
    *,
    conversation_id: str | None,
    client_request_id: str | None,
    owner_user_id: str | None,
) -> bool:
    """Return True when (conversation_id, client_request_id) refers to an already-completed owned turn."""
    if not db or not conversation_id or not client_request_id:
        return False
    conv_id_str = str(conversation_id).strip()
    if not conv_id_str:
        return False
    try:
        from models.models import AiConversation, AiTurn

        owner = str(owner_user_id or "anonymous")
        row = (
            db.query(AiTurn.response_payload)
            .join(AiConversation, AiTurn.conversation_id == AiConversation.id)
            .filter(
                AiConversation.id == conv_id_str,
                AiConversation.owner_user_id == owner,
                AiTurn.client_request_id == str(client_request_id),
                AiTurn.status == "completed",
            )
            .first()
        )
        return bool(row and row[0])
    except Exception:
        return False


def get_budget_health_snapshot() -> dict[str, Any]:
    """Return secret-free budget & timeout telemetry for /api/ai/diagnostics."""
    with _state_lock:
        active = _active_concurrent_requests
        rejected = _rejected_budget_requests
    return {
        "max_concurrent_requests": max_concurrent_chat_requests(),
        "active_concurrent_requests": active,
        "daily_user_request_limit": daily_user_request_limit(),
        "daily_user_token_limit": daily_user_token_limit(),
        "max_request_input_tokens": max_request_input_tokens(),
        "router_timeout_seconds": router_timeout_seconds(),
        "synthesis_timeout_seconds": synthesis_timeout_seconds(),
        "rejected_budget_requests": rejected,
    }


def reset_usage_budget_state_for_tests() -> None:
    """Reset in-memory budget counters and concurrency state for test isolation."""
    global _active_concurrent_requests, _rejected_budget_requests
    with _state_lock:
        _active_concurrent_requests = 0
        _rejected_budget_requests = 0
        _daily_user_requests.clear()
        _daily_user_tokens.clear()


__all__ = [
    "AiBudgetExceededError",
    "acquire_chat_concurrency_slot",
    "check_request_token_budget",
    "check_user_daily_budget",
    "daily_user_request_limit",
    "daily_user_token_limit",
    "estimate_tokens",
    "get_budget_health_snapshot",
    "is_existing_completed_replay",
    "max_concurrent_chat_requests",
    "max_request_input_tokens",
    "record_user_tokens",
    "reset_usage_budget_state_for_tests",
    "router_timeout_seconds",
    "synthesis_timeout_seconds",
]
