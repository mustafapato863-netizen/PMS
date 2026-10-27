import { useId, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
} from 'recharts';
import { getGradeTone } from '../../constants/grades';

export interface SixMonthKpiPoint {
  month: string;
  periodKey: string;
  actual: number | null;
  target: number | null;
  actualFormatted: string;
  targetFormatted: string;
  metTarget: boolean | null;
}

export interface SixMonthKpiSeriesItem {
  id: string;
  kpiKey: string;
  name: string;
  shortName: string;
  unit: string;
  betterDirection: 'higher' | 'lower';
  actualDisplay: string;
  targetDisplay: string;
  achievementPct: number;
  gapLabel: string;
  diagnosis: string;
  structuralDiagnosis?: string;
  trend6Mo: SixMonthKpiPoint[];
}

interface ScoreTrendChartProps {
  data: Array<{ month: string; score: number; benchmarkScore?: number; isPeak?: boolean }>;
  targetScore?: number;
  benchmarkName?: string;
  mode?: 'actuals' | 'team_avg' | 'team_best' | 'personal_best';
}

interface TooltipEntry {
  value: number;
  color: string;
  dataKey: string;
  name: string;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string;
}

interface CustomDotProps {
  cx?: number;
  cy?: number;
  payload?: { isPeak?: boolean };
}

const CustomTooltip = ({ active, payload, label }: CustomTooltipProps) => {
  if (!active || !payload?.length) return null;

  return (
    <div className="bg-[var(--bg-surface-elevated)] border border-[var(--border-medium)] rounded-2xl px-4 py-3 shadow-xl text-sm min-w-[160px] backdrop-blur-md">
      <div className="text-xs text-[var(--text-muted)] font-extrabold uppercase tracking-widest mb-2 border-b border-[var(--border-light)] pb-1.5">
        {label}
      </div>
      {payload.map((entry, index) => {
        const score = entry.value;
        let color = entry.color;
        if (entry.dataKey === 'score') {
          color = getGradeTone(score).text;
        }

        return (
          <div key={index} className="flex justify-between items-center py-0.5">
            <span className="text-xs font-semibold text-[var(--text-secondary)] flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: entry.color }} />
              {entry.name}:
            </span>
            <span className="font-mono font-black text-sm ml-4" style={{ color }}>
              {score.toFixed(1)}%
            </span>
          </div>
        );
      })}
    </div>
  );
};

const CustomDot = (props: CustomDotProps) => {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null) return null;
  if (payload?.isPeak) {
    return (
      <g>
        <circle cx={cx} cy={cy} r={10} fill="var(--bg-surface)" stroke="#F59E0B" strokeWidth={2} />
        <text x={cx} y={cy} dy={3.5} textAnchor="middle" fontSize="12">
          🏆
        </text>
      </g>
    );
  }
  return (
    <circle
      cx={cx}
      cy={cy}
      r={4}
      fill="var(--color-meet)"
      stroke="var(--bg-surface)"
      strokeWidth={2}
    />
  );
};

function formatKpiAxisValue(value: number, unit: string): string {
  const kind = unit.trim().toLowerCase();
  if (kind === 'min' || kind === 'mins' || kind === 'minutes') {
    return `${value.toFixed(value >= 100 ? 0 : 1)} min`;
  }
  if (kind === 'aed' || kind === 'egp' || kind === 'usd') {
    return `${Math.round(value).toLocaleString('en-US')} ${unit.toUpperCase()}`;
  }
  if (kind === '%' || kind === 'percent' || kind === 'percentage' || kind.includes('%')) {
    return `${value >= 100 || Number.isInteger(value) ? Math.round(value) : value.toFixed(1)}%`;
  }
  if (kind === 'count' || kind === 'number' || kind === 'visits' || kind === 'hours') {
    return Math.round(value).toLocaleString('en-US');
  }
  return Number.isInteger(value) ? value.toLocaleString('en-US') : value.toFixed(1);
}

