# Monthly evaluation settings: Admin operating guide

Status: reviewed candidate guide, 9 October 2026. Coding and Outbound correction flows passed actual component/API checks with synthetic authentication and in-memory data on desktop/tablet/mobile. Actual approved Outbound upload preview, commit, full-precision provenance and resolved reads also passed integration tests. Complete application-login, production verification and wider team activation remain separate gates. This guide does not mean the feature is deployed or every team's formula is supported.

## Select the exact scope

Select source team, performance level, applicable position, year and month. Check that selection's capability message. A team appearing in the catalog is not proof that its calculation is editable. Unsupported formulas remain blocked. Admin alone manages every stage; other roles retain their authorized ordinary performance reads.

## Create a month's settings

1. Start from the selected month's source baseline, or explicitly copy the previous approved month.
2. Review destination-template changes. July-to-August Outbound introduces Productivity and the August weights; it must not silently drop that KPI.
3. Edit permitted fields and save. Weights must total 1; no silent normalization. KPI keys, formula families, achievement caps and grade bands are not free-form edits.
4. Preview the full selected scope's stored evidence. Review original workbook targets, proposed applied targets, missing evidence, affected counts, and before/after scores and grades.
5. Approve the version. Approval alone does not rewrite historical results.
6. Separately apply to existing results, or use the approved version in a subsequent admitted upload.

With no stored results, rules can be validated and approved, but no employee score impact is available. Apply remains blocked until evidence exists.

## Correct an already approved month

Choose **Revise this month**. The new draft copies that month's approved settings, not current file defaults or another month. The original approved snapshot stays immutable and traceable.

Follow **Save → Preview impact → Approve → Apply**. Apply is separate and explicit. Editing rules clears the preview; a changed upload also makes it stale. Preview again before approval/application.

The active approval and saved applied evidence are different states. A newly approved version controls subsequent admitted uploads. Existing records describe their saved basis until explicit apply. A correction cannot change other scopes/months, saved reports, plans, actions or human notes.

## Targets and source evidence

Use the KPI's stored unit. Fraction-based percentages use `0.65` for 65% and `0.8` for 80%, not `65` or `80`. Counts, durations and currency retain their own units.

- Workbook targets come from the original source.
- Fixed targets come from approved settings. A conflicting target in a **new upload** blocks the upload until resolved; no acknowledgment or override bypass exists.
- An explicit historical correction shows original and applied targets separately and preserves source evidence for subsequent revisions.
- Missing weighted actuals block correction. Never substitute zero or infer Productivity from available time or a final score.

## Audited Outbound example

| Period | Scored KPIs | Attendance weight | Productivity weight |
|---|---|---:|---:|
| July 2026 | Attendance, Booking, Quality, Other | 70% | Not scored |
| August 2026 | Attendance, Booking, Quality, Other, Productivity | 60% | 10% |

Source attendance target is 65% in **both** supplied months. The 55%→65% scenario is a synthetic correction test, not the source chronology. AHT remains zero-weight diagnostic. Unvalidated months do not inherit August's formula or Productivity.

## Safe rollback

Only the eligible latest applied revision can roll back. It restores complete prior saved evidence, whether pinned or legacy, without reactivating an old immutable approval. Changes to records, KPIs, notes, upload identity or source evidence after apply cause refusal; newer data stays untouched. Older revisions cannot undo newer ones; repeated rollback cannot repeat side effects.

Broader activation needs separate source, calculation, security and release gates. See [the implementation reference](../plans/monthly-evaluation-settings-plan.md).
