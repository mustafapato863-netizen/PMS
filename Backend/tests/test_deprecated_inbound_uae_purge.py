"""Tests for permanent purging of the deprecated Inbound UAE team and related records."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from models.models import (
    Action,
    Base,
    Employee,
    EvaluationRevision,
    EvaluationScope,
    GradeThreshold,
    KPIValue,
    OnboardingState,
    PerformancePlan,
    PerformanceRecord,
    ReportDraft,
    Team,
    TeamConfigurationVersion,
    TeamKPIConfig,
    UploadLog,
    User,
    UserTeamAssignment,
)
from services.deprecated_team_purge import purge_deprecated_inbound_uae


def test_purge_deprecated_inbound_uae_removes_team_and_related_records_preserving_egypt():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as db:
        admin = User(
            id=uuid.uuid4(),
            username="purge_admin",
            email="purge-admin@example.com",
            password_hash="hashed",
            role="Admin",
            is_active=True,
        )
        inbound_egy = Team(
            id=uuid.uuid4(),
            name="Inbound",
            db_name="Inbound",
            display_name="Inbound",
            region="EGY",
            team_level="employee",
            is_active=True,
        )
        inbound_uae = Team(
            id=uuid.uuid4(),
            name="inbound_uae",
            db_name="Inbound UAE",
            display_name="Inbound UAE",
            region="UAE",
            team_level="employee",
            is_active=True,
        )
        db.add_all([admin, inbound_egy, inbound_uae])
        db.flush()

        emp_egy = Employee(
            id=uuid.uuid4(),
            employee_id="EGY-1",
            name="Egypt Agent",
            team_id=inbound_egy.id,
            region="EGY",
        )
        emp_uae = Employee(
            id=uuid.uuid4(),
            employee_id="UAE-1",
            name="UAE Agent",
            team_id=inbound_uae.id,
            region="UAE",
        )
        db.add_all([emp_egy, emp_uae])
        db.flush()

        upload_uae = UploadLog(
            id=uuid.uuid4(),
            team_id=inbound_uae.id,
            month="March",
            year=2026,
            uploaded_by_user_id=admin.id,
            record_count=1,
            status="success",
        )
        db.add(upload_uae)
        db.flush()

        rec_egy = PerformanceRecord(
            id=uuid.uuid4(),
            year=2026,
            month="March",
            employee_id=emp_egy.id,
            team_id=inbound_egy.id,
            performance_level="Employee",
            region="EGY",
            score=90,
            grade="B",
            status="Meets",
        )
        rec_uae = PerformanceRecord(
            id=uuid.uuid4(),
            year=2026,
            month="March",
            employee_id=emp_uae.id,
            team_id=inbound_uae.id,
            upload_id=upload_uae.id,
            performance_level="Employee",
            region="UAE",
            score=78,
            grade="D",
            status="Below",
        )
        db.add_all([rec_egy, rec_uae])
        db.flush()

        db.add_all([
            KPIValue(
                record_id=rec_egy.id,
                record_year=2026,
                kpi_key="booking_cr",
                actual_value=0.35,
                target_value=0.35,
                achievement_ratio=1.0,
                weight_applied=1.0,
                contribution=1.0,
            ),
            KPIValue(
                record_id=rec_uae.id,
                record_year=2026,
                kpi_key="booking_cr",
                actual_value=0.22,
                target_value=0.35,
                achievement_ratio=0.63,
                weight_applied=1.0,
                contribution=0.63,
            ),
            TeamKPIConfig(
                team_id=inbound_uae.id,
                kpi_key="booking_cr",
                kpi_label="Booking CR",
                weight=1.0,
                actual_col="actual_booking_cr",
                target_col="target_booking_cr",
            ),
            GradeThreshold(team_id=inbound_uae.id, grade_a=95, grade_b=90, grade_c=80, grade_d=70),
            OnboardingState(team_id=inbound_uae.id, current_step=3, status="completed"),
            UserTeamAssignment(user_id=admin.id, team_id=inbound_uae.id, access_level="admin", assigned_by="purge_admin"),
            Action(
                id=uuid.uuid4(),
                employee_id=emp_uae.id,
                team_id=inbound_uae.id,
                month="March",
                year=2026,
                action_type="Coaching",
                action_text="Coach UAE agent",
                status="Open",
            ),
            PerformancePlan(
                id=uuid.uuid4(),
                name="Inbound UAE Recovery",
                scope_type="Team",
                team_id=inbound_uae.id,
                performance_level="Employee",
                region="UAE",
                period_start=date(2026, 3, 1),
                period_end=date(2026, 3, 31),
                due_date=date(2026, 4, 15),
                owner_user_id=admin.id,
                baseline_value=70,
                target_value=85,
            ),
            EvaluationScope(
                id=uuid.uuid4(),
                team_id=inbound_uae.id,
                team_key="inbound_uae",
                display_name="Inbound UAE",
                performance_level="Employee",
                position_name="",
                readiness="supported",
                history_note="Legacy scope",
                source_kind="config",
            ),
        ])
        ver_uae = TeamConfigurationVersion(
            id=uuid.uuid4(),
            team_id=inbound_uae.id,
            version_number=1,
            status="approved",
            effective_month="March",
            effective_year=2026,
            effective_from_month=3,
            effective_from_year=2026,
            effective_until_month=3,
            effective_until_year=2026,
            performance_level="Employee",
            position_name="",
            config_snapshot={"kpis": []},
            config_checksum="a" * 64,
            published_at=datetime(2026, 3, 15, tzinfo=timezone.utc),
        )
        db.add(ver_uae)
        db.flush()

        db.add(
            EvaluationRevision(
                id=uuid.uuid4(),
                team_id=inbound_uae.id,
                performance_level="Employee",
                position_name="",
                year=2026,
                month=3,
                version_id=ver_uae.id,
                status="active",
                prior_snapshot={},
                applied_snapshot={},
            )
        )
        db.add_all([
            ReportDraft(
                id=uuid.uuid4(),
                name="Inbound UAE Report",
                report_type="team",
                owner_user_id=admin.id,
                primary_period_month="March",
                primary_period_year=2026,
                scope_json={"team": "Inbound UAE"},
                definition_json={},
                management_commentary_json={},
            ),
            ReportDraft(
                id=uuid.uuid4(),
                name="Executive Summary",
                report_type="executive",
                owner_user_id=admin.id,
                primary_period_month="June",
                primary_period_year=2026,
                scope_json={"region": "ALL"},
                definition_json={"note": "historical"},
                management_commentary_json={},
            ),
        ])
        inbound_uae_hex = inbound_uae.id.hex
        inbound_egy_hex = inbound_egy.id.hex
        db.commit()

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE team_onboarding_drafts ("
                "id TEXT PRIMARY KEY, "
                "published_team_id TEXT, "
                "status TEXT, "
                "team_identity TEXT, "
                "workbook_metadata TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO team_onboarding_drafts "
                "(id, published_team_id, status, team_identity, workbook_metadata) "
                "VALUES (:id, :tid, :st, :ti, :wm)"
            ),
            [
                {
                    "id": str(uuid.uuid4()),
                    "tid": inbound_uae_hex,
                    "st": "published",
                    "ti": json.dumps({"team": "Inbound UAE"}),
                    "wm": json.dumps({"sheets": ["Inbound UAE"]}),
                },
                {
                    "id": str(uuid.uuid4()),
                    "tid": inbound_egy_hex,
                    "st": "published",
                    "ti": json.dumps({"team": "Inbound"}),
                    "wm": json.dumps({"sheets": ["Inbound", "Inbound UAE"]}),
                },
            ],
        )

    with engine.begin() as conn:
        counts = purge_deprecated_inbound_uae(conn)
        assert counts["teams"] == 1
        assert counts["employees"] == 1
        assert counts["performance_records"] == 1
        assert counts["kpi_values"] == 1
        assert counts["actions"] == 1
        assert counts["evaluation_revisions"] == 1
        assert counts["team_configuration_versions"] == 1
        assert counts["report_drafts"] == 1
        assert counts["team_onboarding_drafts"] == 1

        # Re-running is idempotent and leaves Inbound (EGY) + unrelated drafts intact.
        assert purge_deprecated_inbound_uae(conn) == {}
        assert conn.execute(text("SELECT name FROM teams")).scalars().all() == ["Inbound"]
        assert conn.execute(text("SELECT employee_id FROM employees")).scalars().all() == ["EGY-1"]
        assert conn.execute(text("SELECT count(*) FROM performance_records")).scalar() == 1
        assert conn.execute(text("SELECT name FROM report_drafts")).scalars().all() == ["Executive Summary"]
        assert conn.execute(text("SELECT count(*) FROM team_onboarding_drafts")).scalar() == 1
