import { describe, expect, it } from 'vitest';
import { insightsWorkspaceUrl } from '../../hooks/api/useInsightsWorkspace';
import {
  apiTeamParam,
  functionOptionsFor,
  reconcileCascade,
  teamBelongsToFunction,
  teamOptionsFor,
} from './filterCascade';

const apiTeams = [
  'Call Center', 'Coding', 'Inbound', 'Marketing', 'Outbound', 'Pre-Approvals IP Offshore',
  'Pre-Approvals IP Final Dubai', 'Pre-Approvals OP Dubai', 'Pre-Approvals OP Final SHJAJM', 'RCM', 'Re-Submission', 'Sales',
];

describe('insights filter cascade', () => {
  it('maps teams to functions with the backend _team_keys semantics', () => {
    expect(teamBelongsToFunction('Inbound', 'Call Center')).toBe(true);
    expect(teamBelongsToFunction('Outbound', 'Call Center')).toBe(true);
    expect(teamBelongsToFunction('Coding', 'Call Center')).toBe(false);
    expect(teamBelongsToFunction('Pre-Approvals IP Offshore', 'RCM')).toBe(true);
    expect(teamBelongsToFunction('Pre-Approvals IP Offshore', 'Pre-Approvals')).toBe(false);
    expect(teamBelongsToFunction('Pre-Approvals OP Dubai', 'Pre-Approvals')).toBe(true);
    expect(teamBelongsToFunction('Marketing', 'Marketing')).toBe(true);
    expect(teamBelongsToFunction('Sales', 'Marketing')).toBe(false);
  });

  it('builds function and team options from the API team list', () => {
    expect(functionOptionsFor(apiTeams)).toEqual(['Call Center', 'RCM', 'Pre-Approvals', 'Marketing']);
    expect(functionOptionsFor(['Inbound', 'Sales'])).toEqual(['Call Center']);
    expect(teamOptionsFor(apiTeams, 'Call Center')).toEqual(['Call Center', 'Inbound', 'Outbound']);
    expect(teamOptionsFor(apiTeams, 'RCM')).toEqual([
      'Coding', 'Pre-Approvals IP Final', 'Pre-Approvals IP Offshore', 'Pre-Approvals OP Final', 'RCM', 'Re-Submission',
    ]);
    expect(teamOptionsFor(apiTeams, 'Pre-Approvals')).toEqual(['Pre-Approvals IP Final', 'Pre-Approvals OP Final']);
    expect(teamOptionsFor(apiTeams)).toContain('Sales');
  });

  it('sends the team, else the function, as the single API team param', () => {
    expect(apiTeamParam({ teamFunction: 'RCM' })).toBe('RCM');
    expect(apiTeamParam({ teamFunction: 'RCM', team: 'Coding' })).toBe('Coding');
    expect(apiTeamParam({})).toBeUndefined();
    const url = insightsWorkspaceUrl({ teamFunction: 'Call Center', team: 'Inbound', region: 'UAE', performanceLevel: 'Employee' });
    const params = new URL(url, 'http://pms.test').searchParams;
    expect(Object.fromEntries(params)).toEqual({ region: 'UAE', team: 'Inbound', performance_level: 'Employee' });
  });

  it('clears the first invalid selection in cascade order and leaves valid ones', () => {
    const options = { regions: ['EGY', 'UAE'], teams: apiTeams, performance_levels: ['Employee'] };
    expect(reconcileCascade({ region: 'UAE', teamFunction: 'Call Center', team: 'Inbound', performanceLevel: 'Employee' }, options)).toBeNull();
    expect(reconcileCascade({ region: 'Mars', team: 'Inbound' }, options)).toMatchObject({ region: undefined, team: 'Inbound' });
    expect(reconcileCascade({ teamFunction: 'Logistics', team: 'Inbound' }, options)).toMatchObject({ teamFunction: undefined, team: undefined });
    expect(reconcileCascade({ teamFunction: 'Call Center', team: 'Coding', kpi: 'aht' }, options)).toMatchObject({ teamFunction: 'Call Center', team: undefined, kpi: undefined });
    // Source branch names are accepted through their canonical merged team.
    expect(reconcileCascade({ teamFunction: 'Pre-Approvals', team: 'Pre-Approvals OP Dubai' }, options)).toBeNull();
    expect(reconcileCascade({ team: 'Inbound', performanceLevel: 'Corporate' }, options)).toMatchObject({ team: 'Inbound', performanceLevel: undefined });
    // Downstream levels wait for the next response after an upstream clear.
    expect(reconcileCascade({ team: 'Nope', performanceLevel: 'Corporate' }, options)).toMatchObject({ team: undefined, performanceLevel: 'Corporate' });
  });
});
