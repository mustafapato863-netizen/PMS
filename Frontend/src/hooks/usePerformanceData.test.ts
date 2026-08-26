import { describe, expect, it } from 'vitest';
import type { AgentRecord } from '../types';
import {
  resolveAutoRootCause,
  agentMatchesLocation,
  resolveHeadcountSnapshot,
  resolveRecordGradeClass,
  reconcileTeamSummaryScore,
  resolveTeamMonths,
  mapScopedPerformanceRecord,
} from './usePerformanceData';

const baseRecord = {
  identity: { name: 'Marketing Employee', month: 'June', team: 'Marketing', employee_id: 'SGHD70001' },
  calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
  geo: {
    bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
    attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
  },
  actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
  achievement: { booking_ach: 0, attend_ach: 0 },
} satisfies Partial<AgentRecord>;

describe('resolveRecordGradeClass', () => {
  it('uses a stored A-E backend grade for Marketing', () => {
    const record = {
      ...baseRecord,
      evaluation: { score: 86, grade: 'B' },
    } as AgentRecord;
    expect(resolveRecordGradeClass(record, 86)).toBe('B');
  });

  it('uses Marketing thresholds when a Marketing record has a legacy grade label', () => {
    const record = {
      ...baseRecord,
      evaluation: { score: 87, grade: 'Meet Expectations' },
    } as AgentRecord;
    expect(resolveRecordGradeClass(record, 87)).toBe('B');
  });

  it('uses the persisted backend grade for operational teams', () => {
    const inbound = {
      ...baseRecord,
      identity: { ...baseRecord.identity, team: 'Inbound' },
      evaluation: { score: 0, grade: 'E' },
    } as AgentRecord;
    const outbound = {
      ...baseRecord,
      identity: { ...baseRecord.identity, team: 'Outbound' },
      evaluation: { score: 0, grade: 'E' },
    } as AgentRecord;

    expect(resolveRecordGradeClass(inbound, 91.3)).toBe('E');
    expect(resolveRecordGradeClass(outbound, 76.6)).toBe('E');
  });
});

describe('resolveAutoRootCause', () => {
  it('uses stored Marketing KPI achievement instead of reporting all metrics good', () => {
    const record = {
      ...baseRecord,
      evaluation: { score: 51.1, grade: 'E' },
      kpi_values: [{
        kpi_key: 'cpl',
        label: 'CPL',
        unit: 'AED',
        direction: 'lower_better',
        actual_value: 136,
        target_value: 60,
        achievement_ratio: 0.441,
        weight_applied: 0.1,
        contribution: 0.0441,
      }],
    } as AgentRecord;

    expect(resolveAutoRootCause(record, 'E')).toBe('CPL (main issue)');
  });

  it('identifies a zero target as requiring review', () => {
    const record = {
      ...baseRecord,
      evaluation: { score: 51.1, grade: 'E' },
      kpi_values: [{
        kpi_key: 'app_installs',
        label: 'App Installs',
        unit: 'count',
        direction: 'higher_better',
        actual_value: 0,
        target_value: 0,
        achievement_ratio: 0,
        weight_applied: 0.1,
        contribution: 0,
      }],
    } as AgentRecord;

    expect(resolveAutoRootCause(record, 'E')).toBe('App Installs target requires review');
  });
});

describe('resolveTeamMonths', () => {
  it('uses the selected team timeline instead of the global latest month', () => {
    const records = [
      { ...baseRecord, identity: { ...baseRecord.identity, team: 'Pre-Approvals OP Dubai', month: 'May' } },
      { ...baseRecord, identity: { ...baseRecord.identity, team: 'Pre-Approvals OP Dubai', month: 'January' } },
      { ...baseRecord, identity: { ...baseRecord.identity, team: 'Inbound UAE', month: 'June' } },
    ] as AgentRecord[];

    expect(resolveTeamMonths(records, 'Pre-Approvals OP Dubai')).toEqual(['January', 'May']);
  });
});

