import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetch, refreshAccessToken, setAccessToken } from './apiClient';
import { RateLimitError, setRateLimitNotifier } from './rateLimit';

function json(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' }, ...init });
}

function rateLimited(retryAfter = '23') {
  return new Response(JSON.stringify({ success: false, message: 'Too many requests.' }), {
    status: 429,
    headers: { 'Content-Type': 'application/json', 'Retry-After': retryAfter },
  });
}

// Each case starts an hour later, so the shared notice window from an earlier case has expired.
let clock = Date.parse('2030-06-01T00:00:00Z');

describe('apiFetch rate limiting', () => {
  let notifier: ReturnType<typeof vi.fn<(message: string) => void>>;

  beforeEach(() => {
    clock += 3_600_000;
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(clock);
    setAccessToken('rate-limit-test-token');
    notifier = vi.fn<(message: string) => void>();
    setRateLimitNotifier(notifier);
  });

  afterEach(() => {
    setRateLimitNotifier(null);
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('rejects a 429 with a typed error carrying Retry-After, and shows one notice', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => rateLimited('23')));
    const error = await apiFetch('/api/reports/export').catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(RateLimitError);
    expect((error as RateLimitError).retryAfterSeconds).toBe(23);
    expect(notifier).toHaveBeenCalledTimes(1);
    expect(notifier).toHaveBeenCalledWith('Too many requests. Try again in 23 seconds.');
  });

  it('does not stack notices for repeated 429s inside the same window', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => rateLimited('30')));
    for (let attempt = 0; attempt < 3; attempt += 1) {
      await expect(apiFetch('/api/reports/export')).rejects.toBeInstanceOf(RateLimitError);
    }
    expect(notifier).toHaveBeenCalledTimes(1);
  });

  it('treats a 429 on the retried request after a token refresh as a rate limit, not a generic failure', async () => {
    let calls = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/auth/refresh')) return json({ success: true, data: { access_token: 'refreshed-token' } });
      calls += 1;
      return calls === 1 ? new Response(null, { status: 401 }) : rateLimited('12');
    }));
    const error = await apiFetch('/api/employee/records').catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(RateLimitError);
    expect((error as RateLimitError).retryAfterSeconds).toBe(12);
    expect(notifier).toHaveBeenCalledTimes(1);
  });

  it('leaves the login 429 to the login form: a typed error, but no shared notice', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => rateLimited('30')));
    const error = await apiFetch('/api/auth/login', { method: 'POST', body: '{}' }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(RateLimitError);
    expect((error as RateLimitError).message).toBe('Too many requests. Try again in 30 seconds.');
    expect(notifier).not.toHaveBeenCalled();
  });

  it('keeps a rate-limited refresh separate from an ended session', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => rateLimited('20')));
    await expect(refreshAccessToken()).rejects.toBeInstanceOf(RateLimitError);
    expect(notifier).toHaveBeenCalledTimes(1);
  });

  it('still reports other failures as before, without the rate-limit path', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ success: false, message: 'Nope' }, { status: 400 })));
    const error = await apiFetch('/api/reports/export').catch((caught: unknown) => caught);
    expect(error).not.toBeInstanceOf(RateLimitError);
    expect(notifier).not.toHaveBeenCalled();
  });
});
