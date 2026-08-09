import re
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import GeneratedReport, ReportDraft, ReportTemplate, User
from models.report_definitions import (
    ReportBlock,
    ManagementCommentary,
    ReportDraftCreate,
    ReportDraftDefinition,
    ReportSlide,
    ReportTemplateDefinition,
    ReportDraftUpdate,
    ReportGenerateRequest,
    ReportPeriod,
    ReportScope,
)
from models.schemas import EvaluationData, PerformanceRecord
from services.report_registry import validate_definition
from services.report_story_service import ReportStoryService, StoryAccessError, StoryConflictError
from services.report_system_templates import SYSTEM_TEMPLATES


class StubRecordService:
    def __init__(self, records):
        self.records = records
        self.filters = []

    def list_records(self, **filters):
        self.filters.append(filters)
        return [
            item for item in self.records
            if all(
                value in {None, ""} or str(getattr(item, key, "")).casefold() == str(value).casefold()
                for key, value in filters.items()
            )
        ]

    def list_analysis_records(self):
        self.filters.append({"analysis_records": True})
        return list(self.records)


def record(employee_id: str, team: str, month: str, score: float, *, target: float = 90, contribution: float = 0.25):
    return PerformanceRecord(
        id=f"{employee_id}-2026-{month}", employee_id=employee_id, employee_name=f"Employee {employee_id}",
        team=team, position="Agent", region="EGY", performance_level="Employee", year=2026, month=month,
        status="Below Target" if score < 70 else "Meets", evaluation=EvaluationData(score=score, grade="D" if score < 70 else "B"),
        kpi_values=[{"kpi_key": "quality", "label": "Quality Score", "actual_value": score, "target_value": target,
                     "achievement_ratio": score / target if target else None, "contribution": contribution, "weight": 0.4,
                     "direction": "higher_better"}],
    )


@pytest.fixture()
def story_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[User.__table__, ReportTemplate.__table__, ReportDraft.__table__, GeneratedReport.__table__])
    session = sessionmaker(bind=engine)()
    user = User(id=uuid.uuid4(), username="story-admin", email="story@example.com", password_hash="unused", role="Admin")
    session.add(user); session.commit()
    yield session, user
    session.close()


def scope(user):
    return {"user": user, "user_id": str(user.id), "username": user.username, "role": "Admin", "accessible_teams": [],
            "accessible_team_levels": [], "is_general_manager": True, "legacy_unscoped": False}


def service(session, records):
    result = ReportStoryService(session, StubRecordService(records))
    result.actions.list_active = lambda: []
    result.plans.list_active = lambda: []
    result.repo.list_upload_logs = lambda: []
    result.insights._authorized_records = lambda _scope: (list(records), 0)
    return result


def draft_payload(template_id: str, name="June Offshore Review"):
    return ReportDraftCreate(name=name, report_type="executive", template_id=template_id, scope=ReportScope(region="EGY"),
                             primary_period=ReportPeriod(month="June", year=2026), comparison_period=ReportPeriod(month="May", year=2026))


def test_system_templates_are_idempotent_versioned_and_registry_compatible(story_db):
    session, user = story_db
    result = service(session, [])
    first = result.list_templates(scope(user)); second = result.list_templates(scope(user))
    assert len(SYSTEM_TEMPLATES) == 8
    assert len(first) == len(second) == 7
    assert session.query(ReportTemplate).count() == 8
    full = next(item for item in first if item["template_key"] == "offshore_monthly_performance_review")
    compact = next(item for item in first if item["template_key"] == "offshore_monthly_executive_brief")
    assert full["version"] == 3 and full["definition"]["story_metadata"]["mode"] == "full"
    assert compact["version"] == 1 and compact["definition"]["story_metadata"]["mode"] == "compact"
    assert all(not [issue for issue in validate_definition(ReportTemplateDefinition.model_validate(item.definition_json)) if issue["severity"] == "error"] for item in session.query(ReportTemplate).all())


