import { createContext, useContext } from 'react';

export interface AiAvailability {
  enabled: boolean;
  /** Separate default-off pilot switch for contextual corrective-action suggestions. */
  correctiveActionPilotEnabled: boolean;
  ready: boolean;
  saving: boolean;
  error: string | null;
  setEnabled: (enabled: boolean) => Promise<void>;
  setCorrectiveActionPilotEnabled: (enabled: boolean) => Promise<void>;
}

export const AiAvailabilityContext = createContext<AiAvailability>({
  enabled: true,
  correctiveActionPilotEnabled: false,
  ready: true,
  saving: false,
  error: null,
  setEnabled: async () => {},
  setCorrectiveActionPilotEnabled: async () => {},
});

export function useAiAvailability(): AiAvailability {
  return useContext(AiAvailabilityContext);
}
