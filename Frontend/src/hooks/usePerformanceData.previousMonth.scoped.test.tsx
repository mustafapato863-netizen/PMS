import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetch } from '../lib/apiClient';
import { useTeamData } from './usePerformanceData';

vi.mock('../lib/apiClient', () => ({ apiFetch: vi.fn() }));
vi.mock('./api/usePerformanceDashboard', () => ({ scopedPerformanceApiEnabled: true }));

// Scoped path: the page asks for the selected period and the one before it, and the previous month's
// agents must still be there when the comparison is worked out.
const periods = [
  { key: '2025-11', month: 'November', year: 2025 },
  { key: '2025-12', month: 'December', year: 2025 },
  { key: '2026-01', month: 'January', year: 2026 },
  { key: '2026-05', month: 'May', year: 2026 },
  { key: '2026-06', month: 'June', year: 2026 },
  { key: '2026-07', month: 'July', year: 2026 },
];

const recordsByPeriod: Record<string, Array<{ id: string; month: string; year: number; score: number }>> = {
  '2025-11': [{ id: 'N1', month: 'November', year: 2025, score: 60 }, { id: 'N2', month: 'November', year: 2025, score: 62 }],
  '2025-12': [{ id: 'D1', month: 'December', year: 2025, score: 70 }],
  '2026-01': [{ id: 'J1', month: 'January', year: 2026, score: 75 }],
  '2026-05': [{ id: 'M1', month: 'May', year: 2026, score: 65 }],
  '2026-06': [{ id: 'U1', month: 'June', year: 2026, score: 80 }, { id: 'U2', month: 'June', year: 2026, score: 84 }],
  '2026-07': [{ id: 'L1', month: 'July', year: 2026, score: 90 }],
};

const clients: QueryClient[] = [];

function wrapperFor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

function item(record: { id: string; month: string; year: number; score: number }) {
  return {
    employee_id: record.id,
    employee_name: `Agent ${record.id}`,
    team: 'Inbound',
    month: record.month,
    year: record.year,
    calls: { inbound: 10 },
    score: record.score,
  };
}

beforeEach(() => {
  localStorage.setItem('pms_session_v1', JSON.stringify({ id: crypto.randomUUID(), role: 'Admin' }));
  vi.mocked(apiFetch).mockReset();
  vi.mocked(apiFetch).mockImplementation(async (url) => {
    const href = String(url);
    if (href.startsWith('/api/performance/catalog')) return { success: true, data: { periods, months: [], scopes: [] } };
    if (href.startsWith('/api/performance/records')) {
      const period = new URL(href, 'http://localhost').searchParams.get('period') || '';
      const rows = (recordsByPeriod[period] || []).map(item);
      return { success: true, data: { items: rows, has_more: false } };
    }
    if (href.startsWith('/api/config/teams')) return { success: true, data: [] };
    return { success: false, message: href };
  });
});

afterEach(() => {
  clients.splice(0).forEach((client) => client.clear());
  localStorage.removeItem('pms_session_v1');
});

describe('previous month for a selected month (scoped path)', () => {
  it('compares a selected month with the previous month that has data', async () => {
    const hook = renderHook(() => useTeamData(null, '2026-07'), { wrapper: wrapperFor() });
    await waitFor(() => expect(hook.result.current.loading).toBe(false));

    expect(hook.result.current.rows.map((row) => row.id)).toEqual(['L1']);
    // June is the previous month with data, and its two agents are the comparison base.
    expect(hook.result.current.prevMonth).toBe('June');
    expect(hook.result.current.prevTotalAgents).toBe(2);
    expect(hook.result.current.prevAvgScore).toBeGreaterThan(0);
  });

  it('compares January with the previous December, not with an older November', async () => {
    const hook = renderHook(() => useTeamData(null, '2026-01'), { wrapper: wrapperFor() });
    await waitFor(() => expect(hook.result.current.loading).toBe(false));

    expect(hook.result.current.rows.map((row) => row.id)).toEqual(['J1']);
    expect(hook.result.current.prevMonth).toBe('December');
    expect(hook.result.current.prevTotalAgents).toBe(1);
  });

  it('compares the latest month in All with the month before it, by year and month', async () => {
    // Latest data is July 2026, so the comparison is June 2026. Sorting by month name alone would
    // treat December 2025 as the latest month and compare it with November 2025.
    const hook = renderHook(() => useTeamData(null, 'All'), { wrapper: wrapperFor() });
    await waitFor(() => expect(hook.result.current.loading).toBe(false));

    expect(hook.result.current.prevMonth).toBe('June');
  });
});
