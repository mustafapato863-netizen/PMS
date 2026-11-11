# Phase 2: Open Questions, Conflicts & Evidence Gaps Register

**Document Version:** 1.1
**Date:** 11 November 2026
**Status:** Gap Register Verified — reconciled to repository sources in Phase 2 (issue #94)
**Scope:** Phase 2 Deliverable for PMS AI Evidence-First Upgrade ([Implementation Plan](file:///D:/Projects/PMS_Dashboard/docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md))

---

## 1. Unresolved Naming and Hierarchy Conflicts

| Area | Current Code State | Conflicting / Ambiguous Evidence | Recommended Resolution Path |
| :--- | :--- | :--- | :--- |
| **Pre-Approvals Scope Split** | Split into `Pre-Approvals IP` and `Pre-Approvals IP Offshore` (Egypt) vs UAE variants (`Pre-Approvals OP Dubai`, `Pre-Approvals OP Final SHJAJM`, `Pre-Approvals IP Final Dubai`, `Pre-Approvals IP Final SHJAJM`, `Pre-Approvals IP Elective Dubai`). `Pre-Approvals OP Final` and `Pre-Approvals IP Final` are presentation merges of two source teams each; `Pre-Approvals IP Dubai` is a presentation name for `Pre-Approvals IP Final Dubai`. | Legacy workbooks occasionally label offshore files simply as `"Pre-Approvals"`. | Maintain strict country prefixing (`EGY` vs `UAE`). Prompt user for clarification if `"Pre-Approvals"` is asked without country context; prompt for the city when a merged presentation name is used without one. |
| **Re-Submission / Resubmission Alias Conflict (open)** | The backend config loader and `team_identity.py` treat `Re-Submission EGY` as the Egypt `Resubmission` team, but the Frontend country-alias list (`countryTeamIdentity.ts`) lists `Re-Submission EGY` as a separate Egypt source name. The runtime does not map bare `re-submission egy` to `Resubmission`; a bare `Re-Submission` with no country context asks for clarification. | Users querying "Re-Submission" in UAE might expect the new Egypt formula, and vice versa. | Owner decision required: confirm whether `Re-Submission EGY` is one team (Egypt `Resubmission`) or a distinct source name, and align the Frontend list with the backend mapping. Until then the alias stays unresolved and the router clarifies. |
| **Support Positions Rollup** | `Support Positions` is a Call Center subteam, not a config team, and consists of 5 config positions (Call Center trainer, Quality Assurance, Workforce analyst, Inbound Team Leader, Outbound Team Leader). | Monthly Review displays an average score across the 5 positions, but individual agents belong to distinct positions with different targets. | In AI responses, explicitly specify whether a score represents an individual specialist or the 5-position Support group average. |

---

## 2. Open Business Questions Requiring Stakeholder Alignment

### Question 1: Historical Target & Weight Basis for Pre-September 2026 Trends
- **Context:** When computing a 6-month historical score trend (e.g. May 2026 â€“ October 2026), older months may have operated under different KPI weights, targets, or excel calculation formulas that were not archived in `team_kpi_config`.
- **Business Risk:** Applying October 2026 targets retroactively to May 2026 records changes historical performance facts and causes discrepancies with previously signed-off monthly review slide decks.
- **Current Conservative Rule:** Calculate historical points using the records and scoring basis available for that month. Where historical basis cannot be verified, display the limitation honestly or show gaps; never present unverified backfills as historical fact.

### Question 2: Employee Mid-Month Department Transfer
- **Context:** If an employee transitions from Inbound Agent to Support Specialist (or Outbound) mid-month, an upload may contain two records for the same employee in different teams.
- **Current Behavior:** Both records are stored independently under different `team_id` foreign keys.
- **Pending Decision:** When a user asks *"How did Employee X perform in October?"*, should the assistant present both team evaluations, or default to the employee's current team assignment?

### Question 3: Corporate BSC Rollup Attribution
- **Context:** Executive queries often ask for "Hospital Performance" or "Overall SGH Achievement".
- **Pending Decision:** Does "Overall Performance" equal the weighted average of Corporate BSC perspectives, or the average of employee department scores? (Recommended: Corporate BSC perspectives for executive level; department average for operational level).

---

## 3. Missing Source Data & Unverified Calculation Gaps

1. **Independent Production Ground Truth Workbooks:**
   - **Gap:** Current automated tests rely on synthetic SQLite fixtures in `Backend/tests/`.
   - **Missing Asset:** An approved, de-identified repository of historical production workbooks (Excel files) for Egypt and UAE across all departments.
   - **Impact:** Certification status in [`COVERAGE_MATRIX.md`](file:///D:/Projects/PMS_Dashboard/docs/plans/pms-ai-evidence-first/COVERAGE_MATRIX.md) remains `partial` or `blocked` until independent source parity is tested against real files.
2. **UAE RCM Formula Verification:**
   - **Gap:** Onshore hospital claims processing, collection ratios, and denial calculations have not been verified against live hospital billing systems.
   - **Impact:** UAE RCM teams (`Coding`, `Submission`, `Re-Submission`) must remain uncertified for AI analytical answers.
3. **Corporate Balanced Scorecard Ground Truth:**
   - **Gap:** Financial perspective and Patient Experience perspectives in `management_kpi_snapshots` lack automated test coverage for AI query routing.

---

## 4. Model Infrastructure and Host Verification Gaps

1. **Host Reachability:**
   - The pilot endpoint `http://pms-qwen-pilot:8080/v1` timed out from the local development checkout.
   - The Windows host port 8080 is occupied by `AgentService.exe` (unrelated background service).
2. **Target VPS Resource Constraints (Hostinger KVM 2):**
   - The production VPS is an 8 GB RAM KVM 2 instance.
   - Hosting a Qwen3 4B Q4_K_M model requires ~4.5â€“6.0 GB RAM alongside PostgreSQL, FastAPI backend, Next.js frontend, and Redis.
   - **Gate:** Live Qwen execution must be benchmarked on target-like hardware for concurrency, memory consumption, and fallback under high load before any pilot rollout.


---

## 5. Phase 2 Reconciliation — Open Owner Questions (issue #94)

These items were reconciled to repository truth in Phase 2 but remain open because only the owning team can resolve them. They are recorded here instead of being silently decided in the docs.

### Question 4: Inbound `Attendance` vs `Attend` key mismatch
- **Context:** The Inbound team JSON uses the KPI key `Attendance`, but `kpi_service.DEFAULT_WEIGHTS` uses `Attend`. The Phase 2 parity check therefore fails for Inbound score and actual/target, and the coverage matrix records those cells as `blocked`.
- **Pending Decision:** Rename one side (JSON key or `DEFAULT_WEIGHTS` key) so the parity check can pass, or confirm that `Attend` is a deliberate separate key with its own mapping. No key was renamed in Phase 2 to force a pass.

### Question 5: Branch comparison for centralized offshore teams
- **Context:** Branch comparison is `blocked` for every team in the coverage matrix because no parity check for branch comparisons has been run. It is not recorded as `not applicable` for centralized offshore teams (e.g. Outbound, Egypt Coding): no repository check establishes that branch comparison does not apply to them.
- **Pending Decision:** Confirm per team whether branch comparison is a meaningful operation. If it is not, the matrix may record `not applicable` with the check that establishes it.

### Question 6: Pre-Approvals presentation merges
- **Context:** `Pre-Approvals OP Final` and `Pre-Approvals IP Final` are presentation merges of two source teams each, and `Pre-Approvals IP Dubai` is a presentation name for `Pre-Approvals IP Final Dubai`. There is no team JSON for the merged names, so the router asks which source team is meant when no city is given.
- **Pending Decision:** Confirm the merged presentation names and the city each source team covers, or replace the merges with the source-team names in the presentation layer.

### Question 7: Corporate BSC region disagreements (Finance / RCM)
- **Context:** `Finance` and `RCM` have config region `All`, but the Corporate BSC catalog records them under UAE. The coverage matrix lists them under a shared-scope section and never folds their rows into a single-country total.
- **Pending Decision:** Approve an attribution rule for shared-scope teams in Corporate BSC, or keep them listed as shared scope only.

### Question 8: Resubmission alias conflict
- **Context:** See the `Re-Submission / Resubmission Alias Conflict` row in section 1. The backend maps `Re-Submission EGY` to the Egypt `Resubmission` team; the Frontend lists it as a separate Egypt source name.
- **Pending Decision:** Confirm whether `Re-Submission EGY` is one team or a distinct source name, and align both sides.
