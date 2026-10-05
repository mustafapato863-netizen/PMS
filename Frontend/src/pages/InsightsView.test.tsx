import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import InsightsView from './InsightsView';
import { insightsWorkspaceUrl } from '../hooks/api/useInsightsWorkspace';
import type { InsightFilters } from '../features/insights/types';

const query = vi.hoisted(() => ({ refetch: vi.fn() }));
const latestFilters = vi.hoisted(() => ({ current: {} as InsightFilters }));
const actionMocks = vi.hoisted(() => ({
  getActionsForEmployee: vi.fn(() => []),
  refreshPerformanceData: vi.fn(),
}));

const insight = {
  id: 'cpl-risk', severity: 'critical', insight_type: 'kpi_driver', title: 'CPL contributed to the performance gap',
  explanation: 'CPL increased from 55.00 AED to 136.00 AED; for a lower better KPI, this is a negative movement.',
  scope: 'Marketing · Media Buyer', impact_points: -5.6, trend_label: 'Compared with previous available period',
  priority_reason: 'Weighted contribution changed the overall score by 5.6%.', status: 'open', team: 'Marketing',
  performance_level: 'Employee', position: 'Media Buyer', employee_id: null, kpi_key: 'cpl',
  detail: { current_value: 136, previous_value: 55, target_value: 60, unit: 'AED', direction: 'lower_better', impact_points: -5.6, affected_teams: ['Marketing'], affected_positions: ['Media Buyer'], affected_employees: [], evidence: [{ label: 'Current value', value: '136.00 AED' }], warnings: [], recommended_focus: 'Review the KPI breakdown.' },
  planning_context: { source_insight_id: 'cpl-risk', team: 'Marketing', kpi_key: 'cpl' },
};

const noShowInsight = {
  ...insight,
  id: 'outbound-no-show',
  title: 'No Show Rate is improving but remains above target',
  explanation: 'No Show Rate improved by 1.0 percentage points, moving from 52.0% to 51.0%. The result remains 31.0 percentage points above target.',
  scope: 'Outbound · Agent',
  impact_points: null,
  trend_label: 'Improving · Still above target',
  priority_reason: 'This operational KPI supports diagnosis but does not contribute to the weighted score for this period.',
  team: 'Outbound',
  position: 'Agent',
  kpi_key: 'no_show_rate',
  detail: {
    ...insight.detail,
    current_value: .51,
    previous_value: .52,
    target_value: .2,
    unit: '%',
    direction: 'lower_better',
    impact_points: null,
    affected_teams: ['Outbound'],
    affected_positions: ['Agent'],
  },
  planning_context: { source_insight_id: 'outbound-no-show', team: 'Outbound', kpi_key: 'no_show_rate' },
};

const aggregateScoreInsight = {
  ...insight,
  id: 'aggregate-score-decline',
  insight_type: 'performance',
  title: 'All positions average declined by 94.4%',
  explanation: 'Average score moved from 94.4 to 0.0 across 32 measured records.',
  scope: 'Inbound Â· All positions',
  impact_points: -94.4,
  team: 'Inbound',
  position: null,
  kpi_key: null,
  detail: {
    ...insight.detail,
    current_value: 0,
    previous_value: 94.4,
    target_value: null,
    unit: '%',
    impact_points: -94.4,
  },
  planning_context: { source_insight_id: 'aggregate-score-decline', team: 'Inbound' },
};

const extraAnalyses = Array.from({ length: 10 }, (_, index) => ({
  ...insight,
  id: `extra-${index + 1}`,
  title: `Extra KPI insight ${index + 1}`,
  explanation: `Extra KPI insight ${index + 1} explanation.`,
  scope: index % 2 === 0 ? 'Inbound · Agent' : 'Outbound · Agent',
  trend_label: `Trend ${index + 1}`,
  team: index % 2 === 0 ? 'Inbound' : 'Outbound',
  planning_context: { source_insight_id: `extra-${index + 1}`, team: index % 2 === 0 ? 'Inbound' : 'Outbound', kpi_key: 'cpl' },
}));

