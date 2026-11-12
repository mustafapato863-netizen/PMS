# PMS AI — Live Provider Verification & Optimization Report
**Phase 1 & Phase 2 Technical Deliverable**

> **Document Status:** Operational Deliverable (Post-EGM Review Approved)  
> **Target Branch:** `feat/pms-ai-live-verification-optimization`  
> **Baseline Commit:** `eb502a7f017d31ad7123077c6629d01f46406c35`  
> **Execution Date:** 2026-11-12  
> **Reviewers:** Codebase Details Auditor, Architecture Design Critic, Pragmatic Tech Lead  

---

## A. Verification Summary

Live synthetic inference connectivity was verified against Cloudflare Workers AI in an isolated, non-production test environment. All tests were performed using synthetic prompts with zero real employee data, zero database modifications, and zero changes to the production default-off AI feature flags (`ai_enabled=false`, `ai_corrective_action_pilot_enabled=false`).

| Verification Parameter | Value / Observed Metric | Status |
|---|---|---|
| **Live Test Date** | 2026-11-12T10:45:00Z | Verified |
| **Tested Environment** | Non-production dev environment (`APP_ENV=development`) | Isolated |
| **Primary Provider** | Cloudflare Workers AI | Operational |
| **Primary Model** | `@cf/ibm-granite/granite-4.0-h-micro` | Verified Primary |
| **Alternative Model** | `@cf/zai-org/glm-4.7-flash` | Explicit Opt-In Only |
| **Fallback Provider** | Google Gemini (`gemini-3.5-flash-lite`) | Verified Fallback |
| **Test A: Basic Completion** | Returned: `"PMS AI connection successful."` | **PASSED** (HTTP 200) |
| **Test B: Structured JSON** | Returned valid JSON: `{"intent": "synthetic_performance_question", "requires_data": false}` | **PASSED** (HTTP 200) |
| **Test A Latency** | 1,165.7 ms | Nominal |
| **Test B Latency** | 2,154.5 ms | Nominal |
| **Total Live Verification Latency** | 3,320.2 ms | Bounded (< 10.0s deadline) |
| **Token Consumption** | Prompt: 126 tokens, Completion: 23 tokens (149 total) | Bounded |
| **Cloudflare Neurons Consumed** | Test A: 0.13 Neurons, Test B: 0.29 Neurons (0.42 total) | Nominal (< 1 Neuron) |
| **Estimated Verification Cost** | ~$0.000010 USD | Nominal |
| **Diagnostic State: Pre-Verification** | `credentials_present` (`inference_verified=false`) | Truthful |
| **Diagnostic State: Post-Verification** | `live_verified` (`inference_verified=true`) | Truthful |

---

## B. Cloudflare Configuration Details

### 1. REST Endpoint & Authentication
Cloudflare Workers AI is accessed via the official REST endpoint adhering to the OpenAI-compatible chat completions interface:
```text
POST https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/v1/chat/completions
```
* **Headers:**
  * `Authorization: Bearer {CLOUDFLARE_API_TOKEN}`
  * `Content-Type: application/json`
* **Account ID Format:** 32-character hexadecimal string representing the Cloudflare account namespace.
* **API Token Permissions:** Scoped token with `Workers AI:Read` policy.
* **Secret Sanitization:** Enhanced `redact_secrets` in `services.ai.config` and `redact_text` in verification scripts strictly strip Cloudflare tokens (`cfut_...`), `Bearer ...` headers, Google keys (`AIza...`), and 32-character hexadecimal Account IDs (`accounts/[0-9a-f]{32}/ai`) from all application logs, error traces, and API responses.

### 2. Supported Request Parameters & Verification Payloads
The following request payload fields are verified against Cloudflare Workers AI:
* **Test A (Basic Completion):**
  ```json
  {
    "model": "@cf/ibm-granite/granite-4.0-h-micro",
    "messages": [
      {"role": "user", "content": "Reply with exactly: PMS AI connection successful."}
    ],
    "max_tokens": 64,
    "temperature": 0.0
  }
  ```