def test_two_block_layout_accepts_mixed_content_without_overlapping_export_bounds():
    definition = ReportTemplateDefinition(slides=[ReportSlide(
        id="mixed-page", title="Mixed Content", layout="two_blocks", order=0,
        blocks=[
            ReportBlock(id="narrative", type="executive_summary", slot="left"),
            ReportBlock(id="performance", type="kpi_performance", slot="right"),
        ],
    )])

    assert validate_definition(definition) == []
    from exports.presentation_pdf import LAYOUT_BOUNDS
    assert LAYOUT_BOUNDS["two_blocks"]["left"] != LAYOUT_BOUNDS["two_blocks"]["right"]


def test_offshore_template_expands_real_authorized_departments_and_refreshes_period_data(story_db):
    session, user = story_db
    records = [record("A", "Inbound", "May", 60), record("A", "Inbound", "June", 70),
               record("B", "Outbound", "May", 80), record("B", "Outbound", "June", 90)]
    result = service(session, records)
    template = next(item for item in result.list_templates(scope(user)) if item["template_key"] == "offshore_monthly_performance_review")
    draft = result.create_draft(draft_payload(template["id"]), scope(user))
    assert len(draft["definition"]["slides"]) == 13
    titles = [page["title"] for page in draft["definition"]["slides"]]
    assert "Inbound - Team / Position Deep Dive" in titles and "Outbound - Team / Position Deep Dive" in titles
    assert sum("Team / Position Deep Dive" in title for title in titles) == 2
    comparison_page = next(page for page in draft["definition"]["slides"] if page["title"] == "Overall Score Movement")
    data = result.resolve_slide(draft["id"], comparison_page["id"], scope(user))
    comparison = next(block for block in data["blocks"].values() if block["block_type"] == "overall_score_movement_bridge")
    assert [comparison["data"]["previous_overall_score"], comparison["data"]["current_overall_score"]] == [70.0, 80.0]


def test_full_and_compact_stories_create_one_page_per_primary_period_team(story_db):
    session, user = story_db
    rows = []
    for index, team in enumerate(["Inbound", "Outbound", "Pre-Approvals"]):
        rows.extend([record(str(index), team, "May", 60 + index), record(str(index), team, "June", 70 + index)])
    result = service(session, rows)
    templates = result.list_templates(scope(user))
    full = next(item for item in templates if item["template_key"] == "offshore_monthly_performance_review")
    compact = next(item for item in templates if item["template_key"] == "offshore_monthly_executive_brief")
    full_draft = result.create_draft(draft_payload(full["id"], "Full Story"), scope(user))
    compact_draft = result.create_draft(draft_payload(compact["id"], "Compact Story"), scope(user))
    assert len(full_draft["definition"]["slides"]) == 14
    assert len(compact_draft["definition"]["slides"]) == 7
    assert sum("Team / Position Deep Dive" in page["title"] for page in full_draft["definition"]["slides"]) == 3
    assert sum("Team Snapshot" in page["title"] for page in compact_draft["definition"]["slides"]) == 3
    full_team_payload = draft_payload(full["id"], "Full Team Story")
    full_team_payload.scope = ReportScope(region="EGY", team="Inbound")
    compact_team_payload = draft_payload(compact["id"], "Compact Team Story")
    compact_team_payload.scope = ReportScope(region="EGY", team="Inbound")
    assert len(result.create_draft(full_team_payload, scope(user))["definition"]["slides"]) == 12
    assert len(result.create_draft(compact_team_payload, scope(user))["definition"]["slides"]) == 5


def test_system_template_v3_seeding_preserves_existing_v1_and_v2(story_db):
    session, user = story_db
    current = next(item for item in SYSTEM_TEMPLATES if item["template_key"] == "offshore_monthly_performance_review")
    definition = ReportTemplateDefinition.model_validate(current["definition"])
    legacy = ReportTemplate(
        name="Legacy Offshore Review", template_key=current["template_key"], report_type="executive",
        description="Legacy v1", owner_user_id=None, visibility="organization", version=1,
        definition_json=definition.model_dump(mode="json"), theme_key=definition.theme_key,
        language=definition.language, preferred_format="pdf", is_system_template=True,
    )
    session.add(legacy); session.commit()
    templates = service(session, []).list_templates(scope(user))
    assert next(item for item in templates if item["template_key"] == current["template_key"])["version"] == 3
    assert session.query(ReportTemplate).filter(ReportTemplate.template_key == current["template_key"]).count() == 3