vi.mock('../hooks/api/useInsightsWorkspace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/api/useInsightsWorkspace')>();
  return {
  ...actual,
  useInsightsWorkspace: (filters: InsightFilters) => {
    latestFilters.current = filters;
    return ({
    data: {
      summary: {
        critical: 1, at_risk: 0, opportunities: 0, data_issues: 1,
        critical_issues: 1, negative_weighted_drivers: 1, positive_weighted_drivers: 0,
        weighted_negative_impact: 5.6, weighted_positive_impact: 0, weighted_net_impact: -5.6,
        analyzed_kpis: 11, expected_kpis: 12, coverage_percent: 91.7,
      },
      priority_insights: [aggregateScoreInsight, insight],
      team_analyses: [insight, noShowInsight, ...extraAnalyses],
      performance_drivers: [
        { id: 'driver', driver: 'CPL', scope: 'Marketing · Media Buyer', impact_points: -5.6, direction: 'negative', insight_id: 'cpl-risk' },
        { id: 'driver-no-show', driver: 'No Show Rate', scope: 'Outbound · Agent', impact_points: -3.1, direction: 'negative', insight_id: 'outbound-no-show' },
        { id: 'driver-booking', driver: 'Booking Rate', scope: 'Inbound · Agent', impact_points: 2.4, direction: 'positive', insight_id: 'extra-1' },
      ],
      risks: [{ key: 'kpis', label: 'High-weight KPI risks', count: 1, explanation: 'High-weight KPIs missing target.', filter_type: 'kpi_driver' }],
      opportunities: [], data_issues: [],
      people_contribution_analysis: {
        kpi_key: 'cpl',
        kpi_label: 'CPL',
        unit: 'AED',
        direction: 'lower_better',
        total_employees: 2,
        negative_contributors: 2,
        positive_contributors: 0,
        data_issues: 0,
        rows: [
          {
            employee_id: 'E1', employee_name: 'Analyst One', team: 'Marketing',
            performance_level: 'Employee', position: 'Media Buyer', kpi_key: 'cpl',
            kpi_label: 'CPL', unit: 'AED', direction: 'lower_better',
            current_value: 136, target_value: 60, gap: -76, weighted_impact: -2.8,
            trend: 81, severity: 'High', classification: 'negative',
          },
          {
            employee_id: 'E2', employee_name: 'Analyst Two', team: 'Marketing',
            performance_level: 'Employee', position: 'Media Buyer', kpi_key: 'cpl',
            kpi_label: 'CPL', unit: 'AED', direction: 'lower_better',
            current_value: 75, target_value: 60, gap: -15, weighted_impact: -1,
            trend: 10, severity: 'Medium', classification: 'negative',
          },
        ],
      },
      kpi_trend: {
        kpi_key: 'cpl',
        kpi_label: 'CPL',
        unit: 'AED',
        direction: 'lower_better',
        points: [
          { period: { year: 2026, month: 'January', key: '2026-01' }, actual_value: 48, target_value: 60, measured_records: 2 },
          { period: { year: 2026, month: 'February', key: '2026-02' }, actual_value: null, target_value: null, measured_records: 0 },
          { period: { year: 2026, month: 'March', key: '2026-03' }, actual_value: 52, target_value: 60, measured_records: 2 },
          { period: { year: 2026, month: 'April', key: '2026-04' }, actual_value: 55, target_value: 60, measured_records: 2 },
          { period: { year: 2026, month: 'May', key: '2026-05' }, actual_value: 55, target_value: 60, measured_records: 2 },
          { period: { year: 2026, month: 'June', key: '2026-06' }, actual_value: 136, target_value: 60, measured_records: 2 },
        ],
      },
      executive_story: {
        headline: 'June 2026 performance is 22.5% below the 100% target.',
        scope_label: 'All regions · All teams · June 2026',
        current_score: 77.5, target_score: 100, gap_points: -22.5, score_change: -1.9,
        primary_scope: 'UAE', primary_scope_contribution_percent: 82.7,
        primary_driver: 'CPL', primary_driver_impact: -5.6,
        recommended_focus: 'Review CPL in Marketing · Media Buyer first.',
        confidence: 'high', evidence: [],
      },
      geography_summaries: [
        { scope: 'UAE', current_score: 74.6, previous_score: 76, score_change: -1.4, gap_points: -25.4, gap_contribution_percent: 82.7, impacted_employees: 4, total_employees: 10, affected_percentage: 40 },
        { scope: 'EGY', current_score: 85.3, previous_score: 86, score_change: -0.7, gap_points: -14.7, gap_contribution_percent: 17.3, impacted_employees: 1, total_employees: 3, affected_percentage: 33.3 },
      ],
      kpi_overview: { total_kpis: 12, on_track: 7, at_risk: 3, critical: 2, points: [] },
      role_summaries: [
        { role: 'Media Buyer', team: 'Marketing', current_score: 69.9, previous_score: 90, movement: -20.1, net_impact: -5.6, affected_employees: 2, total_employees: 5, primary_insight_id: 'cpl-risk' },
      ],
      team_summaries: [
        { team: 'Marketing', current_score: 69.9, previous_score: 90, score_change: -20.1, impacted_employees: 2, total_employees: 5, critical: 1, at_risk: 0, opportunities: 0, main_insight_id: 'cpl-risk', main_cause: 'CPL contributed to the performance gap' },
        { team: 'Outbound', current_score: 86, previous_score: 84, score_change: 2, impacted_employees: 1, total_employees: 8, critical: 0, at_risk: 1, opportunities: 1, main_insight_id: 'outbound-no-show', main_cause: 'No Show Rate is improving but remains above target' },
        { team: 'Sales', current_score: 90, previous_score: 89, score_change: 1, impacted_employees: 0, total_employees: 4, critical: 0, at_risk: 0, opportunities: 0, main_insight_id: null, main_cause: null },
      ],
      options: { periods: [{ year: 2026, month: 'June', key: '2026-06' }], regions: ['EGY'], teams: ['Inbound', 'Marketing', 'Outbound', 'Sales'], performance_levels: ['Employee'], positions: ['Media Buyer'], employees: [], kpis: [{ key: 'cpl', label: 'CPL' }], severities: ['critical', 'risk', 'opportunity', 'information'], insight_types: ['performance', 'kpi_driver', 'employee_risk', 'opportunity', 'data_quality'], statuses: ['open'] },
      comparison: { current: { year: 2026, month: 'June', key: '2026-06' }, previous: { year: 2026, month: 'May', key: '2026-05' }, is_adjacent: true, note: null },
      deferred_capabilities: ['Overdue corrective actions require a persisted due date.'],
    },
    isLoading: false, isFetching: false, error: null, refetch: query.refetch,
  });
  },
  };
});

