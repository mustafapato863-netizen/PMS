import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FIXTURE_TEAM_FUNCTIONS, fixtureActions, fixtureAgentRecords, fixtureDrivers } from './executive.fixture';
import { composeExecutiveSummary, toExecRecords } from './compose';
import { executiveSummaryUrl, useExecutiveSummary } from './useExecutiveSummary';
import { executiveFunctionForTeam } from './functions';

const mocks = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  workspaceFilters: [] as unknown[],
  workspaceEnabled: [] as boolean[],
  followUp: vi.fn(),
  agents: [] as unknown[],
}));

vi.mock('../../lib/apiClient', () => ({ apiFetch: mocks.apiFetch }));
vi.mock('../../hooks/usePerformanceData', () => ({
  mapScopedPerformanceRecord: (record: unknown) => record,
  usePerformanceData: (_m: string, _l: string, _r: string, _p: string, enabled: boolean) => ({
    agents: enabled ? mocks.agents : [], loading: false, dataSource: 'api', errorMessage: null,
  }),
}));
vi.mock('../../hooks/api/useInsightsWorkspace', () => ({
  useInsightsWorkspace: (filters: unknown, options: { enabled?: boolean }) => {
    mocks.workspaceFilters.push(filters);
    mocks.workspaceEnabled.push(Boolean(options.enabled));
    const { drivers, items } = fixtureDrivers();
    return {
      data: options.enabled ? { performance_drivers: drivers, team_analyses: items, priority_insights: [], opportunities: [], options: { team_functions: FIXTURE_TEAM_FUNCTIONS } } : undefined,
      isLoading: false,
    };
  },
}));
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
  mocks.agents = fixtureAgentRecords();
  mocks.followUp.mockResolvedValue({
    summary: {},
    actions: fixtureActions(TODAY).map((action) => ({ ...action, action_text: action.title, action_type: 'Coaching', team: action.team ?? '' })),
  });
});

describe('executiveSummaryUrl', () => {
  it('maps filters to the API_NEEDS query', () => {
    expect(executiveSummaryUrl('corporate', { periodKey: '2026-06', region: 'UAE', teamFunction: 'RCM', team: 'Coding', performanceLevel: 'Employee' }))
      .toBe('/api/executive/summary?view=corporate&year=2026&month=6&region=UAE&function=RCM&team=Coding&performance_level=Employee');
    expect(executiveSummaryUrl('function', {}, 'Pre-Approvals')).toBe('/api/executive/summary?view=function&function=Pre-Approvals');
  });
});

describe('useExecutiveSummary', () => {
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
    });
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
  it('uses GET /api/executive/summary as-is when the endpoint answers', async () => {
    const records = toExecRecords(fixtureAgentRecords());
    const apiSummary = { ...composeExecutiveSummary({ view: 'corporate', role: 'Admin', records, filters: {}, today: TODAY }), meta: { source: 'api', unavailable: [], driver_metric: 'weighted_gap' } };
    mocks.apiFetch.mockResolvedValue({ success: true, data: apiSummary });
    const { result } = renderHook(() => useExecutiveSummary({ view: 'corporate', role: 'Admin', filters: {}, today: TODAY }), { wrapper });
    await waitFor(() => expect(result.current.source).toBe('api'));
    expect(result.current.summary?.meta.driver_metric).toBe('weighted_gap');
    expect(mocks.workspaceEnabled.every((enabled) => !enabled)).toBe(true);
    expect(mocks.followUp).not.toHaveBeenCalled();
  });

  it('composes from existing endpoints when the summary endpoint 404s', async () => {
    mocks.apiFetch.mockRejectedValue(new Error('Not Found'));
    const { result } = renderHook(() => useExecutiveSummary({ view: 'corporate', role: 'Admin', filters: { periodKey: '2026-07' }, today: TODAY }), { wrapper });
    await waitFor(() => expect(result.current.summary?.corrective_actions ?? null).not.toBeNull());
    const summary = result.current.summary!;
    expect(result.current.source).toBe('composed');
    expect(summary.period.fallback_applied).toBe(true);
    expect(summary.drivers.negative.length).toBeGreaterThan(0);
    expect(summary.corrective_actions?.summary.due_this_week).toBe(3);
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

  it('does not ask Insights or follow-up for roles without access (Viewer)', async () => {
    mocks.apiFetch.mockRejectedValue(new Error('Not Found'));
    const { result } = renderHook(() => useExecutiveSummary({ view: 'corporate', role: 'Viewer', filters: {}, today: TODAY }), { wrapper });
    await waitFor(() => expect(result.current.summary ?? null).not.toBeNull());
    expect(mocks.workspaceEnabled.every((enabled) => !enabled)).toBe(true);
    expect(mocks.followUp).not.toHaveBeenCalled();
    expect(result.current.summary?.meta.unavailable).toEqual(expect.arrayContaining(['drivers', 'corrective_actions']));
  });
});
