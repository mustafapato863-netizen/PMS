"""Bootstrap a brand-new database from the canonical ORM metadata.

The historical Alembic root alters tables it does not create, so this command
does not execute that revision. An empty database gets create_all, a history
guard check, and a stamp. An existing database without alembic_version is refused.
The root-chain limitation is reported by the PostgreSQL verifier, not by
running the failing migration here.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Running as `python scripts/bootstrap_schema.py` puts scripts/ on sys.path[0],
# which hides the backend root (`config`, `models`). Ensure /app (backend root)
# is importable regardless of invocation style.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from config.database import engine
from models.evaluation_history_schema import REVISION, ROOT_REVISION, missing_history_objects
from models.models import Base


def _alembic_config() -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(backend_dir / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(backend_dir / "migrations"))
    return alembic_config


def _database_identity() -> tuple[str, str]:
    with engine.connect() as connection:
        row = connection.execute(text("SELECT current_database(), current_user")).one()
    return str(row[0]), str(row[1])


def _assert_expected_database() -> None:
    expected_database = os.environ.get("PMS_BOOTSTRAP_EXPECT_DATABASE")
    expected_user = os.environ.get("PMS_BOOTSTRAP_EXPECT_USER")
    if not expected_database and not expected_user:
        return
    database_name, user_name = _database_identity()
    if expected_database and database_name != expected_database:
        raise RuntimeError(
            f"Bootstrap connected to {database_name}, not the expected database {expected_database}."
        )
    if expected_user and user_name != expected_user:
        raise RuntimeError(
            f"Bootstrap connected as {user_name}, not the expected user {expected_user}."
        )


def _public_tables() -> set[str]:
    inspector = inspect(engine)
    try:
        return set(inspector.get_table_names(schema="public"))
    except Exception:
        return set(inspector.get_table_names())


def main() -> None:
    _assert_expected_database()
    tables = _public_tables()
    if "alembic_version" in tables:
        return
    if tables:
        raise RuntimeError(
            "Database has existing tables but no alembic_version; refusing "
            "to bootstrap an unverified schema."
        )

    Base.metadata.create_all(bind=engine)
    with engine.connect() as connection:
        missing = missing_history_objects(connection)
    if missing:
        raise RuntimeError(
            "Fresh schema is missing required history guards and will not be stamped: "
            + "; ".join(missing)
        )
    command.stamp(_alembic_config(), "head")
    database_name, user_name = _database_identity()
    print(
        "FRESH_SCHEMA_BOOTSTRAP "
        f"database={database_name} user={user_name} stamped={REVISION} "
        f"tables={len(Base.metadata.tables)}. "
        "Not a replay of the historical migration chain. "
        f"Root revision {ROOT_REVISION} is not executed; it alters employees, "
        "kpi_values, performance_records, team_kpi_config, and teams without creating them.",
        flush=True,
    )


if __name__ == "__main__":
    main()
