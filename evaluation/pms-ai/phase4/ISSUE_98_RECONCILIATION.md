# Issue #98 Reconciliation: Contextual Corrective-Action Suggestion Drafter & Validation API

**Issue:** `#98` — `[Wave 2][PR-4] Qwen Contextual Corrective-Action Suggestion Drafter & Validation API`  
**Status:** Reconciled to Unified Cloudflare-Primary / Gemini-Fallback Architecture (merged on `main` at `ce238bba`)  
**Phase 4 Cleanup:** Updated `Backend/api/routers/ai_corrective_actions.py` `model_unavailable` message to provider-neutral wording (`"The AI suggestion service is temporarily unavailable. Retry later or enter the action manually."`).

---

## Executive Summary

Issue #98 originally targeted a local `llama_cpp` / Qwen runtime (`provider_used: "llama_cpp" | "deterministic" | "none"`). During Phases 1–3, PMS AI migrated to `UnifiedProviderEngine` (`Backend/services/ai/provider_engine.py`) with **Cloudflare Workers AI** (`@cf/ibm-granite/granite-4.0-h-micro`) as the primary provider and **Google Gemini** (`gemini-2.5-flash`) as the automatic fallback for transient errors/rate limits (while keeping safety refusals terminal).

All core safety, gating, read-only, evidence-binding, closed-vocabulary validation, and human-in-the-loop (HITL) requirements of Issue #98 are fully implemented and preserved in the current `main` codebase.

---

## Deliverable & Constraint Mapping

| Issue #98 Deliverable / Constraint | Current Merged Implementation | Notes / Architectural Delta |
|---|---|---|
| Request/response schemas in `Backend/models/ai_schemas.py` (`AiCorrectiveActionSuggestionRequest`, `AiCorrectiveActionSuggestionPayload`, `AiCorrectiveActionSuggestionResponse`, `AiCorrectiveActionSuggestionDraft`) | Implemented in `Backend/models/ai_schemas.py` (lines 336–460) | `CorrectiveActionSuggestionProvider` uses `Literal["cloudflare", "gemini", "deterministic", "none"]` instead of `"llama_cpp"`. `outcome` adds explicit `"draft_rejected"` alongside `"suggested"`, `"insufficient_evidence"`, `"model_unavailable"`. `read_only: Literal[True]` and `requires_human_confirmation: Literal[True]` enforced. |
| Drafter service (`Backend/services/ai/corrective_action_drafter.py`) | `CorrectiveActionDrafter` & `generate_corrective_action_suggestion` | Replaced `llm_client.chat_completion` (`llama_cpp`) with `get_unified_provider_engine().generate(...)` (`cloudflare` primary, `gemini` fallback). Preserves `read_only_session(self.db)` + `release_read_transaction(self.db)` before provider calls, deterministic focus KPI selection, and zero-LLM short-circuit on insufficient evidence. |
| Closed-vocabulary & strict draft validator (`validate_model_draft`) | Implemented in `Backend/services/ai/corrective_action_drafter.py` (lines 278–422) | Enforces allow-listed `ALLOWED_DRAFT_ACTION_TYPES` (`"Coaching"`, `"Training"`, `"Monitor"` — never `PIP`/`Warning`/`Reward`/`Promotion`), `STEP_START_VERBS` + `STEP_VOCABULARY` + request `evidence_vocabulary`, strict JSON schema, ASCII-only text, zero digits/number words, and `_FORBIDDEN_PATTERNS` blocking causes, employment facts, owner assignments, dates/deadlines, approval claims, disciplinary escalations, financial claims, and prompt-injection echoes. Never substitutes a static draft when rejected (`outcome="draft_rejected"`, `draft=None`). |
| Untrusted input sanitization & zero-PII outbound payload | `_safe_label`, `_KNOWN_PRIOR_ACTION_TYPES`, `_KNOWN_PRIOR_STATUSES`, `_INSTRUCTION_LIKE_RE` | Drops free-text prior action notes, root causes, employee names, employee IDs, country/region codes, owners, and due dates from `ProviderRequest`. Only sanitized function/team/position/level/period, focus KPI numbers/direction, other below-target KPI names, and allow-listed prior action types/statuses reach the provider. |
| Router (`Backend/api/routers/ai_corrective_actions.py`) mounted in `Backend/api/routers/__init__.py` | `POST /api/ai/corrective-action-suggestions` mounted via `ai_corrective_actions_router` | Enforces `require_ai_diagnostic_session`, `require_ai_admin`, `require_ai_corrective_action_pilot_enabled`, and authoritative `require_authenticated_scope` Admin check + service-level `PermissionError` (`403`) / `ValueError` (`422`). Independent of `ai_enabled`. |
| Never saves or mutates `Action` rows | Enforced in `CorrectiveActionEvidenceService`, `CorrectiveActionDrafter`, and `ai_corrective_actions.py` | `read_only_session` wraps DB reads; `approval_status="unapproved_draft"` and `requires_human_confirmation=True`. Saving remains in the existing corrective-action workflow (`EmployeeActionModal.tsx` / `CorrectiveActionService`). |
| Provider-neutral user-facing messages | Updated in `Backend/api/routers/ai_corrective_actions.py` line 51 | Replaced legacy `"The local AI model is unavailable..."` with `"The AI suggestion service is temporarily unavailable. Retry later or enter the action manually."`. |
| Automated tests & inventory sync | `Backend/tests/test_ai_corrective_action_drafter.py` + `Backend/tests/test_ai_corrective_action_drafter_unified.py` | Unit/API tests updated to mock `UnifiedProviderEngine` (`cloudflare` primary, `gemini` fallback, terminal safety refusal, closed-vocabulary rejection, RBAC 401/403, real-zero vs missing `None`, zero DB writes, zero PII leakage). Live model tests remain gated behind `PMS_AI_RUN_LIVE_MODEL_TESTS=true`. |
