"""The record resolver and the endpoints that read it answer exactly as before the speed-up.

The baseline (fixtures/record_resolver_baseline.json) was captured from the code before the change, with this
module's build_database and snapshot. The data is synthetic and covers the resolver's paths: a configured team
(Marketing), a legacy rebuild (Outbound), Pre-Approvals IP Elective Dubai's scoped KPIs, OP Dubai, Offshore's new
scoring method, a pinned evaluation, a payload that fails validation and a missing payload. Record ids are
replaced by their order of first appearance, and request and database times and the process-wide cache version are
removed, so the comparison does not depend on random ids, the clock or earlier tests in the same process.
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import test_preapprovals_ip_elective_dubai as elective
import test_preapprovals_offshore_importer as offshore
import test_preapprovals_op_dubai as op_dubai
from config import settings
from models.models import Base, PerformanceRecord, Team, User
from repositories.performance_repository import PerformanceRepository
from services import seeding_service
from services.dashboard_record_service import DashboardRecordService
from services.seeding_service import DatabaseSeeder
from test_runtime_json_storage import _marketing_workbook
from test_upload_header_notices import _ordinary_bytes

BASELINE = Path(__file__).parent / "fixtures" / "record_resolver_baseline.json"
ADMIN_ID = uuid.UUID("f0000000-0000-4000-8000-000000000001")
UUID_TEXT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)?")
PAGE_SECTIONS = "options,comparison,executive_story,priority_insights,people_contribution_analysis,kpi_trend,kpi_diagnosis,tracking_indicators"


def _excel(frame: pd.DataFrame, sheet: str) -> bytes:
    import io

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=sheet, index=False)
    return buffer.getvalue()


def build_database():
    """Synthetic records through the real upload path, then the three edge rows."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    previous = seeding_service.SessionLocal
    seeding_service.SessionLocal = sessionmaker(bind=engine)
    try:
        seeder = DatabaseSeeder()
        seeder.process_uploaded_file("PMS_Marketing.xlsx", _marketing_workbook())
        seeder.process_uploaded_file("PMS_Trend_All.xlsx", _ordinary_bytes())
        seeder.process_uploaded_file("PMS_Trend_All.xlsx", _excel(elective._source_rows(), elective.TEAM))
        seeder.process_uploaded_file("PMS_Trend_All.xlsx", _excel(op_dubai._source_rows(), "Pre-Approvals OP Dubai"))
        offshore_rows = [offshore._row(f"TA-OF-00{index}", date=datetime(2026, 6, 1)) for index in (1, 2)]
        seeder.process_uploaded_file("PMS_Trend_All.xlsx", offshore._workbook(offshore_rows).getvalue())
    finally:
        seeding_service.SessionLocal = previous

    with Session(engine) as db:
        records = (
            db.query(PerformanceRecord).join(Team, PerformanceRecord.team_id == Team.id)
            .order_by(Team.name, PerformanceRecord.month, PerformanceRecord.year)
            .all()
        )
        marketing = [record for record in records if record.team.name == "Marketing"]
        others = [record for record in records if record.team.name != "Marketing"]
        pinned = others[0]
        payload = dict(pinned.record_payload or {})
        first_key = pinned.kpi_values[0].kpi_key
        payload["evaluation_basis"] = {
            "pinned": True,
            "lines": [{"kpi_key": first_key, "label": "Pinned label", "direction": "higher_better", "unit": "%"}],
        }
        pinned.record_payload = payload
        marketing[0].record_payload = {"kpi_values": "not a list"}
        marketing[1].record_payload = None
        db.add(User(id=ADMIN_ID, username="resolver-admin", full_name="Resolver Admin", email="resolver-admin@example.invalid",
                    password_hash="synthetic", role="Admin", is_active=True))
        db.commit()
    return engine


def _canonical(value) -> str:
    """Sorted JSON with record ids in order of first appearance, and no clock times."""
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    text = TIMESTAMP.sub("<time>", text)
    ids: dict[str, str] = {}
    return UUID_TEXT.sub(lambda match: ids.setdefault(match.group(0), f"<id{len(ids)}>"), text)


# Not data: the request time, and the process-wide cache version that any earlier invalidation in the process bumps.
VOLATILE_FIELDS = {"as_of", "data_version"}


def _without_volatile(value):
    if isinstance(value, dict):
        return {key: _without_volatile(item) for key, item in value.items() if key not in VOLATILE_FIELDS}
    if isinstance(value, list):
        return [_without_volatile(item) for item in value]
    return value


