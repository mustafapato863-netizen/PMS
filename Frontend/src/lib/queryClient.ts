/**
 * React Query Client Configuration
 * Centralized query client with default settings for the entire app.
 * Handles caching, retries, and stale time globally.
 */

import { QueryClient } from '@tanstack/react-query';
import { isRateLimitError } from './rateLimit';

/** Retries up to `limit` times, but never a rate-limited request: retrying it only extends the limit. */
export function shouldRetryRequest(limit: number) {
  return (failureCount: number, error: unknown) => !isRateLimitError(error) && failureCount < limit;
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 2 * 60 * 1000, // 2 minutes before data is considered stale
      gcTime: 10 * 60 * 1000, // Keep unused data in cache for 10 minutes (formerly cacheTime)
      retry: shouldRetryRequest(2), // Retry failed requests up to 2 times, except rate-limited ones
      refetchOnWindowFocus: false, // Don't refetch when window regains focus
      refetchOnReconnect: true, // Refetch only when the query is stale after reconnecting
      refetchOnMount: true, // Refetch only when the query is stale on mount
    },
    mutations: {
      retry: shouldRetryRequest(1), // Retry failed mutations once, except rate-limited ones
    },
  },
});

/**
 * Remove all user-scoped server state during a session boundary.
 * Cancellation is awaited before clearing so in-flight responses cannot
 * repopulate private data after logout.
 */
export async function clearAuthenticatedQueryState(): Promise<void> {
  await queryClient.cancelQueries();
  queryClient.clear();
}
