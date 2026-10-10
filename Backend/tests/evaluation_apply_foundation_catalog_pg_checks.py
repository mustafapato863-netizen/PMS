"""Opt-in actual catalog drift regressions on the owned PostgreSQL pair only.

Not collected by normal pytest. Run serially by this exact path, with the
same isolated environment and allowlist as evaluation_apply_foundation_pg_checks.
Each schema mutation is rolled back. No non-allowlisted database is opened.
"""
import importlib.util
import os
from pathlib import Path

if os.environ.get("APP_ENV") != "test" or os.environ.get("DATABASE_URL") != "sqlite:///:memory:":
    raise RuntimeError("Catalog checks require APP_ENV=test and DATABASE_URL=sqlite:///:memory:")
if os.environ.get("REDIS_URL", ""):
    raise RuntimeError("Catalog checks refuse a non-empty REDIS_URL")

import pytest
from sqlalchemy import text

spec = importlib.util.spec_from_file_location(
    "catalog_candidate_apply_checks", Path(__file__).with_name("evaluation_apply_foundation_pg_checks.py")
)
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
pg = candidate.pg

VARIANTS = {
    "disabled_trigger": ["ALTER TABLE evaluation_apply_stage_rows DISABLE TRIGGER trg_evaluation_apply_stage_guard"],
    "replica_only_trigger": ["ALTER TABLE evaluation_apply_stage_rows ENABLE REPLICA TRIGGER trg_evaluation_apply_stage_guard"],
    "detached_trigger": ["DROP TRIGGER trg_evaluation_apply_stage_guard ON evaluation_apply_stage_rows"],
    "wrong_trigger_function": [
        "DROP TRIGGER trg_evaluation_apply_stage_guard ON evaluation_apply_stage_rows",
        "CREATE FUNCTION reviewer_noop_stage() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$",
        "CREATE TRIGGER trg_evaluation_apply_stage_guard BEFORE INSERT OR UPDATE OR DELETE ON evaluation_apply_stage_rows FOR EACH ROW EXECUTE FUNCTION reviewer_noop_stage()",
    ],
    "wrong_trigger_timing": [
        "DROP TRIGGER trg_evaluation_apply_stage_guard ON evaluation_apply_stage_rows",
        "CREATE TRIGGER trg_evaluation_apply_stage_guard AFTER INSERT OR UPDATE OR DELETE ON evaluation_apply_stage_rows FOR EACH ROW EXECUTE FUNCTION guard_evaluation_apply_stage_row()",
    ],
    "missing_trigger_events": [
        "DROP TRIGGER trg_evaluation_apply_stage_guard ON evaluation_apply_stage_rows",
        "CREATE TRIGGER trg_evaluation_apply_stage_guard BEFORE INSERT ON evaluation_apply_stage_rows FOR EACH ROW EXECUTE FUNCTION guard_evaluation_apply_stage_row()",
    ],
    "conditional_trigger": [
        "DROP TRIGGER trg_evaluation_apply_stage_guard ON evaluation_apply_stage_rows",
        "CREATE TRIGGER trg_evaluation_apply_stage_guard BEFORE INSERT OR UPDATE OR DELETE ON evaluation_apply_stage_rows FOR EACH ROW WHEN (false) EXECUTE FUNCTION guard_evaluation_apply_stage_row()",
    ],
    "weaker_month_check": [
        "ALTER TABLE evaluation_apply_controls DROP CONSTRAINT ck_evaluation_apply_month",
        "ALTER TABLE evaluation_apply_controls ADD CONSTRAINT ck_evaluation_apply_month CHECK(month BETWEEN 1 AND 13)",
    ],
    "negative_epoch_allowed": [
        "ALTER TABLE processing_jobs DROP CONSTRAINT ck_processing_job_claim_epoch",
        "ALTER TABLE processing_jobs ADD CONSTRAINT ck_processing_job_claim_epoch CHECK(claim_epoch IS NULL OR claim_epoch >= -1)",
    ],
    "extra_job_kind": [
        "ALTER TABLE processing_jobs DROP CONSTRAINT ck_processing_job_kind",
        "ALTER TABLE processing_jobs ADD CONSTRAINT ck_processing_job_kind CHECK(kind IN ('pms_upload','report_generation','story_report_generation','evaluation_apply','reviewer_unapproved_kind'))",
    ],
    "wrong_open_index_keys": [
        "DROP INDEX uq_evaluation_apply_one_open_scope_month",
        "CREATE UNIQUE INDEX uq_evaluation_apply_one_open_scope_month ON evaluation_apply_controls(job_id,scope_id,year,month) WHERE state IN ('pending','staging','promoting')",
    ],
    "wrong_open_index_predicate": [
        "DROP INDEX uq_evaluation_apply_one_open_scope_month",
        "CREATE UNIQUE INDEX uq_evaluation_apply_one_open_scope_month ON evaluation_apply_controls(scope_id,year,month) WHERE state IN ('pending','staging','promoting','failed')",
    ],
    "wrong_outbox_index_keys": [
        "DROP INDEX idx_cache_invalidation_outbox_unpublished",
        "CREATE INDEX idx_cache_invalidation_outbox_unpublished ON cache_invalidation_outbox(id) WHERE published_at IS NULL",
    ],
}