describe('resolveHeadcountSnapshot', () => {
  const records = [
    { ...baseRecord, identity: { ...baseRecord.identity, employee_id: 'EMP-1', team: 'Inbound', month: 'May' } },
    { ...baseRecord, identity: { ...baseRecord.identity, employee_id: 'EMP-1', team: 'Inbound', month: 'May' } },
    { ...baseRecord, identity: { ...baseRecord.identity, employee_id: 'EMP-2', team: 'Sales', month: 'May' } },
    { ...baseRecord, identity: { ...baseRecord.identity, employee_id: 'EMP-1', team: 'Inbound', month: 'June' } },
    { ...baseRecord, identity: { ...baseRecord.identity, employee_id: 'EMP-3', team: 'Coding', month: 'June' } },
  ] as AgentRecord[];

  it('uses distinct employees and teams from the latest available month for All Months', () => {
    expect(resolveHeadcountSnapshot(records, 'All')).toEqual({
      month: 'June',
      totalAgents: 2,
      uniqueTeamCount: 2,
    });
  });

  it('uses only the selected month and does not accumulate historical records', () => {
    expect(resolveHeadcountSnapshot(records, 'May')).toEqual({
      month: 'May',
      totalAgents: 2,
      uniqueTeamCount: 2,
    });
  });
});

describe('reconcileTeamSummaryScore', () => {
  it('falls back to the actual employee score average when a pooled score is out of scale', () => {
    expect(reconcileTeamSummaryScore(9.3, [98.5, 95.2, 99.3, 80.5, 100])).toBeCloseTo(94.7, 5);
  });

  it('keeps a pooled score when it agrees with the employee scores', () => {
    expect(reconcileTeamSummaryScore(95.1, [94, 96])).toBe(95.1);
  });
});

describe('agentMatchesLocation', () => {
  it('honors the source Team branch before synthesized geo totals', () => {
    const ajman = {
      ...baseRecord,
      identity: { ...baseRecord.identity, team: 'Pre-Approvals OP Final SHJAJM' },
      raw_data: { Team: 'AJM' },
      geo: {
        bookings: { dubai: 10, sharjah: 10, ajman: 10, clinics: 0 },
        attended: { dubai: 10, sharjah: 10, ajman: 10, clinics: 0 },
      },
      evaluation: { score: 0, grade: 'E' },
    } as AgentRecord;

    expect(agentMatchesLocation(ajman, 'ajman')).toBe(true);
    expect(agentMatchesLocation(ajman, 'sharjah')).toBe(false);
    expect(agentMatchesLocation(ajman, 'dubai')).toBe(false);
  });
});

describe('mapScopedPerformanceRecord', () => {
  it('maps the bounded REST detail contract into the legacy dashboard model', () => {
    const record = mapScopedPerformanceRecord({
      id: 'record-1',
      employee_id: 'EMP-1',
      employee_name: 'Bounded Employee',
      team: 'Inbound',
      month: 'June',
      year: 2026,
      region: 'UAE',
      performance_level: 'Employee',
      position: 'Agent',
      status: 'Meets',
      score: 91,
      grade: 'A',
      previous_score: 87,
      trend: 4,
      calls: { inbound: 10, outbound: 2, total_handled: 12, abandoned: 1, aht_raw: '00:05:00' },
      geo: {
        bookings: { dubai: 4, sharjah: 0, ajman: 0, clinics: 0 },
        attended: { dubai: 3, sharjah: 0, ajman: 0, clinics: 0 },
      },
      actual: { booking_rate: 0.4, attend_rate: 0.75, abandon_rate: 0.08 },
      achievement: { booking_ach: 1, attend_ach: 0.9 },
      evaluation: { score: 91, grade: 'A' },
      raw_data: { Team: 'Dubai' },
      kpi_values: [],
    });

    expect(record.identity).toMatchObject({
      employee_id: 'EMP-1',
      name: 'Bounded Employee',
      month: 'June',
      team: 'Inbound',
    });
    expect(record.evaluation.score).toBe(91);
    expect(record.geo.bookings.dubai).toBe(4);
    expect(record.calls.total_handled).toBe(12);
  });
});
