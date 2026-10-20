import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '../context/ThemeContext';
import type { TeamAgentRow } from '../hooks/usePerformanceData';
import type { AgentRecord } from '../types';
import TeamDashboardView from './TeamDashboardView';

const hookState = vi.hoisted(() => ({
  rows: [] as TeamAgentRow[],
  configs: {} as Record<string, unknown>,
}));

vi.mock('../context/RoleContext', () => ({
  useUserRole: () => ({ role: 'Admin', fetchWithRole: vi.fn() }),
}));
vi.mock('../context/auth', () => ({ useAuth: () => ({ currentUser: null }) }));
vi.mock('../features/executive/useFunctionScope', () => ({
  useFunctionScope: () => ({ restricted: false, allowed: [], allowsTeam: () => true }),
}));
vi.mock('../hooks/useTeamConfig', () => ({
  useTeamConfig: (teamName: string) => ({ data: hookState.configs[teamName] }),
}));
vi.mock('../hooks/api/useInsightsWorkspace', () => ({ useInsightsWorkspace: () => ({ data: undefined }) }));
vi.mock('../hooks/useActionStore', () => ({
  useActionStore: () => ({
    getActionsForEmployee: () => [],
    getAllActions: () => [],
    saveAction: vi.fn(),
    updateAction: vi.fn(),
    isSaving: false,
  }),
}));
vi.mock('../lib/apiClient', () => ({ apiFetch: vi.fn(() => Promise.resolve({ success: false })) }));
vi.mock('../hooks/usePerformanceData', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/usePerformanceData')>()),
  useTeamData: () => ({
    rows: hookState.rows,
    avgScore: 80,
    classCounts: { A: 0, B: 1, C: 0, D: 0, E: 0 },
    pctAB: 100,
    pctDE: 0,
    totalAgents: Math.max(hookState.rows.length, 1),
    uniqueTeamCount: 1,
    prevMonth: null,
    prevPeriodKey: null,
    previousPeriodAgents: [],
    loading: false,
    dataSource: 'api',
    errorMessage: null,
    prevAvgScore: null,
    prevPctAB: null,
    prevPctDE: null,
    prevTotalAgents: null,
  }),
  usePerformanceData: () => ({
    uniqueMonths: ['August'],
    agents: hookState.rows.map((row) => row.raw),
  }),
}));

function positionConfig(team: string, position: string, label: string) {
  return {
    team,
    db_name: team,
    region: 'EGY' as const,
    employee_id_col: 'Employee ID',
    employee_name_col: 'Employee Name',
    grade_thresholds: { A: 95, B: 90, C: 80, D: 70 },
    kpis: [],
    performance_levels: {
      Employee: {
        positions: {
          [position]: {
            kpis: [{
              key: 'pinnedkpi',
              label,
              weight: 1,
              direction: 'higher_better' as const,
              unit: '%' as const,
              color: '#2563EB',
              actual_col: 'Actual Value',
              target_col: 'Target Value',
              aggregation: { method: 'average' as const },
            }],
          },
        },
      },
    },
  };
}

function agentRow(options: {
  id: string;
  name: string;
  team: string;
  position?: string;
  score: number;
  kpiLabel?: string;
}): TeamAgentRow {
  const raw: AgentRecord = {
    identity: {
      name: options.name,
      month: 'August',
      team: options.team,
      employee_id: options.id,
      position: options.position ?? null,
    },
    position: options.position ?? null,
    region: 'EGY',
    year: 2026,
    performance_level: 'Employee',
    calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
    geo: {
      bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
      attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
    },
    actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
    achievement: { booking_ach: 0, attend_ach: 0 },
    evaluation: { score: options.score / 100, grade: 'B' },
    raw_data: {},
    kpi_values: options.kpiLabel ? [{
      kpi_key: 'pinnedkpi',
      label: options.kpiLabel,
      unit: '%',
      direction: 'higher_better',
      actual_value: 0.9,
      target_value: 1,
      achievement_ratio: 0.9,
      weight_applied: 1,
      contribution: 0.9,
      evaluation_pinned: true,
    }] : undefined,
  };
  return {
    id: options.id,
    name: options.name,
    team: options.team,
    month: 'August',
    performanceLevel: 'Employee',
    score: options.score,
    gradeClass: 'B',
    gradeLabel: 'Meet Expectations',
    status: 'Meet',
    rootCauseAuto: '',
    rootCauseNote: '',
    correctiveAction: '',
    suggestedAction: '',
    ahtMinutes: 0,
    bookingRate: 0,
    attendRate: 0,
    raw,
  };
}

function renderTeam(path: string) {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/team/:teamId" element={<TeamDashboardView />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  hookState.rows = [];
  hookState.configs = {};
});

