import { useId, useMemo, useRef, useState } from 'react';

interface LineChartProps {
  history: Array<{
    month: string;
    year: number;
    score?: number | null;
  }>;
  targetValue?: number | null;
  color?: string;
  height?: number;
  showTarget?: boolean;
}

interface ChartPoint {
  month: string;
  year: number;
  score: number;
  sourceIndex: number;
}

interface ChartTooltipState {
  x: number;
  y: number;
  placement: 'above' | 'below';
  month: string;
  year: number;
  score: number;
  sourceIndex: number;
}

const CHART_WIDTH = 560;
const PAD_LEFT = 40;
const PAD_RIGHT = 16;
const PAD_TOP = 16;
const PAD_BOTTOM = 26;
const TOOLTIP_HALF_WIDTH = 82;

const isValidScore = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

const formatScore = (value: number) =>
  `${value.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  })}%`;

const formatMonthMmm = (month: string, year: number) => {
  const value = month.trim();

  // Supports: "January", "Jan", "2026-01", "01"
  const numericMonth = value.match(/^(?:\d{4}[-/])?(\d{1,2})$/);

  if (numericMonth) {
    const monthNumber = Number(numericMonth[1]);

    if (monthNumber >= 1 && monthNumber <= 12) {
      return new Intl.DateTimeFormat('en-US', {
        month: 'short',
        timeZone: 'UTC',
      }).format(new Date(Date.UTC(year, monthNumber - 1, 1)));
    }
  }

  const parsedDate = new Date(`${value} 1, ${year}`);

  if (!Number.isNaN(parsedDate.getTime())) {
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      timeZone: 'UTC',
    }).format(parsedDate);
  }

  return value.slice(0, 3);
};

const getBezierPath = (
  points: ChartPoint[],
  toX: (index: number) => number,
  toY: (value: number) => number,
) => {
  if (!points.length) return '';

  return points.reduce((path, point, index) => {
    const currentX = toX(point.sourceIndex);
    const currentY = toY(point.score);

    if (index === 0) {
      return `M ${currentX.toFixed(1)},${currentY.toFixed(1)}`;
    }

    const previous = points[index - 1];
    const previousX = toX(previous.sourceIndex);
    const previousY = toY(previous.score);
    const controlOffset = (currentX - previousX) / 3;

    return [
      path,
      `C ${(previousX + controlOffset).toFixed(1)},${previousY.toFixed(1)}`,
      `${(currentX - controlOffset).toFixed(1)},${currentY.toFixed(1)}`,
      `${currentX.toFixed(1)},${currentY.toFixed(1)}`,
    ].join(' ');
  }, '');
};

const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max);

