"""Replay a bounded presentation correction against typed PMS evidence."""
from __future__ import annotations

import os
import re
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from models.ai_schemas import TypedMetricEvidence
from models.models import AiInteractionTrace, AiLearningRun


MEASUREMENT_RULE = "single_current_measurement_v1"
CONCISE_RANKING_RULE = "concise_ranking_winner_v1"


def _measurement(plan: dict, evidence: list) -> TypedMetricEvidence | None:
    if plan.get("operation_kind_v2") != "current_value" or len(evidence) != 1:
        return None
    try:
        item = TypedMetricEvidence.model_validate(evidence[0])
    except ValidationError:
        return None
    if (item.actual is None or not item.actual_display or not item.period
            or not (item.employee_name or item.team) or not (item.source_link or "").startswith("/")):
        return None
    return item


def corrected_measurement(plan: dict, evidence: list, headline: str) -> str | None:
    """Fill an omitted current value. Leave comparative, compound and ambiguous answers alone."""
    item = _measurement(plan, evidence)
    if not item:
        return None
    display = item.actual_display.strip().casefold()
    number = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)\s*(%|mins?|minutes?|hrs?|hours?|secs?|seconds?)?", display)
    if not number:
        return None
    # A formatted 3.40 minutes and 3.4 min describe the same measurement.
    unit = number[2] or ""
    units = (r"(?:%|percent\b)" if unit == "%" else
             r"(?:minutes?|mins?)\b" if unit.startswith("m") else
             r"(?:hours?|hrs?)\b" if unit.startswith("h") else
             r"(?:seconds?|secs?)\b" if unit.startswith("s") else r"(?!\s*[%\w])")
    mentions = re.finditer(r"(?<![\w.+-])([-+]?\d+(?:\.\d+)?)(?![\d.]\d)\s*" + units, headline, re.I)
    if any(Decimal(match[1]) == Decimal(number[1]) for match in mentions):
        return None
    subject = item.employee_name or item.team
    return f"{subject} · {item.display_name} was {item.actual_display} in {item.period}."


def replay_measurement_correction(db: Session, traces, *, min_users: int) -> str:
    users = set()
    for sample in traces:
        row = db.get(AiInteractionTrace, UUID(sample.trace_id))
        if not row or row.feedback_rating != "down" or row.guardrail_triggered or not row.non_empty_evidence:
            continue
        response = row.structured_response or {}
        if response.get("applied_correction") == MEASUREMENT_RULE:
            return "withdrawn"
        if not row.user_id or response.get("outcome") != "answer" or response.get("feedback_governance", {}).get("pii_quarantined"):
            continue
        plan = response.get("structured_query") or {}
        evidence = response.get("typed_evidence") or []
        headline = str(response.get("headline") or "")
        if not headline or not isinstance(plan, dict) or not isinstance(evidence, list):
            continue
        correction = corrected_measurement(plan, evidence, headline)
        if correction and corrected_measurement(plan, evidence, correction) is None:
            users.add(row.user_id)
    return "verified" if len(users) >= min_users else "insufficient_evidence"


def _latest_correction_status(db: Session, result_key: str) -> str:
    if os.getenv("PMS_AI_AUTO_CORRECTIONS_ENABLED", "").lower() not in {"true", "1", "yes", "on"}:
        return "disabled"
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=7)).isoformat()
    runs = db.query(AiLearningRun.results).filter(
        AiLearningRun.day > cutoff, AiLearningRun.state == "completed",
    ).order_by(AiLearningRun.day.desc())
    for (results,) in runs:
        status = (results or {}).get(result_key)
        if status in {"verified", "withdrawn", "insufficient_evidence"}:
            return str(status)
    return "insufficient_evidence"


def active_measurement_correction(db: Session) -> bool:
    return _latest_correction_status(db, "measurement_correction") == "verified"


def active_ranking_correction(db: Session) -> bool:
    return _latest_correction_status(db, "ranking_correction") == "verified"


def correction_status_summary(db: Session) -> dict[str, dict[str, str | bool]]:
    m_status = _latest_correction_status(db, "measurement_correction")
    r_status = _latest_correction_status(db, "ranking_correction")
    return {
        MEASUREMENT_RULE: {
            "status": "active" if m_status == "verified" else m_status,
            "active": m_status == "verified",
        },
        CONCISE_RANKING_RULE: {
            "status": "active" if r_status == "verified" else r_status,
            "active": r_status == "verified",
        },
    }


def _ranking_winner_fact(
    plan: dict, evidence: list, *, detail: str = "brief",
) -> tuple[TypedMetricEvidence, dict] | None:
    if str(detail or "brief").casefold() == "detailed":
        return None
    if plan.get("intent") != "ranking" and plan.get("operation_kind_v2") != "ranking":
        return None
    qr = plan.get("query_rankings_args") or {}
    if not isinstance(qr, dict):
        qr = {}
    if qr.get("group_by") not in (None, "none"):
        return None
    if int(qr.get("limit") or 1) > 1 or not evidence:
        return None
    try:
        item = TypedMetricEvidence.model_validate(evidence[0])
    except ValidationError:
        return None
    if (item.actual is None or not item.actual_display or not item.period
            or not (item.employee_name or item.team or item.position)
            or not (item.source_link or "").startswith("/")):
        return None
    return item, qr


