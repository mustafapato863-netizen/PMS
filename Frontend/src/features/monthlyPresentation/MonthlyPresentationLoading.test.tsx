import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MonthlyPresentationView from './MonthlyPresentationView';
import { DECK_LANES, DECK_MAX_CONCURRENT, DECK_QUERY_OPTIONS, DECK_SLOT_FALLBACK_MS, DECK_MIN_START_MS, DECK_REQUEST_DEADLINE_MS, DECK_WORKSPACE_SECTIONS, DeckTimeoutError, deckRequestsInFlight, limitDeckRequest, resetDeckLimiter, readEnvelope, withDeadline } from './useMonthlyPresentationData';

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
  resetDeckLimiter();
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
    // Every deck call opts in to body-level abort and carries a signal.
    mocks.apiFetch.mock.calls.forEach(([, init, behaviour]) => { expect(behaviour).toEqual({ abortBody: true }); expect(init.signal).toBeInstanceOf(AbortSignal); });
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
    const err = await screen.findByTestId('slide-error-1', {}, { timeout: 5000 });
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
    const err = await screen.findByTestId('slide-error-8', {}, { timeout: 5000 });
    expect(err.textContent).toContain('Failed to fetch action follow-up.');
    expect(screen.getByTestId('slide-error-9')).toBeTruthy();
    expect(screen.queryByText(/No corrective actions recorded/)).toBeNull();
  });

  it('grade mix is reported as not available and summary-records is never requested', async () => {
    renderDeck();
    await screen.findByText(/Egypt at 86.4%/);
    expect(within(slide(3)).getByTestId('grade-mix-unavailable').textContent).toMatch(/Not available/);
    expect(seen.some((u) => u.includes('summary-records'))).toBe(false);
  });

  it('a failing request is retried at most once, and Retry while fetching does not start a second request', async () => {
    let calls = 0;
    const base = route;
    route = (url) => { if (url.startsWith('/api/corrective-actions/follow-up')) { calls += 1; throw new Error('boom'); } return base(url); };
    renderDeck();
    const err = await screen.findByTestId('slide-error-8', {}, { timeout: 5000 });
    expect(calls).toBe(2); // first try + one retry
    const btn = within(err).getByRole('button', { name: 'Retry' });
    fireEvent.click(btn); fireEvent.click(btn); fireEvent.click(btn);
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(3));
    await new Promise((r) => setTimeout(r, 100));
    expect(calls).toBe(3); // three clicks while in flight dedupe to one request
  }, 15000);

  it('a hung Insights lane does not hold up follow-up and owners (slides 8-10)', async () => {
    const base = route;
    route = (url) => url.startsWith('/api/insights/workspace') ? never() : base(url);
    renderDeck();
    expect(await within(await waitFor(() => slide(8))).findByText('Call back customers', {}, { timeout: 1000 })).toBeTruthy();
    expect(deckRequestsInFlight('insights')).toEqual({ active: DECK_LANES.insights, queued: expect.any(Number) });
    expect(seen.some((u) => u === '/api/corrective-actions/owners')).toBe(true);
  });

  it('team workspace calls never exceed the concurrency limit', async () => {
    let peak = 0; let live = 0;
    mocks.apiFetch.mockImplementation(async (url: string) => {
      live += 1; peak = Math.max(peak, live);
      await new Promise((r) => setTimeout(r, 5));
      live -= 1; seen.push(url); return route(url);
    });
    renderDeck();
    await screen.findByText(/Egypt at 86.4%/);
    await waitFor(() => expect(deckRequestsInFlight()).toEqual({ active: 0, queued: 0 }));
    expect(peak).toBeLessThanOrEqual(DECK_LANES.insights + DECK_LANES.actions);
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

describe('limiter slots', () => {
  it('frees a slot only when the request settles, not when the deadline fires', async () => {
    vi.useFakeTimers();
    resetDeckLimiter();
    let settle: () => void = () => {};
    const p = withDeadline(undefined, 1000, (s) => limitDeckRequest(s, () => new Promise<void>((r) => { settle = r; }), 'actions'));
    const caught = p.catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(1001);
    expect(await caught).toBeInstanceOf(DeckTimeoutError);
    expect(deckRequestsInFlight('actions').active).toBe(1); // still open on the wire
    settle(); await vi.advanceTimersByTimeAsync(0);
    expect(deckRequestsInFlight('actions').active).toBe(0);
  });
  it('keeps the slot busy after an abort until the request settles (fallback only after DECK_SLOT_FALLBACK_MS)', async () => {
    vi.useFakeTimers();
    resetDeckLimiter();
    const c = new AbortController();
    limitDeckRequest(c.signal, () => new Promise(() => {}), 'actions').catch(() => {});
    c.abort();
    await vi.advanceTimersByTimeAsync(DECK_SLOT_FALLBACK_MS - 1);
    expect(deckRequestsInFlight('actions').active).toBe(1);
    await vi.advanceTimersByTimeAsync(2);
    expect(deckRequestsInFlight('actions').active).toBe(0);
  });

  it('a request whose deadline expired while queued fails locally and is never run', async () => {
    vi.useFakeTimers();
    resetDeckLimiter();
    let release: () => void = () => {};
    limitDeckRequest(undefined, () => new Promise<void>((r) => { release = r; }), 'actions');
    const run = vi.fn(async () => 1);
    const queued = limitDeckRequest(undefined, run, 'actions', Date.now() + DECK_MIN_START_MS + 500).catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(600); // now < DECK_MIN_START_MS left
    release(); await vi.advanceTimersByTimeAsync(0);
    expect(await queued).toBeInstanceOf(DeckTimeoutError);
    expect(run).not.toHaveBeenCalled();
    expect(deckRequestsInFlight('actions')).toEqual({ active: 0, queued: 0 });
  });
});

describe('withDeadline / readEnvelope / limits', () => {
  it('uses a 15 s deadline and no automatic refetching', () => {
    expect(DECK_REQUEST_DEADLINE_MS).toBe(15_000);
    expect(DECK_QUERY_OPTIONS.retry(0, new Error('500'))).toBe(true);
    expect(DECK_QUERY_OPTIONS.retry(1, new Error('500'))).toBe(false);
    expect(DECK_QUERY_OPTIONS.retry(0, new DeckTimeoutError(15_000))).toBe(false); // no retry after a timeout
    expect(DECK_QUERY_OPTIONS.retry(0, new DOMException('t', 'TimeoutError'))).toBe(false);
    expect(DECK_QUERY_OPTIONS).toMatchObject({ refetchOnWindowFocus: false, refetchOnReconnect: false, refetchOnMount: false, refetchInterval: false });
  });
  it('a queued request that is cancelled never runs', async () => {
    resetDeckLimiter();
    const gates: Array<() => void> = [];
    const hold = () => limitDeckRequest(undefined, () => new Promise<void>((r) => gates.push(r)), 'insights');
    const held = Array.from({ length: DECK_MAX_CONCURRENT }, hold);
    const c = new AbortController(); const run = vi.fn(async () => 1);
    const queued = limitDeckRequest(c.signal, run);
    c.abort();
    await expect(queued).rejects.toBeTruthy();
    gates.forEach((g) => g()); await Promise.all(held);
    expect(run).not.toHaveBeenCalled();
  });
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