def test_phase_two_template_builds_all_management_analysis_blocks_and_preserves_user_template(story_db):
    session, user = story_db
    private_definition = ReportTemplateDefinition(slides=[ReportSlide(
        id="private-page", title="Private Page", layout="full_width", order=0,
        blocks=[ReportBlock(id="private-summary", type="executive_summary", slot="full")],
    )])
    private = ReportTemplate(
        name="My Saved Story", template_key="my_saved_story", report_type="executive",
        description="User-owned", owner_user_id=user.id, visibility="private", version=1,
        definition_json=private_definition.model_dump(mode="json"), theme_key="sgh_default",
        language="en", preferred_format="pdf", is_system_template=False,
    )
    session.add(private); session.commit()
    result = service(session, [])
    templates = result.list_templates(scope(user))
    full = next(item for item in templates if item["template_key"] == "offshore_monthly_performance_review")
    phase_two_types = {
        "overall_score_movement_bridge", "lowest_kpis_weighted_impact", "lowest_employees_current_period",
        "three_month_consecutive_low_performers", "applied_configuration_audit", "root_cause_evidence_matrix",
    }
    actual = {block["type"] for page in full["definition"]["slides"] for block in page["blocks"]}
    assert full["version"] == 3 and phase_two_types <= actual
    saved = next(item for item in templates if item["template_key"] == "my_saved_story")
    assert saved["version"] == 1 and saved["definition"]["slides"][0]["title"] == "Private Page"


def test_management_blocks_respect_action_permission_without_hiding_performance_evidence(story_db):
    session, user = story_db
    records = [record("A", "Inbound", month, score) for month, score in [("April", 60), ("May", 59), ("June", 58)]]
    result = service(session, records)
    viewer_scope = scope(user) | {"role": "Viewer", "accessible_teams": ["Inbound"], "is_general_manager": False}
    template = next(item for item in result.list_templates(viewer_scope) if item["template_key"] == "offshore_monthly_performance_review")
    payload = draft_payload(template["id"], "Permission Scoped Story")
    payload.scope = ReportScope(team="Inbound")
    draft = result.create_draft(payload, viewer_scope)
    root_page = next(page for page in draft["definition"]["slides"] if page["title"] == "Evidence-Based Root Cause Analysis")
    result.actions.list_active = lambda: (_ for _ in ()).throw(AssertionError("Actions must not load without view_actions"))
    resolved = result.resolve_slide(draft["id"], root_page["id"], viewer_scope)
    root = next(iter(resolved["blocks"].values()))
    assert root["state"] == "ready"
    assert any(row["evidence_source_type"] == "Authorization boundary" for row in root["data"]["rows"])
    validation = result.validate_draft(draft["id"], viewer_scope, persist=False)
    assert not any(issue.code == "unquantified_action" for issue in validation.issues)


def test_explicit_team_without_primary_period_data_is_rejected(story_db):
    session, user = story_db
    result = service(session, [record("A", "Inbound", "May", 70)])
    template = next(item for item in result.list_templates(scope(user)) if item["template_key"] == "offshore_monthly_performance_review")
    payload = draft_payload(template["id"], "Missing Primary Team")
    payload.scope = ReportScope(region="EGY", team="Inbound")
    with pytest.raises(ValueError, match="No performance data is available for June 2026"):
        result.create_draft(payload, scope(user))


