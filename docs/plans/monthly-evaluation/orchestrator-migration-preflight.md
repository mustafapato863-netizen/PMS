# Orchestrator migration preflight — 2026-10-08

Baseline commit: 2af9eb1e3991cb649ebcc695e3f2c42fbce4f40a. This evidence was independently obtained by Codex, not inferred from Grok's report.

- A dedicated disposable PostgreSQL 16.15 container, pms-evaluation-test-20261008, was created without a persistent volume. Loopback-only port 55432; synthetic empty database pms_evaluation_test. Existing local dataskyway database was not changed.
- Python pytest, SQLAlchemy, psycopg2 and Alembic imports passed. Runtime Python was 3.13; CI uses 3.11 (compatibility must be checked separately).
- `command.upgrade(Config('alembic.ini'), 'head')`, with DATABASE_URL explicitly pinned to the disposable loopback database in-process, failed on the first revision 975c072657f1.
- Failure: `psycopg2.errors.UndefinedTable: relation "employees" does not exist` from `ALTER TABLE employees ALTER COLUMN created_at DROP NOT NULL` at migration line 24. Despite its "Fresh schema" title, the root revision assumes pre-existing tables.

This is a pre-existing bootstrap gap, not an evaluation implementation regression. Empty-schema migration verification has NOT passed. Do not mark migration/Phase 1 acceptance green by stamping a database or creating all current ORM tables and pretending that tests the migration chain. Determine the actual supported bootstrap contract, then test that and legacy-shaped upgrade paths separately. Any migration/bootstrap repair requires a bounded reviewed task, backward compatibility and no existing-database mutation.

## Supported bootstrap discovered and verified

Subsequent source verification found `Backend/scripts/bootstrap_schema.py`, explicitly designed to create ORM metadata and stamp head for a truly empty database because the historical chain assumes a pre-existing schema. `compose.production.yml:60` invokes this script before `alembic upgrade head`. Thus the direct-upgrade failure above is not evidence that the documented production startup is broken.

Codex created a separate disposable empty database, pms_evaluation_bootstrap, and invoked the actual script followed by upgrade head. Result: **passed**, 38 ORM tables, stamped d9e4b7a2c106. This verifies supported bootstrap, not execution of the historical migration chain.

Post-bootstrap schema inspection found management_kpi_config, management_kpi_config_history and management_kpi_snapshots, but **no team_configuration_versions/coverage tables and no performance_records version column**. This confirms the source-audit ORM/migration drift on a fresh supported bootstrap; it does not prove the state of any existing deployment. Phase 1 must reconcile both legacy-migrated and fresh ORM-created schema paths before acceptance.

`Database/pms_scheme.sql` also exists as the historical pre-Alembic schema. It was applied successfully, only to a third disposable database pms_evaluation_legacy, in preparation for separately testing the historical upgrade path.

Historical SQL-schema upgrade failed at 975c072657f1 when changing performance_records.grade: PostgreSQL rejected ALTER TYPE because materialized view mv_team_monthly_summary depends on grade. This is another pre-existing legacy migration incompatibility. No test database was stamped to bypass this failure; no existing deployment was modified. A complete historical-chain roundtrip is not established.

Primary local API at 127.0.0.1:8000 was also unavailable (connection refused) during this task; earlier session service status is stale. No user services were started/stopped to conceal this missing runtime evidence.

No production schema was inspected and no existing database migrated. Local runtime schema/data audit is still a separate evidence requirement.

## Independently rerun existing baseline tests

With APP_ENV=test and DATABASE_URL explicitly pinned to the dedicated disposable loopback database, Codex ran `python -m pytest -q` equivalent for tests/test_function_access_scope.py, tests/test_dashboard_record_config_resolution.py and tests/test_config_loader_cache.py: **20 passed**, 7 existing Pydantic deprecation/config warnings, 4.98s. These use mocked/synthetic evidence and do not establish actual live database schema or new feature implementation.
