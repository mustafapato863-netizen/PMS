import type { ReactNode } from 'react';
import { ArrowDownRight, ArrowUpRight } from 'lucide-react';
import { readKpiTrend, selectableKpiCardClass, type KpiBetterDirection } from './selectableKpiCardUtils';

export type KpiSelectionStatus = 'On Target' | 'Needs Attention' | 'Below Target';

export function KpiTrendMovement({
  label,
  betterDirection,
}: {
  label: string;
  betterDirection: KpiBetterDirection;
}) {
  const trend = readKpiTrend(label, betterDirection);
  const tone =
    trend.favorable === true
      ? 'text-emerald-700'
      : trend.favorable === false
      ? 'text-rose-700'
      : 'text-slate-500';

  return (
    <span className={`inline-flex shrink-0 items-center gap-0.5 font-medium tabular-nums ${tone}`}>
      {trend.direction === 'up' ? <ArrowUpRight className="size-3.5 shrink-0" aria-hidden /> : null}
      {trend.direction === 'down' ? <ArrowDownRight className="size-3.5 shrink-0" aria-hidden /> : null}
      {trend.text}
    </span>
  );
}

const TONE: Record<KpiSelectionStatus, { pill: string; value: string; bar: string; gap: string }> = {
  'Below Target': {
    pill: 'bg-rose-50 text-rose-700',
    value: 'text-rose-700',
    bar: 'bg-rose-500',
    gap: 'text-rose-700',
  },
  'Needs Attention': {
    pill: 'bg-amber-50 text-amber-800',
    value: 'text-slate-950',
    bar: 'bg-amber-500',
    gap: 'text-amber-800',
  },
  'On Target': {
    pill: 'bg-emerald-50 text-emerald-700',
    value: 'text-slate-950',
    bar: 'bg-emerald-500',
    gap: 'text-emerald-700',
  },
};

export function SelectableKpiCard({
  selected,
  status,
  title,
  titleTooltip,
  betterDirection,
  actual,
  target,
  achievementPct,
  gapLabel,
  movement,
  biggestGap = false,
  biggestGapTestId,
  weightPct,
  contributionPct,
  pointsLost,
  testId,
  onSelect,
  asTab = false,
  accessory,
  children,
}: {
  selected: boolean;
  status: KpiSelectionStatus;
  title: string;
  titleTooltip?: string;
  betterDirection: KpiBetterDirection;
  actual: string;
  target: string;
  achievementPct: number;
  gapLabel?: string | null;
  movement?: ReactNode;
  biggestGap?: boolean;
  biggestGapTestId?: string;
  weightPct: number;
  contributionPct: number;
  pointsLost: number;
  testId?: string;
  onSelect?: () => void;
  asTab?: boolean;
  accessory?: ReactNode;
  children?: ReactNode;
}) {
  const tone = TONE[status];
  const cappedPct = Math.min(100, Math.max(0, Number.isFinite(achievementPct) ? achievementPct : 0));
  const interactive = Boolean(onSelect) && !accessory && !children;
  const className = selectableKpiCardClass(selected);

  const body = (
    <>
      {selected && <span className={`absolute inset-x-0 top-0 h-1 ${tone.bar}`} aria-hidden />}

      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold text-slate-950" title={titleTooltip || title}>
            {title}
          </p>
          <p className="mt-0.5 text-[11px] text-slate-500">
            {betterDirection === 'lower' ? 'Lower is better' : 'Higher is better'}
          </p>
        </div>
        <span className={`shrink-0 rounded-md px-2 py-1 text-[11px] font-semibold ${tone.pill}`}>{status}</span>
      </div>

      <p className={`mt-3 text-[28px] leading-none font-semibold tracking-tight tabular-nums ${tone.value}`}>
        {actual}
      </p>
      <p className="mt-1.5 text-[12px] text-slate-500">
        Target <span className="font-medium text-slate-800 tabular-nums">{target}</span>
      </p>

      <div className="mt-3 flex items-center gap-2">
        <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-100">
          <div className={`h-full rounded-full ${tone.bar}`} style={{ width: `${cappedPct}%` }} />
        </div>
        <span className="shrink-0 text-[11px] font-medium text-slate-600 tabular-nums">
          {cappedPct.toFixed(1)}% of target
        </span>
      </div>

      {(gapLabel || movement) && (
        <div className="mt-2 flex items-center justify-between gap-2 text-[12px]">
          {gapLabel ? <span className={`truncate font-medium ${tone.gap}`}>{gapLabel}</span> : <span />}
          {movement}
        </div>
      )}

      {biggestGap && pointsLost > 0 && (
        <p data-testid={biggestGapTestId} className="mt-2 text-[11px] font-medium text-rose-700">
          Biggest Gap
        </p>
      )}
    </>
  );

  const footer = (
    <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-slate-100 pt-3">
      <div>
        <dt className="text-[10px] font-medium tracking-wide text-slate-400 uppercase">Weight</dt>
        <dd className="mt-0.5 text-[13px] font-semibold text-slate-900 tabular-nums">{Math.round(weightPct)}%</dd>
      </div>
      <div>
        <dt className="text-[10px] font-medium tracking-wide text-slate-400 uppercase">Contribution</dt>
        <dd className="mt-0.5 text-[13px] font-semibold text-slate-900 tabular-nums">
          {contributionPct.toFixed(1)}%
        </dd>
      </div>
      <div>
        <dt className="text-[10px] font-medium tracking-wide text-slate-400 uppercase">Score gap</dt>
        <dd className={`mt-0.5 text-[13px] font-semibold tabular-nums ${pointsLost > 0 ? tone.gap : 'text-emerald-700'}`}>
          {pointsLost > 0 ? `−${pointsLost.toFixed(1)} pts` : 'Full pts'}
        </dd>
      </div>
    </dl>
  );

  if (interactive) {
    return (
      <button
        type="button"
        role={asTab ? 'tab' : undefined}
        aria-selected={asTab ? selected : undefined}
        data-testid={testId}
        data-selected={selected ? 'true' : 'false'}
        onClick={onSelect}
        className={className}
      >
        {body}
        {footer}
      </button>
    );
  }

  return (
    <article data-testid={testId} data-selected={selected ? 'true' : 'false'} className={className}>
      <button
        type="button"
        aria-pressed={selected}
        onClick={onSelect}
        className="w-full text-left"
      >
        {body}
      </button>
      {accessory}
      {children}
      {footer}
    </article>
  );
}
