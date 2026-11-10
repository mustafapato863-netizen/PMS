# Phase 2: Scope & Operation Coverage Matrix

**Document Version:** 1.0  
**Date:** 10 November 2026  
**Status:** Conservative Verification Audit  
**Scope:** Phase 2 Deliverable for PMS AI Evidence-First Upgrade ([Implementation Plan](file:///D:/Projects/PMS_Dashboard/docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md))

---

## 1. Certification Classification Rules

To prevent unwarranted claims of capability, every cell in this matrix is classified under strict verification criteria:

| Status Code | Meaning / Criteria | Release Rule |
| :--- | :--- | :--- |
| **`verified`** | Validated against **independent production source ground truth** (owner spreadsheets or verified database parity). | Eligible for production release. *(Currently 0 cells qualify).* |
| **`partial_evidence`** | Code implemented and passing **synthetic/mocked application tests** (`test_ai_workspace.py`, `test_ai_booking_comparisons.py`), but independent source parity is pending. | Requires Phase 3 independent source verification before certification. |
| **`verified_no_data`** | Scope and calculation verified, but **no published records** exist for the requested period. The system truthfully returns an honest empty state. | Safe behavioral state. |
| **`unverified`** | Entity exists in the catalog or configuration, but **no automated tests or source parity** have been executed. | Must be treated as unverified in model responses. |
| **`unsupported`** | The operation is fundamentally invalid for this scope (e.g. branch volume comparison for a purely centralized offshore team). | Model must return a polite refusal explaining the limitation. |

---

## 2. Country × Function × Team × Level × Operation Coverage Matrix

### 2.1 Offshore Egypt Operations

| Function | Team / Role | Level | Score / Summary | Actual vs Target | Ranking / Bottom | 6-Month Trend | Branch Comparison | Follow-Up | Page Navigation | Evidence Reference & Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Call Center** | `Inbound` | Employee | `partial_evidence` | `partial_evidence` | `partial_evidence` | `partial_evidence` | `partial_evidence` | `partial_evidence` | `partial_evidence` | [`test_ai_workspace.py`](file:///D:/Projects/PMS_Dashboard/Backend/tests/test_ai_workspace.py) & [`test_ai_booking_comparisons.py`](file:///D:/Projects/PMS_Dashboard/Backend/tests/test_ai_booking_comparisons.py) |
| **Call Center** | `Outbound` | Employee | `partial_evidence` | `partial_evidence` | `partial_evidence` | `partial_evidence` | `unsupported` | `partial_evidence` | `partial_evidence` | [`test_ai_workspace.py`](file:///D:/Projects/PMS_Dashboard/Backend/tests/test_ai_workspace.py) (Branch comparison not applicable) |
| **Call Center** | `Support Positions` | Employee | `partial_evidence` | `partial_evidence` | `partial_evidence` | `partial_evidence` | `unsupported` | `partial_evidence` | `partial_evidence` | [`test_ai_workspace.py`](file:///D:/Projects/PMS_Dashboard/Backend/tests/test_ai_workspace.py) (Averaged across 3 support roles) |
| **RCM** | `Coding EGY` | Employee | `partial_evidence` | `partial_evidence` | `unverified` | `unverified` | `unsupported` | `unverified` | `partial_evidence` | [`catalog.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/catalog.py) (Scoring rules implemented; ranking tests pending) |
| **RCM** | `Submission EGY` | Employee | `partial_evidence` | `partial_evidence` | `unverified` | `unverified` | `unsupported` | `unverified` | `partial_evidence` | Config loaded; source parity pending |
| **RCM** | `Resubmission` | Employee | `partial_evidence` | `partial_evidence` | `unverified` | `unverified` | `unsupported` | `unverified` | `partial_evidence` | Unified Egypt alias rules tested; production data pending |
| **RCM** | `Pre-Approvals IP` | Employee | `partial_evidence` | `partial_evidence` | `unverified` | `unverified` | `unsupported` | `unverified` | `partial_evidence` | Config loaded; offshore scoring rules pending test |
| **Shared** | `Marketing` | Employee | `partial_evidence` | `unverified` | `unverified` | `unverified` | `unsupported` | `unverified` | `partial_evidence` | Basic metadata verified; deep metrics unverified |

---

### 2.2 UAE Operations

| Function | Team / Role | Level | Score / Summary | Actual vs Target | Ranking / Bottom | 6-Month Trend | Branch Comparison | Follow-Up | Page Navigation | Evidence Reference & Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **RCM** | `Coding` | Employee | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | `partial_evidence` | Distinct UAE schema; automated tests pending |
| **RCM** | `Submission` | Employee | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | `partial_evidence` | Distinct UAE schema; automated tests pending |
| **RCM** | `Re-Submission` | Employee | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | `partial_evidence` | Separate UAE calculation method; pending Phase 3 revamp |
| **RCM** | `Pre-Approvals OP Final` | Employee | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | `partial_evidence` | Regional split (Dubai vs Shj/Ajm) unverified |
| **RCM** | `Pre-Approvals IP Dubai` | Employee | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | `partial_evidence` | Hospital inpatient authorization; unverified |
| **Shared** | `Pharmacy` | Employee | `partial_evidence` | `unverified` | `unverified` | `unverified` | `partial_evidence` | `unverified` | `partial_evidence` | Basic branch breakdown in catalog; source tests pending |
| **Shared** | `CSR` | Employee | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | `partial_evidence` | Patient relations desks across branches; unverified |
| **Shared** | `Sales` | Employee | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | `partial_evidence` | Corporate commercial sales; unverified |

---

### 2.3 Managerial & Corporate BSC Operations

| Scope | Function / Area | Level | Score / Summary | Perspective Breakdown | Target vs Actual | 6-Month Trend | Action Proposals | Status & Evidence |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Shared (All)** | `Executive Summary` | Corporate | `unverified` | `unverified` | `unverified` | `unverified` | `unsupported` | Organization-level rollup; source parity pending |
| **Shared (All)** | `Corporate BSC` | Corporate | `partial_evidence` | `partial_evidence` | `partial_evidence` | `unverified` | `unsupported` | 4 perspectives (Financial, Customer, Process, Learning) mapped in `corporate_bsc_catalog_data.py` |
| **EGY / UAE** | `Department Managers` | Managerial | `unverified` | `unverified` | `unverified` | `unverified` | `unsupported` | Scorecards exist in `management_kpi_snapshots`; AI queries unverified |

---

## 3. Key Findings from the Coverage Audit

1. **Synthetic Coverage vs Real Source Parity:**
   While `Inbound`, `Outbound`, and `Support Positions` pass all tests in `Backend/tests/test_ai_workspace.py`, these tests run against mocked fixtures. **Zero cells have been certified against production ground truth**.
2. **UAE RCM Remains Largely Unverified:**
   The UAE RCM teams have distinct schemas, but their AI exploration routes have not yet been evaluated end-to-end.
3. **Branch Comparison Limitations:**
   Branch comparisons are only supported for entities with explicit branch breakdowns in `record_payload['geo']` (Inbound, Pharmacy, CSR). Attempting branch comparisons on offshore centralized teams (e.g. Outbound, Egypt Coding) correctly returns `unsupported`.
