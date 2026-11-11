# Phase 2: Scope & Operation Coverage Matrix

**Document Version:** 1.1
**Date:** 11 November 2026
**Status:** Conservative Verification Audit — reconciled to repository sources in Phase 2 (issue #94)
**Date:** 10 November 2026
**Status:** Conservative Verification Audit
**Scope:** Phase 2 Deliverable for PMS AI Evidence-First Upgrade ([Implementation Plan](file:///D:/Projects/PMS_Dashboard/docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md))

---

## 1. Certification Classification Rules

To prevent unwarranted claims of capability, every cell in this matrix is classified under strict verification criteria. Statuses use the roadmap vocabulary only (`verified`, `verified no data`, `partial`, `blocked`, `not applicable`); the legacy words `partial_evidence`, `unverified`, and `unsupported` are not used. Statuses in sections 2.1–2.2 are the Phase 2 inventory statuses from `evaluation/pms-ai/phase2/coverage_manifest.json`.

| Status Code | Meaning / Criteria | Release Rule |
| :--- | :--- | :--- |
| **`verified`** | Validated against **independent production source ground truth** (owner spreadsheets or verified database parity) **and** a passing permission check. | Eligible for production release. *(Currently 0 cells qualify).* |
| **`partial`** | One repository parity check passed (e.g. team JSON scored keys and weights match `kpi_service.DEFAULT_WEIGHTS`); independent source parity and the permission check are still open. | Requires Phase 3 independent source verification before certification. |
| **`verified no data`** | Scope and calculation verified, but **no published records** exist for the requested period. The system truthfully returns an honest empty state. | Safe behavioral state. *(Currently 0 cells qualify).* |
| **`blocked`** | A source contradiction, a failed parity check, or a check that was not run. `not_checked` means no check failed; the cell is still blocked from certification. | Must be treated as blocked in model responses. |
| **`not applicable`** | The operation is fundamentally invalid for this scope (e.g. a tracking-only measure asked as a score). | Model must return a polite refusal explaining the limitation. |
## 2. Country Ã— Function Ã— Team Ã— Level Ã— Operation Coverage Matrix

### 2.1 Offshore Egypt Operations

| Function | Team / Role | Level | Score / Summary | Actual vs Target | Ranking / Bottom | 6-Month Trend | Branch Comparison | Follow-Up | Page Navigation | Evidence Reference & Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Call Center** | `Inbound` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status); application tests: `test_ai_workspace.py` — score/actual-target blocked: team JSON key `Attendance` does not match `kpi_service.DEFAULT_WEIGHTS` key `Attend` |
| **Call Center** | `Outbound` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status); application tests: `test_ai_workspace.py` — score/actual-target blocked: parity check failed (Outbound basis unselected) |
| **Call Center** | `Support Positions` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status); application tests: `test_ai_workspace.py` — Call Center subteam; channel-rollup basis |
| **Call Center** | `Call Center` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — config team; channel-rollup basis |
| **RCM** | `Coding EGY` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — position-level KPIs only |
| **RCM** | `Submission EGY` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — position-level KPIs only |
| **RCM** | `Resubmission` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — position-level KPIs only |
| **RCM** | `Pre-Approvals IP` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — position-level KPIs only |
| **RCM** | `Pre-Approvals IP Offshore` | Employee | `partial` | `partial` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — score/actual-target partial: one repository parity check passed; permission check not run |
| **Shared** | `Marketing` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — period basis unselected (position period variants) |
| **Shared** | `Human Resources` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — position-level KPIs only |
| **Shared** | `IT` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — position-level KPIs only |
| **Shared** | `Offshore Admin & Management` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — position-level KPIs only |

---
### 2.2 UAE Operations

| Function | Team / Role | Level | Score / Summary | Actual vs Target | Ranking / Bottom | 6-Month Trend | Branch Comparison | Follow-Up | Page Navigation | Evidence Reference & Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **RCM** | `Coding` | Employee | `partial` | `partial` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — score/actual-target partial: one repository parity check passed; permission check not run |
| **RCM** | `Submission` | Employee | `partial` | `partial` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — score/actual-target partial: one repository parity check passed; permission check not run |
| **RCM** | `Re-Submission` | Employee | `partial` | `partial` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — score/actual-target partial: one repository parity check passed; permission check not run |
| **RCM** | `Pre-Approvals OP Dubai` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — position-level KPIs only |
| **RCM** | `Pre-Approvals OP Final SHJAJM` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — position-level KPIs only |
| **RCM** | `Pre-Approvals IP Final Dubai` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — position-level KPIs only |
| **RCM** | `Pre-Approvals IP Final SHJAJM` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — position-level KPIs only |
| **RCM** | `Pre-Approvals IP Elective Dubai` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — position-level KPIs only |
| **Shared** | `Pharmacy` | Employee | `partial` | `partial` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — score/actual-target partial: one repository parity check passed; permission check not run |
| **Shared** | `CSR` | Employee | `partial` | `partial` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — score/actual-target partial: one repository parity check passed; permission check not run |
| **Shared** | `Sales` | Employee | `partial` | `partial` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — score/actual-target partial: one repository parity check passed; permission check not run |

