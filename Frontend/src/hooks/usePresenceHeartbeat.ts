import { useEffect } from 'react';
import { apiFetch } from '../lib/apiClient';

export const PRESENCE_HEARTBEAT_INTERVAL_MS = 30_000;

export function usePresenceHeartbeat(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;

    let requestInFlight = false;
    const sendHeartbeat = () => {
      if (requestInFlight) return;
      requestInFlight = true;
      void apiFetch('/api/auth/presence/heartbeat', { method: 'POST' })
        .catch(() => undefined)
        .finally(() => {
          requestInFlight = false;
        });
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') sendHeartbeat();
    };

    sendHeartbeat();
    const intervalId = window.setInterval(sendHeartbeat, PRESENCE_HEARTBEAT_INTERVAL_MS);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [enabled]);
}
