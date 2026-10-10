# Dormant cache outbox delivery

Implementer record for a default-disabled publisher. This note is advisory. It is not independent acceptance, a release, or a runtime activation.

Date: 2026-10-10. Checkout: `C:\Users\sghd70204\.codex\worktrees\evaluation-outbox-delivery\PMS_Dashboard`, detached at `dbecea2ec736be327958e32f0951997d9e5699ea`. No commit, push, pull request, deploy, or production access. No existing source, test, schema, API, worker, settings, UI, config, or roadmap file was edited. No PostgreSQL or Redis server was contacted, reset, or started.

## Files and interface

### Independent review and narrow repairs

The writer completed and exited before reviewer edits. Complete new service, normal tests and opt-in native checks were inspected. The normal module no longer overwrites environment variables or removes `CI` at import; it requires the runner's explicit anonymous environment without imposing a Windows checkout location.

An immutable external reviewer failure-boundary probe produced **1 FAIL / 3 PASS, 7.14s**: due-row selection was outside the transaction error handler, so a selection failure escaped as raw details without rollback. The reviewer moved that selection/empty-page handling into the existing protected transaction; no scoring, API, runtime or schema change. Four normally collected regressions now cover selection/flush/actual commit-method failure plus a later row failure that rolls back the whole page. The immutable probe remains unchanged.

Fresh independent `CI=true` anonymous run: **16 PASS, 7 warnings, 8.28s** (12 normal cases + 4 immutable external cases), artifact `D:/Projects/PMS_Dashboard/tmp/reviewer-outbox-ack-ci-green-20261010.xml`. Actual commit-method failure leaves the row unpublished; a new publisher can repeat the already-successful external increment and acknowledge once. This is at-least-once, not exactly-once. No real Redis was contacted.

The reviewer then ran the opt-in checks sequentially on the strictly allowlisted PG16/18 scratch pair: **4 PASS, 7 warnings, 13.23s**, artifact `D:/Projects/PMS_Dashboard/tmp/reviewer-outbox-native-final-20261010.xml`. A holder locks the outbox only; another publisher skips it while independent parent lock probes succeed. Committed failure and rollback/crash-before-ack retry leave scores unchanged. Native behavior is real PostgreSQL with an injected fake client, not deployed multi-process/Redis certification. `git diff --check` passed. Local acceptance remains dormant; no worker registration, main push, PR or deployment. The full composed integration gate is separate.

New files only:

- `Backend/services/evaluation/outbox_publisher.py`
- `Backend/tests/test_evaluation_outbox_publisher.py`
- `Backend/tests/evaluation_outbox_publisher_pg_checks.py` (opt-in; not executed)
- `docs/qa/evaluation-outbox-delivery-2026-10-10.md`

`CacheOutboxPublisher(db, client=None, clock=None)` exposes `deliver_due(*, enabled=False, limit=20)`. The default `enabled` is `False`. Any value other than the boolean `True` returns immediately:

```text
{"enabled": false, "considered": 0, "published": 0, "failed": 0}
```

That return happens before the session, the client, and the clock are touched. There is no settings flag, worker branch, route, or package export. `worker.py`, `app.py`, `services/__init__.py`, and `services/evaluation/__init__.py` do not name this module. The module imports models and `apply_job_schema` only. It does not import the app, the worker, settings, Redis, `redis_provider`, or `CacheInvalidationService`.

An enabled call returns the same four keys with `enabled` true. `considered` is the locked page size. `published` and `failed` count rows whose delivery columns were flushed in that page. A database acknowledgment failure rolls back and raises `OutboxDeliveryError`; that path does not return a summary.

| Name | Value |
| --- | --- |
| `DEFAULT_BATCH_LIMIT` | 20 |
| `MAX_BATCH_LIMIT` | 25 |
| `BASE_RETRY_SECONDS` | 30 |
| `MAX_RETRY_SECONDS` | 900 |
| `DATA_VERSION_KEY` | `pms:version:data` |
| `INVALIDATION_CHANNEL` | `cache_invalidation` |

`require_batch_limit` accepts only a real `int` from 1 through 25. `bool`, `float`, `str`, `None`, zero, negatives, and larger integers raise `OutboxDeliveryError("invalid_batch_limit")` before SQL. The clock must return an aware `datetime`. A naive clock raises `invalid_clock` before SQL. When no clock is injected, the service uses `datetime.now(timezone.utc)`.

The Redis message is `json.dumps({"action": "version_bump", "type": "data", "version": version})`, which is `{"action": "version_bump", "type": "data", "version": 1}` for version 1. The client is used only as `incr("pms:version:data")` and `publish("cache_invalidation", message)`. The service never evaluates the client with `bool()`.

