import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetch } from '../../lib/apiClient';

vi.mock('../../lib/apiClient', () => ({ apiFetch: vi.fn() }));

const periods = [
  { key: '2024-12', year: 2024, month: 'December' },
  { key: '2025-07', year: 2025, month: 'July' },
  { key: '2026-01', year: 2026, month: 'January' },
  { key: '2026-07', year: 2026, month: 'July' },
];

function summary(period: string, agents: number, previous: string | null, scope: { location?: string; region?: string | null; performance_level?: string | null }) {
  const [year, monthNumber] = period.split('-');
  const month = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'][Number(monthNumber) - 1];
  const previousPeriod = previous
    ? { key: previous, year: Number(previous.slice(0, 4)), month: previous.endsWith('12') ? 'December' : 'January' }
    : null;
  return {
    success: true,
    data: {
      scope: {
        period,
        team: null,
        performance_level: scope.performance_level ?? null,
        region: scope.region ?? null,
        position: null,
        location: scope.location ?? 'all',
      },
      period: { key: period, month, year: Number(year) },
      previous_period: previousPeriod,
      current: { total_agents: agents, average_score: 80, grade_counts: { A: agents } },
      previous: null,
      trend: [],
      team_breakdown: [],
      data_version: 1,
      as_of: '2026-10-09T00:00:00Z',
    },
  };
}

let releaseNext: (() => void) | null = null;

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv('VITE_SCOPED_PERFORMANCE_API', 'true');
  localStorage.removeItem('pms_session_v1');
  releaseNext = null;
  vi.mocked(apiFetch).mockReset();
  vi.mocked(apiFetch).mockImplementation(async (url) => {
    const href = String(url);
    if (href.startsWith('/api/performance/catalog')) return { success: true, data: { periods, months: [], scopes: [] } };
    const params = new URL(href, 'http://localhost').searchParams;
    const period = params.get('period') || '';
    const location = params.get('location') || 'all';
    const region = params.get('region');
    const level = params.get('performance_level');
    if (location === 'sharjah' || region === 'UAE' || level === 'Employee') {
      return new Promise((resolve) => { releaseNext = () => resolve(summary(period, 4, '2026-01', { location, region, performance_level: level })); });
    }
    const agents = period === '2025-07' ? 5 : 11;
    const previous = period === '2025-07' ? '2024-12' : '2026-01';
    return summary(period, agents, previous, { location });
  });
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

async function loadSummary() {
  const mod = await import('./usePerformanceDashboard');
  expect(mod.scopedPerformanceApiEnabled).toBe(true);
  return mod.useScopedExecutiveSummary;
}

function renderSummary(selector: string, region = 'All', location = 'all', level = 'All') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return { client, wrapper, selector, region, location, level };
}

describe('useScopedExecutiveSummary period and scope', () => {
  it('requests an exact period and uses the API previous period from the prior year', async () => {
    const useScopedExecutiveSummary = await loadSummary();
    const { wrapper } = renderSummary('2025-07');
    const hook = renderHook(() => useScopedExecutiveSummary('2025-07', 'All', 'all', 'All'), { wrapper });
    await waitFor(() => expect(hook.result.current.totalAgents).toBe(5));
    expect(hook.result.current.activePeriod?.key).toBe('2025-07');
    expect(hook.result.current.previousPeriod?.key).toBe('2024-12');
    const requested = vi.mocked(apiFetch).mock.calls.map(([url]) => String(url)).filter((url) => url.includes('/summary'));
    expect(requested.some((url) => url.includes('period=2025-07'))).toBe(true);
    expect(requested.some((url) => url.includes('period=2026-07'))).toBe(false);
  });

  it('uses the latest matching month when no exact period is present', async () => {
    const useScopedExecutiveSummary = await loadSummary();
    const { wrapper } = renderSummary('July');
    const hook = renderHook(() => useScopedExecutiveSummary('July'), { wrapper });
    await waitFor(() => expect(hook.result.current.totalAgents).toBe(11));
    expect(hook.result.current.activePeriod?.key).toBe('2026-07');
    const requested = vi.mocked(apiFetch).mock.calls.map(([url]) => String(url)).find((url) => url.includes('/summary'));
    expect(requested).toContain('period=2026-07');
  });

  it('hides placeholder totals when the same period is requested for another location', async () => {
    const useScopedExecutiveSummary = await loadSummary();
    const { wrapper } = renderSummary('2026-07');
    const hook = renderHook(
      ({ location }: { location: string }) => useScopedExecutiveSummary('2026-07', 'All', location, 'All'),
      { wrapper, initialProps: { location: 'dubai' } },
    );
    await waitFor(() => expect(hook.result.current.totalAgents).toBe(11));
    hook.rerender({ location: 'sharjah' });
    await waitFor(() => expect(hook.result.current.loading).toBe(true));
    expect(hook.result.current.totalAgents).toBe(0);
    expect(hook.result.current.previousPeriod).toBeNull();
    releaseNext?.();
    await waitFor(() => expect(hook.result.current.totalAgents).toBe(4));
    expect(hook.result.current.loading).toBe(false);
  });

  it('hides placeholder totals when the same period changes region or level', async () => {
    const useScopedExecutiveSummary = await loadSummary();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const hook = renderHook(
      ({ region, level }: { region: string; level: string }) => useScopedExecutiveSummary('2026-07', region, 'all', level),
      { wrapper, initialProps: { region: 'All', level: 'All' } },
    );
    await waitFor(() => expect(hook.result.current.totalAgents).toBe(11));
    hook.rerender({ region: 'UAE', level: 'All' });
    await waitFor(() => expect(hook.result.current.loading).toBe(true));
    expect(hook.result.current.totalAgents).toBe(0);
    releaseNext?.();
    await waitFor(() => expect(hook.result.current.totalAgents).toBe(4));

    hook.rerender({ region: 'UAE', level: 'Employee' });
    await waitFor(() => expect(hook.result.current.loading).toBe(true));
    expect(hook.result.current.totalAgents).toBe(0);
  });
});
