import { percentDecimals } from '../../utils/percentForm';

const MINUS_SIGN = '−';

/** Signed text: "+" for a rise, a true minus for a fall, nothing extra for no change. */
function signed(delta: number, body: string): string {
  if (delta > 0) return `+${body}`;
  if (delta < 0) return `${MINUS_SIGN}${body}`;
  return body;
}

/**
 * Change against the previous month in the KPI's own unit. Percentage KPIs are a
 * difference in points ("−0.94 pts vs Aug"), not a relative percent of a rate.
 * Other units keep theirs: "+12 vs Aug", "+1.5 min vs Aug", "+AED 12.5 vs Aug".
 */
export function formatMonthChange(delta: number, unit: string | undefined, monthLabel: string): string {
  const magnitude = Math.abs(delta);
  let body: string;
  if (unit === '%') {
    body = `${magnitude.toFixed(percentDecimals(magnitude))} pts`;
  } else if (unit === 'min') {
    body = `${magnitude.toFixed(1)} min`;
  } else if (unit === 's') {
    body = `${Math.round(magnitude)}s`;
  } else if (unit === 'currency') {
    body = `AED ${magnitude.toFixed(1)}`;
  } else {
    body = magnitude.toLocaleString(undefined, { maximumFractionDigits: 1 });
  }
  return `${signed(delta, body)} vs ${monthLabel}`;
}

/** Muted line for a card with no change to show. Says which one is missing. */
export function missingMonthChangeText(hasPreviousMonth: boolean): string {
  return hasPreviousMonth ? 'No previous value' : 'No previous month';
}
