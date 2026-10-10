# Phase 7A durable apply contract

Status: schema and guard foundation only. This document is the contract for later slices. It does not mark Phase 7 or EVAL-19 complete. Creating these tables does not bound apply memory, query count, or latency.

The synchronous `EvaluationWorkflow.apply` path is unchanged. Nothing in this slice creates a processing job, claims a lease, scores a row, writes a revision, publishes a cache notification, or exposes a route.

## Decisions this schema must not undo

- D001: a persisted active Admin is required at every later management stage. The database stores the requester and an actor snapshot. It does not trust that snapshot as a role grant.
- D002: later enqueue admits only a proven Coding, Submission, or Outbound Employee period. Every other family stays blocked. This slice does not promote a family.
- D003: a new upload with a fixed-target mismatch stays blocked. Apply of an already stored conflict keeps today's `check_conflicts=False` behavior. This slice does not flip that check.
- D004: July and August Outbound keep their distinct 4-KPI and 5-KPI source templates. Formulas, caps, grades, and precision stay as they are.
- D005: a same-month correction is immutable history. Approve does not rescore. Apply is explicit. Rollback is latest-only and guarded. An old approval is never reactivated.

Do not invent lost history, renormalize weights, rewrite human plans, actions, report bytes, or source payloads.

## Objects

Migration `b4e7c2a9d815` revises `f7c3a9e1d5b8`. The helper is `Backend/services/evaluation/apply_job_schema.py`. Models are `EvaluationApplyControl`, `EvaluationApplyStageRow`, and `CacheInvalidationOutbox`.

`processing_jobs.claim_epoch` is nullable, default 0. The kind check additionally allows `evaluation_apply`. Public `JOB_KINDS` stays `pms_upload`, `report_generation`, and `story_report_generation`. No route or worker dispatches the new kind. Upload and report behavior is unchanged.

### `evaluation_apply_controls`

Primary key `job_id`, foreign key to `processing_jobs.id` `ON DELETE RESTRICT`.

Captured identity: `scope_id`, `version_id`, `team_id`, `performance_level`, `position_name` (empty string means no position), `year`, `month`, `engine_version`, `rules_checksum`, `proof_source_fingerprint`, `lineage_fingerprint`, `requested_by_user_id`, `actor_snapshot`.

Progress: `state`, `claim_epoch`, `stage_cursor`, `staged_count`, `promoted_count`, `promoted_revision_id`.

There is no population, employee list, or before/after snapshot column on this row.

Checks: state is one of `pending`, `staging`, `promoting`, `promoted`, `failed`, `cancelled`; month is 1..12; year is 2000..2100; level is Employee, Managerial, or Corporate; counts are non-negative; fingerprints are 64 characters; an open state requires a requester; a promoted row has a revision; any other state has no revision and a zero promoted count; a pending row has a zero staged count and a null cursor.

Partial unique index `uq_evaluation_apply_one_open_scope_month` on `(scope_id, year, month)` where state is `pending`, `staging`, or `promoting`.

Foreign keys prove the job, scope, version, team, user, and revision rows exist. User deletion is `ON DELETE SET NULL`. Every other foundation foreign key is `RESTRICT`. A foreign key is not proof that the scope, version, month, approved rules, and source payload describe the same work.

### `evaluation_apply_stage_rows`

Primary key `(job_id, claim_epoch, record_id, record_year)`.

`record_id, record_year` references `performance_records(id, year)` `ON DELETE RESTRICT`. `job_id` references the control `ON DELETE RESTRICT`.

Each row stores one canonical before object, one canonical after object, both hashes, the rules checksum, and `captured_at`. The keyset index is `(job_id, claim_epoch, record_year, record_id)`.

A write is accepted only while the control state is `staging` and the control epoch and the processing-job epoch both equal the row epoch. A repeat write of the same evidence is a no-op. Any other update is rejected. Older epochs stay stored until a separately approved cleanup. Delete is rejected.

The performance-record score and payload stay mutable so a later promotion can write the applied score. Team, month, level, position, id, and year are frozen once a stage row exists. Deleting that historical row is rejected.

A missing `(id, year)` fails the composite foreign key. A present row whose team, level, position, year, or month name disagrees with the control fails with `evaluation apply stage record is outside the captured scope month`.

### `cache_invalidation_outbox`

