"""add configuration coverage

Revision ID: b8f2d4a9c731
Revises: 8716484ca95c
Create Date: 2026-07-07 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b8f2d4a9c731"
down_revision: Union[str, Sequence[str], None] = "8716484ca95c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MONTH_CASE = """
CASE lower(trim(effective_month))
    WHEN 'january' THEN 1
    WHEN 'february' THEN 2
    WHEN 'march' THEN 3
    WHEN 'april' THEN 4
    WHEN 'may' THEN 5
    WHEN 'june' THEN 6
    WHEN 'july' THEN 7
    WHEN 'august' THEN 8
    WHEN 'september' THEN 9
    WHEN 'october' THEN 10
    WHEN 'november' THEN 11
    WHEN 'december' THEN 12
    ELSE NULL
END
"""


def upgrade() -> None:
    op.add_column("team_configuration_versions", sa.Column("effective_from_month", sa.SmallInteger(), nullable=True))
    op.add_column("team_configuration_versions", sa.Column("effective_from_year", sa.SmallInteger(), nullable=True))
    op.add_column("team_configuration_versions", sa.Column("effective_until_month", sa.SmallInteger(), nullable=True))
    op.add_column("team_configuration_versions", sa.Column("effective_until_year", sa.SmallInteger(), nullable=True))
    op.add_column(
        "performance_records",
        sa.Column("configuration_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    bind = op.get_bind()
    invalid = bind.execute(
        sa.text(
            f"""
            SELECT id, effective_month, effective_year
            FROM team_configuration_versions
            WHERE {MONTH_CASE} IS NULL OR effective_year IS NULL
            """
        )
    ).fetchall()
    if invalid:
        raise RuntimeError(f"Invalid team configuration effective periods require manual cleanup: {invalid}")

    ambiguous = bind.execute(
        sa.text(
            """
            SELECT team_id, count(*) AS version_count
            FROM team_configuration_versions
            WHERE status = 'published'
            GROUP BY team_id
            HAVING count(*) > 1
            """
        )
    ).fetchall()
    if ambiguous:
        raise RuntimeError(
            f"Multiple published versions would migrate as overlapping open-ended coverage: {ambiguous}"
        )

    bind.execute(
        sa.text(
            f"""
            UPDATE team_configuration_versions
            SET effective_from_month = {MONTH_CASE},
                effective_from_year = effective_year
            """
        )
    )

    op.alter_column("team_configuration_versions", "effective_from_month", nullable=False)
    op.alter_column("team_configuration_versions", "effective_from_year", nullable=False)
    op.create_check_constraint(
        "ck_team_config_effective_from_month",
        "team_configuration_versions",
        "effective_from_month BETWEEN 1 AND 12",
    )
    op.create_check_constraint(
        "ck_team_config_effective_until_month",
        "team_configuration_versions",
        "effective_until_month IS NULL OR effective_until_month BETWEEN 1 AND 12",
    )
    op.create_check_constraint(
        "ck_team_config_effective_range",
        "team_configuration_versions",
        "effective_until_year IS NULL OR "
        "(effective_until_year * 12 + effective_until_month) >= "
        "(effective_from_year * 12 + effective_from_month)",
    )
    op.create_index(
        "idx_team_config_coverage",
        "team_configuration_versions",
        [
            "team_id",
            "status",
            "effective_from_year",
            "effective_from_month",
            "effective_until_year",
            "effective_until_month",
        ],
    )
    op.create_foreign_key(
        "fk_performance_records_configuration_version",
        "performance_records",
        "team_configuration_versions",
        ["configuration_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_performance_records_configuration_version", "performance_records", type_="foreignkey")
    op.drop_index("idx_team_config_coverage", table_name="team_configuration_versions")
    op.drop_constraint("ck_team_config_effective_range", "team_configuration_versions", type_="check")
    op.drop_constraint("ck_team_config_effective_until_month", "team_configuration_versions", type_="check")
    op.drop_constraint("ck_team_config_effective_from_month", "team_configuration_versions", type_="check")
    op.drop_column("performance_records", "configuration_version_id")
    op.drop_column("team_configuration_versions", "effective_until_year")
    op.drop_column("team_configuration_versions", "effective_until_month")
    op.drop_column("team_configuration_versions", "effective_from_year")
    op.drop_column("team_configuration_versions", "effective_from_month")
