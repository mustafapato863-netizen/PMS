from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.models import AiInteractionTrace, AiLearningRun
from services.ai import learning_worker
from services.ai.learning_corrections import (
    CONCISE_RANKING_RULE,
    MEASUREMENT_RULE,
    active_measurement_correction,
    active_ranking_correction,
    corrected_concise_ranking,
    corrected_measurement,
    replay_ranking_correction,
)
from services.ai.quality_summary import sampled_quality


def test_feedback_replay_activates_once_and_withdraws_on_regression(monkeypatch):
    engine = create_engine("sqlite://")
    AiInteractionTrace.__table__.create(engine)
    AiLearningRun.__table__.create(engine)
    monkeypatch.setenv("PMS_AI_BACKGROUND_LEARNING_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_AUTO_CORRECTIONS_ENABLED", "true")
    monkeypatch.setattr(learning_worker, "read_ai_enabled", lambda db: True)
    monkeypatch.setattr(learning_worker, "read_ai_access_tier", lambda db: "all_authenticated_users")
    monkeypatch.setattr(learning_worker, "is_feedback_analyzer_configured", lambda: False)
    plan = {"operation_kind_v2": "current_value"}
    evidence = [{"metric_id": "m", "kpi_key": "wait", "display_name": "Waiting time", "team": "Team A",
                 "actual": 3.4, "actual_display": "3.4 min", "period": "September 2026", "source_link": "/team/a"}]
    assert corrected_measurement(plan, evidence, "Waiting time was 3.4 min.") is None
    assert corrected_measurement(plan, evidence, "Waiting time was 3.40 minutes.") is None
    assert corrected_measurement(plan, evidence, "Waiting time was 13.4 minutes.")
    assert corrected_measurement({"operation_kind_v2": "trend"}, evidence, "Waiting time declined.") is None
    assert corrected_measurement(plan, evidence * 2, "Two figures.") is None
    response = {"structured_query": plan, "typed_evidence": evidence, "outcome": "answer", "headline": "It improved."}
    with Session(engine) as db:
        rows = [AiInteractionTrace(id=uuid4(), user_id=str(uuid4()), prompt="Wait?", sanitized_prompt="Wait?",
                                   feedback_rating="down", non_empty_evidence=True, structured_response=response)
                for _ in range(3)]
        db.add_all(rows)
        db.commit()
        samples = [SimpleNamespace(trace_id=str(r.id)) for r in rows]
        calls = []
        def clusters(*args, **kwargs):
            calls.append(1)
            return SimpleNamespace(clusters=[SimpleNamespace(affected_users=3, traces=samples)])
        monkeypatch.setattr(learning_worker.FeedbackGovernanceService, "cluster_failures", clusters)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        learning_worker.run_feedback_tick(db, yesterday)
        learning_worker.run_feedback_tick(db, yesterday)
        assert len(calls) == 1
        assert active_measurement_correction(db)
        assert "3.4 min" in corrected_measurement(plan, evidence, "It improved.")
        rows[0].structured_response = {**response, "applied_correction": MEASUREMENT_RULE}
        db.commit()
        samples.pop(0)
        learning_worker.run_feedback_tick(db)
        assert not active_measurement_correction(db)
        stats = sampled_quality(db)
        assert stats["corrected_answers"] == 1 and stats["flagged_turns"] == 3
        assert stats["sample_size"] == 3
        assert stats["flagged_after_correction"] == 1
        assert stats["weekly"] == [{"turns": 3, "flagged": 3}, {"turns": 0, "flagged": 0}]


