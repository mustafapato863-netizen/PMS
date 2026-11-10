from __future__ import annotations

import pytest
from services.ai.catalog import ai_evidence_cache
from services.ai.domain_policies import ParsedPromptSignals
from services.ai.providers import DeterministicLocalProviderAdapter


@pytest.fixture(autouse=True)
def _clear_cache():
    ai_evidence_cache.clear()
    yield
    ai_evidence_cache.clear()



def _synthesize(prompt: str, merged: dict, asks_least: bool = False):
    sig = ParsedPromptSignals()
    sig.asks_booking_count = True
    sig.asks_branch_comparison = True
    adapter = DeterministicLocalProviderAdapter()
    res = adapter.synthesize(
        prompt=prompt,
        signals=sig,
        tool_digests=[merged],
        guardrail_notes=[],
    )
    return res.headline, res.narrative_bullets


def test_three_valid_zero_counts():
    """Three valid recorded zero booking counts must announce a tie with 0 bookings each, not missing data."""
    merged = {
        "period": "September 2026",
        "scope": "Inbound",
        "requested_branches": ["Dubai", "Sharjah", "Ajman"],
        "branch_comparison": [
            {"branch": "Dubai", "bookings": 0, "attended": 0, "attendance_rate_pct": 0.0, "data_present": True},
            {"branch": "Sharjah", "bookings": 0, "attended": 0, "attendance_rate_pct": 0.0, "data_present": True},
            {"branch": "Ajman", "bookings": 0, "attended": 0, "attendance_rate_pct": 0.0, "data_present": True},
        ],
    }
    headline, bullets = _synthesize(
        prompt="Which branch has the most bookings: Dubai, Sharjah, or Ajman?",
        merged=merged,
    )
    assert "tied with 0 bookings each" in headline
    assert "missing or unpublished" not in headline
    assert len(bullets) >= 1
    assert "0 bookings" in bullets[0]


def test_one_missing_count_and_two_valid_counts():
    """When one branch has missing data, do not rank it as zero or declare a complete winner."""
    merged = {
        "period": "September 2026",
        "scope": "Inbound",
        "requested_branches": ["Dubai", "Sharjah", "Ajman"],
        "branch_comparison": [
            {"branch": "Dubai", "bookings": 150, "attended": 140, "attendance_rate_pct": 93.3, "data_present": True},
            {"branch": "Sharjah", "bookings": 80, "attended": 70, "attendance_rate_pct": 87.5, "data_present": True},
            {"branch": "Ajman", "bookings": None, "attended": None, "attendance_rate_pct": 0.0, "data_present": False},
        ],
    }
    headline, bullets = _synthesize(
        prompt="Which branch has the most bookings: Dubai, Sharjah, or Ajman?",
        merged=merged,
    )
    # Must report partially available data, mention Ajman as missing, and NOT declare Dubai complete winner
    assert "partially available" in headline
    assert "Ajman" in headline and "missing or unpublished" in headline
    assert "Dubai recorded 150 bookings" in headline
    assert "Sharjah recorded 80 bookings" in headline
    assert "led" not in headline


def test_two_branches_tied_for_highest_count():
    """Two branches tied for the highest count must announce the tie for first place without declaring a single winner."""
    merged = {
        "period": "September 2026",
        "scope": "Inbound",
        "requested_branches": ["Dubai", "Sharjah", "Ajman"],
        "branch_comparison": [
            {"branch": "Dubai", "bookings": 150, "attended": 140, "attendance_rate_pct": 93.3, "data_present": True},
            {"branch": "Sharjah", "bookings": 150, "attended": 135, "attendance_rate_pct": 90.0, "data_present": True},
            {"branch": "Ajman", "bookings": 90, "attended": 80, "attendance_rate_pct": 88.9, "data_present": True},
        ],
    }
    headline, bullets = _synthesize(
        prompt="Which branch has the most bookings: Dubai, Sharjah, or Ajman?",
        merged=merged,
    )
    assert "Dubai and Sharjah tied for the most" in headline
    assert "150 each" in headline
    assert "followed by Ajman with 90" in headline
    assert "led September" not in headline


