import { describe, expect, it } from 'vitest';
import {
  composeExecutiveSummary,
  gradeDistribution,
  kpiRows,
  mapDrivers,
  summarizeActions,
  toExecRecords,
  type ComposeInput,
  type ExecRecord,
} from './compose';
import { executiveFunctionForTeam, functionFromSlug, functionSlug } from './functions';
import { FIXTURE_TEAM_FUNCTIONS, fixtureActions, fixtureAgentRecords, fixtureDrivers } from './executive.fixture';

const TODAY = new Date(2026, 6, 6); // 6 Jul 2026 (local)
const records = toExecRecords(fixtureAgentRecords());

function compose(patch: Partial<ComposeInput> = {}) {
  return composeExecutiveSummary({
    view: 'corporate',
    role: 'Admin',
    records,
    filters: {},
    teamFunctions: FIXTURE_TEAM_FUNCTIONS,
    drivers: fixtureDrivers(),
    actions: fixtureActions(TODAY),
    comparisonRecords: records,
    today: TODAY,
    ...patch,
  });
}

const record = (score: number, patch: Partial<ExecRecord> = {}): ExecRecord => ({
  employeeId: `e${score}`, name: `E ${score}`, team: 'Inbound', region: 'EGY', position: 'Agent L1', level: 'Employee',
  period: { key: '2026-06', year: 2026, month: 'June' } as ExecRecord['period'], score, kpis: [], ...patch,
});

describe('executive function membership (disjoint, Executive cards only)', () => {
  it('puts IP Offshore under RCM and UAE pre-approvals under Pre-Approvals even when the backend lists both', () => {
    expect(executiveFunctionForTeam('Pre-Approvals IP Offshore', FIXTURE_TEAM_FUNCTIONS)).toBe('RCM');
    expect(executiveFunctionForTeam('Pre-Approvals IP Offshore')).toBe('RCM');
    expect(executiveFunctionForTeam('Pre-Approvals IP Final', FIXTURE_TEAM_FUNCTIONS)).toBe('Pre-Approvals');
    expect(executiveFunctionForTeam('Pre-Approvals OP Final', FIXTURE_TEAM_FUNCTIONS)).toBe('Pre-Approvals');
    expect(executiveFunctionForTeam('Pre-Approvals OP Final')).toBe('Pre-Approvals');
  });

  it('follows backend team_functions for CSR (not Call Center) and gives outside teams no card', () => {
    expect(executiveFunctionForTeam('CSR', FIXTURE_TEAM_FUNCTIONS)).toBeNull();
    expect(executiveFunctionForTeam('CSR')).toBeNull();
    expect(executiveFunctionForTeam('Inbound', FIXTURE_TEAM_FUNCTIONS)).toBe('Call Center');
    expect(executiveFunctionForTeam('Content', FIXTURE_TEAM_FUNCTIONS)).toBe('Marketing');
    expect(executiveFunctionForTeam('Sales', FIXTURE_TEAM_FUNCTIONS)).toBeNull();
  });

  it('round-trips function slugs', () => {
    expect(functionSlug('Pre-Approvals')).toBe('pre-approvals');
    expect(functionFromSlug('call-center')).toBe('Call Center');
    expect(functionFromSlug('nope')).toBeNull();
  });

  it('builds one card per function with disjoint teams; CSR counts in the company score only', () => {
    const summary = compose();
    expect(summary.functions.map((card) => card.function)).toEqual(['Call Center', 'RCM', 'Pre-Approvals', 'Marketing']);
    const rcm = summary.functions.find((card) => card.function === 'RCM')!;
    const pa = summary.functions.find((card) => card.function === 'Pre-Approvals')!;
    expect(rcm.teams).toContain('Pre-Approvals IP Offshore');
    expect(pa.teams).not.toContain('Pre-Approvals IP Offshore');
    expect(pa.teams).toContain('Pre-Approvals IP Final');
    const cardTeams = summary.functions.flatMap((card) => card.teams);
    expect(new Set(cardTeams).size).toBe(cardTeams.length);
    expect(cardTeams).not.toContain('CSR');
    expect(summary.teams.map((team) => team.team)).toContain('CSR');
    const cardHeadcount = summary.functions.reduce((sum, card) => sum + card.employees, 0);
    expect(summary.hero.employees).toBe(cardHeadcount + 5);
  });
});

