# Phase 2: Open Questions, Conflicts & Evidence Gaps Register

**Document Version:** 1.0  
**Date:** 10 November 2026  
**Status:** Gap Register Verified  
**Scope:** Phase 2 Deliverable for PMS AI Evidence-First Upgrade ([Implementation Plan](file:///D:/Projects/PMS_Dashboard/docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md))

---

## 1. Unresolved Naming and Hierarchy Conflicts

| Area | Current Code State | Conflicting / Ambiguous Evidence | Recommended Resolution Path |
| :--- | :--- | :--- | :--- |
| **Pre-Approvals Scope Split** | Split into `Pre-Approvals IP` (Egypt) vs UAE variants (`Pre-Approvals OP Final`, `Pre-Approvals IP Final Dubai`, `Pre-Approvals IP Final Northern`). | Legacy workbooks occasionally label offshore files simply as `"Pre-Approvals"`. | Maintain strict country prefixing (`EGY` vs `UAE`). Prompt user for clarification if `"Pre-Approvals"` is asked without country context. |
| **UAE Re-Submission Modernization** | Unified Egypt aliases (`Resubmission` & `Re-Submission EGY`) use updated calculations, while UAE `Re-Submission` retains legacy formula. | UAE Re-Submission is scheduled for future revamp. Users querying "Re-Submission" in UAE might expect the new Egypt formula. | Enforce business decision: UAE Re-Submission must retain separate source data and calculation. Disclose that UAE calculation is independent. |
| **Support Positions Rollup** | `Support Positions` is modeled as a pseudo-team in Call Center, but consists of 3 distinct roles (Quality, Trainer, Workforce). | Monthly Review displays an average score across the 3 roles, but individual agents belong to distinct positions with different targets. | In AI responses, explicitly specify whether a score represents an individual specialist or the 3-role Support group average. |

---

## 2. Open Business Questions Requiring Stakeholder Alignment

### Question 1: Historical Target & Weight Basis for Pre-September 2026 Trends
- **Context:** When computing a 6-month historical score trend (e.g. May 2026 – October 2026), older months may have operated under different KPI weights, targets, or excel calculation formulas that were not archived in `team_kpi_config`.
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
   - **Impact:** Certification status in [`COVERAGE_MATRIX.md`](file:///D:/Projects/PMS_Dashboard/docs/plans/pms-ai-evidence-first/COVERAGE_MATRIX.md) remains `partial_evidence` or `unverified` until independent source parity is tested against real files.
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
   - Hosting a Qwen3 4B Q4_K_M model requires ~4.5–6.0 GB RAM alongside PostgreSQL, FastAPI backend, Next.js frontend, and Redis.
   - **Gate:** Live Qwen execution must be benchmarked on target-like hardware for concurrency, memory consumption, and fallback under high load before any pilot rollout.