def test_two_branches_tied_for_lowest_count():
    """Two branches tied for the lowest count must be accurately reported."""
    merged = {
        "period": "September 2026",
        "scope": "Inbound",
        "requested_branches": ["Dubai", "Sharjah", "Ajman"],
        "branch_comparison": [
            {"branch": "Dubai", "bookings": 180, "attended": 160, "attendance_rate_pct": 88.9, "data_present": True},
            {"branch": "Sharjah", "bookings": 70, "attended": 60, "attendance_rate_pct": 85.7, "data_present": True},
            {"branch": "Ajman", "bookings": 70, "attended": 65, "attendance_rate_pct": 92.9, "data_present": True},
        ],
    }
    headline, bullets = _synthesize(
        prompt="Which branch has the fewest bookings: Dubai, Sharjah, or Ajman?",
        merged=merged,
    )
    assert "Sharjah and Ajman tied for the fewest" in headline
    assert "70 each" in headline
    assert "Dubai with 180" in headline


def test_three_equal_nonzero_counts():
    """Three branches with equal counts must announce a tie across all three."""
    merged = {
        "period": "September 2026",
        "scope": "Inbound",
        "requested_branches": ["Dubai", "Sharjah", "Ajman"],
        "branch_comparison": [
            {"branch": "Dubai", "bookings": 120, "attended": 110, "attendance_rate_pct": 91.7, "data_present": True},
            {"branch": "Sharjah", "bookings": 120, "attended": 105, "attendance_rate_pct": 87.5, "data_present": True},
            {"branch": "Ajman", "bookings": 120, "attended": 108, "attendance_rate_pct": 90.0, "data_present": True},
        ],
    }
    headline, bullets = _synthesize(
        prompt="Compare Dubai, Sharjah, and Ajman bookings",
        merged=merged,
    )
    assert "tied with 120 bookings each" in headline


def test_normal_comparison_with_single_winner():
    """Normal comparison with single distinct winner."""
    merged = {
        "period": "September 2026",
        "scope": "Inbound",
        "requested_branches": ["Dubai", "Sharjah", "Ajman"],
        "branch_comparison": [
            {"branch": "Dubai", "bookings": 200, "attended": 185, "attendance_rate_pct": 92.5, "data_present": True},
            {"branch": "Sharjah", "bookings": 110, "attended": 95, "attendance_rate_pct": 86.4, "data_present": True},
            {"branch": "Ajman", "bookings": 65, "attended": 55, "attendance_rate_pct": 84.6, "data_present": True},
        ],
    }
    headline, bullets = _synthesize(
        prompt="Which branch has the most bookings: Dubai, Sharjah, or Ajman?",
        merged=merged,
    )
    assert "Dubai led September 2026 Inbound bookings with 200" in headline
    assert "Sharjah with 110 and Ajman with 65" in headline


def test_missing_or_unpublished_month():
    """Missing or unpublished month reports missing/unpublished without fabricating zeros."""
    merged = {
        "period": "October 2026",
        "scope": "Inbound",
        "requested_branches": ["Dubai", "Sharjah", "Ajman"],
        "branch_comparison": [
            {"branch": "Dubai", "bookings": None, "period_published": False, "data_present": False},
            {"branch": "Sharjah", "bookings": None, "period_published": False, "data_present": False},
            {"branch": "Ajman", "bookings": None, "period_published": False, "data_present": False},
        ],
    }
    headline, bullets = _synthesize(
        prompt="Which branch has the most bookings in October 2026?",
        merged=merged,
    )
    assert "Booking data is missing or unpublished for Dubai, Sharjah, Ajman in October 2026." in headline
    assert "No booking records were found" in bullets[0]


def _build_test_db_session():
    from config.database import Base
    from models.models import ProductSetting
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(ProductSetting(key="ai_enabled", enabled=True))
    session.commit()
    return session


