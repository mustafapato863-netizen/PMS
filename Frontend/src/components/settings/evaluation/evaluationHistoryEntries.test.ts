import { describe, expect, it } from 'vitest';
import type { EvaluationVersion } from '../evaluationSettings';
import { SHORT_CHECKSUM_LENGTH, versionEntry } from './evaluationHistoryEntries';

const FULL = 'a'.repeat(32) + 'b'.repeat(32);

const APPROVED: EvaluationVersion = {
  id: 'approved-july',
  status: 'approved',
  lines: [],
  version_number: 2,
  checksum: FULL,
  source_version_id: 'draft-june',
  month_name: 'July',
};

describe('versionEntry', () => {
  it('names the version by its number and gives month and status as the detail', () => {
    const entry = versionEntry(APPROVED, 'Fallback');
    expect(entry.title).toBe('Version 2');
    expect(entry.detail).toBe('July · approved');
    expect(entry.status).toBe('approved');
  });

  it('falls back to the month being shown when the version has no month name', () => {
    const entry = versionEntry({ ...APPROVED, month_name: undefined }, 'August');
    expect(entry.detail).toBe('August · approved');
  });

  it('falls back to a plain title and an unknown status when those fields are missing', () => {
    const entry = versionEntry({ ...APPROVED, version_number: null, status: '', month_name: undefined }, '');
    expect(entry.title).toBe('Version');
    expect(entry.detail).toBe('unknown');
    expect(entry.status).toBe('unknown');
  });

  it('shows only the first 8 characters of the checksum and keeps the full value for copying', () => {
    const entry = versionEntry(APPROVED, 'July');
    expect(SHORT_CHECKSUM_LENGTH).toBe(8);
    expect(entry.shortChecksum).toBe('aaaaaaaa');
    expect(entry.checksum).toBe(FULL);
    expect(entry.shortChecksum).not.toBe(FULL);
  });

  it('trims a checksum and treats a blank one as missing', () => {
    expect(versionEntry({ ...APPROVED, checksum: '  sum-1  ' }, 'July').checksum).toBe('sum-1');
    const blank = versionEntry({ ...APPROVED, checksum: '   ' }, 'July');
    expect(blank.checksum).toBeNull();
    expect(blank.shortChecksum).toBeNull();
    expect(versionEntry({ ...APPROVED, checksum: null }, 'July').checksum).toBeNull();
  });

  it('carries the source version only when there is one', () => {
    expect(versionEntry(APPROVED, 'July').sourceVersionId).toBe('draft-june');
    expect(versionEntry({ ...APPROVED, source_version_id: null }, 'July').sourceVersionId).toBeNull();
  });
});