@pytest.mark.parametrize("variant", list(VARIANTS))
def test_verifier_rejects_semantically_drifted_schema(pg, variant):
    engine, target = pg
    with engine.connect() as connection:
        candidate.assert_public_search_path(connection, target)
        assert candidate.missing_apply_foundation_objects(connection) == []
        try:
            for statement in VARIANTS[variant]:
                connection.execute(text(statement))
            assert candidate.missing_apply_foundation_objects(connection), f"Verifier accepted {variant}"
        finally:
            connection.rollback()


@pytest.mark.parametrize("variant", ["wrong_referenced_column", "wrong_referenced_schema", "not_valid"])
def test_verifier_checks_actual_foreign_key_target_and_validation(pg, variant):
    engine, target = pg
    with engine.connect() as connection:
        candidate.assert_public_search_path(connection, target)
        assert candidate.missing_apply_foundation_objects(connection) == []
        fk_name = connection.execute(text("""
            SELECT c.conname FROM pg_constraint c
            JOIN pg_class r ON r.oid=c.conrelid
            JOIN pg_namespace n ON n.oid=r.relnamespace
            WHERE n.nspname='public' AND r.relname='evaluation_apply_controls'
              AND c.contype='f' AND c.conkey=ARRAY[(
                SELECT attnum FROM pg_attribute WHERE attrelid=r.oid AND attname='requested_by_user_id'
              )]::smallint[]
        """)).scalar_one()
        assert fk_name.replace("_", "").isalnum()
        try:
            connection.execute(text(f'ALTER TABLE evaluation_apply_controls DROP CONSTRAINT "{fk_name}"'))
            if variant == "wrong_referenced_column":
                connection.execute(text("ALTER TABLE users ADD COLUMN reviewer_other_id uuid UNIQUE"))
                reference = "public.users(reviewer_other_id)"
            elif variant == "wrong_referenced_schema":
                connection.execute(text("CREATE SCHEMA reviewer_foundation_shadow"))
                connection.execute(text("CREATE TABLE reviewer_foundation_shadow.users(id uuid PRIMARY KEY)"))
                reference = "reviewer_foundation_shadow.users(id)"
            else:
                reference = "public.users(id)"
            suffix = " NOT VALID" if variant == "not_valid" else ""
            connection.execute(text(f'ALTER TABLE evaluation_apply_controls ADD CONSTRAINT "{fk_name}" FOREIGN KEY(requested_by_user_id) REFERENCES {reference} ON DELETE SET NULL{suffix}'))
            assert candidate.missing_apply_foundation_objects(connection), f"Verifier accepted {variant}"
        finally:
            connection.rollback()
