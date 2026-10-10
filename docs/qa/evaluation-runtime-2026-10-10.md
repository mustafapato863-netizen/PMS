# Opt-in evaluation apply runtime

## Independent reviewer follow-up (supersedes implementer seams below)

The original candidate independently passed146 cases in35.25s with process-local explicit anonymous environment values. Windows PowerShell deletes empty environment assignments; an earlier reviewer143-pass/3-fail run accidentally resolved localhost Redis and is not isolation evidence. The corrected runner verifies resolved REDIS_URL is empty before imports. No application/private database was used.

Reviewer reproduced actual latest-job same-second/UUID ordering and live page-budget starvation failures. The runtime now resumes only its own live staging token on the next bounded tick, with coordinator reauthorization/epoch/lease guards intact. Other workers cannot resume it; expired tokens still follow the existing new-epoch recovery. The25-page budget remains finite but no longer forces endlessly restarting larger cohorts. Admission records fenced, microsecond-monotonic job chronology; latest lookup prioritizes an open binding over tied historic terminal rows. API status adds can_cancel/can_retry/can_recover presentation hints, while command authorization stays persisted-Admin and same-job retry stays requester-only. Safe failure codes are now exposed without exception text. No schema or admitted scoring math changed.

Focused29 cases passed9.80s. A strengthened independent actual-login-JWT regression forcing both insert AND update timestamps tied passed1 case3.24s; original RED evidence is retained. A subsequent149-case run passed148 and failed only a new reviewer test retaining a detached ORM User object after status rollback; the harness now captures its scalar id before that boundary. The corrected independent suite passed149 cases,10 warnings,37.57s, exit0 (reviewer-runtime-final-candidate-20261010.xml). Native/browser/final composition gates remain pending. Implementer statements below describing live leases waiting/restarting after the page cap and absent permission hints are historical, not current behavior.

Implementer record for Phase 7C2. The durable lease coordinator is now callable from the worker and from an authenticated management API. The product flag stays off. This note is advisory. It is not independent acceptance, a completed release, a p95, or evidence from PostgreSQL, the full backend suite, a browser, Docker, or a private workbook.

Date: 2026-10-10. Checkout: `C:\Users\sghd70204\.codex\worktrees\evaluation-runtime-management\PMS_Dashboard`, HEAD `e5176bcf777173ee0e16a1b6d9705ffadbd08f0e`. No commit, push, pull request, or deploy. Nothing is staged.

`graphify-out/graph.json` is absent, so there was no graph query. `graphify update` was not run. The reviewer owns that update.

## Files

- `Backend/config/settings.py` — `PMS_EVALUATION_APPLY_JOBS_ENABLED`, default false.
- `Backend/worker.py` — one hook before the legacy claim. The hook returns before `SessionLocal` unless the flag is the literal `True`.
- `Backend/api/routers/evaluation_settings.py` — apply-job routes on the existing evaluation router.
- `Backend/services/evaluation/lease_coordinator.py` — cross-Admin status, cancel, and recover; same-transaction audit; `fail_live`.
- `Backend/services/evaluation/outbox_publisher.py` — module docstring only. Delivery behavior is unchanged.
- `Backend/services/evaluation/runtime.py` — new worker adapter and outbox registration.
- `Backend/tests/test_evaluation_runtime.py` — new anonymous SQLite characterization.
- `Backend/tests/test_evaluation_lease_coordinator.py` — the other-Admin status denial is now an allowed inspect. Start by that Admin stays denied.
- `Backend/tests/test_evaluation_bounded_apply.py` — `PUBLIC_ROUTES` gained the seven new route tuples. The equality check is unchanged.
- `docs/qa/evaluation-runtime-2026-10-10.md` — this note.

No migration, model, scoring formula, bounded-service formula, frontend, or `evaluation/__init__.py` edit. No native opt-in file was added. `processing_job_service.JOB_KINDS` stays `pms_upload`, `report_generation`, and `story_report_generation`. `worker.py` does not contain `evaluation_apply`, `outbox_publisher`, or `CacheOutboxPublisher`. The runtime does not import `EvaluationWorkflow`.

## Flag

`parse_bool(..., default=False)`. Unset stays false. The environment values `1`, `true`, `yes`, and `on` parse to boolean `True` at process start. The Python string `"true"` is not `is True`, and the copy on `_SettingsCompatibility` is taken when that class body runs. The worker, the routes, and `run_enabled_tick` read the module global and accept only the literal `True`.

Synchronous `POST /apply`, draft, revise, approve, read, and rollback are not gated.

## Management API

Routes sit on the evaluation-settings router. The mounted paths are under `/api/settings/evaluation`.

