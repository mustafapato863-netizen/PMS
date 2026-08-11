"""add durable processing jobs

Revision ID: f5c2d7e8a901
Revises: e4a7c1d9b520
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f5c2d7e8a901"
down_revision = "e4a7c1d9b520"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(
        postgresql.JSONB(astext_type=sa.Text()),
        "postgresql",
    )
    op.create_table(
        "processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_by_name", sa.String(length=255), nullable=True),
        sa.Column("request_json", json_type, nullable=False),
        sa.Column("input_path", sa.String(length=500), nullable=True),
        sa.Column("progress", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("worker_id", sa.String(length=150), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_type", sa.String(length=60), nullable=True),
        sa.Column("result_id", sa.String(length=100), nullable=True),
        sa.Column("result_json", json_type, nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("safe_error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "idempotency_key", name="uq_processing_job_idempotency"),
        sa.CheckConstraint(
            "kind IN ('pms_upload', 'report_generation', 'story_report_generation')",
            name="ck_processing_job_kind",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_processing_job_status",
        ),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_processing_job_progress"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_processing_job_attempts"),
        sa.CheckConstraint("max_attempts >= 1", name="ck_processing_job_max_attempts"),
    )
    op.create_index(
        "idx_processing_job_claim",
        "processing_jobs",
        ["status", "available_at", "created_at"],
    )
    op.create_index(
        "idx_processing_job_requester",
        "processing_jobs",
        ["requested_by_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_processing_job_requester", table_name="processing_jobs")
    op.drop_index("idx_processing_job_claim", table_name="processing_jobs")
    op.drop_table("processing_jobs")
