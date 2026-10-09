import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { mapScopedPerformanceRecord } from '../../../hooks/usePerformanceData';
import { composeExecutiveSummary, toExecRecords } from '../../../features/executive/compose';
import { FIXTURE_TEAM_FUNCTIONS } from '../../../features/executive/executive.fixture';
import type { ExecutiveSummary } from '../../../features/executive/types';
import DriversCard from './DriversCard';
import { TeamsNeedingAttentionCard } from './FunctionTeamsCards';
import TeamKpiTable from './TeamKpiTable';

const TODAY = new Date(2026, 7, 9);

function scopedRow(month: 'July' | 'August', kpis: Array<Record<string, unknown>>) {
  return mapScopedPerformanceRecord({
    id: `anonymous-${month}`,
    employee_id: 'ANONYMOUS-PERCENT',
    employee_name: 'Anonymous percent fixture',
    team: 'Outbound',
    month,
    year: 2026,
    performance_level: 'Employee',
    score: 79.82,
    region: 'EGY',
    raw_data: { 'A.Attend%': month === 'August' ? 0.4607 : 0.4, 'T.Attend%': 0.65 },
    kpi_values: kpis,
    evaluation_basis: { pinned: true, version_id: `anonymous-${month}` },
  });
}

function kpi(
  key: string,
  label: string,
  unit: string,
  actual: number,
  target: number,
  direction: 'higher_better' | 'lower_better',
  weight: number,
  achievementRatio?: number,
) {
  const ratio = achievementRatio ?? (direction === 'lower_better'
    ? (actual <= 0 ? 1 : target / actual)
    : actual / target);
  const capped = Math.min(Math.max(ratio, 0), 1);
  return {
    kpi_key: key,
    label,
    unit,
    actual_value: actual,
    target_value: target,
    achievement_ratio: capped,
    weight_applied: weight,
    contribution: capped * weight,
    direction,
    evaluation_pinned: true,
  };
}

function summaryFor(view: 'function' | 'corporate'): ExecutiveSummary {
  const august = scopedRow('August', [
    kpi('Attendance', 'Attendance Rate', '%', 0.4607, 0.65, 'higher_better', 0.6),
    kpi('Abandon', 'Abandon Rate', '%', 0.08, 0.05, 'lower_better', 0.05, 0.95),
    kpi('QA', 'QA Score', '%', 88, 90, 'higher_better', 0.2),
    kpi('Rework', 'Rework', '%', 0.1, 5, 'higher_better', 0.01, 0.99),
    kpi('Conversion', 'Conversion', '%', 1.077, 1, 'higher_better', 0.01),
    kpi('AHT', 'Handle Time', 's', 440, 360, 'lower_better', 0.05, 0.9),
    kpi('Calls', 'Calls Completed', 'count', 24, 20, 'higher_better', 0.01),
  ]);
  const july = scopedRow('July', [
    kpi('Attendance', 'Attendance Rate', '%', 0.4, 0.65, 'higher_better', 0.6),
    kpi('Abandon', 'Abandon Rate', '%', 0.04, 0.05, 'lower_better', 0.05, 0.95),
    kpi('QA', 'QA Score', '%', 86, 90, 'higher_better', 0.2),
    kpi('Rework', 'Rework', '%', 0.1, 5, 'higher_better', 0.01, 0.99),
    kpi('Conversion', 'Conversion', '%', 1, 1, 'higher_better', 0.01),
    kpi('AHT', 'Handle Time', 's', 418, 360, 'lower_better', 0.05, 0.9),
    kpi('Calls', 'Calls Completed', 'count', 22, 20, 'higher_better', 0.01),
  ]);
  const records = toExecRecords([august, july]);
  return composeExecutiveSummary({
    view,
    role: 'Admin',
    records,
    filters: {},
    requestedPeriodKey: '2026-08',
    functionName: view === 'function' ? 'Call Center' : null,
    teamFunctions: FIXTURE_TEAM_FUNCTIONS,
    drivers: null,
    deriveScopedDrivers: true,
    actions: null,
    comparisonRecords: records,
    today: TODAY,
  });
}

function renderSurfaces(functionSummary: ExecutiveSummary, corporateSummary: ExecutiveSummary) {
  return render(
    <MemoryRouter>
      <TeamKpiTable
        rows={functionSummary.kpis}
        effective={functionSummary.period.effective}
        previous={functionSummary.period.previous}
        score={functionSummary.hero.score}
      />
      <TeamsNeedingAttentionCard teams={functionSummary.teams} fn="Call Center" />
      <DriversCard summary={functionSummary} viewAllHref={null} title="Function drivers" />
      <DriversCard summary={corporateSummary} viewAllHref={null} title="Department drivers" />
    </MemoryRouter>,
  );
}

