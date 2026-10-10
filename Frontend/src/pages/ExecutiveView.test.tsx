import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, RouterProvider, Routes, createMemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '../types';
import { ThemeProvider } from '../context/ThemeContext';
import ExecutiveView from './ExecutiveView';

const state = vi.hoisted(() => ({
  role: 'Admin' as string,
  user: { id: 'u1', name: 'Super Admin', role: 'Admin', accessible_teams: [] } as Partial<User>,
}));

const calls = vi.hoisted(() => ({ summary: [] as unknown[][] }));

vi.mock('../context/RoleContext', () => ({ useUserRole: () => ({ role: state.role }) }));
vi.mock('../context/auth', () => ({ useAuth: () => ({ currentUser: state.user }) }));
vi.mock('../hooks/useActionStore', () => ({ useActionStore: () => ({ getAllActions: () => [] }) }));
vi.mock('../lib/apiClient', () => ({ apiFetch: vi.fn().mockResolvedValue({ success: true, data: [] }) }));
vi.mock('../hooks/api/usePerformanceDashboard', () => ({
  scopedPerformanceApiEnabled: true,
  useScopedExecutiveSummary: (...args: unknown[]) => {
    calls.summary.push(args);
    return {
      summaries: [],
      previousSummaries: [],
      totalAgents: 12,
      uniqueTeamCount: 3,
      overallAvgScore: 84.2,
      pctAB: 61.5,
      pctDE: 8.4,
      allClassCounts: { A: 4, B: 3, C: 3, D: 1, E: 1 },
      uniqueMonths: ['May', 'June'],
      activePeriod: { month: 'June', year: 2026, key: '2026-06' },
      previousPeriod: { month: 'May', year: 2026, key: '2026-05' },
      basisContext: { state: 'changed', like_for_like: false, raw_performance: 'partial', reasons: ['weight'], message: 'Scores can be affected by evaluation settings.' },
      previousTotalAgents: 10,
      previousOverallAvgScore: 80,
      previousPctAB: 55,
      previousPctDE: 10,
      loading: false,
      dataSource: 'api',
      errorMessage: null,
    };
  },
}));

function lastSummary() {
  return calls.summary.at(-1) as [string, string, string, string];
}

function renderAt(path = '/executive') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/executive" element={<ExecutiveView />} />
            <Route path="/function-summary" element={<div>Function Summary page</div>} />
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

function renderHistory(entries: string[]) {
  const router = createMemoryRouter([
    { path: '/executive', element: <ExecutiveView /> },
    { path: '/function-summary', element: <div>Function Summary page</div> },
  ], { initialEntries: entries, initialIndex: entries.length - 1 });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <RouterProvider router={router} />
      </ThemeProvider>
    </QueryClientProvider>,
  );
  return router;
}

function openFilters() {
  fireEvent.click(screen.getByRole('button', { name: /Filters/ }));
}

beforeEach(() => {
  state.role = 'Admin';
  state.user = { id: 'u1', name: 'Super Admin', role: 'Admin', accessible_teams: [] };
  calls.summary.length = 0;
});

