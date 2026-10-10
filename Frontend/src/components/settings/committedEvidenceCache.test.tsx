import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useExecutiveSummary } from '../../features/executive/useExecutiveSummary';
import { useSummaryRecords } from '../../features/executive/useSummaryRecords';
import { useInsightsWorkspace } from '../../hooks/api/useInsightsWorkspace';
import { useReportsCenter } from '../../hooks/api/useReports';
import { discardPerformanceCache, mapScopedPerformanceRecord, refreshPerformanceData, usePerformanceData } from '../../hooks/usePerformanceData';
import { apiFetch } from '../../lib/apiClient';
import { queryClient as appQueryClient } from '../../lib/queryClient';
import { invalidateCommittedEvidence } from './monthlyCorrection';

vi.mock('../../lib/apiClient', () => ({ apiFetch: vi.fn() }));
vi.mock('../../hooks/api/usePerformanceDashboard', () => ({ scopedPerformanceApiEnabled: false }));

const selection = { scopeId: 'scope-1', year: 2026, month: 8 };

function agent(score: number, target: number, weight: number) {
  return mapScopedPerformanceRecord({
    employee_id: 'E1',
    employee_name: 'Outbound agent',
    team: 'Outbound',
    month: 'August',
    year: 2026,
    performance_level: 'Employee',
    score,
    calls: { outbound: 4 },
    raw_data: { 'T.Attend%': 0.65 },
    kpi_values: [{ kpi_key: 'Attendance', label: 'Attendance', target_value: target, weight_applied: weight, actual_value: 0.46, direction: 'higher_better' }],
    evaluation: { score, grade: 'C', manager_notes: 'keep the human note' },
  });
}

function clientFor() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 2 * 60 * 1000,
        retry: false,
        refetchOnWindowFocus: false,
        refetchOnMount: true,
      },
    },
  });
}

function calls(urlPart: string) {
  return vi.mocked(apiFetch).mock.calls.filter(([url]) => String(url).includes(urlPart));
}

afterEach(() => {
  discardPerformanceCache();
  localStorage.removeItem('pms_session_v1');
});