describe('executive percent display from scoped records', () => {
  it('shows Outbound ratio attendance as percent points and leaves other units on their stored scale', () => {
    const functionSummary = summaryFor('function');
    const corporateSummary = summaryFor('corporate');
    const attendance = functionSummary.kpis.find((row) => row.kpi_key === 'Attendance');
    const abandon = functionSummary.kpis.find((row) => row.kpi_key === 'Abandon');
    expect(attendance?.actual).toBeCloseTo(46.07, 2);
    expect(attendance?.target).toBeCloseTo(65, 2);
    expect(attendance?.raw_change).toBeCloseTo(6.07, 2);
    expect(attendance?.change_value).toBeCloseTo(6.07, 2);
    expect(abandon).toMatchObject({ actual: 8, target: 5, raw_change: 4, change_value: -4, gap_value: -3 });
    expect(functionSummary.hero.score).toBe(79.8);

    renderSurfaces(functionSummary, corporateSummary);

    const attendanceRow = screen.getAllByTestId('kpi-row').find((row) => within(row).queryByText('Attendance Rate'));
    expect(attendanceRow).toBeTruthy();
    const attendanceCells = within(attendanceRow!).getAllByRole('cell');
    expect(attendanceCells[2]).toHaveTextContent('46.1%');
    expect(attendanceCells[3]).toHaveTextContent('65%');
    expect(attendanceCells[5]).toHaveTextContent('+6.1%');
    expect(attendanceCells[6]).toHaveTextContent('60%');

    const abandonRow = screen.getAllByTestId('kpi-row').find((row) => within(row).queryByText('Abandon Rate'));
    const abandonCells = within(abandonRow!).getAllByRole('cell');
    expect(abandonCells[2]).toHaveTextContent('8%');
    expect(abandonCells[3]).toHaveTextContent('5%');
    expect(abandonCells[4]).toHaveTextContent('−3%');
    expect(abandonCells[5]).toHaveTextContent('−4%');

    const qaRow = screen.getAllByTestId('kpi-row').find((row) => within(row).queryByText('QA Score'));
    const qaCells = within(qaRow!).getAllByRole('cell');
    expect(qaCells[2]).toHaveTextContent('88%');
    expect(qaCells[3]).toHaveTextContent('90%');

    const reworkRow = screen.getAllByTestId('kpi-row').find((row) => within(row).queryByText('Rework'));
    const reworkCells = within(reworkRow!).getAllByRole('cell');
    expect(reworkCells[2]).toHaveTextContent('0.1%');
    expect(reworkCells[3]).toHaveTextContent('5%');

    const conversionRow = screen.getAllByTestId('kpi-row').find((row) => within(row).queryByText('Conversion'));
    const conversionCells = within(conversionRow!).getAllByRole('cell');
    expect(conversionCells[2]).toHaveTextContent('107.7%');
    expect(conversionCells[3]).toHaveTextContent('100%');

    const handleRow = screen.getAllByTestId('kpi-row').find((row) => within(row).queryByText('Handle Time'));
    const handleCells = within(handleRow!).getAllByRole('cell');
    expect(handleCells[2]).toHaveTextContent('440 s');
    expect(handleCells[3]).toHaveTextContent('360 s');
    expect(handleCells[5]).toHaveTextContent('−22 s');

    const callsRow = screen.getAllByTestId('kpi-row').find((row) => within(row).queryByText('Calls Completed'));
    const callsCells = within(callsRow!).getAllByRole('cell');
    expect(callsCells[2]).toHaveTextContent('24');
    expect(callsCells[2]).not.toHaveTextContent('%');

    expect(screen.getByText(/Attendance Rate at 46\.1% vs 65% target/)).toBeInTheDocument();
    expect(screen.getAllByText('46.1%').length).toBeGreaterThan(1);
    expect(screen.queryByText('0.5%')).not.toBeInTheDocument();
    expect(screen.queryByText('0.7%')).not.toBeInTheDocument();
    expect(corporateSummary.drivers.negative.some((driver) => driver.kpi_label === 'Attendance Rate' && Math.abs((driver.current_value ?? 0) - 46.07) < 0.001)).toBe(true);
    expect(functionSummary.drivers.negative.some((driver) => driver.kpi_label === 'Attendance Rate' && Math.abs((driver.current_value ?? 0) - 46.07) < 0.001)).toBe(true);
  });
});
