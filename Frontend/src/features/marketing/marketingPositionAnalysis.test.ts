import { describe, expect, it } from 'vitest';
import type { MarketingKpiAggregate } from './types';
import {
  buildKpiAnalysis,
  buildKpiNarrative,
  buildKpiRecommendation,
  formatMarketingKpiValue,
  rankKpisByNegativeImpact,
} from './marketingPositionAnalysis';

const kpi = (overrides: Partial<MarketingKpiAggregate> = {}): MarketingKpiAggregate => ({
  key: 'cpl',
  label: 'CPL',
  perspective: 'Financial',
  weight: 0.2,
  direction: 'lower_better',
  unit: 'AED',
  color: '#2563EB',
  display_order: 1,
  currentPeriodLabel: 'June 2026',
  previousPeriodLabel: 'May 2026',
  averageActual: 136,
  averageTarget: 60,
  previousActual: 55,
  previousTarget: 60,
  averageAchievement: 44.1,
  averageContribution: 8.8,
  previousAchievement: 100,
  achievementDelta: -55.9,
  affectedEmployees: 1,
  averageGap: 76,
  baselineActual: 55,
  baselinePeriodLabel: 'May 2026',
  previousBaselineActual: 55,
  previousBaselinePeriodLabel: 'May 2026',
  isNewBaseline: false,
  ...overrides,
});

describe('marketing position analysis', () => {
  it('describes movement using the KPI direction and exact target gap', () => {
    const analysis = buildKpiAnalysis(kpi());
    const narrative = buildKpiNarrative(kpi());
    expect(analysis.tone).toBe('critical');
    expect(analysis.statusLabel).toBe('Critical gap');
    expect(analysis.movement).toMatchObject({
      kind: 'increase',
      positive: false,
      verb: 'Worsened',
      fromValue: 'AED 55',
      toValue: 'AED 136',
    });
    expect(analysis.baseline).toMatchObject({ available: true, isNew: false, gap: 81 });
    expect(analysis.target.achieved).toBe(false);
    expect(analysis.impact.lostPoints).toBeCloseTo(11.2);
    expect(narrative).toContain('worsened from AED 55 to AED 136 versus May 2026');
    expect(narrative).toContain('June 2026 - AED 81 From Baseline');
    expect(narrative).toContain('exceeded the target ceiling of AED 60 by AED 76');
    expect(narrative).toContain('reducing the position result by 11.2%');
  });

  it('uses a percentage display and treats a decrease as negative for higher-better KPIs', () => {
    const item = kpi({
      key: 'cr',
      label: 'CR',
      direction: 'higher_better',
      unit: '%',
      averageActual: 34,
      averageTarget: 42,
      previousActual: 36,
      baselineActual: 38,
      baselinePeriodLabel: 'April 2026',
      previousBaselineActual: 38,
      previousBaselinePeriodLabel: 'April 2026',
      averageAchievement: 81,
      averageContribution: 16.2,
    });
    const analysis = buildKpiAnalysis(item);
    const narrative = buildKpiNarrative(item);
    expect(analysis.movement.kind).toBe('decrease');
    expect(analysis.movement.positive).toBe(false);
    expect(narrative).toContain('worsened from 36% to 34% versus May 2026');
    expect(narrative).toContain('June 2026 - 4% From Baseline');
    expect(narrative).toContain('8% below');
  });

  it('identifies a new best historical result and compares it with the previous baseline', () => {
    const item = kpi({
      key: 'quality',
      label: 'Quality',
      direction: 'higher_better',
      unit: '%',
      averageActual: 72.3,
      averageTarget: 70,
      previousActual: 69,
      baselineActual: 72.3,
      baselinePeriodLabel: 'June 2026',
      previousBaselineActual: 70,
      previousBaselinePeriodLabel: 'April 2026',
      isNewBaseline: true,
      averageAchievement: 100,
      averageContribution: 20,
      affectedEmployees: 0,
    });

    const analysis = buildKpiAnalysis(item);
    expect(analysis.baseline).toMatchObject({ available: true, isNew: true });
    expect(analysis.baseline.detail).toContain('June 2026 set a new baseline at 72.3%');
    expect(analysis.baseline.detail).toContain('improving by 2.3% from the previous best 70% (April 2026)');
    expect(buildKpiRecommendation(item)).toBe('Protect new Quality baseline');
  });

  it('does not automatically claim a zero target was achieved', () => {
    const item = kpi({
      averageActual: 0,
      averageTarget: 0,
      previousActual: null,
      previousPeriodLabel: null,
      baselineActual: 0,
      baselinePeriodLabel: 'June 2026',
      previousBaselineActual: null,
      previousBaselinePeriodLabel: null,
      averageAchievement: 0,
      averageContribution: 0,
    });
    const analysis = buildKpiAnalysis(item);
    const narrative = buildKpiNarrative(item);
    expect(analysis.target.achieved).toBeNull();
    expect(narrative).toContain('Previous-period comparison is unavailable');
    expect(narrative).toContain('target is zero');
    expect(narrative).not.toContain('met the target');
  });

  it('prioritizes the largest lost score contribution and derives focus labels', () => {
    const ranked = rankKpisByNegativeImpact([
      kpi({ key: 'low-impact', label: 'Response Rate', weight: 0.1, averageContribution: 8 }),
      kpi({
        key: 'high-impact',
        label: 'Lead Volume',
        direction: 'higher_better',
        unit: 'count',
        weight: 0.3,
        averageActual: 40,
        averageTarget: 100,
        averageContribution: 10,
      }),
    ]);
    expect(ranked.map((item) => item.key)).toEqual(['high-impact', 'low-impact']);
    expect(buildKpiRecommendation(ranked[0])).toBe('Increase Lead Volume by 60');
    expect(buildKpiRecommendation(kpi())).toBe('Reduce CPL by AED 76');
    expect(formatMarketingKpiValue(0.34, '%')).toBe('34%');
  });
});
