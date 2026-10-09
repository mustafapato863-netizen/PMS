import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '../types';
import { ThemeProvider } from '../context/ThemeContext';
import ExecutiveView from './ExecutiveView';

const state = vi.hoisted(() => ({
  role: 'Admin' as string,
  user: { id: 'u1', name: 'Super Admin', role: 'Admin', accessible_teams: [] } as Partial<User>,
}));

vi.mock('../context/RoleContext', () => ({ useUserRole: () => ({ role: state.role }) }));
vi.mock('../context/auth', () => ({ useAuth: () => ({ currentUser: state.user }) }));
vi.mock('../hooks/useActionStore', () => ({ useActionStore: () => ({ getAllActions: () => [] }) }));
vi.mock('../lib/apiClient', () => ({ apiFetch: vi.fn().mockResolvedValue({ success: true, data: [] }) }));
vi.mock('../hooks/api/usePerformanceDashboard', () => ({
  scopedPerformanceApiEnabled: true,
  useScopedExecutiveSummary: () => ({
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
    previousTotalAgents: 10,
    previousOverallAvgScore: 80,
    previousPctAB: 55,
    previousPctDE: 10,
    loading: false,
    dataSource: 'api',
    errorMessage: null,
  }),
}));

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

beforeEach(() => {
  state.role = 'Admin';
  state.user = { id: 'u1', name: 'Super Admin', role: 'Admin', accessible_teams: [] };
});

describe('Executive overview', () => {
  it('restores the company overview with region, branch and month filters', () => {
    renderAt();
    expect(screen.getByRole('heading', { name: 'Executive Overview' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Filters/ }));
    expect(screen.getByRole('combobox', { name: 'Filter by region' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Filter by branch' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Filter by month' })).toBeInTheDocument();
    expect(screen.getByText('Total Agents')).toBeInTheDocument();
    expect(screen.getByText('Avg Performance Score')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Actions Summary' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Team Summary' })).toBeInTheDocument();
  });

  it('sends a Function Viewer to Function Summary', () => {
    state.role = 'Function Viewer';
    renderAt();
    expect(screen.getByText('Function Summary page')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Executive Overview' })).not.toBeInTheDocument();
  });
});