One bounded row per notification. Columns: `id`, `job_id`, `revision_id`, `namespace`, `dedup_key`, `created_at`, `delivery_attempts`, `next_retry_at`, `published_at`, `last_error`. Namespace is `data`. There is no payload column and no employee field.

Unique `(namespace, dedup_key)`. The helper key is `evaluation_apply:{job_id}:{revision_id}:data`.

Insert is accepted only when the control is `promoted` and `revision_id` equals `promoted_revision_id`, with `published_at` null, `delivery_attempts` 0, and `last_error` null. Attempts may rise while unpublished. `published_at` may be set once, and only when attempts are at least 1. After publish the row is frozen, including `published_at`. Delete is rejected.

At-least-once Redis `INCR` of `pms:version:data` is acceptable later. The row stays unpublished until `published_at` is set, so a crash cannot record a delivery that did not happen. There is no in-progress state that looks done. The publisher and any canonical database cache identity are later work. Insights does not read the current data version; this outbox does not by itself fix that reader.

## State machine

Insert must be `pending`, counts 0, cursor null, revision null, requester present, and `claim_epoch` equal to `processing_jobs.claim_epoch`. The actor snapshot state must be `known`, and its user id must match the requester when the requester is present.

Allowed moves:

- `pending` to `staging`, `failed`, or `cancelled`
- `staging` to `staging` (cursor and non-decreasing staged count), `promoting`, `failed`, or `cancelled`
- `promoting` to `promoting`, `promoted`, or `failed`
- `promoted` stays `promoted`
- `failed` or `cancelled` to the same state, or back to `pending` only as a retry

A retry sets `claim_epoch` to the old epoch plus one, clears counts, cursor, and revision, and requires the processing job epoch to already equal the new value. The requester must still be present. Epoch does not change on any other update. A missing requester cannot be put back.

`promoting` cannot already point at a revision. `promoted` requires a revision and is otherwise immutable. Captured scope, version, team, level, position, year, month, engine, fingerprints, actor snapshot, and `created_at` do not change after insert.

A control delete is allowed only while `pending` and only when no stage row, outbox row, or revision id exists. The job header cannot be deleted or change kind while a control exists. An `evaluation_apply` job's `request_json` and `result_json` text are capped at 2048 characters. Upload and report payloads are not capped by this guard.

Scope id, team, level, and position freeze while a control references that scope. Readiness may still change. The scope row cannot be deleted while referenced.

## What the database deliberately does not decide

Enqueue and promotion still have to reject:

- a requester who is not a persisted active Admin at that moment
- a deleted Admin replayed from the actor snapshot
- a scope outside the proven Coding, Submission, or Outbound Employee admission
- a version that is not the approved version for that exact scope and month
- a rules checksum, engine version, proof fingerprint, or lineage fingerprint that does not match the pinned source
- a cross-scope or cross-month binding that merely shares a team id
- a stale admin, engine, or source observed again at promotion time

Nullable user deletion cannot reopen a job. The snapshot remains attribution. It is not authorization.

The history year check on revisions remains 2000..2200. This foundation uses 2000..2100 for apply controls and stage rows only. History guards are not weakened.

SQL does not recompute the canonical hash. SQLite `json()` and PostgreSQL `jsonb` do not produce the same text, so equality of hash to payload stays in the application helper `canonical_row_hash`. The database rejects a non-object payload and a hash that is not 64 lowercase hex characters.

## Later revision manifest

Do not change `EvaluationRevision` or the workflow writer in this slice. Legacy revisions still store full `prior_snapshot` and `applied_snapshot` documents. Readers and rollback of those documents stay as they are.

A later promotion may store this object instead of rebuilding the population into the revision:

```json
{
  "schema": "evaluation_apply_manifest_v1",
  "job_id": "<processing job id>",
  "claim_epoch": 0,
  "evidence_table": "evaluation_apply_stage_rows",
  "record_count": 0,
  "before_hash": "<64 lowercase hex>",
  "after_hash": "<64 lowercase hex>"
}
```

The manifest points at immutable stage rows for that job and epoch. It is not a place to paste the population. A reader that does not recognize `evaluation_apply_manifest_v1` must keep treating every other snapshot shape as a legacy full snapshot. This slice does not implement that reader.

## Downgrade

Downgrade counts `evaluation_apply` jobs, non-zero `claim_epoch` values, controls, stage rows, and outbox rows. Any non-zero count raises `Refusing populated evaluation apply downgrade before any schema change` before a drop or a constraint restore. A missing foundation object raises `refusing to invent a downgrade path` rather than guessing a shape.

