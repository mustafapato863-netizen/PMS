"""add ai provider configs

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9, f7c3a9e1d5b8

Merges the two open heads so the provider-config table lands on a single
linear head again.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e5f6a7b8c9d0"
down_revision = ("d4e5f6a7b8c9", "f7c3a9e1d5b8")
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_provider_configs",
        sa.Column("provider", sa.String(32), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.Column("primary_model", sa.String(160), nullable=True),
        sa.Column("alternate_model", sa.String(160), nullable=True),
        sa.Column("account_id_encrypted", sa.Text(), nullable=True),
        sa.Column("alternate_account_id_encrypted", sa.Text(), nullable=True),
        sa.Column("primary_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("alternate_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("active_key_slot", sa.String(16), nullable=False, server_default="primary"),
        sa.Column("auto_failover_key", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("daily_limit", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_ai_provider_configs_updated_at",
        "ai_provider_configs",
        ["updated_at"],
    )


def downgrade():
    op.drop_index("idx_ai_provider_configs_updated_at", table_name="ai_provider_configs")
    op.drop_table("ai_provider_configs")