Stored failure text is one of these strings, each shorter than the existing 240-character outbox limit:

- `cache delivery client unavailable`
- `cache delivery increment failed`
- `cache delivery publish failed`
- `cache delivery increment reply invalid`
- `cache delivery publish reply invalid`
- `cache delivery revision binding missing`

The warning log is `cache outbox delivery retained: <code>` with that code only. `OutboxDeliveryError` messages are `invalid_batch_limit`, `invalid_clock`, or `acknowledgment_failed`.

## Transaction, lock, and failure boundaries

One enabled call reads one page and ends its own transaction. The caller is expected to have committed the promote first. The page is unpublished `namespace='data'` rows whose `next_retry_at` is null or at or before the clock, ordered by `next_retry_at` ascending, then `id` ascending, with `LIMIT` and no offset clause. An empty page rolls back and returns considered 0 without calling the client.

On a PostgreSQL dialect the select is `FOR UPDATE SKIP LOCKED` of `cache_invalidation_outbox` only. Other dialects, including the SQLite tests, pass `lock=False`. The statement does not lock processing jobs, scopes, apply controls, teams, or performance records, and it does not select stage rows, employees, KPI JSON, or `actor_snapshot`. After the lock, a second select reads `job_id` and `promoted_revision_id` where `state='promoted'`. That select has no `FOR UPDATE`. A row is deliverable when that promoted revision matches the outbox `revision_id`. The current requester role and `teams.is_active` are not read, so a committed invalidation stays deliverable after a later role or team change.

For each locked row the service then:

1. Marks `binding_missing` when the promoted revision does not match.
2. Marks `client_unavailable` when the injected client is `None`.
3. Calls `INCR`. An exception is `increment_failed`. The reply must be a real `int` greater than or equal to 1. `True`, `False`, `0`, negatives, floats, strings, and `None` are `increment_reply_invalid` and do not publish.
4. Calls `PUBLISH` with the generic message. An exception is `publish_failed`. The reply must be a real `int` greater than or equal to 0. Zero is accepted Redis command completion. It is not a subscriber acknowledgment.
5. On both valid replies, sets `delivery_attempts` to the previous count plus one, `published_at` to the same clock value, `next_retry_at` to null, and `last_error` to null.

A failed row stays unpublished. `delivery_attempts` rises by one, `last_error` is the generic string, and `next_retry_at` is the clock plus a bounded delay. After failure number 1 through 7 the delays measured in the SQLite suite were 30, 60, 120, 240, 480, 900, and 900 seconds. The formula is `min(30 * 2 ** min(attempts - 1, 5), 900)` where `attempts` is the count after that failure. A row whose `next_retry_at` is still in the future is left out of the page. The same row delivers after the clock reaches that instant and a client is present. Auth and session keys are not cleared. There is no process-local version fallback and no call to `bump_data_version`.

The page is flushed once and committed once. Redis command failures are part of that commit. `db.info["outbox_publisher_fault"]` set to `after_publish_before_ack` raises after both Redis replies and before the in-memory success mark. `before_ack_commit` raises after flush and before commit. Either fault, and any unexpected database error, rolls the page back. Unexpected errors become `OutboxDeliveryError("acknowledgment_failed")` with no `__cause__`. The raised path does not report `published`. After a successful commit each outbox object is expunged. Rows are never deleted.

The existing outbox guards are unchanged: identity is immutable, attempts cannot decrease, a published row's delivery columns stay frozen, and `published_at` still requires `delivery_attempts >= 1`. This publisher does not insert outbox rows and does not write a rollback outbox row.

## Tests and timings

