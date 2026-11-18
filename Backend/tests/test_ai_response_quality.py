from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ai_provider_fakes import failed_response, install_scripted_provider
from api.middleware.auth_middleware import AuthMiddleware
from api.routers.ai_workspace import router as ai_router
from config.database import Base, get_db
from models.ai_schemas import AiChatRequest, ConfirmedQueryContext, SessionFilterContext, TypedMetricEvidence
from models.models import ProductSetting
from services.ai.catalog import ai_evidence_cache
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.router import HybridQueryRouter
from services.auth_service import AuthenticationService
from services.dashboard_record_service import DashboardRecordService
from services.database_record_source import DatabaseRecordSource
from test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records


def _make_rich_records() -> list[SimpleNamespace]:
    recs: list[SimpleNamespace] = []
    # Inbound multi-month (July-October 2026)
    for month, sara_sc, adham_sc, sara_bk in [
        ("March", 80.0, 82.0, 110),
        ("April", 83.0, 85.0, 120),
        ("May", 85.0, 87.5, 130),
        ("June", 87.0, 90.0, 140),
        ("July", 88.0, 91.0, 150),
        ("August", 91.0, 96.5, 165),
        ("September", 94.0, 91.0, 195),
    ]:
        r1 = _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", sara_sc, 45, 50, sara_bk, 220, month=month)
        r1.position = "Senior Call Center Agent"
        r1.geo.bookings.dubai = sara_bk - 80
        r1.geo.bookings.sharjah = 50
        r1.geo.bookings.ajman = 30
        recs.append(r1)

        r2 = _make_call_center_record("EMP102", "Adham Tarek", "Inbound", adham_sc, 30, 50, 100, 150, month=month)
        r2.position = "Inbound Agent"
        r2.geo.bookings.dubai = 40
        r2.geo.bookings.sharjah = 35
        r2.geo.bookings.ajman = 25
        recs.append(r2)

    # Two Mariams in Inbound for disambiguation & missing HR join date check
    for month in ("July", "August", "September"):
        recs.append(_make_call_center_record("EMP601", "Mariam Ali", "Inbound", 88.0, 30, 50, 80, 100, month=month))
    for month in ("August", "September"):
        recs.append(_make_call_center_record("EMP602", "Mariam Hassan", "Inbound", 84.0, 25, 45, 70, 95, month=month))

    # Outbound agents (Omar leads bookings)
    for month in ("August", "September"):
        ob1 = _make_call_center_record("EMP201", "Omar Khalid", "Outbound", 89.0, 35, 40, 260, 300, month=month)
        ob1.position = "Outbound Specialist"
        ob1.geo.bookings.dubai = 140
        ob1.geo.bookings.sharjah = 70
        ob1.geo.bookings.ajman = 50
        recs.append(ob1)

    # Support Positions with tie + position
    sup1 = _make_call_center_record("EMP301", "Kareem Adel", "Call Center", 62.0, 0, 0, 0, 0, month="September")
    sup1.position = "Quality Assurance"
    sup2 = _make_call_center_record("EMP302", "Ziad Nabil", "Call Center", 62.0, 0, 0, 0, 0, month="September")
    sup2.position = "Trainer"
    sup3 = _make_call_center_record("EMP303", "Nour Hassan", "Call Center", 93.0, 0, 0, 0, 0, month="September")
    sup3.position = "Workforce analyst"
    recs.extend([sup1, sup2, sup3])

    # RCM Pre-Approvals IP Offshore with Controllable Rejection Rate
    for month, rej in [("August", 0.08), ("September", 0.12)]:
        rcm = _make_call_center_record(
            "EMP401", "Heba Nabil", "Pre-Approvals IP Offshore", 86.0 if month == "September" else 90.0, 0, 0, 0, 0, month=month
        )
        rcm.region = "EGY"
        rcm.kpi_values = [
            {
                "kpi_key": "RejectionRate",
                "label": "Controllable Rejection Rate",
                "actual_value": rej,
                "target_value": 0.05,
                "achievement_ratio": 0.5,
                "weight_applied": 0.5,
                "unit": "%",
                "direction": "lower_better",
            }
        ]
        recs.append(rcm)
    return recs


def _install_db_read_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(DatabaseRecordSource, "get_all", lambda *a, **k: calls.append("db") or [])
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda *a, **k: calls.append("list") or [])
    return calls


