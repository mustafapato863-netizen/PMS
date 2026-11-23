import { describe, expect, it } from 'vitest';
import { buildRemoteSearchResults } from './searchNavigation';

describe('global search team results', () => {
  it('distinguishes the two Coding results by country', () => {
    const results = buildRemoteSearchResults({
      query: 'coding',
      employees: [],
      teams: [
        { name: 'Coding', subtitle: 'Team dashboard' },
        { name: 'Coding EGY', subtitle: 'Team dashboard' },
      ],
    });
    expect(results.map(({ label, path }) => [label, path])).toEqual([
      ['Coding · UAE', '/team/coding?region=UAE'],
      ['Coding · Egypt', '/team/coding?region=EGY'],
    ]);
  });

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
      ['Coding', '/team/coding?region=UAE'],
    ]);
  });
});
