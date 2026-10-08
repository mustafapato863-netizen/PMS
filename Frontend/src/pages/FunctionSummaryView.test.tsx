import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '../types';
import type { ExecutiveSummary } from '../features/executive/types';
import { composeExecutiveSummary, toExecRecords, type ComposeInput } from '../features/executive/compose';
import { FIXTURE_TEAM_FUNCTIONS, fixtureAgentRecords, fixtureDrivers } from '../features/executive/executive.fixture';
import type { UseExecutiveSummaryArgs } from '../features/executive/useExecutiveSummary';
import FunctionSummaryView from './FunctionSummaryView';

const state = vi.hoisted(() => ({
  role: 'Function Viewer' as string,
  user: null as Partial<User> | null,
  summary: null as ExecutiveSummary | null,
  lastArgs: null as UseExecutiveSummaryArgs | null,
}));

vi.mock('../context/RoleContext', () => ({ useUserRole: () => ({ role: state.role }) }));
vi.mock('../context/auth', () => ({ useAuth: () => ({ currentUser: state.user }) }));
vi.mock('../hooks/useActionStore', () => ({ useUpdateActionStatus: () => ({ mutateAsync: vi.fn() }) }));
vi.mock('../features/executive/useSummaryRecords', () => ({ useSummaryRecords: () => ({ data: undefined, isError: true, isLoading: false }) }));
vi.mock('../features/executive/useExecutiveSummary', () => ({
  useExecutiveSummary: (args: UseExecutiveSummaryArgs) => {
    state.lastArgs = args;
    return {
      summary: state.summary,
      options: { regions: ['EGY', 'UAE'], functions: [], teams: ['Coding', 'Submission', 'Pre-Approvals OP Dubai', 'Pre-Approvals IP Offshore'], levels: ['Employee'] },
      isLoading: false,
      error: null,
      source: 'composed',
      managerTeam: null,
    };
  },
}));

vi.mock('../hooks/usePerformanceData', () => ({
  usePerformanceData: () => ({ agents: [], loading: false }),
  mapScopedPerformanceRecord: (record: unknown) => record,
}));
vi.mock('../hooks/api/usePerformanceDashboard', () => ({
  scopedPerformanceApiEnabled: false,
  useScopedEmployeePerformanceHistory: () => ({ data: undefined, isFetching: false, isError: false }),
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
  view: 'function', role: 'Function Viewer', records, filters: {}, functionName: 'RCM', teamFunctions: FIXTURE_TEAM_FUNCTIONS,
  drivers: null, actions: null, comparisonRecords: null, today: TODAY, ...patch,
});

function Where() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/function-summary" element={<FunctionSummaryView />} />
          <Route path="/function-summary/:functionSlug" element={<FunctionSummaryView />} />
        </Routes>
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const launcher = screen.queryByRole('button', { name: /Function filters/i });
  if (launcher) fireEvent.click(launcher);
  return rendered;
}

beforeEach(() => {
  state.role = 'Function Viewer';
  state.user = { id: 'fv1', name: 'Laila Ashraf', role: 'Function Viewer', accessible_teams: [], accessible_functions: ['RCM', 'Pre-Approvals'] };
  state.summary = build();
  state.lastArgs = null;
});