@pytest.mark.parametrize(
    ("prompt", "expected_mode"),
    [
        ("How can you help with my team?", "capabilities_help"),
        ("What can you do for RCM?", "capabilities_help"),
        ("Hi", "greeting"),
        ("Thanks!", "greeting"),
        ("October", "clarification"),
        ("Check the numbers", "clarification"),
    ],
)
def test_keyword_and_help_gate_never_query_performance_data(
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
    expected_mode: str,
) -> None:
    monkeypatch.setenv("PMS_AI_INTENT_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    spy = _install_db_read_spy(monkeypatch)
    db = _build_in_memory_db()
    orch = PmsAiOrchestrator(db, {"role": "General Manager", "user_id": "u-gm", "has_unrestricted_team_access": True})

    # Even with a prior team in session_state (without a pending active analytical query), bare "October" / capabilities / greeting must not fetch team scores
    resp = orch.run_chat_turn(
        AiChatRequest(
            prompt=prompt,
            session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
        )
    )
    assert spy == []
    assert resp.tool_calls == []
    assert resp.capability_mode == expected_mode
    if expected_mode == "clarification":
        assert resp.outcome == "clarification"
    else:
        assert resp.outcome == "answer"
        if "RCM" in prompt:
            assert "RCM" in resp.headline


def test_multiturn_pronoun_correction_topic_switch_and_explain_previous(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_INTENT_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "true")

    db = _build_in_memory_db()
    _patch_records(monkeypatch, _make_rich_records())
    ai_evidence_cache.clear()
    orch = PmsAiOrchestrator(db, {"role": "General Manager", "user_id": "u-multi", "has_unrestricted_team_access": True})

    # 1. "Who leads bookings in Inbound?"
    t1 = orch.run_chat_turn(AiChatRequest(prompt="Who leads bookings in Inbound?"))
    assert t1.outcome == "answer"
    assert "Sara Mahmoud" in t1.headline
    assert t1.conversation_id is not None

    # 2. "And her position?" -> resolves pronoun from Sara Mahmoud cleanly
    t2 = orch.run_chat_turn(
        AiChatRequest(
            prompt="And her position?",
            conversation_id=t1.conversation_id,
            context_version=t1.context_version,
            session_state=t1.resolved_session_state,
        )
    )
    assert t2.outcome == "answer"
    assert "Sara Mahmoud" in t2.headline
    assert "Senior Call Center Agent" in t2.headline
    assert t2.structured_query is not None and t2.structured_query.employee_id == "EMP101"

    # 3. "No, I meant Outbound." -> switches team, clears Sara Mahmoud, preserves bookings ranking direction, recomputes
    t3 = orch.run_chat_turn(
        AiChatRequest(
            prompt="No, I meant Outbound.",
            conversation_id=t2.conversation_id,
            context_version=t2.context_version,
            session_state=t2.resolved_session_state,
        )
    )
    assert t3.outcome == "answer"
    assert "Omar Khalid" in t3.headline
    assert "Outbound" in t3.headline
    assert t3.structured_query is not None
    assert t3.structured_query.team == "Outbound"
    assert t3.structured_query.employee_id is None

    # 4. "Thanks!" -> brief ack without clearing valid Outbound context
    t4 = orch.run_chat_turn(
        AiChatRequest(
            prompt="Thanks!",
            conversation_id=t3.conversation_id,
            context_version=t3.context_version,
            session_state=t3.resolved_session_state,
        )
    )
    assert t4.outcome == "answer"
    assert t4.capability_mode == "greeting"
    assert t4.resolved_session_state.team == "Outbound"

    # 5. "Now show RCM rejection trends." -> topic switch clears Call Center, Outbound, bookings, employee
    t5 = orch.run_chat_turn(
        AiChatRequest(
            prompt="Now show RCM rejection trends.",
            conversation_id=t4.conversation_id,
            context_version=t4.context_version,
            session_state=t4.resolved_session_state,
        )
    )
    assert t5.outcome == "answer"
    assert "RCM" in t5.headline
    assert "Rejection Rate" in t5.headline
    assert t5.structured_query is not None
    assert t5.structured_query.function == "RCM"
    assert t5.structured_query.team is None
    assert t5.structured_query.employee_id is None
    assert "Inbound" not in t5.headline and "Outbound" not in t5.headline

    # 6. "What do you mean?" -> explains the RCM answer rather than running another generic team summary
    t6 = orch.run_chat_turn(
        AiChatRequest(
            prompt="What do you mean?",
            conversation_id=t5.conversation_id,
            context_version=t5.context_version,
            session_state=t5.resolved_session_state,
        )
    )
    assert t6.outcome == "answer"
    assert t6.capability_mode == "explain_previous"
    assert "RCM" in t6.headline
    assert t6.tool_calls == []


def test_tied_leading_agent_keeps_candidates_and_selected_followup_question(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_INTENT_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "true")

    db = _build_in_memory_db()
    _patch_records(monkeypatch, _make_rich_records())
    ai_evidence_cache.clear()
    orch = PmsAiOrchestrator(
        db,
        {"role": "General Manager", "user_id": "u-tie-followup", "has_unrestricted_team_access": True},
    )
    try:
        first = orch.run_chat_turn(
            AiChatRequest(
                prompt="Compare Inbound Booking Rate trend and reveal the leading agent in September 2026."
            )
        )
        assert first.outcome == "answer"
        assert first.resolved_session_state.last_confirmed_query is not None
        saved = first.resolved_session_state.last_confirmed_query
        assert saved.last_subject_employee_id is None
        assert {row["employee_id"] for row in saved.candidate_employees} >= {"EMP101", "EMP102"}, (
            saved.model_dump(),
            first.structured_query.model_dump() if first.structured_query else None,
        )

        followup = "How did her overall trend develop across those months?"
        ambiguous = orch.run_chat_turn(
            AiChatRequest(
                prompt=followup,
                conversation_id=first.conversation_id,
                context_version=first.context_version,
                session_state=first.resolved_session_state,
            )
        )
        assert ambiguous.outcome == "clarification"
        assert ambiguous.clarification is not None
        choices = {choice.id: choice for choice in ambiguous.clarification.choices}
        assert "choice-person-EMP101" in choices
        assert choices["choice-person-EMP101"].prompt_to_send == followup

        selected = orch.run_chat_turn(
            AiChatRequest(
                prompt=followup,
                clarification_choice_id="choice-person-EMP101",
                conversation_id=ambiguous.conversation_id,
                context_version=ambiguous.context_version,
                session_state=ambiguous.resolved_session_state,
            )
        )
        assert selected.outcome == "answer"
        assert "Sara Mahmoud" in selected.headline
        assert selected.structured_query is not None
        assert selected.structured_query.employee_id == "EMP101"
        assert selected.resolved_session_state.last_confirmed_query is not None
        assert selected.resolved_session_state.last_confirmed_query.last_subject_employee_id == "EMP101"
    finally:
        db.close()


def test_explicit_employee_outside_requested_team_asks_for_scope_clarification(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_INTENT_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "true")
    _patch_records(monkeypatch, _make_rich_records())
    ai_evidence_cache.clear()
    with _build_in_memory_db() as db:
        response = PmsAiOrchestrator(
            db,
            {"role": "General Manager", "user_id": "u-scope-mismatch", "has_unrestricted_team_access": True},
        ).run_chat_turn(
            AiChatRequest(
                prompt="What was Sara Mahmoud's score in Outbound in September 2026?",
            )
        )

    assert response.outcome == "clarification", response.model_dump()
    assert response.clarification is not None
    assert response.clarification.code == "AMBIGUOUS_PERSON"
    assert "Sara Mahmoud" in response.clarification.question
    assert "Inbound" in response.clarification.question
    assert "Outbound" in response.clarification.question
    assert response.tool_calls == []
    assert response.resolved_session_state.employee_id is None


def test_country_switch_is_visible_without_changing_team_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_INTENT_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "true")

    db = _build_in_memory_db()
    country_records = _make_rich_records()
    coding_uae = _make_call_center_record("EMP701", "Hassan Zaki", "Coding", 92.0, 20, 25, 35, 40)
    coding_uae.region = "UAE"
    coding_uae.position = "Medical Coder"
    coding_egy = _make_call_center_record("EMP801", "Mona Samir", "Coding EGY", 94.5, 20, 25, 35, 40)
    coding_egy.region = "EGY"
    coding_egy.position = "Medical Coder"
    country_records.extend([coding_uae, coding_egy])
    _patch_records(monkeypatch, country_records)
    ai_evidence_cache.clear()
    orch = PmsAiOrchestrator(
        db,
        {"role": "General Manager", "user_id": "u-country-display", "has_unrestricted_team_access": True},
    )
    try:
        egypt = orch.run_chat_turn(
            AiChatRequest(
                prompt="Review Coding performance for September 2026 in Egypt.",
                session_state=SessionFilterContext(month="September", year=2026),
            )
        )
        assert egypt.outcome == "answer"
        assert "Coding · Egypt" in egypt.headline
        assert "Coding · Egypt · Egypt" not in egypt.headline

        uae = orch.run_chat_turn(
            AiChatRequest(
                prompt="Make that UAE instead.",
                conversation_id=egypt.conversation_id,
                context_version=egypt.context_version,
                session_state=egypt.resolved_session_state,
            )
        )
        assert uae.outcome == "answer"
        assert "Coding · UAE" in uae.headline
        assert "Coding · UAE · UAE" not in uae.headline
        assert uae.resolved_session_state.region == "UAE"
        assert uae.structured_query is not None and uae.structured_query.team == "Coding"
    finally:
        db.close()


def test_bare_month_only_applies_when_active_analytical_context_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_INTENT_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "true")

    db = _build_in_memory_db()
    _patch_records(monkeypatch, _make_rich_records())
    ai_evidence_cache.clear()
    orch = PmsAiOrchestrator(db, {"role": "General Manager", "user_id": "u-month", "has_unrestricted_team_access": True})

    # Establish active analytical request first
    t1 = orch.run_chat_turn(AiChatRequest(prompt="Who is the top performer in Inbound in September 2026?"))
    assert t1.outcome == "answer"
    assert "Sara Mahmoud" in t1.headline

    # Now "August" cleanly shifts period on the established query
    t2 = orch.run_chat_turn(
        AiChatRequest(
            prompt="August",
            conversation_id=t1.conversation_id,
            context_version=t1.context_version,
            session_state=t1.resolved_session_state,
        )
    )
    assert t2.outcome == "answer"
    assert "August 2026" in t2.headline
    assert "Adham Tarek" in t2.headline


