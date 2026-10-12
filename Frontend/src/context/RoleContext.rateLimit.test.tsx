import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RateLimitError, setRateLimitNotifier } from '../lib/rateLimit';
import { RoleProvider, useUserRole } from './RoleContext';

vi.mock('./auth', () => ({
  useAuth: () => ({ currentUser: null }),
}));

function Requester() {
  const { fetchWithRole } = useUserRole();
  const [outcome, setOutcome] = useState('');
  return (
    <>
      <button
        type="button"
        onClick={async () => {
          try {
            const response = await fetchWithRole('/api/settings/system-errors');
            setOutcome(`status ${response.status}`);
          } catch (error) {
            setOutcome(error instanceof RateLimitError ? `rate limited ${error.retryAfterSeconds}` : 'other error');
          }
        }}
      >
        Request
      </button>
      <p data-testid="outcome">{outcome}</p>
    </>
  );
}

function renderRequester() {
  render(<RoleProvider><Requester /></RoleProvider>);
  fireEvent.click(screen.getByRole('button', { name: 'Request' }));
}

describe('fetchWithRole rate limiting', () => {
  let notifier: ReturnType<typeof vi.fn<(message: string) => void>>;
  // Each case starts an hour later, so a notice window from an earlier case has expired.
  let clock = Date.parse('2030-05-01T09:00:00Z');

  beforeEach(() => {
    clock += 3_600_000;
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(clock);
    notifier = vi.fn<(message: string) => void>();
    setRateLimitNotifier(notifier);
  });

  afterEach(() => {
    setRateLimitNotifier(null);
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('turns a 429 into a typed error and shows the single notice', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 429, headers: { 'Retry-After': '17' } })));
    renderRequester();
    await waitFor(() => expect(screen.getByTestId('outcome')).toHaveTextContent('rate limited 17'));
    expect(notifier).toHaveBeenCalledWith('Too many requests. Try again in 17 seconds.');
  });

  it('returns other responses unchanged, so each caller keeps its own error handling', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 500 })));
    renderRequester();
    await waitFor(() => expect(screen.getByTestId('outcome')).toHaveTextContent('status 500'));
    expect(notifier).not.toHaveBeenCalled();
  });

  it('is safe to call again after a rate limit', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 429, headers: { 'Retry-After': '5' } })));
    renderRequester();
    await waitFor(() => expect(screen.getByTestId('outcome')).toHaveTextContent('rate limited 5'));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Request' }));
    });
    await waitFor(() => expect(screen.getByTestId('outcome')).toHaveTextContent('rate limited 5'));
    expect(notifier).toHaveBeenCalledTimes(1);
  });
});
