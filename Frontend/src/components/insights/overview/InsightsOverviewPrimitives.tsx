import type { ReactNode } from 'react';
import { ArrowRight } from 'lucide-react';
import { getGradeTone } from '../../../constants/grades';

/** White section card used by every overview section (Figma 18:138 / 18:199 …). */
export function SectionCard({
  labelledBy,
  className = '',
  tone = 'default',
  children,
}: {
  labelledBy: string;
  className?: string;
  /** `muted` = the tinted "More analysis" surface (Figma 18:491). */
  tone?: 'default' | 'muted';
  children: ReactNode;
}) {
  const surface = tone === 'muted'
    ? 'border-[var(--insights-muted-surface-border)] bg-[var(--insights-muted-surface)]'
    : 'border-[var(--insights-card-border)] bg-[var(--bg-surface)]';
  return (
    <section
      aria-labelledby={labelledBy}
      className={`flex min-w-0 flex-col rounded-[12px] border px-[24px] ${surface} ${className}`}
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
  subtitleTone = 'muted',
}: {
  id: string;
  icon: ReactNode;
  iconBackground: string;
  title: string;
  subtitle?: ReactNode;
  action?: ReactNode;
  align?: 'start' | 'center';
  /** `subtle` = lighter helper copy used on the optional "More analysis" card (Figma #7B8794). */
  subtitleTone?: 'muted' | 'subtle';
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
        {subtitle && <p className={`truncate text-[13px] font-normal ${subtitleTone === 'subtle' ? 'text-[var(--insights-subtle-text)]' : 'text-[var(--text-muted)]'}`}>{subtitle}</p>}
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
  variant = 'button',
}: {
  label?: string;
  onClick: () => void;
  expanded?: boolean;
  controls?: string;
  /** `button` = tinted "View all drivers" button; `link` = borderless text link (Figma 18:208 / 18:248 / 18:380). */
  variant?: 'button' | 'link';
}) {
  const look = variant === 'link'
    ? 'text-[11px] text-[var(--insights-link)] hover:bg-[var(--insights-link-hover-bg)] hover:underline'
    : 'border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] text-[12px] text-[var(--insights-accent-text)] hover:border-[var(--insights-accent)]';
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={expanded}
      aria-controls={controls}
      data-variant={variant}
      className={`inline-flex h-[32px] shrink-0 items-center gap-[6px] rounded-[8px] pl-[14px] pr-[12px] font-semibold leading-normal transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)] ${look}`}
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
