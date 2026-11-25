# Grades and Scoring Guide

## Grade Scale and Definitions (A to E)

PMS uses a single unified 5-tier grade scale (**A** through **E**) across every team, region (Egypt and UAE), and performance level (**Employee**, **Managerial**, and **Corporate**). Thresholds are inclusive lower bounds:

- **Grade A — Excellent (95.0% to 100.0%)**: Top-tier performance; exceeds expectations across weighted KPIs.
- **Grade B — Meet Expectations (90.0% to 94.9%)**: On-target, solid performance meeting the 90% PMS benchmark.
- **Grade C — Average (80.0% to 89.9%)**: Acceptable mid-range performance, below the 90% Meet Expectations benchmark; typically needs targeted coaching on 1–2 KPI gaps to move into Grade B.
- **Grade D — Below Average (70.0% to 79.9%)**: Underperforming; flagged on the **Teams at Risk** watchlist and requires focused coaching or a structured improvement plan.
- **Grade E — Unsatisfactory (below 70.0%)**: Critical performance deficit; flagged as **Critical <70%** on **Teams at Risk** and requires immediate corrective action or PIP review.

Because thresholds are inclusive lower bounds, `80.0%` is **Grade C** while `79.9%` is **Grade D**, and `70.0%` is **Grade D** while `69.9%` is **Grade E**.

## KPI Scoring Formula and Achievement Cap

Each employee, team, or scorecard receives a weighted performance score from `0%` to `100%` based on its configured KPI targets, directions, and weights (weights total `100%`):

- **Higher-is-better KPIs** (such as Reachability, Utilization, Booking Rate, Attendance Rate, TAT Compliance, and Revenue): `achievement = min(actual / target, 100%)`.
- **Lower-is-better KPIs** (such as AHT, Abandonment Rate, Quality Errors Rate, Controllable Rejection Rate, Waiting Time, CPL, and Rework): `achievement = min(target / actual, 100%)` (meeting or beating the ceiling earns `100%`).
- **Global Achievement Cap (`100%`)**: Individual KPI achievement is capped at `100%` (`1.0`), so over-achieving one KPI cannot hide a deficit in another KPI.
- **Weighted Score**: `Overall Score = sum(KPI achievement × KPI weight)`.
- **Score Scale Rule**: Stored ratios in `(0, 1]` are multiplied by `100` (for example, `0.85` displays as `85.0%`), while values above `1` are already percentages.

## Gap vs Gap Share Explained

PMS reports two distinct gap metrics so leaders can see both **how far below 100%** a score is and **which region or team drives the biggest share of that gap**:

- **Gap (vs 100% Target)**: Simple distance from a `100%` score (`score - 100`). For example, an overall company score of `86.4%` has a `-13.6%` gap to `100%`.
- **Gap Share (% of the company gap)**: A region or team's headcount-weighted share of the total company gap: `((100 - score) × headcount) / total_weighted_gap × 100`.
- **Why Gap Share can be high (e.g. 84%) while overall gap is smaller (e.g. -13.6%)**: Gap Share is a percentage *of the total gap*, not a score drop. If UAE represents `79%` of evaluated headcount with a `-14.8%` gap, UAE accounts for roughly `84%` of the overall `-13.6%` company gap, while Egypt accounts for the remaining `16%`.