describe('comprehensive department position rows', () => {
  it('renders a pinned Call Center position row on All Channels, with its KPI and an action', async () => {
    const user = userEvent.setup();
    hookState.configs['Call Center'] = positionConfig(
      'Call Center',
      'Call Center trainer',
      'Certification Pass Rate (Patch)',
    );
    hookState.rows = [
      agentRow({ id: 'IN-1', name: 'Inbound Only Agent', team: 'Inbound', score: 70 }),
      agentRow({
        id: 'CC-1',
        name: 'Nour Position Trainer',
        team: 'Call Center',
        position: 'Call Center trainer',
        score: 95,
        kpiLabel: 'Certification Pass Rate (Patch)',
      }),
    ];

    renderTeam('/team/call-center');

    expect(screen.getByRole('heading', { name: 'Call Center Overview' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Nour Position Trainer' })).toBeInTheDocument();
    expect(screen.getByText('Certification Pass Rate (Patch)')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Inbound Only Agent' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Add action for Nour Position Trainer' }));
    expect(screen.getByRole('dialog', { name: 'Nour Position Trainer' })).toBeInTheDocument();
  });

  it('keeps a Call Center position row out of an Inbound channel drill', () => {
    hookState.configs['Call Center'] = positionConfig(
      'Call Center',
      'Call Center trainer',
      'Certification Pass Rate (Patch)',
    );
    hookState.rows = [
      agentRow({ id: 'IN-1', name: 'Inbound Only Agent', team: 'Inbound', score: 70 }),
      agentRow({
        id: 'CC-1',
        name: 'Nour Position Trainer',
        team: 'Call Center',
        position: 'Call Center trainer',
        score: 95,
        kpiLabel: 'Certification Pass Rate (Patch)',
      }),
    ];

    renderTeam('/team/call-center?channel=inbound');

    expect(screen.getByRole('link', { name: 'Inbound Only Agent' })).toBeInTheDocument();
    expect(screen.queryByText('Nour Position Trainer')).not.toBeInTheDocument();
    expect(screen.queryByText('Certification Pass Rate (Patch)')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Call Center Overview' })).not.toBeInTheDocument();
  });

  it('renders a pinned RCM position row on the employee department view', () => {
    hookState.configs.RCM = positionConfig('RCM', 'Group Claims Operations Manager', 'Denial Overturn Rate');
    hookState.rows = [
      agentRow({ id: 'CD-1', name: 'Coding Domain Clerk', team: 'Coding', score: 80 }),
      agentRow({
        id: 'RCM-1',
        name: 'RCM Position Lead',
        team: 'RCM',
        position: 'Group Claims Operations Manager',
        score: 92,
        kpiLabel: 'Denial Overturn Rate',
      }),
    ];

    renderTeam('/team/rcm');

    expect(screen.getByRole('heading', { name: 'RCM Operating Groups' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'RCM Position Lead' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Coding Domain Clerk' })).toBeInTheDocument();
    expect(screen.getByText('Denial Overturn Rate')).toBeInTheDocument();
  });

  it('keeps an RCM position row out of a single domain drill', () => {
    hookState.configs.RCM = positionConfig('RCM', 'Group Claims Operations Manager', 'Denial Overturn Rate');
    hookState.rows = [
      agentRow({ id: 'CD-1', name: 'Coding Domain Clerk', team: 'Coding', score: 80 }),
      agentRow({
        id: 'RCM-1',
        name: 'RCM Position Lead',
        team: 'RCM',
        position: 'Group Claims Operations Manager',
        score: 92,
        kpiLabel: 'Denial Overturn Rate',
      }),
    ];

    renderTeam('/team/rcm?domain=coding');

    expect(screen.getByRole('link', { name: 'Coding Domain Clerk' })).toBeInTheDocument();
    expect(screen.queryByText('RCM Position Lead')).not.toBeInTheDocument();
    expect(screen.queryByText('Denial Overturn Rate')).not.toBeInTheDocument();
  });

  it('renders a pinned RCM position row beside the domain summary when a group is selected', () => {
    hookState.configs.RCM = positionConfig('RCM', 'Group Claims Operations Manager', 'Denial Overturn Rate');
    hookState.rows = [
      agentRow({
        id: 'RCM-1',
        name: 'RCM Position Lead',
        team: 'RCM',
        position: 'Group Claims Operations Manager',
        score: 92,
        kpiLabel: 'Denial Overturn Rate',
      }),
    ];

    renderTeam('/team/rcm?group=offshore_egy');

    expect(screen.getByRole('heading', { name: 'RCM Domain Summary' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'RCM Position Lead' })).toBeInTheDocument();
    expect(screen.getByText('Denial Overturn Rate')).toBeInTheDocument();
  });
});