def test_top_performers_resolves_with_scoped_records_without_loading_actions_or_plans(story_db):
    session, user = story_db
    records = [
        record("A", "Inbound", "May", 70),
        record("A", "Inbound", "June", 82),
        record("B", "Outbound", "June", 95),
    ]
    result = service(session, records)
    result.actions.list_active = lambda: (_ for _ in ()).throw(AssertionError("Actions must not load"))
    result.plans.list_active = lambda: (_ for _ in ()).throw(AssertionError("Plans must not load"))
    payload = ReportDraftCreate(
        name="Focused People Preview",
        report_type="executive",
        template_id=None,
        scope=ReportScope(region="EGY", team="Inbound"),
        primary_period=ReportPeriod(month="June", year=2026),
        comparison_period=ReportPeriod(month="May", year=2026),
    )
    draft = result.create_draft(payload, scope(user))
    definition = ReportDraftDefinition(
        slides=[ReportSlide(
            id="people-page",
            title="Top Performers",
            layout="full_width",
            order=0,
            blocks=[ReportBlock(id="top-people", type="top_performers", slot="full")],
        )],
    )
    updated = result.update_draft(
        draft["id"],
        ReportDraftUpdate(expected_version=draft["version"], definition=definition),
        scope(user),
    )

    resolved = result.resolve_slide(updated["id"], "people-page", scope(user))

    assert [row["employee"] for row in resolved["blocks"]["top-people"]["data"]["rows"]] == ["Employee A"]


def test_team_story_business_blocks_resolve_from_canonical_workspace(story_db):
    session, user = story_db
    result = service(session, [record("A", "Inbound", "May", 60), record("A", "Inbound", "June", 70)])
    template = next(item for item in result.list_templates(scope(user)) if item["template_key"] == "offshore_monthly_performance_review")
    draft = result.create_draft(draft_payload(template["id"], "Business Blocks"), scope(user))
    team_page = next(page for page in draft["definition"]["slides"] if page["title"] == "Inbound - Team / Position Deep Dive")
    resolved = result.resolve_slide(draft["id"], team_page["id"], scope(user))
    by_type = {value["block_type"]: value for value in resolved["blocks"].values()}
    assert by_type["team_performance_overview"]["state"] == "ready"
    assert by_type["team_performance_overview"]["data"]["metrics"][0]["display"] == "70.0%"
    assert by_type["team_performance_analysis"]["state"] == "ready"
    assert "narrative" in by_type["team_performance_analysis"]["data"]


def test_zero_target_is_not_divided_and_optimistic_save_detects_conflict(story_db):
    session, user = story_db
    rows = [record("A", "Inbound", "May", 60, target=0), record("A", "Inbound", "June", 61, target=0)]
    result = service(session, rows)
    template = next(item for item in result.list_templates(scope(user)) if item["template_key"] == "team_performance_review")
    draft = result.create_draft(draft_payload(template["id"], "June Team Review"), scope(user))
    context = result._context(result._get_draft(draft["id"], scope(user)), scope(user))
    kpi = result._kpis(context)[0]
    assert kpi["achievement"] is None and kpi["status"] == "invalid target"
    updated = result.update_draft(draft["id"], ReportDraftUpdate(expected_version=1, management_commentary=ManagementCommentary(entries={})), scope(user))
    assert updated["version"] == 2
    with pytest.raises(StoryConflictError):
        result.update_draft(draft["id"], ReportDraftUpdate(expected_version=1, name="Stale save"), scope(user))


def test_three_month_rule_requires_consecutive_valid_low_periods(story_db):
    session, user = story_db
    rows = [record("LOW", "Inbound", month, score) for month, score in [("April", 60), ("May", 59), ("June", 58)]]
    rows += [record("GAP", "Inbound", "March", 50), record("GAP", "Inbound", "May", 50), record("GAP", "Inbound", "June", 50)]
    result = service(session, rows)
    template = next(item for item in result.list_templates(scope(user)) if item["template_key"] == "team_performance_review")
    draft = result.create_draft(draft_payload(template["id"], "Three Month Review"), scope(user))
    context = result._context(result._get_draft(draft["id"], scope(user)), scope(user))
    employees = [item["employee"] for item in result._consecutive_low(context)]
    assert employees == ["Employee LOW"]


def test_score_movement_reconciles_contributions_and_labels_estimates(story_db):
    session, user = story_db
    result = service(session, [record("A", "Inbound", "May", 60, contribution=0.20), record("A", "Inbound", "June", 65, contribution=0.25)])
    template = next(item for item in result.list_templates(scope(user)) if item["template_key"] == "team_performance_review")
    draft = result.create_draft(draft_payload(template["id"], "Movement Review"), scope(user))
    context = result._context(result._get_draft(draft["id"], scope(user)), scope(user))
    movement = result._movement(context, result._kpis(context))
    assert movement["score_change"] == 5
    assert movement["reconciled_total"] == 5
    assert movement["is_exact"] is True
    assert "Measured KPI contribution" in movement["narrative"]


