"""Reviewer-owned public-contract probes; no production data or mocked scoring."""
import pytest
from sqlalchemy import text

from models.models import TeamConfigurationVersion
from services.evaluation.access import EvaluationError
from tests.test_evaluation_workflow_consumer import _World, db


@pytest.mark.parametrize("pinned", [False, True], ids=["legacy", "uniform-pin"])
def test_multiple_authorized_people_do_not_report_first_person_as_scope_score(db, pinned):
    world = _World(db)
    first = world.record(world.employee, "August", {}, score="70")
    second = world.record(world.colleague, "August", {}, score="88")
    if pinned:
        for record in (first, second):
            record.record_payload = {"evaluation_basis": {
                "pinned": True, "version_id": "same-saved-version",
                "lines": [{"kpi_key": "Attendance", "target": 0.65, "weight": 0.6}],
            }}
    db.commit()
    body = world.workflow.reads(world.actor, world.scope["id"], 2026, [8])["periods"][0]
    assert body["basis_state"] == ("pinned" if pinned else "legacy")
    assert body["stored_score"] is None
    assert {row["score"] for row in body["evidence"]} == {70, 88}
    period = world.workflow.period(world.actor, world.scope["id"], 2026, 8)
    assert period["stored_score"] is None
    assert period["stored_actuals"] == {}


def test_cached_active_team_cannot_grant_draft_after_database_deactivation(db):
    world = _World(db)
    assert world.team.is_active is True
    db.execute(text("UPDATE teams SET is_active = false WHERE id = :id"), {"id": world.team.id.hex})
    assert world.team.is_active is True  # ORM cache deliberately retains stale state.
    assert db.execute(text("SELECT is_active FROM teams WHERE id = :id"), {"id": world.team.id.hex}).scalar_one() == 0
    with pytest.raises(EvaluationError) as denied:
        world.workflow.open_draft(world.actor, world.scope["id"], 2026, 8)
    assert denied.value.data["code"] == "scope_blocked"
    assert db.query(TeamConfigurationVersion).count() == 0
