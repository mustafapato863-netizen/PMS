import { describe, expect, it } from 'vitest';
import { formatPercentPoints, formatPercentRatio, percentDecimals, percentPointsFromRatio } from './percentForm';
import { kpiCountsInScore } from './kpiCountsInScore';

describe('percent form helper', () => {
  it.each([
    // [ratio, expected text] — the stored form
    [0, '0.00%'],
    [0.0026, '0.26%'],
    [0.01, '1.0%'],
    [0.005, '0.50%'],
    [0.5, '50.0%'],
    [0.9, '90.0%'],
    [1, '100.0%'],
    [1.63, '163.0%'],
    [90, '9000.0%'],
    [100, '10000.0%'],
  ])('formats the ratio %s as %s', (ratio, expected) => {
    expect(formatPercentRatio(ratio)).toBe(expected);
  });

  it.each([
    // [percentage points, expected text] — the already-converted form
    [0, '0.00%'],
    [0.0026 * 100, '0.26%'],
    [0.01 * 100, '1.0%'],
    [0.5 * 100, '50.0%'],
    [0.9 * 100, '90.0%'],
    [1, '1.0%'],
    [1.63, '1.6%'],
    [90, '90.0%'],
    [100, '100.0%'],
  ])('formats %s percentage points as %s', (points, expected) => {
    expect(formatPercentPoints(points)).toBe(expected);
  });

  it('converts a ratio to points exactly once', () => {
    expect(percentPointsFromRatio(0.0026)).toBeCloseTo(0.26, 12);
    expect(formatPercentPoints(percentPointsFromRatio(0.0026))).toBe(formatPercentRatio(0.0026));
  });

  it('uses two decimals below one point and one decimal from one point up', () => {
    expect(percentDecimals(0.26)).toBe(2);
    expect(percentDecimals(0.999)).toBe(2);
    expect(percentDecimals(1)).toBe(1);
    expect(percentDecimals(26.2)).toBe(1);
  });

  it('shows a missing value as a dash', () => {
    expect(formatPercentRatio(null)).toBe('—');
    expect(formatPercentRatio(undefined)).toBe('—');
    expect(formatPercentRatio(Number.NaN)).toBe('—');
    expect(formatPercentPoints(Number.POSITIVE_INFINITY)).toBe('—');
  });

  it('keeps a large-percentage ratio KPI unchanged apart from the one conversion', () => {
    // An Inbound-style percentage KPI: 0.884 is 88.4%.
    expect(formatPercentRatio(0.884)).toBe('88.4%');
  });
});

describe('counts in score helper', () => {
  it.each([
    [0.5, true],
    [0.2, true],
    [0.0001, true],
    [0, false],
    [-0.1, false],
    [null, false],
    [undefined, false],
    [Number.NaN, false],
  ])('weight %s counts in the score: %s', (weight, expected) => {
    expect(kpiCountsInScore(weight)).toBe(expected);
  });
});