Environment before imports: `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, `REDIS_URL` empty, `CI` removed, `PYTHONUTF8=1`. Working directory `Backend`. Commands were prefixed with `rtk proxy`. The SQLite tests reuse the anonymous `db` fixture from `test_evaluation_bounded_apply.py` by loading that module. Assertions read `cache_invalidation_outbox` back from the database. The injected client is a fake. `EvaluationWorkflow._bump` stays patched by that fixture, so promote does not touch Redis.

`python -X utf8 -m pytest -q -p no:cacheprovider --tb=short tests/test_evaluation_outbox_publisher.py`: **8 passed, 7 warnings, 4.81s**. The warnings are the existing Pydantic v1 validators in `models/team_models.py`.

| Test | What the database and fake client showed |
| --- | --- |
| `test_disabled_call_does_not_query_or_touch_the_client` | `enabled` omitted, `False`, `None`, `0`, `1`, and `"true"` return the zero summary. A raising session, client, and clock are not called. AST import and worker/app text checks pass. |
| `test_batch_limit_and_clock_reject_before_any_sql` | Bad limits and a naive clock emit no SQL. An empty table with limit 25 runs one outbox select and does not call the client. |
| `test_postgresql_lock_sql_is_outbox_skip_locked_only` | Compiled PostgreSQL SQL contains `FOR UPDATE` and `SKIP LOCKED` on the outbox table, has no offset clause, and does not name parent or payload tables. The binding select reads `promoted_revision_id` and has no `FOR UPDATE`. |
| `test_success_with_zero_subscribers_is_immutable_without_authority` | Coding July promote, then the admin becomes inactive Performance Team and every team is inactive. Publish reply 0 commits attempts 1 and `published_at`. A new instance does not increment again. Live scores, plans, actions, and saved report bytes stay put. The process-local fallback counter stays put. |
| `test_absent_client_backoff_is_bounded_and_a_new_instance_can_finish` | Seven absent-client failures use the delays above. One second early, the row is skipped. A new instance at the due instant publishes once and leaves attempts 8. |
| `test_redis_failures_and_invalid_replies_do_not_acknowledge` | Increment exceptions and invalid increment replies do not publish. A publish exception after a successful increment, and invalid publish replies, leave the row unpublished. A later new instance publishes. Log text has no sentinel payload. |
| `test_crash_after_external_success_does_not_persist_or_suppress_retry` | Faults after publish and before commit roll back to attempts 0. The fake version is already 2. The next instance publishes with version 3 and attempts 1. A further call does not increment. |
| `test_batch_retains_one_row_and_a_fixed_query_budget` | Coding and Submission July leave two outbox rows. Limit 1 locks only the first due id. The identity map at the lock callback contains only `CacheInvalidationOutbox`. SQL kinds are outbox select, binding select, outbox update. The second call publishes the other row and leaves the first image unchanged. |

SQLite renders `LIMIT ? OFFSET ?` with integer binds `[limit, 0]` even though the statement's offset clause is `None`. The batch test requires those binds and rejects the text `offset 1`. SQLite does not take `FOR UPDATE`, so the SQLite suite does not certify skip-locked overlap.

Related, same environment: `tests/test_evaluation_apply_foundation.py`, `tests/test_evaluation_public_authority.py`, and `tests/test_processing_jobs.py`: **60 passed, 8 warnings, pytest 12.18s** (shell 15.06s). Those files were not edited. The full backend suite was not run.

`evaluation_outbox_publisher_pg_checks.py` is not named `test_*.py`, so normal collection does not run it. It was not executed. It reuses the existing foundation PostgreSQL fixture and the history allowlist `127.0.0.1:55432/pms_eval_review_fix16` and `127.0.0.1:55433/pms_eval_review_fix18`. Its two cases are a holder connection that keeps the outbox row lock while a second publisher considers zero rows and parent `FOR UPDATE` probes do not block, and a committed publish failure followed by crash-before-ack retries that increment again. The foundation fixture resets `public`. A reviewer runs that file alone, sequentially, on those scratch databases.

Repository-root `git diff --check` was run after these files existed. `graphify update .` completed as AST extraction with no LLM call: exit 0, shell 68.73s, 10465 nodes, 28628 edges, 460 communities. `graphify-out/` remains gitignored. The extractor also warned that 21 JSON sources produced no nodes and that `tree_sitter_sql` is not installed.

## At-least-once behavior

A crash or a rolled-back commit after `INCR` or `PUBLISH` leaves `published_at` null. The next attempt may increment and publish again. The SQLite crash test observes versions 1 and 2 with the row still at attempts 0, then a persisted publish at version 3. The service keeps no delivered-id set. A new instance has no memory of the earlier Redis replies. Completion is the committed `published_at`, not an in-memory flag.

The page shares one commit. If a later row in that page raises before commit, earlier rows in the same uncommitted page lose their delivery-column updates too, while their Redis commands may already have run. A retry of those rows increments again. A Redis failure on one row is committed with the page, so a later successful retry is another increment after the failed attempt's increment. `PUBLISH` returning 0 records acceptance of the command. It does not record that a subscriber ran.

Already published rows stay out of the due predicate. The success and crash tests read the row image back and require the identity columns to stay unchanged, and a following call issues no further `INCR`.

## Pending gates

Native PostgreSQL overlap and the opt-in file above were not run. No real Redis server was used. The full backend suite, enqueue, worker registration, lease, recovery, and UI were not added and were not exercised as a runtime. `evaluation_cache_identity` remains the database authority; this service does not replace it with Redis, a TTL, or an actor snapshot. Scoring, formulas, caps, precision, units, weights, grades, and ingestion were not edited. The Marketing 131-versus-68 failure was not re-run and was not modified. No migration was added. No release, UAT, or production publication was performed.
