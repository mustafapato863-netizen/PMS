import { useId } from 'react';
import type { ExecutiveTrendPoint } from '../../../features/executive/types';
import { fmtScore, shortMonth } from '../../../features/executive/format';
import { useElementWidth } from './execModel';

const HEIGHT = 170;
const AXIS_W = 32;

function axisRange(values: number[], target: number): [number, number] {
  if (!values.length) return [75, 100];
  const min = Math.min(...values, target);
  const max = Math.max(...values, target);
  const low = Math.max(0, Math.floor((min - 3) / 5) * 5);
  const high = Math.min(Math.max(100, Math.ceil(max / 5) * 5), 150);
  return [Math.min(low, high - 10), high];
}

/** Company / team score over the trailing months: actual, optional comparison, dashed target. */
export default function ScoreTrendChart({ points, comparisonLabel, title }: { points: ExecutiveTrendPoint[]; comparisonLabel?: string | null; title: string }) {
  const [ref, measured] = useElementWidth<HTMLDivElement>(510);
  const gradientId = useId().replace(/:/g, '');
  const width = Math.max(measured - AXIS_W, 160);
  const target = points[0]?.target ?? 100;
  const actual = points.map((point) => point.score);
  const comparison = points.map((point) => point.comparison_score);
  const hasComparison = comparison.some((value) => value !== null);
  const values = [...actual, ...comparison].filter((value): value is number => value !== null);
  const [low, high] = axisRange(values, target);
  const ticks = Array.from({ length: Math.round((high - low) / 5) + 1 }, (_, index) => high - index * 5);
  const step = points.length > 1 ? width / (points.length - 1) : width;
  const x = (index: number) => (points.length > 1 ? index * step : width / 2);
  const y = (value: number) => 6 + (HEIGHT - 12) * (1 - (value - low) / (high - low));
  const line = (series: Array<number | null>) => series
    .map((value, index) => (value === null ? null : `${x(index).toFixed(1)},${y(value).toFixed(1)}`))
    .filter(Boolean)
    .map((point, index) => `${index ? 'L' : 'M'}${point}`)
    .join(' ');
  const actualPath = line(actual);
  const firstIdx = actual.findIndex((value) => value !== null);
  const lastIdx = actual.length - 1 - [...actual].reverse().findIndex((value) => value !== null);
  const area = actualPath && firstIdx >= 0 ? `${actualPath} L${x(lastIdx).toFixed(1)},${HEIGHT} L${x(firstIdx).toFixed(1)},${HEIGHT} Z` : '';
  const range = points.length ? `${shortMonth(points[0].period)} – ${shortMonth(points[points.length - 1].period)} ${points[points.length - 1].period.year}` : '';
  const summary = points.map((point) => `${shortMonth(point.period)} ${fmtScore(point.score)}`).join(', ');

  return (
    <div className="flex min-w-0 flex-col gap-[10px] rounded-[12px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-[16px]">
      <div className="flex items-center justify-between gap-[8px]">
        <h3 className="text-[13px] font-semibold text-[var(--insights-heading)]">{title}</h3>
        {range && <span className="rounded-[6px] bg-[var(--exec-chip-bg)] px-[8px] py-[3px] text-[11px] font-medium text-[var(--exec-chip-text)]">{range}</span>}
      </div>
      <div className="flex gap-0">
        <div aria-hidden="true" className="relative shrink-0" style={{ width: AXIS_W, height: HEIGHT }}>
          {ticks.map((tick) => (
            <span key={tick} className="absolute left-0 -translate-y-1/2 text-[10px] text-[var(--text-muted)]" style={{ top: y(tick) }}>{tick}</span>
          ))}
        </div>
        <div ref={ref} className="min-w-0 flex-1">
          <svg role="img" aria-label={`${title}: ${summary}`} width="100%" height={HEIGHT} viewBox={`0 0 ${width} ${HEIGHT}`} className="block overflow-visible">
            <defs>
              <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="var(--insights-accent)" stopOpacity="0.22" />
                <stop offset="100%" stopColor="var(--insights-accent)" stopOpacity="0.02" />
              </linearGradient>
            </defs>
            {ticks.map((tick) => (
              <line key={tick} x1={0} x2={width} y1={y(tick)} y2={y(tick)} stroke="var(--insights-row-border)" strokeWidth={1} />
            ))}
            <line x1={0} x2={width} y1={y(target)} y2={y(target)} stroke="var(--text-muted)" strokeWidth={1.25} strokeDasharray="5 4" data-series="target" />
            {area && <path d={area} fill={`url(#${gradientId})`} />}
            {hasComparison && <path d={line(comparison)} fill="none" stroke="var(--exec-comparison-line)" strokeWidth={1.75} strokeDasharray="2 3" data-series="comparison" />}
            {actualPath && <path d={actualPath} fill="none" stroke="var(--insights-accent)" strokeWidth={2.25} strokeLinejoin="round" data-series="actual" />}
            {actual.map((value, index) => (value === null ? null : (
              <circle key={index} cx={x(index)} cy={y(value)} r={index === lastIdx ? 4 : 3} fill={index === lastIdx ? 'var(--insights-accent)' : 'var(--bg-surface)'} stroke="var(--insights-accent)" strokeWidth={1.75} />
            )))}
          </svg>
          <div aria-hidden="true" className="relative mt-[6px] h-[14px]">
            {points.map((point, index) => (
              <span key={point.period.key} className="absolute -translate-x-1/2 text-[10px] text-[var(--text-muted)]" style={{ left: `${(x(index) / width) * 100}%` }}>{shortMonth(point.period)}</span>
            ))}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-[14px] text-[11px] text-[var(--text-secondary)]">
        <span className="inline-flex items-center gap-[6px]"><span className="size-[8px] rounded-full bg-[var(--insights-accent)]" />Actual</span>
        {hasComparison && comparisonLabel && (
          <span className="inline-flex items-center gap-[6px]"><span className="h-0 w-[14px] border-t-2 border-dotted border-[var(--exec-comparison-line)]" />{comparisonLabel}</span>
        )}
        <span className="inline-flex items-center gap-[6px]"><span className="h-0 w-[14px] border-t border-dashed border-[var(--text-muted)]" />Target {target}%</span>
      </div>
    </div>
  );
}
