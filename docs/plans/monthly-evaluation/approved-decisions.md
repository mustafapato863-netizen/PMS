# Approved implementation decisions

## D-001 — Evaluation Settings is Admin-only

Confirmed directly by the user on 2026-10-08: "Admin فقط يدير كل المراحل".

Admin alone manages monthly evaluation settings: configuration workspace/catalog access, drafting/copying, editing, validation, impact preview, approval, history administration and applying/recalculating. Do not give Performance Team drafting or preview capabilities in this release. All other roles must be denied these settings operations server-side; hiding controls alone is insufficient.

This decision replaces the plan's proposed Performance Team draft/preview capability. It does not remove ordinary scoped scorecard/performance access from any existing role. Historical results remain unchanged unless Admin explicitly confirms an apply job; approval alone does not recalculate.

Further unresolved technical/data decisions remain gated on Phase 0 evidence; no new defaults are silently activated.
