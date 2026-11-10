# PMS AI: Evidence-First Assistant and Learning Plan

**Status:** Proposed, 10 November 2026. This is an execution plan, not a statement that the phases or the current candidate are complete.

**Related plan:** [PMS AI all-departments roadmap](PMS_AI_ALL_DEPARTMENTS_ROADMAP.md). This document refines the agreed nine-phase sequence and feedback/training workflow; reconcile the two rather than silently discarding prior findings or changing existing release gates.

## Product outcome

Deliver an English-language PMS assistant that understands varied questions, explores authorized evidence through bounded tools, and answers directly and briefly. Qwen is intended to lead question understanding, tool choice, follow-up reasoning, and answer composition; PMS remains authoritative for access, data, calculations, and validation. Provide optional deeper explanation and source navigation, not mandatory charts or lengthy reports.

Examples: answer a greeting briefly; identify the lowest Support performer and position with sufficient evidence; determine whether September was a person's best month; and compare Dubai, Ajman, and Sharjah booking counts. Ask for missing identity, country, period, or metric when needed. A missing value is not zero, a tie is not a single winner, and a first performance record is not a hire date.

## Operating decisions and boundaries

- **Pilot:** Admin only, with the existing product switch off by default. An Admin can read all data within the Admin's actual authorized scope. Expand roles only after explicit acceptance and permission tests.
- **Model:** use the existing Qwen3 4B candidate where actually available; verify model identity, version, endpoint, inference, and fallback. A local experiment does not establish hosted equivalence. No new model instance on the VPS without explicit authorization.
- **Data:** read-only, bounded server-defined tools and a database account restricted to necessary read access. No unrestricted model credentials, arbitrary writes, automatic action approvals, or production-data mutation. Treat prompts, spreadsheet content, tool outputs, and model output as untrusted.
- **Gemini's role:** optional offline assistant to classify de-identified negative feedback, suggest paraphrases and fixes, and propose test cases. It is not an authoritative source for PMS values. Do not send employee-identifying or sensitive material externally without approved policy and explicit authorization; free-tier data handling must be checked for the chosen service.
- **Evidence:** every accepted factual claim binds subject, country, team/position, period, metric, unit, value, source, authorization and relevant scoring basis. Unknown/ambiguous/partial evidence must be surfaced, not guessed.
- **Cleanup:** inventory redundant prompt-specific routing, canned answers, stale scripts and duplicated libraries; remove only after a verified replacement exists and regression tests pass. Preserve security controls, calculations, original upload contracts, and independent evaluation sets.
- **Change control:** no production deployment, feature enablement, destructive testing, migration, or release implied by this plan. Keep existing user work and historical artifacts intact. For any database change audit the schema, justify it, use an additive separately reviewed migration and test upgrade/rollback against a production-shaped copy.

## Phase 1 — Establish and preserve the baseline

**Objective:** identify what actually runs and make current behavior reproducible before changing it.

1. Record branch, base/candidate SHA, dirty/untracked relevant files, runtime configuration without secrets, model name/hash/endpoint reachability, and actual active deployment status separately from repository state. Never overwrite existing evidence.
2. Map request flows for the dedicated page and contextual assistant: authentication, scope resolution, intent, model/tool calls, data source, scoring, synthesis, response, feedback, fallback, and flags. Identify hard-coded defaults and scenario-specific responses without presuming every deterministic rule is redundant.
3. Reproduce the known Inbound metric, Clinics booking, and branch-comparison issues using isolated, independently expected fixtures. Report exact prompts, period/scope, expected versus actual, provider used, and categories. Distinguish app defects from model errors and data gaps.
4. Freeze a baseline covering neutral and scoped questions, missing and zero, ties, ambiguities, multi-turn changes, Admin/non-Admin checks, and provider down/fallback. Preserve original results; record passed, failed, ungraded, blocked and denominators.
5. Record which existing tests are synthetic, mocked, live-model, source-parity, or browser tests. A green test suite alone does not establish factual coverage.

**Outputs:** baseline inventory, flow diagram, issue register, evidence and test inventory, exact reproduction commands and candidate identity. No production writes.

**Gate:** another reviewer can reproduce each supported example or see its explicit blocker; provider and fallback are observable; historical artifacts and uncommitted user changes are preserved.

## Phase 2 — Build and review the domain and data map

**Objective:** create a factual, versioned reference for how PMS names and computes data, without inventing source rules.

1. Inventory authorized active functions, teams/subteams, positions and Employee/Managerial/Corporate levels across Egypt, UAE and shared scopes. Distinguish Call Center, Inbound/Outbound and support positions; preserve distinct RCM Egypt and UAE rules and documented aliases.
2. Map each operation and metric to its authoritative PMS service, source tables/relationships, upload fields, period, unit, direction, actual/target/weight and versioned scoring basis. Distinguish bookings counts from booking rates, tracking-only KPIs from scored KPIs, and employee scores from pooled team scores.
3. Produce a reviewable coverage matrix: country × function × team/position × level × operation × period/source. Separate organization access, AI capability, data availability, and verification evidence. Mark unsupported, partial, missing evidence, or unverified honestly; data availability must be scoped to the requested period.
4. Record ambiguity rules, identity matching, branch attribution, shared scopes, publication semantics, zero vs missing vs unpublished, ties, data freshness and migration/schema risks. Use read-only synthetic or approved, de-identified evidence. Do not expose employee rows in documentation.
5. Link each verified cell to independent source parity and tests; do not certify an entire team from its name or a generic unit test. List open business questions and missing source files.

**Outputs:** versioned glossary and relationship map, metric/source dictionary, scope and operation coverage matrix, ambiguities and unresolved-evidence register, phase-2 review report. Include a current-state ERD or relationship map only where derived from inspected schema; propose schema changes only for a proven gap.

