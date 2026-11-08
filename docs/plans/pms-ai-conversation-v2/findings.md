# Planning findings — 2026-11-06

- Active AI source changes exist in the shared working tree. This is a moving snapshot, not a completed release audit.
- Existing implementation includes router, classifier, catalog, tool registry, trace logger, typed query/evidence/context schemas, and React AI workspace.
- Existing dependencies already cover FastAPI, Pydantic, SQLAlchemy, Alembic, Redis, NumPy, HTTPX, pytest, Hypothesis, React Query, Zod, Vitest and Playwright. RapidFuzz and scikit-learn are not declared in Backend/requirements.txt at inspection time.
- PerformanceRecord has composite primary key (id, year); KPIValue correctly uses (record_id, record_year). Preserve that identity in any provenance links.
- AiInteractionTrace exists in ORM, with string user_id; its logger still calls a runtime table-create helper. No matching AI trace migration was found in the migration search. Verify real schema before adopting the table into migrations.
- Current conversation context lacks a durable, server-owned conversation identity and a complete typed reference model for people and compound requests.
- Monthly Presentation is the intended hierarchy/UX reference, but callCenterDeepDiveData.ts includes fallback values. Only verified live published evidence is an answer source.
- Existing evidence caching includes scope and data/config/evaluation versions; verify all dimensions and permission revocation rather than introduce competing caches.
- Earlier 8/26 dialogue result and transient ranking TypeErrors were measured during concurrent edits. Rerun on an immutable baseline; do not use them as current release evidence.
- Official docs checked: PostgreSQL FK constraints; Alembic generated migration review; RapidFuzz matching; scikit-learn text features, calibration and model persistence.

## Read-only inspection issues
- `rtk proxy Get-Content` cannot launch a PowerShell builtin. Resolved with `rtk proxy powershell -NoProfile -Command ...`.
- Initial search used nonexistent src/ and cache_invalidation.py paths. Resolved to Frontend/src and cache_invalidation_service.py.
- Gemini structured-output page returned unsupported text/markdown to web open. Provider details remain subject to official-doc verification before implementation; no model version or pricing recommendation is asserted.
- Documentation validation initially failed because PowerShell consumed literal backticks in a regex. Changed the validator to construct the backtick with chr(96); no source or document content was affected.
