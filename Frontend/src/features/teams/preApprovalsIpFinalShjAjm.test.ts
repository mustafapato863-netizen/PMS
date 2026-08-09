import { describe, expect, it } from 'vitest';
import { TEAM_DB_NAME_MAP, TEAM_ID_MAP, TEAM_NAME_MAP } from '../../types';

describe('Pre-Approvals IP Final SHJ/AJM navigation mapping', () => {
  it('maps the canonical team name, route slug, and database name', () => {
    const name = 'Pre-Approvals IP Final SHJAJM';
    const slug = 'pre-approvals-ip-final-shj-ajm';

    expect(TEAM_ID_MAP[name]).toBe(slug);
    expect(TEAM_NAME_MAP[slug]).toBe(name);
    expect(TEAM_DB_NAME_MAP[slug]).toBe(name);
  });
});
