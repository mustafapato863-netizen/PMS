import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '../types';
import type { ExecutiveSummary } from '../features/executive/types';
import { composeExecutiveSummary, toExecRecords, type ComposeInput } from '../features/executive/compose';
import { FIXTURE_TEAM_FUNCTIONS, fixtureActions, fixtureAgentRecords, fixtureDrivers } from '../features/executive/executive.fixture';
import type { UseExecutiveSummaryArgs } from '../features/executive/useExecutiveSummary';
import ExecutiveView from './ExecutiveView';
import { periodOptionsFor } from '../features/executive/viewModel';

const state = vi.hoisted(() => ({
  role: 'Admin' as string,
  user: null as Partial<User> | null,
  summary: null as ExecutiveSummary | null,
  loading: false,
  lastArgs: null as UseExecutiveSummaryArgs | null,
}));

vi.mock('../context/RoleContext', () => ({ useUserRole: () => ({ role: state.role }) }));
vi.mock('../context/auth', () => ({ useAuth: () => ({ currentUser: state.user }) }));
vi.mock('../features/executive/useExecutiveSummary', () => ({
  useExecutiveSummary: (args: UseExecutiveSummaryArgs) => {
    state.lastArgs = args;
    return {
      summary: state.summary,
      options: { regions: ['EGY', 'UAE'], functions: ['Call Center', 'RCM', 'Pre-Approvals', 'Marketing'], teams: ['Inbound', 'Outbound'], levels: ['Employee'] },
      isLoading: state.loading,
      error: null,
      source: 'composed',
      managerTeam: args.view === 'managerial' ? 'Inbound' : null,
    };
  },
}));
vi.mock('../lib/apiClient', () => ({
  apiFetch: vi.fn().mockResolvedValue({
    success: true,
    data: { items: [], page_size: 8, next_cursor: null, has_more: false, total: 0 },
  }),
}));

const TODAY = new Date(2026, 6, 6);
const records = toExecRecords(fixtureAgentRecords());
const build = (patch: Partial<ComposeInput> = {}) => composeExecutiveSummary({
  view: 'corporate', role: 'Admin', records, filters: {}, teamFunctions: FIXTURE_TEAM_FUNCTIONS,
  drivers: fixtureDrivers(), actions: fixtureActions(TODAY), comparisonRecords: records, today: TODAY, ...patch,
});

function renderAt(path = '/executive') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/executive" element={<ExecutiveView />} />
          <Route path="/function-summary" element={<div>Function Summary page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const launcher = screen.queryByRole('button', { name: /Executive filters/i });
  if (launcher) fireEvent.click(launcher);
  return rendered;
}

beforeEach(() => {
  state.role = 'Admin';
  state.user = { id: 'u1', name: 'Super Admin', role: 'Admin', accessible_teams: [] };
  state.summary = build();
  state.loading = false;
  state.lastArgs = null;
});

describe('ExecutiveView role routing', () => {
  it.each(['Admin', 'General Manager', 'Executive', 'Viewer'])('%s gets the Corporate view', (role) => {
    state.role = role;
    renderAt();
    expect(state.lastArgs?.view).toBe('corporate');
    expect(screen.getByTestId('executive-corporate')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Executive Summary' })).toBeInTheDocument();
  });

  it('Manager gets the Managerial view with region/function/team locked', () => {
    state.role = 'Manager';
    state.user = { id: 'm1', name: 'Hany Mostafa', role: 'Manager', accessible_teams: ['Inbound'] };
    state.summary = build({ view: 'managerial', role: 'Manager', team: 'Inbound', comparisonRecords: null });
    renderAt();
    expect(state.lastArgs).toMatchObject({ view: 'managerial', managerTeams: ['Inbound'] });
    expect(screen.getByTestId('executive-managerial')).toBeInTheDocument();
    expect(screen.getByText('Team scope')).toBeInTheDocument();
    const filters = screen.getByRole('group', { name: 'Executive filters' });
    expect(within(filters).getByRole('group', { name: /Region: EGY \(fixed by your role\)/ })).toBeInTheDocument();
    expect(within(filters).getByRole('group', { name: /Function: Call Center \(fixed by your role\)/ })).toBeInTheDocument();
    expect(within(filters).getByRole('group', { name: /Team: Inbound \(fixed by your role\)/ })).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('Scoped to your team');
    expect(screen.getByRole('note')).toHaveTextContent('function-average comparison appears once the backend summary endpoint is live');
    expect(screen.getByRole('heading', { name: 'Team KPIs — worst first' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Corrective actions' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Functions' })).not.toBeInTheDocument();
  });

  it('applies the selected team parent function together with the team filter', () => {
    renderAt();

    fireEvent.change(screen.getByLabelText('Team'), { target: { value: 'Inbound' } });

    expect(state.lastArgs?.filters).toMatchObject({ teamFunction: 'Call Center', team: 'Inbound' });
  });

  it('clears scope filters from the icon while preserving the selected period', () => {
    renderAt('/executive?period=2026-06&region=UAE&branch=Dubai&function=RCM&team=Inbound&level=Employee');

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));

    expect(state.lastArgs?.filters).toEqual({ periodKey: '2026-06' });
  });

  it('Function Viewer is redirected to /function-summary', () => {
    state.role = 'Function Viewer';
    renderAt();
    expect(screen.getByText('Function Summary page')).toBeInTheDocument();
  });

  it('marks the corporate view read-only for Executive and Viewer, not for Admin', () => {
    state.role = 'Executive';
    const { unmount } = renderAt();
    expect(screen.getByText('Read-only')).toBeInTheDocument();
    unmount();
    state.role = 'Admin';
    renderAt();
    expect(screen.queryByText('Read-only')).not.toBeInTheDocument();
  });
});

