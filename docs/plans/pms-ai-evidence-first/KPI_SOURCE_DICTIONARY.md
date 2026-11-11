# Phase 2: KPI & Metric Source Dictionary

**Document Version:** 1.1
**Date:** 11 November 2026
**Status:** Metric Definitions & Provenance Verified — reconciled to repository sources in Phase 2 (issue #94)
**Scope:** Phase 2 Deliverable for PMS AI Evidence-First Upgrade ([Implementation Plan](file:///D:/Projects/PMS_Dashboard/docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md))

---

## 1. Core Principles: Metric Types & Measurement Boundaries

The PMS AI system enforces strict mathematical and operational boundaries across all metrics:

### 1.1 Count vs Rate Distinction
A major source of historical query confusion was conflating operational counts with conversion percentages:
- **Rate KPIs (%)**: Normalized percentages representing efficiency or compliance (e.g. `Booking Rate = Bookings / Offered Calls`). Rates are compared against percentage targets (e.g. 65.0%).
- **Volume Counts (Integer)**: Absolute operational counts (e.g. 180 clinic bookings, 1,420 handled calls). Counts must **never** be formatted with a `%` sign or substituted for conversion rates in branch comparisons.

### 1.2 Scored KPIs vs Tracking-Only Indicators
- **Scored KPIs**: Configured with a positive weight (`weight > 0.0`) in `team_kpi_config`. The sum of weights equals 100% (1.0). Every scored KPI directly influences the employee's composite performance score and grade.
- **Tracking-Only Indicators**: Configured with `weight = 0.0` or registered in `tracking_indicators`. They provide operational diagnostic context (e.g. handle time, dropped calls, adherence) but **must never contribute to the performance score**.

---

## 2. Call Center Metric Catalog (Offshore Egypt)

Keys, weights, directions, and units below are the team-JSON template keys (`Backend/config/teams/inbound.json`, `outbound.json`). Targets are the code defaults in `Backend/services/kpi_service.py` (`DEFAULT_TARGETS`); the team JSONs carry no target values. Inbound and Outbound have different template keys, so each team has its own table. Record-payload volumes (abandoned-call counts, handled-call counts, branch booking counts) are not team-JSON KPIs; see section 4.

### Inbound — template KPIs (`inbound.json`)

| KPI Key | Canonical Display Name | Metric Type | Unit | Polarity (Direction) | Default Target | Scored vs Tracking | Source Field / Storage Key |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **`Attendance`** | Attendance Rate | Rate | `%` | `higher_better` | 75.0% | **Scored** (Weight: 70%) | `kpi_values.actual_value`<br>Workbook: `Attendance %` |
| **`Booking`** | Booking Rate | Rate | `%` | `higher_better` | 45.0% | **Scored** (Weight: 10%) | `kpi_values.actual_value`<br>Workbook: `Booking %` |
| **`Quality`** | Quality Score | Rate | `%` | `higher_better` | 95.0% | **Scored** (Weight: 5%) | `kpi_values.actual_value`<br>Workbook: `Quality %` |
| **`AHT`** | Average Handle Time (AHT) | Duration | `min` | `lower_better` | 150 seconds (2.50 min) | **Scored** (Weight: 5%) | `record_payload['calls']['aht']`<br>Workbook: `AHT` |
| **`Other`** | Abandon Rate | Rate | `%` | `lower_better` | 1.0% | **Scored** (Weight: 10%) | `kpi_values.actual_value`<br>Workbook: `Abandoned` |

Inbound AHT is scored at weight 0.05. It is not a tracking-only indicator. The `Other` slot in Inbound is the Abandon Rate.

### Outbound — template KPIs (`outbound.json`)

| KPI Key | Canonical Display Name | Metric Type | Unit | Polarity (Direction) | Default Target | Scored vs Tracking | Source Field / Storage Key |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **`Attendance`** | Attendance Rate | Rate | `%` | `higher_better` | 55.0% | **Scored** (Weight: 70%) | `kpi_values.actual_value`<br>Workbook: `Attendance %` |
| **`Booking`** | Booking Rate | Rate | `%` | `higher_better` | 46.0% | **Scored** (Weight: 10%) | `kpi_values.actual_value`<br>Workbook: `Booking %` |
| **`Quality`** | Quality Score | Rate | `%` | `higher_better` | 95.0% | **Scored** (Weight: 10%) | `kpi_values.actual_value`<br>Workbook: `Quality %` |
| **`Other`** | Reachability | Rate | `%` | `higher_better` | 75.0% | **Scored** (Weight: 10%) | `kpi_values.actual_value`<br>Workbook: `Reachability` |

Outbound has no AHT KPI in its team JSON. AHT in Outbound is a tracking-only measure at weight 0 (`Backend/services/outbound_period_basis.py`). The `Other` slot in Outbound is Reachability, not Abandon Rate.
## 3. RCM Metric Catalog (Revenue Cycle Management)

### 3.1 Egypt RCM Metrics (`Coding EGY`, `Submission EGY`, `Resubmission`)

Egypt RCM KPIs live under Employee positions in the team JSONs, not under top-level team keys, and each team has its own key set. No numeric targets are recorded for these keys in the team JSONs or in `kpi_service.DEFAULT_TARGETS`; do not invent targets for them.

### Coding EGY — position KPIs (`coding_egy.json`, position `RCM -SHJ- OP CODING`)

| KPI Key | Display Name | Unit | Direction | Target | Weight | Status | Source Location |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`egy_coding_quality_errors`** | Quality Errors Rate | `%` | `lower_better` | — (not in team JSON or code defaults) | 50% | Scored | `kpi_values`<br>Workbook: `Quality Errors Rate` |
| **`egy_coding_rejection`** | Rejection Rate | `%` | `lower_better` | — (not in team JSON or code defaults) | 0% | Tracking | `kpi_values`<br>Workbook: `Rejection Rate` |
| **`egy_coding_tat`** | TAT | `%` | `higher_better` | — (not in team JSON or code defaults) | 50% | Scored | `kpi_values`<br>Workbook: `TAT` |

### Submission EGY — position KPIs (`submission_egy.json`, position `Claim & Audit Specialist`)

| KPI Key | Display Name | Unit | Direction | Target | Weight | Status | Source Location |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`egy_submission_initial_rejection`** | Initial Rejection % | `%` | `lower_better` | — (not in team JSON or code defaults) | 60% | Scored | `kpi_values`<br>Workbook: `Initial Rejection %` |
| **`egy_submission_due_date`** | % of Submission Within Due date | `%` | `higher_better` | — (not in team JSON or code defaults) | 40% | Scored | `kpi_values`<br>Workbook: `% of Submission Within Due date` |

### Resubmission — position KPIs (`resubmission.json`, position `Resubmission Analyst`)

| KPI Key | Display Name | Unit | Direction | Target | Weight | Status | Source Location |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`egy_resubmission_quality_errors`** | Quality Errors Rate | `%` | `lower_better` | — (not in team JSON or code defaults) | 50% | Scored | `kpi_values`<br>Workbook: `Quality Errors Rate` |
| **`egy_resubmission_rejection`** | Rejection Rate After Re-Submission | `%` | `lower_better` | — (not in team JSON or code defaults) | 0% | Tracking | `kpi_values`<br>Workbook: `Rejection Rate After Re-Submission` |
| **`egy_resubmission_tat`** | TAT | `%` | `higher_better` | — (not in team JSON or code defaults) | 50% | Scored | `kpi_values`<br>Workbook: `TAT` |
### 3.2 UAE RCM Metrics (`Coding`, `Submission`, `Re-Submission`, `Pre-Approvals`)

UAE RCM employs onshore hospital KPIs, separate weight distributions, and insurer-specific denial metrics. Each team has its own key set; there is no shared UAE RCM key set. Targets below are the code defaults in `kpi_service.DEFAULT_TARGETS` where one exists for the team; otherwise no target is recorded in the team JSON or the code defaults.

### Coding — template KPIs (`coding.json`)

| KPI Key | Display Name | Unit | Direction | Target | Weight | Status | Source Location |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`QualityErrors`** | Quality Errors | `%` | `lower_better` | 5.0% | 20% | Scored | `kpi_values`<br>Workbook: `Quality Errors` |
| **`Rejection`** | Rejection | `%` | `lower_better` | 4.0% | 50% | Scored | `kpi_values`<br>Workbook: `Rejection` |
| **`TAT`** | Turnaround Time | `hours` | `lower_better` | 2.5 hours | 30% | Scored | `kpi_values`<br>Workbook: `TAT` |

### Submission — template KPIs (`submission.json`)

| KPI Key | Display Name | Unit | Direction | Target | Weight | Status | Source Location |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`initial_rejection_rate`** | Initial Rejection Rate | `%` | `lower_better` | — (not in team JSON or code defaults) | 60% | Scored | `kpi_values`<br>Workbook: `Initial Rejection Rate` |
| **`submission_within_due_date`** | Submission Within Due Date | `%` | `higher_better` | — (not in team JSON or code defaults) | 40% | Scored | `kpi_values`<br>Workbook: `Submission Within Due Date` |

### Re-Submission — template KPIs (`re_submission.json`)

| KPI Key | Display Name | Unit | Direction | Target | Weight | Status | Source Location |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`quality_errors_rate`** | Quality Errors Rate | `%` | `lower_better` | — (not in team JSON or code defaults) | 20% | Scored | `kpi_values`<br>Workbook: `Quality Errors Rate` |
| **`rejection_rate_after_resubmission`** | Rejection Rate After Re-Submission | `%` | `lower_better` | — (not in team JSON or code defaults) | 50% | Scored | `kpi_values`<br>Workbook: `Rejection Rate After Re-Submission` |
| **`tat`** | TAT compliance % | `%` | `higher_better` | — (not in team JSON or code defaults) | 30% | Scored | `kpi_values`<br>Workbook: `TAT` |
## 4. Operational Volumes & Branch Attribution Structure

Operational breakdown evidence (e.g. clinic bookings, hospital split) is preserved directly within the JSONB column `performance_records.record_payload`:

```json
{
  "calls": {
    "offered": 1550,
    "handled": 1420,
    "abandoned": 130,
    "aht_seconds": 164.5,
    "aht_display": "2.74 min"
  },
  "geo": {
    "bookings": {
      "dubai": 180,
      "ajman": 70,
      "sharjah": 0,
      "clinics": 95
    }
  },
  "raw_columns": {
    "Agent ID": "E001",
    "Agent Name": "Aya Ramadan",
    "Booking %": 0.043,
    "Attendance %": 0.678,
    "Quality %": 0.0
  }
}
```

---

## 5. Mathematical Scoring & Aggregation Formulas

Authoritative score calculations are implemented in [`Backend/services/calculation_service.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/calculation_service.py):

### 5.1 KPI Achievement Ratio Formula
- **Higher is Better (`higher_better`):**
  $$\text{Achievement} = \min\left(1.0, \frac{\text{Actual Value}}{\text{Target Value}}\right)$$
  *(Note: Certain management configurations allow uncapped performance exceeding 100% up to 120%).*

- **Lower is Better (`lower_better`):**
  $$\text{Achievement} = \max\left(0.0, 1.0 - \frac{\text{Actual Value} - \text{Target Value}}{\text{Target Value}}\right)$$
  *(Alternatively formulated as $\text{Target} / \max(\text{Actual}, 0.0001)$ depending on team configuration).*

### 5.2 Individual Composite Score
$$\text{Composite Score} = \sum_{i=1}^{n} \left( \text{Achievement}_i \times \text{Weight}_i \right)$$
Where $\sum \text{Weight}_i = 1.00$ (100%).

### 5.3 Grade Assignment Scale
- **Grade A (Excellent):** Score $\ge 95.0\%$
- **Grade B (Meets Expectations):** $90.0\% \le \text{Score} < 95.0\%$
- **Grade C (Average):** $80.0\% \le \text{Score} < 90.0\%$
- **Grade D (Below Average):** $70.0\% \le \text{Score} < 80.0\%$
- **Grade E (Unsatisfactory):** Score $< 70.0\%$
