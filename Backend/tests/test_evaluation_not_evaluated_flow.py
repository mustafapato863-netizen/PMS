"""Not-evaluated rows through upload, impact preview, approve, apply and rollback (synthetic data only)."""
from __future__ import annotations

import copy
import io
import uuid
from datetime import datetime

import pytest
from openpyxl import Workbook
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from models.models import Employee, EvaluationRevision, PerformanceRecord, Team
from services.evaluation.access import TargetConflict  # noqa: F401  (kept for parity with the upload tests)
from services.evaluation.workflow import EvaluationError, EvaluationWorkflow
from services.seeding_service import DatabaseSeeder
from tests.test_monthly_evaluation import _actor, _coding_scope, _user, db  # noqa: F401  (fixture re-export)

HEADER = [
    "HRID", "AgentName", "Role", "Date", "Status",
    "A.QualityErrorsRate", "T.QualityErrorsRate",
    "A.RejectionRate", "T.RejectionRate",
    "A.TAT", "T.TAT",
]


def _row(hrid, status, *, quality=None, rejection=None, tat=None, month=7):
    return [
        hrid, f"Coder {hrid}", "Employee", datetime(2026, month, 15), status,
        quality, 55, rejection, 55, tat, 55,
    ]


def _workbook(rows):
    book = Workbook()
    sheet = book.active
    sheet.title = "Coding"
    sheet.append(HEADER)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _approved_july(db, monkeypatch, month: int = 7):
    """An approved 2026 Coding basis for ``month`` with fixed targets 55, as in the existing upload test."""
    monkeypatch.setattr(
        "services.seeding_service.SessionLocal",
        sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False),
    )
    admin = _user("Admin", "not-evaluated-admin")
    coding = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
    db.add_all([admin, coding])
    db.commit()
    actor = _actor(admin)
    workflow = EvaluationWorkflow(db)
    scope = _coding_scope(workflow, actor)
    draft = workflow.open_draft(actor, scope["id"], 2026, month)
    workflow.edit_draft(actor, draft["id"], [{**line, "target_mode": "fixed", "target": 55} for line in draft["lines"]])
    workflow.impact_preview(actor, draft["id"])
    workflow.approve(actor, draft["id"])
    seeder = DatabaseSeeder()
    return actor, workflow, scope, seeder


def _stored(db, employee_code, month="July"):
    return (
        db.query(PerformanceRecord)
        .join(Employee, PerformanceRecord.employee_id == Employee.id)
        .filter(Employee.employee_id == employee_code, PerformanceRecord.month == month, PerformanceRecord.year == 2026)
        .one()
    )


def _snapshot(record):
    return (
        float(record.score),
        record.grade,
        record.status,
        sorted((item.kpi_key, float(item.actual_value or 0), float(item.achievement_ratio), float(item.contribution))
               for item in record.kpi_values),
    )


MIXED = [
    _row("C-1", "Active", quality=60, rejection=55, tat=55),
    _row("C-2", "Leave"),
    _row("C-3", "Active - New"),
]


def test_approved_upload_saves_leave_and_new_rows_unscored_and_reports_them(db, monkeypatch):
    _actor_, _workflow, _scope, seeder = _approved_july(db, monkeypatch)
    book = _workbook(MIXED)

    preview = seeder.process_uploaded_file("coding-mixed.xlsx", book, dry_run=True)
    db.rollback()
    committed = seeder.process_uploaded_file("coding-mixed.xlsx", book, dry_run=False)
    db.rollback()

    assert preview["not_evaluated"] == committed["not_evaluated"]
    assert committed["not_evaluated"]["count"] == 2
    reasons = {item["employee_id"]: item["reason"] for item in committed["not_evaluated"]["rows"]}
    assert reasons == {"C-2": "Not evaluated: on leave, no actuals", "C-3": "Not evaluated: new, no actuals"}
    not_evaluated_warnings = [item for item in committed["warnings"] if item.get("code") == "not_evaluated"]
    assert len(not_evaluated_warnings) == 2
    assert preview["scored_rows"] == committed["scored_rows"]

    scored = {item["employee_id"]: item for item in committed["scored_rows"]}
    assert scored["C-2"]["rows"] == [] and "not_evaluated" in scored["C-2"]
    assert scored["C-1"]["rows"] and "not_evaluated" not in scored["C-1"]


