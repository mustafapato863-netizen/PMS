import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CircleAlert, CircleCheck, Info, TriangleAlert, type LucideIcon } from 'lucide-react';
import { AdminNotice } from './AdminNotice';

export type CardTone = 'good' | 'warning' | 'attention' | 'info';

/** `static` is a navigation-only card. `loading`, `error` and `ready` come from that card's own request. */
export type CardStatus = 'static' | 'loading' | 'error' | 'ready';

const TONES: Record<
  CardTone,
  { label: string; icon: LucideIcon; background: string; color: string; accent: string }
> = {
  good: {
    label: 'Good',
    icon: CircleCheck,
    background: 'var(--exec-pos-bg)',
    color: 'var(--exec-pos-text)',
    accent: 'linear-gradient(90deg, #10b981 0%, #34d399 100%)',
  },
  warning: {
    label: 'Warning',
    icon: TriangleAlert,
    background: 'var(--exec-warning-bg)',
    color: 'var(--exec-warning-text)',
    accent: 'linear-gradient(90deg, #f59e0b 0%, #fbbf24 100%)',
  },
  attention: {
    label: 'Attention',
    icon: CircleAlert,
    background: 'var(--exec-neg-bg)',
    color: 'var(--exec-neg-text)',
    accent: 'linear-gradient(90deg, #ef4444 0%, #f87171 100%)',
  },
  info: {
    label: 'Info',
    icon: Info,
    background: 'var(--exec-info-bg)',
    color: 'var(--exec-info-text)',
    accent: 'linear-gradient(90deg, #0084ce 0%, #38bdf8 100%)',
  },
};

/** The tone is always shown as an icon and a word, never as colour alone. */
export function ToneBadge({ tone }: { tone: CardTone }) {
  const { label, icon: Icon, background, color } = TONES[tone];
  return (
    <span
      className="inline-flex shrink-0 items-center gap-[5px] rounded-full px-[9px] py-[2.5px] text-xs font-semibold leading-normal shadow-2xs"
      style={{ background, color }}
    >
      <Icon className="size-[11px]" strokeWidth={2.2} aria-hidden="true" />
      {label}
    </span>
  );
}

/** Same action on every card and every attention row. */
export function AdminActionLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="group inline-flex min-h-11 items-center gap-2 rounded-lg px-3 text-[13px] font-semibold text-[var(--insights-accent)] transition-[background-color,box-shadow,transform] duration-200 hover:-translate-y-px hover:bg-[var(--exec-info-bg)] hover:shadow-[0_4px_12px_rgba(0,163,224,0.12)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary)] motion-reduce:transition-none"
    >
      {children}
      <span className="inline-flex size-6 items-center justify-center rounded-full bg-[var(--exec-tile-bg)] transition-colors duration-200 group-hover:bg-[var(--bg-surface)]">
        <ArrowRight
          className="size-[14px] transition-transform duration-200 group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </span>
    </Link>
  );
}

function CardSkeleton({ title }: { title: string }) {
  return (
    <div role="status" aria-label={`Loading ${title}`} className="space-y-2.5 py-1">
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

export function OverviewCard({
  title,
  description,
  icon: Icon,
  actionLabel,
  to,
  status,
  tone,
  onRetry,
  children,
}: OverviewCardProps) {
  const accentBg = status === 'ready' && tone ? TONES[tone].accent : 'transparent';

  return (
    <article
      aria-busy={status === 'loading'}
      className="group/card relative flex h-full w-full min-w-0 flex-col gap-[12px] overflow-hidden rounded-[16px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-[16px] shadow-[var(--exec-card-shadow)] transition-all duration-200 hover:border-[var(--border-medium)]"
    >
      {/* Top Semantic Status Accent Bar */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-[3px] opacity-85"
        style={{ background: accentBg }}
      />

      <div className="flex min-w-0 items-center justify-between gap-[10px]">
        <div className="flex min-w-0 items-center gap-[10px]">
          <span className="flex size-[38px] shrink-0 items-center justify-center rounded-[10px] border border-[var(--border-light)] bg-[var(--exec-tile-bg)] text-[var(--insights-accent)] shadow-2xs">
            <Icon className="size-[18px]" strokeWidth={1.85} aria-hidden="true" />
          </span>
          <h3 className="min-w-0 text-[15px] font-bold leading-[1.3] tracking-[-0.02em] text-[var(--insights-heading)]">
            {title}
          </h3>
        </div>
        {status === 'ready' && tone && <ToneBadge tone={tone} />}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-[8px]">
        {status === 'loading' && <CardSkeleton title={title} />}
        {status === 'error' && (
          <AdminNotice tone="error" title="Could not load this area.">
            <button
              type="button"
              aria-label={`Retry ${title}`}
              onClick={onRetry}
              className="mt-2 inline-flex min-h-11 items-center rounded-[8px] border border-red-500/30 bg-red-500/5 px-3 text-[13px] font-semibold transition-colors hover:bg-red-500/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary)]"
            >
              Retry
            </button>
          </AdminNotice>
        )}
        {status === 'ready' && children}
        <p className="mt-auto pt-1 text-xs leading-[1.5] text-[var(--text-muted)]">{description}</p>
      </div>

      <div className="border-t border-[var(--exec-card-border)] pt-[10px]">
        <AdminActionLink to={to}>{actionLabel}</AdminActionLink>
      </div>
    </article>
  );
}
