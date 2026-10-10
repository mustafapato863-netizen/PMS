"""Anonymous SQLite characterization for the dormant bounded apply service.

The service is not dispatched, routed, or flagged on. These tests use the
proven Coding, Submission, and Outbound July/August 2026 ratio math. They do
not open a private workbook and they do not change the known Marketing
131-versus-68 expectation.
"""

from __future__ import annotations

import gc
import hashlib
import inspect
import json
import logging
import tracemalloc
import uuid
import warnings
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.pool import StaticPool

from api.routers.evaluation_settings import router as evaluation_router
from models.models import (
    Action,
    Base,
    CacheInvalidationOutbox,
    Employee,
    EvaluationApplyControl,
    EvaluationApplyStageRow,
    EvaluationRevision,
    EvaluationScope,
    GeneratedReport,
    KPIValue,
    PerformancePlan,
    PerformanceRecord,
    ProcessingJob,
    Team,
    TeamConfigurationVersion,
    UploadLog,
    User,
)
from services.evaluation.access import AccessDenied, TargetConflict
from services.evaluation.apply_job_schema import canonical_json_text, canonical_row_hash, cache_dedup_key
import services.evaluation.bounded_apply as bounded_apply_module
import services.evaluation.workflow as workflow_module
from services.evaluation.bounded_apply import (
    FAULT_POINTS,
    MANIFEST_SCHEMA,
    BoundedApplyService,
    StreamingChecksum,
    applied_count,
    classify_snapshot,
)
from services.evaluation.resolver import score_basis
from services.evaluation.scoring import ENGINE_VERSION
from services.evaluation.workflow import (
    EvaluationConflict,
    EvaluationError,
    EvaluationWorkflow,
    _checksum,
    _json_default,
    _source_fingerprint,
)
from services.outbound_period_basis import SOURCE_TARGETS
from services.processing_job_service import JOB_KINDS, ProcessingJobService


PUBLIC_ROUTES = {
    ("GET", "/catalog"),
    ("POST", "/drafts"),
    ("PATCH", "/drafts/{version_id}"),
    ("POST", "/drafts/{version_id}/preview"),
    ("POST", "/drafts/{version_id}/impact-preview"),
    ("POST", "/drafts/{version_id}/approve"),
    ("POST", "/jobs/{version_id}/preview"),
    ("POST", "/versions/{version_id}/revise"),
    ("GET", "/versions/{version_id}"),
    ("GET", "/versions/{version_id}/export"),
    ("GET", "/periods"),
    ("GET", "/reads"),
    ("POST", "/apply"),
    ("POST", "/revisions/{revision_id}/rollback"),
    ("GET", "/apply-jobs/capabilities"),
    ("GET", "/apply-jobs"),
    ("POST", "/apply-jobs"),
    ("GET", "/apply-jobs/{job_id}"),
    ("POST", "/apply-jobs/{job_id}/cancel"),
    ("POST", "/apply-jobs/{job_id}/retry"),
    ("POST", "/apply-jobs/{job_id}/recover"),
}


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda self, kind: None)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _code(caught) -> str:
    return caught.value.data["code"]


def _persisted(db) -> bool:
    """True when the pending write commits. Foundation immutability aborts return False."""
    try:
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        message = str(exc).lower()
        assert "immutable" in message or "abort" in message
        return False


def _performance(db, record_id, year: int) -> PerformanceRecord:
    return (
        db.query(PerformanceRecord)
        .options(selectinload(PerformanceRecord.kpi_values), selectinload(PerformanceRecord.employee))
        .filter(PerformanceRecord.id == record_id, PerformanceRecord.year == year)
        .one()
    )


def _user(role: str, name: str) -> User:
    suffix = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        full_name=name,
        username=f"{name}-{suffix}",
        email=f"{name}-{suffix}@example.com",
        password_hash="test-hash",
        role=role,
        is_active=True,
    )


def _actor(user: User) -> dict:
    return {
        "user_id": str(user.id),
        "role": user.role,
        "employee_id": user.employee_id or "",
        "accessible_teams": [],
        "accessible_functions": [],
        "accessible_regions": [],
        "accessible_branches": [],
        "has_unrestricted_team_access": user.role == "Admin",
        "legacy_unscoped": False,
    }


def _line_edit(lines: list[dict], target: float) -> list[dict]:
    edited = []
    for index, line in enumerate(lines):
        edited.append({
            **line,
            "weight": 1 if index == 0 else 0,
            "direction": "higher_better",
            "target_mode": "fixed",
            "target": target if index == 0 else 1,
        })
    return edited


def _approve(workflow: EvaluationWorkflow, actor: dict, version_id: str) -> dict:
    workflow.impact_preview(actor, version_id)
    return workflow.approve(actor, version_id)


def _stage_all(service: BoundedApplyService, actor: dict, job_id: str, expected: int, page_size: int = 100) -> list[dict]:
    pages = []
    while len(pages) <= expected + 2:
        page = service.stage_page(actor, job_id, page_size=page_size)
        pages.append(page)
        if page["complete"]:
            break
    else:
        raise AssertionError(f"staging did not finish at {expected} rows")
    assert pages[-1]["staged_count"] == expected
    assert sum(page["inserted_count"] for page in pages) == expected
    return pages


