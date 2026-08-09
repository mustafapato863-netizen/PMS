# Frontend UI/UX and Cross-Browser Audit

Date: 2026-07-29
Application: PMS Dashboard frontend
Framework: React 19.2, TypeScript 6, Vite 8, React Router 7, Tailwind CSS 4
UI libraries: custom components, Lucide icons, Framer Motion, Recharts

## Scope and Method

This audit preserves the existing product identity, page structure, routes, terminology, permissions, API contracts, and business behavior. No implementation code was changed before completing this audit.

The real Vite development server was run at `http://127.0.0.1:5173`. Native Microsoft Edge and the Chromium, Firefox, and WebKit engines were exercised with deterministic, browser-local authentication and non-destructive API fixtures. The fixture session does not modify users, permissions, backend data, or the database.

Stage 1 skills:

- `planning-with-files`
- `ui-ux-pro-max`
- `accessibility-auditor` was requested but is not installed; semantic source inspection and browser measurements were used instead.

## Affected Pages

The primary defect is in the shared application shell and therefore affects every authenticated page:

- Executive dashboard
- Team dashboards
- Marketing dashboard
- Employee profile
- Insights
- Planning
- Reports
- Settings

The Executive, employee, and generic team empty states were captured directly. Insights and Marketing require structured API fixtures; generic array responses correctly reached the error boundary but are not classified as application defects.

## Reproduced Defects

### 1. Mobile header clipping

At 390×844 in native Edge, the header control group ends at approximately x=428 while the viewport ends at x=390. The document reports no horizontal overflow because the root stylesheet forces `overflow-x: hidden !important`. The profile control is therefore clipped rather than reflowed.

The same measurement occurs in:

- Native Edge 150.0.4078.83
- Chromium 149.0.7827.55
- Firefox 151.0
- WebKit 26

The defect is also visible at 412×915.

### 2. Incorrect tablet/corporate-laptop breakpoint

At 1024×768, the `lg` desktop sidebar activates and consumes 272px, leaving only 752px for the page. The sticky header still renders desktop search and controls. Results:

- global search collapses to a tiny unreadable fragment;
- headings wrap earlier than necessary;
- filter groups become visually compressed;
- the sidebar occupies disproportionate space for a tablet or scaled corporate display.

At a 1366px display with an effective 125% zoom width of approximately 1093 CSS pixels, the same desktop sidebar remains active and reduces content width to 821px.

### 3. Hidden layout overflow

`src/index.css` applies:

```css
html, body, #root {
  max-width: 100vw;
  overflow-x: hidden !important;
}
```

This masks root-cause overflow and clips controls, menus, or focus indication. It prevents reliable page-level overflow detection.

### 4. Font fallback variability

Inter is loaded only from Google Fonts. If corporate policy blocks the CDN, the stack falls directly to generic `system-ui`. On Windows/Edge this normally resolves to Segoe UI, but the implicit fallback makes metric changes less predictable. Explicit Windows and general fallback faces are needed.

### 5. Dynamic Tailwind grid class

`TeamKpiSection` constructs `xl:grid-cols-${...}` at runtime. Tailwind cannot reliably discover arbitrary runtime class strings, so the expected KPI column count may not exist in the generated CSS.

## Browser-Specific Findings

- Native Edge reproduces the shared header and breakpoint defects; no Edge-only rendering hack is required.
- Edge desktop widths 1280, 1366, 1440, 1536, and 1920 have matching document/client widths in the empty-dashboard state.
- The defects are engine-independent and originate in shared responsive CSS and component sizing.
- Native Edge is available, so final evidence must use Edge rather than a Chromium fallback.

## Responsive Findings

| Viewport/effective width | Baseline result |
|---|---|
| 1920×1080 | Stable empty dashboard shell |
| 1536×864 | Stable empty dashboard shell |
| 1440×900 | Stable empty dashboard shell |
| 1366×768 | Stable shell; header search text is dense |
| 1280×720 | Stable but space-constrained desktop shell |
| 1024×768 | Fail: desktop sidebar and header compress content |
| 820×1180 | Sidebar correctly becomes off-canvas |
| 412×915 | Fail: right side of header is clipped |
| 390×844 | Fail: right side of header/profile is clipped |
| 1366 at simulated 110% | Structurally stable |
| 1366 at simulated 125% | Fail: sidebar strategy compresses content to 821px |
| 1366 at simulated 90%/80% | Stable |

Zoom simulation uses equivalent CSS viewport dimensions; it does not claim native browser UI zoom automation.

## Visual Hierarchy and Density

