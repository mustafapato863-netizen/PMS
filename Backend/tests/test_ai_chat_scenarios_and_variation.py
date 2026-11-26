"""Regression tests for variation_seed, static scenario hygiene, executive variation synthesis, and contextual page help."""

from __future__ import annotations

import json
import pytest
from pydantic import ValidationError

from models.ai_schemas import (
    AiChatMessage,
    AiChatRequest,
    PageContextV1,
    SessionFilterContext,
    TypedMetricEvidence,
)
from repositories.ai_conversation_repository import compute_request_fingerprint
from services.ai.catalog import get_ai_catalog
from services.ai.contextual_assistant import (
    build_navigation_payload,
    build_page_help_payload,
    normalize_page_id,
)
from services.ai.domain_policies import (
    build_call_center_starter_prompts,
    extract_prompt_signals,
)
from services.ai.local_evidence_synthesis import synthesize_validated_executive_variation
from services.ai.provider_engine import ProviderResponse, TokenUsage
from services.ai.providers import DeterministicLocalProviderAdapter, resolve_variation_index


def test_chat_history_supports_fifty_turns_of_memory():
    history = [
        AiChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"message {i}")
        for i in range(80)
    ]
    req = AiChatRequest(prompt="In the same department, show the bottom 3", history=history)
    assert len(req.history) == 80

    with pytest.raises(ValidationError):
        AiChatRequest(
            prompt="too much history",
            history=[AiChatMessage(role="user", content="x") for _ in range(101)],
        )


def test_variation_seed_schema_and_fingerprint_preservation():
    req_default = AiChatRequest(prompt="Show Inbound score")
    assert req_default.variation_seed is None

    req_valid = AiChatRequest(prompt="Show Inbound score", variation_seed=5)
    assert req_valid.variation_seed == 5

    with pytest.raises(ValidationError):
        AiChatRequest(prompt="Show Inbound score", variation_seed=-1)

    with pytest.raises(ValidationError):
        AiChatRequest(prompt="Show Inbound score", variation_seed=51)

    session = SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026)
    fp_none = compute_request_fingerprint(
        prompt="Show Inbound score",
        clarification_choice_id=None,
        answer_detail="auto",
        session_state=session,
        variation_seed=None,
    )
    fp_zero = compute_request_fingerprint(
        prompt="Show Inbound score",
        clarification_choice_id=None,
        answer_detail="auto",
        session_state=session,
        variation_seed=0,
    )
    fp_seed1 = compute_request_fingerprint(
        prompt="Show Inbound score",
        clarification_choice_id=None,
        answer_detail="auto",
        session_state=session,
        variation_seed=1,
    )
    fp_seed2 = compute_request_fingerprint(
        prompt="Show Inbound score",
        clarification_choice_id=None,
        answer_detail="auto",
        session_state=session,
        variation_seed=2,
    )

    assert fp_none == fp_zero
    assert fp_seed1 != fp_none
    assert fp_seed2 != fp_none
    assert fp_seed1 != fp_seed2


def test_starter_prompts_scope_safety_and_team_tailoring():
    neutral = build_call_center_starter_prompts(SessionFilterContext())
    assert len(neutral) == 6
    assert neutral[0].label == "Review overall performance"
    pharmacy = build_call_center_starter_prompts(SessionFilterContext(function="Call Center", team="Pharmacy"))
    assert pharmacy[0].label == "Review Pharmacy performance"
    assert all("Call Center" not in prompt.prompt for prompt in pharmacy)
    assert {p.category for p in neutral} == {"team", "people", "branch", "kpi", "governance"}
    neutral_blob = " ".join(f"{p.label} {p.subtitle} {p.prompt}" for p in neutral)
    assert "call center" not in neutral_blob.lower()
    assert "uae" not in neutral_blob.lower()

    inbound = build_call_center_starter_prompts(SessionFilterContext(function="Call Center", team="Inbound"))
    assert len(inbound) == 6
    kpi_inbound = [p for p in inbound if p.category == "kpi"]
    assert len(kpi_inbound) == 1
    assert kpi_inbound[0].id == "inbound-kpi-decisions"
    assert kpi_inbound[0].label == "Inbound KPI Gaps & Queue Decisions"

    support = build_call_center_starter_prompts(
        SessionFilterContext(function="Call Center", team="Support Positions")
    )
    assert len(support) == 6
    kpi_support = [p for p in support if p.category == "kpi"]
    assert len(kpi_support) == 1
    assert kpi_support[0].id == "support-kpi-decisions"
    assert kpi_support[0].label == "Support Positions KPI Diagnosis"

    outbound = build_call_center_starter_prompts(SessionFilterContext(function="Call Center", team="Outbound"))
    assert len(outbound) == 6
    kpi_outbound = [p for p in outbound if p.category == "kpi"]
    assert len(kpi_outbound) == 1
    assert kpi_outbound[0].id == "outbound-paradox"
    assert "100%" not in kpi_outbound[0].subtitle
    assert "56.6%" not in kpi_outbound[0].subtitle