def _live(session) -> tuple:
    rows = (
        session.query(PerformanceRecord)
        .options(selectinload(PerformanceRecord.kpi_values))
        .order_by(PerformanceRecord.year.asc(), PerformanceRecord.id.asc())
        .all()
    )
    body = []
    for row in rows:
        kpis = tuple(sorted(
            (
                value.kpi_key,
                str(value.actual_value),
                str(value.target_value),
                str(value.achievement_ratio),
                str(value.weight_applied),
                str(value.contribution),
            )
            for value in row.kpi_values
        ))
        payload = json.dumps(row.record_payload, sort_keys=True, default=str) if row.record_payload is not None else None
        body.append((str(row.id), int(row.year), str(row.month), str(row.score), row.grade, row.status, kpis, payload))
    return tuple(body)


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class _World:
    def __init__(self, session, teams=("Coding",)):
        self.db = session
        self.admin = _user("Admin", "bounded-admin")
        self.manager = _user("Manager", "bounded-manager")
        self.teams = {}
        for name in teams:
            self.teams[name] = Team(
                id=uuid.uuid4(),
                name=name,
                db_name=name,
                display_name=name,
                region="UAE",
                team_level="employee",
                is_active=True,
            )
        self.uploaded_at = datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc)
        session.add_all([self.admin, self.manager, *self.teams.values()])
        session.commit()
        self.admin_id = self.admin.id
        self.manager_id = self.manager.id
        self.team_ids = {name: row.id for name, row in self.teams.items()}
        self.actor = _actor(self.admin)
        self.workflow = EvaluationWorkflow(session)
        self.catalog = self.workflow.sync_catalog(self.actor)
        self.service = BoundedApplyService(session)

    def scope(self, name: str, level: str = "Employee", position: str = "") -> dict:
        return next(
            item for item in self.catalog["scopes"]
            if item["display_name"].casefold() == name.casefold()
            and item["performance_level"] == level
            and item["position_name"] == position
        )

    def upload_for(self, team: Team, month: str, year: int = 2026) -> UploadLog:
        row = UploadLog(
            id=uuid.uuid4(),
            team_id=team.id,
            month=month,
            year=year,
            record_count=1,
            status="completed",
            uploaded_at=self.uploaded_at,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def employee(self, team: Team, code: str, name: str, level: str = "Employee") -> Employee:
        row = Employee(
            id=uuid.uuid4(),
            employee_id=code,
            name=name,
            team=team,
            region="UAE",
            performance_level=level,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def record(
        self,
        employee: Employee,
        month: str,
        score: str,
        grade: str,
        *,
        team: Team | None = None,
        level: str = "Employee",
        position: str = "",
        year: int = 2026,
        record_id=None,
        payload=None,
        upload: UploadLog | None = None,
    ) -> PerformanceRecord:
        team = team or employee.team
        row = PerformanceRecord(
            id=record_id or uuid.uuid4(),
            year=year,
            employee_id=employee.id,
            team_id=team.id,
            month=month,
            performance_level=level,
            position_name=position,
            region="UAE",
            branch_key="dubai",
            score=Decimal(score),
            grade=grade,
            status="Below",
            upload_id=None if upload is None else upload.id,
            uploaded_at=self.uploaded_at,
            record_payload=payload or {
                "manager_notes": f"keep {month}",
                "evaluation": {"score": float(score), "grade": grade},
            },
        )
        self.db.add(row)
        self.db.flush()
        return row

    def kpi(self, record: PerformanceRecord, key: str, actual, target) -> KPIValue:
        row = KPIValue(
            id=uuid.uuid4(),
            record_id=record.id,
            record_year=record.year,
            kpi_key=key,
            actual_value=Decimal(str(actual)),
            target_value=Decimal(str(target)),
            achievement_ratio=Decimal("1"),
            weight_applied=Decimal("1"),
            contribution=Decimal("1"),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def ratio_draft(self, scope_id: str, month: int, target: float = 50) -> dict:
        draft = self.workflow.open_draft(self.actor, scope_id, 2026, month)
        return self.workflow.edit_draft(self.actor, draft["id"], _line_edit(draft["lines"], target))

    def protect(self, team: Team) -> dict:
        plan = PerformancePlan(
            id=uuid.uuid4(),
            name="July coaching plan",
            scope_type="Team",
            team_id=team.id,
            performance_level="Employee",
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 31),
            due_date=date(2026, 7, 31),
            owner_user_id=self.admin.id,
            baseline_value=1,
            target_value=10,
            outcome_unit="%",
            outcome_direction="higher_better",
            status="Draft",
        )
        action = Action(
            id=uuid.uuid4(),
            team_id=team.id,
            month="July",
            year=2026,
            action_type="Coaching",
            action_text="Coach the queue",
            status="Open",
        )
        report = GeneratedReport(
            id=uuid.uuid4(),
            name="July pack",
            report_type="team",
            scope_summary=team.display_name,
            period_label="July 2026",
            created_by_name="bounded-admin",
            output_format="pdf",
            status="ready",
            file_name="july.pdf",
            content_type="application/pdf",
            file_data=b"saved-report-bytes",
            configuration={},
            scope_json={},
            final_definition_json={},
            narrative_snapshot_json={"text": "original narrative"},
            data_snapshot_json={"score": 70},
            validation_json={},
        )
        self.db.add_all([plan, action, report])
        self.db.commit()
        return self.workflow.protected_texts()


def _prepared_ratio(world: _World, name: str, month: int, people: list[tuple[str, str, str]]) -> dict:
    """Approve one weighted KPI. ``people`` is (code, name, actual). Workbook target stays 40."""
    team = world.teams[name]
    scope = world.scope(name)
    draft = world.ratio_draft(scope["id"], month, 50)
    key = draft["lines"][0]["kpi_key"]
    month_name = {7: "July", 8: "August"}[month]
    upload = world.upload_for(team, month_name)
    for code, person, actual in people:
        employee = world.employee(team, code, person)
        record = world.record(employee, month_name, "70.00", "D", upload=upload)
        world.kpi(record, key, actual, "40")
    world.db.commit()
    approved = _approve(world.workflow, world.actor, draft["id"])
    return {"scope": scope, "draft": draft, "approved": approved, "key": key}


def test_streaming_hash_matches_legacy_ascii_and_not_the_row_hash():
    moment = datetime(2026, 7, 4, 1, 2, 3, tzinfo=timezone.utc)
    first_id = str(uuid.UUID(int=1))
    second_id = str(uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"))
    items = [
        {
            "id": second_id,
            "year": 2026,
            "label": "café — naïve",
            "note": None,
            "amount": Decimal("-0.000"),
            "uploaded_at": moment,
            "payload": {"raw": None, "rate": "10.50", "label": "café"},
        },
        {
            "id": first_id,
            "year": 2026,
            "label": "plain",
            "note": None,
            "amount": Decimal("0.6500"),
            "uploaded_at": moment,
            "payload": {"raw": {"missing": None}, "rate": "0.6500"},
        },
    ]
    ordered = sorted(items, key=lambda item: (item["id"], item["year"]))
    digest = StreamingChecksum()
    for item in ordered:
        digest.add(item)
    assert digest.hexdigest() == _checksum(ordered)
    reversed_digest = StreamingChecksum()
    for item in reversed(ordered):
        reversed_digest.add(item)
    assert reversed_digest.hexdigest() != digest.hexdigest()
    native = {"label": "café", "note": None, "rate": "0.65", "raw": {"x": None}}
    canonical = canonical_json_text(native)
    ascii_dump = json.dumps(native, sort_keys=True, separators=(",", ":"), default=_json_default)
    assert "café" in canonical
    assert "\\u" in ascii_dump
    assert canonical_row_hash(native) == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert canonical_row_hash(native) != hashlib.sha256(ascii_dump.encode("utf-8")).hexdigest()
    assert ENGINE_VERSION == "employee-ratio-cap-v1"


def test_manifest_count_does_not_use_an_empty_record_list():
    legacy = {"records": [], "hash": "ab" * 32}
    assert classify_snapshot(legacy) == "legacy"
    assert applied_count(legacy) == 0
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "job_id": str(uuid.uuid4()),
        "claim_epoch": 0,
        "evidence_table": "evaluation_apply_stage_rows",
        "record_count": 3,
        "before_hash": "cd" * 32,
        "after_hash": "ef" * 32,
    }
    assert classify_snapshot(manifest) == "manifest"
    assert applied_count(manifest) == 3
    assert classify_snapshot({**manifest, "schema": "evaluation_apply_manifest_v2"}) == "unknown_manifest"
    assert classify_snapshot({**manifest, "records": []}) == "malformed"
    assert classify_snapshot({**manifest, "record_count": True}) == "malformed"
    with pytest.raises(EvaluationConflict) as caught:
        applied_count({**manifest, "schema": "evaluation_apply_manifest_v9"})
    assert _code(caught) == "invalid_manifest"


def test_public_surface_stays_dormant(db):
    found = set()
    for route in evaluation_router.routes:
        methods = set(getattr(route, "methods", set())) - {"HEAD", "OPTIONS"}
        for method in methods:
            found.add((method, route.path))
    assert found == PUBLIC_ROUTES
    worker_source = (Path(__file__).resolve().parents[1] / "worker.py").read_text(encoding="utf-8")
    dispatch = inspect.cleandoc(worker_source.split("def process_job_once", 1)[1].split("\n    db = SessionLocal()", 1)[0])
    assert "evaluation_apply" not in dispatch
    assert JOB_KINDS == {"pms_upload", "report_generation", "story_report_generation"}
    before = db.query(ProcessingJob).count()
    with pytest.raises(ValueError, match="Unsupported processing job kind"):
        ProcessingJobService.create(
            db,
            kind="evaluation_apply",
            request_json={"scope_id": str(uuid.uuid4())},
            requested_by_user_id=None,
            requested_by_name="Admin",
        )
    db.rollback()
    assert db.query(ProcessingJob).count() == before


def test_new_upload_conflict_stays_blocked_while_stored_correction_applies(db, monkeypatch):
    calls = {"apply": 0, "exact": 0, "full": 0, "proof": 0, "matches": 0}
    real_apply = EvaluationWorkflow.apply
    original_exact = EvaluationWorkflow._exact_records
    original_full = workflow_module._full_snapshot
    original_proof = EvaluationWorkflow._assert_proof

    def _count_exact(self, *args, **kwargs):
        calls["exact"] += 1
        return original_exact(self, *args, **kwargs)

    def _count_full(records):
        calls["full"] += 1
        return original_full(records)

    def _count_proof(self, *args, **kwargs):
        calls["proof"] += 1
        return original_proof(self, *args, **kwargs)

    def _count_matches(records, snapshot):
        calls["matches"] += 1
        raise AssertionError("bounded apply reused whole-population evidence matching")

    world = _World(db, ("Coding", "Pharmacy"))
    protected = world.protect(world.teams["Coding"])
    prepared = _prepared_ratio(world, "Coding", 7, [("C-1", "Ada", "60"), ("C-2", "Ben", "30")])
    version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.status == "approved").one()
    with pytest.raises(TargetConflict) as conflict:
        score_basis(version, [{"kpi_key": prepared["key"], "actual": 60, "workbook_target": 40}])
    assert conflict.value.data["code"] == "target_conflict"

    outside = world.employee(world.teams["Coding"], "C-out", "Out")
    august = world.record(outside, "August", "71.00", "D")
    managerial = world.record(outside, "July", "80.00", "C", level="Managerial")
    other = world.record(outside, "July", "88.00", "B", team=world.teams["Pharmacy"])
    positioned = world.record(outside, "July", "77.00", "C", position="Agent")
    for row in (august, managerial, other, positioned):
        world.kpi(row, prepared["key"], "60", "40")
    db.commit()
    kept_ids = {
        str(august.id): Decimal("71.00"),
        str(managerial.id): Decimal("80.00"),
        str(other.id): Decimal("88.00"),
        str(positioned.id): Decimal("77.00"),
    }
    monkeypatch.setattr(EvaluationWorkflow, "apply", lambda self, *args, **kwargs: calls.__setitem__("apply", calls["apply"] + 1))
    monkeypatch.setattr(EvaluationWorkflow, "_exact_records", _count_exact)
    monkeypatch.setattr(workflow_module, "_full_snapshot", _count_full)
    monkeypatch.setattr(EvaluationWorkflow, "_assert_proof", _count_proof)
    monkeypatch.setattr(bounded_apply_module, "_evidence_matches", _count_matches)
    before = _live(db)
    handler = _Capture()
    logger = logging.getLogger("services.evaluation.bounded_apply")
    logger.addHandler(handler)
    try:
        captured = world.service.capture(world.actor, prepared["scope"]["id"], 2026, 7)
        resumed = world.service.capture(world.actor, prepared["scope"]["id"], 2026, 7)
    finally:
        logger.removeHandler(handler)
    assert resumed["job_id"] == captured["job_id"]
    assert resumed["resumed"] is True
    assert captured["engine_version"] == ENGINE_VERSION
    assert captured["expected_count"] == 2
    loaded = (
        db.query(PerformanceRecord)
        .options(selectinload(PerformanceRecord.kpi_values), selectinload(PerformanceRecord.employee))
        .filter(PerformanceRecord.month == "July", PerformanceRecord.performance_level == "Employee", PerformanceRecord.position_name == "")
        .filter(PerformanceRecord.team_id == world.team_ids["Coding"])
        .all()
    )
    assert captured["source_fingerprint"] == _source_fingerprint(loaded)
    job = db.query(ProcessingJob).one()
    assert set(job.request_json) == {"scope_id", "year", "month", "expected_count"}
    assert len(json.dumps(job.request_json)) <= 2048
    control = db.query(EvaluationApplyControl).one()
    assert control.state == "staging"
    admin = db.query(User).filter(User.id == world.admin_id).one()
    assert control.actor_snapshot["state"] == "known"
    assert control.actor_snapshot["user_id"].replace("-", "") == str(admin.id).replace("-", "")
    assert control.actor_snapshot["username"] == admin.username
    assert control.actor_snapshot["full_name"] == admin.full_name
    assert control.actor_snapshot["role"] == "Admin"
    assert _live(db) == before

    with pytest.raises(EvaluationError) as bad_page:
        world.service.stage_page(world.actor, captured["job_id"], page_size=True)
    assert _code(bad_page) == "invalid_page"
    with pytest.raises(EvaluationError) as oversized:
        world.service.stage_page(world.actor, captured["job_id"], page_size=501)
    assert _code(oversized) == "invalid_page"
    pages = _stage_all(world.service, world.actor, captured["job_id"], 2, page_size=1)
    assert [page["page_count"] for page in pages] == [1, 1]
    assert _live(db) == before
    assert calls == {"apply": 0, "exact": 0, "full": 0, "proof": 0, "matches": 0}

    promoted = world.service.promote(world.actor, captured["job_id"])
    assert promoted["idempotent"] is False
    assert promoted["applied_count"] == 2
    again = world.service.promote(world.actor, captured["job_id"])
    assert again["idempotent"] is True
    assert again["revision_id"] == promoted["revision_id"]
    by_code = {
        row.employee.employee_id: row
        for row in db.query(PerformanceRecord).options(selectinload(PerformanceRecord.employee), selectinload(PerformanceRecord.kpi_values)).all()
        if row.employee is not None
    }
    assert by_code["C-1"].score == Decimal("100.00")
    assert by_code["C-1"].grade == "A"
    assert by_code["C-1"].status == "Exceeds"
    assert by_code["C-1"].kpi_values[0].actual_value == Decimal("60.0000")
    assert by_code["C-1"].kpi_values[0].target_value == Decimal("50.0000")
    assert by_code["C-2"].score == Decimal("60.00")
    assert by_code["C-2"].grade == "E"
    assert by_code["C-2"].status == "Below"
    assert by_code["C-2"].kpi_values[0].target_value == Decimal("50.0000")
    fresh_scores = {str(row.id): row.score for row in db.query(PerformanceRecord).all()}
    for record_id, score in kept_ids.items():
        assert fresh_scores[record_id] == score
    revision = db.query(EvaluationRevision).one()
    assert revision.status == "active"
    assert revision.previous_revision_id is None
    assert classify_snapshot(revision.applied_snapshot) == "manifest"
    assert classify_snapshot(revision.prior_snapshot) == "manifest"
    assert applied_count(revision.applied_snapshot) == 2
    assert "records" not in revision.applied_snapshot
    readback = world.service.read_manifest(revision.id)
    assert readback["verified"] is True
    assert readback["record_count"] == 2
    outbox = db.query(CacheInvalidationOutbox).one()
    assert outbox.published_at is None
    assert outbox.delivery_attempts == 0
    assert outbox.last_error is None
    assert outbox.namespace == "data"
    job = db.query(ProcessingJob).one()
    revision = db.query(EvaluationRevision).one()
    assert outbox.dedup_key == cache_dedup_key(job.id, revision.id)
    assert job.status == "succeeded"
    assert set(job.result_json) == {"outcome", "revision_id", "count"}
    blob = json.dumps({"request": job.request_json, "result": job.result_json, "logs": handler.messages})
    assert "Ada" not in blob and "Ben" not in blob and "C-1" not in blob and "C-2" not in blob
    assert world.workflow.protected_texts() == protected
    period = world.workflow.period(world.actor, prepared["scope"]["id"], 2026, 7)
    assert period["revisions"][0]["affected_count"] == 2
    assert period["revisions"][0]["can_rollback"] is True
    monkeypatch.setattr(EvaluationWorkflow, "apply", real_apply)
    idempotent_apply = world.workflow.apply(world.actor, prepared["scope"]["id"], 2026, 7)
    assert idempotent_apply["idempotent"] is True
    assert idempotent_apply["applied_count"] == 2
    assert db.query(EvaluationRevision).count() == 1
    assert calls["full"] == 0
    assert calls["proof"] == 0
    assert calls["matches"] == 0
    assert calls["apply"] == 0

    rolled = world.workflow.rollback(world.actor, promoted["revision_id"])
    assert rolled["status"] == "rolled_back"
    assert rolled["restored_basis"] == [{"restored_count": 2}]
    assert rolled["restored_revision_id"] is None
    restored = {
        row.employee.employee_id: row
        for row in db.query(PerformanceRecord).options(selectinload(PerformanceRecord.employee), selectinload(PerformanceRecord.kpi_values)).all()
        if row.employee is not None
    }
    assert restored["C-1"].score == Decimal("70.00")
    assert restored["C-1"].kpi_values[0].target_value == Decimal("40.0000")
    assert restored["C-2"].score == Decimal("70.00")
    revision = db.query(EvaluationRevision).one()
    assert revision.status == "rolled_back"
    assert db.query(EvaluationRevision).filter(EvaluationRevision.status == "active").count() == 0
    with pytest.raises(EvaluationError) as immutable:
        world.service.rollback_latest(world.actor, promoted["revision_id"])
    assert _code(immutable) == "immutable"
    assert world.workflow.protected_texts() == protected
    assert calls["apply"] == 0


def _bulk_coding(db, count: int, actual: str = "60", month: int = 7):
    world = _World(db)
    scope = world.scope("Coding")
    draft = world.ratio_draft(scope["id"], month, 50)
    key = draft["lines"][0]["kpi_key"]
    month_name = "July" if month == 7 else "August"
    team = world.teams["Coding"]
    upload = world.upload_for(team, month_name)
    employees = [
        Employee(
            id=uuid.uuid4(),
            employee_id=f"C-{index:04d}",
            name=f"Person {index}",
            team_id=team.id,
            region="UAE",
            performance_level="Employee",
        )
        for index in range(count)
    ]
    db.add_all(employees)
    db.flush()
    records = [
        PerformanceRecord(
            id=uuid.uuid4(),
            year=2026,
            employee_id=employee.id,
            team_id=team.id,
            month=month_name,
            performance_level="Employee",
            position_name="",
            region="UAE",
            branch_key="dubai",
            score=Decimal("70.00"),
            grade="D",
            status="Below",
            upload_id=upload.id,
            uploaded_at=world.uploaded_at,
            record_payload={"manager_notes": "keep", "evaluation": {"score": 70.0, "grade": "D"}},
        )
        for employee in employees
    ]
    db.add_all(records)
    db.flush()
    db.add_all([
        KPIValue(
            id=uuid.uuid4(),
            record_id=record.id,
            record_year=record.year,
            kpi_key=key,
            actual_value=Decimal(actual),
            target_value=Decimal("40"),
            achievement_ratio=Decimal("1"),
            weight_applied=Decimal("1"),
            contribution=Decimal("1"),
        )
        for record in records
    ])
    db.commit()
    _approve(world.workflow, world.actor, draft["id"])
    return world, scope


def _engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return engine


def _statements_containing(statements, needle: str) -> list[str]:
    return [statement for statement in statements if needle in statement.lower()]


@pytest.mark.parametrize("count", [1, 99, 100, 101])
def test_page_boundaries_score_the_captured_rows(db, count):
    world, scope = _bulk_coding(db, count)
    before = _live(db)
    captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    assert captured["expected_count"] == count
    pages = _stage_all(world.service, world.actor, captured["job_id"], count, page_size=100)
    assert _live(db) == before
    if count <= 100:
        assert [page["page_count"] for page in pages] == [count]
        assert pages[0]["complete"] is True
    else:
        assert [page["page_count"] for page in pages] == [100, count - 100]
        assert pages[0]["complete"] is False
        assert pages[1]["complete"] is True
    replay = world.service.stage_page(world.actor, captured["job_id"], page_size=100, cursor=None, replay=True)
    assert replay["inserted_count"] == 0
    assert replay["idempotent"] is True
    assert replay["staged_count"] == count
    promoted = world.service.promote(world.actor, captured["job_id"])
    assert promoted["applied_count"] == count
    assert db.query(PerformanceRecord).filter(PerformanceRecord.score == Decimal("100"), PerformanceRecord.grade == "A").count() == count
    rolled = world.service.rollback_latest(world.actor, promoted["revision_id"])
    assert rolled["status"] == "rolled_back"
    assert db.query(PerformanceRecord).filter(PerformanceRecord.score == Decimal("70"), PerformanceRecord.grade == "D").count() == count
    assert db.query(EvaluationRevision).filter(EvaluationRevision.status == "active").count() == 0


def test_sparse_uuids_composite_year_and_unicode_match_the_legacy_fingerprint(db):
    world = _World(db)
    scope = world.scope("Coding")
    draft = world.ratio_draft(scope["id"], 7, 50)
    key = draft["lines"][0]["kpi_key"]
    team = world.teams["Coding"]
    team_id = world.team_ids["Coding"]
    upload = world.upload_for(team, "July")
    chosen = [
        uuid.UUID(int=1),
        uuid.UUID(int=2),
        uuid.UUID(int=2**120),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
    ]
    shared = uuid.uuid4()
    chosen.append(shared)
    employee = world.employee(team, "C-ü", "Naïve café")
    records = []
    for record_id in chosen:
        payload = {
            "manager_notes": "café — naïve",
            "raw_data": {"note": None, "rate": "0.6500", "label": "café"},
            "evaluation": {"score": 70.0, "grade": "D"},
        }
        records.append(world.record(
            employee, "July", "70.00", "D", record_id=record_id, payload=payload, upload=upload,
        ))
        world.kpi(records[-1], key, "60", "40")
    older = world.record(employee, "July", "70.00", "D", record_id=shared, year=2025, payload={"manager_notes": "other year"}, upload=upload)
    world.kpi(older, key, "60", "40")
    older_id = older.id
    db.commit()
    _approve(world.workflow, world.actor, draft["id"])
    captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    loaded = (
        db.query(PerformanceRecord)
        .options(selectinload(PerformanceRecord.kpi_values), selectinload(PerformanceRecord.employee))
        .filter(PerformanceRecord.year == 2026, PerformanceRecord.team_id == team_id)
        .all()
    )
    assert captured["source_fingerprint"] == _source_fingerprint(loaded)
    assert captured["expected_count"] == len(chosen)
    pages = _stage_all(world.service, world.actor, captured["job_id"], len(chosen), page_size=1)
    assert len(pages) == len(chosen)
    staged = [
        str(row.record_id)
        for row in db.query(EvaluationApplyStageRow).order_by(EvaluationApplyStageRow.record_year.asc(), EvaluationApplyStageRow.record_id.asc()).all()
    ]
    assert staged == sorted(str(record_id) for record_id in chosen)
    assert all(row.record_year == 2026 for row in db.query(EvaluationApplyStageRow).all())
    assert db.query(EvaluationApplyStageRow).filter(EvaluationApplyStageRow.record_id == shared).count() == 1
    world.service.promote(world.actor, captured["job_id"])
    older = db.query(PerformanceRecord).filter(PerformanceRecord.id == older_id, PerformanceRecord.year == 2025).one()
    assert older.score == Decimal("70.00")
    assert older.year == 2025


def test_query_count_and_memory_stay_paged_from_100_to_1000(monkeypatch):
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda self, kind: None)
    measured = {}
    for count in (100, 1000):
        engine = _engine()
        session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        try:
            world, scope = _bulk_coding(session, count)
            captured = world.service.capture(world.actor, scope["id"], 2026, 7)
            session.expunge_all()
            gc.collect()
            statements = []

            def _capture(conn, cursor, statement, parameters, context, executemany):
                statements.append(statement)

            event.listen(engine, "before_cursor_execute", _capture)
            started_tracing_here = not tracemalloc.is_tracing()
            if started_tracing_here:
                tracemalloc.start()
            tracemalloc.clear_traces()
            tracemalloc.reset_peak()
            try:
                _stage_all(world.service, world.actor, captured["job_id"], count, page_size=100)
                current, peak = tracemalloc.get_traced_memory()
            finally:
                event.remove(engine, "before_cursor_execute", _capture)
                if started_tracing_here:
                    tracemalloc.stop()
            assert list(session.identity_map) == []
            for statement in statements:
                lowered = " ".join(statement.lower().split())
                if "from performance_records" in lowered and "count(" not in lowered:
                    assert "limit" in lowered, lowered
            measured[count] = {
                "employees": len(_statements_containing(statements, "from employees")),
                "versions": len(_statements_containing(statements, "from team_configuration_versions")),
                "records": len(_statements_containing(statements, "from performance_records")),
                "current": current,
                "peak": peak,
            }
            assert measured[count]["employees"] < count
            assert measured[count]["versions"] < count
            promoted = world.service.promote(world.actor, captured["job_id"])
            assert session.query(PerformanceRecord).filter(PerformanceRecord.grade == "A", PerformanceRecord.score == Decimal("100")).count() == count
            world.service.rollback_latest(world.actor, promoted["revision_id"])
            assert session.query(PerformanceRecord).filter(PerformanceRecord.grade == "D", PerformanceRecord.score == Decimal("70")).count() == count
        finally:
            session.close()
            engine.dispose()
    message = (
        "bounded-apply-measure "
        f"rows=100 employees={measured[100]['employees']} versions={measured[100]['versions']} "
        f"records={measured[100]['records']} current={measured[100]['current']} peak={measured[100]['peak']}; "
        f"rows=1000 employees={measured[1000]['employees']} versions={measured[1000]['versions']} "
        f"records={measured[1000]['records']} current={measured[1000]['current']} peak={measured[1000]['peak']}"
    )
    warnings.warn(message, UserWarning, stacklevel=1)
    Path(__import__("tempfile").gettempdir(), "bounded-apply-measure.txt").write_text(message, encoding="utf-8")
    assert measured[1000]["peak"] < measured[100]["peak"] * 8


