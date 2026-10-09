import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { discardPerformanceCache, refreshPerformanceData, usePerformanceData } from '../../hooks/usePerformanceData';
import { apiFetch } from '../../lib/apiClient';
import { invalidateCommittedEvidence } from './monthlyCorrection';

vi.mock('../../lib/apiClient', () => ({ apiFetch: vi.fn() }));
vi.mock('../../hooks/api/usePerformanceDashboard', () => ({ scopedPerformanceApiEnabled: true }));

const selection = { scopeId: 'scope-1', year: 2026, month: 8 };
let score = 79.82;

function wrapperFor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 2 * 60 * 1000, refetchOnMount: true } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return { client, wrapper };
}

beforeEach(() => {
  score = 79.82;
  localStorage.setItem('pms_session_v1', JSON.stringify({ id: crypto.randomUUID(), role: 'Admin' }));
  vi.mocked(apiFetch).mockReset();
  vi.mocked(apiFetch).mockImplementation(async (url: string) => {
    if (url === '/api/performance/catalog') {
      return { success: true, data: { periods: [{ key: '2026-08', year: 2026, month: 'August' }] } };
    }
    if (String(url).startsWith('/api/performance/records')) {
      return { success: true, data: { items: [{ employee_id: 'E1', employee_name: 'Outbound agent', team: 'Outbound', month: 'August', year: 2026, performance_level: 'Employee', score, calls: { outbound: 4 }, raw_data: { 'T.Attend%': 0.65 }, kpi_values: [{ kpi_key: 'Attendance', target_value: score === 79.93 ? 0.7 : 0.65, weight_applied: score === 79.93 ? 0.5 : 0.6 }] }], has_more: false } };
    }
    if (url === '/api/performance') throw new Error('legacy performance cache must stay unused');
    throw new Error(`unexpected ${url}`);
  });
});

afterEach(() => {
  discardPerformanceCache();
  localStorage.removeItem('pms_session_v1');
});

it('refreshes scoped team records after a committed apply and does not call the legacy route', async () => {
  const { client, wrapper } = wrapperFor();
  const hook = renderHook(() => usePerformanceData('August', 'all'), { wrapper });
  await waitFor(() => expect(hook.result.current.agents[0]?.evaluation.score).toBe(79.82));
  const reads = () => vi.mocked(apiFetch).mock.calls.filter(([url]) => String(url).startsWith('/api/performance/records'));
  const warmed = reads().length;
  hook.unmount();
  const remounted = renderHook(() => usePerformanceData('August', 'all'), { wrapper });
  await waitFor(() => expect(remounted.result.current.loading).toBe(false));
  expect(remounted.result.current.agents[0]?.evaluation.score).toBe(79.82);
  expect(reads()).toHaveLength(warmed);

  score = 79.93;
  act(() => invalidateCommittedEvidence(client, selection, refreshPerformanceData));
  await waitFor(() => expect(remounted.result.current.agents[0]?.evaluation.score).toBe(79.93));
  expect(remounted.result.current.agents[0]?.kpi_values?.[0]?.target_value).toBe(0.7);
  expect(reads().length).toBeGreaterThan(warmed);
  expect(vi.mocked(apiFetch).mock.calls.some(([url]) => url === '/api/performance')).toBe(false);
});
