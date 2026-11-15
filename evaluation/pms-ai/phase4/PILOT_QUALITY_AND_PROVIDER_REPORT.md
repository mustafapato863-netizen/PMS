# Phase 4 Pilot Quality & Provider Evaluation Report

- **Dataset:** `evaluation/pms-ai/phase4/pilot_corrective_action_cases.json`
- **Execution Mode:** `scripted_unified_engine` (isolated in-memory SQLite; zero production data, zero live external calls by default)
- **Total Cases:** `29`
- **Graded Denominator:** `29` (`passed=29`, `failed=0`)
- **Non-Graded Counts:** `ungraded=0`, `blocked=0`, `skipped=0`
- **DB Mutations Observed:** `0`
- **Outbound PII Leaks Observed:** `0`

## Rubric Dimension Summary

| Dimension | Passed / Graded | Rate |
|---|---|---|
| `factual_support` | 29 / 29 | 100.0% |
| `focus_kpi_relevance` | 29 / 29 | 100.0% |
| `evidence_appropriateness` | 29 / 29 | 100.0% |
| `actionable_specificity` | 29 / 29 | 100.0% |
| `uncertainty_non_causal_framing` | 29 / 29 | 100.0% |
| `non_disciplinary_compliance` | 29 / 29 | 100.0% |
| `hitl_zero_pii_safety` | 29 / 29 | 100.0% |

## Case-by-Case Results

| Case | Team | Country | Outcome | Provider | Model Called | Status | Notes |
|---|---|---|---|---|---|---|---|
| `CA-01` | Inbound | EGY | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
| `CA-02` | Inbound | EGY | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
| `CA-03` | Outbound | EGY | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
| `CA-04` | Inbound | EGY | `insufficient_evidence` | `none` | `False` | `passed` | All 7 rubric checks passed |
| `CA-05` | Support Positions | EGY | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
| `CA-06` | Coding | UAE | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
| `CA-07` | Pre-Approvals IP | EGY | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
| `CA-08` | Pre-Approvals OP Dubai | UAE | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
| `CA-09` | Marketing | EGY | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
| `CA-10` | Marketing | EGY | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
| `CA-11` | Pharmacy | UAE | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
| `CA-12` | CSR | UAE | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
| `CA-13` | Inbound | EGY | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
| `CA-14` | Inbound | EGY | `insufficient_evidence` | `none` | `False` | `passed` | All 7 rubric checks passed |
| `CA-15` | Outbound | EGY | `insufficient_evidence` | `none` | `False` | `passed` | All 7 rubric checks passed |
| `CA-16` | Coding | UAE | `insufficient_evidence` | `none` | `False` | `passed` | All 7 rubric checks passed |
| `CA-17` | Inbound | EGY | `insufficient_evidence` | `none` | `False` | `passed` | All 7 rubric checks passed |
| `CA-18` | Pre-Approvals IP | EGY | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
| `CA-19` | CSR | UAE | `insufficient_evidence` | `none` | `False` | `passed` | All 7 rubric checks passed |
| `CA-20` | Inbound | EGY | `insufficient_evidence` | `none` | `False` | `passed` | All 7 rubric checks passed |
| `CA-21` | Inbound | EGY | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
| `CA-22` | Coding | UAE | `suggested` | `gemini` | `True` | `passed` | All 7 rubric checks passed |
| `CA-23` | Outbound | EGY | `suggested` | `gemini` | `True` | `passed` | All 7 rubric checks passed |
| `CA-24` | Pharmacy | UAE | `model_unavailable` | `none` | `True` | `passed` | All 7 rubric checks passed |
| `CA-25` | Inbound | EGY | `model_unavailable` | `none` | `True` | `passed` | All 7 rubric checks passed |
| `CA-26` | Inbound | EGY | `draft_rejected` | `none` | `True` | `passed` | All 7 rubric checks passed |
| `CA-27` | Inbound | EGY | `draft_rejected` | `none` | `True` | `passed` | All 7 rubric checks passed |
| `CA-28` | Inbound | EGY | `draft_rejected` | `none` | `True` | `passed` | All 7 rubric checks passed |
| `CA-29` | Inbound | EGY | `suggested` | `cloudflare` | `True` | `passed` | All 7 rubric checks passed |