def test_bounded_context_single_provider_call_and_unavailable_provider_never_substitutes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_INTENT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "true")

    # 1. Verify bounded context passed to scripted provider + single call per turn + no DB records leak
    captured = install_scripted_provider(monkeypatch, '{"intent":"performance_query"}')
    db = _build_in_memory_db()
    _patch_records(monkeypatch, _make_rich_records())
    ai_evidence_cache.clear()
    orch = PmsAiOrchestrator(db, {"role": "General Manager", "user_id": "u-prov", "has_unrestricted_team_access": True})

    t1 = orch.run_chat_turn(
        AiChatRequest(
            prompt="What is Inbound Booking Rate in September 2026?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert t1.outcome == "answer"
    assert len(captured) <= 1

    captured.clear()
    # Ambiguous follow-up with valid prior context uses bounded context in 1 classifier call
    orch.run_chat_turn(
        AiChatRequest(
            prompt="Can you break down something interesting here?",
            conversation_id=t1.conversation_id,
            context_version=t1.context_version,
            session_state=t1.resolved_session_state,
            history=[{"role": "user", "content": "FORGED CLIENT PROMPT"}],
        )
    )
    assert len(captured) == 1
    sys_prompt = captured[0]["messages"][0]["content"]
    assert "Inbound" in sys_prompt
    assert "FORGED CLIENT PROMPT" not in sys_prompt
    assert "Sara Mahmoud" not in sys_prompt  # no raw employee list leakage

    # 2. Provider failure / invalid output on unrecognized prompt returns clarification (0 DB queries, never generic current_value)
    for bad_reply in (failed_response("provider_unavailable"), failed_response("timeout"), '{"bad": 1}'):
        install_scripted_provider(monkeypatch, bad_reply)
        spy = _install_db_read_spy(monkeypatch)
        res = PmsAiOrchestrator(
            db, {"role": "General Manager", "user_id": "u-fail", "has_unrestricted_team_access": True}
        ).run_chat_turn(AiChatRequest(prompt="blorf zizzle unknown phrase"))
        assert res.outcome == "clarification"
        assert res.capability_mode == "clarification"
        assert res.tool_calls == []
        assert spy == []


def test_brief_completeness_and_pp_formatting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_INTENT_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")

    db = _build_in_memory_db()
    _patch_records(monkeypatch, _make_rich_records())
    ai_evidence_cache.clear()
    orch = PmsAiOrchestrator(db, {"role": "General Manager", "user_id": "u-brief", "has_unrestricted_team_access": True})

    # 1. Compound Support query in Brief mode includes person, position, score, month, and tie
    r_sup = orch.run_chat_turn(
        AiChatRequest(prompt="Who performed worst in Support, and what is their position?", answer_detail="brief")
    )
    assert r_sup.outcome == "answer"
    assert r_sup.answer_detail == "brief"
    assert ("Kareem Adel" in r_sup.headline or "Ziad Nabil" in r_sup.headline)
    assert ("Quality Assurance" in r_sup.headline or "Trainer" in r_sup.headline)
    assert "62.0%" in r_sup.headline
    assert "September 2026" in r_sup.headline
    assert "tied with" in r_sup.headline

    # 2. Adham best month + full period comparison
    r_adham = orch.run_chat_turn(
        AiChatRequest(prompt="Was September Adham's best month?", session_state=SessionFilterContext(team="Inbound"))
    )
    assert r_adham.headline.startswith("No.")
    assert "August 2026 at 96.5%" in r_adham.headline
    assert "March–September 2026" in r_adham.headline

    # 3. 3-branch bookings comparison ranks all 3 branches
    r_br = orch.run_chat_turn(
        AiChatRequest(prompt="Which branch has the most Inbound bookings: Dubai, Ajman, or Sharjah?", answer_detail="brief")
    )
    combined_br = r_br.headline + " " + " ".join(r_br.narrative_bullets)
    assert all(b in combined_br for b in ("Dubai", "Sharjah", "Ajman"))

    # 4. Score movement uses percentage points ("pp")
    r_sara = orch.run_chat_turn(AiChatRequest(prompt="How did Sara Mahmoud score in September 2026?"))
    assert "pp vs August" in r_sara.headline


def test_permission_revocation_revalidates_saved_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_INTENT_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "true")

    db = _build_in_memory_db()
    _patch_records(monkeypatch, _make_rich_records())
    ai_evidence_cache.clear()

    full_scope = {
        "role": "Manager",
        "user_id": "00000000-0000-0000-0000-000000000555",
        "has_unrestricted_team_access": False,
        "accessible_functions": ["Call Center"],
        "accessible_teams": ["Inbound", "Outbound"],
    }
    t1 = PmsAiOrchestrator(db, full_scope).run_chat_turn(AiChatRequest(prompt="Who leads bookings in Inbound?"))
    assert t1.outcome == "answer"
    assert "Sara Mahmoud" in t1.headline

    # Revoke Inbound access before turn 2 on the same conversation
    revoked_scope = {
        "role": "Manager",
        "user_id": "00000000-0000-0000-0000-000000000555",
        "has_unrestricted_team_access": False,
        "accessible_functions": ["Call Center"],
        "accessible_teams": ["Outbound"],
    }
    t2 = PmsAiOrchestrator(db, revoked_scope).run_chat_turn(
        AiChatRequest(
            prompt="And her position?",
            conversation_id=t1.conversation_id,
            context_version=t1.context_version,
            session_state=t1.resolved_session_state,
        )
    )
    assert "Sara Mahmoud" not in t2.headline
    assert t2.outcome in ("clarification", "restricted_access")


def test_local_fastapi_multiturn_endpoint_and_fresh_chat_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_INTENT_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "true")

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        AuthenticationService.create_user(db, "rq_admin", "rq@example.invalid", "AdminSecret123!", "Admin")
        db.add(ProductSetting(key="ai_enabled", enabled=True))
        db.commit()
        tok = AuthenticationService.authenticate_user(db, "rq_admin", "AdminSecret123!")

    _patch_records(monkeypatch, _make_rich_records())
    ai_evidence_cache.clear()

    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(ai_router, prefix="/api")
    def override_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {tok}"}

    t0 = time.perf_counter()
    r1 = client.post("/api/ai/chat", headers=headers, json={"prompt": "Who leads bookings in Inbound?"})
    r1_ms = (time.perf_counter() - t0) * 1000.0
    assert r1.status_code == 200
    d1 = r1.json()["data"]
    assert "Sara Mahmoud" in d1["headline"]
    assert d1["provider_usage"]["provider_calls"] == 0

    r2 = client.post(
        "/api/ai/chat",
        headers=headers,
        json={
            "prompt": "No, I meant Outbound.",
            "conversation_id": d1["conversation_id"],
            "context_version": d1["context_version"],
            "session_state": d1["resolved_session_state"],
        },
    )
    assert r2.status_code == 200
    d2 = r2.json()["data"]
    assert "Omar Khalid" in d2["headline"]
    assert d2["provider_usage"]["provider_calls"] == 0
    assert r1_ms < 2000.0

    # Starting a new chat isolates context completely: "October" clarifies instead of inheriting Outbound
    r_new = client.post("/api/ai/conversations", headers=headers, json={"origin": "workspace"})
    new_cid = r_new.json()["data"]["conversation_id"]
    r_oct = client.post(
        "/api/ai/chat",
        headers=headers,
        json={"prompt": "October", "conversation_id": new_cid},
    )
    assert r_oct.status_code == 200
    d_oct = r_oct.json()["data"]
    assert d_oct["outcome"] == "clarification"
    assert d_oct["tool_calls"] == []


def test_explain_previous_provider_backed_validation_ambiguity_and_honest_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.ai.contextual_assistant import build_explain_previous_payload

    scope = {"role": "General Manager", "user_id": "u-exp", "has_unrestricted_team_access": True}
    ss = SessionFilterContext(function="RCM", team="Pre-Approvals IP Offshore")
    summary = {
        "restricted": False,
        "headline": "Pre-Approvals IP Offshore Controllable Rejection Rate reached 12.0% in September 2026, moving +4.0 pp vs August (8.0%).",
        "narrative_bullets": ["Target is 5.0%, so September is 7.0 pp above the allowed ceiling."],
        "detail_bullets": ["August: 8.0% · September: 12.0%"],
        "scope_banner": "All Branches · Pre-Approvals IP Offshore · Employee · September 2026",
        "basis_warning": "Scoring basis shifted in June 2026.",
        "structured_query": {"function": "RCM", "team": "Pre-Approvals IP Offshore", "metric": "pre_approvals_ip_offshore:rejection"},
        "evidence_items": [
            {"label": "Controllable Rejection Rate", "value": "12.0%", "target": "5.0%", "period": "2026-09", "team": "Pre-Approvals IP Offshore"},
            {"label": "Policy Rejection Rate", "value": "3.0%", "target": "0.0%", "period": "2026-09", "team": "Pre-Approvals IP Offshore"},
        ],
    }

    # 1. Provider-backed plain-language explanation succeeds and preserves exact facts
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    install_scripted_provider(
        monkeypatch,
        json.dumps(
            {
                "headline": "The 4.0 percentage points rise means rejections increased directly from 8.0% in August to 12.0% in September.",
                "bullets": ["That put September 7.0 pp above the 5.0% target ceiling."],
            }
        ),
    )
    hl, bullets, details, _, outcome, meta = build_explain_previous_payload(
        last_turn_summary=summary,
        scope=scope,
        session_state=ss,
        prompt="What does 4 percentage points mean here?",
    )
    assert outcome == "answer"
    assert meta["provider_calls"] == 1
    assert "In my previous answer" not in hl
    assert "8.0%" in hl and "12.0%" in hl
    assert any("June 2026" in b for b in bullets)
    assert any("Original summary:" in d for d in details)

    # 2. Ungrounded invented cause / number from provider is rejected and falls back honestly
    install_scripted_provider(
        monkeypatch,
        json.dumps(
            {
                "headline": "Rejections spiked to 45.0% because of a staffing shortage.",
                "bullets": ["Add 10 more staff next week."],
            }
        ),
    )
    hl_rej, bullets_rej, _, _, outcome_rej, meta_rej = build_explain_previous_payload(
        last_turn_summary=summary,
        scope=scope,
        session_state=ss,
        prompt="What does 4 percentage points mean here?",
    )
    assert outcome_rej == "answer"
    assert meta_rej["fallback_outcome"] == "validation_rejected"
    assert "staffing shortage" not in hl_rej.casefold()
    assert "45.0%" not in hl_rej
    assert any("unavailable" in b.casefold() for b in bullets_rej)
    assert "percentage point" in hl_rej.casefold()

    # 3. Provider timeout falls back honestly without parroting
    install_scripted_provider(monkeypatch, failed_response("timeout"))
    hl_fail, bullets_fail, _, _, outcome_fail, meta_fail = build_explain_previous_payload(
        last_turn_summary=summary,
        scope=scope,
        session_state=ss,
        prompt="Explain that more simply.",
    )
    assert outcome_fail == "answer"
    assert meta_fail["fallback_outcome"] == "timeout"
    assert not hl_fail.startswith("In my previous answer")
    assert "12.0%" in hl_fail
    assert any("timeout" in b.casefold() for b in bullets_fail)

    # 4. Ambiguous reference asks one short clarification
    hl_amb, _, _, _, outcome_amb, meta_amb = build_explain_previous_payload(
        last_turn_summary=summary,
        scope=scope,
        session_state=ss,
        prompt="Which number do you mean?",
    )
    assert outcome_amb == "clarification"
    assert meta_amb["provider_calls"] == 0
    assert "Controllable Rejection Rate" in hl_amb


