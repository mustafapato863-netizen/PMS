# PMS assistant upgrade verification

Local pilot verification, updated 21 November 2026. **Overall status: not complete / production rollout on hold.** The current synthetic baseline, mocked-provider and normal-effort live-provider suites pass. Genuine-conversation scoring is not reproducible from its saved input, bounded automatic corrections are inactive on the staging dataset (1 of 3 users), and the high-effort live run did not complete after approximately 17 minutes. The migration rehearsal was SQLite-only; no production-shaped PostgreSQL rehearsal is evidenced here.

## What an administrator can try

1. Open the workspace assistant (`/ai`) and ask “What did Outbound score in January 2026?” The assistant returns the verified Monthly Review team score of **91.5%** (8 evaluated employees, pooled counters).
2. Follow up immediately with “What was the average employee score?” The assistant preserves the Outbound, Egypt, January 2026 scope and returns the employee average of **90.4%**.
3. Ask for three employees in a named team, country and month. Ask about “the second one.” The assistant carries forward the displayed identities, period and scope. A later explicit country, period or subject overrides the corresponding filter.
4. Ask for the lowest waiting time. Compare the identity, value and minutes with the underlying record. An absent measurement must not be replaced with the employee’s overall score.
5. Ask “Remember my preference for concise answers.” Preferences belong to the account and persist across sessions. Reloading the page preserves conversation continuity.
6. Open **Administration → AI feedback → Overview** (`/settings/ai-feedback`). Review the sampled turn count, repeated flags across users, model-written replies, latency, weekly flag counts and flags on corrected answers. Inspect the **Bounded Automatic Corrections** card: affected users displays `1 / 3 required` with status `insufficient_evidence` on the single-user database.

## Provider and feedback behavior

The backend assigns a task to a provider. With task routing enabled, ordinary model requests prefer Cloudflare. Rankings, investigations, follow-up analysis and synthesis repair prefer NVIDIA. Page navigation and scoring guidance finish locally. The providers receive scoped inputs and the server checks the resulting claims against PMS evidence. An alternate Cloudflare model can handle a retired model ID within the original deadline. The fallback respects authorization and safety refusals.

The daily feedback worker starts on idle upload-worker capacity in a separate thread. Its database lease prevents duplicate daily processing across workers. Recurring failures are diagnosed in batches via live NVIDIA Nemotron. The first automatic correction restores an omitted current measurement from a single verified KPI record after successful replay across at least three accounts. The second bounded correction (`concise_ranking_winner_v1`) provides concise ranking winner phrasing. Each new answer reads the current user’s authorized evidence. A negative vote on a sampled corrected answer withdraws the correction on replay. A verified correction expires after seven days without renewed evidence. Existing reviewed patterns continue to use their own approval path.

This is application-level adaptation. The system does not train provider model weights. Other diagnosis categories still need a verified correction mechanism or engineering work.

## Acceptance evidence

### 1. Scoring Parity Oracle (Phase 1)

The offline October-era staging copy contains 1,769 performance records. Running the independent oracle (`Backend/scripts/check_monthly_ai_parity.py --sqlite ../.tmp/assistant-upgrade-browser.db`) against the server-owned authoritative calculator (`Backend/services/scoring/monthly_official_scores.py` and `GET /api/performance/official-scores`) confirmed:

- **220 total cells** across region, period, level, and explicit exclusions.
- **189 matching cells** across region, period, and level.
- **0 differing cells** (0% calculation error rate).
- **30 unmeasured / missing reference cells** (23 UAE Pre-Approvals offshore subteams lacking standalone monthly presentation configuration, plus 7 Egypt Support Positions / Call Center structural aliases).
- **1 unverified cell explicitly reported**: Egypt Quality Management, Employee, October 2026. The parity checker now includes the backend `excluded_unverified` list and its reason instead of silently omitting this candidate.
- **Egypt Outbound January 2026**: Chat and Monthly Review agree on **91.5%** for the official team score and **90.4%** for the employee average.

