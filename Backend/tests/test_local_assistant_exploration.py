from __future__ import annotations

import io
import json
import os
from typing import Any

import pytest

from models.ai_schemas import AiChatRequest, SessionFilterContext
from services.ai.catalog import ai_evidence_cache
from services.ai.local_data_explorer import (
    build_authorized_concept_summary,
    build_exploration_step_json_schema,
    local_exploration_enabled,
    run_bounded_exploration,
)
from services.ai.orchestrator import PmsAiOrchestrator
from test_ai_workspace import (
    _build_in_memory_db,
    _make_call_center_record,
    _patch_records,
)


def _mock_llama_steps(monkeypatch: pytest.MonkeyPatch, step_payloads: list[dict[str, Any] | str]) -> list[dict[str, Any]]:
    """Patch urllib.request.build_opener in local_data_explorer to return scripted step responses."""
    captured_requests: list[dict[str, Any]] = []
    idx = {"val": 0}

    class _MockOpener:
        def open(self, request: Any, timeout: float = 8.0) -> io.BytesIO:
            req_body = json.loads(request.data.decode("utf-8"))
            captured_requests.append(req_body)
            step_idx = min(idx["val"], len(step_payloads) - 1)
            idx["val"] += 1
            payload_item = step_payloads[step_idx]
            content_str = payload_item if isinstance(payload_item, str) else json.dumps(payload_item)
            envelope = {"choices": [{"message": {"content": content_str}}]}
            return io.BytesIO(json.dumps(envelope).encode("utf-8"))

    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_: _MockOpener())
    return captured_requests


def test_exploration_disabled_by_default_and_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", raising=False)
    assert not local_exploration_enabled()

    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    assert local_exploration_enabled()

    monkeypatch.setenv("APP_ENV", "production")
    assert not local_exploration_enabled()


def test_remote_or_non_loopback_endpoint_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_URL", "http://example.com/v1/chat/completions")
    records = [_make_call_center_record("EMP001", "Alice Example", "Inbound", 84.0, 20, 40, 50, 80)]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()

    with _build_in_memory_db() as db:
        res = run_bounded_exploration(
            db=db,
            scope={"role": "Admin", "has_unrestricted_team_access": True},
            prompt="What is Inbound score in September 2026?",
            session_state=SessionFilterContext(function="Call Center", month="September", year=2026),
            published_periods={"2026-09"},
            employee_candidates=[],
        )
    assert not res.handled
    assert res.fallback_reason == "invalid_endpoint"


def test_authorized_concept_summary_never_leaks_unauthorized_scopes() -> None:
    inbound_dubai_scope = {
        "role": "Branch Director",
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Inbound"],
        "accessible_functions": ["Call Center"],
        "accessible_branches": ["dubai"],
        "accessible_team_levels": [("Inbound", "Employee")],
    }
    summary = build_authorized_concept_summary(
        scope=inbound_dubai_scope,
        session_state=SessionFilterContext(function="Call Center", team="Inbound", branch="dubai", month="September", year=2026),
        published_periods={"2026-08", "2026-09"},
    )
    assert summary["authorized_teams"] == ["Inbound"]
    assert "Outbound" not in summary["authorized_teams"]
    assert "Coding" not in summary["authorized_teams"]
    assert summary["authorized_branches"] == ["dubai"]
    assert "sharjah" not in summary["authorized_branches"]
    assert summary["authorized_levels"] == ["Employee"]
    assert all(m["team"] == "Inbound" and m["level"] == "Employee" for m in summary["authorized_metrics"])

    self_only_scope = {
        "role": "Employee",
        "is_self_only": True,
        "employee_id": "EMP001",
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Inbound"],
        "accessible_functions": ["Call Center"],
    }
    self_summary = build_authorized_concept_summary(
        scope=self_only_scope,
        session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
        published_periods={"2026-09"},
    )
    assert self_summary["is_self_only"] is True
    assert self_summary["self_employee_id"] == "EMP001"
    assert "rank_employees" not in self_summary["allowed_tools"]
    assert "compare_branches" not in self_summary["allowed_tools"]


