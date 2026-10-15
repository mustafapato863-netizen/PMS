"""Runtime storage guards: the upload and the main read endpoints need no data/*.json file, production code imports
no JSON repository except the listed blockers, and the startup notice never opens a data file. Synthetic data only.
"""

import ast
import builtins
import io
import logging
import os
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import insights as insights_router
from api.routers import performance as performance_router
from config.loader import load_team_config
from models.models import Base
from services import seeding_service
from services.obsolete_json_data import warn_obsolete_json_files
from services.seeding_service import DatabaseSeeder

BACKEND = Path(__file__).resolve().parents[1]



def _scope():
    return {
        "role": "Admin",
        "has_unrestricted_team_access": True,
        "legacy_unscoped": False,
        "accessible_teams": [],
        "accessible_team_levels": [],
    }


def _marketing_workbook() -> bytes:
    """A small multi-position Marketing sheet, built from the checked-in team configuration."""
    config = load_team_config("Marketing")
    rows = []
    for position_index, position in enumerate(["Media Buyer", "Web Developer"], start=1):
        definitions = config["performance_levels"]["Employee"]["positions"][position]["kpis"]
        for definition in definitions:
            target = 100.0
            actual = 50.0 if definition["direction"] == "lower_better" else 120.0
            rows.append({
                "Employee ID": f"SGHD90{position_index:03d}",
                "Region": "EGY",
                "Team": "Marketing",
                "Employee Name": f"Employee {position_index}",
                "Position": position,
                "Performance Level": "Employee",
                "Date": pd.Timestamp("2026-07-01"),
                "Perspective": definition["perspective"],
                "KPI": definition["label"],
                "Direction": definition["direction"].replace("_", " ").title(),
                "Weight": definition["weight"],
                "Target Value": target,
                "Target Unit": definition["unit"],
                "Actual Value": actual,
                "Actual Unit": definition["unit"],
                "Achievement %": None,
                "Weighted Score %": None,
                "Performance Score": None,
            })
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Marketing", index=False)
    return output.getvalue()


@pytest.fixture
def empty_read_only_data_dir(tmp_path, monkeypatch):
    """An empty data directory that the runtime may not write to. Every module-level copy of the path is pointed
    here, and writes into it raise, so a runtime write fails the test instead of creating a file."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    real_open = builtins.open
    real_makedirs = os.makedirs
    real_replace = os.replace
    inside = str(data_dir)

    def _refuse_write(path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if isinstance(path, (str, os.PathLike)) and str(Path(path).resolve()).startswith(str(Path(inside).resolve())):
            if any(flag in str(mode) for flag in "wax+"):
                raise PermissionError(f"read-only data directory: {path}")
        return real_open(path, *args, **kwargs)

    def _refuse_dir(path, *args, **kwargs):
        if str(Path(path).resolve()).startswith(str(Path(inside).resolve())):
            raise PermissionError(f"read-only data directory: {path}")
        return real_makedirs(path, *args, **kwargs)

    def _refuse_replace(src, dst, *args, **kwargs):
        if str(Path(dst).resolve()).startswith(str(Path(inside).resolve())):
            raise PermissionError(f"read-only data directory: {dst}")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _refuse_write)
    monkeypatch.setattr(os, "makedirs", _refuse_dir)
    monkeypatch.setattr(os, "replace", _refuse_replace)
    return data_dir


def test_upload_and_read_endpoints_create_no_files_in_an_empty_read_only_data_dir(empty_read_only_data_dir, monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(seeding_service, "SessionLocal", sessionmaker(bind=engine))

    result = DatabaseSeeder().process_uploaded_file("PMS_Marketing.xlsx", _marketing_workbook())
    assert result["records_imported"] > 0

    with Session(bind=engine) as db:
        planning = performance_router.get_planning_categories(
            month="July", performance_level=None, db=db, role="Admin",
        )
        insights = performance_router.get_insights(month="July", performance_level=None, db=db, role="Admin")
        monkeypatch.setattr(insights_router, "require_authenticated_scope", lambda _db, _request: _scope())
        workspace = insights_router.get_insights_workspace(
            request=None, db=db, month="July", year=2026, region=None, team=None, function=None,
            performance_level=None, position=None, employee_id=None, kpi=None, severity=None,
            insight_type=None, status_filter=None, view="full", _role="Admin",
        )
    assert planning.success is True
    assert insights.success is True
    assert workspace.success is True
    assert os.listdir(empty_read_only_data_dir) == []
    engine.dispose()


def _production_json_repository_importers() -> set[str]:
    importers: set[str] = set()
    for path in BACKEND.rglob("*.py"):
        relative = path.relative_to(BACKEND).as_posix()
        if relative.startswith(("tests/", ".venv/", "venv/")) or "__pycache__" in relative:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            elif isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            else:
                continue
            if any("json_repos" in module for module in modules):
                importers.add(relative)
    return importers


def test_no_json_repository_module_exists_and_no_code_imports_one():
    assert not (BACKEND / "repositories" / "json_repos.py").exists()
    assert _production_json_repository_importers() == set()


def test_startup_names_obsolete_json_files_once_without_opening_them(tmp_path, monkeypatch, caplog):
    (tmp_path / "users.json").write_text('[{"password": "x"}]', encoding="utf-8")
    (tmp_path / "performance_records.json").write_text("[]", encoding="utf-8")
    real_open = builtins.open

    def _refuse_data_read(path, *args, **kwargs):
        if str(path).endswith(".json"):
            raise AssertionError("the startup notice must not open a data file")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _refuse_data_read)
    with caplog.at_level(logging.WARNING):
        names = warn_obsolete_json_files(str(tmp_path))

    assert names == ["performance_records.json", "users.json"]
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "users.json" in warnings[0].getMessage()


def test_startup_is_silent_when_no_obsolete_json_file_exists(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        assert warn_obsolete_json_files(str(tmp_path)) == []
    assert not [record for record in caplog.records if record.levelno == logging.WARNING]
