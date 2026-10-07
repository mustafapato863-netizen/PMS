import { useId } from 'react';
import type { ExecutiveFunctionCard } from '../../../features/executive/types';
import { fmtScore, shortMonth } from '../../../features/executive/format';
import { smoothPath, splitSeries } from './trendGeometry';

/** Static SVG: no animation, event handlers, tooltips, resize observers, or interactive state. */
export default function FunctionTrendChart({ points, title, color }: {
  points: ExecutiveFunctionCard['trend'];
  title: string;
  color: string;
}) {
  const gradientId = useId();
  const segments = splitSeries(points.map((point) => point.score));
  const values = segments.flatMap((segment) => segment.map((point) => point.value));
  if (!values.length) return <div data-testid="function-trend-empty" className="flex min-h-[190px] items-center justify-center rounded-[12px] border border-dashed border-[var(--exec-card-border)] p-[16px] text-center text-[12px] text-[var(--text-muted)]">No measured score in the last six months.</div>;
  const minimum = Math.max(0, Math.min(50, Math.floor(Math.min(...values) / 25) * 25));
  const maximum = Math.max(100, Math.ceil(Math.max(...values) / 25) * 25);
  const ticks = [minimum, (minimum + maximum) / 2, maximum];
  const plot = { left: 34, right: 314, top: 38, bottom: 162 };
  const x = (index: number) => points.length > 1 ? 58 + index * (232 / (points.length - 1)) : 174;
  const y = (value: number) => plot.bottom - ((Math.max(minimum, Math.min(value, maximum)) - minimum) / (maximum - minimum)) * (plot.bottom - plot.top);
  const description = `${title} trend, last six months: ` + points.map((point) => `${shortMonth(point.period)} ${point.score !== null && Number.isFinite(point.score) ? fmtScore(point.score) : 'no data'}`).join(', ');
  return (
    <svg role="img" aria-label={description} focusable="false" viewBox="0 0 330 190" className="mx-auto block h-auto w-full max-w-[300px]" pointerEvents="none" data-testid="function-trend-chart">
      <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity={0.2} /><stop offset="100%" stopColor={color} stopOpacity={0.015} /></linearGradient></defs>
      {ticks.map((tick) => <g key={tick}>
        <line x1={plot.left} x2={plot.right} y1={y(tick)} y2={y(tick)} stroke="var(--exec-card-border)" strokeDasharray="3 4" />
        <text x={plot.left - 6} y={y(tick)} dominantBaseline="middle" textAnchor="end" fontSize={10} fill="var(--text-muted)" data-testid="function-trend-tick">{tick}%</text>
      </g>)}
      <line x1={plot.left} x2={plot.right} y1={y(100)} y2={y(100)} stroke="var(--text-muted)" strokeOpacity={0.65} strokeDasharray="4 4" />
      {segments.map((segment, index) => segment.length > 1 && <g key={index}>
        <path d={smoothPath(segment, x, y) + ` L${x(segment[segment.length - 1].index)} ${plot.bottom} L${x(segment[0].index)} ${plot.bottom} Z`} fill={`url(#${gradientId})`} data-testid="function-trend-area" />
        <path d={smoothPath(segment, x, y)} fill="none" stroke={color} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" data-testid="function-trend-series" />
      </g>)}
      {points.map((point, index) => <g key={point.period.key}>
        {point.score !== null && Number.isFinite(point.score) && <>
          <circle cx={x(index)} cy={y(point.score)} r={4} fill="var(--bg-surface)" stroke={color} strokeWidth={2.5} data-testid="function-trend-point" />
          <g data-testid="function-trend-value">
            <rect x={x(index) - 23} y={y(point.score) - 32} width={46} height={23} rx={8} fill="var(--bg-surface)" stroke={color} strokeOpacity={0.16} />
            <text x={x(index)} y={y(point.score) - 17} textAnchor="middle" fontSize={10} fontWeight={700} fill={color}>{fmtScore(point.score)}</text>
          </g>
        </>}
        <text x={x(index)} y={184} textAnchor="middle" fontSize={10} fill="var(--text-muted)">{shortMonth(point.period)}</text>
      </g>)}
    </svg>
  );
}
