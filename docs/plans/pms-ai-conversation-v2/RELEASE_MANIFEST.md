# PMS AI Conversational Analytics v2 — Release Manifest

## 1. Executive Summary

PMS AI Conversational Analytics v2 has been implemented, audited against all independent review findings from commit `b470ef6`, and verified against `docs/plans/pms-ai-conversation-v2/IMPLEMENTATION_BLUEPRINT.md`.

- **Conversational Scenarios & Test Coverage**:
  - Backend pytest suites in `Backend/tests/test_ai_workspace.py` covering all 9 post-`b470ef6` review fixes (team-level replay authorization, legacy un-fingerprinted turn safety, live mid-request & context-restoration permission revalidation, best/worst month follow-ups & missing-score handling, full-request fingerprint & refreshed-context retry binding, Unicode-safe trace/training redaction & PII quarantine, hardened migration adoption & rollback, semantic answer correctness evaluation, and optional "AI is watching" rail).
  - `25/25` (`100.0%`, `0` failures) v2 conversational & multi-turn scenarios in `Backend/tests/fixtures/ai_questions/conversation_v2_scenarios.jsonl` evaluated via `Backend/scripts/evaluate_ai_classifier.py` (`verify_semantic_answer_correctness`) across `15` disjoint conversation/paraphrase families (`train`: `1/1`, `val`: `5/5`, held-out `test`: `19/19`, `paraphrase_split_zero_leakage: true`).
  - `15/15` (`100.0%`, `0` failures) contextual assistant scenarios in `Backend/tests/fixtures/ai_questions/contextual_assistant_scenarios.jsonl` covering `page_help`, `navigation`, `performance_query` with `PageContextV1`, `proposal`, fallback sample data refusal, and unauthorized `PageContextV1` refusal across `train` (`5/5`), `val` (`4/4`), and `test` (`6/6`) splits (`paraphrase_split_zero_leakage: true`).
  - `26/26` (`100.0%`) dialogue cases in `Backend/scripts/evaluate_call_center_dialogue.py`.
  - `6/6` (`100.0%`) frontend Vitest suites in `Frontend/src/pages/PmsAiWorkspaceView.test.tsx` and `6/6` (`100.0%`) in `Frontend/src/components/ai/ContextualAssistantPanel.test.tsx`.
- **Separated Split Routing Benchmark (`ai_english_questions.json`, 130 deduplicated questions across 64 paraphrase groups, zero group leakage)**:
  - `train` split: `59/59` (`100.0%`, `0` failures) on Hybrid Router (`24/59` on Legacy Router, `22` Classifier accepted / `37` Classifier abstained) across `28` paraphrase groups.
  - `val` split: `23/23` (`100.0%`, `0` failures) on Hybrid Router (`12/23` on Legacy Router, `3` Classifier accepted / `20` Classifier abstained) across `12` paraphrase groups.
  - Held-out `test` split: `48/48` (`100.0%`, `0` failures) on Hybrid Router (`16/48` on Legacy Router, `16` Classifier accepted / `32` Classifier abstained) across `24` paraphrase groups.
- **Evaluation Scope & Limitations**:
  - The `130`-question routing fixture (`2` exact cross-file duplicates `q095` and `q130` removed during Phase 0 deduplication), `25`-scenario v2 conversational suite, and `15`-scenario contextual assistant suite run against controlled synthetic fixtures (`16` performance records across `Inbound`, `Support Positions`, and `Coding` in `evaluate_ai_classifier.py`) to verify deterministic routing, RBAC boundary enforcement, follow-up context inheritance/override, missing-score handling, and semantic answer consistency.
  - These synthetic suites prove regression invariants and calculation parity on the covered fixtures; they do not by themselves measure open-ended live production phrasing accuracy.
  - Only `3` Call Center Employee scopes (`Inbound`, `Outbound`, `Support Positions`) hold full 6-gate certification (`certified: true`, `status: "verified"`); `4` scopes (`Coding`, `Pre-Approvals IP Offshore`, `Marketing`, `Pharmacy`) hold `partial_evidence`, and `11` allowlisted scopes remain `unverified` (`certified: false`) pending full multi-period source-evidence parity datasets.