describe('Function Summary routing and scope', () => {
  it('treats legacy All filter values as unfiltered', () => {
    state.role = 'Admin';
    renderAt('/function-summary/rcm?region=All&branch=all&team=ALL&level=All&position=All');
    expect(state.lastArgs?.filters).toMatchObject({
      region: undefined, branch: undefined, team: undefined, performanceLevel: undefined, position: undefined,
    });
    expect(screen.getByLabelText('Region')).toHaveValue('');
  });
  it('redirects the old public Pre-Approvals route to its RCM parent team', () => {
    state.role = 'Admin';
    renderAt('/function-summary/pre-approvals?period=2026-06');
    expect(screen.getByTestId('location')).toHaveTextContent('/function-summary/rcm?period=2026-06&team=Pre-Approvals');
    expect(state.lastArgs).toMatchObject({ functionName: 'RCM', filters: { team: 'Pre-Approvals' } });
  });

  it('filters a sub-team and clears it without dropping the assigned function or period', () => {
    state.role = 'Function Director';
    state.user = { id: 'fd', role: 'Function Director', accessible_functions: ['RCM'] };
    renderAt('/function-summary/rcm?period=2026-06&team=Pre-Approvals&sub_team=Pre-Approvals%20IP%20Offshore&level=Corporate');
    expect(screen.getByRole('group', { name: /Function: RCM \(fixed by your role\)/ })).toHaveAttribute('aria-disabled', 'true');
    expect(state.lastArgs).toMatchObject({ functionName: 'RCM', filters: { team: 'Pre-Approvals IP Offshore', performanceLevel: 'Corporate' } });
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/function-summary/rcm?period=2026-06');
    expect(state.lastArgs).toMatchObject({ functionName: 'RCM', accessibleFunctions: ['RCM'] });
    expect(state.lastArgs?.filters.team).toBeUndefined();
  });
  it('redirects /function-summary to the first allowed function, keeping the query', () => {
    renderAt('/function-summary?period=2026-06');
    expect(screen.getByTestId('location')).toHaveTextContent('/function-summary/rcm?period=2026-06');
  });

  it('redirects an unknown or disallowed slug to the first allowed function', () => {
    const { unmount } = renderAt('/function-summary/call-center');
    expect(screen.getByTestId('location')).toHaveTextContent('/function-summary/rcm');
    unmount();
    renderAt('/function-summary/finance');
    expect(screen.getByTestId('location')).toHaveTextContent('/function-summary/rcm');
  });

  it('opens an allowed function and asks for the function view only', () => {
    state.summary = build({ functionName: 'Pre-Approvals' });
    renderAt('/function-summary/pre-approvals');
    expect(screen.getByTestId('location')).toHaveTextContent('/function-summary/pre-approvals');
    expect(state.lastArgs).toMatchObject({ view: 'function', functionName: 'Pre-Approvals', accessibleFunctions: ['RCM', 'Pre-Approvals'] });
  });

  it('lets Admin open every current function', () => {
    state.role = 'Admin';
    state.user = { id: 'a1', name: 'Admin', role: 'Admin', accessible_teams: [] };
    state.summary = build({ role: 'Admin', functionName: 'Marketing' });
    renderAt('/function-summary/marketing');
    expect(screen.getByTestId('location')).toHaveTextContent('/function-summary/marketing');
    expect(screen.getAllByRole('radio').map((radio) => radio.textContent)).toEqual(['Call Center', 'RCM', 'Marketing', 'Sales', 'CSR', 'Pharmacy']);
    expect(screen.queryByText('Read-only')).not.toBeInTheDocument();
  });

  it('shows a clear message when none of the assigned functions is known', () => {
    state.user = { ...state.user, accessible_functions: ['Finance'] };
    renderAt('/function-summary');
    expect(screen.getByRole('alert')).toHaveTextContent('No functions are assigned to your account yet');
  });
});

