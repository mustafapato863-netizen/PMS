import type { ReactNode } from 'react';
import { CircleAlert, CircleCheck, Info, TriangleAlert, type LucideIcon } from 'lucide-react';

export type AdminNoticeTone = 'info' | 'success' | 'warning' | 'error';

interface AdminNoticeProps {
  tone?: AdminNoticeTone;
  title?: string;
  children: ReactNode;
}

const TONES: Record<AdminNoticeTone, { icon: LucideIcon; className: string }> = {
  info: { icon: Info, className: 'border-blue-500/25 bg-blue-500/10 text-blue-700 dark:text-blue-300' },
  success: { icon: CircleCheck, className: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' },
  warning: { icon: TriangleAlert, className: 'border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-300' },
  error: { icon: CircleAlert, className: 'border-red-500/20 bg-red-500/10 text-red-600 dark:text-red-400' },
};

/** Errors interrupt (alert); other tones are announced politely (status). */
export function AdminNotice({ tone = 'info', title, children }: AdminNoticeProps) {
  const { icon: Icon, className } = TONES[tone];
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={`flex min-w-0 items-start gap-3 rounded-xl border px-4 py-3 text-sm ${className}`}>
      <Icon size={18} aria-hidden="true" className="mt-0.5 shrink-0" />
      <div className="min-w-0 space-y-1 [overflow-wrap:anywhere]">
        {title && <p className="font-bold">{title}</p>}
        <div>{children}</div>
      </div>
    </div>
  );
}
