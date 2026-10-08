"""Allow independent Sales, CSR and Pharmacy function grants.

Revision ID: d9e4b7a2c106
Revises: c8d3f6a1b205
"""
from alembic import op
import sqlalchemy as sa

revision = "d9e4b7a2c106"
down_revision = "c8d3f6a1b205"
branch_labels = None
depends_on = None

OLD_NAMES = ("Call Center", "RCM", "Pre-Approvals", "Marketing")
NEW_NAMES = (*OLD_NAMES, "Sales", "CSR", "Pharmacy")
CONSTRAINT = "ck_user_function_assignment_name"


def _constraint(names):
    values = ", ".join(f"'{name}'" for name in names)
    return f"function_name IN ({values})"


def upgrade():
    with op.batch_alter_table("user_function_assignments") as batch:
        batch.drop_constraint(CONSTRAINT, type_="check")
        batch.create_check_constraint(CONSTRAINT, _constraint(NEW_NAMES))


def downgrade():
    # Never silently delete or broaden grants to make a rollback possible.
    # Admin must explicitly reassign new grants before reverting this schema.
    if op.get_context().as_sql:
        op.execute("""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM user_function_assignments
                       WHERE function_name IN ('Sales', 'CSR', 'Pharmacy')) THEN
                RAISE EXCEPTION 'Reassign Sales/CSR/Pharmacy grants before downgrading';
            END IF;
        END $$;""")
    else:
        grants = sa.table("user_function_assignments", sa.column("function_name", sa.String()))
        count = op.get_bind().execute(sa.select(sa.func.count()).select_from(grants).where(
            grants.c.function_name.in_(("Sales", "CSR", "Pharmacy")),
        )).scalar_one()
        if count:
            raise RuntimeError("Reassign Sales/CSR/Pharmacy grants before downgrading; no grants were changed")
    with op.batch_alter_table("user_function_assignments") as batch:
        batch.drop_constraint(CONSTRAINT, type_="check")
        batch.create_check_constraint(CONSTRAINT, _constraint(OLD_NAMES))
