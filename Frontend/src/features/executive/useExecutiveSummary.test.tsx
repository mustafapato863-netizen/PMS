import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FIXTURE_TEAM_FUNCTIONS, fixtureActions, fixtureAgentRecords, fixtureDrivers } from './executive.fixture';
import type { PMSAction } from '../../types';
import { useExecutiveSummary, type ExecutiveFilterState } from './useExecutiveSummary';
import { executiveFunctionForTeam } from './functions';

const mocks = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  workspaceFilters: [] as unknown[],
  workspaceEnabled: [] as boolean[],
  followUp: vi.fn(),
  agents: [] as unknown[],
  /** Disabled legacy reads must keep one agents array, matching usePerformanceData. */
  emptyAgents: [] as unknown[],
  /** This device's action queue, passed to the hook as `queuedActions`. */
  queued: [] as PMSAction[],
  composeCalls: 0,
  workspaceData: null as {
    performance_drivers: unknown[];
    team_analyses: unknown[];
    priority_insights: unknown[];
    opportunities: unknown[];
    options: { team_functions: typeof FIXTURE_TEAM_FUNCTIONS };
  } | null,
}));

vi.mock('../../lib/apiClient', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../lib/apiClient')>(), apiFetch: mocks.apiFetch,
}));
vi.mock('../../hooks/usePerformanceData', () => ({
  mapScopedPerformanceRecord: (record: unknown) => record,
  usePerformanceData: (_m: string, _l: string, _r: string, _p: string, enabled: boolean) => ({
    agents: enabled ? mocks.agents : mocks.emptyAgents, loading: false, dataSource: 'api', errorMessage: null,
  }),
}));
vi.mock('../../hooks/api/useInsightsWorkspace', () => ({
  useInsightsWorkspace: (filters: unknown, options: { enabled?: boolean }) => {
    mocks.workspaceFilters.push(filters);
    mocks.workspaceEnabled.push(Boolean(options.enabled));
    return {
      data: options.enabled ? mocks.workspaceData ?? undefined : undefined,
      isLoading: false,
    };
  },
}));
vi.mock('./compose', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./compose')>();
  return {
    ...actual,
    composeExecutiveSummary: (input: Parameters<typeof actual.composeExecutiveSummary>[0]) => {
      mocks.composeCalls += 1;
      return actual.composeExecutiveSummary(input);
    },
  };
});
vi.mock('../../hooks/useActionStore', () => ({ fetchFollowUp: mocks.followUp, mapBackendAction: (record: unknown) => record }));

const TODAY = new Date(2026, 6, 6);
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
);

beforeEach(() => {
  mocks.apiFetch.mockReset();
  mocks.followUp.mockReset();
  mocks.workspaceFilters = [];
  mocks.workspaceEnabled = [];
  mocks.composeCalls = 0;
  const { drivers, items } = fixtureDrivers();
  mocks.workspaceData = {
    performance_drivers: drivers,
    team_analyses: items,
    priority_insights: [],
    opportunities: [],
    options: { team_functions: FIXTURE_TEAM_FUNCTIONS },
  };
  mocks.agents = fixtureAgentRecords();
  mocks.queued = [];
  mocks.followUp.mockResolvedValue({
    summary: {},
    actions: fixtureActions(TODAY).map((action) => ({ ...action, action_text: action.title, action_type: 'Coaching', team: action.team ?? '' })),
  });
});

