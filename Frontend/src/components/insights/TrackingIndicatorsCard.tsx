import type { InsightTrackingIndicator, InsightTrackingTrendPoint } from '../../features/insights/types';
import { formatPercentRatio, percentDecimals, percentPointsFromRatio } from '../../utils/percentForm';

const TAG_TEXT = 'Tracking only · not in the score';

const formatCount = (value: number): string => (Number.isInteger(value) ? value.toLocaleString() : value.toFixed(1));

/** A change between two ratios, shown as percentage points with a sign and no colour. */
const formatChange = (change: number): string => {
  const points = percentPointsFromRatio(change);
  const sign = points > 0 ? '+' : points < 0 ? '−' : '';
  return `${sign}${Math.abs(points).toFixed(percentDecimals(points))} pts`;
};

const shortMonth = (month: string): string => month.slice(0, 3);

function TrendSparkline({ trend, label }: { trend: InsightTrackingTrendPoint[]; label: string }) {
  const measured = trend
    .map((point, index) => ({ index, value: point.value }))
    .filter((point): point is { index: number; value: number } => point.value !== null);
  if (measured.length === 0) return null;

  const width = 120;
  const height = 36;
  const pad = 4;
  const values = measured.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (index: number) => (trend.length <= 1 ? width / 2 : pad + (index * (width - 2 * pad)) / (trend.length - 1));
  const y = (value: number) => height - pad - ((value - min) / span) * (height - 2 * pad);
  const description = measured
    .map((point) => `${shortMonth(trend[point.index].period.month)} ${formatPercentRatio(point.value)}`)
    .join(', ');

  return (
    <svg
      role="img"
      aria-label={`${label} monthly trend: ${description}`}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="mt-3 h-9 w-full max-w-[160px]"
    >
      <polyline
        points={measured.map((point) => `${x(point.index)},${y(point.value)}`).join(' ')}
        fill="none"
        stroke="var(--text-muted)"
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
      />
      {measured.map((point) => (
        <circle key={point.index} cx={x(point.index)} cy={y(point.value)} r="2.2" fill="var(--text-muted)" />
      ))}
    </svg>
  );
}

function TrackingIndicatorItem({ indicator }: { indicator: InsightTrackingIndicator }) {
  const countsLine = indicator.denominator > 0
    ? `${formatCount(indicator.numerator)} of ${formatCount(indicator.denominator)} ${indicator.denominator_label ?? 'requests'}`
    : null;
  const shareLine = indicator.policy_share !== null && indicator.share_denominator !== null
    ? `${formatPercentRatio(indicator.policy_share)} of ${formatCount(indicator.share_denominator)} ${indicator.share_denominator_label ?? 'rejections'} are policy`
    : null;
  const previousMonth = indicator.previous_period?.month;
  const changeLine = indicator.change !== null && indicator.previous_value !== null
    ? `${formatChange(indicator.change)} vs ${previousMonth ?? 'the previous month'} (${formatPercentRatio(indicator.previous_value)})`
    : 'No earlier month in this scope';

  return (
    <article className="min-w-0 rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/35 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-extrabold text-[var(--text-primary)]">{indicator.label}</h3>
          <p className="text-xs text-[var(--text-muted)]">{indicator.team} · {indicator.period.month} {indicator.period.year}</p>
        </div>
        <span className="rounded-full border border-[var(--border-light)] px-2 py-0.5 text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]">
          {TAG_TEXT}
        </span>
      </div>
      <p className="mt-3 text-2xl font-extrabold tabular-nums text-[var(--text-primary)]">{formatPercentRatio(indicator.value)}</p>
      {countsLine && <p className="mt-1 text-xs text-[var(--text-secondary)]">{countsLine}</p>}
      {shareLine && <p className="text-xs text-[var(--text-secondary)]">{shareLine}</p>}
      <p className="mt-1 text-xs text-[var(--text-secondary)]">{changeLine}</p>
      <TrendSparkline trend={indicator.trend} label={indicator.label} />
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
  return (
    <section
      aria-labelledby="tracking-indicators-title"
      className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5 shadow-sm"
    >
      <h2 id="tracking-indicators-title" className="text-base font-extrabold text-[var(--text-primary)]">Tracking indicators</h2>
      <p className="mt-1 text-xs text-[var(--text-muted)]">Measured for information. They do not change the score or any on-track count.</p>
      <div className="mt-4 grid min-w-0 gap-3 md:grid-cols-2">
        {indicators.map((indicator) => (
          <TrackingIndicatorItem key={`${indicator.team}-${indicator.key}`} indicator={indicator} />
        ))}
      </div>
    </section>
  );
}
