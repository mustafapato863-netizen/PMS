# Bounded apply and persisted authority — local composition

Reviewed local closure: `dbecea2`, combining public authority `2af8b95` (sourcec479437) and dormant bounded atomic apply `dbecea2` (sourceb28f362). Public and bounded candidates were independently reviewed and tested before local cherry-picks; workflow merged without conflicts. This is not main publication, deployment or completed Phase7.

## Independent gates on the composed checkout

- Entire default backend collection, no exclusions: **1329 passed,1 failed,1 skipped,65warnings452.23s**. The unchanged real-Marketing-workbook fixture still expects68 vs actual131. Evidence: `D:/Projects/PMS_Dashboard/tmp/reviewer-composed-bounded-authority-full-20261010.xml`. This is not a fully green release suite.
- Real PostgreSQL16/18 bounded promotion/rollback/epoch/lock/authority cases plus immutable public Apply/Rollback revocation/deactivation probes: **18 passed62.61s** (`reviewer-composed-bounded-authority-native-20261010.xml`). Each fixture verifies owned loopback databases and resets only their disposable public schema. No production database was accessed. Prior independently rerun72foundation checks remain recorded in the bounded delta; this18-case composed gate is not a second72-case run.
- Actual auth-router password login, issued JWT, real AuthMiddleware and public evaluation/performance routers: **1 scenario passed7.25s**, with no dependency/authentication bypass other than providing an anonymous SQLite database. Test removes pytest legacy-access environment and checks unauthenticated401. Staging changes no live scores; promotion changes two Coding scores70→80. Public period reads the manifest with count2/can_rollback; public Apply recognizes it idempotently without duplicate revision/outbox. Manager and subsequently revoked Admin are denied rollback; restored persisted Admin rolls back exactly and repeat rollback stays422. Protected human texts remain unchanged. Evidence: `reviewer-bounded-public-jwt-20261010.py` and its XML in the same tmp directory. This is API integration, not browser or full deployed-app certification.
- AST-only graph update completed:10371nodes,28354edges,442communities. Existing empty-JSON/missing-SQL-parser/label warnings retained; no semantic API call or dependency installation. Graph output is not behavioral acceptance.

## Boundaries retained

## CI portability follow-up

Independent `CI=true` collection reproduced a new normal-test blocker: `test_evaluation_public_authority.py` required CI unset, so no cases could collect. Removed only that inappropriate CI restriction; explicit anonymous environment requirements and every authority assertion remain. The backend GitHub CI job now explicitly sets test environment, in-memory SQLite, empty Redis URL, an anonymous test-only JWT secret and disabled seed flags before imports. The unchanged37authority+35related cases then passed **72 cases,8warnings20.55s under CI=true**, evidence `reviewer-public-authority-ci-green-20261010.xml`. The earlier1329-case complete run predates this test/workflow-only portability repair; it is not described as a full CI execution. No native database guard or application authorization/scoring behavior was changed.

## Runtime and data boundaries

Fresh active persisted Admin is checked after the Team fence. Native races prove denial when revocation commits before the post-fence user SELECT. No User row lock serializes revocation after that SELECT; no stronger guarantee is claimed.

Promotion remains one transaction for scores, manifest revision, immutable control and one unpublished outbox. Page100 at the actual200-employee cohort measured1.516seconds/36SELECT/400sourcevisits/3.21MBtraced peak in synthetic SQLite stage-only; page200 reduced SQL but measured1.658seconds/5.49MBpeak. Default remains100. Full-month fingerprint scans persist on each page, so this is bounded retention, not linear-time growth or a production SLA.

Public async enqueue, evaluation lease/claim/reclaim/cancel/retry, outbox delivery and progress UI are not activated. Separate legacy queue isolation and dormant publisher candidates are being implemented; they are not accepted based on Grok reports. No formula/family admission, fixed-target upload behavior, original source, approval nonwrite, latest-only rollback, saved report bytes or user changes were altered. Missing approved family goldens remain blockers. Existing synchronous/public legacy snapshots remain compatible.
