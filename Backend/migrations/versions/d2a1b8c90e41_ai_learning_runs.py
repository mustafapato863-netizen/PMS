"""Daily AI feedback worker checkpoints."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "d2a1b8c90e41"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_learning_runs",
        sa.Column("day", sa.String(10), primary_key=True),
        sa.Column("claim", sa.String(36), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("results", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    )


def downgrade():
    op.drop_table("ai_learning_runs")