def test_page_crash_replay_conflict_and_stale_epoch_leave_live_rows(db):
    world, scope = _bulk_coding(db, 2)
    before = _live(db)
    db.info["bounded_apply_fault"] = "before_commit"
    with pytest.raises(EvaluationConflict) as crashed:
        world.service.capture(world.actor, scope["id"], 2026, 7)
    assert _code(crashed) == "fault_injected"
    assert db.query(ProcessingJob).count() == 0
    assert _live(db) == before
    db.info.pop("bounded_apply_fault")
    captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    db.info["bounded_apply_fault"] = "before_commit"
    with pytest.raises(EvaluationConflict) as page_crash:
        world.service.stage_page(world.actor, captured["job_id"], page_size=1)
    assert _code(page_crash) == "fault_injected"
    assert db.query(EvaluationApplyStageRow).count() == 0
    assert _live(db) == before
    db.info.pop("bounded_apply_fault")
    first = world.service.stage_page(world.actor, captured["job_id"], page_size=1)
    assert first["inserted_count"] == 1
    assert first["complete"] is False
    replay = world.service.stage_page(world.actor, captured["job_id"], page_size=1, cursor=None, replay=True)
    assert replay["inserted_count"] == 0
    assert replay["idempotent"] is True
    control = db.query(EvaluationApplyControl).one()
    assert control.staged_count == 1
    held_cursor = control.stage_cursor
    kpi = db.query(KPIValue).filter(KPIValue.record_id == uuid.UUID(held_cursor.split(":", 1)[1])).one()
    kpi.achievement_ratio = Decimal("0.2500")
    db.commit()
    with pytest.raises(EvaluationConflict) as conflict:
        world.service.stage_page(world.actor, captured["job_id"], page_size=1, cursor=None, replay=True)
    assert _code(conflict) == "conflicting_stage"
    control = db.query(EvaluationApplyControl).one()
    assert control.staged_count == 1
    assert control.stage_cursor == held_cursor
    stage = db.query(EvaluationApplyStageRow).one()
    assert stage.before_row["kpis"][0]["achievement"] == "1"
    assert _live(db) != before
    with pytest.raises(EvaluationConflict) as stale:
        world.service.stage_page(world.actor, captured["job_id"], page_size=1, expected_epoch=4)
    assert _code(stale) == "stale_epoch"
    control = db.query(EvaluationApplyControl).one()
    assert control.staged_count == 1
    assert db.query(EvaluationRevision).count() == 0


