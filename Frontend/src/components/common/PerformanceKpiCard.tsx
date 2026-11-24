import { memo, useEffect, useId, useMemo, useState, type KeyboardEvent } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Minus, RotateCcw, RotateCw, TrendingDown, TrendingUp } from 'lucide-react';
import { getGradeTone } from '../../constants/grades';
import { gradeGradientVar } from '../executive/v1/gradeGradient';
import { formatPercentOfTargetLabel } from './performanceKpiProgress';

export type PerformanceKpiBadgeType = 'success' | 'warning' | 'danger' | 'neutral';

export interface KpiTrendSeriesPoint {
  month: string;
  actual: number | null;
  target: number | null;
}

interface PerformanceKpiCardProps {
  icon: LucideIcon;
  iconBgColor?: string;
  iconAccentColor?: string;
  label: string;
  value: string;
  detailLabel?: string;
  badgeText?: string;
  badgeType?: PerformanceKpiBadgeType;
  trendDelta?: number | null;
  trendUnit?: string;
  /** Replaces the default "+1.2% MoM" line, e.g. "−0.94 pts vs Aug". */
  trendText?: string;
  /** Muted line shown when there is no change, so the card keeps its layout. */
  trendEmptyText?: string;
  isTrendGood?: boolean;
  progressPercent?: number | null;
  /** Score points from the caller. 0.7 means 0.7%, including values at or below 1. */
  contribution?: number | null;
  weight?: number | null;
  weightLabel?: string;
  /** Display-only KPI. The card keeps its value and target and shows no weight. */
  viewOnly?: boolean;
  targetValue?: string | number | null;
  /** Last 6 months Actual vs Target series. When provided, clicking the card smoothly flips 180° to show the trend. */
  trendSeries?: KpiTrendSeriesPoint[];
  /** Unit used to format values on the back-face 6-month trend chart. */
  trendSeriesUnit?: string;
  /** True when lower values are better (e.g., AHT, error rate, rejection rate). */
  trendLowerBetter?: boolean;
}

const BADGE_CLASSES: Record<PerformanceKpiBadgeType, string> = {
  success: 'border-emerald-500/25 bg-gradient-to-br from-emerald-500/12 to-teal-500/10 text-emerald-700 dark:text-emerald-300',
  warning: 'border-amber-500/25 bg-gradient-to-br from-amber-500/12 to-orange-500/10 text-amber-700 dark:text-amber-300',
  danger: 'border-rose-500/25 bg-gradient-to-br from-rose-500/12 to-pink-500/10 text-rose-600 dark:text-rose-300',
  neutral: 'border-slate-500/20 bg-slate-500/10 text-slate-600 dark:text-slate-300',
};

/**
 * Resolve the effective score (0–100) used to drive the Executive Summary
 * 95 / 90 / 80 / 70 grade-gradient tokens (A / B / C / D / E / N/A).
 */
function resolveCardGradeScore(
  progressPercent: number | null | undefined,
  badgeType: PerformanceKpiBadgeType,
): number | null {
  if (progressPercent !== undefined && progressPercent !== null && Number.isFinite(progressPercent)) {
    return Math.min(Math.max(progressPercent, 0), 100);
  }
  if (badgeType === 'success') return 100;
  if (badgeType === 'warning') return 85;
  if (badgeType === 'danger') return 65;
  return null;
}

function formatTargetBadgeValue(val: string | number): string {
  if (typeof val === 'number') {
    const rounded = Math.round(val);
    if (Math.abs(val - rounded) < 0.05) return `${rounded}`;
    return `${Math.round(val * 10) / 10}`;
  }
  const str = String(val).trim();
  const numMatch = str.match(/^([0-9]+(?:\.[0-9]+)?)\s*(%?)$/);
  if (numMatch) {
    const num = parseFloat(numMatch[1]);
    const unit = numMatch[2];
    // Percentages below 10 keep the decimals the caller formatted ("1.0%", "0.26%").
    if (unit === '%' && num < 10) return str;
    const rounded = Math.round(num);
    if (Math.abs(num - rounded) < 0.05) {
      return `${rounded}${unit}`;
    }
    return `${Math.round(num * 10) / 10}${unit}`;
  }
  return str;
}

