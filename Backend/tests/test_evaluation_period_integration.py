"""Exact-month Outbound catalog, approved-upload gate, schema readiness, and team locks.

Callable contract exercised here. Omit ``year`` and ``month`` and Outbound stays
blocked. Pass both and only July 2026 and August 2026 Outbound Employee (empty
position) can be admitted. Coding and Submission ignore the period.

    calculation_for(display, level, position, config, importers=None, year=None, month=None) -> CapabilityDecision
    catalog.decision_for(scope, year=None, month=None) -> CapabilityDecision
    catalog.baseline_lines(scope, year=None, month=None) -> list[dict]
    catalog.serialize(scope, year=None, month=None) -> dict
    catalog.reconcile_period_lines(scope, year, month, copied_lines) -> dict
    require_approved_capability(version, *, team_name, config, year=None, month=None) -> CapabilityDecision
    lock_team_rows(db, team_ids) -> list[Team]
    schema_ready(db) -> bool
    assert_schema(db) -> None
    overlay_pinned_kpis(db, team_name, level, position, year, month, kpis, records=None, *, preview_approved=False) -> list[dict]

``reconcile_period_lines`` returns ``lines``, ``diagnostics``, ``template_changed``,
``preserved_values``, ``source_baseline`` (the destination's canonical template),
``blocked``, ``period_status``, and ``weights_total``. ``source_baseline`` is the
audited destination month, not the copied lines.

``serialize(scope)`` keeps Outbound blocked. ``serialize(scope, 2026, 8)`` sets
top-level ``readiness`` to ``supported`` and ``supported`` to true.
``global_readiness`` and ``global_supported`` keep the stored catalog result.
September stays blocked.

``schema_ready`` returns false for a legacy database with no monthly marker.
Once monthly objects are activated, both ``schema_ready`` and ``assert_schema``
require the full history schema, including ``evaluation_revisions``. A missing
table or guard raises ``SchemaIncomplete`` (503) with no approved rows required.
PostgreSQL inspection SQL targets ``public``. ``overlay_pinned_kpis`` with
``records`` omitted does not query. ``preview_approved=True`` is the only
settings preview. Historical management runtime config passes already-authorized
records and does not use that preview.
"""
from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects.postgresql import dialect as PgDialect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from config.loader import load_team_config
from models.evaluation_history_schema import SQLITE_VERSION_TRIGGERS
from models.models import (
    Employee as DBEmployee,
    EvaluationRevision,
    EvaluationScope,
    KPIValue,
    PerformanceRecord as DBPerformanceRecord,
    Team,
    TeamConfigurationVersion,
    TeamKPIConfig,
)
from models.schemas import Employee, EvaluationData, PerformanceRecord
from services.evaluation.access import EvaluationError, SchemaIncomplete, TargetConflict
from services.evaluation.capabilities import decide
from services.evaluation.catalog import EvaluationCatalog, calculation_for
from services.evaluation.resolver import (
    _column_names,
    _table_names,
    _team_lock_query,
    approved_version,
    assert_schema,
    lock_team_rows,
    overlay_pinned_kpis,
    require_approved_capability,
    schema_ready,
    score_basis,
)
from services.evaluation.scoring import conflicts_for
from services.kpi_service import DEFAULT_WEIGHTS
from services.outbound_period_basis import (
    SOURCE_TARGETS,
    OutboundUnsupportedApprovedBinding,
    period_capability,
)
from services.seeding_service import DatabaseSeeder


def _session(*tables, full: bool = False):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    if full:
        Base.metadata.create_all(bind=engine)
    else:
        Base.metadata.create_all(bind=engine, tables=list(tables))
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def _close(db) -> None:
    db.close()


def _team(name: str, *, region: str = "EGY", level: str = "employee", db_name: str | None = None, display: str | None = None, team_id=None) -> Team:
    return Team(
        id=team_id or uuid.uuid4(),
        name=name,
        db_name=db_name or name,
        display_name=display or name,
        region=region,
        team_level=level,
        is_active=True,
    )


def _scope(display: str, level: str = "Employee", position: str = "", readiness: str = "blocked") -> EvaluationScope:
    return EvaluationScope(
        id=uuid.uuid4(),
        team_key=display.casefold(),
        display_name=display,
        performance_level=level,
        position_name=position,
        readiness=readiness,
        block_reason=None,
        history_note="Historical scores stay as saved.",
        ambiguous_kpis=[],
        importer_name=None,
        policy_family="unsupported",
        source_kind="file",
    )


