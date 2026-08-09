import { describe, expect, it } from 'vitest';
import { TEAM_DB_NAME_MAP, TEAM_ID_MAP, TEAM_NAME_MAP } from '../../types';

describe('Pre-Approvals IP Elective Dubai navigation mapping', () => {
  it('maps the display name, route slug, and database name consistently', () => {
    const name = 'Pre-Approvals IP Elective Dubai';
    const slug = 'pre-approvals-ip-elective-dubai';
    expect(TEAM_ID_MAP[name]).toBe(slug);
    expect(TEAM_NAME_MAP[slug]).toBe('Pre-Approvals IP Elective');
    expect(TEAM_DB_NAME_MAP[slug]).toBe(name);
  });
});
