# Pages Enhancement Pass

## Scope
Enhanced the uploaded page set without changing API/business logic or test-facing copy.

## Main UI improvements
- Unified page shell spacing and maximum content width.
- Premium light-mode page hero/header treatment.
- Stronger filter and toolbar surfaces.
- Improved KPI/stat cards and corrective-action cards.
- Cleaner report history table and sticky table headers.
- Improved report builder shell and report preview canvas.
- Better Team Management toolbar, empty state, and delete modal.
- Improved Settings, Executive, Employee Profile, Insights, Planning, Marketing, and Team Dashboard page framing.
- Refined login and 404 presentation.
- Better responsive behavior on smaller screens.
- Stronger focus-visible states and form focus feedback.

## Performance improvements
- Removed continuous decorative animation from the 404 page.
- Reduced unnecessary glass/blur styling in page-level surfaces.
- Added CSS containment to repeated KPI/action cards.
- Added reduced-motion support.
- Added optional content-visibility utility for future heavy off-screen sections.
- Kept existing application logic and data flows unchanged.

## Dependencies
No new dependency is required by this page pass.
The source already uses Lucide and Framer Motion, so the enhancement reuses the existing stack.

## New file
- `PageEnhancements.css`

Every production page imports this stylesheet so the page-level visual system stays consistent.
