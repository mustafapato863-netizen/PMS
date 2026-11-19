"""Lightweight live verification probes for Admin-managed AI credentials.

Each probe sends one deliberately tiny request directly to the provider and
returns metadata only. Request headers, keys, and raw error bodies are never
returned to the caller; error text is redacted before it leaves this module.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from services.ai.config import redact_secrets

DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


def _http_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict,
    timeout: float,
) -> tuple[int, dict | None, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            raw = response.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed = None
        return status, parsed if isinstance(parsed, dict) else None, ""
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            body = ""
        return int(getattr(exc, "code", 0) or 0), None, redact_secrets(body or f"HTTP {exc.code}")
    except Exception as exc:
        return 0, None, redact_secrets(str(exc))


def _result(
    *,
    ok: bool,
    status_code: int,
    started: float,
    message: str,
    tested_model: str,
) -> dict:
    return {
        "ok": bool(ok),
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "status_code": int(status_code),
        "message": message,
        "tested_model": tested_model,
    }


def probe_cloudflare(
    *,
    api_key: str,
    model: str,
    account_id: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    started = time.perf_counter()
    if not api_key:
        return _result(ok=False, status_code=0, started=started, message="No Cloudflare API token configured", tested_model=model)
    if not account_id:
        return _result(ok=False, status_code=0, started=started, message="Cloudflare Account ID is required", tested_model=model)

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions"
    status, body, error = _http_json(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        payload={
            "model": model,
            "messages": [{"role": "user", "content": "Reply with OK"}],
            "max_tokens": 1,
        },
        timeout=timeout,
    )
    success_flag = (body or {}).get("success")
    ok = status == 200 and success_flag is not False
    if ok:
        message = "Cloudflare token verified"
    elif error:
        message = f"Cloudflare rejected the request: {error.replace(api_key, '[redacted]')}"
    else:
        message = f"Cloudflare returned HTTP {status}"
    return _result(
        ok=ok,
        status_code=status,
        started=started,
        message=message,
        tested_model=model,
    )


def probe_gemini(
    *,
    api_key: str,
    model: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    started = time.perf_counter()
    if not api_key:
        return _result(ok=False, status_code=0, started=started, message="No Gemini API key configured", tested_model=model)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    status, body, error = _http_json(
        url,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        payload={
            "contents": [{"role": "user", "parts": [{"text": "Reply with OK"}]}],
            "generationConfig": {"maxOutputTokens": 1},
        },
        timeout=timeout,
    )
    candidates = (body or {}).get("candidates")
    ok = status == 200 and isinstance(candidates, list) and bool(candidates)
    if ok:
        message = "Gemini key verified"
    elif error:
        message = f"Gemini rejected the request: {error.replace(api_key, '[redacted]')}"
    else:
        message = f"Gemini returned HTTP {status}"
    return _result(
        ok=ok,
        status_code=status,
        started=started,
        message=message,
        tested_model=model,
    )


def probe_nvidia(
    *,
    api_key: str,
    model: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    started = time.perf_counter()
    if not api_key:
        return _result(ok=False, status_code=0, started=started, message="No NVIDIA API key configured", tested_model=model)

    base_url = (
        os.environ.get("NVIDIA_API_BASE_URL") or DEFAULT_NVIDIA_BASE_URL
    ).strip().rstrip("/")
    url = f"{base_url}/chat/completions"
    status, body, error = _http_json(
        url,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        payload={
            "model": model,
            "messages": [{"role": "user", "content": "Reply with OK"}],
            "temperature": 0.0,
            "max_tokens": 1,
            "stream": False,
        },
        timeout=timeout,
    )
    choices = (body or {}).get("choices")
    ok = status == 200 and isinstance(choices, list) and bool(choices)
    if ok:
        message = "NVIDIA key verified"
    elif error:
        message = f"NVIDIA rejected the request: {error.replace(api_key, '[redacted]')}"
    else:
        message = f"NVIDIA returned HTTP {status}"
    return _result(
        ok=ok,
        status_code=status,
        started=started,
        message=message,
        tested_model=model,
    )


def probe_provider(
    provider: str,
    *,
    api_key: str,
    model: str,
    account_id: str = "",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    if provider == "cloudflare":
        return probe_cloudflare(
            api_key=api_key,
            model=model,
            account_id=account_id,
            timeout=timeout,
        )
    if provider == "gemini":
        return probe_gemini(api_key=api_key, model=model, timeout=timeout)
    if provider == "nvidia":
        return probe_nvidia(api_key=api_key, model=model, timeout=timeout)
    raise ValueError(f"Unsupported AI provider: {provider}")
