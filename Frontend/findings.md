# Frontend UI/UX Cross-Browser Findings

## Verification update
- The first four-browser layout run passed 22 of 24 cases.
- WebKit reports a 1019px document client width at a nominal 1024px viewport because the vertical scrollbar consumes five pixels; assertions must compare layout width to `documentElement.clientWidth`.
- WebKit's actionability retry can race with the Framer Motion profile-menu element and observe a detached node. Waiting for visibility and dispatching the semantic click removes the test-only race.
- With those test assumptions corrected, the WebKit layout/a11y route set passes 6/6.
- The project TypeScript gate exposed several stale-but-local contract mismatches: legacy report template IDs were absent from `ReportType`, direct report generation does not carry builder slides, weight responses support position scopes, and raw aggregate values must remain string-compatible. These were corrected without changing API calls or calculation behavior.
- WebKit full-page screenshots can change height while route data resolves even after fonts and CSS animation disabling. Requiring a stable document height for 750ms produces deterministic full-page evidence without a fixed sleep.
- Final Edge inspection confirms the 1280px shell breakpoint preserves desktop density while giving 1024px/tablet and mobile layouts the full canvas.
- Firefox exposed a separate 399px Employee comparison control at a 390px viewport; mobile-only padding and type sizing removed the 9px overflow without changing tablet/desktop density.
- Native Edge Axe identified three borderline contrast cases missed by the initial animation-timed scan. Waiting for the page entrance transition and using one-step darker semantic colors produced a clean four-browser serious/critical scan.

## Requirements
- Reproduce and correct the poor scaling, clipping, compression, and inconsistency reported in Microsoft Edge.
- Verify desktop widths 1280, 1366, 1440, 1536, and 1920; tablet widths 820 and 1024; mobile widths 390 and 412.
- Verify Chromium, native Edge when available, Firefox, and WebKit.
- Audit responsive layout, accessibility, filters, cards, tables, charts, fonts, dialogs, and browser zoom/display scaling.
- Produce baseline/final screenshots and audit/verification documents.
- Preserve product identity, routes, business behavior, and authorized data access.

## Research Findings
- The frontend is React 19.2 + TypeScript 6 + Vite 8, using React Router 7, Tailwind CSS 4, Material-free custom components, Lucide SVG icons, Framer Motion, and Recharts.
- No Playwright dependency, configuration, E2E directory, or visual-regression setup currently exists.
- The application shell reserves a fixed 272px desktop sidebar using `lg:ml-[272px]` and `lg:w-[calc(100%-272px)]`; this is a primary area to verify under Edge zoom/scaling.
- Global CSS currently forces `max-width: 100vw` and `overflow-x: hidden !important` near the document root. This can conceal layout overflow rather than prevent it and may cause clipped content.
- The shell combines a fixed 272px sidebar with both a main margin and an explicit calculated main width. In a flex container this is redundant sizing and risks overflow/compression at zoom-dependent breakpoints.
- The sticky header contains three non-shrinking groups. Its left group, centered search group, and right controls need direct mobile/zoom measurement because only the search group becomes flexible at `lg`.
- Native Edge is installed at `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`; native Edge evidence is therefore required, not a Chromium-only fallback.
- Chrome is also installed. Firefox/WebKit runtimes are not yet established.
- The global CSS removes outlines from every Recharts descendant using `!important`. This may suppress keyboard focus without providing an alternative and is an accessibility risk.
- The configured font stack starts with `Inter`, but font loading/fallback behavior still needs inspection; the requested design audit must preserve identity rather than adopt the skill's unrelated Fira recommendation.
- `index.html` loads Inter only from Google Fonts. The fallback is generic `system-ui`, so the app remains usable when blocked, but Windows metrics can change because there is no explicit Segoe UI fallback. This can alter wrapping and density in Edge on corporate devices.
- The viewport meta tag is correct.
- The mobile/tablet header still renders title, global-search trigger, month picker, notifications, theme, and profile as non-shrinking groups. This is a concrete compression risk below desktop widths.
- The backend is responding on port 8000, while the Vite frontend was not running at the start of baseline capture.
- The real Vite development server is now running at `http://127.0.0.1:5173`.
- The bundled automation runtime exposes Chromium, Firefox, and WebKit engines. Native Edge will be launched with its installed executable/channel.
- No repository-documented local admin password was found in the backend search. Baseline automation must reuse authorized local state or deterministic request fixtures without altering users or credentials.
- Important tables generally use internal `overflow-x-auto` with explicit minimum widths, which is the correct broad pattern but still needs browser verification.
- Recharts is normally wrapped in `ResponsiveContainer`; several charts use fixed pixel heights that may be reasonable but need zoom/tablet verification.
- Numerous responsive safeguards already exist (`min-w-0`, internal table scrolling), so corrections should target actual failures rather than replace the layout system.
- The repository has 53 Vitest files but no browser automation or approved visual baselines.
- The installed `accessibility-auditor` skill requested by the brief is unavailable; accessibility will be audited using repository inspection, browser semantics, and available test tooling.
- UI guidance prioritizes form labels, modal focus management, dynamic announcements, visible focus, horizontal-overflow prevention, and responsive dashboard grids.

## Technical Decisions