describe('Function Summary page', () => {
  it('renders the function layout read-only with the switcher limited to assigned functions', () => {
    renderAt('/function-summary/rcm');
    expect(screen.getByRole('heading', { name: 'Function Summary' })).toBeInTheDocument();
    expect(screen.getByText(/^RCM · June 2026 vs May 2026 · 7 teams · \d+ people$/)).toBeInTheDocument();
    expect(screen.getByText(/Submission leads at \d+\.\d%; Pre-Approvals IP Final .*is holding the function back\./)).toBeInTheDocument();
    expect(screen.getByText('Read-only')).toBeInTheDocument();
    const switcher = screen.getByRole('radiogroup', { name: 'Function' });
    expect(within(switcher).getAllByRole('radio').map((radio) => radio.textContent)).toEqual(['RCM', 'Pre-Approvals']);
    expect(within(switcher).getByRole('radio', { name: 'RCM' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByText(/Read-only view of your functions \(RCM, Pre-Approvals\)/)).toBeInTheDocument();
    expect(screen.getByTestId('executive-function')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Team leaderboard' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Function KPI rollup — worst first' })).toBeInTheDocument();
    expect(screen.getByText(/Headcount-weighted across RCM teams · June 2026/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Level split' })).toBeInTheDocument();
    // No corrective actions or function cards on the function view.
    expect(screen.queryByRole('heading', { name: 'Functions' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /corrective actions/i })).not.toBeInTheDocument();
  });

  it('lists only the function teams in the leaderboard, linked to their dashboards', () => {
    renderAt('/function-summary/rcm');
    const board = screen.getByRole('region', { name: 'Team leaderboard' });
    const names = within(board).getAllByRole('link').map((link) => link.textContent);
    expect(names).toEqual(expect.arrayContaining(['Coding', 'Submission', 'Re-Submission', 'Pre-Approvals IP Offshore']));
    expect(names).not.toContain('Inbound');
    expect(names).toContain('Pre-Approvals OP Final');
    expect(within(board).getByRole('link', { name: 'Coding' })).toHaveAttribute('href', '/team/coding');
  });

  it('switching function navigates and keeps period + level only', () => {
    renderAt('/function-summary/rcm?period=2026-05&level=Employee&team=Coding');
    fireEvent.click(screen.getByRole('radio', { name: 'Pre-Approvals' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/function-summary/pre-approvals?period=2026-05&level=Employee');
  });

  it('labels the team filter for the function', () => {
    renderAt('/function-summary/rcm');
    expect(screen.getByRole('button', { name: /Team/ })).toHaveTextContent('All RCM teams');
  });

  it('removes Reports & export and offers all three performance levels and branch choices', () => {
    renderAt('/function-summary/rcm');
    expect(screen.queryByTestId('function-export')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Reports & export' })).not.toBeInTheDocument();
    const levelSelect = screen.getByRole('combobox', { name: 'Performance level' });
    expect(within(levelSelect).getAllByRole('option').map((option) => option.textContent)).toEqual(['All levels', 'Employee', 'Managerial', 'Corporate']);
    const branchSelect = screen.getByRole('combobox', { name: 'Branch' });
    expect(within(branchSelect).getAllByRole('option').map((option) => option.textContent)).toEqual(['All Branches', 'Dubai', 'Sharjah (Sharqa)', 'Ajman', 'Clinics']);
    fireEvent.change(branchSelect, { target: { value: 'sharjah' } });
    expect(state.lastArgs?.filters.branch).toBe('sharjah');
    fireEvent.change(levelSelect, { target: { value: 'Corporate' } });
    expect(state.lastArgs?.filters.performanceLevel).toBe('Corporate');
  });

  it('softens the drivers card when driver analysis is unavailable to the Function Viewer', () => {
    renderAt('/function-summary/rcm');
    expect(screen.getByRole('heading', { name: 'What moved RCM vs May' })).toBeInTheDocument();
    expect(screen.getByText("Driver analysis isn't available for this view yet.")).toBeInTheDocument();
  });

  it('shows the full empty state only when the function has no data at all', () => {
    state.summary = build({ records: [] });
    renderAt('/function-summary/rcm');
    expect(screen.queryByTestId('executive-function')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Upload/ })).not.toBeInTheDocument();
  });
});

describe('Function view compose', () => {
  it('only claims "Most improved" against the other functions when all-function records exist', () => {
    const withoutComparison = build();
    expect(withoutComparison.highlights.most_improved).toBeNull();
    const all = composeExecutiveSummary({
      view: 'corporate', role: 'Admin', records, filters: {}, teamFunctions: FIXTURE_TEAM_FUNCTIONS, comparisonRecords: records, today: TODAY,
    });
    const leader = all.functions.find((card) => card.is_most_improved)?.function;
    const rcm = build({ role: 'Admin', comparisonRecords: records });
    expect(Boolean(rcm.highlights.most_improved)).toBe(leader === 'RCM');
  });

  it('filters drivers to the function when they are available (Admin)', () => {
    const summary = build({ role: 'Admin', drivers: fixtureDrivers({ weightedGap: true }), comparisonRecords: records });
    expect(summary.meta.unavailable).not.toContain('drivers');
    [...summary.drivers.negative, ...summary.drivers.positive].forEach((driver) => {
      expect(driver.function === undefined || driver.function === null || driver.function === 'RCM').toBe(true);
    });
  });
});