describe('Corporate sections', () => {
  it('renders hero, function cards, drivers, regions, teams at risk, grades and actions', () => {
    renderAt();
    expect(screen.getByRole('heading', { name: /^June 2026 company performance is \d+\.\d% below target\.$/ })).toBeInTheDocument();
    expect(screen.getAllByRole('article').map((card) => card.getAttribute('aria-label'))).toEqual([
      'Call Center function', 'RCM function', 'Pre-Approvals function', 'Marketing function',
    ]);
    expect(screen.getByRole('link', { name: 'View RCM function' })).toHaveAttribute('href', '/function-summary/rcm');
    expect(screen.getByRole('heading', { name: 'What moved the score vs May' })).toBeInTheDocument();
    expect(screen.getAllByTestId('region-box')).toHaveLength(2);
    expect(screen.getByRole('heading', { name: 'All teams' })).toBeInTheDocument();
    expect(screen.getAllByTestId('risk-row')).toHaveLength(state.summary?.teams.length ?? 0);
    expect(screen.getByRole('heading', { name: 'Grade distribution' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Corrective actions' })).toBeInTheDocument();
    expect(screen.getByTestId('corrective-action-insights')).toBeInTheDocument();
    expect(screen.queryByTestId('action-tile-due-this-week')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open Corrective Actions' })).not.toBeInTheDocument();
  });

  it('labels the driver metric neutrally until weighted_gap_points arrives', () => {
    renderAt();
    expect(screen.getByText(/change in the KPI's weighted contribution to the score vs May/)).toBeInTheDocument();
  });

  it('switches the driver footnote to weight × gap when the backend sends it', () => {
    state.summary = build({ drivers: fixtureDrivers({ weightedGap: true }) });
    renderAt();
    expect(screen.getByText('Impact = KPI weight × gap to target, in score points.')).toBeInTheDocument();
  });

  it('renders direction-aware driver rows: a rising lower-is-better KPI is red, a falling one is green', () => {
    renderAt();
    const negatives = screen.getAllByTestId('driver-negative');
    const rejection = negatives.find((row) => row.textContent?.includes('Initial Rejection %'))!;
    expect(within(rejection).getByText('↓ better')).toBeInTheDocument();
    expect(within(rejection).getByText('↓ −1.6 pp')).toHaveAttribute('data-tone', 'bad');
    const denial = screen.getAllByTestId('driver-positive').find((row) => row.textContent?.includes('Denial Rate'))!;
    expect(within(denial).getByText('↑ +0.8 pp')).toHaveAttribute('data-tone', 'good');
  });

  it('hides function links and the Insights link for Executive (no Function Summary / Insights access)', () => {
    state.role = 'Executive';
    renderAt();
    expect(screen.queryByRole('link', { name: /View .* function/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'View all drivers' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Corrective actions' })).toBeInTheDocument();
  });

  it('hides corrective actions for Viewer (no follow-up access)', () => {
    state.role = 'Viewer';
    renderAt();
    expect(screen.queryByRole('heading', { name: 'Corrective actions' })).not.toBeInTheDocument();
  });

  it('softens drivers when the workspace is unavailable instead of inventing numbers', () => {
    state.summary = build({ drivers: null });
    renderAt();
    expect(screen.getByText("Driver analysis isn't available for this view yet.")).toBeInTheDocument();
    expect(screen.queryAllByTestId('driver-negative')).toHaveLength(0);
  });
});

describe('fallback and empty states', () => {
  it('shows the fallback notice when the requested month has no data', () => {
    state.summary = build({ requestedPeriodKey: '2026-07' });
    renderAt('/executive?period=2026-07');
    expect(screen.getByText('No performance data for July 2026 yet — showing June 2026, the latest month with data.')).toBeInTheDocument();
    expect(screen.getByTestId('executive-corporate')).toBeInTheDocument();
    expect(state.lastArgs?.filters.periodKey).toBe('2026-07');
  });

  it('shows the full empty state with Upload for Admin when the scope has no data at all', () => {
    state.summary = build({ records: [], comparisonRecords: [] });
    renderAt('/executive?period=2026-07');
    expect(screen.getByTestId('executive-empty')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'No performance data for July 2026' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Upload performance data' })).toHaveAttribute('href', '/settings');
    expect(screen.getByRole('button', { name: 'Pick another month' })).toBeInTheDocument();
  });

  it('tells non-admins to ask their admin instead of offering Upload', () => {
    state.role = 'Manager';
    state.summary = build({ view: 'managerial', role: 'Manager', team: 'Inbound', records: [], comparisonRecords: null });
    renderAt('/executive?period=2026-07');
    expect(screen.queryByRole('link', { name: 'Upload performance data' })).not.toBeInTheDocument();
    expect(screen.getByText('Ask your admin to upload July data.')).toBeInTheDocument();
  });

  it('lists the requested month as "(no data)" in the Date filter', () => {
    const options = periodOptionsFor(build(), '2026-07', TODAY);
    expect(options[0]).toEqual({ value: '2026-07', label: 'July 2026 (no data)' });
    expect(options[1]).toEqual({ value: '2026-06', label: 'June 2026' });
  });
});
