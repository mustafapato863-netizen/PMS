"""SQLite must not coerce a valid UUID's hex into a number and lose identity."""
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from config.database import Base
from models.models import Team


@pytest.mark.parametrize("hex_value", ["0" * 31 + "1", "1" + "0" * 27 + "e123", "12345678901234567890123456789012"])
def test_numeric_looking_uuid_round_trips_losslessly_on_sqlite(hex_value):
    identifier = uuid.UUID(hex_value)
    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine, tables=[Team.__table__])
        with Session(engine) as session:
            session.add(Team(id=identifier, name="AnonymousUUID", db_name="AnonymousUUID", region="UAE", team_level="employee"))
            session.commit()
            session.expunge_all()
            assert session.execute(text("SELECT typeof(id) FROM teams")).scalar_one() == "text"
            assert session.query(Team).one().id == identifier
    finally:
        engine.dispose()


def test_uuid_remains_native_on_postgres_and_text_on_sqlite():
    column_type = Team.__table__.c.id.type
    assert str(column_type.compile(dialect=postgresql.dialect())) == "UUID"
    assert str(column_type.compile(dialect=sqlite.dialect())).startswith("CHAR")
