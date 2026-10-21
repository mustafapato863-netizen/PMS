/**
 * Lane caps measured on the real fetch boundary: apiClient is NOT mocked, global fetch is. A fetch counts as
 * in flight from the call until it has actually settled (rejected after abort, or its body finished).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MonthlyPresentationView from './MonthlyPresentationView';
import { DECK_LANES, DECK_REQUEST_DEADLINE_MS, deckRequestsInFlight, resetDeckLimiter } from './useMonthlyPresentationData';
import { setAccessToken } from '../../lib/apiClient';

vi.mock('../../context/auth', () => ({ useAuth: () => ({ currentUser: { role: 'Admin', accessible_regions: [] } }) }));
vi.mock('../../context/RoleContext', () => ({ useUserRole: () => ({ role: 'Admin' }) }));

type Mode = 'hung-headers' | 'slow-body';
const laneOf = (url: string) => (url.includes('/api/insights/') ? 'insights' : url.includes('/api/corrective-actions/') ? 'actions' : 'other');

function harness(mode: Mode) {
  const live = { insights: 0, actions: 0, other: 0 };
  const peak = { insights: 0, actions: 0, other: 0 };
  const calls = { insights: 0, actions: 0, other: 0 };
  const fetchMock = vi.fn((input: RequestInfo | URL, init: RequestInit = {}) => {
    const lane = laneOf(String(input));
    calls[lane] += 1; live[lane] += 1; peak[lane] = Math.max(peak[lane], live[lane]);
    let done = false;
    const settle = () => { if (!done) { done = true; live[lane] -= 1; } };
    const signal = init.signal!;
    const untilAbort = () => new Promise<never>((_, reject) => {
      const fail = () => { settle(); reject(signal.reason); };
      if (signal.aborted) fail(); else signal.addEventListener('abort', fail, { once: true });
    });
    if (mode === 'hung-headers') return untilAbort();
    return Promise.resolve({ ok: true, status: 200, statusText: 'OK', json: untilAbort } as unknown as Response);
  });
  return { fetchMock, live, peak, calls };
}

const renderDeck = () => render(
  <QueryClientProvider client={new QueryClient()}>
    <MemoryRouter initialEntries={['/monthly-presentation?region=egy&month=2026-09']}>
      <MonthlyPresentationView today={new Date(2026, 9, 21)} />
    </MemoryRouter>
  </QueryClientProvider>,
);

describe.each<Mode>(['hung-headers', 'slow-body'])('real in-flight fetches stay within the lane caps (%s)', (mode) => {
  beforeEach(() => {
    resetDeckLimiter();
    setAccessToken('caps-test-token');
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it('never exceeds 2 Insights / 1 actions, sends no request that expired in the queue, errors at ~15 s', async () => {
    const h = harness(mode);
    vi.stubGlobal('fetch', h.fetchMock);
    const view = renderDeck();
    for (let t = 0; t < 40_000; t += 250) {
      await act(async () => { await vi.advanceTimersByTimeAsync(250); });
      expect(h.live.insights).toBeLessThanOrEqual(DECK_LANES.insights);
      expect(h.live.actions).toBeLessThanOrEqual(DECK_LANES.actions);
      if (t === DECK_REQUEST_DEADLINE_MS + 1_000) {
        // ~16 s: every slide that depends on a hung request already shows its error (no retry after a timeout).
        expect(view.container.querySelector('[data-testid="slide-error-1"]')).not.toBeNull();
        expect(view.container.querySelector('[data-testid="slide-error-8"]')).not.toBeNull();
      }
    }
    expect(h.peak.insights).toBe(DECK_LANES.insights);
    expect(h.peak.actions).toBe(DECK_LANES.actions);
    // 7 Insights calls (region, overview, 5 teams) and 2 action calls were requested; the queued ones expired
    // locally, so only the first wave reached fetch.
    expect(h.calls.insights).toBe(DECK_LANES.insights);
    expect(h.calls.actions).toBe(DECK_LANES.actions);
    expect(h.live).toEqual({ insights: 0, actions: 0, other: 0 });
    expect(deckRequestsInFlight('insights')).toEqual({ active: 0, queued: 0 });
    expect(deckRequestsInFlight('actions')).toEqual({ active: 0, queued: 0 });
    view.unmount();
  });
});
