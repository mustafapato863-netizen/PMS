"""add employee upload batches and persisted dashboard payload

Revision ID: e8c1a7d4b920
Revises: d5a7c9e2f410
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e8c1a7d4b920"
down_revision = "d5a7c9e2f410"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_upload_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("team_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="processing"),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uploaded_by_name", sa.String(length=255), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "upload_log",
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_upload_log_batch_id",
        "upload_log",
        "employee_upload_batches",
        ["batch_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_upload_log_batch", "upload_log", ["batch_id"], unique=False)
    op.add_column(
        "performance_records",
        sa.Column(
            "record_payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )

    # Existing UploadLog rows did not identify source files and their counts
    # were incremented on every replacement.  Consolidate them into one honest
    # legacy batch and recalculate counts from the current records.
    connection = op.get_bind()
    existing_logs = connection.execute(sa.text("SELECT COUNT(*) FROM upload_log")).scalar_one()
    if existing_logs:
        legacy_batch_id = uuid.uuid4()
        aggregate = connection.execute(sa.text("""
            SELECT
                COUNT(*) AS record_count,
                COUNT(DISTINCT performance_records.team_id) AS team_count,
                MAX(upload_log.uploaded_at) AS uploaded_at
            FROM performance_records
            LEFT JOIN upload_log ON upload_log.id = performance_records.upload_id
        """)).mappings().one()
        connection.execute(
            sa.text("""
                INSERT INTO employee_upload_batches
                    (id, filename, record_count, team_count, status, uploaded_by_name, uploaded_at)
                VALUES
                    (:id, :filename, :record_count, :team_count, 'success', 'Admin', :uploaded_at)
            """),
            {
                "id": legacy_batch_id,
                "filename": "Legacy PMS data (before file tracking)",
                "record_count": int(aggregate["record_count"] or 0),
                "team_count": int(aggregate["team_count"] or 0),
                "uploaded_at": aggregate["uploaded_at"],
            },
        )
        connection.execute(
            sa.text("UPDATE upload_log SET batch_id = :batch_id WHERE batch_id IS NULL"),
            {"batch_id": legacy_batch_id},
        )
        connection.execute(sa.text("""
            UPDATE upload_log
            SET record_count = (
                SELECT COUNT(*)
                FROM performance_records
                WHERE performance_records.upload_id = upload_log.id
            )
        """))


def downgrade() -> None:
    op.drop_column("performance_records", "record_payload")
    op.drop_index("idx_upload_log_batch", table_name="upload_log")
    op.drop_constraint("fk_upload_log_batch_id", "upload_log", type_="foreignkey")
    op.drop_column("upload_log", "batch_id")
    op.drop_table("employee_upload_batches")
