"""seed ai_access_tier product setting (and ensure value_str column exists)

Revision ID: d4e5f6a7b8c9
Revises: 5d3a9b1c7e20
"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "5d3a9b1c7e20"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("product_settings")}
    if "value_str" not in columns:
        op.add_column(
            "product_settings",
            sa.Column("value_str", sa.String(80), nullable=True),
        )

    existing = bind.execute(
        sa.text("SELECT 1 FROM product_settings WHERE key = :k"),
        {"k": "ai_access_tier"},
    ).first()
    if existing is None:
        bind.execute(
            sa.text(
                "INSERT INTO product_settings (key, enabled, value_str) "
                "VALUES (:k, :enabled, :val)"
            ),
            {"k": "ai_access_tier", "enabled": True, "val": "admin_only"},
        )


def downgrade():
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM product_settings WHERE key = :k"),
        {"k": "ai_access_tier"},
    )
