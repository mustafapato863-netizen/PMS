import { afterEach, describe, expect, it } from 'vitest';
import { clearAuthenticatedQueryState, queryClient } from './queryClient';

afterEach(() => {
  queryClient.clear();
});

describe('clearAuthenticatedQueryState', () => {
  it('cancels an active private query before clearing the cache', async () => {
    let aborted = false;
    const pending = queryClient.fetchQuery({
      queryKey: ['private', 'active-user'],
      queryFn: ({ signal }) => new Promise<never>((_resolve, reject) => {
        signal.addEventListener('abort', () => {
          aborted = true;
          reject(new DOMException('Cancelled', 'AbortError'));
        });
      }),
    });

    await clearAuthenticatedQueryState();

    await expect(pending).rejects.toBeDefined();
    expect(aborted).toBe(true);
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });
});