@pytest.mark.parametrize(
    ("team", "function", "region", "level"),
    [
        (row["team"], row["function"], region, level)
        for row in get_ai_catalog().get_full_coverage_scope_registry()
        for region in (("EGY", "UAE") if row["region"] == "All" else (row["region"],))
        for level in row["performance_levels"]
    ],
)
def test_starter_scenarios_stay_within_each_catalog_scope(team, function, region, level):
    prompts = build_call_center_starter_prompts(SessionFilterContext(
        team=team, function=function, region=region, performance_level=level,
    ))
    assert {prompt.category for prompt in prompts} == {"team", "people", "branch", "kpi", "governance"}
    if team.casefold() not in ("inbound", "outbound", "call center", "support positions"):
        assert prompts[0].prompt == f"Review {team} performance"
        assert not any("call center" in item.prompt.casefold() for item in prompts)


def test_deterministic_multi_variant_composer_and_dynamic_followups():
    assert resolve_variation_index("What is Inbound score?", None, None) == 0
    assert resolve_variation_index("What is Inbound score?", None, 0) == 0
    assert resolve_variation_index("What is Inbound score?", None, 1) == 1
    assert resolve_variation_index("What is Inbound score?", None, 2) == 2
    assert resolve_variation_index("What is Inbound score?", None, 3) == 0

    overlapping_history = [
        AiChatMessage(role="user", content="What is Inbound score in September 2026?"),
        AiChatMessage(role="assistant", content="Inbound scored 88.4% in September 2026."),
    ]
    assert resolve_variation_index("Show Inbound score again", overlapping_history, None) >= 1

    adapter = DeterministicLocalProviderAdapter()
    session = SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026)
    prompt = "What is Inbound score in September 2026?"
    signals = extract_prompt_signals(prompt, session)
    digests = [
        {
            "scope": "Inbound",
            "branch": "All Branches",
            "period": "September 2026",
            "average_score": 88.4,
            "score_change": 3.2,
            "total_records": 12,
            "employees_below_target": 2,
        }
    ]

    syn0 = adapter.synthesize(prompt=prompt, signals=signals, tool_digests=digests, guardrail_notes=[], variation_seed=0)
    syn1 = adapter.synthesize(prompt=prompt, signals=signals, tool_digests=digests, guardrail_notes=[], variation_seed=1)
    syn2 = adapter.synthesize(prompt=prompt, signals=signals, tool_digests=digests, guardrail_notes=[], variation_seed=2)

    assert len({syn0.headline, syn1.headline, syn2.headline}) == 3
    for syn in (syn0, syn1, syn2):
        sentences = [s for s in syn.headline.split(". ") if s.strip()]
        assert 1 <= len(sentences) <= 2

    # Non-Call-Center dynamic follow-ups must never propose Dubai vs Sharjah.
    non_cc_session = SessionFilterContext(function="Pharmacy", team="Pharmacy", month="September", year=2026)
    non_cc_prompt = "Show Pharmacy score in September 2026"
    non_cc_signals = extract_prompt_signals(non_cc_prompt, non_cc_session)
    non_cc_digests = [
        {
            "scope": "Pharmacy",
            "branch": "All Branches",
            "period": "September 2026",
            "average_score": 91.0,
            "score_change": 1.5,
            "total_records": 8,
            "employees_below_target": 1,
        }
    ]
    non_cc_syn = adapter.synthesize(
        prompt=non_cc_prompt,
        signals=non_cc_signals,
        tool_digests=non_cc_digests,
        guardrail_notes=[],
        history=[AiChatMessage(role="user", content="Compare branches in Pharmacy")],
        variation_seed=1,
    )
    assert all("dubai" not in f.lower() and "sharjah" not in f.lower() for f in non_cc_syn.suggested_followups)
    assert all("compare branches in pharmacy" not in f.lower() for f in non_cc_syn.suggested_followups)