export function LineChart({
  history,
  targetValue,
  color = '#2E6FE0',
  height = 150,
  showTarget = true,
}: LineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const gradientId = useId().replace(/:/g, '');

  const [activeTooltip, setActiveTooltip] =
    useState<ChartTooltipState | null>(null);

  const chartHeight = Math.max(120, height);

  const { measuredPoints, lineSegments } = useMemo(() => {
    const points: ChartPoint[] = [];
    const segments: ChartPoint[][] = [];
    let currentSegment: ChartPoint[] = [];

    history.forEach((item, sourceIndex) => {
      if (isValidScore(item.score)) {
        const point: ChartPoint = {
          month: item.month,
          year: item.year,
          score: item.score,
          sourceIndex,
        };

        points.push(point);
        currentSegment.push(point);
        return;
      }

      // Stop the path at missing-data months.
      // We must not connect a fake trend across missing values.
      if (currentSegment.length > 0) {
        segments.push(currentSegment);
        currentSegment = [];
      }
    });

    if (currentSegment.length > 0) {
      segments.push(currentSegment);
    }

    return {
      measuredPoints: points,
      lineSegments: segments.filter((segment) => segment.length >= 2),
    };
  }, [history]);

  const hasMeasuredData = measuredPoints.length > 0;
  const hasEnoughData = measuredPoints.length >= 2;

  if (!hasMeasuredData) {
    return (
      <div
        className="flex items-center justify-center rounded-xl border border-dashed px-4 text-center"
        style={{
          height: chartHeight,
          borderColor: 'var(--bsc-border)',
          background: 'color-mix(in srgb, var(--bsc-panel-bg-soft) 82%, transparent)',
        }}
        role="status"
      >
        <div className="space-y-1">
          <p className="text-xs font-semibold" style={{ color: 'var(--bsc-panel-text)' }}>
            No History Yet
          </p>
          <p className="text-xs leading-5" style={{ color: 'var(--bsc-panel-muted)' }}>
            Monthly performance will appear after valid records are available.
          </p>
        </div>
      </div>
    );
  }

  if (!hasEnoughData) {
    return (
      <div
        className="flex items-center justify-center rounded-xl border border-dashed px-4 text-center"
        style={{
          height: chartHeight,
          borderColor: 'var(--bsc-border)',
          background: 'color-mix(in srgb, var(--bsc-panel-bg-soft) 82%, transparent)',
        }}
        role="status"
      >
        <div className="space-y-1">
          <p className="text-xs font-semibold" style={{ color: 'var(--bsc-panel-text)' }}>
            Not Enough Data for Trend
          </p>
          <p className="text-xs leading-5" style={{ color: 'var(--bsc-panel-muted)' }}>
            At least two measured monthly records are needed.
          </p>
        </div>
      </div>
    );
  }

  const usableTarget =
    showTarget && isValidScore(targetValue) ? targetValue : null;

  const values = [
    ...measuredPoints.map((point) => point.score),
    ...(usableTarget !== null ? [usableTarget] : []),
  ];

  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const dynamicPadding = Math.max(6, (rawMax - rawMin) * 0.14);

  const minValue = Math.max(0, Math.floor(rawMin - dynamicPadding));
  const maxValue = Math.ceil(
    Math.max(rawMax + dynamicPadding, minValue + 10),
  );

  const range = Math.max(1, maxValue - minValue);
  const innerWidth = CHART_WIDTH - PAD_LEFT - PAD_RIGHT;
  const innerHeight = chartHeight - PAD_TOP - PAD_BOTTOM;
  const xDenominator = Math.max(history.length - 1, 1);

  const toX = (index: number) =>
    PAD_LEFT + (index / xDenominator) * innerWidth;

  const toY = (value: number) =>
    PAD_TOP + innerHeight - ((value - minValue) / range) * innerHeight;

  const targetY = usableTarget !== null ? toY(usableTarget) : null;

  const ticks = Array.from({ length: 4 }, (_, index) => {
    const value = minValue + (range * index) / 3;

    return {
      value,
      y: toY(value),
      label: `${Math.round(value)}%`,
    };
  });

  const labelEvery =
    history.length > 8 ? Math.ceil(history.length / 6) : 1;

  const visibleMonthLabels = history.map((item, index) => ({
    index,
    label: formatMonthMmm(item.month, item.year),
    visible:
      index === 0 ||
      index === history.length - 1 ||
      index % labelEvery === 0,
  }));

  const setTooltipForPoint = (
    point: ChartPoint,
    rawX: number,
    pointY: number,
    containerWidth: number,
  ) => {
    const x = clamp(
      rawX,
      TOOLTIP_HALF_WIDTH + 8,
      containerWidth - TOOLTIP_HALF_WIDTH - 8,
    );

    setActiveTooltip({
      x,
      y: pointY,
      placement: pointY < 62 ? 'below' : 'above',
      month: point.month,
      year: point.year,
      score: point.score,
      sourceIndex: point.sourceIndex,
    });
  };

  const showTooltip = (point: ChartPoint, target: SVGElement) => {
    if (!containerRef.current) return;

    const containerRect = containerRef.current.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const rawX = targetRect.left - containerRect.left + targetRect.width / 2;
    const pointY = targetRect.top - containerRect.top + targetRect.height / 2;

    setTooltipForPoint(point, rawX, pointY, containerRect.width);
  };

  const showTooltipFromBand = (
    point: ChartPoint,
    event: React.MouseEvent<SVGRectElement>,
  ) => {
    if (!containerRef.current) return;

    const containerRect = containerRef.current.getBoundingClientRect();
    const rawX = event.clientX - containerRect.left;
    const pointY = toY(point.score);

    setTooltipForPoint(point, rawX, pointY, containerRect.width);
  };

  const hideTooltip = () => setActiveTooltip(null);

  const toggleTooltip = (point: ChartPoint, target: SVGElement) => {
    if (activeTooltip?.sourceIndex === point.sourceIndex) {
      hideTooltip();
      return;
    }

    showTooltip(point, target);
  };

  return (
    <div ref={containerRef} className="relative min-w-0">
      <svg
        width="100%"
        height={chartHeight}
        viewBox={`0 0 ${CHART_WIDTH} ${chartHeight}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Monthly performance trend chart"
        className="block overflow-visible"
      >
        <defs>
          <linearGradient
            id={`line-chart-gradient-${gradientId}`}
            x1="0"
            y1="0"
            x2="0"
            y2="1"
          >
            <stop offset="0%" stopColor={color} stopOpacity="0.16" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>

        {ticks.map((tick) => (
          <g key={tick.value}>
            <text
              x={PAD_LEFT - 8}
              y={tick.y + 3.5}
              fill="var(--bsc-panel-muted)"
              fontSize="9"
              textAnchor="end"
            >
              {tick.label}
            </text>
          </g>
        ))}

        {/* Target line */}
        {targetY !== null && (
          <g>
            <line
              x1={PAD_LEFT}
              y1={targetY}
              x2={CHART_WIDTH - PAD_RIGHT}
              y2={targetY}
              stroke={color}
              strokeWidth="1.25"
              strokeDasharray="4 4"
              strokeOpacity="0.5"
              vectorEffect="non-scaling-stroke"
            />

            <text
              x={CHART_WIDTH - PAD_RIGHT}
              y={Math.max(PAD_TOP + 10, targetY - 6)}
              fill={color}
              fillOpacity="0.82"
              fontSize="9.5"
              fontWeight="700"
              textAnchor="end"
            >
              Target {formatScore(usableTarget ?? 0)}
            </text>
          </g>
        )}

        {/* Trend segments - no fake connection over missing months */}
        {lineSegments.map((segment) => {
          const linePath = getBezierPath(segment, toX, toY);

          const firstPoint = segment[0];
          const lastPoint = segment[segment.length - 1];
          const baselineY = chartHeight - PAD_BOTTOM;

          const areaPath = [
            linePath,
            `L ${toX(lastPoint.sourceIndex).toFixed(1)},${baselineY.toFixed(1)}`,
            `L ${toX(firstPoint.sourceIndex).toFixed(
              1,
            )},${baselineY.toFixed(1)}`,
            'Z',
          ].join(' ');

          return (
            <g key={`${firstPoint.sourceIndex}-${lastPoint.sourceIndex}`}>
              <path
                d={areaPath}
                fill={`url(#line-chart-gradient-${gradientId})`}
              />

              <path
                d={linePath}
                fill="none"
                stroke={color}
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
            </g>
          );
        })}

        {/* Measured points */}
        {measuredPoints.map((point) => {
          const x = toX(point.sourceIndex);
          const y = toY(point.score);
          const isLastPoint =
            point.sourceIndex ===
            measuredPoints[measuredPoints.length - 1].sourceIndex;

          return (
            <g
              key={`${point.year}-${point.month}-${point.sourceIndex}`}
              role="button"
              tabIndex={0}
              aria-label={`${formatMonthMmm(
                point.month,
                point.year,
              )} ${point.year}: ${formatScore(point.score)}`}
              className="cursor-pointer outline-none"
              onMouseEnter={(event) =>
                showTooltip(point, event.currentTarget)
              }
              onMouseLeave={hideTooltip}
              onFocus={(event) => showTooltip(point, event.currentTarget)}
              onBlur={hideTooltip}
              onClick={(event) => toggleTooltip(point, event.currentTarget)}
              onKeyDown={(event) => {
                if (event.key === 'Escape') {
                  hideTooltip();
                }

                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  toggleTooltip(point, event.currentTarget);
                }
              }}
            >
              {/* Wider invisible tap target for mobile */}
              <circle
                cx={x}
                cy={y}
                r="13"
                fill="transparent"
                pointerEvents="all"
              />

              <circle
                cx={x}
                cy={y}
                r={isLastPoint ? 5 : 4}
                fill={color}
                stroke="var(--bsc-panel-bg-solid)"
                strokeWidth="2"
                vectorEffect="non-scaling-stroke"
              />
            </g>
          );
        })}

        {measuredPoints.map((point, index) => {
          const currentX = toX(point.sourceIndex);
          const previousX =
            index > 0 ? toX(measuredPoints[index - 1].sourceIndex) : PAD_LEFT;
          const nextX =
            index < measuredPoints.length - 1
              ? toX(measuredPoints[index + 1].sourceIndex)
              : CHART_WIDTH - PAD_RIGHT;
          const leftBound =
            index === 0 ? PAD_LEFT : (previousX + currentX) / 2;
          const rightBound =
            index === measuredPoints.length - 1
              ? CHART_WIDTH - PAD_RIGHT
              : (currentX + nextX) / 2;

          return (
            <rect
              key={`hover-band-${point.sourceIndex}`}
              x={leftBound}
              y={PAD_TOP}
              width={Math.max(0, rightBound - leftBound)}
              height={innerHeight}
              fill="transparent"
              pointerEvents="all"
              onMouseEnter={(event) => showTooltipFromBand(point, event)}
              onMouseMove={(event) => showTooltipFromBand(point, event)}
              onMouseLeave={hideTooltip}
            />
          );
        })}

        {/* X-axis labels */}
        {visibleMonthLabels.map(
          ({ index, label, visible }) =>
            visible && (
              <text
                key={`${label}-${index}`}
                x={toX(index)}
                y={chartHeight - 5}
                fill="var(--bsc-panel-muted)"
                fontSize="9"
                fontWeight="600"
                textAnchor="middle"
              >
                {label}
              </text>
            ),
        )}
      </svg>

      {/* Tooltip */}
      {activeTooltip && (
        <div
          role="status"
          aria-live="polite"
          className="pointer-events-none absolute z-20 w-40 rounded-2xl p-3 backdrop-blur-md"
          style={{
            left: activeTooltip.x,
            top:
              activeTooltip.placement === 'above'
                ? activeTooltip.y - 8
                : activeTooltip.y + 10,
            transform:
              activeTooltip.placement === 'above'
                ? 'translate(-50%, -100%)'
                : 'translate(-50%, 0)',
            border: '1px solid var(--bsc-border)',
            background: 'color-mix(in srgb, var(--bsc-tooltip-bg) 84%, transparent)',
            boxShadow: 'var(--bsc-shadow-lg)',
            boxSizing: 'border-box',
          }}
        >
          <div
            className="mb-1.5 border-b pb-1.5 text-[10px] font-extrabold uppercase tracking-[0.08em]"
            style={{ borderColor: 'var(--bsc-table-row)', color: 'var(--bsc-panel-muted)' }}
          >
            {formatMonthMmm(activeTooltip.month, activeTooltip.year)}
          </div>

          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="flex items-center gap-1.5 font-semibold" style={{ color: 'var(--bsc-panel-subtle)' }}>
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: color }}
              />
              Score
            </span>

            <strong className="text-[13px] font-bold" style={{ color: 'var(--bsc-panel-text)' }}>
              {formatScore(activeTooltip.score)}
            </strong>
          </div>
        </div>
      )}
    </div>
  );
}

export default LineChart;
