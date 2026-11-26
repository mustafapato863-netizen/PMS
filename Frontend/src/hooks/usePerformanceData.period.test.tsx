import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetch } from '../lib/apiClient';
import { usePerformanceData, useTeamData } from './usePerformanceData';

vi.mock('../lib/apiClient', () => ({ apiFetch: vi.fn() }));
vi.mock('./api/usePerformanceDashboard', () => ({ scopedPerformanceApiEnabled: false }));

const clients: QueryClient[] = [];

function wrapperFor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(client);
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

function rawAgent(id: string, name: string, month: string, year: number) {
  return {
    employee_id: id,
    employee_name: name,
    team: 'Inbound',
    month,
    year,
    calls: { inbound: 10 },
    score: year,
  };
}




beforeEach(() => {
  localStorage.setItem('pms_session_v1', JSON.stringify({ id: crypto.randomUUID(), role: 'Admin' }));
  vi.mocked(apiFetch).mockReset();
  vi.mocked(apiFetch).mockImplementation(async (url) => {
    const href = String(url);
    if (href.startsWith('/api/performance/catalog')) {
      return { success: true, data: { periods: [
        { key: '2026-07', year: 2026, month: 'July' },
        { key: '2026-06', year: 2026, month: 'June' },
        { key: '2025-07', year: 2025, month: 'July' },
        { key: '2025-06', year: 2025, month: 'June' },
      ] } };
    }
    if (href.startsWith('/api/performance/records')) {
      const period = new URL(href, 'http://x').searchParams.get('period');
      const all = [rawAgent('E2025', 'July 2025', 'July', 2025), rawAgent('E2026', 'July 2026', 'July', 2026), rawAgent('J2025', 'June 2025', 'June', 2025), rawAgent('J2026', 'June 2026', 'June', 2026)];
      const items = all.filter((item) => `${item.year}-${item.month === 'July' ? '07' : '06'}` === period);
      return { success: true, data: { items, has_more: false } };
    }
    if (String(url).startsWith('/api/config/teams')) return { success: true, data: [] };
    return { success: false, message: String(url) };
  });
});

afterEach(() => {
  clients.splice(0).forEach((client) => client.clear());
  localStorage.removeItem('pms_session_v1');
});

describe('default bounded performance period selection', () => {
  it('keeps July 2025 and July 2026 apart for an exact period', async () => {
    const exact = renderHook(() => usePerformanceData('2025-07', 'all'), { wrapper: wrapperFor() });
    await waitFor(() => expect(exact.result.current.agents.map((item) => item.identity.employee_id)).toEqual(['E2025']));
    expect(exact.result.current.agents[0]?.year).toBe(2025);

    const named = renderHook(() => usePerformanceData('July', 'all'), { wrapper: wrapperFor() });
    await waitFor(() => expect(named.result.current.agents.map((item) => item.identity.employee_id)).toEqual(['E2026']));
  });

  it('counts headcount for the exact year inside team summaries', async () => {
    const team = renderHook(() => useTeamData(null, '2025-07'), { wrapper: wrapperFor() });
    await waitFor(() => expect(team.result.current.loading).toBe(false));
    expect(team.result.current.rows.map((row) => row.name)).toEqual(['July 2025']);
    expect(team.result.current.totalAgents).toBe(1);
    expect(team.result.current.prevTotalAgents).toBe(1);
    expect(team.result.current.currMonthName).toBe('July');

    const latestJuly = renderHook(() => useTeamData(null, 'July'), { wrapper: wrapperFor() });
    await waitFor(() => expect(latestJuly.result.current.rows.map((row) => row.name)).toEqual(['July 2026']));
    expect(latestJuly.result.current.totalAgents).toBe(1);
  });
});
