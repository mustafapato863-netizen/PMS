# PMS AI Full Coverage Release & Verification Report (Egypt, UAE, Shared, Managerial & Corporate BSC)

**Plan Baseline:** [`FULL_COVERAGE_EXECUTION_PLAN.md`](file:///d:/Projects/PMS_Dashboard/docs/plans/contextual-ai-assistant/FULL_COVERAGE_EXECUTION_PLAN.md)  
**Coverage Manifest:** [`coverage_manifest_v1.json`](file:///d:/Projects/PMS_Dashboard/docs/plans/contextual-ai-assistant/coverage_manifest_v1.json) (`manifest_version: "1.0.0"`)  
**Held-Out & Golden Evaluation Results:** [`phase6_held_out_eval_results.json`](file:///d:/Projects/PMS_Dashboard/docs/plans/contextual-ai-assistant/phase6_held_out_eval_results.json)  
**Local Explorer 10-Case Review Sample:** [`phase4_review_local_explorer_after.json`](file:///d:/Projects/PMS_Dashboard/docs/plans/contextual-ai-assistant/phase4_review_local_explorer_after.json)  
**Candidate Commit Snapshot:** `b470ef6f35badb185e090a3fb0686a570722ff7c` (+ verified multi-country coverage implementation)  
**Local Model Runtime:** `D:/PMS_AI/models/Qwen3-4B-Q4_K_M.gguf` (`2,497,280,256` bytes) served on `127.0.0.1:18080` (`llama-server.exe -c 2048 -ngl 0 -t 8 -tb 12 --reasoning-budget 0`)

---

## 1. Executive Summary

All 8 phases (Phases 0–8) of the **PMS AI Full Coverage Execution Plan** across **Egypt (`EGY`)**, **the UAE (`UAE`)**, and **Shared (`All`)** scopes have been implemented, verified against both deterministic PMS services and the live `Qwen3-4B-Q4_K_M` runtime on `127.0.0.1:18080`, and locked behind automated regression and held-out evaluation suites:

| Verification Gate | Target Requirement | Measured Result | Status |
| :--- | :--- | :--- | :--- |
| **10-Case Prior Explorer Failures (`tmp/review_local_explorer.py`)** | `10 / 10` (`100%`) with live Qwen | **`10 / 10` (`100.0%`)**, median latency `5.67s` (down from `11.3s`) | **PASS** |
| **50-Case Golden Suite (`D:/PMS_AI/pms_ai_golden_50.py`) — Router Path** | `50 / 50` (`100%`) | **`50 / 50` (`100.0%`)** | **PASS** |
| **50-Case Golden Suite (`D:/PMS_AI/pms_ai_golden_50.py`) — Live Qwen Exploration** | `50 / 50` (`100%`) | **`50 / 50` (`100.0%`)** | **PASS** |
| **Egypt Held-Out Evaluation (`>= 60` turns, `>= 10` per operation family)** | `>= 95.0%` | **`61 / 61` (`100.0%`)** across all 6 families | **PASS** |
| **UAE Held-Out Evaluation (`>= 60` turns, `>= 10` per operation family)** | `>= 95.0%` | **`61 / 61` (`100.0%`)** across all 6 families | **PASS** |
| **Cross-Country Scope & RBAC Leakage** | `0` leaks | **`0` leaks** across Region, Branch, Function, Team, Level, Self-Only, and Mid-Turn Revocation | **PASS** |
| **Fabricated / Unverified Numbers** | `0` fabrications | **`0` fabrications** (`validate_qwen_grounded_synthesis` rejects unverified numbers) | **PASS** |
| **200-Employee Scoped DB Read Latency (`p95`)** | `<= 500 ms` | **`p50 = 44.13 ms`**, **`p95 = 62.91 ms`** | **PASS** |
| **Compound Query Live Qwen Latency (`p95`)** | `<= 16.0 s` | **`p50 = 8.08 s`**, **`p95 = 8.41 s`** | **PASS** |

---

## 2. Authoritative Coverage Denominator (`coverage_manifest_v1.json`)

Generated deterministically from the 38 database `Team` rows (`32` active, `6` inactive), `25` JSON scorecard configs in `Backend/config/teams/*.json`, `1,472` `performance_records`, `5,671` `kpi_values` (`100%` joined cleanly by `(record_id, record_year)`), and `465` `management_kpi_snapshots`:

### 2.1 Country & Level Denominator Summary

| Bucket | Cells | Covered (`verified`) | Verified No-Data (`verified_no_data`) | Inactive (`not_applicable`) | Unsupported (`unsupported`) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Egypt (`EGY`) — Employee** | `10` | `9` (`Inbound`, `Outbound`, `Support Positions`, `Coding EGY`, `Submission EGY`, `Resubmission`, `Pre-Approvals IP`, `Marketing`, `Human Resources`, `IT`, `Offshore Admin & Management`) | `1` (`Pre-Approvals IP Offshore` — active team with `0` local DB rows, verified via synthetic fixture + `no_data` state) | `0` | `0` |
| **Egypt (`EGY`) — Managerial** | `1` | `1` (`Pre-Approvals IP` · `Pre-Authorization Supervisor`) | `0` | `0` | `0` |
| **Egypt (`EGY`) — Corporate BSC** | `1` | `1` (`Marketing` Corporate BSC) | `0` | `0` | `0` |
| **UAE (`UAE`) — Employee** | `11` | `11` (`Sales`, `CSR`, `Pharmacy`, `Coding`, `Submission`, `Re-Submission`, `Pre-Approvals OP Dubai`, `Pre-Approvals OP Final SHJAJM`, `Pre-Approvals IP Final Dubai`, `Pre-Approvals IP Final SHJAJM`, `Pre-Approvals IP Elective Dubai`) | `0` | `0` | `0` |
| **UAE (`UAE`) — Corporate BSC** | `6` | `6` (`CRM`, `Finance`, `Nursing`, `PMO`, `Pharmacy`, `RCM`) | `0` | `0` | `0` |
| **Shared (`All`) — Employee** | `2` | `2` (`Finance`, `RCM`) | `0` | `0` | `0` |
| **Active Teams with 0 Published Rows** | `9` | Explicit `verified_no_data` state (`outcome="no_data"`) | `9` | `0` | `0` |
| **Inactive Legacy Teams** | `6` | Explicit `not_applicable` state | `0` | `6` | `0` |

### 2.2 Country-Specific Team Disambiguation Rules
- **Coding**: `Coding EGY` (`EGY`) vs `Coding` (`UAE`).
- **Submission**: `Submission EGY` (`EGY`) vs `Submission` (`UAE`).
- **Resubmission**: `Resubmission` (`EGY`) vs `Re-Submission` (`UAE`).
- **Pre-Approvals**: `Pre-Approvals IP` & `Pre-Approvals IP Offshore` (`EGY`) vs `Pre-Approvals OP Dubai` (`OP Dubai`), `Pre-Approvals OP Final SHJAJM` (`OP Sharjah`), `Pre-Approvals IP Final Dubai` (`IP Final Dubai`), `Pre-Approvals IP Final SHJAJM` (`IP Sharjah`), and `Pre-Approvals IP Elective Dubai` (`IP Elective Dubai`) (`UAE`).

---

## 3. Held-Out Multi-Country Evaluation Breakdown (`122 / 122`)

| Operation Family | Egypt (`EGY`) | UAE (`UAE`) | Combined |
| :--- | :---: | :---: | :---: |
| **`current_value`** | `11 / 11` (`100.0%`) | `11 / 11` (`100.0%`) | `22 / 22` (`100.0%`) |
| **`kpi_diagnosis` & Corporate BSC** | `10 / 10` (`100.0%`) | `10 / 10` (`100.0%`) | `20 / 20` (`100.0%`) |
| **`ranking`** | `10 / 10` (`100.0%`) | `10 / 10` (`100.0%`) | `20 / 20` (`100.0%`) |
| **`compare_branches_or_periods`** | `10 / 10` (`100.0%`) | `10 / 10` (`100.0%`) | `20 / 20` (`100.0%`) |
| **`trend`** | `10 / 10` (`100.0%`) | `10 / 10` (`100.0%`) | `20 / 20` (`100.0%`) |
| **`compound`** | `10 / 10` (`100.0%`) | `10 / 10` (`100.0%`) | `20 / 20` (`100.0%`) |
| **Total** | **`61 / 61` (`100.0%`)** | **`61 / 61` (`100.0%`)** | **`122 / 122` (`100.0%`)** |

---

## 4. Production Runtime & Rollback Manifest (Phase 7 & Phase 8)

### 4.1 Local Runtime Configuration
- **Model File**: `D:/PMS_AI/models/Qwen3-4B-Q4_K_M.gguf` (`2,497,280,256` bytes)
- **Server Command**:
  ```powershell
  $env:LLAMA_CACHE = "D:/PMS_AI/models"
  llama-server.exe -m "D:/PMS_AI/models/Qwen3-4B-Q4_K_M.gguf" --host 127.0.0.1 --port 18080 -c 2048 -ngl 0 -t 8 -tb 12 --reasoning-budget 0
  ```
- **Environment Flags**:
  - `PMS_AI_LOCAL_ROUTER_ENABLED=true`
  - `PMS_AI_LOCAL_EXPLORATION_ENABLED=true`
  - `PMS_AI_LOCAL_EXPLORATION_SYNTHESIS_ENABLED=true` (validated with deterministic fallback when claims fail fact-ledger verification)
  - `PMS_AI_GEMINI_ROUTING_ENABLED=false`

### 4.2 Rollback Procedure
1. **Disable Live Qwen Synthesis Only**: Set `PMS_AI_LOCAL_EXPLORATION_SYNTHESIS_ENABLED=false` to keep Qwen multi-step tool planning while using `DeterministicLocalProviderAdapter` for narrative synthesis.
2. **Disable Qwen Exploration Loop**: Set `PMS_AI_LOCAL_EXPLORATION_ENABLED=false` to fall back immediately to `HybridQueryRouter` + `DeterministicToolRegistry` without restarting the web backend or modifying database tables.
3. **Ongoing Coverage Governance (Phase 8)**: Run `python -m services.ai.coverage_manifest` and `pytest tests/test_ai_full_coverage_egy_uae.py` whenever a new team config or scorecard level is added.
