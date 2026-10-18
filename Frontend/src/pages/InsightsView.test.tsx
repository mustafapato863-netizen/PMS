import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import InsightsView from './InsightsView';
import Sidebar from '../components/common/Sidebar';
import { ThemeProvider } from '../context/ThemeContext';
import { insightsWorkspaceUrl } from '../hooks/api/useInsightsWorkspace';
import type { InsightFilters } from '../features/insights/types';

// Each test renders the whole Insights view and then runs several user-event steps. Alone the slowest test takes about 1.5s,
// but in a full parallel run the same steps took 3-5s, and one hit the 5s default. The cost is CPU load, not a wrong result,
// so only this file gets a longer budget. The global default stays at 5s.
vi.setConfig({ testTimeout: 15_000 });

const query = vi.hoisted(() => ({ refetch: vi.fn() }));
const latestFilters = vi.hoisted(() => ({ current: {} as InsightFilters }));
const teamDataCalls = vi.hoisted(() => ({ calls: [] as unknown[][] }));
// Authorized records behind the mocked workspace options. By default the
// mock scopes options like PR #14 (`InsightsService._options`); tests can
// switch to the main @ 0d4d48d shape (no `team_functions`).
const scopeMock = vi.hoisted(() => ({
  mode: 'pr14' as 'pr14' | 'legacy',
  teamFunctionsOverride: null as Record<string, string[]> | null,
  records: [
    { region: 'UAE', team: 'Call Center', level: 'Managerial', period: '2026-06' },
    { region: 'UAE', team: 'Inbound', level: 'Employee', period: '2026-06' },
    { region: 'UAE', team: 'Outbound', level: 'Employee', period: '2026-06' },
    { region: 'UAE', team: 'Marketing', level: 'Employee', period: '2026-06' },
    { region: 'UAE', team: 'Sales', level: 'Employee', period: '2026-06' },
    { region: 'UAE', team: 'Pre-Approvals OP Dubai', level: 'Employee', period: '2026-06' },
    { region: 'UAE', team: 'Pre-Approvals OP Final SHJAJM', level: 'Managerial', period: '2026-06' },
    { region: 'UAE', team: 'Pre-Approvals IP Final Dubai', level: 'Employee', period: '2026-06' },
    { region: 'UAE', team: 'Pre-Approvals IP Elective Dubai', level: 'Employee', period: '2026-06' },
    { region: 'UAE', team: 'RCM', level: 'Corporate', period: '2026-06' },
    { region: 'EGY', team: 'Inbound', level: 'Employee', period: '2026-06' },
    { region: 'EGY', team: 'Coding', level: 'Employee', period: '2026-06' },
    { region: 'EGY', team: 'Pre-Approvals IP Offshore', level: 'Employee', period: '2026-06' },
    // Pharmacy only has data in May, so it is outside the latest-month options.
    { region: 'UAE', team: 'Pharmacy', level: 'Employee', period: '2026-05' },
    { region: 'UAE', team: 'Marketing', level: 'Employee', period: '2026-05' },
  ],
}));
// Per-test overrides for the workspace payload and query state.
const workspaceMock = vi.hoisted(() => ({
  overrides: {} as Record<string, unknown>,
  query: {} as Record<string, unknown>,
}));
const actionMocks = vi.hoisted(() => ({
  getActionsForEmployee: vi.fn(() => []),
  getAllActions: vi.fn((): unknown[] => []),
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
  explanation: 'No Show Rate improved by 1.0%, moving from 52.0% to 51.0%. The result remains 31.0% above target.',
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
  const { scopedInsightOptions, periodFromKey } = await import('../test/insightsScopeOptions');
  return {
  ...actual,
  useInsightsWorkspace: (filters: InsightFilters) => {
    latestFilters.current = filters;
    const scoped = scopedInsightOptions(scopeMock.records, filters, scopeMock.mode);
    const scopedOptions = scopeMock.teamFunctionsOverride
      ? { ...scoped.options, team_functions: { ...scoped.options.team_functions, ...scopeMock.teamFunctionsOverride } }
      : scoped.options;
    const currentPeriod = periodFromKey(scoped.currentPeriod || '2026-06');
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
            trend: 81, severity: 'High', classification: 'negative', performance_score: 74.2, target_status: 'missed',
          },
          {
            employee_id: 'E2', employee_name: 'Analyst Two', team: 'Marketing',
            performance_level: 'Employee', position: 'Media Buyer', kpi_key: 'cpl',
            kpi_label: 'CPL', unit: 'AED', direction: 'lower_better',
            current_value: 75, target_value: 60, gap: -15, weighted_impact: -1,
            trend: 10, severity: 'Medium', classification: 'negative', performance_score: 85, target_status: 'missed',
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
      kpi_diagnosis: [
        {
          key: 'cpl', label: 'CPL', unit: 'AED', direction: 'lower_better', weight: 0.2,
          actual: 136, target: 60, achievement_percent: 44.12, status: 'critical',
          effect_points: -3.8,
          people_below_target: 2,
          six_months: [
            { year: 2026, month: 'June', actual_value: 136, status: 'critical' },
          ],
          most_below_team: { team: 'Marketing', actual: 136, target: 60, achievement_percent: 44.12, status: 'critical' },
          other_cohorts: [],
          teams: ['Marketing'],
        },
        {
          key: 'no_show_rate', label: 'No Show Rate', unit: '%', direction: 'lower_better', weight: 0.1,
          actual: 0.51, target: 0.2, achievement_percent: 39.22, status: 'critical',
          effect_points: null,
          people_below_target: 0,
          six_months: [],
          most_below_team: null,
          other_cohorts: ['Inbound · Other'],
          teams: ['Inbound'],
        },
        {
          key: 'booking', label: 'Booking rate', unit: '%', direction: 'higher_better', weight: 0.3,
          actual: 0.6, target: 0.5, achievement_percent: 100, status: 'on_track',
          effect_points: 0,
          people_below_target: 0,
          six_months: [],
          most_below_team: null,
          other_cohorts: [],
          teams: ['Marketing'],
        },
      ],
      role_summaries: [
        { role: 'Media Buyer', team: 'Marketing', current_score: 69.9, previous_score: 90, movement: -20.1, net_impact: -5.6, affected_employees: 2, total_employees: 5, primary_insight_id: 'cpl-risk' },
      ],
      team_summaries: [
        { team: 'Marketing', current_score: 69.9, previous_score: 90, score_change: -20.1, impacted_employees: 2, total_employees: 5, critical: 1, at_risk: 0, opportunities: 0, main_insight_id: 'cpl-risk', main_cause: 'CPL contributed to the performance gap' },
        { team: 'Outbound', current_score: 86, previous_score: 84, score_change: 2, impacted_employees: 1, total_employees: 8, critical: 0, at_risk: 1, opportunities: 1, main_insight_id: 'outbound-no-show', main_cause: 'No Show Rate is improving but remains above target' },
        { team: 'Sales', current_score: 90, previous_score: 89, score_change: 1, impacted_employees: 0, total_employees: 4, critical: 0, at_risk: 0, opportunities: 0, main_insight_id: null, main_cause: null },
      ],
      options: { ...scopedOptions, positions: ['Media Buyer'], employees: [], kpis: [{ key: 'cpl', label: 'CPL' }], severities: ['critical', 'risk', 'opportunity', 'information'], insight_types: ['performance', 'kpi_driver', 'employee_risk', 'opportunity', 'data_quality'], statuses: ['open'] },
      comparison: { current: currentPeriod, previous: { year: 2026, month: 'May', key: '2026-05' }, is_adjacent: true, note: null },
      deferred_capabilities: ['Overdue corrective actions require a persisted due date.'],
      ...workspaceMock.overrides,
    },
    isLoading: false, isFetching: false, isPlaceholderData: false, error: null, refetch: query.refetch,
    ...workspaceMock.query,
  });
  },
  };
});

