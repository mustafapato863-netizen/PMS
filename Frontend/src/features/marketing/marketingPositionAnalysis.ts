import type { MarketingKpiAggregate } from './types';
import { formatMarketingGapValue, formatMarketingValue } from './marketingNumberFormat';

export type KpiAnalysisTone = 'positive' | 'warning' | 'critical' | 'neutral';

export interface MarketingKpiAnalysis {
  tone: KpiAnalysisTone;
  statusLabel: string;
  movement: {
    kind: 'increase' | 'decrease' | 'unchanged' | 'unavailable';
    positive: boolean | null;
    verb: string;
    fromValue: string | null;
    toValue: string | null;
    detail: string;
  };
  target: {
    achieved: boolean | null;
    detail: string;
  };
  baseline: {
    available: boolean;
    isNew: boolean;
    gap: number | null;
    detail: string;
  };
  impact: {
    lostPoints: number | null;
    detail: string;
  };
}

export const formatMarketingKpiValue = (value: number | null, unit: string): string => {
  return formatMarketingValue(value, unit).display;
};

export const formatMarketingGap = (value: number, unit: string): string => {
  return formatMarketingGapValue(value, unit);
};

export const getKpiNegativeImpact = (kpi: MarketingKpiAggregate): number => {
  if (kpi.averageContribution === null) return 0;
  return Math.max((kpi.weight * 100) - kpi.averageContribution, 0);
};

export const rankKpisByNegativeImpact = (
  kpis: MarketingKpiAggregate[],
): MarketingKpiAggregate[] => kpis
  .filter((kpi) => kpi.averageAchievement !== null && kpi.averageAchievement < 100)
  .slice()
  .sort((left, right) => (
    getKpiNegativeImpact(right) - getKpiNegativeImpact(left)
    || (left.averageAchievement ?? 0) - (right.averageAchievement ?? 0)
  ));

const describeMovement = (kpi: MarketingKpiAggregate): MarketingKpiAnalysis['movement'] => {
  const current = kpi.averageActual;
  const previous = kpi.previousActual;
  if (current === null) {
    return {
      kind: 'unavailable',
      positive: null,
      verb: 'Unavailable',
      fromValue: null,
      toValue: null,
      detail: 'Current actual data is unavailable.',
    };
  }
  if (previous === null) {
    return {
      kind: 'unavailable',
      positive: null,
      verb: 'No comparison',
      fromValue: null,
      toValue: formatMarketingKpiValue(current, kpi.unit),
      detail: kpi.previousPeriodLabel
        ? `No ${kpi.label} result is available for ${kpi.previousPeriodLabel}.`
        : 'Previous-period comparison is unavailable.',
    };
  }
  const difference = current - previous;
  if (difference === 0) {
    return {
      kind: 'unchanged',
      positive: null,
      verb: 'Unchanged',
      fromValue: formatMarketingKpiValue(previous, kpi.unit),
      toValue: formatMarketingKpiValue(current, kpi.unit),
      detail: `${kpi.label} was unchanged at ${formatMarketingKpiValue(current, kpi.unit)}${kpi.previousPeriodLabel ? ` compared with ${kpi.previousPeriodLabel}` : ' compared with the previous period'}.`,
    };
  }
  const increased = difference > 0;
  const positive = kpi.direction === 'lower_better' ? !increased : increased;
  return {
    kind: increased ? 'increase' : 'decrease',
    positive,
    verb: positive ? 'Improved' : 'Worsened',
    fromValue: formatMarketingKpiValue(previous, kpi.unit),
    toValue: formatMarketingKpiValue(current, kpi.unit),
    detail: `${kpi.label} ${positive ? 'improved' : 'worsened'} from ${formatMarketingKpiValue(previous, kpi.unit)} to ${formatMarketingKpiValue(current, kpi.unit)}${kpi.previousPeriodLabel ? ` versus ${kpi.previousPeriodLabel}` : ' versus the previous period'}.`,
  };
};

const describeBaseline = (kpi: MarketingKpiAggregate): MarketingKpiAnalysis['baseline'] => {
  const current = kpi.averageActual;
  const baseline = kpi.baselineActual;
  if (current === null || baseline === null || !kpi.baselinePeriodLabel) {
    return {
      available: false,
      isNew: false,
      gap: null,
      detail: 'Historical baseline is unavailable for the selected scope.',
    };
  }

  if (kpi.isNewBaseline && kpi.previousBaselineActual !== null && kpi.previousBaselinePeriodLabel) {
    const improvement = Math.abs(current - kpi.previousBaselineActual);
    return {
      available: true,
      isNew: true,
      gap: improvement,
      detail: `${kpi.currentPeriodLabel || 'Current period'} set a new baseline at ${formatMarketingKpiValue(current, kpi.unit)}, improving by ${formatMarketingGap(improvement, kpi.unit)} from the previous best ${formatMarketingKpiValue(kpi.previousBaselineActual, kpi.unit)} (${kpi.previousBaselinePeriodLabel}).`,
    };
  }

  const gap = kpi.direction === 'lower_better'
    ? current - baseline
    : baseline - current;
  if (Math.abs(gap) <= 1e-9) {
    const firstAvailable = kpi.previousBaselineActual === null
      && kpi.baselinePeriodLabel === kpi.currentPeriodLabel;
    return {
      available: true,
      isNew: false,
      gap: 0,
      detail: firstAvailable
        ? `${kpi.currentPeriodLabel || 'Current period'} established the first available baseline at ${formatMarketingKpiValue(current, kpi.unit)}.`
        : `${kpi.currentPeriodLabel || 'Current period'} matches the best historical result of ${formatMarketingKpiValue(baseline, kpi.unit)} (${kpi.baselinePeriodLabel}).`,
    };
  }

  return {
    available: true,
    isNew: false,
    gap: Math.abs(gap),
    detail: `${kpi.currentPeriodLabel || 'Current period'} - ${formatMarketingGap(Math.abs(gap), kpi.unit)} From Baseline. Best historical result: ${formatMarketingKpiValue(baseline, kpi.unit)} (${kpi.baselinePeriodLabel}).`,
  };
};

