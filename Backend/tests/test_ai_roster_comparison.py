"""Regression coverage for missing employees and teams across PMS periods."""

import pytest

from ai_provider_fakes import failed_response, install_scripted_provider, tool_response

from models.ai_schemas import AiChatMessage, AiChatRequest, SessionFilterContext
from models.models import AiTurn, Employee, PerformanceRecord, Team
from services.ai.conversation_service import AiConversationService
from services.ai.orchestrator import PmsAiOrchestrator
from test_ai_workspace import _build_in_memory_db

SCREENSHOT_PROMPT = "so who is missing teams in UAE in oct were in sep"


@pytest.fixture
def roster_db(monkeypatch):
    monkeypatch.setenv("PMS_AI_GUIDED_READS_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")

    with _build_in_memory_db() as db:
        pharmacy = Team(name="Pharmacy", db_name="Pharmacy", display_name="Pharmacy", region="UAE")
        finance = Team(name="Finance", db_name="Finance", display_name="Finance", region="UAE")
        egypt = Team(name="Outbound", db_name="Outbound", display_name="Outbound", region="EGY")
        db.add_all([pharmacy, finance, egypt])
        db.flush()

        for code, name, region, entries in [
            ("1", "UAE Missing", "UAE", [(2026, "September", pharmacy)]),
            ("2", "UAE Moved", "UAE", [(2026, "September", finance), (2026, "October", pharmacy)]),
            ("3", "UAE New", "UAE", [(2026, "October", pharmacy)]),
            ("4", "Egypt Missing", "EGY", [(2026, "September", egypt)]),
            ("5", "Old UAE Record", "UAE", [(2025, "September", pharmacy), (2025, "October", finance)]),
        ]:
            employee = Employee(employee_id=code, name=name, region=region, team_id=entries[-1][2].id)
            db.add(employee)
            db.flush()
            for year, month, team in entries:
                db.add(PerformanceRecord(
                    employee_id=employee.id, team_id=team.id, year=year, month=month,
                    region=region, performance_level="Employee", score=0.0, grade="E", status="Needs Attention",
                ))
        db.commit()
        yield db


def test_screenshot_prompt_uses_uae_records_and_employee_ids(roster_db, monkeypatch):
    def unexpected_classifier(*args, **kwargs):
        pytest.fail("A recognized roster comparison should bypass the generic capability classifier")

    monkeypatch.setattr("services.ai.orchestrator.detect_contextual_capability", unexpected_classifier)
    response = PmsAiOrchestrator(roster_db, {"role": "Admin"}).run_chat_turn(AiChatRequest(
        prompt=SCREENSHOT_PROMPT,
        history=[
            AiChatMessage(role="user", content="how can u help me"),
            AiChatMessage(role="assistant", content="I can analyze verified PMS performance."),
        ],
        session_state=SessionFilterContext(region="EGY", team="Outbound", function="Call Center"),
    ))
    assert response.outcome == "answer"
    assert response.validated_plan_v2.scope.periods == ["2026-09", "2026-10"]
    assert response.scope_banner == "UAE · September 2026 → October 2026"
    assert response.headline == "1 employee with September 2026 evaluations has no October 2026 evaluation in UAE."
    assert [(item.title, item.subtitle) for item in response.visual_cards[0].items] == [("UAE Missing", "Pharmacy")]
    assert response.evidence_envelope_v2[0].missing_count == 1
    assert response.provider_usage.provider_calls == 0


@pytest.mark.parametrize(("prompt", "expected_periods", "expected_names"), [
    ("Which teams were in UAE in Sep but missing in October 2026?", ["2026-09", "2026-10"], ["Finance"]),
    ("Who is missing in Sep 2026 but was evaluated in October 2026 in UAE?", ["2026-10", "2026-09"], ["UAE New"]),
    ("Which employees in UAE had a 2025-10 evaluation but not 2026-10?", ["2025-10", "2026-10"], ["Old UAE Record"]),
])
def test_roster_comparison_variants(roster_db, prompt, expected_periods, expected_names):
    response = PmsAiOrchestrator(roster_db, {"role": "Admin"}).run_chat_turn(AiChatRequest(prompt=prompt))
    assert response.outcome == "answer"
    assert response.validated_plan_v2.scope.periods == expected_periods
    assert [item.title for item in response.visual_cards[0].items] == expected_names


def test_missing_period_and_zero_missing_have_distinct_replies(roster_db):
    orchestrator = PmsAiOrchestrator(roster_db, {"role": "Admin"})
    unavailable = orchestrator.run_chat_turn(AiChatRequest(prompt="Who is missing in November after Oct 2026 in UAE?"))
    assert unavailable.outcome == "unavailable_data"
    assert "November 2026" in unavailable.headline
    assert not unavailable.visual_cards

    result = orchestrator.run_chat_turn(AiChatRequest(prompt="Which employees were missing in October in UAE?"))
    assert result.outcome == "clarification"
    assert result.clarification.code == "MISSING_COMPARISON_PERIOD"
    assert "UAE" in result.clarification.question

    employee_comparison = orchestrator.run_chat_turn(AiChatRequest(prompt="Who was missing in October compared to September 2026 in UAE?"))
    assert employee_comparison.outcome == "answer"
    assert employee_comparison.evidence_envelope_v2[0].missing_count == 1

    all_teams = orchestrator.run_chat_turn(AiChatRequest(prompt="Which teams were missing in September compared to October 2026 in UAE?"))
    assert all_teams.outcome == "answer"
    assert all_teams.evidence_envelope_v2[0].missing_count == 0
    assert "also appears in September 2026" in all_teams.headline


def test_employee_and_disallowed_region_cannot_read_roster(roster_db):
    for scope in (
        {"role": "Employee", "employee_id": "1"},
        {"role": "Regional Manager", "accessible_regions": ["EGY"]},
    ):
        response = PmsAiOrchestrator(roster_db, scope).run_chat_turn(AiChatRequest(prompt=SCREENSHOT_PROMPT))
        assert response.outcome == "restricted_access"
        assert not response.tool_calls
        assert "UAE Missing" not in response.model_dump_json()


def test_team_manager_only_compares_assigned_team(roster_db):
    scope = {
        "role": "Manager",
        "accessible_teams": ["Pharmacy"],
        "accessible_team_levels": [("Pharmacy", "Employee")],
    }
    orchestrator = PmsAiOrchestrator(roster_db, scope)
    response = orchestrator.run_chat_turn(AiChatRequest(prompt=SCREENSHOT_PROMPT))
    assert response.outcome == "answer"
    assert response.evidence_envelope_v2[0].record_count == 3

    restricted = orchestrator.run_chat_turn(AiChatRequest(
        prompt="Who from Finance is missing in October compared to September 2026 in UAE?",
    ))
    assert restricted.outcome == "restricted_access"
    assert not restricted.tool_calls


def test_roster_conversation_saves_evidence_and_rechecks_scope(roster_db, monkeypatch):
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "true")
    scope = {"role": "Regional Manager", "user_id": "regional-roster-test", "accessible_regions": ["UAE"]}
    response = PmsAiOrchestrator(roster_db, scope).run_chat_turn(
        AiChatRequest(prompt=SCREENSHOT_PROMPT, client_request_id="roster-1")
    )
    assert response.outcome == "answer"
    assert response.context_version is not None
    turn = roster_db.query(AiTurn).filter_by(id=response.turn_id).one()
    assert turn.status == "completed"
    assert turn.evidence_summary["items"][0]["missing_count"] == 1

    service = AiConversationService(roster_db, scope)
    assert service._is_turn_evidence_authorized(turn, scope)
    assert not service._is_turn_evidence_authorized(turn, {**scope, "accessible_regions": ["EGY"]})


UNSEEN_ROSTER_PROMPT = "UAE roll-call churn Sep vs Oct"


def test_model_selects_existing_roster_tool_for_unseen_phrasing(roster_db, monkeypatch):
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    calls = install_scripted_provider(monkeypatch, tool_response(
        "compare_evaluation_rosters",
        entity="employee",
        baseline_period="2026-09",
        target_period="2026-10",
        region="EGY",
    ))
    response = PmsAiOrchestrator(roster_db, {"role": "Admin"}).run_chat_turn(
        AiChatRequest(prompt=UNSEEN_ROSTER_PROMPT)
    )
    assert response.outcome == "answer", response.headline
    assert [item.title for item in response.visual_cards[0].items] == ["UAE Missing"]
    assert response.validated_plan_v2.scope.periods == ["2026-09", "2026-10"]
    assert response.tool_calls[0].arguments["region"] == "UAE"
    assert response.provider_usage.route_used == "model_led_pilot"
    assert response.provider_usage.provider_calls == 1
    assert [call["purpose"] for call in calls] == ["model_led_router"]
    assert calls[0]["task_role"] == "investigation"



def test_model_reuses_verified_roster_periods_for_a_follow_up(roster_db, monkeypatch):
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    calls = install_scripted_provider(monkeypatch, tool_response(
        "compare_evaluation_rosters", entity="team", baseline_period="2026-09", target_period="2026-10",
    ))
    orchestrator = PmsAiOrchestrator(roster_db, {"role": "Admin"})
    first = orchestrator.run_chat_turn(AiChatRequest(prompt=SCREENSHOT_PROMPT))
    follow_up = orchestrator.run_chat_turn(AiChatRequest(
        prompt="Same comparison at team level?",
        session_state=first.resolved_session_state,
    ))
    assert follow_up.outcome == "answer", follow_up.headline
    assert follow_up.validated_plan_v2.scope.periods == ["2026-09", "2026-10"]
    assert [item.title for item in follow_up.visual_cards[0].items] == ["Finance"]
    assert "Prior roster comparison: baseline 2026-09, target 2026-10" in calls[0]["messages"][-1]["content"]


def test_model_proposed_roster_dates_cannot_replace_requested_periods(roster_db, monkeypatch):
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(monkeypatch, tool_response(
        "compare_evaluation_rosters", entity="employee", baseline_period="2026-08", target_period="2026-10",
    ))
    response = PmsAiOrchestrator(roster_db, {"role": "Admin"}).run_chat_turn(
        AiChatRequest(prompt=UNSEEN_ROSTER_PROMPT)
    )
    assert response.outcome == "answer"
    assert response.validated_plan_v2.scope.periods == ["2026-09", "2026-10"]
    assert [item.title for item in response.visual_cards[0].items] == ["UAE Missing"]


@pytest.mark.parametrize("planner_reply", [
    failed_response("timeout"),
    {"response_type": "conversational", "direct_response": "The answer was 99%."},
])
def test_unfamiliar_question_has_no_unverified_fallback(roster_db, monkeypatch, planner_reply):
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(monkeypatch, planner_reply)
    response = PmsAiOrchestrator(roster_db, {"role": "Admin"}).run_chat_turn(
        AiChatRequest(prompt=UNSEEN_ROSTER_PROMPT)
    )
    assert response.outcome == "unavailable_data", response.headline
    assert "99%" not in response.headline
    assert not response.tool_calls



@pytest.mark.parametrize(("prompt", "planner_reply", "outcome"), [
    (
        "UAE door badge swipes Sep vs Oct",
        {"response_type": "unsupported"},
        "unsupported_request",
    ),
    (
        UNSEEN_ROSTER_PROMPT,
        {"response_type": "clarification", "clarification_prompt": "Should I compare employees or teams?"},
        "clarification",
    ),
])
def test_model_distinguishes_an_unsupported_query_from_a_missing_choice(
    roster_db, monkeypatch, prompt, planner_reply, outcome,
):
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(monkeypatch, planner_reply)
    response = PmsAiOrchestrator(roster_db, {"role": "Admin"}).run_chat_turn(
        AiChatRequest(prompt=prompt)
    )
    assert response.outcome == outcome
    assert not response.tool_calls
    if outcome == "clarification":
        assert response.clarification.question == "Should I compare employees or teams?"


def test_model_led_gate_respects_pilot_role_and_provider_override(monkeypatch):
    from services.ai.contextual_assistant import detect_contextual_capability

    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    question = AiChatRequest(prompt=UNSEEN_ROSTER_PROMPT)
    admin_scope = {"role": "Admin"}
    assert detect_contextual_capability(question, scope=admin_scope)[1] == "model_led_pilot"
    assert detect_contextual_capability(question, scope={"role": "Manager"})[1] != "model_led_pilot"
    deterministic = question.model_copy(update={"provider_override": "deterministic"})
    assert detect_contextual_capability(deterministic, scope=admin_scope)[1] != "model_led_pilot"
