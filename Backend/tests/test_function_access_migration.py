"""Exercise the grant constraint migration without touching the app database."""
import importlib.util
import io
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def migration():
    path = Path(__file__).resolve().parents[1] / "migrations/versions/d9e4b7a2c106_expand_function_director_assignments.py"
    spec = importlib.util.spec_from_file_location("function_grants_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def database(migration):
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.String(), primary_key=True))
    grants = sa.Table("user_function_assignments", metadata,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("function_name", sa.String(50), nullable=False),
        sa.UniqueConstraint("user_id", "function_name", name="uq_user_function_assignment"),
        sa.CheckConstraint(migration._constraint(migration.OLD_NAMES), name=migration.CONSTRAINT),
        sa.Index("idx_user_function_assignment_scope", "user_id", "function_name"),
    )
    metadata.create_all(engine)
    with engine.connect() as connection:
        connection.execute(sa.text("INSERT INTO users (id) VALUES ('audit')"))
        connection.execute(grants.insert().values(id="legacy", user_id="audit", function_name="Pre-Approvals"))
        connection.commit()
        yield connection, grants
    engine.dispose()


def _run(module, connection, operation):
    with Operations.context(MigrationContext.configure(connection)):
        getattr(module, operation)()


def test_upgrade_and_rollback_preserve_old_grants_and_constraints(migration, database):
    connection, grants = database
    _run(migration, connection, "upgrade")
    assert connection.execute(sa.select(grants.c.function_name)).scalars().all() == ["Pre-Approvals"]
    for name in ("Sales", "CSR", "Pharmacy"):
        connection.execute(grants.insert().values(id=name, user_id="audit", function_name=name))
    assert connection.execute(sa.select(sa.func.count()).select_from(grants)).scalar_one() == 4
    inspector = sa.inspect(connection)
    assert inspector.get_unique_constraints("user_function_assignments")[0]["column_names"] == ["user_id", "function_name"]
    assert inspector.get_foreign_keys("user_function_assignments")[0]["referred_table"] == "users"
    assert any(index["name"] == "idx_user_function_assignment_scope" for index in inspector.get_indexes("user_function_assignments"))
    connection.execute(grants.delete().where(grants.c.function_name.in_(("Sales", "CSR", "Pharmacy"))))
    _run(migration, connection, "downgrade")
    assert connection.execute(sa.select(grants.c.function_name)).scalars().all() == ["Pre-Approvals"]
    with pytest.raises(IntegrityError):
        connection.execute(grants.insert().values(id="Sales", user_id="audit", function_name="Sales"))


def test_rollback_refuses_to_destroy_new_grants(migration, database):
    connection, grants = database
    _run(migration, connection, "upgrade")
    connection.execute(grants.insert().values(id="Sales", user_id="audit", function_name="Sales"))
    with pytest.raises(RuntimeError, match="Reassign"):
        _run(migration, connection, "downgrade")
    assert set(connection.execute(sa.select(grants.c.function_name)).scalars()) == {"Sales", "Pre-Approvals"}
    connection.execute(grants.insert().values(id="CSR", user_id="audit", function_name="CSR"))


@pytest.mark.parametrize("operation", ["upgrade", "downgrade"])
def test_postgresql_offline_sql_is_additive_and_rollback_has_guard(migration, operation):
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        getattr(migration, operation)()
    sql = output.getvalue()
    assert "ALTER TABLE user_function_assignments DROP CONSTRAINT" in sql
    assert "ALTER TABLE user_function_assignments ADD CONSTRAINT" in sql
    assert "DELETE FROM" not in sql and "DROP TABLE" not in sql
    if operation == "downgrade":
        assert "RAISE EXCEPTION" in sql and "Reassign" in sql
