# Phase 8 Gate Decision: Model Training & Architecture Selection

- **Decision Date:** 2026-11-15
- **Selected Option:** **Option A — Retain `UnifiedProviderEngine` (Cloudflare Workers AI `@cf/ibm-granite/granite-4.0-h-micro` primary + Google Gemini `gemini-2.5-flash` fallback) with Deterministic PMS Evidence & Claim-Ledger Validation; Defer LoRA / QLoRA Fine-Tuning.**

## Decision Rationale

1. **Zero Safety & Grounding Regressions Without Training:**
   - All numeric facts, KPI values, rankings, scopes, and corrective-action uncertainty statements are computed deterministically in PMS backend services (`CorrectiveActionEvidenceService`, `claim_validator.py`, `PmsAiOrchestrator`).
   - Corrective-action draft generation enforces a closed imperative verb and word allow-list (`validate_model_draft` in `Backend/services/ai/corrective_action_drafter.py`), preventing invented numbers, causal claims, or disciplinary actions (`Coaching`, `Training`, `Monitor` only).
   - Both `rules-only` and `scripted-provider` (`scripted_mocked`) evaluations record:
     - `accepted_fabricated_facts = 0`
     - `cross_scope_disclosures = 0`
     - `unconfirmed_action_writes = 0`

2. **Infrastructure & Operational Constraints (8 GB KVM 2 VPS):**
   - Training or hosting a second local model / LoRA adapter on the 8 GB KVM 2 production VPS is strictly prohibited and unnecessary given managed Cloudflare Workers AI primary inference and Gemini fallback.
   - Any future LoRA/QLoRA experiment would require an off-box GPU host and must never run on KVM 2.

3. **Unresolved Owner Sign-Offs & Post-Pilot Evidence Gate:**
   - Phase 0 expected-value owner sign-offs (`#97`) remain `PENDING` for unsigned `frozen_v1` / `heldout_v1` cases.
   - Phase 6 (`#101`) establishes a privacy-preserving, Admin-approved, k>=5 cohort-anonymized feedback export pipeline (`GET /api/ai/feedback/export-bundle`). Fine-tuning is not justified before collecting real Admin-approved pilot feedback demonstrating residual model-layer failures that prompt/tool fixes cannot resolve.

## Revisit Criteria (When to Trigger Off-Box LoRA Evaluation)

Re-open Phase 8 training evaluation **only if all** of the following are met:
1. Phase 0 owner sign-offs (`#97`) and Phase 9 Admin corrective-action pilot (`#103`) have completed initial observation.
2. Admin-approved, k>=5 de-identified Phase 6 feedback clusters show persistent model-layer failures after prompt/vocabulary/tool fixes.
3. Training runs exclusively off-box (never on KVM 2) using only Admin-reviewed, PII-quarantine-clean exports (`GET /api/ai/traces/export?verified_only=true` / `GET /api/ai/feedback/export-bundle?approved_only=true`).
