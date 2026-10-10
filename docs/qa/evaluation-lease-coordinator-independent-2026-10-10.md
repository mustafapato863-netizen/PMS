# Independent lease coordinator acceptance

Date: 10 October 2026. Local acceptance only; no main merge, publication, runtime activation or deployment.

## Evidence

- Anonymous CI-shaped SQLite suite: 125 passed, 9 warnings, 147.36 seconds. Five related modules plus the four immutable reviewer clock cases. Artifact: `D:/Projects/PMS_Dashboard/tmp/reviewer-lease-independent-normal-20261010.xml`.
- Sequential PostgreSQL 16/18 run: 24 passed and eight reviewer-harness failures. The 24 passing cases cover original claim/cancel, expired reclaim and old-token rejection, split promotion/ack recovery, cancel/promotion races, and committed role revocation/inactivation during a real Team lock wait. Artifact: `D:/Projects/PMS_Dashboard/tmp/reviewer-lease-independent-native-20261010.xml`.
- Corrected harness repeat: all eight expired-during-Team-wait cases passed, no errors or skips, 24.529 seconds. Artifact: `D:/Projects/PMS_Dashboard/tmp/reviewer-lease-clock-native-adapter-green-20261010.xml`.

The original immutable PostgreSQL probe was retained. Its error-code helper expects a pytest exception wrapper, but the thread returns an exception directly. A separate adapter wraps that exception with `.value`; timing, exact error type/code, and unchanged-state assertions remain unchanged. Before the product fix, all eight operations incorrectly succeeded and failed the earlier assertion, independently reproducing the stale admission-clock defect. The harness correction does not reinterpret those genuine RED results as passing.

## Review boundaries

The two bounded-apply seams retain their existing defaults. Capture, scoring families, source evidence, proof/lineage checks and latest-only rollback are unchanged. Coordinator execution uses fresh persisted active Admin authority after the Team fence and the immutable captured requester; actor snapshots are attribution, not grants. Another Admin cannot adopt this job. A revoked/deleted requester requires a separately reviewed administration policy before general runtime rollout.

Time is validated before SQL, then sampled again after ordered Team/job/scope/control fences. Lease admission is checked at that instant, not again at commit. User authority is a nonlocking fresh read; revocation committed after that read is not serialized across the whole transaction.

Promotion commits scores, revision and outbox before the later acknowledgement, which is recoverable without duplicate promotion. Ordinary legacy workers continue to reject the evaluation kind. No coordinator route, worker polling, publisher registration or UI is enabled by this acceptance.

This evidence certifies the dormant coordinator slice, not all teams, all consumers, the full composed backend, production throughput or the complete roadmap. Unsupported mathematical families remain blocked pending approved source goldens. AST update completed with 10,696 nodes, 29,368 edges and 462 communities; existing empty-JSON and SQL-parser warnings remain.
