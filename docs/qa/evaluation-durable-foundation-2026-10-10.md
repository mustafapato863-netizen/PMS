# Evaluation durable apply foundation — 2026-10-10

Slice: Phase 7A schema foundation only. Branch `codex/evaluation-durable-apply-foundation` at base `625abf431ae10659edb93ddb3e879de4ac47c6d8`. Nothing was staged, committed, pushed, or applied to an existing database.

This is not a Phase 7 exit, not EVAL-19, and not a performance budget. The contract is `docs/plans/monthly-evaluation/phase7-durable-apply-contract.md`.

## What landed

- `Backend/services/evaluation/apply_job_schema.py` — expand-only helper, guards, and verifier.
- `Backend/migrations/versions/b4e7c2a9d815_add_evaluation_apply_foundation.py` — revises `f7c3a9e1d5b8`. Old migration files were not rewritten.
- `Backend/models/models.py` — `processing_jobs.claim_epoch`, kind check widened with `evaluation_apply`, and the three foundation models.
- `Backend/tests/test_evaluation_apply_foundation.py` — in-memory SQLite proof, including direct SQL.
- `Backend/tests/evaluation_apply_foundation_pg_checks.py` — opt-in PostgreSQL 16/18 module. Not named `test_*.py`. Not executed in this session.
- No scoring, auth, worker, API, frontend, Insights, or `EvaluationWorkflow.apply` / rollback edits. `JOB_KINDS` is still the original three kinds.

## SQLite results

Environment: `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, `REDIS_URL` empty, `CI` unset. Engines in the new test also open `sqlite:///:memory:` directly. No PostgreSQL connection was opened.

`tests/test_evaluation_apply_foundation.py`: 14 passed in 2.48s (re-run after the final opt-in module edit).

The same foundation file plus the existing regressions below passed together before that module-only edit: 40 passed in 7.93s.

- `tests/test_evaluation_apply_foundation.py`
- `tests/test_processing_jobs.py`
- `tests/test_evaluation_history_integrity.py`
- `tests/test_evaluation_month_revision.py`
- `tests/test_evaluation_revision_actor_guard.py`
- `tests/test_migration_graph.py`

The module-only edit does not change those five existing files. They were not re-run after it.

The full suite was not run. The known Marketing 131 vs 68 failure was not re-observed because `tests/test_marketing_import.py` was not run.

Direct SQL, not only the ORM, rejected: a year outside 2000..2100, a month outside 1..12, a non-hex fingerprint, a second open job for the same scope/month, a missing requester on an open or retried job, a stale claim epoch, a changed stage payload, a missing `(record id, year)`, a stage row outside the captured month, job-header delete and kind change, an oversized `evaluation_apply` status payload, scope identity change, revision delete, outbox insert before promotion, outbox dedup, an error longer than 240 characters, publish with zero attempts, unpublish, and deletes of stage, outbox, and captured controls. An empty downgrade restored the three-kind check and removed `claim_epoch` while keeping the old upload payload. A populated downgrade raised `before any schema change` and left the control row in place. `ProcessingJobService.create` still rejects `evaluation_apply` before insert. History guards remained installed.

## Not certified here

- PostgreSQL 16/18. The reviewer module targets only `127.0.0.1:55432/pms_eval_review_fix16` and `127.0.0.1:55433/pms_eval_review_fix18` as user `pms_eval_test`, and it refuses any other host, database, or search path. Run it sequentially by path. This session did not start containers or call that module.
- SQLite does not enforce foreign keys unless `PRAGMA foreign_keys=ON`. The new test turns that on. SQLite also does not enforce `VARCHAR` length, so length is a CHECK.
- SQLite reports a partial unique failure as `UNIQUE constraint failed` and does not include `uq_evaluation_apply_one_open_scope_month` in the error text. The test reads that index from `sqlite_master` and asserts the UNIQUE failure separately.
- SQLite runs `BEFORE` triggers in reverse creation order. The helper creates them reversed so runtime order follows the PostgreSQL guard functions. That parity was not executed on PostgreSQL.
- Canonical hash equality is Python-only. SQL rejects a non-object and a bad hash charset. It does not recompute the hash.
- The database does not prove Admin role, version approval, checksum equality with the version row, or Coding/Submission/Outbound admission. Those remain enqueue and promotion checks.
- Performance-record score and payload stay mutable after stage capture. Identity columns do not.
- `create_all` places `claim_epoch` after `max_attempts`. The migration appends it. The SQLite rebuild accepts only the historical column order or the already-widened epoch-last order.
- `Database/pms_scheme.sql` partitioning is not what this Alembic chain upgrades. The stage foreign key uses the composite `(id, year)` identity.
- No query, memory, or latency budget was measured. Tables alone do not bound `EvaluationWorkflow.apply`.

