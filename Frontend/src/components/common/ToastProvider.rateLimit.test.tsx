import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { notifyRateLimited } from '../../lib/rateLimit';
import { ToastProvider } from './ToastProvider';

const MESSAGE = 'Too many requests. Try again in 23 seconds.';

describe('ToastProvider rate-limit notices', () => {
  it('shows one warning with the retry seconds, and repeated 429s inside the window do not stack', () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(Date.parse('2030-03-01T10:00:00Z'));
    try {
      render(<ToastProvider><p>Page</p></ToastProvider>);
      act(() => {
        notifyRateLimited(23);
        notifyRateLimited(23);
        notifyRateLimited(23);
      });
      expect(screen.getAllByText(MESSAGE)).toHaveLength(1);
      expect(screen.getByRole('alert')).toHaveTextContent(MESSAGE);
    } finally {
      vi.useRealTimers();
    }
  });

  it('stops listening once unmounted, so a late 429 cannot reach an unmounted viewport', () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(Date.parse('2030-03-02T10:00:00Z'));
    try {
      const { unmount } = render(<ToastProvider><p>Page</p></ToastProvider>);
      unmount();
      expect(() => act(() => notifyRateLimited(5))).not.toThrow();
    } finally {
      vi.useRealTimers();
    }
  });
});
