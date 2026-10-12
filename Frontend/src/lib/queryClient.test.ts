import { describe, expect, it } from 'vitest';
import { queryClient, shouldRetryRequest } from './queryClient';
import { RateLimitError } from './rateLimit';

describe('shouldRetryRequest', () => {
  it('never retries a rate-limited request, however few attempts have failed', () => {
    const retry = shouldRetryRequest(2);
    expect(retry(0, new RateLimitError(30))).toBe(false);
    expect(retry(1, new RateLimitError(30))).toBe(false);
  });

  it('keeps the normal retry budget for other failures', () => {
    const retry = shouldRetryRequest(2);
    expect(retry(0, new Error('server error'))).toBe(true);
    expect(retry(1, new Error('server error'))).toBe(true);
    expect(retry(2, new Error('server error'))).toBe(false);
  });
});

describe('queryClient defaults', () => {
  it('apply the rate-limit rule to queries and mutations alike', () => {
    const defaults = queryClient.getDefaultOptions();
    const queryRetry = defaults.queries?.retry as (count: number, error: unknown) => boolean;
    const mutationRetry = defaults.mutations?.retry as (count: number, error: unknown) => boolean;
    expect(typeof queryRetry).toBe('function');
    expect(typeof mutationRetry).toBe('function');
    expect(queryRetry(0, new RateLimitError(5))).toBe(false);
    expect(mutationRetry(0, new RateLimitError(5))).toBe(false);
    expect(queryRetry(0, new Error('boom'))).toBe(true);
    expect(mutationRetry(0, new Error('boom'))).toBe(true);
    expect(mutationRetry(1, new Error('boom'))).toBe(false);
  });
});