def _make_schema_record(
    *,
    emp_id: str,
    name: str,
    team: str,
    score: float,
    dubai_b: int,
    sharjah_b: int,
    ajman_b: int,
    month: str = "September",
    year: int = 2026,
):
    from models.schemas import CallsData, EvaluationData, GeoBreakdown, GeoData, PerformanceRecord as SchemaRecord

    return SchemaRecord(
        id=f"{team}_{emp_id}_{year}_{month[:3]}",
        employee_id=emp_id,
        employee_name=name,
        team=team,
        month=month,
        year=year,
        region="EGY",
        position="Call Center Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=score, grade="B"),
        calls=CallsData(inbound=400, total_handled=500, abandoned=15),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=dubai_b, sharjah=sharjah_b, ajman=ajman_b, clinics=10),
            attended=GeoBreakdown(dubai=max(0, dubai_b - 5), sharjah=max(0, sharjah_b - 5), ajman=max(0, ajman_b - 5), clinics=8),
        ),
        kpi_values=[],
    )


def test_full_data_path_normal_winner(monkeypatch):
    """Full data path from database rows through PmsAiOrchestrator for normal winner."""
    session = _build_test_db_session()
    rec = _make_schema_record(emp_id="E001", name="Agent 1", team="Inbound", score=88.0, dubai_b=200, sharjah_b=110, ajman_b=65)
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_records", lambda _self, **_kw: [rec])
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_analysis_records", lambda _self, **_kw: [rec])
    
    from services.ai.orchestrator import PmsAiOrchestrator
    from models.ai_schemas import AiChatRequest, SessionFilterContext

    scope = {"role": "Admin", "accessible_teams": ["Inbound", "Outbound"], "accessible_branches": ["dubai", "sharjah", "ajman"]}
    orchestrator = PmsAiOrchestrator(session, scope)
    res = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="Which branch had more Inbound bookings in September 2026: Dubai or Sharjah?",
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
            provider_override="deterministic",
        )
    )
    assert res.outcome == "answer"
    assert "Dubai led" in res.headline or "Dubai" in res.headline
    assert "200" in res.headline
    assert "110" in res.headline


def test_full_data_path_three_valid_zeros(monkeypatch):
    """Full data path: all branches recorded 0 bookings in database."""
    session = _build_test_db_session()
    rec = _make_schema_record(emp_id="E001", name="Agent 1", team="Inbound", score=88.0, dubai_b=0, sharjah_b=0, ajman_b=0)
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_records", lambda _self, **_kw: [rec])
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_analysis_records", lambda _self, **_kw: [rec])
    
    from services.ai.orchestrator import PmsAiOrchestrator
    from models.ai_schemas import AiChatRequest, SessionFilterContext

    scope = {"role": "Admin", "accessible_teams": ["Inbound", "Outbound"], "accessible_branches": ["dubai", "sharjah", "ajman"]}
    orchestrator = PmsAiOrchestrator(session, scope)
    res = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="Which branch has the most bookings: Dubai, Sharjah, or Ajman in September 2026?",
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
            provider_override="deterministic",
        )
    )
    assert res.outcome == "answer"
    assert "tied with 0 bookings each" in res.headline
    assert "missing or unpublished" not in res.headline


def test_full_data_path_tied_highest_count(monkeypatch):
    """Full data path: two branches tied for highest count."""
    session = _build_test_db_session()
    rec = _make_schema_record(emp_id="E001", name="Agent 1", team="Inbound", score=88.0, dubai_b=150, sharjah_b=150, ajman_b=90)
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_records", lambda _self, **_kw: [rec])
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_analysis_records", lambda _self, **_kw: [rec])

    from services.ai.orchestrator import PmsAiOrchestrator
    from models.ai_schemas import AiChatRequest, SessionFilterContext

    scope = {"role": "Admin", "accessible_teams": ["Inbound", "Outbound"], "accessible_branches": ["dubai", "sharjah", "ajman"]}
    orchestrator = PmsAiOrchestrator(session, scope)
    res = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="Which branch has the most bookings: Dubai, Sharjah, or Ajman in September 2026?",
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
            provider_override="deterministic",
        )
    )
    assert res.outcome == "answer"
    assert "Dubai and Sharjah tied for the most" in res.headline
    assert "150 each" in res.headline
    assert "followed by Ajman with 90" in res.headline


