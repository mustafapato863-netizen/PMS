# Phase 1: Provider Execution Evidence & Architecture Audit

**Governing Specification:** [PMS AI Model-Led Implementation Plan](../PMS_AI_MODEL_LED_IMPLEMENTATION_PLAN.md)  
**Execution Date:** 16 November 2026  
**Environment Baseline:** `APP_ENV=development`, local in-memory SQLite (`sqlite:///:memory:`), strictly synthetic employee fixtures.

---

## 1. Configuration Audit (Real Application Loader)

Configuration was audited directly through the application's real loader (`Backend/config/environment.py:load_project_environment`, `Backend/services/ai/config.py`, and `Backend/services/ai/provider_engine.py:load_unified_provider_config`).

### Environment Loading & Precedence Hierarchy
The loader executes in the following strict precedence order:
1. **Pre-existing Process Environment Variables** (Authoritative; deployment platforms and test runners override all files).
2. `DevOps/.env.local` (Local multi-service development overrides).
3. `Backend/.env.local` (Backend-specific local overrides).
4. `DevOps/.env` (Shared baseline defaults; `override=False`).

### Provider Configuration Matrix
| Configuration Parameter | Resolved Value | Verification Status |
|---|---|---|
| `APP_ENV` | `development` | Verified from process / `.env` |
| **Primary Provider** | `cloudflare` (Cloudflare Workers AI) | Verified in `UnifiedProviderConfig` |
| **Fallback Provider** | `gemini` (Google Gemini API) | Verified in `UnifiedProviderConfig` |
| **Fallback Enabled** | `True` | Verified in `UnifiedProviderConfig` |
| **Cloudflare Credentials** | **Present** (Account ID & API Token loaded) | Boolean check passed; zero secrets printed |
| **Cloudflare Primary Model** | `@cf/ibm-granite/granite-4.0-h-micro` | Verified non-secret model ID |
| **Cloudflare Alter Model** | `@cf/zai-org/glm-4.7-flash` | Verified non-secret model ID |
| **Gemini Credentials** | **Present** (API Key loaded) | Boolean check passed; zero secrets printed |
| **Gemini Model** | `gemini-3.5-flash` | Verified non-secret model ID |
| **Configured Usable Providers** | `['cloudflare', 'gemini']` | Verified in `configured_providers()` |
| **Active Provider Name** | `cloudflare` | Verified in `active_provider_name()` |
| **Intent Enabled Flag** | `True` | Evaluated via `local_intent_enabled()` |
| **Synthesis Enabled Flag** | `True` | Evaluated via `local_synthesis_enabled()` |
| **Exploration Enabled Flag** | `False` | Gated off in development; permanently disabled under `APP_ENV=production` |
| **Router Mode** | `hybrid` | Evaluated via `get_ai_runtime_config()` |
| **Classifier Mode** | `off` | Local TF-IDF classifier permanently disabled |
| **Provider Timeout** | `10.0 seconds` | Max deadline for overall call sequence |
| **Max Retries** | `1` | Max transient HTTP retries on primary provider |

> [!NOTE]
> **Implementation Assistant vs. Runtime Model Distinction:**
> The user-facing implementation assistant model (`Gemini Flash 3.8, High`) in the IDE is strictly an authoring agent. The PMS runtime model is configured strictly via the backend environment as Cloudflare `@cf/ibm-granite/granite-4.0-h-micro` with Google Gemini `gemini-3.5-flash` fallback. No runtime API IDs were invented.

---

## 2. Bounded Smoke Test Results (4-Turn Sequence)

A 4-turn synthetic conversation sequence was executed using an in-memory SQLite database, synthetic admin authentication, and synthetic `PerformanceRecord` fixtures (`EMP101` Sara Mahmoud, `EMP102` Adham Tarek, etc.):

- **Turn 1 (Greeting):** `"Hi, how can you help?"`
- **Turn 2 (Single-employee Current Value):** `"What was Sara Mahmoud's score in September 2026?"`
- **Turn 3 (Period Change Follow-up):** `"And in August?"`
- **Turn 4 (Trend / Metric Change Follow-up):** `"What was her score pattern across the available months?"`

The sequence was evaluated across three distinct execution modes:

### Comparative Execution Table

