"""add persona_tier to ai_approved_patterns

Revision ID: c2d3e4f5a6b7
Revises: b8a4d91e0c72
"""

from alembic import op
import sqlalchemy as sa

revision = "c2d3e4f5a6b7"
down_revision = "b8a4d91e0c72"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_approved_patterns",
        sa.Column("persona_tier", sa.String(20), nullable=True),
    )
    op.create_index(
        "idx_ai_approved_patterns_persona",
        "ai_approved_patterns",
        ["is_active", "persona_tier"],
    )


def downgrade():
    op.drop_index("idx_ai_approved_patterns_persona", table_name="ai_approved_patterns")
    op.drop_column("ai_approved_patterns", "persona_tier")
