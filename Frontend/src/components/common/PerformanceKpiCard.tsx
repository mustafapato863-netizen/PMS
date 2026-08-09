import { useEffect } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Minus, TrendingDown, TrendingUp } from 'lucide-react';

export type PerformanceKpiBadgeType = 'success' | 'warning' | 'danger' | 'neutral';

interface PerformanceKpiCardProps {
  icon: LucideIcon;
  iconBgColor?: string;
  iconAccentColor?: string;
  label: string;
  value: string;
  detailLabel?: string;
  badgeText?: string;
  badgeType?: PerformanceKpiBadgeType;
  trendDelta?: number | null;
  trendUnit?: string;
  isTrendGood?: boolean;
  progressPercent?: number | null;
  contribution?: number | null;
  weight?: number | null;
  targetValue?: string | number | null;
}

const BADGE_CLASSES: Record<PerformanceKpiBadgeType, string> = {
  success: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  warning: 'border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  danger: 'border-rose-500/20 bg-rose-500/10 text-rose-600 dark:text-rose-400',
  neutral: 'border-slate-500/20 bg-slate-500/10 text-slate-600 dark:text-slate-300',
};

const PROGRESS_CLASSES: Record<PerformanceKpiBadgeType, string> = {
  success: 'bg-emerald-500',
  warning: 'bg-amber-500',
  danger: 'bg-rose-500',
  neutral: 'bg-slate-400',
};

function formatTargetBadgeValue(val: string | number): string {
  if (typeof val === 'number') {
    const rounded = Math.round(val);
    if (Math.abs(val - rounded) < 0.05) return `${rounded}`;
    return `${Math.round(val * 10) / 10}`;
  }
  const str = String(val).trim();
  const numMatch = str.match(/^([0-9]+(?:\.[0-9]+)?)\s*(%?)$/);
  if (numMatch) {
    const num = parseFloat(numMatch[1]);
    const unit = numMatch[2];
    const rounded = Math.round(num);
    if (Math.abs(num - rounded) < 0.05) {
      return `${rounded}${unit}`;
    }
    return `${Math.round(num * 10) / 10}${unit}`;
  }
  return str;
}

function formatProgressLabel(progressPercent: number): string {
  if (!Number.isFinite(progressPercent)) {
    return 'Target unavailable';
  }
  if (progressPercent > 200) {
    return '100.0% of target';
  }
  return `${progressPercent.toFixed(1)}% of target`;
}