- The existing data-dense design language is appropriate and should be preserved.
- Desktop cards and grids already use responsive one/two/four-column patterns in most pages.
- The 1024px shell breakpoint, rather than card design, is the main density failure.
- Mobile page filters generally wrap deliberately, but the shared header competes with them by retaining a redundant global month control.

## Accessibility Findings

1. Executive region, branch, and month selects lack associated labels or accessible names.
2. The Insights analysis table uses clickable rows without keyboard row activation semantics. The nested action button remains operable.
3. Recharts focus outlines are globally suppressed with `!important` and no visible alternative.
4. Focus-visible styles exist in several navigation components but are not consistently applied to every icon button.
5. Dialogs generally use `role="dialog"` and `aria-modal`; focus trapping and focus return are not consistently evident.
6. Dynamic status components often use text plus color, which is good; this pattern must be preserved.
7. Small mobile header buttons are mostly 40px, below the preferred 44px touch target.

## Filter Bar and Page Header Findings

- Executive filters wrap correctly at mobile sizes.
- At 1024px, the sidebar leaves insufficient width and makes the filter/header composition look broken.
- The shared header uses three non-shrinking groups.
- The global month selector duplicates page-level filters on mobile and is the most practical low-risk control to hide below the small breakpoint.
- The mobile profile control is clipped and must remain reachable.

## Cards and Dashboard Density

- KPI cards generally use responsive grids and do not need redesign.
- Card minimum sizes should be validated after shell correction.
- `PerformanceKpiCard` uses very small supporting text; changing metric meaning or approved color semantics is out of scope.
- Runtime Tailwind grid construction can cause uneven team KPI grids and should be replaced with static class mapping.

## Tables and Long Content

- Important tables usually use an internal `overflow-x-auto` wrapper and an explicit table minimum width.
- This is the correct containment strategy and should remain.
- No evidence supports hiding business columns.
- Final E2E checks must assert that wide tables scroll internally without increasing document width.

## Charts and Visualisations

- Recharts is normally rendered through `ResponsiveContainer`.
- Fixed chart heights are used, but widths are responsive.
- No canvas chart code was found; device-pixel-ratio canvas correction is not applicable.
- The global removal of focus outlines is an accessibility defect.
- Final browser tests must verify non-zero chart containers and no page overflow after sidebar/header changes.

## Font and Icon Reliability

- Google Fonts is the only Inter source.
- Add an explicit fallback stack including Segoe UI and Arial without changing the primary typeface.
- Lucide SVG icons are consistently used; icon layout does not depend on icon fonts.

## Probable Root Causes

1. Desktop sidebar and desktop header activate too early at the `lg`/1024px breakpoint.
2. Header groups refuse to shrink or selectively hide lower-priority controls on mobile.
3. Root-level `overflow-x: hidden !important` conceals the overflow produced by the header.
4. External-only Inter loading allows Windows font metric changes when blocked.
5. Runtime-generated Tailwind grid classes can be missing from the compiled stylesheet.

## Files Requiring Modification and Risk

| File | Planned correction | Risk |
|---|---|---|
| `src/App.tsx` | Move persistent sidebar/main offset from `lg` to `xl`; simplify main sizing | Medium: shared shell |
| `src/components/common/Sidebar.tsx` | Align off-canvas breakpoint with the shell | Medium: all authenticated routes |
| `src/components/common/Header.tsx` | Align menu breakpoint; hide redundant mobile month control; allow safe shrinking | Medium: all authenticated routes |
| `src/index.css` | Remove forced root overflow masking; improve font fallback and focus-visible chart treatment | Medium: global styles |
| `src/pages/ExecutiveView.tsx` | Add accessible names to filters | Low |
| `src/components/team/TeamKpiSection.tsx` | Replace runtime grid class with static mapping | Low |
| Playwright configuration/tests | Add deterministic browser and visual regression checks | Low: test-only |

## Baseline Evidence

Baseline screenshots are stored under `artifacts/ui-baseline/`.

Representative files:

- `executive-edge-390x844-empty.png`
- `executive-edge-1024x768-empty.png`
- `executive-edge-1366x768-empty.png`
- `executive-edge-1536x864-empty.png`
- `executive-edge-1920x1080-empty.png`
- `executive-chromium-390x844-empty.png`
- `executive-firefox-390x844-empty.png`
- `executive-webkit-390x844-empty.png`
- `employee-SGHD70149-edge-390x844-baseline.png`
- `team-inbound-edge-390x844-baseline.png`

## Audit Boundary

This document completes the audit and baseline stage. It does not claim that corrections or final verification have been completed.
