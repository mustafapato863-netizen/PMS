import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { apiFetch } from '../lib/apiClient';
import { mapScopedPerformanceRecord, usePerformanceData } from './usePerformanceData';

vi.mock('../lib/apiClient', () => ({ apiFetch: vi.fn() }));
vi.mock('./api/usePerformanceDashboard', () => ({ scopedPerformanceApiEnabled: false }));

afterEach(() => localStorage.removeItem('pms_session_v1'));

const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;

it('does not reuse legacy cached rows after a role/grant change in the same session', async () => {
  const save = (role: string, branches: string[]) => localStorage.setItem('pms_session_v1', JSON.stringify({ id: 'scope-test', role, accessible_branches: branches }));
  const agent = mapScopedPerformanceRecord({ employee_id: 'E1', employee_name: 'One', team: 'Inbound', month: 'June', calls: { inbound: 10 }, score: 82 });
  save('Admin', []);
  vi.mocked(apiFetch).mockResolvedValueOnce({ success: true, data: [agent] });
  const first = renderHook(() => usePerformanceData('All', 'all'), { wrapper });
  await waitFor(() => expect(first.result.current.agents).toHaveLength(1));
  first.unmount();

  save('Branch Director', ['dubai']);
  let finish: (value: { success: boolean; data: typeof agent[] }) => void = () => {};
  vi.mocked(apiFetch).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  const second = renderHook(() => usePerformanceData('All', 'all'), { wrapper });
  expect(second.result.current.agents).toEqual([]);
  expect(second.result.current.loading).toBe(true);
  await act(async () => finish({ success: true, data: [] }));
  await waitFor(() => expect(second.result.current.loading).toBe(false));
  expect(second.result.current.agents).toEqual([]);
  expect(apiFetch).toHaveBeenCalledTimes(2);
});