describe('Executive overview', () => {
  it('shows the scoped API basis note without replacing numeric performance', () => {
    renderAt();
    expect(screen.getByTestId('basis-comparison-note')).toHaveTextContent('Scores can be affected by evaluation settings.');
    expect(screen.getByText('84.2%')).toBeInTheDocument();
    expect(lastSummary()).toEqual(['All', 'All', 'all', 'All']);
  });
  it('restores the company overview with region, branch and month filters', () => {
    renderAt();
    expect(screen.getByRole('heading', { name: 'Executive Overview' })).toBeInTheDocument();
    openFilters();
    expect(screen.getByRole('combobox', { name: 'Filter by region' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Filter by branch' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Filter by month' })).toBeInTheDocument();
    expect(screen.getByText('Total Agents')).toBeInTheDocument();
    expect(screen.getByText('Avg Performance Score')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Actions Summary' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Team Summary' })).toBeInTheDocument();
  });

  it('sends a Function Viewer to Function Summary without mounting the overview', () => {
    state.role = 'Function Viewer';
    renderAt();
    expect(screen.getByText('Function Summary page')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Executive Overview' })).not.toBeInTheDocument();
    expect(calls.summary).toHaveLength(0);
  });

  it('sends a Function Director to Function Summary and does not clear the function scope here', () => {
    state.role = 'Function Director';
    state.user = { id: 'fd', role: 'Function Director', accessible_functions: ['Call Center'] };
    renderAt('/executive?function=Marketing');
    expect(screen.getByText('Function Summary page')).toBeInTheDocument();
    expect(calls.summary).toHaveLength(0);
  });

  it('passes an exact period through even when the same month name is also present', () => {
    renderAt('/executive?period=2025-07&month=July');
    expect(lastSummary()[0]).toBe('2025-07');
    openFilters();
    expect(screen.getByRole('combobox', { name: 'Filter by month' })).toHaveValue('July');
  });

  it('locks a Branch Director to the assigned branch and keeps that scope when filters are cleared', () => {
    state.role = 'Branch Director';
    state.user = { id: 'bd', role: 'Branch Director', accessible_branches: ['Dubai'] };
    renderAt('/executive?period=2025-07&branch=sharjah&region=EGY&performance_level=Employee');
    expect(lastSummary()).toEqual(['2025-07', 'EGY', 'dubai', 'Employee']);
    openFilters();
    const branch = screen.getByRole('combobox', { name: 'Filter by branch' });
    expect(branch).toBeDisabled();
    expect(branch).toHaveValue('dubai');
    expect(Array.from((branch as HTMLSelectElement).options).map((option) => option.value)).toEqual(['dubai']);
    fireEvent.change(branch, { target: { value: 'sharjah' } });
    expect(lastSummary()[2]).toBe('dubai');
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(lastSummary()).toEqual(['2025-07', 'All', 'dubai', 'All']);
    expect(screen.getByRole('heading', { name: 'Executive Overview' })).toBeInTheDocument();
  });

  it('locks a Regional Manager to the assigned region when the URL names another region', () => {
    state.role = 'Regional Manager';
    state.user = { id: 'rm', role: 'Regional Manager', accessible_regions: ['uae'] };
    renderAt('/executive?region=EGY&branch=sharjah');
    expect(lastSummary()[1]).toBe('UAE');
    expect(lastSummary()[2]).toBe('sharjah');
    openFilters();
    const region = screen.getByRole('combobox', { name: 'Filter by region' });
    expect(region).toBeDisabled();
    expect(region).toHaveValue('UAE');
    fireEvent.change(region, { target: { value: 'EGY' } });
    expect(lastSummary()[1]).toBe('UAE');
  });

  it('does not invent one branch or region when several are assigned', () => {
    state.role = 'Branch Director';
    state.user = { id: 'bd', role: 'Branch Director', accessible_branches: ['Dubai', 'Sharjah'] };
    renderAt('/executive?branch=ajman');
    expect(lastSummary()[2]).toBe('all');
    openFilters();
    const branch = screen.getByRole('combobox', { name: 'Filter by branch' });
    expect(branch).toBeDisabled();
    expect(branch).toHaveTextContent('dubai, sharjah');
    cleanup();

    state.role = 'Regional Manager';
    state.user = { id: 'rm', role: 'Regional Manager', accessible_regions: ['EGY', 'KSA'] };
    renderAt('/executive?region=UAE');
    expect(lastSummary()[1]).toBe('All');
    openFilters();
    expect(screen.getAllByRole('combobox', { name: 'Filter by region' }).at(-1)).toHaveTextContent('EGY, KSA');
  });

  it('lets an Admin follow the branch in the URL and drops an exact period when the month changes', () => {
    renderAt('/executive?period=2025-07&month=July&branch=sharjah&region=UAE&performance_level=Employee');
    expect(lastSummary()).toEqual(['2025-07', 'UAE', 'sharjah', 'Employee']);
    openFilters();
    expect(screen.getByRole('combobox', { name: 'Filter by branch' })).toBeEnabled();
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter by month' }), { target: { value: 'June' } });
    expect(lastSummary()).toEqual(['June', 'UAE', 'sharjah', 'Employee']);
  });

  it('keeps the assigned branch when the back stack contains a tampered branch URL', async () => {
    state.role = 'Branch Director';
    state.user = { id: 'bd', role: 'Branch Director', accessible_branches: ['dubai'] };
    const router = renderHistory([
      '/executive?period=2025-07&branch=dubai',
      '/executive?period=2025-07&branch=sharjah',
    ]);
    expect(lastSummary()[2]).toBe('dubai');
    await act(async () => { await router.navigate(-1); });
    expect(router.state.location.pathname).toBe('/executive');
    expect(screen.getByRole('heading', { name: 'Executive Overview' })).toBeInTheDocument();
    expect(screen.queryByText('Function Summary page')).not.toBeInTheDocument();
    expect(lastSummary()).toEqual(['2025-07', 'All', 'dubai', 'All']);
  });

  it('restores an unlocked branch from the back stack', async () => {
    const router = renderHistory([
      '/executive?branch=dubai',
      '/executive?branch=sharjah',
    ]);
    expect(lastSummary()[2]).toBe('sharjah');
    await act(async () => { await router.navigate(-1); });
    expect(router.state.location.pathname).toBe('/executive');
    expect(lastSummary()[2]).toBe('dubai');
  });
});
