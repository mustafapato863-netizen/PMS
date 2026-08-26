import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import InsightsView from './InsightsView';

const query = vi.hoisted(() => ({ refetch: vi.fn() }));
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

vi.mock('../hooks/api/useInsightsWorkspace', () => ({
  useInsightsWorkspace: () => ({
    data: {
      summary: {
        critical: 1, at_risk: 0, opportunities: 0, data_issues: 1,
        critical_issues: 1, negative_weighted_drivers: 1, positive_weighted_drivers: 0,
        weighted_negative_impact: 5.6, weighted_positive_impact: 0, weighted_net_impact: -5.6,
        analyzed_kpis: 11, expected_kpis: 12, coverage_percent: 91.7,
      },
      priority_insights: [aggregateScoreInsight, insight],
      team_analyses: [insight, noShowInsight, ...extraAnalyses],
      performance_drivers: [{ id: 'driver', driver: 'CPL', scope: 'Marketing · Media Buyer', impact_points: -5.6, direction: 'negative', insight_id: 'cpl-risk' }],
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
  }),
}));

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

describe('InsightsView', () => {
  it('renders evidence-based summaries and opens insight details', async () => {
    const user = userEvent.setup();
    const { container } = render(<MemoryRouter><InsightsView /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: 'Insights' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Weighted Score Contribution' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Insight Summary' })).toBeInTheDocument();
    expect(screen.getByText('Net weighted KPI impact')).toBeInTheDocument();
    expect(screen.getByText('91.7%')).toBeInTheDocument();
    expect(screen.getAllByText('All positions average declined by 94.4%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('-5.6%').length).toBeGreaterThan(1);
    expect(screen.getAllByText('CPL contributed to the performance gap').length).toBeGreaterThan(1);
    expect(screen.getAllByText('-5.6%').length).toBeGreaterThan(1);
    await user.click(screen.getByRole('button', { name: 'View KPI details' }));
    const dialog = screen.getByRole('dialog', { name: 'CPL contributed to the performance gap' });
    expect(dialog).toBeInTheDocument();
    expect(container).not.toContainElement(dialog);
    expect(dialog.closest('.fixed')?.parentElement).toBe(document.body);
    expect(screen.getAllByText('136.00 AED').length).toBeGreaterThan(0);
  });

  it('requires confirmation before preparing unsaved planning context', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><InsightsView /></MemoryRouter>);
    await user.click(screen.getByRole('button', { name: 'View KPI details' }));
    await user.click(screen.getByRole('button', { name: /Create Plan/i }));

    expect(screen.getByText(/does not create or save a plan/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirm and prepare draft/i })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Confirm and prepare draft/i }));
    expect(screen.getByRole('button', { name: /Open Planning to assign owner and due date/i })).toBeInTheDocument();
  });

  it('renders authorized team analyses and opens the canonical detail drawer', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><InsightsView /></MemoryRouter>);

    await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), 'Marketing');
    expect(screen.getByRole('heading', { name: 'Team KPI Analysis' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Team Risk Matrix' })).toBeInTheDocument();
    expect(screen.getAllByText('Sales').length).toBeGreaterThan(1);
    expect(screen.getByText('No measured issue')).toBeInTheDocument();
    expect(screen.getAllByText('Outbound').length).toBeGreaterThan(1);
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

  it('shows the report reference by default and detailed people analysis after selecting a KPI', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><InsightsView /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: 'Report reference' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '6-Month KPI Trend' })).toBeInTheDocument();
    expect(screen.getAllByText('Analyst One').length).toBeGreaterThan(0);
    expect(screen.getAllByText('-2.8%').length).toBeGreaterThan(0);
    expect(screen.queryByRole('heading', { name: 'People Contribution Analysis' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Filters/i }));
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
});