def _version(month: int, lines: list[dict], *, policy: str | None = "employee_ratio", level: str = "Employee", position: str = "", year: int = 2026, team_id=None) -> TeamConfigurationVersion:
    snapshot = {"lines": lines, "grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65}}
    if policy is not None:
        snapshot["policy"] = policy
    from services.evaluation.periods import month_name

    return TeamConfigurationVersion(
        id=uuid.uuid4(),
        team_id=team_id or uuid.uuid4(),
        version_number=1,
        status="approved",
        effective_month=month_name(month),
        effective_year=year,
        config_snapshot=snapshot,
        config_checksum="c" * 64,
        effective_from_month=month,
        effective_from_year=year,
        effective_until_month=month,
        effective_until_year=year,
        performance_level=level,
        position_name=position,
        published_at=datetime.now(timezone.utc),
        actor_created_snapshot={"state": "unknown"},
        actor_published_snapshot={"state": "unknown"},
    )


def _scored(lines: list[dict]) -> dict[str, dict]:
    return {line["kpi_key"]: line for line in lines if float(line.get("weight") or 0) > 0}


def _outbound_config() -> dict:
    return load_team_config("Outbound")


def _catalog() -> EvaluationCatalog:
    return EvaluationCatalog(None)


# ---------------------------------------------------------------- contract


def test_callable_contract_keeps_period_arguments_optional():
    assert list(inspect.signature(calculation_for).parameters) == [
        "display", "level", "position", "config", "importers", "year", "month",
    ]
    decision_params = list(inspect.signature(EvaluationCatalog.decision_for).parameters)
    assert decision_params == ["self", "scope", "year", "month"]
    assert list(inspect.signature(EvaluationCatalog.baseline_lines).parameters)[1:] == ["scope", "year", "month"]
    assert list(inspect.signature(EvaluationCatalog.serialize).parameters)[1:] == ["scope", "year", "month"]
    assert list(inspect.signature(EvaluationCatalog.reconcile_period_lines).parameters)[1:] == [
        "scope", "year", "month", "copied_lines",
    ]
    require_params = inspect.signature(require_approved_capability).parameters
    assert require_params["year"].kind is inspect.Parameter.KEYWORD_ONLY
    assert require_params["month"].kind is inspect.Parameter.KEYWORD_ONLY
    overlay_params = inspect.signature(overlay_pinned_kpis).parameters
    assert overlay_params["records"].default is None
    assert overlay_params["preview_approved"].kind is inspect.Parameter.KEYWORD_ONLY
    assert overlay_params["preview_approved"].default is False
    assert "db" not in inspect.signature(score_basis).parameters
    assert "schema_ready" not in inspect.getsource(score_basis)
    assert "approved_version" not in inspect.getsource(score_basis)
    assert "weight_only" not in inspect.signature(decide).parameters


def test_client_flag_cannot_grant_formula_permission():
    with pytest.raises(TypeError):
        decide(
            team_name="Outbound",
            level="Employee",
            position="",
            kpis=_outbound_config()["kpis"],
            importer_registered=True,
            weight_only=True,
        )


# ---------------------------------------------------------------- admission


def test_outbound_is_admitted_only_for_july_and_august_2026():
    config = _outbound_config()
    file_keys = {kpi["key"] for kpi in config["kpis"]}
    assert file_keys == {"Attendance", "Booking", "Quality", "Other"}
    assert next(kpi["weight"] for kpi in config["kpis"] if kpi["key"] == "Attendance") == 0.70
    assert DEFAULT_WEIGHTS["Outbound"]["AHT"] == 0.00
    assert "Productivity" not in file_keys

    blocked = calculation_for("Outbound", "Employee", "", config)
    assert blocked.allows_ratio_edit is False
    assert blocked.weight_only_allowed is False
    assert "July 2026" in blocked.reason and "August 2026" in blocked.reason

    partial_year = calculation_for("Outbound", "Employee", "", config, year=2026)
    partial_month = calculation_for("Outbound", "Employee", "", config, month=8)
    assert partial_year.allows_ratio_edit is False
    assert partial_month.allows_ratio_edit is False

    july = calculation_for("Outbound", "Employee", "", config, year=2026, month=7)
    august = calculation_for("Outbound", "Employee", "", config, year=2026, month="August")
    assert july.allows_ratio_edit is True and july.edit_mode == "full" and july.weight_only_allowed is False
    assert august.allows_ratio_edit is True and august.weight_only_allowed is False

    for year, month in ((2026, 6), (2026, 9), (2025, 8), (2027, 7)):
        refused = calculation_for("Outbound", "Employee", "", config, year=year, month=month)
        assert refused.allows_ratio_edit is False
        assert refused.weight_only_allowed is False
        assert "Productivity" not in refused.reason or "not inferred" in refused.reason or "not admitted" in refused.reason

    coding = calculation_for("Coding", "Employee", "", load_team_config("Coding"), year=2026, month=9)
    submission = calculation_for("Submission", "Employee", "", load_team_config("Submission"))
    assert coding.allows_ratio_edit is True
    assert "calculate_achievement" in coding.reason
    assert submission.allows_ratio_edit is True
    assert calculation_for("Mystery Desk", "Employee", "", None, year=2026, month=8).allows_ratio_edit is False
    positioned = calculation_for("Outbound", "Employee", "Agent", config, year=2026, month=8)
    assert positioned.allows_ratio_edit is False
    assert "not proof of the ratio formula" in positioned.reason


def test_period_lines_use_source_targets_and_optional_aht():
    catalog = _catalog()
    scope = _scope("Outbound")
    july = catalog.baseline_lines(scope, 2026, 7)
    august = catalog.baseline_lines(scope, 2026, 8)
    september = catalog.baseline_lines(scope, 2026, 9)
    july_scored = _scored(july)
    august_scored = _scored(august)
    assert set(july_scored) == {"Attendance", "Booking", "Quality", "Other"}
    assert july_scored["Attendance"]["weight"] == pytest.approx(0.70)
    assert july_scored["Booking"]["weight"] == pytest.approx(0.10)
    assert july_scored["Attendance"]["target"] == pytest.approx(SOURCE_TARGETS["Attendance"])
    assert august_scored["Attendance"]["weight"] == pytest.approx(0.60)
    assert august_scored["Productivity"]["weight"] == pytest.approx(0.10)
    assert august_scored["Productivity"]["target"] == pytest.approx(SOURCE_TARGETS["Productivity"])
    assert set(august_scored) == {"Booking", "Attendance", "Other", "Quality", "Productivity"}
    for lines in (july, august):
        for line in lines:
            if line["kpi_key"] == "AHT":
                assert line["weight"] == 0
                assert line["optional"] is True and line["scored"] is False and line["enabled"] is False
                continue
            assert line["direction"] == "higher_better"
            assert line["unit"] == "%"
            assert line["target_mode"] == "workbook"
    assert "Productivity" not in _scored(september)
    assert all(line["target"] is None for line in september if line["kpi_key"] != "AHT")
    no_period = catalog.decision_for(scope)
    assert no_period.allows_ratio_edit is False
    assert catalog.decision_for(scope, 2026, 7).allows_ratio_edit is True
    assert catalog.decision_for(scope, 2026, 9).allows_ratio_edit is False


def test_global_catalog_lists_outbound_as_period_dependent_without_enabling_every_month():
    db = _session(Team.__table__, EvaluationScope.__table__)
    try:
        db.add_all([
            _team("Outbound", region="EGY"),
            _team("Coding", region="UAE"),
            _team("Submission", region="UAE"),
        ])
        db.commit()
        rows = EvaluationCatalog(db).sync()
        outbound = next(row for row in rows if row.display_name == "Outbound" and row.performance_level == "Employee" and row.position_name == "")
        coding = next(row for row in rows if row.display_name == "Coding" and row.performance_level == "Employee" and row.position_name == "")
        assert outbound.readiness == "blocked"
        assert coding.readiness == "supported"
        body = EvaluationCatalog(db).serialize(outbound)
        assert body["supported"] is False
        assert body["edit_mode"] == "blocked"
        assert body["readiness"] == "blocked"
        assert body["period_dependent"] is True
        assert body["weight_only_allowed"] is False
        assert [(item["year"], item["month"]) for item in body["admitted_periods"]] == [(2026, 7), (2026, 8)]
        assert "period_readiness" not in body
        period = EvaluationCatalog(db).serialize(outbound, 2026, 8)
        assert period["supported"] is True
        assert period["readiness"] == "supported"
        assert period["edit_mode"] == "full"
        assert period["global_readiness"] == "blocked"
        assert period["global_supported"] is False
        assert outbound.readiness == "blocked"
        assert period["period_readiness"] == "supported"
        assert period["period_supported"] is True
        assert period["period_edit_mode"] == "full"
        assert period["period"]["status"] == "august_2026"
        assert period["period"]["approved_binding"] == "apply"
        assert period["period"]["catalog_template_supported"] is True
        assert period["period"]["infer_from_august"] is False
        assert "Productivity" in period["period"]["scored_keys"]
        later = EvaluationCatalog(db).serialize(outbound, 2026, 9)
        assert later["readiness"] == "blocked"
        assert later["supported"] is False
        assert later["edit_mode"] == "blocked"
        assert later["global_readiness"] == "blocked"
        assert later["global_supported"] is False
        assert later["period_readiness"] == "blocked"
        assert later["period"]["catalog_template_supported"] is False
        assert "Productivity" not in _scored(later["lines"])
        coding_body = EvaluationCatalog(db).serialize(coding, 2026, 9)
        assert coding_body["supported"] is True
        assert coding_body["period_dependent"] is False
        assert coding_body["admitted_periods"] == []
    finally:
        _close(db)


# ---------------------------------------------------------------- reconcile


def test_copying_july_into_august_uses_the_canonical_productivity_template():
    catalog = _catalog()
    scope = _scope("Outbound")
    copied = [line for line in catalog.baseline_lines(scope, 2026, 7) if line["kpi_key"] != "AHT"]
    result = catalog.reconcile_period_lines(scope, 2026, 8, copied)
    scored = _scored(result["lines"])
    assert result["template_changed"] is True
    assert result["preserved_values"] is False
    assert result["blocked"] is False
    assert result["period_status"] == "august_2026"
    assert set(scored) == {"Booking", "Attendance", "Other", "Quality", "Productivity"}
    assert scored["Attendance"]["weight"] == pytest.approx(0.60)
    assert scored["Productivity"]["target"] == pytest.approx(0.8)
    assert result["weights_total"] == pytest.approx(1.0)
    assert any("Productivity" in item for item in result["diagnostics"])
    assert "Productivity" in _scored(result["source_baseline"])
    assert all(line["kpi_key"] != "Productivity" for line in copied)


def test_same_month_revise_keeps_admin_weights_and_refuses_keys_outside_the_template():
    catalog = _catalog()
    scope = _scope("Outbound")
    copied = [dict(line) for line in catalog.baseline_lines(scope, 2026, 8) if line["kpi_key"] != "AHT"]
    for line in copied:
        if line["kpi_key"] == "Attendance":
            line["weight"] = 0.40
            line["target"] = 0.55
            line["target_mode"] = "fixed"
        elif line["kpi_key"] == "Booking":
            line["weight"] = 0.30
    result = catalog.reconcile_period_lines(scope, 2026, 8, copied)
    by_key = {line["kpi_key"]: line for line in result["lines"]}
    assert result["preserved_values"] is True
    assert result["template_changed"] is False
    assert by_key["Attendance"]["weight"] == pytest.approx(0.40)
    assert by_key["Attendance"]["target"] == pytest.approx(0.55)
    assert by_key["Attendance"]["target_mode"] == "fixed"
    assert by_key["Booking"]["weight"] == pytest.approx(0.30)
    assert by_key["AHT"]["weight"] == 0
    assert by_key["Attendance"]["weight"] != pytest.approx(0.60)

    short = [dict(line) for line in copied]
    for line in short:
        if line["kpi_key"] == "Attendance":
            line["weight"] = 0.50
    uneven = catalog.reconcile_period_lines(scope, 2026, 8, short)
    assert uneven["preserved_values"] is True
    assert any("not rescaled" in item for item in uneven["diagnostics"])
    assert _scored(uneven["lines"])["Attendance"]["weight"] == pytest.approx(0.50)

    extra = [dict(line) for line in copied]
    extra.append({"kpi_key": "Mystery", "weight": 0.0, "direction": "higher_better", "target_mode": "workbook"})
    rejected = catalog.reconcile_period_lines(scope, 2026, 8, extra)
    assert rejected["preserved_values"] is False
    assert "Mystery" not in {line["kpi_key"] for line in rejected["lines"]}

    activated = [dict(line) for line in catalog.baseline_lines(scope, 2026, 8)]
    for line in activated:
        if line["kpi_key"] == "AHT":
            line["weight"] = 0.05
        if line["kpi_key"] == "Attendance":
            line["weight"] = 0.55
    aht = catalog.reconcile_period_lines(scope, 2026, 8, activated)
    assert _scored(aht["lines"]).get("AHT") is None
    assert next(line["weight"] for line in aht["lines"] if line["kpi_key"] == "AHT") == 0


def test_september_does_not_inherit_august_lines():
    catalog = _catalog()
    scope = _scope("Outbound")
    august = [line for line in catalog.baseline_lines(scope, 2026, 8) if line["kpi_key"] != "AHT"]
    result = catalog.reconcile_period_lines(scope, 2026, 9, august)
    assert result["blocked"] is True
    assert result["template_changed"] is True
    assert result["period_status"] == "unconfigured"
    assert "Productivity" not in _scored(result["lines"])
    assert any("not inferred" in item for item in result["diagnostics"])
    assert all(line["target"] is None for line in result["lines"] if line["kpi_key"] != "AHT")


# ---------------------------------------------------------------- capability gate


def _august_lines(**weights) -> list[dict]:
    lines = [dict(line) for line in period_capability(2026, 8)["lines"]]
    for line in lines:
        if line["kpi_key"] in weights:
            line["weight"] = weights[line["kpi_key"]]
    return lines


def test_approved_gate_allows_custom_weights_and_refuses_aht_and_key_changes():
    config = _outbound_config()
    custom = _version(8, _august_lines(Attendance=0.45, Productivity=0.25))
    decision = require_approved_capability(custom, team_name="Outbound", config=config, year=2026, month=8)
    assert decision.allows_ratio_edit is True
    assert decision.weight_only_allowed is False
    omitted = require_approved_capability(custom, team_name="Outbound", config=config)
    assert omitted.allows_ratio_edit is True

    activated = _version(8, _august_lines() + [{
        "kpi_key": "AHT", "weight": 0.10, "direction": "lower_better", "target_mode": "workbook", "target": None,
    }])
    with pytest.raises(EvaluationError) as aht:
        require_approved_capability(activated, team_name="Outbound", config=config, year=2026, month=8)
    assert aht.value.data["code"] == "unsupported_calculation"
    assert aht.value.data["weight_only_allowed"] is False
    assert aht.value.data["edit_mode"] == "blocked"
    assert "cannot be activated" in aht.value.message

    missing = _version(8, [line for line in _august_lines() if line["kpi_key"] != "Productivity"])
    with pytest.raises(EvaluationError) as keys:
        require_approved_capability(missing, team_name="Outbound", config=config, year=2026, month=8)
    assert keys.value.data["capability_reason"] == "scored_keys"

    outsider = _version(8, _august_lines() + [{
        "kpi_key": "Mystery", "weight": 0, "direction": "higher_better", "target_mode": "workbook",
    }])
    with pytest.raises(EvaluationError) as extra:
        require_approved_capability(outsider, team_name="Outbound", config=config, year=2026, month=8)
    assert extra.value.data["capability_reason"] == "kpi_key"

    lowered = _august_lines()
    lowered[0]["direction"] = "lower_better"
    with pytest.raises(EvaluationError) as direction:
        require_approved_capability(_version(8, lowered), team_name="Outbound", config=config, year=2026, month=8)
    assert direction.value.data["capability_reason"] == "direction"

    capped = _august_lines()
    capped[0]["capping"] = "baseline_80"
    with pytest.raises(EvaluationError) as cap:
        require_approved_capability(_version(8, capped), team_name="Outbound", config=config, year=2026, month=8)
    assert cap.value.data["capability_reason"] == "cap"

    with pytest.raises(EvaluationError) as policy:
        require_approved_capability(
            _version(8, _august_lines(), policy="baseline_80"),
            team_name="Outbound",
            config=config,
            year=2026,
            month=8,
        )
    assert policy.value.data["capability_reason"] == "policy"

    with pytest.raises(EvaluationError) as period:
        require_approved_capability(custom, team_name="Outbound", config=config, year=2026, month=7)
    assert period.value.data["capability_reason"] == "period"

    september = _version(9, [dict(line) for line in period_capability(2026, 9)["lines"]])
    with pytest.raises(EvaluationError) as later:
        require_approved_capability(september, team_name="Outbound", config=config, year=2026, month=9)
    assert later.value.data["weight_only_allowed"] is False

    mystery = _version(8, [{"kpi_key": "Booking", "weight": 1, "direction": "higher_better"}])
    with pytest.raises(EvaluationError) as unknown:
        require_approved_capability(mystery, team_name="Mystery Desk", config=None, year=2026, month=8)
    assert unknown.value.data["code"] == "unsupported_calculation"
    assert unknown.value.data["weight_only_allowed"] is False

    coding_lines = [
        {"kpi_key": key, "weight": weight, "direction": "lower_better", "target_mode": "workbook"}
        for key, weight in (("QualityErrors", 0.2), ("Rejection", 0.5), ("TAT", 0.3))
    ]
    coding = require_approved_capability(
        _version(9, coding_lines),
        team_name="Coding",
        config=load_team_config("Coding"),
        year=2026,
        month=9,
    )
    assert coding.allows_ratio_edit is True
    assert coding.weight_only_allowed is False


def test_score_basis_stays_pure_and_target_conflict_stays_visible():
    lines = _august_lines()
    lines[0]["target_mode"] = "fixed"
    lines[0]["target"] = 0.55
    version = _version(8, lines)
    rows = [{
        "kpi_key": lines[0]["kpi_key"],
        "actual": 0.4,
        "workbook_target": 0.65,
    }]
    assert conflicts_for(lines, rows)
    with pytest.raises(TargetConflict) as conflict:
        score_basis(version, rows)
    assert conflict.value.data["code"] == "target_conflict"
    assert conflict.value.data["conflicts"][0]["approved_target"] == pytest.approx(0.55)


# ---------------------------------------------------------------- schema


def _legacy_db():
    return _session(
        Team.__table__,
        DBEmployee.__table__,
        DBPerformanceRecord.__table__,
        KPIValue.__table__,
        TeamKPIConfig.__table__,
    )


def _outbound_shape_db():
    return _session(
        Team.__table__,
        DBEmployee.__table__,
        DBPerformanceRecord.__table__,
        KPIValue.__table__,
        TeamKPIConfig.__table__,
        TeamConfigurationVersion.__table__,
        EvaluationScope.__table__,
        EvaluationRevision.__table__,
    )


def test_legacy_schema_stays_ready_false_and_does_not_roll_back():
    db = _legacy_db()
    try:
        team = _team("Coding", region="UAE")
        db.add(team)
        db.flush()
        assert schema_ready(db) is False
        assert approved_version(db, team_id=team.id, level="Employee", position="", year=2026, month=7) is None
        assert db.query(Team).filter(Team.id == team.id).count() == 1
        db.add(_team("Submission", region="UAE"))
        db.flush()
        assert db.query(Team).count() == 2
    finally:
        _close(db)


def test_partial_scope_table_and_missing_guard_raise_without_rollback():
    db = _outbound_shape_db()
    try:
        team = _team("Outbound")
        db.add(team)
        db.flush()
        db.execute(text(f"DROP TRIGGER {SQLITE_VERSION_TRIGGERS[0]}"))
        with pytest.raises(SchemaIncomplete) as missing_guard:
            schema_ready(db)
        assert SQLITE_VERSION_TRIGGERS[0] in " ".join(missing_guard.value.data["missing"])
        assert db.query(Team).filter(Team.id == team.id).count() == 1
        assert db.in_transaction()
    finally:
        _close(db)

    stub = _session(Team.__table__)
    try:
        stub.add(_team("Outbound"))
        stub.flush()
        stub.execute(text("CREATE TABLE evaluation_scopes (id TEXT)"))
        with pytest.raises(SchemaIncomplete) as partial:
            schema_ready(stub)
        assert any("evaluation_scopes" in item for item in partial.value.data["missing"])
        assert stub.query(Team).count() == 1
        stub.add(_team("Coding", region="UAE"))
        stub.flush()
        assert stub.query(Team).count() == 2
    finally:
        _close(stub)


def test_missing_revisions_are_refused_after_monthly_activation():
    db = _outbound_shape_db()
    try:
        assert schema_ready(db) is True
        assert_schema(db)
        assert approved_version(db, team_id=uuid.uuid4(), level="Employee", position="", year=2026, month=8) is None
        team = _team("Outbound")
        db.add(team)
        db.flush()
        db.execute(text("DROP TABLE evaluation_revisions"))
        with pytest.raises(SchemaIncomplete) as missing:
            schema_ready(db)
        assert missing.value.status_code == 503
        assert any("evaluation_revisions" in item for item in missing.value.data["missing"])
        assert db.in_transaction()
        assert db.query(Team).filter(Team.id == team.id).count() == 1
        with pytest.raises(SchemaIncomplete) as settings:
            assert_schema(db)
        assert settings.value.status_code == 503
        db.add(_team("Coding", region="UAE"))
        db.flush()
        assert db.query(Team).count() == 2
    finally:
        _close(db)


def test_postgresql_inspection_targets_public_not_search_path():
    from types import SimpleNamespace

    class _Conn:
        dialect = SimpleNamespace(name="postgresql")
        statements = []

        def execute(self, statement, params=None):
            self.statements.append(str(statement))
            return []

    connection = _Conn()
    assert _table_names(connection) == set()
    assert _column_names(connection, "evaluation_revisions") == set()
    sql = "\n".join(connection.statements)
    assert "n.nspname = 'public'" in sql
    assert "table_schema = 'public'" in sql
    assert "current_schema" not in sql


def test_complete_history_schema_is_ready_and_inspection_errors_propagate(monkeypatch):
    db = _session(full=True)
    try:
        assert schema_ready(db) is True
        assert_schema(db)
        team = _team("Outbound")
        db.add(team)
        db.flush()

        def boom(_connection):
            raise RuntimeError("inspection failed")

        monkeypatch.setattr("services.evaluation.resolver._table_names", boom)
        with pytest.raises(RuntimeError, match="inspection failed"):
            schema_ready(db)
        assert db.query(Team).filter(Team.id == team.id).count() == 1
    finally:
        _close(db)


# ---------------------------------------------------------------- locks and upload gate


def test_postgres_lock_statement_is_for_update_ordered_by_id():
    db = _legacy_db()
    try:
        first, second = uuid.uuid4(), uuid.uuid4()
        sql = str(_team_lock_query(db, [second, first]).statement.compile(dialect=PgDialect()))
        folded = " ".join(sql.upper().split())
        assert "FOR UPDATE" in folded
        assert "ORDER BY TEAMS.ID" in folded
    finally:
        _close(db)


def test_lock_orders_ids_before_an_approved_lookup():
    db = _outbound_shape_db()
    try:
        low = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
        high = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2")
        db.add_all([
            _team("Outbound", team_id=high),
            _team("Coding", region="UAE", team_id=low),
        ])
        db.flush()
        acquired = lock_team_rows(db, [high, low, high])
        assert [row.id for row in acquired] == [low, high]
        assert db.info["evaluation_team_lock_order"] == [[low, high]]
    finally:
        _close(db)


def _upload_record(team: str, month: str, kpis: list[dict], employee_id: str = "ANON-1") -> PerformanceRecord:
    return PerformanceRecord(
        id=f"{employee_id}_2026_{month}",
        employee_id=employee_id,
        employee_name="Anonymous Agent",
        team=team,
        month=month,
        year=2026,
        region="EGY",
        performance_level="Employee",
        position="",
        evaluation=EvaluationData(score=70, grade="C"),
        kpi_values=kpis,
    )


def _employee(team: str, employee_id: str = "ANON-1") -> Employee:
    return Employee(id=employee_id, name="Anonymous Agent", team=team, region="EGY", performance_level="Employee", position="")


def _evidence(lines: list[dict]) -> list[dict]:
    rows = []
    for line in lines:
        if float(line.get("weight") or 0) <= 0:
            continue
        rows.append({
            "kpi_key": line["kpi_key"],
            "actual_value": 0.5,
            "target_value": line.get("target") if line.get("target") is not None else 0.5,
            "achievement_ratio": None,
            "weight_applied": line["weight"],
            "contribution": None,
        })
    return rows


def test_pin_path_locks_then_checks_capability_before_scoring(monkeypatch):
    db = _outbound_shape_db()
    events = []
    try:
        team = _team("Outbound")
        lines = _august_lines(Attendance=0.45, Productivity=0.25)
        version = _version(8, lines, team_id=team.id)
        db.add_all([team, version])
        db.commit()
        real_lock = lock_team_rows
        real_approved = approved_version
        real_require = require_approved_capability
        real_score = score_basis

        def track_lock(session, team_ids):
            events.append("lock")
            return real_lock(session, team_ids)

        def track_approved(*args, **kwargs):
            events.append("approved")
            return real_approved(*args, **kwargs)

        def track_require(*args, **kwargs):
            events.append(("require", kwargs.get("team_name"), kwargs.get("year"), kwargs.get("month")))
            return real_require(*args, **kwargs)

        def track_score(*args, **kwargs):
            events.append("score")
            return real_score(*args, **kwargs)

        monkeypatch.setattr("services.evaluation.resolver.lock_team_rows", track_lock)
        monkeypatch.setattr("services.evaluation.resolver.approved_version", track_approved)
        monkeypatch.setattr("services.evaluation.resolver.require_approved_capability", track_require)
        monkeypatch.setattr("services.evaluation.workflow.require_approved_capability", track_require)
        monkeypatch.setattr("services.evaluation.resolver.score_basis", track_score)
        monkeypatch.setattr("services.evaluation.workflow.score_basis", track_score)

        record = _upload_record("Outbound", "August", _evidence(lines))
        DatabaseSeeder()._pin_uploaded_records(db, [record])
        assert events[:4] == ["lock", "approved", ("require", "Outbound", 2026, 8), "score"]
        assert db.info["evaluation_team_lock_order"][0] == [team.id]

        def before_delete(conn, cursor, statement, parameters, context, executemany):
            if "kpi_values" in statement.lower() and statement.lstrip().lower().startswith("delete"):
                events.append("kpi_delete")
                assert db.info["evaluation_team_lock_order"]

        event.listen(db.bind, "before_cursor_execute", before_delete)
        try:
            DatabaseSeeder()._sync_to_database([record], [_employee("Outbound")], db_session=db)
        finally:
            event.remove(db.bind, "before_cursor_execute", before_delete)
        assert "kpi_delete" in events
        delete_at = events.index("kpi_delete")
        assert events.index("lock") < events.index("approved") < delete_at
        assert events.count("score") >= 2
        assert sum(1 for item in events if isinstance(item, tuple) and item[0] == "require" and item[1] == "Outbound") >= 2
        assert delete_at > max(index for index, item in enumerate(events) if item == "lock")
    finally:
        _close(db)


def test_september_binding_is_refused_before_the_capability_gate(monkeypatch):
    db = _outbound_shape_db()
    called = []
    try:
        team = _team("Outbound")
        lines = [dict(line) for line in period_capability(2026, 9)["lines"]]
        db.add_all([team, _version(9, lines, team_id=team.id)])
        db.commit()

        def track_require(*args, **kwargs):
            called.append("require")
            raise AssertionError("capability gate ran before the Outbound month guard")

        monkeypatch.setattr("services.evaluation.resolver.require_approved_capability", track_require)
        record = _upload_record("Outbound", "September", _evidence(lines))
        with pytest.raises(OutboundUnsupportedApprovedBinding):
            DatabaseSeeder()._pin_uploaded_records(db, [record])
        assert called == []
        assert db.query(KPIValue).count() == 0
    finally:
        _close(db)


def test_fixed_target_conflict_is_not_swallowed_on_the_pin_path():
    db = _outbound_shape_db()
    try:
        team = _team("Outbound")
        lines = _august_lines()
        for line in lines:
            if line["kpi_key"] == "Attendance":
                line["target_mode"] = "fixed"
                line["target"] = 0.55
        db.add_all([team, _version(8, lines, team_id=team.id)])
        db.commit()
        evidence = _evidence(lines)
        for row in evidence:
            if row["kpi_key"] == "Attendance":
                row["target_value"] = 0.65
        with pytest.raises(TargetConflict):
            DatabaseSeeder()._pin_uploaded_records(db, [_upload_record("Outbound", "August", evidence)])
        assert db.query(DBPerformanceRecord).count() == 0
    finally:
        _close(db)


def test_legacy_multi_team_sync_locks_in_id_order_before_kpi_delete():
    db = _legacy_db()
    try:
        low = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
        high = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2")
        db.add_all([
            _team("Coding", region="UAE", team_id=high),
            _team("Submission", region="UAE", team_id=low),
        ])
        db.commit()
        assert schema_ready(db) is False
        seen = {"delete": False}

        def before_delete(conn, cursor, statement, parameters, context, executemany):
            if "kpi_values" in statement.lower() and statement.lstrip().lower().startswith("delete"):
                locks = db.info.get("evaluation_team_lock_order") or []
                assert locks and locks[0] == [low, high]
                seen["delete"] = True

        event.listen(db.bind, "before_cursor_execute", before_delete)
        try:
            DatabaseSeeder()._sync_to_database(
                [
                    _upload_record("Coding", "May", [{
                        "kpi_key": "QualityErrors", "actual_value": 0.1, "target_value": 0.2,
                        "achievement_ratio": 1, "weight_applied": 1, "contribution": 1,
                    }], employee_id="CODE-1"),
                    _upload_record("Submission", "May", [{
                        "kpi_key": "initial_rejection_rate", "actual_value": 0.1, "target_value": 0.2,
                        "achievement_ratio": 1, "weight_applied": 1, "contribution": 1,
                    }], employee_id="SUB-1"),
                ],
                [_employee("Coding", "CODE-1"), _employee("Submission", "SUB-1")],
                db_session=db,
            )
        finally:
            event.remove(db.bind, "before_cursor_execute", before_delete)
        assert seen["delete"] is True
        assert len(db.info["evaluation_team_lock_order"]) == 1
    finally:
        _close(db)


# ---------------------------------------------------------------- historical overlay


def _kpis():
    return [
        {"key": "Booking", "weight": 0.30, "target": 0.20, "direction": "higher_better"},
        {"key": "Attendance", "weight": 0.70, "target": 0.50, "direction": "higher_better"},
    ]


def _saved(version_id: str, attendance_target: float, *, pinned: bool = True, month: int = 8) -> dict:
    return {
        "team": "Outbound",
        "performance_level": "Employee",
        "position_name": "",
        "year": 2026,
        "month": "August",
        "branch_key": "branch-a",
        "employee_id": "ANON-1",
        "record_payload": {
            "branch": "branch-a",
            "evaluation_basis": {
                "pinned": pinned,
                "version_id": version_id,
                "year": 2026,
                "month": month,
                "lines": [
                    {"kpi_key": "Booking", "weight": 0.10, "direction": "higher_better", "target_mode": "fixed", "target": 0.30},
                    {"kpi_key": "Attendance", "weight": 0.60, "direction": "higher_better", "target_mode": "fixed", "target": attendance_target},
                ],
            },
        },
    }


def test_overlay_uses_saved_basis_and_keeps_business_weight():
    db = _outbound_shape_db()
    try:
        team = _team("Outbound")
        latest = _august_lines()
        for line in latest:
            if line["kpi_key"] == "Attendance":
                line["target_mode"] = "fixed"
                line["target"] = 0.99
        db.add_all([team, _version(8, latest, team_id=team.id)])
        db.commit()
        overlaid = overlay_pinned_kpis(
            db, "Outbound", "Employee", "", 2026, 8, _kpis(), records=[_saved("saved-1", 0.65)],
        )
        booking = next(item for item in overlaid if item["key"] == "Booking")
        attendance = next(item for item in overlaid if item["key"] == "Attendance")
        assert booking["weight"] == pytest.approx(0.30)
        assert booking["aggregation_weight"] == pytest.approx(0.30)
        assert booking["scoring_weight"] == pytest.approx(0.10)
        assert booking["target"] == pytest.approx(0.30)
        assert attendance["target"] == pytest.approx(0.65)
        assert attendance["weight"] == pytest.approx(0.70)
        assert "branch" not in booking and "branch_key" not in booking and "employee_id" not in booking

        legacy = overlay_pinned_kpis(
            db, "Outbound", "Employee", "", 2026, 8, _kpis(), records=[_saved("saved-1", 0.65, pinned=False)],
        )
        assert next(item["target"] for item in legacy if item["key"] == "Attendance") == pytest.approx(0.50)
        assert "scoring_weight" not in legacy[0]

        mixed = overlay_pinned_kpis(
            db,
            "Outbound",
            "Employee",
            "",
            2026,
            8,
            _kpis(),
            records=[_saved("saved-1", 0.65), _saved("saved-2", 0.40)],
        )
        mixed_booking = next(item for item in mixed if item["key"] == "Booking")
        mixed_attendance = next(item for item in mixed if item["key"] == "Attendance")
        assert mixed_booking["target"] == pytest.approx(0.30)
        assert mixed_attendance["target"] == pytest.approx(0.50)
        assert "scoring_weight" not in mixed_attendance

        def fail_query(*_args, **_kwargs):
            raise AssertionError("overlay queried performance rows")

        original = db.query
        db.query = fail_query
        try:
            untouched = overlay_pinned_kpis(db, "Outbound", "Employee", "", 2026, 8, _kpis(), records=[])
            historical = overlay_pinned_kpis(db, "Outbound", "Employee", "", 2026, 8, _kpis())
        finally:
            db.query = original
        assert untouched[0]["target"] == pytest.approx(0.20)
        historical_attendance = next(item for item in historical if item["key"] == "Attendance")
        assert historical_attendance["target"] == pytest.approx(0.50)
        assert historical_attendance.get("evaluation_pinned") is not True
        assert "scoring_weight" not in historical_attendance
        preview = overlay_pinned_kpis(
            db, "Outbound", "Employee", "", 2026, 8, _kpis(), preview_approved=True,
        )
        assert next(item["target"] for item in preview if item["key"] == "Attendance") == pytest.approx(0.99)
    finally:
        _close(db)


def test_overlay_does_not_pick_a_second_team_or_another_branch():
    db = _outbound_shape_db()
    try:
        employee = _team("Outbound")
        management = _team("Outbound HQ", db_name="Outbound HQ", display="Outbound", level="management")
        lines = _august_lines()
        for line in lines:
            line["target_mode"] = "fixed"
            line["target"] = 0.11
        db.add_all([employee, management, _version(8, lines, team_id=employee.id)])
        db.commit()
        unchanged = overlay_pinned_kpis(db, "Outbound", "Employee", "", 2026, 8, _kpis())
        assert next(item["target"] for item in unchanged if item["key"] == "Attendance") == pytest.approx(0.50)

        other_branch = _saved("other", 0.12)
        other_branch["team"] = "Inbound"
        kept = overlay_pinned_kpis(
            db, "Outbound", "Employee", "", 2026, 8, _kpis(), records=[other_branch],
        )
        assert next(item["target"] for item in kept if item["key"] == "Attendance") == pytest.approx(0.50)
    finally:
        _close(db)


def test_management_runtime_keeps_history_until_a_saved_pin_is_authorized():
    from types import SimpleNamespace

    from services.management_bsc_service import ManagementBSCService

    db = _outbound_shape_db()
    try:
        team = _team("Outbound")
        latest = _august_lines()
        for line in latest:
            if line["kpi_key"] == "Attendance":
                line["target_mode"] = "fixed"
                line["target"] = 0.99
        db.add_all([team, _version(8, latest, team_id=team.id)])
        db.commit()
        config_row = SimpleNamespace(
            effective_month="August",
            effective_year=2026,
            display_order=1,
            kpi_label="Attendance",
            kpi_key="Attendance",
            perspective_key="Customer",
            weight=0.7,
            direction="higher_better",
            target_unit="%",
        )
        service = ManagementBSCService(db)
        omitted = service._build_runtime_config([config_row], {}, "Outbound", "Employee", (2026, 8))
        assert omitted["kpis"][0]["weight"] == pytest.approx(0.7)
        assert omitted["kpis"][0].get("target") is None
        assert omitted["kpis"][0].get("evaluation_pinned") is not True

        legacy = service._build_runtime_config(
            [config_row], {}, "Outbound", "Employee", (2026, 8),
            records=[_saved("saved-1", 0.65, pinned=False)],
        )
        assert legacy["kpis"][0].get("target") is None
        assert legacy["kpis"][0].get("evaluation_pinned") is not True

        saved = service._build_runtime_config(
            [config_row], {}, "Outbound", "Employee", (2026, 8),
            records=[_saved("saved-1", 0.65)],
        )
        pinned = saved["kpis"][0]
        assert pinned["weight"] == pytest.approx(0.7)
        assert pinned["aggregation_weight"] == pytest.approx(0.7)
        assert pinned["scoring_weight"] == pytest.approx(0.60)
        assert pinned["target"] == pytest.approx(0.65)
        assert pinned["evaluation_pinned"] is True

        other = _saved("saved-1", 0.12)
        other["team"] = "Inbound"
        isolated = service._build_runtime_config(
            [config_row], {}, "Outbound", "Employee", (2026, 8), records=[other],
        )
        assert isolated["kpis"][0].get("target") is None
        assert isolated["kpis"][0].get("evaluation_pinned") is not True
    finally:
        _close(db)