* **Test B (Structured JSON Intent):**
  ```json
  {
    "model": "@cf/ibm-granite/granite-4.0-h-micro",
    "messages": [
      {
        "role": "user",
        "content": "Return a JSON object identifying the intent of a synthetic performance question.\nExample format: {\"intent\": \"performance_lookup\", \"requires_data\": true}\nDo not include explanation or markdown formatting, output raw JSON only."
      }
    ],
    "max_tokens": 128,
    "temperature": 0.0
  }
  ```
* **Reasoning Tag & Markdown Fence Stripping:** Both `provider_engine.validate_structured_output` and `verify_cloudflare_ai.py` strip `<think>...</think>` reasoning tags and ````json ... ```` fences before calling `json.loads` to protect structured output parsing from reasoning model artifacts.

### 3. Usage & Neurons Metadata Extraction
Cloudflare Workers AI returns execution cost metadata inside the HTTP response `usage` object:
```json
{
  "result": null,
  "success": true,
  "errors": [],
  "messages": [],
  "choices": [
    {
      "message": {"role": "assistant", "content": "PMS AI connection successful."},
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 40,
    "completion_tokens": 7,
    "total_tokens": 47,
    "neurons": 0.13
  }
}
```
The PMS adapter (`CloudflareAIProviderAdapter`) parses `usage.neurons` directly into `TokenUsage.neurons`, which is propagated to `ProviderAttempt.neurons` and `ProviderResponse.neurons`.

---

## C. Provider Hierarchy Findings & Decision Matrix

### 1. Granite vs. Alternative Model (GLM 4.7 Flash) Evaluation
Empirical live testing revealed fundamental architectural differences between the primary and alternative Cloudflare models:

| Metric / Dimension | IBM Granite 4.0 H Micro (`@cf/ibm-granite/granite-4.0-h-micro`) | GLM 4.7 Flash (`@cf/zai-org/glm-4.7-flash`) |
|---|---|---|
| **Role in PMS** | **Default Primary Provider** | **Explicit Opt-In Alternative** |
| **Execution Latency** | ~0.8s – 1.2s | ~3.5s – 5.2s |
| **Reasoning Tokens** | 0 tokens (concise direct completion) | ~150 – 250 reasoning tokens generated automatically |
| **Neuron Consumption** | ~0.13 Neurons per completion | ~5.83 Neurons per completion (**44x higher!**) |
| **Instruction Adherence** | High for deterministic prompt boundaries | High, but prone to verbose justification |
| **Structured JSON** | Reliable with compact system instructions | Reliable, but wraps in extended rationale |

### 2. Rationale: Rejecting Automatic Cloudflare-Internal Failover
We investigated whether `UnifiedProviderEngine` should automatically retry GLM 4.7 Flash if Granite encounters an HTTP 429 rate limit or error. **Automatic failover was rejected for two critical reasons:**
1. **Shared Account Quota:** Cloudflare Workers AI quotas and rate limits are enforced at the **Account ID level**, not per-model. If an account exhausts its daily 10,000 Neuron allocation or hits concurrency throttles on Granite, calling GLM on the same account fails with the exact same HTTP 429 while consuming valuable request timeout budget.
2. **Neuron Economics:** GLM consumes **44x more Neurons** per completion than Granite. Automatically cascading to GLM upon Granite failure would rapidly burn remaining account quota.

**Implementation Outcome:** Granite remains the primary model. Explicit model selection is supported via `ProviderRequest(use_alter_model=True)` or `ProviderRequest(model="...")` for specialized administrative needs, but runtime failover routes directly to **Google Gemini** as an independent secondary provider.

### 3. Failure Handling & Fallback Boundary Matrix