def test_not_evaluated_rows_are_stored_unpinned_like_the_legacy_path(db, monkeypatch):
    _actor_, _workflow, _scope, seeder = _approved_july(db, monkeypatch)
    seeder.process_uploaded_file("coding-mixed.xlsx", _workbook(MIXED), dry_run=False)
    db.rollback()

    leave = _stored(db, "C-2")
    new = _stored(db, "C-3")
    scored = _stored(db, "C-1")
    assert "evaluation_basis" not in (leave.record_payload or {})
    assert "evaluation_basis" not in (new.record_payload or {})
    assert (scored.record_payload or {}).get("evaluation_basis", {}).get("pinned") is True


def test_active_row_with_a_missing_actual_still_blocks_with_todays_message(db, monkeypatch):
    _approved_july(db, monkeypatch)
    seeder = DatabaseSeeder()
    blocked = _workbook([_row("C-4", "Active", quality=None, rejection=55, tat=55)])

    for dry_run in (True, False):
        with pytest.raises(EvaluationError, match="Actual for QualityErrors is missing"):
            seeder.process_uploaded_file("coding-active-missing.xlsx", blocked, dry_run=dry_run)
        db.rollback()


def test_new_row_with_a_missing_weighted_actual_is_not_evaluated_and_does_not_block(db, monkeypatch):
    _approved_july(db, monkeypatch)
    seeder = DatabaseSeeder()
    partial = _workbook([_row("C-5", "Active - New", quality=60, rejection=None, tat=None)])

    for dry_run in (True, False):
        result = seeder.process_uploaded_file("coding-new-partial.xlsx", partial, dry_run=dry_run)
        db.rollback()
        assert result["not_evaluated"]["count"] == 1
        assert result["not_evaluated"]["rows"][0]["reason"] == "Not evaluated: new, actual missing for Rejection, TAT"


def test_the_real_new_employee_shape_uploads_as_not_evaluated_in_dry_run_and_commit(db, monkeypatch):
    # Four new rows: a real number, a dash in the rejection cell, a real number.
    _approved_july(db, monkeypatch)
    seeder = DatabaseSeeder()
    book = _workbook([_row(f"N-{index}", "Active - New", quality=0, rejection="-", tat=0.8) for index in range(4)])

    preview = seeder.process_uploaded_file("coding-new-shape.xlsx", book, dry_run=True)
    db.rollback()
    committed = seeder.process_uploaded_file("coding-new-shape.xlsx", book, dry_run=False)
    db.rollback()

    assert preview["not_evaluated"] == committed["not_evaluated"]
    assert committed["not_evaluated"]["count"] == 4
    assert {item["reason"] for item in committed["not_evaluated"]["rows"]} == {"Not evaluated: new, actual missing for Rejection"}


def test_an_all_blank_leave_row_is_not_evaluated(db, monkeypatch):
    _approved_july(db, monkeypatch)
    seeder = DatabaseSeeder()
    book = _workbook([_row("L-1", "Leave"), _row("L-2", "Leave")])

    committed = seeder.process_uploaded_file("coding-leave.xlsx", book, dry_run=False)
    db.rollback()
    assert committed["not_evaluated"]["count"] == 2
    assert {item["reason"] for item in committed["not_evaluated"]["rows"]} == {"Not evaluated: on leave, no actuals"}


