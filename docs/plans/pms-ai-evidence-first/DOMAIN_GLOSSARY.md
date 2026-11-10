# Phase 2: Domain Glossary and Entity Hierarchy

**Document Version:** 1.0  
**Date:** 10 November 2026  
**Status:** Domain Reference Verified  
**Scope:** Phase 2 Deliverable for PMS AI Evidence-First Upgrade ([Implementation Plan](file:///D:/Projects/PMS_Dashboard/docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md))

---

## 1. Verified Organizational Hierarchy

The PMS platform organizes performance data across five strictly typed structural tiers:

```
Organization (SGH Group)
└── Country Scope (Egypt / UAE / Shared "All")
    └── Function (e.g. Call Center, RCM, Shared Functions)
        └── Team / Channel (e.g. Inbound, Outbound, Support Positions, Coding EGY)
            └── Position / Role (e.g. Agent, Trainer, Quality Specialist, Coder)
                └── Performance Level (Employee, Managerial, Corporate BSC)
```

### 1.1 Country Scope
1. **Egypt (`EGY` / "Offshore Egypt"):**
   - Independent operational scope hosting Offshore Call Center and Offshore RCM teams.
   - All records, KPI targets, weights, and employee IDs are isolated from the UAE database namespace.
2. **United Arab Emirates (`UAE`):**
   - Onshore hospital, clinic, and regional operations (Dubai, Ajman, Sharjah).
   - Operates independent RCM teams, pharmacy, and management scorecards.
3. **Shared Scope (`All`):**
   - Executive Summary, Corporate Balanced Scorecard (BSC), and cross-regional leadership.
   - Shared data must never silently merge Egypt and UAE records without explicit regional attribution.

---

## 2. Function & Team Hierarchy Breakdown

### 2.1 Function: Call Center (Offshore Egypt)
A critical domain rule in PMS is that **Call Center is a Function**, not a team. It encompasses two operational channels and one governance position group:
- **`Inbound` (Team / Channel):**
  - **Level:** Employee.
  - **Roles:** Inbound Agents.
  - **Scored KPIs:** Booking Rate (65% target), Attendance Rate (75% target), Quality Score (95% target).
  - **Tracking-Only Indicators:** Average Handle Time (AHT, 2.50 min target), Abandoned Calls.
- **`Outbound` (Team / Channel):**
  - **Level:** Employee.
  - **Roles:** Outbound Agents.
  - **Scored KPIs:** Outbound Booking Rate, Attendance Rate, Quality Score, Contact Conversion.
  - **Tracking Indicators:** Call Volume, No-Show Rate.
- **`Support Positions` (Position Group / Governance):**
  - **Level:** Employee (Enablement & Governance layer).
  - **Roles:**
    1. `Quality Specialist` (Monitors call compliance, audit volumes, coaching conversion).
    2. `Trainer` (Refresher workshops, certification labs, impact on agent KPI lift).
    3. `Workforce Specialist` (Scheduling adherence, occupancy, shrinkage management).
  - **Scoring Basis:** Evaluated independently by role; reported as an average score across support roles in executive overviews.

---

### 2.2 Function: RCM (Revenue Cycle Management)

#### Crucial Business Decision: Strict Egypt vs UAE Separation
RCM exists in both countries but operates under completely distinct calculations, upload schemas, and target weights. They must **never** be merged or calculated using the other country's formula.

```
RCM Function
├── Egypt RCM (Offshore)
│   ├── Coding EGY
│   ├── Submission EGY
│   ├── Resubmission (Aliases: "Resubmission", "Re-Submission EGY")
│   └── Pre-Approvals IP
└── UAE RCM (Onshore)
    ├── Coding
    ├── Submission
    ├── Re-Submission (Separate UAE calculation & source)
    ├── Pre-Approvals OP Final (Dubai / Sharjah & Ajman)
    ├── Pre-Approvals IP Final Dubai
    └── Pre-Approvals IP Final Northern (Sharjah & Ajman)
```

#### Re-Submission Naming & Calculation Decision (Confirmed)
- **Egypt Re-Submission:**
  - Names `"Resubmission"` and `"Re-Submission EGY"` are confirmed aliases of the same offshore team.
  - Both aliases share the exact same Egypt calculation method and monthly upload processing.
  - De-duplication rule: If records exist under both aliases for the same employee and month, the record from the latest successful upload batch is authoritative.
- **UAE Re-Submission:**
  - Displays as `"Re-Submission"` in the UAE scope.
  - Uses its own separate UAE source records and calculation method.
  - Historical UAE results and formulas remain untouched pending a later phase upgrade.

---

## 3. Performance Levels Definition

The system defines three distinct calculation tiers via [`PerformanceLevel`](file:///D:/Projects/PMS_Dashboard/Backend/utils/performance_levels.py):

| Level | Database Value | Scope & Aggregation Rules | Authoritative Model |
| :--- | :--- | :--- | :--- |
| **Employee** | `'employee'` | Monthly evaluations for individual contributors (Agents, Coders, Billers, Support Roles). Includes employee ID, name, grade (A–E), status (Exceeds, Meets, Below), and raw KPI achievements. | `PerformanceRecord` & `KPIValue` |
| **Managerial** | `'management'` | Department head and team leader scorecards. Evaluates supervisory KPIs (team SLA, attrition, escalation resolution). | `ManagementKPISnapshot` |
| **Corporate** | `'corporate'` | Organization-wide Balanced Scorecard (BSC). Structured across four perspectives: Financial, Customer, Internal Business Processes, and Learning & Growth. | `management_kpi_snapshots` |

---

## 4. Comprehensive Team & Alias Catalog

To ensure consistent query resolution across the chatbot and UI navigation, the following canonical alias mappings are enforced by `resolve_canonical_team_name()` in [`Backend/services/ai/catalog.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/catalog.py):

| Canonical Team Name | Country Scope | Function | Supported English Aliases & Synonyms |
| :--- | :---: | :--- | :--- |
| **`Inbound`** | EGY | Call Center | `inbound`, `inbound team`, `inbound call center`, `inbound agents` |
| **`Outbound`** | EGY | Call Center | `outbound`, `outbound team`, `outbound call center`, `outbound agents` |
| **`Support Positions`** | EGY | Call Center | `support`, `support positions`, `call center support`, `support roles`, `support team` |
| **`Call Center`** | EGY | Call Center | `call center`, `contact center`, `cc` *(Refers to the overarching function/department)* |
| **`Coding EGY`** | EGY | RCM | `coding egy`, `egypt coding`, `coding in egypt`, `coding (egy)`, `offshore coding` |
| **`Submission EGY`** | EGY | RCM | `submission egy`, `egypt submission`, `submission in egypt`, `offshore submission` |
| **`Resubmission`** | EGY | RCM | `resubmission`, `resubmission egy`, `egypt resubmission`, `re-submission egy`, `offshore resubmission` |
| **`Pre-Approvals IP`** | EGY | RCM | `pre-approvals ip`, `pre approvals ip`, `egypt pre-approvals ip`, `ip pre-approvals egy` |
| **`Coding`** | UAE | RCM | `coding`, `medical coding`, `coding team`, `uae coding`, `coding uae` |
| **`Submission`** | UAE | RCM | `submission`, `claims submission`, `submission team`, `uae submission` |
| **`Re-Submission`** | UAE | RCM | `re-submission`, `re submission`, `uae resubmission`, `re-submission uae` |
| **`Pre-Approvals OP Final`** | UAE | RCM | `pre-approvals op final`, `op pre-approvals`, `outpatient pre-approvals uae` |
| **`Pre-Approvals IP Final Dubai`** | UAE | RCM | `pre-approvals ip final dubai`, `dubai ip pre-approvals`, `ip pre-approvals dubai` |
| **`Marketing`** | EGY | Shared | `marketing`, `digital marketing`, `marketing team`, `offshore marketing` |
| **`Pharmacy`** | UAE | Shared | `pharmacy`, `pharmacies`, `uae pharmacy`, `pharmacy department` |
| **`CSR`** | UAE | Shared | `csr`, `customer service representatives`, `patient service representatives` |
| **`Sales`** | UAE | Shared | `sales`, `sales team`, `commercial sales`, `uae sales` |