const describeTarget = (kpi: MarketingKpiAggregate): MarketingKpiAnalysis['target'] => {
  const actual = kpi.averageActual;
  const target = kpi.averageTarget;
  if (actual === null || target === null) {
    return { achieved: null, detail: 'Target comparison is unavailable.' };
  }
  if (target === 0) {
    return {
      achieved: null,
      detail: 'The configured target is zero, so target attainment is not interpreted automatically.',
    };
  }
  const difference = actual - target;
  if (difference === 0) {
    return {
      achieved: true,
      detail: `${kpi.label} met the target of ${formatMarketingKpiValue(target, kpi.unit)}.`,
    };
  }
  if (kpi.direction === 'lower_better') {
    return {
      achieved: difference <= 0,
      detail: difference > 0
        ? `${kpi.label} exceeded the target ceiling of ${formatMarketingKpiValue(target, kpi.unit)} by ${formatMarketingGap(difference, kpi.unit)}.`
        : `${kpi.label} performed better than the target of ${formatMarketingKpiValue(target, kpi.unit)} by ${formatMarketingGap(Math.abs(difference), kpi.unit)}.`,
    };
  }
  return {
    achieved: difference >= 0,
    detail: difference > 0
      ? `${kpi.label} exceeded the target of ${formatMarketingKpiValue(target, kpi.unit)} by ${formatMarketingGap(difference, kpi.unit)}.`
      : `${kpi.label} remains ${formatMarketingGap(Math.abs(difference), kpi.unit)} below the target of ${formatMarketingKpiValue(target, kpi.unit)}.`,
  };
};

const describeImpact = (kpi: MarketingKpiAggregate): MarketingKpiAnalysis['impact'] => {
  if (kpi.averageContribution === null) {
    return { lostPoints: null, detail: 'Its score contribution is unavailable.' };
  }
  const maximumContribution = kpi.weight * 100;
  const negativeImpact = getKpiNegativeImpact(kpi);
  if (negativeImpact <= 0.05) {
    return {
      lostPoints: 0,
      detail: `It delivered its full ${maximumContribution.toFixed(1)}% contribution to the position score.${kpi.affectedEmployees > 0 ? ` ${kpi.affectedEmployees} employee${kpi.affectedEmployees === 1 ? '' : 's'} remain below target.` : ''}`,
    };
  }
  return {
    lostPoints: negativeImpact,
    detail: `It contributed ${kpi.averageContribution.toFixed(1)}% against a maximum contribution of ${maximumContribution.toFixed(1)}%, reducing the position result by ${negativeImpact.toFixed(1)}%. ${kpi.affectedEmployees} employee${kpi.affectedEmployees === 1 ? ' is' : 's are'} below target for this KPI.`,
  };
};

export const buildKpiAnalysis = (kpi: MarketingKpiAggregate): MarketingKpiAnalysis => {
  const movement = describeMovement(kpi);
  const target = describeTarget(kpi);
  const baseline = describeBaseline(kpi);
  const impact = describeImpact(kpi);
  const tone: KpiAnalysisTone = target.achieved === true && (impact.lostPoints ?? 0) <= 0.05
    ? 'positive'
    : (impact.lostPoints ?? 0) >= 5 || (kpi.averageAchievement ?? 100) < 80
      ? 'critical'
      : target.achieved === false
        ? 'warning'
        : 'neutral';
  return {
    tone,
    statusLabel: tone === 'positive'
      ? 'On target'
      : tone === 'critical'
        ? 'Critical gap'
        : tone === 'warning'
          ? 'Needs attention'
          : 'Review',
    movement,
    target,
    baseline,
    impact,
  };
};

export const buildKpiNarrative = (kpi: MarketingKpiAggregate): string => {
  const analysis = buildKpiAnalysis(kpi);
  return `${analysis.movement.detail} ${analysis.baseline.detail} ${analysis.target.detail} ${analysis.impact.detail}`;
};

export const buildKpiRecommendation = (kpi: MarketingKpiAggregate): string => {
  const analysis = buildKpiAnalysis(kpi);
  if (analysis.target.achieved === false && kpi.averageActual !== null && kpi.averageTarget !== null) {
    const gap = Math.abs(kpi.averageActual - kpi.averageTarget);
    return kpi.direction === 'lower_better'
      ? `Reduce ${kpi.label} by ${formatMarketingGap(gap, kpi.unit)}`
      : `Increase ${kpi.label} by ${formatMarketingGap(gap, kpi.unit)}`;
  }
  if (analysis.baseline.isNew) return `Protect new ${kpi.label} baseline`;
  if ((analysis.baseline.gap ?? 0) > 0) {
    return `Recover ${formatMarketingGap(analysis.baseline.gap ?? 0, kpi.unit)} to ${kpi.label} baseline`;
  }
  return `Maintain ${kpi.label}`;
};
