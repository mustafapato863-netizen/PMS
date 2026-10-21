import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetch, setAccessToken } from './apiClient';
import { API_TIMEOUT_MS } from '../config';

/** A response whose headers arrive at once and whose body never finishes until the fetch signal aborts. */
function stalledBodyFetch() {
  const signals: AbortSignal[] = [];
  const fetchMock = vi.fn(async (_input: unknown, init: RequestInit) => {
    const signal = init.signal!;
    signals.push(signal);
    return {
      ok: true, status: 200, statusText: 'OK',
      json: () => new Promise((_, reject) => {
        if (signal.aborted) reject(signal.reason);
        signal.addEventListener('abort', () => reject(signal.reason), { once: true });
      }),
    } as unknown as Response;
  });
  return { fetchMock, signals };
}

describe('apiFetch abortBody', () => {
  beforeEach(() => setAccessToken('abort-body-test-token'));
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('with abortBody, the caller signal cancels a stalled body after the headers arrived', async () => {
    const { fetchMock, signals } = stalledBodyFetch();
    vi.stubGlobal('fetch', fetchMock);
    const caller = new AbortController();
    const pending = apiFetch('/api/corrective-actions/owners', { signal: caller.signal }, { abortBody: true });
    await vi.waitFor(() => expect(signals).toHaveLength(1));
    caller.abort(new DOMException('left the page', 'AbortError'));
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect(signals[0].aborted).toBe(true);
  });

  it('with abortBody, the API timeout also cancels a stalled body', async () => {
    vi.useFakeTimers();
    const { fetchMock, signals } = stalledBodyFetch();
    vi.stubGlobal('fetch', fetchMock);
    const pending = apiFetch('/api/corrective-actions/owners', {}, { abortBody: true });
    const settled = pending.catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(API_TIMEOUT_MS + 1);
    expect(await settled).toMatchObject({ name: 'TimeoutError' });
    expect(signals[0].aborted).toBe(true);
  });

  it('a completed abortBody request releases its timer and listener', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ success: true, data: [] }), { status: 200 })));
    const caller = new AbortController();
    const remove = vi.spyOn(caller.signal, 'removeEventListener');
    await expect(apiFetch('/api/x', { signal: caller.signal }, { abortBody: true })).resolves.toEqual({ success: true, data: [] });
    expect(remove).toHaveBeenCalledWith('abort', expect.any(Function));
  });

  it('default behaviour is unchanged: the link to the caller signal ends at the headers', async () => {
    const { fetchMock, signals } = stalledBodyFetch();
    vi.stubGlobal('fetch', fetchMock);
    const caller = new AbortController();
    const pending = apiFetch('/api/other-page', { signal: caller.signal });
    pending.catch(() => {});
    await vi.waitFor(() => expect(signals).toHaveLength(1));
    await new Promise((r) => setTimeout(r, 10)); // headers resolved, body still pending
    caller.abort();
    await new Promise((r) => setTimeout(r, 10));
    expect(signals[0].aborted).toBe(false);
  });
});