vi.mock('../context/RoleContext', () => ({
  useUserRole: () => ({ role: 'Admin' }),
}));

// The real Sidebar (QA BUG-1b) needs auth, the performance catalog and apiFetch.
vi.mock('../context/auth', () => ({
  useAuth: () => ({
    currentUser: { id: 'admin-1', name: 'Admin', username: 'admin', role: 'Admin', has_unrestricted_team_access: true, accessible_teams: [] },
    logout: vi.fn(),
  }),
}));

vi.mock('../hooks/api/usePerformanceCatalog', () => ({
  usePerformanceCatalog: () => ({ data: { months: ['June'], periods: [], scopes: [] } }),
}));

vi.mock('../lib/apiClient', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/apiClient')>()),
  apiFetch: vi.fn().mockResolvedValue({ success: true, data: [], scopes: [] }),
}));

vi.mock('../hooks/useActionStore', () => ({
  useActionStore: () => ({
    getActionsForEmployee: actionMocks.getActionsForEmployee,
    getAllActions: actionMocks.getAllActions,
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
    useTeamData: (...args: unknown[]) => {
      teamDataCalls.calls.push(args);
      return {
      rows: [row('E1', 'Analyst One', 69.9), row('E2', 'Analyst Two', 82)],
      avgScore: 75.95,
      };
    },
    refreshPerformanceData: actionMocks.refreshPerformanceData,
  };
});

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location-search">{location.search}</output>;
}

function HistoryProbe() {
  const navigate = useNavigate();
  return (
    <nav aria-label="Test navigation">
      <button type="button" onClick={() => navigate(-1)}>Browser back</button>
      <button type="button" onClick={() => navigate(1)}>Browser forward</button>
      {/* Same target as the sidebar "Insights" link. */}
      <Link to="/insights">Sidebar Insights</Link>
      <button type="button" onClick={() => navigate('/insights?function=Marketing')}>Open Marketing link</button>
    </nav>
  );
}

/** The production Sidebar next to Insights / Executive, inside one router. */
function renderWithRealSidebar(entries: string[]) {
  const sidebar = <Sidebar isOpen setIsOpen={vi.fn()} />;
  const rendered = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={entries} initialIndex={entries.length - 1}>
      <ThemeProvider>
        <Routes>
          <Route path="/insights" element={<>{sidebar}<InsightsView /><LocationProbe /><HistoryProbe /></>} />
          <Route path="/executive" element={<>{sidebar}<p>Executive page</p><LocationProbe /></>} />
        </Routes>
      </ThemeProvider>
    </MemoryRouter>
    </QueryClientProvider>,
  );
  const launcher = screen.queryByRole('button', { name: /Insights filters/i });
  if (launcher) fireEvent.click(launcher);
  return rendered;
}

const realSidebarInsightsLink = () => within(screen.getByRole('complementary', { name: 'Primary navigation' }))
  .getByRole('link', { name: 'Insights' });

/** Router with a page before Insights, so Back can leave the page. */
function renderWithHistory(entries: string[], initialIndex = entries.length - 1) {
  const rendered = render(
    <MemoryRouter initialEntries={entries} initialIndex={initialIndex}>
      <Routes>
        <Route path="/insights" element={<><InsightsView /><LocationProbe /><HistoryProbe /></>} />
        <Route path="/executive" element={<><p>Executive page</p><HistoryProbe /></>} />
      </Routes>
    </MemoryRouter>,
  );
  const launcher = screen.queryByRole('button', { name: /Insights filters/i });
  if (launcher) fireEvent.click(launcher);
  return rendered;
}

function currentSearch() {
  return new URLSearchParams(screen.getByTestId('location-search').textContent || '');
}

function renderInsights(entry = '/insights', openFilters = true) {
  const rendered = render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/insights" element={<><InsightsView /><LocationProbe /></>} />
        <Route path="/employee/:employeeId" element={<p>Employee profile page</p>} />
        <Route path="/planning" element={<p>Planning page</p>} />
      </Routes>
    </MemoryRouter>,
  );
  const launcher = openFilters ? screen.queryByRole('button', { name: /Insights filters/i }) : null;
  if (launcher) fireEvent.click(launcher);
  return rendered;
}

function section(name: string) {
  return screen.getByRole('region', { name });
}

