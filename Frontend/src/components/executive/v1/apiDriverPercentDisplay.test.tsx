import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { composeExecutiveSummary, mapDrivers, scopedRecordDrivers, type ExecRecord } from '../../../features/executive/compose';
import { FIXTURE_TEAM_FUNCTIONS } from '../../../features/executive/executive.fixture';
import type { InsightDriver, InsightItem } from '../../../features/insights/types';
import DriversCard from './DriversCard';

const TODAY = new Date(2026, 7, 9);
const MINUS = '\u2212';

function insightItem(patch: Partial<InsightItem> & Pick<InsightItem, 'id' | 'kpi_key'> & { detail: InsightItem['detail'] }): InsightItem {
  return {
    severity: 'critical',
    insight_type: 'kpi_driver',
    title: patch.kpi_key ?? patch.id,
    explanation: '',
    scope: 'Outbound · All positions',
    impact_points: patch.detail.impact_points,
    trend_label: 'Compared with previous available period',
    priority_reason: '',
    status: 'open',
    team: 'Outbound',
    performance_level: 'Employee',
    position: null,
    employee_id: null,
    planning_context: {},
    ...patch,
  };
}

function driverFor(item: InsightItem, impact: number, label = item.kpi_key ?? item.id): InsightDriver {
  return {
    id: `${item.id}-driver`,
    driver: label,
    scope: item.scope,
    impact_points: impact,
    direction: impact < 0 ? 'negative' : 'positive',
    insight_id: item.id,
    kpi_direction: item.detail.direction,
  };
}

const attendance = insightItem({
  id: 'anonymous-attendance',
  kpi_key: 'Attendance',
  detail: {
    current_value: 0.4607,
    previous_value: 0.5529,
    target_value: 0.65,
    unit: '%',
    direction: 'higher_better',
    impact_points: -8.510769230769228,
    affected_teams: ['Outbound'],
    affected_positions: [],
    affected_employees: [],
    evidence: [],
    warnings: [],
    recommended_focus: 'Attendance Rate',
    gap_value: -0.18930000000000002,
    achievement_percent: 70.88,
    change_value: -0.09219999999999995,
    raw_change: -0.09219999999999995,
    trend_status: 'declining',
    target_status: 'missed',
    direction_defaulted: false,
  },
});

const booking = insightItem({
  id: 'anonymous-booking',
  kpi_key: 'Booking',
  severity: 'opportunity',
  insight_type: 'opportunity',
  detail: {
    current_value: 0.3008,
    previous_value: 0.1704,
    target_value: 0.3,
    unit: '%',
    direction: 'higher_better',
    impact_points: 4.319999999999999,
    affected_teams: ['Outbound'],
    affected_positions: [],
    affected_employees: [],
    evidence: [],
    warnings: [],
    recommended_focus: 'Booking Rate',
    gap_value: 0.0008000000000000229,
    achievement_percent: 100,
    change_value: 0.13040000000000002,
    raw_change: 0.13040000000000002,
    trend_status: 'improving',
    target_status: 'met',
    direction_defaulted: false,
  },
});

const apiDrivers = [driverFor(attendance, -8.51, 'Attendance Rate'), driverFor(booking, 4.32, 'Booking Rate')];
const apiItems = [attendance, booking];

function summaryFor(view: 'function' | 'corporate') {
  return composeExecutiveSummary({
    view,
    role: 'Admin',
    records: [],
    filters: {},
    requestedPeriodKey: '2026-08',
    functionName: view === 'function' ? 'Call Center' : null,
    teamFunctions: FIXTURE_TEAM_FUNCTIONS,
    drivers: { drivers: apiDrivers, items: apiItems },
    actions: null,
    comparisonRecords: null,
    today: TODAY,
  });
}

function renderCards() {
  const functionSummary = summaryFor('function');
  const corporateSummary = summaryFor('corporate');
  render(
    <MemoryRouter>
      <div data-testid="function-drivers">
        <DriversCard summary={functionSummary} viewAllHref={null} title="Function drivers" />
      </div>
      <div data-testid="department-drivers">
        <DriversCard summary={corporateSummary} viewAllHref={null} title="Department drivers" />
      </div>
    </MemoryRouter>,
  );
  return { functionSummary, corporateSummary };
}

