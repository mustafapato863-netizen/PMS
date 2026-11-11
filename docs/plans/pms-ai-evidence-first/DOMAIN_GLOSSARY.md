# Phase 2: Domain Glossary and Entity Hierarchy

**Document Version:** 1.1
**Date:** 11 November 2026
**Status:** Domain Reference Verified — reconciled to repository sources in Phase 2 (issue #94)
**Scope:** Phase 2 Deliverable for PMS AI Evidence-First Upgrade ([Implementation Plan](file:///D:/Projects/PMS_Dashboard/docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md))

---

## 1. Verified Organizational Hierarchy

The PMS platform organizes performance data across five strictly typed structural tiers:

```
Organization (SGH Group)
â””â”€â”€ Country Scope (Egypt / UAE / Shared "All")
    â””â”€â”€ Function (e.g. Call Center, RCM, Shared Functions)
        â””â”€â”€ Team / Channel (e.g. Inbound, Outbound, Support Positions, Coding EGY)
            â””â”€â”€ Position / Role (e.g. Agent, Trainer, Quality Specialist, Coder)
                â””â”€â”€ Performance Level (Employee, Managerial, Corporate BSC)
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
Call Center is both a function and a config team: `Backend/config/teams/call_center.json` defines a team named Call Center (region EGY), and the function list also contains Call Center. It encompasses two operational channel teams and one governance position group whose positions live on the Call Center config:
- **`Inbound` (Team / Channel):**
  - **Level:** Employee.
  - **Roles:** Inbound Agents.
  - **Scored KPIs** (`inbound.json`, weights sum to 1.0): Attendance 0.70 (code-default target 75%), Booking 0.10 (target 45%), Quality 0.05 (target 95%), AHT 0.05 lower-is-better (target 150 seconds), Other 0.10 lower-is-better (Abandon Rate or UTZ). AHT is a scored KPI in Inbound, not a tracking-only indicator. Abandoned Calls is a record-payload count (`record_payload['calls']['abandoned']`), not a team-JSON KPI.
- **`Outbound` (Team / Channel):**
  - **Level:** Employee.
  - **Roles:** Outbound Agents.
  - **Scored KPIs** (`outbound.json`, weights sum to 1.0): Attendance 0.70 (code-default target 55%), Booking 0.10 (target 46%), Quality 0.10 (target 95%), Other 0.10 higher-is-better (Reachability, target 75%). Outbound has no AHT KPI in its team JSON; AHT there is a tracking-only measure at weight 0 (`Backend/services/outbound_period_basis.py`).
- **`Support Positions` (Position Group / Governance):**
  - **Level:** Employee (Enablement & Governance layer).
  - **Note:** Support Positions is a Call Center subteam, not a config team of its own. Its positions are stored on `call_center.json`:
    1. `Call Center trainer`
    2. `Quality Assurance`
    3. `Workforce analyst`
    4. `Inbound Team Leader`
    5. `Outbound Team Leader`
  - **Scoring Basis:** Evaluated independently by role; reported as an average score across support roles in executive overviews.

---

### 2.2 Function: RCM (Revenue Cycle Management)

#### Crucial Business Decision: Strict Egypt vs UAE Separation
RCM exists in both countries but operates under completely distinct calculations, upload schemas, and target weights. They must **never** be merged or calculated using the other country's formula.

```
RCM Function
â”œâ”€â”€ Egypt RCM (Offshore)
â”‚   â”œâ”€â”€ Coding EGY
â”‚   â”œâ”€â”€ Submission EGY
â”‚   â”œâ”€â”€ Resubmission
â”‚   â”œâ”€â”€ Pre-Approvals IP
â”‚   â””â”€â”€ Pre-Approvals IP Offshore
â””â”€â”€ UAE RCM (Onshore)
    â”œâ”€â”€ Coding
    â”œâ”€â”€ Submission
    â”œâ”€â”€ Re-Submission (Separate UAE calculation & source)
    â”œâ”€â”€ Pre-Approvals OP Dubai
    â”œâ”€â”€ Pre-Approvals OP Final SHJAJM
    â”œâ”€â”€ Pre-Approvals IP Final Dubai
    â”œâ”€â”€ Pre-Approvals IP Final SHJAJM
    â””â”€â”€ Pre-Approvals IP Elective Dubai
```

`Pre-Approvals OP Final` and `Pre-Approvals IP Final` are presentation names that merge the Dubai and SHJAJM source teams; neither has a team JSON. `Pre-Approvals IP Dubai` is likewise a presentation name, not a config team (the config team is `Pre-Approvals IP Final Dubai`). Do not treat a presentation name as a single config team: the router asks which source team is meant when no city qualifier is given.

#### Re-Submission Naming & Calculation Decision (Open Conflict)
- **Egypt Re-Submission:**
  - The Egypt config team is `"Resubmission"` (`resubmission.json`). That file lists `"Re-Submission EGY"` in its aliases and `Backend/utils/team_identity.py` maps the same spelling to the Egypt team, so backend upload and de-duplication paths treat the two spellings as one team.
  - That alias is **not confirmed across sources**: the Frontend country-alias table still lists `"Re-Submission EGY"` as a separate Egypt source name, and the Phase 2 manifest files the pair as unresolved alias conflict `team:re-submission egy`. Until the owner confirms the Frontend table, AI resolution must not present the pair as a confirmed alias, and must not merge records on the alias alone.
  - De-duplication rule (backend upload path only): If records exist under both spellings for the same employee and month, the record from the latest successful upload batch is authoritative.
- **UAE Re-Submission:**
  - Displays as `"Re-Submission"` in the UAE scope.
  - Uses its own separate UAE source records and calculation method.
  - Historical UAE results and formulas remain untouched pending a later phase upgrade.

---

## 3. Performance Levels Definition

The system defines three distinct calculation tiers via [`PerformanceLevel`](file:///D:/Projects/PMS_Dashboard/Backend/utils/performance_levels.py):

| Level | Database Value | Scope & Aggregation Rules | Authoritative Model |
| :--- | :--- | :--- | :--- |
| **Employee** | `'Employee'` | Monthly evaluations for individual contributors (Agents, Coders, Billers, Support Roles). Includes employee ID, name, grade (Aâ€“E), status (Exceeds, Meets, Below), and raw KPI achievements. | `PerformanceRecord` & `KPIValue` |
| **Managerial** | `'Managerial'` | Department head and team leader scorecards. Evaluates supervisory KPIs (team SLA, attrition, escalation resolution). | `ManagementKPISnapshot` |
| **Corporate** | `'Corporate'` | Organization-wide Balanced Scorecard (BSC). Structured across four perspectives: Financial, Customer, Internal Business Processes, and Learning & Growth. | `management_kpi_snapshots` |

`performance_records.performance_level` is constrained to `Employee`, `Managerial`, and `Corporate` (`PerformanceLevel` enum; `ck_performance_record_level`). Do not confuse it with `teams.team_level`, a different column constrained to `employee` and `management` (`ck_team_level`).

---

## 4. Comprehensive Team & Alias Catalog

To ensure consistent query resolution across the chatbot and UI navigation, the following canonical alias mappings are enforced by `resolve_canonical_team_name()` in [`Backend/services/ai/catalog.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/catalog.py):

**Bare cross-country names are ambiguous and are not aliases of one country.** Bare `Coding`, `Submission`, `Re-Submission` and `Resubmission` — with no country word, single-region scope, or scoped session team — must not silently resolve to UAE (or to Egypt). The router asks which country is meant. Only the country-qualified aliases below resolve directly. `Re-Submission EGY` is an unresolved alias conflict (see section 2.2), not a confirmed alias of `Resubmission`.

| Canonical Team Name | Country Scope | Function | Supported English Aliases & Synonyms |
| :--- | :---: | :--- | :--- |
| **`Inbound`** | EGY | Call Center | `inbound`, `inbound team`, `inbound call center`, `inbound agents` |
| **`Outbound`** | EGY | Call Center | `outbound`, `outbound team`, `outbound call center`, `outbound agents` |
| **`Support Positions`** | EGY | Call Center | `support`, `support positions`, `call center support`, `support roles`, `support team` |
| **`Call Center`** | EGY | Call Center | `call center`, `contact center`, `cc` *(Refers to the overarching function/department)* |
| **`Coding EGY`** | EGY | RCM | `coding egy`, `egypt coding`, `coding in egypt`, `coding (egy)`, `offshore coding` |
| **`Submission EGY`** | EGY | RCM | `submission egy`, `egypt submission`, `submission in egypt`, `offshore submission` |
| **`Resubmission`** | EGY | RCM | `resubmission egy`, `egypt resubmission`, `offshore resubmission` (bare `resubmission` is ambiguous; `re-submission egy` is an unresolved alias conflict) |
| **`Pre-Approvals IP`** | EGY | RCM | `pre-approvals ip`, `pre approvals ip`, `egypt pre-approvals ip`, `ip pre-approvals egy` |
| **`Pre-Approvals IP Offshore`** | EGY | RCM | `pre-approvals ip offshore`, `offshore pre-approvals`, `pre-approvals offshore`, `egypt pre-approvals offshore` (distinct config team from `Pre-Approvals IP`; never collapsed) |
| **`Coding`** | UAE | RCM | `medical coding`, `coding team`, `uae coding`, `coding uae` (bare `coding` is ambiguous) |
| **`Submission`** | UAE | RCM | `claims submission`, `submission team`, `uae submission`, `submission uae` (bare `submission` is ambiguous) |
| **`Re-Submission`** | UAE | RCM | `uae resubmission`, `re-submission uae`, `resubmission uae` (bare `re-submission` / `re submission` are ambiguous) |
| **`Pre-Approvals OP Final`** | UAE | RCM | `pre-approvals op final`, `op pre-approvals`, `outpatient pre-approvals uae` (presentation merge of `Pre-Approvals OP Dubai` and `Pre-Approvals OP Final SHJAJM`; no team JSON — the router asks which source team is meant when no city is given) |
| **`Pre-Approvals OP Dubai`** | UAE | RCM | `pre-approvals op dubai`, `pre approvals op dubai`, `op dubai` |
| **`Pre-Approvals OP Final SHJAJM`** | UAE | RCM | `pre-approvals op final shjajm`, `pre approvals op final shjajm`, `op final shjajm`, `op sharjah` |
| **`Pre-Approvals IP Final Dubai`** | UAE | RCM | `pre-approvals ip final dubai`, `dubai ip pre-approvals`, `ip pre-approvals dubai` |
| **`Pre-Approvals IP Final SHJAJM`** | UAE | RCM | `pre-approvals ip final shjajm`, `pre approvals ip final shjajm`, `ip final shjajm`, `ip sharjah` |
| **`Pre-Approvals IP Final`** | UAE | RCM | `pre-approvals ip final`, `ip final pre-approvals`, `inpatient pre-approvals` (presentation merge of `Pre-Approvals IP Final Dubai` and `Pre-Approvals IP Final SHJAJM`; no team JSON — the router asks which source team is meant when no city is given) |
| **`Pre-Approvals IP Elective Dubai`** | UAE | RCM | `pre-approvals ip elective dubai`, `pre approvals ip elective dubai`, `ip elective dubai` |
| **`Marketing`** | EGY | Shared | `marketing`, `digital marketing`, `marketing team`, `offshore marketing` |
| **`Pharmacy`** | UAE | Shared | `pharmacy`, `pharmacies`, `uae pharmacy`, `pharmacy department` |
| **`CSR`** | UAE | Shared | `csr`, `customer service representatives`, `patient service representatives` |
| **`Sales`** | UAE | Shared | `sales`, `sales team`, `commercial sales`, `uae sales` |
