import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CircleAlert, CircleCheck, Info, TriangleAlert, type LucideIcon } from 'lucide-react';
import { AdminNotice } from './AdminNotice';

export type CardTone = 'good' | 'warning' | 'attention' | 'info';

/** `static` is a navigation-only card. `loading`, `error` and `ready` come from that card's own request. */
export type CardStatus = 'static' | 'loading' | 'error' | 'ready';

const TONES: Record<CardTone, { label: string; icon: LucideIcon; className: string }> = {
  good: { label: 'Good', icon: CircleCheck, className: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' },
  warning: { label: 'Warning', icon: TriangleAlert, className: 'border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-300' },
  attention: { label: 'Attention', icon: CircleAlert, className: 'border-red-500/20 bg-red-500/10 text-red-600 dark:text-red-400' },
  info: { label: 'Info', icon: Info, className: 'border-blue-500/25 bg-blue-500/10 text-blue-700 dark:text-blue-300' },
};

/** The tone is always shown as an icon and a word, never as colour alone. */
export function ToneBadge({ tone }: { tone: CardTone }) {
  const { label, icon: Icon, className } = TONES[tone];
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-bold ${className}`}>
      <Icon size={14} aria-hidden="true" />
      {label}
    </span>
  );
}

function CardSkeleton({ title }: { title: string }) {
  return (
    <div role="status" aria-label={`Loading ${title}`} className="space-y-2">
      <div className="h-6 w-2/3 animate-pulse rounded-md bg-[var(--border-light)]/60 motion-reduce:animate-none" />
      <div className="h-3 w-full animate-pulse rounded bg-[var(--border-light)]/60 motion-reduce:animate-none" />
      <div className="h-3 w-4/5 animate-pulse rounded bg-[var(--border-light)]/60 motion-reduce:animate-none" />
    </div>
  );
}

interface OverviewCardProps {
  title: string;
  description: string;
  icon: LucideIcon;
  actionLabel: string;
  to: string;
  status: CardStatus;
  tone?: CardTone;
  onRetry?: () => void;
  children?: ReactNode;
}

export function OverviewCard({ title, description, icon: Icon, actionLabel, to, status, tone, onRetry, children }: OverviewCardProps) {
  return (
    <article aria-busy={status === 'loading'} className="flex h-full min-w-0 flex-col gap-3 rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] p-4">
      <div className="flex min-w-0 items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-3">
          <span className="shrink-0 rounded-xl bg-blue-500/10 p-2 text-blue-600 dark:text-blue-400">
            <Icon size={18} aria-hidden="true" />
          </span>
          <h3 className="min-w-0 text-base font-bold text-[var(--text-primary)]">{title}</h3>
        </div>
        {status === 'ready' && tone && <ToneBadge tone={tone} />}
      </div>
      {status === 'loading' && <CardSkeleton title={title} />}
      {status === 'error' && (
        <AdminNotice tone="error" title="Could not load this area.">
          <button
            type="button"
            aria-label={`Retry ${title}`}
            onClick={onRetry}
            className="mt-2 inline-flex min-h-11 items-center rounded-xl border border-red-500/30 px-3 text-sm font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary)]"
          >
            Retry
          </button>
        </AdminNotice>
      )}
      {status === 'ready' && children}
      <p className="text-sm text-[var(--text-secondary)]">{description}</p>
      <Link
        to={to}
        className="mt-auto inline-flex min-h-11 w-fit items-center gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 text-sm font-bold text-[var(--text-primary)] transition-colors duration-200 hover:border-blue-500/30 hover:text-blue-600 motion-reduce:transition-none dark:hover:text-blue-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary)]"
      >
        {actionLabel}
        <ArrowRight size={16} aria-hidden="true" />
      </Link>
    </article>
  );
}