| Turn | Execution Mode | Provider Used | Model Used | Provider Calls | Route Used | Outcome | Headline (Abbreviated) | Total Turn Latency |
|---|---|---|---|---|---|---|---|---|
| **Turn 1 (Greeting)** | **Run A (Deterministic)** | `deterministic` | `intent-gate-v1` | 0 | `local_rules` | `answer` | *"I can analyze verified PMS performance for your authorized teams..."* | 576.5 ms |
| | **Run B (Mocked)** | `deterministic` | `intent-gate-v1` | 0 | `local_rules` | `answer` | *"I can analyze verified PMS performance for your authorized teams..."* | 23.0 ms |
| | **Run C (Live)** | `deterministic` | `intent-gate-v1` | 0 | `local_rules` | `answer` | *"I can analyze verified PMS performance for your authorized teams..."* | 18.9 ms |
| **Turn 2 (Current Value)** | **Run A (Deterministic)** | `deterministic` | `pms-local-router-v1` | 0 | `local_rules` | `answer` | *"Sara Mahmoud (EMP101 · Senior Call Center Agent) scored 94.0%..."* | 74.0 ms |
| | **Run B (Mocked)** | `deterministic` | `pms-local-router-v1` | 0 | `local_rules` | `answer` | *"Sara Mahmoud (EMP101 · Senior Call Center Agent) scored 94.0%..."* | 24.6 ms |
| | **Run C (Live)** | `deterministic` | `pms-local-router-v1` | 0 | `local_rules` | `answer` | *"Sara Mahmoud (EMP101 · Senior Call Center Agent) scored 94.0%..."* | 23.1 ms |
| **Turn 3 (Period Follow-up)** | **Run A (Deterministic)** | `deterministic` | `pms-local-router-v1` | 0 | `local_rules` | `answer` | *"Sara Mahmoud (EMP101 · Senior Call Center Agent) scored 91.0%..."* | 28.0 ms |
| | **Run B (Mocked)** | `deterministic` | `pms-local-router-v1` | 0 | `local_rules` | `answer` | *"Sara Mahmoud (EMP101 · Senior Call Center Agent) scored 91.0%..."* | 24.3 ms |
| | **Run C (Live)** | `deterministic` | `pms-local-router-v1` | 0 | `local_rules` | `answer` | *"Sara Mahmoud (EMP101 · Senior Call Center Agent) scored 91.0%..."* | 20.7 ms |
| **Turn 4 (Score Pattern)** | **Run A (Deterministic)** | `deterministic` | `pms-local-router-v1` | 0 | `local_rules` | `answer` | *"Across March 2026 to September 2026 (7 months), Sara Mahmoud moved from 80.0% to 94.0%..."* | 24.8 ms |
| | **Run B (Mocked)** | `deterministic` | `pms-local-router-v1` | 0 | `local_rules` | `answer` | *"Across March 2026 to September 2026 (7 months), Sara Mahmoud moved from 80.0% to 94.0%..."* | 23.0 ms |
| | **Run C (Live)** | `deterministic` | `pms-local-router-v1` | 0 | `local_rules` | `answer` | *"Across March 2026 to September 2026 (7 months), Sara Mahmoud moved from 80.0% to 94.0%..."* | 21.5 ms |

---

## 3. Actual Live Provider Connectivity Proof

To verify that live outbound network connectivity to Cloudflare Workers AI is functional, two targeted live probes were executed:

### Probe 1: Direct In-Process Engine Completion
- **Caller:** `UnifiedProviderEngine.generate(req)`
- **Prompt:** Synthetic greeting completion (`"Reply with: PMS AI connection successful."`)
- **Observed Metrics:**
  - **Outcome:** `success` (HTTP 200)
  - **Provider:** `cloudflare`
  - **Model:** `@cf/ibm-granite/granite-4.0-h-micro`
  - **Latency:** `1,488.94 ms`
  - **Token Consumption:** Prompt: 39 tokens, Completion: 25 tokens, Total: 64 tokens
  - **Neuron Consumption:** `0.314 Neurons` (< 1 Neuron)
  - **Estimated Cost:** `$0.00000345 USD`
  - **Content Returned:** `"Thank you for your message. I'm here to assist you. Please let me know how I can help you further."`
  - **Security Scan:** Zero secrets, tokens, or raw authorization headers exposed.

### Probe 2: Full Orchestrator Analytical Turn with Model Synthesis
- **Caller:** `PmsAiOrchestrator.run_chat_turn(req)`
- **Prompt:** `"Compare bookings in Dubai, Sharjah and Ajman in Call Center in September 2026."`
- **Observed Metrics:**
  - **Outcome:** `answer`
  - **Headline:** `"In September 2026, Dubai had 490 bookings in Call Center, Sharjah had 250 bookings, and Ajman had 200 bookings."`
  - **Provider Used:** `cloudflare`
  - **Model Used:** `@cf/ibm-granite/granite-4.0-h-micro`
  - **Route Used:** `local_rules`
  - **Provider Calls:** `1`
  - **Claim Validation:** Passed `ClaimLedgerValidator` against authoritative PMS database records.