- **Server-Owned Conversation Concurrency, Replay Authorization & Live Permission Revalidation**:
  - Automatic server-owned `AiConversation` creation on Turn 1 when `conversation_id` is `None`.
  - Optimistic concurrency (`expected_context_version`) verified before claiming a pending turn and atomically with worker `claim_token` upon completion; stale requests release claims immediately so corrected retries are never blocked until the claim deadline.
  - Canonical `scope_fingerprint` (`canonical_scope_identity`) binds all effective authorization dimensions (`role`, `is_active`, `is_self_only`, `employee_id`, `has_unrestricted_team_access`, `accessible_functions`, `accessible_regions`, `accessible_branches`, `accessible_teams`, and `accessible_team_levels`).
  - Replay checks additionally revalidate live database user/assignment state (`build_user_scope_from_db_user`) and specific turn evidence (`_is_turn_evidence_authorized`) before returning any cached response.
  - Legacy turns lacking complete `request_fingerprint`, `scope_fingerprint`, or `eval_id` metadata are treated as unverified and recomputed after validating current request and scope rather than replaying unverified payloads.
  - Live permissions are revalidated at turn start, after slow tool/provider operations before committing or returning an answer, and when restoring `GET /api/ai/conversations/{id}/context` (redacting unauthorized employees, pending choices, and confirmed context without leaking restricted identities).
- **Unicode-Safe Privacy Redaction & Training Curation Boundaries**:
  - Full and partial employee names across Latin, Arabic, accented, hyphenated, and mixed-script text are redacted (`<EMPLOYEE_NAME>`) alongside employee IDs, emails, and UAE/Egypt phone numbers across prompts and nested trace/export structures.
  - `assess_pii_quarantine` flags uncertain person references or residual PII (`pii_quarantined: true`) and excludes unreviewed quarantined rows from training exports.
  - `export_distillation_dataset(verified_only=True)` exports only rows explicitly verified by an Admin (`is_distillation_eligible=True` AND `reviewer_verified=True`).
- **Classifier Promotion Decision**:
  - **`DO_NOT_PROMOTE_KEEP_HYBRID_RULES`** (`runtime_dependency_added: false` in `Backend/requirements.txt`; evaluation dependencies isolated in `Backend/requirements-ai-eval.txt`).

---

## 2. Verified Conversational & Multi-Turn Scenarios (`conversation_v2_scenarios.jsonl`)

Evaluated via `verify_semantic_answer_correctness` in `Backend/scripts/evaluate_ai_classifier.py` (enforcing validated operation presence, yes/no vs. open-ended polarity, person/direction/period/value semantic binding, tie reporting, and missing-month headline disclosures):

