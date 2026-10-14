/**
 * Percentage KPI values reach the team and employee screens as ratios: 0.0026 is
 * 0.26% and 1 is 100%. Convert to percentage points once, here, where the form is
 * known, then format. Never choose the form from the size of the number.
 */
export function percentPointsFromRatio(ratio: number): number {
  return ratio * 100;
}

/** Two decimals below one percentage point, so 0.26% stays readable. One decimal otherwise. */
export function percentDecimals(points: number): number {
  return Math.abs(points) < 1 ? 2 : 1;
}

/** Format a value that is already in percentage points, such as 26.2 for 26.2%. */
export function formatPercentPoints(points: number | null | undefined): string {
  if (points === null || points === undefined || !Number.isFinite(points)) return '—';
  return `${points.toFixed(percentDecimals(points))}%`;
}

/** Format a stored or aggregated ratio, such as 0.0026 for 0.26%. */
export function formatPercentRatio(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined || !Number.isFinite(ratio)) return '—';
  return formatPercentPoints(percentPointsFromRatio(ratio));
}