def test_bounded_last_turn_retrieval_long_excluded_sequence_and_security() -> None:
    from sqlalchemy import event
    from models.models import AiConversation, AiTurn
    from services.ai.conversation_service import AiConversationService

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    gm_scope = {"role": "General Manager", "user_id": "00000000-0000-0000-0000-000000000801", "has_unrestricted_team_access": True}

    turn_sql_statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _track_sql(conn, cursor, statement, parameters, context, executemany):
        if "ai_turns" in statement.casefold():
            turn_sql_statements.append(statement)

    with Session() as db:
        svc = AiConversationService(db, gm_scope)

        # 1. Empty conversation returns None in 1 bounded query
        c_empty = svc.create_conversation(scope=gm_scope, origin="workspace")
        turn_sql_statements.clear()
        assert svc.get_last_completed_turn_summary(c_empty.conversation_id, scope=gm_scope) is None
        assert len(turn_sql_statements) == 1
        assert "limit" in turn_sql_statements[0].casefold()
        assert "user_prompt" not in turn_sql_statements[0].casefold()

        # 2. Long 80-turn conversation with 25 trailing greetings/off-topic/explain turns after turn 54 analytical answer
        c_long = svc.create_conversation(scope=gm_scope, origin="workspace")
        owner_id, _ = svc._resolve_owner(gm_scope)
        for idx in range(80):
            if idx <= 54:
                cap = "performance_query"
                hl = f"Inbound scored {80.0 + (idx % 10):.1f}% in September 2026 (turn {idx})."
                team_val = "Inbound"
            else:
                cap = ("greeting", "off_topic", "explain_previous")[idx % 3]
                hl = f"Excluded turn {idx}"
                team_val = None
            db.add(
                AiTurn(
                    conversation_id=c_long.conversation_id,
                    turn_index=idx,
                    client_request_id=f"req-{idx}",
                    status="completed",
                    user_prompt=f"prompt {idx}",
                    user_prompt_redacted=f"prompt {idx}",
                    validated_plan={"scope": {"team": team_val, "function": "Call Center" if team_val else None}},
                    evidence_summary={},
                    response_payload={
                        "headline": hl,
                        "narrative_bullets": ["Verified metric."],
                        "capability_mode": cap,
                        "structured_query": {"team": team_val, "function": "Call Center" if team_val else None},
                    },
                    outcome="answer",
                    route_used="local_rules",
                )
            )
        db.commit()

        turn_sql_statements.clear()
        t0 = time.perf_counter()
        summary = svc.get_last_completed_turn_summary(c_long.conversation_id, scope=gm_scope, batch_size=15, max_batches=4)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert summary is not None and summary["restricted"] is False
        assert summary["turn_index"] == 54
        assert len(turn_sql_statements) == 2  # turns 79..65 then 64..50 (stops at 54)
        assert all("limit" in s.casefold() and "order by" in s.casefold() and "desc" in s.casefold() for s in turn_sql_statements)
        assert elapsed_ms < 250.0

        # 3. Latest analytical turn unauthorized -> NEVER silently fall back to older authorized turn (idx 53 Outbound vs 54 Inbound)
        c_sec = svc.create_conversation(scope=gm_scope, origin="workspace")
        for idx, t_name in [(0, "Outbound"), (1, "Inbound"), (2, "Outbound")]:
            cap = "greeting" if idx == 2 else "performance_query"
            db.add(
                AiTurn(
                    conversation_id=c_sec.conversation_id,
                    turn_index=idx,
                    client_request_id=f"sec-{idx}",
                    status="completed",
                    user_prompt=f"sec {idx}",
                    user_prompt_redacted=f"sec {idx}",
                    validated_plan={"scope": {"team": t_name if idx < 2 else None, "function": "Call Center"}},
                    evidence_summary={},
                    response_payload={
                        "headline": f"{t_name} scored 90.0%.",
                        "capability_mode": cap,
                        "structured_query": {"team": t_name if idx < 2 else None, "function": "Call Center"},
                    },
                    outcome="answer",
                    route_used="local_rules",
                )
            )
        db.commit()

        # General Manager created it; test same owner after role scope narrowed to Outbound-only
        from repositories.ai_conversation_repository import AiConversationRepository
        conv_row = AiConversationRepository(db).get_owned_conversation(
            conversation_id=c_sec.conversation_id, owner_user_id=owner_id
        )
        assert conv_row is not None
        restricted_same_owner_scope = {
            "role": "Manager",
            "user_id": "00000000-0000-0000-0000-000000000801",
            "has_unrestricted_team_access": False,
            "accessible_functions": ["Call Center"],
            "accessible_teams": ["Outbound"],
        }
        # Reassign owner role wouldn't match _resolve_owner if user_id kept same
        conv_row.owner_user_id = AiConversationService(db)._resolve_owner(restricted_same_owner_scope)[0]
        db.commit()
        sec_summary = AiConversationService(db).get_last_completed_turn_summary(
            c_sec.conversation_id, scope=restricted_same_owner_scope
        )
        assert sec_summary == {"restricted": True}


def test_unseen_multiturn_evaluation_dev_split() -> None:
    from scripts.run_unseen_eval import evaluate_unseen_dataset

    report = evaluate_unseen_dataset(use_live_provider=False)
    assert report["summary"]["dev"]["total"] >= 20
    assert report["summary"]["heldout"]["total"] >= 10
    assert report["summary"]["dev"]["accuracy_pct"] == 100.0


def test_exposed_response_quality_v2_preserves_booking_scope_clarification() -> None:
    from scripts.run_unseen_eval import evaluate_unseen_dataset

    report = evaluate_unseen_dataset(
        use_live_provider=False,
        fixture_name="ai_response_quality_holdout_v2.json",
    )
    assert report["summary"]["dev"]["total"] == 16
    assert report["summary"]["heldout"]["total"] == 16
    assert report["summary"]["dev"]["accuracy_pct"] == 100.0
    failures = {row["turn_id"]: row for row in report["results"] if not row["passed"]}
    # The historical fixture expected an implicit booking source on these two turns.
    # Without a team selection there is no confirmed branch comparison to carry forward.
    assert set(failures) == {"v2_06_t1", "v2_06_t2"}
    assert failures["v2_06_t1"]["clarification"]["code"] == "AMBIGUOUS_TEAM_SCOPE"
    for row in failures.values():
        assert row["outcome"] == "clarification"
        assert row["tool_names"] == []
        assert row["typed_evidence"] == []


