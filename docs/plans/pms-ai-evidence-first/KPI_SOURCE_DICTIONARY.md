# Phase 2: KPI & Metric Source Dictionary

**Document Version:** 1.0
**Date:** 10 November 2026
**Status:** Metric Definitions & Provenance Verified
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

| KPI Key | Canonical Display Name | Metric Type | Unit | Polarity (Direction) | Default Target | Scored vs Tracking | Source Field / Storage Key |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`booking_rate`** | Booking Rate | Rate | `%` | `higher_better` | 65.0% | **Scored** (Weight: 40%) | `kpi_values.actual_value`<br>Workbook: `Booking %` |
| **`attendance_rate`** | Attendance Rate | Rate | `%` | `higher_better` | 75.0% | **Scored** (Weight: 30%) | `kpi_values.actual_value`<br>Workbook: `Attendance %` |
| **`quality_score`** | Quality Score | Rate | `%` | `higher_better` | 95.0% | **Scored** (Weight: 30%) | `kpi_values.actual_value`<br>Workbook: `Quality %` |
| **`aht`** | Average Handle Time (AHT) | Duration | `min` | `lower_better` | 2.50 min | **Tracking-Only** (Weight: 0%) | `record_payload['calls']['aht']`<br>Workbook: `AHT` |
| **`abandoned_calls`** | Abandoned Calls | Count | Calls | `lower_better` | 0 | **Tracking-Only** (Weight: 0%) | `record_payload['calls']['abandoned']`<br>Workbook: `Abandoned` |
| **`total_calls`** | Total Calls Handled | Count | Calls | `higher_better` | N/A (Volume) | **Tracking-Only** (Weight: 0%) | `record_payload['calls']['handled']`<br>Workbook: `Handled Calls` |
| **`branch_bookings`** | Branch Booking Count | Count | Bookings | `higher_better` | N/A (Volume) | **Operational Volume** | `record_payload['geo']['bookings'][branch_key]` |

---

## 3. RCM Metric Catalog (Revenue Cycle Management)

### 3.1 Egypt RCM Metrics (`Coding EGY`, `Submission EGY`, `Resubmission`)
In Egypt RCM, scoring focuses on throughput and clean submission turnaround:

| KPI Key | Display Name | Unit | Direction | Target | Weight | Status | Source Location |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`productivity_ach`** | Daily Productivity Target | `%` | `higher_better` | 100.0% | 40% | Scored | `kpi_values`<br>Workbook: `Productivity Ach%` |
| **`quality_accuracy`** | Quality & Audit Accuracy | `%` | `higher_better` | 98.0% | 40% | Scored | `kpi_values`<br>Workbook: `Quality %` |
| **`tat_compliance`** | Turnaround Time (TAT) SLA | `%` | `higher_better` | 95.0% | 20% | Scored | `kpi_values`<br>Workbook: `TAT SLA %` |
| **`rejection_rate`** | First-Pass Rejection Rate | `%` | `lower_better` | 3.0% | 0% | Tracking | `record_payload['rcm']['rejection_rate']` |

### 3.2 UAE RCM Metrics (`Coding`, `Submission`, `Re-Submission`, `Pre-Approvals`)
UAE RCM employs onshore hospital KPIs, separate weight distributions, and insurer-specific denial metrics:

| KPI Key | Display Name | Unit | Direction | Target | Weight | Status | Source Location |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`clean_claim_rate`** | Clean Claim Rate | `%` | `higher_better` | 92.0% | 35% | Scored | `kpi_values`<br>Workbook: `Clean Claim Rate` |
| **`denial_rate`** | Initial Denial Rate | `%` | `lower_better` | 5.0% | 35% | Scored | `kpi_values`<br>Workbook: `Denial Rate` |
| **`collection_ratio`** | Net Collection Ratio | `%` | `higher_better` | 95.0% | 30% | Scored | `kpi_values`<br>Workbook: `Collection %` |
| **`resubmission_tat`** | Resubmission Turnaround | Days | `lower_better` | 7.0 days | 0% | Tracking | `record_payload['rcm']['resub_tat']` |

---

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
