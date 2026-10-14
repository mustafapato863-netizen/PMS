/**
 * The period labels the Executive cards show. Month mode returns the wording each card has always used.
 * Range mode returns the range ("Jun – Sep 2026") wherever a card would otherwise name its single month,
 * so no card in range mode names only the last month of the range.
 */
import { formatPeriod } from './compose';
import { rangeLabel } from './rangeParams';
import type { ExecutivePeriod, ExecutiveRangeBlock } from './types';

/** What a card covers: "Jun – Sep 2026" in range mode; "June 2026" in month mode; '' when there is no period. */
export function coveredPeriodLabel(effective: ExecutivePeriod | null, range: ExecutiveRangeBlock | null | undefined): string {
  return range ? rangeLabel(range.start, range.end) : formatPeriod(effective);
}

/** The comparison period as a name: "Aug" in month mode, "Feb – May 2026" in range mode; null when nothing to compare. */
export function comparisonName(previous: ExecutivePeriod | null, range: ExecutiveRangeBlock | null | undefined): string | null {
  if (range) return range.previous ? rangeLabel(range.previous.start, range.previous.end) : null;
  return previous ? previous.month.slice(0, 3) : null;
}

/**
 * "vs Aug" in month mode; "vs Feb – May 2026" in range mode. With nothing to compare: `monthFallback` in
 * month mode (as each card had it), "vs no earlier range" in range mode.
 */
export function vsLabel(previous: ExecutivePeriod | null, range: ExecutiveRangeBlock | null | undefined, monthFallback = ''): string {
  const name = comparisonName(previous, range);
  if (name) return `vs ${name}`;
  return range ? 'vs no earlier range' : monthFallback;
}
