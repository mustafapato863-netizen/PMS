import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { useAuth } from '../../context/auth';
import { apiFetch } from '../../lib/apiClient';

type AiSettingResponse = { success: boolean; data?: { enabled?: boolean } };

export interface AiAvailability {
  /** False until an administrator turns PMS AI on. Components rendered outside the provider stay available for their own tests. */
  enabled: boolean;
  ready: boolean;
  saving: boolean;
  error: string | null;
  setEnabled: (enabled: boolean) => Promise<void>;
}

const standalone: AiAvailability = {
  enabled: true,
  ready: true,
  saving: false,
  error: null,
  setEnabled: async () => {},
};

const AiAvailabilityContext = createContext<AiAvailability>(standalone);

export function AiAvailabilityProvider({ children }: { children: ReactNode }) {
  const { currentUser } = useAuth();
  const [enabled, setEnabledState] = useState(false);
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentUser) {
      setEnabledState(false);
      setReady(true);
      return;
    }
    let active = true;
    setReady(false);
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
  }, [currentUser?.id]);

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

export function useAiAvailability(): AiAvailability {
  return useContext(AiAvailabilityContext);
}
