"""Bootstrap a brand-new database from the canonical ORM metadata.

The historical Alembic chain starts from an existing schema and therefore
cannot initialize an empty hosted database. This script handles only the
empty-database case, then records the current migration head. It refuses to
guess when a database contains tables but has no Alembic history.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from config.database import engine
from models.models import Base


def main() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names(schema="public"))
    if "alembic_version" in tables:
        return
    if tables:
        raise RuntimeError(
            "Database has existing tables but no alembic_version; refusing "
            "to bootstrap an unverified schema."
        )

    Base.metadata.create_all(bind=engine)
    backend_dir = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(backend_dir / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(backend_dir / "migrations"))
    command.stamp(alembic_config, "head")
    print(f"Bootstrapped {len(Base.metadata.tables)} tables and stamped head.")


if __name__ == "__main__":
    main()
