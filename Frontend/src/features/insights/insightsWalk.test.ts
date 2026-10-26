import { describe, expect, it } from 'vitest';
import { buildInsightsWalk, dragForWalkStep, leadForWalkStep } from './insightsWalk';
import type { InsightRoleSummary } from './types';

const options = {
  teams: ['Marketing', 'Inbound', 'Coding'],
  functions: ['Marketing', 'Call Center', 'RCM'],
  team_functions: {
    Marketing: ['Marketing'],
    Inbound: ['Call Center'],
    Coding: ['RCM'],
  },
};

const teams = [
  { team: 'Marketing', current_score: 69.9, score_change: -20.1, main_cause: 'CPL contributed to the performance gap' },
  { team: 'Inbound', current_score: 91.2, score_change: 1.1, main_cause: null },
  { team: 'Coding', current_score: 53.6, score_change: -4, main_cause: null },
];

const roles: InsightRoleSummary[] = [
  { role: 'Media Buyer', team: 'Marketing', current_score: 69.9, previous_score: 90, movement: -20.1, net_impact: -5.6, affected_employees: 2, total_employees: 5, primary_insight_id: null },
];

describe('buildInsightsWalk', () => {
  it('lists functions by their lowest live team, without averaging', () => {
    const walk = buildInsightsWalk({}, options, teams, roles);
    expect(walk.depth).toBe('company');
    expect(walk.crumbs.map((crumb) => crumb.label)).toEqual(['Company']);
    expect(walk.steps.map((step) => step.label)).toEqual(['RCM', 'Marketing', 'Call Center']);
    expect(walk.steps[0]).toMatchObject({
      score: 53.6, movement: -4, detail: 'Lowest team · Coding', focus: 'Coding', facts: '1 team',
    });
    expect(walk.steps[1].detail).toBe('Lowest team · Marketing — CPL contributed to the performance gap');
    expect(walk.steps[2]).toMatchObject({ score: 91.2, detail: 'Lowest team · Inbound' });
  });

  it('opens the function onto its live teams, worst score first', () => {
    const walk = buildInsightsWalk({ teamFunction: 'RCM' }, options, teams, roles);
    expect(walk.depth).toBe('function');
    expect(walk.steps).toEqual([
      expect.objectContaining({ kind: 'team', label: 'Coding', score: 53.6, movement: -4 }),
    ]);
  });

  it('opens the team onto live roles and stops at the role', () => {
    const team = buildInsightsWalk({ teamFunction: 'Marketing', team: 'Marketing' }, options, teams, roles);
    expect(team.depth).toBe('team');
    expect(team.steps[0]).toMatchObject({ label: 'Media Buyer', detail: '2 of 5 scored below 70', team: null });

    const role = buildInsightsWalk(
      { teamFunction: 'Marketing', team: 'Marketing', position: 'Media Buyer' },
      options,
      teams,
      roles,
    );
    expect(role.depth).toBe('role');
    expect(role.crumbs.map((crumb) => crumb.label)).toEqual(['Company', 'Marketing', 'Marketing', 'Media Buyer']);
    expect(role.steps).toEqual([]);
  });

  it('opens live roles when a function has no team summary', () => {
    const walk = buildInsightsWalk({ teamFunction: 'Marketing' }, options, [], roles);
    expect(walk.steps).toEqual([
      expect.objectContaining({ kind: 'role', label: 'Media Buyer', detail: '2 of 5 scored below 70', team: 'Marketing' }),
    ]);
  });

  it('stays empty when the function has no live team or role rows', () => {
    const walk = buildInsightsWalk({ teamFunction: 'Finance' }, options, teams, roles);
    expect(walk.steps).toEqual([]);
  });

  it('ranks a function by its share of the gap, and keeps the lowest team as a second fact', () => {
    const shared = teams.map((row) => ({
      ...row,
      gap_contribution_percent: row.team === 'Inbound' ? 41 : row.team === 'Marketing' ? 12 : 4,
      impacted_employees: row.team === 'Inbound' ? 6 : 1,
      total_employees: 10,
      basis_context: row.team === 'Inbound'
        ? { state: 'changed' as const, like_for_like: false, raw_performance: 'changed' as const, membership: 'changed' as const, reasons: [], message: 'The compared people changed.' }
        : null,
    }));
    const rankedOptions = {
      ...options,
      teams: [...options.teams, 'Payment Posting'],
      team_functions: { ...options.team_functions, 'Payment Posting': ['RCM'] },
    };
    const posted = {
      team: 'Payment Posting',
      current_score: 80,
      score_change: -1,
      main_cause: null,
      gap_contribution_percent: 30,
      impacted_employees: 2,
      total_employees: 8,
      basis_context: null,
    };
    const walk = buildInsightsWalk({}, rankedOptions, [...shared, posted], roles);
    expect(walk.steps.map((step) => step.label)).toEqual(['Call Center', 'RCM', 'Marketing']);
    expect(walk.steps[0]).toMatchObject({
      focus: 'Inbound',
      focusShare: 41,
      contribution: 41,
      score: 91.2,
      detail: 'Inbound · 91.2% · 41% of the gap',
      basisNote: 'The compared people changed.',
    });
    expect(leadForWalkStep(walk.steps[0])).toBe(
      'Start with Call Center. Inbound accounts for 41% of the gap at 91.2%.',
    );
    expect(walk.steps[1]).toMatchObject({
      focus: 'Payment Posting',
      focusShare: 30,
      contribution: 34,
      score: 80,
      detail: 'Payment Posting · 80.0% · 30% of the gap',
      lowestNote: 'Lowest team · Coding at 53.6%',
    });
    const opened = buildInsightsWalk({ teamFunction: 'Call Center' }, rankedOptions, [...shared, posted], roles);
    expect(opened.steps[0]).toMatchObject({
      label: 'Inbound',
      facts: '41% of the gap · 6 of 10 scored below 70',
      basisNote: 'The compared people changed.',
      contribution: 41,
    });
    expect(leadForWalkStep(opened.steps[0])).toBe('Start with Inbound at 91.2%, 41% of the gap.');
  });

  it('keeps the drag that names the start step and drops one about somewhere else', () => {
    const walk = buildInsightsWalk({}, options, teams, roles);
    const drivers = [
      { id: 'elsewhere', driver: 'AHT', scope: 'Call Center', impact_points: -12, direction: 'negative' as const, insight_id: 'aht' },
      { id: 'here', driver: 'Denial rate', scope: 'RCM · Coding', impact_points: -3, direction: 'negative' as const, insight_id: 'denial' },
    ];
    expect(walk.steps[0].label).toBe('RCM');
    expect(dragForWalkStep(drivers, walk.steps[0])).toMatchObject({ id: 'here' });
    expect(dragForWalkStep(drivers, undefined)).toBeNull();
  });

  it('keeps a team that was chosen without a function', () => {
    const walk = buildInsightsWalk({ team: 'Marketing' }, options, teams, roles);
    expect(walk.depth).toBe('team');
    expect(walk.crumbs.map((crumb) => crumb.label)).toEqual(['Company', 'Marketing']);
  });
});