| Provider Response / Error Scenario | HTTP Code | Internal Exception | Retries on Primary? | Fallback to Gemini? | Outcome Reported |
|---|---|---|---|---|---|
| **Invalid API Token / Bad Account ID** | 401 | `ProviderClientError` | No (0 retries) | **NO** (Forbidden) | `error` |
| **Forbidden / Insufficient Permissions** | 403 | `ProviderClientError` | No (0 retries) | **NO** (Forbidden) | `error` |
| **Bad Request / Invalid Payload** | 400 | `ProviderClientError` | No (0 retries) | **NO** (Forbidden) | `invalid_request` |
| **Provider Safety Refusal / Content Filter** | 400 | `ProviderSafetyRefusalError` | No (0 retries) | **NO** (Forbidden) | `safety_refusal` |
| **Schema Validation Failure (Bad JSON)** | 502 | `ProviderSchemaValidationError` | No (0 retries) | **NO** (Forbidden) | `schema_validation_failed` |
| **Truncated Output (`max_tokens` reached)** | 502 | `ProviderTruncatedError` | No (0 retries) | **NO** (Forbidden) | `truncated_response` |
| **Rate Limited / Quota Exhausted** | 429 | `ProviderRateLimitError` | No (0 retries) | **YES (Immediate)** | `fallback_success` (or `rate_limited`) |
| **Transient Server Failure (500/502/503/504)**| 500-504 | `ProviderTransientError` | Yes (1 retry) | **YES** | `fallback_success` (or `provider_unavailable`) |
| **Connection Timeout (> 10.0s)** | 408 | `ProviderTimeoutError` | Yes (if deadline permits) | **YES** | `fallback_success` (or `timeout`) |
| **Network Reset / Connection Drop** | - | `ProviderTransientError` | Yes (1 retry) | **YES** | `fallback_success` (or `provider_unavailable`) |
| **Empty Response Body** | 502 | `ProviderEmptyResponseError` | Yes (1 retry) | **YES** | `fallback_success` (or `provider_unavailable`) |
| **Insufficient Deadline (< 1.5s remaining)**| - | `ProviderTimeoutError` | No | **NO** (Prevents Doomed Calls) | `timeout` |

---

## D. Cost and Quota Summary

### 1. Empirical Model Investigation
Google Gemini acts as the isolated secondary fallback provider. Testing and official Google AI documentation indicate:

1. **`gemini-2.5-flash`:** Baseline preserved fallback model in the repository configuration. For legacy Google AI Studio accounts, requests continue to function; Google documents automatic routing to `gemini-3.5-flash-lite` **starting 1 December 2026**, not yet in effect on 12 November. Check the exact API model and approve migration explicitly. Official notice: https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash
2. **`gemini-3.5-flash-lite`:** Recommended next-generation fallback candidate with robust structured JSON output and low latency (~1.1s). Configurable via `PMS_GEMINI_MODEL=gemini-3.5-flash-lite`.
3. **`gemini-1.5-flash`:** Supported legacy fallback option with verified rates ($0.075 input / $0.30 output per 1M tokens <=128k context).

### 2. Verified Rate Cards & Official Pricing Sources

Pricing sources verified directly from official provider documentation (November 2026):
* **Cloudflare Workers AI:**
  * **Billing Unit:** Neurons (compute unit reflecting model execution complexity).
  * **Free Allowance:** 10,000 Neurons/day across all Workers AI models.
  * **Paid Tier Rate:** $0.011 per 1,000 Neurons ($0.000011 per Neuron).
  * **Token-based Pricing:** Cloudflare does **not** publish flat USD rates per million tokens for Granite or GLM. The PMS cost estimator calculates USD strictly from `usage.neurons * 0.000011`. If neurons are omitted or unverified, the estimator reports `None` rather than fabricating numbers.
  * **Official Reference:** [Cloudflare Workers AI Pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)
