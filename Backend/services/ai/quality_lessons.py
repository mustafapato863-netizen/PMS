"""Quality loop stage 3: lessons the primary model sees, and regression cases for the eval set.

Lessons and corrections live on the trace (``structured_response["judge"]``) written by
``quality_judge``. A lesson only reaches the model after an admin approves it. Behind
``PMS_AI_QUALITY_LOOP_ENABLED``. English only; no schema migration.
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from models.models import AiInteractionTrace
from services.ai.quality_scoring import quality_loop_enabled

MAX_LESSONS_IN_PROMPT = 5
CACHE_SECONDS = 60.0
_cache: dict[str, Any] = {"at": 0.0, "lessons": []}
_lock = threading.Lock()
_PCT_RE = re.compile(r"\d{1,3}(?:\.\d+)?\s*%")


def _recent_judged(db: Session, days: int = 30, limit: int = 500) -> list[AiInteractionTrace]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(AiInteractionTrace).filter(AiInteractionTrace.created_at >= since)
        .order_by(AiInteractionTrace.created_at.desc()).limit(limit).all()
    )
    return [t for t in rows if isinstance(t.structured_response, dict) and isinstance(t.structured_response.get("judge"), dict)]


def approved_lessons(db: Session, limit: int = MAX_LESSONS_IN_PROMPT) -> list[str]:
    """Distinct admin-approved lesson texts, newest first (cached for a minute)."""
    if not quality_loop_enabled():
        return []
    with _lock:
        if time.monotonic() - _cache["at"] < CACHE_SECONDS:
            return list(_cache["lessons"])[:limit]
    out: list[str] = []
    try:
        for t in _recent_judged(db):
            lesson = t.structured_response["judge"].get("lesson")
            if isinstance(lesson, dict) and lesson.get("status") == "approved":
                text = str(lesson.get("text") or "").strip()
                if text and text.casefold() not in {o.casefold() for o in out}:
                    out.append(text)
    except Exception:  # noqa: BLE001 - learning must never break chat
        out = []
    with _lock:
        _cache.update(at=time.monotonic(), lessons=out)
    return out[:limit]


def lessons_prompt_block(db: Session) -> str:
    lessons = approved_lessons(db)
    if not lessons:
        return ""
    return "\nQuality lessons from reviewed mistakes (follow them; evidence still wins):\n" + "\n".join(f"- {x}" for x in lessons) + "\n"


def set_lesson_status(db: Session, trace_id: str, status: str) -> bool:
    """Admin approve / reject / deactivate a lesson. Returns False when there is no such lesson."""
    if status not in {"approved", "rejected", "pending"}:
        raise ValueError("invalid lesson status")
    try:
        tid = uuid.UUID(str(trace_id))
    except (ValueError, TypeError):
        return False
    row = db.query(AiInteractionTrace).filter(AiInteractionTrace.id == tid).first()
    resp = dict(row.structured_response or {}) if row else {}
    judge = dict(resp.get("judge") or {})
    lesson = judge.get("lesson")
    if not isinstance(lesson, dict):
        return False
    judge["lesson"] = {**lesson, "status": status}
    resp["judge"] = judge
    row.structured_response = resp
    db.add(row)
    db.commit()
    with _lock:
        _cache["at"] = 0.0
    return True


def regression_cases(db: Session) -> list[dict[str, Any]]:
    """Judged failures with a grounded correction, in the eval fixture format.

    ``all_of`` holds the figures from the corrected headline, so a regression passes only when the
    assistant's answer carries the same evidence-backed numbers. Review before adding to the fixture.
    """
    cases: list[dict[str, Any]] = []
    for t in _recent_judged(db, days=90, limit=1000):
        j = t.structured_response["judge"]
        fix = j.get("correction")
        if j.get("verdict") != "fail" or not isinstance(fix, dict):
            continue
        figures = [m.group(0).replace(" ", "").rstrip("%") for m in _PCT_RE.finditer(str(fix.get("headline") or ""))]
        if not figures:
            continue
        cases.append({
            "id": f"reg_{str(t.id)[:8]}",
            "cat": "regression",
            "prompt": str(t.sanitized_prompt or t.prompt),
            "all_of": [[f] for f in figures[:3]],
            "issues": list(j.get("issues") or []),
        })
    return cases