def snapshot(engine) -> dict[str, str]:
    """The resolver's records for several filters, and every resolver-backed endpoint, canonicalised."""
    result: dict[str, str] = {}
    with Session(engine) as db:
        service = DashboardRecordService(db)
        for label, filters in (
            ("records: all", {}),
            ("records: Marketing", {"team": "Marketing"}),
            ("records: Outbound", {"team": "Outbound"}),
            ("records: July 2026", {"month": "July", "year": 2026}),
            ("records: one employee", {"employee_id": "SGHD90001"}),
            ("records: analysis", None),
        ):
            records = service.list_analysis_records() if filters is None else service.list_records(**filters)
            result[label] = _canonical([record.model_dump(mode="json") for record in records])

    app = FastAPI()

    @app.middleware("http")
    async def admin(request, call_next):
        request.state.user = {"user_id": str(ADMIN_ID), "role": "Admin", "username": "resolver-admin", "employee_id": ""}
        return await call_next(request)

    from api.routers import router as api_router
    from config.database import get_db

    app.include_router(api_router, prefix="/api")
    factory = sessionmaker(bind=engine)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    previous_flag = settings.PMS_SCOPED_PERFORMANCE_API_ENABLED
    settings.PMS_SCOPED_PERFORMANCE_API_ENABLED = True
    try:
        for label, method, url, body in (
            ("summary records", "GET", "/api/performance/summary-records", None),
            ("summary July", "GET", "/api/performance/summary?period=2026-07", None),
            ("records page July", "GET", "/api/performance/records?period=2026-07&page_size=100&include_total=true", None),
            ("insights full", "GET", "/api/insights/workspace?month=July&year=2026", None),
            ("insights page sections", "GET", f"/api/insights/workspace?month=July&year=2026&sections={PAGE_SECTIONS}", None),
            ("team dashboard priority", "GET", "/api/insights/workspace?month=July&year=2026&team=Marketing&view=priority", None),
            ("employee history", "GET", "/api/performance/employee/SGHD90001", None),
            ("employee profile", "GET", "/api/employee/SGHD90001", None),
            ("report preview", "POST", "/api/reports/preview", {
                "report_type": "executive", "report_name": "Resolver", "start_month": "July", "start_year": 2026,
                "included_sections": ["summary", "details"],
            }),
        ):
            response = client.request(method, url, json=body)
            result[f"endpoint: {label}"] = _canonical({"status": response.status_code, "body": _without_volatile(response.json())})
    finally:
        settings.PMS_SCOPED_PERFORMANCE_API_ENABLED = previous_flag
    return result


def test_the_resolver_and_its_endpoints_answer_exactly_as_the_captured_baseline():
    engine = build_database()
    try:
        current = snapshot(engine)
    finally:
        engine.dispose()
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    assert current.keys() == baseline.keys()
    for label in baseline:
        assert current[label] == baseline[label], label


def test_the_column_rows_resolve_exactly_like_the_orm_rows():
    engine = build_database()
    try:
        with Session(engine) as db:
            service = DashboardRecordService(db)
            repository = PerformanceRepository(db, PerformanceRecord)
            for filters in ({}, {"team": "Outbound"}, {"month": "June", "year": 2026}):
                light = service.list_records(**filters)
                orm = service.resolve_records(repository.get_dashboard_records(**filters))
                assert _canonical([record.model_dump(mode="json") for record in light]) == _canonical(
                    [record.model_dump(mode="json") for record in orm]
                ), filters
    finally:
        engine.dispose()


def test_the_call_memos_do_not_outlive_a_call():
    from services import legacy_kpi_evidence, outbound_period_basis

    engine = build_database()
    try:
        with Session(engine) as db:
            assert DashboardRecordService(db).list_records()
        assert legacy_kpi_evidence._TEXT_MEMO.get() is None
        assert outbound_period_basis._NAME_MEMO.get() is None
    finally:
        engine.dispose()


def test_the_baseline_covers_every_resolver_path():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    all_records = baseline["records: all"]
    for team in ("Marketing", "Outbound", "Pre-Approvals IP Elective Dubai", "Pre-Approvals OP Dubai", "Pre-Approvals IP Offshore"):
        assert f'"team": "{team}"' in all_records, team
    assert '"evaluation_pinned": true' in all_records
    assert all(baseline[label].startswith('{"body"') for label in baseline if label.startswith("endpoint:"))