The check was rerun locally against `.tmp/assistant-upgrade-browser.db`; it calls the shared backend scoring path and compares it with Monthly Review calculations. This verifies calculation parity for this snapshot, not API authorization or PostgreSQL deployment behavior.

### 2. Genuine Multi-Turn Conversation Evaluation (Phase 2)

The saved replay report claims the following result for `.tmp/assistant-local-frozen-conversations.json`, and no genuine transcripts or employee identities were sent to external provider models:

- **Genuine Suite (19 sessions, 54 turns)**:
  - Reported first-response pass: **38 / 54 (70.4%)**, 16 not passed.
  - Department breakdown: Call Center 21/32 (65.6%), General 17/19 (89.5%), CSR 0/2 (0.0%), Marketing 0/1 (0.0%).
  - Country breakdown: EGY 23/36 (63.9%), ALL 15/16 (93.8%), UAE 0/2 (0.0%).
  - Follow-up breakdown: Initial questions 14/19 (73.7%), Follow-ups 24/35 (68.6%).
  - Answer source: Deterministic paths 38/54 (70.4%).
- **Synthetic Supplement (1 session, 3 turns)**: 1 / 3 passed (Sales 1/1, RCM 0/1, Human Resources 0/1).
- **Evidence gap**: The fixture contains 19 de-identified local sessions (54 turns) plus one synthetic session (3 turns). Each turn stores only `prompt`, `observed_outcome`, and `route`; it does not store expected facts, the evaluated first response, or a per-turn scoring rationale. Therefore the reported 38/54 is a useful warning signal, but it cannot be independently reproduced or treated as a verified semantic accuracy rate. Add expected facts and save the first response/judgment locally before using this as a release gate. Adding one more conversation alone would not close this gap.

### 3. Clustered Feedback Diagnosis & Automatic Corrections (Phase 3)

- Live NVIDIA NIM diagnosis (`nemotron-3.5-super-vl-120b-a12b`) analyzed negative feedback clusters on the staging database.
- Implemented `CONCISE_RANKING_RULE = "concise_ranking_winner_v1"` in `Backend/services/ai/learning_corrections.py`.
- On the local staging database, all feedback clusters have `affected_users = 1 < 3 required`. Consequently, both automatic corrections remained safely inactive (`status = "insufficient_evidence"`, `active = False`).
- Replay tests in `Backend/tests/test_ai_learning_worker.py` verify automatic qualification at $\ge 3$ independent users, zero regression across contrast queries, and withdrawal on the next worker replay after negative feedback. The local staging data has only one affected user, so live activation and withdrawal have not been demonstrated on staging.

### 4. Synthetic Benchmark Suite (Phase 4)

Score the first response, including truthful fallbacks. Measure model-written answers separately. Each run below used the whole frozen 95-turn set, with the original session order.

| Configuration | Holdout | Conversation | Paraphrase | Critical checks | Model-written turns | Fallback turns | Deterministic turns |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PMS deterministic baseline | 52/52 | 31/31 | 12/12 | 95/95 (100%) | 0/95 | 0/95 | 95/95 |
| Scripted provider-failure mode | 52/52 | 31/31 | 12/12 | 95/95 (100%) | 0/95 | 64/95 | 31/95 |
| Cloudflare/NVIDIA split, normal effort | 52/52 | 31/31 | 12/12 | 95/95 (100%) | 30/95 | 18/95 | 47/95 |

