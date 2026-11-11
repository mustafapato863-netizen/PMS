import { useEffect, useState, type ReactNode } from 'react';
import { useAuth } from '../../context/auth';
import { apiFetch } from '../../lib/apiClient';
import { AiAvailabilityContext } from './aiAvailabilityContext';

type AiSettingResponse = {
  success: boolean;
  data?: { enabled?: boolean; corrective_action_pilot_enabled?: boolean };
};

type PilotSettingResponse = {
  success: boolean;
  data?: { corrective_action_pilot_enabled?: boolean };
};

export function AiAvailabilityProvider({ children }: { children: ReactNode }) {
  const { currentUser } = useAuth();
  const userId = currentUser?.id;
  return <AiAvailabilitySession key={userId ?? 'anonymous'} userId={userId}>{children}</AiAvailabilitySession>;
}

function AiAvailabilitySession({ userId, children }: { userId: string | undefined; children: ReactNode }) {
  const [enabled, setEnabledState] = useState(false);
  const [correctiveActionPilotEnabled, setCorrectiveActionPilotEnabledState] = useState(false);
  const [ready, setReady] = useState(!userId);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) return;
    let active = true;
    apiFetch<AiSettingResponse>('/api/settings/ai-assistant')
      .then((response) => {
        if (active) {
          setEnabledState(response.data?.enabled === true);
          setCorrectiveActionPilotEnabledState(response.data?.corrective_action_pilot_enabled === true);
        }
      })
      .catch(() => {
        if (active) {
          setEnabledState(false);
          setCorrectiveActionPilotEnabledState(false);
        }
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
      if (typeof response.data?.corrective_action_pilot_enabled === 'boolean') {
        setCorrectiveActionPilotEnabledState(response.data.corrective_action_pilot_enabled);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not update PMS AI';
      setError(message);
      throw err;
    } finally {
      setSaving(false);
    }
  };

  const setCorrectiveActionPilotEnabled = async (next: boolean) => {
    setSaving(true);
    setError(null);
    try {
      const response = await apiFetch<PilotSettingResponse>('/api/settings/ai-corrective-action-pilot', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: next }),
      });
      setCorrectiveActionPilotEnabledState(response.data?.corrective_action_pilot_enabled === true);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not update the corrective-action pilot';
      setError(message);
      throw err;
    } finally {
      setSaving(false);
    }
  };

  return (
    <AiAvailabilityContext.Provider
      value={{
        enabled,
        correctiveActionPilotEnabled,
        ready,
        saving,
        error,
        setEnabled,
        setCorrectiveActionPilotEnabled,
      }}
    >
      {children}
    </AiAvailabilityContext.Provider>
  );
}
