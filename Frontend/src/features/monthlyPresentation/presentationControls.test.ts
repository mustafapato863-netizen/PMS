import { describe, expect, it } from 'vitest';
import { presentationMonthOptions, stepPresentation } from './presentationControls';

const today = new Date(2026, 9, 25);

describe('presentationMonthOptions', () => {
  it('lists opened months that have rows for the selected region, newest first', () => {
    const options = presentationMonthOptions(
      [
        { region: 'EGY', periodKey: '2026-07' },
        { region: 'EGY', periodKey: '2026-09' },
        { region: 'EGY', periodKey: '2026-08' },
        { region: 'UAE', periodKey: '2026-08' },
        { region: 'EGY', periodKey: '2026-10' },
      ],
      'EGY',
      today,
      '2026-09',
    );

    expect(options.map((month) => month.key)).toEqual(['2026-09', '2026-08', '2026-07']);
    expect(options[0]?.label).toBe('September 2026');
  });

  it('keeps the displayed month when that region has no measured rows', () => {
    const options = presentationMonthOptions([], 'UAE', today, '2026-09');
    expect(options).toEqual([{ key: '2026-09', label: 'September 2026' }]);
  });
});

describe('stepPresentation', () => {
  const slugs = ['rcm', 'marketing', 'it'];

  it('walks the overview and then the function cards, without entering a detail', () => {
    expect(stepPresentation({ slugs, currentSlug: '', direction: 'next', insideDetail: false })).toEqual({
      slug: 'rcm',
      clearDetail: false,
    });
    expect(stepPresentation({ slugs, currentSlug: 'rcm', direction: 'next', insideDetail: false })).toEqual({
      slug: 'marketing',
      clearDetail: false,
    });
    expect(stepPresentation({ slugs, currentSlug: 'rcm', direction: 'previous', insideDetail: false })).toEqual({
      slug: null,
      clearDetail: false,
    });
    expect(stepPresentation({ slugs, currentSlug: '', direction: 'previous', insideDetail: false })).toEqual({
      slug: null,
      clearDetail: false,
    });
    expect(stepPresentation({ slugs, currentSlug: 'it', direction: 'next', insideDetail: false })).toEqual({
      slug: 'it',
      clearDetail: false,
    });
  });

  it('leaves a team or role for the function line instead of stepping inside it', () => {
    expect(stepPresentation({ slugs, currentSlug: 'rcm', direction: 'previous', insideDetail: true })).toEqual({
      slug: 'rcm',
      clearDetail: true,
    });
    expect(stepPresentation({ slugs, currentSlug: 'rcm', direction: 'next', insideDetail: true })).toEqual({
      slug: 'marketing',
      clearDetail: true,
    });
  });
});
