# PMS AI — Live Provider Verification & Optimization Report
**Phase 1 & Phase 2 Technical Deliverable**

> **Document Status:** Operational Deliverable  
> **Target Branch:** `feat/pms-ai-live-verification-optimization`  
> **Baseline Commit:** `eb502a7f017d31ad7123077c6629d01f46406c35`  
> **Execution Date:** 2026-11-12  
> **Lead Architecture:** Senior Python Backend Engineer / AI Integration Architect  

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
| **Diagnostic State: Pre-Verification** | `credentials_present` (`live_verified=false`) | Truthful |
| **Diagnostic State: Post-Verification** | `live_verified` (`live_verified=true`) | Truthful |

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
* **API Token Permissions:** Scoped token with `Workers AI:Read` policy. Secret sanitization filters (`redact_secrets`) strictly strip tokens (`cfut_...`) and account IDs from all application logs, error traces, and API responses.

### 2. Supported Request Parameters
The following request payload fields are verified against Cloudflare Workers AI:
```json
{
  "model": "@cf/ibm-granite/granite-4.0-h-micro",
  "messages": [
    {"role": "system", "content": "You are PMS AI Assistant."},
    {"role": "user", "content": "Reply with exactly: PMS AI connection successful."}
  ],
  "max_tokens": 128,
  "temperature": 0.0,
  "stream": false
}
```

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
The PMS adapter (`CloudflareAIProviderAdapter`) parses `usage.neurons` directly into `TokenUsage.neurons` and records it on each `ProviderAttempt`.

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

---

## D. Gemini Fallback Optimization & Verification

### 1. Empirical Model Investigation
Google Gemini acts as the isolated secondary fallback provider. Live testing with the owner's Google AI Studio API key revealed a critical deprecation:

1. **`gemini-2.5-flash`:** Returned `HTTP 404 Not Found` with upstream API message:
   > *"This model models/gemini-2.5-flash is no longer available to new users. Please update your code to use models/gemini-3.8-flash."*
2. **`gemini-3.5-flash-lite`:** Returned `HTTP 200 OK`, latency ~1.1s, robust JSON adherence.
3. **`gemini-3.5-flash`:** Returned `HTTP 200 OK`, latency ~1.3s.

### 2. Free Tier Quota & Cost Benchmark

| Model Identifier | Free Tier RPM | Free Tier Daily Limit (RPD) | Input / 1M Tokens | Output / 1M Tokens | PMS Recommendation |
|---|---|---|---|---|---|
| `gemini-2.5-flash` | Deprecated | 0 RPD (HTTP 404 for new keys) | $0.15 | $0.60 | **Do Not Use** |
| `gemini-3.5-flash` | 15 RPM | **20 RPD** | $0.075 | $0.30 | Secondary candidate |
| `gemini-3.5-flash-lite`| **15 RPM** | **500 RPD** (25x higher free capacity!) | **$0.0375** | **$0.15** | **Verified Fallback Standard** |

**Outcome:** `DevOps/.env.example` has been updated to recommend `PMS_GEMINI_MODEL=gemini-3.5-flash-lite`. The provider engine respects this configuration and uses the verified model for low-latency, zero-cost fallback within the 500 RPD free tier.

---

## E. Cost & Observability Infrastructure

### 1. Model Pricing Metadata
Token cost estimation in `Backend/services/ai/provider_engine.py` was refactored with the typed `ModelPricing` dataclass:
```python
@dataclass(frozen=True)
class ModelPricing:
    input_per_million: float
    output_per_million: float
    currency: str = "USD"
    effective_date: str = "2026-11-12"
    source: str = "Published Provider Reference"
```
The dictionary patterns are evaluated in order of pattern length descending to guarantee specific models (e.g., `gemini-3.5-flash-lite`) match accurately prior to shorter prefixes (`gemini-3.5-flash`).

### 2. Token & Neuron Usage Monitoring
Each invocation records structured attempt metadata:
```text
{"provider": "cloudflare", "model": "@cf/ibm-granite/granite-4.0-h-micro", "status": "success", "latency_ms": 1165.7, "input_tokens": 40, "output_tokens": 7, "neurons": 0.13, "retry_count": 0}
```
* **PII Protection:** Prompts, completions, user IDs, and secret tokens are **never** logged to disk or emitted in telemetry.
* **Observability Log:** Formatted log line includes purpose, outcome, provider, model, latency, tokens, neurons, estimated cost, and fallback indicator.

---

## F. AI Health Diagnostics (6 Discrete States)

Routine application operations and health checks must **never** consume AI tokens. The diagnostic subsystem in `Backend/services/ai/llm_client.py` and `Backend/api/routers/ai_workspace.py` strictly distinguishes 6 states without network probes:

