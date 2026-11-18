# PMS AI model-led assistant: authoritative implementation plan

Status: proposed execution contract, 16 November 2026. Planning only; no runtime migration or release has been performed.

## 1. Authority and executor instructions

This document is the single execution reference for the next AI architecture transition. Earlier AI plans are historical inputs, not concurrent instructions. Repository security, scoring, data-source and permission contracts still apply.

The user intends to use an executor identified in their coding application as **Gemini Flash 3.8, High**. This records their executor preference, not a verified API model ID. Verify availability in that application. Do not copy this label into PMS runtime configuration. The coding assistant and the application's inference provider are separate choices.

Read this plan, the scoped progress ledger, AGENTS.md and RTK.md. Then read only files relevant to the current phase. Use at most three relevant skills. Do not load every historical AI plan or all skills. Do not tune code to isolated question wording.

Preserve the current dirty worktree. Do not merge, push, deploy, change credentials, enable production AI or mutate production data under this document alone. Phase completion requires artifacts and evidence, not a completion checkbox.

## 2. Verified starting point

Local inspection found:

- Branch `fix/pre-approvals-ip-single-team` contains uncommitted AI and related frontend work. Capture fresh status and diff before implementation.
- `config/environment.py` loads `DevOps/.env`, `Backend/.env.local`, and `DevOps/.env.local`, restoring pre-existing process variables as authoritative.
- After that loader runs, local provider configuration has Cloudflare primary, Gemini fallback, and Gemini credentials present. This proves local configuration availability, not provider connectivity or production configuration.
- Intent and synthesis switches resolve true locally. Exploration resolves false.
- `services/ai/llm_client.py` explicitly disables exploration when APP_ENV is production.
- `contextual_assistant.py` can terminate requests through lexical rules before provider understanding.
- `orchestrator.py` builds deterministic prose and offers provider synthesis only in selected paths; connecting credentials does not make the model responsible for all dialogue.
- Previous regression scores were deterministic. A subsequent reported final set scored 27/32 and exposed country switching, employee extraction and non-booking KPI response defects. Verify current results rather than trusting historical green reports.

## 3. Product contract

English interface and replies. A manager receives the direct answer first, normally one to three sentences or up to three short bullets. Details and sources remain available without a mandatory dashboard dump. Offer at most one useful deeper follow-up.

Cover every authorized function, team, position, country, branch and performance level through common tools and catalog metadata. Retain country-specific calculation differences and the Monthly Presentation hierarchy. Missing data is not zero; first observed performance is not a hire date; a tie is not a unique winner.

The model owns language understanding, contextual clarification, tool selection and answer composition. The backend owns authentication, authorization, published data selection, calculations, units, tool validation and factual verification. Feedback is not automatic model training.

## 4. Cleanup FIRST: exact inventory and disposition

Cleanup has two gates: documentation/context cleanup immediately; runtime deletion only after a proven replacement. Reducing contradictory instructions can reduce executor confusion, but does not guarantee factual model accuracy.

### Documentation inventory