function formatTrendPointValue(value: number | null, unit?: string): string {
  if (value === null || !Number.isFinite(value)) return '—';
  if (unit === 's') {
    const totalSeconds = Math.max(0, Math.round(value));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
  }
  if (unit === '%') {
    return `${value.toFixed(1)}%`;
  }
  if (unit === 'min') {
    return `${value.toFixed(1)}m`;
  }
  if (unit === 'currency') {
    return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : `${value.toFixed(0)}`;
  }
  if (Math.abs(value) >= 1000) {
    return `${(value / 1000).toFixed(1)}k`;
  }
  return Number.isInteger(value) ? `${value}` : value.toFixed(1);
}

function formatAxisTick(value: number, unit?: string): string {
  if (!Number.isFinite(value)) return '—';
  if (unit === '%') {
    return Number.isInteger(value) ? `${value}%` : `${value.toFixed(1)}%`;
  }
  return formatTrendPointValue(value, unit);
}

/**
 * Computes a proportional Y-axis domain so small Actual-vs-Target gaps
 * (e.g. 68.1% vs 75.0%) are not visually exaggerated into full-height cliffs.
 */
export function computeTrendYDomain(
  allValues: number[],
  unit?: string,
): { domainMin: number; domainMax: number; domainSpan: number } {
  if (allValues.length === 0) {
    return { domainMin: 0, domainMax: 100, domainSpan: 100 };
  }

  const rawMin = Math.min(...allValues);
  const rawMax = Math.max(...allValues);
  const rawSpan = rawMax - rawMin;

  if (unit === '%') {
    // Low-rate percentage KPIs (e.g. Error Rate 1.5% vs 3.0%): anchor cleanly at 0%.
    if (rawMax <= 20) {
      const domainMax = Math.ceil(Math.max(rawMax * 1.5, rawMax + 2, 5));
      return { domainMin: 0, domainMax, domainSpan: Math.max(domainMax, 1) };
    }

    // Standard 0–100% attainment KPIs: enforce at least a 40-point span on round 10% ticks.
    if (rawMax <= 100) {
      let domainMax = Math.min(100, Math.ceil((rawMax + 12) / 10) * 10);
      let domainMin = Math.max(0, Math.floor((rawMin - 15) / 10) * 10);
      if (domainMax - domainMin < 40) {
        const deficit = 40 - (domainMax - domainMin);
        domainMin = Math.max(0, Math.floor((domainMin - deficit) / 10) * 10);
        if (domainMax - domainMin < 40) {
          domainMax = Math.min(100, Math.ceil((domainMin + 40) / 10) * 10);
        }
      }
      if (domainMin <= 10) domainMin = 0;
      return {
        domainMin,
        domainMax,
        domainSpan: Math.max(domainMax - domainMin, 1),
      };
    }
  }

  // Non-percentage or >100% KPIs: maintain at least a 35% relative span around the max value.
  const minSpan = Math.max(Math.abs(rawMax) * 0.35, 10);
  const extraPad = Math.max(rawSpan * 0.25, (minSpan - rawSpan) / 2, 1);
  const domainMin = Math.max(0, rawMin - extraPad);
  const domainMax = rawMax + extraPad;
  return {
    domainMin,
    domainMax,
    domainSpan: Math.max(domainMax - domainMin, 1),
  };
}
function isPointOnTarget(actual: number | null, target: number | null, lowerBetter: boolean): boolean | null {
  if (actual === null || target === null || !Number.isFinite(actual) || !Number.isFinite(target)) return null;
  return lowerBetter ? actual <= target : actual >= target;
}

