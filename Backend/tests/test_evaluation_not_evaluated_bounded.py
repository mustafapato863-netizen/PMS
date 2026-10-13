"""Bounded apply with not-evaluated rows: staged as unchanged, never written, never rolled back (synthetic data only)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from models.models import Employee, EvaluationApplyStageRow, EvaluationRevision, KPIValue, PerformanceRecord
from services.evaluation.workflow import EvaluationError
from tests.test_evaluation_bounded_apply import _approve, _code, _live, _World, _stage_all, db  # noqa: F401  (fixture re-export)

KEYS = {"QualityErrors": "A.QualityErrorsRate", "Rejection": "A.RejectionRate", "TAT": "A.TAT"}


def _record(world, team, employee_code, status, *, actuals, score="70.00", grade="D"):
    raw = {"HRID": employee_code, "AgentName": employee_code, "Status": status, "Date": "2026-07-15"}
    for key, column in KEYS.items():
        raw[column] = actuals.get(key)
        raw[column.replace("A.", "T.", 1)] = 55.0  # the workbook carries the target beside each actual
    employee = Employee(
        id=uuid.uuid4(), employee_id=employee_code, name=employee_code,
        team_id=team.id, region="UAE", performance_level="Employee",
    )
    world.db.add(employee)
    world.db.flush()
    record = PerformanceRecord(
        id=uuid.uuid4(), year=2026, employee_id=employee.id, team_id=team.id, month="July",
        performance_level="Employee", position_name="", region="UAE", branch_key="dubai",
        score=Decimal(score), grade=grade, status="Below", uploaded_at=world.uploaded_at,
        record_payload={"raw_data": raw, "evaluation": {"score": float(score), "grade": grade}, "manager_notes": "keep"},
    )
    world.db.add(record)
    world.db.flush()
    for key in KEYS:
        world.db.add(KPIValue(
            id=uuid.uuid4(), record_id=record.id, record_year=2026, kpi_key=key,
            actual_value=Decimal(str(actuals.get(key) or 0)), target_value=Decimal("40"),
            achievement_ratio=Decimal("1"), weight_applied=Decimal("1"), contribution=Decimal("1"),
        ))
    world.db.flush()
    return record


def _full():
    return {"QualityErrors": 60.0, "Rejection": 55.0, "TAT": 55.0}


def _empty():
    return {"QualityErrors": None, "Rejection": None, "TAT": None}


def _built(db, rows):
    world = _World(db)
    scope = world.scope("Coding")
    # All three Coding KPIs carry weight, as in the checked-in file (0.2 / 0.5 / 0.3).
    opened = world.workflow.open_draft(world.actor, scope["id"], 2026, 7)
    weighted = [
        {**line, "weight": weight, "direction": "lower_better", "target_mode": "fixed", "target": 50}
        for line, weight in zip(opened["lines"], (0.2, 0.5, 0.3))
    ]
    draft = world.workflow.edit_draft(world.actor, opened["id"], weighted)
    team = world.teams["Coding"]
    records = {code: _record(world, team, code, status, actuals=actuals) for code, status, actuals in rows}
    db.commit()
    _approve(world.workflow, world.actor, draft["id"])
    return world, scope, records


def _state(record):
    return (
        float(record.score),
        record.grade,
        sorted((item.kpi_key, float(item.actual_value), float(item.achievement_ratio), float(item.contribution))
               for item in record.kpi_values),
    )


def test_bounded_apply_writes_only_evaluated_rows_and_rollback_restores_only_them(db):
    world, scope, records = _built(db, [
        ("C-1", "Active", _full()),
        ("C-2", "Leave", _empty()),
        ("C-3", "Active - New", _empty()),
    ])
    db.expire_all()
    before = {code: _state(db.get(PerformanceRecord, (record.id, 2026))) for code, record in records.items()}

    captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    assert captured["expected_count"] == 3
    _stage_all(world.service, world.actor, captured["job_id"], 3, page_size=100)
    staged = {row.record_id: row.after_row for row in db.query(EvaluationApplyStageRow).filter(
        EvaluationApplyStageRow.job_id == uuid.UUID(str(captured["job_id"])),
    )}
    assert staged[records["C-2"].id].get("not_evaluated") == "Not evaluated: on leave, no actuals"
    assert staged[records["C-3"].id].get("not_evaluated") == "Not evaluated: new, no actuals"
    assert staged[records["C-1"].id].get("not_evaluated") is None
    promoted = world.service.promote(world.actor, captured["job_id"])
    db.expire_all()

    assert _state(db.get(PerformanceRecord, (records["C-2"].id, 2026))) == before["C-2"]
    assert _state(db.get(PerformanceRecord, (records["C-3"].id, 2026))) == before["C-3"]
    assert _state(db.get(PerformanceRecord, (records["C-1"].id, 2026))) != before["C-1"]

    world.service.rollback_latest(world.actor, promoted["revision_id"])
    db.expire_all()
    assert _state(db.get(PerformanceRecord, (records["C-1"].id, 2026))) == before["C-1"]
    assert _state(db.get(PerformanceRecord, (records["C-2"].id, 2026))) == before["C-2"]
    assert _state(db.get(PerformanceRecord, (records["C-3"].id, 2026))) == before["C-3"]
    assert db.query(EvaluationRevision).filter(EvaluationRevision.status == "active").count() == 0
