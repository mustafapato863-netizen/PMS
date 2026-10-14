import { describe, expect, it } from 'vitest';
import { formatEffect, formatKpiValue, formatTarget } from './kpiDiagnosisFormat';

describe('KPI diagnosis formatting', () => {
  it('shows an effect with its sign and a true minus for a fall', () => {
    expect(formatEffect(-3.8)).toBe('−3.80 pts');
    expect(formatEffect(2.4)).toBe('+2.40 pts');
    expect(formatEffect(0)).toBe('0.00 pts');
    expect(formatEffect(null)).toBe('—');
  });

  it('shows a percentage value as a percent whether it is a ratio or already points', () => {
    expect(formatKpiValue(0.26, '%')).toBe('26.0%');
    expect(formatKpiValue(26, '%')).toBe('26.0%');
    expect(formatKpiValue(null, '%')).toBe('N/A');
  });

  it('shows the target with its direction: at most for lower-is-better, at least for higher-is-better', () => {
    expect(formatTarget({ target: 1, unit: '%', direction: 'lower_better' })).toBe('≤ 100.0%');
    expect(formatTarget({ target: 60, unit: 'AED', direction: 'lower_better' })).toBe('≤ 60 AED');
    expect(formatTarget({ target: 0.9, unit: '%', direction: 'higher_better' })).toBe('≥ 90.0%');
  });
});