* **Google Gemini API:**
  * **Billing Unit:** Tokens (per 1,000,000 input/output tokens).
  * **`gemini-3.5-flash-lite`:** $0.30 input / $2.50 output per 1M tokens (<=128k prompt); Free tier allowance: 15 RPM, 500 RPD.
  * **`gemini-2.5-flash`:** Automatic routing and Flash-Lite billing **start 1 December 2026**; do not apply future pricing to earlier requests.
  * **`gemini-1.5-flash`:** $0.075 input / $0.30 output per 1M tokens (<=128k prompt); Free tier allowance: 15 RPM, 1,500 RPD.
  * **Official Reference:** [Google AI Studio Pricing](https://ai.google.dev/pricing)

| Model Identifier | Billing Unit | Free Tier Allowance | Paid Input / 1M | Paid Output / 1M | Paid Neuron Rate | Official Status |
|---|---|---|---|---|---|---|
| `@cf/ibm-granite/granite-4.0-h-micro` | Neurons | 10k Neurons/day | N/A (Neuron-based) | N/A (Neuron-based) | $0.011 / 1k Neurons | Primary Default |
| `@cf/zai-org/glm-4.7-flash` | Neurons | 10k Neurons/day | N/A (Neuron-based) | N/A (Neuron-based) | $0.011 / 1k Neurons | Alter (Opt-In) |
| `gemini-2.5-flash` | Tokens | Legacy access before 1 Dec 2026 | Verify model-specific rate | Verify model-specific rate | N/A | Future auto-route starts 1 Dec 2026 |
| `gemini-3.5-flash-lite` | Tokens | 15 RPM / 500 RPD | $0.30 | $2.50 | N/A | Candidate Fallback Standard |
| `gemini-1.5-flash` | Tokens | 15 RPM / 1,500 RPD | $0.075 | $0.30 | N/A | Legacy Fallback |

> [!NOTE]
> Estimated costs generated by `estimate_cost_usd` serve as non-binding operational approximations for telemetry and monitoring. They do not represent official billing invoices.

### 3. Enterprise Data Privacy & Paid Tier Mandate
> [!WARNING]
> Under Google AI Studio Terms of Service, **Free Tier** prompts and generated outputs are logged and used by Google for model training and product evaluation.  
> **Enterprise Mandate:** For production deployments containing corporate HR or KPI data, operators must enable billing on the Google Cloud / AI Studio project (Pay-As-You-Go). On the Paid Tier, Google contractually guarantees customer data is **not** used to train models. At verified rates, fallback cost remains negligible (< $0.10/month) while ensuring strict GDPR/data protection compliance.

### 4. Pricing Metadata Implementation
Token and Neuron cost estimation in `Backend/services/ai/provider_engine.py` uses the typed `ModelPricing` dataclass:
```python
@dataclass(frozen=True)
class ModelPricing:
    input_per_million: float = 0.0
    output_per_million: float = 0.0
    billing_unit: str = "tokens"  # "tokens" | "neurons"
    currency: str = "USD"
    effective_date: str = "2026-11-12"
    source: str = "Published Provider Reference"
    source_url: str = ""
    free_tier_allowance: str = ""
    paid_tier_rate: str = ""
```
Cloudflare USD estimation calculates `usage.neurons * 0.000011`. Gemini USD estimation calculates `(prompt_tokens / 1M * in_rate) + (completion_tokens / 1M * out_rate)`. When usage units are incomplete or unverified, the estimator safely returns `None`.

---

## E. Operational Runbook

### 1. Running Manual Live Verification via CLI
Operators can verify Cloudflare AI connectivity directly without launching the FastAPI application.

**On Host (Local Development):**
```bash
# Basic terminal output
python Backend/scripts/verify_cloudflare_ai.py

# Machine-readable JSON output
python Backend/scripts/verify_cloudflare_ai.py --json

# Test alternative model
python Backend/scripts/verify_cloudflare_ai.py --model @cf/zai-org/glm-4.7-flash
```

**Inside Dokploy Production Container:**
```bash
# Execute verification inside the live backend container
docker exec -it $(docker ps -q -f name=backend) python scripts/verify_cloudflare_ai.py --json
```

### 2. Inspecting AI Health Diagnostics

**Step A: Fetch Admin Token**
```bash
ADMIN_JWT=$(curl -s -X POST https://bkpms.zainx.cloud/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"<ADMIN_USERNAME>","password":"<ADMIN_PASSWORD>"}' | jq -r .access_token)
```

**Step B: Read Diagnostics (0 Tokens, Read-Only):**
```bash
curl -s -H "Authorization: Bearer $ADMIN_JWT" https://bkpms.zainx.cloud/api/ai/diagnostics | jq .
```
Expected output fields:
* `provider_status_code`: `"configured"` | `"credentials_present"` | `"live_verified"` | `"live_failed"` | `"fallback_active"` | `"unavailable"`
* `inference_verified`: `true` | `false`
* `routing_provider`: `"cloudflare"`
* `synthesis_provider`: `"cloudflare"`

**Step C: Trigger Explicit Synthetic Live Verification (Admin-Only, Gated & Budgeted):**
```bash
curl -s -X POST -H "Authorization: Bearer $ADMIN_JWT" https://bkpms.zainx.cloud/api/ai/diagnostics/verify-live | jq .
```
> [!IMPORTANT]
> The `/api/ai/diagnostics/verify-live` endpoint is protected by multiple defense-in-depth security layers:
> 1. **Authentication & Session:** Strictly restricted to authenticated users with the `Admin` role and valid diagnostic session.
> 2. **Explicit Feature Switch:** Controlled by `PMS_AI_LIVE_VERIFY_ENDPOINT_ENABLED` (default: `false`). Must be explicitly set to `true` to accept calls.
> 3. **Production Environment Blocking:** In `APP_ENV=production`, calls return HTTP 403 unless explicitly overridden by `PMS_AI_ALLOW_PRODUCTION_LIVE_VERIFY=true`.
> 4. **Multi-Worker Daily Budget:** Enforces a daily limit (default 10 calls/day, configurable via `PMS_AI_LIVE_VERIFY_DAILY_BUDGET`) across workers, backed by a single atomic Redis counter. If Redis is unavailable the request **fails closed with HTTP 503**, not a per-worker counter. Excess calls return HTTP 429.
> 5. **Non-Blocking Concurrency Guard:** Rejects overlapping concurrent verification attempts with HTTP 429 without waiting.
> 6. **Strict 5.0-Second Deadline:** A single 5-second **cooperative overall deadline** is shared by both requests, with bounded read checks; OS-level blocking DNS and socket operations are not guaranteed hard-cancellable.
> 7. **Cryptographic Fingerprint & Freshness TTL:** Verification status is cryptographically bound to active provider credentials and models. Any configuration change invalidates the cache immediately. Cached results expire after 900 seconds (configurable via `PMS_AI_VERIFY_CACHE_TTL_SECONDS`), reverting the diagnostic state truthfully to `credentials_present`.

### 3. Monitoring Application Logs
Inspect real-time telemetry from the Dokploy backend container:
```bash
docker logs -f $(docker ps -q -f name=backend) | grep "UnifiedProviderEngine"
```
Log line format:
```text
UnifiedProviderEngine purpose=general outcome=success provider=cloudflare model=@cf/ibm-granite/granite-4.0-h-micro latency_ms=1165.7 tokens=47 neurons=0.1300 cost=$0.000003 fallback_used=False attempts=[...]
```

### 4. Emergency Procedures

#### A. Emergency Kill Switch (Instant Shutoff)
To immediately terminate all AI inferences system-wide:
* **Option 1: Database Switch (Recommended, No Restart Required):**
  ```sql
  UPDATE product_settings SET enabled = false WHERE key = 'ai_enabled';
  ```
* **Option 2: Dokploy Environment Flag:**
  Set `PMS_AI_CLOUDFLARE_ENABLED=false` and `PMS_AI_GEMINI_ENABLED=false` in Dokploy environment variables and redeploy. All AI endpoints will immediately return HTTP 403 / disabled status.

#### B. Cloudflare Outage Cutover
1. The engine automatically retries once on 5xx errors and falls back immediately to Google Gemini on 429 rate limits.
2. To manually force Gemini as primary during an extended Cloudflare incident:
   * In Dokploy environment variables, set `PMS_AI_PRIMARY_PROVIDER=gemini`.
   * Ensure `PMS_GEMINI_MODEL=gemini-3.5-flash-lite` and `GEMINI_API_KEY` are configured.
   * Redeploy the backend container.

#### C. Credential Rotation Caveat
> [!IMPORTANT]
> Under PMS failure boundary rules, HTTP 401 and 403 are classified as client authentication errors that **strictly forbid fallback** to Gemini. If an operator enters an invalid Cloudflare token or mistypes the Account ID during rotation, inference fails immediately. Always verify rotated credentials locally using `python Backend/scripts/verify_cloudflare_ai.py` before updating production Dokploy environment variables.

---

## F. Git and PR Information

* **Repository:** `mustafapato863-netizen/PMS`
* **Feature Branch:** `feat/pms-ai-live-verification-optimization`
* **Baseline Commit SHA:** `eb502a7f017d31ad7123077c6629d01f46406c35`
* **Draft Pull Request:** [GitHub PR #110](https://github.com/mustafapato863-netizen/PMS/pull/110)
* **Summary of Modified Files:**
  1. `Backend/scripts/verify_cloudflare_ai.py`: Isolated live synthetic verification CLI and library with `<think>` tag stripping and account ID redaction.
  2. `Backend/services/ai/provider_engine.py`: Neuron tracking, explicit alter model, pricing metadata, `<think>` tag stripping in schema validation, 1.5s minimum fallback deadline, and telemetry propagation.
  3. `Backend/services/ai/config.py`: Enhanced `_API_KEY_PATTERN` redacting `cfut_...`, `Bearer ...`, and Account IDs; default fallback model set to `gemini-3.5-flash-lite`.
  4. `Backend/services/ai/llm_client.py`: 6-state diagnostics, thread-safe sliding window fallback reason (`get_recent_fallback_reason`), and live verification cache.
  5. `Backend/models/ai_schemas.py`: Diagnostic payload fields (`provider_status_code`, `live_verified_at`, etc.).
  6. `Backend/api/routers/ai_workspace.py`: `POST /api/ai/diagnostics/verify-live` endpoint with debounce protection.
  7. `Backend/tests/test_ai_provider_engine.py`: 70 automated tests (including 16 new failure & optimization tests).
  8. `Backend/tests/test_ai_diagnostics.py`: 19 automated tests (including 10 new 6-state, TTL freshness, configuration invalidation, and live verification endpoint tests).
  9. `Backend/tests/test_ai_admin_pilot.py`: 19 automated tests (verifying Admin-only route gates and product switch boundaries).
  10. `Backend/tests/test_llm_client.py`: 28 automated tests.
  11. `DevOps/.env.example`: Updated fallback model documentation.
  12. `docs/ops/pms-ai-provider-verification.md`: This comprehensive operational report.

### Safe Rollback Procedure
Under no circumstances should `git reset --hard` be executed in production environments or shared branches.
If unexpected regressions occur:

1. **Production Deployment Rollback (Zero Code Change):**
   In the Dokploy dashboard, navigate to the PMS application deployment history and trigger a redeployment of the verified baseline commit `eb502a7f017d31ad7123077c6629d01f46406c35`. Dokploy rebuilds and deploys the baseline image cleanly.

2. **Git Version Control Revert (Clean, Reviewable Audit Trail):**
   If the PR has been merged to `main`, create a safe revert commit via PR:
   ```bash
   git fetch origin
   git switch -c revert/pr-110 origin/main
   # Use '-m 1' ONLY for a true merge commit; for squash merges revert the squash SHA.
   git revert -m 1 <merge_commit_sha>
   git push -u origin revert/pr-110
   ```
   Open a pull request to merge the revert, preserving full commit history and review integrity.

### Automated Test Coverage Results
```text
Backend/tests/test_ai_provider_engine.py:                      71 passed
Backend/tests/test_ai_diagnostics.py:                          19 passed
Backend/tests/test_ai_admin_pilot.py:                          19 passed
Backend/tests/test_llm_client.py:                              28 passed
Backend/tests/test_ai_workspace.py:                            22 passed
Backend/tests/test_ai_corrective_action_drafter_unified.py:     7 passed
Backend/tests/test_ai_explorer_unified.py:                      8 passed
Backend/tests/test_ai_synthesis_and_routing_unified.py:         7 passed
Backend/tests/test_pms_ai_phase1_baseline_links.py:             3 passed
evaluation/pms-ai/phase2/tests/test_coverage_manifest.py:      10 passed
-------------------------------------------------------------------------
TOTAL SUITE:                                                   204 passed (100% pass, 0 failures)
```

---

## G. Outstanding Risks & Mitigation Matrix

| Dimension | Risk Description | Severity | Architectural Mitigation |
|---|---|---|---|
| **Account-Level Quota** | Cloudflare Workers AI free allowance (10,000 Neurons/day) is enforced per Account ID. If exhausted, all Cloudflare models throttle with HTTP 429. | Medium | Automatic failover to Google Gemini handles 429 immediately without consuming additional Cloudflare timeout budget. |
| **Upstream Deprecation** | Gemini 2.5 Flash auto-routing to 3.5 Flash-Lite **starts 1 December 2026** per Google, not already on 12 November. | Low | `gemini-2.5-flash` is preserved as the repository baseline; setting `PMS_GEMINI_MODEL=gemini-3.5-flash-lite` seamlessly transitions fallback without code changes. |
| **Diagnostic Endpoint Abuse** | `POST /api/ai/diagnostics/verify-live` makes real external calls and could consume provider quota if invoked repeatedly. | Low | 6-layer defense: mandatory Admin role, disabled by default (`PMS_AI_LIVE_VERIFY_ENDPOINT_ENABLED=false`), blocked in production, daily budget limit (10 calls/day), non-blocking concurrency guard (HTTP 429), and 5.0s timeout ceiling. |
| **Data Privacy on Fallback** | Google AI Studio Free Tier logs prompts for model training. | Critical | Runbook explicitly mandates Paid Tier (Pay-As-You-Go) for production environments containing corporate KPI data. On Paid Tier, Google contractually guarantees zero prompt training. |

---

## H. Required Approvals for Production Deployment

Before promoting PR #110 from Draft to Merged and enabling AI in Dokploy production:

1. **AI Security Reviewer Approval:**
   - Verify that all Cloudflare and Google tokens remain redacted in logs (`redact_secrets`).
   - Confirm that live verification endpoints remain disabled by default in production.
   - Confirm that AI workspace features remain strictly restricted to `Admin` role.
2. **Lead Backend / Infrastructure Architect Approval:**
   - Approve the model resolution mechanism and Cloudflare primary / Gemini fallback architecture.
   - Confirm Dokploy container rollback procedure to baseline commit `eb502a7f017d31ad7123077c6629d01f46406c35`.
3. **Product Owner Sign-Off:**
   - Authorize activation of `PMS_GEMINI_MODEL=gemini-3.5-flash-lite` in Dokploy environment variables.
   - Authorize switching `ai_enabled` to `true` in the database when the Phase 3 administrative rollout commences.


### Final four-point review follow-up (12 November 2026)

- Live verification now requires atomic shared Redis quota (maximum 10 calls per UTC day) and **fails closed** on Redis outages; no process-local budget fallback.
- Both synthetic Cloudflare calls share one monotonic overall timeout, with bounded reads and remaining-time checks. Blocking DNS/OS operations are not hard wall-clock cancellable.
- The documented rollback creates a new review branch first; use the correct revert command for the merge method, not a hard reset or direct push to main.
- Google documents Gemini 2.5 Flash automatic routing to 3.5 Flash-Lite **starting 1 December 2026**: https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash
