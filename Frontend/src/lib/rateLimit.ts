/**
 * HTTP 429 handling shared by every request layer (fetchWithRole and apiFetch).
 *
 * A rate-limited response becomes a typed RateLimitError. TanStack Query does not retry it,
 * and one notice is shown per retry window, so repeated 429s never stack toasts.
 */

export const RATE_LIMIT_STATUS = 429;

/** Used when the server sends no usable Retry-After. */
const FALLBACK_RETRY_SECONDS = 60;

export function rateLimitMessage(seconds: number): string {
  return `Too many requests. Try again in ${seconds} ${seconds === 1 ? 'second' : 'seconds'}.`;
}

export class RateLimitError extends Error {
  readonly status = RATE_LIMIT_STATUS;
  readonly retryAfterSeconds: number;

  constructor(retryAfterSeconds: number) {
    super(rateLimitMessage(retryAfterSeconds));
    this.name = 'RateLimitError';
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export function isRateLimitError(error: unknown): error is RateLimitError {
  return error instanceof RateLimitError;
}

/** Whole seconds from Retry-After, at least 1. A missing, date-form or unreadable value uses the fallback. */
export function retryAfterSeconds(response: Response): number {
  const value = Number(response.headers.get('Retry-After'));
  return Number.isFinite(value) && value >= 1 ? Math.ceil(value) : FALLBACK_RETRY_SECONDS;
}

/**
 * Turn a 429 response into the error to throw. With `notify`, the single notice is shown too.
 * Callers that show their own message (the login form) pass `notify: false`.
 */
export function rejectRateLimited(response: Response, { notify }: { notify: boolean }): RateLimitError {
  const error = new RateLimitError(retryAfterSeconds(response));
  if (notify) notifyRateLimited(error.retryAfterSeconds);
  return error;
}

type RateLimitNotifier = (message: string) => void;

let notifier: RateLimitNotifier | null = null;
let quietUntil = 0;

/** ToastProvider registers its toast here while mounted. Passing null unregisters. */
export function setRateLimitNotifier(next: RateLimitNotifier | null): void {
  notifier = next;
}

/**
 * Shows one notice for the whole retry window. Repeated 429s inside it are silent.
 * With no notifier registered nothing is shown, and the window is not started.
 */
export function notifyRateLimited(seconds: number, now: number = Date.now()): void {
  if (!notifier || now < quietUntil) return;
  quietUntil = now + seconds * 1000;
  notifier(rateLimitMessage(seconds));
}