def test_synthesize_validated_executive_variation_accepts_grounded_and_rejects_unverified(monkeypatch):
    evidence = [
        TypedMetricEvidence(
            metric_id="Inbound:overall_score",
            kpi_key="overall_score",
            display_name="Overall Score",
            team="Inbound",
            performance_level="Employee",
            branch="all",
            period="September 2026",
            actual=88.4,
            target=90.0,
            actual_display="88.4%",
            target_display="90.0%",
            achievement_percent=98.2,
            weight_percent=100.0,
            unit="%",
            direction="higher_better",
            source_link="/team/inbound",
        )
    ]
    digests = [{"team": "Inbound", "period": "September 2026", "overall_score": 88.4}]

    monkeypatch.setattr("services.ai.local_evidence_synthesis.local_synthesis_enabled", lambda: False)
    assert (
        synthesize_validated_executive_variation(
            question="How did Inbound perform?",
            digests=digests,
            typed_evidence=evidence,
            variant_idx=1,
        )
        is None
    )

    class _FakeEngine:
        def __init__(self, payload: dict):
            self.payload = payload

        def generate(self, _req):
            return ProviderResponse(
                content=json.dumps(self.payload),
                provider="cloudflare",
                model="@cf/test-model",
                outcome="success",
                latency_ms=42.0,
                usage=TokenUsage(prompt_tokens=120, completion_tokens=45, total_tokens=165),
            )

    monkeypatch.setattr("services.ai.local_evidence_synthesis.local_synthesis_enabled", lambda: True)
    monkeypatch.setattr(
        "services.ai.local_evidence_synthesis.get_unified_provider_engine",
        lambda: _FakeEngine(
            {
                "headline": "Overall Score for Inbound reached 88.4% against the 90.0% target in September 2026.",
                "narrative_bullets": ["Inbound Overall Score stood at 88.4% in September 2026 (target: 90.0%)."],
            }
        ),
    )
    ok_res = synthesize_validated_executive_variation(
        question="Summarize Inbound risk in September 2026",
        digests=digests,
        typed_evidence=evidence,
        variant_idx=1,
    )
    assert ok_res is not None
    assert ok_res.provider_used == "cloudflare"
    assert "88.4%" in ok_res.headline
    assert len(ok_res.narrative_bullets) == 1

    # Ungrounded invented metric value -> rejected cleanly (returns None)
    monkeypatch.setattr(
        "services.ai.local_evidence_synthesis.get_unified_provider_engine",
        lambda: _FakeEngine(
            {
                "headline": "Inbound jumped to 97.3% in September 2026.",
                "narrative_bullets": ["Score rose to 97.3%."],
            }
        ),
    )
    assert (
        synthesize_validated_executive_variation(
            question="Summarize Inbound",
            digests=digests,
            typed_evidence=evidence,
            variant_idx=1,
        )
        is None
    )

    # More than 2 sentences -> rejected cleanly (returns None)
    monkeypatch.setattr(
        "services.ai.local_evidence_synthesis.get_unified_provider_engine",
        lambda: _FakeEngine(
            {
                "headline": "Inbound Overall Score reached 88.4%. The target is 90.0%. Period is September 2026.",
                "narrative_bullets": ["Overall Score: 88.4%."],
            }
        ),
    )
    assert (
        synthesize_validated_executive_variation(
            question="Summarize Inbound",
            digests=digests,
            typed_evidence=evidence,
            variant_idx=2,
        )
        is None
    )