describe('periods: fallback and empty', () => {
  it('uses the latest month by default with no notice', () => {
    const summary = compose();
    expect(summary.period.effective?.key).toBe('2026-06');
    expect(summary.period.previous?.key).toBe('2026-05');
    expect(summary.period.fallback_applied).toBe(false);
    expect(summary.period.notice).toBeNull();
    expect(summary.data_status.has_data).toBe(true);
  });

  it('falls back to the latest month with data and explains it when the requested month is empty', () => {
    const summary = compose({ requestedPeriodKey: '2026-07' });
    expect(summary.period.requested?.key).toBe('2026-07');
    expect(summary.period.effective?.key).toBe('2026-06');
    expect(summary.period.fallback_applied).toBe(true);
    expect(summary.period.notice).toBe('No performance data for July 2026 yet — showing June 2026, the latest month with data.');
  });

  it('honours a requested month that has data', () => {
    const summary = compose({ requestedPeriodKey: '2026-03' });
    expect(summary.period.effective?.key).toBe('2026-03');
    expect(summary.period.previous?.key).toBe('2026-02');
    expect(summary.trend.map((point) => point.period.key)).toEqual(['2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03']);
  });

  it('reports no data at all for an empty scope', () => {
    const summary = compose({ records: [], comparisonRecords: [] });
    expect(summary.data_status.has_data).toBe(false);
    expect(summary.period.effective).toBeNull();
    expect(summary.hero.score).toBeNull();
    expect(summary.functions).toEqual([]);
  });

  it('marks upload metadata as unavailable in composed mode', () => {
    expect(compose().meta.unavailable).toContain('upload_meta');
    expect(compose().meta.source).toBe('composed');
  });
});

describe('grades use the live 95/90/80/70 palette', () => {
  it('buckets scores on the frontend cut-offs (not the backend 95/85/75/65)', () => {
    const scores = [96, 95, 94, 90, 89, 85, 80, 79, 75, 70, 69, 65];
    const distribution = gradeDistribution(scores.map((score, index) => record(score, { employeeId: `e${index}` })), [])!;
    expect(distribution.counts).toEqual({ A: 2, B: 2, C: 3, D: 3, E: 2 });
    expect(distribution.total).toBe(12);
    expect(distribution.movement).toBeNull();
  });

  it('reports headcount movement vs the previous month', () => {
    const current = [record(96, { employeeId: 'a' }), record(91, { employeeId: 'b' })];
    const previous = [record(91, { employeeId: 'a' }), record(85, { employeeId: 'b' })];
    const distribution = gradeDistribution(current, previous)!;
    expect(distribution.movement).toEqual({ A: 1, B: 0, C: -1, D: 0, E: 0 });
  });
});

describe('direction-aware KPI rows', () => {
  it('treats a rising lower-is-better KPI as a decline and sorts worst achievement first', () => {
    const kpi = (actual: number, achievement: number) => ({
      kpi_key: 'aht', label: 'Average Handle Time', unit: 's', direction: 'lower_better' as const,
      actual_value: actual, target_value: 360, achievement_ratio: achievement, weight_applied: 0.25, contribution: 0,
    });
    const qa = (actual: number) => ({
      kpi_key: 'qa', label: 'QA Score', unit: '%', direction: 'higher_better' as const,
      actual_value: actual, target_value: 90, achievement_ratio: actual / 90, weight_applied: 0.25, contribution: 0,
    });
    const rows = kpiRows([record(80, { kpis: [kpi(440, 0.82), qa(88)] })], [record(80, { kpis: [kpi(418, 0.86), qa(86)] })]);
    expect(rows.map((row) => row.kpi_key)).toEqual(['aht', 'qa']);
    const aht = rows[0];
    expect(aht.raw_change).toBe(22);
    expect(aht.change_value).toBe(-22);
    expect(aht.trend_status).toBe('declining');
    expect(aht.raw_gap).toBe(80);
    expect(aht.gap_value).toBe(-80);
    expect(aht.target_status).toBe('missed');
    expect(rows[1].trend_status).toBe('improving');
  });
});