def test_promotion_faults_leave_one_revision_after_retry(db):
    world, scope = _bulk_coding(db, 1)
    captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    _stage_all(world.service, world.actor, captured["job_id"], 1)
    before = _live(db)
    other_factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)
    for point in FAULT_POINTS:
        db.info["bounded_apply_fault"] = point
        with pytest.raises(EvaluationConflict) as faulted:
            world.service.promote(world.actor, captured["job_id"], expected_epoch=0)
        assert _code(faulted) == "fault_injected"
        db.info.pop("bounded_apply_fault")
        assert _live(db) == before
        other = other_factory()
        try:
            control = other.query(EvaluationApplyControl).one()
            assert control.state == "staging"
            assert control.promoted_revision_id is None
            assert control.promoted_count == 0
            assert other.query(EvaluationRevision).count() == 0
            assert other.query(CacheInvalidationOutbox).count() == 0
            assert other.query(PerformanceRecord).one().score == Decimal("70.00")
        finally:
            other.close()
    with pytest.raises(EvaluationConflict) as stale_before:
        world.service.promote(world.actor, captured["job_id"], expected_epoch=3)
    assert _code(stale_before) == "stale_epoch"
    assert _live(db) == before
    assert db.query(EvaluationRevision).count() == 0
    promoted = world.service.promote(world.actor, captured["job_id"], expected_epoch=0)
    repeated = world.service.promote(world.actor, captured["job_id"], expected_epoch=0)
    assert repeated["idempotent"] is True
    assert repeated["revision_id"] == promoted["revision_id"]
    other = other_factory()
    try:
        assert other.query(EvaluationRevision).count() == 1
        assert other.query(CacheInvalidationOutbox).count() == 1
        outbox = other.query(CacheInvalidationOutbox).one()
        assert outbox.published_at is None
        assert outbox.delivery_attempts == 0
        assert other.query(PerformanceRecord).one().grade == "A"
        assert other.query(EvaluationApplyControl).one().state == "promoted"
    finally:
        other.close()
    repeated_stale = world.service.promote(world.actor, captured["job_id"], expected_epoch=3)
    assert repeated_stale["idempotent"] is True
    assert repeated_stale["revision_id"] == promoted["revision_id"]
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(CacheInvalidationOutbox).count() == 1


