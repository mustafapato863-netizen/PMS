# Phase 1: Baseline and Runtime Environment Audit

**Document Version:** 1.0  
**Date:** 10 November 2026  
**Status:** Audit Verified — Read-Only Baseline  
**Scope:** Phase 1 Deliverable for PMS AI Evidence-First Upgrade ([Implementation Plan](file:///D:/Projects/PMS_Dashboard/docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md))

---

## 1. Candidate Environment Identity

This audit identifies the exact git tree, candidate commits, untracked artifacts, and runtime configuration before applying any Phase 3+ changes.

| Attribute | Value / Description | Verification Evidence |
| :--- | :--- | :--- |
| **Current Branch** | `feat/pms-ai-all-departments-upgrade` | `git status` / `git branch --show-current` |
| **Candidate HEAD SHA** | `b1c4c519` (`feat(ai): add evidence-grounded PMS workspace and trends`) | `git rev-parse HEAD` |
| **Base Commit SHA** | `339cbf30` (`Merge pull request #83 from mustafapato863-netizen/cursor/pms-ai-phase0-eval-prep-f61e`) | `git merge-base HEAD main` |
| **Working Tree State** | Tracked files: Clean (`nothing added to commit but untracked files present`). Untracked evaluation artifacts preserved. | `git status` |
| **Deployment State** | Local development candidate; not deployed to production. Feature toggle `ai_enabled` is inactive. | Database inspection of `product_settings` |

### Untracked Files Inventory (Preserved)
The following untracked files in the working directory contain valuable evaluation baselines, schemas, and implementation guides, and have been deliberately preserved without resets, stashes, or overwrites:
1. `docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md` (Implementation roadmap and phase criteria)
2. `evaluation/pms-ai/phase0/results/rules_only_339cbf30_dirty_7ce5807bd71d.json` (Phase 0 run traces)
3. `evaluation/pms-ai/phase0/results/rules_only_339cbf30_dirty_7ce5807bd71d.summary.json` (Phase 0 summary: 50 passed, 86 ungraded)
4. `evaluation/pms-ai/phase0/results/rules_only_339cbf30_dirty_e15d47df32a7.json` (Phase 0 run traces)
5. `evaluation/pms-ai/phase0/results/rules_only_339cbf30_dirty_e15d47df32a7.summary.json` (Phase 0 summary)
6. `evaluation/pms-ai/phase0/results/rules_only_339cbf30_dirty_edec9fdb9154.json` (Phase 0 run traces)
7. `evaluation/pms-ai/phase0/results/rules_only_339cbf30_dirty_edec9fdb9154.summary.json` (Phase 0 summary)

---

## 2. Runtime Configuration and Safety Gates

### 2.1 Feature Gates & Authorization
- **Product Gate (`ai_enabled`):**
  - Stored in table `product_settings` with primary key `key = 'ai_enabled'`.
  - Default: `enabled = False` (`server_default = false()`).
  - Enforcement: Checked by `require_ai_enabled()` in [`feature_gate.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/feature_gate.py). When off, all API calls to `/api/ai/*` return HTTP `403 Forbidden` (`detail="AI assistant features are currently disabled by system administrator."`).
- **Role Gate (`require_ai_admin`):**
  - Enforcement: Checked by `require_ai_admin()` in [`feature_gate.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/feature_gate.py).
  - Rule: `current_user.role == "Admin"`. Any non-admin role (e.g. Employee, Team Leader, Regional Manager) receives HTTP `403 Forbidden` (`detail="AI assistant access is restricted to Administrators during this pilot phase."`).
- **Data Mutability Boundary:**
  - Read-only tools only. No write, update, delete, or arbitrary SQL endpoints exist for the model.
  - Action proposals require explicit UI-based user confirmation and standard PMS authorization.

### 2.2 Environment Variables & Provider Configuration
- `PMS_AI_LLM_BASE_URL`: Default `http://pms-qwen-pilot:8080/v1` (or unset).
- `PMS_AI_LLM_MODEL`: Default `qwen3-4b-q4_k_m`.
- `PMS_AI_INTENT_PROVIDER`: `local_model` or `local_rules` (fallback).
- `PMS_AI_SYNTHESIS_PROVIDER`: `local_model` or `deterministic` (fallback).
- `APP_ENV`: Gating variable. When `APP_ENV=production`, `local_data_explorer.py` explicitly disables exploration and forces strict deterministic boundaries.
- `LOCAL_DATA_EXPLORATION_ENABLED`: Boolean switch for exploratory bounded tool usage.

---

## 3. Model Reachability and Inference Audit

An empirical health check was executed against the configured model endpoint using `check_model_health()` in [`llm_client.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/llm_client.py).

### Health Check Diagnostics
```json
{
  "configured_model": "qwen3-4b-q4_k_m",
  "endpoint_configured": true,
  "endpoint_host": "pms-qwen-pilot",
  "available": false,
  "inference_verified": false,
  "reason": "timeout"
}
```

### Local Host Environment Audit
- **Port 18080 & Port 11434:** No active listener.
- **Port 8080:** Occupied by host system process `AgentService.exe` (unrelated service). Read-only `GET /v1/models` against port 8080 times out.
- **Docker Desktop:** Offline / not available on local Windows host.
- **Audit Conclusion:** Live Qwen inference is currently **unreachable/offline** in this local checkout. In accordance with project instructions:
  - No model process was started or downloaded.
  - Live model execution is marked **BLOCKED** for local evaluation.
  - Deterministic rules fallback is active and auditable.
  - No synthetic or mock output was masqueraded as live Qwen generation.

---

## 4. Test Suite Inventory and Categorization

The PMS AI test suite was cataloged by methodology to distinguish synthetic unit checks from live source-parity verification:

| Test Category | Files / Suites | Count | Description / Evidence Value |
| :--- | :--- | :--- | :--- |
| **Synthetic / Mocked Unit Tests** | [`Backend/tests/test_ai_booking_comparisons.py`](file:///D:/Projects/PMS_Dashboard/Backend/tests/test_ai_booking_comparisons.py)<br>[`Backend/tests/test_ai_workspace.py`](file:///D:/Projects/PMS_Dashboard/Backend/tests/test_ai_workspace.py)<br>[`Backend/tests/test_ai_conversation_v2.py`](file:///D:/Projects/PMS_Dashboard/Backend/tests/test_ai_conversation_v2.py) | 75 passed | Validates internal routing, data structures, and edge-case handling using in-memory SQLite fixtures. Demonstrates code execution, **not source-parity**. |
| **Browser / E2E Tests** | `Frontend/tests/pms-ai.spec.ts`<br>`Frontend/src/features/pmsAi/__tests__/` | 47 passed | Validates UI rendering, filter selections, message list state, and Admin role display in Next.js frontend. |
| **Independent Source-Parity Tests** | None | 0 verified | **GAP:** No independent test suite currently reconciles model/tool output against production database ground truth or verified owner spreadsheets. |
| **Live Qwen Inference Tests** | `evaluation/pms-ai/run_qwen_evaluation.py` | 0 executed | **BLOCKED:** Live Qwen inference is unreachable locally (timeout to `pms-qwen-pilot`). |

---

## 5. Audit of Phase 0 Baseline (`baseline.json`)

An exhaustive audit of the Phase 0 evaluation baseline was conducted using the frozen benchmark artifacts in `evaluation/pms-ai/phase0/`:

### 5.1 Headline Metrics vs Actual Denominators
- **Total Questions in Dataset:** 136 (55 Frozen V0, 81 Heldout V0).
- **Reported Result:**
  - **Passed:** 50
  - **Ungraded:** 86
  - **Failed:** 0

### 5.2 Critical Baseline Findings
1. **Zero Performance Records in Test Database:**
   The evaluation script `run_rules_only_baseline.py` ran against an isolated, freshly created SQLite database with **zero `performance_records`** populated.
2. **Zero Model Inference Turns Attempted:**
   The run was executed strictly in `rules_only` mode (`attempted_model_turns = 0`). Qwen was never invoked.
3. **What Actually Passed:**
   The 50 passes consisted entirely of:
   - Non-Admin access denials (`403 Forbidden`).
   - Sample-data warning guardrails when `is_fallback_data=True`.
   - Neutral greeting offers ("Hello! How can I help you today?").
   - Prompt injection and system prompt leak refusals.
4. **What Remained Ungraded:**
   All **86 domain performance questions** (e.g. asking for top agents, booking rates, branch comparisons, 6-month trends, or KPI drag) received an `UNGRADED` status because no data existed in the database and no model generated an answer.
5. **Conclusion:**
   The Phase 0 baseline is a **behavioral security and gateway benchmark**, not a measure of analytical accuracy or department coverage. No factual correctness claim can be made based on the 50 passes.
