"""Ensure primary keys that later foreign keys reference.

Revision ID: 0b5d8e2f6c41
Revises: d9e4b7a2c106

The production schema has no primary key or unique constraint on teams.id or
performance_records(id, year). Revisions a7c3e5f9b214, e1b6c9d4a870,
f7c3a9e1d5b8 and b4e7c2a9d815 add foreign keys to them. Each key is added only
when it is missing and the data has no NULLs or duplicates (checked here at
runtime). Otherwise it is skipped with a warning, and the dependent foreign
keys are skipped too. No rows are modified.

Downgrade drops only keys this revision added (marked by a constraint comment)
and only when no foreign key depends on them.
"""

from alembic import op

from utils.schema_key_guards import drop_added_key, ensure_key


revision = "0b5d8e2f6c41"
down_revision = "d9e4b7a2c106"
branch_labels = None
depends_on = None

REFERENCED_KEYS = (
    ("teams", ("id",)),
    ("performance_records", ("id", "year")),
)


def upgrade() -> None:
    bind = op.get_bind()
    for table, columns in REFERENCED_KEYS:
        ensure_key(bind, table, columns, revision)


def downgrade() -> None:
    bind = op.get_bind()
    for table, columns in reversed(REFERENCED_KEYS):
        drop_added_key(bind, table, columns, revision)
