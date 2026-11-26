"""Quality loop stage 2: sampled judge + corrector on free Cloudflare Workers AI.

Runs in the background worker only, never in the chat path. Everything is behind
``PMS_AI_QUALITY_LOOP_ENABLED`` (default off) and needs no schema migration: results are
stored on the trace (``structured_response["judge"]``), and the per-key daily neuron budget is
rebuilt from those stored results, so it survives restarts.

Free plan facts (https://developers.cloudflare.com/workers-ai/platform/pricing/):
10,000 neurons/day per account, resets 00:00 UTC, error 3036 when spent. Each key is capped at
``PMS_AI_QUALITY_NEURON_BUDGET_PER_KEY`` (default 9000 = 90%). English only.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from models.models import AiInteractionTrace
from services.ai.quality_scoring import _walk_numbers, quality_loop_enabled

logger = logging.getLogger(__name__)

DEFAULT_JUDGE_MODEL = "@cf/openai/gpt-oss-120b"
# neurons per million tokens (input, output), from the Cloudflare pricing page.
NEURON_RATES: dict[str, tuple[float, float]] = {
    "@cf/openai/gpt-oss-120b": (31818, 68182),
    "@cf/openai/gpt-oss-20b": (18182, 27273),
    "@cf/google/gemma-4-26b-a4b-it": (9091, 27273),
    "@cf/qwen/qwen3-30b-a3b-fp8": (4625, 30475),
    "@cf/zai-org/glm-4.7-flash": (5500, 36400),
    "@cf/nvidia/nemotron-3-120b-a12b": (45455, 136364),
}
FALLBACK_RATE = (45455, 136364)  # unknown model: assume the dearest allowed one
CF_ERROR_ALLOWANCE_SPENT = 3036
MAX_DIGEST_CHARS = 6000

JUDGE_SYSTEM = (
    "You are a strict QA reviewer for an HR performance analytics assistant. English only. "
    "You get a question, the assistant's answer and the evidence digest it was built from. "
    "Judge ONLY against the evidence. Return one JSON object with keys: "
    '"verdict" ("pass" or "fail"), "score" (0-100), "issues" (list of short strings from: '
    '"ungrounded_number","wrong_ranking_order","wrong_period","incomplete","hallucination","other"), '
    '"notes" (one sentence). Fail when a number or name is not supported by the evidence, the best/worst '
    "order is reversed, the period differs from the question, or part of the question is unanswered."
)
CORRECT_SYSTEM = (
    "You fix a faulty answer for an HR performance analytics assistant. English only. Use ONLY facts and "
    "numbers present in the evidence digest. Return one JSON object with keys: "
    '"headline" (one sentence), "bullets" (list of at most 3 short strings), '
    '"lesson" (one general rule, max 200 chars, that would prevent this mistake; no names or numbers).'
)


class AllowanceSpent(Exception):
    """A key has no free allowance left today."""


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, "").strip() or default))
    except ValueError:
        return default


def judge_model() -> str:
    return (os.environ.get("PMS_AI_QUALITY_JUDGE_MODEL") or DEFAULT_JUDGE_MODEL).strip()


def estimate_neurons(model: str, tokens_in: int, tokens_out: int) -> int:
    rin, rout = NEURON_RATES.get(model, FALLBACK_RATE)
    return int(round(tokens_in * rin / 1_000_000 + tokens_out * rout / 1_000_000))


def _utc_day(now: datetime) -> str:
    return now.astimezone(timezone.utc).date().isoformat()


def _cf_keys(db: Session | None) -> list[dict[str, str]]:
    """Cloudflare credential slots that are actually configured (primary, alternate)."""
    from services.ai import provider_config_store

    cfg = provider_config_store.resolve_provider_config("cloudflare", db=db)
    slots = []
    if cfg.primary_api_key and cfg.account_id:
        slots.append({"slot": "primary", "account": cfg.account_id, "token": cfg.primary_api_key})
    if cfg.alternate_api_key and (cfg.alternate_account_id or cfg.account_id):
        slots.append({"slot": "alternate", "account": cfg.alternate_account_id or cfg.account_id, "token": cfg.alternate_api_key})
    return slots


def _post_json(url: str, token: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https hosts
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        if exc.code == 429 or str(CF_ERROR_ALLOWANCE_SPENT) in body:
            raise AllowanceSpent(f"http {exc.code}") from exc
        raise


def _chat_cloudflare(key: dict[str, str], model: str, system: str, user: str, max_tokens: int, timeout: float) -> tuple[str, int]:
    data = _post_json(
        f"https://api.cloudflare.com/client/v4/accounts/{key['account']}/ai/v1/chat/completions",
        key["token"],
        {"model": model, "temperature": 0.0, "max_tokens": max_tokens,
         "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        timeout,
    )
    for err in data.get("errors") or []:
        if isinstance(err, dict) and err.get("code") == CF_ERROR_ALLOWANCE_SPENT:
            raise AllowanceSpent("3036")
    choice = (data.get("choices") or [{}])[0]
    text = str((choice.get("message") or {}).get("content") or "")
    usage = data.get("usage") or {}
    neurons = estimate_neurons(model, int(usage.get("prompt_tokens") or len(user) // 3), int(usage.get("completion_tokens") or len(text) // 3))
    return text, neurons


def _parse_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        out = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return out if isinstance(out, dict) else None


def neurons_used_today(db: Session, now: datetime) -> dict[str, int]:
    """Per key slot neurons already spent today (UTC), rebuilt from stored judge results."""
    day = _utc_day(now)
    since = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    used: dict[str, int] = {}
    rows = db.query(AiInteractionTrace.structured_response).filter(AiInteractionTrace.created_at >= since - timedelta(days=1)).all()
    for (resp,) in rows:
        j = (resp or {}).get("judge") if isinstance(resp, dict) else None
        if isinstance(j, dict) and j.get("day") == day:
            used[str(j.get("slot") or "?")] = used.get(str(j.get("slot") or "?"), 0) + int(j.get("neurons") or 0)
            # a judged row can carry a correction call too
            used[str(j.get("fix_slot") or j.get("slot") or "?")] = used.get(str(j.get("fix_slot") or j.get("slot") or "?"), 0) + int(j.get("fix_neurons") or 0)
    return used


def _is_sampled(trace_id: str, percent: int) -> bool:
    return int(hashlib.sha256(str(trace_id).encode()).hexdigest()[:6], 16) % 100 < percent


def _candidates(db: Session, now: datetime, sample_percent: int) -> list[AiInteractionTrace]:
    rows = (
        db.query(AiInteractionTrace)
        .filter(AiInteractionTrace.created_at >= now - timedelta(hours=24))
        .order_by(AiInteractionTrace.created_at.desc()).limit(500).all()
    )
    ranked: list[tuple[int, AiInteractionTrace]] = []
    for t in rows:
        resp = t.structured_response if isinstance(t.structured_response, dict) else {}
        if resp.get("judge") or resp.get("outcome") != "answer":
            continue
        q = resp.get("quality") or {}
        if t.feedback_rating == "down":
            ranked.append((0, t))
        elif q.get("low"):
            ranked.append((1, t))
        elif _is_sampled(str(t.id), sample_percent):
            ranked.append((2, t))
    ranked.sort(key=lambda p: p[0])
    return [t for _, t in ranked]


def _evidence_text(trace: AiInteractionTrace) -> str:
    return json.dumps(trace.tool_digest or {}, ensure_ascii=False, default=str)[:MAX_DIGEST_CHARS]


def _grounded(correction: dict[str, Any], trace: AiInteractionTrace) -> bool:
    """A correction may only use numbers that exist in the evidence digest."""
    allowed: set[float] = set()
    _walk_numbers(trace.tool_digest or {}, allowed)
    text = " ".join([str(correction.get("headline") or ""), *[str(b) for b in correction.get("bullets") or []]])
    import re
    for m in re.finditer(r"(?<![\w.])(\d{1,3}(?:\.\d+)?)\s*(?:%|pp\b|pts?\b)", text):
        if round(float(m.group(1)), 1) not in allowed:
            return False
    return bool(str(correction.get("headline") or "").strip())


def judge_trace(db: Session, trace: AiInteractionTrace, key: dict[str, str], now: datetime, model: str) -> int:
    """Judge one trace (and correct it when it fails). Returns neurons spent. Raises AllowanceSpent."""
    resp = dict(trace.structured_response or {})
    user = (
        f"QUESTION:\n{trace.sanitized_prompt or trace.prompt}\n\nANSWER HEADLINE:\n{resp.get('headline')}\n"
        f"ANSWER BULLETS:\n{json.dumps(resp.get('narrative_bullets') or [], ensure_ascii=False)}\n\nEVIDENCE DIGEST:\n{_evidence_text(trace)}"
    )
    text, neurons = _chat_cloudflare(key, model, JUDGE_SYSTEM, user, 700, 60.0)
    verdict = _parse_json(text) or {}
    passed = str(verdict.get("verdict") or "").lower() == "pass"
    judge: dict[str, Any] = {
        "day": _utc_day(now), "slot": key["slot"], "model": model, "neurons": neurons,
        "verdict": "pass" if passed else ("fail" if verdict else "unparsed"),
        "score": verdict.get("score") if isinstance(verdict.get("score"), (int, float)) else None,
        "issues": [str(i)[:40] for i in (verdict.get("issues") or [])][:6],
        "notes": str(verdict.get("notes") or "")[:300],
    }
    if judge["verdict"] == "fail":
        try:
            ftext, fneu = _chat_cloudflare(key, model, CORRECT_SYSTEM, user + f"\n\nJUDGE ISSUES: {judge['issues']}", 900, 60.0)
            judge.update({"fix_slot": key["slot"], "fix_neurons": fneu})
            fix = _parse_json(ftext) or {}
            if _grounded(fix, trace):
                judge["correction"] = {
                    "headline": str(fix["headline"])[:360],
                    "bullets": [str(b)[:360] for b in (fix.get("bullets") or [])][:3],
                }
                lesson = str(fix.get("lesson") or "").strip()[:200]
                if lesson:
                    judge["lesson"] = {"text": lesson, "status": "pending"}
            else:
                judge["correction_rejected"] = "not_grounded"
        except AllowanceSpent:
            raise
        except Exception:  # noqa: BLE001
            logger.warning("Quality corrector failed", exc_info=False)
    resp["judge"] = judge
    trace.structured_response = resp
    db.add(trace)
    db.commit()
    return neurons + int(judge.get("fix_neurons") or 0)


def run_quality_tick(db: Session, now: datetime | None = None) -> dict[str, Any]:
    """Judge a bounded number of candidate answers within the free per-key budgets."""
    if not quality_loop_enabled() or os.environ.get("PMS_AI_QUALITY_JUDGE_ENABLED", "true").lower() in {"0", "false", "off", "no"}:
        return {"status": "disabled"}
    now = now or datetime.now(timezone.utc)
    budget = _env_int("PMS_AI_QUALITY_NEURON_BUDGET_PER_KEY", 9000)
    max_calls = _env_int("PMS_AI_QUALITY_MAX_JUDGED_PER_DAY", 60)
    per_tick = _env_int("PMS_AI_QUALITY_MAX_PER_TICK", 5)
    sample = min(100, _env_int("PMS_AI_QUALITY_SAMPLE_PERCENT", 10))
    model = judge_model()
    keys = _cf_keys(db)
    if not keys:
        return {"status": "no_keys"}
    used = neurons_used_today(db, now)
    day = _utc_day(now)
    judged_today = sum(
        1 for (r,) in db.query(AiInteractionTrace.structured_response).filter(AiInteractionTrace.created_at >= now - timedelta(hours=48)).all()
        if isinstance(r, dict) and isinstance(r.get("judge"), dict) and r["judge"].get("day") == day
    )
    done = 0
    exhausted: set[str] = set()
    for trace in _candidates(db, now, sample):
        if done >= per_tick or judged_today + done >= max_calls:
            break
        # a judge+fix pair costs at most ~3x a judge call; keep a reserve
        reserve = estimate_neurons(model, 4000, 1800)
        judged = False
        while not judged:
            key = next((k for k in keys if k["slot"] not in exhausted and used.get(k["slot"], 0) + reserve <= budget), None)
            if key is None:
                break
            try:
                used[key["slot"]] = used.get(key["slot"], 0) + judge_trace(db, trace, key, now, model)
                done += 1
                judged = True
            except AllowanceSpent:
                exhausted.add(key["slot"])
                used[key["slot"]] = budget  # fail over to the other key
                db.rollback()
            except Exception:  # noqa: BLE001
                db.rollback()
                logger.warning("Quality judge call failed", exc_info=False)
                return {"status": "error", "judged": done, "used": used, "budget_per_key": budget}
        if not judged:
            break
    return {"status": "ok", "judged": done, "used": used, "budget_per_key": budget}
