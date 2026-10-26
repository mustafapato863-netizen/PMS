import { describe, expect, it } from 'vitest';
import type { ExecRecord } from '../executive/compose';
import { buildTeamDeepDiveFromRecords } from './teamDeepDiveData';

const september = { year: 2026, month: 'September', key: '2026-09' };

function kpi(
  key: string,
  label: string,
  actual: number,
  target: number,
  direction: 'higher_better' | 'lower_better',
  ratio: number,
): ExecRecord['kpis'][number] {
  return {
    kpi_key: key,
    label,
    unit: 'percent',
    direction,
    actual_value: actual,
    target_value: target,
    achievement_ratio: ratio,
    weight_applied: 0.4,
    contribution: 1,
  };
}

function person(employeeId: string, name: string, score: number, kpis: ExecRecord['kpis']): ExecRecord {
  return {
    employeeId,
    name,
    team: 'Pre-Approvals IP',
    region: 'EGY',
    position: 'Specialist',
    level: 'Employee',
    branches: [],
    period: september,
    score,
    kpis,
  };
}

describe('generic team deep dive agent KPIs', () => {
  it('shows each measured KPI on the agent row instead of a dash', () => {
    const dive = buildTeamDeepDiveFromRecords('pre-approvals-ip', [
      person('ali', 'Ali Mohamed', 74.8, [
        kpi('error', 'Error %', 2.1, 5, 'lower_better', 0.4),
        kpi('approval', 'Approval within 48 hrs', 70.4, 90, 'higher_better', 0.78),
      ]),
      person('hadeer', 'Hadeer Gamal', 86.5, [
        kpi('error', 'Error %', 0.4, 5, 'lower_better', 1),
        kpi('approval', 'Approval within 48 hrs', 59.6, 90, 'higher_better', 0.66),
      ]),
    ], [], 'EGY', '2026-09');

    const ali = dive.agentsAverageOrBelow.find((agent) => agent.employeeId === 'ali');
    const hadeer = dive.agentsAverageOrBelow.find((agent) => agent.employeeId === 'hadeer');
    expect(ali?.kpiCells.map((cell) => cell.actualFormatted)).toEqual(['2.1%', '70.4%']);
    expect(hadeer?.kpiCells.map((cell) => cell.actualFormatted)).toEqual(['0.4%', '59.6%']);
    expect(ali?.kpiCells.find((cell) => cell.kpiKey === 'error')?.metTarget).toBe(true);
    expect(hadeer?.kpiCells.find((cell) => cell.kpiKey === 'approval')?.metTarget).toBe(false);

    const error = dive.kpis.find((item) => item.kpiKey === 'error');
    const approval = dive.kpis.find((item) => item.kpiKey === 'approval');
    expect(error?.agentsMeetingTarget).toBe(2);
    expect(approval?.agentsMeetingTarget).toBe(0);
  });
});
