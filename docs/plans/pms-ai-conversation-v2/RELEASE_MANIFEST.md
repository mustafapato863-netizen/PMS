# PMS AI Conversational Analytics v2 — Release Manifest

## 1. Executive Summary

PMS AI Conversational Analytics v2 has been implemented, audited against all 9 review findings, and verified against `docs/plans/pms-ai-conversation-v2/IMPLEMENTATION_BLUEPRINT.md`.

- **Conversational Scenarios & Test Coverage**:
  - `18/18` backend pytest suites in `Backend/tests/test_ai_workspace.py` (including `test_v2_review_findings_all_nine_fixes`).
  - `20/20` (`100.0%`) v2 conversational & multi-turn scenarios in `Backend/tests/fixtures/ai_questions/conversation_v2_scenarios.jsonl` evaluated via `Backend/scripts/evaluate_ai_classifier.py` with independent expected numeric/string assertions (`train`: `1/1`, `val`: `2/2`, held-out `test`: `17/17`).
  - `26/26` (`100.0%`) dialogue cases in `Backend/scripts/evaluate_call_center_dialogue.py`.
  - `7/7` (`100.0%`) frontend Vitest suites in `Frontend/src/pages/PmsAiWorkspaceView.test.tsx`.
- **Separated Split Routing Accuracy (`ai_english_questions.json`, 132 questions across 64 paraphrase groups, zero group leakage)**:
  - `train` split: `59/59` (`100.0%`) across `28` paraphrase groups.
  - `val` split: `24/24` (`100.0%`) across `12` paraphrase groups.
  - Held-out `test` split: `49/49` (`100.0%`) across `24` paraphrase groups (exceeding the `>= 95.0%` target gate).
- **Dashboard & Presentation Numeric Parity**:
  - **100%** numeric parity across Call Center (`Inbound`, `Outbound`, `Support Positions`), 3-branch booking counts (`dubai`, `ajman`, `sharjah`), best (`person_best_period`) vs. worst (`person_worst_period`) month evaluation without pre-ranking rounding or `100.0` score caps, explicit tie reporting, and `None` score preservation.
- **Server-Owned Conversation Concurrency & Replay Safety**:
  - Automatic server-owned `AiConversation` creation on Turn 1 when `conversation_id` is `None`.
  - Optimistic concurrency (`expected_context_version`) and worker `claim_token` verification enforced atomically when completing turns.
  - Idempotent `client_request_id` bound to a canonical `request_fingerprint` (`RequestIdReuseConflictError` -> HTTP 409 on payload mismatch) and revalidated against live account status, `scope_fingerprint`, and `eval_id` (`evaluation_cache_identity(db)` + data/config versions) before replaying completed responses.
  - Controlled `ConversationDeletedError` (HTTP 404) on late requests to soft-deleted conversations.
- **Privacy, Name Redaction & Training Curation Boundaries**:
  - Full and partial employee names are redacted (`<EMPLOYEE_NAME>`) alongside employee IDs, emails, and UAE/Egypt phone numbers in stored turn prompts, interaction traces, and legacy trace exports.
  - End-user thumbs-up feedback sets `is_distillation_eligible=True` and never sets `reviewer_verified=True`.
  - `export_distillation_dataset(verified_only=True)` filters strictly by `is_distillation_eligible.is_(True)` AND `reviewer_verified.is_(True)` (Admin-only via `POST /api/ai/traces/{trace_id}/review`).
- **Classifier Promotion Decision**:
  - **`DO_NOT_PROMOTE_KEEP_HYBRID_RULES`** (`runtime_dependency_added: false` in `Backend/requirements.txt`; evaluation dependencies isolated in `Backend/requirements-ai-eval.txt`).

---

## 2. Verified Conversational & Multi-Turn Scenarios (`conversation_v2_scenarios.jsonl`)

Evaluated against independent expected numeric and string values in `Backend/scripts/evaluate_ai_classifier.py`:

