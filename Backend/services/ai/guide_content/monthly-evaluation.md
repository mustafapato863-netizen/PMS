# Monthly Evaluation Settings (Admin)

## Monthly Evaluation Settings Workflow

Admins manage monthly KPI targets and weights through the four-stage **Save → Preview → Approve → Apply** workflow in **Settings** (`/settings`):

1. **Select the exact scope**: choose the source team, performance level, applicable position, year, and month, and confirm the scope's formula is editable.
2. **Save**: start from the month's baseline or copy the previous approved month, edit permitted targets and weights (weights enter as percentages totaling `100%`), and click **Save** to store the draft with its captured checksum.
3. **Preview**: run **Preview** against stored evidence for that scope and month to inspect original vs proposed targets, missing evidence, affected employee counts, and before/after scores and grades.
4. **Approve**: click **Approve** to lock the immutable version. Approval governs subsequent admitted uploads and does not rewrite historical results on its own.
5. **Apply**: explicitly run **Apply** to update existing stored results using the approved version. Editing a draft clears any prior preview so you must preview again before approval or application.

To correct an already approved month, choose **Revise this month** to create a new draft from that month's approved settings. Only the eligible latest applied revision can be safely rolled back.
