import { describe, expect, it } from 'vitest';
import type { AgentRecord } from '../../types';
import { composeExecutiveSummary, gradeDistribution, hasRealActivity, toExecRecords } from './compose';
import { actionPeriodKey, actionsInActivePeriod } from './actionAnalytics';

/** An employee-month with nothing above zero; each test switches on one field. */
function employeeMonth(overrides: Record<string, unknown> = {}, identity: Record<string, unknown> = {}): AgentRecord {
  const zeroGeo = { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 };
  return {
    identity: { name: 'Test Agent', month: 'August', team: 'Outbound', employee_id: 'TA-T-01', ...identity },
    year: 2026,
    region: 'EGY',
    performance_level: 'Employee',
    evaluation: { score: 0, grade: 'E' },
    calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
    geo: { bookings: { ...zeroGeo }, attended: { ...zeroGeo } },
    kpi_values: [],
    raw_data: {},
    ...overrides,
  } as unknown as AgentRecord;
}

describe('hasRealActivity (server rule, performance_dashboard_read_service.py)', () => {
  it('treats an employee-month with nothing above zero as inactive', () => {
    expect(hasRealActivity(employeeMonth())).toBe(false);
  });

  it('counts a positive score as activity', () => {
    expect(hasRealActivity(employeeMonth({ evaluation: { score: 88, grade: 'C' } }))).toBe(true);
  });

  it('counts a KPI contribution above zero as activity', () => {
    expect(hasRealActivity(employeeMonth({ kpi_values: [{ kpi_key: 'quality', contribution: 2 }] }))).toBe(true);
  });

  it('counts a call above zero as activity', () => {
    expect(hasRealActivity(employeeMonth({ calls: { inbound: 3, outbound: 0, total_handled: 0, abandoned: 0 } }))).toBe(true);
  });

  it('counts a geo booking or attendance above zero as activity', () => {
    expect(hasRealActivity(employeeMonth({ geo: { bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 1 }, attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 } } }))).toBe(true);
  });

  it('counts a numeric raw value above zero, but not a text value', () => {
    expect(hasRealActivity(employeeMonth({ raw_data: { Branch: 'Dubai' } }))).toBe(false);
    expect(hasRealActivity(employeeMonth({ raw_data: { Attendance: '4' } }))).toBe(true);
  });

  it('never counts a row named total, even with a score', () => {
    expect(hasRealActivity(employeeMonth({ evaluation: { score: 90, grade: 'B' } }, { name: 'Total' }))).toBe(false);
  });

  it('does not count a negative value as activity', () => {
    expect(hasRealActivity(employeeMonth({ evaluation: { score: -5, grade: 'E' } }))).toBe(false);
  });
});

describe('inactive employee-months in the browser composition', () => {
  it('leaves inactive rows out of toExecRecords', () => {
    const records = toExecRecords([
      employeeMonth({ evaluation: { score: 80, grade: 'C' } }),
      employeeMonth({}, { employee_id: 'TA-T-02' }),
    ]);
    expect(records.map((record) => record.employeeId)).toEqual(['TA-T-01']);
  });

  it('counts only active people and their average in the summary', () => {
    const summary = composeExecutiveSummary({
      view: 'corporate',
      role: 'Admin',
      records: toExecRecords([
        employeeMonth({ evaluation: { score: 90, grade: 'B' } }),
        employeeMonth({}, { employee_id: 'TA-T-02' }),
      ]),
      filters: {},
      today: new Date(2026, 7, 13),
    });
    expect(summary.hero.employees).toBe(1);
    expect(summary.hero.score).toBe(90);
    expect(summary.grade_distribution?.total).toBe(1);
  });

  it('reports an empty scope when every row in it is inactive', () => {
    const summary = composeExecutiveSummary({
      view: 'corporate',
      role: 'Admin',
      records: toExecRecords([employeeMonth(), employeeMonth({}, { employee_id: 'TA-T-02' })]),
      filters: {},
      today: new Date(2026, 7, 13),
    });
    expect(summary.data_status.has_data).toBe(false);
    expect(summary.hero.employees).toBe(0);
  });
});

describe('combined grade shares', () => {
  it('computes D + E from the counts and rounds once', () => {
    // One E (66), one D (74), one B (90): D + E = 2 of 3 = 66.7. Adding the rounded
    // per-grade shares (33.3 + 33.3) would give 66.6.
    const records = toExecRecords([
      employeeMonth({ evaluation: { score: 66, grade: 'E' } }, { employee_id: 'TA-T-01' }),
      employeeMonth({ evaluation: { score: 74, grade: 'D' } }, { employee_id: 'TA-T-02' }),
      employeeMonth({ evaluation: { score: 90, grade: 'B' } }, { employee_id: 'TA-T-03' }),
    ]);
    const distribution = gradeDistribution(records, []);
    expect(distribution?.percents.D).toBe(33.3);
    expect(distribution?.percents.E).toBe(33.3);
    expect(distribution?.combined_percents).toEqual({ AB: 33.3, DE: 66.7 });
  });
});

describe('action period (year and month)', () => {
  it('reads a stored YYYY-MM directly', () => {
    expect(actionPeriodKey({ month: '2026-07', created_at: null })).toBe('2026-07');
  });

  it('takes the year of a month-name action from created_at', () => {
    expect(actionPeriodKey({ month: 'July', created_at: '2025-07-09T00:00:00' })).toBe('2025-07');
  });

  it('returns null for a month-name action with no usable date', () => {
    expect(actionPeriodKey({ month: 'July', created_at: null })).toBeNull();
  });

  it('uses created_at when the month is empty', () => {
    expect(actionPeriodKey({ month: '', created_at: '2026-07-15T00:00:00' })).toBe('2026-07');
  });

  it('keeps only the actions of the active year and month', () => {
    const actions = [
      { id: 'july-2026', month: 'July', created_at: '2026-07-15T00:00:00' },
      { id: 'july-2025', month: 'July', created_at: '2025-07-09T00:00:00' },
      { id: 'july-undated', month: 'July', created_at: null },
      { id: 'august-2026', month: 'August', created_at: '2026-08-12T00:00:00' },
    ];
    expect(actionsInActivePeriod(actions, 'July', '2026-07').map((action) => action.id)).toEqual(['july-2026', 'july-undated']);
  });

  it('falls back to the month name when the page has no period key', () => {
    const actions = [
      { id: 'july-2026', month: 'July', created_at: '2026-07-15T00:00:00' },
      { id: 'july-2025', month: 'July', created_at: '2025-07-09T00:00:00' },
    ];
    expect(actionsInActivePeriod(actions, 'July', null).map((action) => action.id)).toEqual(['july-2026', 'july-2025']);
  });
});
