"""Data snapshot export and import: round trip, user references, dry run and commit, rollback, refusals, conflicts,
audit entries, no files on disk, and the admin gate. Synthetic data only. The databases are in memory; the snapshot
never touches the disk."""

import dataclasses
import datetime as dt
import json
import tempfile
import uuid
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import data_snapshot as snapshot_router
from config import settings
from config.database import get_db
from models.models import Action, AuditLog, Base, Employee, PerformancePlan, RefreshSession, Team, User
from services import data_snapshot_service as snapshot
from services import seeding_service
from services.seeding_service import DatabaseSeeder
from test_runtime_json_storage import _marketing_workbook

ADMIN = "snapshot-admin"
PLANNER = "snapshot-planner"
ADMIN_PASSWORD_HASH = "$2b$synthetic-admin-hash-for-tests"
PLANNER_PASSWORD_HASH = "$2b$synthetic-planner-hash-for-tests"
SOURCE_IDS = {
    ADMIN: uuid.UUID("c0000000-0000-4000-8000-000000000001"),
    PLANNER: uuid.UUID("c0000000-0000-4000-8000-000000000002"),
}
TARGET_IDS = {
    ADMIN: uuid.UUID("d0000000-0000-4000-8000-000000000001"),
    PLANNER: uuid.UUID("d0000000-0000-4000-8000-000000000002"),
}


def _engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return engine


def _account(username: str, account_id: uuid.UUID, password_hash: str = "$2b$target-hash") -> User:
    return User(
        id=account_id,
        username=username,
        full_name=f"Full name of {username}",
        email=f"{username}@example.invalid",
        password_hash=password_hash,
        role="Admin" if username == ADMIN else "Manager",
        is_active=True,
    )


def _target(*usernames: str):
    """An empty database that holds the given accounts under ids that differ from the source's."""
    engine = _engine()
    with Session(engine) as db:
        for username in usernames:
            db.add(_account(username, TARGET_IDS[username]))
        db.commit()
    return engine


@pytest.fixture
def source(monkeypatch):
    """Seeded through the real upload path, plus two accounts, an action and a plan that name them, and a session."""
    engine = _engine()
    monkeypatch.setattr(seeding_service, "SessionLocal", sessionmaker(bind=engine))
    DatabaseSeeder().process_uploaded_file("PMS_Marketing.xlsx", _marketing_workbook())
    with Session(engine) as db:
        db.add(_account(ADMIN, SOURCE_IDS[ADMIN], ADMIN_PASSWORD_HASH))
        db.add(_account(PLANNER, SOURCE_IDS[PLANNER], PLANNER_PASSWORD_HASH))
        db.flush()
        employee = db.query(Employee).filter(Employee.employee_id == "SGHD90001").one()
        team = db.query(Team).filter(Team.name == "Marketing").one()
        db.add(Action(
            employee_id=employee.id,
            team_id=team.id,
            month="July",
            year=2026,
            action_type="PIP",
            action_text="New plan",
            root_cause_note="cause",
            status="Open",
            is_active=True,
            created_by_user_id=SOURCE_IDS[ADMIN],
        ))
        db.add(PerformancePlan(
            name="Retention plan",
            scope_type="Team",
            team_id=team.id,
            performance_level="Employee",
            period_start=dt.date(2026, 7, 1),
            period_end=dt.date(2026, 9, 30),
            due_date=dt.date(2026, 9, 30),
            owner_user_id=SOURCE_IDS[PLANNER],
            baseline_value=Decimal("50"),
            target_value=Decimal("60"),
            created_by_user_id=SOURCE_IDS[ADMIN],
        ))
        db.add(RefreshSession(
            id=uuid.uuid4(),
            user_id=SOURCE_IDS[ADMIN],
            family_id=uuid.uuid4(),
            token_hash="7" * 64,
            csrf_token_hash="8" * 64,
            expires_at=dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc),
        ))
        db.commit()
    yield engine
    engine.dispose()


def _export_bytes(engine) -> bytes:
    plan = snapshot.plan_export(engine)
    return b"".join(snapshot.stream_export(engine, plan))


def _document(engine) -> dict:
    return snapshot.parse_snapshot(_export_bytes(engine))


def _rows(engine, table_name: str, user_ids: dict | None = None) -> list[dict]:
    """Rows as JSON values. user_ids rewrites the user references, as an import with matching accounts would."""
    table = Base.metadata.tables[table_name]
    user_columns = set(snapshot.user_reference_columns().get(table_name, []))
    with engine.connect() as connection:
        rows = connection.execute(select(table).order_by(*table.primary_key.columns)).mappings().all()
    result = []
    for row in rows:
        values = {column.name: snapshot._to_json(row[column]) for column in table.columns}
        if user_ids is not None:
            for name in user_columns:
                if values[name] is not None:
                    values[name] = user_ids[values[name]]
        result.append(values)
    return result


