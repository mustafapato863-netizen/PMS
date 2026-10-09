import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetch } from '../lib/apiClient';
import { mapScopedPerformanceRecord, useAllTeamsSummary, usePerformanceData, useTeamData } from './usePerformanceData';

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

function agent(id: string, name: string, month: string, year: number) {
  return mapScopedPerformanceRecord({
    employee_id: id,
    employee_name: name,
    team: 'Inbound',
    month,
    year,
    calls: { inbound: 10 },
    score: year,
  });
}

const july2025 = agent('E2025', 'July 2025', 'July', 2025);
const july2026 = agent('E2026', 'July 2026', 'July', 2026);
const june2025 = agent('J2025', 'June 2025', 'June', 2025);
const june2026 = agent('J2026', 'June 2026', 'June', 2026);

beforeEach(() => {
  localStorage.setItem('pms_session_v1', JSON.stringify({ id: crypto.randomUUID(), role: 'Admin' }));
  vi.mocked(apiFetch).mockReset();
  vi.mocked(apiFetch).mockImplementation(async (url) => {
    if (String(url).startsWith('/api/performance')) return { success: true, data: [july2025, july2026, june2025, june2026] };
    if (String(url).startsWith('/api/config/teams')) return { success: true, data: [] };
    return { success: false, message: String(url) };
  });
});

afterEach(() => {
  clients.splice(0).forEach((client) => client.clear());
  localStorage.removeItem('pms_session_v1');
});

describe('legacy performance period selection', () => {
  it('keeps July 2025 and July 2026 apart for an exact period', async () => {
    const exact = renderHook(() => usePerformanceData('2025-07', 'all'), { wrapper: wrapperFor() });
    await waitFor(() => expect(exact.result.current.agents.map((item) => item.identity.employee_id)).toEqual(['E2025']));
    expect(exact.result.current.agents[0]?.year).toBe(2025);

    const named = renderHook(() => usePerformanceData('July', 'all'), { wrapper: wrapperFor() });
    await waitFor(() => expect(named.result.current.agents.map((item) => item.identity.employee_id)).toEqual(['E2026']));
  });

  it('counts headcount for the exact year inside team and executive summaries', async () => {
    const team = renderHook(() => useTeamData(null, '2025-07'), { wrapper: wrapperFor() });
    await waitFor(() => expect(team.result.current.loading).toBe(false));
    expect(team.result.current.rows.map((row) => row.name)).toEqual(['July 2025']);
    expect(team.result.current.totalAgents).toBe(1);
    expect(team.result.current.prevTotalAgents).toBe(1);
    expect(team.result.current.currMonthName).toBe('July');

    const latestJuly = renderHook(() => useTeamData(null, 'July'), { wrapper: wrapperFor() });
    await waitFor(() => expect(latestJuly.result.current.rows.map((row) => row.name)).toEqual(['July 2026']));
    expect(latestJuly.result.current.totalAgents).toBe(1);

    const summary = renderHook(() => useAllTeamsSummary('2026-07'), { wrapper: wrapperFor() });
    await waitFor(() => expect(summary.result.current.loading).toBe(false));
    expect(summary.result.current.totalAgents).toBe(1);
    expect(summary.result.current.summaries.reduce((sum, item) => sum + item.agentCount, 0)).toBe(1);
  });
});
