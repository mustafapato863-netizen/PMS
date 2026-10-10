# Monthly evaluation background-apply progress UX

## Independent reviewer checkpoint

After the delegate exited, reviewer read product files and test changes, then independently reran77 focused cases (7.04s), type checking, lint, and build:ci, all exit0. Production build1.19s and bundle budgets passed; existing512.75kB entry warning persists. Existing28 panel assertions are preserved; their mock router now explicitly returns disabled capability for the synchronous baseline, without relaxing their lifecycle or scoring assertions. The reviewed backend now returns the exact latest/status envelope plus Boolean presentation hints, with server-side command authorization remaining mandatory. Local integration and actual200-person browser/worker/native recovery verification still pending; this is not production acceptance.

Implementer record for a frontend candidate. This note is advisory. It is not independent acceptance, a completed Phase 7D, a release, or an all-team admission change. Browser checks and live API checks were not run. The reviewer composes those after the backend review.

Date: 2026-10-10. Checkout: `C:\Users\sghd70204\.codex\worktrees\evaluation-apply-progress-ui\PMS_Dashboard`, HEAD `e5176bcf777173ee0e16a1b6d9705ffadbd08f0e`. The work is uncommitted. No commit, push, pull request, deploy, or index update. No server, private database, PostgreSQL, Redis, Docker, or browser process was started. Backend files were not edited.

`graphify-out/graph.json` was absent, so there was no graph query. `graphify update` was not run. This lane forbids index changes.

## What the screen does

The existing Evaluation settings panel still posts synchronous `POST /api/settings/evaluation/apply` only after capability data is the literal boolean `enabled: false`. While the capability request is pending or refetching, Apply is omitted and neither path runs. A capability error, a non-boolean `enabled`, or a malformed capability body shows an unavailable message and a **Retry availability check** button. That state does not fall back to synchronous apply.

When `enabled` is literal `true`, Apply posts `POST /api/settings/evaluation/apply-jobs` with `{ scope_id, year, month }`. A queued acceptance is shown as **Queued** with “Scores are unchanged.” It is not a completed apply and it does not refresh live evidence. The card then shows staged progress bounded to 0–99, **Committing** at 99, **Committed** while acknowledgement is still outstanding at 99, and **Succeeded** at 100. Failed and cancelled jobs say that uncommitted scores are unchanged.

Cancel requires a second confirmation. Retry is offered for a failed or cancelled job unless the status says retry is false; that false flag explains that another admin cancels the old job and captures a new one, and the original attribution stays. Recovery is offered only for a committed revision that is still awaiting acknowledgement, and the button acknowledges that revision. It does not post another apply. Rollback stays on the existing latest-history control.

Changing scope, year, or month while a job is open is allowed. The page says the background apply continues on the server and follows the selection. A second Apply click on the same open binding does not post again. A network failure or a response that is not a valid queued payload refreshes the latest job first. An already-open job is adopted. Otherwise the screen says acceptance was not confirmed and waits for another user click. There is no automatic second POST and no synchronous fallback. HTTP 401 and 403 keep the server message and add that this screen did not grant permission.

The first confirmed promoted state that has a revision id, or a succeeded state, refreshes committed evidence once for that job and revision. Later polls, a succeeded state for the same revision, and reopening the screen do not refresh it again. A response for a different scope or month does not refresh the period on screen. Draft, revise, approve, enqueue, cancel, and retry do not refresh live evidence.

Non-admin roles do not start these queries. The existing admission copy is unchanged: unsupported families stay blocked by the panel behavior that was already tested.

## Endpoint assumptions

Every call uses the existing `fetchWithRole` helper and `readEvaluationEnvelope`. A successful StandardResponse returns `body.data`. When `data` is null, the reader returns the whole body, matching the panel’s current `readJson`. An HTTP error uses `detail` string, `detail.message`, or `body.message`, and keeps `detail.code` on `EvaluationRequestError`.

| Call | Body | Accepted data |
| --- | --- | --- |
| `GET /apply-jobs/capabilities` | none | `{ enabled: true }` or `{ enabled: false }` only |
| `GET /apply-jobs?scope_id&year&month` | none | one latest job, or no job. See the envelope list below |
| `POST /apply-jobs` | `{ scope_id, year, month }` | `{ enabled: true, outcome: "queued", job_id, state: "pending", job_status: "queued", claim_epoch, expected_count, resumed }` |
| `GET /apply-jobs/{id}` | none | `{ enabled: true, outcome: "status", job_id, state, job_status, claim_epoch, staged_count, promoted_count, stage_cursor, revision_id, progress, attempt_count, safe_reason }` |
| `POST /apply-jobs/{id}/cancel` | `{}` | `{ state, job_status, ... }` with a valid pair |
| `POST /apply-jobs/{id}/retry` | `{}` | `{ state: "pending", job_status: "queued", claim_epoch, ... }` |
| `POST /apply-jobs/{id}/recover` | `{ expected_epoch }` | `{ state, job_status, revision_id, ... }` |

`expected_epoch` is the job’s current `claim_epoch`. Cancel and retry send `Content-Type: application/json` and the exact body `{}`.

Status may also include `expected_count` and permission flags. The flags are optional booleans `can_cancel`, `can_retry`, and `can_recover`, or `permissions.cancel`, `permissions.retry`, and `permissions.recover`. A missing flag stays unknown. It is not treated as a grant or a denial. A non-boolean flag, or a direct flag that disagrees with the nested flag, is a malformed status. A command response that omits the flags keeps the flags already known for that job.

