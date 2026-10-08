# Monthly evaluation delegation queue

Canonical reference: `../monthly-evaluation-settings-plan.md` (PMS-EVAL-001).

Model: Grok Build `grok-4.7`; maximum supported reasoning `xhigh`, verified by CLI validation and successful no-tool preflight on 2026-10-08. Reported serving model was `grok-4.7-build`. No silent fast-model downgrade.

Policy D-001 approved by user: Admin-only for ALL Evaluation Settings stages. See approved-decisions.md; this overrides Performance Team proposals in the reference. Phase 0 run 1 dispatched using Grok relay; terminal session 54591, Grok session 01a11cd2-0e4e-74f0-baec-d8e37f172055. Outputs outside the worktree: C:/Users/sghd70204/AppData/Local/Temp/pms-grok-evaluation-20261008/phase-0-run-1.

| Phase | Brief | State | Dependency / gate |
|---|---|---|---|
| 0 Audit and golden baseline | phase-0-brief.md | Source/test slice reviewed; partial, draft PR pending | Source baseline 2af9eb1; golden/rollout gates remain |
| 1 Schema/evidence | phase-1-brief.md | Queued, not dispatched | Accepted Phase 0; verified schema and business defaults |
| 2 Catalog/resolver | phase-2-brief.md | Queued, not dispatched | Accepted Phase 1 |
| 3 Lifecycle API | phase-3-brief.md | Queued, not dispatched | Accepted Phase 2 |
| 4 Actual ingestion | phase-4-brief.md | Queued, not dispatched | Accepted Phases 2–3 |
| 5 All consumers/cache | phase-5-brief.md | Queued, not dispatched | Accepted Phase 4 |
| 6 Settings UX | phase-6-brief.md | Queued, not dispatched | Real API and reader contracts, Phases 3/5 |
| 7 Explicit apply/history | phase-7-brief.md | Queued, not dispatched | Accepted Phases 4–6 |
| 8 Integrated UAT/release gate | phase-8-brief.md | Queued, not dispatched | All preceding phases accepted |
| 9 Custom formulas | No implementation brief | Deferred, outside this release | Actual formula examples + separate approval |

Each phase receives an isolated `codex/` branch and a separate reviewed PR; overly large phases may be split further. Later prompts must be refined with actual accepted contracts before dispatch. Parallel sessions are optional and limited to independent scopes. Nothing merges into main or deploys while dependent phases or release gates remain incomplete. Codex owns review, rework, independent verification, commits, PR creation and final integration.

No phase is accepted based only on the implementer's success report. Track sessions, commits, PR URLs and evidence here as they occur.

Phase 0 run 1 stopped at its 100-turn limit (exit 1), leaving 20 characterization tests and a source inventory. It is NOT accepted. Codex independently ran tests and supplied review/local schema evidence. A specific-session continuation with phase-0-rework-brief.md will finish the audit and tighten baseline assertions; no downstream phase dispatched.

Run 2 completed on the same session/model/effort. Codex reviewed the full report, corrected factual wording, and independently reran 64 passing targeted tests (1 existing local-dataset skip). Full local suite had 1064 passing tests, 1 existing external Marketing workbook failure reproduced on untouched main, 1 skip. No full release green claim. Draft PR base will be codex/monthly-evaluation-integration; main stays at 2af9eb1. Further phase dispatch is gated on reviewed contracts and unresolved scoring decisions, not assumed from CLI exit 0.
