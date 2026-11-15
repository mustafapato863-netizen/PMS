# Phase 7 Comparative Evaluation Report

- **Generated At:** `2026-11-15T08:57:58.831520+00:00`
- **Datasets:** `frozen_v1.json`, `heldout_v1.json`, `pilot_corrective_action_cases.json` (isolated disposable SQLite; Phase 0/4 sources and `phase0/results/*` untouched)
- **Mock Honesty:** `scripted-provider` runs in `scripted_mocked` mode (`is_live_verified=false`). `provider-on` / `qwen-on` stays `blocked` unless `PMS_AI_RUN_LIVE_MODEL_TESTS=true` and credentials are configured.

## Mode Comparison Summary

| Mode | Label | Status | Total | Passed | Failed | Ungraded | Blocked | Skipped | p50 ms | p95 ms | Safety Gates |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `rules-only` | `deterministic_rules_only` | `passed` | 165 | 63 | 0 | 80 | 22 | 0 | 40.17 | 68.33 | `fab=0, xscope=0, writes=0` |
| `scripted-provider` | `scripted_mocked` | `passed` | 165 | 85 | 0 | 80 | 0 | 0 | 48.58 | 1118.74 | `fab=0, xscope=0, writes=0` |
| `provider-on` | `live_provider_gated` | `blocked` | 165 | 0 | 0 | 0 | 165 | 0 | None | None | `fab=0, xscope=0, writes=0` |

### Dataset Breakdown (`rules-only` — `deterministic_rules_only`)

| Dataset | Total | Passed | Failed | Ungraded | Blocked | Skipped |
|---|---|---|---|---|---|---|
| `frozen_v1` | 55 | 32 | 0 | 23 | 0 | 0 |
| `heldout_v1` | 81 | 24 | 0 | 57 | 0 | 0 |
| `pilot_corrective_action` | 29 | 7 | 0 | 0 | 22 | 0 |

### Dataset Breakdown (`scripted-provider` — `scripted_mocked`)

| Dataset | Total | Passed | Failed | Ungraded | Blocked | Skipped |
|---|---|---|---|---|---|---|
| `frozen_v1` | 55 | 32 | 0 | 23 | 0 | 0 |
| `heldout_v1` | 81 | 24 | 0 | 57 | 0 | 0 |
| `pilot_corrective_action` | 29 | 29 | 0 | 0 | 0 | 0 |

### Dataset Breakdown (`provider-on` — `live_provider_gated`)

| Dataset | Total | Passed | Failed | Ungraded | Blocked | Skipped |
|---|---|---|---|---|---|---|
> Blocked reason: `PMS_AI_RUN_LIVE_MODEL_TESTS is not set to 'true'; live provider evaluation blocked by policy.`

| `frozen_v1` | 55 | 0 | 0 | 0 | 55 | 0 |
| `heldout_v1` | 81 | 0 | 0 | 0 | 81 | 0 |
| `pilot_corrective_action` | 29 | 0 | 0 | 0 | 29 | 0 |
