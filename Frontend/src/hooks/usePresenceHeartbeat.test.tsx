import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PRESENCE_HEARTBEAT_INTERVAL_MS, usePresenceHeartbeat } from './usePresenceHeartbeat';

const apiMock = vi.hoisted(() => ({
  apiFetch: vi.fn().mockResolvedValue({ success: true }),
}));

vi.mock('../lib/apiClient', () => ({
  apiFetch: apiMock.apiFetch,
}));

describe('usePresenceHeartbeat', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    apiMock.apiFetch.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('sends an immediate authenticated heartbeat and keeps it alive on a timer', async () => {
    const { rerender, unmount } = renderHook(({ enabled }) => usePresenceHeartbeat(enabled), {
      initialProps: { enabled: true },
    });

    expect(apiMock.apiFetch).toHaveBeenCalledTimes(1);
    expect(apiMock.apiFetch).toHaveBeenCalledWith('/api/auth/presence/heartbeat', { method: 'POST' });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(PRESENCE_HEARTBEAT_INTERVAL_MS);
    });
    expect(apiMock.apiFetch).toHaveBeenCalledTimes(2);

    rerender({ enabled: false });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PRESENCE_HEARTBEAT_INTERVAL_MS * 2);
    });
    expect(apiMock.apiFetch).toHaveBeenCalledTimes(2);
    unmount();
  });

  it('refreshes presence when the signed-in tab becomes visible', async () => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    renderHook(() => usePresenceHeartbeat(true));
    expect(apiMock.apiFetch).toHaveBeenCalledTimes(1);

    await act(async () => { await Promise.resolve(); });
    act(() => document.dispatchEvent(new Event('visibilitychange')));

    expect(apiMock.apiFetch).toHaveBeenCalledTimes(2);
  });
});
