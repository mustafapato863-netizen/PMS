import type { ReactNode } from 'react';
import { ArrowRight } from 'lucide-react';
import { getGradeTone } from '../../../constants/grades';

/** White section card used by every overview section (Figma 18:138 / 18:199 …). */
export function SectionCard({
  labelledBy,
  className = '',
  children,
}: {
  labelledBy: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      aria-labelledby={labelledBy}
      className={`flex min-w-0 flex-col rounded-[12px] border border-[var(--insights-card-border)] bg-[var(--bg-surface)] px-[24px] ${className}`}
    >
      {children}
    </section>
  );
}

/** 32px coloured icon tile + bold title/subtitle + optional right-aligned action. */
export function SectionHeader({
  id,
  icon,
  iconBackground,
  title,
  subtitle,
  action,
  align = 'start',
}: {
  id: string;
  icon: ReactNode;
  iconBackground: string;
  title: string;
  subtitle?: ReactNode;
  action?: ReactNode;
  align?: 'start' | 'center';
}) {
  return (
    <div className={`flex w-full gap-[12px] ${align === 'center' ? 'items-center' : 'items-start'}`}>
      <span
        aria-hidden="true"
        className="grid size-[32px] shrink-0 place-items-center rounded-[8px] text-white"
        style={{ background: iconBackground }}
      >
        {icon}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-[2px] leading-normal">
        <h2 id={id} className="truncate text-[16px] font-bold text-[var(--insights-heading)]">{title}</h2>
        {subtitle && <p className="truncate text-[13px] font-normal text-[var(--text-muted)]">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function ViewAllButton({
  label = 'View all',
  onClick,
  expanded,
  controls,
}: {
  label?: string;
  onClick: () => void;
  expanded?: boolean;
  controls?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={expanded}
      aria-controls={controls}
      className="inline-flex h-[32px] shrink-0 items-center gap-[6px] rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] pl-[14px] pr-[12px] text-[12px] font-semibold leading-normal text-[var(--insights-accent-text)] transition hover:border-[var(--insights-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)]"
    >
      {label}
      <ArrowRight aria-hidden="true" className="size-[14px]" strokeWidth={1.75} />
    </button>
  );
}

/** "D · Below Average" pill coloured from the A–E grade palette tokens. */
export function GradeBadge({ score }: { score: number | null | undefined }) {
  const tone = getGradeTone(score);
  return (
    <span
      data-grade={tone.grade ?? 'na'}
      className="inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-[8px] py-[3px] text-[11px] font-semibold leading-normal"
      style={{ background: tone.badgeBg, color: tone.badgeText }}
    >
      {tone.grade ? `${tone.grade} · ${tone.label}` : tone.label}
    </span>
  );
}

/** 8px rounded progress bar (Figma "Bar track" / "Bar fill"). */
export function ShareBar({
  percent,
  color,
  track = 'var(--insights-track)',
}: {
  percent: number;
  color: string;
  track?: string;
}) {
  const width = Math.max(0, Math.min(100, percent));
  return (
    <span aria-hidden="true" className="flex h-[8px] min-w-0 flex-1 overflow-hidden rounded-[4px]" style={{ background: track }}>
      <span className="h-[8px] rounded-[4px]" style={{ width: `${width}%`, background: color }} />
    </span>
  );
}
