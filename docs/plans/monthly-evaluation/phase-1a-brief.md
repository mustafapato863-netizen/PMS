<task>
Implement Phase 1A ONLY: reconcile and map the already-existing team configuration version groundwork so fresh supported ORM bootstrap and existing migrated PostgreSQL schemas have the same usable baseline. This is the first bounded slice of Phase 1, not the full monthly settings feature. Leave application scoring, upload, dashboard behavior, endpoints, permissions and frontend unchanged. Do not execute Phase 1B or later tasks.
</task>

<accepted_predecessor>
Base commit e6947b4a3b6e7dc67ab4cbe3215d3b938ee161f3, branch codex/evaluation-phase-1-foundation. Phase 0 source/test PR #24 is draft, reviewed off-main. Its source/test commit a68898f passed CI 37831220705 (backend/frontend/containers); independent targeted baseline 64 passed/1 existing skip. Full local suite 1064 passed/1 pre-existing external Marketing workbook acceptance failure/1 skip; identical failure exists on untouched main. Do not weaken/skip that test.
Read dispatch-contract.md, approved-decisions.md, phase-0-review.md, phase-0-audit.md, orchestrator-local-schema-inventory.md and orchestrator-migration-preflight.md under docs/plans/monthly-evaluation/. Read canonical PMS-EVAL-001 for integration context, but this bounded brief defines implementation scope.
D-001: every evaluation settings lifecycle stage is Admin-only. D-002: unsupported target/direction changes remain blocked; weight-only changes may use validated achievement without inventing missing inputs. Real-workbook goldens remain activation gates, not a reason to guess formulas. No production activation.
</accepted_predecessor>

<verified_schema>
LOCAL is PostgreSQL 18.4, current Alembic head d9e4b7a2c106. Existing table team_configuration_versions was added in 8716484ca95c; coverage columns are on that table from b8f2d4a9c731; snapshot fields from c4a7b7d8f2ac. Existing version rows and management histories must be preserved exactly. PerformanceRecord has composite primary identity (id, year), with yearly PostgreSQL partitions and existing configuration_version_id UUID / FK SET NULL in the migrated schema, currently unmapped in ORM. Existing version table has team/version uniqueness, team FK CASCADE and actor FKs SET NULL. Do not silently claim these deletion semantics satisfy immutable-history requirements; that is a Phase 1B retention gate.
Supported fresh startup runs scripts/bootstrap_schema.py (empty-only ORM create_all then stamp head) before alembic upgrade. Current ORM omits version groundwork, so an old-head ORM-created schema lacks version table and record version column. Direct empty historical Alembic chain and historical Database/pms_scheme.sql chain have separate pre-existing failures; do not edit old migrations or misrepresent bootstrap stamping as chain execution.
</verified_schema>

<deliverables>
1. Map TeamConfigurationVersion and nullable PerformanceRecord.configuration_version_id to the audited existing contract, including coverage, management publish snapshot fields, types, relationships/constraints/indexes needed for metadata bootstrap. Preserve backwards compatible nullable legacy records; no assumed historical version assignment. Avoid duplicate competing version tables, circular imports or unrelated ORM changes.
2. Add ONE expand-only forward Alembic reconciliation revision after d9e4b7a2c106. Inspect actual table/column/index/FK shape before creating missing groundwork. It must repair old-head ORM bootstrap shape, preserve existing migrated shape/data and succeed on repeat reconciliation. Fail visibly on incompatible shape rather than destructive rebuild, data coercion or silent catch/default. Preserve partition-correct references and existing raw/KPI/management rows. Do not alter the original migration chain or stamp existing databases in runtime code.
3. A non-destructive downgrade/rollback contract must retain any reused or referenced version evidence. Do not drop previously existing columns/tables just because this forward revision knows their names. Choose and document an explicit retention-first downgrade; verify re-upgrade. Normal production rollback is application rollback with expanded schema retained, not history deletion.
4. Add synthetic tests for actual ORM roundtrip of version rows and legacy nullable record links; migration tests for old-head bootstrap shape versus representative migrated/partitioned shape, version rows/payloads/management sentinels unchanged, no duplicate FKs/indexes, and downgrade/re-upgrade. SQLite-only is insufficient for PostgreSQL acceptance. Do not assert architecture absence.
5. Write phase-1a-evidence.md with exact scope, schema changes, actual tests/results, bootstrap-vs-chain distinction, downgrade behavior, limitations and concrete Phase 1B prerequisites (monthly scope bindings/concurrency, immutable retention/audit and applied evidence/revision foundation). Mark Phase 1 still partial.
</deliverables>

<safe_test_environment>
Orchestrator created two DEDICATED DISPOSABLE databases containing no user data:
PostgreSQL 18 container pms-evaluation-pg18-20261008: postgresql://pms_eval_test:pms-local-disposable-test@127.0.0.1:55433/pms_eval_foundation18
PostgreSQL 16 container pms-evaluation-test-20261008: postgresql://pms_eval_test:pms-local-disposable-test@127.0.0.1:55432/pms_eval_foundation16
These credentials are synthetic test-only. You may write/reset ONLY these exact test databases, after checking parsed loopback host, exact port/name and APP_ENV=test. Never use an implicit default URL. Do not access/reset other databases or containers, real local/production schema, or existing services. Test scripts must require explicit opt-in test URL and reject any non-allowlisted target; do not put destructive migration fixtures on an environment-derived user database. Orchestrator owns containers. If sandbox blocks access, report that accurately; do not escalate access or fabricate results. Ordinary unit tests pin DATABASE_URL=sqlite:///:memory: and APP_ENV=test before importing models/config.
</safe_test_environment>

<verification_loop>
Prefix terminal commands with rtk. Inspect tests/bootstrap/real ORM conventions, then run targeted new tests and the Phase 0 baseline tests with isolated env. Run actual PG18 migration/bootstrap/downgrade/re-upgrade cases and PG16 compatibility cases on above disposable targets. Record executed commands/results, not inferred passes. Do not edit CI/workflows or existing tests to suppress failure. Run full backend pytest when safe; report known local workbook exclusion/input limitation separately. No frontend checks required for unchanged frontend. Refresh graph after source changes if installed; report availability separately.
</verification_loop>

<action_safety>
Work only in this supplied worktree and bounded Phase 1A files. Read no .env/credentials, external memory or unrelated repositories. No production, history backfill, recalculation, new formulas, monthly lifecycle/API activation or permission changes. No git add/commit/push/merge/reset/clean/checkout or PR creation; Codex owns publication after independent review. Use apply_patch for edits. Maintain concise progress and finish rather than spending turns on repeated broad exploration. Stop on a scope-changing premise and report it.
</action_safety>

<structured_output_contract>
Leave changes uncommitted. Final report: (1) complete/partial/blocked for Phase 1A, not overall feature, (2) files changed and rationale, (3) exact test commands/counts and real PG roundtrip outcomes, (4) decisions/limitations and what Phase 1B must do. No claims of live production or full Phase 1 acceptance.
</structured_output_contract>