def test_contextual_page_help_all_pages_and_variation():
    scope = {"user_id": "u-1", "role": "General Manager", "teams": ["Inbound", "Outbound", "Pharmacy"]}
    session = SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026)

    pages = [
        ("monthly_presentation", "/monthly-presentation", "Monthly Presentation"),
        ("team_dashboard", "/team/inbound", "Team Dashboard"),
        ("executive_summary", "/executive", "Executive Summary & Balanced Scorecard"),
        ("function_summary", "/function/call-center", "Function Summary"),
        ("employee_profile", "/employee/E-101", "Employee Scorecard"),
        ("insights", "/insights", "Performance Insights"),
        ("corrective_actions", "/corrective-actions", "Corrective Actions Follow-Up"),
    ]

    for page_id, route, expected_title_fragment in pages:
        ctx = PageContextV1(page_id=page_id, route_id=route, month="September", year=2026)
        assert normalize_page_id(ctx) == page_id

        req0 = AiChatRequest(prompt="Explain this page", session_state=session, page_context=ctx, variation_seed=0)
        req1 = AiChatRequest(prompt="Explain this page", session_state=session, page_context=ctx, variation_seed=1)
        req2 = AiChatRequest(prompt="Explain this page", session_state=session, page_context=ctx, variation_seed=2)

        h0, _b0, sec0, _t0, f0, _w0 = build_page_help_payload(
            req=req0, scope=scope, session_state=session, selected_metric_display=None
        )
        h1, _b1, sec1, _t1, f1, _w1 = build_page_help_payload(
            req=req1, scope=scope, session_state=session, selected_metric_display=None
        )
        h2, _b2, sec2, _t2, f2, _w2 = build_page_help_payload(
            req=req2, scope=scope, session_state=session, selected_metric_display=None
        )

        assert expected_title_fragment in sec0.page_title
        assert expected_title_fragment in sec1.page_title
        assert expected_title_fragment in sec2.page_title
        assert len({h0, h1, h2}) == 3
        assert f0 != f1

    nav_req0 = AiChatRequest(prompt="Where can I check my dashboards?", session_state=session, variation_seed=0)
    nav_req1 = AiChatRequest(prompt="Where can I check my dashboards?", session_state=session, variation_seed=1)
    nh0, _, _, _ = build_navigation_payload(req=nav_req0, scope=scope, session_state=session)
    nh1, _, _, _ = build_navigation_payload(req=nav_req1, scope=scope, session_state=session)
    assert nh0 != nh1


def test_executive_variation_ledger_40_fact_parity(monkeypatch: pytest.MonkeyPatch):
    """Prompt fact rows and ClaimLedger validation must share the same 40-fact slice."""
    evidence = [
        TypedMetricEvidence(
            metric_id=f"Call Center:Inbound:metric_{chr(97 + idx)}:Employee",
            kpi_key=f"metric_{chr(97 + idx)}",
            display_name=f"Metric {chr(65 + idx)}",
            team="Inbound",
            performance_level="Employee",
            branch="all",
            period="September 2026",
            actual=float(70 + idx),
            target=90.0,
            actual_display=f"{70 + idx:.1f}%",
            target_display="90.0%",
            achievement_percent=float(75 + idx),
            weight_percent=5.0,
            unit="%",
            direction="higher_better",
            contributes_to_score=True,
            sample_size=20,
            source_link="/team/inbound?month=September&year=2026",
        )
        for idx in range(18)
    ]
    digests = [{"scope": "Inbound", "period": "September 2026", "overall_score": 85.0}]
    captured_prompts: list[str] = []

    class _CapturingEngine:
        def generate(self, request):
            captured_prompts.append(request.messages[0].content)
            return ProviderResponse(
                content=json.dumps(
                    {
                        "headline": "Inbound tracked Metric A at 70.0% and Metric R at 87.0% against 90.0% targets in September 2026.",
                        "narrative_bullets": [
                            "Metric A: 70.0%, Metric B: 71.0%, Metric C: 72.0%, Metric D: 73.0%, Metric E: 74.0%, Metric F: 75.0%.",
                            "Metric G: 76.0%, Metric H: 77.0%, Metric I: 78.0%, Metric J: 79.0%, Metric K: 80.0%, Metric L: 81.0%.",
                            "Metric M: 82.0%, Metric N: 83.0%, Metric O: 84.0%, Metric P: 85.0%, Metric Q: 86.0%, Metric R: 87.0%.",
                        ],
                    }
                ),
                provider="cloudflare",
                model="@cf/test-model",
                outcome="success",
                latency_ms=15.0,
                usage=TokenUsage(prompt_tokens=100, completion_tokens=30, total_tokens=130),
            )

    monkeypatch.setattr("services.ai.local_evidence_synthesis.local_synthesis_enabled", lambda: True)
    monkeypatch.setattr("services.ai.local_evidence_synthesis.get_unified_provider_engine", lambda: _CapturingEngine())

    res = synthesize_validated_executive_variation(
        question="Summarize all Inbound metrics in September 2026",
        digests=digests,
        typed_evidence=evidence,
        variant_idx=1,
    )
    assert res is not None
    assert "87.0%" in res.headline
    assert captured_prompts and "87.0%" in captured_prompts[0]


