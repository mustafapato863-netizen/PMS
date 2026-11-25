"""Unit tests for the local searchable PMS Product Guide (validation, fuzzy retrieval, RBAC, and latency)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from models.ai_schemas import SessionFilterContext
from services.ai.product_guide import (
    GUIDE_CONTENT_DIR,
    ProductGuideValidationError,
    get_guide_section_by_id,
    get_product_guide,
    load_product_guide_from_dir,
    search_product_guide,
)


def test_bundled_guide_loads_and_validates_all_sections():
    guide = get_product_guide()
    assert guide.guide_version == "1.0.0"
    ids = set(guide.sections_by_id)
    assert {
        "corrective-actions-navigation",
        "corrective-actions-followup",
        "corrective-actions-filters",
        "pms-overview",
        "team-dashboard-navigation",
        "monthly-evaluation-workflow",
    }.issubset(ids)
    # UI label parity check against CorrectiveActionsView.tsx and ActionFollowUpBoard.tsx
    ca_nav = guide.sections_by_id["corrective-actions-navigation"]
    assert "All actions" in ca_nav.body
    assert "Follow-up" in ca_nav.body
    ca_fu = guide.sections_by_id["corrective-actions-followup"]
    assert "Overdue" in ca_fu.body
    assert "Follow-up" in ca_fu.body
    # Monthly evaluation workflow check against docs/guides/monthly-evaluation-admin.md
    me = guide.sections_by_id["monthly-evaluation-workflow"]
    for stage in ("Save", "Preview", "Approve", "Apply"):
        assert stage in me.body


@pytest.mark.parametrize(
    ("query", "expected_section_id", "expected_route_prefix"),
    [
        ("Where can I see corrective actions?", "corrective-actions-navigation", "/corrective-actions"),
        ("where to follow up on overdue corrective actions", "corrective-actions-followup", "/corrective-actions"),
        ("overdu correctiv actons follow up", "corrective-actions-followup", "/corrective-actions"),
        ("الاجراءات التصحيحية المتأخرة", "corrective-actions-followup", "/corrective-actions"),
        ("tell me breef for system", "pms-overview", "/monthly-presentation"),
        ("how can i check specfic team", "team-dashboard-navigation", "/monthly-presentation"),
        ("how do I approve and apply monthly evaluation settings?", "monthly-evaluation-workflow", "/settings?tab=evaluation"),
        ("what c grade mean", "pms-grade-scale", "/monthly-presentation"),
        ("what does grade C mean", "pms-grade-scale", "/monthly-presentation"),
        ("what is gap share", "pms-gap-vs-gap-share", "/monthly-presentation"),
        ("what does critical <70% mean", "pms-teams-at-risk", "/monthly-presentation"),
        ("what is balanced scorecard", "pms-performance-levels", "/executive"),
        ("what roles exist in pms", "pms-roles-and-access", "/monthly-presentation"),
        ("what does aht mean", "pms-kpi-glossary", "/insights"),
        ("معنى تقدير C", "pms-grade-scale", "/monthly-presentation"),
    ],
)
def test_guide_fuzzy_paraphrase_typo_and_arabic_retrieval(query: str, expected_section_id: str, expected_route_prefix: str):
    admin_scope = {"role": "Admin", "user_id": "guide-admin", "has_unrestricted_team_access": True}
    matches = search_product_guide(query, scope=admin_scope, session_state=SessionFilterContext(), max_results=3)
    assert matches, f"No guide matches for {query!r}"
    top_ids = [m.section.id for m in matches]
    assert expected_section_id in top_ids, f"Expected {expected_section_id} in {top_ids} for {query!r}"
    matched = next(m for m in matches if m.section.id == expected_section_id)
    assert matched.navigation_target is not None
    assert matched.navigation_target.route.startswith(expected_route_prefix)


def test_guide_resolves_team_specific_link_when_authorized_and_blocks_unauthorized_team():
    outbound_manager_scope = {
        "role": "Manager",
        "user_id": "mgr-out",
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Outbound"],
        "accessible_functions": ["Call Center"],
    }
    # Authorized team -> direct /team/outbound link
    ok_matches = search_product_guide(
        "how can i check specfic team",
        scope=outbound_manager_scope,
        session_state=SessionFilterContext(team="Outbound", function="Call Center"),
    )
    team_match = next(m for m in ok_matches if m.section.id == "team-dashboard-navigation")
    assert team_match.navigation_target is not None
    assert team_match.navigation_target.route.startswith("/team/outbound")

    # Unauthorized team -> never emits /team/finance link!
    unauth_matches = search_product_guide(
        "how can i check specfic team",
        scope=outbound_manager_scope,
        session_state=SessionFilterContext(team="Finance", function="Finance"),
    )
    team_match_unauth = next(m for m in unauth_matches if m.section.id == "team-dashboard-navigation")
    assert team_match_unauth.navigation_target is None or "/team/finance" not in team_match_unauth.navigation_target.route


def test_guide_enforces_role_access_for_admin_only_and_self_only_users():
    manager_scope = {"role": "Manager", "user_id": "mgr-1", "has_unrestricted_team_access": False, "accessible_teams": ["Inbound"]}
    employee_scope = {"role": "Employee", "user_id": "emp-1", "employee_id": "EMP101", "is_self_only": True}

    # Manager cannot retrieve Admin-only monthly-evaluation-workflow
    assert get_guide_section_by_id("monthly-evaluation-workflow", scope=manager_scope, session_state=SessionFilterContext()) is None
    mgr_matches = search_product_guide("save preview approve apply monthly evaluation", scope=manager_scope, session_state=SessionFilterContext())
    assert all(m.section.id != "monthly-evaluation-workflow" for m in mgr_matches)

    # Self-only Employee cannot retrieve corrective-actions or team-dashboard admin/manager sections, only overview
    assert get_guide_section_by_id("corrective-actions-navigation", scope=employee_scope, session_state=SessionFilterContext()) is None
    emp_ca = search_product_guide("Where can I see corrective actions?", scope=employee_scope, session_state=SessionFilterContext())
    assert all(m.section.page_id != "corrective_actions" for m in emp_ca)

    emp_overview = search_product_guide("tell me breef for system", scope=employee_scope, session_state=SessionFilterContext())
    assert any(m.section.id == "pms-overview" for m in emp_overview)
    assert emp_overview[0].navigation_target is not None
    assert emp_overview[0].navigation_target.route == "/employee/EMP101"


def test_guide_validation_rejects_missing_heading_and_unpermitted_page_id(tmp_path: Path):
    # Missing heading in markdown
    (tmp_path / "doc.md").write_text("# Doc\n\n## Actual Heading\n\nSome content.\n", encoding="utf-8")
    (tmp_path / "index.json").write_text(
        json.dumps({
            "guide_version": "1.0.0",
            "sections": [{
                "id": "bad-heading",
                "title": "Missing",
                "file": "doc.md",
                "heading": "Nonexistent Heading",
                "page_id": "corrective_actions",
                "audiences": ["Admin"],
            }],
        }),
        encoding="utf-8",
    )
    with pytest.raises(ProductGuideValidationError, match="not found or empty"):
        load_product_guide_from_dir(tmp_path)

    # Unpermitted page_id
    (tmp_path / "index.json").write_text(
        json.dumps({
            "guide_version": "1.0.0",
            "sections": [{
                "id": "bad-page",
                "title": "Actual",
                "file": "doc.md",
                "heading": "Actual Heading",
                "page_id": "secret_admin_backdoor",
                "audiences": ["Admin"],
            }],
        }),
        encoding="utf-8",
    )
    with pytest.raises(ProductGuideValidationError, match="unpermitted page_id"):
        load_product_guide_from_dir(tmp_path)


def test_guide_warm_local_retrieval_meets_p95_under_50ms():
    scope = {"role": "Admin", "user_id": "bench-admin", "has_unrestricted_team_access": True}
    ss = SessionFilterContext()
    # Warm cache once
    get_product_guide()
    queries = [
        "Where can I see corrective actions?",
        "where to follow up on overdue actions",
        "tell me breef for system",
        "how can i check specfic team",
        "save preview approve apply monthly evaluation",
        "الاجراءات التصحيحية المتأخرة",
    ]
    latencies_ms: list[float] = []
    for _ in range(10):
        for q in queries:
            t0 = time.perf_counter()
            res = search_product_guide(q, scope=scope, session_state=ss)
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)
            assert res
    latencies_ms.sort()
    p95 = latencies_ms[int(len(latencies_ms) * 0.95) - 1]
    assert p95 <= 50.0, f"Warm guide retrieval p95={p95:.2f}ms exceeded 50ms budget"
    assert GUIDE_CONTENT_DIR.is_dir()


@pytest.mark.parametrize(
    ("prompt", "expected_snippets"),
    [
        ("what c grade mean", ("Grade C", "Average", "80.0%")),
        ("what does grade C mean", ("Grade C", "Average", "80.0%")),
        ("what does grade E mean?", ("Grade E", "Unsatisfactory", "70.0%")),
        ("what is gap share?", ("Gap Share", "headcount")),
        ("what does Critical <70% mean?", ("Critical <70%", "Grade E")),
        ("what is balanced scorecard?", ("Balanced Scorecard", "Managerial", "Corporate")),
        ("what roles exist in PMS?", ("Admin", "Manager", "Employee")),
        ("what does AHT mean?", ("AHT", "lower better")),
    ],
)
def test_orchestrator_answers_general_pms_guide_questions_with_zero_db_reads(
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
    expected_snippets: tuple[str, ...],
):
    from services.ai.orchestrator import PmsAiOrchestrator
    from services.dashboard_record_service import DashboardRecordService
    from services.database_record_source import DatabaseRecordSource
    from models.ai_schemas import AiChatRequest
    from test_ai_workspace import _build_in_memory_db

    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_GUIDED_READS_ENABLED", "false")

    db_calls: list[str] = []
    monkeypatch.setattr(DatabaseRecordSource, "get_all", lambda *a, **kw: db_calls.append("get_all") or [])
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda *a, **kw: db_calls.append("list") or [])

    db = _build_in_memory_db()
    try:
        res = PmsAiOrchestrator(
            db,
            {"role": "Admin", "user_id": "guide-user", "has_unrestricted_team_access": True},
        ).run_chat_turn(AiChatRequest(prompt=prompt, session_state=SessionFilterContext()))
        assert res.outcome == "answer", f"Expected answer for {prompt!r}, got {res.outcome}: {res.headline}"
        assert res.capability_mode == "page_help"
        combined = f"{res.headline} {' '.join(res.narrative_bullets)}"
        for snippet in expected_snippets:
            assert snippet.casefold() in combined.casefold(), f"Expected {snippet!r} in {combined!r}"
        assert db_calls == []
    finally:
        db.close()
