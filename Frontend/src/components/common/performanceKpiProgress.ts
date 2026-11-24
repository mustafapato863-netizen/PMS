export const calculateKpiTargetProgress = (
  actual: number,
  target: number,
  lowerBetter = false,
) => {
  if (!Number.isFinite(actual) || !Number.isFinite(target) || target <= 0) return null;
  if (lowerBetter) {
    return actual <= 0 ? 100 : (target / actual) * 100;
  }
  return (actual / target) * 100;
};

export type KpiTargetStatus = 'on_target' | 'needs_attention' | 'below_target' | 'no_data' | 'target_review';

export const resolveKpiTargetStatus = (
  actual: number | null,
  target: number | null,
  lowerBetter = false,
): { progressPercent: number | null; status: KpiTargetStatus } => {
  if (target === 0) {
    return { progressPercent: null, status: 'target_review' };
  }
  if (actual === null || target === null) {
    return { progressPercent: null, status: 'no_data' };
  }

  const progressPercent = calculateKpiTargetProgress(actual, target, lowerBetter);
  if (progressPercent === null) {
    return { progressPercent: null, status: 'no_data' };
  }
  if (progressPercent >= 100) {
    return { progressPercent, status: 'on_target' };
  }
  if (progressPercent >= 80) {
    return { progressPercent, status: 'needs_attention' };
  }
  return { progressPercent, status: 'below_target' };
};

/**
 * Percentage KPIs are stored as ratios in the performance payload.  The
 * target determines the scale: a target in the (0, 1] range means both the
 * target and its actual are fractions, even when an actual exceeds 1.0.
 *
 * For example, 1.077 against a target of 1.0 means 107.7% against 100%, not
 * 1.1% against 100%.
 */
/** Label for percent-of-target. Scores cap at 100%, so the label does too. */
export const formatPercentOfTargetLabel = (progressPercent: number): string => {
  if (!Number.isFinite(progressPercent)) return 'Target unavailable';
  const displayed = Math.min(progressPercent, 100);
  return `${displayed.toFixed(1)}% of target`;
};

export const normalizePercentageKpiForDisplay = (
  value: number,
  target: number,
  unit: string | undefined,
) => unit === '%' && target > 0 && target <= 1 ? value * 100 : value;

/**
 * Computes a proportional Y-axis domain so small Actual-vs-Target gaps
 * (e.g. 68.1% vs 75.0%) are not visually exaggerated into full-height cliffs.
 */
export function computeTrendYDomain(
  allValues: number[],
  unit?: string,
): { domainMin: number; domainMax: number; domainSpan: number } {
  if (allValues.length === 0) {
    return { domainMin: 0, domainMax: 100, domainSpan: 100 };
  }

  const rawMin = Math.min(...allValues);
  const rawMax = Math.max(...allValues);
  const rawSpan = rawMax - rawMin;

  if (unit === '%') {
    // Low-rate percentage KPIs (e.g. Error Rate 1.5% vs 3.0%): anchor cleanly at 0%.
    if (rawMax <= 20) {
      const domainMax = Math.ceil(Math.max(rawMax * 1.5, rawMax + 2, 5));
      return { domainMin: 0, domainMax, domainSpan: Math.max(domainMax, 1) };
    }

    // Standard 0–100% attainment KPIs: enforce at least a 40-point span on round 10% ticks.
    if (rawMax <= 100) {
      let domainMax = Math.min(100, Math.ceil((rawMax + 12) / 10) * 10);
      let domainMin = Math.max(0, Math.floor((rawMin - 15) / 10) * 10);
      if (domainMax - domainMin < 40) {
        const deficit = 40 - (domainMax - domainMin);
        domainMin = Math.max(0, Math.floor((domainMin - deficit) / 10) * 10);
        if (domainMax - domainMin < 40) {
          domainMax = Math.min(100, Math.ceil((domainMin + 40) / 10) * 10);
        }
      }
      if (domainMin <= 10) domainMin = 0;
      return {
        domainMin,
        domainMax,
        domainSpan: Math.max(domainMax - domainMin, 1),
      };
    }
  }

  // Non-percentage or >100% KPIs: maintain at least a 35% relative span around the max value.
  const minSpan = Math.max(Math.abs(rawMax) * 0.35, 10);
  const extraPad = Math.max(rawSpan * 0.25, (minSpan - rawSpan) / 2, 1);
  const domainMin = Math.max(0, rawMin - extraPad);
  const domainMax = rawMax + extraPad;
  return {
    domainMin,
    domainMax,
    domainSpan: Math.max(domainMax - domainMin, 1),
  };
}
