"""Process recurring feedback on idle worker capacity; all timestamps are UTC."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.models import AiInteractionTrace, AiLearningRun
from services.ai.feature_gate import read_ai_access_tier, read_ai_enabled
from services.ai.learning_corrections import (
    CONCISE_RANKING_RULE,
    MEASUREMENT_RULE,
    replay_measurement_correction,
    replay_ranking_correction,
)
from services.ai.feedback_service import FeedbackGovernanceService
from services.ai.nemotron_analyzer import NemotronFeedbackAnalyzerService, is_feedback_analyzer_configured


def learning_enabled() -> bool:
    return os.getenv("PMS_AI_BACKGROUND_LEARNING_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def run_feedback_tick(db: Session, now: datetime | None = None) -> None:
    if not learning_enabled() or not read_ai_enabled(db):
        return
    now = now or datetime.now(timezone.utc)
    day = now.date().isoformat()
    claim = str(uuid4())
    row = db.get(AiLearningRun, day)
    if row is None:
        row = AiLearningRun(day=day, claim=claim, state="running", updated_at=now, results={})
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return
    else:
        acquired = db.query(AiLearningRun).filter(
            AiLearningRun.day == day, AiLearningRun.state == "running",
            AiLearningRun.updated_at < now - timedelta(minutes=15),
        ).update({"claim": claim, "updated_at": now}, synchronize_session=False)
        db.commit()
        if not acquired:
            return
        db.refresh(row)
    results = dict(row.results or {})
    statuses = dict(results.get("samples") or {})
    pilot = read_ai_access_tier(db) == "admin_only"
    clusters = FeedbackGovernanceService(db).cluster_failures(
        caller_role="Admin", rating="down", since=now - timedelta(days=30),
    ).clusters
    analyzer = NemotronFeedbackAnalyzerService(db)
    # A regression still counts when its trace falls outside the cluster sample.
    flagged_correction = db.query(AiInteractionTrace.id).filter(
        AiInteractionTrace.created_at >= now - timedelta(days=30),
        AiInteractionTrace.feedback_rating == "down",
        AiInteractionTrace.structured_response["applied_correction"].as_string() == MEASUREMENT_RULE,
    ).first()
    replay_status = "withdrawn" if flagged_correction else "insufficient_evidence"
    flagged_ranking = db.query(AiInteractionTrace.id).filter(
        AiInteractionTrace.created_at >= now - timedelta(days=30),
        AiInteractionTrace.feedback_rating == "down",
        AiInteractionTrace.structured_response["applied_correction"].as_string() == CONCISE_RANKING_RULE,
    ).first()
    ranking_status = "withdrawn" if flagged_ranking else "insufficient_evidence"
    ranking_affected_users = 0
    for cluster in clusters:
        if not flagged_correction:
            verdict = replay_measurement_correction(db, cluster.traces, min_users=3)
            if verdict in {"verified", "withdrawn"}:
                replay_status = verdict
            if verdict == "withdrawn":
                flagged_correction = True
        if not flagged_ranking:
            r_verdict = replay_ranking_correction(db, cluster.traces, min_users=3)
            ranking_affected_users = max(ranking_affected_users, int(r_verdict.get("affected_users") or 0))
            r_st = str(r_verdict.get("status") or "insufficient_evidence")
            if r_st in {"verified", "withdrawn"}:
                ranking_status = r_st
            if r_st == "withdrawn":
                flagged_ranking = True
    for cluster in clusters:
        if len(statuses) >= 3 or not is_feedback_analyzer_configured():
            break
        if cluster.affected_users < (1 if pilot else 3) or not cluster.traces:
            continue
        trace_id = cluster.traces[0].trace_id
        if trace_id in statuses:
            continue
        result = analyzer.analyze_worker_sample(trace_id)
        statuses[trace_id] = result.outcome
        owned = db.query(AiLearningRun).filter_by(day=day, claim=claim).update(
            {"results": {"samples": statuses}, "updated_at": datetime.now(timezone.utc)},
            synchronize_session=False,
        )
        db.commit()
        if not owned:
            return
    db.query(AiLearningRun).filter_by(day=day, claim=claim).update(
        {
            "state": "completed",
            "results": {
                "samples": statuses,
                "measurement_correction": replay_status,
                "ranking_correction": ranking_status,
                "ranking_affected_users": ranking_affected_users,
            },
            "updated_at": datetime.now(timezone.utc),
        },
        synchronize_session=False,
    )
    db.commit()
