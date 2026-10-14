import { describe, expect, it } from 'vitest';
import { collapseRange, composeExecutiveSummary, monthsBetween, periodOf, previousRangeOf, type ComposeInput, type ExecRecord } from './compose';
import { presetIdFor, readRangeSelection, rangeMonthKeys, rangePresets, rangeRequestIsInvalid } from './rangeParams';

const TODAY = new Date(2026, 8, 20);

/** Synthetic employee-month rows: one row per employee and month, all in team Inbound, region UAE. */
function row(employeeId: string, month: string, score: number, team = 'Inbound'): ExecRecord {
  return {
    employeeId,
    name: `Person ${employeeId}`,
    team,
    region: 'UAE',
    position: 'Agent L1',
    level: 'Employee',
    period: periodOf(2026, month),
    score,
    kpis: [],
  };
}

const JUNE = periodOf(2026, 'June');
const SEPTEMBER = periodOf(2026, 'September');

function compose(records: ExecRecord[], patch: Partial<ComposeInput> = {}) {
  return composeExecutiveSummary({
    view: 'corporate', role: 'Admin', records, filters: {}, today: TODAY, comparisonRecords: records, ...patch,
  });
}

describe('range mode, person-first', () => {
  it('weighs each person once: a person with one month counts as much as a person with three', () => {
    // A: one counted month, 80. B: three counted months, all 60. Person-first: (80 + 60) / 2 = 70.
    // A plain mean of the rows would give (80 + 60 * 3) / 4 = 65.
    const records = [
      row('A', 'September', 80),
      row('B', 'July', 60), row('B', 'August', 60), row('B', 'September', 60),
    ];

    const summary = compose(records, { range: { months: monthsBetween(periodOf(2026, 'July'), SEPTEMBER), previousMonths: [] } });

    expect(summary.hero.score).toBe(70);
    expect(summary.hero.employees).toBe(2);
    expect(summary.people?.top.find((person) => person.employee_id === 'B')?.months).toBe(3);
    expect(summary.people?.top.find((person) => person.employee_id === 'A')?.months).toBe(1);
  });

  it('grades a person from the average of their months, so a boundary crossing is graded on the average', () => {
    // C: 94 in June and 96 in July. Monthly grades are B then A; the range average 95 is grade A.
    const records = [row('C', 'June', 94), row('C', 'July', 96), row('D', 'July', 84)];

    const summary = compose(records, { range: { months: monthsBetween(JUNE, periodOf(2026, 'July')), previousMonths: [] } });

    const person = summary.people?.top.find((item) => item.employee_id === 'C');
    expect(person?.score).toBe(95);
    expect(person?.grade).toBe('A');
    expect(summary.grade_distribution?.counts.A).toBe(1);
    expect(summary.grade_distribution?.counts.C).toBe(1);
    expect(summary.grade_distribution?.total).toBe(2);
  });

  it('leaves an empty month inside the range out of a person\'s average and counts the months with data', () => {
    // D has June and September only. July and August are empty for everyone, so D averages 2 months.
    const records = [row('D', 'June', 70), row('D', 'September', 90), row('E', 'June', 80)];

    const summary = compose(records, { range: { months: monthsBetween(JUNE, SEPTEMBER), previousMonths: [] } });

    expect(summary.people?.top.find((person) => person.employee_id === 'D')).toMatchObject({ score: 80, months: 2 });
    expect(summary.period.range?.months).toHaveLength(4);
    expect(summary.period.range?.months_with_data).toBe(2);
  });

  it('reports no comparison when the previous range has no counted data', () => {
    const records = [row('A', 'September', 80)];

    const summary = compose(records, {
      range: { months: monthsBetween(periodOf(2026, 'July'), SEPTEMBER), previousMonths: monthsBetween(periodOf(2026, 'April'), periodOf(2026, 'June')) },
    });

    expect(summary.period.previous).toBeNull();
    expect(summary.period.range?.previous).toBeNull();
    expect(summary.hero.previous_score).toBeNull();
    expect(summary.hero.change).toBeNull();
  });

  it('compares with the previous range of the same length', () => {
    const records = [row('A', 'September', 80), row('A', 'August', 70), row('A', 'July', 70), row('A', 'June', 60)];

    const months = monthsBetween(periodOf(2026, 'July'), SEPTEMBER);
    const summary = compose(records, { range: { months, previousMonths: previousRangeOf(months) } });

    expect(summary.hero.score).toBe(73.3);
    expect(summary.hero.previous_score).toBe(60);
    expect(summary.period.range?.previous?.start.month).toBe('April');
  });

  it('keeps the one-month range identical to the month view', () => {
    const records = [
      row('A', 'August', 71), row('A', 'September', 83),
      row('B', 'August', 64), row('B', 'September', 77),
      row('C', 'September', 92, 'Outbound'),
    ];

    const month = compose(records, { requestedPeriodKey: '2026-09' });
    const range = compose(records, { range: { months: [SEPTEMBER], previousMonths: [periodOf(2026, 'August')] } });

    expect(range.hero.score).toBe(month.hero.score);
    expect(range.hero.previous_score).toBe(month.hero.previous_score);
    expect(range.hero.change).toBe(month.hero.change);
    expect(range.hero.employees).toBe(month.hero.employees);
    expect(range.teams.map((team) => [team.team, team.score, team.grade])).toEqual(month.teams.map((team) => [team.team, team.score, team.grade]));
    expect(range.grade_distribution?.counts).toEqual(month.grade_distribution?.counts);
    expect(range.people?.top.map((person) => [person.employee_id, person.score])).toEqual(month.people?.top.map((person) => [person.employee_id, person.score]));
    expect(range.regions).toEqual(month.regions);
    expect(range.levels).toEqual(month.levels);
    expect(range.basis_context).toEqual(month.basis_context);
  });

  it('shows a target only when it is the same for every person and month, otherwise marks it as varying', () => {
    const withTarget = (employeeId: string, month: string, target: number): ExecRecord => ({
      ...row(employeeId, month, 80),
      kpis: [{ kpi_key: 'aht', label: 'AHT', direction: 'lower_better', unit: 's', actual_value: 400, target_value: target, weight_applied: 0.5, achievement_ratio: 1, contribution: 50 }],
    });
    const same = compose([withTarget('A', 'June', 300), withTarget('A', 'July', 300)], { range: { months: monthsBetween(JUNE, periodOf(2026, 'July')), previousMonths: [] } });
    const varies = compose([withTarget('A', 'June', 300), withTarget('A', 'July', 280)], { range: { months: monthsBetween(JUNE, periodOf(2026, 'July')), previousMonths: [] } });

    expect(same.kpis[0]).toMatchObject({ target: 300, target_varies: false });
    expect(varies.kpis[0]).toMatchObject({ target: null, target_varies: true });
  });

  it('collapses one person into one record at the range\'s last month', () => {
    const collapsed = collapseRange([row('A', 'June', 70), row('A', 'July', 90)], monthsBetween(JUNE, periodOf(2026, 'July')), periodOf(2026, 'July'));

    expect(collapsed).toHaveLength(1);
    expect(collapsed[0]).toMatchObject({ score: 80, months: 2 });
    expect(collapsed[0].period.key).toBe('2026-07');
  });
});