class _MockContext:
    def __init__(self, records):
        self._records = records

    def get_scoped_records(self):
        return self._records


def test_scenario_1_attendance_present_booking_absent():
    from types import SimpleNamespace
    from services.ai.tool_registry import DeterministicToolRegistry

    rec = SimpleNamespace(
        id="rec_att_only",
        employee_id="E1",
        employee_name="Emp 1",
        team="Inbound",
        month="September",
        year=2026,
        region="EGY",
        geo=SimpleNamespace(
            bookings=None,
            attended=SimpleNamespace(dubai=10, sharjah=5, ajman=2),
        ),
        calls=None,
    )
    reg = DeterministicToolRegistry(_MockContext([rec]))
    res = reg._compute_operational_volumes(month="September", year=2026, team="Inbound", function=None, branch="dubai")
    assert res["total_bookings"] is None
    assert res["booking_present"] is False
    assert res["attended_present"] is True
    assert res["total_attended"] == 10.0


def test_scenario_2_calls_present_booking_absent():
    from types import SimpleNamespace
    from services.ai.tool_registry import DeterministicToolRegistry

    rec = SimpleNamespace(
        id="rec_calls_only",
        employee_id="E2",
        employee_name="Emp 2",
        team="Inbound",
        branch_key="dubai",
        month="September",
        year=2026,
        region="EGY",
        calls=SimpleNamespace(inbound=250, total_handled=300),
        geo=None,
    )
    reg = DeterministicToolRegistry(_MockContext([rec]))
    res = reg._compute_operational_volumes(month="September", year=2026, team="Inbound", function=None, branch="dubai")
    assert res["total_bookings"] is None
    assert res["booking_present"] is False
    assert res["calls_present"] is True
    assert res["total_calls_handled"] == 300.0


def test_scenario_3_explicit_zero_booking():
    from types import SimpleNamespace
    from services.ai.tool_registry import DeterministicToolRegistry

    rec = SimpleNamespace(
        id="rec_zero",
        employee_id="E3",
        employee_name="Emp 3",
        team="Inbound",
        month="September",
        year=2026,
        region="EGY",
        geo=SimpleNamespace(
            bookings=SimpleNamespace(dubai=0, sharjah=10, ajman=5),
            attended=SimpleNamespace(dubai=0, sharjah=8, ajman=4),
        ),
        calls=None,
    )
    reg = DeterministicToolRegistry(_MockContext([rec]))
    res = reg._compute_operational_volumes(month="September", year=2026, team="Inbound", function=None, branch="dubai")
    assert res["total_bookings"] == 0.0
    assert res["booking_present"] is True
    assert res["data_present"] is True


def test_scenario_5_mix_present_and_missing_in_same_branch():
    from types import SimpleNamespace
    from services.ai.tool_registry import DeterministicToolRegistry

    rec1 = SimpleNamespace(
        id="rec_5a",
        employee_id="E5a",
        employee_name="Emp 5a",
        team="Inbound",
        branch_key="dubai",
        month="September",
        year=2026,
        region="EGY",
        geo=SimpleNamespace(
            bookings=SimpleNamespace(dubai=40, sharjah=10, ajman=5),
            attended=SimpleNamespace(dubai=35, sharjah=8, ajman=4),
        ),
        calls=None,
    )
    rec2 = SimpleNamespace(
        id="rec_5b",
        employee_id="E5b",
        employee_name="Emp 5b",
        team="Inbound",
        branch_key="dubai",
        month="September",
        year=2026,
        region="EGY",
        geo=None,
        calls=None,
    )
    reg = DeterministicToolRegistry(_MockContext([rec1, rec2]))
    res = reg._compute_operational_volumes(month="September", year=2026, team="Inbound", function=None, branch="dubai")
    assert res["booking_present"] is True
    assert res["has_partial_evidence"] is True
    assert res["booking_complete"] is False
    assert res["total_bookings"] == 40.0


