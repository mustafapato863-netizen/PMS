"""add rotating refresh sessions

Revision ID: a6d4e8f1c220
Revises: f5c2d7e8a901
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a6d4e8f1c220"
down_revision = "f5c2d7e8a901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ip_type = sa.String(length=45).with_variant(postgresql.INET(), "postgresql")
    op.create_table(
        "refresh_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("parent_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("replaced_by_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("remember_me", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", ip_type, nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_session_id"], ["refresh_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["replaced_by_session_id"], ["refresh_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_session_token_hash"),
    )
    op.create_index(
        "idx_refresh_session_user_active",
        "refresh_sessions",
        ["user_id", "revoked_at", "expires_at"],
    )
    op.create_index("idx_refresh_session_family", "refresh_sessions", ["family_id"])
    op.create_index("idx_refresh_session_parent", "refresh_sessions", ["parent_session_id"])


def downgrade() -> None:
    op.drop_index("idx_refresh_session_parent", table_name="refresh_sessions")
    op.drop_index("idx_refresh_session_family", table_name="refresh_sessions")
    op.drop_index("idx_refresh_session_user_active", table_name="refresh_sessions")
    op.drop_table("refresh_sessions")
