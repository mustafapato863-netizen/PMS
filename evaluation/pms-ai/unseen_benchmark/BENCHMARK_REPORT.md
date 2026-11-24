# PMS AI Unseen Benchmark Report

- **Generated At:** `2026-11-24T14:19:15.269347+00:00`
- **Benchmark SHA-256:** `925b95b6954bc2cac5b34591b6cd1723d5bba0010dead2da8ed63ce87ee4f1a7`
- **Split Filter:** `all`

## Mode: `deterministic` (`is_live_verified=False`)

| Split | Scenarios | Whole-Turn Acc % | Per-Part Acc % | Decision Acc % | Needless Clarif % | Critical Errors | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| `dev` | 120/120 | 100.0% | 100.0% | 100.0% | 0.0% | 0 | 69.7 | 105.38 |
| `val` | 60/60 | 100.0% | 100.0% | 100.0% | 0.0% | 0 | 69.31 | 109.43 |
| `blind` | 53/60 | 90.0% | 95.0% | 98.57% | 0.0% | 0 | 67.36 | 104.02 |

- **Corrective Action Sub-Suite:** `4/4` passed

## Mode: `scripted_mocked` (`is_live_verified=False`)

| Split | Scenarios | Whole-Turn Acc % | Per-Part Acc % | Decision Acc % | Needless Clarif % | Critical Errors | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| `dev` | 120/120 | 100.0% | 100.0% | 100.0% | 0.0% | 0 | 77.91 | 128.38 |
| `val` | 60/60 | 100.0% | 100.0% | 100.0% | 0.0% | 0 | 79.7 | 109.49 |
| `blind` | 53/60 | 90.0% | 95.0% | 98.57% | 0.0% | 0 | 80.34 | 102.77 |

- **Corrective Action Sub-Suite:** `4/4` passed

## Mode: `live` (`is_live_verified=False`)

> Blocked: `PMS_AI_RUN_LIVE_MODEL_TESTS is not set to 'true'; live benchmark execution skipped.`

## Release Scorecard Summary

- **Scorecard Split:** `blind` · **Offline Gates Passed:** `True`
  - `whole_turn_gte_90`: `True`
  - `per_part_gte_95`: `True`
  - `needless_clarification_lt_3`: `True`
  - `critical_errors_zero`: `True`
  - `p95_under_15000ms`: `True`
  - `corrective_subsuite_all_passed`: `True`
