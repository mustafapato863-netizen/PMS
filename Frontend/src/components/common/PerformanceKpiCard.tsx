import { useEffect } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Minus, TrendingDown, TrendingUp } from 'lucide-react';
import { formatPercentOfTargetLabel } from './performanceKpiProgress';

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
  /** Replaces the default "+1.2% MoM" line, e.g. "−0.94 pts vs Aug". */
  trendText?: string;
  /** Muted line shown when there is no change, so the card keeps its layout. */
  trendEmptyText?: string;
  isTrendGood?: boolean;
  progressPercent?: number | null;
  /** Score points from the caller. 0.7 means 0.7%, including values at or below 1. */
  contribution?: number | null;
  weight?: number | null;
  weightLabel?: string;
  /** Display-only KPI. The card keeps its value and target and shows no weight. */
  viewOnly?: boolean;
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
    // Percentages below 10 keep the decimals the caller formatted ("1.0%", "0.26%").
    if (unit === '%' && num < 10) return str;
    const rounded = Math.round(num);
    if (Math.abs(num - rounded) < 0.05) {
      return `${rounded}${unit}`;
    }
    return `${Math.round(num * 10) / 10}${unit}`;
  }
  return str;
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
  trendText,
  trendEmptyText,
  isTrendGood,
  progressPercent,
  contribution,
  weight,
  weightLabel = 'Weight',
  viewOnly = false,
  targetValue,
}: PerformanceKpiCardProps) => {
  useEffect(() => {
    if (viewOnly || weight === 0) return;
    if ((weight === undefined || weight === null) && import.meta.env.DEV) {
      console.warn(`[Missing Weight] KPI "${label}" is missing a weight config.`);
    }
  }, [label, viewOnly, weight]);

  const hasTrend = trendDelta !== undefined && trendDelta !== null && Number.isFinite(trendDelta);
  const stableTrend = hasTrend && trendDelta === 0;
  const trendDown = hasTrend && trendDelta < 0;
  const TrendIcon = stableTrend ? Minus : trendDown ? TrendingDown : TrendingUp;
  const trendIsGood = isTrendGood ?? (!trendDown && !stableTrend);
  const progressAvailable = progressPercent !== undefined
    && progressPercent !== null
    && Number.isFinite(progressPercent);
  const visualProgress = progressAvailable ? Math.min(Math.max(progressPercent, 0), 100) : 0;
  const progressLabel = progressAvailable ? formatPercentOfTargetLabel(progressPercent) : 'Target unavailable';
  const formattedTarget = targetValue !== undefined && targetValue !== null && targetValue !== ''
    ? formatTargetBadgeValue(targetValue)
    : '';
  const normalizedWeight = weight !== undefined && weight !== null
    ? (weight > 1 ? weight / 100 : weight)
    : null;
  // Callers already pass score points. A value at or below 1 is still points, not a fraction.
  const isViewOnly = viewOnly;
  const contributionPercent = isViewOnly || contribution === undefined || contribution === null
    ? null
    : Math.min(
      Math.max(contribution, 0),
      normalizedWeight !== null ? Math.max(normalizedWeight, 0) * 100 : 100,
    );
  return (
    <article className="glass-card group relative flex flex-col justify-between overflow-hidden rounded-2xl p-4 shadow-sm transition-all hover:scale-[1.01]">
      <div
        className={`pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full opacity-[0.05] transition-opacity duration-500 group-hover:opacity-[0.1] ${iconAccentColor ? '' : iconBgColor}`}
        style={iconAccentColor ? { backgroundColor: iconAccentColor } : undefined}
      />

      <div className="relative flex items-start justify-between gap-2">
        <span
          data-kpi-icon-accent={iconAccentColor || undefined}
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white shadow-sm ${iconAccentColor ? '' : iconBgColor}`}
          style={iconAccentColor ? { backgroundColor: iconAccentColor } : undefined}
        >
          <Icon size={17} />
        </span>
        {badgeText ? (
          <span className={`flex flex-col items-end rounded-md border px-2 py-1 text-right text-xs font-semibold leading-4 ${BADGE_CLASSES[badgeType]}`}>
            <span className="whitespace-nowrap">{badgeText}</span>
            {formattedTarget && (
              <span className="whitespace-nowrap text-[11px] font-medium leading-4 opacity-80">{formattedTarget}</span>
            )}
          </span>
        ) : formattedTarget ? (
          <span className="text-[11px] font-semibold leading-4 text-[var(--text-secondary)]">{formattedTarget}</span>
        ) : null}
      </div>

      <div className="relative mt-3">
        <p className="truncate text-xs font-semibold text-[var(--text-muted)]" title={label}>
          {label}
        </p>
        <div className="mt-1 text-display-card font-bold leading-none tracking-tight text-[var(--text-primary)]">
          {value}
        </div>
        <div className="mt-1.5 flex min-h-5 items-center justify-between gap-2">
          <p className="min-w-0 truncate text-xs font-semibold text-[var(--text-secondary)]">
            {detailLabel}
          </p>
          {hasTrend && (
            <span className={`inline-flex shrink-0 items-center gap-1 text-xs font-semibold ${
              stableTrend
                ? 'text-[var(--text-muted)]'
                : trendIsGood
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-rose-600 dark:text-rose-500'
            }`}>
              <TrendIcon size={11} />
              <span>
                {trendText ?? (
                  <>{trendDelta > 0 ? '+' : ''}{trendDelta.toFixed(trendUnit === 's' ? 0 : 1)}{trendUnit} MoM</>
                )}
              </span>
            </span>
          )}
          {!hasTrend && trendEmptyText && (
            <span className="shrink-0 text-xs font-semibold text-[var(--text-muted)]">{trendEmptyText}</span>
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
          <span className="min-w-[74px] text-right text-xs font-semibold text-[var(--text-muted)]">
            {progressLabel}
          </span>
        </div>
      </div>

      <div className="relative mt-2 flex items-center justify-between border-t border-[var(--border-light)] pt-2 text-xs font-semibold text-[var(--text-secondary)]">
        <span>
          Contribution
          <strong className="ml-1 font-bold text-[var(--text-primary)]">
            {contributionPercent !== null
              ? `${contributionPercent.toFixed(1)}%`
              : '—'}
          </strong>
        </span>
        <span>
          {isViewOnly ? (
            <strong className="font-bold text-[var(--text-primary)]">View</strong>
          ) : (
            <>
              {weightLabel}
              <strong className="ml-1 font-bold text-[var(--text-primary)]">
                {weight !== undefined && weight !== null ? `${(weight * 100).toFixed(0)}%` : '—'}
              </strong>
            </>
          )}
        </span>
      </div>
    </article>
  );
};

export default PerformanceKpiCard;