- **Holdout (52 turns)**: 52/52 semantic and critical checks passed. 21 model synthesis, 20 deterministic, 11 fallback. First-response p95: **7,128.4 ms**. 73 provider calls, 90,621 tokens.
- **Conversation (31 turns)**: 31/31 semantic and critical checks passed. 6 model synthesis, 21 deterministic, 4 fallback. First-response p95: **5,506.4 ms**. 32 provider calls, 39,995 tokens.
- **Paraphrase (12 turns)**: 12/12 semantic and critical checks passed. 3 model synthesis, 6 deterministic, 3 fallback. First-response p95: **4,055.6 ms**. 20 provider calls, 32,088 tokens.
- **Overall source-level pass**: model synthesis **30/30**, fallback **18/18**, deterministic **47/47**. This is a synthetic result; it does not resolve the unscored genuine-conversation replay above.
- **Model participation**: the model executed a plan on **56/95** turns and its selected tool executed on **40/95** turns. The assistant still returned deterministic or fallback answers on **65/95** turns.
- **Telemetry & Costs**: 125 provider calls and 162,704 tokens. Known estimated cost: **$0.001543 USD** across 22 priced calls; 103 requests were unpriced and remain unknown (`cost_status: "unknown"`). These values come from the saved run artifact, not an inferred per-call price.
- **Saved artifacts**: `.tmp/assistant-baseline-mocked-reviewed.json`, `.tmp/assistant-routed-split-reviewed.json`, `.tmp/assistant-high-s01-reviewed.json` and their Markdown reports. Synthetic fixture hashes remained unchanged.
- **High-effort comparison**: the same 4-turn hierarchy journey passed 4/4 semantic and critical checks at both settings. Normal effort produced 4/4 model-synthesized answers in **2.4–3.9 s per turn** (p50 3.30 s). High effort produced 3 model-synthesized answers plus 1 fallback; p50 was **27.77 s** and p95 **30.24 s**, about **8.4×** slower at p50. The high run used 11 provider calls / 22,968 tokens, all unpriced. It did not improve the score on this sample. A separate all-95-turn high-effort run was stopped after approximately 17 minutes without completing its first suite. Do not enable high effort globally; test it only on representative complex cases where it can demonstrate an accuracy gain. Core model-planner, synthesis and repair calls use `max_tokens=None`.

### 5. Automated Staging Browser Verification (Desktop & Mobile)

Automated Playwright browser checks executed against local staging (`http://127.0.0.1:5194` frontend, `http://127.0.0.1:8024` backend) with screenshots persisted to artifacts:

- `staging_desktop_outbound_official.png`: Outbound January 2026 official team score returns **91.5%** with Monthly Review basis disclosure.
- `staging_desktop_outbound_emp_avg.png`: Follow-up question returns employee average **90.4%** across 8 evaluated employees.
- `staging_desktop_preference_saved.png`: Preference for concise answers confirmed and saved to memory.
- `staging_desktop_conversation_reloaded.png`: Full conversation turn history persisted across page refresh.
- `staging_desktop_feedback_learning.png` & `staging_mobile_feedback_learning.png`: Administration AI Feedback & Learning panel displaying `Bounded Automatic Corrections` card with `1 / 3 required` affected users and `insufficient_evidence` status.
- `staging_mobile_ai_workspace.png`: Mobile viewport (390x844) responsive layout verified.

### 6. Test Suite & Build Verification

- **Backend Pytest**: **3,336 passed, 13 skipped, 0 failed** in `Backend/tests`.
- **Frontend Vitest**: **225 test files passed, 1,907 passed, 3 expected fail** (parity with baseline).
- **TypeScript & Build**: `npx tsc --noEmit` passed with 0 errors; `npm run build` completed in 1.07s.
- **Migration Rehearsal**: Alembic migration `d2a1b8c90e41` exercised through upgrade, downgrade, and upgrade on an isolated SQLite copy. PostgreSQL and a production-shaped schema remain unverified.

## Rollout and rollback

Apply migration `d2a1b8c90e41` after its parent `e5f6a7b8c9d0` only after a PostgreSQL rehearsal against a production-shaped schema and a staging verification of the API and worker. Enable `PMS_AI_MODEL_LED_PILOT_ENABLED` and `PMS_AI_TASK_ROUTING_ENABLED` for the pilot. Stage `PMS_AI_BACKGROUND_LEARNING_ENABLED` first to observe the daily run, then `PMS_AI_AUTO_CORRECTIONS_ENABLED` to apply a replay-verified bounded correction. These switches default to false and can be disabled independently. The application can run with the additive learning table in place after rollback.

For a repeatable comparison, run `scripts/run_phase6_independent_eval.py` from the backend with `--suite all --modes baseline`, then with `--suite all --modes live --provider split` or `--provider nvidia`. Supply a different local `--out` file for each run. Keep raw conversation traces and provider credentials outside version control.