SOURCE_TO_TARGET = {str(SOURCE_IDS[name]): str(TARGET_IDS[name]) for name in SOURCE_IDS}


def _import(engine, document, *, policy="skip", dry_run=False):
    with Session(engine) as db:
        return snapshot.import_snapshot(db, document, policy=policy, dry_run=dry_run)


def _nothing_imported(engine) -> bool:
    return all(_rows(engine, table.name) == [] for table in snapshot.included_tables())


def _audit_rows(engine, operation: str) -> list[AuditLog]:
    with Session(engine) as db:
        return db.query(AuditLog).filter(AuditLog.table_name == "data_snapshot", AuditLog.operation == operation).all()


def test_round_trip_moves_every_included_table_and_maps_users_by_username(source):
    target = _target(ADMIN, PLANNER)
    report = _import(target, _document(source))

    assert report["committed"] is True
    for table in snapshot.included_tables():
        assert _rows(target, table.name) == _rows(source, table.name, SOURCE_TO_TARGET), table.name
    assert report["user_references"] == {"matched": 3, "cleared": {}, "missing_accounts": []}
    assert sorted(row["username"] for row in _rows(target, "users")) == [ADMIN, PLANNER]
    assert _rows(target, "refresh_sessions") == []


def test_the_export_holds_no_credentials_or_account_details(source):
    body = _export_bytes(source).decode("utf-8")
    document = json.loads(body)

    assert "users" not in document["tables"]
    assert "refresh_sessions" not in document["tables"]
    assert document["user_references"] == [
        {"id": str(SOURCE_IDS[ADMIN]), "username": ADMIN},
        {"id": str(SOURCE_IDS[PLANNER]), "username": PLANNER},
    ]
    for needle in (
        ADMIN_PASSWORD_HASH, PLANNER_PASSWORD_HASH, "password_hash", "token_hash", "csrf_token_hash",
        "7" * 8, "8" * 8, "example.invalid", "Full name of",
    ):
        assert needle not in body, needle


def test_every_cleared_reference_is_nullable():
    for table_name, columns in snapshot.cleared_references().items():
        table = Base.metadata.tables[table_name]
        for name in columns:
            assert table.c[name].nullable, f"{table_name}.{name} is required but points at an excluded table"


def test_a_required_user_reference_without_a_matching_account_blocks_the_import(source):
    document = _document(source)
    target = _target(ADMIN)

    dry = _import(target, document, dry_run=True)
    assert dry["importable"] is False
    assert dry["user_references"]["missing_accounts"] == [PLANNER]
    assert dry["blocking_conflicts"][0]["table"] == "performance_plans"
    assert PLANNER in dry["blocking_conflicts"][0]["reason"]

    with Session(target) as db:
        with pytest.raises(snapshot.SnapshotError) as refused:
            snapshot.import_snapshot(db, document, policy="skip", dry_run=False)
    assert refused.value.status_code == 409
    assert _nothing_imported(target)


def test_an_optional_user_reference_without_a_matching_account_is_cleared_and_reported(source):
    target = _target(PLANNER)

    report = _import(target, _document(source))

    assert report["committed"] is True
    assert report["user_references"]["missing_accounts"] == [ADMIN]
    assert report["user_references"]["cleared"] == {
        "actions.created_by_user_id": 1,
        "performance_plans.created_by_user_id": 1,
    }
    plan = _rows(target, "performance_plans")[0]
    assert plan["owner_user_id"] == str(TARGET_IDS[PLANNER])
    assert plan["created_by_user_id"] is None
    assert [row["created_by_user_id"] for row in _rows(target, "actions")] == [None]


def test_dry_run_and_commit_report_the_same_and_the_dry_run_saves_nothing(source):
    document = _document(source)
    target = _target(ADMIN, PLANNER)

    dry = _import(target, document, dry_run=True)
    assert _nothing_imported(target)
    assert _audit_rows(target, "IMPORT") == []

    committed = _import(target, document, dry_run=False)
    assert dry["dry_run"] is True and dry["committed"] is False
    assert committed["dry_run"] is False and committed["committed"] is True
    assert dry["importable"] is True and committed["importable"] is True
    for key in ("tables", "totals", "user_references", "cleared_references", "blocking_conflict_count"):
        assert dry[key] == committed[key], key


