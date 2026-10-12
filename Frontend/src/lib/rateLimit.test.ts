import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  RateLimitError,
  isRateLimitError,
  notifyRateLimited,
  rateLimitMessage,
  rejectRateLimited,
  retryAfterSeconds,
  setRateLimitNotifier,
} from './rateLimit';

function response(headers: Record<string, string> = {}, status = 429) {
  return new Response(null, { status, headers });
}

describe('rateLimitMessage', () => {
  it('names the wait in seconds, with the singular only for one second', () => {
    expect(rateLimitMessage(23)).toBe('Too many requests. Try again in 23 seconds.');
    expect(rateLimitMessage(1)).toBe('Too many requests. Try again in 1 second.');
  });
});

describe('retryAfterSeconds', () => {
  it('reads a whole number of seconds from Retry-After', () => {
    expect(retryAfterSeconds(response({ 'Retry-After': '23' }))).toBe(23);
  });

  it('rounds up fractions and uses the fallback for a missing, zero or unreadable value', () => {
    expect(retryAfterSeconds(response({ 'Retry-After': '2.4' }))).toBe(3);
    expect(retryAfterSeconds(response({ 'Retry-After': '0' }))).toBe(60);
    expect(retryAfterSeconds(response({ 'Retry-After': 'Wed, 21 Oct 2026 07:28:00 GMT' }))).toBe(60);
    expect(retryAfterSeconds(response())).toBe(60);
  });
});

describe('RateLimitError', () => {
  it('carries the status, the wait and the message', () => {
    const error = new RateLimitError(12);
    expect(error.status).toBe(429);
    expect(error.retryAfterSeconds).toBe(12);
    expect(error.message).toBe('Too many requests. Try again in 12 seconds.');
    expect(isRateLimitError(error)).toBe(true);
    expect(isRateLimitError(new Error('boom'))).toBe(false);
    expect(isRateLimitError({ status: 429 })).toBe(false);
  });

  it('rejectRateLimited builds the error from the response and notifies only when asked', () => {
    const notifier = vi.fn();
    setRateLimitNotifier(notifier);
    try {
      const silent = rejectRateLimited(response({ 'Retry-After': '9' }), { notify: false });
      expect(silent.retryAfterSeconds).toBe(9);
      expect(notifier).not.toHaveBeenCalled();
    } finally {
      setRateLimitNotifier(null);
    }
  });
});

describe('notifyRateLimited', () => {
  // Each case starts an hour after the last one, which is longer than any retry window.
  let clock = Date.parse('2030-01-01T00:00:00Z');

  beforeEach(() => {
    clock += 3_600_000;
  });

  afterEach(() => {
    setRateLimitNotifier(null);
  });

  it('shows one message for the retry window, and nothing while no notifier is registered', () => {
    expect(() => notifyRateLimited(10, clock)).not.toThrow();
    const notifier = vi.fn();
    setRateLimitNotifier(notifier);
    notifyRateLimited(10, clock + 1_000);
    notifyRateLimited(10, clock + 2_000);
    notifyRateLimited(10, clock + 9_999);
    expect(notifier).toHaveBeenCalledTimes(1);
    expect(notifier).toHaveBeenCalledWith('Too many requests. Try again in 10 seconds.');
  });

  it('shows the next message once the window has passed', () => {
    const notifier = vi.fn();
    setRateLimitNotifier(notifier);
    notifyRateLimited(10, clock);
    notifyRateLimited(10, clock + 10_000);
    expect(notifier).toHaveBeenCalledTimes(2);
  });

  it('unregisters cleanly', () => {
    const notifier = vi.fn();
    setRateLimitNotifier(notifier);
    setRateLimitNotifier(null);
    notifyRateLimited(5, clock);
    expect(notifier).not.toHaveBeenCalled();
  });
});
