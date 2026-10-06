import { describe, expect, it } from 'vitest';
import { insightsWorkspaceUrl } from '../../hooks/api/useInsightsWorkspace';
import {
  apiTeamParam,
  functionOptionsFor,
  reconcileCascade,
  teamBelongsToFunction,
  teamOptionsFor,
} from './filterCascade';
import { pr14Options } from './pr14Options.fixture';

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
    expect(functionOptionsFor({ teams: apiTeams })).toEqual(['Call Center', 'RCM', 'Pre-Approvals', 'Marketing']);
    expect(functionOptionsFor({ teams: ['Inbound', 'Sales'] })).toEqual(['Call Center']);
    expect(teamOptionsFor(apiTeams, 'Call Center')).toEqual(['Call Center', 'Inbound', 'Outbound']);
    expect(teamOptionsFor(apiTeams, 'RCM')).toEqual([
      'Coding', 'Pre-Approvals IP Final', 'Pre-Approvals IP Offshore', 'Pre-Approvals OP Final', 'RCM', 'Re-Submission',
    ]);
    expect(teamOptionsFor(apiTeams, 'Pre-Approvals')).toEqual(['Pre-Approvals IP Final', 'Pre-Approvals OP Final']);
    expect(teamOptionsFor(apiTeams)).toContain('Sales');
  });

  it('keeps the single team param for team-only endpoints and sends function= to the workspace API', () => {
    expect(apiTeamParam({ teamFunction: 'RCM' })).toBe('RCM');
    expect(apiTeamParam({ teamFunction: 'RCM', team: 'Coding' })).toBe('Coding');
    expect(apiTeamParam({})).toBeUndefined();
    const url = insightsWorkspaceUrl({ teamFunction: 'Call Center', team: 'Inbound', region: 'UAE', performanceLevel: 'Employee' });
    const params = new URL(url, 'http://pms.test').searchParams;
    expect(Object.fromEntries(params)).toEqual({ region: 'UAE', function: 'Call Center', team: 'Inbound', performance_level: 'Employee' });
    // Function only: sent as `function`, never as `team` (PR #14 param).
    const functionOnly = new URL(insightsWorkspaceUrl({ teamFunction: 'Pre-Approvals' }), 'http://pms.test').searchParams;
    expect(Object.fromEntries(functionOnly)).toEqual({ function: 'Pre-Approvals' });
    // Team only (e.g. after "All functions"): just `team`.
    expect(Object.fromEntries(new URL(insightsWorkspaceUrl({ team: 'Coding' }), 'http://pms.test').searchParams)).toEqual({ team: 'Coding' });
  });

  it('prefers PR #14 team_functions (team → functions[]) and lists multi-function teams under each', () => {
    const teamFunctions = {
      'Pre-Approvals OP Dubai': ['RCM', 'Pre-Approvals'],
      'Pre-Approvals IP Final Dubai': ['RCM', 'Pre-Approvals'],
      'Pre-Approvals IP Offshore': ['RCM'],
      Coding: ['RCM'],
      Inbound: ['Call Center'],
      // An API-only mapping the helper doesn't know proves the API wins.
      'Prior Auth Desk': ['Pre-Approvals'],
      Marketing: ['Marketing'],
      Sales: ['Sales'],
    };
    const teams = Object.keys(teamFunctions);
    expect(teamBelongsToFunction('Prior Auth Desk', 'Pre-Approvals', teamFunctions)).toBe(true);
    expect(teamBelongsToFunction('Prior Auth Desk', 'Pre-Approvals')).toBe(false);
    // The API mapping overrides the helper even where they disagree.
    expect(teamBelongsToFunction('Coding', 'Call Center', { Coding: ['Call Center'] })).toBe(true);
    expect(teamOptionsFor(teams, 'Pre-Approvals', teamFunctions)).toEqual([
      'Pre-Approvals IP Final', 'Pre-Approvals OP Final', 'Prior Auth Desk',
    ]);
    expect(teamOptionsFor(teams, 'RCM', teamFunctions)).toEqual([
      'Coding', 'Pre-Approvals IP Final', 'Pre-Approvals IP Offshore', 'Pre-Approvals OP Final',
    ]);
    // Canonical merged names resolve through their source teams in the map.
    expect(teamBelongsToFunction('Pre-Approvals OP Final', 'RCM', teamFunctions)).toBe(true);
    expect(teamBelongsToFunction('Pre-Approvals OP Final', 'Pre-Approvals', teamFunctions)).toBe(true);
    // Teams missing from the map fall back to the helper.
    expect(teamBelongsToFunction('Outbound', 'Call Center', teamFunctions)).toBe(true);
  });

  it('keeps the visible functions fixed to the four, intersected with options.functions when present', () => {
    const teamFunctions = { Inbound: ['Call Center'], Coding: ['RCM'], Sales: ['Sales'], Marketing: ['Marketing'] };
    expect(functionOptionsFor({
      teams: ['Inbound', 'Coding', 'Sales', 'Marketing'],
      functions: ['Call Center', 'Marketing', 'RCM', 'Sales'],
      team_functions: teamFunctions,
    })).toEqual(['Call Center', 'RCM', 'Marketing']);
    expect(functionOptionsFor({ teams: ['Sales'], functions: ['Sales'], team_functions: { Sales: ['Sales'] } })).toEqual([]);
  });

  it('includes every UAE Pre-Approvals sub-team under Pre-Approvals with the helper fallback', () => {
    const uae = [
      'Pre-Approvals', 'Pre-Approvals OP Dubai', 'Pre-Approvals OP Final SHJAJM', 'Pre-Approvals IP Final Dubai',
      'Pre-Approvals IP Final SHJAJM', 'Pre-Approvals IP Elective', 'Pre-Approvals IP Elective Dubai', 'Pre-Approvals IP Offshore',
    ];
    expect(teamOptionsFor(uae, 'Pre-Approvals')).toEqual([
      'Pre-Approvals', 'Pre-Approvals IP Elective', 'Pre-Approvals IP Elective Dubai', 'Pre-Approvals IP Final', 'Pre-Approvals OP Final',
    ]);
    expect(teamOptionsFor(uae, 'RCM')).toEqual([
      'Pre-Approvals', 'Pre-Approvals IP Elective', 'Pre-Approvals IP Elective Dubai', 'Pre-Approvals IP Final',
      'Pre-Approvals IP Offshore', 'Pre-Approvals OP Final',
    ]);
  });

  it('clears the first invalid selection in cascade order and leaves valid ones', () => {
    const options = { regions: ['EGY', 'UAE'], teams: apiTeams, performance_levels: ['Employee'] };
    expect(reconcileCascade({ region: 'UAE', teamFunction: 'Call Center', team: 'Inbound', performanceLevel: 'Employee' }, options)).toBeNull();
    expect(reconcileCascade({ region: 'Mars', team: 'Inbound' }, options)).toMatchObject({ region: undefined, team: 'Inbound' });
    // An unknown region empties the team list: blame the region, not the function.
    expect(reconcileCascade({ region: 'Mars', teamFunction: 'RCM' }, { ...options, teams: [], performance_levels: [] }))
      .toMatchObject({ region: undefined, teamFunction: 'RCM' });
    expect(reconcileCascade({ teamFunction: 'Logistics', team: 'Inbound' }, options)).toMatchObject({ teamFunction: undefined, team: undefined });
    expect(reconcileCascade({ teamFunction: 'Call Center', team: 'Coding', kpi: 'aht' }, options)).toMatchObject({ teamFunction: 'Call Center', team: undefined, kpi: undefined });
    // Source branch names are accepted through their canonical merged team.
    expect(reconcileCascade({ teamFunction: 'Pre-Approvals', team: 'Pre-Approvals OP Dubai' }, options)).toBeNull();
    expect(reconcileCascade({ team: 'Inbound', performanceLevel: 'Corporate' }, options)).toMatchObject({ team: 'Inbound', performanceLevel: undefined });
    // A team with no data (empty level list) is cleared; its level is re-checked next response.
    expect(reconcileCascade({ team: 'Nope', performanceLevel: 'Corporate' }, { ...options, performance_levels: [] }))
      .toMatchObject({ team: undefined, performanceLevel: 'Corporate' });
    // PR #14 faceting: teams narrowed by the level drop the team, but the team still
    // has levels, so the downstream level is what clears.
    expect(reconcileCascade(
      { team: 'Inbound', performanceLevel: 'Corporate' },
      { regions: ['UAE'], teams: ['RCM'], performance_levels: ['Employee'], functions: ['RCM'], team_functions: { RCM: ['RCM'] } },
    )).toMatchObject({ team: 'Inbound', performanceLevel: undefined });
    // PR #14 faceting: regions narrowed by the team drop the region; the team is cleared first.
    expect(reconcileCascade(
      { region: 'EGY', team: 'Sales' },
      { regions: ['UAE'], teams: ['Inbound', 'Coding'], performance_levels: [], functions: ['Call Center', 'RCM'], team_functions: { Inbound: ['Call Center'], Coding: ['RCM'] } },
    )).toMatchObject({ region: 'EGY', team: undefined });
  });
});

