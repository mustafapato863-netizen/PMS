# Plan: Raise scoped-manager AI daily limit from 50 → 200 turns

## Goal
Increase the daily AI chat-turn budget for the `scoped_manager` persona tier (used by the automation agent reviewing/extracting/correcting feedback) from **50 turns / 25,000 tokens** to **200 turns / 100,000 tokens** per UTC day, so the agent is not throttled mid-workday.

## Current state

| Tier | Daily turns | Daily tokens | Roles typically mapped |
|---|---|---|---|
| `global_exec` | 100 | 50,000 | Admin, General Manager, Performance Team |
| `scoped_manager` | **50** | **25,000** | Manager (automation agent scope) |
| `self_only` | 20 | 10,000 | Agent, Employee, Executive |

The limit lives in `Backend/services/ai/usage_budget.py`, `TIER_BUDGETS` (lines 76–80). It is enforced by `check_user_daily_budget()` (line 205) whenever the access tier is widened beyond `admin_only` and no explicit env cap (`PMS_AI_DAILY_USER_REQUEST_LIMIT` / `PMS_AI_DAILY_USER_TOKEN_LIMIT`) is set.

Tests asserting the current value: `Backend/tests/test_usage_budget_tiers.py` lines 9–27.

## Changes

### 1. `Backend/services/ai/usage_budget.py`
Raise `scoped_manager` budget proportionally (4× turns → 4× tokens so the token ceiling does not become the new bottleneck):

```python
TIER_BUDGETS: dict[str, dict[str, int]] = {
    "global_exec": {"daily_turns": 100, "daily_tokens": 50_000},
    "scoped_manager": {"daily_turns": 200, "daily_tokens": 100_000},
    "self_only": {"daily_turns": 20, "daily_tokens": 10_000},
}
```

### 2. `Backend/tests/test_usage_budget_tiers.py`
Update assertions:
- Line 10: `scoped_manager["daily_turns"] == 50` → `== 200`
- Add assertion for `scoped_manager["daily_tokens"] == 100_000` (currently only turns are asserted; add token coverage for completeness).

### 3. Documentation (optional but recommended)
Note the env-var override path in ops docs so future tuning does not require code changes:
- `PMS_AI_DAILY_USER_REQUEST_LIMIT` overrides turns
- `PMS_AI_DAILY_USER_TOKEN_LIMIT` overrides tokens

Verify whether `docs/ops/pms-ai-pilot-release-checklist.md` or `docs/ops/pms-ai-provider-verification.md` mention the 50-turn default; update if present.

## What this does NOT change
- `global_exec` (100 / 50k) and `self_only` (20 / 10k) tiers are untouched.
- Admin users are not affected by tier budgets (access tier `admin_only` skips tier fallback).
- Per-request input ceiling (256k) and per-message caps are untouched.

## Verification steps
1. `python -m pytest tests/test_usage_budget_tiers.py -q` — scoped-manager tier assertions.
2. `python -m pytest tests/test_ai_phase7_budgets_and_telemetry.py -q` — daily-limit enforcement paths.
3. Full AI-focused suite: `tests/test_ai_workspace.py`, `tests/test_ai_response_quality.py`, `tests/test_ai_phase4_conversation_answers.py` — confirm no regression in chat flow.
4. Full backend suite — confirm only pre-existing `test_marketing_import` failure remains.

## Rollback
Revert `TIER_BUDGETS["scoped_manager"]` to `{"daily_turns": 50, "daily_tokens": 25_000}` and restore test assertions. One-line code change; no migration or schema impact.

## Delivery
Commit and push to `origin` + `gitlab` `main` only after the above tests pass.

---

**Awaiting your approval** — confirm:
1. Proceed with scoped_manager 200 turns / 100,000 tokens?
2. Should I also add/verify env-var documentation for `PMS_AI_DAILY_USER_REQUEST_LIMIT` / `PMS_AI_DAILY_USER_TOKEN_LIMIT`?
3. Any specific automation-agent role/identity to scope this to beyond `scoped_manager`?
