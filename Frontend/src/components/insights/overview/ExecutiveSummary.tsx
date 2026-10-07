import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent as ReactMouseEvent, type ReactNode } from 'react';
import { ArrowDownRight, ArrowUpRight, Calendar, Info, LineChart as LineChartIcon, Link2 } from 'lucide-react';
import type { InsightExecutiveStory, InsightKpiTrend, InsightOverallTrendPoint, InsightsWorkspace } from '../../../features/insights/types';
import { GradeBadge } from './InsightsOverviewPrimitives';
import {
  cleanScope, formatPercent, formatSignedPercent, movementTone, priorityFocusText, resolveMovementTone, selectTrendSeries,
  type MovementTone, type TrendPoint, type TrendSeries,
} from './insightsOverviewModel';

const CHART_HEIGHT = 176;
const TONE_COLOR: Record<MovementTone, string> = {
  good: 'var(--insights-positive)',
  bad: 'var(--insights-negative)',
  flat: 'var(--text-muted)',
  unknown: 'var(--text-muted)',
};

/** Rendered width of the chart box; the SVG is drawn in real pixels so text never scales. */
function useElementWidth<T extends HTMLElement>(fallback: number) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect.width ?? 0);
      if (next > 0) setWidth(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

function formatRaw(value: number | null, unit: string | null) {
  if (value === null || !Number.isFinite(value)) return 'N/A';
  if (unit === '%') return `${(Math.abs(value) <= 1 ? value * 100 : value).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${unit ? ` ${unit}` : ''}`;
}

function formatRawDelta(delta: number, unit: string | null, reference: number | null) {
  const scale = unit === '%' && reference !== null && Math.abs(reference) <= 1 ? 100 : 1;
  const value = delta * scale;
  const suffix = unit === '%' ? '%' : unit ? ` ${unit}` : '';
  return `${value > 0 ? '+' : ''}${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${suffix}`;
}

/** Month-over-month movement for a trend point, coloured by KPI direction. */
function pointMovement(series: TrendSeries, index: number) {
  const point = series.points[index];
  const previousPoint = index > 0 ? series.points[index - 1] : null;
  if (!previousPoint) return null;
  if (series.source === 'kpi' && point.raw) {
    const { actual, previous, unit, direction, trendStatus, changeValue } = point.raw;
    if (actual === null || previous === null) return null;
    // Arrow follows the raw movement; colour follows the API's direction-aware status when present.
    const delta = actual - previous;
    return { delta, tone: resolveMovementTone({ trendStatus, changeValue, rawDelta: delta, direction }), text: formatRawDelta(delta, unit, actual), against: previousPoint.label };
  }
  if (point.actual === null || previousPoint.actual === null) return null;
  const delta = point.actual - previousPoint.actual;
  return { delta, tone: movementTone(delta, 'higher_better'), text: `${delta > 0 ? '+' : ''}${delta.toFixed(1)}%`, against: previousPoint.label };
}

function TrendSkeleton() {
  return (
    <div role="status" aria-label="Loading performance trend" data-testid="performance-trend-loading" className="relative w-full" style={{ height: CHART_HEIGHT }}>
      <div className="absolute inset-x-[36px] bottom-[26px] top-[16px] animate-pulse overflow-hidden rounded-[8px]">
        <svg viewBox="0 0 300 120" preserveAspectRatio="none" className="h-full w-full" aria-hidden="true">
          <path d="M0 92 C40 80, 60 70, 100 74 S160 50, 200 46 S260 34, 300 30" fill="none" stroke="var(--bg-sunken)" strokeWidth={6} strokeLinecap="round" />
          <path d="M0 24 H300" stroke="var(--bg-sunken)" strokeWidth={2} strokeDasharray="6 6" />
        </svg>
      </div>
      <div className="absolute inset-x-[36px] bottom-[6px] flex justify-between" aria-hidden="true">
        {Array.from({ length: 6 }, (_, index) => <span key={index} className="h-[8px] w-[22px] animate-pulse rounded bg-[var(--bg-sunken)]" />)}
      </div>
      <span className="sr-only">Loading performance trend</span>
    </div>
  );
}

function TrendEmpty({ source }: { source: TrendSeries['source'] }) {
  return (
    <div data-testid="performance-trend-empty" className="flex w-full flex-col items-center justify-center gap-[6px] rounded-[8px] border border-dashed border-[var(--insights-card-border)] px-6 text-center" style={{ height: CHART_HEIGHT }}>
      <LineChartIcon aria-hidden="true" className="size-[20px] text-[var(--text-faint)]" strokeWidth={1.5} />
      <p className="text-[12px] font-semibold text-[var(--insights-heading)]">No trend data for this scope</p>
      <p className="max-w-[260px] text-[11px] text-[var(--text-muted)]">
        {source === 'overall' ? 'No measured score' : 'No measured leading-KPI value'} in the last six months for the selected filters.
      </p>
    </div>
  );
}

function PerformanceTrendChart({ series }: { series: TrendSeries }) {
  const { points } = series;
  const [boxRef, width] = useElementWidth<HTMLDivElement>(388);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);
  const [rovingIndex, setRovingIndex] = useState<number | null>(null);
  // Escape hides the tooltip without moving keyboard focus off the point.
  const [dismissed, setDismissed] = useState(false);
  const pointRefs = useRef<Array<SVGGElement | null>>([]);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [tooltipHeight, setTooltipHeight] = useState(96);

  // A tap / click outside the chart closes a touch-opened tooltip.
  useEffect(() => {
    if (hoveredIndex === null) return undefined;
    const onPointerDown = (event: Event) => {
      if (boxRef.current && event.target instanceof Node && boxRef.current.contains(event.target)) return;
      setHoveredIndex(null);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setHoveredIndex(null);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('touchstart', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('touchstart', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [hoveredIndex, boxRef]);

  // Measure the tooltip so it can be clamped inside the chart box (it never spills out of the card).
  useLayoutEffect(() => {
    const height = tooltipRef.current?.offsetHeight;
    if (height && height !== tooltipHeight) setTooltipHeight(height);
  }, [hoveredIndex, focusedIndex, dismissed, tooltipHeight]);

  const measuredIndexes = points.map((point, index) => (point.actual !== null ? index : -1)).filter((index) => index >= 0);
  if (!points.length || !measuredIndexes.length) {
    return <div ref={boxRef} className="w-full"><TrendEmpty source={series.source} /></div>;
  }

  const plot = { left: 36, right: width - 10, top: 18, bottom: CHART_HEIGHT - 26 };
  const inset = Math.min(22, (plot.right - plot.left) / 12);
  const values = points.flatMap((point) => [point.actual, point.target]).filter((value): value is number => value !== null);
  const yMax = Math.max(100, Math.ceil(Math.max(...values) / 25) * 25);
  const y = (value: number) => plot.bottom - (Math.min(Math.max(value, 0), yMax) / yMax) * (plot.bottom - plot.top);
  const step = points.length > 1 ? (plot.right - plot.left - inset * 2) / (points.length - 1) : 0;
  const x = (index: number) => (points.length > 1 ? plot.left + inset + index * step : (plot.left + plot.right) / 2);
  const ticks = [0, 50, 100, ...(yMax - 100 >= 25 ? [yMax] : [])];

  const segments: Array<Array<{ index: number; value: number }>> = [];
  let segment: Array<{ index: number; value: number }> = [];
  points.forEach((point, index) => {
    if (point.actual === null) {
      if (segment.length) segments.push(segment);
      segment = [];
      return;
    }
    segment.push({ index, value: point.actual });
  });
  if (segment.length) segments.push(segment);
  const curve = (segmentPoints: Array<{ index: number; value: number }>) => segmentPoints.reduce((path, point, index) => {
    const pointX = x(point.index);
    const pointY = y(point.value);
    if (index === 0) return `M${pointX.toFixed(1)} ${pointY.toFixed(1)}`;
    const previous = segmentPoints[index - 1];
    const controlOffset = (pointX - x(previous.index)) / 3;
    return `${path} C${(x(previous.index) + controlOffset).toFixed(1)} ${y(previous.value).toFixed(1)}, ${(pointX - controlOffset).toFixed(1)} ${pointY.toFixed(1)}, ${pointX.toFixed(1)} ${pointY.toFixed(1)}`;
  }, '');

  const targetIndexes = points.map((point, index) => (point.target !== null ? index : -1)).filter((index) => index >= 0);
  const targetPath = targetIndexes.length
    ? targetIndexes.map((index, order) => `${order === 0 ? 'M' : 'L'}${(order === 0 ? plot.left : x(index)).toFixed(1)} ${y(points[index].target as number).toFixed(1)}`).join(' ')
      + ` H${plot.right.toFixed(1)}`
    : null;
  const lastTarget = targetIndexes.length ? points[targetIndexes[targetIndexes.length - 1]].target : null;

  const tabStop = (rovingIndex !== null && measuredIndexes.includes(rovingIndex) ? rovingIndex : null) ?? measuredIndexes[measuredIndexes.length - 1];
  const activeIndex = dismissed ? null : (hoveredIndex ?? focusedIndex);
  const activePoint = activeIndex === null ? null : points[activeIndex];
  const activeValue = activePoint?.actual ?? null;
  const valueLabel = series.source === 'overall' ? 'Score' : 'Actual';

  const describe = (point: TrendPoint, index: number) => {
    const movement = pointMovement(series, index);
    const parts = [
      `${point.label}: ${valueLabel.toLowerCase()} ${point.actual?.toFixed(1)}%${series.source === 'kpi' ? ' of target' : ''}`,
      point.target !== null ? `target ${point.target.toFixed(0)}%` : null,
      series.source === 'kpi' && point.raw ? `value ${formatRaw(point.raw.actual, point.raw.unit)}` : null,
      movement ? `${movement.text} vs ${movement.against}, ${movement.tone === 'good' ? 'improving' : movement.tone === 'bad' ? 'worsening' : 'no change'}` : null,
    ];
    return parts.filter(Boolean).join(', ');
  };

  const onPointerMove = (event: ReactMouseEvent<SVGRectElement>) => {
    const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    const scale = rect && rect.width > 0 ? width / rect.width : 1;
    const pointerX = (event.clientX - (rect?.left ?? 0)) * scale;
    const nearest = measuredIndexes.reduce((best, index) => (Math.abs(x(index) - pointerX) < Math.abs(x(best) - pointerX) ? index : best), measuredIndexes[0]);
    setDismissed(false);
    setHoveredIndex(nearest);
  };
  const moveFocus = (from: number, offset: number | 'first' | 'last') => {
    const position = measuredIndexes.indexOf(from);
    const nextPosition = offset === 'first' ? 0 : offset === 'last' ? measuredIndexes.length - 1
      : Math.min(measuredIndexes.length - 1, Math.max(0, position + offset));
    const next = measuredIndexes[nextPosition];
    setRovingIndex(next);
    pointRefs.current[next]?.focus();
  };

  const movement = activeIndex === null ? null : pointMovement(series, activeIndex);
  const activeX = activeIndex === null ? null : x(activeIndex);
  const activeY = activeValue === null ? null : y(activeValue);
  const tooltipWidth = series.source === 'kpi' ? 212 : 188;
  // Like Recharts: the tooltip sits beside the hovered month (right of it, or left near the right edge),
  // vertically centred on the point and clamped to the chart box so it never covers the point itself.
  const tooltipGap = 14;
  const placeLeft = activeX !== null && activeX + tooltipGap + tooltipWidth > width;
  const tooltipLeft = activeX === null ? 0 : Math.max(0, placeLeft ? activeX - tooltipGap - tooltipWidth : activeX + tooltipGap);
  const tooltipTop = activeY === null ? 0 : Math.min(Math.max(activeY - tooltipHeight / 2, 0), Math.max(0, CHART_HEIGHT - tooltipHeight));

  return (
    <div ref={boxRef} className="relative w-full" style={{ height: CHART_HEIGHT }}>
      <svg
        role="group"
        aria-label={`${series.source === 'overall' ? 'Overall score' : `Leading KPI${series.kpiLabel ? ` ${series.kpiLabel}` : ''}`} trend, last six months: ${points.map((point) => `${point.label} ${point.actual === null ? 'no data' : `${point.actual.toFixed(1)}%`}`).join(', ')}. Use arrow keys to move between months.`}
        width={width}
        height={CHART_HEIGHT}
        viewBox={`0 0 ${width} ${CHART_HEIGHT}`}
        className="block overflow-visible"
        data-testid="performance-trend-chart"
        data-source={series.source}
      >
        {ticks.map((tick) => (
          <text key={tick} x={plot.left - 8} y={y(tick)} dominantBaseline="middle" textAnchor="end" fontSize={10} fill="var(--text-muted)" data-testid="performance-trend-tick">{`${tick}%`}</text>
        ))}
        <path d={`M${plot.left} ${plot.bottom}H${plot.right}`} stroke="var(--insights-card-border)" strokeWidth={1} data-testid="performance-trend-baseline" />
        {targetPath && (
          <>
            <path data-testid="performance-trend-target" d={targetPath} stroke="var(--insights-target)" strokeOpacity={0.75} strokeWidth={1.25} strokeDasharray="4 4" fill="none" />
            <text x={plot.right} y={y(lastTarget as number) - 6} textAnchor="end" fontSize={10} fontWeight={600} fill="var(--text-muted)" data-testid="performance-trend-target-label">{`Target ${(lastTarget as number).toFixed(0)}%`}</text>
          </>
        )}
        {activeX !== null && (
          <line data-testid="performance-trend-crosshair" x1={activeX} x2={activeX} y1={plot.top} y2={plot.bottom} stroke="var(--insights-card-border)" strokeWidth={1} pointerEvents="none" />
        )}
        {segments.map((segmentPoints) => segmentPoints.length > 1 && (
          <path key={segmentPoints[0].index} d={curve(segmentPoints)} stroke="var(--insights-accent)" strokeWidth={2.25} strokeLinecap="round" strokeLinejoin="round" fill="none" />
        ))}
        {points.map((point, index) => point.actual !== null && (
          <g
            key={point.key}
            ref={(node) => { pointRefs.current[index] = node; }}
            role="img"
            tabIndex={index === tabStop ? 0 : -1}
            aria-label={describe(point, index)}
            data-testid={`performance-trend-point-${point.key}`}
            className="group outline-none"
            onFocus={() => {
              setDismissed(false);
              setFocusedIndex(index);
              setRovingIndex(index);
            }}
            onBlur={() => setFocusedIndex((current) => (current === index ? null : current))}
            onKeyDown={(event) => {
              const keys: Record<string, number | 'first' | 'last'> = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1, Home: 'first', End: 'last' };
              if (event.key === 'Escape') {
                setHoveredIndex(null);
                setDismissed(true);
              } else if (event.key in keys) {
                event.preventDefault();
                moveFocus(index, keys[event.key]);
              }
            }}
          >
            {/* Subtle ring on the keyboard-focused point only (:focus-visible). */}
            <circle
              data-testid="performance-trend-focus-ring"
              cx={x(index)}
              cy={y(point.actual)}
              r={8}
              fill="none"
              stroke="var(--insights-heading)"
              strokeOpacity={0.55}
              strokeWidth={1.5}
              className="opacity-0 transition-opacity group-focus-visible:opacity-100"
              pointerEvents="none"
            />
            <circle
              cx={x(index)}
              cy={y(point.actual)}
              r={activeIndex === index ? 4.5 : 3}
              fill="var(--insights-accent)"
              stroke="var(--bg-surface)"
              strokeWidth={activeIndex === index ? 2 : 1.5}
            />
          </g>
        ))}
        {points.map((point, index) => (
          <text key={`${point.key}-label`} x={x(index)} y={CHART_HEIGHT - 8} textAnchor="middle" fontSize={10} fill="var(--text-muted)">{point.label}</text>
        ))}
        {/* Hover anywhere over the plot shows the nearest month, like the app's Recharts tooltips. */}
        <rect
          data-testid="performance-trend-hover-area"
          x={plot.left}
          y={0}
          width={Math.max(0, plot.right - plot.left)}
          height={plot.bottom}
          fill="transparent"
          onMouseMove={onPointerMove}
          onMouseLeave={() => setHoveredIndex(null)}
        />
      </svg>
      {activePoint && activeValue !== null && activeIndex !== null && activeY !== null && (
        <div
          ref={tooltipRef}
          aria-hidden="true"
          data-testid="performance-trend-tooltip"
          className="pointer-events-none absolute z-10 rounded-[12px] border border-[var(--insights-card-border)] bg-[var(--bg-surface)] px-[12px] py-[9px] shadow-[0_10px_24px_rgba(15,23,42,0.16)]"
          style={{
            width: tooltipWidth,
            left: tooltipLeft,
            top: tooltipTop,
          }}
          data-placement={placeLeft ? 'left' : 'right'}
        >
          <p className="mb-[6px] border-b border-[var(--insights-row-border)] pb-[5px] text-[11px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">{activePoint.label}</p>
          <div className="flex items-center justify-between gap-3 text-[12px]">
            <span className="inline-flex items-center gap-[7px] font-medium text-[var(--text-secondary)]"><span className="size-[8px] rounded-full bg-[var(--insights-accent)]" />{valueLabel}</span>
            <strong className="font-semibold tabular-nums text-[var(--insights-heading)]">{activeValue.toFixed(1)}%</strong>
          </div>
          {activePoint.target !== null && (
            <div className="mt-[3px] flex items-center justify-between gap-3 text-[12px]" data-testid="performance-trend-tooltip-target">
              <span className="inline-flex items-center gap-[7px] font-medium text-[var(--text-secondary)]">
                <svg width="10" height="4" viewBox="0 0 10 4"><path d="M0 2H4M6 2H10" stroke="var(--insights-target)" strokeWidth={2} /></svg>
                Target
              </span>
              <strong className="font-semibold tabular-nums text-[var(--insights-heading)]">{activePoint.target.toFixed(0)}%</strong>
            </div>
          )}
          {series.source === 'kpi' && activePoint.raw && (
            <p className="mt-[5px] text-[11px] text-[var(--text-muted)]" data-testid="performance-trend-tooltip-raw">
              {formatRaw(activePoint.raw.actual, activePoint.raw.unit)} vs {formatRaw(activePoint.raw.target, activePoint.raw.unit)} target
            </p>
          )}
          {movement && (
            <p className="mt-[3px] flex items-center gap-[4px] text-[11px] font-semibold" style={{ color: TONE_COLOR[movement.tone] }} data-testid="performance-trend-tooltip-movement" data-tone={movement.tone}>
              <span aria-hidden="true">{movement.delta > 0 ? '▲' : movement.delta < 0 ? '▼' : '→'}</span>
              {movement.text} vs {movement.against}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function PerformanceTrend({ series, loading, filterKey }: { series: TrendSeries; loading?: boolean; filterKey?: string }) {
  const overall = series.source === 'overall';
  const lowerBetter = !overall && series.direction === 'lower_better';
  const explanation = overall
    ? 'Overall score for the selected filters over the last six months; the latest month matches the Current score.'
    : `The API has no overall score series yet, so this shows the leading KPI${series.kpiLabel ? ` "${series.kpiLabel}"` : ''} as a percentage of target (100% = on target${lowerBetter ? '; lower raw values are better' : ''}). It is not the overall score.`;
  return (
    <div data-testid="performance-trend-card" className="flex w-full min-w-0 shrink-0 flex-col gap-[10px] rounded-[12px] border border-[var(--insights-card-border)] bg-[var(--bg-surface)] px-[16px] pb-[14px] pt-[16px] xl:w-[420px]">
      <div className="flex w-full items-center gap-[6px]">
        <h3 className="text-[13px] font-semibold leading-normal text-[var(--insights-heading)]">{overall ? 'Performance trend' : 'Leading KPI trend'}</h3>
        <span title={explanation} className="inline-flex text-[var(--text-muted)]">
          <Info aria-hidden="true" className="size-[14px]" strokeWidth={1.5} />
          <span className="sr-only">{explanation}</span>
        </span>
        <span className="h-px min-w-px flex-1" />
        <span className="inline-flex items-center gap-[6px] rounded-[6px] border border-[var(--insights-card-border)] bg-[var(--insights-chip-bg)] px-[10px] py-[6px] text-[12px] font-medium leading-normal text-[var(--insights-chip-text)]">
          <Calendar aria-hidden="true" className="size-[14px]" strokeWidth={1.5} />
          Last 6 months
        </span>
      </div>
      <p className="-mt-[4px] truncate text-[11px] text-[var(--text-muted)]" title={explanation} data-testid="performance-trend-subtitle">
        {overall
          ? 'Overall score · % of target'
          : `${series.kpiLabel ?? 'Leading KPI'} · % of target${lowerBetter ? ' · lower is better' : ''}`}
      </p>
      {loading
        ? <TrendSkeleton />
        : <PerformanceTrendChart key={`${filterKey ?? ''}|${series.source}|${series.kpiLabel ?? ''}|${series.points.map((point) => point.key).join(',')}`} series={series} />}
      <div className="flex w-full items-center justify-center gap-[20px] text-[12px] leading-normal text-[var(--text-secondary)]">
        <span className="inline-flex items-center gap-[6px]"><span aria-hidden="true" className="size-[8px] rounded-full bg-[var(--insights-accent)]" />{overall ? 'Overall score' : 'KPI actual'}</span>
        <span className="inline-flex items-center gap-[6px]">
          <svg aria-hidden="true" width="16" height="4" viewBox="0 0 16 4"><path d="M0 2H6M10 2H16" stroke="var(--insights-target)" strokeWidth={2} /></svg>
          Target
        </span>
      </div>
    </div>
  );
}

/** "↓ 1.9%" month-over-month pill next to the grade badge (Figma 34:8). */
function TrendBadge({ change, previousLabel }: { change: number | null; previousLabel: string }) {
  if (change === null || !Number.isFinite(change)) return null;
  const tone = change < 0 ? 'down' : change > 0 ? 'up' : 'flat';
  const glyph = tone === 'down' ? '↓' : tone === 'up' ? '↑' : '→';
  const styles = {
    down: 'bg-[var(--insights-trend-down-bg)] text-[var(--insights-trend-down-text)]',
    up: 'bg-[var(--insights-trend-up-bg)] text-[var(--insights-trend-up-text)]',
    flat: 'bg-[var(--insights-chip-bg)] text-[var(--insights-chip-text)]',
  }[tone];
  const spoken = `${tone === 'down' ? 'Down' : tone === 'up' ? 'Up' : 'No change'} ${Math.abs(change).toFixed(1)}% ${previousLabel.toLowerCase()}`;
  return (
    <span data-testid="executive-trend-badge" data-tone={tone} className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-[8px] py-[3px] text-[11px] font-semibold leading-normal ${styles}`}>
      <span aria-hidden="true">{`${glyph} ${Math.abs(change).toFixed(1)}%`}</span>
      <span className="sr-only">{spoken}</span>
    </span>
  );
}

function SummaryKpi({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col items-start gap-[6px]">
      <p className="text-[12px] font-normal leading-normal text-[var(--text-muted)]">{label}</p>
      {children}
    </div>
  );
}

function Divider() {
  return <span aria-hidden="true" className="hidden h-[60px] w-px shrink-0 bg-[var(--insights-card-border)] sm:block" />;
}

function toneColor(value: number | null | undefined) {
  if (value === null || value === undefined) return 'var(--insights-heading)';
  return value < 0 ? 'var(--insights-negative)' : 'var(--insights-positive)';
}

export default function ExecutiveSummary({
  story,
  comparison,
  trend,
  overallTrend,
  trendLoading = false,
  filterKey,
}: {
  story: InsightExecutiveStory | null | undefined;
  comparison: InsightsWorkspace['comparison'];
  /** Leading-KPI series (fallback until the API returns `overall_trend`). */
  trend: InsightKpiTrend | null | undefined;
  /** Overall score per month (proposed `overall_trend`); preferred when present. */
  overallTrend?: InsightOverallTrendPoint[] | null;
  /** True while the workspace for the current filters is still loading. */
  trendLoading?: boolean;
  /** Serialized active filters; any change resets the pinned trend point. */
  filterKey?: string;
}) {
  const period = comparison.current ? `${comparison.current.month} ${comparison.current.year}` : 'The selected period';
  const gap = story?.gap_points ?? null;
  const change = story?.score_change ?? null;
  const previousLabel = comparison.previous && !comparison.is_adjacent
    ? `vs. ${comparison.previous.month} ${comparison.previous.year}`
    : 'vs. Previous Month';
  let headline: ReactNode = story?.headline ?? `No measured performance is available for ${period}.`;
  if (story && story.current_score !== null && gap !== null) {
    if (gap < 0) {
      headline = <>{period} performance is <span className="text-[var(--insights-negative)]">{Math.abs(gap).toFixed(1)}%</span> below target.</>;
    } else if (gap > 0) {
      headline = <>{period} performance is <span className="text-[var(--insights-positive)]">{gap.toFixed(1)}%</span> above target.</>;
    } else {
      headline = <>{period} performance is on target.</>;
    }
  }

  return (
    <section
      aria-labelledby="executive-summary-title"
      className="flex min-w-0 flex-col gap-[28px] rounded-[14px] border border-[var(--insights-summary-border)] bg-[var(--insights-summary-bg)] py-[24px] pl-[28px] pr-[24px] shadow-[var(--insights-summary-shadow)] xl:flex-row xl:items-start"
    >
      <div className="flex min-w-0 flex-1 flex-col gap-[20px]">
        <div className="flex w-full items-center gap-[12px]">
          <span aria-hidden="true" className="grid size-[32px] place-items-center rounded-[8px] bg-[var(--insights-icon-summary)] text-white">
            <Link2 className="size-[18px]" strokeWidth={1.5} />
          </span>
          <h2 id="executive-summary-title" className="text-[15px] font-semibold leading-normal text-[var(--insights-heading)]">Executive Summary</h2>
        </div>
        <div className="flex w-full flex-col gap-[10px]">
          {story && story.current_score !== null && (
            <div className="flex w-full flex-wrap items-center gap-[8px]" data-testid="executive-status-row">
              <GradeBadge score={story.current_score} />
              <TrendBadge change={change} previousLabel={previousLabel} />
            </div>
          )}
          <p data-testid="executive-headline" className="w-full text-[28px] font-bold leading-tight tracking-[-0.28px] text-[var(--insights-heading)]">{headline}</p>
        </div>
        <div
          data-testid="executive-priority-focus"
          className="flex w-full items-center gap-[12px] rounded-[9px] border border-[var(--insights-info-border)] bg-[var(--insights-info-bg)] px-[12px] py-[10px]"
          title={story ? cleanScope(story.recommended_focus) : undefined}
        >
          <span className="shrink-0 whitespace-nowrap rounded-full bg-[var(--insights-info-pill-bg)] px-[10px] py-[4px] text-[10px] font-semibold uppercase leading-normal tracking-[0.4px] text-[var(--insights-info-pill-text)]">Priority focus</span>
          <p className="min-w-0 flex-1 text-[13px] font-semibold leading-normal text-[var(--insights-info-text)]">{priorityFocusText(story)}</p>
        </div>
        <div className="flex w-full flex-col gap-[12px]">
          <span aria-hidden="true" className="h-px w-full bg-[var(--insights-card-border)]" />
        <div className="grid w-full grid-cols-2 gap-[20px] sm:flex sm:items-start">
          <SummaryKpi label="Current">
            <p className="text-[26px] font-bold leading-normal text-[var(--insights-heading)]">{formatPercent(story?.current_score)}</p>
            <GradeBadge score={story?.current_score} />
          </SummaryKpi>
          <Divider />
          <SummaryKpi label="Target">
            <p className="text-[26px] font-bold leading-normal text-[var(--insights-heading)]">{formatPercent(story?.target_score)}</p>
          </SummaryKpi>
          <Divider />
          <SummaryKpi label="Gap">
            <p className="text-[26px] font-bold leading-normal" style={{ color: toneColor(gap) }}>{formatSignedPercent(gap)}</p>
          </SummaryKpi>
          <Divider />
          <SummaryKpi label={previousLabel}>
            <p className="flex items-center gap-[6px] text-[26px] font-bold leading-normal" style={{ color: toneColor(change) }}>
              {formatSignedPercent(change)}
              {change !== null && (change < 0
                ? <ArrowDownRight aria-hidden="true" className="size-[18px]" strokeWidth={1.875} />
                : <ArrowUpRight aria-hidden="true" className="size-[18px]" strokeWidth={1.875} />)}
            </p>
          </SummaryKpi>
        </div>
        </div>
      </div>
      <PerformanceTrend series={selectTrendSeries(overallTrend, trend)} loading={trendLoading} filterKey={filterKey} />
    </section>
  );
}