def test_fully_populated_leave_and_inactive_rows_are_scored_and_pinned(db, monkeypatch):
    _approved_july(db, monkeypatch)
    seeder = DatabaseSeeder()
    book = _workbook([
        _row("L-3", "Leave", quality=60, rejection=55, tat=55),
        _row("I-1", "Inactive", quality=60, rejection=55, tat=55),
    ])

    committed = seeder.process_uploaded_file("coding-full-leave.xlsx", book, dry_run=False)
    db.rollback()
    assert committed["not_evaluated"]["count"] == 0
    assert not [item for item in committed["warnings"] if item.get("code") == "not_evaluated"]
    for code in ("L-3", "I-1"):
        assert (_stored(db, code).record_payload or {}).get("evaluation_basis", {}).get("pinned") is True


def test_active_row_with_a_dash_in_a_weighted_actual_blocks_with_the_missing_message(db, monkeypatch):
    _approved_july(db, monkeypatch)
    seeder = DatabaseSeeder()
    blocked = _workbook([_row("A-1", "Active", quality=60, rejection="-", tat=55)])

    for dry_run in (True, False):
        with pytest.raises(EvaluationError, match="Actual for Rejection is missing") as caught:
            seeder.process_uploaded_file("coding-active-dash.xlsx", blocked, dry_run=dry_run)
        assert caught.value.data["code"] == "missing_actual"
        db.rollback()


def test_active_row_with_malformed_text_still_raises_invalid_evidence(db, monkeypatch):
    _approved_july(db, monkeypatch)
    seeder = DatabaseSeeder()
    malformed = _workbook([_row("A-2", "Active", quality="12abc", rejection=55, tat=55)])

    for dry_run in (True, False):
        with pytest.raises(EvaluationError) as caught:
            seeder.process_uploaded_file("coding-malformed.xlsx", malformed, dry_run=dry_run)
        assert caught.value.data["code"] == "invalid_evidence"
        db.rollback()


def test_upload_for_a_month_without_an_approved_version_is_unchanged(db, monkeypatch):
    monkeypatch.setattr(
        "services.seeding_service.SessionLocal",
        sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False),
    )
    db.add(Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee"))
    db.commit()
    seeder = DatabaseSeeder()

    result = seeder.process_uploaded_file("coding-august.xlsx", _workbook([_row("C-2", "Leave", month=8)]), dry_run=False)
    db.rollback()

    assert result["not_evaluated"] == {"count": 0, "rows": []}
    assert not [item for item in result["warnings"] if item.get("code") == "not_evaluated"]


def test_impact_preview_apply_and_rollback_leave_not_evaluated_rows_untouched(db, monkeypatch):
    monkeypatch.setattr(
        "services.seeding_service.SessionLocal",
        sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False),
    )
    admin = _user("Admin", "not-evaluated-correction")
    coding = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
    db.add_all([admin, coding])
    db.commit()
    actor = _actor(admin)
    workflow = EvaluationWorkflow(db)
    scope = _coding_scope(workflow, actor)
    seeder = DatabaseSeeder()
    # Stored before approval: the legacy upload saves all three rows.
    seeder.process_uploaded_file("coding-stored.xlsx", _workbook(MIXED), dry_run=False)
    db.rollback()
    before = {code: _snapshot(_stored(db, code)) for code in ("C-1", "C-2", "C-3")}

    draft = workflow.open_draft(actor, scope["id"], 2026, 7)
    workflow.edit_draft(actor, draft["id"], [{**line, "target_mode": "fixed", "target": 55} for line in draft["lines"]])
    proof = workflow.impact_preview(actor, draft["id"])
    assert proof["not_evaluated_count"] == 2
    assert {item["employee_code"] for item in proof["not_evaluated"]} == {"C-2", "C-3"}
    assert proof["missing_evidence"] == []
    workflow.approve(actor, draft["id"])

    workflow.apply(actor, scope["id"], 2026, 7)
    db.expire_all()
    revision = db.query(EvaluationRevision).filter(
        EvaluationRevision.year == 2026,
        EvaluationRevision.month == 7,
        EvaluationRevision.status == "active",
    ).one()
    assert _snapshot(_stored(db, "C-2")) == before["C-2"]
    assert _snapshot(_stored(db, "C-3")) == before["C-3"]
    assert _snapshot(_stored(db, "C-1")) != before["C-1"]

    workflow.rollback(actor, revision.id)
    db.expire_all()
    assert _snapshot(_stored(db, "C-1")) == before["C-1"]
    assert _snapshot(_stored(db, "C-2")) == before["C-2"]
    assert _snapshot(_stored(db, "C-3")) == before["C-3"]


