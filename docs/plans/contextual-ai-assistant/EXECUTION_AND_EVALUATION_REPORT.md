# PMS Contextual AI Assistant — Phase 0 to Phase 6 Execution & Evaluation Report

## 1. Phase 0 — Production Overhead Audit & Measured Cleanup

### 1.1 Audit Findings
- **Backend Docker Build Paths**:
  - `Backend/Dockerfile` (`context: ./Backend` in `DevOps/docker-compose.yml` and `docker-compose.prod.yml`): previously copied all of `Backend/` (`COPY . .`) and installed `pytest`, `pytest-asyncio`, and `hypothesis` into the production image from `Backend/requirements.txt`. `Backend/.dockerignore` did not exclude `tests/`, `scripts/`, `logs/`, `*.db`, or `.claude/`.
  - `DevOps/Dockerfile.backend` (`context: .` root): copied `Backend/` (`COPY Backend/ .`); root `.dockerignore` did not exclude `Backend/tests`, `Backend/scripts`, `Backend/logs`, `.claude/`, `graphify-out/`, or `*.gguf` model weights.
- **Runtime Classifier Overhead**:
  - `Backend/services/ai/router.py` previously called `LocalIntentClassifier.from_fixture_train_split()` at live request time when `PMS_AI_CLASSIFIER_MODE != "off"`, reading `Backend/tests/fixtures/ai_english_questions.json` and training a TF-IDF + LogisticRegression model inside the request path despite the release manifest decision `DO_NOT_PROMOTE_KEEP_HYBRID_RULES`.
- **Evaluation Fixture Duplication**:
  - Audited `ai_english_questions.json` (`132` questions), `call_center_100_questions.jsonl` (`100` questions), and `conversation_v2_scenarios.jsonl` (`25` scenarios).
  - Found `0` intra-file duplicates and `2` exact cross-file duplicates (`q095`: `"Show corrective actions for Outbound"`, `q130`: `"Who is the best agent in Inbound and what is his trend?"`), which were already covered in `call_center_100_questions.jsonl`.

### 1.2 Before vs. After Measurements

| Metric | Before Cleanup | After Cleanup | Delta / Savings |
| --- | --- | --- | --- |
| `Backend/` Docker Build Context (`Backend/.dockerignore`) | `54.55 MiB` (`391` files) | `6.01 MiB` (`177` files) | **`-48.53 MiB` (`-89.0%`)** |
| Root `.` Docker Build Context (`.dockerignore`) | `104.90 MiB` (`1,341` files) | `11.75 MiB` (`760` files) | **`-93.15 MiB` (`-88.8%`)** |
| Production Python Site-Packages (`pytest`, `pytest-asyncio`, `hypothesis`, `iniconfig`, `pluggy` moved to `Backend/requirements-dev.txt`) | Included in `Backend/requirements.txt` | Separated into `Backend/requirements-dev.txt` | **`-7.20 MiB` unpacked** |
| Live-Request Classifier Training (`from_fixture_train_split`) | Active when `classifier_mode != "off"` | Removed from live routing; forced `off` in `production` | **`0` runtime fixture reads** |
| Single-Turn Benchmark Fixture (`ai_english_questions.json`) | `132` questions (`2` cross-file duplicates) | `130` deduplicated questions (`64` paraphrase groups) | **`0` coverage loss** |

---

## 2. Phase 1 — Reuse / Gap Matrix & Stabilization Verification

| Component | Path | Classification | Notes |
| --- | --- | --- | --- |
| Scope & Permission Identity | `Backend/repositories/ai_conversation_repository.py`, `Backend/utils/report_scope.py` | **Reused as-is** | `canonical_scope_identity`, `compute_scope_fingerprint`, and live DB permission revalidation (`build_user_scope_from_db_user`) enforce team, branch, region, function, self-only, and `accessible_team_levels`. |
| Deterministic KPI & Evidence Engine | `Backend/services/ai/tools.py`, `Backend/services/ai/catalog.py` | **Reused as-is** | Authoritative for KPI scores, targets, weights, branch breakdowns, employee rankings, and 6-gate scope certification. |
| Corrective Action Persistence | `Backend/services/corrective_action_service.py`, `Backend/services/team_action_service.py` | **Reused as-is** | Persists employee-level and team-level actions with `status="Open"` and invalidates dashboard caches via `CacheInvalidationService`. |
| Contextual Assistant Service | `Backend/services/ai/contextual_assistant.py` | **Extended / Added** | Implements `PageContextV1` resolution, pre-query authorization, capability routing (`page_help`, `navigation`, `performance_query`, `proposal`), curated role-aware help catalog, and `confirm_corrective_action_proposal`. |
| Local Model Router (`Qwen3 4B`) | `Backend/services/ai/local_model_router.py` | **Replaced JSON mode** | Upgraded from `{"type": "json_object"}` (which returned `0/4` valid JSON on `llama-server.exe`) to strict `response_format={"type": "json_schema", "json_schema": build_intent_json_schema()}` (`max_tokens=32`, timeout `6.0s`). |
| Embedded Contextual UI Panel | `Frontend/src/components/ai/ContextualAssistantPanel.tsx` | **Added & Embedded** | Embedded in `MonthlyPresentationView.tsx` and `TeamDashboardView.tsx` while preserving `/ai` (`PmsAiWorkspaceView.tsx`). |