def test_cross_scope_isolation_blocks_unauthorized_team_branch_level_and_peer_employee_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    records = [
        _make_call_center_record("EMP001", "Alice Example", "Inbound", 82.0, 15, 30, 45, 70),
        _make_call_center_record("EMP002", "Bob Example", "Outbound", 91.0, 20, 35, 55, 80),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()

    # 1. Model attempts to request Outbound tool while user is scoped only to Inbound
    _mock_llama_steps(
        monkeypatch,
        [
            {
                "action": "call_tools",
                "unknown_code": "none",
                "tools": [{"tool": "get_team_score_summary", "team": "Outbound", "period": "2026-09"}],
            }
        ],
    )
    inbound_only_scope = {
        "role": "Manager",
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Inbound"],
        "accessible_functions": ["Call Center"],
        "accessible_team_levels": [("Inbound", "Employee")],
    }
    with _build_in_memory_db() as db:
        resp_team = PmsAiOrchestrator(db, inbound_only_scope).run_chat_turn(
            AiChatRequest(
                prompt="How is overall team performance in September 2026?",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            )
        )
    assert resp_team.outcome == "restricted_access"
    assert "Outbound" in resp_team.headline
    assert resp_team.tool_calls == []
    assert resp_team.evidence_envelope_v2 == []

    # 2. Model attempts to request Sharjah branch while user is scoped only to Dubai
    _mock_llama_steps(
        monkeypatch,
        [
            {
                "action": "call_tools",
                "unknown_code": "none",
                "tools": [{"tool": "get_kpi_diagnosis", "team": "Inbound", "branch": "sharjah", "period": "2026-09"}],
            }
        ],
    )
    dubai_only_scope = {
        "role": "Branch Director",
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Inbound"],
        "accessible_functions": ["Call Center"],
        "accessible_branches": ["dubai"],
        "accessible_team_levels": [("Inbound", "Employee")],
    }
    with _build_in_memory_db() as db:
        resp_branch = PmsAiOrchestrator(db, dubai_only_scope).run_chat_turn(
            AiChatRequest(
                prompt="Check Inbound KPI gaps in September 2026",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", branch="dubai", month="September", year=2026),
            )
        )
    assert resp_branch.outcome == "restricted_access"
    assert "Sharjah" in resp_branch.headline
    assert resp_branch.tool_calls == []

    # 3. Model attempts to request Managerial level while user only has Employee level grant
    _mock_llama_steps(
        monkeypatch,
        [
            {
                "action": "call_tools",
                "unknown_code": "none",
                "tools": [
                    {
                        "tool": "get_kpi_diagnosis",
                        "team": "Inbound",
                        "performance_level": "Managerial",
                        "period": "2026-09",
                    }
                ],
            }
        ],
    )
    with _build_in_memory_db() as db:
        resp_level = PmsAiOrchestrator(db, inbound_only_scope).run_chat_turn(
            AiChatRequest(
                prompt="Check Inbound KPI performance in September 2026",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            )
        )
    assert resp_level.outcome == "restricted_access"
    assert "Managerial" in resp_level.headline
    assert resp_level.tool_calls == []

    # 4. Self-only employee attempts peer ranking or another employee's summary
    _mock_llama_steps(
        monkeypatch,
        [
            {
                "action": "call_tools",
                "unknown_code": "none",
                "tools": [{"tool": "get_employee_summary", "team": "Inbound", "employee_query": "EMP002", "period": "2026-09"}],
            }
        ],
    )
    self_only_scope = {
        "role": "Employee",
        "is_self_only": True,
        "employee_id": "EMP001",
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Inbound"],
        "accessible_functions": ["Call Center"],
    }
    with _build_in_memory_db() as db:
        resp_self = PmsAiOrchestrator(db, self_only_scope).run_chat_turn(
            AiChatRequest(
                prompt="How did my score perform in September 2026?",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", employee_id="EMP001", month="September", year=2026),
            )
        )
    assert resp_self.outcome == "restricted_access"
    assert "own employee scorecard" in resp_self.headline
    assert resp_self.tool_calls == []


def test_malformed_requests_and_sql_injection_fall_back_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    records = [
        _make_call_center_record("EMP001", "Alice Example", "Inbound", 80.0, 10, 30, 40, 120),
        _make_call_center_record("EMP002", "Bob Example", "Inbound", 90.0, 20, 40, 30, 60),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}

    malformed_cases = [
        "not valid json at all {{{",
        {"action": "call_tools", "unknown_code": "none", "tools": [{"tool": "execute_raw_sql", "team": "Inbound"}]},
        {
            "action": "call_tools",
            "unknown_code": "none",
            "tools": [{"tool": "get_kpi_diagnosis", "team": "Inbound'; DROP TABLE employees; --"}],
        },
        {
            "action": "call_tools",
            "unknown_code": "none",
            "tools": [{"tool": "get_kpi_diagnosis", "team": "Inbound", "employee_query": "1 OR 1=1 UNION SELECT * FROM users"}],
        },
        {
            "action": "call_tools",
            "unknown_code": "none",
            "tools": [{"tool": "rank_employees", "team": "Inbound", "limit": 999}],
        },
        {
            "action": "finish",
            "unknown_code": "none",
            "tools": [],
        },
    ]

    for bad_payload in malformed_cases:
        _mock_llama_steps(monkeypatch, [bad_payload])
        with _build_in_memory_db() as db:
            resp = PmsAiOrchestrator(db, admin_scope).run_chat_turn(
                AiChatRequest(
                    prompt="What is Inbound score in September 2026?",
                    session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
                )
            )
        # Falls back cleanly to deterministic PMS routing and still answers accurately from PMS records
        assert resp.outcome == "answer"
        assert "85.0%" in resp.headline
        assert resp.provider_usage.fallback_outcome != "none"


def test_clear_unknowns_disclose_missing_schema_concepts_without_guessing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    records = [_make_call_center_record("EMP001", "Alice Example", "Inbound", 85.0, 15, 30, 40, 80)]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}

    # 1. Compensation / Salary unknown
    _mock_llama_steps(
        monkeypatch,
        [{"action": "unknown", "unknown_code": "unsupported_compensation_data", "tools": []}],
    )
    with _build_in_memory_db() as db:
        resp_sal = PmsAiOrchestrator(db, admin_scope).run_chat_turn(
            AiChatRequest(
                prompt="What is the monthly salary and bonus of Inbound agents in September 2026?",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            )
        )
    assert resp_sal.outcome == "unsupported_request"
    assert "salary" in resp_sal.headline.casefold()
    assert resp_sal.tool_calls == []

    # 2. HR Join Date unknown
    _mock_llama_steps(
        monkeypatch,
        [{"action": "unknown", "unknown_code": "missing_hr_join_date", "tools": []}],
    )
    with _build_in_memory_db() as db:
        resp_join = PmsAiOrchestrator(db, admin_scope).run_chat_turn(
            AiChatRequest(
                prompt="What is the exact HR hire date for Inbound agents?",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            )
        )
    assert resp_join.outcome == "clarification"
    assert resp_join.clarification is not None
    assert resp_join.clarification.code == "MISSING_HR_JOIN_DATE"
    assert resp_join.tool_calls == []

    # 3. Unpublished future period requested by model tool call
    _mock_llama_steps(
        monkeypatch,
        [
            {
                "action": "call_tools",
                "unknown_code": "none",
                "tools": [{"tool": "get_team_score_summary", "team": "Inbound", "period": "2026-12"}],
            }
        ],
    )
    with _build_in_memory_db() as db:
        resp_unpub = PmsAiOrchestrator(db, admin_scope).run_chat_turn(
            AiChatRequest(
                prompt="What is Inbound score in December 2026?",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            )
        )
    assert resp_unpub.outcome == "unavailable_data"
    assert "2026-12" in resp_unpub.headline
    assert resp_unpub.tool_calls == []


