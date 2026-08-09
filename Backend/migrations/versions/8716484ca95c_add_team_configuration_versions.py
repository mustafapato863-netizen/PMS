"""add team configuration versions

Revision ID: 8716484ca95c
Revises: 0402585d70d0
Create Date: 2026-07-07 01:26:24.672678
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8716484ca95c"
down_revision: Union[str, Sequence[str], None] = "0402585d70d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_configuration_versions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("effective_month", sa.String(length=20), nullable=False),
        sa.Column("effective_year", sa.SmallInteger(), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("config_checksum", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("team_id", "version_number", name="uq_team_config_version"),
    )

    op.add_column(
        "team_onboarding_drafts",
        sa.Column("published_team_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "team_onboarding_drafts",
        sa.Column(
            "published_configuration_version_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column("team_onboarding_drafts", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "team_onboarding_drafts",
        sa.Column("published_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_drafts_published_team",
        "team_onboarding_drafts",
        "teams",
        ["published_team_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_drafts_published_config",
        "team_onboarding_drafts",
        "team_configuration_versions",
        ["published_configuration_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_drafts_published_by",
        "team_onboarding_drafts",
        "users",
        ["published_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_drafts_published_by", "team_onboarding_drafts", type_="foreignkey")
    op.drop_constraint("fk_drafts_published_config", "team_onboarding_drafts", type_="foreignkey")
    op.drop_constraint("fk_drafts_published_team", "team_onboarding_drafts", type_="foreignkey")
    op.drop_column("team_onboarding_drafts", "published_by_user_id")
    op.drop_column("team_onboarding_drafts", "published_at")
    op.drop_column("team_onboarding_drafts", "published_configuration_version_id")
    op.drop_column("team_onboarding_drafts", "published_team_id")
    op.drop_table("team_configuration_versions")
