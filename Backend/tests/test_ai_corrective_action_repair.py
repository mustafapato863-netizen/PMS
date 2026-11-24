"""Focused PR 3 regression tests: bounded 1-retry corrective draft repair and safety boundaries."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.ai_schemas import AiCorrectiveActionSuggestionRequest
from models.models import Action, Employee, KPIValue, PerformanceRecord, Team
from services.ai import corrective_action_drafter as drafter_mod
from services.ai.catalog import ai_evidence_cache
from services.ai.corrective_action_drafter import (
    CorrectiveActionDrafter,
    classify_draft_validation_errors,
    corrective_draft_repair_enabled,
)
from services.ai.providers import ProviderResponse

ADMIN_SCOPE = {
    "user_id": "u-repair-adm",
    "role": "Admin",
    "permissions": ["*"],
    "has_unrestricted_team_access": True,
}


def _seed_inbound_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    team = Team(
        id=uuid.uuid4(),
        name="inbound",
        db_name="Inbound",
        display_name="Inbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    db.add(team)
    db.flush()
    employee = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-1",
        name="Sara Inbound",
        team_id=team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    db.add(employee)
    db.flush()
    record = PerformanceRecord(
        id=uuid.uuid4(),
        employee_id=employee.id,
        team_id=team.id,
        month="September",
        year=2026,
        performance_level="Employee",
        position_name="Agent",
        region="EGY",
        branch_key=None,
        score=70.0,
        grade="C",
        status="Below",
    )
    db.add(record)
    db.flush()
    for key, actual, target, ratio, weight in [("bookings_count", 30, 40, 0.75, 0.5), ("upsell", 0, 10, 0.0, 0.2)]:
        db.add(
            KPIValue(
                record_id=record.id,
                record_year=2026,
                kpi_key=key,
                actual_value=actual,
                target_value=target,
                achievement_ratio=ratio,
                weight_applied=weight,
                contribution=ratio * weight,
            )
        )
    db.commit()
    return db


class _SequentialEngine:
    def __init__(self, responses: list[ProviderResponse]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def generate(self, request):
        idx = min(len(self.calls), len(self.responses) - 1)
        self.calls.append(
            {
                "purpose": getattr(request, "purpose", None),
                "user": request.messages[-1].content if request.messages else "",
                "timeout_seconds": getattr(request, "timeout_seconds", None),
            }
        )
        return self.responses[idx]


def _default_req() -> AiCorrectiveActionSuggestionRequest:
    return AiCorrectiveActionSuggestionRequest(
        employee_id="EMP-1",
        team="Inbound",
        month="September",
        year=2026,
        performance_level="Employee",
        linked_kpi_key="bookings_count",
    )


def test_classify_draft_validation_errors_distinguishes_repairable_vs_safety():
    assert (
        classify_draft_validation_errors(parsed_ok=True, raw={"focus_kpi_key": "upsell"}, errors=["focus_kpi_mismatch"])
        == "repairable_structure_or_focus"
    )
    assert (
        classify_draft_validation_errors(parsed_ok=False, raw=None, errors=["malformed_model_response"])
        == "repairable_structure_or_focus"
    )
    assert (
        classify_draft_validation_errors(
            parsed_ok=True,
            raw={"focus_kpi_key": "bookings_count"},
            errors=["word_outside_allowed_vocabulary", "invented_cause"],
        )
        == "non_repairable_safety_or_fact"
    )


def test_focus_kpi_mismatch_recovers_via_single_bounded_repair(monkeypatch):
    monkeypatch.setenv("PMS_AI_NVIDIA_ROUTING_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED", "true")
    ai_evidence_cache.clear()
    db = _seed_inbound_db()
    try:
        wrong_focus = json.dumps(
            {
                "focus_kpi_key": "upsell",
                "action_type": "Coaching",
                "steps": [
                    "Review recent calls with missed Bookings opportunities.",
                    "Hold a short coaching session on Bookings talk tracks.",
                ],
            }
        )
        valid_focus = json.dumps(
            {
                "focus_kpi_key": "bookings_count",
                "action_type": "Coaching",
                "steps": [
                    "Review recent calls with missed Bookings opportunities.",
                    "Hold a short coaching session on Bookings talk tracks.",
                ],
            }
        )
        eng = _SequentialEngine(
            [
                ProviderResponse(outcome="success", content=wrong_focus, provider="nvidia", model="mock-v1", latency_ms=22.0),
                ProviderResponse(outcome="success", content=valid_focus, provider="nvidia", model="mock-v1", latency_ms=18.0),
            ]
        )
        monkeypatch.setattr(drafter_mod, "get_unified_provider_engine", lambda: eng)
        payload = CorrectiveActionDrafter(db).suggest(user_scope=ADMIN_SCOPE, request=_default_req())

        assert payload.outcome == "suggested"
        assert payload.repair_attempted is True
        assert payload.repair_outcome == "repaired"
        assert payload.repair_latency_ms == 18.0
        assert len(eng.calls) == 2
        assert eng.calls[1]["purpose"] == "corrective_action_draft_repair"
        # Repair prompt preserves top-level evidence structure and zero unconfirmed writes occur.
        repair_evidence = json.loads(eng.calls[1]["user"])
        assert repair_evidence["focus_kpi"]["kpi_key"] == "bookings_count"
        assert db.query(Action).count() == 0
    finally:
        ai_evidence_cache.clear()
        db.close()


def test_non_repairable_fabrication_skips_retry_and_preserves_pms_fallback(monkeypatch):
    monkeypatch.setenv("PMS_AI_NVIDIA_ROUTING_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED", "true")
    ai_evidence_cache.clear()
    db = _seed_inbound_db()
    try:
        fabricated = json.dumps(
            {
                "focus_kpi_key": "bookings_count",
                "action_type": "Coaching",
                "steps": [
                    "Address staff fatigue causing missed calls.",
                    "Hold a coaching session because of staffing shortage.",
                ],
            }
        )
        valid = json.dumps(
            {
                "focus_kpi_key": "bookings_count",
                "action_type": "Coaching",
                "steps": [
                    "Review recent calls with missed Bookings opportunities.",
                    "Hold a short coaching session on Bookings talk tracks.",
                ],
            }
        )
        eng = _SequentialEngine(
            [
                ProviderResponse(outcome="success", content=fabricated, provider="nvidia", model="mock-v1", latency_ms=20.0),
                ProviderResponse(outcome="success", content=valid, provider="nvidia", model="mock-v1", latency_ms=20.0),
            ]
        )
        monkeypatch.setattr(drafter_mod, "get_unified_provider_engine", lambda: eng)
        payload = CorrectiveActionDrafter(db).suggest(user_scope=ADMIN_SCOPE, request=_default_req())

        assert payload.outcome == "draft_rejected"
        assert payload.repair_attempted is False
        assert payload.repair_outcome == "non_repairable"
        assert len(eng.calls) == 1
        assert payload.evidence_next_step is not None
        assert payload.evidence_next_step_source == "pms_evidence"
    finally:
        ai_evidence_cache.clear()
        db.close()


def test_deadline_exhausted_skips_repair_cleanly(monkeypatch):
    monkeypatch.setenv("PMS_AI_NVIDIA_ROUTING_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED", "true")
    monkeypatch.setattr(drafter_mod, "synthesis_timeout_seconds", lambda: 10.0)
    ai_evidence_cache.clear()
    db = _seed_inbound_db()
    try:
        wrong_focus = json.dumps(
            {
                "focus_kpi_key": "upsell",
                "action_type": "Coaching",
                "steps": [
                    "Review recent calls with missed Bookings opportunities.",
                    "Hold a short coaching session on Bookings talk tracks.",
                ],
            }
        )
        # First call consumed 9,500ms out of a 10,000ms budget -> < 1.5s remaining window -> skip repair
        eng = _SequentialEngine(
            [ProviderResponse(outcome="success", content=wrong_focus, provider="nvidia", model="mock-v1", latency_ms=9500.0)]
        )
        monkeypatch.setattr(drafter_mod, "get_unified_provider_engine", lambda: eng)
        payload = CorrectiveActionDrafter(db).suggest(user_scope=ADMIN_SCOPE, request=_default_req())

        assert payload.outcome == "draft_rejected"
        assert payload.repair_attempted is False
        assert payload.repair_outcome == "time_exhausted"
        assert len(eng.calls) == 1
    finally:
        ai_evidence_cache.clear()
        db.close()


def test_reversible_repair_toggle_disables_retry(monkeypatch):
    monkeypatch.setenv("PMS_AI_NVIDIA_ROUTING_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED", "false")
    assert corrective_draft_repair_enabled() is False
    ai_evidence_cache.clear()
    db = _seed_inbound_db()
    try:
        wrong_focus = json.dumps(
            {
                "focus_kpi_key": "upsell",
                "action_type": "Coaching",
                "steps": [
                    "Review recent calls with missed Bookings opportunities.",
                    "Hold a short coaching session on Bookings talk tracks.",
                ],
            }
        )
        eng = _SequentialEngine(
            [ProviderResponse(outcome="success", content=wrong_focus, provider="nvidia", model="mock-v1", latency_ms=12.0)]
        )
        monkeypatch.setattr(drafter_mod, "get_unified_provider_engine", lambda: eng)
        payload = CorrectiveActionDrafter(db).suggest(user_scope=ADMIN_SCOPE, request=_default_req())

        assert payload.outcome == "draft_rejected"
        assert payload.repair_attempted is False
        assert payload.repair_outcome == "non_repairable"
        assert len(eng.calls) == 1
    finally:
        ai_evidence_cache.clear()
        db.close()