| Scenario ID | Split | User Prompt / Context | Expected & Verified Outcome |
| --- | --- | --- | --- |
| `v2_s01_greeting` | `test` | `Hi` | `answer` (`greeting`), one-sentence English greeting, `0` performance reads (`tool_calls: []`). |
| `v2_s02_thanks` | `test` | `Thanks` | `answer` (`thanks`), one-sentence English closing reply, `0` performance reads (`tool_calls: []`). |
| `v2_s03_mariam_new_joiner` | `test` | `Is Mariam Ali a new joiner in Inbound?` | `clarification` (`MISSING_HR_JOIN_DATE`): states `Mariam Ali`'s first available Inbound record is `July 2026` and that PMS has no verified HR joining date. |
| `v2_s04_support_lowest_position` | `test` | `Who is lowest in Support and what is his position?` | `answer` (`ranking` on `Support Positions`): returns `Kareem Adel (EMP701 · Quality Assurance)` at `62.0%`, explicitly reporting the tie with `Ziad Nabil (EMP702 · Trainer)`. |
| `v2_s05_adham_best_month_sep` | `test` | `Was September Adham's best month?` | `answer` (`person_best_period`): `No. Adham Tarek (EMP501) scored 91.0% in September 2026, while their best month across March–September 2026 by Overall PMS Score was August 2026 at 96.5%.` |
| `v2_s06_adham_followup_august` | `test` | `What about August?` (following `v2_s05`) | `answer` (`person_best_period`, inherits `EMP501`): `Yes. August 2026 was Adham Tarek's (EMP501) best month across March–September 2026 in Inbound by Overall PMS Score at 96.5%.` |
| `v2_s07_three_branch_booking_counts` | `test` | `Which has more bookings: Dubai, Ajman or Sharjah?` | `answer` (`compare_branches` on `call_center:bookings_count`): `Dubai led September 2026 Inbound bookings with 345, followed by Sharjah with 155 and Ajman with 125.` |
| `v2_s08_booking_trend_and_best` | `test` | `Show booking trend and who is best in Inbound` | `answer` (`trend` + `ranking` on `inbound:booking_rate`): reports April–September 2026 Booking Rate trend (`28.0%`) and `#1 top performer` `Mariam Mohssen Mahmoud (SGHD70231)` at `28.0% Booking Rate (Overall Score 94.4%)`. |
| `v2_s09_correction_lowest` | `test` | `No, I mean the lowest` (following `v2_s08`) | `answer` (`ranking`, mutates `ranking_direction="worst"` while preserving `Inbound`, `inbound:booking_rate`, `2026-09`): returns `Maryam Elsayed Mahmoud Eid (SGHD70250)` (`lowest-scoring`) and lists ties. |
| `v2_s10_count_vs_rate_bookings` | `val` | `How many bookings did Inbound get in Dubai vs Sharjah?` | `answer` (`compare_branches` on `call_center:bookings_count`): `Dubai led September 2026 Inbound bookings with 345, followed by Sharjah with 155.` |
| `v2_s11_booking_rate_comparison` | `val` | `Compare Dubai and Sharjah Booking Rate for Inbound` | `answer` (`compare_branches` on `inbound:booking_rate`): `In September 2026, Dubai leads at 93.2% vs. Sharjah at 77.7% (15.5 pts gap).` |
| `v2_s12_ambiguous_attendance` | `train` | `What is Attendance in Call Center?` | `clarification` (`AMBIGUOUS_ATTENDANCE_DEFINITION`): asks whether to inspect Employee Patient Attendance Rate or Managerial Attendance Compliance. |
| `v2_s13_mariam_statement_order_inbound_manager` | `test` | `mariam is new joiner in inbound team ?` (`Manager` scoped to `Inbound`) | `clarification` (`AMBIGUOUS_PERSON`): `I found three Mariams in Inbound. Which one do you mean?` listing `Mariam Ali`, `Mariam Mohssen Mahmoud`, and `Maryam Elsayed Mahmoud Eid` (excluding CSR Mariam). |
| `v2_s14_branch_director_3branch_restricted` | `test` | `Which has more bookings: Dubai, Ajman or Sharjah?` (`Branch Director` scoped to `dubai`) | `restricted_access`: refuses Ajman/Sharjah branch read (`0` tool calls) and never substitutes Dubai-only data. |
| `v2_s15_branch_director_managerial_bsc_guardrail` | `test` | `Show Inbound Managerial Balanced Scorecard in September 2026` (`Branch Director` scoped to `dubai`) | `answer` (guardrail notice, `0` records evaluated): explains that Managerial and Corporate Balanced Scorecards are evaluated at the team level and not partitioned by individual UAE hospital branches. |
| `v2_s16_inbound_manager_support_restricted` | `test` | `Who is lowest in Support and what is his position?` (`Manager` scoped to `Inbound`) | `restricted_access`: `Access restricted: your role does not have permission to view Support Positions data.` |
| `v2_s17_rcm_director_inbound_restricted` | `test` | `What is Inbound Abandon Rate in September 2026?` (`Function Director` scoped to `RCM`) | `restricted_access`: `Access restricted: your role does not have permission to view Inbound data.` |
| `v2_s18_rcm_director_coding_authorized` | `test` | `What is Coding score in September 2026?` (`Function Director` scoped to `RCM`) | `answer`: returns authorized `Coding` score (`92.1%`) in September 2026. |
| `v2_s19_adham_worst_month` | `test` | `What was Adham's worst month?` | `answer` (`person_worst_period`): `No. Adham Tarek (EMP501) scored 91.0% in September 2026, while their worst month across March–September 2026 by Overall PMS Score was March 2026 at 82.0%.` |
| `v2_s20_adham_pronoun_lowest_score` | `test` | `Which month had his lowest score?` (pronoun follow-up on `EMP501`) | `answer` (`person_worst_period`, inherits `Adham Tarek (EMP501)`): reports `March 2026 at 82.0%`. |

