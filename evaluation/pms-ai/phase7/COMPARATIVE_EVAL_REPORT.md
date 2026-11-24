# Phase 7 Comparative Evaluation Report

- **Generated At:** `2026-11-24T14:18:35.699078+00:00`
- **Datasets:** `frozen_v1.json`, `heldout_v1.json`, `pilot_corrective_action_cases.json` (isolated disposable SQLite; Phase 0/4 sources and `phase0/results/*` untouched)
- **Mock Honesty:** `scripted-provider` runs in `scripted_mocked` mode (`is_live_verified=false`). `provider-on` / `qwen-on` stays `blocked` unless `PMS_AI_RUN_LIVE_MODEL_TESTS=true` and credentials are configured.

## Mode Comparison Summary

| Mode | Label | Status | Total | Passed | Failed | Ungraded | Blocked | Skipped | p50 ms | p95 ms | Safety Gates |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `rules-only` | `deterministic_rules_only` | `passed` | 165 | 70 | 0 | 73 | 22 | 0 | 69.94 | 139.27 | `fab=0, xscope=0, writes=0` |
| `scripted-provider` | `scripted_mocked` | `passed` | 165 | 94 | 0 | 71 | 0 | 0 | 105.78 | 1298.28 | `fab=0, xscope=0, writes=0` |
| `provider-on` | `live_provider_gated` | `blocked` | 165 | 0 | 0 | 0 | 165 | 0 | None | None | `fab=0, xscope=0, writes=0` |

### Dataset Breakdown (`rules-only` — `deterministic_rules_only`)

| Dataset | Total | Passed | Failed | Ungraded | Blocked | Skipped |
|---|---|---|---|---|---|---|
| `frozen_v1` | 55 | 37 | 0 | 18 | 0 | 0 |
| `heldout_v1` | 81 | 26 | 0 | 55 | 0 | 0 |
| `pilot_corrective_action` | 29 | 7 | 0 | 0 | 22 | 0 |

#### Denominator Audit & Ungraded Reasons (`rules-only`)

- Total: `165` · Graded: `70` · Ungraded: `73` · Blocked: `22`

| Ungraded Reason | Count |
|---|---|
| `behaviour_outcome_ungraded:answer:unsupported_request` | 1 |
| `behaviour_outcome_ungraded:clarify:unsupported_request` | 2 |
| `missing_navigation_parts_oracle` | 2 |
| `pending_score_oracle_empty_db` | 59 |
| `unobservable_binding_in_empty_db` | 9 |

### Dataset Breakdown (`scripted-provider` — `scripted_mocked`)

| Dataset | Total | Passed | Failed | Ungraded | Blocked | Skipped |
|---|---|---|---|---|---|---|
| `frozen_v1` | 55 | 37 | 0 | 18 | 0 | 0 |
| `heldout_v1` | 81 | 28 | 0 | 53 | 0 | 0 |
| `pilot_corrective_action` | 29 | 29 | 0 | 0 | 0 | 0 |

#### Denominator Audit & Ungraded Reasons (`scripted-provider`)

- Total: `165` · Graded: `94` · Ungraded: `71` · Blocked: `0`

| Ungraded Reason | Count |
|---|---|
| `behaviour_outcome_ungraded:refuse:answer` | 1 |
| `missing_navigation_parts_oracle` | 2 |
| `pending_score_oracle_empty_db` | 59 |
| `unobservable_binding_in_empty_db` | 9 |

### Dataset Breakdown (`provider-on` — `live_provider_gated`)

| Dataset | Total | Passed | Failed | Ungraded | Blocked | Skipped |
|---|---|---|---|---|---|---|
> Blocked reason: `PMS_AI_RUN_LIVE_MODEL_TESTS is not set to 'true'; live provider evaluation blocked by policy.`

| `frozen_v1` | 55 | 0 | 0 | 0 | 55 | 0 |
| `heldout_v1` | 81 | 0 | 0 | 0 | 81 | 0 |
| `pilot_corrective_action` | 29 | 0 | 0 | 0 | 29 | 0 |