| Existing path | Disposition | Reason / retained material |
| --- | --- | --- |
| `docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md` | Supersede and archive | Explicit Qwen-led implementation and offline-only Gemini role conflict with new provider-led direction. Retain evidence and privacy requirements. |
| `docs/plans/PMS_AI_ALL_DEPARTMENTS_ROADMAP.md` | Supersede and archive | Historical Qwen milestones and release status. Preserve scope coverage requirements. |
| `docs/plans/pms-ai-chatbot-implementation-plan.md` | Supersede and archive | Local composition / optional classifier direction conflicts with model-led conversation. Retain hierarchy and calculation contracts. |
| `docs/plans/contextual-ai-assistant/IMPLEMENTATION_PLAN.md` and `FULL_COVERAGE_EXECUTION_PLAN.md` | Review, extract valid contracts, archive as historical | Prevent competing execution instructions. |
| `docs/plans/contextual-ai-assistant/LOCAL_EVIDENCE_SYNTHESIS_PILOT.md` and `LOCAL_DATA_EXPLORATION_REPORT.md` | Historical reference only | Useful adapter findings, not a mandate to restore local models. |
| `docs/plans/pms-ai-conversation-v2/IMPLEMENTATION_BLUEPRINT.md` | Retain conversation contracts; supersede architecture instructions | Persistence, ownership and deletion semantics remain valuable. |
| `docs/plans/pms-ai-conversation-origin-fix/` | Preserve as historical bug evidence | Do not regress duplicate-chat and origin fixes. |
| `docs/plans/pms-ai-response-quality-final/` | Preserve, mark exposed regression history | Contains current WIP findings and known failing cases. Do not delete current work. |
| `docs/plans/pms-ai-evidence-first/` | Retain dictionaries, data relationships, coverage and glossary; supersede stale execution queue | Business definitions are not obsolete merely because routing changes. |
| `docs/plans/pms-ai-classifier-evaluation-report.md` | Historical experiment | No classifier runtime requirement in this plan. |
| `docs/ops/pms-ai-provider-verification.md`, `pms-ai-pilot-release-checklist.md` | Reconcile and retain | Operations procedures must match the final provider and feature controls. |

Before any move, enumerate references using rg and distinguish tracked files from untracked WIP. Initially add a brief SUPERSEDED notice linking here rather than moving heavily referenced documents. If relocating to `docs/archive/pms-ai/2026-11-16/`, update inbound links and preserve paths in an archive manifest. Do not recursively move/delete whole directories. Preserve reports and fixture provenance. Do not archive Monthly Evaluation plans: they describe a separate business subsystem.

### Runtime inventory

| Path / area | Treatment |
| --- | --- |
| `Backend/services/ai/provider_engine.py`, `llm_client.py` | Reuse provider transport, bounded retries, configuration and metrics. Audit actual supported tool protocol before extending. |
| `local_model_router.py`, `local_data_explorer.py`, `local_evidence_synthesis.py` | Active-looking names do not prove obsolete code. Trace imports/callers, extract useful schemas/validators, then rename/refactor incrementally. No blind deletion based on `local`. |
| `router.py`, `domain_policies.py`, `contextual_assistant.py` | Retire language heuristics from the new execution path; preserve security/domain validation. |
| `orchestrator.py`, `providers.py` | Replace mandatory deterministic analytical composition in the pilot; retain an explicit honest failure response and rollback path temporarily. |
| `tool_registry.py`, catalog, authorization and dashboard read services | Reuse authoritative calculations and data access; adapt tool interfaces and audit country/level coverage. |
| conversation repository/service, feedback and audit services | Preserve ownership, versioning, idempotency and deletion. Audit gaps before schema changes. |
| `Backend/scripts/run_unseen_eval.py`, `evaluate_pms_ai_improvements.py`, `evaluate_ai_classifier.py` | Identify overlapping responsibilities. Establish one documented runner entry point; retain meaningful tests and historical artifacts. Remove obsolete scripts only after callers are checked. |
| `ai_unseen_multiturn_eval.json`, `ai_response_quality_holdout_v2.json`, `ai_response_quality_final_blind_eval.json` | Preserve and label exposed. They are regression data, not production answer banks or blind evidence. |
| dependency manifests, Dockerfiles, deployment scripts | Audit local-model/classifier libraries by imports and build usage. Remove only proven unused dependencies and update locks/builds. No blanket deletion of ML libraries. |

Phase 0 output: `CLEANUP_MANIFEST.md` with exact path, current purpose, callers, proposed action, replacement, validation and status. Archive notices and a single plan index must be finished before new orchestration coding. Runtime deletions remain scheduled for Phase 6.

## 5. Target request flow