describe('drivers (CoS: impact_points keeps its meaning; weighted_gap_points preferred)', () => {
  it('ranks negatives by the existing impact_points and labels the metric neutrally when weighted gap is absent', () => {
    const { drivers, items } = fixtureDrivers();
    const split = mapDrivers(drivers, items, FIXTURE_TEAM_FUNCTIONS);
    expect(split.metric).toBe('contribution_change');
    expect(split.hasWeightedGap).toBe(false);
    expect(split.negative.map((driver) => driver.kpi_label)).toEqual(['Initial Rejection %', 'Average Handle Time', 'First Call Resolution']);
    expect(split.positive.map((driver) => driver.kpi_label)).toEqual(['Clean Claim Rate', 'Denial Rate', 'Response Rate']);
    expect(split.negative[0]).toMatchObject({ team: 'Pre-Approvals IP Final', function: 'Pre-Approvals', kpi_direction: 'lower_better', raw_change: 1.6, trend_status: 'declining' });
  });

  it('ranks negatives by weighted_gap_points and positives by impact_change_points when present', () => {
    const { drivers, items } = fixtureDrivers({ weightedGap: true });
    const split = mapDrivers(drivers, items, FIXTURE_TEAM_FUNCTIONS);
    expect(split.metric).toBe('weighted_gap');
    expect(split.negative.map((driver) => driver.kpi_label)).toEqual(['Rejection', 'Initial Rejection %', 'First Call Resolution']);
    expect(split.positive.map((driver) => driver.kpi_label)).toEqual(['Clean Claim Rate', 'Denial Rate', 'Response Rate']);
  });

  it('merges a KPI × team split across positions', () => {
    const { drivers, items } = fixtureDrivers();
    const doubled = [...drivers, { ...drivers[1], scope: 'Inbound · Agent L2', impact_points: -0.5 }];
    const split = mapDrivers(doubled, items, FIXTURE_TEAM_FUNCTIONS);
    expect(split.negative[0]).toMatchObject({ kpi_label: 'Average Handle Time', impact_points: -0.81 });
  });

  it('keeps only the function’s own drivers in the function view (disjoint membership)', () => {
    const summary = compose({ view: 'function', functionName: 'Pre-Approvals' });
    expect(summary.drivers.negative.map((driver) => driver.team)).toEqual(['Pre-Approvals IP Final']);
    expect(summary.drivers.positive).toEqual([]);
  });

  it('marks drivers unavailable when the workspace was not loaded', () => {
    const summary = compose({ drivers: null });
    expect(summary.meta.unavailable).toContain('drivers');
    expect(summary.drivers).toEqual({ negative: [], positive: [] });
  });
});

describe('corrective actions summary', () => {
  it('counts due this week from today (today..+6, open only, overdue excluded) and closed in the effective month', () => {
    const result = summarizeActions(fixtureActions(TODAY), TODAY, { key: '2026-06', year: 2026, month: 'June' } as never);
    expect(result.summary).toMatchObject({ as_of: '2026-07-06', open: 7, overdue: 3, due_this_week: 3, closed_in_month: 2 });
    expect(result.actions).toHaveLength(4);
    expect(result.actions.slice(0, 3).every((action) => action.follow_up_state === 'overdue')).toBe(true);
    expect(result.actions.every((action) => action.status !== 'Completed')).toBe(true);
  });

  it('treats a due date exactly 7 days out as next week', () => {
    const result = summarizeActions([
      { id: 'a', status: 'Open', due_date: '2026-07-12' },
      { id: 'b', status: 'Open', due_date: '2026-07-13' },
      { id: 'c', status: 'Completed', due_date: '2026-07-07' },
    ], TODAY, null);
    expect(result.summary.due_this_week).toBe(1);
    expect(result.summary.closed_in_month).toBeNull();
  });
});

describe('scope', () => {
  it('managerial view: team only, filters locked, function average from all-teams records', () => {
    const summary = compose({ view: 'managerial', role: 'Manager', team: 'Inbound', comparisonRecords: records });
    expect(summary.scope).toMatchObject({ view: 'managerial', team: 'Inbound', function: 'Call Center', region: 'EGY', locked: { region: true, function: true, team: true } });
    expect(summary.teams.map((team) => team.team)).toEqual(['Inbound']);
    expect(summary.hero.comparison?.label).toBe('Call Center average');
    expect(summary.people?.bottom.length).toBeGreaterThan(0);
  });

  it('managerial view without all-teams records hides the function average instead of inventing it', () => {
    const summary = compose({ view: 'managerial', role: 'Manager', team: 'Inbound', comparisonRecords: null });
    expect(summary.hero.comparison).toBeNull();
    expect(summary.meta.unavailable).toContain('function_average');
    expect(summary.trend.every((point) => point.comparison_score === null)).toBe(true);
  });

  it('corporate filters narrow the company aggregate', () => {
    const egy = compose({ filters: { region: 'EGY' } });
    expect(egy.regions.map((region) => region.region)).toEqual(['EGY']);
    expect(egy.teams.every((team) => team.regions.includes('EGY'))).toBe(true);
  });
});
