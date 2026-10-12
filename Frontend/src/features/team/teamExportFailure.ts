import { isRateLimitError } from '../../lib/rateLimit';

/**
 * The alert for a failed team export, or null when no second message should show. A rate-limited export already
 * showed the shared notice with the retry time, so repeating it as an alert would contradict it.
 */
export function teamExportFailureAlert(error: unknown): string | null {
  if (isRateLimitError(error)) return null;
  return 'Export failed: backend offline.';
}
