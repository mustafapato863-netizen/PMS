import type { InsightTrackingIndicator, InsightTrackingTrendPoint } from '../../features/insights/types';
import { percentPointsFromRatio } from '../../utils/percentForm';

const TAG_TEXT = 'Tracking only';

/** Two decimals below 10% (6.56%), one decimal from 10% (14.3%). Neutral: no target and no good or bad direction. */
const formatShare = (ratio: number | null): string => {
  if (ratio === null) return '—';
  const percent = ratio * 100;
  return `${Math.abs(percent) < 10 ? percent.toFixed(2) : percent.toFixed(1)}%`;
};

/** A change in percentage points with a sign: "+3.90 pts", "−0.28 pts". The sign is text, never a colour. */
const formatPoints = (points: number): string => {
  const sign = points > 0 ? '+' : points < 0 ? '−' : '';
  const magnitude = Math.abs(points);
  return `${sign}${magnitude < 10 ? magnitude.toFixed(2) : magnitude.toFixed(1)} pts`;
};

const formatCount = (value: number): string => (Number.isInteger(value) ? value.toLocaleString() : value.toFixed(1));

const shortMonth = (month: string): string => month.slice(0, 3);

/** A thin proportion bar. Neutral grey on the sunken track, whatever the value. */
function ProportionTile({ label, value, detail, ratio }: { label: string; value: string; detail?: string; ratio: number }) {
  const width = Math.min(Math.max(ratio * 100, 0), 100);
  return (
    <div className="min-w-0 rounded-[10px] border border-[var(--border-light)] bg-[var(--bg-surface)] p-3">
      <p className="text-xs font-semibold text-[var(--text-secondary)]">{label}</p>
      <p className="mt-1 text-sm font-bold tabular-nums text-[var(--text-primary)]">{value}</p>
      {detail && <p className="text-xs text-[var(--text-muted)]">{detail}</p>}
      <div aria-hidden="true" className="mt-2 h-[4px] overflow-hidden rounded-full bg-[var(--bg-sunken)]">
        <div className="h-full rounded-full bg-[var(--text-muted)]" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

/**
 * One column per effective month, oldest first. Each column shows its month and value as text;
 * the bar height is relative to the highest month. The current month is emphasised.
 */
function MonthlyTrend({ trend, label, currentKey }: { trend: InsightTrackingTrendPoint[]; label: string; currentKey: string }) {
  const measured = trend.filter((point): point is InsightTrackingTrendPoint & { value: number } => point.value !== null);
  if (measured.length === 0) return null;
  const highest = Math.max(...measured.map((point) => point.value), 0);
  const description = measured.map((point) => `${shortMonth(point.period.month)} ${formatShare(point.value)}`).join(', ');
  return (
    <ol aria-label={`${label} monthly trend: ${description}`} className="flex min-w-0 items-end gap-2">
      {trend.map((point) => {
        const current = point.period.key === currentKey;
        const measuredValue = point.value;
        return (
          <li key={point.period.key} className="flex min-w-0 flex-1 flex-col items-center gap-1" title={measuredValue === null ? `${point.period.month}: no data` : `${point.period.month} ${formatShare(measuredValue)}`}>
            <span className={`text-xs tabular-nums ${current ? 'font-bold text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'}`}>
              {measuredValue === null ? '—' : formatShare(measuredValue)}
            </span>
            <span aria-hidden="true" className="flex h-[56px] w-full items-end justify-center">
              <span
                className={`block w-full max-w-[28px] rounded-t-[4px] ${current ? 'bg-[var(--text-primary)]' : 'bg-[var(--text-muted)]/45'}`}
                style={{ height: measuredValue === null || highest === 0 ? '0px' : `${Math.max((measuredValue / highest) * 100, 6)}%` }}
              />
            </span>
            <span className={`text-xs ${current ? 'font-bold text-[var(--text-primary)]' : 'text-[var(--text-muted)]'}`}>{shortMonth(point.period.month)}</span>
          </li>
        );
      })}
    </ol>
  );
}

function TrackingIndicatorItem({ indicator, wide }: { indicator: InsightTrackingIndicator; wide: boolean }) {
  const hasCounts = indicator.denominator > 0;
  const hasShare = indicator.policy_share !== null && indicator.share_denominator !== null;
  const previousMonth = indicator.previous_period?.month;
  const change = indicator.change !== null && indicator.previous_value !== null
    ? `${formatPoints(percentPointsFromRatio(indicator.change))} vs ${previousMonth ? shortMonth(previousMonth) : 'the previous month'}`
    : null;

  return (
    <article className="min-w-0 rounded-[12px] border border-[var(--border-light)] bg-[var(--bg-sunken)]/35 p-4">
      <div className="flex min-w-0 items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-extrabold text-[var(--text-primary)]">{indicator.label}</h3>
          <p className="text-xs text-[var(--text-muted)]">{indicator.team} · {indicator.period.month} {indicator.period.year}</p>
        </div>
        <span className="shrink-0 text-xs leading-normal text-[var(--text-muted)]">{TAG_TEXT}</span>
      </div>

      <div className={`mt-4 grid min-w-0 gap-4 ${wide ? 'lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)_minmax(0,1.4fr)]' : ''}`}>
        <div className="flex min-w-0 flex-col items-start gap-2">
          <p className="text-[28px] font-extrabold leading-none tabular-nums text-[var(--text-primary)]">{formatShare(indicator.value)}</p>
          {change
            ? <span className="rounded-full bg-[var(--bg-surface)] px-2 py-0.5 text-xs font-semibold tabular-nums text-[var(--text-secondary)]">{change}</span>
            : <span className="text-xs text-[var(--text-muted)]">No earlier month in this scope</span>}
        </div>

        <div className="grid min-w-0 gap-2">
          {hasCounts && (
            <ProportionTile
              label="Policy rejections"
              value={`${formatCount(indicator.numerator)} of ${formatCount(indicator.denominator)} ${indicator.denominator_label ?? 'requests'}`}
              ratio={indicator.value ?? 0}
            />
          )}
          {hasShare && (
            <ProportionTile
              label="Policy share of rejections"
              value={formatShare(indicator.policy_share ?? 0)}
              detail={`${formatCount(indicator.numerator)} of ${formatCount(indicator.share_denominator ?? 0)} ${indicator.share_denominator_label ?? 'rejections'}`}
              ratio={indicator.policy_share ?? 0}
            />
          )}
        </div>

        <div className="min-w-0">
          <MonthlyTrend trend={indicator.trend} label={indicator.label} currentKey={indicator.period.key} />
        </div>
      </div>
    </article>
  );
}

/**
 * Tracking-only indicators from the team configuration. Shown for information
 * only: no target, achievement, grade or status, and never counted as on track
 * or at risk. Renders nothing when the scope has no indicator.
 */
export default function TrackingIndicatorsCard({ indicators }: { indicators: InsightTrackingIndicator[] }) {
  if (indicators.length === 0) return null;
  const wide = indicators.length === 1;
  return (
    <section
      aria-labelledby="tracking-indicators-title"
      className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5 shadow-sm"
    >
      <h2 id="tracking-indicators-title" className="text-base font-extrabold text-[var(--text-primary)]">Tracking indicators</h2>
      <p className="mt-1 text-xs text-[var(--text-muted)]">Measured for information, not in the score. They do not change the score or any on-track count.</p>
      <div className={`mt-4 grid min-w-0 gap-3 ${wide ? '' : 'md:grid-cols-2'}`}>
        {indicators.map((indicator) => (
          <TrackingIndicatorItem key={`${indicator.team}-${indicator.key}`} indicator={indicator} wide={wide} />
        ))}
      </div>
    </section>
  );
}
