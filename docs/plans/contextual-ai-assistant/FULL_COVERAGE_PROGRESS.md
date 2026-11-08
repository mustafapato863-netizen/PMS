# PMS AI Full Coverage — Persistent Execution Progress

**Plan Baseline:** `docs/plans/contextual-ai-assistant/FULL_COVERAGE_EXECUTION_PLAN.md`  
**Candidate Commit Baseline:** `b470ef6f35badb185e090a3fb0686a570722ff7c` (plus uncommitted assistant work)  
**Local Model Runtime:** `D:/PMS_AI/models/Qwen3-4B-Q4_K_M.gguf` (`2,497,280,256` bytes) served on `127.0.0.1:18080` (`llama-server.exe -c 2048 -ngl 0 -t 8 -tb 12 --reasoning-budget 0`)

---

## Phase 0 — Freeze and Reproduce (`COMPLETE - PASS`)

- **Frozen Prior Review Output**: Preserved `D:/PMS_AI/local_explorer_review_sample.json` (`0/10` passed, median `11.3s`) to `docs/plans/contextual-ai-assistant/phase0_prior_review_sample_frozen.json` and `D:/PMS_AI/local_explorer_review_sample_frozen_baseline.json`.
- **Reproduced Baseline**: Executed `tmp/review_local_explorer.py` logic against the initial working tree and saved `docs/plans/contextual-ai-assistant/phase0_reproduction_results.json` (`0/10` passed).
- **Root Causes Identified and Resolved**:
  1. `build_exploration_step_json_schema()` previously exposed only `{action, unknown_code, tool}` without structured tool arguments (`team`, `period`, `metric`, `branch`, `compare_branch`, `direction`, `performance_level`, `position`).
  2. `_validate_and_normalize_tool_call()` did not bind explicit prompt entities (`team`, `country`, `position`, `metric`, `period`, `branch`) ahead of `session_state` defaults (`session_state.team=None, function='Call Center'`).
  3. `compare_branches` for `"Inbound bookings"` reported branch overall score percentages (`71.2% vs 59.2%`) instead of booking counts (`Dubai 180`, `Sharjah 70`).
  4. Compound questions (`id=41, 42, 43`) stopped after `inspect_authorized_concepts` + 1 tool call, and `_synthesize_explored_evidence` included empty discovery digests in multi-part synthesis.
  5. Ambiguous comparison without context (`id=46`: `"Which one is doing better?"`) executed `get_executive_and_priority_insights` instead of returning `outcome="clarification"`.

---

## Phase 1 — Build the Authoritative Inventory and Catalog (`COMPLETE - PASS`)

- **Database & Config Snapshot**: Saved `docs/plans/contextual-ai-assistant/phase1_db_inventory_snapshot.json` and generated `docs/plans/contextual-ai-assistant/coverage_manifest_v1.json` via `Backend/services/ai/coverage_manifest.py`:
  - `38` total `Team` rows (`32` active, `6` inactive).
  - `5,671 / 5,671` `kpi_values` rows joined cleanly by `(record_id, record_year)` (`0` orphans).
  - **Egypt Denominator (`12` cells)**:
    - `10` Egypt Employee teams (`Inbound`, `Outbound`, `Support Positions`, `Coding EGY`, `Submission EGY`, `Resubmission`, `Pre-Approvals IP`, `Pre-Approvals IP Offshore`, `Marketing`, `Human Resources`, `IT`, `Offshore Admin & Management` — with `Pre-Approvals IP Offshore` tracked as `verified_no_data` in local DB and evaluated against synthetic fixture).
    - `1` Egypt Managerial team (`Pre-Approvals IP`, position `Pre-Authorization Supervisor`).
    - `1` Egypt Corporate BSC team (`Marketing`).
  - **UAE Denominator (`17` cells)**:
    - `11` UAE Employee teams (`Sales`, `CSR`, `Pharmacy`, `Coding`, `Submission`, `Re-Submission`, `Pre-Approvals OP Dubai`, `Pre-Approvals OP Final SHJAJM`, `Pre-Approvals IP Final Dubai`, `Pre-Approvals IP Final SHJAJM`, `Pre-Approvals IP Elective Dubai`).
    - `6` UAE Corporate BSC teams (`CRM`, `Finance`, `Nursing`, `PMO`, `Pharmacy`, `RCM`).
  - **Shared Denominator (`2` cells, `region="All"`)**:
    - `Finance` (`31` records across 7 positions) and `RCM` (`18` records across 3 positions).
- **Country-Aware Disambiguation**: Updated `Backend/services/ai/catalog.py`, `Backend/services/ai/router.py`, `Backend/services/ai/domain_policies.py`, and `Backend/utils/report_scope.py` so country-paired teams (`Coding` vs `Coding EGY`, `Submission` vs `Submission EGY`, `Re-Submission` vs `Resubmission`, `Pre-Approvals IP` vs `Pre-Approvals IP Offshore` vs UAE Pre-Approvals subteams) never merge silently.

---

## Phase 2 — Enforce Permissions and Scoped Reads (`COMPLETE - PASS`)

- Enforced country (`EGY`, `UAE`, and shared `All`), function, team, subteam, branch, performance level (`Employee`, `Managerial`, `Corporate`), position, and self-only employee restrictions across:
  - Catalog discovery (`find_concepts`, `inspect_authorized_concepts`, `describe_metric`, `list_available_periods`)
  - Tool argument validation and record filtering (`filter_records_by_scope`, `user_can_access_team`, `user_can_access_team_level`, `user_can_access_branch`)
  - Source links (`build_verified_deep_link`)
  - Evidence cache keys and conversation replay (`canonical_scope_identity`)
