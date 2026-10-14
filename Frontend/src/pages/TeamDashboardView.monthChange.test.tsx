import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '../context/ThemeContext';
import TeamDashboardView from './TeamDashboardView';

const hookState = vi.hoisted(() => ({
  prevPeriodKey: '2026-06' as string | null,
  prevTotalAgents: 8,
  prevAvgScore: 82,
  prevPctAB: 45,
  prevPctDE: 12,
}));

vi.mock('../context/RoleContext', () => ({
  useUserRole: () => ({ role: 'Admin', fetchWithRole: vi.fn() }),
}));
vi.mock('../context/auth', () => ({ useAuth: () => ({ currentUser: null }) }));
vi.mock('../features/executive/useFunctionScope', () => ({
  useFunctionScope: () => ({ restricted: false, allowed: [], allowsTeam: () => true }),
}));
vi.mock('../hooks/useTeamConfig', () => ({ useTeamConfig: () => ({ data: undefined }) }));
vi.mock('../hooks/api/useInsightsWorkspace', () => ({ useInsightsWorkspace: () => ({ data: undefined }) }));
vi.mock('../hooks/useActionStore', () => ({
  useActionStore: () => ({ getActionsForEmployee: () => [], getAllActions: () => [] }),
}));
vi.mock('../lib/apiClient', () => ({ apiFetch: vi.fn(() => Promise.resolve({ success: false })) }));
vi.mock('../hooks/usePerformanceData', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/usePerformanceData')>()),
  // Headcount 10 against 8 last month, average 85 against 82, A&B 50 against 45, D&E 10 against 12.
  useTeamData: () => ({
    rows: [], avgScore: 85, classCounts: { A: 1, B: 4, C: 3, D: 1, E: 1 }, pctAB: 50, pctDE: 10,
    totalAgents: 10, uniqueTeamCount: 3, prevMonth: hookState.prevPeriodKey ? 'June' : null,
    prevPeriodKey: hookState.prevPeriodKey, previousPeriodAgents: [],
    loading: false, dataSource: 'api', errorMessage: null,
    prevAvgScore: hookState.prevAvgScore, prevPctAB: hookState.prevPctAB, prevPctDE: hookState.prevPctDE,
    prevTotalAgents: hookState.prevTotalAgents,
  }),
  usePerformanceData: () => ({ uniqueMonths: [], agents: [] }),
}));

function renderAllTeams(search: string) {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[`/team/all${search}`]}>
        <Routes>
          <Route path="/team/:teamId" element={<TeamDashboardView />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  hookState.prevPeriodKey = '2026-06';
  hookState.prevTotalAgents = 8;
  hookState.prevAvgScore = 82;
  hookState.prevPctAB = 45;
  hookState.prevPctDE = 12;
});

describe('summary tiles change against the previous month', () => {
  it('shows the change for a selected month against the previous month', () => {
    renderAllTeams('?month=2026-07');

    expect(screen.getByText('+2 vs Jun')).toBeInTheDocument();
    expect(screen.getByText('+3.0 pts vs Jun')).toBeInTheDocument();
    expect(screen.getByText('+5.0 pts vs Jun')).toBeInTheDocument();
    expect(screen.getByText('−2.0 pts vs Jun')).toBeInTheDocument();
    expect(screen.queryByText(/% MoM/)).not.toBeInTheDocument();
  });

  it('shows the same change in All', () => {
    renderAllTeams('');

    expect(screen.getByText('+2 vs Jun')).toBeInTheDocument();
    expect(screen.getByText('+3.0 pts vs Jun')).toBeInTheDocument();
  });

  it('shows a muted No previous month on each tile when there is no previous month with data', () => {
    hookState.prevPeriodKey = null;
    hookState.prevTotalAgents = 0;
    hookState.prevAvgScore = 0;
    hookState.prevPctAB = 0;
    hookState.prevPctDE = 0;
    renderAllTeams('?month=2026-01');

    expect(screen.getAllByText('No previous month')).toHaveLength(4);
  });
});
