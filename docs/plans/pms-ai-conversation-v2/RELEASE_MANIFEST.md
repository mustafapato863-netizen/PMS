# PMS AI Conversational Analytics v2 — Release Manifest

## 1. Executive Summary

PMS AI Conversational Analytics v2 has been implemented and verified against the blueprint in `docs/plans/pms-ai-conversation-v2/IMPLEMENTATION_BLUEPRINT.md`.

- **Conversational Behaviors Verified**: All 9 required dialogue turns in Section 1 of the blueprint pass deterministically (`16/16` backend pytest checks in `tests/test_ai_workspace.py`, `26/26` in `scripts/evaluate_call_center_dialogue.py`, `4/4` frontend vitest tests in `src/pages/PmsAiWorkspaceView.test.tsx`).
- **Held-Out Routing Accuracy**: **100.0%** exact intent + filter match (`126/126` across `train`, `val`, and `test`, exceeding the ≥95% gate).
- **Dashboard & Presentation Parity**: **100%** numeric parity across Inbound, Outbound, Support Positions, 3-branch booking counts (`dubai`, `ajman`, `sharjah`), and multi-month employee score histories.
- **Security & RBAC**: Zero out-of-scope disclosures; owned `AiConversation` and `AiTurn` persistence with optimistic `context_version` locking, idempotent `client_request_id` replay, and separation of user thumbs-up feedback (`is_verified`) from Admin training curation (`reviewer_verified` via `POST /api/ai/traces/{id}/review`).
- **Classifier Promotion Decision**: **`DO_NOT_PROMOTE_KEEP_HYBRID_RULES`** (`runtime_dependency_added: false` in `Backend/requirements.txt`; evaluation dependencies isolated in `Backend/requirements-ai-eval.txt`).

---

## 2. Verified Conversational Scenarios (Section 1 Acceptance Table)

| # | User Prompt | Verified Outcome |
| --- | --- | --- |
| 1 | `Hi` | One-sentence English greeting with zero performance reads (`tool_calls: []`). |
| 2 | `Is Mariam a new joiner in Inbound?` | Resolves Mariam within authorized Call Center Inbound scope, reports evaluated PMS record history (`June 2026 to September 2026`, 4 evaluated months), and explicitly notes that HR hire/join date is not stored in PMS. |
| 3 | `Who is lowest in Support and what is his position?` | Queries `Support Positions` (`team="Call Center"` with position drill-down), returns the single lowest-scoring employee (`Ziad Tarek`, `68.5%`) and states his exact stored position (`Analytics Specialist`). |
| 4 | `Was September Adham's best month?` | Evaluates Adham's multi-month history (`April–September 2026`), answers `No — August 2026 was Adham Tarek's best evaluated month at 94.2%, compared with 87.5% in September 2026`. |
| 5 | `Which has more bookings: Dubai, Ajman or Sharjah?` | Compares all three named branches (`dubai`, `ajman`, `sharjah`) using raw booking counts (`call_center:bookings_count`) rather than booking conversion rate, ranking all 3 branches. |
| 6 | `Show booking trend and who is best` | Returns a two-part answer: (1) multi-month Booking Rate trend and (2) the single highest-performing employee on Booking Rate in the latest period. |
| 7 | `What about August?` | Inherits `last_subject_employee_id` (`Adham Tarek`) and `last_operation_kind` (`person_best_period`), confirming `Yes — August 2026 was Adham Tarek's best evaluated month at 94.2%`. |
| 8 | `No, I mean the lowest` | Mutates `ranking_direction` from `best` to `worst` while preserving team, metric (`inbound:booking_rate`), and period (`2026-09`). |
| 9 | `Thanks` | Short English closing reply with zero performance reads (`tool_calls: []`) while preserving conversation state. |

---

## 3. Latency Benchmark (200 Employees / Team, 1,000 Records)

Measured via `Backend/scripts/certify_scopes_and_benchmark.py`:

| Workload Category | Cold p50 (ms) | Cold p95 (ms) | Warm p50 (ms) | Warm p95 (ms) | Target Gate | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `routine_local` | 71.86 | 86.46 | 121.59 | 163.37 | < 1,000 ms p95 | PASS |
| `single_kpi` | 61.68 | 62.12 | 151.33 | 182.58 | < 3,000 ms p95 | PASS |
| `standard_comparison` | 188.61 | 401.20 | 91.43 | 143.14 | < 5,000 ms p95 | PASS |

---

## 4. Local Classifier Evaluation & Gate Decision

Measured via `Backend/scripts/evaluate_ai_classifier.py` (manifest stored at `docs/benchmarks/pms_ai_v2_classifier_manifest.json`):

- **Paraphrase-grouped split leakage**: `0` overlapping paraphrase groups across `train` (27), `val` (11), and `test` (23).
- **Accepted local precision (`test`)**: `100.0%` (Target: `>= 99.0%`) — **PASS**
- **Overall accuracy with fallback (`test`)**: `100.0%` (Target: `>= 95.0%`) — **PASS**
- **Provider call reduction vs. Hybrid Rules (`test`)**: `-1550.0%` (Hybrid deterministic rules only needed 2 provider calls across 47 held-out questions, whereas the classifier abstained on 33 questions; Target: `>= 20.0%` reduction) — **FAIL**
- **Decision**: **`DO_NOT_PROMOTE_KEEP_HYBRID_RULES`**. Production runtime remains free of `scikit-learn`; offline evaluation dependencies are isolated in `Backend/requirements-ai-eval.txt`.

---

## 5. Rollout & Rollback Flags

- `AI_CONVERSATION_STATE_ENABLED=true`: Enables server-owned `AiConversation` and `AiTurn` persistence, `context_version` optimistic concurrency, and `client_request_id` idempotency. Set to `false` to fall back to stateless session context.
- `AI_ROUTER_MODE=hybrid`: Uses deterministic local rules + entity resolver first and only calls Gemini when `provider_routing_enabled` is enabled and local routing abstains.
- `AI_ENABLE_CLASSIFIER=false`: Keeps the local ML classifier disabled in production runtime per the benchmark gate decision.
