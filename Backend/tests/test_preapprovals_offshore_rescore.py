"""Rescore command for Pre-Approvals IP Offshore: dry run, apply, backup, restore, eligibility (synthetic data)."""
from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import Employee, KPIValue, PerformanceRecord, Team, TeamConfigurationVersion
from scripts import rescore_preapprovals_offshore as rescore
from services.preapprovals_offshore_scoring import NEW_METHOD_ID, OffshoreCounts, score_counts

OFFSHORE = rescore.TEAM_NAME
CODING = "Coding"


def _raw(*, policy=2, assigned=100, approved=90, rejected=5, within_48h=85, submitted=200, errors=2):
    raw = {
        "AssignedRequest": str(assigned),
        "ApprovedRequests": str(approved),
        "RejectedRequests": str(rejected),
        "ApprovalWithin48HR": str(within_48h),
        "SubmittedClaims": str(submitted),
        "ErrosClaims": str(errors),
        "IPInitialRejection%": "0.05",
        "T.Rejection%": "0.03",
    }
    if policy is not None:
        raw["PolicyRej"] = str(policy)
    return raw


def _kpi(record, year, key, actual, target, achievement, weight, contribution):
    return KPIValue(
        record_id=record.id,
        record_year=year,
        kpi_key=key,
        actual_value=Decimal(str(actual)),
        target_value=Decimal(str(target)),
        achievement_ratio=Decimal(str(achievement)),
        weight_applied=Decimal(str(weight)),
        contribution=Decimal(str(contribution)),
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed(session):
    offshore = Team(id=uuid.uuid4(), name=OFFSHORE, db_name=OFFSHORE, display_name=OFFSHORE, region="EGY", team_level="employee", is_active=True)
    coding = Team(id=uuid.uuid4(), name=CODING, db_name="coding", display_name=CODING, region="UAE", team_level="employee", is_active=True)
    session.add_all([offshore, coding])
    session.flush()
    people = {
        "TA-OF-101": offshore, "TA-OF-102": offshore, "TA-OF-103": offshore, "TA-OF-104": offshore,
        "TA-OF-105": offshore, "TA-CD-901": coding,
    }
    employees = {}
    for code, team in people.items():
        employees[code] = Employee(id=uuid.uuid4(), employee_id=code, name=f"Test {code}", team_id=team.id, region="EGY")
    session.add_all(employees.values())
    session.flush()

    def record(code, team, year, month, raw, score, grade, *, kpis=None, level="Employee"):
        payload = {"raw_data": raw, "evaluation": {"score": score, "grade": grade}, "kpi_values": []}
        row = PerformanceRecord(
            id=uuid.uuid4(), year=year, month=month, employee_id=employees[code].id, team_id=team.id,
            performance_level=level, region="EGY", score=Decimal(str(score)), grade=grade, status="Below",
            record_payload=payload,
        )
        session.add(row)
        session.flush()
        for kpi in kpis or []:
            session.add(_kpi(row, year, *kpi))
        session.flush()
        return row

    old_kpis = [
        ("Rejection", 0.05, 0.03, 0.6, 0.5, 0.3),
        ("InitialError", 0.02, 0.03, 1.0, 0.2, 0.2),
        ("Submission", 0.94, 0.90, 1.0, 0.3, 0.3),
    ]
    rows = {
        # Scored from June 2026 (old stored values, PolicyRej present).
        "june": record("TA-OF-101", offshore, 2026, "June", _raw(), 70.0, "D", kpis=old_kpis),
        "july": record("TA-OF-102", offshore, 2026, "July", _raw(policy=4, rejected=8), 60.0, "E", kpis=old_kpis),
        # Refused: August has an approved monthly version.
        "august": record("TA-OF-103", offshore, 2026, "August", _raw(), 70.0, "D", kpis=old_kpis),
        # Skipped: September record without PolicyRej.
        "september": record("TA-OF-104", offshore, 2026, "September", _raw(policy=None), 70.0, "D", kpis=old_kpis),
        # Never touched: before the effective period, another team, another year.
        "may": record("TA-OF-105", offshore, 2026, "May", _raw(), 80.0, "C", kpis=old_kpis),
        "coding_june": record("TA-CD-901", coding, 2026, "June", _raw(), 90.0, "B", kpis=old_kpis, level="Employee"),
        "last_year": record("TA-OF-105", offshore, 2025, "December", _raw(), 75.0, "C", kpis=old_kpis),
    }
    session.add(TeamConfigurationVersion(
        id=uuid.uuid4(), team_id=offshore.id, version_number=1, status="approved", effective_month="August",
        effective_year=2026, config_snapshot={}, config_checksum="0" * 64, effective_from_month=8,
        effective_from_year=2026, effective_until_month=8, effective_until_year=2026,
        performance_level="Employee", position_name="", is_active=True,
        published_at=datetime.now(timezone.utc),
    ))
    session.commit()
    return rows


def _snapshot(session):
    records = sorted(
        (str(row.id), row.year, str(row.score), row.grade, row.status, json.dumps(row.record_payload, sort_keys=True, default=str))
        for row in session.query(PerformanceRecord).all()
    )
    kpis = sorted(
        (str(row.id), str(row.record_id), row.record_year, row.kpi_key, str(row.actual_value), str(row.target_value),
         str(row.achievement_ratio), str(row.weight_applied), str(row.contribution))
        for row in session.query(KPIValue).all()
    )
    return records, kpis


def _run(session, **overrides):
    options = dict(year=2026, months=None, apply=False, report=None, backup=None, treat_missing_policy=False)
    options.update(overrides)
    return rescore.run(session, **options)


def _csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _by_month(rows):
    return {row["month"]: row for row in rows}


def _expected(raw_policy=2, rejected=5, assigned=100, approved=90, within_48h=85, submitted=200, errors=2):
    return score_counts(OffshoreCounts(
        assigned=float(assigned), approved=float(approved), rejected=float(rejected), policy_rejected=float(raw_policy),
        approved_within_48h=float(within_48h), submitted=float(submitted), errors=float(errors),
    ))


def test_dry_run_writes_nothing_and_the_report_matches_the_plan(db, tmp_path):
    _seed(db)
    before = _snapshot(db)
    report = tmp_path / "dry_run.csv"

    _run(db, report=report)
    db.rollback()

    assert _snapshot(db) == before
    rows = _by_month(_csv(report))
    assert set(rows) == {"June", "July", "August", "September"}  # May, 2025 and Coding are out of scope
    assert rows["June"]["status"] == "rescored"
    assert rows["July"]["status"] == "rescored"
    assert rows["August"]["status"] == "refused"
    assert rows["September"]["status"] == "skipped"
    assert "PolicyRej" in rows["September"]["reason"]
    june_expected = _expected()
    assert float(rows["June"]["new_score"]) == pytest.approx(june_expected.score)
    assert rows["June"]["new_grade"] == june_expected.grade
    assert float(rows["June"]["old_score"]) == pytest.approx(70.0)
    assert float(rows["June"]["new_rejection_actual"]) == pytest.approx(0.03)
    assert float(rows["June"]["new_rejection_target"]) == pytest.approx(0.01)
    assert float(rows["June"]["old_rejection_actual"]) == pytest.approx(0.05)
    assert float(rows["June"]["old_rejection_target"]) == pytest.approx(0.03)
    assert rows["June"]["new_policy_rejection_weight"] in ("0", "0.0")


def test_apply_changes_exactly_the_expected_rows_and_is_idempotent(db, tmp_path):
    rows = _seed(db)
    before = _snapshot(db)
    backup = tmp_path / "backup.json"

    summary = _run(db, apply=True, backup=backup, report=tmp_path / "applied.csv")
    db.commit()

    assert summary["counts"]["rescored"] == 2
    assert summary["backup_records"] == 2
    assert summary["applied"]["records"] == 2

    june = db.get(PerformanceRecord, (rows["june"].id, 2026))
    july = db.get(PerformanceRecord, (rows["july"].id, 2026))
    assert float(june.score) == pytest.approx(_expected().score)
    assert june.grade == _expected().grade
    assert june.record_payload["raw_data"]["ScoringMethod"] == NEW_METHOD_ID
    assert june.record_payload["raw_data"]["IPInitialRejection%"] == "0.05"  # existing raw key kept
    assert float(july.score) == pytest.approx(_expected(raw_policy=4, rejected=8).score)
    policy_rows = db.query(KPIValue).filter(KPIValue.record_id == june.id, KPIValue.kpi_key == "PolicyRejection").all()
    assert len(policy_rows) == 1 and float(policy_rows[0].weight_applied) == 0.0

    # Refused, skipped, other team, other years: byte-for-byte unchanged.
    after = _snapshot(db)
    for key in ("august", "september", "may", "coding_june", "last_year"):
        assert [item for item in after[0] if item[0] == str(rows[key].id)] == [item for item in before[0] if item[0] == str(rows[key].id)]
    assert "PolicyRejection" not in {row.kpi_key for row in db.query(KPIValue).filter(KPIValue.record_id == rows["may"].id)}

    # Second run: nothing left to change, nothing to back up.
    second = _run(db, apply=True, backup=tmp_path / "backup2.json", report=tmp_path / "again.csv")
    db.commit()
    assert second["counts"]["rescored"] == 0
    assert second["backup_records"] == 0
    assert second["applied"]["records"] == 0


def test_restore_returns_every_touched_row_to_its_previous_bytes(db, tmp_path):
    _seed(db)
    before = _snapshot(db)
    backup = tmp_path / "backup.json"

    _run(db, apply=True, backup=backup, report=tmp_path / "applied.csv")
    db.commit()
    assert _snapshot(db) != before

    result = rescore.restore(db, backup)
    db.commit()

    assert result["restored"]["records"] == 2
    assert _snapshot(db) == before


def test_restore_refuses_a_backup_it_does_not_recognise(db, tmp_path):
    bogus = tmp_path / "not_a_backup.json"
    bogus.write_text(json.dumps({"format": "something_else", "version": 1, "records": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="not a preapprovals_offshore_rescore_backup"):
        rescore.restore(db, bogus)


def test_apply_refuses_to_overwrite_an_existing_backup(db, tmp_path):
    _seed(db)
    backup = tmp_path / "backup.json"
    backup.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError):
        _run(db, apply=True, backup=backup, report=tmp_path / "applied.csv")
    db.rollback()
    assert backup.read_text(encoding="utf-8") == "{}"


def test_record_without_policy_rej_is_reported_and_only_scored_with_the_explicit_flag(db, tmp_path):
    _seed(db)
    report = tmp_path / "flagged.csv"

    _run(db, report=report, treat_missing_policy=True)
    db.rollback()

    row = _by_month(_csv(report))["September"]
    assert row["status"] == "rescored"
    assert "PolicyRej missing" in row["flags"]


def test_earlier_months_are_refused_with_a_clear_message():
    with pytest.raises(rescore.EligibilityError, match="before the effective period June 2026"):
        rescore.parse_months(["May"], 2026)
    with pytest.raises(rescore.EligibilityError, match="before the effective period June 2026"):
        rescore.parse_months(["June", "April"], 2026)


def test_june_and_later_months_are_accepted_and_earlier_years_are_refused():
    assert rescore.parse_months(["June"], 2026) == [6]
    assert rescore.parse_months(["7", "August"], 2026) == [7, 8]
    with pytest.raises(rescore.EligibilityError, match="before the effective period"):
        rescore.parse_months(["December"], 2025)


def test_the_command_refuses_before_connecting_when_asked_for_may(tmp_path, capsys):
    code = rescore.main(["--months", "May", "--report", str(tmp_path / "x.csv")])

    assert code == 2
    assert "before the effective period June 2026" in capsys.readouterr().out
    assert not (tmp_path / "x.csv").exists()


def test_default_run_does_not_include_may(db, tmp_path):
    _seed(db)
    report = tmp_path / "default.csv"

    _run(db, report=report)
    db.rollback()

    assert "May" not in _by_month(_csv(report))


def test_apply_requires_a_backup_path(tmp_path):
    with pytest.raises(SystemExit):
        rescore.main(["--apply", "--report", str(tmp_path / "x.csv")])


def test_approved_monthly_version_refuses_the_whole_month(db, tmp_path):
    rows = _seed(db)
    before_august = db.get(PerformanceRecord, (rows["august"].id, 2026))
    before_score = before_august.score

    summary = _run(db, apply=True, backup=tmp_path / "b.json", report=tmp_path / "r.csv")
    db.commit()

    assert summary["counts"]["refused"] == 1
    assert db.get(PerformanceRecord, (rows["august"].id, 2026)).score == before_score
