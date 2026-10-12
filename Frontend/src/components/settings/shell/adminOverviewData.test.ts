import { describe, expect, it } from 'vitest';
import {
  SYSTEM_ERROR_LIMIT,
  SYSTEM_ERROR_WINDOW_MS,
  isFailedStatus,
  latestUpload,
  parseUploads,
  readRows,
  summarizeSystemErrors,
  summarizeUsers,
} from './adminOverviewData';

describe('readRows', () => {
  it('returns the rows of a successful payload', () => {
    expect(readRows({ success: true, data: [{ id: 1 }] })).toEqual([{ id: 1 }]);
  });

  it('returns null when the request reported a failure or the data is not a list', () => {
    expect(readRows({ success: false, message: 'nope' })).toBeNull();
    expect(readRows({ success: true, data: 'text' })).toBeNull();
    expect(readRows(null)).toBeNull();
    expect(readRows(['not', 'an', 'object'])).toBeNull();
  });
});

describe('parseUploads and latestUpload', () => {
  it('skips rows that are not objects and keeps missing fields as null', () => {
    const rows = parseUploads([null, 'x', { id: 'a', uploaded_at: 'not a date', status: 7 }], 'employee');
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ id: 'a', timestamp: null, status: null, recordCount: null, filename: null });
  });

  it('never carries status or record count for management rows', () => {
    const [row] = parseUploads([{ id: 'm', status: 'success', record_count: 9 }], 'management');
    expect(row).toMatchObject({ kind: 'management', status: null, recordCount: null });
  });

  it('picks the newest upload by timestamp', () => {
    const rows = parseUploads([
      { id: 'old', uploaded_at: '2026-01-01T00:00:00Z' },
      { id: 'new', uploaded_at: '2026-03-01T00:00:00Z' },
      { id: 'middle', uploaded_at: '2026-02-01T00:00:00Z' },
    ], 'employee');
    expect(latestUpload(rows)?.id).toBe('new');
  });

  it('falls back to the first row when no row has a usable date, and to null when there are none', () => {
    const rows = parseUploads([{ id: 'first' }, { id: 'second' }], 'management');
    expect(latestUpload(rows)?.id).toBe('first');
    expect(latestUpload([])).toBeNull();
  });
});

describe('isFailedStatus', () => {
  it('treats failure words as failures, case-insensitively', () => {
    expect(isFailedStatus('failed')).toBe(true);
    expect(isFailedStatus('FAILED')).toBe(true);
    expect(isFailedStatus('error')).toBe(true);
  });

  it('does not treat success, processing or a missing status as a failure', () => {
    expect(isFailedStatus('success')).toBe(false);
    expect(isFailedStatus('processing')).toBe(false);
    expect(isFailedStatus(null)).toBe(false);
  });
});

describe('summarizeUsers', () => {
  it('counts roles, disabled accounts, must-change-password and reassignment flags', () => {
    const summary = summarizeUsers([
      { role: 'Manager', is_active: false, must_change_password: true },
      { role: 'Admin', is_active: true },
      { role: 'Manager', legacy_role_needs_reassignment: true },
    ]);
    expect(summary).toEqual({
      total: 3,
      byRole: [{ role: 'Manager', count: 2 }, { role: 'Admin', count: 1 }],
      disabled: 1,
      mustChangePassword: 1,
      needsReassignment: 1,
    });
  });

  it('ignores non-object rows and treats a missing is_active as active, like the user panel', () => {
    const summary = summarizeUsers([null, 3, { role: 42 }, { role: 'Viewer', is_active: 'no' }]);
    expect(summary.total).toBe(2);
    expect(summary.disabled).toBe(0);
    expect(summary.byRole).toEqual([{ role: 'Unknown role', count: 1 }, { role: 'Viewer', count: 1 }]);
  });
});

describe('summarizeSystemErrors', () => {
  // A fixed clock, so no assertion depends on the real time.
  const NOW = Date.parse('2026-10-12T12:00:00Z');
  const HOUR = 60 * 60 * 1000;
  const at = (msAgo: number) => new Date(NOW - msAgo).toISOString();
  const error = (msAgo: number | null, errorClass = 'ValueError') => ({
    endpoint: '/api/a',
    method: 'GET',
    error_class: errorClass,
    occurred_at: msAgo === null ? null : at(msAgo),
  });

  it('counts only errors inside the last 24 hours and reports the newest of those', () => {
    const summary = summarizeSystemErrors([
      error(23 * HOUR, 'Older'),
      error(1 * HOUR, 'Newest'),
      error(2 * 24 * HOUR, 'Stale'),
    ], NOW);
    expect(summary.count).toBe(2);
    expect(summary.capped).toBe(false);
    expect(summary.latest?.errorClass).toBe('Newest');
    expect(summary.lastError?.errorClass).toBe('Newest');
  });

  it('counts nothing when every error is older than 24 hours, but still reports the last one', () => {
    const summary = summarizeSystemErrors([error(3 * 24 * HOUR, 'Old'), error(2 * 24 * HOUR, 'Older')], NOW);
    expect(summary.count).toBe(0);
    expect(summary.capped).toBe(false);
    expect(summary.latest).toBeNull();
    // The newest of the old errors is the one from two days ago.
    expect(summary.lastError?.errorClass).toBe('Older');
    expect(summary.lastError?.timestamp).toBe(NOW - 2 * 24 * HOUR);
  });

  it('treats the exact window start as inside the window', () => {
    const summary = summarizeSystemErrors([error(SYSTEM_ERROR_WINDOW_MS)], NOW);
    expect(summary.count).toBe(1);
  });

  it('marks the count as a lower bound only when the page is full and every row is inside the window', () => {
    const fullAndRecent = Array.from({ length: SYSTEM_ERROR_LIMIT }, () => error(HOUR));
    expect(summarizeSystemErrors(fullAndRecent, NOW)).toMatchObject({ count: SYSTEM_ERROR_LIMIT, capped: true });
  });

  it('is not capped when the full page still holds an error older than the window', () => {
    const rows = [...Array.from({ length: SYSTEM_ERROR_LIMIT - 1 }, () => error(HOUR)), error(2 * 24 * HOUR)];
    expect(summarizeSystemErrors(rows, NOW)).toMatchObject({ count: SYSTEM_ERROR_LIMIT - 1, capped: false });
  });

  it('is exact, not capped, when a short page holds only recent errors', () => {
    const summary = summarizeSystemErrors([error(HOUR), error(2 * HOUR), error(3 * HOUR)], NOW);
    expect(summary).toMatchObject({ count: 3, capped: false });
  });

  it('ignores rows with a missing, unparseable or non-object timestamp, without throwing', () => {
    const rows: unknown[] = [error(HOUR, 'Good'), error(null), { occurred_at: 'not a date', error_class: 'Bad' }, null, 'junk'];
    const summary = summarizeSystemErrors(rows, NOW);
    expect(summary.count).toBe(1);
    expect(summary.latest?.errorClass).toBe('Good');
    expect(summary.capped).toBe(false);
  });

  it('does not claim a lower bound when a bad row sits on an otherwise full page', () => {
    const rows: unknown[] = [null, ...Array.from({ length: SYSTEM_ERROR_LIMIT - 1 }, () => error(HOUR))];
    expect(summarizeSystemErrors(rows, NOW)).toMatchObject({ count: SYSTEM_ERROR_LIMIT - 1, capped: false });
  });

  it('reports nothing for an empty list', () => {
    expect(summarizeSystemErrors([], NOW)).toEqual({ count: 0, capped: false, latest: null, lastError: null });
  });
});