---

## 3. Scope Allowlisting vs. 6-Gate Certification Status

`AiKpiCatalog.get_scope_certification_registry()` separates runtime allowlisting (`enabled`, controlled via `PMS_AI_ENABLED_SCOPES`) from 6-gate verification (`certified`, requiring all 6 gates: `source_mappings`, `metric_semantics`, `calculations`, `permissions`, `periods`, `destination_links`):

| Scope / Team | Parent Function | Enabled (Allowlist) | Certified (All 6 Gates) | Status | Verification Notes |
| --- | --- | --- | --- | --- | --- |
| `Inbound` | Call Center | `true` | **`true`** | `verified` | Full 6-gate parity verified against Monthly Presentation and Team Scorecard (`Attendance` 70%, `Booking` 20%, `Other/Abandon Rate` 10%, branch projections, and Managerial/Corporate BSC structure). |
| `Outbound` | Call Center | `true` | **`true`** | `verified` | Full 6-gate parity verified (`Attendance` 70%, `Booking` 20%, `Other/Reachability` 10%, branch projections). |
| `Support Positions` | Call Center | `true` | **`true`** | `verified` | Full 6-gate parity verified for Call Center records with stored positions (`Quality Assurance`, `Trainer`, `Analytics Specialist`, `Supervisor`, `Team Leader`, `Real-Time Analyst`). |
| `Coding` | RCM | `true` | `false` | `partial_evidence` | Catalog metrics, permissions, periods, and links verified; full multi-period calculation parity pending additional production fixture coverage. |
| `Pre-Approvals IP Offshore` | Pre-Approvals | `true` | `false` | `partial_evidence` | June 2026 (`2026-06`) controllable `Rejection` (50% weight) vs. tracking-only `PolicyRejection` (0% weight) basis warning verified; full calculation gate pending broader historical fixtures. |
| `Marketing` | Marketing | `true` | `false` | `partial_evidence` | Position-specific metrics (`Media Buyer` CPL, `Graphic Designer` Rework) verified; calculation gate marked unverified pending full position-level parity dataset. |
| `Pharmacy` | Pharmacy | `true` | `false` | `partial_evidence` | Scored `WaitingTime` (20% weight) vs. diagnostic 0-weight `AJM Pharmacy Manager` `IV Cost Saving` verified; calculation gate pending full branch/position parity dataset. |
| Remaining 11 Teams (`Submission`, `Re-Submission`, `Collections`, `Denial Management`, `Pre-Approvals OP Dubai`, `Pre-Approvals IP Initial Dubai`, `Pre-Approvals IP Final Dubai`, `Pre-Approvals OP Sharjah`, `Pre-Approvals OP Ajman`, `CSR`, `Sales`) | RCM / Pre-Approvals / CSR / Sales | `true` | `false` | `unverified` | Allowlisted for standard dashboard read routing; marked `certified: false` (`status: "unverified"`) until dedicated source-evidence and calculation parity checks are completed. |

---

## 4. Latency Benchmark (200 Employees / Team, 1,000 Records)