def test_revoked_inactive_deleted_and_forged_actors_are_not_grants(db):
    world, scope = _bulk_coding(db, 1)
    captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    forged = dict(world.actor)
    forged["role"] = "Admin"
    forged["user_id"] = str(world.manager_id)
    with pytest.raises(Exception) as denied:
        world.service.stage_page(forged, captured["job_id"])
    assert denied.value.status_code == 403
    assert db.query(EvaluationApplyStageRow).count() == 0
    admin = db.query(User).filter(User.id == world.admin_id).one()
    admin.role = "Manager"
    db.commit()
    snapshot = db.query(EvaluationApplyControl).one().actor_snapshot
    assert snapshot["role"] == "Admin"
    with pytest.raises(Exception) as revoked:
        world.service.stage_page(world.actor, captured["job_id"])
    assert revoked.value.status_code == 403
    admin = db.query(User).filter(User.id == world.admin_id).one()
    admin.role = "Admin"
    admin.is_active = False
    db.commit()
    with pytest.raises(Exception) as inactive:
        world.service.stage_page(world.actor, captured["job_id"])
    assert inactive.value.status_code == 403
    admin = db.query(User).filter(User.id == world.admin_id).one()
    admin.is_active = True
    db.commit()
    admin_id = admin.id
    removed = False
    try:
        db.delete(admin)
        db.commit()
        removed = True
    except Exception:
        db.rollback()
    if removed:
        with pytest.raises(Exception) as deleted:
            world.service.promote(world.actor, captured["job_id"])
        assert deleted.value.status_code in {403, 422, 409}
    else:
        assert db.query(User).filter(User.id == admin_id).count() == 1
        world.service.stage_page(world.actor, captured["job_id"], page_size=1)
        assert db.query(EvaluationApplyStageRow).count() == 1
    manager_user = db.query(User).filter(User.id == world.manager_id).one()
    with pytest.raises(Exception) as manager:
        world.service.capture(_actor(manager_user), scope["id"], 2026, 8)
    assert manager.value.status_code == 403
    assert db.query(ProcessingJob).count() == 1


def test_drift_rejects_before_any_score_write(db):
    world, scope = _bulk_coding(db, 2)
    captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    first = world.service.stage_page(world.actor, captured["job_id"], page_size=1)
    assert first["complete"] is False
    before = _live(db)
    moving = db.query(KPIValue).filter(~KPIValue.record_id.in_(
        db.query(EvaluationApplyStageRow.record_id)
    )).first()
    moving_id = moving.id
    moving.actual_value = Decimal("61")
    db.commit()
    with pytest.raises(EvaluationConflict) as changed:
        world.service.stage_page(world.actor, captured["job_id"], page_size=1)
    assert _code(changed) == "evidence_changed"
    moving = db.query(KPIValue).filter(KPIValue.id == moving_id).one()
    moving.actual_value = Decimal("60")
    db.commit()
    second = world.service.stage_page(world.actor, captured["job_id"], page_size=1)
    assert second["inserted_count"] == 1
    assert second["complete"] is True
    assert second["staged_count"] == 2
    assert db.query(PerformanceRecord).filter(PerformanceRecord.score != Decimal("70")).count() == 0

    control = db.query(EvaluationApplyControl).one()
    control.engine_version = "employee-ratio-cap-v2"
    if _persisted(db):
        with pytest.raises(EvaluationConflict) as engine:
            world.service.promote(world.actor, captured["job_id"])
        assert _code(engine) == "stale_preview"
        assert db.query(PerformanceRecord).filter(PerformanceRecord.score != Decimal("70")).count() == 0
        control = db.query(EvaluationApplyControl).one()
        control.engine_version = ENGINE_VERSION
        assert _persisted(db)
    else:
        assert db.query(EvaluationApplyControl).one().engine_version == ENGINE_VERSION
        assert db.query(PerformanceRecord).filter(PerformanceRecord.score != Decimal("70")).count() == 0

    version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.status == "approved").one()
    version_id = version.id
    original_target = version.config_snapshot["lines"][0]["target"]
    mutated = json.loads(json.dumps(version.config_snapshot))
    mutated["lines"][0]["target"] = 44
    version.config_snapshot = mutated
    flag_modified(version, "config_snapshot")
    if _persisted(db):
        with pytest.raises(EvaluationConflict) as rules:
            world.service.promote(world.actor, captured["job_id"])
        assert _code(rules) == "stale_preview"
        version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == version_id).one()
        restored_snapshot = json.loads(json.dumps(version.config_snapshot))
        restored_snapshot["lines"][0]["target"] = original_target
        version.config_snapshot = restored_snapshot
        flag_modified(version, "config_snapshot")
        assert _persisted(db)
    else:
        version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == version_id).one()
        assert version.config_snapshot["lines"][0]["target"] == original_target
        assert db.query(PerformanceRecord).filter(PerformanceRecord.score != Decimal("70")).count() == 0

    scope_row = db.query(EvaluationScope).filter(EvaluationScope.id == uuid.UUID(scope["id"])).one()
    extra = EvaluationRevision(
        team_id=scope_row.team_id,
        performance_level=scope_row.performance_level,
        position_name=scope_row.position_name or "",
        year=2026,
        month=7,
        version_id=version_id,
        status="active",
        prior_snapshot={"records": [], "hash": "ab" * 32},
        applied_snapshot={"records": [], "hash": "ab" * 32},
        created_by_user_id=world.admin_id,
        actor_snapshot={"state": "known", "user_id": str(world.admin_id)},
    )
    db.add(extra)
    try:
        db.flush()
    except Exception:
        db.rollback()
        extra = None
    if extra is not None:
        with pytest.raises(EvaluationConflict) as lineage:
            world.service.promote(world.actor, captured["job_id"])
        assert _code(lineage) == "lineage_changed"
        assert db.query(PerformanceRecord).filter(PerformanceRecord.score != Decimal("70")).count() == 0
        assert db.query(CacheInvalidationOutbox).count() == 0
        assert db.query(EvaluationRevision).count() == 0
    promoted = world.service.promote(world.actor, captured["job_id"])
    assert promoted["applied_count"] == 2
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(PerformanceRecord).filter(PerformanceRecord.grade == "A").count() == 2


