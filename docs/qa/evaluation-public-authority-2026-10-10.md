# Public workflow Admin recheck after the team fence

## Independent reviewer verification

The reviewer reran all 37 new authority tests plus 35 unchanged monthly workflow/direction tests: **72 passed, 8 warnings, 23.78s**, evidence `D:/Projects/PMS_Dashboard/tmp/reviewer-public-normal-green-20261010.xml`. The immutable two-connection PostgreSQL16/18 probe first reproduced **8 unauthorized-success failures** on accepted closure446735a, then passed **8 cases in21.11s** on this candidate. It preloads the User, waits for the genuine Team row-lock barrier, commits role revocation or deactivation from another connection, then verifies denied Apply/Rollback and unchanged scored state. Evidence: `reviewer-public-revocation-pg-red-20261010.xml` and `reviewer-public-revocation-pg-green-20261010.xml` in the same primary tmp directory.

The complete new test file and workflow diff were reviewed independently; `git diff --check` passed. This verifies visibility of revocation committed **before the post-fence SELECT**, not transaction-wide revocation serialization. Full composed backend/regression acceptance remains separate; no production access or publication occurred. The original implementer-only report below is retained with its narrower execution boundary.

Date: 2026-10-10. Checkout: `C:\Users\sghd70204\.codex\worktrees\evaluation-public-authority\PMS_Dashboard`, detached at `446735a963658e34dcbd1e2edc924dc2692e69b9`. No commit, push, pull request, deploy, or runtime activation. The bounded-apply worktree was not read or edited. No PostgreSQL database was created, reset, or queried.

## Change

`EvaluationWorkflow._require_admin` is unchanged as a check. It still calls `require_action` and then loads the persisted user with `populate_existing()`. The actor dict is not the persisted role. A non-Admin actor is still rejected before that read. A missing user, a role other than Admin, or `is_active` other than true raises `AccessDenied`.

New `EvaluationWorkflow._require_admin_after_fence` calls that same check. It does not lock the user row and does not retry the team lock.

`EvaluationWorkflow._guard_period` now takes the actor. After `_lock_team` returns, and before the inactive-team check or the capability decision, it calls `_require_admin_after_fence`. Callers that pass the actor are `open_draft`, `edit_draft`, `approve`, `preview`, `revise`, `impact_preview`, and `apply`. `run_preview_job` is covered because it calls `preview`.

`EvaluationWorkflow.rollback` calls `_require_admin_after_fence` immediately after its own `_lock_team` and before the revision lock or any restore.

`_lock_team` is still the existing `lock_team_rows` call. Version, scope, and revision locks are unchanged and still come after the team fence. There is no new table, migration, session actor cache, or user-row lock.

## What this freshness is

The new read is one non-locking `SELECT` after the team fence returns and before the management mutation. In the sequencing hook, the role or `is_active` update is flushed inside the replaced `_lock_team`, with `synchronize_session=False`, after the real lock request returns. The preloaded `User` still shows Admin until `populate_existing()` runs. The post-fence check then sees Performance Team or `is_active` false and raises. The mutation does not commit.

That is not transaction-wide revocation serialization. A revocation that becomes visible only after this `SELECT`, including one that commits while later version, record, or revision locks are held, is not read again. The team row lock does not block an update to the user row. SQLite does not take the team row lock, so these tests do not certify a PostgreSQL wait. On READ COMMITTED PostgreSQL, a `SELECT` after `lock_team_rows` returns would be expected to see a user update that committed while this transaction waited for the team row. This lane did not run that race.

Several public methods still call `catalog.sync()` before the fence. That existing call can commit scope-catalog rows before the revocation is visible. The post-fence denial does not roll that commit back, and it does not commit the settings mutation.

## Paths without this recheck

These methods do not wait on the team fence. This lane left them on their existing entry checks:

- `sync_catalog` writes scope rows and has no team fence.
- `export_version`, `get_version`, and `period` are Admin reads.
- `reads` is an applied-evidence read and is not Admin-only.
- `rescore_uploaded` is the upload pin. It has no actor and is not a settings management call.

No API, worker, importer, formula, or UI file was edited.

## Invariants left in place

Entry `require_action` remains. A direct workflow actor whose role is Manager is denied before the fence even when the persisted user is Admin. HTTP `get_current_user_scope` still copies the persisted role onto the actor, so a request role of Manager or Employee for a persisted active Admin can still apply and roll back. A request that presents a Performance Team user as Admin is still 403 before the fence.

A persisted Admin who is still Admin after an idle fence can apply. A second apply of the same evidence stays idempotent and does not bump the data cache version. Approval does not rescore. Rollback restores the pre-apply record snapshot, leaves a superseded approval superseded, leaves the current approval approved, and a second rollback stays `immutable`. Plans, actions, and saved report bytes stay unchanged on the denied paths and on that happy path.

No formula, cap, weight, grade, precision, or source unit was edited. Supported Coding Employee, Submission Employee, and Outbound Employee July and August 2026, and the blocked families, stay in the files this lane did not touch. The related suites below passed without edits.

## Gates

Environment before imports: `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, `REDIS_URL` empty, `CI` unset, `PYTHONUTF8=1`. Working directory `Backend`. Commands were prefixed with `rtk proxy`.

RED, before the workflow edit, `python -X utf8 -m pytest -q -p no:cacheprovider --tb=line tests/test_evaluation_public_authority.py`: 22 failed, 15 passed, 8 warnings, pytest 18.70s (shell 22.67s). Every failure was `AccessDenied` not raised at the fence revocation test. The 22 failures are apply, rollback, idempotent apply, open draft, copy-previous open draft, edit draft, approve, revise, impact preview, preview, and preview job, each for a role change to Performance Team and for deactivation. Spoof, direct stale actor, idle fence, happy path, and stale HTTP request role passed on that run.

GREEN, same file after the edit: 37 passed, 8 warnings, pytest 16.35s (shell 19.75s).

Related: `tests/test_evaluation_month_revision.py`, `tests/test_monthly_evaluation.py`, `tests/test_evaluation_workflow_consumer.py`, `tests/test_evaluation_direction_lifecycle.py`: 35 passed, 8 warnings, pytest 21.44s (shell 25.61s).

Repository root `git diff --check` exited 0 with no findings. The full backend suite was not run. `graphify-out/` was absent; `graphify update .` rebuilt a gitignored graph (878 files, 120.73s) and did not add a tracked path.
