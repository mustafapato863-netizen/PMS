# Model-led transition ledger

Authoritative specification: ../PMS_AI_MODEL_LED_IMPLEMENTATION_PLAN.md

This execution closes Phases 0–6 (accepted through Phase 6). Phase 7 staging/rollout remains out of scope.

- [x] Inspect local routing/configuration and inventory historical plan candidates.
- [x] Write the transition plan and cleanup-first policy.
- [x] Phase 0: reconcile active instructions and manifest; revalidate/create a recoverable snapshot covering the current WIP.
- [x] Phase 1: reproduce authenticated synthetic HTTP provider use and record configured providers separately from runtime usage.
- [x] EGM guidance: use the repository's EGM review report; no separately installed EGM skill was found.
- [x] Phase 2: gated model-led path, invalid-tool rejection, numerical validation, and authenticated HTTP synthesis trace.
- [x] Phase 3: shared authorized tools and scope coverage; this execution audits the matrix claim-by-claim and corrects overstatements.
- [x] Phase 4: conversation and evidence-bound answers; this execution strengthens the HTTP acceptance criteria and records the signed-in UI availability check.
- [x] Phase 5 execution: governed feedback, immutable frozen semantic set (80 prompts / 20 conversations), separate deterministic/mock/live evidence, and quality-gate evaluation. The quality gate failed; see `PHASE_5_EVALUATION_AND_HANDOFF.md`.
- [x] Run focused authorization, country-scope, offshore branch-attribution, and successful mocked-planner regressions; record the remaining quality clusters, check the diff, and refresh Graphify.
- [x] Coordinator rework follow-up: bounded classifier context, scope and clarification regressions, structured source-link contract, and varied model-led pilot prompts. The combined response-quality/Phase 4/booking-parity suite passed 121/121; the frozen evaluation gate remains failed and was not rerun.
- [x] Prepare coordinator handoff and stop before Phase 6.

## Acceptance checks

- [x] Snapshot artifact exists, includes all current tracked/untracked WIP, and its tracked patch passes reverse-apply check.
- [x] Authenticated synthetic HTTP provider trace records sanitized configuration metadata separately from actual provider/model/call usage.
- [x] Waiting Time Sep/target/miss, Aug value, and 0.6 min improvement assertions reject incorrect status/direction.
- [x] Matrix distinguishes synthetic parity, published proof, verified no data, unsupported, and not verified by country/team/level/operation.
- [x] Authenticated HTTP acceptance covers compound booking/ranking answers, Egypt switch, terse inherited follow-up, reload/isolation, deletion, duplicate-turn idempotency, narrowed scope, and fallback source; see prior Phase 4 evidence and the current handoff for remaining issues.
- [x] Feedback provenance/ownership/idempotency/reviewer decisions/retention are covered without automatic training or stale-fact replay.
- [x] Frozen final set passes 100% critical authorization/numeric-unit/source checks and ≥95% semantic checks; no reproduced high-priority defect. (`phase5_corrected_glm_30s_v1_r2`: **80/80 = 100.0% semantic**, **74/74 = 100.0% critical**, `gate.passed: true`; result SHA-256 `c05939a8ecb4caea91d7f79f0537dde5194fed3061e84d12a3e577f5086832c5`, manifest SHA-256 `5b8569d844647f4e2a1461445ee141b0db8f7146081db184eb0b13fee01fc1bb`)

Acceptance verified on 18 November 2026 (`PHASE_5_REVIEW_REPORT.md`: `VERDICT: ACCEPTED`). Phases 0–5 are complete; halted before Phase 6 cleanup.

## Phase 5 post-fix acceptance follow-up — 17 November 2026

- [x] Preserve original frozen fixture, manifest, and first-run outputs; validate their recorded hashes before rescore.
- [x] Rescore saved deterministic, mocked, and live outputs using contract `pms-ai-metadata-units-v1`, with raw failures retained and separate manifest/result artifacts.
- [x] Run current deterministic 80-turn result under a separate manifest and runner hash.
- [x] Pass focused model-led planner, RBAC, country isolation, typed-evidence, and claim-validator checks (15/15); fix the discovered local import shadowing defect.
- [x] Verify governed feedback tests (27 passed), official frontend typecheck, and relevant AI response-card tests (6 passed).
- [x] Recheck Phase 3 status: Corporate level and KSA remain Not verified; correct the review report's broad department-coverage wording.
- [x] Complete bounded 80-turn post-fix synthetic live run and record provider, fallback, latency, and cost-status evidence.
- [x] Update the Phase 5 handoff with final v2 evidence and remaining acceptance blockers; stop before Phase 6.

## Phase 6 — Runtime Cleanup, Evaluator Consolidation & CI Gates (2026-11-18)

- [x] Ticket 01: Repair baseline non-Phase-5 test regressions (`tool_registry.py`, `contextual_assistant.py` + `domain_policies.py`, `ai_workspace.py`), regenerate Phase 0/Phase 2 manifests, verify zero secrets, and create local Phase 5 checkpoint commit `1c54e5b1d33dabbc93ed3f73a1c7ab476b7c1903` on `fix/pre-approvals-ip-single-team`.
- [x] Ticket 02: Retire and delete `Backend/services/ai/classifier.py`, `Backend/scripts/evaluate_ai_classifier.py`, `Backend/scripts/evaluate_pms_ai_improvements.py`, and `Backend/requirements-ai-eval.txt`; clean `.dockerignore` and `Backend/.dockerignore` while preserving `!.env.example` rules; pin `AiRuntimeConfig.classifier_mode = "off"`; update `test_ai_phase7_eval_gates.py` and `evaluation/pms-ai/phase7/LEGACY_CLEANUP_INVENTORY.md`.
- [x] Ticket 03: Extract `ValidatedExplorationToolCall`, `build_fact_ledger_from_evidence`, and `validate_grounded_synthesis` into `Backend/services/ai/claim_validator.py`; remove `run_bounded_exploration` branch from `orchestrator.py` (preserving `local_exploration_enabled` import hook); pin `local_exploration_enabled() -> False` in `llm_client.py`; delete `local_data_explorer.py`, `test_local_assistant_exploration.py`, and `test_ai_explorer_unified.py`; migrate RBAC revocation & claim-validation tests onto `PmsAiOrchestrator` and `claim_validator` seams.
- [x] Ticket 04: Create `Backend/services/ai/prompt_versions.py` (`ACTIVE_PROMPT_VERSIONS`) and bind in `orchestrator.py`, `router.py`, `local_model_router.py`, `local_evidence_synthesis.py`, and `contextual_assistant.py`; guard `extract_overall_score_facts` under `model_led_pilot_enabled`; resolve `plan.periods[-1]` and dynamic year in `router.py`; skip redundant `suggest_intent` on Admin model-led fallback; verify via Red->Green TDD tests.
- [x] Ticket 05: Resync deterministic manifests, pass full CI/replay/provenance/hygiene gates, update handoff docs, complete independent EGM Goldfish audit (`VERDICT: ACCEPTED`), and create final local Phase 6 commit (no `git push`).

Phases 0–6 complete & accepted (`PHASE_6_REVIEW_REPORT.md`: `VERDICT: ACCEPTED`, 0 Blocker, 0 Major); halted before Phase 7.