def test_the_gate_still_fails_for_an_evaluated_row_with_a_missing_actual(db, monkeypatch):
    monkeypatch.setattr(
        "services.seeding_service.SessionLocal",
        sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False),
    )
    admin = _user("Admin", "not-evaluated-gate")
    coding = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
    db.add_all([admin, coding])
    db.commit()
    actor = _actor(admin)
    workflow = EvaluationWorkflow(db)
    scope = _coding_scope(workflow, actor)
    seeder = DatabaseSeeder()
    seeder.process_uploaded_file(
        "coding-gate.xlsx",
        _workbook(MIXED + [_row("C-4", "Active", quality=None, rejection=55, tat=55)]),
        dry_run=False,
    )
    db.rollback()
    draft = workflow.open_draft(actor, scope["id"], 2026, 7)
    workflow.edit_draft(actor, draft["id"], [{**line, "target_mode": "fixed", "target": 55} for line in draft["lines"]])
    with pytest.raises(EvaluationError) as caught:
        workflow.impact_preview(actor, draft["id"])
    assert caught.value.data["code"] == "missing_evidence"


def test_a_stored_row_with_no_status_evidence_and_no_actual_stays_missing_evidence(db, monkeypatch):
    monkeypatch.setattr(
        "services.seeding_service.SessionLocal",
        sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False),
    )
    admin = _user("Admin", "not-evaluated-no-status")
    coding = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
    db.add_all([admin, coding])
    db.commit()
    actor = _actor(admin)
    workflow = EvaluationWorkflow(db)
    scope = _coding_scope(workflow, actor)
    seeder = DatabaseSeeder()
    seeder.process_uploaded_file(
        "coding-no-status.xlsx",
        _workbook([_row("C-6", None, quality=None, rejection=None, tat=None), _row("C-7", "Active", quality=60, rejection=55, tat=55)]),
        dry_run=False,
    )
    db.rollback()
    draft = workflow.open_draft(actor, scope["id"], 2026, 7)
    workflow.edit_draft(actor, draft["id"], [{**line, "target_mode": "fixed", "target": 55} for line in draft["lines"]])
    with pytest.raises(EvaluationError) as caught:
        workflow.impact_preview(actor, draft["id"])
    assert caught.value.data["code"] == "missing_evidence"


def _stored_payload_edit(db, employee_code, cells):
    """Replace KPI actual cells in a stored record's workbook row (the legacy-stored payload)."""
    record = _stored(db, employee_code)
    payload = copy.deepcopy(record.record_payload)
    payload["raw_data"].update(cells)
    record.record_payload = payload
    flag_modified(record, "record_payload")
    db.commit()


def _stored_coding_month(db, monkeypatch, rows):
    """Legacy-store Coding July rows before any approval, as an earlier upload did."""
    monkeypatch.setattr(
        "services.seeding_service.SessionLocal",
        sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False),
    )
    admin = _user("Admin", "not-evaluated-stored")
    coding = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
    db.add_all([admin, coding])
    db.commit()
    actor = _actor(admin)
    workflow = EvaluationWorkflow(db)
    scope = _coding_scope(workflow, actor)
    seeder = DatabaseSeeder()
    seeder.process_uploaded_file("coding-stored-markers.xlsx", _workbook(rows), dry_run=False)
    db.rollback()
    return actor, workflow, scope


