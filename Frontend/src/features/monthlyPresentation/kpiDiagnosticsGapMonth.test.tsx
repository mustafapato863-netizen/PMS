import { describe, expect, it } from 'vitest';
import { buildCallCenterDeepDiveFromRecords } from './callCenterDeepDiveData';
import type { ExecRecord } from '../executive/compose';

function makeRecord(
  employeeId: string,
  team: 'Inbound' | 'Outbound',
  periodKey: string,
  monthName: string,
  year: number,
  score: number,
  bookingActual: number,
): ExecRecord {
  return {
    employeeId,
    name: employeeId,
    team,
    region: 'EGY',
    position: 'Specialist',
    level: 'Employee',
    branches: [],
    period: { year, month: monthName, key: periodKey },
    score,
    kpis: [
      {
        kpi_key: 'Booking',
        label: 'Booking Rate',
        unit: 'percent',
        direction: 'higher_better',
        actual_value: bookingActual,
        target_value: 95,
        achievement_ratio: bookingActual / 95,
        weight_applied: 0.4,
        contribution: 1,
      },
    ],
  };
}

describe('KPI diagnostics never span a missing calendar month (Item 3b)', () => {
  it('shows "No previous-month data" on the Booking KPI card when September is missing, even though August was measured', () => {
    const records: ExecRecord[] = [
      // August: Booking 70. September: no records at all.
      makeRecord('inb1', 'Inbound', '2026-08', 'August', 2026, 80, 70),
      makeRecord('out1', 'Outbound', '2026-08', 'August', 2026, 80, 70),
      // October: Booking 90 — a +20 jump vs August, but August is not the
      // previous calendar month, so no month-over-month change may be shown.
      makeRecord('inb1', 'Inbound', '2026-10', 'October', 2026, 90, 90),
      makeRecord('out1', 'Outbound', '2026-10', 'October', 2026, 84, 90),
    ];
    const dive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-10');
    const booking = dive.keyKpis.find((kpi) => kpi.kpiKey === 'Booking');
    expect(booking).toBeDefined();
    expect(booking!.trendLabel).toBe('No previous-month data');
    expect(booking!.trendLabel).not.toContain('August');
    expect(booking!.trendLabel).not.toContain('▲');
    // The tone must not claim "Improving" on a change computed across the gap.
    expect(booking!.trendTone).not.toBe('positive');
  });

  it('shows the measured change vs September when September is measured', () => {
    const records: ExecRecord[] = [
      makeRecord('inb1', 'Inbound', '2026-09', 'September', 2026, 80, 70),
      makeRecord('out1', 'Outbound', '2026-09', 'September', 2026, 80, 70),
      makeRecord('inb1', 'Inbound', '2026-10', 'October', 2026, 90, 90),
      makeRecord('out1', 'Outbound', '2026-10', 'October', 2026, 84, 90),
    ];
    const dive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-10');
    const booking = dive.keyKpis.find((kpi) => kpi.kpiKey === 'Booking');
    expect(booking).toBeDefined();
    expect(booking!.trendLabel).toContain('vs September');
    expect(booking!.trendLabel).toContain('▲');
    expect(booking!.trendTone).toBe('positive');
  });
});
