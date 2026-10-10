import { useEffect, useId, useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { Calendar, LineChart } from 'lucide-react';
import type { ExecutiveTrendPoint } from '../../../features/executive/types';
import { fmtScore, shortMonth } from '../../../features/executive/format';
import BasisComparisonNote from '../../../features/evaluation/BasisComparisonNote';
import { useElementWidth } from './execModel';
import { smoothPath, splitSeries, type SegmentPoint } from './trendGeometry';

const TOOLTIP_WIDTH = 194;
const CHART_HEIGHT = 260;
const lineColor = 'var(--insights-accent)';

function straightPath(points: SegmentPoint[], x: (index: number) => number, y: (value: number) => number): string {
  return points.map((point, index) => {
    const command = index === 0 ? 'M' : 'L';
    return command + x(point.index).toFixed(1) + ' ' + y(point.value).toFixed(1);
  }).join(' ');
}

function formatMovement(delta: number): string {
  const rounded = Number(delta.toFixed(1));
  return (rounded > 0 ? '+' : '') + rounded.toFixed(1) + '%';
}

/** Score trend with the hover, keyboard, and empty-state behaviour used in Insights. */
export default function ScoreTrendChart({ points, comparisonLabel, title }: {
  points: ExecutiveTrendPoint[];
  comparisonLabel?: string | null;
  title: string;
}) {
  const gradientId = useId();
  const [boxRef, width] = useElementWidth<HTMLDivElement>(510);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);
  const [rovingIndex, setRovingIndex] = useState<number | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const pointRefs = useRef<Array<SVGGElement | null>>([]);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [tooltipHeight, setTooltipHeight] = useState(98);

  useEffect(() => {
    if (hoveredIndex === null) return undefined;
    const onPointerDown = (event: Event) => {
      if (boxRef.current && event.target instanceof Node && boxRef.current.contains(event.target)) return;
      setHoveredIndex(null);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setHoveredIndex(null);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [hoveredIndex, boxRef]);

  useLayoutEffect(() => {
    const height = tooltipRef.current?.offsetHeight;
    if (height && height !== tooltipHeight) setTooltipHeight(height);
  }, [hoveredIndex, focusedIndex, dismissed, tooltipHeight]);

  const measuredIndexes = points.map((point, index) => (point.score !== null && Number.isFinite(point.score) ? index : -1)).filter((index) => index >= 0);
  const values = points.flatMap((point) => [point.score, point.comparison_score, point.target])
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const maximum = Math.max(100, ...values);
  const yMax = Math.max(100, Math.ceil(maximum / 25) * 25);
  const plot = { left: 40, right: Math.max(46, width - 12), top: 24, bottom: CHART_HEIGHT - 28 };
  const inset = Math.min(18, (plot.right - plot.left) / 12);
  const x = (index: number) => points.length > 1
    ? plot.left + inset + index * ((plot.right - plot.left - inset * 2) / (points.length - 1))
    : (plot.left + plot.right) / 2;
  const y = (value: number) => plot.bottom - (Math.min(Math.max(value, 0), yMax) / yMax) * (plot.bottom - plot.top);
  const ticks = [0, 50, 100, ...(yMax > 100 ? [yMax] : [])];
  const target = points[0]?.target ?? 100;
  const actualSegments = splitSeries(points.map((point) => point.score));
  const comparisonSegments = splitSeries(points.map((point) => point.comparison_score));
  const hasComparison = comparisonSegments.length > 0;
  const range = points.length
    ? shortMonth(points[0].period) + ' – ' + shortMonth(points[points.length - 1].period) + ' ' + points[points.length - 1].period.year
    : '';
  const description = title + ' trend, last six months: ' + points.map((point) => {
    const label = shortMonth(point.period);
    return label + ' ' + (point.score === null ? 'no data' : fmtScore(point.score));
  }).join(', ') + '. Use arrow keys to move between measured months.';

  const tabStop = (rovingIndex !== null && measuredIndexes.includes(rovingIndex) ? rovingIndex : null)
    ?? measuredIndexes[measuredIndexes.length - 1];
  const activeIndex = dismissed ? null : (hoveredIndex ?? focusedIndex);
  const activePoint = activeIndex === null ? null : points[activeIndex];
  const activeScore = activePoint?.score ?? null;
  const activeX = activeIndex === null ? null : x(activeIndex);
  const activeY = activeScore === null ? null : y(activeScore);

  const moveFocus = (from: number, offset: number | 'first' | 'last') => {
    const position = measuredIndexes.indexOf(from);
    const nextPosition = offset === 'first' ? 0 : offset === 'last' ? measuredIndexes.length - 1
      : Math.min(measuredIndexes.length - 1, Math.max(0, position + offset));
    const next = measuredIndexes[nextPosition];
    if (next === undefined) return;
    setDismissed(false);
    setFocusedIndex(next);
    setRovingIndex(next);
    pointRefs.current[next]?.focus();
  };

  const onPointerMove = (event: ReactPointerEvent<SVGRectElement>) => {
    const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    const scale = rect && rect.width > 0 ? width / rect.width : 1;
    const pointerX = (event.clientX - (rect?.left ?? 0)) * scale;
    const nearest = measuredIndexes.reduce(
      (best, index) => Math.abs(x(index) - pointerX) < Math.abs(x(best) - pointerX) ? index : best,
      measuredIndexes[0],
    );
    setDismissed(false);
    setHoveredIndex(nearest);
  };

  const movement = activeIndex !== null && activeIndex > 0
    && activeScore !== null && points[activeIndex - 1]?.score !== null
    ? activeScore - (points[activeIndex - 1].score as number)
    : null;
  const tooltipWidth = Math.min(TOOLTIP_WIDTH, Math.max(160, width - 12));
  const tooltipGap = 14;
  const placeLeft = activeX !== null && activeX + tooltipGap + tooltipWidth > width;
  const tooltipLeft = activeX === null ? 0
    : Math.max(0, Math.min(width - tooltipWidth, placeLeft ? activeX - tooltipGap - tooltipWidth : activeX + tooltipGap));
  const tooltipTop = activeY === null ? 0
    : Math.min(Math.max(activeY - tooltipHeight / 2, 0), Math.max(0, CHART_HEIGHT - tooltipHeight));

  return (
    <section className="flex min-w-0 flex-col justify-between gap-[20px] rounded-[18px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-[16px] sm:p-[20px]">
      <div className="flex flex-wrap items-center justify-between gap-[10px]">
        <h3 className="text-[16px] font-bold text-[var(--insights-heading)]">{title}</h3>
        {range && <span className="inline-flex items-center gap-[6px] rounded-[9px] border border-[var(--exec-card-border)] bg-[var(--exec-chip-bg)] px-[10px] py-[7px] text-[11px] font-semibold text-[var(--exec-chip-text)]"><Calendar aria-hidden="true" className="size-[14px]" />{range}</span>}
      </div>

      <div ref={boxRef} className="w-full" style={{ height: CHART_HEIGHT }}>
      {measuredIndexes.length ? (
        <div className="relative w-full" style={{ height: CHART_HEIGHT }}>
          <svg
            role="group"
            aria-label={description}
            width={width}
            height={CHART_HEIGHT}
            viewBox={'0 0 ' + width + ' ' + CHART_HEIGHT}
            className="block overflow-visible"
            data-testid="executive-trend-chart"
          >
            <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={lineColor} stopOpacity={0.2} /><stop offset="100%" stopColor={lineColor} stopOpacity={0.015} /></linearGradient></defs>
            {ticks.map((tick) => <line key={'grid-' + tick} x1={plot.left} x2={plot.right} y1={y(tick)} y2={y(tick)} stroke="var(--exec-card-border)" strokeOpacity={0.7} />)}
            {ticks.map((tick) => (
              <text key={tick} x={plot.left - 8} y={y(tick)} dominantBaseline="middle" textAnchor="end" fontSize={10} fill="var(--text-muted)" data-testid="executive-trend-tick">
                {tick + '%'}
              </text>
            ))}
            <path d={'M' + plot.left + ' ' + plot.bottom + ' H' + plot.right} stroke="var(--exec-card-border)" strokeWidth={1} data-testid="executive-trend-baseline" />
            <path d={'M' + plot.left + ' ' + y(target) + ' H' + plot.right} stroke="var(--text-muted)" strokeOpacity={0.75} strokeWidth={1.25} strokeDasharray="4 4" fill="none" data-testid="executive-trend-target" />
            <text x={plot.right} y={y(target) - 6} textAnchor="end" fontSize={10} fontWeight={600} fill="var(--text-muted)" data-testid="executive-trend-target-label">
              {'Target ' + target.toFixed(0) + '%'}
            </text>
            {actualSegments.map((segment, index) => segment.length > 1 && (
              <path key={'area-' + index} d={smoothPath(segment, x, y) + ' L' + x(segment[segment.length - 1].index).toFixed(1) + ' ' + plot.bottom + ' L' + x(segment[0].index).toFixed(1) + ' ' + plot.bottom + ' Z'} fill={`url(#${gradientId})`} pointerEvents="none" data-testid="executive-trend-area" />
            ))}
            {activeX !== null && (
              <line data-testid="executive-trend-crosshair" x1={activeX} x2={activeX} y1={plot.top} y2={plot.bottom} stroke="var(--exec-card-border)" strokeWidth={1} pointerEvents="none" />
            )}
            {actualSegments.map((segment, index) => segment.length > 1 && (
              <path key={'actual-' + index} d={smoothPath(segment, x, y)} stroke={lineColor} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" fill="none" data-series="actual" data-testid="executive-trend-series" />
            ))}
            {comparisonSegments.map((segment, index) => segment.length > 1 && (
              <path key={'comparison-' + index} d={straightPath(segment, x, y)} stroke="var(--exec-comparison-line)" strokeWidth={1.75} strokeDasharray="2 3" strokeLinecap="round" fill="none" data-series="comparison" data-testid="executive-trend-series" />
            ))}
            {points.map((point, index) => point.comparison_score !== null && Number.isFinite(point.comparison_score) && (
              <circle key={point.period.key + '-comparison'} cx={x(index)} cy={y(point.comparison_score)} r={2.5} fill="var(--exec-comparison-line)" />
            ))}
            {points.map((point, index) => point.score !== null && Number.isFinite(point.score) && (
              <g
                key={point.period.key}
                ref={(node) => { pointRefs.current[index] = node; }}
                role="img"
                tabIndex={index === tabStop ? 0 : -1}
                aria-label={shortMonth(point.period) + ': score ' + fmtScore(point.score) + ', target ' + fmtScore(point.target)
                  + (point.comparison_score !== null ? ', ' + (comparisonLabel || 'comparison') + ' ' + fmtScore(point.comparison_score) : '')
                  + (point.measured_records !== undefined ? ', ' + point.measured_records + ' measured records' : '')}
                data-testid={'executive-trend-point-' + point.period.key}
                className="group outline-none"
                onFocus={() => {
                  setDismissed(false);
                  setFocusedIndex(index);
                  setRovingIndex(index);
                }}
                onBlur={() => setFocusedIndex((current) => current === index ? null : current)}
                onKeyDown={(event) => {
                  const keys: Record<string, number | 'first' | 'last'> = {
                    ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1, Home: 'first', End: 'last',
                  };
                  if (event.key === 'Escape') {
                    setHoveredIndex(null);
                    setDismissed(true);
                  } else if (event.key in keys) {
                    event.preventDefault();
                    moveFocus(index, keys[event.key]);
                  }
                }}
              >
                <circle
                  cx={x(index)}
                  cy={y(point.score)}
                  r={8}
                  fill="none"
                  stroke="var(--insights-heading)"
                  strokeOpacity={0.55}
                  strokeWidth={1.5}
                  className="opacity-0 transition-opacity group-focus-visible:opacity-100"
                  pointerEvents="none"
                  data-testid="executive-trend-focus-ring"
                />
                <circle
                  cx={x(index)}
                  cy={y(point.score)}
                  r={activeIndex === index ? 5.5 : 4}
                  fill={lineColor}
                  stroke="var(--bg-surface)"
                  strokeWidth={2.5}
                />
              </g>
            ))}
            {points.map((point, index) => (
              <text key={point.period.key + '-label'} x={x(index)} y={CHART_HEIGHT - 7} textAnchor="middle" fontSize={10} fill="var(--text-muted)">
                {shortMonth(point.period)}
              </text>
            ))}
            <rect
              data-testid="executive-trend-hover-area"
              x={plot.left}
              y={0}
              width={Math.max(0, plot.right - plot.left)}
              height={plot.bottom}
              fill="transparent"
              onPointerMove={onPointerMove}
              onPointerDown={onPointerMove}
              onPointerLeave={() => setHoveredIndex(null)}
            />
          </svg>

          {activePoint && activeScore !== null && activeIndex !== null && activeY !== null && (
            <div
              ref={tooltipRef}
              aria-hidden="true"
              data-testid="executive-trend-tooltip"
              data-placement={placeLeft ? 'left' : 'right'}
              className="pointer-events-none absolute z-10 rounded-[12px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-[12px] py-[9px] shadow-[0_10px_24px_rgba(15,23,42,0.16)]"
              style={{ width: tooltipWidth, left: tooltipLeft, top: tooltipTop }}
            >
              <p className="mb-[6px] border-b border-[var(--insights-row-border)] pb-[5px] text-[11px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                {shortMonth(activePoint.period) + ' ' + activePoint.period.year}
              </p>
              <div className="flex items-center justify-between gap-3 text-[12px]">
                <span className="inline-flex items-center gap-[7px] font-medium text-[var(--text-secondary)]"><span className="size-[8px] rounded-full" style={{ background: lineColor }} />Score</span>
                <strong className="font-semibold tabular-nums text-[var(--insights-heading)]">{fmtScore(activeScore)}</strong>
              </div>
              {activePoint.comparison_score !== null && (
                <div className="mt-[3px] flex items-center justify-between gap-3 text-[12px]">
                  <span className="inline-flex items-center gap-[7px] font-medium text-[var(--text-secondary)]"><span className="size-[8px] rounded-full bg-[var(--exec-comparison-line)]" />{comparisonLabel || 'Comparison'}</span>
                  <strong className="font-semibold tabular-nums text-[var(--insights-heading)]">{fmtScore(activePoint.comparison_score)}</strong>
                </div>
              )}
              <div className="mt-[3px] flex items-center justify-between gap-3 text-[12px]">
                <span className="inline-flex items-center gap-[7px] font-medium text-[var(--text-secondary)]">
                  <svg width="10" height="4" viewBox="0 0 10 4"><path d="M0 2H4M6 2H10" stroke="var(--text-muted)" strokeWidth={2} /></svg>
                  Target
                </span>
                <strong className="font-semibold tabular-nums text-[var(--insights-heading)]">{fmtScore(activePoint.target)}</strong>
              </div>
              {activePoint.measured_records !== undefined && (
                <p className="mt-[5px] text-[11px] text-[var(--text-muted)]">
                  {activePoint.measured_records.toLocaleString() + ' measured record' + (activePoint.measured_records === 1 ? '' : 's')}
                </p>
              )}
              {movement !== null && (
                <p className="mt-[3px] text-[11px] font-semibold" style={{ color: movement > 0 ? 'var(--insights-positive)' : movement < 0 ? 'var(--insights-negative)' : 'var(--text-muted)' }}>
                  {formatMovement(movement) + ' vs ' + shortMonth(points[activeIndex - 1].period)}
                </p>
              )}
              {activePoint.basis_context?.message && (
                <p className="mt-[5px] whitespace-normal break-words text-[11px] leading-4 text-[var(--text-secondary)]">{activePoint.basis_context.message}</p>
              )}
            </div>
          )}
        </div>
      ) : (
        <div data-testid="executive-trend-empty" className="flex w-full flex-col items-center justify-center gap-[6px] rounded-[8px] border border-dashed border-[var(--exec-card-border)] px-6 text-center" style={{ height: CHART_HEIGHT }}>
          <LineChart aria-hidden="true" className="size-[20px] text-[var(--text-faint)]" strokeWidth={1.5} />
          <p className="text-[12px] font-semibold text-[var(--insights-heading)]">No trend data for this scope</p>
          <p className="max-w-[260px] text-[11px] text-[var(--text-muted)]">No measured score in the last six months.</p>
        </div>
      )}
      </div>

      <div className="flex flex-wrap items-center gap-[14px] text-[12px] text-[var(--text-secondary)]">
        <span className="inline-flex items-center gap-[6px]"><span className="size-[9px] rounded-full" style={{ background: lineColor }} />Score</span>
        {hasComparison && comparisonLabel && (
          <span className="inline-flex items-center gap-[6px]"><span className="h-0 w-[14px] border-t-2 border-dotted border-[var(--exec-comparison-line)]" />{comparisonLabel}</span>
        )}
        <span className="inline-flex items-center gap-[6px]"><span className="h-0 w-[14px] border-t border-dashed border-[var(--text-muted)]" />Target {target}%</span>
      </div>
      <BasisComparisonNote messages={[points[points.length - 1]?.basis_context?.message]} />
    </section>
  );
}
