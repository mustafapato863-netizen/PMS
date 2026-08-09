import { describe, expect, it } from 'vitest';
import { shouldShowMarketingNavigation } from './navigation';

describe('Marketing navigation visibility', () => {
  it('appears only after Employee data is available', () => {
    expect(shouldShowMarketingNavigation(new Set(), null)).toBe(false);
    expect(shouldShowMarketingNavigation(new Set(['marketing:Employee']), null)).toBe(true);
  });

  it('respects team-level access scope', () => {
    const data = new Set(['marketing:Employee']);
    expect(shouldShowMarketingNavigation(data, new Set(['inbound']))).toBe(false);
    expect(shouldShowMarketingNavigation(data, new Set(['marketing']))).toBe(true);
  });
});
