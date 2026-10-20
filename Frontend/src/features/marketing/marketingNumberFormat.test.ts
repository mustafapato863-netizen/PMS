import { describe, expect, it } from 'vitest';
import { formatMarketingGapValue, formatMarketingValue } from './marketingNumberFormat';

describe('formatMarketingValue units', () => {
  it('renders an invalid stored unit as a percent and never as a None suffix', () => {
    const formatted = formatMarketingValue(0.8583, 'None');
    expect(formatted.display).toBe('85.83%');
    expect(formatted.exact).toBe('85.83%');
    expect(formatted.display).not.toMatch(/none/i);
    expect(formatMarketingValue(0.6945, 'null').display).toBe('69.45%');
    expect(formatMarketingValue(1, 'undefined').display).toBe('100%');
    expect(formatMarketingValue(0.796296296, 'nan').display).toBe('79.63%');
    expect(formatMarketingGapValue(0.796296296, 'None')).toBe('79.63%');
    expect(formatMarketingGapValue(43, 'None')).not.toMatch(/none/i);
  });

  it('keeps real currency and day units', () => {
    expect(formatMarketingValue(400, 'AED').display).toBe('AED 400');
    expect(formatMarketingValue(12, 'Days').display).toBe('12 Days');
  });
});
