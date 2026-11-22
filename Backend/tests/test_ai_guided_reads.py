"""Acceptance tests for guided corrective-action reads, searchable product guide, compound requests,
RBAC enforcement, read-only immutability, rollback toggle, Reachability target assessment, Waiting Time
regression protection, and the 24-case (12 dev + 12 held-out) evaluation suite.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.ai_schemas import AiChatRequest, SessionFilterContext
from models.models import (
    Action,
    Employee,
    PerformanceRecord as OrmPerformanceRecord,
    Team,
    TeamConfigurationVersion,
    User,
    UserTeamAssignment,
)
from models.schemas import (
    AchievementMetrics,
    ActualMetrics,
    CallsData,
    EvaluationData,
    GeoData,
    PerformanceRecord as SchemaPerformanceRecord,
)
from services.ai.catalog import ai_evidence_cache
from services.ai.orchestrator import PmsAiOrchestrator
from services.corrective_action_service import CorrectiveActionService
from services.dashboard_record_service import DashboardRecordService
from services.database_record_source import DatabaseRecordSource

TODAY = dt.date(2026, 9, 27)
ID_INB_OVERDUE = "11111111-1111-1111-1111-111111111111"
ID_INB_UPCOMING = "22222222-2222-2222-2222-222222222222"
ID_INB_COMPLETED = "33333333-3333-3333-3333-333333333333"
ID_OUT_OVERDUE = "44444444-4444-4444-4444-444444444444"
ID_FIN_OVERDUE = "55555555-5555-5555-5555-555555555555"


def _seed_guided_db():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng, autoflush=False, autocommit=False)()

    t_inb = Team(name="Inbound", db_name="Inbound", display_name="Inbound", region="EGY")
    t_out = Team(name="Outbound", db_name="Outbound", display_name="Outbound", region="EGY")
    t_fin = Team(name="Finance", db_name="Finance", display_name="Finance", region="EGY")
    db.add_all([t_inb, t_out, t_fin])
    db.flush()

    e1 = Employee(employee_id="EMP-INB-1", name="Sara Inbound", team_id=t_inb.id, region="EGY", position_name="Inbound Agent")
    e2 = Employee(employee_id="EMP-OUT-1", name="Omar Outbound", team_id=t_out.id, region="EGY", position_name="Outbound Agent")
    e3 = Employee(employee_id="EMP-FIN-1", name="Heba Finance", team_id=t_fin.id, region="EGY", position_name="General Accountant")
    db.add_all([e1, e2, e3])
    db.flush()

    for emp, team in ((e1, t_inb), (e2, t_out), (e3, t_fin)):
        db.add(OrmPerformanceRecord(
            employee_id=emp.id,
            team_id=team.id,
            month="September",
            year=2026,
            region="EGY",
            performance_level="Employee",
            position_name=emp.position_name,
            score=78.0,
            grade="C",
            status="Needs Attention",
        ))

    u_admin = User(
        id=uuid.uuid4(),
        full_name="Admin Guided",
        username="admin_guided",
        email="admin@guided.test",
        password_hash="x",
        role="Admin",
        is_active=True,
    )
    u_out_mgr = User(
        id=uuid.uuid4(),
        full_name="Outbound Manager",
        username="mgr_outbound",
        email="out@guided.test",
        password_hash="x",
        role="Manager",
        is_active=True,
    )
    db.add_all([u_admin, u_out_mgr])
    db.flush()

    db.add(UserTeamAssignment(
        id=uuid.uuid4(),
        user_id=u_out_mgr.id,
        team_id=t_out.id,
        performance_level="Employee",
        access_level="write",
        assigned_by="test",
    ))

    actions = [
        Action(
            id=uuid.UUID(ID_INB_OVERDUE),
            employee_id=e1.id,
            team_id=t_inb.id,
            month="September",
            year=2026,
            status="Open",
            action_type="Coaching",
            action_text="Coach Sara on abandon rate",
            due_date=dt.date(2026, 9, 20),
            created_by_user_id=u_admin.id,
        ),
        Action(
            id=uuid.UUID(ID_INB_UPCOMING),
            employee_id=e1.id,
            team_id=t_inb.id,
            month="September",
            year=2026,
            status="Open",
            action_type="Coaching",
            action_text="Upcoming QA check for Sara",
            due_date=dt.date(2026, 10, 15),
            created_by_user_id=u_admin.id,
        ),
        Action(
            id=uuid.UUID(ID_INB_COMPLETED),
            employee_id=e1.id,
            team_id=t_inb.id,
            month="September",
            year=2026,
            status="Completed",
            action_type="Coaching",
            action_text="Completed script review for Sara",
            due_date=dt.date(2026, 9, 10),
            created_by_user_id=u_admin.id,
        ),
        Action(
            id=uuid.UUID(ID_OUT_OVERDUE),
            employee_id=e2.id,
            team_id=t_out.id,
            month="September",
            year=2026,
            status="In Progress",
            action_type="PIP",
            action_text="Outbound reachability follow-up for Omar",
            due_date=dt.date(2026, 9, 18),
            created_by_user_id=u_admin.id,
        ),
        Action(
            id=uuid.UUID(ID_FIN_OVERDUE),
            employee_id=e3.id,
            team_id=t_fin.id,
            month="September",
            year=2026,
            status="Open",
            action_type="Warning",
            action_text="Finance reconciliation overdue for Heba",
            due_date=dt.date(2026, 9, 15),
            created_by_user_id=u_admin.id,
        ),
    ]
    db.add_all(actions)

    # Approved-but-not-yet-applied monthly evaluation version for Outbound Reachability
    db.add(TeamConfigurationVersion(
        id=uuid.uuid4(),
        team_id=t_out.id,
        version_number=2,
        status="approved",
        effective_month="September",
        effective_year=2026,
        effective_from_month=9,
        effective_from_year=2026,
        effective_until_month=9,
        effective_until_year=2026,
        config_snapshot={"targets": {"Other": 0.75}, "weights": {"Other": 0.10}},
        config_checksum="a" * 64,
        performance_level="Employee",
        position_name="",
        is_active=True,
    ))
    db.commit()
    return db, {"t_inb": t_inb, "t_out": t_out, "t_fin": t_fin, "e1": e1, "u_admin": u_admin, "u_out_mgr": u_out_mgr}


def _outbound_reachability_records() -> list[SchemaPerformanceRecord]:
    return [
        SchemaPerformanceRecord(
            id="OUT-JUL-1",
            employee_id="OUT1",
            employee_name="Omar Outbound",
            team="Outbound",
            region="EGY",
            performance_level="Employee",
            month="July",
            year=2026,
            evaluation=EvaluationData(score=88.0, grade="B"),
            actual=ActualMetrics(other=72.0),
            achievement=AchievementMetrics(other=90.0),
            calls=CallsData(total_handled=120),
            geo=GeoData(),
            kpi_values=[{"kpi_key": "Other", "label": "Reachability", "actual_value": 72.0, "target_value": 80.0, "achievement": 90.0, "unit": "%", "direction": "higher_better"}],
        ),
        SchemaPerformanceRecord(
            id="OUT-AUG-1",
            employee_id="OUT1",
            employee_name="Omar Outbound",
            team="Outbound",
            region="EGY",
            performance_level="Employee",
            month="August",
            year=2026,
            evaluation=EvaluationData(score=81.0, grade="B"),
            actual=ActualMetrics(other=64.0),
            achievement=AchievementMetrics(other=80.0),
            calls=CallsData(total_handled=115),
            geo=GeoData(),
            kpi_values=[{"kpi_key": "Other", "label": "Reachability", "actual_value": 64.0, "target_value": 80.0, "achievement": 80.0, "unit": "%", "direction": "higher_better"}],
        ),
    ]


def _patch_analysis_records(monkeypatch, records: list[SchemaPerformanceRecord]) -> None:
    monkeypatch.setattr(DatabaseRecordSource, "get_all", lambda *a, **kw: list(records))
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda *a, **kw: list(records))
    monkeypatch.setattr(DashboardRecordService, "list_record_index", lambda *a, **kw: None)


def _snapshot_actions(db) -> list[tuple]:
    rows = db.query(Action).order_by(Action.id.asc()).all()
    return [(str(r.id), r.status, r.due_date, r.action_text, r.is_active) for r in rows]


def test_five_core_workflow_cases_and_read_only_immutability(monkeypatch):
    """End-to-end verification of the 5 agreed workflow requests against independent list_follow_up oracles."""
    monkeypatch.setenv("PMS_AI_GUIDED_READS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_REFERENCE_DATE", TODAY.isoformat())
    ai_evidence_cache.clear()
    db, _ = _seed_guided_db()
    try:
        before_snapshot = _snapshot_actions(db)
        scope = {"role": "Admin", "user_id": "admin-core", "has_unrestricted_team_access": True}
        svc = CorrectiveActionService(db, today=TODAY)
        exp_overdue_all = [a["id"] for a in svc.list_follow_up(scope, state="overdue")["actions"]]
        exp_completed_all = [a["id"] for a in svc.list_follow_up(scope, state="completed")["actions"]]
        exp_overdue_out = [a["id"] for a in svc.list_follow_up(scope, state="overdue", team="Outbound")["actions"]]
        assert exp_overdue_all == [ID_FIN_OVERDUE, ID_OUT_OVERDUE, ID_INB_OVERDUE]
        assert exp_completed_all == [ID_INB_COMPLETED]
        assert exp_overdue_out == [ID_OUT_OVERDUE]

        orch = PmsAiOrchestrator(db, scope)

        # 1. Where can I see corrective actions?
        r1 = orch.run_chat_turn(AiChatRequest(prompt="Where can I see corrective actions?", provider_override="deterministic"))
        assert r1.outcome == "answer"
        assert any(n.route == "/corrective-actions" for n in r1.navigation_targets)
        assert "Follow-up" in (r1.headline + " " + " ".join(r1.narrative_bullets))

        # 2. Show overdue corrective actions.
        r2 = orch.run_chat_turn(AiChatRequest(prompt="Show overdue corrective actions.", provider_override="deterministic"))
        assert r2.outcome == "answer"
        assert r2.validated_plan_v2 is not None
        assert r2.validated_plan_v2.operations[0].kind == "corrective_actions"
        assert r2.validated_plan_v2.operations[0].args.get("state") == "overdue"
        assert r2.tool_calls[0].records_evaluated == len(exp_overdue_all)
        assert r2.tool_calls[0].arguments["record_ids"] == exp_overdue_all
        assert "3 overdue" in r2.headline
        assert "2026-09-20" in " ".join(r2.narrative_bullets)

        # 3. Show completed ones. (follow-up switches state to completed)
        r3 = orch.run_chat_turn(AiChatRequest(
            prompt="Show completed ones.",
            conversation_id=r2.conversation_id,
            context_version=r2.context_version,
            session_state=r2.resolved_session_state,
            provider_override="deterministic",
        ))
        assert r3.outcome == "answer"
        assert r3.tool_calls[0].arguments["record_ids"] == exp_completed_all
        assert "1 completed" in r3.headline

        # 4. Compound: Show overdue corrective actions and tell me where to follow up.
        r4 = orch.run_chat_turn(AiChatRequest(
            prompt="Show overdue corrective actions and tell me where to follow up.",
            provider_override="deterministic",
        ))
        assert r4.outcome == "answer"
        assert r4.validated_plan_v2 is not None
        assert [op.kind for op in r4.validated_plan_v2.operations] == ["corrective_actions", "guide_lookup"]
        assert r4.validated_plan_v2.operations[0].args.get("state") == "overdue"
        ca_tc = next(tc for tc in r4.tool_calls if tc.tool_name == "get_corrective_actions_status")
        guide_tc = next(tc for tc in r4.tool_calls if tc.tool_name == "guide_lookup")
        assert ca_tc.arguments["record_ids"] == exp_overdue_all
        assert guide_tc.arguments.get("guide_sections")
        assert any(n.route == "/corrective-actions" for n in r4.navigation_targets)
        combined4 = r4.headline + " " + " ".join(r4.narrative_bullets)
        assert "3 overdue" in combined4 and "Follow-up" in combined4 and "Overdue" in combined4

        # 5. Follow-up: What about Outbound? (keeps overdue state, switches team after access check)
        r5 = orch.run_chat_turn(AiChatRequest(
            prompt="What about Outbound?",
            conversation_id=r4.conversation_id,
            context_version=r4.context_version,
            session_state=r4.resolved_session_state,
            provider_override="deterministic",
        ))
        assert r5.outcome == "answer"
        assert r5.tool_calls[0].arguments["record_ids"] == exp_overdue_out
        assert "1 overdue" in r5.headline and "Outbound" in r5.headline

        # Read-only guarantee: zero changes to action records
        assert _snapshot_actions(db) == before_snapshot
    finally:
        db.close()


def test_full_count_before_truncation_empty_failed_read_and_partial_guide_failure(monkeypatch):
    """Verify full filtering count before display limit, empty valid outcome, failed read unavailable, and partial compound fallback."""
    monkeypatch.setenv("PMS_AI_GUIDED_READS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_REFERENCE_DATE", TODAY.isoformat())
    ai_evidence_cache.clear()
    db, meta = _seed_guided_db()
    try:
        # Add 8 more overdue Inbound actions so total overdue = 11 (> 8 display limit)
        for i in range(8):
            db.add(Action(
                id=uuid.uuid4(),
                employee_id=meta["e1"].id,
                team_id=meta["t_inb"].id,
                month="September",
                year=2026,
                status="Open",
                action_type="Coaching",
                action_text=f"Extra overdue coaching #{i + 1}",
                due_date=dt.date(2026, 9, 10 + (i % 5)),
                created_by_user_id=meta["u_admin"].id,
            ))
        db.commit()

        scope = {"role": "Admin", "user_id": "admin-edge", "has_unrestricted_team_access": True}
        orch = PmsAiOrchestrator(db, scope)

        # Count reflects all 11 matching authorized records before display limit
        r_many = orch.run_chat_turn(AiChatRequest(prompt="Show overdue corrective actions.", provider_override="deterministic"))
        assert r_many.outcome == "answer"
        assert r_many.tool_calls[0].records_evaluated == 11
        assert len(r_many.tool_calls[0].arguments["record_ids"]) == 11
        assert "11 overdue" in r_many.headline
        assert any("of 11" in b for b in r_many.detail_bullets)

        # Partial failure: records succeed while guide lookup fails -> returns records + explains missing guide
        import services.ai.product_guide as pg_mod

        monkeypatch.setattr(pg_mod, "search_product_guide", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("guide disk err")))
        r_partial = orch.run_chat_turn(AiChatRequest(
            prompt="Show overdue corrective actions and tell me where to follow up.",
            provider_override="deterministic",
        ))
        assert r_partial.outcome == "answer"
        assert "11 overdue" in r_partial.headline
        assert "guide section is currently unavailable" in (r_partial.headline + " " + " ".join(r_partial.narrative_bullets)).casefold()

        # Service read failure -> reported honestly as unavailable_data, never 0 results
        monkeypatch.setattr(CorrectiveActionService, "list_follow_up", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("db timeout")))
        r_fail = orch.run_chat_turn(AiChatRequest(prompt="Show overdue corrective actions.", provider_override="deterministic"))
        assert r_fail.outcome == "unavailable_data"
        assert "temporarily unavailable" in r_fail.headline.casefold()
    finally:
        db.close()


def test_rollback_flag_restores_previous_behavior(monkeypatch):
    """PMS_AI_GUIDED_READS_ENABLED=false disables guided reads cleanly without DB changes."""
    monkeypatch.setenv("PMS_AI_GUIDED_READS_ENABLED", "false")
    ai_evidence_cache.clear()
    db, _ = _seed_guided_db()
    try:
        scope = {"role": "Admin", "user_id": "admin-rb", "has_unrestricted_team_access": True}
        orch = PmsAiOrchestrator(db, scope)
        resp = orch.run_chat_turn(AiChatRequest(prompt="Show overdue corrective actions and tell me where to follow up.", provider_override="deterministic"))
        assert resp.model_used != "pms-guided-reads-v1"
        assert all(tc.tool_name != "guide_lookup" for tc in resp.tool_calls)
    finally:
        db.close()


def test_reachability_target_assessment_hypothetical_and_missing_evidence(monkeypatch):
    """Outbound Reachability assessment: actual stays fixed while hypothetical target changes attainment; pending approved target shown separately."""
    monkeypatch.setenv("PMS_AI_GUIDED_READS_ENABLED", "true")
    _patch_analysis_records(monkeypatch, _outbound_reachability_records())
    ai_evidence_cache.clear()
    db, _ = _seed_guided_db()
    try:
        scope = {"role": "Admin", "user_id": "admin-reach", "has_unrestricted_team_access": True}
        orch = PmsAiOrchestrator(db, scope)

        # Full assessment across July (72% vs 80%) and August (64% vs 80%) + pending approved target (75%)
        r_base = orch.run_chat_turn(AiChatRequest(
            prompt="Should we adjust the Outbound Reachability target?",
            provider_override="deterministic",
        ))
        assert r_base.outcome == "answer"
        txt = r_base.headline + " " + " ".join(r_base.narrative_bullets)
        assert "64.0%" in txt and "80.0%" in txt
        assert "Pending approved target (not yet applied)" in txt and "75.0%" in txt
        assert "Performance decline explanation fits better" in txt

        # Hypothetical target 70% vs 60%: actual stays 64.0%, attainment changes (91.4% vs 100.0% at PMS cap)
        r_70 = orch.run_chat_turn(AiChatRequest(
            prompt="What if we lower the Outbound Reachability target to 70%?",
            provider_override="deterministic",
        ))
        r_60 = orch.run_chat_turn(AiChatRequest(
            prompt="What if we lower the Outbound Reachability target to 60%?",
            provider_override="deterministic",
        ))
        assert "fixed at 64.0%" in r_70.headline and "91.4%" in r_70.headline
        assert "fixed at 64.0%" in r_60.headline and "100.0%" in r_60.headline

        # Insufficient evidence (no Outbound records) discloses missing evidence honestly
        _patch_analysis_records(monkeypatch, [])
        r_empty = orch.run_chat_turn(AiChatRequest(
            prompt="Should we adjust the Outbound Reachability target?",
            provider_override="deterministic",
        ))
        assert "Insufficient Outbound Reachability evidence" in r_empty.headline
    finally:
        db.close()


def test_waiting_time_kpi_regression_preserved_when_guided_reads_enabled(monkeypatch):
    """Pharmacy Waiting Time KPI queries remain on the verified KPI read path with exact min unit."""
    monkeypatch.setenv("PMS_AI_GUIDED_READS_ENABLED", "true")
    records = [
        SchemaPerformanceRecord(
            id="PH-1-SEP",
            employee_id="PH001",
            employee_name="Nadia Pharmacist",
            team="Pharmacy",
            region="UAE",
            performance_level="Employee",
            month="September",
            year=2026,
            evaluation=EvaluationData(score=92.0, grade="B"),
            calls=CallsData(),
            geo=GeoData(),
            kpi_values=[{"kpi_key": "WaitingTime", "label": "Waiting Time", "actual_value": 4.5, "target_value": 5.0, "achievement": 111.1, "unit": "min", "direction": "lower_better"}],
        )
    ]
    _patch_analysis_records(monkeypatch, records)
    ai_evidence_cache.clear()
    db, _ = _seed_guided_db()
    try:
        scope = {"role": "Admin", "user_id": "admin-wt", "has_unrestricted_team_access": True}
        orch = PmsAiOrchestrator(db, scope)
        resp = orch.run_chat_turn(AiChatRequest(
            prompt="What is Pharmacy Waiting Time in September 2026?",
            session_state=SessionFilterContext(team="Pharmacy", month="September", year=2026),
            provider_override="deterministic",
        ))
        assert resp.outcome == "answer"
        assert resp.model_used != "pms-guided-reads-v1"
        combined = (resp.headline + " " + " ".join(resp.narrative_bullets)).casefold()
        assert "4.5" in combined and "min" in combined
    finally:
        db.close()


def test_24_case_dev_and_heldout_guided_reads_eval_suite(monkeypatch):
    """Grade all 24 cases (12 dev + 12 held-out) on operations, filters, record IDs, routes, and RBAC."""
    monkeypatch.setenv("PMS_AI_GUIDED_READS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_REFERENCE_DATE", TODAY.isoformat())
    _patch_analysis_records(monkeypatch, _outbound_reachability_records())
    ai_evidence_cache.clear()

    fixture_path = Path(__file__).parent / "fixtures" / "ai_guided_reads_eval_v1.json"
    suite = json.loads(fixture_path.read_text(encoding="utf-8"))
    cases = suite["cases"]
    assert sum(1 for c in cases if c["split"] == "dev") == 12
    assert sum(1 for c in cases if c["split"] == "heldout") == 12

    db, meta = _seed_guided_db()
    try:
        before_snapshot = _snapshot_actions(db)
        scopes = {
            "Admin": {"role": "Admin", "user_id": str(meta["u_admin"].id), "has_unrestricted_team_access": True},
            "OutboundManager": {
                "role": "Manager",
                "user_id": str(meta["u_out_mgr"].id),
                "has_unrestricted_team_access": False,
                "accessible_functions": ["Call Center"],
                "accessible_teams": ["Outbound"],
            },
            "DubaiBranchDirector": {
                "role": "Branch Director",
                "user_id": "dir-dubai",
                "has_unrestricted_team_access": True,
                "accessible_branches": ["dubai"],
                "allowed_branches": ["dubai"],
            },
        }

        failures: list[str] = []
        for case in cases:
            orch = PmsAiOrchestrator(db, scopes[case["role"]])
            prev = None
            if case.get("prior_prompt"):
                prev = orch.run_chat_turn(AiChatRequest(prompt=case["prior_prompt"], provider_override="deterministic"))
            resp = orch.run_chat_turn(AiChatRequest(
                prompt=case["prompt"],
                conversation_id=prev.conversation_id if prev else None,
                context_version=prev.context_version if prev else None,
                session_state=prev.resolved_session_state if prev else SessionFilterContext(),
                provider_override="deterministic",
            ))

            cid = case["id"]
            if resp.outcome != case["expected_outcome"]:
                failures.append(f"{cid}: outcome {resp.outcome!r} != {case['expected_outcome']!r} ({resp.headline})")
                continue

            ops = [op.kind for op in (resp.validated_plan_v2.operations if resp.validated_plan_v2 else [])]
            if ops != case["expected_operations"]:
                failures.append(f"{cid}: ops {ops} != {case['expected_operations']}")

            if "expected_state" in case and resp.validated_plan_v2:
                actual_state = resp.validated_plan_v2.operations[0].args.get("state")
                if actual_state != case["expected_state"]:
                    failures.append(f"{cid}: state {actual_state!r} != {case['expected_state']!r}")

            if "expected_team" in case and resp.validated_plan_v2:
                if resp.validated_plan_v2.scope.team != case["expected_team"]:
                    failures.append(f"{cid}: team {resp.validated_plan_v2.scope.team!r} != {case['expected_team']!r}")

            if "expected_record_ids" in case:
                ca_tc = next((tc for tc in resp.tool_calls if tc.tool_name == "get_corrective_actions_status"), None)
                actual_ids = ca_tc.arguments.get("record_ids", []) if ca_tc else []
                if actual_ids != case["expected_record_ids"]:
                    failures.append(f"{cid}: record_ids {actual_ids} != {case['expected_record_ids']}")

            if "expected_routes" in case:
                actual_routes = [n.route for n in resp.navigation_targets]
                for exp_r in case["expected_routes"]:
                    if not any(r.startswith(exp_r) for r in actual_routes):
                        failures.append(f"{cid}: expected route {exp_r!r} not in {actual_routes}")
                if case["expected_routes"] == [] and actual_routes:
                    failures.append(f"{cid}: expected zero routes, got {actual_routes}")

            full_text = "\n".join([resp.headline, *resp.narrative_bullets, *resp.detail_bullets, *(n.route for n in resp.navigation_targets)])
            for group in case.get("must_contain_any", []):
                if not any(tok.casefold() in full_text.casefold() for tok in group):
                    failures.append(f"{cid}: missing any of {group} in {full_text!r}")
            for bad in case.get("must_not_contain", []):
                if bad.casefold() in full_text.casefold():
                    failures.append(f"{cid}: forbidden token {bad!r} leaked in {full_text!r}")

        assert not failures, "\n".join(failures)
        assert _snapshot_actions(db) == before_snapshot
    finally:
        db.close()