## Reviewer PostgreSQL gate

This section records the reviewer's run. It does not replace the SQLite results above, and it is not a PostgreSQL pass.

The reviewer replaced the empty bootstrap with representative parent tables, ran the existing `f5c2d7e8a901` processing-job migration under Alembic operations, stamped `f7c3a9e1d5b8`, and then upgraded `b4e7c2a9d815`. The earlier empty bootstrap reported eight setup errors because `employees` was missing. An intermediate fixture also imported `PRIOR_KIND_CHECK_SQL` after that name was missing, and ORM-created job defaults caused four unrelated failures until the prior migration's defaults were used.

With that predecessor, the reviewer reported 4 passed and 4 failed on PostgreSQL 16 and 18. Empty downgrade and direct SQL passed. The four failures were verifier errors: about 20 false drift reports because PostgreSQL deparses checks with casts, `ANY`, and parentheses. Populated downgrade did refuse before the schema change, and the verifier then wrongly flagged the still-present foundation. The opt-in overlap test `test_validated_stage_write_serializes_with_epoch_and_record_changes` was red: a `claim_epoch` update and a performance-record month update both committed while a validated stage insert was paused. The stage guard selected the job, control, and record without row locks.

The rework after that report canonicalizes check predicates, requires validated checks, requires each guard trigger to be attached and enabled, and compares foreign-key targets and index keys rather than names alone. Stage validation and reclaim now use one lock order: `processing_jobs`, `evaluation_scopes`, `evaluation_apply_controls`, `performance_records`. `models.py` aliases SQLAlchemy `Uuid` as `UUID` so new metadata is CHAR(32) on SQLite and native UUID on PostgreSQL. That import does not rewrite existing SQLite id values. No PostgreSQL connection was opened for this rework. The reviewer still has to rerun the allowlisted 16/18 pair. Until that rerun, PostgreSQL certification remains pending.

The actor snapshot remains attribution (`known` plus the user id). It is not a role grant. Active Admin authorization remains later work. No worker, route, or consumer was added.

## Reviewer catalog rerun

The reviewer reran the six normal SQLite modules: 46 passed in 6.29s. The owned allowlisted PostgreSQL 16/18 suite then passed 12 tests in 21.44s, including the four overlap cases that had been red. That rerun is the reviewer's result. It is not a claim that every later catalog mutation was accepted.

An external adversarial harness, not run in this session, then reported 22 passed and 10 failed in 51.48s. Five variants failed on both targets: a guard trigger that was `AFTER`, `INSERT`-only, or `WHEN (false)` was accepted, and a public foreign key to `reviewer_foundation_shadow.users(id)` or a `NOT VALID` foreign key was accepted. The wrong referenced column stayed rejected. The follow-up reads `tgtype`, `tgqual`, and the function schema for triggers, and the referenced namespace plus `convalidated` for foreign keys. SQLite characterization covers those catalog shapes in memory. This session opened no PostgreSQL connection. The reviewer still has to rerun the adversarial catalog cases. Until that rerun, those five variants remain pending rather than passed.

## Independent final foundation review

The later reviewer rerun supersedes the pending catalog verdict above: **44 passed in 68.03s** on the allowlisted PostgreSQL 16/18 pair (12 migration/direct-SQL/concurrency cases plus 32 actual catalog mutation cases). All five previously accepted bad catalog shapes now fail verification. The six normal SQLite modules independently passed again: **46 passed, 8 warnings in 8.35s**. The actual catalog regressions are retained in opt-in `Backend/tests/evaluation_apply_foundation_catalog_pg_checks.py`; their committed-path repeat alongside the original module independently passed **44 tests in 83.24s**. Run them serially, never against ordinary databases. These results certify this inactive foundation only, not a background worker, atomic scoring promotion, load budget, all-team calculations, or production RLS. The full candidate backend suite is in progress; no full-suite pass is claimed.

## Next slice (unchanged)

### Whole candidate backend suite

Independent unexcluded run in the isolated environment: **1187 passed, 1 failed, 1 existing skipped, 63 warnings in 196.20s**. The only failure is the previously reproduced baseline `tests/test_marketing_import.py::test_real_marketing_workbook_imports_with_incomplete_rows_excluded` (131 source rows versus 68 expected). No assertion, expected workbook count, skip, or CI environment was altered to hide it. This is a scoped foundation acceptance, **not a green release verdict**. The accepted closure branch has newer independent non-foundation tests; combined-tree gates must be repeated after local integration.

Phase 7B, as written in the contract: a keyset stager and one promotion transaction. Do not call `EvaluationWorkflow.apply`. Do not add a worker, route, or UI in that slice. Keep legacy full-snapshot rollback. Add crash-point coverage on the disposable PostgreSQL pair only after the promotion transaction exists.
