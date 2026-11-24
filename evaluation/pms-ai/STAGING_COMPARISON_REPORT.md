# PMS AI Staging Candidate Comparison & Section 5 Release Scorecard

- **Generated At:** `2026-11-24T14:20:10.723405+00:00`
- **Total Scenarios:** `240` (dev=120, val=60, blind=60)

## Comparison Matrix

| Arm | Status | Live Verified | Overall Acc % | Per-Part % | Blind Whole % | Blind Per-Part % | Needless Clarif % | Critical Err | p95 ms | Billing / Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| `legacy_rules_flags_off` | `completed` | `False` | 65.88% | 76.81% | 42.86% | 61.11% | 0.0% | 5 | 109.86 | `not_applicable_deterministic` |
| `improved_app_flags_on` | `completed` | `False` | 97.25% | 98.41% | 90.0% | 95.0% | 0.0% | 0 | 114.0 | `not_applicable_deterministic_and_mocked` |
| `forced_timeout_fallback` | `completed` | `False` | 97.25% | 98.41% | 90.0% | 95.0% | 0.0% | 0 | 128.85 | `unavailable_offline_timeout_simulation` |
| `staging_live_candidate` | `blocked` | `False` | n/a | n/a | n/a | n/a | n/a | n/a | n/a | `unavailable_live_execution_blocked` |

## Section 5 Release Scorecard (Offline + Blind Verified)

- **Blind Whole-Turn Accuracy:** `90.0%` (Gate >= 90%)
- **Blind Per-Part Accuracy:** `95.0%` (Gate >= 95%)
- **Blind Needless Clarifications:** `0.0%` (Gate < 3%)
- **Blind Critical Errors:** `0` (Gate == 0)
- **Blind p95 Latency:** `90.83 ms` (Gate <= 15000 ms)
- **Overall Improvement vs Legacy Flags Off:** `+31.37 pp`
- **Corrective 1-Retry Repair Recovery:** `True`
- **Forced Timeout Safe Fallback Verified:** `True`
- **Live Staging Status:** `blocked`
- **All Offline Scorecard Gates Passed:** `True`

## Reversible Rollout Flags

| Flag | Effective Default | Instant Revert |
|---|---|---|
| `PMS_AI_COMPOUND_PARTS_ENABLED` | `True` (default `True`) | `export PMS_AI_COMPOUND_PARTS_ENABLED=false` |
| `PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED` | `True` (default `True`) | `export PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED=false` |
| `PMS_AI_MODEL_LED_PILOT_ENABLED` | `True` (default `False`) | `export PMS_AI_MODEL_LED_PILOT_ENABLED=false` |
| `PMS_AI_NVIDIA_ROUTING_ENABLED` | `False` (default `False`) | `export PMS_AI_NVIDIA_ROUTING_ENABLED=false` |
