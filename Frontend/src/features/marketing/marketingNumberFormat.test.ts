import { describe, expect, it } from 'vitest';
import { formatMarketingGapValue, formatMarketingValue } from './marketingNumberFormat';

describe('marketing number formatting', () => {
  it('keeps small values readable and compacts thousands, millions, and billions', () => {
    expect(formatMarketingValue(136, 'AED')).toEqual({
      display: 'AED 136',
      exact: 'AED 136.00',
    });
    expect(formatMarketingValue(45_000, 'AED').display).toBe('AED 45K');
    expect(formatMarketingValue(2_254_888, 'AED').display).toBe('AED 2.25M');
    expect(formatMarketingValue(1_250_000_000, 'count').display).toBe('1.25B');
  });

  it('removes trailing zeros while preserving full exact values for tooltips', () => {
    expect(formatMarketingValue(2_500_000, 'AED')).toEqual({
      display: 'AED 2.5M',
      exact: 'AED 2,500,000.00',
    });
    expect(formatMarketingValue(9_844, 'count')).toEqual({
      display: '9.84K',
      exact: '9,844',
    });
  });

  it('formats percentages, negative values, units, and gaps consistently', () => {
    expect(formatMarketingValue(0.34, '%')).toEqual({
      display: '34%',
      exact: '34.00%',
    });
    expect(formatMarketingValue(-1_250, 'count').display).toBe('-1.25K');
    expect(formatMarketingValue(4, 'sec').display).toBe('4 sec');
    expect(formatMarketingGapValue(0.08, '%')).toBe('8%');
  });

  it('returns a neutral unavailable representation', () => {
    expect(formatMarketingValue(null, 'AED')).toEqual({
      display: '—',
      exact: 'Unavailable',
    });
  });
});