describe('useExecutiveSummary', () => {
  it('never requests /api/executive/summary, which the backend does not provide', async () => {
    mocks.apiFetch.mockImplementation((url: string) => url.startsWith('/api/performance/summary-records')
      ? Promise.resolve({ success: true, data: mocks.agents })
      : Promise.reject(new Error('Not Found')));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const sharedWrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result, rerender } = renderHook(({ team }: { team?: string }) => useExecutiveSummary({ view: 'corporate', role: 'Viewer', filters: { team }, today: TODAY }), { initialProps: { team: undefined } as { team?: string }, wrapper: sharedWrapper });
    await waitFor(() => expect(result.current.source).toBe('composed'));
    rerender({ team: 'Coding' });
    await waitFor(() => expect(result.current.summary?.scope.team).toBe('Coding'));
    expect(mocks.apiFetch.mock.calls.filter(([url]) => String(url).startsWith('/api/executive/summary'))).toHaveLength(0);
    client.clear();
  });

  it('includes old undated actions and deduplicates tracked records by persisted ID', async () => {
    const action = { id: 'old-action', employee_id: 'old-employee', employee_name: 'Old employee', team: 'Coding', month: 'June', action_text: 'Coaching', action_type: 'Coaching' };
    mocks.followUp.mockResolvedValue({ actions: [{ ...action, status: 'In Progress', due_date: '2026-07-07' }] });
    mocks.apiFetch.mockImplementation((url: string) => url === '/api/corrective-actions/'
      ? Promise.resolve({ success: true, data: [action, { ...action, id: 'undated' }] })
      : Promise.reject(new Error('Not Found')));
    const { result } = renderHook(() => useExecutiveSummary({ view: 'function', role: 'Admin', functionName: 'RCM', filters: {}, today: TODAY }), { wrapper });
    await waitFor(() => expect(result.current.summary?.corrective_actions?.summary.open).toBe(2));
    expect(result.current.summary?.corrective_actions?.actions).toHaveLength(2);
    expect(result.current.summary?.corrective_actions?.summary.due_this_week).toBe(1);
  });

  it('preserves root cause evidence when merging tracked actions and scopes monthly analysis to the selected team', async () => {
    const action = { id: 'merged', employee_id: 'e1', team: 'Inbound', month: 'June', action_text: 'Coach calls', action_type: 'Coaching', root_cause_note: 'Booking rate and AHT', created_at: '2026-06-15' };
    mocks.followUp.mockResolvedValue({ actions: [{ ...action, root_cause_note: '', status: 'Completed' }] });
    mocks.apiFetch.mockImplementation((url: string) => url === '/api/corrective-actions/'
      ? Promise.resolve({ success: true, data: [action, { ...action, id: 'other-team', team: 'Coding' }, { ...action, id: 'other-month', month: 'May' }] })
      : Promise.reject(new Error('Not Found')));
    const { result } = renderHook(() => useExecutiveSummary({ view: 'corporate', role: 'Admin', filters: { team: 'Inbound', periodKey: '2026-06' }, today: TODAY }), { wrapper });
    await waitFor(() => expect(result.current.summary?.corrective_actions?.analytics?.actions).toHaveLength(1));
    expect(result.current.summary?.corrective_actions?.analytics?.actions[0]).toMatchObject({
      id: 'merged', team: 'Inbound', action_type: 'Coaching', kpi_mentions: ['Booking Rate', 'AHT (Handle Time)'],
      root_cause_note: 'Booking rate and AHT',
    });
  });

  it('counts only unsynced queued actions in the active period as Pending Sync, and leaves the totals alone', async () => {
    const queuedAction = (overrides: Pick<PMSAction, 'id' | 'month' | 'synced'> & Partial<PMSAction>): PMSAction => ({
      employee_id: 'e1', employee_name: 'Queued agent', team: 'Inbound', action_type: 'Training', action_text: 'Train',
      root_cause_note: '', created_by: 'Admin', created_at: '2026-06-20T09:00:00Z', ...overrides,
    });
    mocks.queued = [
      queuedAction({ id: 'queued-june', month: 'June', synced: false }),
      queuedAction({ id: 'synced-june', month: 'June', synced: true }),
      queuedAction({ id: 'queued-may', month: 'May', created_at: '2026-05-20T09:00:00Z', synced: false }),
    ];
    mocks.followUp.mockResolvedValue({ actions: [] });
    mocks.apiFetch.mockImplementation((url: string) => url === '/api/corrective-actions/'
      ? Promise.resolve({ success: true, data: [] })
      : Promise.reject(new Error('Not Found')));
    const { result } = renderHook(() => useExecutiveSummary({ view: 'corporate', role: 'Admin', filters: { periodKey: '2026-06' }, queuedActions: mocks.queued, today: TODAY }), { wrapper });
    await waitFor(() => expect(result.current.summary?.corrective_actions?.analytics?.pending_sync).toHaveLength(1));
    expect(result.current.summary?.corrective_actions?.analytics?.pending_sync).toEqual([{ id: 'queued-june', team: 'Inbound' }]);
    expect(result.current.summary?.corrective_actions?.analytics?.actions).toHaveLength(0);
    expect(result.current.summary?.corrective_actions?.summary.open).toBe(0);
  });
  it('uses canonical management and employee evidence and scopes function actions', async () => {
    mocks.apiFetch.mockImplementation((url: string) => url.startsWith('/api/performance/summary-records')
      ? Promise.resolve({ success: true, data: mocks.agents })
      : Promise.reject(new Error('Not Found')));
    const { result } = renderHook(() => useExecutiveSummary({ view: 'function', role: 'Admin', functionName: 'RCM', filters: {}, today: TODAY }), { wrapper });
    await waitFor(() => expect(result.current.summary?.corrective_actions ?? null).not.toBeNull());
    expect(mocks.apiFetch).toHaveBeenCalledWith('/api/performance/summary-records', expect.anything());
    expect(result.current.options.levels).toEqual(['Employee', 'Managerial', 'Corporate']);
    expect(result.current.summary?.people?.below_90).toBeDefined();
    expect(result.current.summary?.corrective_actions?.actions.every((action) => executiveFunctionForTeam(action.team, FIXTURE_TEAM_FUNCTIONS) === 'RCM')).toBe(true);
  });
  it('composes from the existing sources when the summary records are unavailable', async () => {
    mocks.apiFetch.mockRejectedValue(new Error('Not Found'));
    const { result } = renderHook(() => useExecutiveSummary({ view: 'corporate', role: 'Admin', filters: { periodKey: '2026-07' }, today: TODAY }), { wrapper });
    await waitFor(() => expect(result.current.summary?.corrective_actions ?? null).not.toBeNull());
    const summary = result.current.summary!;
    expect(result.current.source).toBe('composed');
    expect(summary.period.fallback_applied).toBe(true);
    expect(summary.drivers.negative.length).toBeGreaterThan(0);
    expect(summary.corrective_actions?.summary.due_this_week).toBe(3);
    // The evaluation-basis note comes from the same records, for the effective month.
    expect(summary.basis_context).toMatchObject({ state: expect.any(String) });
    // Drivers are asked for the effective (fallback) month.
    expect(mocks.workspaceFilters.at(-1)).toMatchObject({ periodKey: '2026-06' });
    expect(result.current.options.regions).toEqual(['EGY', 'UAE']);
  });

  it('scopes the Manager to their team and never fetches all-teams comparisons', async () => {
    mocks.apiFetch.mockRejectedValue(new Error('Not Found'));
    const { result } = renderHook(() => useExecutiveSummary({ view: 'managerial', role: 'Manager', filters: {}, managerTeams: ['Inbound'], today: TODAY }), { wrapper });
    await waitFor(() => expect(result.current.summary?.corrective_actions ?? null).not.toBeNull());
    const summary = result.current.summary!;
    expect(result.current.managerTeam).toBe('Inbound');
    expect(summary.teams.map((team) => team.team)).toEqual(['Inbound']);
    expect(summary.meta.unavailable).toContain('function_average');
    expect(summary.corrective_actions?.actions.every((action) => action.team === 'Inbound')).toBe(true);
    expect(mocks.workspaceFilters.at(-1)).toMatchObject({ team: 'Inbound' });
  });

  describe('Manager with two assigned teams', () => {
    const TWO_TEAMS = ['Inbound', 'Outbound'];
    const renderManager = (filters: ExecutiveFilterState) => renderHook(
      () => useExecutiveSummary({ view: 'managerial', role: 'Manager', filters, managerTeams: TWO_TEAMS, today: TODAY }),
      { wrapper },
    );

    it('shows every assigned team by default, offers exactly those two, and never shows an unassigned team', async () => {
      mocks.apiFetch.mockRejectedValue(new Error('Not Found'));
      const { result } = renderManager({});
      await waitFor(() => expect(result.current.summary?.corrective_actions ?? null).not.toBeNull());
      expect(result.current.managerTeam).toBeNull();
      expect(result.current.managerTeamOptions).toEqual(TWO_TEAMS);
      expect(result.current.summary?.scope.team).toBeNull();
      expect(result.current.summary?.teams.map((team) => team.team).sort()).toEqual(TWO_TEAMS);
      expect(result.current.summary?.corrective_actions?.actions.every((action) => TWO_TEAMS.includes(action.team ?? ''))).toBe(true);
      expect(result.current.summary?.teams.some((team) => team.team === 'Coding')).toBe(false);
    });

    it('opens on an assigned team named in the URL', async () => {
      mocks.apiFetch.mockRejectedValue(new Error('Not Found'));
      const { result } = renderManager({ team: 'Outbound' });
      await waitFor(() => expect(result.current.summary?.corrective_actions ?? null).not.toBeNull());
      expect(result.current.managerTeam).toBe('Outbound');
      expect(result.current.summary?.scope.team).toBe('Outbound');
      expect(result.current.summary?.teams.map((team) => team.team)).toEqual(['Outbound']);
      expect(result.current.summary?.corrective_actions?.actions.every((action) => action.team === 'Outbound')).toBe(true);
    });

    it('ignores an unassigned team in the URL and opens on every assigned team', async () => {
      mocks.apiFetch.mockRejectedValue(new Error('Not Found'));
      const { result } = renderManager({ team: 'Coding' });
      await waitFor(() => expect(result.current.summary?.corrective_actions ?? null).not.toBeNull());
      expect(result.current.managerTeam).toBeNull();
      expect(result.current.managerTeamOptions).toEqual(TWO_TEAMS);
      expect(result.current.summary?.teams.map((team) => team.team).sort()).toEqual(TWO_TEAMS);
    });
  });

  it('does not compose again when a new filters object has the same values', async () => {
    mocks.apiFetch.mockImplementation((url: string) => url.startsWith('/api/performance/summary-records')
      ? Promise.resolve({ success: true, data: mocks.agents })
      : Promise.reject(new Error('Not Found')));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const stableWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const filters = { periodKey: '2026-06', region: 'EGY' };
    const { result, rerender } = renderHook(
      ({ next }: { next: ExecutiveFilterState }) => useExecutiveSummary({ view: 'corporate', role: 'Admin', filters: next, today: TODAY }),
      { initialProps: { next: filters }, wrapper: stableWrapper },
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.source).toBe('composed');
    const settled = mocks.composeCalls;
    expect(settled).toBeGreaterThan(0);

    rerender({ next: { periodKey: '2026-06', region: 'EGY' } });
    expect(mocks.composeCalls).toBe(settled);

    const drivers = mocks.workspaceData?.performance_drivers ?? [];
    mocks.workspaceData = { ...mocks.workspaceData!, performance_drivers: [...drivers] };
    rerender({ next: { periodKey: '2026-06', region: 'EGY' } });
    expect(mocks.composeCalls).toBe(settled + 1);

    rerender({ next: { periodKey: '2026-06', region: 'EGY', team: 'Inbound' } });
    expect(mocks.composeCalls).toBeGreaterThan(settled + 1);
    client.clear();
  });

  it('does not ask Insights or follow-up for roles without access (Viewer)', async () => {
    mocks.apiFetch.mockRejectedValue(new Error('Not Found'));
    const { result } = renderHook(() => useExecutiveSummary({ view: 'corporate', role: 'Viewer', filters: {}, today: TODAY }), { wrapper });
    await waitFor(() => expect(result.current.summary ?? null).not.toBeNull());
    expect(mocks.workspaceEnabled.every((enabled) => !enabled)).toBe(true);
    expect(mocks.followUp).not.toHaveBeenCalled();
    expect(result.current.summary?.meta.unavailable).toEqual(expect.arrayContaining(['drivers', 'corrective_actions']));
  });
});
