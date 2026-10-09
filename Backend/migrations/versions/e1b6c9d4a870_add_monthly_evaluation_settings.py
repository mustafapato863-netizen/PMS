"""Add monthly evaluation scopes and exact-month bindings.

Revision ID: e1b6c9d4a870
Revises: d9e4b7a2c106

Expand-only. This revision does not update performance scores, plans,
actions, or saved reports. Downgrade refuses once a monthly binding exists.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e1b6c9d4a870"
down_revision = "d9e4b7a2c106"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("team_configuration_versions", sa.Column("performance_level", sa.String(length=20), nullable=True))
    op.add_column("team_configuration_versions", sa.Column("position_name", sa.String(length=255), nullable=True))
    op.create_check_constraint(
        "ck_team_config_version_level",
        "team_configuration_versions",
        "performance_level IS NULL OR performance_level IN ('Employee', 'Managerial', 'Corporate')",
    )
    op.create_index(
        "uq_team_config_one_approved_month",
        "team_configuration_versions",
        ["team_id", "performance_level", "position_name", "effective_from_year", "effective_from_month"],
        unique=True,
        postgresql_where=sa.text("status = 'approved' AND performance_level IS NOT NULL"),
    )
    op.create_index(
        "uq_team_config_one_draft_month",
        "team_configuration_versions",
        ["team_id", "performance_level", "position_name", "effective_from_year", "effective_from_month"],
        unique=True,
        postgresql_where=sa.text("status = 'draft' AND performance_level IS NOT NULL"),
    )

    op.create_table(
        "evaluation_scopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("team_key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("performance_level", sa.String(length=20), nullable=False),
        sa.Column("position_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("readiness", sa.String(length=40), nullable=False),
        sa.Column("block_reason", sa.Text(), nullable=True),
        sa.Column("history_note", sa.Text(), nullable=False),
        sa.Column("ambiguous_kpis", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("importer_name", sa.String(length=120), nullable=True),
        sa.Column("policy_family", sa.String(length=40), nullable=False, server_default="employee_ratio"),
        sa.Column("source_kind", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "performance_level IN ('Employee', 'Managerial', 'Corporate')",
            name="ck_evaluation_scope_level",
        ),
        sa.CheckConstraint(
            "readiness IN ('supported', 'blocked', 'unlinked_baseline')",
            name="ck_evaluation_scope_readiness",
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_key", "performance_level", "position_name", name="uq_evaluation_scope_identity"),
    )
    op.create_table(
        "evaluation_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("performance_level", sa.String(length=20), nullable=False),
        sa.Column("position_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("month", sa.SmallInteger(), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("previous_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("prior_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("applied_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active', 'rolled_back')", name="ck_evaluation_revision_status"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_evaluation_revision_month"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["team_configuration_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["previous_revision_id"], ["evaluation_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_evaluation_revision_period",
        "evaluation_revisions",
        ["team_id", "performance_level", "position_name", "year", "month", "status"],
    )


def downgrade():
    bind = op.get_bind()
    bindings = bind.execute(
        sa.text("SELECT count(*) FROM team_configuration_versions WHERE performance_level IS NOT NULL")
    ).scalar()
    if bindings:
        raise RuntimeError(
            "Monthly evaluation bindings exist. Rollback has to restore a previous active revision, not drop this schema."
        )
    op.drop_index("idx_evaluation_revision_period", table_name="evaluation_revisions")
    op.drop_table("evaluation_revisions")
    op.drop_table("evaluation_scopes")
    op.drop_index("uq_team_config_one_draft_month", table_name="team_configuration_versions")
    op.drop_index("uq_team_config_one_approved_month", table_name="team_configuration_versions")
    op.drop_constraint("ck_team_config_version_level", "team_configuration_versions", type_="check")
    op.drop_column("team_configuration_versions", "position_name")
    op.drop_column("team_configuration_versions", "performance_level")
