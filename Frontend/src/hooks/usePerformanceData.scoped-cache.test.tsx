import { StrictMode, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { apiFetch } from '../lib/apiClient';
import { refreshPerformanceData, usePerformanceData, useTeamData } from './usePerformanceData';

vi.mock('../lib/apiClient', () => ({ apiFetch: vi.fn() }));
vi.mock('./api/usePerformanceDashboard', () => ({ scopedPerformanceApiEnabled: true }));

const clients: QueryClient[] = [];
const wrapperFor = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  return ({ children }: { children: ReactNode }) => <StrictMode><QueryClientProvider client={client}>{children}</QueryClientProvider></StrictMode>;
};
const recordReads = () => vi.mocked(apiFetch).mock.calls.filter(([url]) => url.startsWith('/api/performance/records'));

beforeEach(() => {
  vi.mocked(apiFetch).mockReset();
  localStorage.setItem('pms_session_v1', JSON.stringify({ id: crypto.randomUUID(), role: 'Admin' }));
  vi.mocked(apiFetch).mockImplementation(async (url) => url === '/api/performance/catalog'
    ? { success: true, data: { periods: [{ key: '2026-06', year: 2026, month: 'June' }] } }
    : { success: true, data: { items: [{ employee_id: 'E1', employee_name: 'Test employee', team: 'Coding', month: 'June', year: 2026, performance_level: 'Employee', score: 82, calls: { inbound: 10 } }], has_more: false } });
});
afterEach(() => {
  clients.splice(0).forEach((client) => client.clear());
  localStorage.removeItem('pms_session_v1');
});

it('shares scoped reads between consumers and reuses them after remounting', async () => {
  const wrapper = wrapperFor();
  const first = renderHook(() => {
    const one = usePerformanceData('All', 'all', 'All', 'Employee', true, 'RCM');
    const two = usePerformanceData('All', 'all', 'All', 'Employee', true, 'RCM');
    return [one, two];
  }, { wrapper });
  await waitFor(() => expect(first.result.current.every((result) => result.agents.length === 1)).toBe(true));
  expect(recordReads()).toHaveLength(1);
  first.unmount();
  const next = renderHook(() => usePerformanceData('All', 'all', 'All', 'Employee', true, 'RCM'), { wrapper });
  expect(next.result.current.loading).toBe(false);
  expect(next.result.current.agents).toHaveLength(1);
  expect(recordReads()).toHaveLength(1);
});

it('narrows parent-team reads on the backend instead of downloading all teams', async () => {
  const hook = renderHook(() => useTeamData('RCM', 'All'), { wrapper: wrapperFor() });
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  expect(recordReads()).toHaveLength(1);
  expect(recordReads()[0][0]).toContain('team=RCM');
});

it('does not reuse another team or changed permission scope and refreshes after data updates', async () => {
  const hook = renderHook(({ team }) => usePerformanceData('All', 'all', 'All', 'Employee', true, team), { initialProps: { team: 'RCM' }, wrapper: wrapperFor() });
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  hook.rerender({ team: 'Sales' });
  expect(hook.result.current.agents).toEqual([]);
  await waitFor(() => expect(recordReads()).toHaveLength(2));
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  localStorage.setItem('pms_session_v1', JSON.stringify({ id: 'scoped-director', role: 'Branch Director', accessible_branches: ['dubai'] }));
  hook.rerender({ team: 'Sales' });
  expect(hook.result.current.agents).toEqual([]);
  await waitFor(() => expect(recordReads()).toHaveLength(3));
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  act(() => refreshPerformanceData());
  await waitFor(() => expect(recordReads()).toHaveLength(4));
});

it('does not fetch disabled performance consumers', () => {
  renderHook(() => usePerformanceData('All', 'all', 'All', 'All', false), { wrapper: wrapperFor() });
  expect(apiFetch).not.toHaveBeenCalled();
});