def test_orchestrator_blocks_cloud_variation_on_pii_override_and_proposal(monkeypatch: pytest.MonkeyPatch):
    """PII queries, deterministic provider_override, and proposal mode must never invoke cloud variation."""
    from services.ai.orchestrator import PmsAiOrchestrator
    from test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records

    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_PILOT_SCOPES", "*")
    monkeypatch.setattr("services.ai.orchestrator.local_synthesis_enabled", lambda: True)

    calls: list[str] = []

    def _spy_variation(**kwargs):
        calls.append(str(kwargs.get("question") or ""))
        return None

    monkeypatch.setattr("services.ai.orchestrator.synthesize_validated_executive_variation", _spy_variation)

    records = [
        _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 91.0, 45, 50, 90, 200),
        _make_call_center_record("EMP102", "Noor Hassan", "Inbound", 72.0, 30, 50, 60, 180),
    ]
    _patch_records(monkeypatch, records)
    db = _build_in_memory_db()
    admin_scope = {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True}
    session = SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026)
    try:
        # 1. provider_override="deterministic" blocks cloud variation even with variation_seed=1
        PmsAiOrchestrator(db, admin_scope).run_chat_turn(
            AiChatRequest(
                prompt="Compare Inbound Abandon Rate vs target in September 2026",
                session_state=session,
                variation_seed=1,
                provider_override="deterministic",
            )
        )
        assert calls == []

        # 2. proposal mode blocks cloud variation
        PmsAiOrchestrator(db, admin_scope).run_chat_turn(
            AiChatRequest(
                prompt="Propose a corrective action for Inbound Abandon Rate",
                session_state=session,
                variation_seed=1,
                provider_override="auto",
            )
        )
        assert calls == []

        # 3. Employee ranking / PII blocks cloud variation
        PmsAiOrchestrator(db, admin_scope).run_chat_turn(
            AiChatRequest(
                prompt="Who is the top performer in Inbound in September 2026?",
                session_state=session,
                variation_seed=1,
                provider_override="auto",
            )
        )
        assert calls == []

        # 4. Employee ID/name in prompt blocks cloud variation via PII sanitizer check
        PmsAiOrchestrator(db, admin_scope).run_chat_turn(
            AiChatRequest(
                prompt="Compare Inbound Abandon Rate vs target for EMP101 in September 2026",
                session_state=session,
                variation_seed=1,
                provider_override="auto",
            )
        )
        assert calls == []

        # 5. Aggregate non-PII query with auto override & variation_seed=1 invokes cloud variation
        PmsAiOrchestrator(db, admin_scope).run_chat_turn(
            AiChatRequest(
                prompt="Compare Inbound Abandon Rate vs target in September 2026",
                session_state=session,
                variation_seed=1,
                provider_override="auto",
            )
        )
        assert len(calls) == 1
    finally:
        db.close()


def test_followups_and_starters_never_leak_uae_to_egy_or_support_positions():
    from services.ai.providers import _build_dynamic_followups

    merged_kpi = {"lowest_kpi": {"kpi_label": "Accuracy", "kpi_key": "accuracy"}}
    for sess, hist in [
        (SessionFilterContext(function="Call Center", region="EGY"), []),
        (SessionFilterContext(function="Call Center", team="Support Positions"), []),
        (
            SessionFilterContext(function="Call Center", team="Inbound"),
            [AiChatMessage(role="user", content="Compare Coding EGY vs Submission EGY")],
        ),
    ]:
        followups = _build_dynamic_followups(
            prompt="What are the largest KPI gaps?",
            history=hist,
            scope=sess.team or sess.function or "Call Center",
            branch="All Branches",
            period="September 2026",
            merged=merged_kpi,
            variant_idx=0,
            session_state=sess,
        )
        joined = " ".join(followups)
        for forbidden in ("Dubai", "Sharjah", "Ajman", "Clinics", "UAE"):
            assert forbidden not in joined

    for sess in [
        SessionFilterContext(function="Call Center", team="Support Positions"),
        SessionFilterContext(function="Call Center", region="EGY"),
    ]:
        prompts = build_call_center_starter_prompts(sess)
        assert len(prompts) == 6
        text = " ".join(f"{p.label} {p.subtitle} {p.prompt}" for p in prompts)
        for forbidden in ("Dubai", "Sharjah", "Ajman", "Clinics", "UAE"):
            assert forbidden not in text
        if sess.team == "Support Positions":
            assert "Attendance gap" not in text