### 2.2a Shared-scope teams (region `All`)

Finance and RCM have config region `All`. They are listed here, not under Egypt or UAE, because their rows must never be folded into a single-country total without an approved attribution rule.

| Function | Team / Role | Level | Score / Summary | Actual vs Target | Ranking / Bottom | 6-Month Trend | Branch Comparison | Follow-Up | Page Navigation | Evidence Reference & Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Shared** | `Finance` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — region `All`; position-level KPIs only; never folded into a single-country total |
| **Shared** | `RCM` | Employee | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Phase 2 manifest `evaluation/pms-ai/phase2/coverage_manifest.json` (inventory status) — region `All`; position-level KPIs only; never folded into a single-country total |

Presentation-only names (no team JSON, so no row above): `Pre-Approvals OP Final` merges `Pre-Approvals OP Dubai` and `Pre-Approvals OP Final SHJAJM`; `Pre-Approvals IP Final` merges `Pre-Approvals IP Final Dubai` and `Pre-Approvals IP Final SHJAJM`; `Pre-Approvals IP Dubai` is a presentation name for `Pre-Approvals IP Final Dubai`. The router asks which source team is meant when one of these names is used without a city qualifier.

---
### 2.3 Managerial & Corporate BSC Operations

| Scope | Function / Area | Level | Score / Summary | Perspective Breakdown | Target vs Actual | 6-Month Trend | Action Proposals | Status & Evidence |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Shared (All)** | `Executive Summary` | Corporate | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Organization-level rollup; source parity pending |
| **Shared (All)** | `Corporate BSC` | Corporate | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | 4 perspectives (Financial, Customer, Process, Learning) mapped in `corporate_bsc_catalog_data.py`; inventory Corporate cells are blocked (permission check not run) |
| **EGY / UAE** | `Department Managers` | Managerial | `blocked` | `blocked` | `blocked` | `blocked` | `blocked` | Scorecards exist in `management_kpi_snapshots`; AI queries are not yet verified |

Corporate BSC-only teams (no team JSON): `CRM`, `Nursing`, and `PMO` exist only in `Backend/services/ai/corporate_bsc_catalog_data.py`. They have Corporate-level scorecards and no Employee rows in sections 2.1–2.2. Their Corporate inventory cells are `blocked` (permission check not run; live `management_kpi_config` rows were not read).
## 3. Key Findings from the Coverage Audit

1. **Synthetic Coverage vs Real Source Parity:**
   While `Inbound`, `Outbound`, and `Support Positions` pass application tests in `Backend/tests/test_ai_workspace.py`, these tests run against mocked fixtures. **Zero cells are verified** against production ground truth. 14 cells are `partial` (score and actual/target for `Coding`, `Submission`, `Re-Submission`, `Pharmacy`, `CSR`, `Sales`, and `Pre-Approvals IP Offshore`); every other cell is `blocked`.
2. **UAE RCM Is Partial Only for Score and Actual/Target:**
   The UAE RCM teams have distinct schemas. `Coding`, `Submission`, and `Re-Submission` are `partial` for score and actual/target (one repository parity check passed); ranking, trend, comparison, follow-up, and navigation are `blocked`.
3. **Branch Comparison Limitations:**
   Branch comparison is `blocked` for every team in this matrix: no parity check for branch comparisons has been run. Whether branch comparison applies to centralized offshore teams (e.g. Outbound, Egypt Coding) is an open owner question — it is not recorded here as `not applicable`, because no repository check establishes that it does not apply.
4. **Inbound Parity Fails on a Key Spelling:**
   Inbound score and actual/target are `blocked` because the team JSON key is `Attendance` while `kpi_service.DEFAULT_WEIGHTS` uses `Attend`. That mismatch is filed as an open owner question; no weight or key was changed to force a pass.