describe('committed evidence cache, legacy mode', () => {
  let score = 79.82;
  let target = 0.65;
  let weight = 0.6;

  beforeEach(() => {
    score = 79.82;
    target = 0.65;
    weight = 0.6;
    localStorage.setItem('pms_session_v1', JSON.stringify({ id: 'legacy-admin', role: 'Admin' }));
    vi.mocked(apiFetch).mockReset();
    vi.mocked(apiFetch).mockImplementation(async (url: string) => {
      const href = String(url);
      if (href === '/api/performance') return { success: true, data: [agent(score, target, weight)] };
      if (href.startsWith('/api/performance/summary-records')) {
        return { success: true, data: [{ employee_id: 'E1', employee_name: 'Outbound agent', team: 'Outbound', month: 'August', year: 2026, score, raw_data: { 'T.Attend%': 0.65 }, kpi_values: [{ kpi_key: 'Attendance', target_value: target, weight_applied: weight }] }] };
      }
      if (href.startsWith('/api/executive/summary')) return { success: true, data: { hero: { score }, meta: { source: 'api' } } };
      if (href.startsWith('/api/reports/center')) return { success: true, data: { summary: { current_score: score } } };
      if (href.startsWith('/api/insights/workspace')) return { success: true, data: { priority_insights: [{ id: 'pin', title: String(score) }] } };
      throw new Error(`unexpected ${href}`);
    });
  });

  it('keeps warmed live readers on the old pin until a committed refresh, and leaves saved story, plan, and action artifacts', async () => {
    expect(appQueryClient.getDefaultOptions().queries?.staleTime).toBe(2 * 60 * 1000);
    const client = clientFor();
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    client.setQueryData(['reports', 'story', 'draft', 'saved-1'], { id: 'saved-1', name: 'Immutable story' });
    client.setQueryData(['planning', 'linkable', 'Outbound'], [{ id: 'plan-1', title: 'Human plan' }]);
    client.setQueryData(['corrective-actions', 'executive', 'follow-up', 'session'], { actions: [{ id: 'action-1' }] });

    const first = renderHook(() => ({
      team: usePerformanceData('August', 'all'),
      summary: useSummaryRecords(true),
      executive: useExecutiveSummary({ view: 'corporate', role: 'Admin', filters: { periodKey: '2026-08' }, today: new Date(2026, 7, 2) }),
      center: useReportsCenter({ period: '2026-08' }),
      insights: useInsightsWorkspace({ periodKey: '2026-08' }),
    }), { wrapper });

    await waitFor(() => expect(first.result.current.team.agents[0]?.evaluation.score).toBe(79.82));
    await waitFor(() => expect(first.result.current.summary.data?.[0]?.evaluation.score).toBe(79.82));
    await waitFor(() => expect(first.result.current.executive.source).toBe('api'));
    await waitFor(() => expect(first.result.current.center.data?.summary.current_score).toBe(79.82));
    await waitFor(() => expect(first.result.current.insights.data?.priority_insights?.[0]?.title).toBe('79.82'));
    const warmed = {
      performance: calls('/api/performance').length,
      summary: calls('/api/performance/summary-records').length,
      executive: calls('/api/executive/summary').length,
      center: calls('/api/reports/center').length,
      insights: calls('/api/insights/workspace').length,
    };
    expect(warmed.performance).toBeGreaterThan(0);

    first.unmount();
    const remounted = renderHook(() => ({
      team: usePerformanceData('August', 'all'),
      summary: useSummaryRecords(true),
      executive: useExecutiveSummary({ view: 'corporate', role: 'Admin', filters: { periodKey: '2026-08' }, today: new Date(2026, 7, 2) }),
      center: useReportsCenter({ period: '2026-08' }),
      insights: useInsightsWorkspace({ periodKey: '2026-08' }),
    }), { wrapper });
    await waitFor(() => expect(remounted.result.current.team.loading).toBe(false));
    expect(remounted.result.current.team.agents[0]?.evaluation.score).toBe(79.82);
    expect(remounted.result.current.executive.summary?.hero).toMatchObject({ score: 79.82 });
    expect(calls('/api/performance')).toHaveLength(warmed.performance);
    expect(calls('/api/performance/summary-records')).toHaveLength(warmed.summary);
    expect(calls('/api/executive/summary')).toHaveLength(warmed.executive);
    expect(calls('/api/reports/center')).toHaveLength(warmed.center);
    expect(calls('/api/insights/workspace')).toHaveLength(warmed.insights);

    score = 79.93;
    target = 0.7;
    weight = 0.5;
    act(() => invalidateCommittedEvidence(client, selection, refreshPerformanceData));
    await waitFor(() => expect(remounted.result.current.team.agents[0]?.evaluation.score).toBe(79.93));
    await waitFor(() => expect(remounted.result.current.summary.data?.[0]?.kpi_values?.[0]?.target_value).toBe(0.7));
    await waitFor(() => expect(remounted.result.current.executive.summary?.hero).toMatchObject({ score: 79.93 }));
    await waitFor(() => expect(remounted.result.current.center.data?.summary.current_score).toBe(79.93));
    await waitFor(() => expect(remounted.result.current.insights.data?.priority_insights?.[0]?.title).toBe('79.93'));
    expect(client.getQueryData(['reports', 'story', 'draft', 'saved-1'])).toEqual({ id: 'saved-1', name: 'Immutable story' });
    expect(client.getQueryData(['planning', 'linkable', 'Outbound'])).toEqual([{ id: 'plan-1', title: 'Human plan' }]);
    expect(client.getQueryData(['corrective-actions', 'executive', 'follow-up', 'session'])).toEqual({ actions: [{ id: 'action-1' }] });
    expect(calls('/api/performance').length).toBeGreaterThan(warmed.performance);
    expect(calls('/api/executive/summary').length).toBeGreaterThan(warmed.executive);
    expect(calls('/api/reports/center').length).toBeGreaterThan(warmed.center);
    expect(calls('/api/insights/workspace').length).toBeGreaterThan(warmed.insights);
  });

  it('does not let an older legacy response replace a newer committed read or a logged-out session', async () => {
    const pending: Array<(value: { success: boolean; data: ReturnType<typeof agent>[] }) => void> = [];
    vi.mocked(apiFetch).mockImplementation((url: string) => {
      if (String(url) !== '/api/performance') return Promise.resolve({ success: true, data: [] });
      return new Promise((resolve) => { pending.push(resolve); });
    });
    const client = clientFor();
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const hook = renderHook(() => usePerformanceData('August', 'all'), { wrapper });
    await waitFor(() => expect(pending).toHaveLength(1));
    act(() => refreshPerformanceData());
    await waitFor(() => expect(pending).toHaveLength(2));
    await act(async () => { pending[1]({ success: true, data: [agent(79.93, 0.7, 0.5)] }); });
    await waitFor(() => expect(hook.result.current.agents[0]?.evaluation.score).toBe(79.93));
    await act(async () => { pending[0]({ success: true, data: [agent(79.82, 0.65, 0.6)] }); });
    expect(hook.result.current.agents[0]?.evaluation.score).toBe(79.93);

    const late: Array<(value: { success: boolean; data: ReturnType<typeof agent>[] }) => void> = [];
    vi.mocked(apiFetch).mockImplementation(() => new Promise((resolve) => { late.push(resolve); }));
    act(() => refreshPerformanceData());
    await waitFor(() => expect(late).toHaveLength(1));
    localStorage.setItem('pms_session_v1', JSON.stringify({ id: 'other-user', role: 'Viewer' }));
    await act(async () => { late[0]({ success: true, data: [agent(79.82, 0.65, 0.6)] }); });
    hook.unmount();
    const next = renderHook(() => usePerformanceData('August', 'all'), { wrapper });
    expect(next.result.current.agents).toEqual([]);
  });
});
