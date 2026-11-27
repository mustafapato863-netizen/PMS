"""Shadow mode for the custom PMS LoRA phrasing model (Cloudflare Workers AI).

Default OFF. In shadow mode the live answer is never changed or delayed: after the
live provider has produced a validated answer, a background thread asks the custom
model to phrase the same verified facts and logs only metrics (no question or answer
text, no names): latency, whether it added numbers that are not in the facts, whether
it matched the live answer. Used to decide promotion with real traffic.

Env:
  PMS_AI_CUSTOM_MODEL=off|shadow        (default off; anything else means off)
  PMS_AI_CUSTOM_MODEL_LORA=pms-assistant-v2
  PMS_AI_CUSTOM_MODEL_BASE=@cf/mistral/mistral-7b-instruct-v0.2-lora
  PMS_AI_CUSTOM_MODEL_SAMPLE=0.1        fraction of eligible answers to shadow
  PMS_AI_CUSTOM_MODEL_DAILY_CAP=100     max shadow calls per UTC day (free neuron budget)
  PMS_AI_CUSTOM_MODEL_TIMEOUT_SECONDS=8
Uses the existing CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN settings.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("pms.ai.custom_model_shadow")

DEFAULT_BASE = "@cf/mistral/mistral-7b-instruct-v0.2-lora"
DEFAULT_LORA = "pms-assistant-v2"
SYSTEM_PROMPT = (
    "You are the PMS performance assistant. Use ONLY the verified facts given in the message. "
    "If no verified facts are given, say you need to look the data up and do not state any score, rank or name. "
    "Never invent numbers."
)
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_lock = threading.Lock()
_day = ""
_count = 0


def mode() -> str:
    raw = (os.environ.get("PMS_AI_CUSTOM_MODEL") or "off").strip().casefold()
    return "shadow" if raw == "shadow" else "off"


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _take_daily_slot() -> bool:
    global _day, _count
    cap = int(_float_env("PMS_AI_CUSTOM_MODEL_DAILY_CAP", 100))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _lock:
        if today != _day:
            _day, _count = today, 0
        if _count >= cap:
            return False
        _count += 1
        return True


def numbers_in(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUM.findall(text or "")}


def invented_numbers(answer: str, allowed_text: str) -> list[str]:
    allowed = numbers_in(allowed_text)
    return sorted(n for n in numbers_in(answer) if n not in allowed)


def _call_model(user_payload: str) -> str:
    account = (os.environ.get("CLOUDFLARE_ACCOUNT_ID") or os.environ.get("CF_ACCOUNT_ID") or "").strip()
    token = (
        os.environ.get("CLOUDFLARE_API_TOKEN") or os.environ.get("CF_API_TOKEN") or os.environ.get("CLOUDFLARE_API_KEY") or ""
    ).strip()
    if not account or not token:
        raise RuntimeError("missing_cloudflare_credentials")
    base = os.environ.get("PMS_AI_CUSTOM_MODEL_BASE", DEFAULT_BASE)
    body = {
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_payload}],
        "max_tokens": 160,
        "temperature": 0,
        "lora": os.environ.get("PMS_AI_CUSTOM_MODEL_LORA", DEFAULT_LORA),
    }
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{base}",
        json.dumps(body).encode(),
        {"Authorization": f"Bearer {token}", "content-type": "application/json"},
    )
    timeout = _float_env("PMS_AI_CUSTOM_MODEL_TIMEOUT_SECONDS", 8.0)
    res = json.load(urllib.request.urlopen(req, timeout=timeout)).get("result", {})
    if "choices" in res:
        return res["choices"][0]["message"].get("content") or ""
    return res.get("response") or ""


def _run(question: str, facts_payload: dict[str, Any], live_answer: str) -> None:
    started = time.monotonic()
    facts_text = json.dumps(facts_payload, ensure_ascii=False, default=str)
    user_payload = f"Verified facts: {facts_text}\n\nQuestion: {question[:600]}"
    outcome = "ok"
    invented: list[str] = []
    same = False
    try:
        answer = _call_model(user_payload)
        invented = invented_numbers(answer, facts_text + " " + question)
        same = " ".join(answer.split()).casefold() == " ".join((live_answer or "").split()).casefold()
    except Exception as exc:  # never affects the live answer
        outcome = f"error:{type(exc).__name__}"
    logger.info(
        "custom_model_shadow outcome=%s latency_ms=%d invented_numbers=%d same_as_live=%s q_sha=%s lora=%s",
        outcome,
        int((time.monotonic() - started) * 1000),
        len(invented),
        same,
        hashlib.sha256(question.encode()).hexdigest()[:8],
        os.environ.get("PMS_AI_CUSTOM_MODEL_LORA", DEFAULT_LORA),
    )


def maybe_shadow(question: str, facts_payload: dict[str, Any], live_answer: str) -> bool:
    """Fire-and-forget. Returns True if a shadow call was started. Never raises."""
    try:
        if mode() != "shadow":
            return False
        if random.random() > max(0.0, min(1.0, _float_env("PMS_AI_CUSTOM_MODEL_SAMPLE", 0.1))):
            return False
        if not _take_daily_slot():
            return False
        threading.Thread(target=_run, args=(question, facts_payload, live_answer), daemon=True).start()
        return True
    except Exception:
        return False