vi.mock('../context/RoleContext', () => ({
  useUserRole: () => ({ role: 'Admin' }),
}));

vi.mock('../hooks/useActionStore', () => ({
  useActionStore: () => ({
    getActionsForEmployee: actionMocks.getActionsForEmployee,
  }),
}));

vi.mock('../hooks/usePerformanceData', () => {
  const row = (id: string, name: string, score: number) => ({
    id,
    name,
    team: 'Marketing',
    month: 'June',
    performanceLevel: 'Employee',
    score,
    gradeClass: score >= 90 ? 'A' : 'D',
    gradeLabel: score >= 90 ? 'A' : 'D',
    status: score >= 90 ? 'Meet' : 'Below',
    rootCauseAuto: 'CPL',
    rootCauseNote: '',
    correctiveAction: '',
    suggestedAction: '',
    ahtMinutes: 0,
    bookingRate: 0,
    attendRate: 0,
    raw: {
      kpi_values: [{
        kpi_key: 'cpl',
        label: 'CPL',
        actual_value: 136,
        target_value: 60,
        unit: 'AED',
        direction: 'lower_better',
        achievement_ratio: .44,
        weight_applied: .1,
        contribution: .044,
      }],
    },
  });
  return {
    useTeamData: () => ({
      rows: [row('E1', 'Analyst One', 69.9), row('E2', 'Analyst Two', 82)],
      avgScore: 75.95,
    }),
    refreshPerformanceData: actionMocks.refreshPerformanceData,
  };
});

