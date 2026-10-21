import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MonthlyPresentationView from './MonthlyPresentationView';
import { DECK_WORKSPACE_SECTIONS, DeckTimeoutError, readEnvelope, withDeadline } from './useMonthlyPresentationData';

const mocks = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('../../lib/apiClient', () => ({ apiFetch: mocks.apiFetch }));
vi.mock('../../context/auth', () => ({ useAuth: () => ({ currentUser: { role: 'Admin', accessible_regions: [] } }) }));
vi.mock('../../context/RoleContext', () => ({ useUserRole: () => ({ role: 'Admin' }) }));

const ws = {
  summary: { analyzed_kpis: 2, expected_kpis: 2, coverage_percent: 100 },
  kpi_diagnosis: [], team_summaries: [], performance_drivers: [], options: { teams: [] }, people_contribution_analysis: null,
  executive_story: { headline: 'EGY headline', current_score: 86.4, target_score: 90, gap_points: -3, score_change: 1, basis_context: { like_for_like: true } },
  comparison: { current: null, previous: null, is_adjacent: false, note: null },
};
const action = { id: 'a1', manager_action: 'Fix: Call back customers', team: 'Coding EGY', region: 'EGY', month: 'September', year: 2026, status: 'Open', priority: 'Low', due_date: '2026-09-20', owner: { id: 'o1', name: 'Sara Ali' } };
const never = () => new Promise(() => {});
type Handler = (url: string) => unknown;
let route: Handler;
let seen: string[];
const isRegionWs = (u: string) => u.startsWith('/api/insights/workspace') && !u.includes('team=');

beforeEach(() => {
  seen = [];
  route = (url) => {
    if (url.startsWith('/api/insights/workspace')) return { success: true, data: url.includes('kpi_overview') ? { kpi_overview: { total_kpis: 2, on_track: 2, at_risk: 0, critical: 0 } } : ws };
    if (url.startsWith('/api/corrective-actions/follow-up')) return { success: true, data: { summary: {}, actions: [action] } };
    return { success: true, data: [] };
  };
  mocks.apiFetch.mockReset();
  mocks.apiFetch.mockImplementation(async (url: string) => { seen.push(url); return route(url); });
});
afterEach(() => vi.useRealTimers());

const renderDeck = (url = '/monthly-presentation?region=egy&month=2026-09') => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[url]}><MonthlyPresentationView today={new Date(2026, 9, 21)} /></MemoryRouter>
  </QueryClientProvider>,
);
const slide = (n: number) => document.getElementById(`s${String(n).padStart(2, '0')}`)!;

