import { describe, expect, it } from 'vitest';
import type { AgentRecord } from '../../types';
import { mergeEmployeeHistory, type EmployeeHistoryRecord } from './employeeProfileHistory';

const record = (month: string, score: number, year = 2026): AgentRecord => ({
  year,
  identity: { name: 'Agent', employee_id: 'EMP-1', team: 'Outbound', month },
  calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
  geo: {
    bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
    attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
  },
  actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
  achievement: { booking_ach: 0, attend_ach: 0 },
  evaluation: { score, grade: 'B' },
});

describe('mergeEmployeeHistory', () => {
  it('keeps every cached month when the profile response is empty', () => {
    const result = mergeEmployeeHistory('EMP-1', [record('May', 91), record('June', 92)], []);

    expect(result.map((item) => item.month)).toEqual(['June', 'May']);
  });

  it('prefers the canonical profile record for a duplicate period', () => {
    const profileJune = {
      ...record('June', 95),
      month: 'June',
      kpi_values: [{
        kpi_key: 'reachability',
        label: 'Reachability',
        unit: '%',
        direction: 'higher_better' as const,
        actual_value: 0.8,
        target_value: 0.75,
        achievement_ratio: 1,
        weight_applied: 0.2,
        contribution: 0.2,
      }],
    } as EmployeeHistoryRecord;

    const [result] = mergeEmployeeHistory('EMP-1', [record('June', 92)], [profileJune]);

    expect(result.evaluation.score).toBe(95);
    expect(result.kpi_values).toHaveLength(1);
  });
});