def test_pdf_generation_is_16_by_9_and_generated_snapshot_is_immutable(story_db):
    session, user = story_db
    rows = [record("A", "Inbound", "May", 60), record("A", "Inbound", "June", 70)]
    result = service(session, rows)
    template = next(item for item in result.list_templates(scope(user)) if item["template_key"] == "team_performance_review")
    draft = result.create_draft(draft_payload(template["id"], "Immutable Team Review"), scope(user))
    generated = result.generate(draft["id"], ReportGenerateRequest(expected_version=draft["version"]), scope(user))
    stored = session.query(GeneratedReport).filter(GeneratedReport.id == uuid.UUID(generated["id"])).one()
    before = bytes(stored.file_data); snapshot = stored.data_snapshot_json
    assert before.count(b"/Type /Page ") == 8
    assert re.search(rb"/MediaBox \[0 0 960 540\]", before)
    rows[-1].evaluation.score = 5
    session.expire_all()
    stored_again = session.query(GeneratedReport).filter(GeneratedReport.id == stored.id).one()
    assert bytes(stored_again.file_data) == before
    assert stored_again.data_snapshot_json == snapshot
    assert set(stored_again.narrative_snapshot_json) == {"system_analysis", "management_commentary"}
    assert len(stored_again.integrity_identifier) == 64


def test_phase_two_preview_and_pdf_share_identical_normalized_management_data(story_db):
    session, user = story_db
    rows = [record("A", "Inbound", month, score, contribution=contribution) for month, score, contribution in [
        ("April", 68, .28), ("May", 65, .25), ("June", 60, .20),
    ]]
    result = service(session, rows)
    template = next(item for item in result.list_templates(scope(user)) if item["template_key"] == "offshore_monthly_performance_review")
    payload = draft_payload(template["id"], "Phase Two Management Story")
    payload.scope = ReportScope(team="Inbound")
    draft = result.create_draft(payload, scope(user))
    page = next(page for page in draft["definition"]["slides"] if page["title"] == "Overall Score Movement")
    preview = result.resolve_slide(draft["id"], page["id"], scope(user))
    block_id = page["blocks"][0]["id"]
    generated = result.generate(draft["id"], ReportGenerateRequest(expected_version=draft["version"]), scope(user))
    stored = session.query(GeneratedReport).filter(GeneratedReport.id == uuid.UUID(generated["id"])).one()
    assert stored.template_version == 3
    assert stored.data_snapshot_json[page["id"]]["blocks"][block_id]["data"] == preview["blocks"][block_id]["data"]
    assert bytes(stored.file_data).count(b"/Type /Page ") == 12
    assert re.search(rb"/MediaBox \[0 0 960 540\]", bytes(stored.file_data))


def test_scope_authorization_is_revalidated_on_draft_creation(story_db):
    session, user = story_db
    result = service(session, [record("A", "Outbound", "June", 70)])
    template = next(item for item in result.list_templates(scope(user)) if item["template_key"] == "team_performance_review")
    manager_scope = scope(user) | {"role": "Manager", "accessible_teams": ["Inbound"], "is_general_manager": False}
    payload = draft_payload(template["id"], "Unauthorized Review")
    payload.scope = ReportScope(team="Outbound")
    with pytest.raises(StoryAccessError):
        result.create_draft(payload, manager_scope)