---

## 3. Phase 2, Phase 3 & Phase 5 — Contextual Engine, Qwen3 4B Reliability & Corrective Action Proposals

1. **`PageContextV1` Precedence & Pre-Query Authorization**:
   - Precedence order enforced in `apply_page_context_to_request` and `HybridQueryRouter`:
     1. Explicit user entity/filter in the current prompt
     2. Selected entity/metric in `PageContextV1`
     3. Active page filters in `PageContextV1`
     4. Confirmed conversation context
     5. Authorized defaults
   - `validate_page_context_scope` blocks unauthorized `team_id`, `function_id`, `branch`, `performance_level`, or `employee_id` before any database/record reads (`0` tool calls).
   - When `page_context.is_fallback_data=True`, `page_help` and `navigation` remain available (with an explicit sample-data disclosure), while analytical queries and action proposals are refused (`outcome="unavailable_data"`, `0` tool calls).
2. **Qwen3 4B (`Q4_K_M`) Local Router Integration**:
   - `local_model_router.py` enforces strict JSON Schema grammar (`ALLOWED_INTENTS = {"current_value", "actual_vs_target", "trend", "ranking", "score_drivers", "page_help", "navigation", "proposal", "clarify"}`).
   - Live smoke verification against `llama-server.exe` on `127.0.0.1:18080` (`Qwen3-4B-Q4_K_M.gguf`) confirmed `100%` valid JSON Schema output with `confidence` in `[0.0, 1.0]`, while PMS deterministic services remain sole authority for data selection, calculations, and permissions.
3. **Evidence-Based Corrective Action Proposals (`POST /api/ai/proposals/confirm`)**:
   - Proposals clearly separate `observed_facts` (computed by PMS) from `hypothesis` to verify during coaching/audit.
   - `can_user_create_action` is `True` only for `Admin`, `General Manager`, `Manager`, and `Performance Team` within their authorized team/level/branch scope; read-only roles (`Function Director`, `Function Viewer`, `Regional Manager`, `Branch Director`, `Viewer`, `Employee`, `Agent`, `Executive`) receive `can_user_create_action=False` and are blocked (`HTTP 403`) if they call `POST /api/ai/proposals/confirm`.
   - `confirm_corrective_action_proposal` revalidates live user permissions and `evidence_revision` (`HTTP 409` if underlying evaluations changed) before persisting via `CorrectiveActionService` (employee target) or `TeamActionService` (team target) with `persisted_status="Open"`.

---

## 4. Phase 4 & Phase 6 — Embedded UI Surfaces & Multi-Dimensional Evaluation

### 4.1 Contextual Assistant Benchmark (`contextual_assistant_scenarios.jsonl`)
Evaluated via `Backend/scripts/evaluate_ai_classifier.py` across `15` scenarios (`5` train, `4` val, `6` held-out test, `paraphrase_split_zero_leakage: true`):

| Quality Dimension | Measured Score | Status |
| --- | --- | --- |
| 1. Intent & Capability Mode Accuracy | `100.0%` (`15/15`) | PASS |
| 2. Question Completeness | `100.0%` (`15/15`) | PASS |
| 3. Context Accuracy (`PageContextV1`) | `100.0%` (`15/15`) | PASS |
| 4. Factual & Numerical Accuracy | `100.0%` (`15/15`) | PASS |
| 5. Access & Guardrail Accuracy (`0` unauthorized reads) | `100.0%` (`15/15`) | PASS |
| 6. Usefulness & Brevity (`<= 320` chars headline) | `100.0%` (`15/15`) | PASS |
| 7. Guidance Quality (`page_help` & `navigation_targets`) | `100.0%` (`15/15`) | PASS |
| 8. Action Proposal Quality (`Open` status, facts vs. hypothesis, write RBAC) | `100.0%` (`15/15`) | PASS |

- **Per-Category Accuracy**: `page_help`: `3/3` (`100.0%`), `navigation`: `3/3` (`100.0%`), `performance_query`: `2/2` (`100.0%`), `proposal`: `3/3` (`100.0%`), `access_control`: `4/4` (`100.0%`).
- **Median / Max Deterministic Latency**: `10.04 ms` median, `34.31 ms` max.

### 4.2 Scope & Limitations
- Currently embedded in **Monthly Presentation** and **Team Dashboard** (while preserving `/ai` full workspace).
- Full 6-gate calculation certification covers `Inbound`, `Outbound`, and `Support Positions` (`Call Center`). Other allowlisted teams use standard dashboard read routing and are marked `partial_evidence` or `unverified` in the certification registry until dedicated multi-period source-evidence parity fixtures are completed.
