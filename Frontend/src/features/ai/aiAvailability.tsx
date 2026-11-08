import { useEffect, useState, type ReactNode } from 'react';
import { useAuth } from '../../context/auth';
import { apiFetch } from '../../lib/apiClient';
import { AiAvailabilityContext } from './aiAvailabilityContext';

type AiSettingResponse = { success: boolean; data?: { enabled?: boolean } };

export function AiAvailabilityProvider({ children }: { children: ReactNode }) {
  const { currentUser } = useAuth();
  const userId = currentUser?.id;
  return <AiAvailabilitySession key={userId ?? 'anonymous'} userId={userId}>{children}</AiAvailabilitySession>;
}

function AiAvailabilitySession({ userId, children }: { userId: string | undefined; children: ReactNode }) {
  const [enabled, setEnabledState] = useState(false);
  const [ready, setReady] = useState(!userId);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) return;
    let active = true;
    apiFetch<AiSettingResponse>('/api/settings/ai-assistant')
      .then((response) => {
        if (active) setEnabledState(response.data?.enabled === true);
      })
      .catch(() => {
        if (active) setEnabledState(false);
      })
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
    };
  }, [userId]);

  const setEnabled = async (next: boolean) => {
    setSaving(true);
    setError(null);
    try {
      const response = await apiFetch<AiSettingResponse>('/api/settings/ai-assistant', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: next }),
      });
      setEnabledState(response.data?.enabled === true);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not update PMS AI';
      setError(message);
      throw err;
    } finally {
      setSaving(false);
    }
  };

  return (
    <AiAvailabilityContext.Provider value={{ enabled, ready, saving, error, setEnabled }}>
      {children}
    </AiAvailabilityContext.Provider>
  );
}