Accepted state pairs are `pending/queued`, `staging/running`, `promoting/running`, `promoted/running`, `promoted/succeeded`, `failed/failed`, and `cancelled/cancelled`. Any other pair, a missing `job_status`, or a body whose message is `ok` without those fields is a visible error. `progress: null` and `progress` above 100 are malformed. A stored progress of 100 still displays 99 until the phase is succeeded. `claim_epoch` may be 0. Booleans are not accepted as counts. `stage_cursor` is kept for parsing and is not rendered. `safe_reason` is shown only when it matches `^[a-z0-9_-]{1,80}$`.

Polling uses TanStack Query `refetchInterval` of 2000 ms only while the open phase is queued, staging, committing, or awaiting acknowledgement. The interval function returns false for a terminal phase, a malformed body, any query error, and an HTTP 401 or 403. `refetchIntervalInBackground` is false, so a background tab uses the library default. These queries and the enqueue, cancel, retry, and recover mutations set `retry: false`. The app QueryClient still retries other mutations once. Reopening the screen calls `GET` latest. The job id is not written to `localStorage` or `sessionStorage`, and the feature does not call `setInterval` or `setTimeout`.

### Latest envelope

`parseLatestApplyJob` is the only latest parser. After the standard wrapper is unwrapped:

- `null`, `{ data: null }`, `{ success: true, data: null }`, `{ job: null }`, `{ latest: null }`, and `{ jobs: [] }` are no job.
- `{ job: snapshot }`, `{ latest: snapshot }`, `{ jobs: [one snapshot] }`, and a bare object that already has `job_id` are parsed with the status parser.
- That snapshot therefore has to include `enabled: true`, `outcome: "status"`, and the status fields above. A thinner summary is a visible malformed status and blocks a new enqueue.
- More than one of `job`, `jobs`, and `latest`, a `jobs` list longer than one, `{}`, `{ message: "ok" }`, and `{ success: true }` without a job are malformed. An empty object blocks enqueue so the screen does not send a second POST.

If the backend’s latest object uses a different wrapper or omits `enabled` and `outcome`, align that envelope or this one helper during review. This lane did not edit the backend to force a match.

## Files

| Path | Role |
| --- | --- |
| `Frontend/src/components/settings/evaluationApplyJobs.ts` | Typed capability, latest, status, enqueue, cancel, retry, and recover client, plus the progress and permission rules |
| `Frontend/src/components/settings/evaluationApplyJobs.test.ts` | Parser, hook, polling, invalidation, and source-boundary tests. 22 tests |
| `Frontend/src/components/settings/EvaluationApplyProgress.tsx` | Compact progress card, semantic progress bar, confirm-cancel, retry, and recover actions |
| `Frontend/src/components/settings/EvaluationApplyProgress.test.tsx` | Card rendering and action tests. 5 tests |
| `Frontend/src/components/settings/EvaluationSettingsPanel.tsx` | Wires the hook beside the existing editor, proof, history, and synchronous apply path |
| `Frontend/src/components/settings/EvaluationSettingsPanel.test.tsx` | Existing assertions kept. 22 background-apply cases added. 50 tests in this file |
| `docs/qa/evaluation-apply-progress-ui-2026-10-10.md` | This note |

No router, sidebar, package, lockfile, marketing, math, performance-cache, backend, or source-workbook file was edited.

## Commands and results

Shell commands were run through `rtk proxy`. Node printed its existing `NO_COLOR` / `FORCE_COLOR` warning on the test, lint, and build commands. Typecheck printed no diagnostics.

1. Focused Vitest, exit 0. Vitest 4.1.11. 3 files, 77 tests passed. Started 20:15:15. Duration 8.89s (transform 942ms, setup 1.61s, import 1.69s, tests 6.98s, environment 5.73s). The 77 tests are 50 panel tests, 22 client tests, and 5 progress-card tests. The panel file’s previous 28 tests are included in the 50.

```
rtk proxy npm --prefix Frontend run test -- src/components/settings/EvaluationSettingsPanel.test.tsx src/components/settings/evaluationApplyJobs.test.ts src/components/settings/EvaluationApplyProgress.test.tsx
```

The new panel cases cover capability false, pending, and error; queued apply with no live-score refresh; one POST for a double click; unknown acceptance and adoption of an open job; a stale month and a stale scope; a malformed `ok` body; one evidence refresh for the first confirmed revision; cancel confirmation; same-job retry; recover with `expected_epoch`; close and reopen without browser storage; draft, revise, and approve without a live refresh; omitted permission flags; a denied retry; history rollback remaining on the latest revision; a selection change while a job continues; and a 403 cancel denial.

2. Typecheck, exit 0, 17.04s.

```
rtk proxy npm --prefix Frontend run typecheck
```

3. Lint, exit 0, 25.93s. `eslint .` reported no findings.

```
rtk proxy npm --prefix Frontend run lint
```

4. Production build and bundle budget, exit 0. Vite 8.1.4 transformed 3400 modules and finished in 1.17s. `dist/assets/index-Bq3rYvE4.js` is 512.75 kB (gzip 153.74 kB). Vite printed its existing warning that some chunks are larger than 500 kB. `node scripts/check-bundle-budget.mjs` printed `charts runtime aggregate: 364.95 kB raw / 108.21 kB gzip` and `Bundle budgets passed.`

```
rtk proxy npm --prefix Frontend run build:ci
```

## Still for the reviewer

The backend runtime is separate. This record does not claim the live routes, the database, or a browser session were exercised. The latest-envelope assumption above is the point to align if the backend summary is thinner than a status document. The candidate remains uncommitted for that review.
