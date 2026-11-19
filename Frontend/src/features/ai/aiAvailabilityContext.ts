import { createContext, useContext } from 'react';
import type { AiAccessTier } from '../../types';

export interface AiAvailability {
  enabled: boolean;
  /** Rollout stage controlling which roles can use PMS AI. */
  accessTier: AiAccessTier;
  /** Separate default-off pilot switch for contextual corrective-action suggestions. */
  correctiveActionPilotEnabled: boolean;
  ready: boolean;
  saving: boolean;
  error: string | null;
  setEnabled: (enabled: boolean) => Promise<void>;
  setAccessTier: (tier: AiAccessTier) => Promise<void>;
  setCorrectiveActionPilotEnabled: (enabled: boolean) => Promise<void>;
}

export const AiAvailabilityContext = createContext<AiAvailability>({
  enabled: true,
  accessTier: 'admin_only',
  correctiveActionPilotEnabled: false,
  ready: true,
  saving: false,
  error: null,
  setEnabled: async () => {},
  setAccessTier: async () => {},
  setCorrectiveActionPilotEnabled: async () => {},
});

export function useAiAvailability(): AiAvailability {
  return useContext(AiAvailabilityContext);
}