Measured via `Backend/scripts/certify_scopes_and_benchmark.py`:

| Workload Category | Cold p50 (ms) | Cold p95 (ms) | Warm p50 (ms) | Warm p95 (ms) | Target Gate | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `routine_local` | 81.15 | 211.50 | 140.57 | 240.13 | < 1,000 ms p95 | PASS |
| `single_kpi` | 75.54 | 85.73 | 156.44 | 187.99 | < 3,000 ms p95 | PASS |
| `standard_comparison` | 348.41 | 426.92 | 180.75 | 240.02 | < 5,000 ms p95 | PASS |

---

## 5. Local Classifier Evaluation & Gate Decision

Measured via `Backend/scripts/evaluate_ai_classifier.py` (artifact stored at `docs/benchmarks/pms_ai_v2_classifier_manifest.json`):

| Split | Questions | Paraphrase Groups | Legacy Router Exact Match | Hybrid Router Exact Match | Hybrid Provider Calls | Classifier Accepted | Classifier Abstained | Classifier Accepted Precision | Classifier Overall (with Fallback) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `train` | 59 | 28 | 40.68% | **100.0%** | 2 | 22 | 37 | 100.0% | 100.0% |
| `val` | 24 | 12 | 50.00% | **100.0%** | 1 | 4 | 20 | 100.0% | 100.0% |
| `test` (held-out) | 49 | 24 | 32.65% | **100.0%** | 2 | 16 | 33 | **100.0%** | **100.0%** |

- **Paraphrase-grouped split leakage**: `0` overlapping paraphrase groups across `train` (28), `val` (12), and `test` (24).
- **Accepted local precision (`test`)**: `100.0%` (Target: `>= 99.0%`) — **PASS**
- **Overall accuracy with fallback (`test`)**: `100.0%` (Target: `>= 95.0%`) — **PASS**
- **Provider call reduction vs. Hybrid Rules (`test`)**: `-1550.0%` (Hybrid deterministic rules needed only `2` provider calls across `49` held-out questions, whereas the local classifier abstained on `33` questions; Target: `>= 20.0%` reduction) — **FAIL**
- **Decision**: **`DO_NOT_PROMOTE_KEEP_HYBRID_RULES`**. Production runtime remains free of `scikit-learn` (`runtime_dependency_added: false`); offline evaluation dependencies remain isolated in `Backend/requirements-ai-eval.txt`.

---

## 6. Database Migration & Rollback Verification

- **Single Alembic Head**: `c9e1a2b3d4f5` (`Backend/migrations/versions/c9e1a2b3d4f5_add_ai_conversations_and_turns.py`, down_revision `b8f4e2a1c9d0`).
- **Production Runtime DDL Disabled**: `AiConversationRepository.ensure_tables()` refuses request-time DDL when `APP_ENV=production` or `PMS_DISABLE_RUNTIME_DDL=true`, raising a controlled `ConversationMigrationUnavailableError` (HTTP 503) if migrations have not been applied.
- **Disposable Schema Upgrade & Downgrade Verified**: Verified in `test_v2_review_findings_all_nine_fixes` against both isolated in-memory schemas (including pre-existing minimal `ai_interaction_traces` tables without new columns) and disposable PostgreSQL schemas (`CREATE SCHEMA tmp_ai_mig_<uuid>` -> `upgrade()` -> `downgrade()` -> `DROP SCHEMA ... CASCADE`) without touching the shared `public` schema.

---

## 7. Rollout & Rollback Flags

- `PMS_AI_CONVERSATION_STATE_ENABLED=true`: Enables server-owned `AiConversation` and `AiTurn` persistence, `context_version` optimistic concurrency, and `client_request_id` idempotency. Set to `false` to fall back to stateless session context.
- `PMS_AI_ROUTER_MODE=hybrid`: Uses deterministic local rules + entity resolver first and only calls Gemini when `PMS_AI_GEMINI_ROUTING_ENABLED=true` and local routing abstains.
- `PMS_AI_CLASSIFIER_MODE=disabled`: Keeps the local ML classifier disabled in production runtime per the promotion gate decision.
- `PMS_AI_ENABLED_SCOPES`: Optional comma-separated team allowlist override (defaults to all 18 configured scopes while `get_scope_certification_registry()` tracks the 3 fully certified Call Center Employee scopes separately).