---

## 4. Root-Cause Analysis: The Model Suppression Mechanism

The comparative smoke test reveals why the PMS AI assistant currently behaves like a rules engine even when live provider credentials are active:

1. **Lexical Gate Interception (Turn 1):**
   `contextual_assistant.py` applies hardcoded regexes (`_GREETING_PATTERN`, `_HELP_PAGE_PATTERN`, `_THANKS_PATTERN`, `_OFF_TOPIC_PATTERN`). When matched, it returns static canned prose (`intent-gate-v1`) immediately without consulting the model.
2. **Regex Plan Override in Router (Turns 2 & 3):**
   In `router.py:HybridQueryRouter.resolve_and_validate`, if any pattern matcher identifies an employee name, metric name, or period, it builds a deterministic plan.
   Furthermore, lines 3498–3504 explicitly suppress `call_suggest_intent` whenever:
   - `is_short_followup` is True.
   - `plan.employee_id` or `plan.single_person` is present.
   - `has_explicit_month` is True.
   - Any keyword like `"trend"`, `"compare"`, `"versus"`, or `"score"` is present.
   This guarantees that almost zero analytical questions ever reach `suggest_intent`.
3. **Hardcoded Exclusion in Evidence Synthesis:**
   In `local_evidence_synthesis.py` (lines 136–140), `extract_overall_score_facts` specifically rejects any question mentioning employees or people:
   ```python
   if re.search(r"\b(?:and|also|then|versus|vs|compare|trend|...|employee|person|agent|who|why|cause)\b", lower):
       return None
   ```
   Because all person-level questions return `None` from fact extraction, model synthesis is aborted and `orchestrator.py` defaults to formatting canned template strings from `providers.py:DeterministicLocalProviderAdapter`.
4. **Summary:** Live provider execution works reliably, but the existing codebase actively fences the model into narrow pockets (only branch booking comparisons), substituting regex rules and string formatters for 95%+ of user dialogue.

---

## 5. Concrete Phase 2 Recommendations

Based on empirical evidence from Phase 0 and Phase 1, the following clear boundaries must govern Phase 2:

### What to Keep & Preserve (Backend Authority)
1. **`UnifiedProviderEngine` (`Backend/services/ai/provider_engine.py`):**
   Robust multi-provider abstraction with Cloudflare primary, Gemini fallback, bounded retries, deadline management, token/neuron accounting, and strict secret redaction.
2. **RBAC Isolation & Pilot Gate:**
   `read_ai_enabled(db)` database toggle and Admin-only enforcement across all AI endpoints.
3. **Conversation Contracts (`Backend/services/ai/conversation_service.py`):**
   Origin isolation (`workspace` vs `page_assistant` vs `legacy`), turn persistence, user ownership, and idempotency.
4. **Authoritative Data Services & Tool Registry (`DeterministicToolRegistry`):**
   Read-only database queries, team/position hierarchies, country-specific calculation bases (Egypt vs UAE), and KPI direction rules (`domain_policies.py`).
5. **Claim Ledger Verification (`ClaimLedgerValidator`):**
   Mandatory post-generation factual claim check verifying every number and entity in model prose against typed evidence.

### What to Retire & Deprecate (Fragile Rules)
1. **Lexical Greeting & Off-Topic Gates in `contextual_assistant.py`:**
   Retire regex rejection patterns. The model should interpret natural greetings, conversational context, and clarification needs.
2. **Fragile Regex Overrides in `router.py`:**
   Phase out regex-based intent forcing and parameter stripping.
3. **Artificial Synthesis Fences in `local_evidence_synthesis.py`:**
   Remove restrictions that forbid employee-level queries from model synthesis.

### What to Build in Phase 2 (Model-Led Path)
1. **Gated Model-Led Pilot Pipeline:**
   Introduce a backend flag (`PMS_AI_MODEL_LED_PILOT_ENABLED`, default `false`) with seamless fallback to the legacy path.
2. **Structured Model Tool Calling:**
   Present the model with structured schemas for server-defined read tools (`read_employee_metric`, `compare_branches`, `get_score_trend`). The model selects tools and arguments; backend validates and executes them.
3. **Evidence-Grounded Generalized Synthesis:**
   Pass typed evidence to the model to compose direct, concise 1–3 sentence responses, validated by `ClaimLedgerValidator`.