| Decision | Rationale |
|---|---|
| Audit before implementation | Required by the brief and prevents speculative CSS changes |
| Use directionally stable responsive primitives rather than Edge-specific CSS | Fixes root causes across engines and zoom levels |

## Issues Encountered

| Issue | Resolution |
|---|---|
| Windows console could not encode a UI skill glyph | Re-run the skill script with UTF-8 mode |
| A combined `rg` command used a Windows-invalid `README*` path and referenced a missing `docs` directory | Use explicit file discovery and create the required docs directory during audit documentation |
| The first documentation patch targeted `progress.md` at the repository parent | Reissued the patch against the Frontend project path |
| A combined background-server PowerShell command was blocked by execution policy | Started Vite directly with Node and a hidden `Start-Process`, then verified HTTP 200 |
| An accessibility `rg` expression was malformed by PowerShell quoting | Split future searches into literal patterns instead of a compound escaped expression |
| A findings patch assumed stale table context | Re-read the persistent files and reapplied against exact content |
| The E2E playbook references optional files absent from the installed skill package | Continued with the available complete implementation playbook and recorded the limitation |

## Resources
- `package.json`
- `src/App.tsx`
- `src/index.css`
- `src/components/common/Header.tsx`
- `src/components/common/Sidebar.tsx`
- `src/`
- Existing Vitest configuration; browser configuration is absent

## Visual/Browser Findings
- Native Edge 150.0.4078.83 successfully rendered the unauthenticated login page at 1366×768 with no page-level overflow and no console errors.
- The Edge login baseline is visually centered, unclipped, and uses the intended Inter font when the external font request succeeds.
- Baseline screenshot: `artifacts/ui-baseline/login-edge-1366x768-default.png`.
- Bundled Chromium, Firefox, and WebKit package APIs are present, but their downloaded browser executables are missing. System Chrome can cover Chromium baseline; Firefox and WebKit must be installed before cross-browser claims.
- Chromium 149, Firefox 151, and WebKit 26.5 browser binaries were downloaded successfully. The persistent automation package expects an older browser revision, so verification must either use explicit executable paths carefully or align the project Playwright dependency/version during Stage 3.
- Native Edge baseline reproduced the reported defect:
  - At 390×844, the header's right control group ends at x=428 while the viewport ends at x=390. Global `overflow-x: hidden !important` clips the profile/control area instead of exposing the overflow.
  - At 412×915, the same group ends at x=428 and remains partially clipped.
  - At 1024×768, the desktop sidebar breakpoint activates, consuming 272px and leaving only 752px for content. The global search collapses to an unreadable fragment and the page heading/filter layout becomes unnecessarily compressed.
- Native Edge desktop widths 1280, 1366, 1440, 1536, and 1920 had matching document/client widths in the empty-dashboard state. The reported poor corporate-laptop presentation is most severe at the 1024 breakpoint and mobile header widths.
- Effective-width simulations for 1366px browser zoom:
  - 110% (~1242 CSS px) remained structurally valid.
  - 125% (~1093 CSS px) retained the 272px desktop sidebar and compressed content to 821px, confirming a breakpoint/available-width problem even without page-level overflow.
- The shell's desktop width formula itself resolved to the correct right edge in measured Edge layouts; the more direct root cause is the sidebar/header breakpoint strategy plus overflow clipping, not a double-width overflow in the measured state.
- Baseline screenshots now cover all requested viewport sizes and Edge zoom-equivalent effective widths under `artifacts/ui-baseline/`.
- Chromium 149, Firefox 151, WebKit 26, and native Edge all measured the same mobile defect at 390×844: the header control group ends at approximately 428px and is clipped.
- Employee and team empty-state pages inherit the same clipped header; their page content itself remains within the mobile viewport.
- The team empty state keeps filters and the primary Export action visible at 390px, but the global header loses the user/profile control.
- Several accessibility defects are visible from source inspection:
  - Executive filter selects have no associated visible label or accessible name.
  - The Insights table makes an entire `<tr>` clickable without keyboard semantics; only the nested eye button is keyboard-operable.
  - Global Recharts outline suppression can remove focus indication.
  - Multiple dialogs use correct `role="dialog"`/`aria-modal`, but focus trapping and focus return are not consistently implemented.
- A dynamic Tailwind class (`xl:grid-cols-${...}`) is constructed at runtime in `TeamKpiSection`; Tailwind cannot reliably statically generate this class, creating inconsistent KPI grid density.
- Key routes captured with generic deterministic empty responses:
  - Executive, employee, and generic team routes render stable empty states.
  - Insights and Marketing require structured fixture objects; their error-boundary screenshots reflect invalid audit fixtures, not a proven product defect, and must not be classified as application failures.
- Post-correction native Edge geometry:
  - 390×844: document/client width 390; rightmost header content x=378.
  - 412×915: document/client width 412; rightmost header content x=400.
  - 1024×768: sidebar is off-canvas and main/header use the full 1024px.
  - 1093px effective width: sidebar is off-canvas and header controls fit.
  - 1280×720: persistent desktop sidebar activates as intended and document width remains stable.
- Stage 3 tooling now includes project-aligned Playwright Test and Axe Playwright dependencies.
- Project-matched Chromium, Firefox, and WebKit browser binaries installed successfully.
- Existing Vitest fixtures provide deterministic Marketing records and a complete Insights workspace shape suitable for non-destructive browser fixtures.
