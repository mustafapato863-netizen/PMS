"""Aggregate assistant quality without exporting questions, answers, or employee records."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from math import ceil

from sqlalchemy.orm import Session

from models.models import AiInteractionTrace, AiLearningRun
from services.ai.learning_corrections import (
    CONCISE_RANKING_RULE,
    MEASUREMENT_RULE,
    active_measurement_correction,
    active_ranking_correction,
    correction_status_summary,
)
from services.ai.learning_worker import learning_enabled


def _correction_metrics(rows: list, rule_id: str, label: str, status_info: dict) -> dict:
    """Compute affected users and before/after failure rates with denominators for one correction."""
    down_users: set[str] = set()
    corrected_rows = []
    uncorrected_rows = []
    for row in rows:
        user, _, vote, op, reason, _, applied, _created = row
        is_target = (
            (rule_id == MEASUREMENT_RULE and (op in {"current_value", "read_employee_metric", "get_kpi_diagnosis_and_trends"} or reason in {"wrong_data", "incorrect_answer"}))
            or (rule_id == CONCISE_RANKING_RULE and (op in {"ranking", "get_query_rankings", "get_agent_spotlight_and_trend"} or reason in {"too_long", "misunderstood_question"}))
        )
        if applied == rule_id:
            corrected_rows.append(row)
        elif is_target:
            uncorrected_rows.append(row)
            if vote == "down" and user:
                down_users.add(str(user))

    before_total = len(uncorrected_rows)
    before_flagged = sum(1 for r in uncorrected_rows if r[2] == "down")
    after_total = len(corrected_rows)
    after_flagged = sum(1 for r in corrected_rows if r[2] == "down")
    return {
        "id": rule_id,
        "label": label,
        "status": str(status_info.get("status") or "insufficient_evidence"),
        "active": bool(status_info.get("active")),
        "affected_users": len(down_users),
        "min_users_required": 3,
        "before_flagged": before_flagged,
        "before_total": before_total,
        "before_failure_rate": round(before_flagged * 100 / before_total, 1) if before_total else None,
        "after_flagged": after_flagged,
        "after_total": after_total,
        "after_failure_rate": round(after_flagged * 100 / after_total, 1) if after_total else None,
        "corrected_answers": after_total,
        "flagged_after_correction": after_flagged,
    }


def sampled_quality(db: Session) -> dict:
    trace = AiInteractionTrace
    governance = trace.structured_response["feedback_governance"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    rows = db.query(
        trace.user_id, trace.latency_ms, trace.feedback_rating,
        governance["operation_family"].as_string(), governance["reason_tag"].as_string(),
        trace.structured_response["answer_source"].as_string(),
        trace.structured_response["applied_correction"].as_string(),
        trace.created_at,
    ).filter(trace.created_at >= cutoff).order_by(trace.created_at.desc(), trace.id.desc()).limit(1000).all()
    flags = [(user, op, reason) for user, _, vote, op, reason, *_ in rows if vote == "down" and user and op and reason]
    accounts = Counter((op, reason) for _, op, reason in set(flags))
    times = sorted(ms for _, ms, *_ in rows if ms and ms > 0)
    recurring = sum(accounts[op, reason] >= 2 for _, op, reason in flags)
    corrected = [row for row in rows if row[6]]
    weekly = [{"turns": 0, "flagged": 0}, {"turns": 0, "flagged": 0}]
    today = datetime.now(timezone.utc).date()
    for row in rows:
        if not row[7]:
            continue
        days_ago = (today - row[7].date()).days
        if 0 <= days_ago < 14:
            bucket = weekly[days_ago // 7]
            bucket["turns"] += 1
            bucket["flagged"] += int(row[2] == "down")
    worker = "disabled"
    if learning_enabled():
        latest = db.query(AiLearningRun).order_by(AiLearningRun.day.desc()).first()
        worker = f"{latest.day} · {latest.state}" if latest else "Awaiting first run"
    statuses = correction_status_summary(db)
    corrections = [
        _correction_metrics(
            rows,
            MEASUREMENT_RULE,
            "Restore omitted current KPI measurement",
            statuses[MEASUREMENT_RULE],
        ),
        _correction_metrics(
            rows,
            CONCISE_RANKING_RULE,
            "Concise single-winner ranking reply",
            statuses[CONCISE_RANKING_RULE],
        ),
    ]
    return {
        "sample_size": len(rows),
        "flagged_turns": sum(vote == "down" for _, _, vote, *_ in rows),
        "recurring_per_100": round(recurring * 100 / len(rows), 1) if rows else None,
        "p95_ms": times[ceil(len(times) * 0.95) - 1] if times else None,
        "model_answers": sum(row[5] == "model_synthesis" for row in rows),
        "corrected_answers": len(corrected),
        "flagged_after_correction": sum(row[2] == "down" for row in corrected),
        "weekly": weekly,
        "measurement_correction_active": active_measurement_correction(db),
        "ranking_correction_active": active_ranking_correction(db),
        "corrections": corrections,
        "worker": worker,
    }
