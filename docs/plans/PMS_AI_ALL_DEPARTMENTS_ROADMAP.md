# PMS AI: all-department chat and assistant roadmap

**Status (10 November 2026):** Phase -1 Qwen wiring and Admin-only pilot, plus the unsigned Phase 0 question freeze, are merged on `main`; all-department implementation and production enablement remain incomplete and unauthorized.
**Product language:** English.
**Reviewed baseline:** local `main` at `339cbf30` (includes PR #82 and PR #83), 10 November 2026. PR #81's Qwen changes are included through PR #82. This review record describes a local implementation candidate; it does not establish an upstream merge, deployment, live-model availability or source correctness.
**Goal:** one concise, conversational PMS assistant that can answer supported questions across all authorized PMS departments and their teams in Egypt, the UAE and explicitly shared scopes, using the same business facts as PMS.

## 1. Outcome and non-negotiable decisions

1. The dedicated PMS AI page starts with the user's authorized organization scope, not Call Center. A specific department, team, role, person, branch, month or level in the question takes precedence over a default; an explicit locked permission always takes precedence over the question.
2. Cover every active department/function, team, subteam and position represented in PMS, for Employee, Managerial and Corporate/BSC levels where applicable. Generate the denominator from the live authorized catalog and data sources; do not use a static list as proof of coverage. Keep Egypt, UAE and shared ownership distinct.
3. Use the existing Qwen3 4B local model as the candidate conversational planner and answer composer, evaluated end to end. PMS remains responsible for authorization, published data, calculations, source versions, exact numeric facts and validation. A fluent model answer is not evidence of correctness.
4. Default to an English answer of one or two short sentences for a single question; give each part of a compound question a direct answer. Include the effective scope and period when needed, a compact source link and at most one relevant optional follow-up. Show detailed analysis only when requested. Greetings must not trigger an unrelated analytics report.
5. **Admin-only pilot:** enforce this at the backend for every AI entry point, not just in the sidebar; keep the feature off by default. Expanding access requires the user to approve the rollout after role and security gates. Once enabled for other roles, limit all data, links, conversations, caches and action drafts to their actual PMS permissions.
6. Analytic tools are read-only. The model may suggest a corrective-action draft, but creating or changing an action must use the existing authorization and explicit user-confirmation flow. No direct model writes, arbitrary SQL, shell or unrestricted network tools.
7. Preserve existing uploaded data and historical score/target/weight/direction basis. Do not backfill or recalculate historical results without verified source evidence and explicit approval. A zero, missing value, unavailable historical setting and an unpublished month are different states.
8. Feedback is a review signal, not automatic model training or a global answer cache. A cached answer is valid only for its exact user/scope, query and current source versions; approved examples can feed an offline evaluation/training candidate after de-identification and review.

## 2. Current findings and evidence limits

| Finding | Evidence in reviewed code | Consequence / required verification |
| --- | --- | --- |
| Neutral department entry has been implemented in the candidate; complete scope-routing verification remains | The working changes remove the Call Center default from the workspace URL state, session schema and watching API. The neutral greeting returns an organization-wide offer; UI coverage selects another function and checks the request scope. | Keep an omitted function omitted until the user or question supplies one. Continue verifying direct links, follow-ups, every AI entry point and current permissions before broad rollout. |
| Qwen wiring and Admin-only pilot are merged, but live model use is unverified | PRs [#81](https://github.com/mustafapato863-netizen/PMS/pull/81) and [#82](https://github.com/mustafapato863-netizen/PMS/pull/82) are closed and their changes are in the reviewed `main` history via PR #82. The pilot remains Admin-only and off by default; production exploration is gated off. | Merged code is not proof of a reachable Qwen service or a successful inference. Verify the authorized endpoint and record the actual provider/fallback for every evaluation turn. Never start a second model or enable the production feature flag as part of evaluation. |
| Explorer and classifier have production gates | `Backend/services/ai/local_data_explorer.py` returns false for local exploration under `APP_ENV=production`; `Backend/services/ai/config.py` sets classifier mode off in production. Model routing also requires explicit configuration. | Do not claim that production is using the local model. Determine actual configured mode from safe diagnostics; change a gate only with tested security, capacity and rollback. |
| Admin-only pilot is enforced in the merged Phase -1 candidate; recheck every route before rollout | PR #82's merged changes add a backend Admin dependency and Admin-only frontend visibility, with the AI switch off by default. PR #83's baseline and current tests include direct non-Admin denial probes. | Keep the pilot Admin-only and off. Any access expansion requires a separate approved change and fresh route/context/conversation authorization tests. |
| Candidate capability lookup is now exact and conservative; independent source-parity evidence is still absent | The working lookup requires country, function, team, level and operation, resolves supported country/team aliases, and returns unverified for missing, unknown or non-unique scopes. Every current evidence entry is partial or unverified because its references are application tests, not an independent owner/source parity record. | Keep all capabilities uncertified until the exact scope and operation have an independently checked expected value from the owning PMS source. Do not translate application-test coverage into source correctness. |
| Model health now checks identity and generated content, but live Qwen remains unverified | The candidate sends the configured model, requires an exact identity in the completion response and non-empty assistant text, uses the shared inference slot and caps both requests to one short deadline. Diagnostics return reason codes and omit raw database errors. Local tests cover wrong identity, empty/malformed completion, invalid listing and success. | Treat local mocks as contract tests only. Same-suite Qwen evaluation remains blocked until an authorized existing endpoint is reachable; do not start or install a model. |
| Phase 0 is unsigned and its rules-only baseline has no representative performance rows | `evaluation/pms-ai/phase0/BASELINE.md` records zero `performance_records` on the isolated SQLite database. The latest local run reports 50 behavioral passes, 86/136 ungraded, and 0 model-attempted turns. Separate application tests now include hand-constructed country, function, missing/zero/tie, identity, permission and follow-up cases; those fixtures are not source-parity evidence. The expected values in `frozen_v0.json` and `heldout_v0.json` remain unsigned/PENDING. | Do not describe these passes as score/source correctness or department coverage. Obtain approved owner values for the frozen set, preserve its criteria and existing artifacts, and report denominators plus provider/fallback. |
| The provider can fall back to rules | Existing router/orchestrator has deterministic paths and local-model opt-ins; the candidate also surfaces provider mode and the latest safe fallback reason in Admin diagnostics. | Measure whether Qwen actually planned and composed each evaluated turn. A rules fallback is not evidence of a correct answer. |
| Contextual assistants exist in some pages | `ContextualAssistantPanel` appears in Monthly Review, Team, Marketing, Departmental/Function and Employee views. | Build an inventory of all entry points, including Executive, BSC and any missing section; verify behavior instead of assuming the shared component is connected everywhere. |
| Qwen endpoint is unavailable from this local checkout; production readiness remains unverified | On 10 November, no local `PMS_AI_LLM_BASE_URL` was configured, ports 18080 and 11434 had no listener, and port 8080 belonged to `AgentService.exe`; a read-only `GET /v1/models` to that unrelated listener timed out. Docker Desktop was unavailable. Previous Hostinger inventory and PR #81's approximate 6 GB memory note are historical, not current host measurements. | Same-suite live Qwen evaluation is blocked. Do not start/install a model or infer Qwen availability from port 8080. Before release, obtain an authorized existing endpoint and measure its model identity, RAM, CPU, disk, checksum, path and latency on the target host. |

Historical local reports mention a 50-question golden suite, a 122-case Egypt/UAE suite and response-time figures. Those are useful starting artifacts, **not newly verified results** and not proof that every real team, live deployment or open-ended question works.

### Local review update — 10 November 2026

- Focused backend review suite: 75 passed. Focused frontend suite: 47 passed. Frontend TypeScript build check passed; `git diff --check` passed.
- The latest rules-only run used a unique disposable SQLite file, had 0 `performance_records`, and attempted 0 model turns. It recorded 50 behavioral passes, 0 failures and 86 ungraded cases across the frozen and held-out sets. No performance or source-parity claim follows from these results.
- The old shared temporary database path was left untouched. No Qwen process was started and no external endpoint was contacted for inference.
- Monthly score-trend and neutral department-filter changes are included in this review. They passed the focused browser tests and typecheck.

## 3. Product and coverage contract

### Entity hierarchy and scope

Use one server-owned hierarchy shared with Monthly Review and the canonical catalog: organization -> country/shared -> function -> team/subteam -> position -> person -> level -> period -> metric. Navigation labels do not redefine source identities. Build IDs and aliases from actual team/position records and configuration, keeping approved mappings versioned and auditable.

- Call Center is a function; Inbound and Outbound are channels/teams; support roles are positions. An ambiguous request must ask rather than silently swap a position for a team.
- RCM, Pre-Approvals and its Egypt/UAE children follow the actual approved PMS hierarchy. Coding, Submission and Re-Submission aliases share display names where approved while their Egypt/UAE records and scoring stay separate. Do not merge different Pre-Approvals source teams merely because names look alike.
- Pharmacy is a function where configured; Marketing questions resolve the person's position and its own KPI definitions; management and Corporate employees open their proper scorecard/BSC.
- Shared `All` records are included in a single-country total only when the approved attribution supports that; otherwise describe them as shared or ask. Never infer a branch from a team name.
- The system must distinguish no assignment, no published data, unsupported mapping, denied access and ambiguous identity. Do not reveal the existence of unauthorized people or scopes through counts, suggestions, errors or cached turns.

### Required answers

| User question | Required behavior |
| --- | --- |
| “Hi” | A short greeting and relevant offer of help; no unsolicited dashboard. |
| “Who is the lowest person in the support team and what is their position?” | Scope and period resolved; rank the requested metric using authorized records, return the name, score and position; disclose ties or missing data. |
| “Was Adham's best month September?” | Resolve the exact person and allowed history; compare all available published months using unrounded values and ties; answer yes/no with the best month and score. |
| “Is Mariam a new joiner in Inbound?” | Only answer from an authorized employment/join-date source. If only evaluation history exists, say the first visible evaluation is not proof of a join date. |
| “Which branch has most bookings: Dubai, Ajman or Sharjah?” | Compare booking **counts**, not conversion percentages. Require comparable, authorized branch evidence; return each count and the winner/tie, or identify missing operands. |
| “How did Coding perform over six months?” | Use the same published team score/basis as its owning PMS dashboard for each calendar month and selected country; preserve gaps and distinguish any changed or unverified basis. |
| “Why did it fall, and suggest an action?” | Provide measured evidence first, label an explanation as a hypothesis unless established, then propose a draft. Saving requires the existing permission and explicit confirmation. |

Short follow-ups such as “what about August?”, “and the lowest?” and “show me the team” must inherit only the last confirmed, currently authorized context. A named team or period in the new question overrides inherited context. Never resolve a record by first name alone when more than one authorized match exists.

## 4. Delivery phases and acceptance gates

**Merge first:** integrate the existing Qwen work before starting the department expansion. Each subsequent phase should be a small independently reviewed change set. Review the exact PR and its current base before merging; preserve the user's instruction to leave its branch unchanged. A phase does not pass just because its code exists.

### Phase -1 — Review and merge the existing Qwen work first

- Identify the latest head and base of [PR #81](https://github.com/mustafapato863-netizen/PMS/pull/81), verify whether its implementer is still working, and review the complete Qwen wiring change against current `main`. Keep the PR branch as-is; resolve integration issues on a separate integration branch if needed.
- Verify that the earlier backend parity and frontend typecheck fixes are present in the merge result, then rerun CI and focused AI, permission, provider-fallback and model-contract tests against the **exact merge result**. Record failures and do not treat stale PR checks as proof of the new result.
- Before merging, verify the actual deployment triggers, production feature flag and Admin-only boundary: updating `main` may automatically redeploy. The merge must not silently enable AI, expose it to additional roles, start a second model or bypass the production exploration gate. If the existing code cannot satisfy this, fix the required boundary in the separate integration changes before the merge.
- Merge the reviewed Qwen work into `main` first once the checks and safeguards pass; synchronize the GitHub and GitLab main repositories if that is authorized for the implementation run. Verify the resulting commit in both repositories and any deployment triggered by that merge; keep model enablement as a separate controlled pilot step.
- **Gate:** the Qwen change is merged into the implementation baseline with its exact commit recorded, relevant checks green, no unexpected access/model activation, and deployment state known. Then start Phase 0 on that merged baseline.

### Phase 0 — Freeze baseline and reproduce

- Capture main/PR SHAs, model file hash, runtime flags, prompt/schema version and masked environment diagnostics; never print secrets. Record whether calls actually reach Qwen or use fallback.
- Reproduce user examples plus greetings, cross-department, missing-month and multi-turn questions through the real UI/API using anonymous or approved local test data. Compare the dedicated chat with contextual entry points and Monthly Review.
- Freeze existing golden cases and independent expected results. Create a separate held-out set; document the source and reviewer for every expected value. Keep raw answers and failures, not just pass counts.
- **Gate:** repeatable baseline for the candidate runtime, with each failure classified as intent, identity, scope, source, calculation, answer composition, UI or latency. No production data writes.

### Phase 1 — Safe runtime and truthful capabilities

- Review PR #81 against the updated main and the current deployment. Test the real endpoint, model name, structured outputs, network isolation, timeout, concurrency and bounded input/output. Do not install a second copy of the model on the 8 GB host.
- Add a protected, non-secret Admin diagnostic showing effective feature state, model availability/version, routing vs synthesis provider, fallback reason and dataset/version freshness. It must not expose credentials, raw prompts or hidden data.
- Enforce Admin-only access on every chat, conversation, catalog, feedback, watching and proposal route during the pilot. The feature toggle remains off by default, including on fresh installation. Confirm whether any existing user-facing surfaces are still visible.
- Replace blanket catalog certification with explicit states: verified, verified no data, partial, blocked and not applicable. Each certification links to exact tests, fixture/source versions, date and reviewer. Missing evidence is not a pass.
- **Gate:** no bypass through direct API or contextual page; Qwen reached in the intended mode or clearly reported as unavailable; no false certification; disabling AI or model access is a tested rollback.

### Phase 2 — Department/metric coverage inventory

- Build a repeatable coverage manifest from actual authorized active teams, region, functions, aliases, position, level, published months and KPI registry. Include shared ownership, source links, data freshness and missing/unsupported evidence. Reconcile with `performance_records`, KPI values, Management BSC and approved config without exposing employee data in the manifest.
- Create a matrix for each **country x function x team/subteam x position/level x operation**: score, actual/target, ranking, trend, comparison, follow-up and navigation. Mark a cell verified only when source parity and permission checks pass. Include tracking-only measures such as AHT and abandoned calls without adding them to score.
- Resolve legacy aliases and current user-facing names centrally; test RCM Egypt separately from UAE calculation paths and handle explicit/shared country rules. Record unresolved conflicts rather than inventing mappings.
- **Gate:** the manifest reconciles to the current catalog, has no unexplained active entries, and represents no-data/inactive/unsupported cases; a product owner can inspect exceptions.

### Phase 3 — Canonical evidence and analytics tools

- Provide a typed allowlisted tool contract for concept lookup, metadata/definitions, published-period selection, scoped team/person lookup, current value, historical points, direction-aware ranking, branch/period comparisons and BSC. Bound rows, time, steps and result size. Join records by their actual composite keys.
- Reuse PMS's authoritative scoring/aggregation services for each source, including employee versus pooled KPI score, weights, units and count-versus-rate. Preserve actual publication month, data version, upload identity and scoring-basis provenance. A structured evidence ledger binds every fact to identity, period, metric, unit, filters and source link.
- Distinguish known zero, missing, empty denominator, unpublished, stale and not-authorized. Branch comparisons require all requested branches or a clear partial answer. No sample dashboard data may feed factual answers.
- **Gate:** independently computed expected values match the owner dashboard and approved source for each verified cell, including historical target changes, zero/missing, ties, same-named teams in both countries, position/BSC and region filters. Do not certify a team whose source rules cannot be proved.

### Phase 4 — Qwen-driven conversation and answer validation

- Qwen interprets the whole question, clarifies ambiguity, chooses from server-exposed typed tools and composes the final short answer from authorized evidence. Permit bounded follow-up reads for multi-part questions; keep deterministic calculations and fallback where validation fails.
- Server binds context, rejects unapproved tools/arguments, validates each claim against the fact ledger and checks both subject and metric/period association. A number appearing somewhere in the evidence is insufficient. Check answer completeness for every question part, units, polarity, rankings and ties. Reject claims that convert correlation to cause or invent personal/employment facts.
- Validate provider JSON with the same schema used by the running model, including failures and timeouts. If Qwen is unavailable, answer deterministically only when the same evidence is sufficient; otherwise say what is unavailable. Never silently substitute another department or latest month.
- Conversation ownership, request idempotency, scope revalidation before/after each tool/model call and safe cache invalidation on data/config/permission change remain mandatory. Model prompts and spreadsheet text are untrusted.
- **Gate:** independent held-out paraphrases and multi-turn cases cover every operation family, including incomplete evidence and misleading model output; direct short responses and exact facts verified, with provider/fallback provenance recorded separately.

### Phase 5 — Dedicated chat and all-page assistant

- Remove hard-coded Call Center defaults from chat state, API defaults and recommendations. Populate department -> team -> position filters from the authorized catalog, with `All authorized departments` as the neutral initial scope. A URL/page selection remains a visible, editable context within permissions.
- Add clear period, country, level and scope chips; preserve them when navigating and changing filters. Keep an honest source link with the answer and an optional “Explain more” or “Open details”; no mandatory charts, lengthy cards or repeated canned suggestions. Support keyboard, mobile and tablet layouts.
- Build an entry-point matrix for dedicated chat, Executive, Monthly Review, function, team, employee, BSC, reports and settings/help. Reuse one shared assistant and same evidence/permission contract. Show help only for verified pages and links; reject stale or unauthorized destinations.
- Add feedback: useful/not useful and optional reason; Admin reviews a de-identified case against source evidence. Do not learn from an unreviewed answer. A proposed action shows the supporting facts and confirmation state before save.
- **Gate:** browser tests exercise neutral opening, department switching, user context override, brief/default and expanded answers, page-to-chat carryover, unknown/error/empty states, access denial, responsiveness and action confirmation.

### Phase 6 — Evaluation, performance and security release gates

- Maintain versioned question sets with independently reviewed expectations. Separate training/development from frozen paraphrase-grouped holdout; include the prior 50 questions but do not tune to that set. Add real-source-derived anonymous cases from every available country/function/level plus unsupported/no-data and Arabic-accented names in English questions, without requiring Arabic UI.
- Report counts and failure categories by department, country, role, operation, data age, provider and fallback. Require **zero cross-scope disclosures**, **zero fabricated accepted facts** on the release suite, **100% required-part coverage** on accepted compound answers, and explicit handling of ties/missing/ambiguity. Set accuracy and latency targets after measuring a frozen baseline with the owner; publish denominators, not just percentages.
- Compare Qwen-on vs rules-only using the same evidence and queries; separately score semantic correctness, correct entity and period, numeric/units accuracy, helpful brevity, clarification quality and latency. Audit a sample manually. Test malicious instructions in uploaded labels and chat, replay/permission changes and action authorization.
- On the target KVM 2 measure idle and peak RSS, available RAM, CPU, queue length, p50/p95 time-to-first-token and completion, concurrent requests, timeouts and impact on dashboard/API/worker/database. Use bounded queue, timeouts, model context, backpressure and graceful fallback. If limits are missed, leave model off and improve capacity or scope; never treat a single-user laptop result as VPS readiness.
- **Gate:** repeatable result bundle, candidate SHA/model hash and resource measurements; no critical security or data-parity failures; approved rollback and monitoring. Keep access Admin-only through acceptance.

### Phase 7 — Controlled release and growth

- Stage the exact release artifact with production-shaped but authorized data and migrations checked separately. Enable for an Admin test account with an explicit feature switch; verify each department's questions and compare to source pages. Obtain the owner's acceptance before enabling other roles.
- Monitor model success/fallback, wrong-answer reviews, permission denials, latency and memory without logging sensitive content. Track every coverage cell and regression. Gradually release access only for role/scope combinations whose evidence and permission gates pass.
- Rollback by disabling the product AI flag and, independently, model routing/synthesis; verify the application and historical results remain healthy. Do not conflate a fallback answer with a successful Qwen response.
- **Gate:** user acceptance, full release evidence, support/runbook ownership, tested disable/rollback and a live health check. No automatic deployment is part of this plan.

## 5. Data model and migration policy

Audit existing AI conversations, turns, trace/feedback, catalog/coverage and evaluation-basis tables and migrations before proposing new tables. Reuse existing schema when it can represent the facts. If a gap is proven, prepare a separately reviewed additive migration for only the missing evidence metadata: `candidate_version`, catalog/coverage cell identifier, source/data revision, provider/fallback, fact references, validation result, review status and timestamps. Store references and redacted summaries rather than copying employee rows into training data. Define indexes, data retention, owner authorization, upgrade and rollback before deployment. Never overwrite historic evaluations or automatically promote feedback to a learned answer.

## 6. Dependencies and implementation constraints

- Start with the existing FastAPI, SQLAlchemy, React, query cache, pytest, Vitest and llama.cpp stack. Inventory package versions and security constraints before adding anything.
- Do **not** add scikit-learn, vector databases, embedding models or a training pipeline by default. The existing classifier report declined promotion because coverage/cost gates were not met. Consider a library only after a measured baseline shows a specific problem, and test quality, memory, maintenance and CPU cost on the target host.
- Build curated English domain aliases and metric metadata from verified PMS definitions. Do not hand-code an answer for each question; the model plans over typed facts, while paraphrase examples serve evaluation and model improvement.
- Any fine-tuning is an optional later experiment: only reviewed, de-identified data; separate training/development and frozen holdout; compare to the untuned Qwen and rules baseline; rollback on failure. It is not required to expose all departments.

## 7. First implementation handoff

1. Complete Phase -1 first: review and integrate the existing Qwen PR without modifying its source branch, run checks on the exact merge result, and merge it into the requested main repositories when authorized.
2. Run Phase 0 on the merged baseline and produce an audit table of current paths, provider use, source correctness, exact failures and scope coverage. Include both the dedicated chat and contextual views.
3. Implement Phase 1 Admin-only protection and truthfully report certification. Then deliver the catalog/coverage matrix and prioritized validated department waves; proceed to later phases only after their gates.
4. Keep every change reviewable, run focused plus relevant cross-layer/security tests, update the manifest and this plan with real evidence, and report remaining blockers. Any production deployment triggered by a main update must be identified and verified; enabling AI remains a separate controlled pilot step.

## Related project evidence

- [Original full-coverage plan](contextual-ai-assistant/FULL_COVERAGE_EXECUTION_PLAN.md) and [reported results](contextual-ai-assistant/FULL_COVERAGE_RELEASE_REPORT.md).
- [Conversation v2 release manifest](pms-ai-conversation-v2/RELEASE_MANIFEST.md) and [classifier evaluation](pms-ai-classifier-evaluation-report.md).
- [Local synthesis pilot](contextual-ai-assistant/LOCAL_EVIDENCE_SYNTHESIS_PILOT.md) and [coverage manifest](contextual-ai-assistant/coverage_manifest_v1.json).
- [Open Qwen wiring PR #81](https://github.com/mustafapato863-netizen/PMS/pull/81); its description is a proposal to verify, not a declaration of production status.
