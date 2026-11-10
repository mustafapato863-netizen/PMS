# PMS AI status

## 2026-11-09 — Phase -1 integration (not merged)

Integration branch `cursor/ai-phase-minus-1-integration-dff5` was opened from main `3f1d914549c06affc5f63ea33e034e711738c3bb` and merge-committed PR #80 `0c7fe890054f154010037dcca64b5e7e1eb8390c` and PR #81 `d5e488ab10d697830a86adb5417d1da31c202bb0`. Those PR branches were not modified.

Admin-only pilot is enforced with `require_ai_admin` on every `/api/ai` route, in addition to `require_ai_enabled`. `ai_enabled` stays off for a fresh migration, a missing row, and seed. Compose `llm` remains profile-gated. Intent and synthesis defaults in Compose, env examples, and the Hostinger workflow are false. Exploration stays off when `APP_ENV=production`.

This change is a pull request only. It was not merged and was not pushed to main.

## 2026-11-10 — Phase 2 coverage manifest (draft, not merged)

Regenerated on main `fabbb3d461c044bd367e6cc38a9c514fcfe300d2`. Generator: `evaluation/pms-ai/phase2/generate_coverage_manifest.py`. Outputs: `coverage_manifest.json` (version 2.0.0), `coverage_matrix.csv`, `coverage_report.md`. No database read, no network, no employee rows, AI left off.

Catalog counts: 3 countries, 14 functions, 28 teams, 55 positions, 56 position/level pairs, 3 levels, 402 KPIs (35 not in score). Matrix: 784 cells — verified 0, verified no data 0, partial 14, blocked 190, not applicable 35, unknown 545. Unresolved alias conflicts: 37. Unexplained active entries: 0.

Nothing is verified. Permission checks were not executed and `performance_records` were not read. Source-parity agreement with `DEFAULT_WEIGHTS` is partial only. RCM Egypt and RCM UAE stay separate. CRM, Nursing, and PMO are corporate-catalog-only. Published months, `teams.is_active`, and live KPI rows are not in the repo.