| Method | Path | When the flag is off |
| --- | --- | --- |
| GET | `/apply-jobs/capabilities` | 200 `{"enabled": false}` after the Admin check |
| GET | `/apply-jobs?scope_id&year&month` | 503 `runtime_disabled` |
| POST | `/apply-jobs` | 503 `runtime_disabled` |
| GET | `/apply-jobs/{job_id}` | 503 `runtime_disabled` |
| POST | `/apply-jobs/{job_id}/cancel` | 503 `runtime_disabled` |
| POST | `/apply-jobs/{job_id}/retry` | 503 `runtime_disabled` |
| POST | `/apply-jobs/{job_id}/recover` | 503 `runtime_disabled` |

The 503 body is `{"message": "Evaluation apply jobs are disabled.", "code": "runtime_disabled"}`. The Admin check runs first. Missing credentials are 401. Manager, Performance Team, Employee, and a JWT whose role says Admin while the persisted user is not, are 403 `access_denied`. An inactive persisted Admin is 401 from the existing middleware. None of those responses capture, stage, or score.

Body models reject unknown fields. `year` and `month` on create, and `expected_epoch` on recover, are strict integers. JSON `true` is not epoch 1 and returns 422. A non-UUID job id is 422 before the handler. The list route returns the latest matching job summary, or `{"job": null}`, with no employee payload.

Same-job retry stays owner-only. Another Admin receives 403 and the message `Evaluation settings are limited to Admin.` That coordinator denial has no `code` key. The route-level non-Admin denial does include `code: access_denied`. The job, attempt count, and audit rows stay as they were.

## Who may manage a job

Any currently persisted active Admin may inspect a job, cancel it, or acknowledge an already committed promotion. A different Admin who wants a new attempt cancels the unpromoted job and enqueues a new job. That new row stores the new Admin as requester and writes a new actor snapshot. The old row keeps its requester, snapshot, and stage rows.

Start, heartbeat, stage, promote, acknowledge, and retry of the same job stay on the captured requester. The execution actor passed into those calls is only `{"user_id": "<persisted requester id>"}`. The stored snapshot is not read and is not a role grant. A revoked or deleted requester is not impersonated.

The grant is a fresh `User` read after the team fence and the job, scope, and control locks. The actor dict and the JWT role are not that grant. A role change that commits before the read is visible. A role change that commits after that nonlocking read is not held off for the rest of the transaction.

Enqueue of a still-open month by a different Admin remains `duplicate_binding` (409). Cancel releases the open binding. The replacement job is a new id.

## Audit

A cross-Admin inspect, cancel, or recover writes one `AuditLog` row in the same transaction as the management result. Same-Admin status still rolls back and writes nothing. The row uses `table_name` `evaluation_apply_controls`, `operation` `UPDATE`, `record_id` the job id, and `performed_by` the Admin who called. `old_values` and `new_values` contain only `action` (`inspect`, `cancel`, or `recover`), `claim_epoch`, `control_state`, `job_status`, and `requested_by_user_id`. Names, snapshots, source arrays, and raw errors are not stored.

Every successful cross-Admin call writes a row, including a repeated inspect, an idempotent cancel, a non-mutating recover, and a repeated recover. There is no UI yet. Polling will grow this table. Audit ids are random UUIDs, so id order is not insertion order.

A commit failure rolls the audit back with the mutation and surfaces `persistence_failed` without the original text.

## Worker tick

`run_worker` calls the evaluation hook, then the existing requeue and `claim_next`. `--once` still returns when the legacy claim is empty. The evaluation pass is capped, so it does not make `--once` infinite.

When the flag is on, one tick selects at most 8 scalar job ids. The statement does not lock `processing_jobs` and does not use `OFFSET`. The coordinator then takes the team fence before the job, scope, and control. The selected rows are `evaluation_apply` jobs whose requester is still an active Admin, and one of:

- `queued` / `pending`, available, and under `max_attempts`
- `running` / `staging` whose `lease_expires_at` is present and already due (`<= now`; equality is expired)
- `running` / `promoted` and still waiting for acknowledgement

A queued job is started, paged at 100 rows, promoted, then acknowledged. Each of those steps commits. An expired staging row is reclaimed through the existing retry proof and a new epoch; the same tick does not start that new epoch. A promoted crash is acknowledged once through `recover` with the stored epoch. That acknowledgement is not a rescore and does not insert another revision or outbox row.

`fail_live` fails a live staging token with an allowlisted reason and the static message `evaluation apply failed`. A promoted control, a succeeded job, or a stored revision id is preserved. `fault_injected`, `lease_expired`, `lease_held`, `persistence_failed`, `stale_epoch`, and `stale_token` are not turned into a second failure. Unexpected exceptions become `persistence_failed` with the cause discarded, and the runtime leaves that live token in place.

The candidate loop catches a failure, logs the static line `evaluation apply candidate skipped`, rolls back, and continues. One denied row does not stop the later rows. Rows whose requester is no longer an active Admin are left out of the window. They are not auto-failed. The month stays blocked until an active Admin cancels that job and enqueues a new one.

