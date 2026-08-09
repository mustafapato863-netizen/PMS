import { describe, expect, it } from 'vitest';
import { formatContributionMetric } from './peopleContributionFormatters';

describe('formatContributionMetric', () => {
  it('formats a gap like its actual AED value, including grouping and unit', () => {
    const options = { maximumFractionDigits: 2 };

    expect(formatContributionMetric(136357, 317609, 'AED')).toBe(
      `${(136357).toLocaleString(undefined, options)} AED`,
    );
    expect(formatContributionMetric(-181252, 317609, 'AED', true)).toBe(
      `${(-181252).toLocaleString(undefined, options)} AED`,
    );
  });

  it('uses the same percentage scale for actual, target, and signed gap', () => {
    expect(formatContributionMetric(0.82, 0.9, '%')).toBe('82.0%');
    expect(formatContributionMetric(0.9, 0.9, '%')).toBe('90.0%');
    expect(formatContributionMetric(-0.08, 0.9, '%', true)).toBe('-8.0%');
  });

  it('keeps units and signs dynamic for non-percentage metrics', () => {
    expect(formatContributionMetric(89, 30, 'min')).toBe('89 min');
    expect(formatContributionMetric(59, 30, 'min', true)).toBe('+59 min');
    expect(formatContributionMetric(null, 30, 'min', true)).toBe('N/A');
  });
});