def test_root_cause_action_quantification_and_feedback_reuse_existing_action(story_db):
    session, user = story_db
    result = service(session, [])
    team = SimpleNamespace(name="Inbound", display_name="Inbound", region="EGY", team_level="employee")
    employee = SimpleNamespace(employee_id="A", name="Employee A")
    owner = SimpleNamespace(username="manager")
    plan = SimpleNamespace(baseline_value=19.2, target_value=25, expected_impact=2.4, actual_impact=None, outcome_unit="%",
                           period_start=date(2026, 6, 15), milestones=[SimpleNamespace(due_date=date(2026, 7, 15), status="Pending")])
    due_date = date.today() + timedelta(days=30)
    action = SimpleNamespace(
        action_type="Coaching", action_text="Increase Booking Conversion Rate", root_cause_note="Script adherence requires coaching",
        team=team, employee=employee, owner=owner, plan=plan, linked_kpi_key="booking_rate", due_date=due_date,
        status="In Progress", priority="High", evidence_reference="QA review", completion_note=None,
        created_at=datetime(2026, 6, 15, tzinfo=timezone.utc), updated_at=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )
    context = {"actions": [action], "current": [record("A", "Inbound", "June", 60)]}
    causes = result._root_causes(context)
    actions = result._serialize_actions(context, "Staff")
    feedback_rows, feedback_counts = result._feedback(context)
    assert causes[0]["classification"] == "Likely Root Cause"
    assert causes[0]["confidence"] == "likely"
    assert causes[0]["category"] == "Staff"
    assert actions[0]["baseline"] == 19.2 and actions[0]["target"] == 25
    assert actions[0]["quantified_action_plan"] is False
    assert actions[0]["expected_change"] is None and actions[0]["projected_score_impact"] is None
    assert "Baseline and quantified target are required" not in actions[0]["validation"]
    assert feedback_rows[0]["status"] == "Scheduled"
    assert feedback_counts["total_required"] == 1


def test_regenerating_system_analysis_never_overwrites_management_commentary(story_db):
    session, user = story_db
    rows = [record("A", "Inbound", "May", 60), record("A", "Inbound", "June", 65)]
    result = service(session, rows)
    template = next(item for item in result.list_templates(scope(user)) if item["template_key"] == "executive_monthly_review")
    draft = result.create_draft(draft_payload(template["id"], "Commentary Review"), scope(user))
    commentary_block = next(block for page in draft["definition"]["slides"] for block in page["blocks"] if block["type"] == "management_commentary")
    commentary = ManagementCommentary(entries={commentary_block["id"]: "Management-confirmed operational context."})
    updated = result.update_draft(draft["id"], ReportDraftUpdate(expected_version=draft["version"], management_commentary=commentary), scope(user))
    from models.report_definitions import NarrativeRegenerateRequest
    regenerated = result.regenerate_narratives(draft["id"], NarrativeRegenerateRequest(expected_version=updated["version"]), scope(user))
    assert regenerated["management_commentary"]["entries"][commentary_block["id"]] == "Management-confirmed operational context."


def test_process_and_staff_providers_are_distinct_and_milestones_are_real_rows(story_db):
    session, user = story_db
    result = service(session, [])
    team = SimpleNamespace(name="Inbound", display_name="Inbound", region="EGY", team_level="employee")
    process_action = SimpleNamespace(action_type="Monitor", action_text="Fix workflow routing system", root_cause_note="Workflow routing issue", team=team)
    staff_action = SimpleNamespace(action_type="Coaching", action_text="Attendance coaching", root_cause_note="Employee attendance adherence", team=team)
    primary = (2026, 6)
    context = {"current": [], "previous": [], "all": [], "primary": primary, "comparison": (2026, 5), "actions": [process_action, staff_action], "plans": [], "uploads": []}
    context["evidence"] = result.evidence.build([], primary, context["actions"])
    block = SimpleNamespace(id="issues", type="process_issues", config=SimpleNamespace(row_limit=10))
    draft = SimpleNamespace(name="Review", definition_json={"slides": []}, management_commentary_json={})
    process_rows = result._resolve_provider("process_issues", context, block, draft).data["rows"]
    block.type = "staff_issues"
    staff_rows = result._resolve_provider("staff_issues", context, block, draft).data["rows"]
    assert {row["evidence"] for row in process_rows} != {row["evidence"] for row in staff_rows}

    owner = SimpleNamespace(username="manager")
    milestone = SimpleNamespace(name="QA review", owner=owner, due_date=date(2026, 7, 10), completion_date=None, status="In Progress")
    context["plans"] = [SimpleNamespace(name="Recovery", milestones=[milestone])]
    block.type = "milestone_overview"
    milestone_rows = result._resolve_provider("milestones", context, block, draft).data["rows"]
    assert milestone_rows[0]["milestone"] == "QA review"
    assert milestone_rows[0]["plan"] == "Recovery"
