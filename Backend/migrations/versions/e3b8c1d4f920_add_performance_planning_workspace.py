"""add performance planning workspace

Revision ID: e3b8c1d4f920
Revises: c7e9a4b2d610
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e3b8c1d4f920"
down_revision = "c7e9a4b2d610"
branch_labels = None
depends_on = None


def upgrade() -> None:
    u = postgresql.UUID(as_uuid=True)
    op.create_table(
        "performance_plans",
        sa.Column("id", u, primary_key=True), sa.Column("name", sa.String(180), nullable=False),
        sa.Column("scope_type", sa.String(20), nullable=False), sa.Column("team_id", u, sa.ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("performance_level", sa.String(20), nullable=False), sa.Column("region", sa.String(10)),
        sa.Column("position_name", sa.String(255)), sa.Column("employee_id", u, sa.ForeignKey("employees.id", ondelete="RESTRICT")),
        sa.Column("period_start", sa.Date(), nullable=False), sa.Column("period_end", sa.Date(), nullable=False), sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("owner_user_id", u, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("baseline_value", sa.Numeric(18, 4), nullable=False), sa.Column("target_value", sa.Numeric(18, 4), nullable=False),
        sa.Column("current_value", sa.Numeric(18, 4)), sa.Column("outcome_unit", sa.String(30), nullable=False),
        sa.Column("outcome_direction", sa.String(20), nullable=False), sa.Column("expected_impact", sa.Numeric(18, 4)), sa.Column("actual_impact", sa.Numeric(18, 4)),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("status_reason", sa.Text()), sa.Column("no_insight_reason", sa.Text()),
        sa.Column("completion_date", sa.Date()), sa.Column("completion_note", sa.Text()), sa.Column("completed_by_user_id", u, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_by_user_id", u, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_by_user_id", u, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("scope_type IN ('Team', 'Position', 'Employee', 'Management')", name="ck_performance_plan_scope_type"),
        sa.CheckConstraint("performance_level IN ('Employee', 'Managerial', 'Corporate')", name="ck_performance_plan_level"),
        sa.CheckConstraint("status IN ('Draft', 'In Progress', 'At Risk', 'Completed', 'Archived')", name="ck_performance_plan_status"),
        sa.CheckConstraint("outcome_direction IN ('higher_better', 'lower_better')", name="ck_performance_plan_direction"),
        sa.CheckConstraint("period_end >= period_start", name="ck_performance_plan_period"),
    )
    op.create_index("idx_performance_plan_scope_status", "performance_plans", ["team_id", "performance_level", "status"])
    op.create_table(
        "plan_insight_links", sa.Column("id", u, primary_key=True), sa.Column("plan_id", u, sa.ForeignKey("performance_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("insight_id", sa.String(64), nullable=False), sa.Column("evidence_month", sa.String(20), nullable=False), sa.Column("evidence_year", sa.SmallInteger(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("plan_id", "insight_id", name="uq_plan_insight_link"),
    )
    op.create_table(
        "plan_objectives", sa.Column("id", u, primary_key=True), sa.Column("plan_id", u, sa.ForeignKey("performance_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False), sa.Column("measurement_type", sa.String(30), nullable=False),
        sa.Column("baseline_value", sa.Numeric(18, 4), nullable=False), sa.Column("target_value", sa.Numeric(18, 4), nullable=False), sa.Column("current_value", sa.Numeric(18, 4)),
        sa.Column("unit", sa.String(30), nullable=False), sa.Column("direction", sa.String(20), nullable=False), sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("owner_user_id", u, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.CheckConstraint("direction IN ('higher_better', 'lower_better')", name="ck_plan_objective_direction"),
        sa.CheckConstraint("status IN ('Not Started', 'In Progress', 'Completed', 'At Risk')", name="ck_plan_objective_status"),
    )
    op.create_table(
        "plan_kpis", sa.Column("id", u, primary_key=True), sa.Column("plan_id", u, sa.ForeignKey("performance_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kpi_key", sa.String(100), nullable=False), sa.Column("kpi_label", sa.String(255), nullable=False), sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False), sa.Column("baseline_value", sa.Numeric(18, 4), nullable=False), sa.Column("target_value", sa.Numeric(18, 4), nullable=False),
        sa.Column("current_value", sa.Numeric(18, 4)), sa.Column("contribution", sa.Numeric(18, 4)), sa.Column("data_month", sa.String(20)), sa.Column("data_year", sa.SmallInteger()),
        sa.UniqueConstraint("plan_id", "kpi_key", name="uq_plan_kpi_key"), sa.CheckConstraint("direction IN ('higher_better', 'lower_better')", name="ck_plan_kpi_direction"),
    )
    op.create_table(
        "plan_objective_kpis", sa.Column("objective_id", u, sa.ForeignKey("plan_objectives.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("kpi_id", u, sa.ForeignKey("plan_kpis.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "plan_milestones", sa.Column("id", u, primary_key=True), sa.Column("plan_id", u, sa.ForeignKey("performance_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False), sa.Column("due_date", sa.Date(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("completion_date", sa.Date()), sa.Column("owner_user_id", u, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("note", sa.Text()),
        sa.CheckConstraint("status IN ('Pending', 'In Progress', 'Completed', 'Overdue')", name="ck_plan_milestone_status"),
    )
    op.create_table(
        "plan_notes", sa.Column("id", u, primary_key=True), sa.Column("plan_id", u, sa.ForeignKey("performance_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_user_id", u, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("text", sa.Text(), nullable=False),
        sa.Column("review_month", sa.String(20)), sa.Column("review_year", sa.SmallInteger()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    with op.batch_alter_table("actions") as batch:
        batch.alter_column("employee_id", existing_type=u, nullable=True)
        batch.add_column(sa.Column("plan_id", u, nullable=True)); batch.add_column(sa.Column("objective_id", u, nullable=True)); batch.add_column(sa.Column("owner_user_id", u, nullable=True))
        batch.add_column(sa.Column("due_date", sa.Date())); batch.add_column(sa.Column("priority", sa.String(20))); batch.add_column(sa.Column("linked_kpi_key", sa.String(100)))
        batch.add_column(sa.Column("completion_note", sa.Text())); batch.add_column(sa.Column("evidence_reference", sa.String(500)))
        batch.create_foreign_key("fk_actions_plan_id", "performance_plans", ["plan_id"], ["id"], ondelete="CASCADE")
        batch.create_foreign_key("fk_actions_objective_id", "plan_objectives", ["objective_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_actions_owner_user_id", "users", ["owner_user_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("actions") as batch:
        for name in ("fk_actions_owner_user_id", "fk_actions_objective_id", "fk_actions_plan_id"): batch.drop_constraint(name, type_="foreignkey")
        for name in ("evidence_reference", "completion_note", "linked_kpi_key", "priority", "due_date", "owner_user_id", "objective_id", "plan_id"): batch.drop_column(name)
        batch.alter_column("employee_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    for table in ("plan_notes", "plan_milestones", "plan_objective_kpis", "plan_kpis", "plan_objectives", "plan_insight_links"):
        op.drop_table(table)
    op.drop_index("idx_performance_plan_scope_status", table_name="performance_plans")
    op.drop_table("performance_plans")
