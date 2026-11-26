"""Admin read model for the answer-quality loop (scores, failures, free-tier usage)."""
from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from models.models import AiInteractionTrace
from services.ai.quality_judge import _env_int, judge_model, neurons_used_today
from services.ai.quality_scoring import quality_loop_enabled


def quality_summary(db: Session, days: int = 14) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    rows = (
        db.query(AiInteractionTrace.created_at, AiInteractionTrace.structured_response, AiInteractionTrace.feedback_rating)
        .filter(AiInteractionTrace.created_at >= now - timedelta(days=days))
        .order_by(AiInteractionTrace.created_at.desc()).limit(5000).all()
    )
    by_day: dict[str, list[int]] = {}
    flags: Counter[str] = Counter()
    scored = low = judged = judge_fail = corrected = 0
    for created, resp, _rating in rows:
        if not isinstance(resp, dict):
            continue
        q = resp.get("quality")
        if isinstance(q, dict) and q.get("score") is not None:
            scored += 1
            low += int(bool(q.get("low")))
            by_day.setdefault(created.date().isoformat(), []).append(int(q["score"]))
            flags.update(str(f) for f in q.get("flags") or [])
        j = resp.get("judge")
        if isinstance(j, dict):
            judged += 1
            judge_fail += int(j.get("verdict") == "fail")
            corrected += int(isinstance(j.get("correction"), dict))
    all_scores = [s for v in by_day.values() for s in v]
    used = neurons_used_today(db, now)
    return {
        "enabled": quality_loop_enabled(),
        "window_days": days,
        "scored_answers": scored,
        "low_score_answers": low,
        "average_score": round(sum(all_scores) / len(all_scores), 1) if all_scores else None,
        "trend": [{"day": d, "average": round(sum(v) / len(v), 1), "answers": len(v)} for d, v in sorted(by_day.items())],
        "top_flags": [{"flag": f, "count": c} for f, c in flags.most_common(8)],
        "judged_answers": judged,
        "judge_failures": judge_fail,
        "corrections_stored": corrected,
        "judge": {
            "model": judge_model(),
            "sample_percent": min(100, _env_int("PMS_AI_QUALITY_SAMPLE_PERCENT", 10)),
            "max_judged_per_day": _env_int("PMS_AI_QUALITY_MAX_JUDGED_PER_DAY", 60),
            "neuron_budget_per_key": _env_int("PMS_AI_QUALITY_NEURON_BUDGET_PER_KEY", 9000),
            "neurons_used_today": used,
            "judge_switch": os.environ.get("PMS_AI_QUALITY_JUDGE_ENABLED", "true"),
        },
    }


def judged_failures(db: Session, limit: int = 30) -> list[dict[str, Any]]:
    rows = (
        db.query(AiInteractionTrace).filter(AiInteractionTrace.created_at >= datetime.now(timezone.utc) - timedelta(days=30))
        .order_by(AiInteractionTrace.created_at.desc()).limit(1000).all()
    )
    out: list[dict[str, Any]] = []
    for t in rows:
        resp = t.structured_response if isinstance(t.structured_response, dict) else {}
        j = resp.get("judge")
        if not isinstance(j, dict) or j.get("verdict") != "fail":
            continue
        lesson = j.get("lesson") if isinstance(j.get("lesson"), dict) else None
        out.append({
            "trace_id": str(t.id),
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "prompt": t.sanitized_prompt or t.prompt,
            "answer": resp.get("headline"),
            "deterministic_score": (resp.get("quality") or {}).get("score"),
            "issues": j.get("issues") or [],
            "notes": j.get("notes"),
            "correction": j.get("correction"),
            "correction_rejected": j.get("correction_rejected"),
            "lesson": lesson,
            "thumbs": t.feedback_rating,
        })
        if len(out) >= limit:
            break
    return out