def test_confirmed_tied_employee_preserved_across_followups_and_cleared_on_scope_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _build_in_memory_db()
    recs = _make_rich_records()
    # Two employees share the exact same score (88.0%) in Inbound July-September so spotlight.ties is populated
    tied_peer = _make_call_center_record("EMP603", "Nourhan Tarek", "Inbound", 88.0, 30, 50, 80, 100, month="September")
    tied_peer.position = "Senior Inbound Agent"
    recs.append(tied_peer)
    _patch_records(monkeypatch, recs)
    ai_evidence_cache.clear()
    orch = PmsAiOrchestrator(db, {"role": "General Manager", "user_id": "u-gm-tie", "has_unrestricted_team_access": True})

    # Turn 1: Ambiguous "Mariam" in Inbound clarifies both Mariams
    r1 = orch.run_chat_turn(AiChatRequest(prompt="What is Mariam's score in Inbound for September 2026?"))
    assert r1.outcome == "clarification"
    assert r1.clarification is not None

    # Turn 2: Explicitly select Mariam Ali via clarification choice
    r2 = orch.run_chat_turn(
        AiChatRequest(
            prompt="What is Mariam's score in Inbound for September 2026?",
            clarification_choice_id="choice-person-EMP601",
            session_state=r1.resolved_session_state,
        )
    )
    assert r2.outcome == "answer"
    assert r2.resolved_session_state.last_confirmed_query is not None
    assert r2.resolved_session_state.last_confirmed_query.last_subject_employee_id == "EMP601"

    # Turn 3: Pronoun follow-up "What is her score?" must NOT lose EMP601 despite shared 88.0% score
    r3 = orch.run_chat_turn(
        AiChatRequest(prompt="What is her score?", session_state=r2.resolved_session_state)
    )
    assert r3.outcome == "answer"
    assert "Mariam Ali" in r3.headline
    assert "88.0%" in r3.headline
    assert r3.resolved_session_state.last_confirmed_query is not None
    assert r3.resolved_session_state.last_confirmed_query.last_subject_employee_id == "EMP601"

    # Turn 4: Pronoun follow-up "What is her job title?" stays on Mariam Ali
    r4 = orch.run_chat_turn(
        AiChatRequest(prompt="What is her job title?", session_state=r3.resolved_session_state)
    )
    assert r4.outcome == "answer"
    assert "Mariam Ali" in r4.headline
    assert "Call Center Agent" in r4.headline
    assert r4.resolved_session_state.last_confirmed_query is not None
    assert r4.resolved_session_state.last_confirmed_query.last_subject_employee_id == "EMP601"

    # Turn 5: Trend follow-up stays on Mariam Ali across her 3 months
    r5 = orch.run_chat_turn(
        AiChatRequest(prompt="Summarize her score pattern across the available months.", session_state=r4.resolved_session_state)
    )
    assert r5.outcome == "answer"
    assert r5.structured_query is not None
    assert r5.structured_query.intent == "trend"
    assert "Mariam Ali" in r5.headline
    assert "July 2026" in r5.headline and "September 2026" in r5.headline

    # Turn 6: Topic/scope switch clears the confirmed employee cleanly
    r6 = orch.run_chat_turn(
        AiChatRequest(prompt="Now show Pre-Approvals IP Offshore rejection trends", session_state=r5.resolved_session_state)
    )
    assert r6.outcome == "answer"
    assert r6.resolved_session_state.employee_id is None
    assert r6.resolved_session_state.last_confirmed_query is not None
    assert r6.resolved_session_state.last_confirmed_query.last_subject_employee_id is None
    assert "Mariam Ali" not in r6.headline


def test_person_followup_respects_operation_and_metric_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _build_in_memory_db()
    recs = _make_rich_records()
    # Add varying August/September bookings & overall scores for Omar Khalid and 1-month-only agent for insufficient history
    for r in recs:
        if getattr(r, "employee_id", None) == "EMP201" and r.month == "August":
            r.evaluation.score = 84.0
            r.geo.bookings.dubai = 90
            r.geo.bookings.sharjah = 50
            r.geo.bookings.ajman = 40
    solo = _make_call_center_record("EMP909", "Youssef Adel", "Inbound", 91.5, 40, 50, 120, 150, month="September")
    solo.position = "Inbound Specialist"
    recs.append(solo)
    _patch_records(monkeypatch, recs)
    ai_evidence_cache.clear()
    orch = PmsAiOrchestrator(db, {"role": "General Manager", "user_id": "u-gm-op", "has_unrestricted_team_access": True})

    # Bookings leader -> score pattern must give multi-month overall score (not bookings)
    t1 = orch.run_chat_turn(AiChatRequest(prompt="Who generated the most bookings in Outbound in September 2026?"))
    assert t1.outcome == "answer" and "Omar Khalid" in t1.headline
    t2 = orch.run_chat_turn(
        AiChatRequest(
            prompt="Summarize this person's score pattern across the available months.",
            session_state=t1.resolved_session_state,
        )
    )
    assert t2.outcome == "answer"
    assert t2.structured_query is not None
    assert t2.structured_query.intent == "trend"
    assert t2.structured_query.metric is None
    assert "84.0%" in t2.headline and "89.0%" in t2.headline
    assert "bookings" not in t2.headline.casefold()

    # Bookings leader -> "What was their booking trend?" gives booking history
    t3 = orch.run_chat_turn(
        AiChatRequest(
            prompt="What was their booking trend?",
            session_state=t1.resolved_session_state,
        )
    )
    assert t3.outcome == "answer"
    assert t3.structured_query is not None
    assert t3.structured_query.intent == "trend"
    assert t3.structured_query.metric == "outbound:bookings_count"
    assert "August 2026" in t3.headline and "September 2026" in t3.headline
    assert "190 bookings" in t3.headline and "270 bookings" in t3.headline

    # Single-month employee asking for score pattern must disclose insufficient history
    t_solo = orch.run_chat_turn(
        AiChatRequest(prompt="Summarize Youssef Adel's score pattern across the available months.")
    )
    assert t_solo.outcome == "answer"
    assert "insufficient" in t_solo.headline.casefold()
    assert "only 1" in t_solo.headline.casefold()
    assert "September 2026" in t_solo.headline

    # Ambiguous multi-metric context + "What was their trend?" clarifies instead of guessing one metric
    t_multi = orch.run_chat_turn(
        AiChatRequest(prompt="Check Omar Khalid's bookings and attendance rate in Outbound for September 2026.")
    )
    assert t_multi.outcome == "answer"
    t_ambig = orch.run_chat_turn(
        AiChatRequest(prompt="What was their trend?", session_state=t_multi.resolved_session_state)
    )
    assert t_ambig.outcome == "clarification"
    assert t_ambig.clarification is not None
    assert t_ambig.clarification.code == "AMBIGUOUS_KPI_SCOPE"


def _install_phase5_model_led_responses(
    monkeypatch: pytest.MonkeyPatch,
    planner_call: dict[str, object],
    synthesis_reply: object,
) -> list[dict[str, object]]:
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    return install_scripted_provider(monkeypatch, [planner_call, synthesis_reply])


def _phase5_planner_call(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {
        "response_type": "tool_call",
        "tool_name": tool_name,
        "tool_arguments": arguments,
    }


def _phase5_nadia_pharmacy_record() -> SimpleNamespace:
    return SimpleNamespace(
        id="Pharmacy_EMP701_2026_Sep",
        employee_id="EMP701",
        employee_name="Nadia Fadel",
        team="Pharmacy",
        month="September",
        year=2026,
        region="UAE",
        position="Pharmacist",
        performance_level="Employee",
        status="Below Target",
        evaluation=SimpleNamespace(score=88.0, grade="B"),
        kpi_values=[
            {
                "kpi_key": "waitingtime",
                "label": "Waiting Time",
                "actual_value": 6.2,
                "target_value": 5.0,
                "unit": "min",
                "direction": "lower_better",
            }
        ],
    )


def test_named_kpi_answer_uses_kpi_actual_in_rules_only_mode(monkeypatch):
    db = _build_in_memory_db()
    _patch_records(monkeypatch, [_phase5_nadia_pharmacy_record()])
    ai_evidence_cache.clear()
    response = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "named-kpi"}).run_chat_turn(
        AiChatRequest(prompt="What was Nadia Fadel's Waiting Time in September 2026?")
    )
    assert response.outcome == "answer"
    assert "Waiting Time" in response.headline
    assert "6.2" in response.headline


def test_namespaced_overall_score_and_hyphenated_surname(monkeypatch):
    from scripts.run_unseen_eval import _build_eval_records

    db = _build_in_memory_db()
    _patch_records(monkeypatch, _build_eval_records())
    ai_evidence_cache.clear()
    _install_phase5_model_led_responses(
        monkeypatch,
        _phase5_planner_call(
            "read_employee_metric", {"metric_name": "sales:overall_score", "period": "2026-09"},
        ),
        {"headline": "Nour El-Sayed's overall score was 89.0% in September 2026.", "narrative_bullets": []},
    )
    response = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "named-score"}).run_chat_turn(
        AiChatRequest(prompt="What was Nour El-Sayed's overall score in Sales in September 2026?")
    )
    assert response.outcome == "answer", response.headline
    assert any(e.employee_id == "EMP904" and e.actual == 89.0 for e in response.typed_evidence)