def test_empty_bad_month_and_unsupported_scopes_do_not_open_a_job(db):
    world = _World(db, ("Coding", "Pharmacy", "Outbound"))
    empty = world.ratio_draft(world.scope("Coding")["id"], 8, 50)
    _approve(world.workflow, world.actor, empty["id"])
    with pytest.raises(EvaluationError) as missing:
        world.service.capture(world.actor, world.scope("Coding")["id"], 2026, 8)
    assert _code(missing) == "insufficient_data"
    assert db.query(ProcessingJob).count() == 0

    draft = world.ratio_draft(world.scope("Coding")["id"], 7, 50)
    key = draft["lines"][0]["kpi_key"]
    employee = world.employee(world.teams["Coding"], "C-bad", "Bad")
    upload = world.upload_for(world.teams["Coding"], "July")
    record = world.record(employee, "7", "70.00", "D", upload=upload)
    world.kpi(record, key, "60", "40")
    db.commit()
    world.workflow.impact_preview(world.actor, draft["id"])
    world.workflow.approve(world.actor, draft["id"])
    with pytest.raises(EvaluationError) as label:
        world.service.capture(world.actor, world.scope("Coding")["id"], 2026, 7)
    assert _code(label) == "invalid_evidence"
    assert db.query(ProcessingJob).count() == 0

    pharmacy = world.scope("Pharmacy")
    with pytest.raises(EvaluationError) as blocked:
        world.service.capture(world.actor, pharmacy["id"], 2026, 7)
    assert _code(blocked) == "unsupported_calculation"
    outbound = world.scope("Outbound")
    for month in (6, 9):
        with pytest.raises(EvaluationError) as refused:
            world.service.capture(world.actor, outbound["id"], 2026, month)
        assert _code(refused) == "unsupported_calculation"
    positioned = [
        item for item in world.catalog["scopes"]
        if item["display_name"] == "Coding" and item["position_name"] not in {"", None}
    ]
    for item in positioned:
        with pytest.raises(EvaluationError) as position:
            world.service.capture(world.actor, item["id"], 2026, 7)
        assert _code(position) == "unsupported_calculation"
    assert db.query(ProcessingJob).count() == 0


def test_missing_duplicate_and_nonfinite_sources_do_not_open_a_job(db):
    world = _World(db)
    scope = world.scope("Coding")
    draft = world.ratio_draft(scope["id"], 7, 50)
    key = draft["lines"][0]["kpi_key"]
    employee = world.employee(world.teams["Coding"], "C-miss", "Miss")
    record = world.record(employee, "July", "70.00", "D")
    world.kpi(record, "NotTheWeightedKpi", "60", "40")
    db.commit()
    with pytest.raises(EvaluationError) as missing:
        world.workflow.impact_preview(world.actor, draft["id"])
    assert _code(missing) == "missing_evidence"
    assert db.query(ProcessingJob).count() == 0

    db.rollback()
    db.delete(record.kpi_values[0])
    db.commit()
    first = world.kpi(record, key, "60", "40")
    world.kpi(record, key, "61", "40")
    db.commit()
    with pytest.raises(EvaluationError) as duplicate:
        world.workflow.impact_preview(world.actor, draft["id"])
    assert _code(duplicate) == "duplicate_kpi"
    assert db.query(ProcessingJob).count() == 0

    db.rollback()
    duplicates = db.query(KPIValue).filter(KPIValue.kpi_key == key).all()
    assert len(duplicates) == 2
    db.delete(duplicates[1])
    db.commit()
    first = duplicates[0]
    try:
        first.actual_value = Decimal("NaN")
        db.commit()
        stored = True
    except Exception:
        db.rollback()
        stored = False
    if stored:
        with pytest.raises(EvaluationError):
            world.workflow.impact_preview(world.actor, draft["id"])
    assert db.query(ProcessingJob).count() == 0


def _outbound_record(world: _World, draft: dict, month_name: str, actuals: dict) -> PerformanceRecord:
    employee = world.employee(world.teams["Outbound"], f"O-{month_name}", f"Outbound {month_name}")
    upload = world.upload_for(world.teams["Outbound"], month_name)
    record = world.record(employee, month_name, "10.00", "E", upload=upload)
    for line in draft["lines"]:
        if float(line["weight"]) <= 0:
            continue
        key = line["kpi_key"]
        world.kpi(record, key, actuals[key], SOURCE_TARGETS[key])
    world.db.commit()
    return record


def test_outbound_july_and_august_use_the_canonical_ratios(db):
    world = _World(db, ("Outbound",))
    scope = world.scope("Outbound")
    july = world.workflow.open_draft(world.actor, scope["id"], 2026, 7)
    july_weights = {line["kpi_key"]: line["weight"] for line in july["lines"] if float(line["weight"]) > 0}
    assert july_weights == {"Attendance": pytest.approx(0.70), "Booking": pytest.approx(0.10), "Quality": pytest.approx(0.10), "Other": pytest.approx(0.10)}
    assert july["lines"][0]["direction"] == "higher_better" or any(
        line["direction"] == "higher_better" and line["kpi_key"] == "Attendance" for line in july["lines"]
    )
    july_record = _outbound_record(world, july, "July", {
        "Attendance": "0.325",
        "Booking": "0.3",
        "Quality": "0.95",
        "Other": "0.75",
    })
    july_id = (july_record.id, july_record.year)
    _approve(world.workflow, world.actor, july["id"])
    captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    _stage_all(world.service, world.actor, captured["job_id"], 1)
    world.service.promote(world.actor, captured["job_id"])
    july_record = _performance(db, july_id[0], july_id[1])
    attendance = next(value for value in july_record.kpi_values if value.kpi_key == "Attendance")
    assert july_record.score == Decimal("65.00")
    assert july_record.grade == "D"
    assert july_record.status == "Below"
    assert attendance.actual_value == Decimal("0.3250")
    assert attendance.target_value == Decimal("0.6500")
    assert attendance.achievement_ratio == Decimal("0.5000")
    assert attendance.weight_applied == Decimal("0.7000")
    assert attendance.contribution == Decimal("0.3500")

    august = world.workflow.open_draft(world.actor, scope["id"], 2026, 8)
    august_weights = {line["kpi_key"]: line["weight"] for line in august["lines"] if float(line["weight"]) > 0}
    assert august_weights["Attendance"] == pytest.approx(0.60)
    assert august_weights["Productivity"] == pytest.approx(0.10)
    august_record = _outbound_record(world, august, "August", {
        "Attendance": "0.65",
        "Booking": "0.3",
        "Quality": "0.95",
        "Other": "0.75",
        "Productivity": "0.8",
    })
    august_id = (august_record.id, august_record.year)
    _approve(world.workflow, world.actor, august["id"])
    august_job = world.service.capture(world.actor, scope["id"], 2026, 8)
    _stage_all(world.service, world.actor, august_job["job_id"], 1)
    world.service.promote(world.actor, august_job["job_id"])
    august_record = _performance(db, august_id[0], august_id[1])
    productivity = next(value for value in august_record.kpi_values if value.kpi_key == "Productivity")
    august_attendance = next(value for value in august_record.kpi_values if value.kpi_key == "Attendance")
    assert august_record.score == Decimal("100.00")
    assert august_record.grade == "A"
    assert august_record.status == "Exceeds"
    assert august_attendance.weight_applied == Decimal("0.6000")
    assert august_attendance.target_value == Decimal("0.6500")
    assert productivity.weight_applied == Decimal("0.1000")
    assert productivity.target_value == Decimal("0.8000")
    assert productivity.actual_value == Decimal("0.8000")
    july_record = _performance(db, july_id[0], july_id[1])
    assert july_record.score == Decimal("65.00")