def test_concise_ranking_correction_replay_activation_visibility_and_withdrawal(monkeypatch):
    engine = create_engine("sqlite://")
    AiInteractionTrace.__table__.create(engine)
    AiLearningRun.__table__.create(engine)
    monkeypatch.setenv("PMS_AI_BACKGROUND_LEARNING_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_AUTO_CORRECTIONS_ENABLED", "true")
    monkeypatch.setattr(learning_worker, "read_ai_enabled", lambda db: True)
    monkeypatch.setattr(learning_worker, "read_ai_access_tier", lambda db: "all_authenticated_users")
    monkeypatch.setattr(learning_worker, "is_feedback_analyzer_configured", lambda: False)

    plan = {
        "intent": "ranking",
        "operation_kind_v2": "ranking",
        "ranking_direction": "best",
        "query_rankings_args": {"entity": "department", "sort_order": "desc", "limit": 1, "group_by": "none"},
    }
    evidence = [{
        "metric_id": "overall_score",
        "kpi_key": "overall_score",
        "display_name": "Overall PMS Score",
        "team": "Sales",
        "actual": 83.2,
        "actual_display": "83.2%",
        "period": "September 2026",
        "source_link": "/monthly-presentation?region=uae",
    }]

    # Labeled verbose ranking & contrast cases
    verbose = ("Here is a very long multi-sentence explanation about various teams across the entire organization with extra commentary.", ["Bullet 1", "Bullet 2"])
    rewritten = corrected_concise_ranking(plan, evidence, verbose[0], verbose[1], detail="brief")
    assert rewritten is not None
    assert "Sales" in rewritten[0] and "83.2%" in rewritten[0] and rewritten[1] == []
    # Idempotent + contrast cases untouched
    assert corrected_concise_ranking(plan, evidence, rewritten[0], rewritten[1], detail="brief") is None
    assert corrected_concise_ranking(plan, evidence, verbose[0], verbose[1], detail="detailed") is None
    assert corrected_concise_ranking({"intent": "trend", "operation_kind_v2": "trend"}, evidence, verbose[0], verbose[1]) is None

    bloated_resp = {
        "structured_query": plan,
        "typed_evidence": evidence,
        "outcome": "answer",
        "answer_detail": "brief",
        "headline": verbose[0],
        "narrative_bullets": verbose[1],
        "feedback_governance": {"operation_family": "get_query_rankings", "reason_tag": "too_long"},
    }
    with Session(engine) as db:
        # 1) Single-user feedback -> stays INACTIVE (insufficient_evidence)
        single = AiInteractionTrace(
            id=uuid4(), user_id=str(uuid4()), prompt="best dep uae sep?", sanitized_prompt="best dep uae sep?",
            feedback_rating="down", non_empty_evidence=True, guardrail_triggered=False, structured_response=bloated_resp,
        )
        db.add(single)
        db.commit()
        monkeypatch.setattr(
            learning_worker.FeedbackGovernanceService,
            "cluster_failures",
            lambda *a, **kw: SimpleNamespace(clusters=[SimpleNamespace(affected_users=1, traces=[SimpleNamespace(trace_id=str(single.id))])]),
        )
        learning_worker.run_feedback_tick(db, datetime.now(timezone.utc) - timedelta(days=2))
        assert not active_ranking_correction(db)

        # 2) Multi-user (>= 3 independent users) -> ACTIVATES automatically
        rows = [
            AiInteractionTrace(
                id=uuid4(), user_id=str(uuid4()), prompt="top department uae sep", sanitized_prompt="top department uae sep",
                feedback_rating="down", non_empty_evidence=True, guardrail_triggered=False, structured_response=bloated_resp,
            )
            for _ in range(3)
        ]
        db.add_all(rows)
        db.commit()
        samples = [SimpleNamespace(trace_id=str(r.id)) for r in rows]
        monkeypatch.setattr(
            learning_worker.FeedbackGovernanceService,
            "cluster_failures",
            lambda *a, **kw: SimpleNamespace(clusters=[SimpleNamespace(affected_users=3, traces=samples)]),
        )
        learning_worker.run_feedback_tick(db, datetime.now(timezone.utc) - timedelta(days=1))
        assert active_ranking_correction(db)

        # Add clean corrected turn + check Admin quality summary metrics
        corrected_turn = AiInteractionTrace(
            id=uuid4(), user_id=str(uuid4()), prompt="which dept led uae", sanitized_prompt="which dept led uae",
            feedback_rating="up", non_empty_evidence=True, guardrail_triggered=False,
            structured_response={
                "outcome": "answer",
                "applied_correction": CONCISE_RANKING_RULE,
                "feedback_governance": {"operation_family": "get_query_rankings", "reason_tag": "helpful"},
            },
        )
        db.add(corrected_turn)
        db.commit()
        stats = sampled_quality(db)
        assert stats["ranking_correction_active"] is True
        rc = next(c for c in stats["corrections"] if c["id"] == CONCISE_RANKING_RULE)
        assert rc["status"] == "active" and rc["affected_users"] >= 3
        assert rc["before_flagged"] == 4 and rc["before_total"] == 4 and rc["before_failure_rate"] == 100.0
        assert rc["after_flagged"] == 0 and rc["after_total"] == 1 and rc["after_failure_rate"] == 0.0

        # 3) Negative feedback on corrected answer (even outside sampled cluster) -> WITHDRAWN
        corrected_turn.feedback_rating = "down"
        db.commit()
        learning_worker.run_feedback_tick(db, datetime.now(timezone.utc))
        assert not active_ranking_correction(db)
        stats_after = sampled_quality(db)
        rc_after = next(c for c in stats_after["corrections"] if c["id"] == CONCISE_RANKING_RULE)
        assert rc_after["status"] == "withdrawn"
        assert rc_after["flagged_after_correction"] == 1 and rc_after["corrected_answers"] == 1