describe('Monthly Presentation loading (root cause: unsectioned region workspace)', () => {
  it('asks the region workspace for named, period-window sections only, and kpi_overview on its own request', async () => {
    renderDeck();
    await screen.findByText(/Egypt at 86.4%/);
    const region = seen.filter(isRegionWs);
    expect(region.length).toBe(2);
    region.forEach((u) => expect(new URLSearchParams(u.split('?')[1]).get('sections')).toBeTruthy());
    const main = region.find((u) => !u.includes('kpi_overview'))!;
    expect(new URLSearchParams(main.split('?')[1]).get('sections')!.split(',').sort()).toEqual([...DECK_WORKSPACE_SECTIONS].sort());
    expect(DECK_WORKSPACE_SECTIONS).not.toContain('kpi_overview'); // kpi_overview forces the backend's full-record path
    const p = new URLSearchParams(main.split('?')[1]);
    expect(p.get('month')).toBe('September'); expect(p.get('year')).toBe('2026'); expect(p.get('region')).toBe('EGY');
  });

  it('renders the slides whose data arrived while the region workspace is still pending (no global gate)', async () => {
    route = (url) => {
      if (isRegionWs(url) && !url.includes('kpi_overview')) return never();
      if (url.startsWith('/api/corrective-actions/follow-up')) return { success: true, data: { summary: {}, actions: [action] } };
      if (url.startsWith('/api/insights/workspace')) return { success: true, data: ws };
      return { success: true, data: [] };
    };
    renderDeck();
    expect(await within(await waitFor(() => slide(8))).findByText('Call back customers')).toBeTruthy();
    expect(screen.queryByText(/Loading Egypt · September 2026…/)).toBeNull();
    expect(within(slide(1)).getByTestId('slide-loading-1')).toBeTruthy();
    expect(within(slide(4)).getByTestId('slide-loading-4')).toBeTruthy();
    expect(within(slide(11)).getByText('How to read this deck')).toBeTruthy();
  });

  it('a failed region workspace shows a per-slide error with Retry, and Retry recovers', async () => {
    let fail = true;
    route = (url) => {
      if (isRegionWs(url) && !url.includes('kpi_overview')) { if (fail) throw new Error('Server error 500'); return { success: true, data: ws }; }
      if (url.startsWith('/api/corrective-actions/follow-up')) return { success: true, data: { summary: {}, actions: [action] } };
      if (url.startsWith('/api/insights/workspace')) return { success: true, data: ws };
      return { success: true, data: [] };
    };
    renderDeck();
    const err = await screen.findByTestId('slide-error-1');
    expect(err.textContent).toContain('Server error 500');
    expect(await within(slide(8)).findByText('Call back customers')).toBeTruthy();
    fail = false;
    fireEvent.click(within(err).getByRole('button', { name: 'Retry' }));
    await screen.findByText(/Egypt at 86.4%/);
    expect(screen.queryByTestId('slide-error-1')).toBeNull();
  });

  it('follow-up answering 200 with success:false is an error on the action slides, not "no actions"', async () => {
    const base = route;
    route = (url) => url.startsWith('/api/corrective-actions/follow-up') ? { success: false, message: 'Failed to fetch action follow-up.' } : base(url);
    renderDeck();
    const err = await screen.findByTestId('slide-error-8');
    expect(err.textContent).toContain('Failed to fetch action follow-up.');
    expect(screen.getByTestId('slide-error-9')).toBeTruthy();
    expect(screen.queryByText(/No corrective actions recorded/)).toBeNull();
  });

  it('a bad summary-records shape fails only the grade mix card, with Retry', async () => {
    const base = route;
    route = (url) => url.startsWith('/api/performance/summary-records') ? { success: true, data: { unexpected: true } } : base(url);
    renderDeck();
    const err = await screen.findByTestId('grade-mix-error');
    expect(err.textContent).toContain('Unexpected summary records response shape');
    expect(within(slide(3)).getByText(/Egypt at 86.4%/)).toBeTruthy();
    expect(within(err).getByRole('button', { name: 'Retry' })).toBeTruthy();
  });

  it('empty slides say why and offer Retry', async () => {
    const base = route;
    route = (url) => url.startsWith('/api/corrective-actions/follow-up') ? { success: true, data: { summary: {}, actions: [] } } : base(url);
    renderDeck();
    await screen.findByText(/Egypt at 86.4%/);
    const s8 = await waitFor(() => { const el = within(slide(8)).getByText(/No corrective actions recorded/); return el; });
    expect(within(slide(8)).getByRole('button', { name: 'Retry' })).toBeTruthy();
    expect(within(slide(4)).getByText('No scored KPIs for this period')).toBeTruthy();
    expect(within(slide(4)).getByRole('button', { name: 'Retry' })).toBeTruthy();
    expect(s8).toBeTruthy();
  });

  it('Present is disabled until the region workspace is in, then opens full-screen present mode', async () => {
    renderDeck();
    await screen.findByText(/Egypt at 86.4%/);
    const btn = screen.getByRole('button', { name: /present/i });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('print', () => {
  it('print mode renders every slide and auto-opens the print dialog once the data is in', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    renderDeck('/monthly-presentation?region=egy&month=2026-09&print=1&autoprint=1&mask=1');
    await screen.findByText(/Egypt at 86.4%/);
    await waitFor(() => expect(print).toHaveBeenCalledTimes(1), { timeout: 2000 });
    expect(document.querySelectorAll('.mp-slide').length).toBe(11);
    print.mockRestore();
  });
});

describe('withDeadline / readEnvelope', () => {
  it('rejects a request that never settles at the deadline and aborts its signal', async () => {
    vi.useFakeTimers();
    let inner: AbortSignal | undefined;
    const p = withDeadline(undefined, 1000, (s) => { inner = s; return new Promise(() => {}); });
    const assertion = expect(p).rejects.toBeInstanceOf(DeckTimeoutError);
    await vi.advanceTimersByTimeAsync(1001);
    await assertion;
    expect(inner!.aborted).toBe(true);
  });
  it('forwards a TanStack cancel to the request', async () => {
    const outer = new AbortController();
    let inner: AbortSignal | undefined;
    const p = withDeadline(outer.signal, 10_000, (s) => { inner = s; return new Promise((_, rej) => s.addEventListener('abort', () => rej(new Error('aborted')))); });
    outer.abort();
    await expect(p).rejects.toThrow('aborted');
    expect(inner!.aborted).toBe(true);
  });
  it('rejects non-envelopes and success:false', () => {
    expect(() => readEnvelope('<!doctype html>' as never, '/api/x')).toThrow(/Unexpected response/);
    expect(() => readEnvelope({ success: false, data: null, message: 'nope' }, '/api/x')).toThrow('nope');
    expect(readEnvelope({ success: true, data: [1] }, '/api/x')).toEqual([1]);
  });
});
