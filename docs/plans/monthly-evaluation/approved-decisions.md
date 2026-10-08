# Approved implementation decisions

## D-001 — Evaluation Settings is Admin-only

Confirmed directly by the user on 2026-10-08: "Admin فقط يدير كل المراحل".

Admin alone manages monthly evaluation settings: configuration workspace/catalog access, drafting/copying, editing, validation, impact preview, approval, history administration and applying/recalculating. Do not give Performance Team drafting or preview capabilities in this release. All other roles must be denied these settings operations server-side; hiding controls alone is insufficient.

This decision replaces the plan's proposed Performance Team draft/preview capability. It does not remove ordinary scoped scorecard/performance access from any existing role. Historical results remain unchanged unless Admin explicitly confirms an apply job; approval alone does not recalculate.

Further unresolved technical/data decisions remain gated on Phase 0 evidence; no new defaults are silently activated.

## D-002 — Unsupported target/direction changes are temporarily blocked

Confirmed directly by the user on 2026-10-08: temporarily block unsupported target/direction changes, while allowing weight changes until an approved source workbook and expected results establish supported recomputation.

Enforce this restriction server-side in validation, preview, approval and apply, not only in the settings UI. Weight-only changes may reuse a validated persisted achievement and recompute its contribution under the unchanged policy/cap; they must not infer a missing achievement or silently recalculate an unsupported formula. A missing trustworthy basis remains blocked.

This decision permits schema foundation and capability-aware implementation to proceed without inventing IP Final parity. It does not approve custom formulas, historical recalculation, a new IP Final algorithm, or production activation. Accepted raw-input/formula golden results remain required before enabling those target/direction edits.

## D-003 — Workbook target conflicts block upload

Confirmed directly by the user on 2026-10-08: when an approved fixed target for the selected month differs from the workbook target, stop the upload until the difference is resolved.

Validation and commit must reject the conflict server-side, including queued ingestion. Show the Admin the affected scope, month, KPI and both values. No acknowledgement or override bypass is permitted. Preserve the original workbook evidence; do not silently overwrite it with the configured target. This policy belongs to the later ingestion phase and is not activated by schema groundwork.