describe('InsightsView', () => {
  beforeEach(() => {
    scopeMock.mode = 'pr14';
    scopeMock.teamFunctionsOverride = null;
    workspaceMock.overrides = {};
    workspaceMock.query = {};
  });

  it('renders the header with labelled Date, Regions, primary Functions, Teams and Levels filters in order', () => {
    renderInsights();

    expect(screen.getByRole('heading', { level: 1, name: 'Insights' })).toBeInTheDocument();
    expect(screen.getByText('Understand what happened, why it happened, and what to do next.')).toBeInTheDocument();
    const filters = screen.getByRole('group', { name: 'Insights filters' });
    ['Date', 'Regions', 'Branches', 'Functions', 'Teams', 'Levels'].forEach((label) => {
      expect(within(filters).getByText(label)).toBeInTheDocument();
    });
    const order = within(filters).getAllByRole('combobox').map((select) => select.getAttribute('aria-label'));
    expect(order).toEqual(['Insight period', 'Region', 'Branch', 'Function', 'Team', 'Performance level']);
    expect(within(filters).getByRole('combobox', { name: 'Team' })).toHaveValue('');
    expect(within(filters).getByText('Primary')).toBeInTheDocument();
    expect(within(filters).getByRole('combobox', { name: 'Insight period' })).toHaveValue('2026-06');
    expect(within(filters).getByRole('combobox', { name: 'Function' })).toHaveValue('');
    expect(within(filters).getByRole('combobox', { name: 'Performance level' })).toBeInTheDocument();
  });

  it('shows people to review from the leading KPI and opens the employee profile', async () => {
    const user = userEvent.setup();
    renderInsights();
    const people = section('People to review');
    const rows = within(within(people).getByRole('list', { name: 'People to review' })).getAllByRole('button');

    expect(within(people).getByText(/People pulling the team score down most on CPL/)).toBeInTheDocument();
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('Analyst One')).toBeInTheDocument();
    expect(within(rows[0]).getByText('Marketing')).toBeInTheDocument();
    expect(within(rows[0]).getByText(/74\.2%/)).toBeInTheDocument();
    expect(within(rows[0]).getByText('D · Below Average')).toBeInTheDocument();
    expect(within(rows[0]).getByText('−2.8 pts')).toBeInTheDocument();
    expect(within(rows[1]).getByText('C · Average')).toBeInTheDocument();

    await user.click(rows[0]);
    expect(screen.getByText('Employee profile page')).toBeInTheDocument();
  });

  it('opens the full people contribution analysis for the leading KPI from its own link, and "Back to overview" returns', async () => {
    const user = userEvent.setup();
    renderInsights();

    await user.click(within(section('People to review')).getByRole('button', { name: 'Full CPL analysis' }));
    expect(latestFilters.current.kpi).toBe('cpl');
    expect(screen.getByRole('heading', { name: 'People Contribution Analysis' })).toBeInTheDocument();

    await user.click(within(section('People to review')).getByRole('button', { name: 'Back to overview' }));
    expect(latestFilters.current.kpi).toBeUndefined();
    expect(screen.queryByRole('heading', { name: 'People Contribution Analysis' })).not.toBeInTheDocument();
  });

  it('shows detailed people analysis and the raw KPI trend after selecting a KPI', async () => {
    const user = userEvent.setup();
    renderInsights();

    expect(screen.queryByRole('heading', { name: 'People Contribution Analysis' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '6-Month KPI Trend' })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByRole('combobox', { name: 'KPI' }), 'cpl');
    await user.click(screen.getByRole('button', { name: 'Done' }));

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

  const optionValues = (name: string) => Array.from(
    (screen.getByRole('combobox', { name }) as HTMLSelectElement).querySelectorAll('option'),
  ).map((option) => option.textContent);

  it('lists only functions with teams in scope and sends the function as the API function filter', async () => {
    const user = userEvent.setup();
    renderInsights();

    expect(screen.queryByRole('combobox', { name: 'Employee' })).not.toBeInTheDocument();
    expect(optionValues('Function')).toEqual(['All functions', 'Call Center', 'RCM', 'Marketing', 'Sales']);

    await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'Call Center');
    expect(latestFilters.current).toMatchObject({ teamFunction: 'Call Center' });
    expect(latestFilters.current.team).toBeUndefined();
    expect(currentSearch().get('function')).toBe('Call Center');
    const workspaceUrl = insightsWorkspaceUrl(latestFilters.current).replace(/\+/g, '%20');
    expect(workspaceUrl).toContain('function=Call%20Center');
    expect(workspaceUrl).not.toContain('team=');
  });

  it('narrows Teams to the selected function and syncs the Team filter with the URL', async () => {
    const user = userEvent.setup();
    renderInsights();

    // Latest month (June): Pharmacy only has May data, so it is not offered.
    expect(optionValues('Team')).toEqual([
      'All teams', 'Call Center', 'Coding', 'Inbound', 'Marketing', 'Outbound',
      'Pre-Approvals IP Elective Dubai', 'Pre-Approvals IP Final', 'Pre-Approvals IP Offshore', 'Pre-Approvals OP Final', 'RCM', 'Sales',
    ]);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'Call Center');
    expect(optionValues('Team')).toEqual(['All teams', 'Call Center', 'Inbound', 'Outbound']);

    await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), 'Outbound');
    expect(latestFilters.current).toMatchObject({ teamFunction: 'Call Center', team: 'Outbound' });
    expect(currentSearch().get('function')).toBe('Call Center');
    expect(currentSearch().get('team')).toBe('Outbound');
    expect(insightsWorkspaceUrl(latestFilters.current)).toContain('team=Outbound');

    await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'RCM');
    // Outbound is not an RCM team, so it is dropped with the function change.
    expect(latestFilters.current.team).toBeUndefined();
    expect(currentSearch().get('team')).toBeNull();
    // UAE Pre-Approvals teams are listed under RCM too (team_functions: ["RCM", "Pre-Approvals"]).
    expect(optionValues('Team')).toEqual([
      'All teams', 'Coding', 'Pre-Approvals IP Elective Dubai', 'Pre-Approvals IP Final',
      'Pre-Approvals IP Offshore', 'Pre-Approvals OP Final', 'RCM',
    ]);

    // Pre-Approvals workflows remain selectable as RCM teams, not as a function.
    expect(optionValues('Function')).not.toContain('Pre-Approvals');

    await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), 'Pre-Approvals OP Final');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), '');
    expect(currentSearch().get('team')).toBeNull();
    expect(insightsWorkspaceUrl(latestFilters.current)).toContain('function=RCM');
    expect(insightsWorkspaceUrl(latestFilters.current)).not.toContain('team=');
  });

  describe('URL history (QA BUG-1)', () => {
    const back = (user: ReturnType<typeof userEvent.setup>) => user.click(screen.getByRole('button', { name: 'Browser back' }));
    const forward = (user: ReturnType<typeof userEvent.setup>) => user.click(screen.getByRole('button', { name: 'Browser forward' }));

    it('steps Back and Forward through filter changes instead of leaving the page', async () => {
      const user = userEvent.setup();
      renderWithHistory(['/executive', '/insights']);

      await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'RCM');
      await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), 'Coding');
      expect(Object.fromEntries(currentSearch())).toEqual({ function: 'RCM', team: 'Coding' });

      await back(user);
      expect(Object.fromEntries(currentSearch())).toEqual({ function: 'RCM' });
      expect(screen.getByRole('combobox', { name: 'Function' })).toHaveValue('RCM');
      expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('');
      expect(latestFilters.current).toEqual({ teamFunction: 'RCM' });

      await back(user);
      expect(currentSearch().toString()).toBe('');
      expect(screen.getByRole('combobox', { name: 'Function' })).toHaveValue('');
      expect(latestFilters.current).toEqual({});

      await back(user);
      expect(screen.getByText('Executive page')).toBeInTheDocument();

      await forward(user);
      await forward(user);
      expect(Object.fromEntries(currentSearch())).toEqual({ function: 'RCM' });
      await forward(user);
      expect(Object.fromEntries(currentSearch())).toEqual({ function: 'RCM', team: 'Coding' });
      await user.click(screen.getByRole('button', { name: /Insights filters/i }));
      expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('Coding');
      expect(latestFilters.current).toEqual({ teamFunction: 'RCM', team: 'Coding' });
    });

    it('resets to defaults when the sidebar Insights link (/insights, no params) is clicked', async () => {
      const user = userEvent.setup();
      renderWithHistory(['/executive', '/insights?function=RCM&performance_level=Employee']);
      expect(screen.getByRole('combobox', { name: 'Function' })).toHaveValue('RCM');

      await user.click(screen.getByRole('link', { name: 'Sidebar Insights' }));
      expect(currentSearch().toString()).toBe('');
      expect(screen.getByRole('combobox', { name: 'Function' })).toHaveValue('');
      expect(screen.getByRole('combobox', { name: 'Performance level' })).toHaveValue('');
      expect(latestFilters.current).toEqual({});

      // The previous filtered view is one Back away.
      await back(user);
      expect(Object.fromEntries(currentSearch())).toEqual({ function: 'RCM', performance_level: 'Employee' });
      expect(screen.getByRole('combobox', { name: 'Function' })).toHaveValue('RCM');
    });

    it('resets filters through the REAL Sidebar Insights link (QA BUG-1b)', async () => {
      const user = userEvent.setup();
      renderWithRealSidebar(['/executive', '/insights?function=RCM&team=Coding&performance_level=Employee']);
      expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('Coding');
      expect(realSidebarInsightsLink()).toHaveAttribute('href', '/insights');

      await user.click(realSidebarInsightsLink());
      expect(currentSearch().toString()).toBe('');
      expect(screen.getByRole('combobox', { name: 'Function' })).toHaveValue('');
      expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('');
      expect(latestFilters.current).toEqual({});

      // Filters picked in the page do not leak into the sidebar link either.
      await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'Call Center');
      expect(Object.fromEntries(currentSearch())).toEqual({ function: 'Call Center' });
      expect(realSidebarInsightsLink()).toHaveAttribute('href', '/insights');
      await user.click(realSidebarInsightsLink());
      expect(latestFilters.current).toEqual({});

      await back(user);
      expect(latestFilters.current).toEqual({ teamFunction: 'Call Center' });
    });

    it('opens default Insights from another dashboard through the REAL Sidebar, even with ?month=', async () => {
      const user = userEvent.setup();
      renderWithRealSidebar(['/executive?month=June&performance_level=Managerial']);
      await user.click(realSidebarInsightsLink());
      expect(currentSearch().toString()).toBe('');
      expect(latestFilters.current).toEqual({});
    });

    it('adopts an in-app navigation to new filter params instead of reverting it', async () => {
      const user = userEvent.setup();
      renderWithHistory(['/insights?function=RCM']);
      await user.click(screen.getByRole('button', { name: 'Open Marketing link' }));
      expect(Object.fromEntries(currentSearch())).toEqual({ function: 'Marketing' });
      expect(screen.getByRole('combobox', { name: 'Function' })).toHaveValue('Marketing');
      expect(latestFilters.current).toEqual({ teamFunction: 'Marketing' });
    });

    it('keeps a Team=Marketing history entry as a team (legacy function links are read on first load only)', async () => {
      const user = userEvent.setup();
      renderWithHistory(['/executive', '/insights']);
      await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), 'Marketing');
      expect(Object.fromEntries(currentSearch())).toEqual({ team: 'Marketing' });
      expect(latestFilters.current).toEqual({ team: 'Marketing' });
      await user.selectOptions(screen.getByRole('combobox', { name: 'Performance level' }), 'Employee');
      await back(user);
      expect(Object.fromEntries(currentSearch())).toEqual({ team: 'Marketing' });
      expect(latestFilters.current).toEqual({ team: 'Marketing' });
      expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('Marketing');
    });

    it('does not add history entries for automatic corrections or unchanged selections', async () => {
      const user = userEvent.setup();
      // Coding is not a Call Center team: the cascade clears it with a replace.
      renderWithHistory(['/executive', '/insights?function=Call%20Center&team=Coding']);
      expect(Object.fromEntries(currentSearch())).toEqual({ function: 'Call Center' });
      await back(user);
      expect(screen.getByText('Executive page')).toBeInTheDocument();
      cleanup();

      // A legacy link is normalised in place too.
      renderWithHistory(['/executive', '/insights?team=Call%20Center']);
      expect(Object.fromEntries(currentSearch())).toEqual({ function: 'Call Center' });
      await back(user);
      expect(screen.getByText('Executive page')).toBeInTheDocument();
      cleanup();

      // Re-selecting the current value is not a new entry.
      renderWithHistory(['/executive', '/insights']);
      await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'RCM');
      await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'RCM');
      await back(user);
      expect(currentSearch().toString()).toBe('');
      await back(user);
      expect(screen.getByText('Executive page')).toBeInTheDocument();
    });
  });

  describe('switching functions directly (QA BUG-5)', () => {
    it('keeps every function listed after one is selected, so the user can switch directly', async () => {
      const user = userEvent.setup();
      renderInsights();
      const all = ['All functions', 'Call Center', 'RCM', 'Marketing', 'Sales'];

      await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'Call Center');
      expect(optionValues('Function')).toEqual(all);
      expect(optionValues('Team')).toEqual(['All teams', 'Call Center', 'Inbound', 'Outbound']);

      await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'RCM');
      expect(latestFilters.current).toMatchObject({ teamFunction: 'RCM' });
      expect(optionValues('Function')).toEqual(all);
      expect(optionValues('Team')).toEqual([
        'All teams', 'Coding', 'Pre-Approvals IP Elective Dubai', 'Pre-Approvals IP Final',
        'Pre-Approvals IP Offshore', 'Pre-Approvals OP Final', 'RCM',
      ]);

      await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'Marketing');
      expect(latestFilters.current).toMatchObject({ teamFunction: 'Marketing' });
      expect(optionValues('Function')).toEqual(all);
      expect(optionValues('Team')).toEqual(['All teams', 'Marketing']);
    });

    it('keeps the function and team selected (no auto-clear) with function-narrowed lists', async () => {
      const user = userEvent.setup();
      renderInsights();
      await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'RCM');
      await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), 'Pre-Approvals OP Final');
      expect(optionValues('Function')).toEqual(['All functions', 'Call Center', 'RCM', 'Marketing', 'Sales']);
      expect(latestFilters.current).toMatchObject({ teamFunction: 'RCM', team: 'Pre-Approvals OP Final' });

      // Clearing the function retains the valid selected Pre-Approvals team.
      await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), '');
      expect(latestFilters.current).toMatchObject({ team: 'Pre-Approvals OP Final' });
      expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('Pre-Approvals OP Final');
      expect(Object.fromEntries(currentSearch())).toEqual({ team: 'Pre-Approvals OP Final' });
    });
  });

  describe('All functions keeps a valid team (QA BUG-4)', () => {
    it('keeps the team when Functions is set to All functions', async () => {
      const user = userEvent.setup();
      renderInsights('/insights?function=Pre-Approvals&team=Pre-Approvals%20OP%20Final');
      expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('Pre-Approvals OP Final');

      await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), '');
      expect(latestFilters.current).toEqual({ team: 'Pre-Approvals OP Final' });
      expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('Pre-Approvals OP Final');
      expect(Object.fromEntries(currentSearch())).toEqual({ team: 'Pre-Approvals OP Final' });
      expect(Object.fromEntries(new URL(insightsWorkspaceUrl(latestFilters.current), 'http://pms.test').searchParams)).toEqual({ team: 'Pre-Approvals OP Final' });
    });

    it('keeps the team when the Function filter chip is removed', async () => {
      const user = userEvent.setup();
      renderInsights('/insights?function=RCM&team=Coding');
      await user.click(screen.getByRole('button', { name: 'Function: RCM' }));
      expect(latestFilters.current).toEqual({ team: 'Coding' });
      expect(Object.fromEntries(currentSearch())).toEqual({ team: 'Coding' });
    });

    it('still drops a team that does not belong to a newly picked function', async () => {
      const user = userEvent.setup();
      renderInsights('/insights?function=Call%20Center&team=Inbound');
      await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'RCM');
      expect(latestFilters.current).toEqual({ teamFunction: 'RCM' });
    });
  });

  it('restores Function and Team from the URL', () => {
    renderInsights('/insights?function=Call%20Center&team=Inbound&period=2026-06');
    expect(screen.getByRole('combobox', { name: 'Function' })).toHaveValue('Call Center');
    expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('Inbound');
    expect(latestFilters.current).toMatchObject({ teamFunction: 'Call Center', team: 'Inbound', periodKey: '2026-06' });
    expect(currentSearch().get('team')).toBe('Inbound');
  });

  it('reads legacy team=<function> links as a Function selection', () => {
    renderInsights('/insights?team=Call%20Center');
    expect(screen.getByRole('combobox', { name: 'Function' })).toHaveValue('Call Center');
    expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('');
    expect(currentSearch().get('function')).toBe('Call Center');
    expect(currentSearch().get('team')).toBeNull();
  });

  it('narrows Functions, Teams and Levels by Region and Levels by Function and Team', async () => {
    const user = userEvent.setup();
    renderInsights();

    expect(optionValues('Performance level')).toEqual(['All levels', 'Corporate', 'Employee', 'Managerial']);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Region' }), 'EGY');
    expect(optionValues('Function')).toEqual(['All functions', 'Call Center', 'RCM']);
    expect(optionValues('Team')).toEqual(['All teams', 'Coding', 'Inbound', 'Pre-Approvals IP Offshore']);
    expect(optionValues('Performance level')).toEqual(['All levels', 'Employee']);

    await user.selectOptions(screen.getByRole('combobox', { name: 'Region' }), '');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'Call Center');
    expect(optionValues('Performance level')).toEqual(['All levels', 'Employee', 'Managerial']);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), 'Inbound');
    expect(optionValues('Performance level')).toEqual(['All levels', 'Employee']);
  });

  it('auto-clears selections that become invalid after a cascade change (main backend, regions not faceted)', async () => {
    scopeMock.mode = 'legacy';
    const user = userEvent.setup();
    renderInsights();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'Call Center');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), 'Outbound');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Region' }), 'EGY');
    // Outbound has no EGY data; Call Center still does (Inbound).
    expect(latestFilters.current).toMatchObject({ region: 'EGY', teamFunction: 'Call Center' });
    expect(latestFilters.current.team).toBeUndefined();
    expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('');
    expect(currentSearch().get('team')).toBeNull();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Region' }), '');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'Marketing');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Region' }), 'EGY');
    expect(latestFilters.current.teamFunction).toBeUndefined();
    expect(screen.getByRole('combobox', { name: 'Function' })).toHaveValue('');
    expect(currentSearch().get('function')).toBeNull();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Region' }), '');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'Call Center');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Performance level' }), 'Managerial');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), 'Inbound');
    // Inbound has no Managerial records, so the level clears instead of showing an empty scope.
    expect(latestFilters.current).toMatchObject({ teamFunction: 'Call Center', team: 'Inbound' });
    expect(latestFilters.current.performanceLevel).toBeUndefined();
    expect(screen.getByRole('combobox', { name: 'Performance level' })).toHaveValue('');
  });

  it.each([
    ['a team outside the function', '/insights?function=Call%20Center&team=Coding', { teamFunction: 'Call Center' }, ['team']],
    ['a function with no data in the region', '/insights?region=EGY&function=Marketing&team=Marketing', { region: 'EGY' }, ['function', 'team']],
    ['an unknown region', '/insights?region=Mars&function=RCM', { teamFunction: 'RCM' }, ['region']],
    ['an unknown function', '/insights?function=Logistics', {}, ['function']],
    ['a level the team does not have', '/insights?team=Inbound&performance_level=Corporate', { team: 'Inbound' }, ['performance_level']],
    ['a team with no data in the region', '/insights?region=EGY&team=Sales&performance_level=Employee', { region: 'EGY', performanceLevel: 'Employee' }, ['team']],
  ])('auto-clears an invalid URL combination: %s', (_label, entry, expected, clearedParams) => {
    renderInsights(entry);
    expect(latestFilters.current).toMatchObject(expected);
    clearedParams.forEach((parameter) => expect(currentSearch().get(parameter)).toBeNull());
    expect(screen.getByRole('heading', { level: 1, name: 'Insights' })).toBeInTheDocument();
  });

  it('sends every header filter to the workspace API and the quick-action team data', async () => {
    const user = userEvent.setup();
    renderInsights();
    teamDataCalls.calls = [];

    await user.selectOptions(screen.getByRole('combobox', { name: 'Region' }), 'EGY');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'Call Center');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), 'Inbound');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Performance level' }), 'Employee');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Insight period' }), '2026-06');

    // Summary, trend, drivers, geography, teams, people and More analysis all
    // render from this one workspace response, so its params scope every section.
    const params = new URL(insightsWorkspaceUrl(latestFilters.current), 'http://pms.test').searchParams;
    expect(Object.fromEntries(params)).toEqual({
      year: '2026', month: 'June', region: 'EGY', function: 'Call Center', team: 'Inbound', performance_level: 'Employee',
    });
    // Quick-action team data (team-only endpoint) still gets the single effective team.
    expect(teamDataCalls.calls.at(-1)?.slice(0, 3)).toEqual(['Inbound', 'June', 'EGY']);
    expect(Object.fromEntries(currentSearch())).toEqual({
      period: '2026-06', region: 'EGY', function: 'Call Center', team: 'Inbound', performance_level: 'Employee',
    });
  });
  it('lists supported standalone functions and hides functions without scoped data', async () => {
    const user = userEvent.setup();
    renderInsights();
    // Standalone functions are selectable when the API has authorized data.
    expect(optionValues('Function')).toEqual(['All functions', 'Call Center', 'RCM', 'Marketing', 'Sales']);
    expect(optionValues('Function')).toContain('Sales');
    // Hide-when-empty is kept: EGY has no Marketing or UAE Pre-Approvals teams.
    await user.selectOptions(screen.getByRole('combobox', { name: 'Region' }), 'EGY');
    expect(optionValues('Function')).toEqual(['All functions', 'Call Center', 'RCM']);
  });

  it('prefers options.team_functions over the built-in team helper', async () => {
    // The backend narrows `teams` by function; the frontend then applies the
    // API mapping, which wins over the helper (the helper puts IP Offshore in RCM).
    scopeMock.teamFunctionsOverride = { 'Pre-Approvals IP Offshore': ['Call Center'] };
    const user = userEvent.setup();
    renderInsights();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'RCM');
    expect(optionValues('Team')).toEqual([
      'All teams', 'Coding', 'Pre-Approvals IP Elective Dubai', 'Pre-Approvals IP Final', 'Pre-Approvals OP Final', 'RCM',
    ]);
  });

  it('falls back to the team helper when the response has no team_functions', async () => {
    scopeMock.mode = 'legacy';
    const user = userEvent.setup();
    renderInsights();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'RCM');
    expect(optionValues('Team')).toContain('Pre-Approvals OP Final');
    expect(optionValues('Team')).toContain('Pre-Approvals IP Offshore');
  });

  it('keeps a Pre-Approvals team when clearing its RCM function', async () => {
    const user = userEvent.setup();
    renderInsights();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'RCM');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), 'Pre-Approvals IP Final');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), '');
    expect(latestFilters.current).toMatchObject({ team: 'Pre-Approvals IP Final' });
    expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('Pre-Approvals IP Final');
  });

  describe('with PR #14 latest-month options', () => {
    it('clears a URL team that has no data in the selected month and keeps the month', () => {
      renderInsights('/insights?period=2026-06&team=Pharmacy');
      expect(latestFilters.current.team).toBeUndefined();
      expect(latestFilters.current.periodKey).toBe('2026-06');
      expect(currentSearch().get('team')).toBeNull();
      expect(currentSearch().get('period')).toBe('2026-06');
      expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('');
    });

    it('clears a URL function that has no teams in the selected month', () => {
      renderInsights('/insights?period=2026-05&function=Call%20Center&team=Inbound');
      expect(latestFilters.current).toMatchObject({ periodKey: '2026-05' });
      expect(latestFilters.current.teamFunction).toBeUndefined();
      expect(latestFilters.current.team).toBeUndefined();
      expect(Object.fromEntries(currentSearch())).toEqual({ period: '2026-05' });
    });

    it('follows the backend default period for a URL team without a month instead of clearing it', () => {
      // PR #14 resolves the default period from the filtered scope, so Pharmacy
      // (May only) loads May; the URL stays free of an explicit period.
      renderInsights('/insights?team=Pharmacy');
      expect(latestFilters.current.team).toBe('Pharmacy');
      expect(screen.getByRole('combobox', { name: 'Insight period' })).toHaveValue('2026-05');
      expect(currentSearch().get('period')).toBeNull();
      expect(currentSearch().get('team')).toBe('Pharmacy');
    });

    it('auto-clears the team when a month without its data is picked', async () => {
      const user = userEvent.setup();
      renderInsights();
      await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'Call Center');
      await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), 'Inbound');
      await user.selectOptions(screen.getByRole('combobox', { name: 'Insight period' }), '2026-05');
      // May has no Call Center teams: the function and its team clear, the month stays.
      expect(latestFilters.current).toMatchObject({ periodKey: '2026-05' });
      expect(latestFilters.current.teamFunction).toBeUndefined();
      expect(latestFilters.current.team).toBeUndefined();
      expect(optionValues('Function')).toEqual(['All functions', 'Marketing', 'Pharmacy']);
      expect(optionValues('Team')).toEqual(['All teams', 'Marketing', 'Pharmacy']);
    });

    it('clears the level, not the team, when PR #14 narrows teams by an invalid level', () => {
      renderInsights('/insights?function=Call%20Center&team=Outbound&performance_level=Managerial');
      expect(latestFilters.current).toMatchObject({ teamFunction: 'Call Center', team: 'Outbound' });
      expect(latestFilters.current.performanceLevel).toBeUndefined();
      expect(currentSearch().get('performance_level')).toBeNull();
    });
  });

  describe('KPI diagnosis, summary, actions and the Executive Summary link', () => {
    beforeEach(() => {
      scopeMock.mode = 'pr14';
      scopeMock.teamFunctionsOverride = null;
      workspaceMock.overrides = {};
      workspaceMock.query = {};
      actionMocks.getAllActions.mockReturnValue([]);
    });

    const action = (overrides: Record<string, unknown>) => ({
      id: 'act-1', employee_id: 'E1', employee_name: 'Analyst One', team: 'Marketing', month: 'June',
      action_type: 'Coaching', action_text: 'Coach the booking script', root_cause_note: '', created_by: 'Manager',
      created_at: '2026-06-01', synced: true, status: 'Open', owner: { id: 'u1', name: 'Ada Owner' }, due_date: '2026-06-30',
      linked_kpi_key: 'cpl', is_overdue: false, ...overrides,
    });

    it('orders the sections: KPI diagnosis, People to review, Actions, and drops the removed sections', () => {
      renderInsights();
      const headings = screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent);
      const order = ['KPI diagnosis', 'People to review', 'Actions'];
      const positions = order.map((title) => headings.indexOf(title));
      expect(positions.every((position) => position >= 0)).toBe(true);
      expect([...positions].sort((a, b) => a - b)).toEqual(positions);
      for (const removed of ['Key drivers of the gap', 'Recommended actions', 'Team KPI Analysis', 'Team Risk Matrix', 'Decision Support Notes', 'More analysis (optional)', 'Geography performance', 'Teams needing attention']) {
        expect(headings).not.toContain(removed);
      }
    });

    it('shows the summary strip with the team score, its change and the KPIs below target', () => {
      renderInsights();
      const strip = screen.getByRole('region', { name: 'Summary' });
      expect(strip).toHaveTextContent('77.5%');
      expect(strip).toHaveTextContent('1.9 pts vs previous month');
      expect(strip).toHaveTextContent('2 of 3 KPIs below target');
    });

    it('shows a critical alert inline only when there are critical priority insights', () => {
      const { unmount } = renderInsights();
      expect(screen.getByRole('button', { name: /2 critical alerts/ })).toBeInTheDocument();
      unmount();

      workspaceMock.overrides = { priority_insights: [] };
      renderInsights();
      expect(screen.queryByRole('button', { name: /critical alerts?/ })).not.toBeInTheDocument();
    });

    it('lists one row per scored KPI in the order the API sends, with the signed effect and the status', () => {
      renderInsights();
      const rows = within(within(section('KPI diagnosis')).getByRole('table')).getAllByRole('row').slice(1);
      expect(rows).toHaveLength(3);
      expect(within(rows[0]).getByRole('button', { name: 'CPL' })).toHaveAttribute('aria-pressed', 'false');
      expect(rows[0]).toHaveTextContent('136 AED vs ≤ 60 AED');
      expect(rows[0]).toHaveTextContent('−3.80 pts');
      expect(rows[0]).toHaveTextContent('Critical');
      expect(rows[0]).toHaveTextContent('Marketing · 44% of target');
      expect(rows[1]).toHaveTextContent('Also in scope: Inbound · Other');
      expect(rows[1]).toHaveTextContent('51.0% vs ≤ 20.0%');
      expect(rows[1]).toHaveTextContent('Critical');
      expect(rows[2]).toHaveTextContent('On target');
    });

    it('shows no team for a KPI when the scope has one team', () => {
      workspaceMock.overrides = {
        kpi_diagnosis: [{
          key: 'cpl', label: 'CPL', unit: 'AED', direction: 'lower_better', weight: 0.2,
          actual: 136, target: 60, achievement_percent: 44.12, status: 'critical', effect_points: -3.8,
          six_months: [], people_below_target: 0, most_below_team: null, other_cohorts: [], teams: ['Marketing'],
        }],
      };
      renderInsights();
      const row = within(within(section('KPI diagnosis')).getByRole('table')).getAllByRole('row')[1];
      expect(within(row).getAllByRole('cell').at(-1)).toHaveTextContent('—');
    });

    it('shows the ten largest negative effects first in a multi-team scope, with a Team column and Show all', async () => {
      const user = userEvent.setup();
      // Backend order: largest negative effect first. Twelve KPIs across two teams.
      workspaceMock.overrides = {
        kpi_diagnosis: Array.from({ length: 12 }, (_, index) => ({
          key: `kpi${index}`, label: `KPI ${index}`, unit: '%', direction: 'higher_better', weight: 0.1,
          actual: 0.5, target: 1, achievement_percent: 50, status: 'critical', effect_points: index - 12,
          people_below_target: 1, six_months: [], most_below_team: null, other_cohorts: [],
          teams: [index % 2 === 0 ? 'Marketing' : 'Inbound'],
        })),
      };
      renderInsights();
      const table = within(section('KPI diagnosis')).getByRole('table');
      expect(within(table).getByRole('columnheader', { name: 'Team' })).toBeInTheDocument();
      expect(within(table).getAllByRole('row').slice(1)).toHaveLength(10);
      expect(within(table).getAllByRole('row')[1]).toHaveTextContent('KPI 0');

      await user.click(within(section('KPI diagnosis')).getByRole('button', { name: 'Show all 12' }));
      expect(within(within(section('KPI diagnosis')).getByRole('table')).getAllByRole('row').slice(1)).toHaveLength(12);
      await user.click(within(section('KPI diagnosis')).getByRole('button', { name: 'Show top 10' }));
      expect(within(within(section('KPI diagnosis')).getByRole('table')).getAllByRole('row').slice(1)).toHaveLength(10);
    });

    it('filters the multi-team table by a team chip and clears the filter with All teams', async () => {
      const user = userEvent.setup();
      renderInsights();
      const diagnosis = section('KPI diagnosis');

      await user.click(within(diagnosis).getByRole('button', { name: 'Inbound' }));
      expect(within(diagnosis).getByRole('button', { name: 'Inbound' })).toHaveAttribute('aria-pressed', 'true');
      expect(within(within(diagnosis).getByRole('table')).getAllByRole('row').slice(1)).toHaveLength(1);

      await user.click(within(diagnosis).getByRole('button', { name: 'All teams' }));
      expect(within(within(diagnosis).getByRole('table')).getAllByRole('row').slice(1)).toHaveLength(3);
    });

    it('names the effect column for what it measures, with the same explanation as its tooltip', () => {
      renderInsights();
      const header = within(section('KPI diagnosis')).getByRole('columnheader', { name: 'Points lost by people below target' });
      expect(header).toHaveAttribute('title', "Effect on team score: the sum of each employee's weighted impact on this KPI, as in People to review.");
    });

    it('notes a KPI that is on target for the team while people below target still lose points', () => {
      workspaceMock.overrides = {
        kpi_diagnosis: [{
          key: 'rejection', label: 'Rejection Rate', unit: '%', direction: 'lower_better', weight: 0.2,
          actual: 0.0089, target: 0.01, achievement_percent: 112.36, status: 'on_track', effect_points: -8.12,
          people_below_target: 4, six_months: [], most_below_team: null, other_cohorts: [], teams: ['Offshore'],
        }],
      };
      renderInsights();
      const row = within(within(section('KPI diagnosis')).getByRole('table')).getAllByRole('row')[1];
      expect(row).toHaveTextContent('−8.12 pts');
      expect(row).toHaveTextContent('Team on target · 4 people below');
    });

    it('selects a KPI from its row: the KPI filter follows and the detail and People to review open for it', async () => {
      const user = userEvent.setup();
      renderInsights();
      await user.click(within(section('KPI diagnosis')).getByRole('button', { name: 'CPL' }));

      expect(latestFilters.current.kpi).toBe('cpl');
      expect(screen.getByRole('region', { name: 'Selected KPI trend' })).toBeInTheDocument();
      expect(within(section('People to review')).getByText(/People pulling the team score down most on CPL/)).toBeInTheDocument();
    });

    it('lists the corrective actions recorded for the selected KPI and counts people below target with no action', async () => {
      const user = userEvent.setup();
      actionMocks.getAllActions.mockReturnValue([action({ is_overdue: true })]);
      renderInsights();
      await user.click(within(section('KPI diagnosis')).getByRole('button', { name: 'CPL' }));

      const actions = section('Actions');
      expect(within(actions).getByText('Coach the booking script')).toBeInTheDocument();
      expect(within(actions).getByText('Ada Owner')).toBeInTheDocument();
      expect(within(actions).getByText(/overdue/)).toHaveClass('text-rose-600');
      expect(actions).toHaveTextContent('1 people below target on CPL have no action yet');
      expect(within(actions).getByRole('button', { name: 'Add action for Analyst Two' })).toBeInTheDocument();
      expect(within(actions).getByRole('link', { name: 'Open follow-up board' })).toHaveAttribute('href', '/corrective-actions');
    });

    it('says so when no action is recorded for the selected KPI, and counts every person below target', async () => {
      const user = userEvent.setup();
      renderInsights();
      await user.click(within(section('KPI diagnosis')).getByRole('button', { name: 'CPL' }));

      const actions = section('Actions');
      expect(actions).toHaveTextContent('No corrective actions are recorded for this KPI in scope.');
      expect(actions).toHaveTextContent('2 people below target on CPL have no action yet');
    });

    it('counts actions with no linked KPI without listing them under a KPI', async () => {
      const user = userEvent.setup();
      actionMocks.getAllActions.mockReturnValue([action({ id: 'act-9', linked_kpi_key: null, action_text: 'General coaching' })]);
      renderInsights();
      await user.click(within(section('KPI diagnosis')).getByRole('button', { name: 'CPL' }));

      const actions = section('Actions');
      expect(within(actions).queryByText('General coaching')).not.toBeInTheDocument();
      expect(actions).toHaveTextContent('1 action in scope has no linked KPI');
    });

    it('links to the Executive Summary for teams and regions, keeping the scope filters', () => {
      renderInsights('/insights?region=UAE');
      const link = screen.getByRole('link', { name: 'Teams and regions are on the Executive Summary' });
      expect(link.getAttribute('href')).toMatch(/^\/executive\?/);
      expect(link.getAttribute('href')).toContain('region=UAE');
    });

    it('shows the same team score as the Executive Summary story for the scope and month', () => {
      renderInsights();
      // executive_story.current_score is the score the Executive Summary shows for the same filters.
      expect(screen.getByRole('region', { name: 'Summary' })).toHaveTextContent('77.5%');
    });

    it('counts KPIs below target by KPI status, not by the Executive Summary person rule (score under 90)', () => {
      renderInsights();
      expect(screen.getByRole('region', { name: 'Summary' })).toHaveTextContent('2 of 3 KPIs below target');
    });

    it('supports branch filter and removes severity, insight type, and status filters', async () => {
      const user = userEvent.setup();
      renderInsights();
      expect(screen.queryByRole('combobox', { name: 'Severity' })).not.toBeInTheDocument();
      expect(screen.queryByRole('combobox', { name: 'Insight type' })).not.toBeInTheDocument();
      expect(screen.queryByRole('combobox', { name: 'Status' })).not.toBeInTheDocument();

      const branchSelect = screen.getByRole('combobox', { name: 'Branch' });
      expect(branchSelect).toBeInTheDocument();
      await user.selectOptions(branchSelect, 'dubai');
      expect(latestFilters.current.branch).toBe('dubai');
    });

    it('preserves function and team filters when branch is selected, narrowing to branch scope', async () => {
      const user = userEvent.setup();
      renderInsights();

      await user.selectOptions(screen.getByRole('combobox', { name: 'Function' }), 'Call Center');
      await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), 'Inbound');
      expect(latestFilters.current).toMatchObject({ teamFunction: 'Call Center', team: 'Inbound' });

      const branchSelect = screen.getByRole('combobox', { name: 'Branch' });
      await user.selectOptions(branchSelect, 'dubai');

      expect(latestFilters.current).toMatchObject({
        branch: 'dubai',
        teamFunction: 'Call Center',
        team: 'Inbound',
      });
      expect(currentSearch().get('branch')).toBe('dubai');
      expect(currentSearch().get('function')).toBe('Call Center');
      expect(currentSearch().get('team')).toBe('Inbound');
    });
  });
});
