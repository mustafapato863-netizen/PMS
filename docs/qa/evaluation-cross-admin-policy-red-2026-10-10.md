# Cross-Admin management policy: independent pre-change evidence

The owner explicitly permits any persisted active Admin to inspect/cancel an unpromoted job or recover an already committed promotion, retaining its original requester and captured attribution. Starting/staging/promoting or retrying the **same** job remains its original active requester's responsibility; no snapshot grants authority after revocation. Cancellation followed by a **new** capture under a different active Admin is a distinct request.

This document records the old-policy baseline, not acceptance of the new implementation. Closure `f296948` still has requester-only management. Neither active delegate checkout was edited or tested by these probes.

## Actual baseline results

- An external immutable native harness exercised the allowlisted disposable PostgreSQL16/18 pair sequentially: **4 failed /7.63 seconds**. Another Admin's status read for an inactive owner was denied, and its concurrent cancel versus the original owner's start was denied. These failures reproduce the policy difference; they are not database fixture/setup failures. Both worker threads joined before fixture teardown.
- A separate anonymous in-memory SQLite harness exercised actual capture/stage/promotion before disabling the requester, and injected audit-write failure on cancellation: **2 failed /3.82 seconds /7 existing warnings**, both at the old requester-only authorization boundary. Recovery never ran; audit atomicity is therefore **unproven** at this checkpoint. The actual pre-recovery promotion completed and left the job running as expected.

Harnesses and XML are retained under the primary workspace's ignored `tmp/`: `reviewer-evaluation-cross-admin-pg-20261010.py`, `reviewer-cross-admin-baseline-red-20261010.xml`, `reviewer-evaluation-cross-admin-recovery-20261010.py`, `reviewer-cross-admin-recovery-baseline-red-20261010.xml`.

The unchanged post-implementation repeat must additionally prove original identity/source equality, actual management audit actor, cancellation and audit in one transaction, exactly one committed revision/outbox after recovery, no rescoring on acknowledgement, and continued refusal of cross-Admin execution. Passing the baseline setup alone does not establish those assertions.

No production database, user workbook, main branch, remote or deployment was changed. These are application authorization tests, not native row-security policy certification.
