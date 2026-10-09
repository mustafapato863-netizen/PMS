import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetch } from '../lib/apiClient';
import { usePerformanceData, useTeamData } from './usePerformanceData';

vi.mock('../lib/apiClient', () => ({ apiFetch: vi.fn() }));
vi.mock('./api/usePerformanceDashboard', () => ({ scopedPerformanceApiEnabled: true }));

const periods = [
  { key: '2025-07', month: 'July', year: 2025 },
  { key: '2026-07', month: 'July', year: 2026 },
];

const clients: QueryClient[] = [];

function wrapperFor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

function item(id: string, name: string, month: string, year: number) {
  return { employee_id: id, employee_name: name, team: 'Inbound', month, year, calls: { inbound: 10 }, score: 80 };
}

beforeEach(() => {
  localStorage.setItem('pms_session_v1', JSON.stringify({ id: crypto.randomUUID(), role: 'Admin' }));
  vi.mocked(apiFetch).mockReset();
  vi.mocked(apiFetch).mockImplementation(async (url) => {
    const href = String(url);
    if (href.startsWith('/api/performance/catalog')) return { success: true, data: { periods, months: ['July'], scopes: [] } };
    if (href.startsWith('/api/performance/records')) {
      const period = new URL(href, 'http://localhost').searchParams.get('period');
      const row = period === '2025-07'
        ? item('E2025', 'July 2025', 'July', 2025)
        : period === '2026-07'
          ? item('E2026', 'July 2026', 'July', 2026)
          : null;
      return { success: true, data: { items: row ? [row] : [], has_more: false } };
    }
    if (href.startsWith('/api/config/teams')) return { success: true, data: [] };
    return { success: false, message: href };
  });
});

afterEach(() => {
  clients.splice(0).forEach((client) => client.clear());
  localStorage.removeItem('pms_session_v1');
});

function recordPeriods() {
  return vi.mocked(apiFetch).mock.calls
    .map(([url]) => String(url))
    .filter((url) => url.startsWith('/api/performance/records'))
    .map((url) => new URL(url, 'http://localhost').searchParams.get('period'));
}

describe('scoped performance period selection', () => {
  it('requests the exact period and does not keep the later year with the same month', async () => {
    const hook = renderHook(() => usePerformanceData('2025-07', 'all'), { wrapper: wrapperFor() });
    await waitFor(() => expect(hook.result.current.agents.map((agent) => agent.identity.employee_id)).toEqual(['E2025']));
    expect(hook.result.current.agents[0]?.year).toBe(2025);
    expect(recordPeriods()).toContain('2025-07');
    expect(recordPeriods()).not.toContain('2026-07');
  });

  it('keeps only the latest July when the month name loads both years', async () => {
    const hook = renderHook(() => useTeamData(null, 'July'), { wrapper: wrapperFor() });
    await waitFor(() => expect(hook.result.current.loading).toBe(false));
    expect(recordPeriods()).toEqual(expect.arrayContaining(['2025-07', '2026-07']));
    expect(hook.result.current.rows.map((row) => row.id)).toEqual(['E2026']);
    expect(hook.result.current.totalAgents).toBe(1);
  });
});