ACTUAL_CELLS = ("A.QualityErrorsRate", "A.RejectionRate", "A.TAT")


def test_stored_not_evaluated_rows_with_a_dash_and_nan_go_through_preview_approve_apply_and_rollback(db, monkeypatch):
    actor, workflow, scope = _stored_coding_month(db, monkeypatch, [
        _row("C-1", "Active", quality=60, rejection=55, tat=55),
        _row("C-2", "Active - New", quality=0, rejection="-", tat=0.8),
        _row("C-3", "Leave"),
    ])
    # The Leave row's stored payload holds float NaN, the other form a blank cell takes in a stored record.
    _stored_payload_edit(db, "C-3", {cell: float("nan") for cell in ACTUAL_CELLS})
    before = {code: _snapshot(_stored(db, code)) for code in ("C-1", "C-2", "C-3")}

    draft = workflow.open_draft(actor, scope["id"], 2026, 7)
    workflow.edit_draft(actor, draft["id"], [{**line, "target_mode": "fixed", "target": 55} for line in draft["lines"]])
    proof = workflow.impact_preview(actor, draft["id"])
    assert proof["not_evaluated_count"] == 2
    assert {item["employee_code"]: item["reason"] for item in proof["not_evaluated"]} == {
        "C-2": "Not evaluated: new, actual missing for Rejection",
        "C-3": "Not evaluated: on leave, no actuals",
    }
    workflow.approve(actor, draft["id"])

    workflow.apply(actor, scope["id"], 2026, 7)
    db.expire_all()
    assert _snapshot(_stored(db, "C-2")) == before["C-2"]
    assert _snapshot(_stored(db, "C-3")) == before["C-3"]
    assert _snapshot(_stored(db, "C-1")) != before["C-1"]

    revision = db.query(EvaluationRevision).filter(
        EvaluationRevision.year == 2026, EvaluationRevision.month == 7, EvaluationRevision.status == "active",
    ).one()
    workflow.rollback(actor, revision.id)
    db.expire_all()
    assert _snapshot(_stored(db, "C-1")) == before["C-1"]
    assert _snapshot(_stored(db, "C-2")) == before["C-2"]
    assert _snapshot(_stored(db, "C-3")) == before["C-3"]


def test_a_stored_active_row_with_a_dash_still_blocks_the_preview(db, monkeypatch):
    actor, workflow, scope = _stored_coding_month(db, monkeypatch, [
        _row("C-4", "Active", quality=60, rejection="-", tat=55),
    ])
    draft = workflow.open_draft(actor, scope["id"], 2026, 7)
    workflow.edit_draft(actor, draft["id"], [{**line, "target_mode": "fixed", "target": 55} for line in draft["lines"]])
    with pytest.raises(EvaluationError) as caught:
        workflow.impact_preview(actor, draft["id"])
    assert caught.value.data["code"] == "missing_evidence"


def test_a_stored_active_row_with_a_nan_actual_still_blocks_the_preview(db, monkeypatch):
    actor, workflow, scope = _stored_coding_month(db, monkeypatch, [
        _row("C-5", "Active", quality=60, rejection=55, tat=55),
    ])
    _stored_payload_edit(db, "C-5", {"A.RejectionRate": float("nan")})
    draft = workflow.open_draft(actor, scope["id"], 2026, 7)
    workflow.edit_draft(actor, draft["id"], [{**line, "target_mode": "fixed", "target": 55} for line in draft["lines"]])
    with pytest.raises(EvaluationError) as caught:
        workflow.impact_preview(actor, draft["id"])
    assert caught.value.data["code"] == "missing_evidence"


