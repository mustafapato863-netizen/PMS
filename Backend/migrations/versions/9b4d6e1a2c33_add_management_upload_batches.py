"""add management upload batch tracking

Revision ID: 9b4d6e1a2c33
Revises: 7c2f3b8a9d11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9b4d6e1a2c33"
down_revision = "7c2f3b8a9d11"
branch_labels = None
depends_on = None


def _uuid_type():
    return postgresql.UUID(as_uuid=True)


def upgrade():
    op.add_column("management_kpi_config", sa.Column("upload_batch_id", _uuid_type(), nullable=True))
    op.create_index("idx_management_kpi_config_batch", "management_kpi_config", ["upload_batch_id"], unique=False)

    op.add_column("management_kpi_snapshots", sa.Column("upload_batch_id", _uuid_type(), nullable=True))
    op.create_index("idx_management_kpi_snapshot_batch", "management_kpi_snapshots", ["upload_batch_id"], unique=False)

    op.add_column("management_kpi_config_history", sa.Column("upload_batch_id", _uuid_type(), nullable=True))
    op.add_column("management_kpi_config_history", sa.Column("source_filename", sa.String(length=255), nullable=True))
    op.create_index("idx_management_kpi_config_history_batch", "management_kpi_config_history", ["upload_batch_id"], unique=False)


def downgrade():
    op.drop_index("idx_management_kpi_config_history_batch", table_name="management_kpi_config_history")
    op.drop_column("management_kpi_config_history", "source_filename")
    op.drop_column("management_kpi_config_history", "upload_batch_id")

    op.drop_index("idx_management_kpi_snapshot_batch", table_name="management_kpi_snapshots")
    op.drop_column("management_kpi_snapshots", "upload_batch_id")

    op.drop_index("idx_management_kpi_config_batch", table_name="management_kpi_config")
    op.drop_column("management_kpi_config", "upload_batch_id")
