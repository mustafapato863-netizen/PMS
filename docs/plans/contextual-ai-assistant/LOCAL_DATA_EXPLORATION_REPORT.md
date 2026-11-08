# Local Assistant Data Exploration Report — 7 November 2026

## 1. Executive Summary

This report documents the design, implementation, security isolation, and measured hardware/model limits of **Bounded Local Data Exploration** for the PMS Contextual AI Assistant using the local `Qwen3-4B-Q4_K_M.gguf` model served via `llama-server.exe` on `127.0.0.1:18080`.

The local model is enabled to explore **caller-authorized PMS concepts** and request **1–2 iterative, permission-scoped evidence tools** across a bounded loop (`max_steps` 1–3, default `2`), while strictly prohibiting raw SQL, model-side arithmetic, or cross-scope data leakage.

---

## 2. Audit of Scoped Data Access, Schema Semantics & Local Database Links

### 2.1 Scoped Data Access & RBAC Enforcement
- **Authoritative Scope Utilities (`Backend/utils/report_scope.py`)**:
  - `user_can_access_team(scope, team)`: Enforces `has_unrestricted_team_access`, `accessible_teams`, and `accessible_functions`. Note: because `Branch Director` relies on record-level branch filtering in `user_can_access_team()`, `build_authorized_concept_summary()` in `Backend/services/ai/local_data_explorer.py` additionally intersects with `scope["accessible_teams"]` when explicitly present so unauthorized team names are never projected to the model.
  - `user_can_access_team_level(scope, team, level)`: Enforces `accessible_team_levels` grants across `Employee`, `Managerial`, and `Corporate` scorecards.
  - `user_can_access_branch(scope, branch)`: Enforces branch-level isolation (`dubai`, `sharjah`, `ajman`, `clinics`, `egypt`, `ksa`).
  - `is_self_only(scope)` & `filter_records_by_scope(records, scope)`: Restricts self-scoped accounts (`Agent`/`Employee`) to their own `employee_id` (`0` peer rows read).
- **Authoritative Tool Execution (`Backend/services/ai/tool_registry.py`)**:
  - All data reads pass through `ToolExecutionContext.get_scoped_records()` (`DashboardRecordService.get_records(self.db, self.scope)`) and `release_read_transaction(db)` immediately after each read step so database transactions are never held open across local LLM HTTP calls.

### 2.2 Schema Semantics & Known Unknowns
- **Tracked in PMS**:
  - Monthly KPI actuals, targets, weights, achievement percentages, weighted evaluation scores, grades (`A`–`F`), rankings, 6-month trends, branch conversion matrices, and corrective actions (`CorrectiveAction`).
- **Explicitly Unrecorded in PMS (Disclosed as Clear Unknowns)**:
  - `missing_hr_join_date`: Employee HR hire/joining dates (`join_date`) are not stored in `employees` or `performance_records` (only earliest tracked scorecard period is available).
  - `unsupported_compensation_data`: Salaries, payroll, bonuses, and commissions are not stored in PMS.
  - `call_center_revenue_not_tracked`: Call Center teams (`Inbound`, `Outbound`, `Telemarketing`) track `Bookings`, `Attended Visits`, and `Calls` rather than financial revenue.
  - `unpublished_period`: Periods outside `published_periods` have no published scorecards.
  - `unverified_scope_calculation`: Uncertified/partial teams without verified records cannot compute certified KPI scores.

### 2.3 Local PostgreSQL Foreign-Key & Sample Link Check
- Foreign-key definitions in `Backend/models/models.py` (`performance_records.employee_id -> employees.id`, `employees.team_id -> teams.id`, `kpi_records.performance_record_id -> performance_records.id`, `corrective_actions.team_id -> teams.id`) were inspected alongside bounded 500-row read-only samples in the local PostgreSQL database.
- **Scope Caveat**: Bounded 500-row samples had `0` missing `employee` / `team` / `kpi_record` links, but this sample check is **not** a complete full-table referential integrity audit.

---

## 3. Bounded Permission-Scoped Exploration Architecture

