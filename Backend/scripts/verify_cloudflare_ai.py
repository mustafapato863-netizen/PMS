#!/usr/bin/env python3
"""Isolated Live Verification Script for Cloudflare Workers AI.

Performs safe, synthetic live connectivity verification against Cloudflare Workers AI:
1. No database writes or schema modifications.
2. No feature flag or product setting updates.
3. No frontend access or authenticated user sessions required.
4. No real employee information or sensitive data (strictly synthetic prompts).
5. Never exposes or logs API keys, bearer tokens, or account IDs in output.
6. Enforces strict timeouts and low token limits.
7. Maximum two live provider calls per verification run (Test A + Test B).
8. Never runs automatically in normal CI; requires explicit execution.

Test A: Basic completion ("Reply with exactly: PMS AI connection successful.")
Test B: Structured JSON intent response ("Return a JSON object identifying intent...")
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_MODEL = "@cf/ibm-granite/granite-4.0-h-micro"
ALTER_MODEL = "@cf/zai-org/glm-4.7-flash"
DEFAULT_TIMEOUT = 10.0


def redact_text(text: str | None) -> str:
    """Mask tokens, secrets, or account IDs from output messages."""
    if not text:
        return ""
    import re
    cleaned = re.sub(r"cfut_[A-Za-z0-9_-]{20,}", "cfut_***REDACTED***", str(text))
    cleaned = re.sub(r"Bearer\s+[A-Za-z0-9_-]{20,}", "Bearer ***REDACTED***", cleaned)
    cleaned = re.sub(r"AIzaSy[A-Za-z0-9_-]{20,}", "AIzaSy***REDACTED***", cleaned)
    cleaned = re.sub(r"(accounts/)[0-9a-f]{32}(/ai)", r"\1***REDACTED***\2", cleaned, flags=re.IGNORECASE)
    return cleaned


def run_live_verification(
    *,
    model: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    account_id: str | None = None,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Execute bounded 2-step synthetic verification against Cloudflare Workers AI.

    Returns structured diagnostics dictionary. Never raises unhandled exceptions.
    """
    t_start = time.perf_counter()

    acct = (
        account_id
        or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        or os.environ.get("CF_ACCOUNT_ID")
        or ""
    ).strip()

    token = (
        api_token
        or os.environ.get("CLOUDFLARE_API_TOKEN")
        or os.environ.get("CF_API_TOKEN")
        or os.environ.get("CLOUDFLARE_API_KEY")
        or ""
    ).strip()

    selected_model = (
        model
        or os.environ.get("CLOUDFLARE_AI_MODEL")
        or DEFAULT_MODEL
    ).strip()

    result: dict[str, Any] = {
        "verified": False,
        "provider": "cloudflare",
        "model": selected_model,
        "account_id_configured": bool(acct),
        "api_token_configured": bool(token),
        "test_a_completion": None,
        "test_b_structured": None,
        "total_latency_ms": 0.0,
        "error": None,
    }

    if not acct:
        result["error"] = "Cloudflare Account ID is missing (CLOUDFLARE_ACCOUNT_ID)"
        result["total_latency_ms"] = round((time.perf_counter() - t_start) * 1000.0, 2)
        return result

    if not token:
        result["error"] = "Cloudflare API Token is missing (CLOUDFLARE_API_TOKEN)"
        result["total_latency_ms"] = round((time.perf_counter() - t_start) * 1000.0, 2)
        return result

    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    # -------------------------------------------------------------------------
    # Call 1: Test A — Basic completion
    # -------------------------------------------------------------------------
    t_a_start = time.perf_counter()
    test_a_res: dict[str, Any] = {
        "status": "failed",
        "http_code": None,
        "content": "",
        "latency_ms": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "neurons": None,
        "error": None,
    }

    payload_a = {
        "model": selected_model,
        "messages": [
            {"role": "user", "content": "Reply with exactly: PMS AI connection successful."}
        ],
        "temperature": 0.0,
        "max_tokens": 64,
    }

    try:
        req_a = urllib.request.Request(
            url,
            data=json.dumps(payload_a).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req_a, timeout=timeout) as resp:
            test_a_res["http_code"] = resp.status
            raw_body = resp.read().decode("utf-8")
            data_a = json.loads(raw_body)

            if isinstance(data_a, dict) and data_a.get("success") is False:
                errors = data_a.get("errors") or []
                err_msg = "; ".join(str(e.get("message", e)) for e in errors) if errors else "Cloudflare success: false"
                test_a_res["error"] = redact_text(err_msg)
            else:
                choices = data_a.get("choices") or []
                if choices:
                    content = str(choices[0].get("message", {}).get("content") or "").strip()
                    test_a_res["content"] = content
                    usage = data_a.get("usage") or {}
                    test_a_res["prompt_tokens"] = int(usage.get("prompt_tokens") or 0)
                    test_a_res["completion_tokens"] = int(usage.get("completion_tokens") or 0)
                    test_a_res["neurons"] = usage.get("neurons")

                    # Programmatic validation: verify message confirms connection
                    if "PMS AI" in content or "connection successful" in content.lower():
                        test_a_res["status"] = "passed"
                    else:
                        test_a_res["error"] = f"Response did not match expected confirmation: {content[:80]}"
                else:
                    test_a_res["error"] = "Zero choices in Cloudflare response"
    except urllib.error.HTTPError as exc:
        test_a_res["http_code"] = exc.code
        test_a_res["error"] = f"HTTP Error {exc.code}"
    except (TimeoutError, urllib.error.URLError) as exc:
        test_a_res["error"] = f"Connection error / timeout: {type(exc).__name__}"
    except Exception as exc:
        test_a_res["error"] = redact_text(str(exc))
    finally:
        test_a_res["latency_ms"] = round((time.perf_counter() - t_a_start) * 1000.0, 2)

    result["test_a_completion"] = test_a_res

    if test_a_res["status"] != "passed":
        result["error"] = f"Test A failed: {test_a_res.get('error') or 'unknown error'}"
        result["total_latency_ms"] = round((time.perf_counter() - t_start) * 1000.0, 2)
        return result

    # -------------------------------------------------------------------------
    # Call 2: Test B — Structured JSON response
    # -------------------------------------------------------------------------
    t_b_start = time.perf_counter()
    test_b_res: dict[str, Any] = {
        "status": "failed",
        "http_code": None,
        "parsed": None,
        "latency_ms": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "neurons": None,
        "error": None,
    }

    target_schema = {
        "type": "object",
        "properties": {
            "intent": {"type": "string"},
            "requires_data": {"type": "boolean"},
        },
        "required": ["intent", "requires_data"],
    }

    prompt_b = (
        "Return a JSON object identifying the intent of a synthetic performance question.\n"
        f"Output schema: {json.dumps(target_schema)}"
    )

    payload_b = {
        "model": selected_model,
        "messages": [
            {
                "role": "system",
                "content": "You are a performance management classifier. Output ONLY valid JSON adhering to the specified schema.",
            },
            {"role": "user", "content": prompt_b},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
        "max_tokens": 128,
    }

    try:
        req_b = urllib.request.Request(
            url,
            data=json.dumps(payload_b).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req_b, timeout=timeout) as resp:
            test_b_res["http_code"] = resp.status
            raw_body = resp.read().decode("utf-8")
            data_b = json.loads(raw_body)

            if isinstance(data_b, dict) and data_b.get("success") is False:
                errors = data_b.get("errors") or []
                err_msg = "; ".join(str(e.get("message", e)) for e in errors) if errors else "Cloudflare success: false"
                test_b_res["error"] = redact_text(err_msg)
            else:
                choices = data_b.get("choices") or []
                if choices:
                    content_b = str(choices[0].get("message", {}).get("content") or "").strip()
                    usage_b = data_b.get("usage") or {}
                    test_b_res["prompt_tokens"] = int(usage_b.get("prompt_tokens") or 0)
                    test_b_res["completion_tokens"] = int(usage_b.get("completion_tokens") or 0)
                    test_b_res["neurons"] = usage_b.get("neurons")

                    # Programmatic JSON validation (strip <think> reasoning blocks and markdown fences)
                    cleaned_b = re.sub(r"<think\b[^>]*>.*?</think>", "", content_b, flags=re.DOTALL | re.IGNORECASE)
                    cleaned_b = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned_b.strip(), flags=re.IGNORECASE).strip()
                    try:
                        parsed_b = json.loads(cleaned_b)
                        if isinstance(parsed_b, dict) and "intent" in parsed_b and "requires_data" in parsed_b:
                            if isinstance(parsed_b["intent"], str) and isinstance(parsed_b["requires_data"], bool):
                                test_b_res["parsed"] = parsed_b
                                test_b_res["status"] = "passed"
                            else:
                                test_b_res["error"] = f"JSON fields invalid types: {parsed_b}"
                        else:
                            test_b_res["error"] = f"JSON missing required keys (intent, requires_data): {parsed_b}"
                    except json.JSONDecodeError as json_err:
                        test_b_res["error"] = f"Non-JSON response text: {content_b[:80]}"
                else:
                    test_b_res["error"] = "Zero choices in Cloudflare response"
    except urllib.error.HTTPError as exc:
        test_b_res["http_code"] = exc.code
        test_b_res["error"] = f"HTTP Error {exc.code}"
    except (TimeoutError, urllib.error.URLError) as exc:
        test_b_res["error"] = f"Connection error / timeout: {type(exc).__name__}"
    except Exception as exc:
        test_b_res["error"] = redact_text(str(exc))
    finally:
        test_b_res["latency_ms"] = round((time.perf_counter() - t_b_start) * 1000.0, 2)

    result["test_b_structured"] = test_b_res

    if test_b_res["status"] == "passed":
        result["verified"] = True
    else:
        result["error"] = f"Test B failed: {test_b_res.get('error') or 'unknown error'}"

    result["total_latency_ms"] = round((time.perf_counter() - t_start) * 1000.0, 2)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Cloudflare Workers AI live connectivity.")
    parser.add_argument("--model", default=None, help=f"Cloudflare model ID (default: {DEFAULT_MODEL})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Per-call timeout seconds")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON only")
    args = parser.parse_args(argv)

    try:
        from dotenv import load_dotenv
        # Look for local development env file if present
        for env_path in ("Backend/.env.local", ".env.local", "Backend/.env", ".env"):
            if os.path.exists(env_path):
                load_dotenv(env_path, override=False)
                break
    except ImportError:
        pass

    diagnostics = run_live_verification(model=args.model, timeout=args.timeout)

    if args.json:
        print(json.dumps(diagnostics, indent=2))
        return 0 if diagnostics["verified"] else 1

    print("=" * 60)
    print("PMS AI — Cloudflare Workers AI Live Verification")
    print("=" * 60)
    print(f"Model: {diagnostics['model']}")
    print(f"Account ID configured: {diagnostics['account_id_configured']}")
    print(f"API Token configured:  {diagnostics['api_token_configured']}")

    test_a = diagnostics.get("test_a_completion") or {}
    print(f"\n[Test A] Basic Completion:")
    print(f"  Status:     {test_a.get('status')}")
    print(f"  HTTP Code:  {test_a.get('http_code')}")
    print(f"  Latency:    {test_a.get('latency_ms')}ms")
    print(f"  Tokens:     prompt={test_a.get('prompt_tokens')}, comp={test_a.get('completion_tokens')}")
    if test_a.get("neurons") is not None:
        print(f"  Neurons:    {test_a.get('neurons')}")
    if test_a.get("content"):
        print(f"  Content:    {test_a.get('content')}")
    if test_a.get("error"):
        print(f"  Error:      {test_a.get('error')}")

    test_b = diagnostics.get("test_b_structured") or {}
    print(f"\n[Test B] Structured JSON:")
    print(f"  Status:     {test_b.get('status')}")
    print(f"  HTTP Code:  {test_b.get('http_code')}")
    print(f"  Latency:    {test_b.get('latency_ms')}ms")
    print(f"  Tokens:     prompt={test_b.get('prompt_tokens')}, comp={test_b.get('completion_tokens')}")
    if test_b.get("neurons") is not None:
        print(f"  Neurons:    {test_b.get('neurons')}")
    if test_b.get("parsed"):
        print(f"  Parsed:     {json.dumps(test_b.get('parsed'))}")
    if test_b.get("error"):
        print(f"  Error:      {test_b.get('error')}")

    print("-" * 60)
    print(f"Total Latency: {diagnostics['total_latency_ms']}ms")
    if diagnostics["verified"]:
        print("OVERALL RESULT: [PASS] Cloudflare Workers AI live verified successfully.")
        return 0
    else:
        print(f"OVERALL RESULT: [FAIL] {diagnostics.get('error') or 'Verification failed'}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
