import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ThemeProvider } from '../../context/ThemeContext';
import { calculateAggregatedTeamPerformance } from '../../features/team/teamKpiAggregator';
import { mapScopedPerformanceRecord } from '../../hooks/usePerformanceData';
import { validateTeamConfig } from '../../schemas/teamConfig.schema';
import type { AgentRecord } from '../../types';
import TeamKpiSection from './TeamKpiSection';

const outboundFile = validateTeamConfig(JSON.parse(readFileSync(
  resolve(process.cwd(), '../Backend/config/teams/outbound.json'),
  'utf8',
)));

const SMALL_ATTENDANCE_POINTS = (0.01 / 0.7) * 0.5 * 100;
const ORDINARY_ATTENDANCE_POINTS = (0.5 / 0.7) * 0.5 * 100;
const PRODUCTIVITY_ACTUAL = 0.7780694444444445;
const PRODUCTIVITY_POINTS = (PRODUCTIVITY_ACTUAL / 0.8) * 0.2 * 100;
const SMALL_PRODUCTIVITY_POINTS = (0.004 / 0.8) * 0.2 * 100;

function pinnedAgent(options: {
  id: string;
  attendActual: number;
  attendTarget?: number;
  bookings: number;
  attended: number;
  productivity?: { actual: number; target: number; weight: number };
}): AgentRecord {
  const attendTarget = options.attendTarget ?? 0.7;
  const attendWeight = 0.5;
  const kpiValues = [
    {
      kpi_key: 'Attendance',
      label: 'Attendance Rate',
      unit: '%',
      actual_value: options.attendActual,
      target_value: attendTarget,
      achievement_ratio: attendTarget > 0 ? options.attendActual / attendTarget : 0,
      weight_applied: attendWeight,
      contribution: attendTarget > 0 ? (options.attendActual / attendTarget) * attendWeight : 0,
      direction: 'higher_better' as const,
      evaluation_pinned: true,
    },
  ];
  if (options.productivity) {
    const { actual, target, weight } = options.productivity;
    kpiValues.push({
      kpi_key: 'Productivity',
      label: 'Productivity',
      unit: '%',
      actual_value: actual,
      target_value: target,
      achievement_ratio: target > 0 ? actual / target : 0,
      weight_applied: weight,
      contribution: target > 0 ? (actual / target) * weight : 0,
      direction: 'higher_better',
      evaluation_pinned: true,
    });
  }
  return mapScopedPerformanceRecord({
    id: options.id,
    employee_id: options.id,
    employee_name: 'Anonymous contribution',
    team: 'Outbound',
    month: 'August',
    year: 2026,
    performance_level: 'Employee',
    score: 0,
    raw_data: {
      'A.Attend%': options.attendActual,
      'T.Attend%': 0.65,
      ...(options.productivity
        ? { Productivity: options.productivity.actual, 'T.Productivity%': options.productivity.target }
        : {}),
    },
    geo: {
      bookings: { dubai: options.bookings, sharjah: 0, ajman: 0, clinics: 0 },
      attended: { dubai: options.attended, sharjah: 0, ajman: 0, clinics: 0 },
    },
    kpi_values: kpiValues,
  });
}

function renderTeam(agents: AgentRecord[]) {
  const rollup = calculateAggregatedTeamPerformance(agents, outboundFile);
  expect(rollup).not.toBeNull();
  const dynamicKpis = [...rollup!.kpis.values()];
  render(
    <ThemeProvider>
      <TeamKpiSection
        totalAgents={agents.length}
        avgScore={rollup!.score}
        pctAB={0}
        pctDE={100}
        classCounts={{ A: 0, B: 0, C: 0, D: 0, E: agents.length }}
        isCallCenterView
        isInbound={false}
        teamId="outbound"
        teamName="Outbound"
        month="August"
        teamMetrics={{
          attendCR: 1,
          bookingCR: 0,
          avgAHT: '0:00',
          avgAHTSec: 0,
          abandonRate: 0,
          reachabilityRate: 0,
          totalBookings: 100,
          totalAttended: 1,
          totalCallsHandled: 100,
          totalAbandoned: 0,
          utzRate: 0,
          hasUtz: false,
          dynamicKpis,
        }}
        prevTeamMetrics={null}
        avgAHTSec={0}
        teamWeights={{ Attend: 0.7 }}
      />
    </ThemeProvider>,
  );
  return { rollup: rollup!, dynamicKpis };
}