Implemented in [`Backend/services/ai/local_data_explorer.py`](file:///d:/Projects/PMS_Dashboard/Backend/services/ai/local_data_explorer.py) and wired into [`Backend/services/ai/orchestrator.py`](file:///d:/Projects/PMS_Dashboard/Backend/services/ai/orchestrator.py):

1. **Opt-In & Production Guardrails (`local_exploration_enabled()`)**:
   - Controlled by `PMS_AI_LOCAL_EXPLORATION_ENABLED` (default `"false"`).
   - Hard-disabled when `APP_ENV == "production"`.
   - Enforces loopback-only HTTP endpoints (`127.0.0.1` / `::1`, path `/v1/chat/completions`, `_NoRedirect`) and a process-local `threading.BoundedSemaphore(1)` concurrency guard.
2. **Caller-Scoped Concept Summary (`build_authorized_concept_summary()`)**:
   - Projects only the caller's authorized teams, certified vs. partial teams, authorized branches, authorized performance levels, published periods, authorized catalog metrics, allowed tools (removing `rank_employees` and `compare_branches` for `is_self_only` users), and known schema unknowns.
3. **Whitelisted Permission-Scoped Tools (`ALLOWED_EXPLORATION_TOOLS`)**:
   - `inspect_authorized_concepts`
   - `get_team_score_summary`
   - `get_kpi_diagnosis`
   - `compare_branches`
   - `get_trend`
   - `rank_employees`
   - `get_employee_summary`
   - `get_corrective_actions`
   - Raw SQL, arbitrary expressions, and unsafe string parameters (`_UNSAFE_PARAM_RE`) are rejected before any database read.
4. **Pre-Execution & Post-Execution Isolation**:
   - Every model-requested tool call is validated against `user_can_access_team`, `user_can_access_branch`, `user_can_access_team_level`, and `is_self_only` **before** calling `DeterministicToolRegistry`, ensuring `0` unauthorized records are read.
   - After tool execution, `live_auth_service.validate_live_account_and_scope(scope)` revalidates live permissions before returning evidence.
5. **Deterministic Multi-Part Synthesis & Safe Fallback**:
   - Evidence from 1–2 iterative steps is synthesized deterministically via `_synthesize_explored_evidence()` and packaged into `EvidenceItemV2` envelopes with verified source links.
   - Any timeout, malformed JSON, unknown tool, or schema violation falls back cleanly to `HybridQueryRouter` + deterministic PMS execution (`fallback_outcome` recorded in `provider_usage`).

---

## 4. Measured Local Model Limits (`Qwen3-4B-Q4_K_M.gguf` on CPU)

| Dimension | Measured Value / Limit | Operational Impact & Mitigation |
| :--- | :--- | :--- |
| **Model & Server** | `Qwen3-4B-Q4_K_M.gguf` (`2.33 GiB`) via `llama-server.exe` (`-c 2048 -ngl 0 -t 4 --reasoning-budget 0`) | Runs on `127.0.0.1:18080` on 16 GB RAM / Intel iGPU host without GPU offload. |
| **Per-Slot Context Window** | `512` tokens per slot (`-c 2048` divided across 4 default parallel server slots) | Initial verbose prompts (`768` tokens) exceeded the 512-token slot and timed out. Compacting the step prompt + flat `json_schema` to `<280` tokens resolved slot overflow completely. |
| **Output Schema Complexity** | Flat `{action, unknown_code, tool}` JSON Schema (`max_tokens: 40`, `~18` generated tokens) | Nested object-array grammar caused slow CPU grammar sampling; flat enum schema generates in `1.8s–2.4s`. |
| **Single-Step Latency (CPU)** | `~5.8s – 7.5s` end-to-end (`~46 tok/s` prompt eval, `~8.2 tok/s` token generation) | Single-intent questions and clear schema unknowns terminate after Step 1 (`1` LLM call). |
| **Two-Step Iterative Latency (CPU)** | `~14.5s – 16.0s` end-to-end across 2 sequential LLM calls + 2 PostgreSQL tool reads | Used only for compound/multi-part questions (e.g., KPI bottleneck diagnosis + lowest-scoring agent). |
| **Concurrency Limit** | `1` concurrent exploration request (`_EXPLORATION_SLOT = threading.BoundedSemaphore(1)`) | Concurrent requests immediately fall back to deterministic routing (`<35 ms`) rather than queueing on CPU. |

---

## 5. Verification Summary

1. **Automated Pytest Verification (`57/57 PASSED`)**:
   - `Backend/tests/test_local_assistant_exploration.py` (`8/8 PASSED`, including live `Qwen3-4B-Q4_K_M` exploration test `test_live_qwen_model_explores_authorized_concepts_and_multi_part_evidence`):
     - Opt-in & production disablement (`test_exploration_disabled_by_default_and_in_production`)
     - Non-loopback endpoint rejection (`test_remote_or_non_loopback_endpoint_is_rejected`)
     - Authorized concept projection isolation (`test_authorized_concept_summary_never_leaks_unauthorized_scopes`)
     - Cross-scope isolation across team, branch, level, and self-only employee (`test_cross_scope_isolation_blocks_unauthorized_team_branch_level_and_peer_employee_requests`)
     - Malformed JSON, unknown tools, and SQL injection safe fallback (`test_malformed_requests_and_sql_injection_fall_back_safely`)
     - Clear schema unknowns without guessing (`test_clear_unknowns_disclose_missing_schema_concepts_without_guessing`)
     - Multi-part 2-step iterative evidence combination (`test_multi_part_iterative_exploration_combines_two_step_evidence`)
     - Live `Qwen3-4B-Q4_K_M` multi-part exploration & unknown detection (`test_live_qwen_model_explores_authorized_concepts_and_multi_part_evidence`)
   - Existing AI suites (`test_local_model_router.py`, `test_local_evidence_synthesis.py`, `test_contextual_assistant.py`, `test_ai_workspace.py`): all `49/49 PASSED`.
2. **Read-Only Local PostgreSQL Verification**:
   - Scoped `Inbound` (`dubai`, `Employee`) manager attempting to query `Outbound`: blocked with `outcome="restricted_access"`, `0` tool calls, `0` records read.
   - Multi-part query (`"Diagnose Inbound KPI gaps in September 2026 and show who is the lowest-scoring agent."`) on local PostgreSQL data: executed `get_kpi_diagnosis_and_trends` + `get_agent_spotlight_and_trend` (`70` scoped records evaluated across 2 tools), returning verified Dubai Inbound AHT (`83.0%` achievement, `3.01 min` vs `2.50 min` target) and lowest-scoring agent `Maryam Elsayed Mahmoud Eid (SGHD70250)` (`79.93%`, Grade `D`, Rank `#35 of 35`).
   - Unrecorded schema concepts (`salary/payroll bonus` and `HR hire/join date`) on local PostgreSQL data: returned `unsupported_request` and `clarification` (`MISSING_HR_JOIN_DATE`) with `0` database records read and zero hallucinated values.
