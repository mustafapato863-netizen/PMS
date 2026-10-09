# Monthly evaluation history integrity

Revision `f7c3a9e1d5b8` follows `e1b6c9d4a870`. It does not edit older migrations and does not add another approval table. No commit, deploy, or application database was used.

## Actor columns

JSON objects. `state` is `unknown` or `known`. Existing rows are backfilled to `{"state":"unknown"}` without reading `users`. A known object may later include `user_id`, `username`, `full_name`, and `role`; the database requires only `state`.

| Table | Column | Type | When it can change |
| --- | --- | --- | --- |
| `team_configuration_versions` | `actor_created_snapshot` | `jsonb` NOT NULL, default `{"state":"unknown"}` | Insert only |
| `team_configuration_versions` | `actor_published_snapshot` | `jsonb` NOT NULL, same default | While the row is still a draft, including the draft-to-approved update. Frozen once stored status is `approved` or `superseded` |
| `evaluation_revisions` | `actor_snapshot` | `jsonb` NOT NULL, same default | Insert only |

User foreign keys stay `ON DELETE SET NULL`. The trigger allows those ids to become NULL and refuses assigning a different user id. Team foreign keys and `evaluation_revisions.previous_revision_id` are `ON DELETE RESTRICT`.

## Monthly identity

A non-null `performance_level` is `Employee`, `Managerial`, or `Corporate`. `position_name` is NOT NULL; `''` means no position. Harmless NULL positions become `''` only after duplicate detection. Distinct positions stay distinct. Ambiguous approved or draft duplicates abort the migration and leave the predecessor schema in place.

Both `effective_until_month` and `effective_until_year` are required and equal the from month. `NULL = month` is unknown to SQL and is rejected by an explicit `IS NOT NULL`. Legacy rows with a NULL performance level keep open-ended periods, including NULL end fields.

Approved and superseded monthly rows cannot change snapshot, checksum, preview, weight, score, `is_active`, notes, `published_at`, actor publication, scope, period, or version number, and cannot be deleted. Allowed status changes are `draft -> approved` and `approved -> superseded`. `draft -> superseded` is rejected. Revision status may move `active -> rolled_back` or `active -> superseded`. A rolled-back revision is not reactivated.

## Fresh bootstrap

`scripts/bootstrap_schema.py` does not run root revision `975c072657f1`. On an empty database it runs ORM `create_all`, checks the history guard definitions, and stamps head. A database that already has tables and no `alembic_version` is refused. The success line says this is not a historical chain replay. The PostgreSQL verifier probes the root separately and records `HISTORICAL_REPLAY_ROOT_FAILURE`; that probe rolls back and leaves no tables.

## Later workflow locks

Set `actor_created_snapshot` on version insert and `actor_published_snapshot` before or during draft approval. Set `actor_snapshot` on revision insert. Do not delete approved or superseded versions, or any revision. Replace a draft in place or by delete; do not mark it superseded. `open_draft(..., copy_previous=True)` still assigns `draft -> superseded` when a draft for that month already exists, so that path needs a later adjustment before it can run against this schema. Do not reactivate a rolled-back revision. Do not change a monthly row's team, level, position, version number, or period, and do not clear either end field. Do not relabel a legacy row as monthly. Do not hard-delete a team that still has versions or revisions. User deletion clears the user ids; the actor JSON is the remaining attribution.

## Gates on 2026-10-09

Disposable databases `pms_eval_review_fix16` (port 55432) and `pms_eval_review_fix18` (port 55433) only. Runner environment was `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, empty `REDIS_URL`, and `CI` unset. Owned PostgreSQL URLs were applied inside the explicit file and restored.

- `python -X utf8 -m pytest tests/test_evaluation_history_integrity.py`: 2 passed. Default collection of `tests` lists those two tests and does not list `evaluation_history_pg_checks.py`.
- `python -X utf8 -m pytest tests/evaluation_history_pg_checks.py`: 22 passed on PostgreSQL 16 and 18. That includes predecessor upgrade, duplicate refusal, empty downgrade and re-upgrade, populated downgrade refusal, legacy retention, concurrent approvals, NULL end-field insert and update, bootstrap versus migrated guard definitions, and the separate root-replay failure.
- Team delete is SQLSTATE `23503` on this PostgreSQL 16 and `23001` (`restrict_violation`) on this PostgreSQL 18. Both name a RESTRICT foreign key, `team_configuration_versions_team_id_fkey` or `evaluation_revisions_team_id_fkey`.
- NULL monthly end fields raise SQLSTATE `23514` on `ck_team_config_monthly_exact_period`.
- `git diff --check` reported no whitespace errors.

## Limitations

This is not a replay of the historical migration chain and not a release-ready claim. Guard comparison covers the two history tables' check text, index definitions, trigger definitions, and guard function bodies. Downgrade refuses while approved or superseded monthly versions or any evaluation revision exist, and it does not turn `''` positions back into NULL. No scoring or workflow code was changed.
