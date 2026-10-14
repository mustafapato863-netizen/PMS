import { describe, expect, it } from 'vitest';
import { kpiRows, type ExecRecord } from './compose';

// Synthetic Pre-Approvals IP Offshore employee-months: three scored KPIs and the
// tracking-only PolicyRejection row (stored weight 0).
const kpi = (key: string, weight: number, actual: number, target: number, achievement: number) => ({
  kpi_key: key,
  label: key,
  unit: '%',
  direction: key === 'Submission' ? 'higher_better' : 'lower_better',
  actual_value: actual,
  target_value: target,
  weight_applied: weight,
  achievement_ratio: achievement,
  contribution: achievement * weight,
});

const offshoreRecord = (): ExecRecord => ({
  team: 'Pre-Approvals IP Offshore',
  kpis: [
    kpi('Rejection', 0.5, 0.0026, 0.01, 1),
    kpi('InitialError', 0.2, 0.0163, 0.01, 0.615),
    kpi('Submission', 0.3, 0.789, 0.9, 0.877),
    kpi('PolicyRejection', 0, 0.0002, 0, 0),
  ],
} as unknown as ExecRecord);

describe('Departmental KPI rows list only the KPIs that count in the score', () => {
  it('drops the tracking-only PolicyRejection row and keeps the three scored KPIs', () => {
    const rows = kpiRows([offshoreRecord()], []);
    expect(rows.map((row) => row.kpi_key).sort()).toEqual(['InitialError', 'Rejection', 'Submission']);
  });

  it('keeps the remaining weights at 100%', () => {
    const rows = kpiRows([offshoreRecord()], []);
    const total = rows.reduce((sum, row) => sum + (row.weight ?? 0), 0);
    expect(total).toBeCloseTo(1, 10);
  });

  it('drops a KPI that is not applicable for an employee-month (weight 0) and keeps it for others', () => {
    const notApplicable = { ...offshoreRecord(), kpis: [kpi('InitialError', 0, 0, 0.01, 0), kpi('Rejection', 0.5, 0.0026, 0.01, 1)] } as unknown as ExecRecord;
    const rows = kpiRows([notApplicable], []);
    expect(rows.map((row) => row.kpi_key)).toEqual(['Rejection']);
  });
});
