"""One OpenAI-compatible client for the self-hosted PMS model.

Intent routing, narrow synthesis, and the optional explorer all call
``chat_completion``. PMS still computes every number. A failure here is a
reason code, and the caller falls back to the rules engine.

The endpoint is configurable. ``PMS_AI_LLM_BASE_URL`` wins. ``PMS_AI_LOCAL_ROUTER_URL``
remains accepted as a full ``/v1/chat/completions`` URL. Hosts must be on
``PMS_AI_LLM_ALLOWED_HOSTS``. Credentials, query strings, and redirects are rejected.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Iterator

from services.ai.config import redact_secrets
from services.ai.runtime_status import last_known_model, note_fallback, remember_model

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_HOSTS = "localhost,127.0.0.1,::1,llm,pms-qwen-pilot,host.docker.internal"
DEFAULT_MODEL_NAME = "qwen3-4b-q4_k_m"
DEFAULT_CHAT_URL = "http://pms-qwen-pilot:8080/v1/chat/completions"
_CHAT_PATH = "/v1/chat/completions"
_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
_THINK_OPEN_RE = re.compile(r"<think\b[^>]*>.*", re.IGNORECASE | re.DOTALL)
_TRUTHY = {"1", "true", "yes", "on", "enabled"}
_MAX_RESPONSE_BYTES = 65536

# One in-flight completion for the whole process. A 2 vCPU box cannot run two inferences.
_SLOT = threading.BoundedSemaphore(1)
_remaining: ContextVar[int | None] = ContextVar("pms_ai_llm_remaining", default=None)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class LlmCompletion:
    ok: bool
    content: str | None
    model: str
    elapsed_ms: float
    reason: str
    http_status: int | None = None


def flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().casefold() in _TRUTHY


def local_intent_enabled() -> bool:
    """Intent routing is safe in production: the model returns one enum, PMS does the rest."""
    return flag_enabled("PMS_AI_LLM_INTENT_ENABLED") or flag_enabled("PMS_AI_LOCAL_ROUTER_ENABLED")


def local_synthesis_enabled() -> bool:
    """Validated synthesis is safe in production. Rejected text falls back to the rules headline."""
    return flag_enabled("PMS_AI_LLM_SYNTHESIS_ENABLED") or flag_enabled("PMS_AI_LOCAL_SYNTHESIS_ENABLED")


def local_exploration_enabled() -> bool:
    """Tool-planning stays off in production.

    The host allowlist does not limit which authorized question the model asks
    PMS to run, and each step can send evidence summaries to the model.
    Intent routing and validated synthesis do neither.
    """
    if os.environ.get("APP_ENV", "").strip().casefold() == "production":
        return False
    falsy = {"0", "false", "no", "off", "disabled"}
    data_flag = os.environ.get("PMS_AI_LOCAL_DATA_EXPLORATION_ENABLED", "").strip().casefold()
    if data_flag in falsy:
        return False
    return (
        flag_enabled("PMS_AI_LLM_EXPLORATION_ENABLED")
        or flag_enabled("PMS_AI_LOCAL_EXPLORATION_ENABLED")
        or data_flag in _TRUTHY
    )


def configured_model_name() -> str:
    return os.environ.get("PMS_AI_LLM_MODEL", "").strip() or DEFAULT_MODEL_NAME


def _bounded_float(names: tuple[str, ...], default: float, maximum: float) -> float:
    raw = ""
    for name in names:
        candidate = os.environ.get(name, "").strip()
        if candidate:
            raw = candidate
            break
    try:
        value = float(raw) if raw else default
    except ValueError:
        value = default
    return max(0.5, min(value, maximum))


def routing_timeout_seconds() -> float:
    """One CPU thread. Default 15s, hard cap 30s."""
    return _bounded_float(("PMS_AI_LLM_TIMEOUT_SECONDS", "PMS_AI_LOCAL_ROUTER_TIMEOUT_SECONDS"), 15.0, 30.0)


def synthesis_timeout_seconds() -> float:
    """One CPU thread. Default 30s, hard cap 60s."""
    return _bounded_float(
        ("PMS_AI_LLM_SYNTHESIS_TIMEOUT_SECONDS", "PMS_AI_LOCAL_SYNTHESIS_TIMEOUT_SECONDS"),
        30.0,
        60.0,
    )


def exploration_timeout_seconds() -> float:
    return _bounded_float(
        ("PMS_AI_LLM_EXPLORATION_TIMEOUT_SECONDS", "PMS_AI_LOCAL_EXPLORATION_TIMEOUT_SECONDS"),
        15.0,
        30.0,
    )


def context_token_limit() -> int:
    """Match the live server: Qwen3-4B is started with --ctx-size 2048."""
    raw = os.environ.get("PMS_AI_LLM_CONTEXT", "2048").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 2048
    return max(512, min(value, 8192))


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def cap_output_tokens(requested: int) -> int:
    """Leave most of the 2048-token window for the prompt."""
    context = context_token_limit()
    try:
        requested_int = int(requested)
    except (TypeError, ValueError):
        requested_int = 64
    return max(16, min(requested_int, 256, context // 4))


def strip_thinking(text: str) -> str:
    """Drop Qwen3 think blocks so JSON parsers see only the answer."""
    cleaned = _THINK_BLOCK_RE.sub("", text or "")
    cleaned = _THINK_OPEN_RE.sub("", cleaned)
    return cleaned.strip()


def _disable_thinking(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    fitted = [{"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")} for item in messages]
    if fitted and fitted[0]["role"] == "system":
        if "/no_think" not in fitted[0]["content"]:
            fitted[0]["content"] = fitted[0]["content"].rstrip() + " /no_think"
    else:
        fitted.insert(0, {"role": "system", "content": "/no_think"})
    return fitted


def fit_messages(messages: list[dict[str, str]], max_tokens: int) -> list[dict[str, str]]:
    """Truncate from the end until the prompt plus the completion fits in the context window."""
    fitted = _disable_thinking(messages)
    budget = max(128, context_token_limit() - max_tokens - 48)

    def total() -> int:
        return estimate_tokens(json.dumps(fitted, ensure_ascii=False))

    for index in range(len(fitted) - 1, -1, -1):
        if total() <= budget:
            break
        content = fitted[index]["content"]
        overhead = total() - estimate_tokens(content)
        char_budget = max(0, (budget - overhead) * 4)
        if len(content) <= char_budget:
            continue
        if char_budget < 16:
            fitted[index]["content"] = ""
        else:
            fitted[index]["content"] = content[: char_budget - 1].rstrip() + "…"
    return fitted


def max_calls_per_turn() -> int:
    raw = os.environ.get("PMS_AI_LLM_MAX_CALLS_PER_TURN", "3").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 3
    return max(1, min(value, 8))


def _normalize_host(value: str) -> str:
    item = value.strip().casefold().rstrip(".")
    if item.startswith("[") and item.endswith("]"):
        item = item[1:-1]
    return item


def allowed_hosts() -> frozenset[str]:
    raw = os.environ.get("PMS_AI_LLM_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS)
    hosts = {_normalize_host(part) for part in raw.split(",") if part.strip()}
    return frozenset(hosts)


def _chat_url_from_base(base: str) -> str:
    trimmed = base.strip().rstrip("/")
    if trimmed.endswith("/chat/completions"):
        return trimmed
    if trimmed.endswith("/v1"):
        return trimmed + "/chat/completions"
    return trimmed + "/v1/chat/completions"


def resolve_chat_url() -> tuple[str | None, str]:
    """Return ``(url, reason)``. ``url`` is set only when ``reason`` is ``ok``."""
    base = os.environ.get("PMS_AI_LLM_BASE_URL", "").strip()
    legacy = os.environ.get("PMS_AI_LOCAL_ROUTER_URL", "").strip()
    if base:
        candidate = _chat_url_from_base(base)
    elif legacy:
        candidate = legacy
    else:
        candidate = DEFAULT_CHAT_URL
    return _validate_chat_url(candidate)


def _validate_chat_url(url: str) -> tuple[str | None, str]:
    try:
        parsed = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return None, "invalid_endpoint"
    if parsed.scheme not in {"http", "https"}:
        return None, "invalid_endpoint"
    if parsed.username or parsed.password:
        return None, "invalid_endpoint"
    if parsed.query or parsed.fragment:
        return None, "invalid_endpoint"
    host = _normalize_host(parsed.hostname or "")
    if not host or host not in allowed_hosts():
        return None, "invalid_endpoint"
    path = parsed.path.rstrip("/") or "/"
    if path != _CHAT_PATH:
        return None, "invalid_endpoint"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, _CHAT_PATH, "", "")), "ok"


def _log_call(*, model: str, host: str, purpose: str, elapsed_ms: float, reason: str, http_status: int | None) -> None:
    logger.info(
        "%s",
        json.dumps(
            {
                "event": "ai_llm_call",
                "purpose": purpose,
                "provider": "llama_cpp",
                "model": model,
                "host": host,
                "elapsed_ms": elapsed_ms,
                "outcome": reason,
                "http_status": http_status,
            },
            separators=(",", ":"),
        ),
    )


def _finish(
    *,
    ok: bool,
    content: str | None,
    model: str,
    started: float,
    reason: str,
    host: str,
    purpose: str,
    http_status: int | None = None,
) -> LlmCompletion:
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
    _log_call(model=model, host=host, purpose=purpose, elapsed_ms=elapsed_ms, reason=reason, http_status=http_status)
    if not ok:
        source = purpose if purpose in {"intent", "routing", "synthesis", "exploration", "probe"} else "llm"
        note_fallback(reason, source)
    return LlmCompletion(ok=ok, content=content, model=model, elapsed_ms=elapsed_ms, reason=reason, http_status=http_status)


@contextmanager
def llm_turn() -> Iterator[None]:
    """Cap model HTTP calls for one chat turn. Nested turns are not supported."""
    token: Token[int | None] = _remaining.set(max_calls_per_turn())
    try:
        yield
    finally:
        _remaining.reset(token)


def _take_budget() -> bool:
    current = _remaining.get()
    if current is None:
        return True
    if current <= 0:
        return False
    _remaining.set(current - 1)
    return True


def chat_completion(
    *,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float = 0.0,
    response_format: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
    purpose: str = "completion",
) -> LlmCompletion:
    """POST one chat completion. Never raises for transport or parse failures."""
    started = time.perf_counter()
    model = configured_model_name()
    url, url_reason = resolve_chat_url()
    host = ""
    if url:
        host = _normalize_host(urllib.parse.urlsplit(url).hostname or "")
    if url is None:
        return _finish(
            ok=False, content=None, model=model, started=started, reason=url_reason, host=host, purpose=purpose
        )
    if not _SLOT.acquire(blocking=False):
        return _finish(ok=False, content=None, model=model, started=started, reason="busy", host=host, purpose=purpose)

    timeout = timeout_seconds if timeout_seconds is not None else routing_timeout_seconds()
    output_tokens = cap_output_tokens(max_tokens)
    fitted_messages = fit_messages(messages, output_tokens)
    payload: dict[str, Any] = {
        "model": model,
        "messages": fitted_messages,
        "temperature": temperature,
        "max_tokens": output_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if response_format is not None:
        payload["response_format"] = response_format
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("PMS_AI_LLM_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        if not _take_budget():
            return _finish(
                ok=False, content=None, model=model, started=started, reason="call_cap", host=host, purpose=purpose
            )
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
            status = getattr(response, "status", None)
        if len(raw) > _MAX_RESPONSE_BYTES:
            return _finish(
                ok=False,
                content=None,
                model=model,
                started=started,
                reason="response_too_large",
                host=host,
                purpose=purpose,
                http_status=status,
            )
        try:
            envelope = json.loads(raw)
            content = envelope["choices"][0]["message"]["content"]
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            logger.warning("ai_llm_call invalid response: %s", redact_secrets(str(exc)))
            return _finish(
                ok=False,
                content=None,
                model=model,
                started=started,
                reason="invalid_response",
                host=host,
                purpose=purpose,
                http_status=status,
            )
        if not isinstance(content, str):
            return _finish(
                ok=False,
                content=None,
                model=model,
                started=started,
                reason="invalid_response",
                host=host,
                purpose=purpose,
                http_status=status,
            )
        content = strip_thinking(content)
        if not content:
            return _finish(
                ok=False,
                content=None,
                model=model,
                started=started,
                reason="invalid_response",
                host=host,
                purpose=purpose,
                http_status=status,
            )
        return _finish(
            ok=True,
            content=content,
            model=model,
            started=started,
            reason="ok",
            host=host,
            purpose=purpose,
            http_status=status,
        )
    except TimeoutError as exc:
        logger.warning("ai_llm_call timeout: %s", redact_secrets(str(exc)))
        return _finish(
            ok=False, content=None, model=model, started=started, reason="timeout", host=host, purpose=purpose
        )
    except urllib.error.HTTPError as exc:
        logger.warning("ai_llm_call http %s: %s", exc.code, redact_secrets(str(exc)))
        return _finish(
            ok=False,
            content=None,
            model=model,
            started=started,
            reason="http_error",
            host=host,
            purpose=purpose,
            http_status=getattr(exc, "code", None),
        )
    except (OSError, urllib.error.URLError) as exc:
        logger.warning("ai_llm_call unavailable: %s", redact_secrets(str(exc)))
        return _finish(
            ok=False,
            content=None,
            model=model,
            started=started,
            reason="unavailable_or_invalid",
            host=host,
            purpose=purpose,
        )
    finally:
        _SLOT.release()


_MODEL_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_PROBE_LIMIT_SECONDS = 1.5


def _model_version(raw: bytes) -> str | None:
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None
    token = data[0].get("id")
    if isinstance(token, str) and _MODEL_TOKEN.match(token):
        return token
    return None


def probe_model_availability(timeout_seconds: float = 0.8) -> dict[str, Any]:
    """GET the configured model's id. The request cannot outlive ``timeout_seconds``.

    The returned dict never includes the URL, credentials, or the response body.
    """
    timeout = max(0.2, min(float(timeout_seconds), _PROBE_LIMIT_SECONDS))
    configured = configured_model_name()
    url, url_reason = resolve_chat_url()
    result: dict[str, Any] = {
        "available": False,
        "name": configured,
        "version": None,
        "probe": "not_sent",
        "reason": "invalid_endpoint",
        "last_known": last_known_model(),
    }
    if url is None:
        result["reason"] = url_reason if url_reason == "invalid_endpoint" else "invalid_endpoint"
        return result

    def once() -> dict[str, Any]:
        models_url = url[: -len("/chat/completions")] + "/models"
        request = urllib.request.Request(models_url, method="GET")
        try:
            with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
                raw = response.read(4096)
                status = getattr(response, "status", 0)
            if not isinstance(status, int) or status < 200 or status >= 300:
                return {"available": False, "version": None, "reason": "unavailable"}
            return {"available": True, "version": _model_version(raw), "reason": "ok"}
        except TimeoutError:
            return {"available": False, "version": None, "reason": "timeout"}
        except Exception:
            return {"available": False, "version": None, "reason": "unavailable"}

    box: dict[str, Any] = {}

    def run() -> None:
        box["value"] = once()

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        result["probe"] = "models"
        result["reason"] = "timeout"
        result["last_known"] = last_known_model()
        return result
    value = box.get("value") or {"available": False, "version": None, "reason": "unavailable"}
    version = value.get("version") if isinstance(value.get("version"), str) else None
    if value.get("available"):
        remember_model(version or configured)
    result.update(
        {
            "available": bool(value.get("available")),
            "version": version,
            "probe": "models",
            "reason": str(value.get("reason") or "unavailable"),
            "last_known": last_known_model(),
        }
    )
    return result
