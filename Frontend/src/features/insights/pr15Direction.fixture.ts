// Real PR #15 (3c2d7af) payload pieces, captured from a throwaway #13 + #14 + #15 merge with
// /workspace/pms-insights-cascade-review/v3/pr15_shape.py (Initial Rejection Rate, lower-better).
import type { InsightDetail, InsightKpiTrend, InsightPersonContribution } from './types';

export const pr15Detail = {
  "direction": "lower_better",
  "current_value": 0.055,
  "previous_value": 0.045,
  "target_value": 0.05,
  "unit": "%",
  "gap_value": -0.0049999999999999975,
  "achievement_percent": 90.91,
  "change_value": -0.010000000000000002,
  "raw_change": 0.010000000000000002,
  "trend_status": "declining",
  "target_status": "missed",
  "direction_defaulted": false
} satisfies Partial<InsightDetail>;

export const pr15PeopleRows = [
  {
    "employee_id": "E1",
    "employee_name": "E1",
    "team": "Submission",
    "performance_level": "Employee",
    "position": "Submission Officer",
    "kpi_key": "initial_rejection_rate",
    "kpi_label": "Initial Rejection Rate",
    "unit": "%",
    "direction": "lower_better",
    "current_value": 0.08,
    "target_value": 0.05,
    "gap": -3.0,
    "weighted_impact": -11.25,
    "trend": 4.0,
    "severity": "High",
    "classification": "negative",
    "achievement_percent": 62.5,
    "change_value": -4.0,
    "trend_status": "declining",
    "target_status": "missed"
  },
  {
    "employee_id": "E2",
    "employee_name": "E2",
    "team": "Submission",
    "performance_level": "Employee",
    "position": "Submission Officer",
    "kpi_key": "initial_rejection_rate",
    "kpi_label": "Initial Rejection Rate",
    "unit": "%",
    "direction": "lower_better",
    "current_value": 0.03,
    "target_value": 0.05,
    "gap": 2.0,
    "weighted_impact": 0.0,
    "trend": -2.0,
    "severity": "On target",
    "classification": "affected",
    "achievement_percent": 100.0,
    "change_value": 2.0,
    "trend_status": "improving",
    "target_status": "met"
  }
] satisfies InsightPersonContribution[];

export const pr15KpiTrend = {
  "kpi_key": "initial_rejection_rate",
  "kpi_label": "Initial Rejection Rate",
  "unit": "%",
  "direction": "lower_better",
  "points": [
    {
      "period": {
        "year": 2026,
        "month": "January",
        "key": "2026-01"
      },
      "actual_value": null,
      "target_value": null,
      "measured_records": 0,
      "achievement_percent": null,
      "status": null,
      "change_value": null,
      "trend_status": null
    },
    {
      "period": {
        "year": 2026,
        "month": "February",
        "key": "2026-02"
      },
      "actual_value": null,
      "target_value": null,
      "measured_records": 0,
      "achievement_percent": null,
      "status": null,
      "change_value": null,
      "trend_status": null
    },
    {
      "period": {
        "year": 2026,
        "month": "March",
        "key": "2026-03"
      },
      "actual_value": null,
      "target_value": null,
      "measured_records": 0,
      "achievement_percent": null,
      "status": null,
      "change_value": null,
      "trend_status": null
    },
    {
      "period": {
        "year": 2026,
        "month": "April",
        "key": "2026-04"
      },
      "actual_value": null,
      "target_value": null,
      "measured_records": 0,
      "achievement_percent": null,
      "status": null,
      "change_value": null,
      "trend_status": null
    },
    {
      "period": {
        "year": 2026,
        "month": "May",
        "key": "2026-05"
      },
      "actual_value": 0.045,
      "target_value": 0.05,
      "measured_records": 2,
      "achievement_percent": 100.0,
      "status": "on_track",
      "change_value": null,
      "trend_status": null
    },
    {
      "period": {
        "year": 2026,
        "month": "June",
        "key": "2026-06"
      },
      "actual_value": 0.055,
      "target_value": 0.05,
      "measured_records": 2,
      "achievement_percent": 90.91,
      "status": "at_risk",
      "change_value": -0.01,
      "trend_status": "declining"
    }
  ],
  "trend_status": "declining"
} satisfies InsightKpiTrend;

export const pr15WatchItem = {
  "severity": "information",
  "insight_type": "kpi_driver",
  "title": "Initial Rejection Rate is on target but worsening"
} as const;