**Gate:** reviewed examples reconcile with their owning PMS pages/source for each claimed cell; missing sources remain unverified; no unauthorized data is exposed.

## Phase 3 — Bounded, trustworthy read tools

Build reusable typed tools for identity/scope lookup, concept definitions, publication/availability, current score and KPI actual/target, ranking/ties, six-month trends, branch/period comparisons, authorized BSC and verified navigation. Use canonical PMS services; preserve source, units, completeness, country and scoring basis. Limit rows, time, number of calls, and result size. Apply authorization to every call and recheck it on continuation. Preserve zero, null and partial results distinctly.

**Gate:** source-to-response integration tests pass for supported cells, including EGY/UAE separation, duplicates, true zero, missing, partial, ties, publication and authorization. Unsupported operations return a truthful explanation.

## Phase 4 — Qwen-led conversation

Provide the model with only the relevant scope, glossary and tools for the current question; allow bounded multi-step reads and clarification. Preserve conversation context but prioritize explicit user corrections. Make Qwen compose a short direct answer from evidence; keep an honest, evidence-backed fallback when unavailable. Record actual provider, model, tool calls and fallback without sensitive logs. Do not inject changing employee facts into model weights.

**Gate:** paired local tests demonstrate actual Qwen calls and independently checked answers for paraphrases, follow-ups, known failures and missing data; fake or unavailable evidence never becomes an answer. Qwen-unavailable is blocked, not passed.

## Phase 5 — Claim validation and concise UX

Validate every returned factual claim against the evidence ledger: correct subject, scope, metric, period, unit, value, polarity, ranking, ties and every required question part. Reject or clarify unsupported facts; do not convert correlation into cause or invent employment facts. Share one assistant contract across dedicated chat and verified page contexts, preserve page context visibly, provide an optional explanation and sources, and support keyboard/mobile/tablet.

**Gate:** adversarial, access-control and end-to-end UI tests cover unauthorized data, partial evidence, scoped follow-ups, short answers, honest empty/error states and verified routes. AI stays Admin-only and off by default.

## Phase 6 — Feedback and Gemini-assisted review

Collect helpful/unhelpful feedback and optional reason with owner/scope, candidate version, evidence references and privacy-preserving retention. Cluster recurring issues. A controlled review process may de-identify cases and ask Gemini to classify failures and propose fixes/tests. Re-identification risk and outbound data policy must be reviewed before any external request. Compare proposed corrections against PMS evidence; an Admin/reviewer approves before promotion. No automatic production change or training from raw votes/model outputs.

**Gate:** permissions, redaction, review audit trail, retention/deletion and rejection paths are tested. Feedback improves the backlog but is not treated as ground truth by itself.

## Phase 7 — Independent evaluation and cleanup

Maintain separate versioned development and frozen held-out sets, grouped by paraphrase and information need to limit leakage. Add independently reviewed expected answers for varied English phrasing, two countries, available functions/levels, compound and follow-up questions, permissions, injections, ties, partial and no-data cases. Compare rules-only and Qwen-on on the same fixtures and evidence. Report passed/failed/ungraded/blocked with denominators by scope and operation, provider/fallback, latency and resource use. Choose quantitative accuracy/latency thresholds after a measured baseline with the owner; zero accepted fabricated facts and zero cross-scope disclosures are release gates.

Once replacements pass, remove only demonstrably obsolete hard-coded scenario paths and libraries. Run regression tests before and after each removal and keep a rollback path.

**Gate:** independently checked results and reproducible candidate/model/fixture identifiers; no unsupported scope advertised as verified. Ungraded cases remain ungraded.

## Phase 8 — Optional model training experiment

Only after data/tools and evaluation are stable, decide whether residual failures justify fine-tuning. Curate approved, de-identified examples of correct tool use, clarification, evidence-grounded response and refusal; keep training, validation and held-out groups separate. Gemini-generated suggestions require human and source review. Consider LoRA/QLoRA on suitable GPU infrastructure using the compatible original training weights; do not train on the KVM 2 production server or assume the existing GGUF is a standard training checkpoint.

Benchmark candidate versus original Qwen on the same held-out data, permission/injection cases, latency and memory. Version model, adapter, data and config. Reject or roll back a candidate that fails gates; no fine-tune is required if tools and prompts already meet targets.

**Gate:** an independently evaluated improvement without correctness/security regressions, with reproducible artifacts and rollback; otherwise retain the original model.

## Phase 9 — Controlled release

Test an exact candidate locally and in a production-shaped isolated environment; confirm hosted model identity and configuration before any equivalence claim. Measure CPU, memory, p50/p95 latency, concurrency, fallback and impact on PMS on target-like hardware. Verify feature-off, Admin-only behavior, migrations if any, monitoring and rollback. Obtain owner acceptance before enabling the Admin pilot, then expand role access only after scope-specific authorization and source-parity tests.

**Gate:** reviewed release evidence, user acceptance, tested rollback and operational ownership. No automatic rollout follows from completing a development phase.

## Review cadence and deliverables

At the end of each phase provide the exact candidate SHA and dirty-input identity, files changed, tests/commands and counts, issues and blocked cases, user-visible effect, and whether Qwen was actually used. Separate synthetic tests, source parity, live-model tests and production verification. Review one phase before advancing; do not batch cleanup, model training, deployment and permission expansion into a single unreviewable change.

For phases 1–2 specifically: perform read-only investigation and write the baseline and domain/coverage documents. Do not implement new runtime functionality, change scoring, modify schema, start a model, or merge/push/deploy unless separately requested. Existing runs and the current working tree are evidence to preserve.
