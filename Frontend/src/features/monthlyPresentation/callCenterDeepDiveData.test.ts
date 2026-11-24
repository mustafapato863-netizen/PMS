import { describe, expect, it } from 'vitest';
import type { ExecRecord } from '../executive/compose';
import { normalizeFunctionSlug, scopeRecordsToRegion } from './callCenterDeepDiveData';

describe('normalizeFunctionSlug', () => {
  it("maps the Qlty&Case-Mngt team name to the executive function slug", () => {
    // slugifyIdentifier turns '&' into 'and' with no dashes, so the raw slug
    // is 'qltyandcase-mngt' — it must still resolve to the canonical
    // 'quality-case-management' or the monthly overview drops the function.
    expect(normalizeFunctionSlug('Qlty&Case-Mngt')).toBe('quality-case-management');
  });

  it('leaves the canonical slug unchanged', () => {
    expect(normalizeFunctionSlug('quality-case-management')).toBe('quality-case-management');
  });

  it('keeps the other Qlty spellings and functions resolving', () => {
    expect(normalizeFunctionSlug('Qlty-and-Case-Mngt')).toBe('quality-case-management');
    expect(normalizeFunctionSlug('Qlty-Case-Mngt')).toBe('quality-case-management');
    expect(normalizeFunctionSlug('Call Center')).toBe('call-center');
    expect(normalizeFunctionSlug('RCM')).toBe('rcm');
    expect(normalizeFunctionSlug('ER Dr')).toBe('er-dr');
  });
});

describe('scopeRecordsToRegion', () => {
  const records = [
    { region: 'EGY' },
    { region: 'UAE' },
    { region: null },
  ] as unknown as ExecRecord[];

  it('passes every record through for the combined All view', () => {
    expect(scopeRecordsToRegion(records, 'ALL')).toHaveLength(3);
  });

  it('still filters to one region for EGY and UAE', () => {
    expect(scopeRecordsToRegion(records, 'EGY').map((record) => record.region)).toEqual(['EGY']);
    expect(scopeRecordsToRegion(records, 'UAE').map((record) => record.region)).toEqual(['UAE']);
  });
});
