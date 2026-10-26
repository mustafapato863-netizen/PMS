import { useId } from 'react';
import type { ExecutiveFunctionCard } from '../../../features/executive/types';
import { fmtScore, shortMonth } from '../../../features/executive/format';
import { smoothPath, splitSeries } from './trendGeometry';

/** Static SVG: no animation, event handlers, tooltips, resize observers, or interactive state. */
export default function FunctionTrendChart({
  points,
  title,
  color,
}: {
  points: ExecutiveFunctionCard['trend'];
  title: string;
  color: string;
}) {
  const gradientId = useId();
  const segments = splitSeries(points.map((point) => point.score));
  const values = segments.flatMap((segment) => segment.map((point) => point.value));
  if (!values.length) {
    return (
      <div
        data-testid="function-trend-empty"
        className="flex min-h-[96px] items-center justify-center rounded-[10px] border border-dashed border-[var(--exec-card-border)] bg-[var(--exec-tile-bg)]/35 p-[10px] text-center text-[11px] text-[var(--text-muted)]"
      >
        No measured score in the last six months.
      </div>
    );
  }

  const minimum = Math.max(0, Math.min(50, Math.floor(Math.min(...values) / 25) * 25));
  const maximum = Math.max(100, Math.ceil(Math.max(...values) / 25) * 25);
  const ticks = [minimum, (minimum + maximum) / 2, maximum];
  const plot = { left: 28, right: 300, top: 24, bottom: 102 };
  const axisFontSize = 10;
  const badgeFontSize = 9.5;
  const x = (index: number) =>
    points.length > 1 ? 46 + index * (238 / (points.length - 1)) : 165;
  const y = (value: number) =>
    plot.bottom -
    ((Math.max(minimum, Math.min(value, maximum)) - minimum) / (maximum - minimum)) *
      (plot.bottom - plot.top);

  const description =
    `${title} trend, last six months: ` +
    points
      .map(
        (point) =>
          `${shortMonth(point.period)} ${
            point.score !== null && Number.isFinite(point.score) ? fmtScore(point.score) : 'no data'
          }`,
      )
      .join(', ');

  return (
    <div className="rounded-[10px] border border-[var(--exec-card-border)] bg-[var(--exec-tile-bg)]/30 px-1.5 py-1">
      <svg
        role="img"
        aria-label={description}
        focusable="false"
        viewBox="0 0 310 122"
        className="mx-auto block h-auto max-h-[96px] w-full max-w-[270px]"
        pointerEvents="none"
        data-testid="function-trend-chart"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.2} />
            <stop offset="100%" stopColor={color} stopOpacity={0.01} />
          </linearGradient>
        </defs>
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={plot.left}
              x2={plot.right}
              y1={y(tick)}
              y2={y(tick)}
              stroke="var(--exec-card-border)"
              strokeDasharray="3 4"
            />
            <text
              x={plot.left - 4}
              y={y(tick)}
              dominantBaseline="middle"
              textAnchor="end"
              fontSize={axisFontSize}
              fill="var(--text-muted)"
              data-testid="function-trend-tick"
            >
              {tick}%
            </text>
          </g>
        ))}
        <line
          x1={plot.left}
          x2={plot.right}
          y1={y(100)}
          y2={y(100)}
          stroke="var(--text-muted)"
          strokeOpacity={0.5}
          strokeDasharray="4 4"
        />
        {segments.map(
          (segment, index) =>
            segment.length > 1 && (
              <g key={index}>
                <path
                  d={
                    smoothPath(segment, x, y) +
                    ` L${x(segment[segment.length - 1].index)} ${plot.bottom} L${x(segment[0].index)} ${plot.bottom} Z`
                  }
                  fill={`url(#${gradientId})`}
                  data-testid="function-trend-area"
                />
                <path
                  d={smoothPath(segment, x, y)}
                  fill="none"
                  stroke={color}
                  strokeWidth={2.25}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  data-testid="function-trend-series"
                />
              </g>
            ),
        )}
        {points.map((point, index) => {
          const isLast = index === points.length - 1;
          const prevScore = index > 0 ? points[index - 1]?.score : null;
          const isCrowded =
            point.score !== null &&
            prevScore !== null &&
            Number.isFinite(prevScore) &&
            Math.abs(point.score - prevScore) < 5 &&
            index % 2 === 1;
          const badgeYOffset = isCrowded ? -24 : -17;

          return (
            <g key={point.period.key}>
              {point.score !== null && Number.isFinite(point.score) && (
                <>
                  {isLast && (
                    <circle
                      cx={x(index)}
                      cy={y(point.score)}
                      r={5.5}
                      fill={color}
                      fillOpacity={0.16}
                    />
                  )}
                  <circle
                    cx={x(index)}
                    cy={y(point.score)}
                    r={isLast ? 3.5 : 2.8}
                    fill={isLast ? color : 'var(--bg-surface)'}
                    stroke={color}
                    strokeWidth={2}
                    data-testid="function-trend-point"
                  />
                  <g data-testid="function-trend-value">
                    <rect
                      x={x(index) - 16.5}
                      y={y(point.score) + badgeYOffset}
                      width={33}
                      height={13.5}
                      rx={4}
                      fill="var(--bg-surface)"
                      stroke={color}
                      strokeOpacity={isLast ? 0.45 : 0.18}
                    />
                    <text
                      x={x(index)}
                      y={y(point.score) + badgeYOffset + 9.5}
                      textAnchor="middle"
                      fontSize={badgeFontSize}
                      fontWeight={isLast ? 800 : 700}
                      fill={color}
                    >
                      {fmtScore(point.score)}
                    </text>
                  </g>
                </>
              )}
              <text
                x={x(index)}
                y={117}
                textAnchor="middle"
                fontSize={axisFontSize}
                fontWeight={isLast ? 700 : 500}
                fill={isLast ? 'var(--insights-heading)' : 'var(--text-muted)'}
              >
                {shortMonth(point.period)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
