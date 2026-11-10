# Phase 1: Issue Register & Known Defect Reproduction

**Document Version:** 1.0  
**Date:** 10 November 2026  
**Status:** Defect Reproduction Verified  
**Scope:** Phase 1 Deliverable for PMS AI Evidence-First Upgrade ([Implementation Plan](file:///D:/Projects/PMS_Dashboard/docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md))

---

## 1. Scenario-Specific Code Inventory

To ensure safe refactoring in subsequent phases without degrading system security or core calculations, all current routing logic, heuristics, and canned strings were cataloged into four architectural categories:

| Component / Logic | File Location | Classification | Action Justification |
| :--- | :--- | :--- | :--- |
| **`require_ai_enabled` Product Gate** | [`Backend/services/ai/feature_gate.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/feature_gate.py) | **KEEP** | Essential operational safety switch. Ensures AI is completely disabled in fresh deployments until explicitly enabled in database settings. |
| **`require_ai_admin` Role Gate** | [`Backend/services/ai/feature_gate.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/feature_gate.py) | **KEEP** | Core security boundary. Restricts pilot to Administrators. Must remain active until explicit authorization gates are approved. |
| **Prompt Injection & Leak Defense** | [`Backend/services/ai/router.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/router.py) | **KEEP** | Protects system instructions and boundaries against adversarial injection attempts. |
| **Read-Only Mutation Blocker** | [`Backend/services/ai/router.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/router.py) | **KEEP** | Strict read-only guarantee. Rejects SQL/mutation requests deterministically before any model or tool invocation. |
| **Sample-Data Warning Guardrail** | [`Backend/services/ai/orchestrator.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/orchestrator.py) | **KEEP** | Prevents analytical answers from being computed on dummy/sample data when `is_fallback_data == True`. |
| **Country Scope Separation (`EGY` vs `UAE`)** | [`Backend/services/ai/catalog.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/catalog.py) | **KEEP** | Preserves business rules: Egyptian records and calculations must never mix with UAE records. |
| **Hard-Coded Greeting Regex** | [`Backend/services/ai/orchestrator.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/orchestrator.py) | **KEEP** | Fast, zero-cost conversational handling. Prevents simple greetings ("Hi") from triggering expensive multi-table database queries. |
| **Hard-Coded "Call Center" Routing Defaults** | [`Backend/services/ai/router.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/router.py) | **REPLACE** | **Defect Source:** Unspecified queries historically defaulted to Call Center. Must be replaced with neutral authorized organization scope. |
| **Keyword-Based Metric Router** | [`Backend/services/ai/router.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/router.py) | **REPLACE** | **Defect Source:** Brittle keyword matching confuses booking counts with booking rates, routing branch queries to bottleneck diagnosis. |
| **Heuristic Tool Plan String Splitting** | [`Backend/services/ai/orchestrator.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/orchestrator.py) | **REPLACE** | **Defect Source:** Prepending empty-state warnings from initial tools to valid data retrieved by subsequent tools causes contradictory output. |
| **Deprecated Legacy Extraction Scripts** | `Backend/services/ai/legacy_extractors.py` | **REMOVE** | Stale code superseded by `DeterministicToolRegistry`. Safe to remove once all Phase 3 tests pass. |
| **Multi-Turn Context Spillover** | [`Backend/services/ai/conversation_service.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/conversation_service.py) | **INVESTIGATE** | Multi-turn dialogues can retain previous country/team context when a user explicitly switches subjects. |

---

## 2. Empirical Reproduction of the Three Known Issues

All three issues were reproduced against isolated, local database sessions without external model calls, verifying the exact code paths and root causes.

---

### Issue 1: Inbound Metric Query Returns Contradictory "No Matching Records" Prefix

#### Reproduction Profile
- **Prompt:** `"Who is the lowest performing agent in Inbound?"`
- **Scope / Period:** `country="EGY"`, `function="Call Center"`, `team="Inbound"`, `period="September 2026"`.
- **Expected Behavior:** Direct, concise identification of the lowest-performing agent based on authorized records:
  > *"Agent 1 (E001) is the lowest-scoring agent in Inbound for September 2026 with an overall score of 76.7%."*
- **Actual Output Observed:**
  > *"No performance records matched the selected filters (Inbound · September 2026). Agent 1 (E001) is the lowest-scoring agent in Inbound with an overall score of 76.7%."*
- **Provider Used:** `local_rules` (Deterministic fallback).

#### Root Cause Analysis
1. In [`Backend/services/ai/orchestrator.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/orchestrator.py), compound question planning generates two sequential tool executions:
   - Tool 1: `inspect_authorized_concepts` (metadata lookup).
   - Tool 2: `get_executive_and_priority_insights` (agent score analysis).
2. The scope dictionary passed to Tool 1 evaluated `team=None` during concept resolution, triggering a helper message: `"No performance records matched the selected filters"`.
3. In [`Backend/services/ai/local_evidence_synthesis.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/local_evidence_synthesis.py), the output string from Tool 1 was naively prepended to the final synthesis output, creating a glaring contradiction where the system simultaneously claims no records exist while presenting the exact lowest agent.

#### Remediation Plan for Phase 3/4
- Decouple metadata concept inspection from data presence checks.
- Prevent preliminary tool warnings from being concatenated into final synthesis responses when primary analytical tools successfully retrieve valid evidence.

---

### Issue 2: Clinics Booking Query Returns Unrelated AHT Bottleneck

#### Reproduction Profile
- **Prompt:** `"What was the Clinics booking in September 2026?"`
- **Scope / Period:** `country="UAE"`, `branch="Clinics"`, `period="September 2026"`.
- **Expected Behavior:** Return the operational booking volume for the Clinics branch (e.g. 180 bookings from `record_payload['geo']['bookings']['clinics']`), or ask for channel clarification.
- **Actual Output Observed:**
  > *"The primary KPI bottleneck in All authorized departments (September 2026 · Clinics) is AHT (Handle Time) at 0.0% achievement against a target of 2.50 min (100.0% below target)."*
- **Provider Used:** `local_rules` (Deterministic router).

#### Root Cause Analysis
1. In [`Backend/services/ai/router.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/router.py) lines 447–454, the router detects the substring `"booking"`.
2. Because the query does not contain explicit multi-branch comparison keywords (such as `"compare"`, `"versus"`, `"vs"`), the router maps `"booking"` to the standard Call Center KPI key `inbound:booking_rate`.
3. Entity extraction identifies `"Clinics"` as a branch key, leaving `team = None`.
4. When searching for `booking_rate` at the department level with `team = None`, the query router fails to resolve a valid team scorecard and falls back to its default diagnostic handler: `get_executive_and_priority_insights(bottleneck=True)`.
5. The diagnostic handler scans unweighted tracking indicators and selects `AHT (Handle Time)` (which is unconfigured for Clinics, showing `0.0%`), presenting AHT as the answer to a booking question.

#### Remediation Plan for Phase 3/4
- Introduce strict entity and intent disambiguation: distinguish **Operational Volume Counts** (e.g. branch booking volumes) from **Conversion KPI Rates** (e.g. Inbound booking rate %).
- When an isolated branch query mentions bookings, route directly to `compare_branches_operational_volumes` or query `record_payload['geo']` rather than defaulting to bottleneck KPI diagnosis.

---

### Issue 3: Branch Comparison Displays Conversion Percentages Instead of Volume Counts

#### Reproduction Profile
- **Prompt:** `"Which branch has most bookings: Dubai, Ajman or Sharjah?"`
- **Scope / Period:** `country="UAE"`, `branches=["Dubai", "Ajman", "Sharjah"]`, `period="September 2026"`.
- **Expected Behavior:** Direct comparison of operational volume **counts**:
  > *"Dubai had the highest bookings in September 2026 with 180 bookings, followed by Ajman with 70 bookings (Dubai +110 vs Ajman). Sharjah had no recorded bookings."*
- **Actual Output Observed (from frozen evaluation trace #21):**
  > *"Dubai leads with 71.2% Attendance Rate compared to Ajman at 59.2% (12.0% gap)."*
- **Provider Used:** Model tool plan selecting KPI trend tool instead of operational volume tool.

#### Root Cause Analysis
1. The tool registry historically offered `get_kpi_diagnosis_and_trends` and lacked an explicit distinction between rate KPIs and operational counts.
2. The language model (or heuristic router) associated the prompt token `"bookings"` with the KPI dictionary, selecting `attendance_rate` or `booking_rate` (which are percentages) because they were the only scoring metrics registered for the team.
3. The underlying branch volume counts (e.g. Dubai 180, Ajman 70) resided inside `record_payload['geo']` and were not queried, resulting in the system comparing attendance percentages while framing them as booking metrics.

#### Remediation Plan for Phase 3/4
- Completed in `test_ai_booking_comparisons.py` and [`tool_registry.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/tool_registry.py): `compare_branches_operational_volumes` is now an explicit, typed tool dedicated to branch volume counts.
- Strict schema validation ensures volume tools only output raw integer counts (`unit="bookings"`), preventing percentage substitution.