def test_explicit_team_trend_does_not_inherit_employee_subject(monkeypatch):
    from scripts.run_unseen_eval import _build_eval_records

    db = _build_in_memory_db()
    _patch_records(monkeypatch, _build_eval_records())
    ai_evidence_cache.clear()
    _install_phase5_model_led_responses(
        monkeypatch,
        _phase5_planner_call(
            "get_employee_history",
            {"team": "Outbound", "metric_id": "outbound:bookings_count", "employee_id": "EMP201"},
        ),
        failed_response("timeout"),
    )
    confirmed = ConfirmedQueryContext(
        intent="current_value", team="Outbound", function="Call Center", periods=["2026-09"],
        last_subject_employee_id="EMP201", last_subject_employee_name="Omar Khalid",
    )
    response = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "team-trend"}).run_chat_turn(
        AiChatRequest(
            prompt="How did Outbound bookings change between August and September 2026?",
            session_state=SessionFilterContext(
                team="Outbound", employee_id="EMP201", last_confirmed_query=confirmed,
            ),
        )
    )
    assert response.outcome == "answer", response.headline
    assert response.tool_calls[0].tool_name == "get_score_trend"
    bookings = [
        e for e in response.typed_evidence
        if e.metric_id.endswith(":bookings_count") and not e.employee_id
    ]
    assert {e.period for e in bookings if e.actual == 370} == {"August 2026", "September 2026"}
    assert "unchanged" in response.headline
    assert "worsening" not in response.headline


def test_explicit_ksa_request_preserves_non_ksa_team_name_and_period(monkeypatch):
    from scripts.run_unseen_eval import _build_eval_records

    db = _build_in_memory_db()
    _patch_records(monkeypatch, _build_eval_records())
    ai_evidence_cache.clear()
    response = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "coding-ksa"}).run_chat_turn(
        AiChatRequest(prompt="What was the Quality Errors rate for Coding in Saudi Arabia in September 2026?")
    )
    assert response.outcome == "unavailable_data", response.headline
    assert response.structured_query is not None
    assert response.structured_query.periods == ["2026-09"]
    assert response.resolved_session_state.region == "KSA"
    assert response.typed_evidence == []


def test_country_filtered_booking_count_keeps_region_after_planner_timeout(monkeypatch):
    from scripts.run_unseen_eval import _build_eval_records

    db = _build_in_memory_db()
    _patch_records(monkeypatch, _build_eval_records())
    ai_evidence_cache.clear()
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(monkeypatch, failed_response("timeout"))
    response = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "booking-ksa"}).run_chat_turn(
        AiChatRequest(prompt="How many Inbound bookings were recorded in Saudi Arabia in September 2026?")
    )
    assert response.outcome == "unavailable_data", response.headline
    assert response.resolved_session_state.region == "KSA"
    assert response.typed_evidence == []
    assert "665" not in response.headline


def test_team_metric_read_does_not_execute_unrequested_branch_comparison(monkeypatch):
    from scripts.run_unseen_eval import _build_eval_records

    db = _build_in_memory_db()
    _patch_records(monkeypatch, _build_eval_records())
    ai_evidence_cache.clear()
    _install_phase5_model_led_responses(
        monkeypatch,
        _phase5_planner_call("compare_branches", {
            "metric": "quality_errors", "branch": "UAE", "branches": ["ajman", "clinics"], "period": "2026-09",
        }),
        failed_response("timeout"),
    )
    response = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "uae-coding"}).run_chat_turn(
        AiChatRequest(prompt="What is the Quality Errors rate for Coding in the UAE in September 2026?")
    )
    assert response.outcome == "answer", response.headline
    assert all(call.tool_name != "compare_branches" for call in response.tool_calls)
    assert all(e.branch not in ("ajman", "clinics") for e in response.typed_evidence)
    assert any(e.team == "Coding" and e.actual == 2.5 for e in response.typed_evidence)


@pytest.mark.parametrize(("team", "prompt", "expected"), [
    ("Inbound", "What was the total number of bookings for the Inbound team in August and September 2026, and which employee had the highest bookings count in September 2026?", (635, 665)),
    ("Outbound", "How did Outbound bookings change between August and September 2026?", (370, 370)),
])
def test_planner_timeout_retains_explicit_team_booking_periods(monkeypatch, team, prompt, expected):
    from scripts.run_unseen_eval import _build_eval_records

    db = _build_in_memory_db()
    _patch_records(monkeypatch, _build_eval_records())
    ai_evidence_cache.clear()
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    provider = install_scripted_provider(monkeypatch, failed_response("timeout"))
    response = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "bookings-timeout"}).run_chat_turn(
        AiChatRequest(prompt=prompt)
    )
    assert any(r["purpose"] == "model_led_router" for r in provider)
    assert response.outcome == "answer", response.headline
    assert {
        e.period: e.actual for e in response.typed_evidence
        if not e.employee_id and e.actual is not None and "booking" in e.kpi_key.casefold()
        and e.unit in {"bookings", "count"}
    } == {"August 2026": expected[0], "September 2026": expected[1]}
    assert all(str(n) in " ".join([response.headline, *response.narrative_bullets]) for n in expected)
    if team == "Inbound":
        assert any(e.employee_id == "EMP101" and e.actual == 205 for e in response.typed_evidence)
    else:
        assert "unchanged" in response.headline


def test_employee_metric_survives_planner_timeout_without_team_filter(monkeypatch):
    from scripts.run_unseen_eval import _build_eval_records

    db = _build_in_memory_db()
    _patch_records(monkeypatch, _build_eval_records())
    ai_evidence_cache.clear()
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(monkeypatch, failed_response("timeout"))
    response = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "employee-metric"}).run_chat_turn(
        AiChatRequest(prompt="What was Nadia Fadel's Waiting Time in September 2026?")
    )
    assert response.outcome == "answer"
    assert response.structured_query.metric.casefold() == "pharmacy:waitingtime"
    assert any(e.employee_id == "EMP701" and e.kpi_key == "WaitingTime" for e in response.typed_evidence)


def test_published_employee_correction_discards_prior_position(monkeypatch):
    from scripts.run_unseen_eval import _build_eval_records

    db = _build_in_memory_db()
    records = _build_eval_records()
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    prior = next(r for r in records if r.employee_id == "EMP601" and r.month == "September")
    _install_phase5_model_led_responses(
        monkeypatch,
        _phase5_planner_call("read_employee_metric", {"employee_id": "EMP102", "metric": "inbound:overall_score", "period": "2026-09"}),
        failed_response("timeout"),
    )
    state = SessionFilterContext(
        team="Inbound", function="Call Center", position=prior.position, employee_id="EMP601",
        month="September", year=2026,
        last_confirmed_query=ConfirmedQueryContext(
            team="Inbound", function="Call Center", position=prior.position, periods=["2026-09"],
            last_subject_employee_id="EMP601", last_subject_employee_name="Mariam Ali",
            metric_id="inbound:overall_score",
        ),
    )
    response = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "employee-switch"}).run_chat_turn(
        AiChatRequest(prompt="Not Mariam Ali — show me Adham Tarek instead.", session_state=state)
    )
    assert response.outcome == "answer", response.headline
    assert any(e.employee_id == "EMP102" and e.actual == 91 for e in response.typed_evidence)
    assert not any(e.employee_id == "EMP601" for e in response.typed_evidence)