describe('TeamKpiSection canonical contribution display', () => {
  it('shows a sub-one attendance point and a sub-one productivity point without clamping them to the weight', () => {
    const agent = pinnedAgent({
      id: 'anonymous-small',
      attendActual: 0.01,
      bookings: 100,
      attended: 1,
      productivity: { actual: 0.004, target: 0.8, weight: 0.2 },
    });
    const { rollup, dynamicKpis } = renderTeam([agent]);
    const attendance = dynamicKpis.find((kpi) => kpi.label.includes('Attendance'));
    const productivity = dynamicKpis.find((kpi) => kpi.label === 'Productivity');

    expect(agent.raw_data?.['T.Attend%']).toBe(0.65);
    expect(agent.kpi_values?.[0].contribution).toBeCloseTo((0.01 / 0.7) * 0.5, 12);
    expect(attendance?.target).toBe(0.7);
    expect(attendance?.weight).toBe(0.5);
    expect(attendance?.contribution).toBeCloseTo(SMALL_ATTENDANCE_POINTS, 12);
    expect(productivity?.weight).toBe(0.2);
    expect(productivity?.contribution).toBeCloseTo(SMALL_PRODUCTIVITY_POINTS, 12);
    expect(rollup.score).toBeCloseTo(SMALL_ATTENDANCE_POINTS + SMALL_PRODUCTIVITY_POINTS, 12);

    const attendanceCard = screen.getByText('Patient Attendance Rate').closest('article');
    expect(attendanceCard).toHaveTextContent('Contribution0.7%');
    expect(attendanceCard).toHaveTextContent('Weight50%');
    expect(attendanceCard).not.toHaveTextContent('Contribution50.0%');
    expect(attendanceCard).not.toHaveTextContent('Weight70%');

    const productivityCard = screen.getByText('Productivity').closest('article');
    expect(productivityCard).toHaveTextContent('Contribution0.1%');
    expect(productivityCard).toHaveTextContent('Weight20%');
    expect(productivityCard).not.toHaveTextContent('Contribution10.0%');
    expect(productivityCard).not.toHaveTextContent('Contribution20.0%');
  });

  it('shows a canonical contribution of exactly one score point as 1.0%', () => {
    const { dynamicKpis } = renderTeam([
      pinnedAgent({
        id: 'anonymous-one-point',
        attendActual: 0.014,
        bookings: 1000,
        attended: 14,
      }),
    ]);
    const attendance = dynamicKpis.find((kpi) => kpi.label.includes('Attendance'));
    expect(attendance?.contribution).toBeCloseTo(1, 8);
    expect(attendance?.weight).toBe(0.5);

    const card = screen.getByText('Patient Attendance Rate').closest('article');
    expect(card).toHaveTextContent(`Contribution${attendance!.contribution!.toFixed(1)}%`);
    expect(card).toHaveTextContent('Contribution1.0%');
    expect(card).toHaveTextContent('Weight50%');
    expect(card).not.toHaveTextContent('Contribution50.0%');
  });

  it('shows a canonical zero contribution as 0.0% and keeps the applied weight', () => {
    const agent = pinnedAgent({
      id: 'anonymous-zero',
      attendActual: 0,
      bookings: 100,
      attended: 0,
    });
    const { rollup, dynamicKpis } = renderTeam([agent]);
    const attendance = dynamicKpis.find((kpi) => kpi.label.includes('Attendance'));

    expect(attendance?.contribution).toBe(0);
    expect(attendance?.weight).toBe(0.5);
    expect(rollup.score).toBe(0);
    expect(agent.kpi_values?.[0].contribution).toBe(0);

    const card = screen.getByText('Patient Attendance Rate').closest('article');
    expect(card).toHaveTextContent('Contribution0.0%');
    expect(card).toHaveTextContent('Weight50%');
    expect(card).not.toHaveTextContent('Contribution—');
  });

  it('shows an ordinary contribution above one point on the same score-point scale', () => {
    const { rollup, dynamicKpis } = renderTeam([
      pinnedAgent({
        id: 'anonymous-ordinary',
        attendActual: 0.5,
        bookings: 100,
        attended: 50,
        productivity: { actual: PRODUCTIVITY_ACTUAL, target: 0.8, weight: 0.2 },
      }),
    ]);
    const attendance = dynamicKpis.find((kpi) => kpi.label.includes('Attendance'));
    const productivity = dynamicKpis.find((kpi) => kpi.label === 'Productivity');

    expect(attendance?.contribution).toBeCloseTo(ORDINARY_ATTENDANCE_POINTS, 12);
    expect(attendance?.target).toBe(0.7);
    expect(attendance?.weight).toBe(0.5);
    expect(productivity?.contribution).toBeCloseTo(PRODUCTIVITY_POINTS, 12);
    expect(productivity?.weight).toBe(0.2);
    expect(rollup.score).toBeCloseTo(ORDINARY_ATTENDANCE_POINTS + PRODUCTIVITY_POINTS, 12);

    const attendanceCard = screen.getByText('Patient Attendance Rate').closest('article');
    expect(attendanceCard).toHaveTextContent(`Contribution${attendance!.contribution!.toFixed(1)}%`);
    expect(attendanceCard).toHaveTextContent('Weight50%');

    const productivityCard = screen.getByText('Productivity').closest('article');
    expect(productivityCard).toHaveTextContent(`Contribution${productivity!.contribution!.toFixed(1)}%`);
    expect(productivityCard).toHaveTextContent('Weight20%');
  });

  it('keeps a varied applied basis blank instead of a zero contribution', () => {
    const { dynamicKpis } = renderTeam([
      pinnedAgent({
        id: 'anonymous-basis-a',
        attendActual: 0.46,
        attendTarget: 0.7,
        bookings: 100,
        attended: 46,
      }),
      pinnedAgent({
        id: 'anonymous-basis-b',
        attendActual: 0.46,
        attendTarget: 0.65,
        bookings: 100,
        attended: 46,
      }),
    ]);
    const attendance = dynamicKpis.find((kpi) => kpi.label.includes('Attendance'));
    expect(attendance?.basisVaries).toBe(true);
    expect(attendance?.contribution).toBeNull();
    expect(attendance?.weight).toBeNull();

    const card = screen.getByText('Patient Attendance Rate').closest('article');
    expect(card).toHaveTextContent('Target: Varies');
    expect(card).toHaveTextContent('Basis varies');
    expect(card).toHaveTextContent('Contribution—');
    expect(card).toHaveTextContent('Weight—');
    expect(card).not.toHaveTextContent('Contribution0.0%');
  });
});
