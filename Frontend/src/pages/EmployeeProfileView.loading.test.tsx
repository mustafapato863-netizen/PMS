import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import EmployeeProfileView from './EmployeeProfileView';

const state = vi.hoisted(() => ({ loading: true }));

vi.mock('../hooks/usePerformanceData', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/usePerformanceData')>()),
  useTeamData: () => ({ rows: [], loading: state.loading }),
  usePerformanceData: () => ({ agents: [], loading: false }),
}));
vi.mock('../features/executive/useSummaryRecords', () => ({ useSummaryRecords: () => ({ data: undefined, isLoading: false }) }));
vi.mock('../hooks/api/usePerformanceDashboard', () => ({
  scopedPerformanceApiEnabled: false,
  useScopedEmployeePerformanceHistory: () => ({ data: [], isLoading: false }),
}));
vi.mock('../context/RoleContext', () => ({ useUserRole: () => ({ role: 'Admin' }) }));
vi.mock('../features/executive/useFunctionScope', () => ({ useFunctionScope: () => ({ scope: null, allowedFunctions: [], isRestricted: false }) }));
vi.mock('../context/auth', () => ({ useAuth: () => ({ currentUser: { id: 'u1', name: 'Admin', username: 'admin', role: 'Admin' } }) }));
vi.mock('../lib/apiClient', () => ({ apiFetch: vi.fn(async () => ({ success: false })) }));

const show = () => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={['/employee/E404']}>
      <Routes><Route path="/employee/:employeeId" element={<EmployeeProfileView />} /></Routes>
    </MemoryRouter>
  </QueryClientProvider>,
);

describe('employee profile loading state', () => {
  beforeEach(() => { localStorage.clear(); });

  it('does not say "Employee not found" while the roster is still loading', () => {
    state.loading = true;
    show();
    expect(screen.queryByText('Employee not found')).not.toBeInTheDocument();
  });

  it('says "Employee not found" once the roster has loaded without the employee', () => {
    state.loading = false;
    show();
    expect(screen.getByText('Employee not found')).toBeInTheDocument();
  });
});