def test_submission_employee_ratio_is_admitted(db):
    world = _World(db, ("Submission",))
    prepared = _prepared_ratio(world, "Submission", 7, [("S-1", "Sam", "60")])
    captured = world.service.capture(world.actor, prepared["scope"]["id"], 2026, 7)
    _stage_all(world.service, world.actor, captured["job_id"], 1)
    world.service.promote(world.actor, captured["job_id"])
    record = db.query(PerformanceRecord).one()
    assert record.score == Decimal("100.00")
    assert record.grade == "A"
    assert record.status == "Exceeds"


def test_legacy_snapshot_rollback_stays_compatible(db):
    world, scope = _bulk_coding(db, 1)
    applied = world.workflow.apply(world.actor, scope["id"], 2026, 7)
    revision = db.query(EvaluationRevision).one()
    revision_id = revision.id
    assert classify_snapshot(revision.applied_snapshot) == "legacy"
    assert applied_count(revision.applied_snapshot) == 1
    assert applied["applied_count"] == 1
    assert db.query(PerformanceRecord).one().score == Decimal("100.00")
    with pytest.raises(EvaluationConflict) as legacy:
        world.service.rollback_latest(world.actor, revision_id)
    assert _code(legacy) == "legacy_snapshot"
    assert db.query(PerformanceRecord).one().score == Decimal("100.00")
    rolled = world.workflow.rollback(world.actor, str(revision_id))
    assert rolled["status"] == "rolled_back"
    assert db.query(PerformanceRecord).one().score == Decimal("70.00")
    assert db.query(EvaluationRevision).one().status == "rolled_back"
    with pytest.raises(EvaluationError) as immutable:
        world.workflow.rollback(world.actor, str(revision_id))
    assert _code(immutable) == "immutable"


def test_old_approval_is_not_reactivated_and_lineage_skips_snapshots(db):
    world, scope = _bulk_coding(db, 1, actual="30")
    first = world.workflow.apply(world.actor, scope["id"], 2026, 7)
    legacy = db.query(EvaluationRevision).one()
    legacy_id = legacy.id
    assert db.query(PerformanceRecord).one().score == Decimal("60.00")
    revised = world.workflow.revise(world.actor, first["version_id"])
    world.workflow.edit_draft(world.actor, revised["id"], _line_edit(revised["lines"], 30))
    _approve(world.workflow, world.actor, revised["id"])
    statements = []

    def _capture_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", _capture_sql)
    try:
        captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _capture_sql)
    revision_sql = _statements_containing(statements, "evaluation_revisions")
    assert revision_sql
    assert all("prior_snapshot" not in statement.lower() and "applied_snapshot" not in statement.lower() for statement in revision_sql)
    _stage_all(world.service, world.actor, captured["job_id"], 1)
    promoted = world.service.promote(world.actor, captured["job_id"])
    legacy = db.query(EvaluationRevision).filter(EvaluationRevision.id == legacy_id).one()
    assert legacy.status == "superseded"
    assert db.query(PerformanceRecord).one().score == Decimal("100.00")
    with pytest.raises(EvaluationConflict) as older:
        world.service.rollback_latest(world.actor, legacy_id)
    assert _code(older) == "not_latest"
    assert db.query(PerformanceRecord).one().score == Decimal("100.00")
    legacy = db.query(EvaluationRevision).filter(EvaluationRevision.id == legacy_id).one()
    assert legacy.status == "superseded"
    rolled = world.service.rollback_latest(world.actor, promoted["revision_id"])
    assert rolled["status"] == "rolled_back"
    legacy = db.query(EvaluationRevision).filter(EvaluationRevision.id == legacy_id).one()
    assert legacy.status == "superseded"
    assert db.query(EvaluationRevision).filter(EvaluationRevision.status == "active").count() == 0
    assert db.query(PerformanceRecord).one().score == Decimal("60.00")


def test_manifest_guards_reject_unknown_malformed_and_altered_evidence(db):
    world, scope = _bulk_coding(db, 1)
    captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    _stage_all(world.service, world.actor, captured["job_id"], 1)
    promoted = world.service.promote(world.actor, captured["job_id"])
    revision = db.query(EvaluationRevision).one()
    assert world.service.read_manifest(revision.id)["verified"] is True
    saved = dict(revision.applied_snapshot)
    for mutated in (
        {**saved, "schema": "evaluation_apply_manifest_v2"},
        {**saved, "record_count": True},
        {**saved, "after_hash": "ab" * 32},
        {**saved, "records": []},
    ):
        revision.applied_snapshot = mutated
        flag_modified(revision, "applied_snapshot")
        with pytest.raises(EvaluationConflict) as bad:
            world.workflow.rollback(world.actor, str(revision.id))
        assert _code(bad) == "invalid_manifest"
        db.rollback()
        revision = db.query(EvaluationRevision).one()
        assert db.query(PerformanceRecord).one().score == Decimal("100.00")
    with pytest.raises(EvaluationConflict) as altered:
        world.service._verify_stage_manifest({**saved, "before_hash": "11" * 32}, side="before")
    assert _code(altered) == "invalid_manifest"
    row = db.query(EvaluationApplyStageRow).one()
    try:
        db.delete(row)
        db.flush()
        deleted = True
    except Exception:
        db.rollback()
        deleted = False
    if deleted:
        with pytest.raises(EvaluationConflict) as missing_row:
            world.service.read_manifest(promoted["revision_id"])
        assert _code(missing_row) == "invalid_manifest"
        db.rollback()
    else:
        assert db.query(EvaluationApplyStageRow).count() == 1
    duplicate = EvaluationApplyStageRow(
        job_id=row.job_id,
        claim_epoch=row.claim_epoch,
        record_id=row.record_id,
        record_year=row.record_year,
        before_row=row.before_row,
        after_row=row.after_row,
        before_hash=row.before_hash,
        after_hash=row.after_hash,
        rules_checksum=row.rules_checksum,
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    assert world.service.read_manifest(promoted["revision_id"])["record_count"] == 1


def test_stage_locks_team_then_job_scope_control_and_batches_stage_reads(db, monkeypatch):
    """Header locks stay behind the team fence. One page issues one stage SELECT."""
    world, scope = _bulk_coding(db, 3)
    captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    order = []
    original_team = bounded_apply_module.lock_team_rows
    original_lock = world.service._lock_query

    def _team(database, team_ids):
        order.append("Team")
        return original_team(database, team_ids)

    def _observed(query, lock):
        entity = query.column_descriptions[0].get("entity")
        name = getattr(entity, "__name__", "")
        if lock and name in {
            "ProcessingJob",
            "EvaluationScope",
            "EvaluationApplyControl",
            "PerformanceRecord",
            "EvaluationRevision",
        }:
            order.append(name)
        return original_lock(query, lock)

    monkeypatch.setattr(bounded_apply_module, "lock_team_rows", _team)
    monkeypatch.setattr(world.service, "_lock_query", _observed)
    selects = []

    def _count(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().casefold().startswith("select") and "from evaluation_apply_stage_rows" in statement.casefold():
            selects.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", _count)
    try:
        page = world.service.stage_page(world.actor, captured["job_id"], page_size=2, expected_epoch=captured["claim_epoch"])
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _count)
    assert page["inserted_count"] == 2
    assert order[0] == "Team"
    assert order[1:4] == ["ProcessingJob", "EvaluationScope", "EvaluationApplyControl"]
    assert "PerformanceRecord" in order
    assert order.index("EvaluationApplyControl") < order.index("PerformanceRecord")
    assert len(selects) == 1
    order.clear()
    selects.clear()
    event.listen(db.get_bind(), "before_cursor_execute", _count)
    try:
        replay = world.service.stage_page(
            world.actor,
            captured["job_id"],
            page_size=2,
            cursor=None,
            replay=True,
            expected_epoch=captured["claim_epoch"],
        )
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _count)
    assert replay["inserted_count"] == 0
    assert len(selects) == 1
    rest = world.service.stage_page(world.actor, captured["job_id"], page_size=2, expected_epoch=captured["claim_epoch"])
    assert rest["inserted_count"] == 1
    assert rest["complete"] is True
    promoted = world.service.promote(world.actor, captured["job_id"], expected_epoch=0)
    order.clear()
    world.service.rollback_latest(world.actor, promoted["revision_id"])
    assert order[0] == "Team"
    assert order.index("Team") < order.index("EvaluationRevision")
    assert order.index("ProcessingJob") < order.index("EvaluationScope") < order.index("EvaluationApplyControl")
    assert order.index("EvaluationApplyControl") < order.index("EvaluationRevision")
    assert order.index("EvaluationRevision") < order.index("PerformanceRecord")