def test_contextual_page_help_monthly_presentation_scope_isolation():
    scope = {"user_id": "u-1", "role": "Manager", "teams": ["Pharmacy", "Support Positions", "Coding EGY"]}
    cases = [
        (
            SessionFilterContext(function="Pharmacy", month="September", year=2026),
            PageContextV1(page_id="monthly_presentation", function_id="Pharmacy", month="September", year=2026),
        ),
        (
            SessionFilterContext(function="Call Center", team="Support Positions", month="September", year=2026),
            PageContextV1(
                page_id="monthly_presentation",
                function_id="Call Center",
                team_id="Support Positions",
                month="September",
                year=2026,
            ),
        ),
        (
            SessionFilterContext(function="Call Center", region="EGY", month="September", year=2026),
            PageContextV1(
                page_id="monthly_presentation",
                function_id="Call Center",
                region="EGY",
                month="September",
                year=2026,
            ),
        ),
    ]
    for sess, ctx in cases:
        for seed in (0, 1, 2):
            req = AiChatRequest(prompt="Explain this page", session_state=sess, page_context=ctx, variation_seed=seed)
            h, bullets, sec, targets, followups, _w = build_page_help_payload(
                req=req, scope=scope, session_state=sess, selected_metric_display=None
            )
            combined = " ".join([h, *bullets, sec.summary, *sec.key_elements, *followups, *(t.description for t in targets)])
            for forbidden in ("UAE", "Dubai", "Sharjah", "Ajman", "Clinics"):
                assert forbidden not in combined


def test_spotlight_missing_months_no_double_period_across_variants():
    adapter = DeterministicLocalProviderAdapter()
    sig = extract_prompt_signals(
        "Was September 2026 the best month for Sara Mahmoud?",
        SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
    )
    digest = {
        "scope": "Inbound",
        "period": "September 2026",
        "spotlight": {
            "id": "EMP101",
            "name": "Sara Mahmoud",
            "team": "Inbound",
            "position": "Agent",
            "score": 93.5,
            "previous_score": 90.0,
            "change_pct": 3.5,
            "previous_period": "August 2026",
            "grade": "A",
            "best_score": 93.5,
            "best_months": ["September 2026"],
            "is_asked_period_best": True,
            "searched_window": "Apr–Sep 2026",
            "missing_months": ["June 2026"],
            "all_history": [
                {"period": "August 2026", "score": 90.0},
                {"period": "September 2026", "score": 93.5},
            ],
        },
    }
    for seed in (0, 1, 2):
        res = adapter.synthesize(
            prompt="Was September 2026 the best month for Sara Mahmoud?",
            signals=sig,
            tool_digests=[digest],
            guardrail_notes=[],
            variation_seed=seed,
        )
        assert ").)" not in res.headline
        assert ".)." not in res.headline
        assert ".." not in res.headline
        assert "June 2026 had no evaluated score and was excluded" in res.headline
        if seed in (1, 2):
            sentences = [s for s in res.headline.split(". ") if s.strip()]
            assert 1 <= len(sentences) <= 2



def test_relative_period_note_for_last_month():
    from services.ai.orchestrator import _relative_period_note

    note = _relative_period_note("which team is weakest last month?", "September 2026")
    assert note and "September 2026" in note
    assert _relative_period_note("ايه اكتر KPI بيهبط الشهر ده؟", "October 2026")


def test_no_relative_period_note_when_month_named_or_not_relative():
    from services.ai.orchestrator import _relative_period_note

    assert _relative_period_note("weakest team in October 2026", "October 2026") is None
    assert _relative_period_note("last month in Oct 2026", "October 2026") is None
    assert _relative_period_note("weakest team", "October 2026") is None
    assert _relative_period_note("last month", "") is None


def test_concern_phrasing_ranks_weakest_first():
    from services.ai.domain_policies import parse_query_rankings_spec

    for prompt in (
        "which team should I worry about most in Call Center?",
        "which team needs the most attention",
    ):
        spec = parse_query_rankings_spec(prompt)
        assert spec is not None and spec.sort_order == "asc" and spec.entity == "team"
    assert parse_query_rankings_spec("which team is best").sort_order == "desc"