@pytest.mark.parametrize("corruption", ["missing_employee", "malformed_uuid", "wrong_count"])
def test_a_broken_file_rolls_back_every_table_and_writes_no_audit(source, corruption):
    document = _document(source)
    if corruption == "missing_employee":
        document["tables"]["performance_records"]["rows"][0]["employee_id"] = str(uuid.uuid4())
    elif corruption == "malformed_uuid":
        document["tables"]["teams"]["rows"][0]["id"] = "not-a-uuid"
    else:
        document["tables"]["kpi_values"]["count"] += 1
    target = _target(ADMIN, PLANNER)

    with Session(target) as db:
        with pytest.raises(snapshot.SnapshotError) as refused:
            snapshot.import_snapshot(db, document, policy="skip", dry_run=False)
    assert refused.value.status_code == 422
    assert _nothing_imported(target)
    assert _audit_rows(target, "IMPORT") == []


def test_a_schema_version_mismatch_is_refused(source):
    raw = json.loads(_export_bytes(source))
    raw["schema_version"] = snapshot.SCHEMA_VERSION + 1

    with pytest.raises(snapshot.SnapshotError) as refused:
        snapshot.parse_snapshot(json.dumps(raw).encode("utf-8"))
    assert refused.value.status_code == 422
    assert "not supported" in refused.value.detail


def test_a_database_revision_mismatch_is_refused_and_nothing_is_written(source):
    document = _document(source)
    document["database_revision"] = "0001_some_other_revision"
    target = _target(ADMIN, PLANNER)

    with Session(target) as db:
        with pytest.raises(snapshot.SnapshotError) as refused:
            snapshot.import_snapshot(db, document, policy="skip", dry_run=False)
    assert refused.value.status_code == 409
    assert _nothing_imported(target)


def test_existing_ids_are_skipped_or_replaced_by_the_policy_chosen_for_the_whole_import(source):
    target = _target(ADMIN, PLANNER)
    _import(target, _document(source))
    document = _document(source)
    team_count = len(document["tables"]["teams"]["rows"])
    for row in document["tables"]["teams"]["rows"]:
        if row["name"] == "Marketing":
            row["display_name"] = "Marketing (renamed)"

    skipped = _import(target, document, policy="skip", dry_run=True)
    assert skipped["tables"]["teams"]["existing_ids"] == team_count
    assert skipped["tables"]["teams"]["skipped"] == team_count
    assert skipped["tables"]["teams"]["replaced"] == 0
    _import(target, document, policy="skip")
    assert [row["display_name"] for row in _rows(target, "teams") if row["name"] == "Marketing"] != ["Marketing (renamed)"]

    replaced = _import(target, document, policy="replace")
    assert replaced["tables"]["teams"]["replaced"] == team_count
    assert replaced["tables"]["teams"]["skipped"] == 0
    assert [row["display_name"] for row in _rows(target, "teams") if row["name"] == "Marketing"] == ["Marketing (renamed)"]


def test_a_duplicate_employee_month_inside_the_snapshot_blocks_the_import(source):
    document = _document(source)
    original = document["tables"]["performance_records"]["rows"][0]
    document["tables"]["performance_records"]["rows"].append(dict(original, id=str(uuid.uuid4())))
    document["tables"]["performance_records"]["count"] += 1
    target = _target(ADMIN, PLANNER)

    dry = _import(target, document, policy="replace", dry_run=True)
    assert dry["importable"] is False
    assert dry["blocking_conflict_count"] == 1
    assert dry["blocking_conflicts"][0]["table"] == "performance_records"
    assert _nothing_imported(target)

    with Session(target) as db:
        with pytest.raises(snapshot.SnapshotError) as refused:
            snapshot.import_snapshot(db, document, policy="replace", dry_run=False)
    assert refused.value.status_code == 409
    assert _nothing_imported(target)


def test_a_business_key_held_by_an_existing_row_under_another_id_blocks_the_import(source):
    target = _target(ADMIN, PLANNER)
    _import(target, _document(source))
    document = _document(source)
    original = document["tables"]["performance_records"]["rows"][0]
    document["tables"]["performance_records"]["rows"][0] = dict(original, id=str(uuid.uuid4()))
    before = _rows(target, "performance_records")

    report = _import(target, document, policy="skip", dry_run=True)
    assert report["importable"] is False
    assert report["blocking_conflicts"][0]["reason"].startswith("the same business key is already held")
    assert _rows(target, "performance_records") == before


