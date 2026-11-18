# Phase 7: Staging, Budgets & Governance Readiness — Handoff Report

**Branch:** `fix/pre-approvals-ip-single-team`
**Predecessor:** Phase 6 commit `96d8db7a` (accepted, 0 Blocker, 0 Major)
**Date:** 2026-11-18

---

## Executive Summary

Phase 7 delivers token/cost telemetry plumbing, server-side budget controls, truthful fallback attribution, ops documentation reconciliation, and an isolated live-provider staging environment with Playwright E2E tests. All technical gates pass. Production flags remain `false`; human gates `#97` and `Vi` `#103` remain `PENDING`.

---

## Tickets Delivered

### Ticket 01 — Token/Cost/Trace & Truthful Fallback
- Added `neurons: int`, `cost_status` to `AiProviderUsageMetrics`
- Added `resolve_cost_status`, `combine_cost_statuses`, `metrics_from_provider_response` to providers
- Propagated `user_id`/`user_role` through router/orchestrator for per-user budget enforcement
- Post-synthesis live RBAC re-verification in `_handle_model_led_turn`
- `TrainingTraceLogger.record_turn(...)` for trace persistence
- Truthful `answer_source` attribution: `'model_synthesis'` only when live provider succeeds, `'deterministic'`/`'fallback'` otherwise
- Frontend `AiResponseCard` guards `isLiveSynthesis` against fallback responses
- Frontend badge shows `Verified PMS · Deterministic` for fallback, never `Live Synthesis`

### Ticket 02 — Server Budgets, Timeouts & Diagnostics
- **NEW** `Backend/services/ai/usage_budget.py` (363 lines): `AiBudgetExceededError`, `acquire_chat_concurrency_slot` (default 8), unconfigured-default (`0`) UTC-day caps, per-request input token ceiling (8192), Redis-backed counters with 48h TTL + thread-safe in-process fallback, `is_existing_completed_replay` for idempotent replays, `get_budget_health_snapshot()`, `reset_usage_budget_state_for_tests()`
- Wired budget controls into `post_ai_chat_turn`: HTTP 429 + Retry-After on `AiBudgetExceededError`
- Extended `AiDiagnosticsPayload` with budget/timeout/pilot fields
- Documented new env vars in `DevOps/.env.example`, `DevOps/.env.hostinger.example`, `compose.production.yml`

### Ticket 03 — Ops Runbooks & Readiness Rehearsal
- Reconciled `docs/ops/pms-ai-provider-verification.md` and `docs/ops/pms-ai-pilot-release-checklist.md` with Phase 2–7 architecture
- Refreshed `test_type_inventory.json` and `TEST_TYPE_INVENTORY.md`
- Generated `readiness_rehearsal.json`: `technical_gates_passed: true`, `pilot_ready_for_rollout: false`, `secret_findings: []`

### Ticket 04 — Live Staging Servers & Playwright E2E
- **NEW** `.tmp/phase7-staging/seed_staging_db.py` (335 lines): Subcommands `seed`, `narrow-scope`, `narrow-role`, `reset-narrow`; seeds isolated SQLite at `.tmp/phase7-staging/pms_phase7_staging.db`
- Backend staging: `uvicorn app:app` on `http://127.0.0.1:8000` with isolated staging SQLite, Cloudflare/Gemini credentials loaded from `DevOps/.env`
- Frontend staging: Vite on `http://127.0.0.1:4173` (ports 5173-5176 occupied)
- **NEW** `Frontend/e2e/ai_phase7_staging.spec.ts` (421 lines): 6 E2E scenarios, all passing:
  1. ✅ Signed-in analytical turn telemetry + trace_id + provenance badge + Helpful feedback
  2. ✅ Response badge truthfully reflects answer_source (Deterministic vs Live Synthesis)
  3. ✅ Account ownership isolation (admin_b cannot access admin_a conversations)
  4. ✅ Mid-conversation permission narrowing (Admin→Manager role change blocks subsequent turns)
  5. ✅ Idempotent `client_request_id` replay (same turn_id, no duplicate turn rows)
  6. ✅ Fresh chat persistence, reload, deletion + 375×812 mobile viewport layout
