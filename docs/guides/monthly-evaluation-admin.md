# Monthly evaluation settings: Admin operating guide

Status: reviewed candidate guide, 10 October 2026. Coding and Outbound correction flows passed actual component/API checks with synthetic authentication and in-memory data on desktop/tablet/mobile. Actual approved Outbound upload preview, commit, full-precision provenance and resolved reads also passed integration tests. The rules editor now accepts percentages for explicit percent targets and for every weight; the API still stores those values as fractions. Complete application-login, production verification and wider team activation remain separate gates. This guide does not mean the feature is deployed, that Phase 6 is complete, or that every team's formula is supported.

## Select the exact scope

Select source team, performance level, applicable position, year and month. Check that selection's capability message. A team appearing in the catalog is not proof that its calculation is editable. Unsupported formulas remain blocked. Admin alone manages every stage; other roles retain their authorized ordinary performance reads.

## Create a month's settings

1. Start from the selected month's source baseline, or explicitly copy the previous approved month.
2. Review destination-template changes. July-to-August Outbound introduces Productivity and the August weights; it must not silently drop that KPI.
3. Edit permitted fields and save. Enter weights as percentages that total 100% for a complete scorecard. The saved payload still stores fractions that total 1, with no silent normalization. KPI keys, formula families, achievement caps and grade bands are not free-form edits. The save sends the rules checksum captured when editing began, with that same version and the selected scope, year, and month.
4. Preview the full selected scope's stored evidence. Review original workbook targets, proposed applied targets, missing evidence, affected counts, and before/after scores and grades.
5. Approve the version. Approval alone does not rewrite historical results.
6. Separately apply to existing results, or use the approved version in a subsequent admitted upload.

With no stored results, rules can be validated and approved, but no employee score impact is available. Apply remains blocked until evidence exists.

## Correct an already approved month

Choose **Revise this month**. The new draft copies that month's approved settings, not current file defaults or another month. The original approved snapshot stays immutable and traceable.

Follow **Save → Preview impact → Approve → Apply**. Apply is separate and explicit. Editing rules clears the preview; a changed upload also makes it stale. Preview again before approval/application.

The active approval and saved applied evidence are different states. A newly approved version controls subsequent admitted uploads. Existing records describe their saved basis until explicit apply. A correction cannot change other scopes/months, saved reports, plans, actions or human notes.

## When two admins edit one draft

Starting an edit keeps the rules checksum, version, and the line units from that moment. A later refresh does not retarget those unsaved numbers onto a new unit or a new checksum. Save sends that captured checksum to that captured version. It does not switch the write onto a version that appeared in the background.

If the draft changed after it was opened, the save is refused and nothing is written. The screen keeps the unsaved text and offers **Reload draft** or **Discard edits**. It does not overwrite the newer draft and it does not retry the save. Reload loads the current draft and drops the captured checksum. Discard drops the unsaved text and the captured checksum. Changing scope, year, or month, or a successful save, does the same. A checksum from one scope, month, or version is not sent for another.

If the draft has no rules checksum, **Save draft** stays unavailable. The screen explains that, and it does not send an empty checksum.

The browser edit requires a persisted active Admin and the captured checksum. A role label in the request is not enough. Internal workflow calls that are not this HTTP edit can still update a draft without a browser checksum; when those calls do supply a checksum, it is checked. A missing checksum on the HTTP edit is refused after the Admin check and does not change the draft.

## Targets and source evidence

Type percentages for a KPI whose rule unit is `%`, `percent`, or `percentage`. The field shows `65` for a stored target of `0.65`, and saving `70` stores `0.7`. The same scale is used for every weight: the field shows `60` for a stored weight of `0.6`, and saving `50` stores `0.5`. Zero remains a valid diagnostic weight. A finite number is saved without clamping or rounding. Only those explicit percent targets, and every weight, move between the 0–100 entry scale and the 0–1 stored scale.

Hours, minutes, counts, and currency stay on the unit printed beside the field. A target of `2.5` hours is stored as `2.5`. A count of `65` is stored as `65`. If the rule has no unit, the field is marked as stored as entered and the number is not treated as a percent. The KPI name is not used to guess the unit.

A blank box or an unfinished value such as `0.` is not saved as zero and does not replace the stored number. The saved value stays visible next to the field. Saving is blocked until every edited number is finite. Changing the reporting period discards unsaved typing. Approved rules and unsupported formulas stay locked. There is no automatic save, approval, or apply.

Impact mismatches use that KPI's rule unit when the rule is on screen. A mismatch whose rule has no explicit unit stays on the stored scale.

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