const PerformanceKpiCard = ({
  icon: Icon,
  iconBgColor = 'bg-indigo-600',
  iconAccentColor,
  label,
  value,
  detailLabel,
  badgeText,
  badgeType = 'neutral',
  trendDelta,
  trendUnit = '%',
  isTrendGood,
  progressPercent,
  contribution,
  weight,
  targetValue,
}: PerformanceKpiCardProps) => {
  useEffect(() => {
    if ((weight === undefined || weight === null) && import.meta.env.DEV) {
      console.warn(`[Missing Weight] KPI "${label}" is missing a weight config.`);
    }
  }, [label, weight]);

  const hasTrend = trendDelta !== undefined && trendDelta !== null && Number.isFinite(trendDelta);
  const stableTrend = hasTrend && trendDelta === 0;
  const trendDown = hasTrend && trendDelta < 0;
  const TrendIcon = stableTrend ? Minus : trendDown ? TrendingDown : TrendingUp;
  const trendIsGood = isTrendGood ?? (!trendDown && !stableTrend);
  const progressAvailable = progressPercent !== undefined
    && progressPercent !== null
    && Number.isFinite(progressPercent);
  const visualProgress = progressAvailable ? Math.min(Math.max(progressPercent, 0), 100) : 0;
  const progressLabel = progressAvailable ? formatProgressLabel(progressPercent) : 'Target unavailable';
  const normalizedWeight = weight !== undefined && weight !== null
    ? (weight > 1 ? weight / 100 : weight)
    : null;
  const contributionPercent = contribution !== undefined && contribution !== null
    ? Math.min(
      Math.max(contribution <= 1 && contribution > 0 ? contribution * 100 : contribution, 0),
      normalizedWeight !== null ? Math.max(normalizedWeight, 0) * 100 : 100,
    )
    : null;
  return (
    <article className="glass-card group relative flex min-h-[190px] flex-col justify-between overflow-hidden rounded-2xl p-4 shadow-sm transition-all hover:scale-[1.01]">
      <div
        className={`pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full opacity-[0.05] transition-opacity duration-500 group-hover:opacity-[0.1] ${iconAccentColor ? '' : iconBgColor}`}
        style={iconAccentColor ? { backgroundColor: iconAccentColor } : undefined}
      />

      <div className="relative flex items-center justify-between gap-2">
        <span
          data-kpi-icon-accent={iconAccentColor || undefined}
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white shadow-sm ${iconAccentColor ? '' : iconBgColor}`}
          style={iconAccentColor ? { backgroundColor: iconAccentColor } : undefined}
        >
          <Icon size={17} />
        </span>
        <div className="flex items-center gap-1.5">
          {targetValue !== undefined && targetValue !== null && targetValue !== '' && (
            <span className="rounded-md border border-slate-500/20 bg-slate-500/10 px-2 py-0.5 text-center text-[9px] font-extrabold text-[var(--text-secondary)]">
              Target: {formatTargetBadgeValue(targetValue)}
            </span>
          )}
          {badgeText && (
            <span className={`max-w-[112px] rounded-md border px-2 py-1 text-center text-[8px] font-extrabold uppercase leading-3 tracking-wide ${BADGE_CLASSES[badgeType]}`}>
              {badgeText}
            </span>
          )}
        </div>
      </div>

      <div className="relative mt-3">
        <p className="truncate text-[9px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]" title={label}>
          {label}
        </p>
        <div className="mt-1 text-[clamp(1.35rem,1.7vw,1.7rem)] font-black leading-none tracking-tight text-[var(--text-primary)]">
          {value}
        </div>
        <div className="mt-1.5 flex min-h-5 items-center justify-between gap-2">
          <p className="min-w-0 truncate text-[10px] font-semibold text-[var(--text-secondary)]">
            {detailLabel}
          </p>
          {hasTrend && (
            <span className={`inline-flex shrink-0 items-center gap-1 text-[9px] font-bold ${
              stableTrend
                ? 'text-[var(--text-muted)]'
                : trendIsGood
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-rose-600 dark:text-rose-500'
            }`}>
              <TrendIcon size={11} />
              <span>{trendDelta > 0 ? '+' : ''}{trendDelta.toFixed(trendUnit === 's' ? 0 : 1)}{trendUnit} MoM</span>
            </span>
          )}
        </div>
      </div>

      <div className="relative mt-2 border-t border-[var(--border-light)] pt-2">
        <div className="flex items-center gap-2">
          <div
            className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--bg-sunken)]"
            role="progressbar"
            aria-label={`${label} progress to target`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressAvailable ? visualProgress : undefined}
            aria-valuetext={progressAvailable ? progressLabel : 'Target progress unavailable'}
          >
            <div
              className={`h-full rounded-full transition-[width] duration-500 ${PROGRESS_CLASSES[badgeType]}`}
              style={{ width: `${visualProgress}%` }}
            />
          </div>
          <span className="min-w-[74px] text-right text-[8px] font-bold text-[var(--text-muted)]">
            {progressLabel}
          </span>
        </div>
      </div>

      <div className="relative mt-2 flex items-center justify-between border-t border-[var(--border-light)] pt-2 text-[10px] font-semibold text-[var(--text-secondary)]">
        <span>
          Contribution
          <strong className="ml-1 font-extrabold text-[var(--text-primary)]">
            {contributionPercent !== null
              ? `${contributionPercent.toFixed(1)}%`
              : '—'}
          </strong>
        </span>
        <span>
          Weight
          <strong className="ml-1 font-extrabold text-[var(--text-primary)]">
            {weight !== undefined && weight !== null ? `${(weight * 100).toFixed(0)}%` : '—'}
          </strong>
        </span>
      </div>
    </article>
  );
};

export default PerformanceKpiCard;
