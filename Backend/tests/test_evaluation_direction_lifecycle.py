"""Anonymous exact-month direction correction; no new family admission."""
from decimal import Decimal
import uuid

import pytest

from models.models import PerformanceRecord, TeamConfigurationVersion
from services.dashboard_record_service import DashboardRecordService
from services.evaluation.workflow import EvaluationConflict
from tests.test_evaluation_month_revision import (
    _World, _approve, _freeze, _line_edit, db,
)


def _stored(world, record_id):
    return world.db.query(PerformanceRecord).populate_existing().filter(
        PerformanceRecord.id == record_id, PerformanceRecord.year == 2026,
    ).one()


def _resolved(world, record_id):
    return DashboardRecordService(world.db).resolve_records([_stored(world, record_id)])[0]


def test_direction_revision_requires_apply_and_restores_the_pinned_basis(db):
    world = _World(db)
    draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 8)
    lines = _line_edit(draft["lines"], 65)
    key = lines[0]["kpi_key"]
    lines[0]["direction"] = "lower_better"
    edited = world.workflow.edit_draft(world.actor, draft["id"], lines)
    august = world.record(world.employee_a, "August", "70", "D")
    july = world.record(world.employee_a, "July", "88", "B")
    world.kpi(august, key, 90, 65)
    world.kpi(july, key, 60, 65)
    db.commit()
    august_id, july_id = august.id, july.id
    before_payload = _freeze(august.record_payload)
    _approve(world.workflow, world.actor, edited["id"])
    assert _stored(world, august_id).score == Decimal("70")
    assert _freeze(_stored(world, august_id).record_payload) == before_payload

    applied_lower = world.workflow.apply(world.actor, world.scope["id"], 2026, 8)
    resolved_lower = _resolved(world, august_id)
    assert resolved_lower.evaluation.score == pytest.approx(72.22)
    assert resolved_lower.evaluation.grade == "D"
    lower_kpi = next(item for item in resolved_lower.kpi_values if item["kpi_key"] == key)
    assert lower_kpi["direction"] == "lower_better"
    assert lower_kpi["actual_value"] == 90
    assert lower_kpi["target_value"] == 65
    assert lower_kpi["achievement_ratio"] == pytest.approx(.7222)
    assert _stored(world, july_id).score == Decimal("88")
    pinned_lower = _freeze(_stored(world, august_id).record_payload)
    original = db.get(TeamConfigurationVersion, uuid.UUID(edited["id"]))
    original_checksum = original.config_checksum
    original_rules = _freeze(original.config_snapshot)

    revised = world.workflow.revise(world.actor, edited["id"])
    higher_lines = [dict(line) for line in revised["lines"]]
    higher_lines[0]["direction"] = "higher_better"
    world.workflow.edit_draft(world.actor, revised["id"], higher_lines)
    _approve(world.workflow, world.actor, revised["id"])
    assert _stored(world, august_id).score == Decimal("72.22")
    assert _freeze(_stored(world, august_id).record_payload) == pinned_lower
    applied_higher = world.workflow.apply(world.actor, world.scope["id"], 2026, 8)
    resolved_higher = _resolved(world, august_id)
    assert resolved_higher.evaluation.score == 100
    assert next(item for item in resolved_higher.kpi_values if item["kpi_key"] == key)["direction"] == "higher_better"
    with pytest.raises(EvaluationConflict) as older:
        world.workflow.rollback(world.actor, applied_lower["revision_id"])
    assert older.value.data["code"] == "not_latest"

    world.workflow.rollback(world.actor, applied_higher["revision_id"])
    restored = _resolved(world, august_id)
    assert restored.evaluation.score == pytest.approx(72.22)
    assert next(item for item in restored.kpi_values if item["kpi_key"] == key)["direction"] == "lower_better"
    assert _freeze(_stored(world, august_id).record_payload) == pinned_lower
    assert _stored(world, july_id).score == Decimal("88")
    db.refresh(original)
    assert original.config_checksum == original_checksum
    assert _freeze(original.config_snapshot) == original_rules
    assert original.status == "superseded", "Rollback must not reactivate an old approval"