def test_scenario_7_record_in_same_month_different_team():
    from types import SimpleNamespace
    from services.ai.tool_registry import DeterministicToolRegistry

    rec_outbound = SimpleNamespace(
        id="rec_outbound",
        employee_id="E7",
        employee_name="Emp 7",
        team="Outbound",
        month="September",
        year=2026,
        region="EGY",
        geo=SimpleNamespace(bookings=SimpleNamespace(dubai=100)),
        calls=None,
    )
    reg = DeterministicToolRegistry(_MockContext([rec_outbound]))
    res = reg._compute_operational_volumes(month="September", year=2026, team="Inbound", function=None, branch="dubai")
    assert res["period_published"] is False
    assert res["booking_present"] is False
    assert res["total_bookings"] is None


def test_scenario_8_record_in_same_month_different_country_scope():
    from services.ai.tool_registry import DeterministicToolRegistry

    # Scoped records filter out UAE records when user/session scope is Egypt
    reg = DeterministicToolRegistry(_MockContext([]))
    res = reg._compute_operational_volumes(month="September", year=2026, team="Inbound", function=None, branch="dubai")
    assert res["period_published"] is False
    assert res["booking_present"] is False
    assert res["total_bookings"] is None


def test_scenario_14_missing_attendance_with_present_bookings():
    from services.ai.domain_policies import ParsedPromptSignals
    from services.ai.providers import DeterministicLocalProviderAdapter

    merged = {
        "period": "September 2026",
        "scope": "Inbound",
        "requested_branches": ["Dubai", "Sharjah", "Ajman"],
        "branch_comparison": [
            {"branch": "Dubai", "bookings": 100, "attended": None, "attendance_rate_pct": None, "data_present": True},
            {"branch": "Sharjah", "bookings": 80, "attended": 70, "attendance_rate_pct": 87.5, "data_present": True},
            {"branch": "Ajman", "bookings": 60, "attended": 50, "attendance_rate_pct": 83.3, "data_present": True},
        ],
    }
    adapter = DeterministicLocalProviderAdapter()
    sig = ParsedPromptSignals()
    sig.asks_booking_count = True
    sig.asks_branch_comparison = True
    res = adapter.synthesize(
        prompt="Compare bookings across branches",
        signals=sig,
        tool_digests=[merged],
        guardrail_notes=[],
    )
    assert any("attendance unrecorded" in b for b in res.narrative_bullets)
    assert not any("0.0%" in b and "Dubai" in b for b in res.narrative_bullets)


def test_scenario_15_missing_score_with_available_booking_counts():
    from services.ai.domain_policies import ParsedPromptSignals
    from services.ai.providers import DeterministicLocalProviderAdapter

    merged = {
        "period": "September 2026",
        "scope": "Inbound",
        "requested_branches": ["Dubai", "Sharjah", "Ajman"],
        "branch_comparison": [
            {"branch": "Dubai", "bookings": 100, "score": None, "data_present": True},
            {"branch": "Sharjah", "bookings": 80, "score": None, "data_present": True},
            {"branch": "Ajman", "bookings": 60, "score": None, "data_present": True},
        ],
    }
    adapter = DeterministicLocalProviderAdapter()
    sig = ParsedPromptSignals()
    sig.asks_booking_count = True
    sig.asks_branch_comparison = True
    res = adapter.synthesize(
        prompt="Compare Dubai and Sharjah bookings",
        signals=sig,
        tool_digests=[merged],
        guardrail_notes=[],
    )
    assert "0.0%" not in res.headline



