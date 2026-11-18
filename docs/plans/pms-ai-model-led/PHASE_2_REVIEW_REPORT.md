# PHASE 2 REVIEW REPORT: Gated Model-Led Pilot & Evidence-Bound Synthesis

**Document Under Review:** Phase 2 of [`docs/plans/PMS_AI_MODEL_LED_IMPLEMENTATION_PLAN.md`](file:///d:/Projects/PMS_Dashboard/docs/plans/PMS_AI_MODEL_LED_IMPLEMENTATION_PLAN.md)  
**Deliverables Audited:**
- [`Backend/services/ai/router.py`](file:///d:/Projects/PMS_Dashboard/Backend/services/ai/router.py) (Structured Pass 1 tool calls, Admin gate, prompt metric extraction)
- [`Backend/services/ai/orchestrator.py`](file:///d:/Projects/PMS_Dashboard/Backend/services/ai/orchestrator.py) (Pass 2 model synthesis, claim validator integration, answer source provenance, pre-query argument validation)
- [`Backend/services/ai/claim_validator.py`](file:///d:/Projects/PMS_Dashboard/Backend/services/ai/claim_validator.py) (Directional polarity, lower-is-better targets, derived deltas)
- [`Backend/scripts/verify_phase2_model_led.py`](file:///d:/Projects/PMS_Dashboard/Backend/scripts/verify_phase2_model_led.py) (End-to-end HTTP verification through FastAPI `TestClient`)
- [`Backend/scripts/phase2_verification_report.json`](file:///d:/Projects/PMS_Dashboard/Backend/scripts/phase2_verification_report.json) (Empirical HTTP test output artifact)

**Review Date:** 17 November 2026  
**Auditor:** EGM Codebase Details Reviewer (Technical Quality Auditor)  
**Protocol:** Elephant-Goldfish Model (EGM) Stateless Audit  
**Historical Note:** Initial review artifact was missing from disk; this fresh review report records the comprehensive audit of the implemented code and empirical HTTP execution artifacts.

---

## 1. Executive Summary

Phase 2 establishes the end-to-end model-led execution path through the PMS AI chat API for authorized Admins. The phase replaces legacy regex-template cascades with a 2-Pass model-led pipeline:
1. **Pass 1 (Structured Tool Calling)**: The configured runtime provider (`@cf/ibm-granite/granite-4.0-h-micro` via Cloudflare Workers AI) interprets user prompts against authorized JSON tool schemas (`DeterministicToolRegistry.AUTHORIZED_MODEL_LED_TOOLS`) and outputs structured tool calls.
2. **Deterministic Data Execution**: Read-only tools execute against authoritative records with pre-query argument and RBAC validation.
3. **Pass 2 (Evidence-Grounded Synthesis)**: The provider generates a concise natural language response grounded in factual evidence.
4. **Claim Verification Gate**: `validate_claims()` audits the generated text against `claim_ledger`. If claims are substantiated, `answer_source="model_synthesis"` is emitted; if unsubstantiated, the system falls back safely to verified facts with `answer_source="fallback"`.

---

## 2. Empirical Verification Evidence (HTTP Reference Trace)

The end-to-end HTTP script [`Backend/scripts/verify_phase2_model_led.py`](file:///d:/Projects/PMS_Dashboard/Backend/scripts/verify_phase2_model_led.py) was executed against the live Cloudflare IBM Granite provider. The complete trace was recorded in [`Backend/scripts/phase2_verification_report.json`](file:///d:/Projects/PMS_Dashboard/Backend/scripts/phase2_verification_report.json):

### A. Turn 1: Single Period Value & Target Evaluation
- **Prompt:** `"What was Nadia Fadel's Waiting Time in September 2026?"`
- **Tool Dispatched:** `read_employee_metric` (`kpi_key="waitingtime"`, `period="2026-09"`)
- **Factual Evidence:** Actual = `6.2 min`, Target = `5.0 min`, Direction = `lower_better`.
- **Generated Headline:**  
  `"Nadia Fadel's Waiting Time was 6.2 min in September 2026, exceeding the target limit of 5.0 min by 1.2 min (did not meet target)"`
- **Audit Verification:**
  - Value fidelity: `6.2 min` correctly extracted and formatted.
  - Target gap: `1.2 min` exceeds the target limit.
  - Lower-is-better polarity: Because lower is better, `6.2 > 5.0` correctly classified as exceeding the limit / missing the target (never erroneously labeled as "Met target").
- **Provenance & Latency:** `answer_source="model_synthesis"`, `latency_ms=5011`, `fallback_outcome="none"`.

### B. Turn 2: Follow-up Period Switch
- **Prompt:** `"And in August?"`
- **Context Inherited:** Nadia Fadel (`EMP501`), `waitingtime`. Period switched to `August 2026`.
- **Generated Headline:**  
  `"Nadia Fadel's Waiting Time was 6.8 min in August 2026, exceeding the target limit of 5.0 min by 1.8 min (did not meet target)"`
- **Audit Verification:**
  - Value fidelity: `6.8 min` correctly extracted.
  - Target gap: `1.8 min` above limit.
- **Provenance & Latency:** `answer_source="model_synthesis"`, `latency_ms=5408`, `fallback_outcome="none"`.

### C. Turn 3: Multi-Month Trend & Polarity
- **Prompt:** `"How did her Waiting Time change across the available months?"`
- **Tool Dispatched:** `get_score_trend` across August (`6.8 min`) and September (`6.2 min`).
- **Generated Headline:**  
  `"Nadia Fadel's Waiting Time improved from 6.8 min in August 2026 to 6.2 min in September 2026, a change of -0.6 min indicating an improvement."`
- **Audit Verification:**
  - Dual period operands bound: August `6.8 min` and September `6.2 min`.
  - Delta: `0.6 min` reduction.
  - Polarity: Reduction in Waiting Time accurately verified and described as an **improvement** (`diff_word="improvement"`).
- **Provenance & Latency:** `answer_source="model_synthesis"`, `latency_ms=6188`, `fallback_outcome="none"`.

---

## 3. Security, Access Boundaries & Edge Cases

1. **Non-Admin Access Denial**:
   - HTTP request with `role="Employee"` sent to `/api/ai/chat` returned `HTTP 403 Forbidden` (`duration_ms=7.98`). Non-Admin users cannot access the pilot.
2. **Pre-Query Rejection of Invalid Arguments**:
   - Tool calls missing required arguments (e.g. missing `metric_id` on `read_employee_metric`) are halted before data access with `outcome="clarification"`, `fallback_outcome="invalid_tool_arguments"`, and 0 data queries executed.
3. **Ambiguity Resolution & Identity Preservation**:
   - Prompt `"Show performance for Mariam"` returned `outcome="clarification"` with choices `choice-person-EMP601` (Mariam Ali) and `choice-person-EMP602` (Mariam Hassan).
   - Sending `clarification_choice_id="choice-person-EMP601"` uniquely resolved to Mariam Ali, returning score `87.0%` via `model_synthesis`.

---

## 4. Final Verdict

Phase 2 implementation, answer validation corrections, lower-is-better polarity rules, and authenticated HTTP test harness are fully verified with empirical evidence.

**VERDICT: ACCEPTED**
