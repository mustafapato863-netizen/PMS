"""add_performance_and_audit_indexes

Revision ID: b31d52f82865
Revises: 20dbf9a1ddeb
Create Date: 2026-06-20 20:50:29.667193

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b31d52f82865'
down_revision: Union[str, Sequence[str], None] = '20dbf9a1ddeb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Composite index on performance_records (employee_id, month, year)
    op.create_index(
        'idx_performance_employee_month_year',
        'performance_records',
        ['employee_id', 'month', 'year']
    )

    # 2. Composite index on performance_records (team_id, month, year)
    op.create_index(
        'idx_performance_team_month_year',
        'performance_records',
        ['team_id', 'month', 'year']
    )

    # 3. Index on performance_records (year)
    op.create_index(
        'idx_performance_year',
        'performance_records',
        ['year']
    )

    # 4. Index on kpi_values (record_id, record_year)
    op.create_index(
        'idx_kpi_values_record',
        'kpi_values',
        ['record_id', 'record_year']
    )

    # 5. Index on users (username)
    op.create_index(
        'idx_users_username',
        'users',
        ['username']
    )

    # 6. Index on user_team_assignments (user_id, team_id)
    op.create_index(
        'idx_user_team_assignments_user',
        'user_team_assignments',
        ['user_id', 'team_id']
    )

    # 7. Index on audit_log (table_name, record_id, performed_at DESC)
    op.create_index(
        'idx_audit_log_table_record',
        'audit_log',
        ['table_name', 'record_id', sa.text('performed_at DESC')]
    )

    # 8. Partial index on employees (team_id) WHERE is_active = true
    op.create_index(
        'idx_employees_active',
        'employees',
        ['team_id'],
        postgresql_where='is_active = true'
    )

    # 9. Partial index on teams (id) WHERE is_active = true
    op.create_index(
        'idx_teams_active',
        'teams',
        ['id'],
        postgresql_where='is_active = true'
    )

    # 10. GIN indexes on audit_log (new_values, old_values)
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.create_index(
            'idx_audit_log_new_values',
            'audit_log',
            ['new_values'],
            postgresql_using='gin'
        )
        op.create_index(
            'idx_audit_log_old_values',
            'audit_log',
            ['old_values'],
            postgresql_using='gin'
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.drop_index('idx_audit_log_old_values', table_name='audit_log')
        op.drop_index('idx_audit_log_new_values', table_name='audit_log')

    op.drop_index('idx_teams_active', table_name='teams')
    op.drop_index('idx_employees_active', table_name='employees')
    op.drop_index('idx_audit_log_table_record', table_name='audit_log')
    op.drop_index('idx_user_team_assignments_user', table_name='user_team_assignments')
    op.drop_index('idx_users_username', table_name='users')
    op.drop_index('idx_kpi_values_record', table_name='kpi_values')
    op.drop_index('idx_performance_year', table_name='performance_records')
    op.drop_index('idx_performance_team_month_year', table_name='performance_records')
    op.drop_index('idx_performance_employee_month_year', table_name='performance_records')