def test_read_manifest_rejects_foreign_parent_and_disagreed_prior(db, monkeypatch):
    from types import SimpleNamespace

    world, scope = _bulk_coding(db, 1)
    captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    _stage_all(world.service, world.actor, captured["job_id"], 1)
    promoted = world.service.promote(world.actor, captured["job_id"], expected_epoch=0)
    revision = db.query(EvaluationRevision).one()
    fields = {column.name: getattr(revision, column.name) for column in EvaluationRevision.__table__.columns}
    foreign = dict(fields)
    foreign["id"] = uuid.uuid4()
    monkeypatch.setattr(world.service, "_revision", lambda _identity: SimpleNamespace(**foreign))
    with pytest.raises(EvaluationConflict) as foreign_parent:
        world.service.read_manifest(promoted["revision_id"])
    assert _code(foreign_parent) == "invalid_manifest"
    shifted = dict(fields)
    shifted["prior_snapshot"] = {**revision.prior_snapshot, "before_hash": "ab" * 32}
    monkeypatch.setattr(world.service, "_revision", lambda _identity: SimpleNamespace(**shifted))
    with pytest.raises(EvaluationConflict) as prior_mismatch:
        world.service.read_manifest(promoted["revision_id"])
    assert _code(prior_mismatch) == "invalid_manifest"
    period = world.workflow.period(world.actor, scope["id"], 2026, 7)
    assert period["revisions"][0]["can_rollback"] is True
    monkeypatch.setattr(world.service, "_revision", lambda _identity, _revision=revision: _revision)
    assert world.service.read_manifest(promoted["revision_id"])["verified"] is True


def test_completed_replay_tolerates_stale_epoch_and_does_not_mutate(db):
    world, scope = _bulk_coding(db, 1)
    captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    _stage_all(world.service, world.actor, captured["job_id"], 1)
    promoted = world.service.promote(world.actor, captured["job_id"], expected_epoch=0)
    before = _live(db)
    replay = world.service.promote(world.actor, captured["job_id"], expected_epoch=8)
    assert replay["idempotent"] is True
    assert replay["revision_id"] == promoted["revision_id"]
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(CacheInvalidationOutbox).count() == 1
    assert _live(db) == before
    outsider = dict(world.actor)
    outsider["user_id"] = str(world.manager_id)
    outsider["role"] = "Admin"
    with pytest.raises(Exception) as denied:
        world.service.promote(outsider, captured["job_id"], expected_epoch=0)
    assert denied.value.status_code == 403
    assert db.query(EvaluationRevision).count() == 1
    assert _live(db) == before


def test_role_change_at_the_team_fence_is_reread_before_mutation(db, monkeypatch):
    """The grant read follows the team fence and refreshes a stale identity map.

    SQLite keeps another connection's commit invisible for the rest of an open
    transaction, so this test updates the role in the same transaction with
    synchronize_session=False. The loaded object stays Admin. The service has
    to reread. The native probe commits that change on a second connection
    while the team lock is waited.
    """
    world, scope = _bulk_coding(db, 1)
    before = _live(db)

    def denied(operation):
        original_team = bounded_apply_module.lock_team_rows
        original_lock = world.service._lock_query
        order = []

        def _team(database, team_ids):
            order.append("Team")
            loaded = database.query(User).filter(User.id == world.admin_id).one()
            assert loaded.role == "Admin"
            database.query(User).filter(User.id == world.admin_id).update(
                {User.role: "Performance Team"},
                synchronize_session=False,
            )
            assert loaded.role == "Admin"
            return original_team(database, team_ids)

        def _observed(query, lock):
            entity = query.column_descriptions[0].get("entity")
            name = getattr(entity, "__name__", "")
            if lock and name:
                order.append(name)
            return original_lock(query, lock)

        monkeypatch.setattr(bounded_apply_module, "lock_team_rows", _team)
        monkeypatch.setattr(world.service, "_lock_query", _observed)
        try:
            with pytest.raises(AccessDenied):
                operation()
        finally:
            monkeypatch.setattr(bounded_apply_module, "lock_team_rows", original_team)
            monkeypatch.setattr(world.service, "_lock_query", original_lock)
        assert order == ["Team"]
        assert db.query(User).filter(User.id == world.admin_id).one().role == "Admin"

    denied(lambda: world.service.capture(world.actor, scope["id"], 2026, 7))
    assert db.query(ProcessingJob).count() == 0
    assert db.query(EvaluationApplyControl).count() == 0
    assert _live(db) == before

    captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    assert db.query(EvaluationApplyControl).one().actor_snapshot["role"] == "Admin"
    denied(lambda: world.service.capture(world.actor, scope["id"], 2026, 7))
    assert db.query(ProcessingJob).count() == 1
    assert db.query(EvaluationApplyControl).one().state == "staging"
    assert db.query(EvaluationApplyControl).one().actor_snapshot["role"] == "Admin"
    assert db.query(EvaluationApplyStageRow).count() == 0
    assert _live(db) == before

    denied(lambda: world.service.stage_page(world.actor, captured["job_id"], expected_epoch=0))
    assert db.query(EvaluationApplyStageRow).count() == 0
    assert db.query(EvaluationApplyControl).one().state == "staging"
    assert _live(db) == before

    staged = world.service.stage_page(world.actor, captured["job_id"], expected_epoch=0)
    assert staged["inserted_count"] == 1
    denied(lambda: world.service.stage_page(
        world.actor,
        captured["job_id"],
        replay=True,
        expected_epoch=0,
    ))
    assert db.query(EvaluationApplyStageRow).count() == 1
    assert _live(db) == before

    denied(lambda: world.service.promote(world.actor, captured["job_id"], expected_epoch=0))
    assert db.query(EvaluationRevision).count() == 0
    assert db.query(CacheInvalidationOutbox).count() == 0
    assert db.query(EvaluationApplyControl).one().state == "staging"
    assert db.query(EvaluationApplyStageRow).count() == 1
    assert _live(db) == before

    promoted = world.service.promote(world.actor, captured["job_id"], expected_epoch=0)
    promoted_rows = _live(db)
    assert promoted_rows != before
    denied(lambda: world.service.promote(world.actor, captured["job_id"], expected_epoch=8))
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(EvaluationRevision).one().status == "active"
    assert db.query(CacheInvalidationOutbox).count() == 1
    assert _live(db) == promoted_rows

    replay = world.service.promote(world.actor, captured["job_id"], expected_epoch=8)
    assert replay["idempotent"] is True
    assert replay["revision_id"] == promoted["revision_id"]
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(CacheInvalidationOutbox).count() == 1
    assert _live(db) == promoted_rows

    denied(lambda: world.service.rollback_latest(world.actor, promoted["revision_id"]))
    assert db.query(EvaluationRevision).one().status == "active"
    assert db.query(CacheInvalidationOutbox).count() == 1
    assert _live(db) == promoted_rows
    assert db.query(EvaluationApplyControl).one().requested_by_user_id == world.admin_id
    assert db.query(EvaluationApplyControl).one().actor_snapshot["role"] == "Admin"

