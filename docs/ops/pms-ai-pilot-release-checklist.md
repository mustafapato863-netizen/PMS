> [!NOTE]
> **OPERATIONAL RELEASE CHECKLIST**
> This checklist enforces the default-off invariant, RBAC isolation, and emergency kill switches for the AI assistant.
> Reconciled with the active transition under [PMS AI Model-Led Implementation Plan](../plans/PMS_AI_MODEL_LED_IMPLEMENTATION_PLAN.md).

# PMS AI Pilot Release Checklist (Phase 9 — #103)

> [!IMPORTANT]
> **Default-off invariant:** Both `ai_enabled` (standalone chat) and `ai_corrective_action_pilot_enabled` (Admin corrective-action suggestion pilot) **MUST remain `false`** in code, migrations, seeders, Compose files, and production until all human gates below are explicitly marked `APPROVED`.

## 1. Pre-Flight Automated Readiness Gate

Run the strictly read-only rehearsal verifier (zero database writes, zero network token burn):

```bash
python scripts/verify_ai_pilot_readiness.py --in-process --json-out evaluation/pms-ai/phase9/readiness_rehearsal_report.json
```

For a running staging/production URL (strictly read-only HTTP checks; supply short-lived bearer tokens via environment variables only):

```bash
PMS_READINESS_ADMIN_BEARER="<token>" python scripts/verify_ai_pilot_readiness.py --base-url https://<pms-backend-host>
```

Expected assertions:
- `technical_gates_passed == true`
- `flags_default_off.ai_enabled == false` and `flags_default_off.ai_corrective_action_pilot_enabled == false`
- `rbac_isolation.passed == true` (`401` anonymous, `403` non-Admin across `/api/ai/*`)
- `diagnostics_truthfulness_and_secret_scan.secret_findings == []`
- `bounded_concurrency_and_timeout_fallback.concurrent_live_verify_status == 429`
- `pilot_ready_for_rollout == false` until blocking human gates (`#97`, `Vi`) are cleared.

## 2. Emergency 1-Command Kill Switch

Disable the corrective-action pilot immediately via authenticated Admin API call (persisted in `product_settings` and audited):

```bash
curl -fsS -X PUT "https://<pms-backend-host>/api/settings/ai-corrective-action-pilot" \
  -H "Authorization: Bearer <ADMIN_JWT>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

To also guarantee standalone chat remains off:

```bash
curl -fsS -X PUT "https://<pms-backend-host>/api/settings/ai-assistant" \
  -H "Authorization: Bearer <ADMIN_JWT>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

Or SQL fail-safe directly against PostgreSQL (`product_settings`):

```sql
UPDATE product_settings
SET enabled = FALSE, updated_at = NOW()
WHERE key IN ('ai_enabled', 'ai_corrective_action_pilot_enabled');
```

## 3. Dokploy Environment & Deployment Rollback

1. **Application-level env kill switch** (Dokploy service `performance-managment-system-backend-pwhfoc`):
   - Set `PMS_AI_CLOUDFLARE_ENABLED=false`
   - Set `PMS_AI_GEMINI_ENABLED=false`
   - Set `PMS_AI_INTENT_ENABLED=false`
   - Set `PMS_AI_SYNTHESIS_ENABLED=false`
   - Set `PMS_AI_EXPLORATION_ENABLED=false`
   - Set `PMS_AI_LIVE_VERIFY_ENDPOINT_ENABLED=false`
   - Clear `CLOUDFLARE_API_TOKEN` / `CF_API_TOKEN` / `CLOUDFLARE_API_KEY` and `GEMINI_API_KEY` / `GOOGLE_API_KEY` if full external provider cutoff is desired, then **Redeploy** in Dokploy.
2. **Container image rollback**:
   - In Dokploy -> `performance-managment-system-backend-pwhfoc` -> Deployments, select the prior known-good `main` deployment SHA and trigger **Rollback / Redeploy**.
   - Verify `/api/health` returns `200` and `/api/ai/diagnostics` confirms `feature_enabled: false` and `inference_verified: false`.

## 4. Staged Rollout Governance (Stages 1–4)

| Stage | Scope | `ai_corrective_action_pilot_enabled` | `ai_enabled` | Entry Criteria | Exit / Hold Criteria |
|---|---|---|---|---|---|
| **Stage 1 — Dark Launch (Current)** | Code merged, switches off | `false` | `false` | `verify_ai_pilot_readiness.py` passes + `#101`/`#102`/`#103` CI green | Any RBAC/403/secret scan failure |
| **Stage 2 — Admin Canary Pilot** | Admin-only corrective-action drafts (`#98`) | `true` (explicitly toggled by Admin after sign-off) | **`false`** (kept off) | `#97` live verification passed + **Vi** Phase 9 sign-off | Error rate >5%, any `429` storm, PII quarantine alert, or Admin thumbs-down cluster |
| **Stage 3 — Governance & Feedback Review** | Admin feedback review (`#101`) + export bundles (`n >= 5`) | `true` | **`false`** (kept off) | >= 20 reviewed pilot traces with zero fabricated-fact incidents | Any `accepted_fabricated_facts > 0` or `cross_scope_disclosures > 0` |
| **Stage 4 — Post-Pilot Decision** | Separate Phase 10+ governance decision | Reviewed | **`false`** unless separately approved | Dedicated leadership/product sign-off after Stage 3 report | Any unresolved safety or accuracy gate |

> [!CAUTION]
> Standalone chat (`ai_enabled`) **stays `false`** throughout Stages 1–4 of the corrective-action pilot.

## 5. Human Sign-Off Table (Blocking Release Gates)

| Gate ID | Reference | Owner | Status | Verification Evidence | Date |
|---|---|---|---|---|---|
| Live Provider & Production Credentials Attestation | Issue `#97` | Admin / DevOps | `PENDING` | Live Cloudflare + Gemini check under `#97` | — |
| Phase 6 Feedback Governance & Export Gate | Issue `#101` | Engineering / Reviewer | `PENDING` (PR Review) | `test_ai_phase6_feedback_governance.py` | — |
| Phase 7–8 Comparative Eval & Model Decision (Option A) | Issue `#102` | Engineering / Reviewer | `PENDING` (PR Review) | `evaluation/pms-ai/phase7/COMPARATIVE_EVAL_REPORT.md` | — |
| **Phase 9 Final Pilot Release Approval** | **Issue `#103`** | **Vi** | **`PENDING`** | **Explicit written sign-off by Vi** | — |