A tick stops after 25 pages. A live `running` / `staging` row is not a candidate, so a month that still has pages after that cap waits until the lease expires, then retry opens a new epoch and restages. The largest real team is 200 people, and the default page is 100, so that team finishes inside one tick. Empty page before completion fails the live token as `incomplete_stage`.

Outbox delivery is registered in `runtime.py` behind the same flag, after the job tick. `deliver_due(enabled=True)` locks at most the publisher's existing batch. The shared client is chosen with `client is None`. It is not tested with `bool()`, because `LazyRedisClient.__bool__` connects. Commands are direct `INCR` and `PUBLISH`. A failed increment leaves `published_at` null, sets `last_error` to `cache delivery increment failed`, and does not bump the process-local fallback version. `evaluation_cache_identity` stays the shared database hash when Redis is down. An empty `REDIS_URL` raises `ConnectionError` inside the client without opening a socket.

## What stayed closed

Admission was not edited. Marketing, Pharmacy, CSR, IP Final, Managerial, and Corporate stay unsupported. There is no weight-only bypass. Coding Employee, Submission Employee, and Outbound Employee for July and August 2026 remain the admitted families. Attendance stays 65 percent in both months. July keeps four KPIs with attendance at 70 percent. August keeps five KPIs with attendance at 60 percent and productivity at 10 percent. New-upload fixed-target conflicts still block. Stored corrections still use `check_conflicts=False`. Approve still does not rescore. Rollback stays latest-only. The identity trigger stays installed.

The SQLite characterization schema rejects an update of `actor_snapshot` with `evaluation apply captured identity is immutable`. A corrupt stored role cannot be planted without disabling that trigger. The trigger was not disabled. The execution test expects the rejection, rolls back, and checks that the stored Admin snapshot is unchanged while the tick passes only the requester id.

## Checks

From `Backend`, before imports: `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, `REDIS_URL` empty, `PYTHONUTF8=1`, `JWT_SECRET=anonymous`, `PMS_AUTO_SEED=false`, `PMS_SEED_DEMO_LEVELS=false`, `PMS_SEED_PERMISSIONS_ON_STARTUP=false`, `CI=true`.

One pytest process, exit 0:

**146 passed, 17 warnings, 35.54s.**

| Module | Collected |
| --- | ---: |
| `tests/test_evaluation_runtime.py` | 13 |
| `tests/test_evaluation_lease_coordinator.py` | 14 |
| `tests/test_evaluation_bounded_apply.py` | 25 |
| `tests/test_evaluation_apply_foundation.py` | 20 |
| `tests/test_evaluation_legacy_queue_isolation.py` | 59 |
| `tests/test_processing_jobs.py` | 3 |
| `tests/test_evaluation_outbox_publisher.py` | 12 |

The 17 warnings are the existing FastAPI, Pydantic, JWT key-length, paged-memory, and stage-row identity warnings. No test was skipped. The flag was left false except inside tests that set the literal `True`.

`git diff --check` on the tracked edits exited 0. The two new Python files and this note are LF and have no trailing whitespace. The existing Python files in this checkout are CRLF. `core.autocrlf=true` may rewrite those new files to CRLF the next time Git checks them out.

The runtime cases cover a disabled tick that does not open a session; the string `"true"` staying off; bearer denial before 503; synchronous `/apply` still scoring with the flag off; cross-Admin inspect, repeat inspect, owner retry denial, cancel, reopen, and recover of a committed promotion; a fault after promotion and before acknowledgement; one revision and one unpublished outbox row; revoked requesters left outside the window; one injected denial not stopping the next candidate; evidence drift and the attempt cap on retry; `fail_live` preserving a promotion; the identity trigger; a partial page held until a later epoch; publisher delivery without client truthiness; and `--once` claiming the legacy upload once while the evaluation job reaches `succeeded` only after the flag is on.

## Not run

Native PostgreSQL on `127.0.0.1:55432/pms_eval_review_fix16` and `127.0.0.1:55433/pms_eval_review_fix18` was not run, and those databases were not reset. Docker, application servers, Redis, private workbooks, the full backend suite, a browser, and a performance run were not started. No native opt-in file was added for the reviewer. SQLite does not certify a PostgreSQL lock wait or a clock that moves after the post-fence reading and before commit.

## Seams left for review

The second user read is the grant, and a revocation after it is visible only to a later transaction. Expired jobs whose requester is no longer an active Admin stay out of the eight-id window and are not failed automatically, so that month stays blocked until cancel. A tick that hits 25 pages leaves a live lease until expiry, then the next tick opens a new epoch. Cross-Admin polling writes an audit row on every call. `persistence_failed` drops the original exception and does not fail the live token. Owner-only retry does not add `access_denied` to the coordinator `AccessDenied` body.
