"""Independent regression probes for monthly management guards and lineage."""
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import update

from models.models import User
from services.evaluation.access import AccessDenied, EvaluationError
from services.evaluation.workflow import EvaluationConflict, _latest_revision
from test_evaluation_month_revision import _World, db  # noqa: F401


def test_disabled_admin_cannot_manage_monthly_settings(db):
    world = _World(db)
    admin = db.query(User).filter(User.id == uuid.UUID(world.actor["user_id"])).one()
    admin.is_active = False
    db.commit()
    with pytest.raises(AccessDenied):
        world.workflow.sync_catalog(world.actor)


def test_reused_session_does_not_accept_a_cached_admin_role(db):
    world = _World(db)
    db.expire_on_commit = False
    cached = db.query(User).filter(User.id == uuid.UUID(world.actor["user_id"])).one()
    db.execute(update(User).where(User.id == cached.id).values(role="Manager").execution_options(synchronize_session=False))
    db.commit()
    assert cached.role == "Admin"
    with pytest.raises(AccessDenied):
        world.workflow.sync_catalog(world.actor)


def test_duplicate_draft_kpi_keys_are_rejected_before_persistence(db):
    world = _World(db)
    line = {
        "kpi_key": "one", "weight": 1, "direction": "higher_better",
        "target_mode": "fixed", "target": 1,
    }
    proposed = [{**line, "weight": 0.5}, {**line, "weight": 0.5}]
    with pytest.raises(EvaluationError) as rejected:
        world.workflow._validate_lines([line], proposed)
    assert rejected.value.data["code"] == "duplicate_kpi"


def test_revision_head_uses_lineage_not_timestamp_or_random_id():
    older = SimpleNamespace(id=uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
                            previous_revision_id=None, created_at=None)
    newer = SimpleNamespace(id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                            previous_revision_id=older.id, created_at=None)
    assert _latest_revision([newer, older]) is newer


def test_broken_or_forked_revision_chains_are_not_guessed():
    root = SimpleNamespace(id=uuid.uuid4(), previous_revision_id=None, created_at=None)
    branch = SimpleNamespace(id=uuid.uuid4(), previous_revision_id=None, created_at=None)
    with pytest.raises(EvaluationConflict):
        _latest_revision([root, branch])
    root.previous_revision_id = uuid.uuid4()
    with pytest.raises(EvaluationConflict):
        _latest_revision([root])
    root.previous_revision_id = branch.id
    branch.previous_revision_id = root.id
    with pytest.raises(EvaluationConflict):
        _latest_revision([root, branch])
