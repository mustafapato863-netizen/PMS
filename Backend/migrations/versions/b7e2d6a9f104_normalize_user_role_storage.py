"""Align legacy PostgreSQL role storage with the application's string model.

Revision ID: b7e2d6a9f104
Revises: a4c8e9d1f203

Some databases were bootstrapped with the four-value ``user_role`` enum.
Keeping that column as an enum rejects both current roles and queries that
include legacy role names. Preserve every account and its current role while
using VARCHAR(50), as declared by the User model. Retain the enum for rollback.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b7e2d6a9f104"
down_revision = "a4c8e9d1f203"
branch_labels = None
depends_on = None


def _change_role_type(column, target_type, using, default_cast):
    default = column.get("default")
    if default is not None:
        op.alter_column("users", "role", server_default=None)
    op.alter_column(
        "users",
        "role",
        existing_type=column["type"],
        type_=target_type,
        existing_nullable=column["nullable"],
        postgresql_using=using,
    )
    if default is not None:
        op.alter_column(
            "users", "role", server_default=sa.text(f"({default})::{default_cast}")
        )


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return
    inspector = sa.inspect(connection)
    column = next(c for c in inspector.get_columns("users") if c["name"] == "role")
    if not isinstance(column["type"], postgresql.ENUM):
        return
    if column["type"].name != "user_role":
        raise RuntimeError("Unexpected users.role enum; inspect it before migrating.")
    _change_role_type(column, sa.String(50), "role::text", "text")


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return
    inspector = sa.inspect(connection)
    column = next(c for c in inspector.get_columns("users") if c["name"] == "role")
    if isinstance(column["type"], postgresql.ENUM):
        return
    legacy_enum = next(
        (e for e in inspector.get_enums() if e["name"] == "user_role" and e["visible"]),
        None,
    )
    # Databases that already used strings have no legacy enum to restore.
    if legacy_enum is None:
        return
    users = sa.table("users", sa.column("role", sa.String(50)))
    unsupported = connection.execute(
        sa.select(sa.func.count()).select_from(users).where(
            users.c.role.not_in(legacy_enum["labels"])
        )
    ).scalar_one()
    if unsupported:
        raise RuntimeError(
            "Cannot downgrade user roles: reassign roles unsupported by the legacy "
            "user_role enum before retrying. No accounts have been changed."
        )
    enum_type = postgresql.ENUM(
        *legacy_enum["labels"],
        name="user_role",
        schema=legacy_enum["schema"],
        create_type=False,
    )
    enum_sql = connection.dialect.identifier_preparer.format_type(enum_type)
    _change_role_type(column, enum_type, f"role::text::{enum_sql}", enum_sql)