def test_multi_part_iterative_exploration_combines_two_step_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_LLM_MODEL", "qwen2.5-3b-instruct")
    records = [
        _make_call_center_record("EMP001", "Alice Example", "Inbound", 76.0, 10, 30, 30, 80, month="September"),
        _make_call_center_record("EMP002", "Bob Example", "Inbound", 94.0, 25, 30, 70, 80, month="September"),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}

    # Step 1 requests KPI diagnosis; Step 2 inspects Step 1 evidence and requests worst employee ranking
    captured = _mock_llama_steps(
        monkeypatch,
        [
            {
                "action": "call_tools",
                "unknown_code": "none",
                "tools": [{"tool": "get_kpi_diagnosis", "team": "Inbound", "period": "2026-09"}],
            },
            {
                "action": "call_tools",
                "unknown_code": "none",
                "tools": [{"tool": "rank_employees", "team": "Inbound", "direction": "worst", "period": "2026-09", "limit": 1}],
            },
        ],
    )

    with _build_in_memory_db() as db:
        resp = PmsAiOrchestrator(db, admin_scope).run_chat_turn(
            AiChatRequest(
                prompt="What is the primary KPI bottleneck in Inbound for September 2026 and who is the lowest-scoring agent?",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            )
        )

    assert len(captured) in (2, 3)
    step2_user_payload = json.loads(captured[1]["messages"][1]["content"])
    assert len(step2_user_payload["collected_evidence"]) == 1
    assert step2_user_payload["collected_evidence"][0]["tool"] == "get_kpi_diagnosis"

    assert resp.outcome == "answer"
    assert resp.provider_used == "llama_cpp"
    assert resp.model_used == "qwen2.5-3b-instruct"
    assert captured[0]["model"] == "qwen2.5-3b-instruct"
    assert resp.provider_usage.provider_calls in (2, 3)
    assert len(resp.tool_calls) == 2
    assert [tc.tool_name for tc in resp.tool_calls] == [
        "get_kpi_diagnosis_and_trends",
        "get_agent_spotlight_and_trend",
    ]
    assert len(resp.evidence_envelope_v2) == 2
    combined_text = f"{resp.headline} {' '.join(resp.narrative_bullets)}"
    assert "Abandon Rate" in combined_text or "Attendance Rate" in combined_text
    assert "Alice Example" in combined_text
    assert "EMP001" in combined_text


