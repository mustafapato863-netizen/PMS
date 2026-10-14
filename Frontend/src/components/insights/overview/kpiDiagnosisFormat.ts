import type { InsightKpiDiagnosisRow, InsightKpiStatus } from '../../../features/insights/types';

export const KPI_STATUS_LABEL: Record<InsightKpiStatus, string> = {
  on_track: 'On target',
  at_risk: 'At risk',
  critical: 'Critical',
};

export const STATUS_CLASS: Record<InsightKpiStatus, string> = {
  on_track: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  at_risk: 'border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  critical: 'border-rose-500/25 bg-rose-500/10 text-rose-700 dark:text-rose-300',
};

/** Actual or target in the KPI's unit. Ratios (0.26 for 26%) and percentage points both read as a percent. */
export function formatKpiValue(value: number | null | undefined, unit: string | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'N/A';
  if (unit === '%') return `${(Math.abs(value) <= 1 ? value * 100 : value).toFixed(1)}%`;
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ''}`;
}

/** Target with its direction: "≤ 1.0%" for lower-is-better, "≥ 90.0%" for higher-is-better. */
export function formatTarget(row: Pick<InsightKpiDiagnosisRow, 'target' | 'unit' | 'direction'>): string {
  const prefix = row.direction === 'lower_better' ? '≤ ' : row.direction === 'higher_better' ? '≥ ' : '';
  return `${prefix}${formatKpiValue(row.target, row.unit)}`;
}

/** Effect on the score in points with its sign, using a true minus sign. */
export function formatEffect(points: number | null | undefined): string {
  if (points === null || points === undefined || !Number.isFinite(points)) return '—';
  if (points === 0) return '0.00 pts';
  return `${points > 0 ? '+' : '−'}${Math.abs(points).toFixed(2)} pts`;
}