1. Authenticate, enforce pilot access and quota, load the owned conversation and current authorized scope.
2. Build bounded context: recent dialogue, compact confirmed state, selected page/filter context and authorized catalog references. Keep user text and retrieved content separate from trusted instructions.
3. Ask the configured model to answer socially, request clarification, or issue typed tool requests. Do not reject unfamiliar English through lexical off-topic rules before this step.
4. Validate each tool request against schemas and live authorization. Execute server-defined read operations and return typed evidence.
5. Allow a bounded follow-up tool request when necessary; stop on sufficient evidence, repeated requests, budget exhaustion or unresolved ambiguity.
6. Ask the model for a brief answer tied to evidence identifiers. Validate factual claims. Permit one bounded repair for invalid output, then return an honest limitation with verified evidence; do not silently replace the user's question with a generic summary.
7. Persist user turn, answer, confirmed context, evidence provenance and execution trace atomically/idempotently through existing conversation contracts.

Proposed initial limits: maximum 3 model/tool rounds, 6 tool executions and one repair within the same total budget. Set explicit wall-time, token and row limits after Phase 1 measurements. Count retries and fallback attempts in the budget. Never use an unlimited loop.

## 6. Phased execution

### Phase 0 — Freeze and clean conflicting context

- Capture HEAD, branch, tracked/untracked status and a recoverable snapshot of current work without overwriting it.
- Complete the cleanup manifest and supersession notices above; publish one active plan index.
- Record existing defects and test baseline without adding new phrase-specific fixes.
- Gate: no ambiguous active AI architecture instructions; no lost files; archive links resolve.

### Phase 1 — Prove configuration and end-to-end provider usage

- Use the real environment loader. Report only presence/boolean flags and nonsecret model identifiers; never output secrets or secret-bearing URLs.
- Trace a synthetic greeting, metric question and two follow-ups through the same API path used by the frontend.
- Record correlation ID, route, provider/model per stage, calls, tool names, timings, token usage when available, fallback and validation reason. Do not log raw sensitive payloads by default.
- Make runtime primary/fallback selection explicit. User's coding-model choice does not authorize changing the runtime provider.
- Gate: actual live-provider trace with synthetic data, or a clearly recorded connectivity blocker. Offline tests cannot satisfy this gate.

### Phase 2 — One model-led pilot path

- Add a distinct admin-only pilot switch with rollback to the existing path.
- Reuse provider engine; inspect whether it supports native tools or validated structured tool requests. Choose one documented protocol with equivalent authorization.
- Reuse useful explorer components only after evaluating their data exposure and output contracts. Do not simply remove the production guard or flip the old exploration switch.
- Separate understanding/execution/rendering from the legacy cascade. No duplicate public chat endpoints unless contract migration requires one.
- The model can clarify entities using an authorized search tool. It must not receive a full employee directory or database credentials.
- Gate: varied wording works through a traceable model/tool path; timeout and unavailable-provider behavior is honest.

### Phase 3 — Shared tools across departments and levels

Proposed capabilities, mapped onto existing services rather than assumed function names:

- Discover authorized hierarchy and metric definitions.
- Resolve employees by ID/name with bounded candidates.
- Read current metric/score evidence for a scope and period.
- Read multi-period series with explicit gaps.
- Rank and compare compatible populations/metrics with ties and denominators.
- Read corrective actions; produce a draft through the existing approval workflow.

Each result carries subject IDs, country, team, level, metric ID, unit, raw/display values, period, status, source reference and scoring-basis metadata. Distinguish count from rate and movement from relative percentage change. Do not infer percentage scale from magnitude. KPI zero, null, missing, unpublished and unauthorized must be distinguishable.

Use the existing scorer; do not reimplement team formulas. Test Egypt/UAE separation, function grants, Employee/Managerial/Corporate scope and country-specific calculation bases. Maintain a coverage matrix with supported, no-data and unsupported states for every catalog scope. A Call Center pilot must not be reported as all-department completion.

Gate: tool parity with authorized PMS source services and no cross-scope leaks.

### Phase 4 — Conversation and concise model answers

