import { describe, expect, it } from 'vitest';
import { buildRemoteSearchResults } from './searchNavigation';

describe('global search team results', () => {
  it('opens a team on its canonical team page, including a Pre-Approvals sub-team', () => {
    const results = buildRemoteSearchResults({
      query: 'pre',
      employees: [],
      teams: [
        { name: 'Pre-Approvals IP Offshore', subtitle: 'RCM' },
        { name: 'Pre-Approvals OP Dubai', subtitle: 'RCM' },
        { name: 'Coding', subtitle: 'RCM' },
      ],
    });
    expect(results.filter((item) => item.group === 'teams').map((item) => [item.label, item.path])).toEqual([
      ['Pre-Approvals IP Offshore', '/team/pre-approvals'],
      ['Pre-Approvals OP Dubai', '/team/pre-approvals-op-final'],
      ['Coding', '/team/coding'],
    ]);
  });
});
