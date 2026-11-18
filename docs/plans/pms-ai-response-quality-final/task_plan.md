> [!NOTE]
> **HISTORICAL REGRESSION & WIP FINDINGS / REFERENCE ONLY**
> This task plan records the response quality review and evaluation fixes (tie handling, confirmed employee persistence, metric independence).
> Active architecture and execution transitions to the model-led pipeline under [PMS AI Model-Led Implementation Plan](../PMS_AI_MODEL_LED_IMPLEMENTATION_PLAN.md).
> All evaluation fixtures and regression contracts documented herein remain preserved as regression baselines.

# PMS AI response quality: remaining acceptance fixes

## Goal
Close the remaining response-quality gaps reported in the unseen evaluation: honest tied rankings and follow-ups, explicit country identity, and a new held-out evaluation. Complete signed-in browser verification only with the authorized local setup.

## Phases
- [x] Inspect current branch, dirty files, prior implementation report, and project instructions; preserve the existing WIP.
- [x] Reproduce and fix tie disclosure, candidate references, country display, and evaluator defects confirmed by source review.
- [x] Build and run a new 32-prompt evaluation across 8 conversations, separate from the previously exposed fixture.
- [x] Run focused backend regressions and frontend type checking; record the unrelated existing TypeScript failure.
- [x] Implement follow-up review fixes: preserve already confirmed employees across follow-ups, keep requested operation/metric independent across trend/score/role/bookings follow-ups, protect URLs/links in country formatting, strengthen `run_unseen_eval.py`, resolve `TeamDeepDiveView.tsx:2711` compile blocker, and run a brand-new sealed final evaluation without tuning against it.
- [x] Check browser availability (`PMS_E2E_USERNAME`/`PMS_E2E_PASSWORD` unset, local ports `8000`/`5173` down; production tab left untouched).
- [x] Review focused changes, run `graphify update .`, and record evidence and remaining limits.

## Constraints
- Preserve existing uncommitted work and keep unrelated changes intact.
- Use synthetic fixtures for mutating tests; do not write to production.
- Do not bypass auth, reset passwords, or enable AI on a shared database.
- Do not merge, push, or deploy.
- Existing report's 14 held-out turns are now exposed; do not label them a fresh holdout.
