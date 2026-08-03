# KPI Scoring Engine

This document provides a detailed specification of the calculations, capping rules, grade thresholds, and formulas used by the PMS scoring engine.

---

## 1. Core Definitions

To align performance metrics across multiple teams, the scoring engine separates actual employee performance (Achievement) from the points added to their final performance rating (Contribution).

### KPI Achievement
A percentage representing the raw ratio of an employee's actual performance relative to their configured target.
- **Direct KPIs:** Higher actuals are better (e.g. Attendance, Booking conversion).
- **Inverse KPIs:** Lower actuals are better (e.g. AHT, Rejection rate, Error rate).
- **Capped:** KPI Achievement is normalized and capped at 100% before it is stored, returned by the API, or displayed.

### Effective Achievement
The achievement score capped at `100%` before applying weight configurations:
$$\text{Effective Achievement} = \min(\text{KPI Achievement}, 100\%)$$

### KPI Weight
The maximum percentage share of the final score allocated to a given KPI (configured per team, e.g. Attendance = 70%).

### KPI Contribution
The actual score points contributed to the Final Performance Score:
$$\text{KPI Contribution} = \text{Effective Achievement} \times \text{KPI Weight}$$
- A KPI Contribution can never exceed its configured weight share.

### Final Performance Score
The sum of all individual KPI contributions:
$$\text{Final Performance Score} = \sum (\text{KPI Contribution})$$
- Because individual contributions are capped by their configured weights, the Final Performance Score can never exceed 100%.

---

## 2. Calculation Formulas

For each performance record, the KPI scores are calculated using the following formulas:

### Direct KPI Achievement Ratio
$$\text{KPI Achievement} = \min\left(\frac{\text{Actual}}{\text{Target}} \times 100\%, 100\%\right)$$

### Inverse KPI Achievement Ratio
$$\text{KPI Achievement} = \min\left(\frac{\text{Target}}{\text{Actual}} \times 100\%, 100\%\right)$$

---

## 3. Concrete Calculation Examples

### Example A: Exceeding Target on High Weight KPI (Direct)
- **KPI:** Patient Attendance Rate
- **Weight:** 70% (`0.70`)
- **Target:** 75%
- **Actual:** 85%
- **Calculation:**
  $$\text{KPI Achievement} = \min\left(\frac{85}{75} \times 100\%, 100\%\right) = 100\%$$
  $$\text{Effective Achievement} = 100\%$$
  $$\text{KPI Contribution} = 100\% \times 0.70 = 70.0\%$$

### Example B: Below Target on Lower Weight KPI (Direct)
- **KPI:** Booking Conversion
- **Weight:** 10% (`0.10`)
- **Target:** 45%
- **Actual:** 30%
- **Calculation:**
  $$\text{KPI Achievement} = \min\left(\frac{30}{45} \times 100\%, 100\%\right) = 66.67\%$$
  $$\text{Effective Achievement} = 66.67\%$$
  $$\text{KPI Contribution} = 66.67\% \times 0.10 = 6.67\%$$

### Example C: Exceeding Target on Inverse KPI
- **KPI:** Avg. Handle Time (AHT)
- **Weight:** 5% (`0.05`)
- **Target:** 150 seconds (2.5 mins)
- **Actual:** 120 seconds (2.0 mins)
- **Calculation:**
  $$\text{KPI Achievement} = \min\left(\frac{150}{120} \times 100\%, 100\%\right) = 100\%$$
  $$\text{Effective Achievement} = 100\%$$
  $$\text{KPI Contribution} = 100\% \times 0.05 = 5.0\%$$

---

## 4. Grade Thresholds & Descriptive Status

Once the Final Performance Score is calculated, the system assigns a letter grade and status:

### Grade Thresholds
Grade metrics are mapped based on team-specific configurations (configured under `grade_thresholds` in team configurations):
- **Grade A:** Score $\ge$ Threshold A (default 95%)
- **Grade B:** Score $\ge$ Threshold B (default 85%)
- **Grade C:** Score $\ge$ Threshold C (default 75%)
- **Grade D:** Score $\ge$ Threshold D (default 65%)
- **Grade E:** Score $<$ Threshold D

### Descriptive Status
- **Meet:** Score $\ge$ 80%
- **Average:** Score $\ge$ 70% and $<$ 80%
- **Below:** Score $<$ 70%
