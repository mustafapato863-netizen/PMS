# PMS AI Assistant and Searchable User Guide Implementation Plan

**Reference baseline** · `main@a97d395`

**First delivery** · The assistant answers “Show overdue corrective actions and tell me where to follow up” with authorized PMS records, verified instructions, and a working link in a single response.

## 1. Scope and existing components

Start with corrective-action guidance and read-only queries. Once this workflow passes the acceptance tests, extend the guide to cover the PMS overview, team selection, and monthly evaluation. Then add support for assessing Outbound Reachability targets.

Use an isolated branch and worktree based on verified `main`. Preserve the uncommitted KPI evaluation changes on `fix/pms-ai-answer-evaluation` and review their tests independently before integration. Deliver a local implementation branch and evidence from isolated tests. Production rollout and user activation require separate authorization.

| Existing component | Planned use |
|---|---|
| `ValidatedQueryPlanV2` and `QueryOperationV2` | Add typed operation arguments and use the existing two-operation limit for the first compound request. |
| `CorrectiveActionService.list_follow_up` | Use the same authoritative service as the follow-up API. The API already passes `state`. The current chat call passes `open_only`. |
| `get_authorized_navigation_targets` | Resolve guide page IDs to authorized links. |
| `AiConversationService` and access controls | Persist validated conversational context and recheck authorization on follow-up turns. |
| KPI read tools, `claim_validator`, and evaluation runner | Reuse scoring, evidence, units, and validation. Extend evaluation to cover the requested operation, effective filters, and service results. |

