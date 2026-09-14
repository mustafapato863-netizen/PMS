import { useContext } from 'react';
import { ToastContext, type ToastContextValue } from '../components/common/ToastProvider';

/**
 * Hook to access the global toast notification system.
 *
 * @example
 * ```tsx
 * const { toast } = useToast();
 * toast.success('Changes saved');
 * toast.error('Upload failed');
 * toast.warning('Approaching storage limit');
 * toast.info('New data available');
 * ```
 */
export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within a <ToastProvider>');
  }
  return ctx;
}
