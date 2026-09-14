/**
 * Global Toast Notification System
 *
 * Provides a context-based toast system with auto-dismiss, stacking,
 * and smooth Framer Motion animations.
 *
 * Usage:
 *   const { toast } = useToast();
 *   toast.success('Report exported successfully');
 *   toast.error('Upload failed — please try again');
 */
import { createContext, useCallback, useState, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from 'lucide-react';

/* ── Types ──────────────────────────────────────────────────── */

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastItem {
  id: string;
  type: ToastType;
  message: string;
  duration: number;
}

export interface ToastActions {
  success: (message: string, duration?: number) => void;
  error: (message: string, duration?: number) => void;
  warning: (message: string, duration?: number) => void;
  info: (message: string, duration?: number) => void;
  dismiss: (id: string) => void;
}

export interface ToastContextValue {
  toast: ToastActions;
}

/* ── Context ────────────────────────────────────────────────── */

export const ToastContext = createContext<ToastContextValue | null>(null);

/* ── Constants ──────────────────────────────────────────────── */

const MAX_TOASTS = 4;
const DEFAULT_DURATION = 4000;

const ICON_MAP: Record<ToastType, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info,
};

const STYLE_MAP: Record<ToastType, string> = {
  success:
    'border-emerald-500/25 bg-emerald-50 text-emerald-800 dark:border-emerald-400/20 dark:bg-emerald-950/80 dark:text-emerald-200',
  error:
    'border-rose-500/25 bg-rose-50 text-rose-800 dark:border-rose-400/20 dark:bg-rose-950/80 dark:text-rose-200',
  warning:
    'border-amber-500/25 bg-amber-50 text-amber-800 dark:border-amber-400/20 dark:bg-amber-950/80 dark:text-amber-200',
  info:
    'border-blue-500/25 bg-blue-50 text-blue-800 dark:border-blue-400/20 dark:bg-blue-950/80 dark:text-blue-200',
};

const ICON_COLOR: Record<ToastType, string> = {
  success: 'text-emerald-600 dark:text-emerald-400',
  error: 'text-rose-600 dark:text-rose-400',
  warning: 'text-amber-600 dark:text-amber-400',
  info: 'text-blue-600 dark:text-blue-400',
};

const PROGRESS_COLOR: Record<ToastType, string> = {
  success: 'bg-emerald-500',
  error: 'bg-rose-500',
  warning: 'bg-amber-500',
  info: 'bg-blue-500',
};

/* ── Single toast item ──────────────────────────────────────── */

function Toast({ item, onDismiss }: { item: ToastItem; onDismiss: (id: string) => void }) {
  const Icon = ICON_MAP[item.type];

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, x: 60, scale: 0.95 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      role="alert"
      aria-live="polite"
      className={`pointer-events-auto relative flex w-[360px] max-w-[calc(100vw-32px)] items-start gap-3 overflow-hidden rounded-2xl border px-4 py-3.5 shadow-lg backdrop-blur-sm ${STYLE_MAP[item.type]}`}
    >
      <Icon size={18} className={`mt-0.5 shrink-0 ${ICON_COLOR[item.type]}`} />
      <p className="flex-1 text-sm font-semibold leading-snug">{item.message}</p>
      <button
        type="button"
        onClick={() => onDismiss(item.id)}
        className="shrink-0 rounded-lg p-1 opacity-60 transition-opacity hover:opacity-100 focus-visible:outline-2 focus-visible:outline-blue-500"
        aria-label="Dismiss notification"
      >
        <X size={14} />
      </button>

      {/* Auto-dismiss progress bar */}
      <motion.div
        className={`absolute inset-x-0 bottom-0 h-[3px] origin-left ${PROGRESS_COLOR[item.type]}`}
        initial={{ scaleX: 1 }}
        animate={{ scaleX: 0 }}
        transition={{ duration: item.duration / 1000, ease: 'linear' }}
      />
    </motion.div>
  );
}

/* ── Provider ───────────────────────────────────────────────── */

let toastCounter = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (type: ToastType, message: string, duration = DEFAULT_DURATION) => {
      const id = `toast-${++toastCounter}`;
      setItems((prev) => [...prev.slice(-(MAX_TOASTS - 1)), { id, type, message, duration }]);

      // Auto-dismiss
      setTimeout(() => dismiss(id), duration);
    },
    [dismiss],
  );

  const toast: ToastActions = {
    success: (msg, dur) => push('success', msg, dur),
    error: (msg, dur) => push('error', msg, dur),
    warning: (msg, dur) => push('warning', msg, dur),
    info: (msg, dur) => push('info', msg, dur),
    dismiss,
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}

      {/* Toast viewport — fixed bottom-right */}
      <div
        aria-label="Notifications"
        className="fixed bottom-4 right-4 z-[9999] flex flex-col-reverse items-end gap-2 pointer-events-none"
      >
        <AnimatePresence mode="popLayout">
          {items.map((item) => (
            <Toast key={item.id} item={item} onDismiss={dismiss} />
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}
