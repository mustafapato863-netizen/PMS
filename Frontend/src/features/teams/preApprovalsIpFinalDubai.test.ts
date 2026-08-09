import { describe, expect, it } from 'vitest';
import {
  TEAM_DB_NAME_MAP,
  TEAM_ID_MAP,
  TEAM_NAME_MAP,
  canonicalTeamName,
  isMergedIpFinalTeam,
} from '../../types';

describe('Pre-Approvals IP Final Dubai navigation mapping', () => {
  it('maps the display name, route slug, and database name consistently', () => {
    const name = 'Pre-Approvals IP Final Dubai';
    const slug = 'pre-approvals-ip-final-dubai';
    expect(TEAM_ID_MAP[name]).toBe(slug);
    expect(TEAM_NAME_MAP[slug]).toBe(name);
    expect(TEAM_DB_NAME_MAP[slug]).toBe(name);
  });
});

describe('Pre-Approvals IP Final merged identity', () => {
  it('exposes one canonical route while preserving both source team names', () => {
    expect(TEAM_ID_MAP['Pre-Approvals IP Final']).toBe('pre-approvals-ip-final');
    expect(TEAM_NAME_MAP['pre-approvals-ip-final']).toBe('Pre-Approvals IP Final');
    expect(TEAM_DB_NAME_MAP['pre-approvals-ip-final']).toBe('Pre-Approvals IP Final');
    expect(canonicalTeamName('Pre-Approvals IP Final Dubai')).toBe('Pre-Approvals IP Final');
    expect(canonicalTeamName('Pre-Approvals IP Final SHJAJM')).toBe('Pre-Approvals IP Final');
    expect(isMergedIpFinalTeam('Pre-Approvals IP Final')).toBe(true);
  });
});