| Scenario ID | Split | Paraphrase Family | User Prompt / Context | Expected & Verified Outcome |
| --- | --- | --- | --- | --- |
| `v2_s01_greeting` | `test` | `social_greeting` | `Hi` | `answer` (`greeting`, open polarity), one-sentence English greeting, `0` performance reads (`tool_calls: []`). |
| `v2_s02_thanks` | `test` | `social_thanks` | `Thanks` | `answer` (`thanks`, open polarity), one-sentence English closing reply, `0` performance reads (`tool_calls: []`). |
| `v2_s03_mariam_new_joiner` | `test` | `person_tenure_mariam` | `Is Mariam Ali a new joiner in Inbound?` | `clarification` (`MISSING_HR_JOIN_DATE`): states `Mariam Ali`'s first available Inbound record is `July 2026` and that PMS has no verified HR joining date. |
| `v2_s04_support_lowest_position` | `test` | `support_lowest_person_position` | `Who is lowest in Support and what is his position?` | `answer` (`ranking`, `direction="worst"`, `Support Positions`): returns `Kareem Adel (EMP701 · Quality Assurance)` at `62.0%`, explicitly reporting the tie with `Ziad Nabil (EMP702 · Trainer)`. |
| `v2_s05_adham_best_month_sep` | `test` | `person_best_period_adham` | `Was September Adham's best month?` | `answer` (`person_best_period`, `no` polarity): `No. Adham Tarek (EMP501) scored 91.0% in September 2026, while their best month across March–September 2026 by Overall PMS Score was August 2026 at 96.5%.` |
| `v2_s06_adham_followup_august` | `test` | `person_best_period_adham` | `What about August?` (following `v2_s05`) | `answer` (`person_best_period`, `yes` polarity, inherits `EMP501`): `Yes. August 2026 was Adham Tarek's (EMP501) best month across March–September 2026 in Inbound by Overall PMS Score at 96.5%.` |
| `v2_s07_three_branch_booking_counts` | `test` | `branch_booking_count_3way` | `Which has more bookings: Dubai, Ajman or Sharjah?` | `answer` (`compare_branches` on `inbound:bookings_count`): `Dubai led September 2026 Inbound bookings with 345, followed by Sharjah with 155 and Ajman with 125.` |
| `v2_s08_booking_trend_and_best` | `test` | `multipart_booking_trend_rank` | `Show booking trend and who is best in Inbound` | `answer` (`trend` + `ranking`, `direction="best"`): reports Booking Rate trend and `#1 top performer` `Mariam Mohssen Mahmoud (SGHD70231)` at `28.0% Booking Rate (Overall Score 94.4%)`. |
| `v2_s09_correction_lowest` | `test` | `multipart_booking_trend_rank` | `No, I mean the lowest` (following `v2_s08`) | `answer` (`ranking`, mutates `direction="worst"` while preserving `Inbound`, `inbound:booking_rate`, `2026-09`): returns `Maryam Elsayed Mahmoud Eid (SGHD70250)` (`lowest-scoring`) and lists ties. |
| `v2_s10_count_vs_rate_bookings` | `val` | `count_vs_rate_bookings` | `How many bookings did Inbound get in Dubai vs Sharjah?` | `answer` (`compare_branches` on `inbound:bookings_count`): `Dubai led September 2026 Inbound bookings with 345, followed by Sharjah with 155.` |
| `v2_s11_booking_rate_comparison` | `val` | `count_vs_rate_bookings` | `Compare Dubai and Sharjah Booking Rate for Inbound` | `answer` (`compare_branches` on `inbound:booking_rate`): `In September 2026, Dubai leads at 93.2% vs. Sharjah at 77.7% (15.5 pts gap).` |
| `v2_s12_ambiguous_attendance` | `train` | `ambiguous_attendance` | `What is Attendance in Call Center?` | `clarification` (`AMBIGUOUS_ATTENDANCE_DEFINITION`): asks whether to inspect Employee Patient Attendance Rate or Managerial Attendance Compliance. |
| `v2_s13_mariam_statement_order_inbound_manager` | `test` | `person_tenure_mariam` | `mariam is new joiner in inbound team ?` (`Manager` scoped to `Inbound`) | `clarification` (`AMBIGUOUS_PERSON`): `I found three Mariams in Inbound. Which one do you mean?` listing `Mariam Ali`, `Mariam Mohssen Mahmoud`, and `Maryam Elsayed Mahmoud Eid`. |
| `v2_s14_branch_director_3branch_restricted` | `test` | `branch_booking_count_3way_rbac` | `Which has more bookings: Dubai, Ajman or Sharjah?` (`Branch Director` scoped to `dubai`) | `restricted_access`: refuses Ajman/Sharjah branch read (`0` tool calls) and never substitutes Dubai-only data. |
| `v2_s15_branch_director_managerial_bsc_guardrail` | `test` | `branch_director_bsc_guardrail` | `Show Inbound Managerial Balanced Scorecard in September 2026` (`Branch Director` scoped to `dubai`) | `answer` (guardrail notice, `0` records evaluated): explains that Managerial and Corporate Balanced Scorecards are evaluated at the team level and not partitioned by individual UAE hospital branches. |
| `v2_s16_inbound_manager_support_restricted` | `test` | `support_lowest_person_position_rbac` | `Who is lowest in Support and what is his position?` (`Manager` scoped to `Inbound`) | `restricted_access` (`0` tool calls): `Access restricted: your role does not have permission to view Support Positions data.` |
| `v2_s17_rcm_director_inbound_restricted` | `test` | `cross_function_rbac_rcm` | `What is Inbound Abandon Rate in September 2026?` (`Function Director` scoped to `RCM`) | `restricted_access` (`0` tool calls): `Access restricted: your role does not have permission to view Inbound data.` |
| `v2_s18_rcm_director_coding_authorized` | `test` | `cross_function_rbac_rcm` | `What is Coding score in September 2026?` (`Function Director` scoped to `RCM`) | `answer`: returns authorized `Coding` score (`92.1%`) in September 2026. |
| `v2_s19_adham_worst_month` | `test` | `person_worst_period_adham` | `What was Adham's worst month?` | `answer` (`person_worst_period`, open polarity — does not start with `No.`): `Adham Tarek's (EMP501) worst month across March–September 2026 in Inbound by Overall PMS Score was March 2026 at 82.0%.` |
| `v2_s20_adham_pronoun_lowest_score` | `test` | `person_worst_period_adham` | `Which month had his lowest score?` (following `person_best_period`) | `answer` (`person_worst_period`, open polarity, overrides inherited best-month operation): `Adham Tarek's (EMP501) worst month across March–September 2026 in Inbound by Overall PMS Score was March 2026 at 82.0%.` |
| `v2_s21_adham_worst_then_best_followup` | `test` | `person_worst_period_adham` | `And his best month?` (following `person_worst_period`) | `answer` (`person_best_period`, open polarity, overrides inherited worst-month operation): `Adham Tarek's (EMP501) best month across March–September 2026 in Inbound by Overall PMS Score was August 2026 at 96.5%.` |
| `v2_s22_adham_best_then_worst_followup` | `test` | `person_best_period_adham` | `What about his worst?` (following `person_best_period`) | `answer` (`person_worst_period`, open polarity, overrides inherited best-month operation): `Adham Tarek's (EMP501) worst month across March–September 2026 in Inbound by Overall PMS Score was March 2026 at 82.0%.` |
| `v2_s23_salma_missing_month_may` | `val` | `person_missing_and_ties_salma` | `What was Salma Fathy's score in May 2026?` | `answer` (`unavailable` polarity — never borrows another month's score): `No published evaluation score is available for Salma Fathy (EMP502) in May 2026 (Inbound). Published scores are available across March–June 2026.` |
| `v2_s24_salma_later_month_june_above_100` | `val` | `person_missing_and_ties_salma` | `What about June 2026?` (following `v2_s23`) | `answer` (open polarity, preserves precision & score > 100): `Salma Fathy (EMP502) scored 104.35% (Grade A, Rank #1 of 2 in Inbound) in June 2026, moving +30.1% vs April (+30.1% since March).` |
| `v2_s25_salma_worst_month_tie_and_missing_limitation` | `val` | `person_missing_and_ties_salma` | `What was Salma Fathy's worst month?` | `answer` (`person_worst_period`, open polarity, ties + missing-month limitation in brief headline): `Salma Fathy's (EMP502) worst month across March–June 2026 in Inbound by Overall PMS Score was March 2026 and April 2026 (tied) at 74.25%. (Note: May 2026 had no evaluated score and was excluded.)` |

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

| Split | Questions | Paraphrase Groups | Legacy Router Matched / Failed | Hybrid Router Matched / Failed | Hybrid Provider Calls | Classifier Accepted (Failed) | Classifier Abstained | Classifier Accepted Precision | Classifier Overall (with Fallback) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `train` | 59 | 28 | 24 / 35 (40.68%) | **59 / 0 (100.0%)** | 0 | 22 (0) | 37 | 100.0% | 100.0% |
| `val` | 23 | 12 | 12 / 11 (52.17%) | **23 / 0 (100.0%)** | 0 | 3 (0) | 20 | 100.0% | 100.0% |
| `test` (held-out) | 48 | 24 | 16 / 32 (33.33%) | **48 / 0 (100.0%)** | 0 | 16 (0) | 32 | **100.0%** | **100.0%** |

- **Paraphrase-grouped split leakage**: `0` overlapping paraphrase groups across `train` (28), `val` (12), and `test` (24) in `ai_english_questions.json`, `0` overlapping conversation/paraphrase families across `train` (1), `val` (2), and `test` (12) in `conversation_v2_scenarios.jsonl`, and `0` overlapping paraphrase groups across `train` (5), `val` (4), and `test` (6) in `contextual_assistant_scenarios.jsonl`.
- **Accepted local precision (`test`)**: `100.0%` (`16/16` accepted, `0` failed; Target: `>= 99.0%`) — **PASS**
- **Overall accuracy with fallback (`test`)**: `100.0%` (`48/48`; Target: `>= 95.0%`) — **PASS**
- **Decision**: **`DO_NOT_PROMOTE_KEEP_HYBRID_RULES`**. Production runtime remains free of `scikit-learn` (`runtime_dependency_added: false`) and `LocalIntentClassifier.from_fixture_train_split()` has been removed from live request routing (`classifier_mode = "off"` in production).

---

## 6. Database Migration Adoption & Safe Rollback Verification

- **Single Alembic Head**: `c9e1a2b3d4f5` (`Backend/migrations/versions/c9e1a2b3d4f5_add_ai_conversations_and_turns.py`, `down_revision = "7b056bf2c4d6"`).
- **Staging & Production Runtime DDL Disabled**: Both `AiConversationRepository` and `ensure_trace_schema_once` disable request-time DDL when `APP_ENV` is `staging` or `production` (or `PMS_DISABLE_RUNTIME_DDL=true`), raising a controlled `ConversationMigrationUnavailableError` (HTTP 503) if migrations have not been applied.
- **Schema Compatibility Inspection Before Adoption**: When adopting an existing `ai_interaction_traces`, `ai_conversations`, or `ai_turns` table, `c9e1a2b3d4f5.upgrade()` inspects actual columns, data types, primary keys, and unique constraints, stopping with a clear `RuntimeError` diagnostic if required base columns are missing or have incompatible types.
- **Safe Application Rollback & Non-Destructive Downgrade**:
  1. **Application Rollback (Recommended, Zero Data Loss)**: Set `PMS_AI_CONVERSATION_STATE_ENABLED=false` to revert the orchestrator to stateless session context while preserving all persisted conversations, turns, traces, and Admin review records.
  2. **Schema Downgrade Guard**: `c9e1a2b3d4f5.downgrade()` never drops columns (`turn_id`, `reviewer_verified`, `reviewer_id`, `reviewed_at`) from `ai_interaction_traces` (preventing removal of pre-existing columns on runtime-adopted tables) and refuses to drop `ai_turns` or `ai_conversations` if persisted turns, conversations, or reviewed/linked trace rows exist (unless `PMS_ALLOW_DESTRUCTIVE_AI_DOWNGRADE=1` is explicitly set in disposable test environments).
- **Disposable Schema Verification**: Verified across fresh PostgreSQL schemas, production-shaped pre-v2 trace tables (preserving existing trace rows), runtime-created trace tables (preserving pre-existing v2 columns across upgrade and downgrade), and incompatible partial tables (stopping with `RuntimeError`).

---

## 7. Rollout & Rollback Flags

- `PMS_AI_CONVERSATION_STATE_ENABLED=true`: Enables server-owned `AiConversation` and `AiTurn` persistence, `context_version` optimistic concurrency, and `client_request_id` idempotency. Set to `false` to fall back to stateless session context without schema changes.
- `PMS_AI_ROUTER_MODE=hybrid`: Uses deterministic local rules + entity resolver first and only calls Gemini when `PMS_AI_GEMINI_ROUTING_ENABLED=true` and local routing abstains.
- `PMS_AI_CLASSIFIER_MODE=disabled`: Keeps the local ML classifier disabled in production runtime per the promotion gate decision.
- `PMS_AI_ENABLED_SCOPES`: Optional comma-separated team allowlist override (defaults to all 18 configured scopes while `get_scope_certification_registry()` tracks the 3 fully certified Call Center Employee scopes separately).
