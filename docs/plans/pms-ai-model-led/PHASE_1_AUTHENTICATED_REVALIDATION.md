# Phase 1 Authenticated HTTP Revalidation

**Date:** 2026-11-17  
**Trace:** `Backend/scripts/phase2_model_led_http_trace_20261117.json`

The verifier used the normal `/api/ai/chat` HTTP boundary with a locally issued Admin bearer token and synthetic records in in-memory SQLite. It records provider configuration separately from observed runtime use and keeps provider logs to aggregate metrics; credential values and raw prompt/response logs are not included.

- **Configured snapshot:** Cloudflare `@cf/ibm-granite/granite-4.0-h-micro` primary; Gemini `gemini-3.5-flash` fallback; configured usable order `cloudflare`, then `gemini`.
- **Observed use:** Cloudflare only; 8 provider calls across the three analytical turns and one ambiguity/candidate flow; 3,810 provider-log tokens; estimated cost `$0.000110`; no fallback.
- **Waiting Time checks:** September 2026 was 6.2 min against the 5.0 min lower-is-better target, missing by 1.2 min. August 2026 was 6.8 min, missing by 1.8 min. The change from August to September was a 0.6 min improvement.
- **Telemetry limitation:** `AiChatResponse.provider_usage` reported zero token and cost fields while `UnifiedProviderEngine` aggregate logs contained metering. The artifact labels token and cost totals as provider-log observations.

This proves live model execution for this synthetic local HTTP path only. It does not establish published-data parity or signed-in browser verification.
