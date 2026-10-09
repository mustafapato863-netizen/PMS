# Outbound period basis contract

This is the hook for a later month-template catalog. It does not edit the catalog, workflow, resolver, or `Backend/config/teams/outbound.json`.

## Call

```python
from services.outbound_period_basis import (
    assess_monthly_actuals,
    canonical_outbound_basis,
    period_capability,
)

basis = canonical_outbound_basis(year, month)
decision = period_capability(year, month)
evidence = assess_monthly_actuals(year, month, actuals_by_kpi_key)
```

`year` is an integer. `month` is a month number or a month name. `actuals_by_kpi_key` uses the stable keys below.

## Decision

`decision["lines"]` is the only canonical scored set for that period. Each line has `kpi_key`, `weight_key`, `label`, `weight`, `direction`, `unit`, `target`, and `target_mode`.

| Period | `status` | Scored lines | `approved_binding` | `catalog_template_supported` |
| --- | --- | --- | --- | --- |
| June 2026 | `june_2026_exception` | Attendance 0.70, Booking 0.10, Quality 0.00, Other 0.20 | `apply` | false |
| July 2026 | `july_2026` | Attendance 0.70, Booking 0.10, Quality 0.10, Other 0.10 | `apply` | true |
| August 2026 | `august_2026` | Booking 0.10, Attendance 0.60, Other 0.10, Quality 0.10, Productivity 0.10 | `apply` | true |
| September 2026 and later | `unconfigured` | Technical four-KPI lines. August weights are not copied. | `refuse` | false |
| Earlier months | `technical_baseline` | Technical four-KPI lines from the calculation defaults | `apply` | false |

`decision["infer_from_august"]` and `decision["silent_fallback"]` are always false. `decision["productivity_key"]` is `Productivity`. Reachability stays on `Other`. AHT stays `{weight: 0, enabled: false, scored: false}`.

`approved_binding: refuse` means an approved snapshot for that period must not be scored and must not fall back to the workbook total. July and August snapshots whose scored keys differ from `decision["scored_keys"]` are refused the same way. A matching snapshot still goes through the existing pin, so a fixed target that differs from the workbook target raises `TargetConflict` with no bypass.

## Evidence

`evidence["sufficient"]` is false when a scored actual on the requested basis is missing. For August 2026 that includes a missing `Productivity` actual: `accepted_as_five_kpi_monthly_evidence` is false and the disposition is `fail_visible_missing_source_actual`. Callers do not zero-fill, drop the KPI, renormalize the other weights, or derive Productivity from available time or a stored trend score. `historical_score_readable` stays true for a legacy row that has no Productivity actual.

Source attendance target on the July and August lines is 0.65. The 0.55 July / 0.65 August pair is a synthetic acceptance scenario in the anonymous golden fixture, not this basis.

## Upload hook

Dry-run and commit both call `services.seeding_service.pin_upload_score(version, evidence)`. That function calls `services.evaluation.resolver.score_basis` and does not catch its errors. A reusable approved-capability guard belongs in `score_basis` so preview and this hook share it. This branch does not add that resolver function.

`DatabaseSeeder.process_uploaded_file(..., db_session=None)` opens `SessionLocal` when no session is injected. An injected session is used for the collision lookup and the pin, rolled back on dry-run, committed on success, and left open. Operational database errors are not swallowed.