const MiniSixMonthTrend = memo(function MiniSixMonthTrend({
  label,
  series,
  unit,
  lowerBetter,
  badgeType,
  flipped,
}: {
  label: string;
  series: KpiTrendSeriesPoint[];
  unit?: string;
  lowerBetter: boolean;
  badgeType: PerformanceKpiBadgeType;
  flipped: boolean;
}) {
  const gradientId = useId().replace(/:/g, '');
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  useEffect(() => {
    if (!flipped) setHoveredIdx(null);
  }, [flipped]);

  const width = 256;
  const height = 104;
  const padLeft = 34;
  const padRight = 10;
  const padTop = 10;
  const padBottom = 20;
  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;

  const chart = useMemo(() => {
    const points = series.slice(-6);
    const measuredPoints = points.filter((point) => point.actual !== null && Number.isFinite(point.actual));

    let latestMeasuredIndex = -1;
    for (let i = points.length - 1; i >= 0; i -= 1) {
      if (points[i].actual !== null && Number.isFinite(points[i].actual)) {
        latestMeasuredIndex = i;
        break;
      }
    }

    const onTargetStats = measuredPoints.reduce(
      (acc, point) => {
        const ok = isPointOnTarget(point.actual, point.target, lowerBetter);
        if (ok !== null) {
          acc.comparable += 1;
          if (ok) acc.met += 1;
        }
        return acc;
      },
      { met: 0, comparable: 0 },
    );

    const allValues = points
      .flatMap((point) => [point.actual, point.target])
      .filter((value): value is number => value !== null && Number.isFinite(value));

    const { domainMin, domainMax, domainSpan } = computeTrendYDomain(allValues, unit);

    const xFor = (index: number) => {
      if (points.length <= 1) return padLeft + plotWidth / 2;
      return padLeft + (index / (points.length - 1)) * plotWidth;
    };
    const yFor = (val: number) => {
      const ratio = (val - domainMin) / domainSpan;
      return padTop + plotHeight - ratio * plotHeight;
    };

    const actualCoords = points
      .map((point, index) => (point.actual !== null && Number.isFinite(point.actual) ? { index, x: xFor(index), y: yFor(point.actual), point } : null))
      .filter((item): item is { index: number; x: number; y: number; point: KpiTrendSeriesPoint } => item !== null);

    const targetCoords = points
      .map((point, index) => (point.target !== null && Number.isFinite(point.target) ? { index, x: xFor(index), y: yFor(point.target), point } : null))
      .filter((item): item is { index: number; x: number; y: number; point: KpiTrendSeriesPoint } => item !== null);

    const actualPath = actualCoords.map((pt, i) => `${i === 0 ? 'M' : 'L'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(' ');
    const targetPath = targetCoords.map((pt, i) => `${i === 0 ? 'M' : 'L'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(' ');
    const areaPath = actualCoords.length >= 2
      ? `${actualPath} L ${actualCoords[actualCoords.length - 1].x.toFixed(1)} ${(padTop + plotHeight).toFixed(1)} L ${actualCoords[0].x.toFixed(1)} ${(padTop + plotHeight).toFixed(1)} Z`
      : '';

    return {
      points,
      measuredPoints,
      latestMeasuredIndex,
      onTargetStats,
      domainMax,
      domainSpan,
      xFor,
      yFor,
      actualCoords,
      actualPath,
      targetPath,
      areaPath,
    };
  }, [series, lowerBetter, unit, plotHeight, plotWidth]);

  const {
    points,
    measuredPoints,
    latestMeasuredIndex,
    onTargetStats,
    domainMax,
    domainSpan,
    xFor,
    yFor,
    actualCoords,
    actualPath,
    targetPath,
    areaPath,
  } = chart;

  const activeIdx = hoveredIdx !== null && hoveredIdx < points.length ? hoveredIdx : latestMeasuredIndex;
  const activePoint = activeIdx >= 0 ? points[activeIdx] : null;
  const hoveredPoint = hoveredIdx !== null && hoveredIdx < points.length ? points[hoveredIdx] : null;

  const hoveredXPercent = hoveredIdx !== null && points.length > 0
    ? Math.min(Math.max((xFor(hoveredIdx) / width) * 100, 18), 82)
    : 50;
  const hoveredMet = hoveredPoint
    ? isPointOnTarget(hoveredPoint.actual, hoveredPoint.target, lowerBetter)
    : null;

  return (
    <div className="flex h-full flex-col justify-between">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-xs font-bold text-[var(--text-primary)]" title={label}>
            {label}
          </p>
          <p className="text-[12px] font-medium text-[var(--text-muted)]">
            Last {Math.max(points.length, 6)} mo · Actual vs Target
          </p>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-[var(--pms-glass-stage-border)] bg-[var(--pms-glass-stage-bg)] px-2 py-0.5 text-[12px] font-semibold text-[var(--text-secondary)]">
          <RotateCcw size={11} aria-hidden="true" />
          Flip
        </span>
      </div>

      {activePoint ? (
        <div
          data-testid="kpi-trend-readout"
          className="mt-1 flex items-center justify-between gap-2 rounded-lg border border-[var(--pms-glass-stage-border)] bg-[var(--pms-glass-stage-bg)] px-2.5 py-1 text-[12px]"
        >
          <span className="font-bold text-[var(--text-primary)]">{activePoint.month}</span>
          <span className="flex items-center gap-2 font-semibold tabular-nums">
            <span className="text-sky-600 dark:text-sky-400">
              Act {formatTrendPointValue(activePoint.actual, unit)}
            </span>
            <span className="text-[var(--text-muted)]">/</span>
            <span className="text-amber-600 dark:text-amber-400">
              Tgt {formatTrendPointValue(activePoint.target, unit)}
            </span>
          </span>
        </div>
      ) : null}

      {measuredPoints.length > 0 ? (
        <div
          className="relative mt-1 w-full"
          aria-label={`${label} 6-month actual vs target trend`}
          onMouseLeave={() => setHoveredIdx(null)}
        >
          {/* Interactive Hover Tooltip showing Score & Target */}
          {hoveredPoint && hoveredIdx !== null && (
            <div
              role="tooltip"
              data-testid="kpi-trend-hover-tooltip"
              className="pointer-events-none absolute top-0 z-20 -translate-x-1/2 rounded-lg border border-[var(--pms-glass-card-border)] bg-[var(--bg-surface)] px-2.5 py-1.5 shadow-md"
              style={{ left: `${hoveredXPercent}%` }}
            >
              <div className="flex items-center justify-between gap-2.5 text-[12px] leading-tight">
                <span className="font-bold text-[var(--text-primary)]">{hoveredPoint.month}</span>
                {hoveredMet !== null && (
                  <span
                    className={`font-bold ${
                      hoveredMet
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : 'text-rose-600 dark:text-rose-400'
                    }`}
                  >
                    {hoveredMet ? 'On target' : 'Below'}
                  </span>
                )}
              </div>
              <div className="mt-0.5 flex items-center gap-2 whitespace-nowrap text-[12px] font-semibold tabular-nums leading-tight">
                <span className="text-sky-600 dark:text-sky-400">
                  Score {formatTrendPointValue(hoveredPoint.actual, unit)}
                </span>
                <span className="text-[var(--text-muted)]">·</span>
                <span className="text-amber-600 dark:text-amber-400">
                  Tgt {formatTrendPointValue(hoveredPoint.target, unit)}
                </span>
              </div>
            </div>
          )}

          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="h-[104px] w-full overflow-visible"
            role="img"
            aria-label={`${label} actual vs target trend chart`}
          >
            <defs>
              <linearGradient id={`kpi-area-${gradientId}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0EA5E9" stopOpacity="0.26" />
                <stop offset="100%" stopColor="#0EA5E9" stopOpacity="0.02" />
              </linearGradient>
            </defs>

            {/* Horizontal grid lines */}
            {[0, 0.5, 1].map((fraction) => {
              const y = padTop + plotHeight * fraction;
              const tickVal = domainMax - domainSpan * fraction;
              return (
                <g key={fraction}>
                  <line
                    x1={padLeft}
                    y1={y}
                    x2={width - padRight}
                    y2={y}
                    stroke="var(--border-light)"
                    strokeDasharray="3 3"
                    strokeWidth="1"
                  />
                  {fraction !== 0.5 && (
                    <text
                      x={padLeft - 4}
                      y={y + 3}
                      textAnchor="end"
                      fill="var(--text-muted)"
                      fontSize="8.5"
                      fontWeight="600"
                    >
                      {formatAxisTick(tickVal, unit)}
                    </text>
                  )}
                </g>
              );
            })}

            {/* Area fill under actual */}
            {areaPath && <path d={areaPath} fill={`url(#kpi-area-${gradientId})`} />}

            {/* Target dashed line */}
            {targetPath && (
              <path
                d={targetPath}
                fill="none"
                stroke="#F59E0B"
                strokeWidth="1.7"
                strokeDasharray="4 3"
                strokeLinecap="round"
              />
            )}

            {/* Actual solid line */}
            {actualPath && (
              <path
                d={actualPath}
                fill="none"
                stroke="#0284C7"
                strokeWidth="2.3"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}

            {/* Vertical hover crosshair guide */}
            {hoveredIdx !== null && (
              <line
                x1={xFor(hoveredIdx)}
                y1={padTop}
                x2={xFor(hoveredIdx)}
                y2={padTop + plotHeight}
                stroke="var(--insights-accent)"
                strokeDasharray="2.5 2.5"
                strokeWidth="1.2"
                opacity="0.7"
              />
            )}

            {/* Target point marker on hover */}
            {hoveredIdx !== null &&
              points[hoveredIdx]?.target !== null &&
              Number.isFinite(points[hoveredIdx]?.target) && (
                <circle
                  cx={xFor(hoveredIdx)}
                  cy={yFor(points[hoveredIdx].target as number)}
                  r={3.2}
                  fill="#F59E0B"
                  stroke="var(--bg-surface)"
                  strokeWidth="1.4"
                />
              )}

            {/* Data point markers */}
            {actualCoords.map(({ index, x, y, point }) => {
              const met = isPointOnTarget(point.actual, point.target, lowerBetter);
              const fill = met === true ? '#10B981' : met === false ? '#F43F5E' : '#0284C7';
              const isSelected = index === activeIdx;
              return (
                <g key={point.month} pointerEvents="none">
                  {isSelected && <circle cx={x} cy={y} r={6.5} fill={fill} opacity={0.22} />}
                  <circle cx={x} cy={y} r={isSelected ? 4 : 3} fill={fill} stroke="var(--bg-surface)" strokeWidth="1.5" />
                </g>
              );
            })}

            {/* Full-column interactive hover hit targets for every month */}
            {points.map((point, index) => {
              const cx = xFor(index);
              const prevX = index > 0 ? xFor(index - 1) : padLeft;
              const nextX = index < points.length - 1 ? xFor(index + 1) : width - padRight;
              const hitLeft = index === 0 ? padLeft - 6 : (prevX + cx) / 2;
              const hitRight = index === points.length - 1 ? width - padRight + 6 : (cx + nextX) / 2;
              return (
                <rect
                  key={`hit-${point.month}-${index}`}
                  data-testid={`kpi-trend-hit-${point.month}`}
                  x={hitLeft}
                  y={padTop - 4}
                  width={Math.max(hitRight - hitLeft, 12)}
                  height={plotHeight + padBottom + 4}
                  fill="transparent"
                  className="cursor-crosshair"
                  onMouseEnter={() => setHoveredIdx(index)}
                  onPointerEnter={() => setHoveredIdx(index)}
                >
                  <title>{`${point.month}: Score ${formatTrendPointValue(point.actual, unit)} · Target ${formatTrendPointValue(point.target, unit)}`}</title>
                </rect>
              );
            })}

            {/* X-axis month labels */}
            {points.map((point, index) => (
              <text
                key={`${point.month}-${index}`}
                x={xFor(index)}
                y={height - 4}
                textAnchor="middle"
                fill={index === activeIdx ? 'var(--text-primary)' : 'var(--text-muted)'}
                fontSize="9"
                fontWeight={index === activeIdx ? '700' : '600'}
                pointerEvents="none"
              >
                {point.month}
              </text>
            ))}
          </svg>
        </div>
      ) : (
        <div className="my-2 flex flex-1 items-center justify-center rounded-xl border border-dashed border-[var(--border-light)] px-3 py-4 text-center text-xs font-semibold text-[var(--text-muted)]">
          No 6-month trend history available yet.
        </div>
      )}

      <div className="mt-1 flex items-center justify-between border-t border-[var(--border-light)] pt-2 text-[12px] font-semibold">
        <span className="inline-flex items-center gap-2.5 text-[var(--text-muted)]">
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-sky-500" aria-hidden="true" />
            Actual
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="w-3 border-t-2 border-dashed border-amber-500" aria-hidden="true" />
            Target
          </span>
        </span>
        <span
          className="rounded-full px-2 py-0.5 text-[12px] font-bold"
          style={{
            background:
              onTargetStats.comparable > 0 && onTargetStats.met === onTargetStats.comparable
                ? 'var(--pms-grad-panel-pos)'
                : badgeType === 'danger'
                  ? 'var(--pms-grad-panel-neg)'
                  : 'var(--pms-grad-panel-info)',
            color:
              onTargetStats.comparable > 0 && onTargetStats.met === onTargetStats.comparable
                ? 'var(--pms-grade-a-text)'
                : badgeType === 'danger'
                  ? 'var(--pms-grade-e-text)'
                  : 'var(--insights-accent-text)',
          }}
        >
          {onTargetStats.comparable > 0
            ? `${onTargetStats.met}/${onTargetStats.comparable} on target`
            : `${measuredPoints.length} mo`}
        </span>
      </div>
    </div>
  );
});

const PerformanceKpiCard = memo(function PerformanceKpiCard({
  icon: Icon,
  iconBgColor = 'bg-indigo-600',
  iconAccentColor,
  label,
  value,
  detailLabel,
  badgeText,
  badgeType = 'neutral',
  trendDelta,
  trendUnit = '%',
  trendText,
  trendEmptyText,
  isTrendGood,
  progressPercent,
  contribution,
  weight,
  weightLabel = 'Weight',
  viewOnly = false,
  targetValue,
  trendSeries,
  trendSeriesUnit,
  trendLowerBetter = false,
}: PerformanceKpiCardProps) {
  const [flipped, setFlipped] = useState(false);

  useEffect(() => {
    if (viewOnly || weight === 0) return;
    if ((weight === undefined || weight === null) && import.meta.env.DEV) {
      console.warn(`[Missing Weight] KPI "${label}" is missing a weight config.`);
    }
  }, [label, viewOnly, weight]);

  const flippable = trendSeries !== undefined;

  const hasTrend = trendDelta !== undefined && trendDelta !== null && Number.isFinite(trendDelta);
  const stableTrend = hasTrend && trendDelta === 0;
  const trendDown = hasTrend && trendDelta < 0;
  const TrendIcon = stableTrend ? Minus : trendDown ? TrendingDown : TrendingUp;
  const trendIsGood = isTrendGood ?? (!trendDown && !stableTrend);
  const progressAvailable = progressPercent !== undefined
    && progressPercent !== null
    && Number.isFinite(progressPercent);
  const visualProgress = progressAvailable ? Math.min(Math.max(progressPercent, 0), 100) : 0;
  const progressLabel = progressAvailable ? formatPercentOfTargetLabel(progressPercent) : 'Target unavailable';
  const formattedTarget = targetValue !== undefined && targetValue !== null && targetValue !== ''
    ? formatTargetBadgeValue(targetValue)
    : '';
  const normalizedWeight = weight !== undefined && weight !== null
    ? (weight > 1 ? weight / 100 : weight)
    : null;
  // Callers already pass score points. A value at or below 1 is still points, not a fraction.
  const isViewOnly = viewOnly;
  const contributionPercent = isViewOnly || contribution === undefined || contribution === null
    ? null
    : Math.min(
      Math.max(contribution, 0),
      normalizedWeight !== null ? Math.max(normalizedWeight, 0) * 100 : 100,
    );

  const gradeScore = resolveCardGradeScore(progressPercent, badgeType);
  const gradeTone = getGradeTone(gradeScore);
  const accentGradient = gradeGradientVar(gradeScore);
  const cardSurfaceStyle = {
    backgroundImage: `radial-gradient(circle at 95% 6%, color-mix(in srgb, ${gradeTone.gauge} 13%, transparent) 0%, transparent 64%), var(--pms-glass-card-bg)`,
    borderColor: `color-mix(in srgb, ${gradeTone.gauge} 20%, var(--pms-glass-card-border))`,
  };

  const toggleFlip = () => {
    if (!flippable) return;
    setFlipped((prev) => !prev);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (!flippable) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      setFlipped((prev) => !prev);
    }
  };

  const frontContent = (
    <>
      <span
        aria-hidden="true"
        data-testid="kpi-card-accent-strip"
        className="pointer-events-none absolute inset-x-0 top-0 h-[3px]"
        style={{ background: accentGradient }}
      />

      <div className="relative flex items-start justify-between gap-2">
        <span
          data-kpi-icon-accent={iconAccentColor || undefined}
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white shadow-sm ${iconAccentColor ? '' : iconBgColor}`}
          style={iconAccentColor ? { backgroundColor: iconAccentColor } : undefined}
        >
          <Icon size={17} />
        </span>
        <div className="flex items-start gap-1.5">
          {badgeText ? (
            <span className={`flex flex-col items-end rounded-md border px-2 py-1 text-right text-xs font-semibold leading-4 ${BADGE_CLASSES[badgeType]}`}>
              <span className="whitespace-nowrap">{badgeText}</span>
              {formattedTarget && (
                <span className="whitespace-nowrap text-[11px] font-medium leading-4 opacity-80">{formattedTarget}</span>
              )}
            </span>
          ) : formattedTarget ? (
            <span className="text-[11px] font-semibold leading-4 text-[var(--text-secondary)]">{formattedTarget}</span>
          ) : null}
          {flippable && (
            <span
              aria-hidden="true"
              title="Click card to flip and view 6-month trend"
              className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[var(--pms-glass-stage-border)] bg-[var(--pms-glass-stage-bg)] text-[var(--text-muted)] opacity-75 transition-all group-hover:border-sky-400/50 group-hover:text-sky-600 group-hover:opacity-100 dark:group-hover:text-sky-400"
            >
              <RotateCw size={12} />
            </span>
          )}
        </div>
      </div>

      <div className="relative mt-3">
        <p className="truncate text-xs font-semibold text-[var(--text-muted)]" title={label}>
          {label}
        </p>
        <div className="mt-1 text-display-card font-bold leading-none tracking-tight text-[var(--text-primary)]">
          {value}
        </div>
        <div className="mt-1.5 flex min-h-5 items-center justify-between gap-2">
          <p className="min-w-0 truncate text-xs font-semibold text-[var(--text-secondary)]">
            {detailLabel}
          </p>
          {hasTrend && (
            <span className={`inline-flex shrink-0 items-center gap-1 text-xs font-semibold ${
              stableTrend
                ? 'text-[var(--text-muted)]'
                : trendIsGood
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-rose-600 dark:text-rose-500'
            }`}>
              <TrendIcon size={11} />
              <span>
                {trendText ?? (
                  <>{trendDelta > 0 ? '+' : ''}{trendDelta.toFixed(trendUnit === 's' ? 0 : 1)}{trendUnit} MoM</>
                )}
              </span>
            </span>
          )}
          {!hasTrend && trendEmptyText && (
            <span className="shrink-0 text-xs font-semibold text-[var(--text-muted)]">{trendEmptyText}</span>
          )}
        </div>
      </div>

      <div className="relative mt-2 border-t border-[var(--border-light)] pt-2">
        <div className="flex items-center gap-2">
          <div
            className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--bg-sunken)]"
            role="progressbar"
            aria-label={`${label} progress to target`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressAvailable ? visualProgress : undefined}
            aria-valuetext={progressAvailable ? progressLabel : 'Target progress unavailable'}
          >
            <div
              className="h-full rounded-full transition-[width] duration-500"
              style={{ width: `${visualProgress}%`, background: accentGradient }}
            />
          </div>
          <span className="min-w-[74px] text-right text-xs font-semibold text-[var(--text-muted)]">
            {progressLabel}
          </span>
        </div>
      </div>

      <div className="relative mt-2 flex items-center justify-between border-t border-[var(--border-light)] pt-2 text-xs font-semibold text-[var(--text-secondary)]">
        <span>
          Contribution
          <strong className="ml-1 font-bold text-[var(--text-primary)]">
            {contributionPercent !== null
              ? `${contributionPercent.toFixed(1)}%`
              : '—'}
          </strong>
        </span>
        <span>
          {isViewOnly ? (
            <strong className="font-bold text-[var(--text-primary)]">View</strong>
          ) : (
            <>
              {weightLabel}
              <strong className="ml-1 font-bold text-[var(--text-primary)]">
                {weight !== undefined && weight !== null ? `${(weight * 100).toFixed(0)}%` : '—'}
              </strong>
            </>
          )}
        </span>
      </div>
    </>
  );

  if (!flippable) {
    return (
      <article
        className="pms-glass-surface pms-glass-surface--interactive group relative flex flex-col justify-between overflow-hidden rounded-2xl p-4"
        style={cardSurfaceStyle}
      >
        {frontContent}
      </article>
    );
  }

  return (
    <article
      tabIndex={0}
      role="button"
      aria-pressed={flipped}
      aria-label={`${label}: ${flipped ? 'showing 6-month actual vs target trend, click to flip back' : `${value}, click to view 6-month actual vs target trend`}`}
      data-flippable="true"
      data-flipped={flipped ? 'true' : 'false'}
      onClick={toggleFlip}
      onKeyDown={handleKeyDown}
      className="pms-flip-scene group cursor-pointer rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
    >
      <div className={`pms-flip-inner h-full ${flipped ? 'is-flipped' : ''}`}>
        {/* Front Face */}
        <div
          aria-hidden={flipped}
          className="pms-flip-face pms-flip-face--front pms-glass-surface pms-glass-surface--interactive relative flex flex-col justify-between overflow-hidden rounded-2xl p-4"
          style={cardSurfaceStyle}
        >
          {frontContent}
        </div>

        {/* Back Face — 6-Month Actual vs Target Trend */}
        <div
          aria-hidden={!flipped}
          data-testid="kpi-card-trend-back"
          className="pms-flip-face pms-flip-face--back pms-glass-surface pms-glass-surface--interactive relative flex flex-col justify-between overflow-hidden rounded-2xl p-4"
          style={cardSurfaceStyle}
        >
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 top-0 h-[3px]"
            style={{ background: accentGradient }}
          />
          <MiniSixMonthTrend
            label={label}
            series={trendSeries}
            unit={trendSeriesUnit ?? trendUnit}
            lowerBetter={trendLowerBetter}
            badgeType={badgeType}
            flipped={flipped}
          />
        </div>
      </div>
    </article>
  );
});

export default PerformanceKpiCard;
