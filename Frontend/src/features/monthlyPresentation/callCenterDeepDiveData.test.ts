import { describe, expect, it } from 'vitest';
import type { ExecRecord } from '../executive/compose';
import { normalizeFunctionSlug, scopeRecordsToRegion } from './callCenterDeepDiveData';

describe('normalizeFunctionSlug', () => {
  it("maps Qlty&Case-Mngt team spellings to the RCM parent function slug", () => {
    expect(normalizeFunctionSlug('Qlty&Case-Mngt')).toBe('rcm');
  });

  it('maps the legacy quality-case-management slug to rcm', () => {
    expect(normalizeFunctionSlug('quality-case-management')).toBe('rcm');
  });

  it('keeps the other Qlty spellings and functions resolving', () => {
    expect(normalizeFunctionSlug('Qlty-and-Case-Mngt')).toBe('rcm');
    expect(normalizeFunctionSlug('Qlty-Case-Mngt')).toBe('rcm');
    expect(normalizeFunctionSlug('Quality and Case Management')).toBe('rcm');
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
