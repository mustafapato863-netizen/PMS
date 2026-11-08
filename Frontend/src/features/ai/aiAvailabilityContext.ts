import { createContext, useContext } from 'react';

export interface AiAvailability {
  enabled: boolean;
  ready: boolean;
  saving: boolean;
  error: string | null;
  setEnabled: (enabled: boolean) => Promise<void>;
}

export const AiAvailabilityContext = createContext<AiAvailability>({
  enabled: true,
  ready: true,
  saving: false,
  error: null,
  setEnabled: async () => {},
});

export function useAiAvailability(): AiAvailability {
  return useContext(AiAvailabilityContext);
}