1. `unavailable`: Providers are disabled in configuration (`PMS_AI_CLOUDFLARE_ENABLED=false`).
2. `configured`: Provider is enabled, but credentials (Account ID / API Token) are missing.
3. `credentials_present`: Credentials are configured, but no live inference has been executed.
4. `live_verified`: Live synthetic verification succeeded.
5. `live_failed`: Live synthetic verification failed (error category recorded).
6. `fallback_active`: Primary provider is unconfigured or failed, and fallback provider is serving requests.

### Admin Live Verification Endpoint
An explicit, authenticated, Admin-only diagnostic action was added:
* **Endpoint:** `POST /api/ai/diagnostics/verify-live`
* **RBAC:** Requires `Admin` role; non-admin roles receive `HTTP 403 Forbidden`.
* **Execution:** Triggers the bounded 2-step synthetic test against Cloudflare, updates in-memory live verification state, and returns diagnostic results.
* **Safety:** Does not modify the database or enable the feature switch.

---

## G. Operational Runbook

### 1. Running Manual Live Verification via CLI
Operators can verify Cloudflare AI connectivity directly from the server or local development environment without launching the web server:
```bash
# Basic terminal output
python Backend/scripts/verify_cloudflare_ai.py

# JSON output for automated scripting
python Backend/scripts/verify_cloudflare_ai.py --json

# Test alternative model
python Backend/scripts/verify_cloudflare_ai.py --model @cf/zai-org/glm-4.7-flash
```

### 2. Inspecting AI Health Diagnostics
* **REST API (Read-only, 0 tokens):**
  ```bash
  curl -H "Authorization: Bearer <ADMIN_JWT>" https://bkpms.zainx.cloud/api/ai/diagnostics
  ```
* **Triggering Live Verification (Consumes ~0.42 Neurons):**
  ```bash
  curl -X POST -H "Authorization: Bearer <ADMIN_JWT>" https://bkpms.zainx.cloud/api/ai/diagnostics/verify-live
  ```
* **Application Logs:** Inspect Dokploy container logs for `UnifiedProviderEngine` entries:
  ```bash
  docker logs -f performance-managment-system-backend-pwhfoc | grep "UnifiedProviderEngine"
  ```

### 3. Outage Procedures
* **Cloudflare Outage (HTTP 5xx / 429):**
  * The engine automatically retries once for 5xx, or falls back immediately to Google Gemini on 429.
  * To force Gemini as primary during an extended Cloudflare incident, set `PMS_AI_PRIMARY_PROVIDER=gemini` in Dokploy environment variables and redeploy.
* **Gemini Outage:**
  * Ensure Cloudflare is healthy. If Gemini fallback is degraded, disable fallback via `PMS_AI_FALLBACK_ENABLED=false` to prevent timeout latency on secondary calls.
* **Dual Outage:**
  * When both providers fail, PMS strictly reports `outcome="provider_unavailable"` and falls back to deterministic rule-based calculation. Real KPI scores and historical employee data are never fabricated or guessed.

---

## H. Git and PR Information

* **Repository:** `mustafapato863-netizen/PMS`
* **Feature Branch:** `feat/pms-ai-live-verification-optimization`
* **Baseline Commit SHA:** `eb502a7f017d31ad7123077c6629d01f46406c35`
* **Modified Files:**
  1. `Backend/scripts/verify_cloudflare_ai.py`: Isolated live synthetic verification CLI and library.
  2. `Backend/services/ai/provider_engine.py`: Neuron tracking, explicit alter model, pricing metadata, fallback boundaries.
  3. `Backend/services/ai/llm_client.py`: 6-state diagnostics, thread-safe verification cache.
  4. `Backend/models/ai_schemas.py`: Diagnostic payload fields (`provider_status_code`, `live_verified_at`, etc.).
  5. `Backend/api/routers/ai_workspace.py`: `POST /api/ai/diagnostics/verify-live` endpoint.
  6. `Backend/tests/test_ai_provider_engine.py`: 16 comprehensive failure handling, alternative model, and pricing tests.
  7. `Backend/tests/test_ai_diagnostics.py`: 4 comprehensive 6-state and live verification endpoint tests.
  8. `DevOps/.env.example`: Updated fallback model documentation (`gemini-3.5-flash-lite`).
  9. `docs/ops/pms-ai-provider-verification.md`: This comprehensive verification report.
* **Automated Test Results:**
  * `test_ai_provider_engine.py`: 70 passed.
  * `test_ai_diagnostics.py`: 13 passed.
  * `test_llm_client.py`: 28 passed.
  * `test_ai_workspace.py`: 22 passed.
  * `test_ai_corrective_action_drafter_unified.py`: 7 passed.
  * `test_ai_explorer_unified.py`: 8 passed.
  * `test_ai_synthesis_and_routing_unified.py`: 7 passed.
  * `evaluation/pms-ai/phase2/tests/test_coverage_manifest.py`: 10 passed.
  * **Total Test Suite:** 100% pass across all 165+ AI & diagnostics tests.