@pytest.mark.skipif(os.environ.get("PMS_AI_RUN_LIVE_MODEL_TESTS") != "true", reason="requires local Qwen server on 127.0.0.1:18080")
def test_live_qwen_model_explores_authorized_concepts_and_multi_part_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_TIMEOUT_SECONDS", "15.0")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")

    records = [
        _make_call_center_record("EMP001", "Alice Example", "Inbound", 76.0, 10, 30, 30, 80, month="August"),
        _make_call_center_record("EMP001", "Alice Example", "Inbound", 78.0, 10, 30, 30, 80, month="September"),
        _make_call_center_record("EMP002", "Bob Example", "Inbound", 94.0, 25, 30, 70, 80, month="September"),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}

    with _build_in_memory_db() as db:
        # 1. Live single/multi-step KPI & lowest performer exploration
        res_kpi = PmsAiOrchestrator(db, admin_scope).run_chat_turn(
            AiChatRequest(
                prompt="Diagnose Inbound KPI gaps in September 2026 and show who is the lowest-scoring agent.",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            )
        )
        assert res_kpi.outcome == "answer"
        assert res_kpi.provider_used == "llama_cpp"
        assert res_kpi.tool_calls
        assert res_kpi.evidence_envelope_v2

        # 2. Live clear unknown detection for unrecorded compensation/salary concept
        res_unknown = PmsAiOrchestrator(db, admin_scope).run_chat_turn(
            AiChatRequest(
                prompt="What is the monthly salary and payroll bonus for Inbound agents in September 2026?",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            )
        )
        assert res_unknown.outcome in ("unsupported_request", "unavailable_data", "clarification")
        assert res_unknown.tool_calls == []
