# Grok implementation contract — PMS-EVAL-001

Owner: Codex (orchestrator/reviewer). Implementer: Grok Build, `grok-4.7`, `xhigh` (verified supported on 2026-10-08).

Read the canonical `docs/plans/monthly-evaluation-settings-plan.md` completely and this contract before implementing any phase. Phase briefs are queued instructions, not evidence that their prerequisites passed. The orchestrator must update each brief with the accepted predecessor artifacts, commit and exact API/schema contracts before dispatch. Do not execute later phases yourself.

Read `approved-decisions.md` as the authoritative record of user decisions overriding proposed defaults in the canonical plan. Confirmed 2026-10-08: Admin alone manages every evaluation-configuration lifecycle stage. No Performance Team draft/preview/edit/approve/apply permission. Ordinary scoped performance reads keep existing authorization.

## Safety and ownership

- Work only in the supplied isolated worktree and assigned phase scope. Preserve unrelated changes. No production access, deployment, live data writes, or changes to running local services.
- Do not read credentials, .env files, external agent memory, or unrelated repositories. Never put secrets or real employee data in artifacts. Only disposable synthetic databases/fixtures may be written. A real local schema audit requires the orchestrator's verified loopback read-only connection.
- No git add/commit/push/merge/reset/clean/checkout/branch deletion or PR creation. The orchestrator owns these after independent review. Do not modify workflows to bypass release gates.
- Do not rewrite old results, grants, saved reports, plans, actions or notes. Preserve existing formulas, caps, grade bands, missing-value behavior and aggregation policy. Target/weight/direction are the initial release; custom formulas (Phase 9) are deferred.
- Preserve source-team identity under RCM/Pre-Approvals; Pharmacy/Sales/CSR are standalone functions. Hierarchy is not authorization. Never broaden narrow legacy grants.
- Prefix terminal commands with `rtk`; use `rtk proxy` where needed. Discover files with `rg`. Use apply_patch for edits. Backend application entry is app.py, not legacy main.py.
- No unsupported scope or silent defaults. Record a blocker where supported raw evidence, current schema, a business decision, or a safe test environment is absent. Do not fabricate runtime verification from migration source.

## Verification loop

Inspect current tests and fixtures before choosing commands. Run relevant tests with synthetic isolated data; make the smallest scoped fix, then rerun. Never weaken/delete/skip assertions merely to turn gates green. Report exact command, exit status, count and environmental limitations.

Known project gates (execute only relevant, safe gates for your phase):

- Backend cwd: `rtk proxy python -m pytest -q` (full suite after checking isolation); targeted tests during development.
- Frontend cwd: `rtk npm run lint`, `rtk npm run typecheck`, `rtk npm test`, `rtk npm run build:ci`.
- Frontend browser scripts: `rtk npm run test:e2e`, `rtk npm run test:visual`; use only Local/Test/Staging synthetic users and disposable data. Do not assume servers are ready.
- Migration phases: verify upgrade/downgrade/re-upgrade against a disposable PostgreSQL database matching production semantics; SQLite is insufficient evidence for partitions/FKs/NULL uniqueness. Never run migrations on existing databases.
- Inspect git diff/stat/untracked files and whitespace. Refresh graph using `rtk proxy graphify update .` after source edits if installed; report unavailability separately, not as test success.

## Output contract

Leave changes uncommitted. Return: status (complete/partial/blocked), concise changes, every touched file, exact tests/results, observed defects, assumptions/decisions, blockers, deferred items and prerequisite evidence for the next phase. Include a phase-specific evidence document. A successful process exit is not an accepted phase.

## PR and integration policy

One bounded implementer session/phase branch per PR. If a phase is too large, split into additional explicitly scoped sessions/PRs. Dependent PRs are stacked on an isolated integration branch, not merged prematurely into main. Parallel sessions are allowed only for truly independent scopes. Codex reviews tests before implementation, independently runs gates and requests rework as needed. Main remains untouched until integrated end-to-end gates pass; production deployment is a separate final action.
