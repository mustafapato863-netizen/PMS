# PMS AI status

## 2026-11-09 — Phase -1 integration (not merged)

Integration branch `cursor/ai-phase-minus-1-integration-dff5` was opened from main `3f1d914549c06affc5f63ea33e034e711738c3bb` and merge-committed PR #80 `0c7fe890054f154010037dcca64b5e7e1eb8390c` and PR #81 `d5e488ab10d697830a86adb5417d1da31c202bb0`. Those PR branches were not modified.

Admin-only pilot is enforced with `require_ai_admin` on every `/api/ai` route, in addition to `require_ai_enabled`. `ai_enabled` stays off for a fresh migration, a missing row, and seed. Compose `llm` remains profile-gated. Intent and synthesis defaults in Compose, env examples, and the Hostinger workflow are false. Exploration stays off when `APP_ENV=production`.

This change is a pull request only. It was not merged and was not pushed to main.
