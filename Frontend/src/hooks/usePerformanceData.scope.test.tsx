import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { apiFetch } from '../lib/apiClient';
import { usePerformanceData } from './usePerformanceData';

vi.mock('../lib/apiClient', () => ({ apiFetch: vi.fn() }));
vi.mock('./api/usePerformanceDashboard', () => ({ scopedPerformanceApiEnabled: false }));

afterEach(() => localStorage.removeItem('pms_session_v1'));

const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;

it('does not reuse cached rows after a role/grant change in the same session', async () => {
  const save = (role: string, branches: string[]) => localStorage.setItem('pms_session_v1', JSON.stringify({ id: 'scope-test', role, accessible_branches: branches }));
  const item = { employee_id: 'E1', employee_name: 'One', team: 'Inbound', month: 'June', year: 2026, calls: { inbound: 10 }, score: 82 };
  const catalog = { success: true, data: { periods: [{ key: '2026-06', year: 2026, month: 'June' }] } };
  save('Admin', []);
  vi.mocked(apiFetch).mockImplementation(async (url) => (String(url).startsWith('/api/performance/catalog')
    ? catalog
    : { success: true, data: { items: [item], has_more: false } }));
  const first = renderHook(() => usePerformanceData('All', 'all'), { wrapper });
  await waitFor(() => expect(first.result.current.agents).toHaveLength(1));
  first.unmount();

  save('Branch Director', ['dubai']);
  let finish: (value: unknown) => void = () => {};
  vi.mocked(apiFetch).mockImplementation((url) => (String(url).startsWith('/api/performance/catalog')
    ? Promise.resolve(catalog)
    : new Promise((resolve) => { finish = resolve; })));
  const second = renderHook(() => usePerformanceData('All', 'all'), { wrapper });
  expect(second.result.current.agents).toEqual([]);
  expect(second.result.current.loading).toBe(true);
  await waitFor(() => expect(vi.mocked(apiFetch).mock.calls.some(([url]) => String(url).startsWith('/api/performance/records'))).toBe(true));
  await act(async () => finish({ success: true, data: { items: [], has_more: false } }));
  await waitFor(() => expect(second.result.current.loading).toBe(false));
  expect(second.result.current.agents).toEqual([]);
});