An empty downgrade drops the outbox, stage, and control tables, restores `ck_processing_job_kind` to the three original kinds, and drops `claim_epoch` plus `ck_processing_job_claim_epoch`. It does not rewrite old migration files, evaluation revisions, or history guards.

SQLite rebuilds `processing_jobs` only when the column list is exactly the pre-foundation order, or already the widened order with `claim_epoch` last. Any other column set is refused. There is no foreign-schema fallback and no repair of a populated invalid schema.

`create_all` places `claim_epoch` after `max_attempts`. The migration places it at the end. Both shapes satisfy the verifier's column set. A SQLite rebuild does not reshuffle an unexpected order.

## Verification limits

SQLite tests prove the helper, the guards, and direct SQL failures in memory. They are not PostgreSQL certification.

The verifier compares each foundation check with its canonical predicate. PostgreSQL may deparse that predicate with casts, `ANY (ARRAY[...])`, and extra parentheses. A different year bound, month bound, or allowed state does not match. A check name alone is not acceptance. Each check must be validated. Each guard trigger must be a `BEFORE` `FOR EACH ROW` trigger for exactly `INSERT`, `UPDATE`, and `DELETE`, with no `WHEN` predicate, enabled for a normal session, and bound to the `public` function of that name. Replica-only is not enabled. Each foreign key must name the referenced schema, columns in order, and delete action, and it must be validated. Each essential index must keep its key order and, where it is partial, its predicate. History guards and the history year span 2000..2200 stay unchanged. Apply controls and stage rows stay 2000..2100.

PostgreSQL guard functions take row locks in one order: `processing_jobs`, then `evaluation_scopes`, then `evaluation_apply_controls`, then `performance_records`. A statement that already holds its own row locks only later rows. Stage validation locks the job, the control, and the performance record before it trusts the epoch or the month. Reclaim locks the job first, then the control and any staged performance records, and re-reads the live epoch. This slice still has no worker, route, or runtime activation.

`Backend/tests/evaluation_apply_foundation_pg_checks.py` is outside normal collection. It reuses the history module's allowlist exactly: `127.0.0.1:55432/pms_eval_review_fix16` and `127.0.0.1:55433/pms_eval_review_fix18`, user `pms_eval_test`. It requires the test environment above before import, refuses any other host, database, or search path, and resets only `public` on those disposable databases. Run it sequentially so it does not overlap another schema reset. This foundation slice does not execute that module.

The Alembic chain's `performance_records` table uses the composite primary key `(id, year)`. The stage foreign key uses that identity. `Database/pms_scheme.sql` is a separate partitioned bootstrap and is not what this migration upgrades.

No query budget or production latency figure is claimed. The audit's snapshot floor (about 8.6MB JSON and 60MB Python peak for 2000 padded rows, about 0.4MB JSON and 3MB peak for a 100-row page) is a measurement of today's synchronous apply, not a service level and not a result of these tables.

## Phase 7B next slice

Schema and the verifier are the gate. Do not start a worker until that gate has passed on SQLite and, separately, on the disposable PostgreSQL pair.

Phase 7B may add a bounded stager and one promotion transaction. It still does not add a worker, a route, or UI.

- Read the exact scope month with a keyset page. Do not call `EvaluationWorkflow.apply`.
- Load the approved version, engine label, and checksum once per batch. Do not change formulas. An engine constant may be introduced without changing caps, grades, or precision.
- Write stage rows only in `staging` at the active epoch. A repeated page is idempotent only when the expected before image, hashes, and rules checksum match.
- Keep attempt lineage. Do not delete older epochs in this next slice.
- Promote in one transaction: write the applied scores, insert one revision whose snapshot may be `evaluation_apply_manifest_v1`, insert one outbox row, then mark the control `promoted` with that revision id.
- Preserve legacy full-snapshot rollback. Do not reactivate an old approval.
- Reject a queued job whose admin, engine, source fingerprint, or approved version changed before promotion.
- Leave `POST /apply`, upload quarantine, `performance_record_versions`, and the public job kinds untouched.
- After that transaction exists, the disposable PostgreSQL checks can add crash points between score write, revision insert, and outbox insert. Those checks stay opt-in and sequential.

Phase 7C is the worker, cancel, retry, and authenticated routes. Phase 7D is the settings UI. Neither starts from this schema alone.
