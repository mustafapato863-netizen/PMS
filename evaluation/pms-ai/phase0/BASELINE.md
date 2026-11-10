# Phase 0 rules-only baseline

Recorded after merging `main` `bd51e73ce711e8fa14c72e98fcc13e9a671cde56` into the draft branch. The code that answered the cases is merge commit `9b238b028b40f1b1cca994fae06624232002ea51`. The machine-readable copy is `baseline.json`. Raw turns are in `results/rules_only_bd51e73.json`.

This is not a Qwen run. No model process was started. The disposable SQLite database had the product switch `ai_enabled` on and **zero** `performance_records` rows. Users were local fixtures (Admin, Manager, Employee, Branch Director, Function Director). No production database was opened.

## Flags

The product switch defaults to off: a missing `product_settings` row, an unreadable table, and seed all leave `ai_enabled` false. `ProductSetting.enabled` defaults to false. This run turned it on for the fixture only.

With `APP_ENV=production`, read from the code at the evaluated commit (secrets not printed):

| Setting | Production value |
| --- | --- |
| Router mode | `hybrid` (`PMS_AI_ROUTER_MODE` default) |
| Gemini routing | false |
| Classifier | `off` (forced while `APP_ENV=production`) |
| Intent (`PMS_AI_LLM_INTENT_ENABLED` or `PMS_AI_LOCAL_ROUTER_ENABLED`) | false |
| Synthesis (`PMS_AI_LLM_SYNTHESIS_ENABLED` or `PMS_AI_LOCAL_SYNTHESIS_ENABLED`) | false |
| Exploration | false. `local_exploration_enabled()` returns false for any flag value when `APP_ENV=production` |
| Conversation state | true unless `PMS_AI_CONVERSATION_STATE_ENABLED` is set false |
| Brief answers | true |
| Configured model name | `qwen3-4b-q4_k_m` (`PMS_AI_LLM_MODEL`, else `DEFAULT_MODEL_NAME`) |
| Model file in Compose / env example | `/models/Qwen3-4B-Q4_K_M.gguf` |
| Model SHA-256 | not available |
| Prompt version | not available. Trace export labels in code are `pms-ai-router-v1` and `pms-ai-narrative-v1`. Request context type is `PageContextV1`. Evidence `aggregation_version` is `v2`. |

Checked-in Compose and `DevOps/.env.example` also default intent, synthesis, and exploration to false. `PMS_AI_LLM_API_KEY` is empty in those examples. This run left the key unset and did not set `PMS_AI_LLM_BASE_URL`.

The process that ran the cases used `APP_ENV=test` so SQLite and the test JWT path were legal. Model flags were the same false values as production. `JWT_SECRET`, `DATABASE_URL`, and the fixture password were set and are not printed. `GEMINI_API_KEY` was unset. `REDIS_URL` was unset.

## How the cases were run

`run_rules_only_baseline.py` calls the FastAPI routes the UI calls:

- Dedicated chat, uploaded-label questions, and the page-opening case: `POST /api/ai/chat` with the dedicated page's opening `session_state` (`function: "Call Center"`).
- Contextual cases: the same route, plus `page_context`, using the panel's session fallback.
- Direct API cases: `POST /api/ai/chat`, `GET /api/ai/catalog`, or `POST /api/ai/feedback` as the case names.
- Multi-turn cases send later user turns with the returned `conversation_id` and `context_version`.

Non-Admin fixtures authenticated as themselves. The pilot dependency rejected them with HTTP 403 and `PMS AI is limited to administrators during the pilot.` No score or name was in those bodies.

## Call Center defaults observed

- `SessionFilterContext.function` defaults to `Call Center`. A chat request that omits `session_state` resolves to that function.
- `GET /api/ai/watching` with no `function` query resolves to `Call Center`.
- `Frontend/src/pages/PmsAiWorkspaceView.tsx` uses `searchParams.get('function') || 'Call Center'`. The empty team menu is labeled "All Call Center" and lists Inbound, Outbound, and Support Positions. The branch control is labeled "Filter UAE Branch". Starter prompts ask about Call Center.
- `ContextualAssistantPanel` sets `function` to the page function or `Call Center`.
- A teamless booking question (`fz-009`) was answered as Inbound, not as a request to name the team: "Dubai led September 2026 Inbound bookings with 0, followed by Ajman with 0 and Sharjah with 0."
- "What is Mariam's score?" and "Who is ahead?" were scoped to Call Center · September 2026 without a question.
- "How did Coding perform over six months?" resolved to team `Coding` (the UAE catalog name) under RCM, with no Egypt/UAE question.
- Some RCM and Pre-Approvals questions kept `function: Call Center` while setting `team` to RCM or Pre-Approvals (`fz-037`, `fz-039`).

Marketing (`fz-021`) did leave Call Center: the resolved function was Marketing. That question names the department.