describe('insights filter cascade against real PR #14 option responses', () => {
  const mutable = <T,>(value: T) => JSON.parse(JSON.stringify(value)) as {
    regions: string[]; teams: string[]; performance_levels: string[]; functions: string[]; team_functions: Record<string, string[]>;
  };

  it('narrows Pre-Approvals to all UAE sub-teams and lists them under RCM too', () => {
    const options = mutable(pr14Options.default);
    expect(functionOptionsFor(options)).toEqual(['Call Center', 'RCM', 'Pre-Approvals', 'Marketing']);
    expect(options.functions).toContain('Sales');
    expect(teamOptionsFor(options.teams, 'Pre-Approvals', options.team_functions)).toEqual([
      'Pre-Approvals IP Elective Dubai', 'Pre-Approvals IP Final', 'Pre-Approvals OP Final',
    ]);
    expect(teamOptionsFor(options.teams, 'RCM', options.team_functions)).toEqual([
      'Coding', 'Pre-Approvals IP Elective Dubai', 'Pre-Approvals IP Final', 'Pre-Approvals IP Offshore', 'Pre-Approvals OP Final',
    ]);
    expect(teamOptionsFor(options.teams, 'Call Center', options.team_functions)).toEqual(['Call Center', 'Inbound', 'Outbound']);
  });

  it('auto-clears the real narrowed responses one selection at a time', () => {
    expect(reconcileCascade({ periodKey: '2026-06', team: 'Pharmacy' }, mutable(pr14Options.juneTeamPharmacy)))
      .toMatchObject({ periodKey: '2026-06', team: undefined });
    expect(reconcileCascade({ team: 'Inbound', performanceLevel: 'Corporate' }, mutable(pr14Options.inboundCorporate)))
      .toMatchObject({ team: 'Inbound', performanceLevel: undefined });
    expect(reconcileCascade({ region: 'EGY', team: 'Sales' }, mutable(pr14Options.egySales)))
      .toMatchObject({ region: 'EGY', team: undefined });
    expect(reconcileCascade({ region: 'EGY' }, mutable(pr14Options.egyNoFilters))).toBeNull();
  });
});
