"""Ensure team_configuration_versions exists before monthly evaluation settings.

Revision ID: a7c3e5f9b214
Revises: d9e4b7a2c106

Production was initialized by scripts.bootstrap_schema (ORM create_all + stamp)
from code whose models did not yet define TeamConfigurationVersion. The table
is created by 8716484ca95c (and extended by b8f2d4a9c731, c4a7b7d8f2ac), all
ancestors of d9e4b7a2c106, so the stamp marked them applied without running
them. e1b6c9d4a870 then failed with UndefinedTable.

This revision is idempotent: if the table is present (any database that really
ran the historical chain, or was bootstrapped from current models) it does
nothing. Otherwise it creates the table in the shape those three revisions
would have left it in, so e1b6c9d4a870 and f7c3a9e1d5b8 apply unchanged.

Downgrade is intentionally a no-op: this revision cannot tell whether it
created the table, and it must never drop configuration history.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a7c3e5f9b214"
down_revision = "d9e4b7a2c106"
branch_labels = None
depends_on = None

TABLE = "team_configuration_versions"


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(TABLE):
        return

    op.create_table(
        TABLE,
        # 8716484ca95c
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("effective_month", sa.String(length=20), nullable=False),
        sa.Column("effective_year", sa.SmallInteger(), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("config_checksum", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        # b8f2d4a9c731
        sa.Column("effective_from_month", sa.SmallInteger(), nullable=False),
        sa.Column("effective_from_year", sa.SmallInteger(), nullable=False),
        sa.Column("effective_until_month", sa.SmallInteger(), nullable=True),
        sa.Column("effective_until_year", sa.SmallInteger(), nullable=True),
        # c4a7b7d8f2ac
        sa.Column("preview_snapshot", sa.JSON(), nullable=True),
        sa.Column("total_weight", sa.Numeric(7, 4), nullable=True),
        sa.Column("overall_score", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("team_id", "version_number", name="uq_team_config_version"),
        sa.CheckConstraint("effective_from_month BETWEEN 1 AND 12", name="ck_team_config_effective_from_month"),
        sa.CheckConstraint(
            "effective_until_month IS NULL OR effective_until_month BETWEEN 1 AND 12",
            name="ck_team_config_effective_until_month",
        ),
        sa.CheckConstraint(
            "effective_until_year IS NULL OR "
            "(effective_until_year * 12 + effective_until_month) >= "
            "(effective_from_year * 12 + effective_from_month)",
            name="ck_team_config_effective_range",
        ),
    )
    op.create_index(
        "idx_team_config_coverage",
        TABLE,
        [
            "team_id",
            "status",
            "effective_from_year",
            "effective_from_month",
            "effective_until_year",
            "effective_until_month",
        ],
    )


def downgrade() -> None:
    # Never drop configuration history; see module docstring.
    pass