- Maintain employee, metric, operation, period and country independently. New explicit instructions override compatible inherited fields.
- Confirmed identity survives follow-ups; unresolved ties require selection; scope changes revalidate identities.
- Include recent dialogue plus a compact versioned state; do not rely on client-supplied state as authorization.
- Preserve original user wording when clarification choices bind IDs.
- The model composes all supported analytical answer types from evidence, not only booking comparisons and overall scores.
- Validate claim subject/value/unit/period/source, not merely whether a number occurs somewhere in evidence. Sources are structured links, not prose rewritten with regex.
- Keep technical evidence panels collapsed. Never attach an unrelated performance summary to a greeting or unsupported question.
- Preserve new/delete/reload conversation isolation, one user submit to one persisted turn, and retry idempotency.
- Gate: complete multi-turn chains answer the actual operation and metric, including Waiting Time after bookings and score trend after KPI discussion.

### Phase 5 — Feedback and evaluation

- Feedback belongs to a specific answer, evidence revision, provider/model and prompt version. Negative feedback creates review work, not an automatic new rule or approved answer.
- Corrected examples require review; use them as limited retrieval examples or future training candidates. Re-fetch current numeric facts. Never replay stale employee answers from a text similarity match.
- Cache only with scope, user permissions, metric/period, data/configuration version and invalidation. Delay semantic answer caching until correctness is established.
- Preserve exposed regressions; strengthen semantic expectations. A correct employee name alone cannot pass a trend question.
- Evaluate at least 80 prompts over 20 conversations covering every operation, both countries, permission levels, ambiguous names, ties, missing periods, corrections, deletion/reload and provider failures. Department coverage must also be explicit rather than inferred from prompt count.
- Freeze a separate final set before first run. Record first-run results; once inspected for tuning it becomes exposed. Keep deterministic tool tests, mocked-provider tests and live-provider results separate.
- Proposed release gates: 100% critical authorization/numeric-unit/source checks; at least 95% semantic task completion on the agreed final set; no known reproduced high-priority defect. Measure p50/p95 latency and cost, then agree workload-specific limits before release. Thresholds do not excuse a serious individual failure.
- Gate: reviewer can inspect exact failed questions and evidence, not only aggregate accuracy.

### Phase 6 — Remove displaced runtime complexity

- Use imports, call graph and runtime traces to confirm pilot-equivalent behavior.
- Remove superseded phrase-specific routing and analytical templates in bounded changes; preserve validators, calculation rules, navigation contracts and security checks.
- Consolidate evaluators and prompt versions. Keep fixtures in test/development paths, exclude training artifacts from runtime images where unused.
- Remove unused dependencies/model-launch scripts only with manifest evidence. This phase does not authorize deleting model files outside the repository or on the server.
- Gate: official typecheck, relevant backend/frontend suites, build and container checks pass; rollback remains possible through version control/release version.

### Phase 7 — Staging and separately authorized rollout

- Test signed-in local/staging behavior with the actual provider. No production tab as a substitute.
- Verify account ownership, narrowing permissions mid-conversation, retries, fresh/deleted chats, mobile use and short answers.
- Start admin-only; enforce server-side request/token/concurrency budgets and measurable provider timeouts. Daily per-user limits may initially be configurable; avoid inventing a user-approved amount.
- Document fallback policy, health visibility and rollback. Never advertise an AI-generated answer when a deterministic fallback was used.
- Production enabling, migration and deployment require the user's release authorization. Keep unverified gates open.

## 7. Database and migration policy

Audit existing conversation, turns, feedback and telemetry models first. Prefer existing JSON/versioned fields where they meet ownership, query and retention needs. Add a migration only for a demonstrated missing durable requirement, such as indexed trace metadata or durable usage accounting. Specify additive upgrade, rollback, backfill and retention; test against a production-shaped copy. Do not rewrite historic chats or feedback. Respect deletion and do not retain removed personal content through hidden caches/training copies.

## 8. Definition of done and handoff

Each phase handoff includes: changed paths, problem/behavior, exact checks and results, trace/evaluation artifact location, open defects, next phase and rollback implications. One phase at a time; do not continue architectural deletion while provider execution remains unproven.

Never claim: credentials prove live connectivity; test accuracy proves model training; a model label proves the requested API model; a green suite proves an untested browser; or a renamed holdout is unseen.

Immediate next assignment: execute Phase 0, then Phase 1. Present the cleanup manifest and synthetic end-to-end provider evidence before implementing Phase 2.
