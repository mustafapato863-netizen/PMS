import { describe, expect, it } from 'vitest';
import { buildKpiAnalysis, formatMarketingGap, formatMarketingKpiValue } from './marketingPositionAnalysis';
import type { MarketingKpiAggregate } from './types';

function rateKpi(overrides: Partial<MarketingKpiAggregate> = {}): MarketingKpiAggregate {
  return {
    key: 'budget_compliance',
    label: 'Budget Compliance',
    perspective: 'Financial',
    weight: 0.2,
    direction: 'higher_better',
    unit: '%',
    color: '#000000',
    display_order: 1,
    currentPeriodLabel: 'September 2026',
    previousPeriodLabel: 'August 2026',
    averageActual: 1.000317,
    averageTarget: 1,
    previousActual: 1,
    previousTarget: 1,
    averageAchievement: 100,
    averageContribution: 20,
    previousAchievement: 100,
    achievementDelta: 0,
    affectedEmployees: 0,
    averageGap: 0.000317,
    baselineActual: 1,
    baselinePeriodLabel: 'August 2026',
    previousBaselineActual: null,
    previousBaselinePeriodLabel: null,
    isNewBaseline: false,
    ...overrides,
  };
}

describe('formatMarketingKpiValue ratio scale', () => {
  it('shows a stored rate just above 1 as 100.03% against a 100% target', () => {
    expect(formatMarketingKpiValue(1.000317, '%', 1)).toBe('100.03%');
    expect(formatMarketingKpiValue(1, '%', 1)).toBe('100%');
    expect(formatMarketingGap(0.000317, '%')).toBe('0.03%');
  });

  it('shows collections stored as 1.5 against target 1 as 150%', () => {
    expect(formatMarketingKpiValue(1.5, '%', 1)).toBe('150%');
    expect(formatMarketingKpiValue(1, '%', 1)).toBe('100%');
  });

  it('leaves lower-better shrinkage of 4 against a target of 10 as 4%', () => {
    expect(formatMarketingKpiValue(4, '%', 10)).toBe('4%');
    expect(formatMarketingKpiValue(10, '%', 10)).toBe('10%');
    expect(formatMarketingGap(6, '%')).toBe('6%');
  });

  it('keeps a ratio at or below 1 on a single percent conversion', () => {
    expect(formatMarketingKpiValue(0.796296296, '%', 1)).toBe('79.63%');
    expect(formatMarketingKpiValue(0.9, '%', 1)).toBe('90%');
    expect(formatMarketingKpiValue(0.01, '%', 1)).toBe('1%');
    expect(formatMarketingKpiValue(0.8583, 'None', 1)).toBe('85.83%');
    expect(formatMarketingKpiValue(400, 'AED', 500)).toBe('AED 400');
    expect(formatMarketingKpiValue(9, 'Days', 12)).toBe('9 Days');
  });

  it('scales the prior month with its own target when that target is also a ratio', () => {
    const analysis = buildKpiAnalysis(rateKpi({
      averageActual: 1.000317,
      averageTarget: 1,
      previousActual: 1,
      previousTarget: 0.9,
    }));
    expect(analysis.movement.fromValue).toBe('100%');
    expect(analysis.movement.toValue).toBe('100.03%');
  });

  it('writes Budget Compliance month copy as 100% to 100.03%', () => {
    const analysis = buildKpiAnalysis(rateKpi());
    expect(analysis.movement.fromValue).toBe('100%');
    expect(analysis.movement.toValue).toBe('100.03%');
    expect(analysis.movement.detail).toContain('from 100% to 100.03%');
    expect(analysis.target.detail).toContain('target of 100%');
    expect(analysis.target.detail).toContain('by 0.03%');
    expect(analysis.target.detail).not.toContain('3.17%');
    expect(analysis.baseline.detail).toContain('100%');
  });

  it('writes collections movement as 100% to 150% against a 100% target', () => {
    const analysis = buildKpiAnalysis(rateKpi({
      key: 'collections',
      label: 'Collections',
      averageActual: 1.5,
      averageTarget: 1,
      previousActual: 1,
      previousTarget: 1,
      baselineActual: 1,
    }));
    expect(analysis.movement.fromValue).toBe('100%');
    expect(analysis.movement.toValue).toBe('150%');
    expect(analysis.movement.detail).toContain('from 100% to 150%');
    expect(analysis.target.detail).toContain('target of 100%');
    expect(analysis.target.detail).toContain('by 50%');
  });

  it('keeps shrinkage copy on the percent-point scale', () => {
    const analysis = buildKpiAnalysis(rateKpi({
      key: 'shrinkage',
      label: 'Shrinkage',
      direction: 'lower_better',
      averageActual: 4,
      averageTarget: 10,
      previousActual: 5,
      previousTarget: 10,
      baselineActual: 4,
    }));
    expect(analysis.movement.fromValue).toBe('5%');
    expect(analysis.movement.toValue).toBe('4%');
    expect(analysis.target.detail).toContain('target of 10%');
    expect(analysis.target.detail).toContain('by 6%');
  });
});