def corrected_concise_ranking(
    plan: dict,
    evidence: list,
    headline: str,
    bullets: list[str] | None = None,
    *,
    detail: str = "brief",
) -> tuple[str, list[str]] | None:
    """Shorten over-detailed single-winner ranking replies using verified PMS evidence."""
    resolved = _ranking_winner_fact(plan, evidence, detail=detail)
    if not resolved:
        return None
    item, qr = resolved
    entity = str(qr.get("entity") or "department")
    if entity == "employee" and item.employee_name:
        subject = item.employee_name
        entity_label = "employee"
    elif entity == "position" and item.position:
        subject = item.position
        entity_label = "role"
    elif entity == "branch" and item.branch and item.branch != "all":
        subject = item.branch.capitalize()
        entity_label = "branch"
    else:
        subject = item.team or item.employee_name or ""
        entity_label = "team" if entity == "team" else "department"
    if not subject:
        return None

    text = str(headline or "").strip()
    bullet_list = [str(b) for b in (bullets or []) if str(b).strip()]
    has_subject = subject.casefold() in text.casefold()
    num_match = re.match(r"([-+]?\d+(?:\.\d+)?)", item.actual_display.strip())
    has_value = bool(num_match and num_match.group(1) in text)
    # Contrast/already-concise guard: leave clean single-line answers untouched.
    if has_subject and has_value and len(text) <= 135 and len(bullet_list) == 0:
        return None

    direction_word = "Lowest" if (qr.get("sort_order") == "asc" or plan.get("ranking_direction") == "worst") else "Best"
    new_headline = f"{direction_word} {entity_label} for {item.period}: {subject} ({item.actual_display})."
    return new_headline, []


def _contrast_ranking_cases_safe() -> bool:
    """Verify concise_ranking_winner_v1 does NOT mutate contrast prompts (trends, grouped, detailed, clean)."""
    clean_ev = [{
        "metric_id": "overall_score",
        "kpi_key": "overall_score",
        "display_name": "Overall PMS Score",
        "team": "Sales",
        "actual": 83.2,
        "actual_display": "83.2%",
        "period": "September 2026",
        "source_link": "/monthly-presentation?region=uae",
    }]
    if corrected_concise_ranking({"intent": "trend", "operation_kind_v2": "trend"}, clean_ev, "Sales rose to 83.2%.") is not None:
        return False
    if corrected_concise_ranking({"intent": "ranking", "query_rankings_args": {"entity": "department", "group_by": "branch", "limit": 1}}, clean_ev, "Best department is Sales at 83.2%.", ["extra"]) is not None:
        return False
    if corrected_concise_ranking({"intent": "ranking", "query_rankings_args": {"entity": "department", "limit": 1}}, clean_ev, "Long detailed answer...", ["b1", "b2"], detail="detailed") is not None:
        return False
    if corrected_concise_ranking({"intent": "ranking", "query_rankings_args": {"entity": "department", "limit": 1}}, clean_ev, "Best department for September 2026: Sales (83.2%).", []) is not None:
        return False
    return True


def replay_ranking_correction(db: Session, traces, *, min_users: int) -> dict[str, object]:
    users: set[str] = set()
    if not _contrast_ranking_cases_safe():
        return {"status": "insufficient_evidence", "affected_users": 0, "contrast_passed": False}
    for sample in traces:
        row = db.get(AiInteractionTrace, UUID(sample.trace_id))
        if not row or row.feedback_rating != "down" or row.guardrail_triggered or not row.non_empty_evidence:
            continue
        response = row.structured_response or {}
        if response.get("applied_correction") == CONCISE_RANKING_RULE:
            return {"status": "withdrawn", "affected_users": len(users), "contrast_passed": True}
        gov = response.get("feedback_governance") or {}
        if not row.user_id or response.get("outcome") != "answer" or gov.get("pii_quarantined"):
            continue
        reason_tag = str(gov.get("reason_tag") or "").casefold()
        if reason_tag not in {"too_long", "misunderstood_question", "incorrect_answer", ""}:
            continue
        plan = response.get("structured_query") or {}
        evidence = response.get("typed_evidence") or []
        headline = str(response.get("headline") or "")
        bullets = list(response.get("narrative_bullets") or [])
        detail = str(response.get("answer_detail") or "brief")
        if not headline or not isinstance(plan, dict) or not isinstance(evidence, list):
            continue
        rewritten = corrected_concise_ranking(plan, evidence, headline, bullets, detail=detail)
        if rewritten is not None:
            new_h, new_b = rewritten
            # Idempotence check on proposed output
            if corrected_concise_ranking(plan, evidence, new_h, new_b, detail=detail) is None:
                users.add(str(row.user_id))
    return {
        "status": "verified" if len(users) >= min_users else "insufficient_evidence",
        "affected_users": len(users),
        "contrast_passed": True,
    }