describe('API insight drivers on the executive cards', () => {
  it('shows ratio attendance and booking as percent points and keeps their score impacts', () => {
    const { functionSummary, corporateSummary } = renderCards();

    for (const summary of [functionSummary, corporateSummary]) {
      const attendanceDriver = summary.drivers.negative[0];
      const bookingDriver = summary.drivers.positive[0];
      expect(summary.drivers.negative.map((driver) => driver.kpi_label)).toEqual(['Attendance Rate']);
      expect(summary.drivers.positive.map((driver) => driver.kpi_label)).toEqual(['Booking Rate']);
      expect(attendanceDriver).toMatchObject({
        impact_points: -8.51,
        achievement_percent: 70.88,
        weight: null,
        unit: '%',
      });
      expect(attendanceDriver.current_value).toBeCloseTo(46.07, 2);
      expect(attendanceDriver.previous_value).toBeCloseTo(55.29, 2);
      expect(attendanceDriver.raw_change).toBeCloseTo(-9.22, 2);
      expect(attendanceDriver.change_value).toBeCloseTo(-9.22, 2);
      expect(attendanceDriver.gap_value).toBeCloseTo(-18.93, 2);
      expect(bookingDriver).toMatchObject({
        impact_points: 4.32,
        achievement_percent: 100,
        weight: null,
        unit: '%',
      });
      expect(bookingDriver.current_value).toBeCloseTo(30.08, 2);
      expect(bookingDriver.previous_value).toBeCloseTo(17.04, 2);
      expect(bookingDriver.raw_change).toBeCloseTo(13.04, 2);
      expect(bookingDriver.change_value).toBeCloseTo(13.04, 2);
    }

    for (const testId of ['function-drivers', 'department-drivers']) {
      const card = screen.getByTestId(testId);
      const negative = within(card).getAllByTestId('driver-negative');
      const positive = within(card).getAllByTestId('driver-positive');
      expect(negative).toHaveLength(1);
      expect(positive).toHaveLength(1);
      expect(negative[0]).toHaveTextContent('Attendance Rate');
      expect(negative[0]).toHaveTextContent('46.1%');
      expect(negative[0]).toHaveTextContent(`${MINUS}9.2%`);
      expect(negative[0]).toHaveTextContent(`${MINUS}8.51%`);
      expect(negative[0]).not.toHaveTextContent('0.5%');
      expect(negative[0]).not.toHaveTextContent(`${MINUS}0.1%`);
      expect(positive[0]).toHaveTextContent('Booking Rate');
      expect(positive[0]).toHaveTextContent('30.1%');
      expect(positive[0]).toHaveTextContent('+13%');
      expect(positive[0]).toHaveTextContent('+4.32%');
      expect(positive[0]).not.toHaveTextContent('0.3%');
      expect(positive[0]).not.toHaveTextContent('+0.1%');
    }
  });

  it('keeps percent points, other units, and missing metadata on their stored scale', () => {
    const qa = insightItem({
      id: 'anonymous-qa',
      kpi_key: 'QA Score',
      team: 'Inbound',
      detail: {
        current_value: 88,
        previous_value: 86,
        target_value: 90,
        unit: '%',
        direction: 'higher_better',
        impact_points: -1.2,
        affected_teams: ['Inbound'],
        affected_positions: [],
        affected_employees: [],
        evidence: [],
        warnings: [],
        recommended_focus: 'QA Score',
        gap_value: -2,
        achievement_percent: 97.8,
        change_value: 2,
        raw_change: 2,
        trend_status: 'improving',
        target_status: 'missed',
      },
    });
    const rework = insightItem({
      id: 'anonymous-rework',
      kpi_key: 'Rework',
      detail: {
        current_value: 0.1,
        previous_value: 0.08,
        target_value: 5,
        unit: '%',
        direction: 'higher_better',
        impact_points: -0.4,
        affected_teams: ['Outbound'],
        affected_positions: [],
        affected_employees: [],
        evidence: [],
        warnings: [],
        recommended_focus: 'Rework',
        gap_value: -4.9,
        achievement_percent: 2,
        change_value: 0.02,
        raw_change: 0.02,
        trend_status: 'improving',
        target_status: 'missed',
      },
    });
    const conversion = insightItem({
      id: 'anonymous-conversion',
      kpi_key: 'Conversion',
      detail: {
        current_value: 1.077,
        previous_value: 1,
        target_value: 1,
        unit: '%',
        direction: 'higher_better',
        impact_points: -0.3,
        affected_teams: ['Outbound'],
        affected_positions: [],
        affected_employees: [],
        evidence: [],
        warnings: [],
        recommended_focus: 'Conversion',
        gap_value: 0.077,
        achievement_percent: 100,
        change_value: 0.077,
        raw_change: 0.077,
        trend_status: 'improving',
        target_status: 'met',
      },
    });
    const handleTime = insightItem({
      id: 'anonymous-aht',
      kpi_key: 'Handle Time',
      detail: {
        current_value: 440,
        previous_value: 418,
        target_value: 360,
        unit: 's',
        direction: 'lower_better',
        impact_points: -0.2,
        affected_teams: ['Outbound'],
        affected_positions: [],
        affected_employees: [],
        evidence: [],
        warnings: [],
        recommended_focus: 'Handle Time',
        gap_value: -80,
        achievement_percent: 81.8,
        change_value: -22,
        raw_change: 22,
        trend_status: 'declining',
        target_status: 'missed',
      },
    });
    const calls = insightItem({
      id: 'anonymous-calls',
      kpi_key: 'Calls Completed',
      detail: {
        current_value: 24,
        previous_value: 22,
        target_value: 20,
        unit: 'count',
        direction: 'higher_better',
        impact_points: -0.1,
        affected_teams: ['Outbound'],
        affected_positions: [],
        affected_employees: [],
        evidence: [],
        warnings: [],
        recommended_focus: 'Calls Completed',
        gap_value: 4,
        achievement_percent: 100,
        change_value: 2,
        raw_change: 2,
        trend_status: 'improving',
        target_status: 'met',
      },
    });
    const revenue = insightItem({
      id: 'anonymous-revenue',
      kpi_key: 'Revenue',
      detail: {
        current_value: 2500,
        previous_value: 2000,
        target_value: 2000,
        unit: 'AED',
        direction: 'higher_better',
        impact_points: 1.5,
        affected_teams: ['Outbound'],
        affected_positions: [],
        affected_employees: [],
        evidence: [],
        warnings: [],
        recommended_focus: 'Revenue',
        gap_value: 500,
        achievement_percent: 100,
        change_value: 500,
        raw_change: 500,
        trend_status: 'improving',
        target_status: 'met',
      },
    });
    const unknownScale = insightItem({
      id: 'anonymous-unknown',
      kpi_key: 'Unspecified Rate',
      detail: {
        current_value: 0.46,
        previous_value: 0.4,
        target_value: null,
        unit: '%',
        direction: 'higher_better',
        impact_points: -0.05,
        affected_teams: ['Outbound'],
        affected_positions: [],
        affected_employees: [],
        evidence: [],
        warnings: [],
        recommended_focus: 'Unspecified Rate',
        gap_value: null,
        achievement_percent: null,
        change_value: null,
        raw_change: null,
        trend_status: null,
        target_status: null,
      },
    });
    const blank = insightItem({
      id: 'anonymous-blank',
      kpi_key: 'Blank Rate',
      detail: {
        current_value: null,
        previous_value: null,
        target_value: 0.65,
        unit: '%',
        direction: null,
        impact_points: -0.04,
        affected_teams: [],
        affected_positions: [],
        affected_employees: [],
        evidence: [],
        warnings: [],
        recommended_focus: 'Blank Rate',
        gap_value: null,
        achievement_percent: null,
        change_value: null,
        raw_change: null,
        trend_status: null,
        target_status: null,
      },
    });
    const items = [qa, rework, conversion, handleTime, calls, revenue, unknownScale, blank];
    const drivers = [
      driverFor(qa, -1.2),
      driverFor(rework, -0.4),
      driverFor(conversion, -0.3),
      driverFor(handleTime, -0.2),
      driverFor(calls, -0.1),
      driverFor(unknownScale, -0.05),
      driverFor(blank, -0.04),
      driverFor(revenue, 1.5),
    ];
    const split = mapDrivers(drivers, items, FIXTURE_TEAM_FUNCTIONS, 20);
    const byLabel = (label: string) => [...split.negative, ...split.positive].find((driver) => driver.kpi_label === label);

    expect(split.negative.map((driver) => driver.impact_points)).toEqual([-1.2, -0.4, -0.3, -0.2, -0.1, -0.05, -0.04]);
    expect(split.positive.map((driver) => driver.impact_points)).toEqual([1.5]);
    expect(byLabel('QA Score')).toMatchObject({ current_value: 88, previous_value: 86, raw_change: 2, gap_value: -2, achievement_percent: 97.8, impact_points: -1.2 });
    expect(byLabel('Rework')).toMatchObject({ current_value: 0.1, previous_value: 0.08, raw_change: 0.02, change_value: 0.02, impact_points: -0.4 });
    expect(byLabel('Conversion')?.current_value).toBeCloseTo(107.7, 2);
    expect(byLabel('Conversion')?.raw_change).toBeCloseTo(7.7, 2);
    expect(byLabel('Handle Time')).toMatchObject({ current_value: 440, previous_value: 418, raw_change: 22, change_value: -22, unit: 's', impact_points: -0.2 });
    expect(byLabel('Calls Completed')).toMatchObject({ current_value: 24, previous_value: 22, raw_change: 2, unit: 'count', impact_points: -0.1 });
    expect(byLabel('Revenue')).toMatchObject({ current_value: 2500, raw_change: 500, gap_value: 500, unit: 'AED', impact_points: 1.5 });
    expect(byLabel('Unspecified Rate')).toMatchObject({ current_value: 0.46, previous_value: 0.4, raw_change: 0.06, impact_points: -0.05 });
    expect(byLabel('Blank Rate')).toMatchObject({ current_value: null, previous_value: null, raw_change: null, gap_value: null, impact_points: -0.04 });

    const summary = composeExecutiveSummary({
      view: 'corporate',
      role: 'Admin',
      records: [],
      filters: {},
      teamFunctions: FIXTURE_TEAM_FUNCTIONS,
      drivers: { drivers, items },
      actions: null,
      today: TODAY,
    });
    render(
      <MemoryRouter>
        <DriversCard summary={summary} viewAllHref={null} title="Stored scale drivers" />
      </MemoryRouter>,
    );
    const negatives = screen.getAllByTestId('driver-negative');
    expect(negatives[0]).toHaveTextContent('QA Score');
    expect(negatives[0]).toHaveTextContent('88%');
    expect(negatives[1]).toHaveTextContent('Rework');
    expect(negatives[1]).toHaveTextContent('0.1%');
    expect(negatives[2]).toHaveTextContent('Conversion');
    expect(negatives[2]).toHaveTextContent('107.7%');
    expect(screen.getByTestId('driver-positive')).toHaveTextContent('AED 2.5K');
    expect(screen.queryByText('8800%')).not.toBeInTheDocument();
    expect(screen.queryByText('10%')).not.toBeInTheDocument();
  });

  it('leaves record-derived driver percents on the kpiRows scale', () => {
    const june: ExecRecord['period'] = { key: '2026-07', year: 2026, month: 'July' };
    const august: ExecRecord['period'] = { key: '2026-08', year: 2026, month: 'August' };
    const kpi = (actual: number) => ({
      kpi_key: 'Attendance',
      label: 'Attendance Rate',
      unit: '%',
      direction: 'higher_better' as const,
      actual_value: actual,
      target_value: 0.65,
      achievement_ratio: actual / 0.65,
      weight_applied: 0.6,
      contribution: (actual / 0.65) * 0.6,
    });
    const row = (period: ExecRecord['period'], actual: number): ExecRecord => ({
      employeeId: 'anonymous-derived',
      name: 'Anonymous derived',
      team: 'Outbound',
      region: 'EGY',
      position: 'Agent',
      level: 'Employee',
      period,
      score: 70,
      kpis: [kpi(actual)],
    });
    const derived = scopedRecordDrivers([row(august, 0.4607)], [row(june, 0.4)], FIXTURE_TEAM_FUNCTIONS);
    expect(derived?.negative[0]?.current_value).toBeCloseTo(46.07, 2);
    expect(derived?.negative[0]?.previous_value).toBeCloseTo(40, 2);
    expect(Math.abs(derived?.negative[0]?.current_value ?? 0)).toBeLessThan(100);
  });
});