def test_coding_country_switch_retains_team_kpi_across_timeout_and_followup(monkeypatch):
    from scripts.run_unseen_eval import _build_eval_records

    db = _build_in_memory_db()
    _patch_records(monkeypatch, _build_eval_records())
    ai_evidence_cache.clear()
    orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "coding-replay"})
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(monkeypatch, [
        _phase5_planner_call("compare_branches", {"metric": "quality_errors", "branch": "UAE", "period": "2026-09"}),
        failed_response("timeout"),
        failed_response("timeout"),
        _phase5_planner_call("read_employee_metric", {"team": "Coding EGY", "metric": "coding:quality_errors", "branch": "UAE", "period": "2026-09"}),
        failed_response("timeout"),
    ])
    state = SessionFilterContext()
    for prompt, team, value in (
        ("What is the Quality Errors rate for Coding in the UAE in September 2026?", "Coding", 2.5),
        ("Switch to Egypt instead.", "Coding EGY", 1.8),
        ("And the rate?", "Coding EGY", 1.8),
    ):
        response = orch.run_chat_turn(AiChatRequest(prompt=prompt, session_state=state))
        assert response.outcome == "answer", (prompt, response.headline)
        assert any(e.team == team and e.actual == value for e in response.typed_evidence), (
            prompt, response.headline,
            (response.structured_query.intent, response.structured_query.metric),
            [(call.tool_name, call.arguments) for call in response.tool_calls],
            [(e.team, e.kpi_key, e.actual) for e in response.typed_evidence],
        )
        assert all(e.team == team for e in response.typed_evidence)
        state = response.resolved_session_state
        assert not state.employee_id and not state.branch


@pytest.mark.parametrize(("scope", "prompt", "outcome"), [
    ({"role": "Admin"}, "What was Adham Tarek's overall score in January 2020?", "unavailable_data"),
    (
        {"role": "Employee", "is_self_only": True, "employee_id": "EMP601"},
        "What was Adham Tarek's overall score in September 2026?",
        "restricted_access",
    ),
    (
        {"role": "Regional Manager", "accessible_regions": ["EGY"], "accessible_teams": ["Coding", "Coding EGY"]},
        "What was the Quality Errors rate for Coding in the UAE in September 2026?",
        "restricted_access",
    ),
])
def test_corrected_reads_preserve_absence_and_access_denial(monkeypatch, scope, prompt, outcome):
    from scripts.run_unseen_eval import _build_eval_records

    db = _build_in_memory_db()
    _patch_records(monkeypatch, _build_eval_records())
    ai_evidence_cache.clear()
    _install_phase5_model_led_responses(
        monkeypatch,
        _phase5_planner_call("read_employee_metric", {"employee_id": "EMP102", "metric": "overall_score", "period": "2020-01"}),
        failed_response("timeout"),
    )
    response = PmsAiOrchestrator(db, {**scope, "user_id": "boundary"}).run_chat_turn(AiChatRequest(prompt=prompt))
    assert response.outcome == outcome, response.headline
    assert response.typed_evidence == []
    if outcome == "restricted_access":
        assert response.tool_calls == []


