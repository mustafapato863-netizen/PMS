"""split logical teams into employee and management identities

Revision ID: 7f3c9a1d2e40
Revises: 6e8a4f2c9d10
"""

from __future__ import annotations

import re
import uuid

from alembic import op
import sqlalchemy as sa


revision = "7f3c9a1d2e40"
down_revision = "6e8a4f2c9d10"
branch_labels = None
depends_on = None


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")
    return normalized or "team"


def _unique_value(bind, column: str, base: str) -> str:
    candidate = base[:100]
    suffix = 2
    while bind.execute(
        sa.text(f"SELECT 1 FROM teams WHERE lower({column}) = lower(:value) LIMIT 1"),
        {"value": candidate},
    ).first():
        suffix_text = f"_{suffix}"
        candidate = f"{base[:100 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE teams SET display_name = name WHERE display_name IS NULL"))

    source_team_ids = [
        row[0]
        for row in bind.execute(sa.text(
            """
            SELECT DISTINCT team_id FROM management_kpi_config
            UNION
            SELECT DISTINCT team_id FROM management_kpi_snapshots
            UNION
            SELECT DISTINCT team_id FROM management_kpi_config_history
            UNION
            SELECT DISTINCT team_id FROM user_team_assignments
            WHERE performance_level IN ('Managerial', 'Corporate')
            """
        )).all()
    ]

    for source_team_id in source_team_ids:
        source = bind.execute(
            sa.text(
                """
                SELECT id, name, db_name, display_name, region, team_level, is_active
                FROM teams
                WHERE id = :team_id
                """
            ),
            {"team_id": source_team_id},
        ).mappings().one()
        logical_name = source["display_name"] or source["name"]

        if source["team_level"] == "management":
            management_team_id = source["id"]
        else:
            existing = bind.execute(
                sa.text(
                    """
                    SELECT id
                    FROM teams
                    WHERE team_level = 'management'
                      AND lower(COALESCE(display_name, name)) = lower(:logical_name)
                    ORDER BY created_at
                    LIMIT 1
                    """
                ),
                {"logical_name": logical_name},
            ).first()
            if existing:
                management_team_id = existing[0]
                bind.execute(
                    sa.text(
                        """
                        UPDATE teams
                        SET is_active = is_active OR :source_is_active
                        WHERE id = :team_id
                        """
                    ),
                    {
                        "source_is_active": source["is_active"],
                        "team_id": management_team_id,
                    },
                )
            else:
                management_team_id = uuid.uuid4()
                base = f"{_slug(logical_name)}_management"
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO teams (
                            id, name, db_name, display_name, region,
                            team_level, is_active
                        )
                        VALUES (
                            :id, :name, :db_name, :display_name, :region,
                            'management', :is_active
                        )
                        """
                    ),
                    {
                        "id": management_team_id,
                        "name": _unique_value(bind, "name", base),
                        "db_name": _unique_value(bind, "db_name", base),
                        "display_name": logical_name,
                        "region": source["region"] or "UAE",
                        "is_active": source["is_active"],
                    },
                )

            for table_name in (
                "management_kpi_config",
                "management_kpi_snapshots",
                "management_kpi_config_history",
            ):
                bind.execute(
                    sa.text(f"UPDATE {table_name} SET team_id = :target WHERE team_id = :source"),
                    {"target": management_team_id, "source": source_team_id},
                )

            bind.execute(
                sa.text(
                    """
                    UPDATE user_team_assignments
                    SET team_id = :target
                    WHERE team_id = :source
                      AND performance_level IN ('Managerial', 'Corporate')
                    """
                ),
                {"target": management_team_id, "source": source_team_id},
            )
            unrestricted = bind.execute(
                sa.text(
                    """
                    SELECT user_id, access_level, assigned_at, assigned_by
                    FROM user_team_assignments
                    WHERE team_id = :source AND performance_level IS NULL
                    """
                ),
                {"source": source_team_id},
            ).mappings().all()
            for assignment in unrestricted:
                exists = bind.execute(
                    sa.text(
                        """
                        SELECT 1 FROM user_team_assignments
                        WHERE user_id = :user_id
                          AND team_id = :team_id
                          AND performance_level IS NULL
                        LIMIT 1
                        """
                    ),
                    {"user_id": assignment["user_id"], "team_id": management_team_id},
                ).first()
                if not exists:
                    bind.execute(
                        sa.text(
                            """
                            INSERT INTO user_team_assignments (
                                id, user_id, team_id, performance_level,
                                access_level, assigned_at, assigned_by
                            )
                            VALUES (
                                :id, :user_id, :team_id, NULL,
                                :access_level, :assigned_at, :assigned_by
                            )
                            """
                        ),
                        {
                            "id": uuid.uuid4(),
                            "user_id": assignment["user_id"],
                            "team_id": management_team_id,
                            "access_level": assignment["access_level"],
                            "assigned_at": assignment["assigned_at"],
                            "assigned_by": assignment["assigned_by"],
                        },
                    )

    op.create_check_constraint(
        "ck_team_level",
        "teams",
        "team_level IN ('employee', 'management')",
    )
    op.create_index(
        "uq_team_logical_level_ci",
        "teams",
        [sa.text("lower(COALESCE(display_name, name))"), "team_level"],
        unique=True,
    )
    op.create_index(
        "idx_team_scope_lookup",
        "teams",
        ["display_name", "team_level", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    management_teams = bind.execute(
        sa.text(
            """
            SELECT id, COALESCE(display_name, name) AS logical_name
            FROM teams
            WHERE team_level = 'management'
            """
        )
    ).mappings().all()
    for management_team in management_teams:
        employee = bind.execute(
            sa.text(
                """
                SELECT id FROM teams
                WHERE team_level = 'employee'
                  AND lower(COALESCE(display_name, name)) = lower(:logical_name)
                ORDER BY created_at
                LIMIT 1
                """
            ),
            {"logical_name": management_team["logical_name"]},
        ).first()
        if not employee:
            continue
        for table_name in (
            "management_kpi_config",
            "management_kpi_snapshots",
            "management_kpi_config_history",
        ):
            bind.execute(
                sa.text(f"UPDATE {table_name} SET team_id = :target WHERE team_id = :source"),
                {"target": employee[0], "source": management_team["id"]},
            )
        bind.execute(
            sa.text(
                """
                UPDATE user_team_assignments
                SET team_id = :target
                WHERE team_id = :source
                  AND performance_level IN ('Managerial', 'Corporate')
                """
            ),
            {"target": employee[0], "source": management_team["id"]},
        )

    op.drop_index("idx_team_scope_lookup", table_name="teams")
    op.drop_index("uq_team_logical_level_ci", table_name="teams")
    op.drop_constraint("ck_team_level", "teams", type_="check")
