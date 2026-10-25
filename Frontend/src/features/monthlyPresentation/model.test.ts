import { describe, expect, it } from 'vitest';
import {
  SECTION_COUNT, accessibleRegions, buildDeckSearch, isMonthAvailable, lastCompleteMonth, nameMasker,
  parseDeckParams, pdfFileName, periodFromKey,
} from './model';

describe('period lock', () => {
  const today = new Date(2026, 9, 21);
  it('opens a month on the 5th of the next month', () => {
    expect(lastCompleteMonth(today)).toBe('2026-09');
    expect(lastCompleteMonth(new Date(2026, 9, 4))).toBe('2026-08');
    expect(periodFromKey('2026-09')!.endDate).toBe('2026-09-30');
    expect(isMonthAvailable('2026-10', today)).toBe(false);
    expect(isMonthAvailable('2026-09', today)).toBe(true);
  });
});

describe('url', () => {
  it('accepts the five review sections and rejects the old deck anchors', () => {
    expect(SECTION_COUNT).toBe(5);
    expect(parseDeckParams('?region=uae&month=2026-09&mode=present&print=1', '#s03')).toMatchObject({
      region: 'uae', month: '2026-09', present: true, print: true, slide: 3,
    });
    expect(parseDeckParams('', '#s05').slide).toBe(5);
    expect(parseDeckParams('', '#s06').slide).toBeNull();
    expect(parseDeckParams('', '#s08').slide).toBeNull();
    expect(parseDeckParams('?region=egy&month=2026-09&function=Call%20Center&team=Inbound')).toMatchObject({
      fn: 'Call Center', team: 'Inbound',
    });
    expect(parseDeckParams('?function=NotAFunction&team=').fn).toBeNull();
    expect(parseDeckParams('?function=Marketing&position=Copywriter')).toMatchObject({ fn: 'Marketing', team: null, position: 'Copywriter' });
    expect(buildDeckSearch('?extra=1', { region: 'egy', month: '2026-09', present: true })).toBe('?extra=1&region=egy&month=2026-09&mode=present');
    expect(buildDeckSearch('?region=egy&month=2026-09&function=RCM&team=Coding', { fn: null, team: null })).toBe('?region=egy&month=2026-09');
    expect(buildDeckSearch('?region=egy&month=2026-09&function=Marketing&position=Copywriter', { fn: null, team: null, position: null })).toBe('?region=egy&month=2026-09');
    expect(pdfFileName('UAE', '2026-09')).toBe('PMS_Monthly_UAE_2026-09.pdf');
  });
});

describe('access and masking', () => {
  it('limits regions from grants, and gives an all-scope user both regions', () => {
    expect(accessibleRegions({ role: 'Regional Manager', accessible_regions: ['UAE'] })).toEqual(['UAE']);
    expect(accessibleRegions({ role: 'Regional Manager', accessible_regions: [] })).toEqual([]);
    expect(accessibleRegions({ role: 'Admin' })).toEqual(['EGY', 'UAE']);
    expect(accessibleRegions({ role: 'Performance Team', accessible_regions: ['Other'] })).toEqual(['EGY', 'UAE']);
  });
  it('assigns aliases in call order', () => {
    const mask = nameMasker();
    expect(mask('Ada')).toBe('Person A');
    expect(mask('Ben')).toBe('Person B');
    expect(mask('Ada')).toBe('Person A');
    expect(mask('  ')).toBe('—');
  });
});
