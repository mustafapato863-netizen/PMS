import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ThemeProvider } from '../../context/ThemeContext';
import TeamKpiSection from './TeamKpiSection';

type Kpi = {
  label: string;
  actual: number;
  target: number;
  unit?: string;
  isLowerBetter?: boolean;
  weight?: number | null;
  contribution?: number | null;
};

const rejection = (actual: number): Kpi => ({
  label: 'Controllable Rejection Rate',
  actual,
  target: 0.01,
  unit: '%',
  isLowerBetter: true,
  weight: 0.5,
  contribution: 0.3,
});

const calls = (actual: number): Kpi => ({
  label: 'Average Hold Minutes',
  actual,
  target: 3,
  unit: 'min',
  isLowerBetter: true,
  weight: 0.2,
  contribution: 0.1,
});

function teamMetrics(dynamicKpis: Kpi[]) {
  return {
    attendCR: 80,
    bookingCR: 50,
    avgAHT: '03:00',
    avgAHTSec: 180,
    abandonRate: 1,
    reachabilityRate: 80,
    totalBookings: 10,
    totalAttended: 8,
    totalCallsHandled: 100,
    totalAbandoned: 1,
    utzRate: 0,
    hasUtz: false,
    dynamicKpis,
  };
}

function renderSection(options: {
  current: Kpi[];
  previous?: Kpi[] | null;
  prevMonthLabel?: string | null;
}) {
  return render(
    <ThemeProvider>
    <TeamKpiSection
      totalAgents={10}
      avgScore={85}
      pctAB={50}
      pctDE={10}
      classCounts={{ A: 1, B: 4, C: 3, D: 1, E: 1 }}
      isCallCenterView={false}
      isInbound={false}
      teamMetrics={teamMetrics(options.current)}
      prevTeamMetrics={options.previous === null || options.previous === undefined
        ? null
        : { ...teamMetrics(options.previous), dynamicKpis: options.previous }}
      avgAHTSec={180}
      teamId="pre-approvals-ip-offshore"
      prevMonthLabel={options.prevMonthLabel ?? null}
    />
    </ThemeProvider>,
  );
}

describe('team KPI card change against the previous month', () => {
  it('shows a percentage KPI as points with the month, not as a relative percent', () => {
    // 0.26% now, 1.20% in August: -0.94 points.
    renderSection({ current: [rejection(0.0026)], previous: [rejection(0.012)], prevMonthLabel: 'Aug' });

    expect(screen.getByText('−0.94 pts vs Aug')).toBeInTheDocument();
    expect(screen.queryByText(/% MoM/)).not.toBeInTheDocument();
  });

  it('colours a falling lower-is-better rate as good', () => {
    renderSection({ current: [rejection(0.0026)], previous: [rejection(0.012)], prevMonthLabel: 'Aug' });

    expect(screen.getByText('−0.94 pts vs Aug').parentElement).toHaveClass('text-emerald-600');
  });

  it('shows other units in their own unit with the month', () => {
    renderSection({ current: [calls(3.5)], previous: [calls(2)], prevMonthLabel: 'Aug' });

    expect(screen.getByText('+1.5 min vs Aug')).toBeInTheDocument();
  });

  it('shows a muted No previous month when the team has no previous month with data', () => {
    renderSection({ current: [rejection(0.0026)], previous: null });

    const note = screen.getAllByText('No previous month')[0];
    expect(note).toHaveClass('text-[var(--text-muted)]');
  });

  it('shows a muted No previous value when the previous month has data but not this KPI', () => {
    renderSection({ current: [rejection(0.0026)], previous: [], prevMonthLabel: 'Aug' });

    expect(screen.getAllByText('No previous value')[0]).toHaveClass('text-[var(--text-muted)]');
  });

  it('compares January with the previous December using the month it was given', () => {
    renderSection({ current: [rejection(0.0026)], previous: [rejection(0.012)], prevMonthLabel: 'Dec' });

    expect(screen.getByText('−0.94 pts vs Dec')).toBeInTheDocument();
  });
});