describe('range selection in the URL', () => {
  it('reads from and to, both inclusive, and round-trips them', () => {
    const selection = readRangeSelection(new URLSearchParams('from=2026-06&to=2026-09'));

    expect(selection).toEqual({ from: '2026-06', to: '2026-09' });
    expect(rangeMonthKeys(selection!)).toEqual(['2026-06', '2026-07', '2026-08', '2026-09']);
  });

  it('treats From after To, or a malformed month, as no range', () => {
    expect(readRangeSelection(new URLSearchParams('from=2026-09&to=2026-06'))).toBeNull();
    expect(readRangeSelection(new URLSearchParams('from=2026-13&to=2026-09'))).toBeNull();
    expect(rangeRequestIsInvalid(new URLSearchParams('from=2026-09&to=2026-06'))).toBe(true);
    expect(rangeRequestIsInvalid(new URLSearchParams('period=2026-09'))).toBe(false);
  });

  it('builds the presets from the anchor month, the quarter of its year and year to date', () => {
    const presets = Object.fromEntries(rangePresets('2026-09').map((preset) => [preset.id, [preset.selection.from, preset.selection.to]]));

    expect(presets.last3).toEqual(['2026-07', '2026-09']);
    expect(presets.last6).toEqual(['2026-04', '2026-09']);
    expect(presets.q3).toEqual(['2026-07', '2026-09']);
    expect(presets.q1).toEqual(['2026-01', '2026-03']);
    expect(presets.ytd).toEqual(['2026-01', '2026-09']);
    expect(presetIdFor({ from: '2026-07', to: '2026-09' }, '2026-09')).toBe('last3');
    expect(presetIdFor({ from: '2026-06', to: '2026-09' }, '2026-09')).toBeNull();
  });

  it('computes the previous range of the same length', () => {
    expect(previousRangeOf([JUNE, periodOf(2026, 'July'), periodOf(2026, 'August'), SEPTEMBER]).map((period) => period.key))
      .toEqual(['2026-02', '2026-03', '2026-04', '2026-05']);
  });
});
