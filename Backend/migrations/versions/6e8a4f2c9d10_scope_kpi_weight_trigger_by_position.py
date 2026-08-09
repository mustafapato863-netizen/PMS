"""scope KPI weight validation by performance level and position

Revision ID: 6e8a4f2c9d10
Revises: f6c2a9d4e810
"""

from alembic import op


revision = "6e8a4f2c9d10"
down_revision = "f6c2a9d4e810"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION check_kpi_weights_sum()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        DECLARE
          total NUMERIC;
        BEGIN
          SELECT ROUND(COALESCE(SUM(weight), 0)::numeric, 4)
          INTO total
          FROM team_kpi_config
          WHERE team_id = NEW.team_id
            AND performance_level = NEW.performance_level
            AND COALESCE(position_name, '') = COALESCE(NEW.position_name, '');

          IF total > 1.0001 THEN
            RAISE EXCEPTION
              'KPI weights for team %, level %, position % sum to %, must not exceed 1.0',
              NEW.team_id,
              NEW.performance_level,
              COALESCE(NEW.position_name, ''),
              total;
          END IF;
          RETURN NEW;
        END;
        $function$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION check_kpi_weights_sum()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        DECLARE
          total NUMERIC;
        BEGIN
          SELECT ROUND(SUM(weight)::numeric, 4)
          INTO total
          FROM team_kpi_config
          WHERE team_id = NEW.team_id;

          IF total > 1.0001 THEN
            RAISE EXCEPTION
              'KPI weights for team % sum to %, must equal 1.0',
              NEW.team_id,
              total;
          END IF;
          RETURN NEW;
        END;
        $function$;
        """
    )
