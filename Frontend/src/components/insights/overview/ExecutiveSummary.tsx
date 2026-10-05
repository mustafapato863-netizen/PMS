import type { ReactNode } from 'react';
import { ArrowDownRight, ArrowUpRight, Calendar, Info, Link2 } from 'lucide-react';
import type { InsightExecutiveStory, InsightKpiTrend, InsightsWorkspace } from '../../../features/insights/types';
import { GradeBadge } from './InsightsOverviewPrimitives';
import { buildPerformanceTrend, cleanScope, formatPercent, formatSignedPercent, priorityFocusText, type TrendPoint } from './insightsOverviewModel';

const PLOT = { left: 40, right: 384, top: 10, bottom: 140, firstX: 68, lastX: 351.3 } as const;

function PerformanceTrendChart({ points, kpiLabel }: { points: TrendPoint[]; kpiLabel: string | null }) {
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

  const actualSegments: string[] = [];
  let segment: string[] = [];
  points.forEach((point, index) => {
    if (point.actual === null) {
      if (segment.length > 1) actualSegments.push(segment.join(' '));
      segment = [];
      return;
    }
    segment.push(`${segment.length ? 'L' : 'M'}${x(index).toFixed(1)} ${y(point.actual).toFixed(2)}`);
  });
  if (segment.length > 1) actualSegments.push(segment.join(' '));

  const targetIndexes = points.map((point, index) => (point.target !== null ? index : -1)).filter((index) => index >= 0);
  const description = points
    .map((point) => `${point.label} ${point.actual === null ? 'no data' : `${point.actual.toFixed(1)}%`}`)
    .join(', ');

  return (
    <svg
      role="img"
      aria-label={`Performance trend${kpiLabel ? ` for ${kpiLabel}` : ''}, % of target: ${description}`}
      viewBox="0 0 388 166"
      className="block h-auto w-full"
      data-testid="performance-trend-chart"
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
      {actualSegments.map((d) => (
        <path key={d} d={d} stroke="var(--insights-accent)" strokeWidth={2.25} strokeLinejoin="round" fill="none" />
      ))}
      {points.map((point, index) => point.actual !== null && (
        <circle key={point.key} cx={x(index)} cy={y(point.actual)} r={3.5} fill="var(--insights-accent)" stroke="var(--bg-surface)" strokeWidth={1.5}>
          <title>{`${point.label}: ${point.actual.toFixed(1)}% of target`}</title>
        </circle>
      ))}
      {points.map((point, index) => (
        <text key={`${point.key}-label`} x={x(index)} y={150} dominantBaseline="hanging" textAnchor="middle" fontSize={10} fill="var(--text-muted)">{point.label}</text>
      ))}
    </svg>
  );
}

function PerformanceTrend({ trend }: { trend: InsightKpiTrend | null | undefined }) {
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
      <PerformanceTrendChart points={points} kpiLabel={kpiLabel} />
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
}: {
  story: InsightExecutiveStory | null | undefined;
  comparison: InsightsWorkspace['comparison'];
  trend: InsightKpiTrend | null | undefined;
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
      <PerformanceTrend trend={trend} />
    </section>
  );
}
