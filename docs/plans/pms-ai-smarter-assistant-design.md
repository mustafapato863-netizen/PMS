# PMS AI: making the assistant smarter (design, English only)

Status: proposal, 26 Nov 2026. Nothing here changes the provider or raises paid usage until approved.

## Findings that shape the design
- A model-led planner already exists behind `PMS_AI_MODEL_LED_PILOT_ENABLED` (Backend/services/ai/config.py). `compose.production.yml` defaults it to false, so the production value must be read from the Dokploy backend env before any claim about what runs live.
- The deterministic router (router.py 5.4k lines, orchestrator.py 7.2k lines) is the fallback and the baseline. On the new offline eval (`Backend/scripts/eval_assistant_quality.py`, 34 English cases) it passes 16/34: direction 5/7, cross-region 1/4, period change 1/4, scope reset 1/2, compound 0/3, why 0/4, period note 0/2, controls 8/8.
- Missing capabilities (not just routing bugs): cross-region comparison, KPI deltas between periods, driver + peer + trend "why" diagnosis, compound questions answered part by part.

## Flow
1. Understand: resolve follow-ups with conversation memory (scope, period, subject) and reset scope on company-wide cues.
2. Plan: the model picks one or more read-only tools and arguments from the registry (JSON plan, max 4 steps). The deterministic router stays as fallback when the model is unavailable, times out, or returns an invalid plan.
3. Execute: tools run read-only and return typed evidence (existing evidence and claim-validator contracts).
4. Answer: model writes from verified facts only; the claim validator rejects unsupported numbers; on rejection use the deterministic text.
5. Show: answer, evidence table/chart, confidence line, and 1-2 suggested next steps.

## New registry tools (each a separate PR, each with eval cases)
- compare_regions(period, metric): Egypt vs UAE overall and by function, with the gap.
- kpi_period_delta(scope, from, to): KPIs that moved most up and down, with actual/target.
- diagnose_why(subject, period): driver KPIs vs target, trend over 3-6 months, peer/team average, ranked contributors, then 1-2 concrete actions (links to Corrective Actions drafts).
- Compound planner: split "A and B" into parts, run each, answer every part.

## Wider additions (top picks, in order)
1. Follow-up memory ("and for UAE?", "the second one").
2. Root-cause "why" with evidence and an uncertainty line ("based on 3 months, 49 evaluated agents").
3. Recommended actions linked to Corrective Actions (draft, never auto-create).
4. "Show the data" (evidence table plus small chart on every analytic answer).
5. Streaming answers and a latency budget with a visible timeout message.
6. Proactive weekly insights (top movers, at-risk teams) via the existing insights page.
Forecast and what-if: what-if exists (`what_if_service.py`); forecast is a later item (needs 6+ months of data per team).

## Latency and cost
- Today: 1 planner call + 1 synthesis call per question (about 25-30 s observed). Target: p50 under 8 s using a smaller planner, cached evidence, parallel tool calls, and streaming the headline first.
- Cost: no provider change. Planner calls stay on the currently configured provider. New tools add no model calls. The "why" diagnosis adds at most one synthesis call.

## Rollout gate
- Flag `PMS_AI_PLANNER_V2_ENABLED` (default off). Offline eval (deterministic and mocked-planner) must not regress, new cases must pass, then a live-provider run on the same cases is compared before flipping. Rollback is flipping the flag.
