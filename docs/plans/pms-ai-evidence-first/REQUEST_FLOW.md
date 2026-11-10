# Phase 1: End-to-End Request Flow Architecture

**Document Version:** 1.0  
**Date:** 10 November 2026  
**Status:** Architecture Map Verified  
**Scope:** Phase 1 Deliverable for PMS AI Evidence-First Upgrade ([Implementation Plan](file:///D:/Projects/PMS_Dashboard/docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md))

---

## 1. Overview and Entry Points

The PMS AI system exposes two user interfaces connecting to a shared backend pipeline:
1. **Dedicated PMS AI Workspace:**
   - **Frontend File:** [`Frontend/src/features/pmsAi/PmsAiWorkspaceView.tsx`](file:///D:/Projects/PMS_Dashboard/Frontend/src/features/pmsAi/PmsAiWorkspaceView.tsx)
   - **Route:** `/ai`
   - **Interaction:** Multi-turn conversational interface with scope filters (Country, Function, Team, Level, Period), suggested prompts, and evidence inspection panels.
2. **Contextual Assistant Panel:**
   - **Frontend File:** [`Frontend/src/features/contextualAssistant/ContextualAssistantPanel.tsx`](file:///D:/Projects/PMS_Dashboard/Frontend/src/features/contextualAssistant/ContextualAssistantPanel.tsx)
   - **Component:** Embedded drawer available on operational dashboard pages (Monthly Review, Team Deep Dive, Employee Scorecard, etc.).
   - **Interaction:** Single-turn or quick-action queries bound to the active page context (`page_route`, `selected_team`, `selected_month`, `is_fallback_data`).

Both entry points communicate with the backend via the FastAPI router [`Backend/api/routers/ai_workspace.py`](file:///D:/Projects/PMS_Dashboard/Backend/api/routers/ai_workspace.py) through two primary endpoints:
- `POST /api/ai/chat` (Full query handling and multi-turn execution)
- `POST /api/ai/watching` (Contextual page change summarization)
- `POST /api/ai/feedback` (User rating and review logging)

---

## 2. The 12-Step Request Flow Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor User as User (Admin)
    participant UI as Frontend (Workspace / Panel)
    participant Gateway as API Gateway & Auth Guard
    participant Scope as Scope & Context Resolver
    participant Intent as Intent Classifier / Router
    participant LLM as Qwen Local LLM (Pilot)
    participant Registry as Deterministic Tool Registry
    participant DB as PMS DB & Data Services
    participant Synth as Evidence Synthesis
    participant Audit as Interaction & Trace Logger

    User->>UI: Submit query ("What was Inbound booking rate in Oct 2026?")
    UI->>Gateway: POST /api/ai/chat (Prompt, Session, PageContext)
    
    rect rgb(240, 245, 255)
    Note over Gateway: Step 1-2: Security & Gates
    Gateway->>Gateway: Check require_ai_enabled() (ProductSetting: ai_enabled)
    Gateway->>Gateway: Check require_ai_admin() (User role == "Admin")
    end

    rect rgb(245, 255, 245)
    Note over Scope: Step 3: Scope Resolution & Guardrails
    Gateway->>Scope: validate_live_account_and_scope()
    Scope->>Scope: Normalize Country (EGY/UAE), Team aliases, Period
    Scope->>Scope: Guardrail: Check is_fallback_data (Return notice if true)
    end

    rect rgb(255, 250, 240)
    Note over Intent,LLM: Step 4-6: Intent Routing & Fallback
    Scope->>Intent: resolve_and_validate(prompt, session_context)
    Intent->>Intent: Intercept greetings/thanks/policy/mutation regex
    alt Local Model Configured & Reachable
        Intent->>LLM: chat_completion() for Structured Tool Plan
        LLM-->>Intent: JSON Tool Plan
    else Model Timeout / Unreachable / Rules Mode
        Intent->>Intent: Fallback to local_rules heuristic routing
    end
    end

    rect rgb(255, 245, 255)
    Note over Registry,DB: Step 7-9: Bounded Tool Execution & Scoring
    Intent->>Registry: Execute Planned Tool (e.g. get_kpi_diagnosis_and_trends)
    Registry->>DB: Query PerformanceRecord, KPIValue, TeamKPIConfig
    DB-->>Registry: Authorized relational records
    Registry->>Registry: Compute exact aggregates, weights, directions
    Registry-->>Synth: Structured Evidence Digest (JSON)
    end

    rect rgb(240, 255, 255)
    Note over Synth,LLM: Step 10: Answer Synthesis
    alt Local Synthesis Enabled & Reachable
        Synth->>LLM: Format concise 1-2 sentence response from digest
        LLM-->>Synth: English text
    else Model Offline / Deterministic Mode
        Synth->>Synth: Format via deterministic templater
    end
    end

    rect rgb(250, 250, 250)
    Note over Audit: Step 11-12: Logging & Delivery
    Synth->>Audit: record_turn() -> ai_interaction_traces & ai_turns
    Synth-->>UI: AiWorkspaceResponse (Answer, Scope, Evidence, Suggestions)
    UI-->>User: Display formatted answer with source chips
    end
```

---

## 3. Step-by-Step Execution Details

### Step 1: Authentication and Product Feature Gate
- **Entry:** `POST /api/ai/chat` in [`Backend/api/routers/ai_workspace.py`](file:///D:/Projects/PMS_Dashboard/Backend/api/routers/ai_workspace.py).
- **Authentication:** `get_current_user` extracts JWT claims and binds the `User` object.
- **Product Gate:** `require_ai_enabled(db)` reads `ProductSetting.key == "ai_enabled"`. If false or missing, execution halts with HTTP `403 Forbidden`.
- **Role Gate:** `require_ai_admin(current_user)` verifies `current_user.role == "Admin"`. Any other role (e.g. `Manager`, `Employee`) receives HTTP `403 Forbidden`.

### Step 2: Session & Idempotency Management
- **Handler:** `AiConversationService` in [`Backend/services/ai/conversation_service.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/conversation_service.py).
- **Turn Claim:** Generates or validates `client_request_id`. Attempts a compare-and-swap update on `ai_turns` using a unique `claim_token`. If an identical request is in flight, duplicate processing is prevented.

### Step 3: Scope, Country, and Period Resolution
- **Files:** [`Backend/services/ai/catalog.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/catalog.py) and [`Backend/utils/report_scope.py`](file:///D:/Projects/PMS_Dashboard/Backend/utils/report_scope.py).
- **Country Resolution:**
  - If prompt specifies "Egypt" / "UAE", explicit query country takes precedence.
  - If omitted, uses user's default authorized region (`accessible_regions`).
  - Cross-country leakage is prevented: Egyptian teams cannot query UAE records, and vice versa.
- **Team & Alias Resolution:**
  - Evaluated via `resolve_canonical_team_name(raw_team, region=eff_region)`.
  - Disambiguates country-specific pairs: e.g. "Resubmission" in Egypt vs "Re-Submission" in UAE.
- **Period Resolution:**
  - Extracts target month and year (e.g. "October 2026"). Defaults to the latest active published month if unspecified.
- **Sample Data Guardrail:**
  - If `page_context.is_fallback_data == True`, execution immediately halts and returns an explicit warning: `"This page is currently displaying sample demonstration data. Analytics are restricted to published production records."`

### Step 4: Intent & Policy Routing
- **File:** [`Backend/services/ai/router.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/router.py) (`HybridQueryRouter`).
- **Deterministic Interceptions (Pre-Model):**
  1. **Greetings / Thanks:** Regex matches (`hi`, `hello`, `thank you`) return concise canned offers of assistance without querying performance tables.
  2. **Mutation Guard:** Regex matches for write verbs (`create`, `delete`, `update`, `drop`, `insert`) return an immediate read-only policy refusal.
  3. **Prompt Injection / System Leak Guard:** Regex patterns checking for instructions to ignore rules or output system prompts return a policy refusal.

### Step 5: Planning & Model Invocation (Qwen Pilot)
- **File:** [`Backend/services/ai/llm_client.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/llm_client.py).
- **Model Check:** Checks `get_ai_runtime_config().local_intent_enabled`.
- **Execution:**
  - Sends a structured prompt with allowed tool schemas to `http://pms-qwen-pilot:8080/v1/chat/completions`.
  - Enforces JSON schema validation on tool arguments.
- **Fallback Path:**
  - If Qwen is unreachable, times out (5.0s deadline), or outputs invalid JSON, `router.py` automatically falls back to `local_rules` mode.
  - The fallback is recorded in the trace diagnostics (`route_used="local_rules"`, `provider_name="deterministic"`).

### Step 6: Tool Execution & Authorization Re-Check
- **File:** [`Backend/services/ai/tool_registry.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/tool_registry.py) (`DeterministicToolRegistry`).
- **Allowlisted Tools:**
  1. `inspect_authorized_concepts`: Catalog and metric definitions.
  2. `get_executive_and_priority_insights`: Top-level performance overview and drag analysis.
  3. `get_kpi_diagnosis_and_trends`: Metric actual vs target, MoM trend, and historical points.
  4. `compare_branches_operational_volumes`: Cross-branch volume comparisons (Dubai, Ajman, Sharjah).
  5. `get_root_cause_and_action_recommendations`: Performance gap diagnosis and draft action proposals.
- **Authorization Re-Check:**
  - Every tool call executes `user_can_access_team()` and `user_can_access_branch()`. Even if an Admin requested the data, strict scope boundaries are re-verified per record.

### Step 7: Calculations and Scoring Engine
- **Files:** [`Backend/services/calculation_service.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/calculation_service.py) and [`Backend/services/performance_service.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/performance_service.py).
- **Scored vs Tracking-Only KPIs:**
  - Scored KPIs (e.g. Booking Rate, Attendance Rate, Quality Score) are weighted and contribute to the 100% score total.
  - Tracking indicators (e.g. AHT, Abandoned Calls) have weight `0.0` and are strictly excluded from score calculation.
- **Aggregation Rules:**
  - Employee-level score: Weighted sum of KPI achievements.
  - Pooled team score: Department-wide ratio of sums or weighted average based on configuration.
  - Country-specific scoring: RCM Egypt scoring rules use separate weights and formulas from RCM UAE rules.

### Step 8: Evidence Digest Construction
- **Object:** `TypedMetricEvidence` and structured dictionary.
- **Guarantees:**
  - Binds subject, country, team, position, period, metric key, unit, actual value, target value, and source file.
  - Distinguishes **zero** from **missing/unmeasured** data.

### Step 9: Response Synthesis
- **File:** [`Backend/services/ai/local_evidence_synthesis.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/local_evidence_synthesis.py).
- **Synthesis Logic:**
  - If `local_synthesis_enabled` and model reachable: Qwen composes a concise 1–2 sentence English answer strictly grounded in the evidence digest.
  - If model offline or fallback active: Deterministic string template formats the final response from evidence fields.
  - Strict Rule: No speculative extrapolation or correlation-to-causation claims are permitted.

### Step 10: Interaction Trace Logging
- **Model:** `AiInteractionTrace` in table `ai_interaction_traces`.
- **Recorded Fields:**
  - `turn_id`, `user_id`, `role`, `sanitized_prompt`, `session_state`, `tool_calls`, `tool_digest`, `structured_response`, `provider_name`, `model_name`, `latency_ms`, `non_empty_evidence`, `guardrail_triggered`.
- **Distillation Flag:** `is_distillation_eligible = False` by default; requires explicit reviewer audit.

### Step 11: Feedback Collection
- **Endpoint:** `POST /api/ai/feedback`.
- **Behavior:**
  - Accepts `turn_id`, `rating` (`"up"` or `"down"`), and optional `reason` text.
  - Updates `ai_interaction_traces.feedback_rating` and `ai_interaction_traces.feedback_reason`.
  - Feedback is strictly an audit signal for reviewers; it never triggers automatic online retraining or cache poisoning.

### Step 12: Exploration Mode Boundaries
- **File:** [`Backend/services/ai/local_data_explorer.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/local_data_explorer.py).
- **Production Gate:** If `APP_ENV == "production"`, `local_exploration_enabled()` returns `False`.
- **Boundaries:** Bounded to a maximum of 3 tool iterations, with row-count and latency limits.