- Verified mid-turn scope revocation and role matrix in `Backend/tests/test_ai_full_coverage_egy_uae.py`.

---

## Phase 3 — Implement Canonical Analytics across Data Waves A, B, C, D (`COMPLETE - PASS`)

- **Wave A (Operational EGY & UAE)**: `Inbound`, `Outbound`, `Support Positions`, `Sales`, `CSR`, `Pharmacy`, including branch volume vs score comparison (`Dubai 180` vs `Sharjah 70` bookings) and position-profile KPIs.
- **Wave B (RCM EGY & UAE)**: `Coding EGY`, `Submission EGY`, `Resubmission`, `Pre-Approvals IP`, `Pre-Approvals IP Offshore` (including the June 2026 Controllable vs Policy Rejection basis transition), `Coding`, `Submission`, `Re-Submission`, and all 5 UAE Pre-Approvals teams (`OP Dubai`, `OP Sharjah`, `IP Final Dubai`, `IP Sharjah`, `IP Elective Dubai`).
- **Wave C (Other & Shared)**: `Marketing`, `Human Resources`, `IT`, `Offshore Admin & Management`, shared `Finance` and `RCM` (`region="All"`), and explicit `no_data` handling for active teams with 0 published rows in a requested period.
- **Wave D (Managerial & Corporate BSC)**: `Pre-Approvals IP` Managerial scorecard (`DashboardRecordService`) and Corporate BSC (`CRM`, `Finance`, `Marketing`, `Nursing`, `PMO`, `Pharmacy`, `RCM` via `ManagementBSCService` and `corporate_bsc_catalog_data.py`).

---

## Phase 4 — Make Qwen Own Exploration and Answer Composition (`COMPLETE - PASS`)

- Exposed a production-shaped tool contract in `Backend/services/ai/local_data_explorer.py` (`build_exploration_step_json_schema`, `_parse_and_validate_step_payload`) where unit tests and live Qwen use the exact same JSON schema and parser.
- Supports up to 3 model decisions + 1 synthesis call and up to 4 logical reads per turn.
- Implemented `build_fact_ledger_from_evidence` and `validate_qwen_grounded_synthesis` so Qwen composes short English answers grounded in `fact_id` citations, rejecting any invented numbers or conflicting entities before display.
- Tracked `planner_provider`, `synthesis_provider`, `validation_outcome`, and `fallback_reason` separately in `AiProviderUsageSummary`.
- Verified `10/10` (`100%`) on `tmp/review_local_explorer.py` with live Qwen3-4B (`median 5.67s`, down from `11.3s`), saved in `docs/plans/contextual-ai-assistant/phase4_review_local_explorer_after.json` and `D:/PMS_AI/local_explorer_review_sample.json`.

---

## Phase 5 — Connect the Shared Assistant and Governed Workflows (`COMPLETE - PASS`)

- Connected the shared contextual assistant across PMS AI Workspace, Monthly Review, Team Dashboard, Executive/Function Summary, Employee Profile, and BSC views (`Backend/services/ai/contextual_assistant.py`, `src/components/ai/ContextualAssistantDrawer.tsx`).
- Verified multi-turn scope switching, fallback-data refusal (`fallback_active=True`), and governed corrective-action proposal + confirmation (`confirm_corrective_action_proposal` requiring explicit confirmation and authorization).

---

## Phase 6 — Independent Verification, Performance & Capacity (`COMPLETE - PASS`)

- **50-Case Golden Suite (`D:/PMS_AI/pms_ai_golden_50.py`)**:
  - Router path: **`50 / 50` (`100.0%`)**
  - Live Qwen3-4B exploration path (`PMS_AI_LOCAL_EXPLORATION_ENABLED=true`): **`50 / 50` (`100.0%`)**
  - Compound latency: `p50 = 8.08s`, `p95 = 8.41s` (meets `<= 16.0s` gate).
- **122-Turn Multi-Country Held-Out Suite (`Backend/services/ai/evaluate_full_coverage_holdout.py`)**:
  - **Egypt (`EGY`)**: **`61 / 61` (`100.0%`)** (`current_value: 11/11`, `kpi_diagnosis: 10/10`, `ranking: 10/10`, `compare_branches_or_periods: 10/10`, `trend: 10/10`, `compound: 10/10`).
  - **UAE (`UAE`)**: **`61 / 61` (`100.0%`)** (`current_value: 11/11`, `kpi_diagnosis: 10/10`, `ranking: 10/10`, `compare_branches_or_periods: 10/10`, `trend: 10/10`, `compound: 10/10`).
  - **16-Turn Live Qwen Multi-Country Slice (including Qwen-authored grounded synthesis)**: **`16 / 16` (`100.0%`)**.
- **200-Employee Scoped DB Read Capacity**:
  - `p50 = 44.13 ms`, `p95 = 62.91 ms` (meets `<= 500 ms` gate).
- **Automated Pytest Suite**:
  - `tests/test_ai_workspace.py`, `tests/test_local_assistant_exploration.py`, `tests/test_ai_full_coverage_egy_uae.py`: **`33 passed, 1 skipped`**.

---

## Phase 7 & Phase 8 — Staging/Release Manifest & Ongoing Coverage Governance (`COMPLETE - PASS`)

- Published release report and rollback manifest in `docs/plans/contextual-ai-assistant/FULL_COVERAGE_RELEASE_REPORT.md`.
- Machine-readable coverage manifest locked in `docs/plans/contextual-ai-assistant/coverage_manifest_v1.json` and enforced by `tests/test_ai_full_coverage_egy_uae.py`.
