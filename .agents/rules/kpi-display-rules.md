# KPI Display & Aggregation Rules — All Teams

These rules apply across **every team, function, role, and view** in the PMS Dashboard (Monthly Review, Executive Summary, Team Dashboard, Role Detail, and Employee Scorecards).

---

## 1. Pooled Team KPI Parity (Team Cards & Trends)

- Aggregate team KPI cards must follow the **same pooled calculation engine** as each team's own Team Dashboard (`calculateAggregatedTeamPerformance` + `achievementFor` via `pooledTeamKpi.ts`).
- Never compute a team card's Achievement % by averaging individually capped (`min(ach, 100%)`) employee achievements while displaying an uncapped team Actual that exceeds target (which produces contradictory cards like `33.5% vs 30.0% Target` showing `92.5% of target`).
- Always use each team's **real KPI weights and contributions** from its team config (`useAllTeamConfigs` / `TeamConfig`), never hardcoded fallback weights like `[30, 30, 20, 20]` when real weights exist.
- For ratio-to-target volume KPIs (`aggregation.method === 'ratio'` with `score_target: 1.0`, e.g., Sales OP/IP Revenue and Census), keep the display Actual and Target in currency/count units while deriving Achievement %, Weight %, and Contribution % from pooled `sum(actual) / sum(target)`.
- For multi-person aggregates without a `TeamConfig` counter definition, derive Achievement % from `actual / target` (or `target / actual` for lower-is-better), capped to `[0, 100%]`. Single-record leader scorecards keep their stored achievement ratio.

---

## 2. Preserve Targets — Never Remove Target Context

- Keep `Target: <value>` visible in KPI table column headers and KPI cards so reviewers can always verify how `Ach %` was calculated from `Actual` vs `Target`.
- Never overwrite an individual employee's personal target with the team average target when employees have individual quotas (e.g., Sales reps).

---

## 3. Zero-Redundancy Employee KPI Table Cells

All employee/agent KPI cells across teams and roles must use the shared `KpiAchievementCell` component and follow these display rules:

1. **Primary Value:** Show `Ach %` in the colored badge directly above the smooth grade-gradient progress bar (`--pms-grad-grade-{a..e}`).
2. **Color Consistency:** Align badge tone with the progress bar (`>= 90%` or target met → emerald, `70–89.9%` → amber, `< 70%` → rose).
3. **No Redundant Subtext:**
   - **Hide** the secondary line underneath the bar whenever normalized `Actual` equals `Ach %` and the employee shares the column target (e.g., 100%-target score KPIs like ER Dr, Radiologist, and Quality & Case Management — never print `17.2%` above the bar and `17.2%` again below it).
   - **Show `Actual / Personal Target`** underneath the bar whenever the employee's normalized personal target differs from the column header target (e.g., Sales `AED 2.55M / AED 5.50M`).
   - **Show `Actual`** underneath the bar whenever `Actual` differs from `Ach %` and the target is shared in the column header (e.g., Call Center `54.1%` for `72.1%` ach vs `75.0%` target, or `3.50 min` for AHT).
4. **Full Precision on Hover:** Always include `${label}: ${ach} achievement (Actual ${actual} vs Target ${target})` in the cell `title` tooltip.
5. **Normalize Percentage Comparisons:** Compare formatted percentages after normalizing decimal precision (e.g., `100%` === `100.0%`) so formatting differences never trigger redundant subtext or false personal-target labels.