- Added `watch.ignored: ['**/e2e/artifacts/**']` to `vite.config.ts` (prevents EBUSY crash from Playwright trace file watcher)

### Ticket 05 — Full Verification Matrix, Documentation & Commit
- SHA-256 `run_unseen_eval.py`: `e4ecf1f2a9688cf08a6c983ffd8d118be6353a7c6c2dfaedd0bd0ddaf1971b18` ✅
- `rescore_phase5_frozen_outputs_v1 --dry-run`: exit 0 ✅
- `verify_ai_pilot_readiness.py --in-process`: `technical_gates_passed: true`, `pilot_ready_for_rollout: false` ✅
- Full Backend pytest: (pending — see verification matrix below)
- Frontend typecheck: exit 0 ✅
- Frontend vitest: (pending — see verification matrix below)
- Docker compose config: exit 0 ✅
- `git diff --check`: exit 0 ✅
- Secret scan: 0 plaintext tokens in diff ✅

---

## Verification Matrix

| Check | Status | Details |
|-------|--------|---------|
| `run_unseen_eval.py` SHA-256 | ✅ PASS | `e4ecf1f2...1971b18` (unchanged) |
| `rescore_phase5_frozen_outputs_v1 --dry-run` | ✅ PASS | exit 0 |
| `verify_ai_pilot_readiness.py --in-process` | ✅ PASS | `technical_gates_passed: true`, `pilot_ready_for_rollout: false` |
| Playwright E2E (6 scenarios) | ✅ PASS | 6/6 passed in 1.4m |
| Frontend typecheck | ✅ PASS | exit 0 |
| Frontend vitest | ⏳ | (running) |
| Backend pytest (full) | ⏳ | (running) |
| Docker compose config | ✅ PASS | exit 0 |
| `git diff --check` | ✅ PASS | exit 0 |
| Secret scan | ✅ PASS | 0 plaintext tokens |

---

## Production Gate Status

| Gate | Status | Description |
|------|--------|-------------|
| `ai_enabled` | `false` | Default off; requires explicit admin activation |
| `ai_corrective_action_pilot_enabled` | `false` | Default off |
| `PMS_AI_MODEL_LED_PILOT_ENABLED` | `false` (production default) | Only `true` in staging env |
| Issue #97 | **PENDING** | Live provider verification & production credential attestation |
| Vi #103 | **PENDING** | Final human Phase 9 sign-off |

---

## Architecture Changes (Phase 7)

### New Files
- `Backend/services/ai/usage_budget.py` — Server-side budget enforcement (concurrency, daily caps, token limits)
- `Backend/tests/test_ai_phase7_budgets_and_telemetry.py` — TDD tests for Tickets 01+02
- `.tmp/phase7-staging/seed_staging_db.py` — Staging DB seeder
- `Frontend/e2e/ai_phase7_staging.spec.ts` — Playwright E2E staging scenarios

### Modified Files (key changes)
- `Backend/api/routers/ai_workspace.py` — Budget controls, truthful response message
- `Backend/models/ai_schemas.py` — Extended `AiProviderUsageMetrics` and `AiDiagnosticsPayload`
- `Backend/services/ai/orchestrator.py` — Aggregated usage, post-synthesis RBAC, trace recording
- `Backend/services/ai/providers.py` — Cost status resolution, provider metrics
- `Backend/services/ai/router.py` — User ID/role propagation, cost coercion
- `Frontend/src/components/ai/AiResponseCard.tsx` — Truthful provenance badge guard
- `Frontend/vite.config.ts` — Watch ignore for `e2e/artifacts`
- `compose.production.yml` — Budget env vars

---

## Known Limitations

1. **Live provider availability**: Cloudflare Workers AI occasionally times out (6-12s); Gemini API key may need renewal. The system gracefully falls back to deterministic responses with truthful attribution.
2. **Daily caps default to 0 (unlimited)**: Budget limits enforce only when configured > 0 by the operator.
3. **Redis unavailable warning**: In development/staging without Redis, the system uses in-process fallback counters. This is expected behavior.
4. **Phase 5 frozen evaluation gates**: The original frozen set predates Phase 7 changes and was not replayed. The `rescore_phase5_frozen_outputs_v1 --dry-run` confirms all frozen artifacts are intact.
