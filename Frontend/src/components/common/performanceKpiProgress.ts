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
export const normalizePercentageKpiForDisplay = (
  value: number,
  target: number,
  unit: string,
) => unit === '%' && target > 0 && target <= 1 ? value * 100 : value;