def test_reupload_of_stored_rows_after_approval_skips_not_evaluated_rows(db, monkeypatch):
    # Stored before approval; the approved month is then re-uploaded over the same rows.
    actor, workflow, scope = _stored_coding_month(db, monkeypatch, MIXED + [_row("C-6", "Active - New", quality=0, rejection="-", tat=0.8)])
    draft = workflow.open_draft(actor, scope["id"], 2026, 7)
    workflow.edit_draft(actor, draft["id"], [{**line, "target_mode": "fixed", "target": 55} for line in draft["lines"]])
    workflow.impact_preview(actor, draft["id"])
    workflow.approve(actor, draft["id"])
    seeder = DatabaseSeeder()
    before = {code: _snapshot(_stored(db, code)) for code in ("C-2", "C-3", "C-6")}

    result = seeder.process_uploaded_file("coding-reupload.xlsx", _workbook(MIXED + [_row("C-6", "Active - New", quality=0, rejection="-", tat=0.8)]), dry_run=False)
    db.rollback()

    assert result["not_evaluated"]["count"] == 3
    assert _snapshot(_stored(db, "C-2")) == before["C-2"]
    assert _snapshot(_stored(db, "C-3")) == before["C-3"]
    assert _snapshot(_stored(db, "C-6")) == before["C-6"]


def test_rescore_uploaded_leaves_a_not_evaluated_record_unpinned_and_pins_an_evaluated_one(db, monkeypatch):
    actor, workflow, scope = _stored_coding_month(db, monkeypatch, MIXED)
    draft = workflow.open_draft(actor, scope["id"], 2026, 7)
    workflow.edit_draft(actor, draft["id"], [{**line, "target_mode": "fixed", "target": 55} for line in draft["lines"]])
    workflow.impact_preview(actor, draft["id"])
    workflow.approve(actor, draft["id"])

    leave = _stored(db, "C-3")
    team = db.get(Team, leave.team_id)
    before_payload = copy.deepcopy(leave.record_payload)
    before_kpis = [(value.kpi_key, value.target_value, value.weight_applied, value.contribution) for value in leave.kpi_values]
    workflow.rescore_uploaded(leave, team, list(leave.kpi_values), 0)
    assert leave.record_payload == before_payload
    assert [(value.kpi_key, value.target_value, value.weight_applied, value.contribution) for value in leave.kpi_values] == before_kpis

    evaluated = _stored(db, "C-1")
    workflow.rescore_uploaded(evaluated, team, list(evaluated.kpi_values), 0)
    assert (evaluated.record_payload or {}).get("evaluation_basis", {}).get("pinned") is True


def test_the_real_august_shape_uploads_under_an_approved_month_with_six_rows_not_evaluated(db, monkeypatch):
    # Shape of the business workbook (counts only, synthetic ids): 4 new partial, 2 blank leave,
    # 1 populated leave, 1 populated inactive, 22 active with all actuals.
    _approved_july(db, monkeypatch, month=8)
    seeder = DatabaseSeeder()
    rows = [_row(f"N-{index}", "Active - New", quality=0, rejection="-", tat=0.8, month=8) for index in range(4)]
    rows += [_row(f"L-{index}", "Leave", month=8) for index in range(2)]
    rows += [_row("L-full", "Leave", quality=0.9, rejection=0.02, tat=0.95, month=8)]
    rows += [_row("I-full", "Inactive", quality=0.9, rejection=0.02, tat=0.95, month=8)]
    rows += [_row(f"A-{index}", "Active", quality=0.9, rejection=0.02, tat=0.95, month=8) for index in range(22)]
    book = _workbook(rows)

    preview = seeder.process_uploaded_file("coding-august-shape.xlsx", book, dry_run=True)
    db.rollback()
    committed = seeder.process_uploaded_file("coding-august-shape.xlsx", book, dry_run=False)
    db.rollback()

    assert preview["not_evaluated"] == committed["not_evaluated"]
    assert committed["not_evaluated"]["count"] == 6
    reported = {item["employee_id"] for item in committed["not_evaluated"]["rows"]}
    assert reported == {"N-0", "N-1", "N-2", "N-3", "L-0", "L-1"}
    assert len(committed["scored_rows"]) == len(rows)
