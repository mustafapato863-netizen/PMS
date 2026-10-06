import type { InsightKpiTrend } from '../../features/insights/types';
import { resolveAchievement, resolveKpiStatus } from './overview/insightsOverviewModel';

export function displayValue(value: number | null, unit: string | null) {
  if (value === null) return null;
  return unit === '%' && Math.abs(value) <= 1 ? value * 100 : value;
}

/**
 * Chart rows for the six-month KPI trend. Achievement and status come from the
 * API (PR #15 `achievement_percent` / `status`) when present, otherwise they are
 * derived with the same direction-aware rule and 100% / 70% thresholds, so a
 * dot's colour always agrees with which side of the target line it sits on
 * (the Y axis is reversed for lower-is-better KPIs).
 */
export function kpiTrendRows(trend: InsightKpiTrend) {
  return trend.points.map((point) => {
    const achievement = point.actual_value === null
      ? null
      : resolveAchievement(point.achievement_percent, point.actual_value, point.target_value, trend.direction);
    return {
      key: point.period.key,
      period: `${point.period.month.slice(0, 3)} ${String(point.period.year).slice(-2)}`,
      actual: displayValue(point.actual_value, trend.unit),
      target: displayValue(point.target_value, trend.unit),
      records: point.measured_records,
      achievement,
      status: point.actual_value === null ? null : resolveKpiStatus(point.status, achievement),
    };
  });
}
