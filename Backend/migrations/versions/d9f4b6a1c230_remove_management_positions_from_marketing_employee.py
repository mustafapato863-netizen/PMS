"""remove management positions from Marketing employee configuration

Revision ID: d9f4b6a1c230
Revises: c2f8a6d9e410
Create Date: 2026-07-29
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9f4b6a1c230"
down_revision: Union[str, Sequence[str], None] = "c2f8a6d9e410"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MANAGEMENT_POSITIONS = (
    "Social Media Head",
    "Media Buyer & SEO Manager",
    "Creative Director",
)

LEGACY_EMPLOYEE_KPIS = (
    ("Social Media Head", "smh_response_rate", "Response rate (%)", "Customer", 0.25, "higher_better", "%", "#2563EB", 1),
    ("Social Media Head", "smh_channels_growth_rate", "Channels growth rate", "Customer", 0.10, "higher_better", "%", "#0D9488", 2),
    ("Social Media Head", "smh_campaign_reach", "Campaign reach", "Internal Process", 0.20, "higher_better", "%", "#D97706", 3),
    ("Social Media Head", "smh_response_time", "Response Time", "Internal Process", 0.15, "lower_better", "min", "#7C3AED", 4),
    ("Social Media Head", "smh_content_calendar_adherence", "Content calendar adherence", "Internal Process", 0.20, "higher_better", "%", "#DC2626", 5),
    ("Social Media Head", "smh_trend_competitive_research_hours", "Trend & competitive research hours", "Learning & Growth", 0.10, "higher_better", "hours", "#0891B2", 6),
    ("Media Buyer & SEO Manager", "mbsm_budget_compliance", "Budget Compliance", "Financial", 0.10, "higher_better", "%", "#2563EB", 1),
    ("Media Buyer & SEO Manager", "mbsm_revenue", "Revenue", "Financial", 0.15, "higher_better", "AED", "#0D9488", 2),
    ("Media Buyer & SEO Manager", "mbsm_bounce_rate", "Bounce Rate%", "Customer", 0.05, "lower_better", "%", "#D97706", 3),
    ("Media Buyer & SEO Manager", "mbsm_website_traffic", "Website Traffic", "Customer", 0.10, "higher_better", "visits", "#7C3AED", 4),
    ("Media Buyer & SEO Manager", "mbsm_leads", "Leads", "Customer", 0.15, "higher_better", "count", "#DC2626", 5),
    ("Media Buyer & SEO Manager", "mbsm_app_installs", "# App installs", "Customer", 0.10, "higher_better", "count", "#0891B2", 6),
    ("Media Buyer & SEO Manager", "mbsm_kwd_ranking_improvement", "KWD Ranking Improvement", "Internal Process", 0.10, "higher_better", "count", "#16A34A", 7),
    ("Media Buyer & SEO Manager", "mbsm_website_speed", "Website Speed", "Internal Process", 0.05, "higher_better", "score", "#EA580C", 8),
    ("Media Buyer & SEO Manager", "mbsm_volume", "Volume", "Internal Process", 0.20, "higher_better", "count", "#4F46E5", 9),
    ("Creative Director", "cd_brand_consistency_score", "Brand consistency score", "Internal Process", 0.20, "higher_better", "%", "#2563EB", 1),
    ("Creative Director", "cd_creative_delivery_timeliness", "Creative delivery timeliness", "Internal Process", 0.25, "higher_better", "%", "#0D9488", 2),
    ("Creative Director", "cd_creative_approval_rate_amendments", "Creative Approval Rate & Amendments", "Internal Process", 0.25, "higher_better", "%", "#D97706", 3),
    ("Creative Director", "cd_quantity", "Quantity", "Internal Process", 0.20, "higher_better", "count", "#7C3AED", 4),
    ("Creative Director", "cd_team_training_development_hours", "Team training & development hours", "Learning & Growth", 0.10, "higher_better", "hours", "#DC2626", 5),
)


def _marketing_employee_team_id(bind):
    return bind.execute(
        sa.text(
            """
            SELECT id
            FROM teams
            WHERE team_level = 'employee'
              AND lower(COALESCE(display_name, name)) = 'marketing'
            ORDER BY created_at
            LIMIT 1
            """
        )
    ).scalar_one_or_none()


def upgrade() -> None:
    bind = op.get_bind()
    team_id = _marketing_employee_team_id(bind)
    if team_id is None:
        return

    bind.execute(
        sa.text(
            """
            DELETE FROM team_kpi_config
            WHERE team_id = :team_id
              AND performance_level = 'Employee'
              AND position_name IN (
                'Social Media Head',
                'Media Buyer & SEO Manager',
                'Creative Director'
              )
            """
        ),
        {"team_id": team_id},
    )


def downgrade() -> None:
    bind = op.get_bind()
    team_id = _marketing_employee_team_id(bind)
    if team_id is None:
        return

    metadata = sa.MetaData()
    config_table = sa.Table("team_kpi_config", metadata, autoload_with=bind)
    existing = {
        (row.position_name, row.kpi_key)
        for row in bind.execute(
            sa.select(config_table.c.position_name, config_table.c.kpi_key).where(
                config_table.c.team_id == team_id,
                config_table.c.performance_level == "Employee",
                config_table.c.position_name.in_(MANAGEMENT_POSITIONS),
            )
        )
    }
    rows = []
    for position, key, label, perspective, weight, direction, unit, color, order in LEGACY_EMPLOYEE_KPIS:
        if (position, key) in existing:
            continue
        rows.append(
            {
                "id": uuid.uuid4(),
                "team_id": team_id,
                "performance_level": "Employee",
                "position_name": position,
                "perspective": perspective,
                "kpi_key": key,
                "kpi_label": label,
                "weight": weight,
                "direction": direction,
                "unit": unit,
                "color": color,
                "actual_col": "Actual Value",
                "target_col": "Target Value",
                "display_order": order,
            }
        )
    if rows:
        bind.execute(config_table.insert(), rows)
