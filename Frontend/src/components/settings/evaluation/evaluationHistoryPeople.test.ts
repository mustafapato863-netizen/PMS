import { describe, expect, it } from 'vitest';
import type { EvaluationVersion } from '../evaluationSettings';
import { personLine, versionEntry } from './evaluationHistoryEntries';

const APPROVED: EvaluationVersion = {
  id: 'approved-june',
  status: 'approved',
  lines: [],
  version_number: 2,
  month_name: 'June',
  created_at: '2026-06-20T08:00:00+00:00',
  created_by: 'Ruth Creator',
  approved_at: '2026-06-28T09:30:00+00:00',
  approved_by: 'Amir Approver',
};

describe('personLine', () => {
  it('reads "Created <relative time> by <name>" and keeps the absolute time for the tooltip', () => {
    const line = personLine('Created', '2026-06-20T08:00:00+00:00', 'Ruth Creator');
    expect(line?.text).toMatch(/^Created .+ ago by Ruth Creator$/);
    expect(line?.title).toBe(new Date('2026-06-20T08:00:00+00:00').toLocaleString());
  });

  it('leaves the name out when it is unknown, and the time out when that is unknown', () => {
    expect(personLine('Approved', '2026-06-28T09:30:00+00:00', null)?.text).toMatch(/^Approved .+ ago$/);
    expect(personLine('Approved', null, 'Amir Approver')?.text).toBe('Approved by Amir Approver');
    expect(personLine('Approved', null, 'Amir Approver')?.title).toBeNull();
  });

  it('returns nothing when neither the time nor the name is known, so nothing reads as unknown', () => {
    expect(personLine('Created', null, null)).toBeNull();
    expect(personLine('Created', '   ', '  ')).toBeNull();
  });

  it('treats an unreadable time as missing', () => {
    expect(personLine('Created', 'not a date', 'Ruth Creator')?.text).toBe('Created by Ruth Creator');
  });

  it('trims the name and does not show a blank one', () => {
    expect(personLine('Created', null, '  Ruth Creator  ')?.text).toBe('Created by Ruth Creator');
  });
});

describe('versionEntry people', () => {
  it('gives an approved version a created line and an approved line', () => {
    const entry = versionEntry(APPROVED, 'June');
    expect(entry.created?.text).toMatch(/^Created .+ by Ruth Creator$/);
    expect(entry.approved?.text).toMatch(/^Approved .+ by Amir Approver$/);
  });

  it('gives a draft a created line and no approved line', () => {
    const draft: EvaluationVersion = { id: 'draft-july', status: 'draft', lines: [], version_number: 3, created_at: '2026-07-02T10:00:00+00:00', created_by: 'Ruth Creator' };
    const entry = versionEntry(draft, 'July');
    expect(entry.created?.text).toMatch(/^Created .+ by Ruth Creator$/);
    expect(entry.approved).toBeNull();
  });

  it('gives no lines for a version from a server that sends no who-and-when', () => {
    const entry = versionEntry({ id: 'old', status: 'approved', lines: [], version_number: 1 }, 'June');
    expect(entry.created).toBeNull();
    expect(entry.approved).toBeNull();
  });
});
