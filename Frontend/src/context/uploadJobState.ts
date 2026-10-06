import { createContext, useContext } from 'react';

export interface UploadJobContextValue {
  activeJobId: string | null;
  trackJob: (jobId: string) => void;
}

export const UploadJobContext = createContext<UploadJobContextValue | undefined>(undefined);

export function useUploadJob() {
  const context = useContext(UploadJobContext);
  if (!context) throw new Error('useUploadJob must be used within an UploadJobProvider');
  return context;
}