function renderInsights() {
  return render(
    <MemoryRouter initialEntries={['/insights']}>
      <Routes>
        <Route path="/insights" element={<InsightsView />} />
        <Route path="/employee/:employeeId" element={<p>Employee profile page</p>} />
        <Route path="/planning" element={<p>Planning page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

function section(name: string) {
  return screen.getByRole('region', { name });
}

describe('InsightsView', () => {
  it('renders the Figma 18:3 header with labelled Date, Regions, primary Functions and Levels filters', () => {
    renderInsights();

    expect(screen.getByRole('heading', { level: 1, name: 'Insights' })).toBeInTheDocument();
    expect(screen.getByText('Understand what happened, why it happened, and what to do next.')).toBeInTheDocument();
    const filters = screen.getByRole('group', { name: 'Insights filters' });
    ['Date', 'Regions', 'Functions', 'Levels'].forEach((label) => {
      expect(within(filters).getByText(label)).toBeInTheDocument();
    });
    expect(within(filters).getByText('Primary')).toBeInTheDocument();
    expect(within(filters).getByRole('combobox', { name: 'Insight period' })).toHaveValue('2026-06');
    expect(within(filters).getByRole('combobox', { name: 'Function' })).toHaveValue('');
    expect(within(filters).getByRole('combobox', { name: 'Performance level' })).toBeInTheDocument();
  });

  it('builds the executive summary from executive_story and the leading KPI trend', () => {
    renderInsights();
    const summary = section('Executive Summary');

    expect(within(summary).getByTestId('executive-headline')).toHaveTextContent('June 2026 performance is 22.5% below target.');
    const priority = within(summary).getByTestId('executive-priority-focus');
    expect(within(priority).getByText('Priority focus')).toBeInTheDocument();
    expect(within(priority).getByText('Review CPL first — largest weighted gap.')).toBeInTheDocument();
    expect(priority).toHaveAttribute('title', 'Review CPL in Marketing · Media Buyer first.');
    const status = within(summary).getByTestId('executive-status-row');
    expect(within(status).getByText('D · Below Average')).toHaveAttribute('data-grade', 'D');
    const trendBadge = within(status).getByTestId('executive-trend-badge');
    expect(trendBadge).toHaveAttribute('data-tone', 'down');
    expect(trendBadge).toHaveTextContent('↓ 1.9%');
    expect(trendBadge).toHaveTextContent('Down 1.9% vs. previous month');
    expect(within(summary).getByText('77.5%')).toBeInTheDocument();
    expect(within(summary).getByText('100.0%')).toBeInTheDocument();
    expect(within(summary).getByText('-22.5%')).toBeInTheDocument();
    expect(within(summary).getByText('vs. Previous Month')).toBeInTheDocument();
    expect(within(summary).getByText('-1.9%')).toBeInTheDocument();
    const grades = within(summary).getAllByText('D · Below Average');
    expect(grades).toHaveLength(2);
    const currentGrade = grades[1];
    expect(currentGrade).toHaveAttribute('data-grade', 'D');
    expect(currentGrade).toHaveStyle({ background: 'var(--pms-grade-d-badge-bg)', color: 'var(--pms-grade-d-badge-text)' });

    expect(within(summary).getByRole('heading', { name: 'Performance trend' })).toBeInTheDocument();
    expect(within(summary).getByText('Last 6 months')).toBeInTheDocument();
    expect(within(summary).getByText('Leading KPI · CPL · % of target')).toBeInTheDocument();
    const chart = within(summary).getByTestId('performance-trend-chart');
    // CPL is lower-better: target 60 / actual 136 = 44.1% of target in June; February has no data.
    expect(chart).toHaveAccessibleName(/Jun 44\.1%/);
    expect(chart).toHaveAccessibleName(/Feb no data/);
    expect(within(summary).getByTestId('performance-trend-target')).toBeInTheDocument();
  });

  it('splits weighted drivers into negative and positive panels and links them to the insight drawer', async () => {
    const user = userEvent.setup();
    renderInsights();
    const drivers = section('Key drivers of the gap');

    const negative = within(drivers).getByRole('list', { name: 'Top negative drivers' });
    const negativeRows = within(negative).getAllByRole('button');
    expect(negativeRows.map((row) => row.getAttribute('aria-label'))).toEqual([
      'CPL for Marketing · Media Buyer: -5.6%',
      'No Show Rate for Outbound · Agent: -3.1%',
    ]);
    const positive = within(drivers).getByRole('list', { name: 'Top positive drivers' });
    expect(within(positive).getByText('Booking Rate')).toBeInTheDocument();
    expect(within(positive).getByText('+2.4%')).toBeInTheDocument();

    await user.click(negativeRows[0]);
    expect(screen.getByRole('dialog', { name: 'CPL contributed to the performance gap' })).toBeInTheDocument();
  });

  it('opens the weighted score contribution analysis from "View all drivers"', async () => {
    const user = userEvent.setup();
    renderInsights();

    expect(screen.queryByRole('region', { name: 'Weighted score contribution' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /View all drivers/ }));
    const weighted = section('Weighted score contribution');
    expect(within(weighted).getByText('Widening the gap')).toBeInTheDocument();
    expect(within(weighted).getByRole('heading', { name: 'Insight summary' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Weighted score contribution/ })).toHaveAttribute('aria-expanded', 'true');
  });

  it('renders geography performance with grade badges and gap share, and focuses a region on click', async () => {
    const user = userEvent.setup();
    renderInsights();
    const geography = section('Geography performance');

    expect(within(geography).getByText('74.6%')).toBeInTheDocument();
    expect(within(geography).getByText('-25.4%')).toBeInTheDocument();
    expect(within(geography).getByText('82.7% gap share')).toBeInTheDocument();
    expect(within(geography).getByText('C · Average')).toHaveAttribute('data-grade', 'C');
    expect(within(geography).getByText('17.3% gap share')).toBeInTheDocument();

    await user.click(within(geography).getByRole('button', { name: /Focus UAE/ }));
    expect(latestFilters.current.region).toBe('UAE');
  });

  it('lists teams needing attention with A–E grades and drills into a team through the Function filter', async () => {
    const user = userEvent.setup();
    renderInsights();
    const teams = section('Teams needing attention');
    const rows = within(within(teams).getByRole('list', { name: 'Teams needing attention' })).getAllByRole('button');

    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText('Marketing')).toBeInTheDocument();
    expect(within(rows[0]).getByText('E · Unsatisfactory')).toHaveAttribute('data-grade', 'E');
    expect(within(rows[0]).getByText('-30.1%')).toBeInTheDocument();
    expect(within(rows[0]).getByRole('img', { name: 'Score moved from 90.0% to 69.9%' })).toBeInTheDocument();
    expect(within(rows[2]).getByText('B · Meet Expectations')).toHaveAttribute('data-grade', 'B');

    await user.click(rows[0]);
    expect(latestFilters.current.team).toBe('Marketing');
    expect(screen.getByRole('combobox', { name: 'Function' })).toHaveValue('Marketing');
  });

  it('shows people to review from the leading KPI and opens the employee profile', async () => {
    const user = userEvent.setup();
    renderInsights();
    const people = section('People to review');
    const rows = within(within(people).getByRole('list', { name: 'People to review' })).getAllByRole('button');

    expect(within(people).getByText(/· CPL/)).toBeInTheDocument();
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('Analyst One')).toBeInTheDocument();
    expect(within(rows[0]).getByText('136 AED / 60 AED')).toBeInTheDocument();
    expect(within(rows[0]).getByText('E · Unsatisfactory')).toBeInTheDocument();
    expect(within(rows[0]).getByText('-2.8%')).toBeInTheDocument();
    expect(within(rows[1]).getByText('C · Average')).toBeInTheDocument();

    await user.click(rows[0]);
    expect(screen.getByText('Employee profile page')).toBeInTheDocument();
  });

  it('orders sections as in Figma 18:3 v2 and renders section "View all" actions as text links', () => {
    renderInsights();
    const headings = screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent);
    const order = ['Executive Summary', 'Key drivers of the gap', 'Recommended actions', 'People to review', 'More analysis (optional)'];
    const positions = order.map((title) => headings.indexOf(title));
    expect(positions.every((position) => position >= 0)).toBe(true);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);

    expect(within(section('People to review')).getByRole('button', { name: /View all/ })).toHaveAttribute('data-variant', 'link');
    expect(within(section('Key drivers of the gap')).getByRole('button', { name: /View all drivers/ })).toHaveAttribute('data-variant', 'button');
  });

  it('opens the full people contribution analysis for the leading KPI from "View all"', async () => {
    const user = userEvent.setup();
    renderInsights();

    await user.click(within(section('People to review')).getByRole('button', { name: /View all/ }));
    expect(latestFilters.current.kpi).toBe('cpl');
    expect(screen.getByRole('heading', { name: 'People Contribution Analysis' })).toBeInTheDocument();
  });

  it('derives recommended actions from the leading driver and low-performing teams', async () => {
    const user = userEvent.setup();
    renderInsights();
    const actions = section('Recommended actions');

    expect(within(actions).getByRole('button', { name: /Focus on CPL/ })).toHaveTextContent('Largest performance gap (-5.6%)');
    expect(within(actions).getByRole('button', { name: /Review low-performing teams/ })).toHaveTextContent('Marketing');
    await user.click(within(actions).getByRole('button', { name: /Coach affected employees/ }));
    expect(screen.getByText('Planning page')).toBeInTheDocument();
  });

  it('expands and collapses every More analysis accordion', async () => {
    const user = userEvent.setup();
    renderInsights();

    await user.click(screen.getByRole('button', { name: 'Expand all' }));
    ['KPI overview', 'Performance by role', 'Weighted score contribution', 'Recent critical alerts'].forEach((name) => {
      expect(section(name)).toBeInTheDocument();
    });
    expect(within(section('KPI overview')).getByText('91.7%')).toBeInTheDocument();
    expect(within(section('Performance by role')).getByText('Media Buyer')).toBeInTheDocument();
    expect(within(section('Recent critical alerts')).getByText('All positions average declined by 94.4%')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Collapse all' }));
    expect(screen.queryByRole('region', { name: 'KPI overview' })).not.toBeInTheDocument();
  });

  it('renders evidence-based summaries and opens insight details', async () => {
    const user = userEvent.setup();
    const { container } = renderInsights();

    await user.click(screen.getByRole('button', { name: /Weighted score contribution/ }));
    expect(screen.getAllByText('-5.6%').length).toBeGreaterThan(1);
    expect(screen.getAllByText('CPL contributed to the performance gap').length).toBeGreaterThan(0);
    await user.click(screen.getByRole('button', { name: 'View KPI details' }));
    const dialog = screen.getByRole('dialog', { name: 'CPL contributed to the performance gap' });
    expect(dialog).toBeInTheDocument();
    expect(container).not.toContainElement(dialog);
    expect(dialog.closest('.fixed')?.parentElement).toBe(document.body);
    expect(screen.getAllByText('136.00 AED').length).toBeGreaterThan(0);
  });

  it('requires confirmation before preparing unsaved planning context', async () => {
    const user = userEvent.setup();
    renderInsights();
    await user.click(screen.getByRole('button', { name: /Weighted score contribution/ }));
    await user.click(screen.getByRole('button', { name: 'View KPI details' }));
    await user.click(screen.getByRole('button', { name: /Create Plan/i }));

    expect(screen.getByText(/does not create or save a plan/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirm and prepare draft/i })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Confirm and prepare draft/i }));
    expect(screen.getByRole('button', { name: /Open Planning to assign owner and due date/i })).toBeInTheDocument();
  });

  it('renders authorized team analyses and opens the canonical detail drawer', async () => {
    const user = userEvent.setup();
    renderInsights();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'Marketing');
    expect(screen.getByRole('heading', { name: 'Team KPI Analysis' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Team Risk Matrix' })).toBeInTheDocument();
    expect(screen.getAllByText('Sales').length).toBeGreaterThan(0);
    expect(screen.getByText('No measured issue')).toBeInTheDocument();
    expect(screen.getAllByText('Outbound').length).toBeGreaterThan(0);
    expect(screen.getByText(/Showing 1–10 of 13 analyses/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '2' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '11' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '2' }));
    expect(screen.getByText(/Showing 11–13 of 13 analyses/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Previous page' }));
    await user.click(screen.getByRole('button', { name: 'View No Show Rate is improving but remains above target' }));

    expect(screen.getByRole('dialog', { name: 'No Show Rate is improving but remains above target' })).toBeInTheDocument();
    expect(screen.getByText(/does not contribute to the weighted score/)).toBeInTheDocument();
  });

  it('shows detailed people analysis and the raw KPI trend after selecting a KPI', async () => {
    const user = userEvent.setup();
    renderInsights();

    expect(screen.queryByRole('heading', { name: 'People Contribution Analysis' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '6-Month KPI Trend' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /More filters/i }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'KPI' }), 'cpl');

    expect(screen.getByRole('heading', { name: 'People Contribution Analysis' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '6-Month KPI Trend' })).toBeInTheDocument();
    expect(screen.getByText('5 of 6 months measured')).toBeInTheDocument();
    expect(screen.getAllByText('Analyst One').length).toBeGreaterThan(0);
    expect(screen.getAllByText('-2.80%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('136 AED').length).toBeGreaterThan(0);

    await user.click(screen.getByRole('button', { name: 'Open actions for Analyst One' }));
    expect(screen.getByRole('menuitem', { name: 'View Employee Profile' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'View Performance Details' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Add Corrective Action' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'View Action History' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Compare with Team Average' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Edit Employee Assignment' })).toBeInTheDocument();
  });

  it('exposes Function options and wires Call Center into team filter and workspace URL', async () => {
    const user = userEvent.setup();
    renderInsights();

    expect(screen.queryByRole('combobox', { name: 'Team' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /More filters/i }));
    expect(screen.queryByRole('combobox', { name: 'Employee' })).not.toBeInTheDocument();

    const functionSelect = screen.getByRole('combobox', { name: 'Function' });
    expect(functionSelect).toBeInTheDocument();
    const optionLabels = Array.from(functionSelect.querySelectorAll('option')).map((option) => option.textContent);
    expect(optionLabels).toEqual([
      'All functions',
      'Call Center',
      'RCM',
      'Pre-Approvals',
      'Marketing',
    ]);

    await user.selectOptions(functionSelect, 'Call Center');
    expect(latestFilters.current.team).toBe('Call Center');
    const workspaceUrl = insightsWorkspaceUrl(latestFilters.current);
    expect(workspaceUrl).toMatch(/team=Call(\+|%20)Center/);
    expect(workspaceUrl.replace(/\+/g, '%20')).toContain('team=Call%20Center');
  });
});