def test_export_and_import_leave_no_file_anywhere(source, tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.chdir(scratch)
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    body = _export_bytes(source)
    target = _target(ADMIN, PLANNER)
    _import(target, snapshot.parse_snapshot(body))

    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_the_export_is_streamed_in_chunks_and_parses_as_one_document(source):
    plan = snapshot.plan_export(source)
    chunks = list(snapshot.stream_export(source, plan))
    document = json.loads(b"".join(chunks))

    assert len(chunks) > len(snapshot.included_tables())
    assert document["format"] == snapshot.FORMAT
    assert document["database_revision"] is None
    for table in snapshot.included_tables():
        assert document["tables"][table.name]["count"] == len(document["tables"][table.name]["rows"])


def test_an_export_whose_table_changes_after_planning_is_cut_short(source):
    plan = snapshot.plan_export(source)
    counts = dict(plan.counts)
    counts["teams"] += 1
    changed = dataclasses.replace(plan, counts=counts)

    with pytest.raises(RuntimeError, match="teams changed"):
        b"".join(snapshot.stream_export(source, changed))


def _client(engine) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def fake_authentication(request, call_next):
        role = request.headers.get("X-Test-Role")
        if role:
            request.state.user = {"user_id": str(SOURCE_IDS[ADMIN]), "role": role}
        return await call_next(request)

    app.include_router(snapshot_router.router, prefix="/api")
    factory = sessionmaker(bind=engine)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _upload(body: bytes) -> dict:
    return {"file": ("snapshot.json", body, "application/json")}


@pytest.mark.parametrize("role", ["Manager", "General Manager", "Performance Team", "Executive", "Viewer"])
def test_non_admins_get_403_for_export_and_import(source, role):
    client = _client(source)
    body = _export_bytes(source)
    headers = {"X-Test-Role": role}

    assert client.get("/api/settings/data-snapshot/export", headers=headers).status_code == 403
    assert client.post("/api/settings/data-snapshot/import/dry-run?policy=skip", files=_upload(body), headers=headers).status_code == 403
    assert client.post("/api/settings/data-snapshot/import?policy=skip", files=_upload(body), headers=headers).status_code == 403


def test_unauthenticated_callers_get_401(source):
    assert _client(source).get("/api/settings/data-snapshot/export").status_code == 401


def test_admin_export_streams_a_download_and_writes_an_audit_entry(source):
    before = len(_audit_rows(source, "EXPORT"))

    response = _client(source).get("/api/settings/data-snapshot/export", headers={"X-Test-Role": "Admin"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    document = json.loads(response.content)
    assert document["format"] == snapshot.FORMAT
    entries = _audit_rows(source, "EXPORT")
    assert len(entries) == before + 1
    assert entries[-1].new_values["tables"]["performance_records"] == len(document["tables"]["performance_records"]["rows"])
    assert entries[-1].new_values["user_references"] == 2
    assert entries[-1].performed_by_user_id == SOURCE_IDS[ADMIN]


def test_admin_dry_run_saves_nothing_and_commit_writes_an_import_audit_entry(source):
    target = _target(ADMIN, PLANNER)
    client = _client(target)
    body = _export_bytes(source)
    headers = {"X-Test-Role": "Admin"}

    dry = client.post("/api/settings/data-snapshot/import/dry-run?policy=skip", files=_upload(body), headers=headers)
    assert dry.status_code == 200
    assert dry.json()["data"]["importable"] is True
    assert _nothing_imported(target)
    assert _audit_rows(target, "IMPORT") == []

    committed = client.post("/api/settings/data-snapshot/import?policy=skip", files=_upload(body), headers=headers)
    assert committed.status_code == 200
    assert committed.json()["data"]["committed"] is True
    entries = _audit_rows(target, "IMPORT")
    assert len(entries) == 1
    assert entries[0].new_values["totals"]["new"] == committed.json()["data"]["totals"]["new"]
    assert entries[0].new_values["user_references_matched"] == 3


def test_a_blocked_dry_run_returns_its_conflicts_over_http(source):
    target = _target(ADMIN)
    response = _client(target).post(
        "/api/settings/data-snapshot/import/dry-run?policy=skip",
        files=_upload(_export_bytes(source)),
        headers={"X-Test-Role": "Admin"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["importable"] is False
    assert data["user_references"]["missing_accounts"] == [PLANNER]
    assert data["blocking_conflicts"][0]["table"] == "performance_plans"
    assert isinstance(next(iter(data["blocking_conflicts"][0]["id"].values())), str)
    assert _nothing_imported(target)


def test_a_blocked_commit_is_refused_with_409_over_http(source):
    target = _target(ADMIN)
    response = _client(target).post(
        "/api/settings/data-snapshot/import?policy=skip",
        files=_upload(_export_bytes(source)),
        headers={"X-Test-Role": "Admin"},
    )

    assert response.status_code == 409
    assert _nothing_imported(target)


def test_an_oversized_upload_is_refused_with_413(source, monkeypatch):
    monkeypatch.setattr(settings, "DATA_SNAPSHOT_MAX_BYTES", 1024)

    response = _client(source).post(
        "/api/settings/data-snapshot/import?policy=skip",
        files=_upload(_export_bytes(source)),
        headers={"X-Test-Role": "Admin"},
    )

    assert response.status_code == 413


def test_an_unknown_conflict_policy_is_refused(source):
    with pytest.raises(snapshot.SnapshotError) as refused:
        _import(_target(ADMIN, PLANNER), _document(source), policy="merge")
    assert refused.value.status_code == 422
