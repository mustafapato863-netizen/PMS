import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { apiFetch } from '../lib/apiClient';
import { RateLimitError, setRateLimitNotifier } from '../lib/rateLimit';
import { AuthProvider } from './AuthContext';
import { useAuth } from './auth';

vi.mock('../lib/apiClient', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/apiClient')>();
  return {
    ...actual,
    apiFetch: vi.fn(),
    getAccessToken: () => 'rate-limit-login-test',
    refreshAccessToken: vi.fn(async () => true),
    setAccessToken: vi.fn(),
    terminateClientSession: vi.fn(async () => undefined),
  };
});

function LoginProbe() {
  const { login } = useAuth();
  const [result, setResult] = useState('');
  return (
    <>
      <button type="button" onClick={async () => {
        const outcome = await login('ops-user', 'password');
        setResult(outcome.success ? 'signed in' : outcome.error ?? '');
      }}>
        Sign in
      </button>
      <p data-testid="login-result">{result}</p>
    </>
  );
}

describe('AuthContext login under rate limiting', () => {
  let notifier: ReturnType<typeof vi.fn<(message: string) => void>>;

  beforeEach(() => {
    vi.mocked(apiFetch).mockReset();
    vi.mocked(apiFetch).mockImplementation(async (endpoint: string) => {
      if (endpoint.includes('/auth/login')) throw new RateLimitError(30);
      return { success: false };
    });
    notifier = vi.fn<(message: string) => void>();
    setRateLimitNotifier(notifier);
  });

  it('returns the rate-limit message for the login form to show inline, without the shared notice', async () => {
    render(<AuthProvider><LoginProbe /></AuthProvider>);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    });
    await waitFor(() => {
      expect(screen.getByTestId('login-result')).toHaveTextContent('Too many requests. Try again in 30 seconds.');
    });
    expect(screen.getByTestId('login-result')).not.toHaveTextContent('Failed to connect');
    expect(notifier).not.toHaveBeenCalled();
    setRateLimitNotifier(null);
  });
});