[Query contract](https://github.com/mustafapato863-netizen/PMS/blob/a97d395/Backend/models/ai_schemas.py#L85-L143) · [Current chat call](https://github.com/mustafapato863-netizen/PMS/blob/a97d395/Backend/services/ai/orchestrator.py#L5373-L5381) · [Corrective-action service](https://github.com/mustafapato863-netizen/PMS/blob/a97d395/Backend/services/corrective_action_service.py#L515-L578) · [Authorized navigation](https://github.com/mustafapato863-netizen/PMS/blob/a97d395/Backend/services/ai/contextual_assistant.py#L1437)

## 2. Expected workflow behavior

| User request | Expected result |
|---|---|
| “Where can I see corrective actions?” | Return the authorized link to `/corrective-actions` and explain how to open **Follow-up**. |
| “Show overdue corrective actions.” | Return the total and display the matching records from the user's authorized scope, including team and due date when available. |
| “Show completed ones.” | Switch the state to `completed` and retain the explicitly established scope for that workflow. |
| “Show overdue corrective actions and tell me where to follow up.” | Return the records and count from PMS, then include the guide steps and authorized link. |
| “What about Outbound?” | Keep the action state and change the team after checking access. |

**Proposed business rule.** Use the existing definition of overdue. An action is overdue when it is open or in progress and its due date is earlier than the PMS reference date. The reporting month is an optional filter, applied when requested or clearly established in the same workflow. Freeze the reference date in tests using the service's `today` argument. The process owner should confirm the reporting-period rule before it becomes final. [Overdue definition](https://github.com/mustafapato863-netizen/PMS/blob/a97d395/Backend/services/corrective_action_service.py#L710-L723)

Report zero results as a valid outcome. Report a failed read as unavailable. If the records load and the guide section is unavailable, return the records and explain the missing guidance. For general how-to questions, give usable steps and ask for a specific team only when needed to complete the request.

**Test example.** Given one overdue, one upcoming, and one completed action, return only the overdue record, then explain **Corrective Actions → Follow-up → Overdue**.

## 3. Request contract and guide design

Proposed extension to the existing contract. Define `args` separately for each operation. Resolve authorized scope on the backend using the authenticated session and the user's validated filters.

```json
{
  "schema_version": "pms-ai-query-v2",
  "scope": {"function": null, "team": null, "periods": []},
  "operations": [
    {"operation_id": "op_1", "kind": "corrective_actions", "args": {"state": "overdue"}},
    {"operation_id": "op_2", "kind": "guide_lookup", "args": {"query": "corrective action follow-up"}}
  ]
}
```

- **Corrective-action reads.** Pass the validated state and scope to the existing service. For a specified month and year, apply the month to the service and the existing year filter before counting or limiting the results. With no applicable period, query follow-up records across the authorized scope.
- **Guide lookup.** Return relevant sections with their stable IDs, page IDs, and content versions. Resolve links through the existing authorization-aware navigation code. When both operations run, retain the result and source of each in the response.
- **Tracing and continuity.** Record the validated operation, effective filters, result count, guide section and version, and execution status. Persist validated context and revisit permissions on subsequent turns. Check access to sections and records before using them in a response or sending them to the model.

Place the guide in `Backend/services/ai/guide_content/` so the backend image contains it. Start with `corrective-actions.md`, then add `overview.md`, `team-dashboard.md`, and `monthly-evaluation.md`. Use `index.json` for section IDs, titles and synonyms, page IDs, audiences, and source versions. Match the UI labels and test selected Arabic and English inputs, including spelling errors.

Load the approved content once per process. Search titles, synonyms, and section text locally with fuzzy matching for spelling errors. Return up to three short, relevant sections. If evaluation identifies a retrieval gap, compare semantic search on the same cases. Review the affected guide section when its screen or workflow changes.

The current corrective-actions page opens on **All actions**. Link to the page and tell the user how to select **Follow-up** and **Overdue**. [Backend packaging](https://github.com/mustafapato863-netizen/PMS/blob/a97d395/DevOps/docker/Dockerfile.backend#L33-L46) · [Initial tab](https://github.com/mustafapato863-netizen/PMS/blob/a97d395/Frontend/src/pages/CorrectiveActionsView.tsx#L219-L231) · [Follow-up filters](https://github.com/mustafapato863-netizen/PMS/blob/a97d395/Frontend/src/components/actions/ActionFollowUpBoard.tsx#L16-L24)

## 4. Implementation sequence

### 1. Establish a reproducible baseline

- Start with the five agreed questions. Seed overdue, upcoming, completed, and out-of-scope records with stable IDs. Freeze the test date and derive expected results directly from `list_follow_up` under the same access scope.
- Extend `Backend/scripts/run_phase6_independent_eval.py` or reuse its runner with a new fixture. Grade the requested operation, effective filters, record IDs, and required facts or instructions. Save the first response, failure reason, guide version, and commit SHA.
- Recheck the baseline CI. The last observed run for the reference SHA failed in `backend` and `coverage-manifest`. Track those failures separately from implementation regressions.
- **Acceptance.** Reproduce the filtering failure before the fix and verify the expected records independently of chat. [Evaluation runner](https://github.com/mustafapato863-netizen/PMS/blob/a97d395/Backend/scripts/run_phase6_independent_eval.py#L226) · [Baseline CI](https://github.com/mustafapato863-netizen/PMS/actions/runs/44903406594)

### 2. Build the corrective-actions guide and local search

- Write `corrective-actions.md` with stable sections for navigation, follow-up, and filters. Implement the reader and search in `Backend/services/ai/product_guide.py`. Validate the index, files, headings, and permitted destinations.
- Test paraphrases, typos, missing sections, sections outside the user's access, and loading from the backend image.
- **Acceptance.** The correct section uses real UI labels, loads in the current image, and can be retrieved locally without a model call.

### 3. Connect single-operation and compound requests

- Add typed arguments in `Backend/models/ai_schemas.py`. Connect `router.py` to execution through `orchestrator.py` and `tool_registry.py`. Reuse `contextual_assistant.py` for navigation after identifying every part of the request so a guide response cannot end a compound turn early.
- Pass the validated state to `execute_corrective_actions_status` and `list_follow_up`. Count all matching authorized records before limiting what the response displays. Apply the same execution rules to model-proposed and fallback plans.
- Render the first version directly from the records and guide steps. Reuse the existing planner for compound requests when needed. If the provider is unavailable, use established context and verified evidence where sufficient, or ask for the missing detail. Verify that read and guide requests leave action records untouched.
- Proposed rollback control · `PMS_AI_GUIDED_READS_ENABLED=false` in `AiRuntimeConfig`, within the current access gates. Enable it in isolated tests. Turning it off restores the previous path without a database change.
- **Acceptance.** Overdue and completed results match the service, navigation opens the approved page, the compound request completes both parts, and follow-up rechecks scope.

### 4. Expand the product guide

- Add the PMS overview, team selection, and monthly evaluation. Provide a concise product summary, give generic team navigation steps when appropriate, and resolve a team-specific link when the team is known and authorized.
- Explain `Save`, `Preview`, `Approve`, and `Apply` according to the existing monthly workflow. Review instructions against the UI and test original typo variants such as `tell me breef for system` and `how can i check specfic team` alongside new phrasing.
- **Acceptance.** Generic requests receive actionable instructions without unnecessary clarification, and links respect the user's access. [Monthly evaluation guide](https://github.com/mustafapato863-netizen/PMS/blob/a97d395/docs/guides/monthly-evaluation-admin.md#L5-L26)

### 5. Add Reachability target assessment

- Interpret “Should we adjust the target?” as a request to assess a decision. Retrieve the KPI definition, comparable actuals, and the targets and scoring basis applied in each period. Identify newly approved targets separately if they have yet to be applied. Include coverage and sample size when available.
- Calculate the effect of a hypothetical target only when verified inputs and an approved calculation are available. Show actual Reachability separately. Compare explanations such as a target change or a performance decline, and state what additional evidence is needed when the periods or data are insufficient.
- **Acceptance.** The response provides a supported assessment or identifies the missing evidence. A scenario test proves that changing the hypothetical target changes measured attainment while the underlying actual remains fixed. [Reachability definition](https://github.com/mustafapato863-netizen/PMS/blob/a97d395/docs/KPI_CONFIGURATION_REFERENCE.md#L238-L250)

## 5. Acceptance and measurement

| Dimension | Verification |
|---|---|
| Intent | “Where” produces navigation, “show” produces a read, and a compound request produces both. “Past due” and “overdue” produce identical results. “Completed” changes the result set. |
| Execution | Exact record IDs match the service. The count reflects full filtering before truncation. Test empty results and failed reads independently. |
| Context and access | Cover authorized and unauthorized teams and branches, permitted links, and changes of team during follow-up. |
| Retrieval | The correct section ranks in the top three, its steps match the UI, and the link opens an authorized page. |
| KPI regression | Preserve Waiting Time coverage for employee, KPI, period, unit, zero, and missing data. |
| Speed and cost | Measure local retrieval `p50` and `p95`, end-to-end latency, and model calls under the same cases and settings. The proposed warm retrieval target is `p95 ≤ 50 ms`, subject to measurement in the test environment. |

**Proposed initial suite.** Use 24 cases for the first workflow, with 12 development cases and 12 held-out cases drawn from independent phrasing and context groups. Require exact matches for core cases, zero unauthorized records or links, and zero changes to action records. Report failures and blocked cases by task. If live model testing on test data is authorized, report it separately from rules-based and mocked runs.

## 6. Verification and delivery

Run focused tests from `Backend/` with Python 3.11, matching CI. The guided reads and product guide test files are proposed additions.

```bash
python -m pytest -q tests/test_action_follow_up.py tests/test_corrective_action_scope.py
python -m pytest -q tests/test_ai_guided_reads.py tests/test_ai_product_guide.py \
  tests/test_ai_intent_gate_and_origin.py tests/test_ai_response_quality.py \
  tests/test_ai_scope_and_context.py tests/test_ai_independent_eval_scoring.py
```

From the repository root, refresh the inventory when tests change, verify coverage and diffs, build the backend image, and check that it can load the guide. Use full Git history for source-provenance checks. Run GitHub CI on the branch after separate authorization to push it.

```bash
python evaluation/pms-ai/phase0/inventory_test_types.py
python -m pytest -q evaluation/pms-ai/phase2/tests/test_coverage_manifest.py
git diff --check
```

**Expansion decision.** Review the baseline, first guide, read and navigation behavior, and held-out compound results together. Expand the guide and add decision support once the first workflow meets its acceptance criteria. For each failure, record the earliest point of divergence, the SHA and runtime settings, and the expected behavior.
