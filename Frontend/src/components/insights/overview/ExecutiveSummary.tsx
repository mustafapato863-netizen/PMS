import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowDownRight, ArrowUpRight, Calendar, Info, Link2 } from 'lucide-react';
import type { InsightExecutiveStory, InsightKpiTrend, InsightsWorkspace } from '../../../features/insights/types';
import { GradeBadge } from './InsightsOverviewPrimitives';
import { buildPerformanceTrend, cleanScope, formatPercent, formatSignedPercent, priorityFocusText, type TrendPoint } from './insightsOverviewModel';

const PLOT = { left: 40, right: 384, top: 10, bottom: 140, firstX: 68, lastX: 351.3 } as const;

function PerformanceTrendChart({ points, kpiLabel }: { points: TrendPoint[]; kpiLabel: string | null }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);
  const [pinnedIndex, setPinnedIndex] = useState<number | null>(null);
  // Escape hides the tooltip without moving keyboard focus off the point.
  const [dismissed, setDismissed] = useState(false);
  const [rovingIndex, setRovingIndex] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const pointRefs = useRef<Array<SVGGElement | null>>([]);

  // While a point is pinned, Escape anywhere or a click outside the chart
  // dismisses it (QA BUG-1).
  useEffect(() => {
    if (pinnedIndex === null) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setPinnedIndex(null);
      setHoveredIndex(null);
      setDismissed(true);
    };
    const onPointerDown = (event: Event) => {
      if (containerRef.current && event.target instanceof Node && containerRef.current.contains(event.target)) return;
      setPinnedIndex(null);
      setHoveredIndex(null);
    };
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('touchstart', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('touchstart', onPointerDown);
    };
  }, [pinnedIndex]);

  const measured = points.filter((point) => point.actual !== null);
  if (!points.length || !measured.length) {
    return (
      <div className="grid h-[166px] place-items-center rounded-[8px] text-center text-[12px] text-[var(--text-muted)]">
        No six-month KPI trend is available for this scope.
      </div>
    );
  }
  const maxActual = Math.max(...measured.map((point) => point.actual ?? 0));
  const yMax = Math.max(125, Math.ceil(maxActual / 25) * 25);
  const y = (value: number) => PLOT.bottom - (Math.min(value, yMax) / yMax) * (PLOT.bottom - PLOT.top);
  const step = points.length > 1 ? (PLOT.lastX - PLOT.firstX) / (points.length - 1) : 0;
  const x = (index: number) => PLOT.firstX + index * step;
  const ticks = Array.from({ length: 6 }, (_, index) => (yMax / 5) * (5 - index));

  const actualSegments: Array<Array<{ index: number; value: number }>> = [];
  let segment: Array<{ index: number; value: number }> = [];
  points.forEach((point, index) => {
    if (point.actual === null) {
      if (segment.length > 1) actualSegments.push(segment);
      segment = [];
      return;
    }
    segment.push({ index, value: point.actual });
  });
  if (segment.length > 1) actualSegments.push(segment);

  const measuredIndexes = points.map((point, index) => (point.actual !== null ? index : -1)).filter((index) => index >= 0);
  // Roving tabindex: the chart is one tab stop; arrow keys move between points.
  const tabStop = [pinnedIndex, rovingIndex].find((index) => index !== null && measuredIndexes.includes(index))
    ?? measuredIndexes[measuredIndexes.length - 1];
  const activeIndex = dismissed ? null : (pinnedIndex ?? hoveredIndex ?? focusedIndex);
  const activePoint = activeIndex === null ? null : points[activeIndex];
  const activeValue = activePoint?.actual ?? null;
  const activeX = activeIndex === null ? null : x(activeIndex);
  const activeY = activeValue === null ? null : y(activeValue);
  const pinnedPoint = pinnedIndex === null ? null : points[pinnedIndex];

  const targetIndexes = points.map((point, index) => (point.target !== null ? index : -1)).filter((index) => index >= 0);
  const description = points
    .map((point) => `${point.label} ${point.actual === null ? 'no data' : `${point.actual.toFixed(1)}%`}`)
    .join(', ');
  const pointSummary = (point: TrendPoint) => `${point.label}: actual ${point.actual?.toFixed(1)}% of target${point.target !== null ? `, target ${point.target.toFixed(0)}%` : ''}`;

  const togglePin = (index: number) => {
    if (pinnedIndex === index) {
      // Unpinning must visibly close the tooltip even though the pointer
      // (or focus) is still on the point.
      setPinnedIndex(null);
      setHoveredIndex(null);
      setDismissed(true);
      return;
    }
    setDismissed(false);
    setPinnedIndex(index);
  };
  const moveFocus = (from: number, offset: number | 'first' | 'last') => {
    const position = measuredIndexes.indexOf(from);
    const nextPosition = offset === 'first'
      ? 0
      : offset === 'last'
        ? measuredIndexes.length - 1
        : Math.min(measuredIndexes.length - 1, Math.max(0, position + offset));
    const next = measuredIndexes[nextPosition];
    setRovingIndex(next);
    pointRefs.current[next]?.focus();
  };

  return (
    <div ref={containerRef} className="relative w-full">
      <svg
        role="group"
        aria-label={`Performance trend${kpiLabel ? ` for ${kpiLabel}` : ''}, % of target: ${description}. Use arrow keys to move between months and Enter to pin a month.`}
        viewBox="0 0 388 166"
        className="block h-auto w-full"
        data-testid="performance-trend-chart"
        onMouseLeave={() => setHoveredIndex(null)}
      >
      {ticks.map((tick, index) => {
        const gridY = PLOT.top + index * ((PLOT.bottom - PLOT.top) / 5);
        return (
          <g key={tick}>
            <path d={`M${PLOT.left} ${gridY}H${PLOT.right}`} stroke="var(--insights-row-border)" strokeDasharray={index === 5 ? undefined : '3 3'} />
            <text x={0} y={gridY} dominantBaseline="middle" fontSize={10} fill="var(--text-muted)">{`${Math.round(tick)}%`}</text>
          </g>
        );
      })}
      <path d={`M${PLOT.left} ${PLOT.top}V${PLOT.bottom}`} stroke="var(--insights-card-border)" />
      {targetIndexes.length > 0 && (
        <path
          data-testid="performance-trend-target"
          d={`M${x(targetIndexes[0]).toFixed(1)} ${y(100)}H${x(targetIndexes[targetIndexes.length - 1]).toFixed(1)}`}
          stroke="var(--insights-target)"
          strokeWidth={1.75}
          strokeDasharray="5 4"
          fill="none"
        />
      )}
      {activeX !== null && activeY !== null && (
        <line
          data-testid="performance-trend-crosshair"
          x1={activeX}
          x2={activeX}
          y1={PLOT.top}
          y2={PLOT.bottom}
          stroke="var(--insights-card-border)"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
          pointerEvents="none"
        />
      )}
      {actualSegments.map((segmentPoints) => {
        const d = segmentPoints.reduce((path, point, index) => {
          const pointX = x(point.index);
          const pointY = y(point.value);
          if (index === 0) return `M${pointX.toFixed(1)} ${pointY.toFixed(2)}`;
          const previous = segmentPoints[index - 1];
          const previousX = x(previous.index);
          const previousY = y(previous.value);
          const controlOffset = (pointX - previousX) / 3;
          return `${path} C${(previousX + controlOffset).toFixed(1)} ${previousY.toFixed(2)}, ${(pointX - controlOffset).toFixed(1)} ${pointY.toFixed(2)}, ${pointX.toFixed(1)} ${pointY.toFixed(2)}`;
        }, '');
        return (
          <path
            key={segmentPoints[0].index}
            d={d}
            stroke="var(--insights-accent)"
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
            fill="none"
          />
        );
      })}
      {points.map((point, index) => point.actual !== null && (
        <g
          key={point.key}
          ref={(node) => { pointRefs.current[index] = node; }}
          role="button"
          tabIndex={index === tabStop ? 0 : -1}
          aria-pressed={pinnedIndex === index}
          aria-label={pointSummary(point)}
          data-testid={`performance-trend-point-${point.key}`}
          className="cursor-pointer outline-none"
          // Mouse clicks pin without moving focus, so a stale focus can't
          // keep the tooltip open after unpinning (QA BUG-1).
          onMouseDown={(event) => event.preventDefault()}
          onMouseEnter={() => {
            setDismissed(false);
            setHoveredIndex(index);
          }}
          onMouseLeave={() => setHoveredIndex((current) => current === index ? null : current)}
          onFocus={() => {
            setDismissed(false);
            setFocusedIndex(index);
            setRovingIndex(index);
          }}
          onBlur={() => setFocusedIndex((current) => current === index ? null : current)}
          onClick={() => togglePin(index)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              setPinnedIndex(null);
              setHoveredIndex(null);
              setDismissed(true);
            } else if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              togglePin(index);
            } else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') {
              event.preventDefault();
              moveFocus(index, 1);
            } else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') {
              event.preventDefault();
              moveFocus(index, -1);
            } else if (event.key === 'Home') {
              event.preventDefault();
              moveFocus(index, 'first');
            } else if (event.key === 'End') {
              event.preventDefault();
              moveFocus(index, 'last');
            }
          }}
        >
          <circle cx={x(index)} cy={y(point.actual)} r={12} fill="transparent" pointerEvents="all" />
          {activeIndex === index && (
            <circle cx={x(index)} cy={y(point.actual)} r={7} fill="none" stroke="var(--insights-accent)" strokeOpacity={0.35} strokeWidth={2} />
          )}
          {focusedIndex === index && (
            // Keyboard focus ring, independent of the hover/pin halo
            // (QA BUG-2, WCAG 2.4.7 / 1.4.11: heading colour on surface).
            <circle
              data-testid="performance-trend-focus-ring"
              cx={x(index)}
              cy={y(point.actual)}
              r={9.5}
              fill="none"
              stroke="var(--insights-heading)"
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
              pointerEvents="none"
            />
          )}
          <circle
            cx={x(index)}
            cy={y(point.actual)}
            r={activeIndex === index ? 4.5 : 3.5}
            fill="var(--insights-accent)"
            stroke="var(--bg-surface)"
            strokeWidth={activeIndex === index ? 2 : 1.5}
          />
        </g>
      ))}
      {points.map((point, index) => (
        <text key={`${point.key}-label`} x={x(index)} y={150} dominantBaseline="hanging" textAnchor="middle" fontSize={10} fill="var(--text-muted)">{point.label}</text>
      ))}
      </svg>
      {/* Announce pin changes only; hover/focus are conveyed by the point labels. */}
      <span role="status" aria-live="polite" className="sr-only" data-testid="performance-trend-live">
        {pinnedPoint && pinnedPoint.actual !== null ? `Pinned ${pointSummary(pinnedPoint)}` : ''}
      </span>
      {activePoint && activeValue !== null && activeIndex !== null && activeY !== null && (
        <div
          aria-hidden="true"
          data-testid="performance-trend-tooltip"
          data-pinned={pinnedIndex === activeIndex ? 'true' : 'false'}
          className="pointer-events-none absolute z-10 w-[176px] rounded-[16px] border border-[var(--insights-card-border)] bg-[var(--bg-surface)] px-[14px] py-[10px] shadow-[0_10px_24px_rgba(15,23,42,0.16)]"
          style={{
            left: `${Math.min(68, Math.max(32, ((activeX ?? PLOT.firstX) / 388) * 100))}%`,
            top: `${(activeY / 166) * 100}%`,
            transform: activeY < 62 ? 'translate(-50%, 12px)' : 'translate(-50%, calc(-100% - 12px))',
          }}
        >
          <p className="mb-[6px] flex items-center justify-between border-b border-[var(--insights-row-border)] pb-[6px] text-[11px] font-extrabold uppercase tracking-[0.08em] text-[var(--text-muted)]">
            {activePoint.label}
            {pinnedIndex === activeIndex && <span className="text-[9px] font-bold tracking-[0.06em] text-[var(--insights-accent-text)]">Pinned</span>}
          </p>
          <div className="flex items-center justify-between gap-3 text-[12px]">
            <span className="inline-flex items-center gap-[7px] font-semibold text-[var(--text-secondary)]">
              <span className="size-[9px] rounded-full bg-[var(--insights-accent)]" />
              Actual
            </span>
            <strong className="font-bold tabular-nums text-[var(--insights-heading)]">{activeValue.toFixed(1)}%</strong>
          </div>
          {activePoint.target !== null && (
            <div className="mt-[4px] flex items-center justify-between gap-3 text-[12px]" data-testid="performance-trend-tooltip-target">
              <span className="inline-flex items-center gap-[7px] font-semibold text-[var(--text-secondary)]">
                <svg width="10" height="4" viewBox="0 0 10 4"><path d="M0 2H4M6 2H10" stroke="var(--insights-target)" strokeWidth={2} /></svg>
                Target
              </span>
              <strong className="font-bold tabular-nums text-[var(--insights-heading)]">{activePoint.target.toFixed(0)}%</strong>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PerformanceTrend({ trend, filterKey }: { trend: InsightKpiTrend | null | undefined; filterKey?: string }) {
  const points = buildPerformanceTrend(trend);
  const kpiLabel = trend?.kpi_label ?? null;
  const explanation = kpiLabel
    ? `Leading KPI "${kpiLabel}": actual as a percentage of target over the last six months (target = 100%).`
    : 'Six-month actual vs target for the leading KPI in this scope.';
  return (
    <div className="flex w-full min-w-0 shrink-0 flex-col gap-[10px] rounded-[12px] border border-[var(--insights-card-border)] bg-[var(--bg-surface)] px-[16px] pb-[14px] pt-[16px] xl:w-[420px]">
      <div className="flex w-full items-center gap-[6px]">
        <h3 className="text-[13px] font-semibold leading-normal text-[var(--insights-heading)]">Performance trend</h3>
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
      {kpiLabel && <p className="-mt-[4px] truncate text-[11px] text-[var(--text-muted)]" title={explanation}>Leading KPI · {kpiLabel} · % of target</p>}
      {/* Remount on any filter or series change so a pin never survives into a different scope. */}
      <PerformanceTrendChart key={`${filterKey ?? ''}|${trend?.kpi_key ?? ''}|${points.map((point) => point.key).join(',')}`} points={points} kpiLabel={kpiLabel} />
      <div className="flex w-full items-center justify-center gap-[20px] text-[12px] leading-normal text-[var(--text-secondary)]">
        <span className="inline-flex items-center gap-[6px]"><span aria-hidden="true" className="size-[8px] rounded-full bg-[var(--insights-accent)]" />Actual</span>
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
  filterKey,
}: {
  story: InsightExecutiveStory | null | undefined;
  comparison: InsightsWorkspace['comparison'];
  trend: InsightKpiTrend | null | undefined;
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
      <PerformanceTrend trend={trend} filterKey={filterKey} />
    </section>
  );
}
