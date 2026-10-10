# Persisted-pin response cache and separate-process freshness

Date: 10 October 2026. Reviewed against local closure `7f7bc34`. No main publication, production change, Redis access or new scoring-family admission.

## Defect and repair

Pinned summary evidence enrichment reused `key` for a `(record_id, year)` pair after computing the scope/version response key. The summary was then stored under that tuple rather than its string response key. A separate warm reader consequently recomputed its summary; its roster response still hit the proper key. Returning current scores was not itself broken. A real Redis command also cannot accept this tuple as a normal key.

Rename only the enrichment loop variable and its evidence index. No score, scope, unit, precision, direction, source or authorization changes. Strengthen the existing lifecycle regression with string-key identity and a repeated pinned summary that must avoid the roster projection; preserve all original apply/rollback assertions.

## Independent evidence

- Strengthened lifecycle test before repair: **1 FAIL, 1 PASS, 2.28s**. Artifact `D:/Projects/PMS_Dashboard/tmp/reviewer-summary-pin-cache-red-20261010.xml`.
- Focused summary/records/basis/reporting gate, explicit anonymous `CI=true`: **53 PASS, 8 warnings, 12.94s**. Artifact `reviewer-summary-pin-cache-green-20261010.xml` in the same directory. This is a local CI-shaped run, not a remote workflow result.
- Owned PostgreSQL16/18 separate-process reader/writer, sequential: **2 PASS, 7 warnings, 13.61s**. Artifact `reviewer-cross-process-cache-pg-final-green-20261010.xml`. A child retains its actual process-local response cache across new SQL sessions while the parent captures, stages, promotes, and performs exact latest rollback. Both Redis clients are absent throughout; versions remain0. Capture/staging leaves scores and identity unchanged; apply and rollback each change committed database identity. Summary and roster repeat requests hit cache after apply **and** rollback, in the same child process. All owned children exit before fixture cleanup.
- The earlier independent PostgreSQL diagnostic reproduced the same-key summary miss and tuple cache write before repair. `reviewer-cross-process-cache-key-red-20261010.xml` is RED evidence, not a release result.
- Complete post-repair default backend, no exclusions: **1400 PASS, 1 unchanged Marketing FAIL, 1 existing SKIP, 65 warnings, 288.58s**. Artifact `reviewer-summary-pin-cache-full-20261010.xml`. The unchanged failure expects68 rows while the local private workbook imports131; neither source nor assertion was altered. Not release-green.
- Actual auth-router password login/issued JWT/public evaluation and performance lifecycle: **1 scenario PASS, 8 warnings, 4.01s**, artifact `reviewer-summary-pin-cache-jwt-20261010.xml`. Covers promoted manifest compatibility, replay, persisted management denial and exact latest rollback. Initial scratch invocation intentionally failed its existing CI guard before collection; rerun used the required anonymous reviewer environment without changing the guard.
- AST-only refresh completed:10563nodes/28917edges/449communities. Existing21zero-node JSON sources, missing SQL parser and164hub-label refresh warnings remain; no dependency install, LLM or remote graph rebuild.

The bounded fixture deliberately stores legacy scalar score70 and contribution1, so its legacy roster reconciles to100. The exact observed summary sequence is70/80/70; roster100/80/100. This is an explicit cache-ownership characterization, **not** a formula/parity golden. No legacy expectation or scoring logic was altered to hide that fixture difference. A diagnostic initially tried to serialize UUID tuple keys to JSON and timed out; string-only diagnostic output corrected the harness, not application behavior.

## Real Redis outage/reconnect follow-up

An isolated cached Redis7 image was available locally. Reviewer created only the labelled ephemeral container `pms-eval-review-redis-20261010`, bound to127.0.0.1:56379, no host volume, read-only root and temporary `/data`. Identity, ownership label and exact loopback binding are checked before every pause/unpause/stop; no existing Redis or production connection was used. The normal runner retains emptyREDIS_URL; the child explicitly injects the actual LazyRedisClient pointing only at that owned instance.

Separate-process PostgreSQL16/18 gate: **2 PASS, 7 warnings, 18.13s**, artifact `D:/Projects/PMS_Dashboard/tmp/reviewer-cross-process-redis-reconnect-pg-20261010.xml`. Real JSON response keys are present in Redis. Warm child reads use shared cache; pausing Redis forces actual socket-timeout fallback. Parent capture/stage/promotion uses the owned database. After unpause the same child reconnects and sees applied80, not Redis's older70. The actual dormant publisher sends directINCR/PUBLISH and commits one acknowledgment; a real subscriber receives exactly the generic version1 notification. Subsequent repeated reads hit cache; latest rollback refreshes the same child to summary70/legacy fixture roster100 with sharedversion1 unchanged. No notification was mistaken for subscriber-wide acknowledgment or exactly-once delivery.

The owned container was stopped and auto-removed after the successful tests; only temporary synthetic cache data was discarded. Both child processes exit before native fixture cleanup. This closes actual unavailable/reconnect proof for canonical summary/roster plus one real outbox-delivery command/subscriber path, not production runtime registration, every consumer, crash-exactly-once or full-role UAT.

## Limits

These gates prove this canonical summary/roster path under unavailable Redis and the explicit local reconnect follow-up above. They do not certify every live consumer, full-role browser behavior, runtime worker activation, production latency or the entire roadmap. The complete post-repair suite still retains its unchanged Marketing131-versus68FAIL/existingSKIP. Phase7C1 is a separate active, unaccepted candidate.
