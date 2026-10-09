"""Guard monthly evaluation approval history.

Revision ID: f7c3a9e1d5b8
Revises: e1b6c9d4a870
Create Date: 2026-10-09 12:00:00.000000

Forward-only correction after the monthly evaluation tables exist.
Legacy NULL-level rows and their published snapshots stay in place.
Ambiguous monthly duplicates or invalid monthly periods abort the migration.
Downgrade refuses while approved monthly history or any evaluation revision exists.
"""

from typing import Sequence, Union

from alembic import op

from models.evaluation_history_schema import (
    add_actor_columns,
    collect_preflight_problems,
    drop_guard_objects_for_downgrade,
    evidence_blocks_downgrade,
    format_preflight_failure,
    install_history_guards,
    install_new_checks_and_index,
    normalize_harmless_null_positions,
    restrict_history_foreign_keys,
)


revision: str = "f7c3a9e1d5b8"
down_revision: Union[str, Sequence[str], None] = "e1b6c9d4a870"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError(
            "Monthly evaluation history guards migrate on PostgreSQL. "
            "SQLite tests install the ORM equivalents when the tables are created."
        )
    add_actor_columns(bind)
    problems = collect_preflight_problems(bind)
    if problems:
        raise RuntimeError(format_preflight_failure(problems))
    normalize_harmless_null_positions(bind)
    install_new_checks_and_index(bind)
    restrict_history_foreign_keys(bind)
    install_history_guards(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("Monthly evaluation history downgrade runs on PostgreSQL.")
    evidence = evidence_blocks_downgrade(bind)
    if evidence["approved_or_superseded_versions"] or evidence["evaluation_revisions"]:
        raise RuntimeError(
            "Refusing to drop monthly evaluation history guards while approved or "
            "superseded monthly versions or evaluation revisions exist. Operational "
            f"rollback must not drop this history: {evidence}"
        )
    drop_guard_objects_for_downgrade(bind)
