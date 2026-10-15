"""Upload stored-state equality.

The stored state of a synthetic workbook upload (every table, the upload result and the scored rows) must stay
byte-identical to the golden dump taken from the code before the runtime became database-only
(fixtures/upload_stored_state_marketing.json). Random UUIDs become <uuid>, timestamps are dropped, and rows are
sorted. The JSON mirror is not part of the stored state. Synthetic data only.
"""

import io
import json
import re
import uuid
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.loader import load_team_config
from models.models import Base
from services import seeding_service
from services.seeding_service import DatabaseSeeder

GOLDEN = Path(__file__).parent / "fixtures" / "upload_stored_state_marketing.json"
FIXED_BATCH = uuid.UUID("00000000-0000-4000-8000-00000000abcd")
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
TIMESTAMP_COLUMNS = {"created_at", "updated_at", "uploaded_at", "last_seen_at", "started_at", "finished_at", "completed_at"}


def _canonical(value):
    return UUID_RE.sub("<uuid>", json.dumps(value, sort_keys=True, default=str))


def _workbook_bytes() -> bytes:
    config = load_team_config("Marketing")
    rows = []
    for position_index, position in enumerate(["Media Buyer", "Web Developer"], start=1):
        for definition in config["performance_levels"]["Employee"]["positions"][position]["kpis"]:
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
                "Target Value": 100.0,
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


def _stored_state(engine, result) -> dict:
    dump = {
        "result": _canonical({key: value for key, value in result.items() if key != "scored_rows"}),
        "scored_rows": _canonical(result.get("scored_rows")),
    }
    with engine.connect() as connection:
        inspector = inspect(connection)
        for table in sorted(inspector.get_table_names()):
            columns = [column["name"] for column in inspector.get_columns(table)]
            keep = [name for name in columns if name not in TIMESTAMP_COLUMNS]
            uuid_columns = {
                column.name for column in Base.metadata.tables[table].columns
                if "UUID" in type(column.type).__name__.upper()
            } if table in Base.metadata.tables else set()
            rows = connection.execute(
                text(f'SELECT {", ".join(chr(34) + name + chr(34) for name in keep)} FROM "{table}"')
            ).fetchall()
            dump[table] = sorted(
                _canonical({
                    name: ("<uuid>" if name in uuid_columns and value is not None else value)
                    for name, value in zip(keep, row)
                })
                for row in rows
            )
    return dump


def test_the_upload_stores_the_same_state_as_before_the_change(tmp_path, monkeypatch):
    # An empty data directory: the runtime must not need, read or create any data/*.json file for this upload.
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(seeding_service, "SessionLocal", sessionmaker(bind=engine))

    result = DatabaseSeeder().process_uploaded_file(
        "PMS_Trend_All.xlsx", _workbook_bytes(), upload_batch_id=str(FIXED_BATCH),
    )
    state = _stored_state(engine, result)
    engine.dispose()

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert state.keys() == golden.keys()
    for table in golden:
        assert state[table] == golden[table], table
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("table", ["performance_records", "kpi_values", "employees"])
def test_the_golden_has_the_records_the_upload_is_expected_to_store(table):
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert golden[table], table