function buildSmoothCurvePath(coords: Array<{ x: number; y: number }>): string {
  if (!coords.length) return '';
  if (coords.length === 1) return `M ${coords[0].x.toFixed(1)} ${coords[0].y.toFixed(1)}`;
  return coords.reduce((acc, pt, idx) => {
    if (idx === 0) return `M ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`;
    const prev = coords[idx - 1];
    const dx = (pt.x - prev.x) / 3;
    return `${acc} C ${(prev.x + dx).toFixed(1)} ${prev.y.toFixed(1)}, ${(pt.x - dx).toFixed(1)} ${pt.y.toFixed(1)}, ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`;
  }, '');
}

/**
 * Interactive 6-Month KPI Trend component shared from the 360 Profile trend module.
 * Supports KPI switching, Actual vs Target comparison, higher/lower direction handling,
 * peak month detection (🏆), 6-month analytics summary strip, and interactive hover tooltips.
 */
export function ProfileKpiSixMonthTrend({
  kpis,
  selectedId,
  onSelectKpi,
}: {
  kpis: SixMonthKpiSeriesItem[];
  selectedId: string;
  onSelectKpi: (id: string) => void;
}) {
  const gradientId = useId().replace(/:/g, '');
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const selected = kpis.find((item) => item.id === selectedId) ?? kpis[0];
  if (!selected) return null;

  const points = selected.trend6Mo;
  const lowerBetter = selected.betterDirection === 'lower';

  const numericActuals = points
    .map((pt) => pt.actual)
    .filter((v): v is number => v !== null && Number.isFinite(v));
  const avgActual =
    numericActuals.length > 0
      ? numericActuals.reduce((sum, v) => sum + v, 0) / numericActuals.length
      : null;

  // Identify Peak Month (best actual according to direction)
  let peakIndex = -1;
  if (numericActuals.length > 0) {
    const bestValue = lowerBetter ? Math.min(...numericActuals) : Math.max(...numericActuals);
    peakIndex = points.findIndex((pt) => pt.actual === bestValue);
  }
  const peakPoint = peakIndex >= 0 ? points[peakIndex] : null;

  const evaluatedPoints = points.filter((pt) => pt.actual !== null && pt.metTarget !== null);
  const metCount = evaluatedPoints.filter((pt) => pt.metTarget === true).length;
  const totalEvaluated = evaluatedPoints.length || points.length;
  const isPartialWindow =
    evaluatedPoints.length > 0 && evaluatedPoints.length < points.length;

  // Chart geometry
  const width = 920;
  const height = 244;
  const pad = { l: 82, r: 34, t: 36, b: 38 };
  const allValues = points.flatMap((pt) =>
    [pt.actual, pt.target].filter((v): v is number => v !== null && Number.isFinite(v)),
  );
  const dataMin = allValues.length ? Math.min(...allValues) : 0;
  const dataMax = allValues.length ? Math.max(...allValues) : 100;
  const unitKind = selected.unit.trim().toLowerCase();
  const isPctUnit =
    unitKind === '%' ||
    unitKind === 'percent' ||
    unitKind === 'percentage' ||
    unitKind.includes('%');

  let min: number;
  let max: number;
  if (isPctUnit) {
    max = 100;
    min = dataMin >= 45 ? 40 : 0;
  } else {
    const rawSpan = dataMax - dataMin;
    const minSpan = Math.max(1, Math.abs(dataMax) * 0.35);
    const span = Math.max(rawSpan, minSpan);
    min = Math.max(0, dataMin - span * 0.5);
    max = dataMax + span * 0.2;
  }
  const domain = max - min || 1;
  const innerW = width - pad.l - pad.r;
  const innerH = height - pad.t - pad.b;

  const xAt = (idx: number) =>
    pad.l + (points.length <= 1 ? innerW / 2 : (idx / (points.length - 1)) * innerW);
  // Standard Y mapping (clamped to [min, max] so percentage charts top out strictly at 100%)
  const yAt = (value: number) => {
    const clamped = Math.max(min, Math.min(max, value));
    return pad.t + (1 - (clamped - min) / domain) * innerH;
  };
  const baseline = pad.t + innerH;

  const actualCoords = points
    .map((pt, idx) =>
      pt.actual === null ? null : { x: xAt(idx), y: yAt(pt.actual), idx, point: pt },
    )
    .filter(
      (item): item is { x: number; y: number; idx: number; point: SixMonthKpiPoint } =>
        item !== null,
    );

  const targetCoords = points
    .map((pt, idx) => (pt.target === null ? null : { x: xAt(idx), y: yAt(pt.target) }))
    .filter((item): item is { x: number; y: number } => item !== null);

  const smoothActual = buildSmoothCurvePath(actualCoords);
  const areaPath =
    actualCoords.length > 1
      ? `${smoothActual} L ${actualCoords[actualCoords.length - 1].x.toFixed(1)} ${baseline.toFixed(1)} L ${actualCoords[0].x.toFixed(1)} ${baseline.toFixed(1)} Z`
      : '';
  const targetPolyline = targetCoords.map((pt) => `${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(' ');

  const hoveredItem =
    hoveredIdx !== null ? actualCoords.find((c) => c.idx === hoveredIdx) ?? null : null;
  const hoveredPoint = hoveredIdx !== null ? points[hoveredIdx] ?? null : null;
  const hoveredX = hoveredIdx !== null ? xAt(hoveredIdx) : null;

  return (
    <div className="space-y-5" data-testid="profile-360-trend-container">
      {/* Top Bar: Selected KPI Title + Interactive 360-Profile KPI Switcher Pills */}
      <div className="flex flex-col gap-4 border-b border-slate-100 pb-5 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-md bg-blue-50 px-2.5 py-0.5 text-[11px] font-bold tracking-wider text-blue-700 uppercase">
              360° 6-Month Performance Trend
            </span>
            <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
              {lowerBetter ? '↓ Lower is better (Target ceiling)' : '↑ Higher is better (Target floor)'}
            </span>
            <span
              className={`rounded-full border px-2.5 py-0.5 text-[11px] font-bold ${
                selected.gapLabel === 'On target'
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-rose-200 bg-rose-50 text-rose-700'
              }`}
            >
              {selected.gapLabel}
            </span>
          </div>
          <h2
            id="role-trend-heading"
            className="mt-2 text-lg font-bold tracking-tight text-slate-900 sm:text-xl"
          >
            {selected.name}
          </h2>
        </div>

        {/* 360-Profile Style Segmented KPI Switcher */}
        {kpis.length > 1 && (
          <div
            role="tablist"
            aria-label="Switch KPI for 6-month trend"
            className="inline-flex flex-wrap items-center gap-1 rounded-2xl border border-slate-200/90 bg-slate-100/80 p-1 shadow-2xs"
          >
            {kpis.map((kpi) => {
              const active = kpi.id === selected.id;
              const onTarget = kpi.gapLabel === 'On target';
              return (
                <button
                  key={kpi.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  data-testid={`trend-kpi-switcher-${kpi.kpiKey}`}
                  onClick={() => {
                    setHoveredIdx(null);
                    onSelectKpi(kpi.id);
                  }}
                  className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold transition-all ${
                    active
                      ? 'border border-slate-200/80 bg-white text-blue-600 shadow-2xs'
                      : 'border border-transparent text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <span
                    className={`size-1.5 rounded-full ${
                      onTarget ? 'bg-emerald-500' : 'bg-rose-500'
                    }`}
                  />
                  <span>{kpi.shortName}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* 360-Profile 5-Metric Summary Strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 px-3.5 py-2.5">
          <div className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
            Latest Actual
          </div>
          <div
            className={`mt-0.5 text-base font-extrabold tabular-nums ${
              selected.gapLabel === 'On target' ? 'text-emerald-700' : 'text-rose-600'
            }`}
          >
            {selected.actualDisplay}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 px-3.5 py-2.5">
          <div className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
            Monthly Target
          </div>
          <div className="mt-0.5 text-base font-bold text-slate-800 tabular-nums">
            {selected.targetDisplay}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 px-3.5 py-2.5">
          <div className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
            6-Month Avg
          </div>
          <div className="mt-0.5 flex items-baseline gap-1.5 text-base font-bold text-slate-800 tabular-nums">
            <span>
              {avgActual !== null ? formatKpiAxisValue(avgActual, selected.unit) : selected.actualDisplay}
            </span>
            {isPartialWindow && (
              <span className="text-[11px] font-semibold text-slate-400">
                ({numericActuals.length} mo)
              </span>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 px-3.5 py-2.5">
          <div className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
            Peak Month
          </div>
          <div className="mt-0.5 text-sm font-bold text-amber-700 tabular-nums">
            {peakPoint ? `🏆 ${peakPoint.month} (${peakPoint.actualFormatted})` : '—'}
          </div>
        </div>

        <div className="col-span-2 rounded-xl border border-slate-200/80 bg-slate-50/60 px-3.5 py-2.5 sm:col-span-1">
          <div className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
            Months at Target
          </div>
          <div className="mt-0.5 flex items-baseline gap-1.5 text-base font-bold text-slate-800 tabular-nums">
            <span>
              {metCount} / {totalEvaluated}
            </span>
            {isPartialWindow && (
              <span className="text-[11px] font-semibold text-slate-400">
                measured
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Interactive 6-Month Line Chart with 360-Profile CustomTooltip & Peak Trophy */}
      <div className="relative rounded-xl border border-slate-200/75 bg-slate-50/30 p-3 sm:p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2 px-1 text-xs">
          <div className="flex items-center gap-5 font-semibold text-slate-600">
            <span className="inline-flex items-center gap-2">
              <span className="inline-block h-0.5 w-5 bg-blue-600" />
              <span>Actual ({selected.shortName})</span>
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="inline-block w-5 border-t-2 border-dashed border-amber-600" />
              <span>Target ({selected.targetDisplay})</span>
            </span>
            <span className="inline-flex items-center gap-1.5 text-slate-500">
              <span>🏆</span>
              <span>Best Month</span>
            </span>
          </div>
          <span className="text-[11px] font-medium text-slate-400">
            Hover any month to inspect Actual vs Target details
          </span>
        </div>

        <svg
          data-testid="role-kpi-chart"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`${selected.name} over 6 months. Actual ${selected.actualDisplay}. Target ${selected.targetDisplay}. ${
            lowerBetter ? 'Lower is better.' : 'Higher is better.'
          }`}
          className="h-60 w-full select-none"
          onMouseLeave={() => setHoveredIdx(null)}
        >
          <defs>
            <linearGradient id={`role-trend-grad-${gradientId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2563eb" stopOpacity="0.16" />
              <stop offset="100%" stopColor="#2563eb" stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Horizontal Gridlines & Y-Axis Labels */}
          {[0, 1 / 3, 2 / 3, 1].map((step) => {
            const value = min + domain * step;
            const y = yAt(value);
            return (
              <g key={step}>
                <line
                  x1={pad.l}
                  x2={width - pad.r}
                  y1={y}
                  y2={y}
                  stroke="#e2e8f0"
                  strokeDasharray={step === 0 ? undefined : '4 4'}
                  strokeWidth="1"
                />
                <text
                  x={pad.l - 12}
                  y={y + 4}
                  textAnchor="end"
                  fill="#64748b"
                  fontSize="11"
                  fontWeight="600"
                >
                  {formatKpiAxisValue(value, selected.unit)}
                </text>
              </g>
            );
          })}

          {/* Vertical Month Guides & Active Crosshair */}
          {points.map((pt, idx) => {
            const x = xAt(idx);
            const isHovered = hoveredIdx === idx;
            return (
              <line
                key={`v-${pt.periodKey}`}
                x1={x}
                x2={x}
                y1={pad.t}
                y2={baseline}
                stroke={isHovered ? '#93c5fd' : '#f1f5f9'}
                strokeWidth={isHovered ? '1.5' : '1'}
                strokeDasharray={isHovered ? '3 3' : undefined}
              />
            );
          })}

          {/* Gradient Area Fill under Actual Curve */}
          {areaPath && (
            <path
              d={areaPath}
              fill={`url(#role-trend-grad-${gradientId})`}
              data-series="actual-area"
            />
          )}

          {/* Target: Dashed Amber/Orange Line */}
          {targetCoords.length > 1 ? (
            <polyline
              data-series="target"
              fill="none"
              stroke="#d97706"
              strokeWidth="2"
              strokeDasharray="6 4"
              points={targetPolyline}
            />
          ) : targetCoords.length === 1 ? (
            <line
              data-series="target"
              x1={pad.l}
              x2={width - pad.r}
              y1={targetCoords[0].y}
              y2={targetCoords[0].y}
              stroke="#d97706"
              strokeWidth="2"
              strokeDasharray="6 4"
            />
          ) : null}

          {/* Actual: Smooth Solid Blue Curve */}
          {actualCoords.length >= 1 && (
            <path
              data-series="actual"
              fill="none"
              stroke="#2563eb"
              strokeWidth="2.75"
              strokeLinejoin="round"
              strokeLinecap="round"
              d={smoothActual}
            />
          )}

          {/* Unmeasured Month Markers ("No data") */}
          {points.map((pt, idx) => {
            if (pt.actual !== null) return null;
            const x = xAt(idx);
            return (
              <text
                key={`no-data-${pt.periodKey}`}
                data-testid={`no-data-marker-${pt.periodKey}`}
                x={x}
                y={baseline - 8}
                textAnchor="middle"
                fill="#cbd5e1"
                fontSize="10"
                fontWeight="600"
              >
                No data
              </text>
            );
          })}

          {/* Data Points + Peak Month Trophy + Value Callouts */}
          {actualCoords.map((item) => {
            const missed = item.point.metTarget === false;
            const isPeak = item.idx === peakIndex;
            const isHovered = hoveredIdx === item.idx;
            const labelY = item.y < 20 ? item.y + 20 : item.y - 13;

            return (
              <g key={item.point.periodKey}>
                {isPeak ? (
                  <g>
                    <circle
                      cx={item.x}
                      cy={item.y}
                      r={isHovered ? 10 : 8.5}
                      fill="#ffffff"
                      stroke="#f59e0b"
                      strokeWidth="2"
                    />
                    <text x={item.x} y={item.y} dy={3.5} textAnchor="middle" fontSize="10">
                      🏆
                    </text>
                  </g>
                ) : (
                  <circle
                    cx={item.x}
                    cy={item.y}
                    r={isHovered ? 6 : 4.5}
                    fill={missed ? '#e11d48' : '#2563eb'}
                    stroke="#ffffff"
                    strokeWidth="2"
                  />
                )}
                <text
                  x={item.x}
                  y={labelY}
                  textAnchor="middle"
                  fill={missed ? '#be123c' : '#1e40af'}
                  fontSize="10.5"
                  fontWeight="700"
                >
                  {item.point.actualFormatted}
                </text>
              </g>
            );
          })}

          {/* Month Labels */}
          {points.map((pt, idx) => (
            <text
              key={pt.periodKey}
              x={xAt(idx)}
              y={height - 10}
              textAnchor="middle"
              fill={hoveredIdx === idx ? '#1e40af' : pt.actual === null ? '#94a3b8' : '#475569'}
              fontSize="11.5"
              fontWeight={hoveredIdx === idx ? '700' : '600'}
            >
              {pt.month}
            </text>
          ))}

          {/* Interactive Hover Bands */}
          {points.map((pt, idx) => {
            const x = xAt(idx);
            const bandW = innerW / Math.max(1, points.length - 1);
            return (
              <rect
                key={`hover-${pt.periodKey}`}
                x={Math.max(pad.l, x - bandW / 2)}
                y={pad.t}
                width={bandW}
                height={innerH}
                fill="transparent"
                className="cursor-pointer"
                onMouseEnter={() => setHoveredIdx(idx)}
                onFocus={() => setHoveredIdx(idx)}
              />
            );
          })}
        </svg>

        {/* 360-Profile Floating Glass Tooltip on Hover */}
        {hoveredPoint && hoveredX !== null && (
          <div
            data-testid="role-kpi-trend-tooltip"
            style={{
              left: `${Math.min(82, Math.max(18, (hoveredX / width) * 100))}%`,
              top: '16px',
              transform: 'translateX(-50%)',
            }}
            className="pointer-events-none absolute z-20 min-w-[185px] rounded-2xl border border-slate-200/95 bg-white/95 px-4 py-3 text-xs shadow-xl backdrop-blur-md"
          >
            <div className="mb-1.5 flex items-center justify-between border-b border-slate-100 pb-1.5">
              <span className="font-extrabold tracking-wider text-slate-500 uppercase">
                {hoveredPoint.month} ({hoveredPoint.periodKey})
              </span>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                  hoveredItem === null
                    ? 'bg-slate-100 text-slate-600'
                    : hoveredPoint.metTarget === false
                    ? 'bg-rose-50 text-rose-700'
                    : 'bg-emerald-50 text-emerald-700'
                }`}
              >
                {hoveredItem === null
                  ? 'No Data'
                  : hoveredPoint.metTarget === false
                  ? 'Missed'
                  : 'Met Target'}
              </span>
            </div>
            {hoveredItem ? (
              <>
                <div className="flex items-center justify-between py-0.5">
                  <span className="flex items-center gap-1.5 font-semibold text-slate-600">
                    <span className="size-2 rounded-full bg-blue-600" />
                    Actual:
                  </span>
                  <span className="font-mono font-bold text-slate-900">
                    {hoveredPoint.actualFormatted}
                  </span>
                </div>
                <div className="flex items-center justify-between py-0.5">
                  <span className="flex items-center gap-1.5 font-semibold text-slate-600">
                    <span className="size-2 rounded-full bg-amber-500" />
                    Target:
                  </span>
                  <span className="font-mono font-bold text-slate-700">
                    {hoveredPoint.targetFormatted}
                  </span>
                </div>
              </>
            ) : (
              <div className="py-1 text-slate-500">
                No KPI data recorded in this month.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const ScoreTrendChart = ({
  data,
  targetScore = 80,
  benchmarkName = 'Benchmark',
}: ScoreTrendChartProps) => {
  if (!data || !data.length) {
    return (
      <div className="h-40 flex items-center justify-center text-[var(--text-muted)] text-sm font-medium">
        No historical data available.
      </div>
    );
  }

  const hasBenchmark = data.some((d) => d.benchmarkScore !== undefined);

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" vertical={false} />
        <XAxis
          dataKey="month"
          tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
          axisLine={false}
          tickLine={false}
          padding={{ left: 10, right: 10 }}
        />
        <YAxis
          tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
          axisLine={false}
          tickLine={false}
          domain={[0, 100]}
        />
        <Tooltip content={<CustomTooltip />} />

        {hasBenchmark && (
          <Legend
            verticalAlign="top"
            height={36}
            iconType="circle"
            wrapperStyle={{ fontSize: '12px', fontWeight: 500 }}
          />
        )}

        <ReferenceLine
          y={targetScore}
          stroke="var(--color-meet)"
          strokeDasharray="4 4"
          strokeOpacity={0.4}
          label={{
            value: `Target Threshold (${targetScore}%)`,
            position: 'insideTopLeft',
            fontSize: 12,
            fill: 'var(--color-meet)',
            fontWeight: 600,
            dy: -8,
          }}
        />

        {hasBenchmark && (
          <Line
            name={benchmarkName}
            type="monotone"
            dataKey="benchmarkScore"
            stroke="#8b5cf6"
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={{ fill: '#8b5cf6', r: 3, strokeWidth: 1, stroke: 'var(--bg-surface)' }}
            activeDot={{ r: 5, stroke: '#8b5cf6', strokeWidth: 2 }}
          />
        )}

        <Line
          name="Actual Score"
          type="monotone"
          dataKey="score"
          stroke="var(--color-meet)"
          strokeWidth={3}
          dot={<CustomDot />}
          activeDot={{ r: 6, stroke: 'var(--color-meet)', strokeWidth: 2 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
};

export default ScoreTrendChart;
