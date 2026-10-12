# Admin panel redesign — plan

Owner of this plan: orchestrator session. Implementation: separate session, one phase per PR.
Scope: `/settings` ("Settings & Administration") only. No backend behaviour, permission, scoring or data change unless a phase says so explicitly.

## 1. What is wrong today (observed in code and in the live screen)

1. **One route, local state.** `/settings` keeps the active section in `useState`. Refresh always returns to Data Management, the back button does not move between sections, and no section or month can be linked.
2. **No overview.** The page opens straight into the upload panel. An Admin cannot see at a glance what needs attention (failed uploads, drafts waiting for approval, recent server errors, accounts needing action).
3. **Flat navigation.** Five unrelated items in one list with no grouping. `SettingsSection` also contains `teams` and `SettingsView` renders `TeamManagementView` for it, but the navigation has no entry, so it is unreachable.
4. **Every panel builds its own chrome.** Header, toolbar, notices, empty/loading/error states are hand-written per panel with different spacing and wording.
5. **Evaluation settings is hard to operate.**
   - Six action buttons of equal weight in one row; the required order (Save -> Impact preview -> Approve -> Apply) is only a sentence above them. This is the direct cause of "I edited the draft and nothing was applied".
   - Each KPI is a large fieldset; the same two help sentences repeat under every target and weight input; the note line repeats the same diagnostic several times.
   - Labels and help text use 10px type. Project rule: never below 12px.
   - History is one raw line with a 64-character checksum.
   - The component is ~1050 lines in one file.
6. **Tables** (users, upload history, system errors) do not share search / sort / pagination / sticky header / row-action conventions.

## 2. Design direction

Reference feel per project rules: Linear / Stripe Dashboard / Vercel settings. Clarity over decoration, data first, progressive disclosure, one primary action per view.

Every admin screen answers, top to bottom: **what is the state -> why it matters -> what to do next.**

### 2.1 Admin shell
- URL-addressable sections: `/settings/:section`, `/settings` redirects to `/settings/overview`. Unknown section -> overview. Evaluation settings keeps its existing `year`/`month` query handling.
- Grouped navigation (left rail on xl, horizontal scrollable tab list below xl, both keyboard reachable with `aria-current`):
  - **Overview**
  - **Data** — Data uploads, Corrective action backup
  - **Evaluation** — Evaluation settings
  - **Access** — Users
  - **System** — System errors
- Shared primitives in `Frontend/src/components/settings/shell/`:
  - `AdminPageHeader` — title, one-line purpose, optional status badge, optional primary-action slot.
  - `AdminSection` — titled content surface (one elevation level, token borders, no nested glass panels).
  - `AdminNotice` — info / success / warning / error with consistent role and icon.
  - Loading, empty and error states reuse `SkeletonLoader` and `NoDataEmptyState` from `components/common`.
- The large hero banner shrinks to a compact page header so content starts above the fold.

### 2.2 Overview page
Four status cards, each: current state, one supporting fact, status colour by project semantics (green good / amber warning / red attention / blue info), and one named action that navigates to the section.
- **Data** — last upload: when, by whom, status, record count.
- **Evaluation** — link card in phase 2 (see 4, open point B).
- **Access** — user counts by role / inactive.
- **System** — server errors in the recent window, most recent one.
Below: "Needs attention" list (only items that require action; empty state when none).

### 2.3 Evaluation settings
- **Context bar**: level, scope, month, year in one compact row with a status badge for the selected month: No version / Draft / Draft with unsaved edits / Approved, not applied / Applied.
- **Stepper**: 1 Edit and save -> 2 Preview impact -> 3 Approve -> 4 Apply. The current step is highlighted, completed steps are checked, and the reason a step is locked is shown next to it. Exactly one primary button: the next valid step. Secondary actions (New draft, Copy previous month, Revise this month, Delete draft) move to a secondary group; destructive ones keep confirmation.
- **KPI editor as a compact grid**: one row per KPI — name, included/tracking toggle, target (+unit), weight, direction, source. Column-header help replaces the per-row repeated sentences; "saved value" appears only on rows that differ from saved. Sticky footer row with total weight and its validity. Below `md` each row becomes a stacked card.
- **Notes** de-duplicated. **Impact proof** keeps its tables, inside an `AdminSection`.
- **History** as a short timeline: version, status, date, actor, 8-character checksum with copy-full.
- File split into subcomponents (context bar, stepper, KPI grid, impact proof, history). **No logic change**: same mutations, same gates, same request payloads, same `aria-label`s on inputs and buttons that existing tests query.

### 2.4 Tables
Users, upload history and system errors share one pattern: search, sortable headers, pagination, sticky header, row actions in a trailing column, badges for status, and the standard loading / empty / error states.

## 3. Non-negotiable rules for every phase
- Existing design tokens and classes only (`var(--…)`, `glass-panel`, existing status/grade classes). No new dependencies, no new colour hexes, no new fonts.
- No text below 12px. Titles 24–32, section 18–20, body 14–16.
- 4px/8px spacing grid. No overflow or clipped content at 390, 768, 1024 and 1440 px. Light and dark themes.
- Keyboard navigation, visible focus, correct roles/labels, 44px touch targets on small screens, motion 150–300ms and respect reduced motion.
- Destructive actions keep confirmation. Buttons name their intent.
- Admin-only gate (`canAccessSettingsContent`) stays exactly as it is, including the soft-lock panel for other roles.
- No backend change unless the phase says so. No change to what any existing action sends or when it is enabled.
- Existing tests are not loosened or skipped. Tests that pin the old layout structure may be updated only where the phase names them.

## 4. Phases (one PR each, in this order)

**Phase 1 — Shell and navigation.** Routes, grouped navigation, shell primitives, compact page header, each existing panel wrapped in the new header without touching its internals. Overview route exists with the four cards as navigation cards only (no data yet).
**Phase 2 — Overview data.** Cards and "Needs attention" from endpoints that already exist (uploads, users, system errors).
**Phase 3 — Evaluation settings.** Context bar, status badge, stepper, KPI grid, history, file split. Behaviour frozen.
**Phase 4 — Tables.** Shared table pattern applied to users, upload history, system errors.

## 5. Open points for the product owner
A. **Teams section**: present in code, absent from navigation. This plan leaves it hidden. Say if it should return under Access.
B. **Evaluation card on Overview**: "months in draft / approved but not applied" across all scopes has no endpoint today (periods are read one scope at a time; there are 31 Employee scopes). Showing real numbers needs one small read-only summary endpoint. Until approved, the card is a navigation card.