@pytest.mark.parametrize("branch,actual", [("dubai", 350), ("sharjah", 180)])
def test_phase5_p503_single_branch_booking_query_uses_branch_aggregate(
    monkeypatch: pytest.MonkeyPatch,
    branch: str,
    actual: int,
) -> None:
    _patch_records(monkeypatch, _make_rich_records())
    ai_evidence_cache.clear()
    branch_label = branch.capitalize()
    _install_phase5_model_led_responses(
        monkeypatch,
        _phase5_planner_call(
            "get_employee_history",
            {
                "team": "Inbound",
                "metric_id": "bookings_count",
                "period": "2026-09",
                "location": branch_label,
            },
        ),
        {
            "headline": f"{branch_label} had {actual} Inbound bookings in September 2026.",
            "narrative_bullets": [],
        },
    )

    response = PmsAiOrchestrator(
        _build_in_memory_db(),
        {"role": "Admin", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(prompt=f"How many Inbound bookings came from {branch_label} in September 2026?")
    )

    assert response.outcome == "answer"
    assert response.tool_calls[0].tool_name == "compare_branches"
    assert response.tool_calls[0].arguments["branches"] == [branch]
    assert branch_label in response.headline and str(actual) in response.headline
    assert any(
        evidence.kpi_key == "bookings_count"
        and evidence.branch == branch
        and evidence.period == "September 2026"
        and evidence.actual == actual
        and evidence.unit == "count"
        and not evidence.employee_id
        and evidence.source_link
        for evidence in response.typed_evidence
    )


def test_phase5_p503_two_branch_booking_comparison_uses_both_branch_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_records(monkeypatch, _make_rich_records())
    ai_evidence_cache.clear()
    _install_phase5_model_led_responses(
        monkeypatch,
        _phase5_planner_call(
            "get_score_trend",
            {
                "team": "Inbound",
                "metric_id": "bookings_count",
                "period": "2026-09",
                "branch": "Dubai",
            },
        ),
        {
            "headline": "Dubai had more Inbound bookings (350) than Sharjah (180) in September 2026.",
            "narrative_bullets": [],
        },
    )

    response = PmsAiOrchestrator(
        _build_in_memory_db(),
        {"role": "Admin", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(prompt="Which had more Inbound bookings in September 2026, Dubai or Sharjah?")
    )

    assert response.outcome == "answer"
    assert response.structured_query.intent == "compare_branches"
    assert response.validated_plan_v2 is not None
    assert response.validated_plan_v2.operations[0].kind == "compare_branches"
    assert response.tool_calls[0].tool_name == "compare_branches"
    assert response.tool_calls[0].arguments["branches"] == ["dubai", "sharjah"]
    branch_counts = {
        evidence.branch: evidence.actual
        for evidence in response.typed_evidence
        if evidence.kpi_key == "bookings_count" and evidence.branch in {"dubai", "sharjah"}
    }
    assert branch_counts == {"dubai": 350, "sharjah": 180}
    assert "Dubai" in response.headline and "Sharjah" in response.headline
    assert "350" in response.headline and "180" in response.headline


def test_phase5_p507_employee_waiting_time_diagnosis_keeps_target_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_records(monkeypatch, [_phase5_nadia_pharmacy_record()])
    ai_evidence_cache.clear()
    _install_phase5_model_led_responses(
        monkeypatch,
        _phase5_planner_call(
            "get_employee_history",
            {
                "employee_name": "Nadia Fadel",
                "team": "Pharmacy",
                "metric_id": "waitingtime",
                "period": "2026-09",
            },
        ),
        {
            "headline": "Nadia Fadel's Waiting Time was 6.2 min against the 5 minute target, exceeding it by 1.2 min.",
            "narrative_bullets": [],
        },
    )

    response = PmsAiOrchestrator(
        _build_in_memory_db(),
        {"role": "Admin", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(prompt="Why did Nadia Fadel's Waiting Time miss the 5 minute target in September 2026?")
    )

    assert response.outcome == "answer", (
        response.headline,
        [(call.tool_name, call.arguments) for call in response.tool_calls],
        response.validated_plan_v2.model_dump() if response.validated_plan_v2 else None,
        [evidence.model_dump() for evidence in response.typed_evidence],
    )
    assert response.structured_query.intent == "score_drivers"
    assert response.structured_query.operation_kind_v2 == "score_drivers"
    assert response.validated_plan_v2 is not None
    assert response.validated_plan_v2.operations[0].kind == "score_drivers"
    assert response.tool_calls[0].tool_name == "get_kpi_diagnosis"
    assert response.tool_calls[0].arguments["employee_id"] == "EMP701"
    assert "6.2" in response.headline and "5" in response.headline and "min" in response.headline
    assert "call volume" not in response.headline.casefold()
    assert any(
        evidence.employee_id == "EMP701"
        and evidence.employee_name == "Nadia Fadel"
        and evidence.metric_id.endswith(":waitingtime")
        and evidence.period == "September 2026"
        and evidence.actual == 6.2
        and evidence.target == 5.0
        and evidence.unit == "min"
        and evidence.source_link
        for evidence in response.typed_evidence
    )


def test_phase5_p508_t1_rejection_metric_wins_over_overall_score_synthesis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = _make_rich_records()
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    _install_phase5_model_led_responses(
        monkeypatch,
        _phase5_planner_call(
            "read_employee_metric",
            {
                "employee_name": "Heba Nabil",
                "team": "Pre-Approvals IP Offshore",
                "metric_id": "controllable_rejection_rate",
                "period": "2026-09",
            },
        ),
        {
            "headline": "Heba Nabil's overall score was 86.0% in September 2026.",
            "narrative_bullets": [],
        },
    )
    response = PmsAiOrchestrator(
        _build_in_memory_db(),
        {"role": "Admin", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(prompt="What was Heba Nabil's controllable rejection rate in September 2026?")
    )

    assert response.outcome == "answer"
    assert response.validated_plan_v2 is not None
    assert response.validated_plan_v2.operations[0].kind == "person_summary"
    assert [call.tool_name for call in response.tool_calls] == ["read_employee_metric"]
    assert response.tool_calls[0].arguments["metric_id"] == "pre_approvals_ip_offshore:rejection_rate"
    assert "12.0 %" in response.headline
    assert "86.0%" not in response.headline
    assert any(
        ev.kpi_key == "RejectionRate"
        and ev.period == "September 2026"
        and ev.actual == 12.0
        and ev.actual_display == "12.0%"
        and ev.employee_id == "EMP401"
        for ev in response.typed_evidence
    )


def test_phase5_p508_t3_rejection_trend_uses_rejection_evidence_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_records(monkeypatch, _make_rich_records())
    ai_evidence_cache.clear()
    _install_phase5_model_led_responses(
        monkeypatch,
        _phase5_planner_call(
            "get_employee_history",
            {
                "employee_name": "Heba Nabil",
                "team": "Pre-Approvals IP Offshore",
                "metric_id": "pre-approvals ip offshore:controllable_rejection_rate",
                "periods": ["2026-08", "2026-09"],
            },
        ),
        {
            "headline": "Heba Nabil's overall score changed from 90.0% in August 2026 to 86.0% in September 2026.",
            "narrative_bullets": [],
        },
    )
    response = PmsAiOrchestrator(
        _build_in_memory_db(),
        {"role": "Admin", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(
            prompt="How did Heba Nabil's controllable rejection rate change from August to September 2026?"
        )
    )

    assert response.outcome == "answer"
    assert response.validated_plan_v2 is not None
    assert response.validated_plan_v2.operations[0].kind == "trend"
    assert [call.tool_name for call in response.tool_calls] == ["get_employee_history"]
    assert response.tool_calls[0].arguments["metric_id"] == "pre_approvals_ip_offshore:rejection_rate"
    assert "August 2026" in response.headline and "September 2026" in response.headline
    assert "8.0 %" in response.headline and "12.0 %" in response.headline
    assert "90.0%" not in response.headline and "86.0%" not in response.headline
    rejection_periods = {
        ev.period: ev.actual_display
        for ev in response.typed_evidence
        if ev.kpi_key == "RejectionRate" and ev.employee_id == "EMP401"
    }
    assert rejection_periods["August 2026"] == "8.0%"
    assert rejection_periods["September 2026"] == "12.0%"
    assert {
        ev.period: ev.actual
        for ev in response.typed_evidence
        if ev.kpi_key == "RejectionRate" and ev.employee_id == "EMP401"
    } == {"August 2026": 8.0, "September 2026": 12.0}


def test_phase5_p508_t1_timeout_fallback_keeps_requested_rejection_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_records(monkeypatch, _make_rich_records())
    ai_evidence_cache.clear()
    _install_phase5_model_led_responses(
        monkeypatch,
        _phase5_planner_call(
            "read_employee_metric",
            {
                "employee_name": "Heba Nabil",
                "team": "Pre-Approvals IP Offshore",
                "metric_id": "controllable_rejection_rate",
                "period": "2026-09",
            },
        ),
        failed_response("timeout"),
    )
    response = PmsAiOrchestrator(
        _build_in_memory_db(),
        {"role": "Admin", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(prompt="What was Heba Nabil's controllable rejection rate in September 2026?")
    )

    assert response.outcome == "answer"
    assert response.provider_usage.fallback_outcome == "timeout"
    assert "12.0 %" in response.headline
    assert "86.0%" not in response.headline


def test_phase5_p502_ranking_plan_cannot_be_downgraded_to_employee_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = _make_rich_records()
    for record in records:
        if getattr(record, "employee_id", None) == "EMP201":
            record.geo.bookings.dubai = 300
            record.geo.bookings.sharjah = 40
            record.geo.bookings.ajman = 20
            record.geo.bookings.clinics = 10
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    _install_phase5_model_led_responses(
        monkeypatch,
        _phase5_planner_call(
            "get_employee_history",
            {
                "team": "Outbound",
                "metric_id": "bookings_count",
                "period": "2026-09",
            },
        ),
        {
            "headline": "Omar Khalid's overall score was 89.0% in September 2026.",
            "narrative_bullets": [],
        },
    )
    response = PmsAiOrchestrator(
        _build_in_memory_db(),
        {"role": "Admin", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(prompt="Who had the most bookings in Outbound in September 2026?")
    )

    assert response.outcome == "answer"
    assert response.validated_plan_v2 is not None
    assert response.validated_plan_v2.operations[0].kind == "ranking"
    assert [call.tool_name for call in response.tool_calls] == ["rank_employees"]
    assert response.tool_calls[0].arguments["metric_id"] == "outbound:bookings_count"
    assert response.tool_calls[0].arguments["period"] == "2026-09"
    assert "Omar Khalid" in response.headline and "370" in response.headline
    assert "89.0%" not in response.headline
    assert any(
        ev.kpi_key == "bookings_count"
        and ev.period == "September 2026"
        and ev.actual == 370
        and ev.employee_id == "EMP201"
        for ev in response.typed_evidence
    )


def test_phase5_evaluator_matches_ratio_fixture_to_display_scale_evidence() -> None:
    from scripts.run_unseen_eval import validate_critical_evidence

    evidence = TypedMetricEvidence(
        metric_id="pre_approvals_ip_offshore:rejection_rate",
        kpi_key="RejectionRate",
        display_name="Rejection Rate",
        team="Pre-Approvals IP Offshore",
        period="September 2026",
        actual=12.0,
        target=5.0,
        actual_display="12.0%",
        target_display="5.0%",
        unit="%",
        employee_id="EMP401",
        employee_name="Heba Nabil",
        source_link="/employee/EMP401?month=September&year=2026",
    )
    turn = {
        "expected_evidence": [
            {
                "kpi_key": "RejectionRate",
                "period": "2026-09",
                "actual": 0.12,
                "unit": "%",
                "employee_id": "EMP401",
                "source_required": True,
            }
        ]
    }

    assert evidence.actual == 12.0
    assert validate_critical_evidence(turn, SimpleNamespace(typed_evidence=[evidence])) == []


def test_structured_evidence_source_link_keeps_team_and_period_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    from urllib.parse import parse_qs, urlsplit

    monkeypatch.setenv("PMS_AI_INTENT_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "true")
    _patch_records(monkeypatch, _make_rich_records())
    ai_evidence_cache.clear()
    with _build_in_memory_db() as db:
        response = PmsAiOrchestrator(
            db,
            {"role": "General Manager", "user_id": "u-source-link", "has_unrestricted_team_access": True},
        ).run_chat_turn(
            AiChatRequest(
                prompt="What was the Inbound overall score in September 2026?",
            )
        )

    assert response.outcome == "answer"
    assert response.structured_query is not None
    assert response.structured_query.team == "Inbound"
    assert response.structured_query.periods == ["2026-09"]
    assert response.primary_source_link is not None
    parsed_link = urlsplit(response.primary_source_link.route)
    query = parse_qs(parsed_link.query)
    assert parsed_link.path.startswith("/team/")
    assert query.get("team") == ["Inbound"]
    assert query.get("month") == ["September"]
    assert query.get("year") == ["2026"]


def test_evaluator_rejects_wrong_single_month_booking_answer_on_trend_turn() -> None:
    from models.ai_schemas import AiChatResponsePayload, StructuredQueryPlan
    from scripts.run_unseen_eval import validate_turn_response

    holdout_path = "tests/fixtures/ai_response_quality_holdout_v2.json"
    data = json.loads(open(holdout_path, encoding="utf-8").read())
    score_pattern_turn = next(
        t for c in data["conversations"] for t in c["turns"] if t["id"] == "v2_03_t3"
    )
    wrong_resp = AiChatResponsePayload(
        trace_id="neg-eval-01",
        scope_banner="Outbound · September 2026",
        outcome="answer",
        headline="Omar Khalid recorded 370 bookings in September 2026.",
        narrative_bullets=[],
        detail_bullets=[],
        structured_query=StructuredQueryPlan(
            intent="current_value",
            metric="outbound:bookings_count",
            employee_id="EMP201",
            employee_name="Omar Khalid",
            team="Outbound",
            function="Call Center",
            periods=["2026-09"],
        ),
        resolved_session_state=SessionFilterContext(team="Outbound", function="Call Center"),
    )
    failures = validate_turn_response(score_pattern_turn, wrong_resp)
    assert failures, "Evaluator must fail a single-month booking response on a score-pattern trend turn"
    assert any("intent" in f for f in failures)
    assert any("metric" in f for f in failures)
    assert any("trend periods" in f for f in failures)


