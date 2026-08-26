import './PageEnhancements.css';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertCircle, AlertTriangle, ArrowRight, ArrowUpRight,
  BadgeAlert, BarChart3, ChevronLeft, ChevronRight, ClipboardCheck, DatabaseZap,
  Download, Eye, Filter, Lightbulb, Loader2, PlusCircle, RefreshCw, SearchCheck, SearchX,
  Share2, ShieldAlert, Sparkles, Target, TrendingDown, UsersRound, Wrench, X, MapPinned,
} from 'lucide-react';
import InsightDetailDrawer from '../components/insights/InsightDetailDrawer';
import KpiSixMonthTrend from '../components/insights/KpiSixMonthTrend';
import PeopleContributionAnalysis from '../components/insights/PeopleContributionAnalysis';
import EmployeeActionModal from '../components/team/EmployeeActionModal';
import EmployeeRowActions from '../components/team/EmployeeRowActions';
import type { InsightFilters, InsightItem, InsightSeverity, InsightKpiOverview, InsightRoleSummary, InsightExecutiveStory, InsightKpiTrend, InsightPeopleContributionAnalysis } from '../features/insights/types';
import { useInsightsWorkspace } from '../hooks/api/useInsightsWorkspace';
import { PageLoadingSkeleton } from '../components/common/SkeletonLoader';
import { refreshPerformanceData, useTeamData, type TeamAgentRow } from '../hooks/usePerformanceData';
import { useActionStore } from '../hooks/useActionStore';
import { useUserRole } from '../context/RoleContext';
import type { PerformanceLevelFilter } from '../types';
import CustomDropdown from '../components/common/CustomDropdown';
import { API_BASE } from '../config';
import { waitForProcessingJob } from '../hooks/api/useProcessingJobs';

function FilterSelect({ label, value, onChange, options, allLabel }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  allLabel?: string;
}) {
  const dropdownOptions = [
    ...(allLabel ? [{ value: '', label: allLabel }] : []),
    ...options,
  ];
  return (
    <div className="min-w-0">
      <span className="sr-only">{label}</span>
      <CustomDropdown
        ariaLabel={label}
        value={value}
        options={dropdownOptions}
        onChange={(nextValue) => onChange(String(nextValue))}
        className="w-full"
        buttonClassName="min-h-11 w-full rounded-xl"
        size="lg"
      />
    </div>
  );
}

// Keep the executive-story component behind a small feature flag while the
// layout continues to evolve without changing the workspace contract.
const SHOW_EXECUTIVE_STORY = true;

const severityStyles: Record<InsightSeverity, string> = {
  critical: 'border-rose-200 bg-rose-50 text-rose-600 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-300',
  risk: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-300',
  opportunity: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-300',
  information: 'border-blue-200 bg-blue-50 text-blue-600 dark:border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-300',
};

const severityLabels: Record<InsightSeverity, string> = {
  critical: 'Critical', risk: 'At risk', opportunity: 'Opportunity', information: 'Data issue',
};

function cleanScope(value: string) {
  return value.replace(/Â/g, '');
}

function formatMetric(value: number | null, unit: string | null) {
  if (value === null) return 'N/A';
  if (unit === '%') return `${(Math.abs(value) <= 1 ? value * 100 : value).toFixed(1)}%`;
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ''}`;
}

function impactLabel(value: number | null) {
  if (value === null) return 'Operational';
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;
}

function pageWindow(currentPage: number, totalPages: number, windowSize = 5) {
  if (totalPages <= windowSize) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  const halfWindow = Math.floor(windowSize / 2);
  let start = Math.max(1, currentPage - halfWindow);
  let end = start + windowSize - 1;

  if (end > totalPages) {
    end = totalPages;
    start = Math.max(1, end - windowSize + 1);
  }

  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

function DriverChart({ drivers, onSelect, onHoverTooltip }: {
  drivers: Array<{ id: string; driver: string; scope: string; impact_points: number; direction: 'positive' | 'negative'; insight_id: string }>;
  onSelect: (id: string) => void;
  onHoverTooltip?: (tooltip: { text: string; x: number; y: number } | null) => void;
}) {
  const displayed = drivers.slice(0, 12);
  const maximum = Math.max(1, ...displayed.map((driver) => Math.abs(driver.impact_points)));

  if (!displayed.length) {
    return <div className="grid min-h-[360px] place-items-center px-6 text-center text-sm text-[var(--text-muted)]">No weighted score drivers match the selected scope.</div>;
  }

  return (
    <div className="space-y-3 px-5 pb-6 pt-4 md:px-7">
      <div className="grid grid-cols-[minmax(105px,0.8fr)_minmax(180px,2fr)] gap-3 text-[9px] font-extrabold uppercase tracking-wide text-[var(--text-faint)]">
        <span />
        <span className="grid grid-cols-2"><span className="text-center text-rose-500">Widening the gap</span><span className="text-center text-emerald-600">Closing the gap</span></span>
      </div>
      {displayed.map((driver) => {
        const width = `${Math.max(5, (Math.abs(driver.impact_points) / maximum) * 100)}%`;
        const positive = driver.direction === 'positive';
        return (
          <button
            key={driver.id}
            type="button"
            onClick={() => onSelect(driver.insight_id)}
            className="group grid w-full grid-cols-[minmax(105px,0.8fr)_minmax(180px,2fr)] items-center gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            aria-label={`${driver.driver} for ${cleanScope(driver.scope)}`}
          >
            <span
              className="min-w-0"
              onMouseEnter={(e) => {
                if (onHoverTooltip) {
                  const rect = e.currentTarget.getBoundingClientRect();
                  onHoverTooltip({
                    text: `${driver.driver} · ${cleanScope(driver.scope)}`,
                    x: rect.left + rect.width / 2,
                    y: rect.top - 8
                  });
                }
              }}
              onMouseLeave={() => onHoverTooltip && onHoverTooltip(null)}
            >
              <strong className="block truncate text-xs font-bold text-[var(--text-secondary)]">{driver.driver}</strong>
              <span className="mt-0.5 block truncate text-[10px] font-semibold text-[var(--text-faint)]">{cleanScope(driver.scope)}</span>
            </span>
            <span className="relative grid h-8 grid-cols-2">
              <span className="absolute inset-y-0 left-1/2 w-px bg-[var(--border-light)]" />
              <span className="flex min-w-0 items-center justify-end gap-1.5 pr-2">
                {!positive && <><span className="h-3.5 rounded-l-full bg-gradient-to-l from-rose-400 to-rose-500 transition-opacity group-hover:opacity-80" style={{ width }} /><strong className="shrink-0 rounded-md border border-rose-200 bg-rose-50 px-1.5 py-0.5 text-[10px] font-black text-rose-700 shadow-sm dark:border-rose-500/30 dark:bg-rose-500/15 dark:text-rose-200">{impactLabel(driver.impact_points)}</strong></>}
              </span>
              <span className="flex min-w-0 items-center gap-1.5 pl-2">
                {positive && <><strong className="shrink-0 rounded-md border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-black text-emerald-800 shadow-sm dark:border-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-200">{impactLabel(driver.impact_points)}</strong><span className="h-3.5 rounded-r-full bg-gradient-to-r from-emerald-500 to-teal-400 transition-opacity group-hover:opacity-80" style={{ width }} /></>}
              </span>
            </span>
          </button>
        );
      })}
      <div className="grid grid-cols-[minmax(105px,0.8fr)_minmax(180px,2fr)] gap-3 pt-2 text-[9px] text-[var(--text-faint)]"><span /><span className="grid grid-cols-3 border-t border-dashed border-[var(--border-light)] pt-2"><span>Negative</span><span className="text-center">0%</span><span className="text-right">Positive</span></span></div>
    </div>
  );
}

function InsightSpotlight({ insight, onOpen }: { insight: InsightItem | null; onOpen: () => void }) {
  if (!insight) return <div className="grid min-h-[360px] place-items-center px-7 text-center text-sm text-[var(--text-muted)]">Select an analysis to inspect its evidence.</div>;
  const Icon = insight.severity === 'critical' ? Target : insight.severity === 'risk' ? AlertTriangle : insight.severity === 'opportunity' ? Sparkles : DatabaseZap;
  const improving = insight.detail.current_value !== null && insight.detail.previous_value !== null && (
    insight.detail.direction === 'lower_better'
      ? insight.detail.current_value < insight.detail.previous_value
      : insight.detail.direction === 'higher_better' && insight.detail.current_value > insight.detail.previous_value
  );
  return (
    <div className="p-5 md:p-6">
      <div className="flex items-start gap-4">
        <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-2xl border ${severityStyles[insight.severity]}`}><Icon size={21} /></span>
        <div className="min-w-0">
          <span className={`inline-flex rounded-full border px-2 py-1 text-[9px] font-black uppercase ${severityStyles[insight.severity]}`}>{severityLabels[insight.severity]}</span>
          <h3 className="mt-2 text-base font-extrabold leading-6 text-[var(--text-primary)]">{insight.title}</h3>
        </div>
      </div>
      <p className="mt-4 text-sm leading-6 text-[var(--text-secondary)]">{insight.explanation}</p>
      <div className="mt-5 rounded-2xl bg-[var(--bg-sunken)] p-4">
        <p className="text-[10px] font-extrabold uppercase tracking-wide text-[var(--text-faint)]">Most affected</p>
        <p className="mt-1 text-sm font-bold text-[var(--text-primary)]">{cleanScope(insight.scope)}</p>
        <div className="mt-4 grid grid-cols-2 gap-4">
          <div><span className="text-[10px] text-[var(--text-muted)]">Current</span><strong className="mt-1 block text-sm text-[var(--text-primary)]">{formatMetric(insight.detail.current_value, insight.detail.unit)}</strong></div>
          <div><span className="text-[10px] text-[var(--text-muted)]">Target</span><strong className="mt-1 block text-sm text-[var(--text-primary)]">{formatMetric(insight.detail.target_value, insight.detail.unit)}</strong></div>
          <div><span className="text-[10px] text-[var(--text-muted)]">Score impact</span><strong className={`mt-1 block text-sm ${insight.impact_points !== null && insight.impact_points >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>{impactLabel(insight.impact_points)}</strong></div>
          <div><span className="text-[10px] text-[var(--text-muted)]">Trend</span><strong className={`mt-1 flex items-center gap-1 text-sm ${improving ? 'text-emerald-600' : 'text-[var(--text-primary)]'}`}>{improving && <TrendingDown size={14} />}{insight.trend_label}</strong></div>
        </div>
      </div>
      <div className="mt-5">
        <p className="text-[10px] font-extrabold uppercase tracking-wide text-[var(--text-faint)]">Recommended focus</p>
        <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">{insight.detail.recommended_focus}</p>
      </div>
      <button type="button" onClick={onOpen} className="mt-5 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-extrabold text-white hover:bg-blue-700"><Eye size={16} /> View KPI details</button>
    </div>
  );
}

function ExecutiveStoryCard({
  story,
  onScopeSelect,
}: {
  story: NonNullable<import('../features/insights/types').InsightsWorkspace['executive_story']>;
  onScopeSelect: (scope: string) => void;
}) {
  const confidenceLabel = story.confidence === 'high' ? 'High confidence' : story.confidence === 'partial' ? 'Partial coverage' : 'Low confidence';
  return (
    <section className="overflow-hidden rounded-2xl border border-blue-200/70 bg-gradient-to-br from-blue-50 via-white to-indigo-50 shadow-sm dark:border-blue-500/20 dark:from-blue-500/10 dark:via-slate-950/80 dark:to-indigo-500/10" aria-labelledby="executive-story-title">
      <div className="flex flex-col gap-4 p-5 md:p-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-blue-600 text-white shadow-sm shadow-blue-500/25"><Sparkles size={17} /></span>
            <span className="text-[10px] font-black uppercase tracking-[0.16em] text-blue-700 dark:text-blue-300">Executive story</span>
            <span className="rounded-full border border-blue-200 bg-white/70 px-2 py-1 text-[10px] font-bold text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-200">{confidenceLabel}</span>
          </div>
          <h2 id="executive-story-title" className="mt-3 max-w-4xl text-lg font-black leading-7 text-[var(--text-primary)]">{story.headline}</h2>
          <p className="mt-2 max-w-4xl text-sm leading-6 text-[var(--text-secondary)]">{story.recommended_focus}</p>
        </div>
        <div className="grid w-full shrink-0 grid-cols-2 gap-2 sm:grid-cols-4 lg:w-[520px]">
          <div className="rounded-xl border border-white/80 bg-white/75 p-3 dark:border-white/10 dark:bg-white/[0.06]"><span className="text-[10px] font-bold uppercase text-[var(--text-faint)]">Current</span><strong className="mt-1 block text-lg font-black text-[var(--text-primary)]">{story.current_score === null ? 'N/A' : `${story.current_score.toFixed(1)}%`}</strong></div>
          <div className="rounded-xl border border-white/80 bg-white/75 p-3 dark:border-white/10 dark:bg-white/[0.06]"><span className="text-[10px] font-bold uppercase text-[var(--text-faint)]">Gap</span><strong className={`mt-1 block text-lg font-black ${story.gap_points !== null && story.gap_points < 0 ? 'text-rose-600' : 'text-emerald-600'}`}>{story.gap_points === null ? 'N/A' : `${story.gap_points > 0 ? '+' : ''}${story.gap_points.toFixed(1)}%`}</strong></div>
          <div className="rounded-xl border border-white/80 bg-white/75 p-3 dark:border-white/10 dark:bg-white/[0.06]"><span className="text-[10px] font-bold uppercase text-[var(--text-faint)]">Movement</span><strong className={`mt-1 block text-lg font-black ${story.score_change !== null && story.score_change < 0 ? 'text-rose-600' : 'text-emerald-600'}`}>{story.score_change === null ? 'N/A' : `${story.score_change > 0 ? '+' : ''}${story.score_change.toFixed(1)}%`}</strong></div>
          <div className="rounded-xl border border-white/80 bg-white/75 p-3 dark:border-white/10 dark:bg-white/[0.06]"><span className="text-[10px] font-bold uppercase text-[var(--text-faint)]">Leading driver</span><strong className="mt-1 block truncate text-sm font-black text-[var(--text-primary)]" title={story.primary_driver || 'Not available'}>{story.primary_driver || 'Not available'}</strong><span className="mt-1 block text-[10px] font-semibold text-rose-600">{story.primary_driver_impact === null ? 'No measured impact' : impactLabel(story.primary_driver_impact)}</span></div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-blue-100/80 px-5 py-3 text-xs dark:border-blue-500/15 md:px-6">
        <span className="font-bold text-[var(--text-muted)]">Analysis path:</span>
        <span className="rounded-full bg-white/80 px-2.5 py-1 font-semibold text-[var(--text-secondary)] dark:bg-white/[0.06]">{story.scope_label}</span>
        {story.primary_scope && <button type="button" onClick={() => onScopeSelect(story.primary_scope!)} className="rounded-full bg-blue-600/10 px-2.5 py-1 font-bold text-blue-700 hover:bg-blue-600/15 dark:text-blue-200">{story.primary_scope} contribution {story.primary_scope_contribution_percent === null ? '' : `· ${story.primary_scope_contribution_percent.toFixed(1)}%`}</button>}
        {story.primary_driver && <span className="rounded-full bg-rose-500/10 px-2.5 py-1 font-bold text-rose-700 dark:text-rose-200">Driver: {story.primary_driver}</span>}
      </div>
    </section>
  );
}

function ReportReference({
  story,
  trend,
  people,
  onOpenEmployee,
}: {
  story: InsightExecutiveStory | null | undefined;
  trend: InsightKpiTrend | null | undefined;
  people: InsightPeopleContributionAnalysis | null | undefined;
  onOpenEmployee: (employeeId: string, performanceLevel: string) => void;
}) {
  const leadingKpi = trend?.kpi_label || story?.primary_driver || 'No leading KPI identified';
  const latestPoint = [...(trend?.points || [])].reverse().find((point) => point.actual_value !== null) || null;
  const negativeRows = (people?.rows || [])
    .filter((row) => row.classification === 'negative')
    .slice(0, 3);

  if (!trend && !people && !story?.primary_driver) return null;

  return (
    <section className="overflow-hidden rounded-2xl border border-amber-200/70 bg-gradient-to-br from-amber-50/80 via-white to-rose-50/60 shadow-sm dark:border-amber-500/20 dark:from-amber-500/10 dark:via-slate-950/80 dark:to-rose-500/10" aria-labelledby="report-reference-title">
      <header className="flex flex-col gap-2 border-b border-amber-200/70 px-5 py-4 md:flex-row md:items-center md:justify-between dark:border-amber-500/15">
        <div>
          <div className="flex items-center gap-2"><span className="grid h-8 w-8 place-items-center rounded-lg bg-amber-500/15 text-amber-700 dark:text-amber-300"><Target size={16} /></span><h2 id="report-reference-title" className="text-lg font-extrabold text-[var(--text-primary)]">Report reference</h2></div>
          <p className="mt-1 text-xs text-[var(--text-muted)]">The leading KPI, its six-period movement, and the people behind the current gap.</p>
        </div>
        <span className="rounded-full border border-amber-200 bg-white/70 px-3 py-1 text-[10px] font-extrabold uppercase tracking-wide text-amber-700 dark:border-amber-500/25 dark:bg-white/[0.06] dark:text-amber-300">Decision evidence</span>
      </header>

      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(250px,0.8fr)_minmax(0,1.4fr)]">
        <article className="rounded-xl border border-amber-200/70 bg-white/75 p-4 dark:border-amber-500/20 dark:bg-white/[0.04]">
          <p className="text-[10px] font-black uppercase tracking-[0.14em] text-rose-700 dark:text-rose-300">Leading KPI pulling the score down</p>
          <h3 className="mt-2 text-xl font-black text-[var(--text-primary)]">{leadingKpi}</h3>
          <p className="mt-1 text-xs font-semibold text-[var(--text-muted)]">{trend?.direction === 'lower_better' ? 'Lower is better' : trend?.direction === 'higher_better' ? 'Higher is better' : 'Configured scoring direction'}</p>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div><span className="text-[10px] font-bold uppercase text-[var(--text-faint)]">Latest actual</span><strong className="mt-1 block text-lg font-black text-[var(--text-primary)]">{latestPoint ? formatMetric(latestPoint.actual_value, trend?.unit || null) : 'N/A'}</strong></div>
            <div><span className="text-[10px] font-bold uppercase text-[var(--text-faint)]">Target</span><strong className="mt-1 block text-lg font-black text-[var(--text-primary)]">{latestPoint ? formatMetric(latestPoint.target_value, trend?.unit || null) : 'N/A'}</strong></div>
          </div>
          <p className="mt-4 border-t border-amber-200/60 pt-3 text-xs font-bold text-rose-700 dark:border-amber-500/15 dark:text-rose-300">Weighted gap: {story?.primary_driver_impact === null || story?.primary_driver_impact === undefined ? 'N/A' : impactLabel(-Math.abs(story.primary_driver_impact))}</p>
        </article>

        <article className="rounded-xl border border-rose-200/70 bg-white/75 p-4 dark:border-rose-500/20 dark:bg-white/[0.04]">
          <div className="flex items-start justify-between gap-3"><div><p className="text-[10px] font-black uppercase tracking-[0.14em] text-rose-700 dark:text-rose-300">People to review</p><h3 className="mt-1 text-base font-black text-[var(--text-primary)]">Employees behind the KPI gap</h3></div><UsersRound size={17} className="text-rose-600" /></div>
          {negativeRows.length ? (
            <div className="mt-3 divide-y divide-rose-200/60 dark:divide-rose-500/15">
              {negativeRows.map((row) => (
                <button key={`${row.team}-${row.employee_id}-${row.performance_level}-${row.position}`} type="button" onClick={() => onOpenEmployee(row.employee_id, row.performance_level)} className="grid w-full grid-cols-[minmax(0,1.1fr)_auto_auto] items-center gap-3 py-3 text-left transition hover:bg-rose-500/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
                  <span className="min-w-0"><strong className="block truncate text-xs font-extrabold text-[var(--text-primary)]">{row.employee_name}</strong><span className="mt-0.5 block truncate text-[10px] text-[var(--text-muted)]">{row.team} · {row.position}</span></span>
                  <span className="text-right"><span className="block text-[9px] font-bold uppercase text-[var(--text-faint)]">Actual / Target</span><strong className="text-[11px] font-extrabold text-[var(--text-primary)]">{formatMetric(row.current_value, row.unit)} / {formatMetric(row.target_value, row.unit)}</strong></span>
                  <span className="text-right"><span className="block text-[9px] font-bold uppercase text-[var(--text-faint)]">Impact</span><strong className="text-[11px] font-extrabold text-rose-600">{impactLabel(row.weighted_impact)}</strong></span>
                </button>
              ))}
            </div>
          ) : <p className="mt-6 text-sm font-semibold text-[var(--text-muted)]">No negative employee contributors were measured for this KPI.</p>}
          <p className="mt-2 text-[10px] font-medium text-[var(--text-muted)]">Impact is weighted contribution to the score gap, not a root-cause claim.</p>
        </article>
      </div>

      {trend && <KpiSixMonthTrend trend={trend} />}
    </section>
  );
}

function GeographyContribution({
  summaries,
  onSelect,
}: {
  summaries: import('../features/insights/types').InsightScopeSummary[];
  onSelect: (scope: string) => void;
}) {
  if (!summaries.length) return null;
  return (
    <section className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm" aria-labelledby="geography-contribution-title">
      <header className="border-b border-[var(--border-light)] px-5 py-4"><div className="flex items-center gap-2"><MapPinned size={17} className="text-blue-600" /><h2 id="geography-contribution-title" className="text-lg font-extrabold text-[var(--text-primary)]">Geography contribution</h2></div><p className="mt-1 text-xs text-[var(--text-muted)]">Select a geography to move from the executive story into team-level analysis.</p></header>
      <div className="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-3">
        {summaries.map((summary) => (
          <button key={summary.scope} type="button" onClick={() => onSelect(summary.scope)} className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/35 p-4 text-left transition hover:border-blue-400/50 hover:bg-blue-500/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
            <div className="flex items-start justify-between gap-3"><span className="text-sm font-black text-[var(--text-primary)]">{summary.scope}</span><ArrowRight size={15} className="text-blue-600" /></div>
            <div className="mt-3 grid grid-cols-2 gap-3"><div><span className="text-[10px] font-bold uppercase text-[var(--text-faint)]">Score</span><strong className="mt-1 block text-xl font-black text-[var(--text-primary)]">{summary.current_score === null ? 'N/A' : `${summary.current_score.toFixed(1)}%`}</strong></div><div><span className="text-[10px] font-bold uppercase text-[var(--text-faint)]">Gap to target</span><strong className={`mt-1 block text-sm font-black ${summary.gap_points !== null && summary.gap_points < 0 ? 'text-rose-600' : 'text-emerald-600'}`}>{summary.gap_points === null ? 'N/A' : `${summary.gap_points > 0 ? '+' : ''}${summary.gap_points.toFixed(1)}%`}</strong></div></div>
            <div className="mt-3 flex items-center justify-between border-t border-[var(--border-light)] pt-3 text-[11px] text-[var(--text-muted)]"><span>{summary.impacted_employees}/{summary.total_employees} affected</span><span className="font-bold text-rose-600">{summary.gap_contribution_percent === null ? 'No gap share' : `${summary.gap_contribution_percent.toFixed(1)}% gap share`}</span></div>
          </button>
        ))}
      </div>
    </section>
  );
}

function ImpactHighlights({
  drivers,
  onOpen,
}: {
  drivers: Array<{ id: string; driver: string; scope: string; impact_points: number; direction: 'positive' | 'negative'; insight_id: string }>;
  onOpen: (id: string) => void;
}) {
  const largestGap = drivers.filter((driver) => driver.impact_points < 0).sort((a, b) => a.impact_points - b.impact_points)[0];
  const positive = drivers.filter((driver) => driver.impact_points > 0).sort((a, b) => b.impact_points - a.impact_points)[0];
  const card = (driver: typeof largestGap, positiveCard: boolean) => (
    <article className={`rounded-2xl border p-5 shadow-sm ${positiveCard ? 'border-emerald-200/70 bg-gradient-to-br from-emerald-50/90 to-white dark:border-emerald-500/20 dark:from-emerald-500/10 dark:to-transparent' : 'border-rose-200/70 bg-gradient-to-br from-rose-50/90 to-white dark:border-rose-500/20 dark:from-rose-500/10 dark:to-transparent'}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className={`text-[10px] font-black uppercase tracking-[0.14em] ${positiveCard ? 'text-emerald-700' : 'text-rose-700'}`}>{positiveCard ? 'Top positive contributor' : 'Largest performance gap'}</p>
          <h2 className="mt-2 text-lg font-black text-[var(--text-primary)]">{driver?.driver || 'No measured driver'}</h2>
          <p className="mt-1 truncate text-xs font-semibold text-[var(--text-muted)]" title={driver?.scope}>{driver ? cleanScope(driver.scope) : 'The selected scope has no measured impact.'}</p>
        </div>
        <span className={`text-2xl font-black ${positiveCard ? 'text-emerald-600' : 'text-rose-600'}`}>{driver ? impactLabel(driver.impact_points) : 'N/A'}</span>
      </div>
      {driver && <button type="button" onClick={() => onOpen(driver.insight_id)} className="mt-5 inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-current/20 px-3 text-xs font-extrabold text-[var(--text-secondary)] transition hover:border-current/40 hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">View analysis <ArrowRight size={14} /></button>}
    </article>
  );
  return <section className="grid gap-4 md:grid-cols-2" aria-label="Impact highlights">{card(largestGap, false)}{card(positive, true)}</section>;
}

function PerformanceByTeam({
  summaries,
  onSelect,
}: {
  summaries: import('../features/insights/types').InsightsWorkspace['team_summaries'];
  onSelect: (team: string) => void;
}) {
  if (!summaries.length) return null;
  return (
    <section className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm" aria-labelledby="performance-by-team-title">
      <header className="flex items-start justify-between gap-3 border-b border-[var(--border-light)] px-5 py-4"><div><h2 id="performance-by-team-title" className="text-base font-extrabold text-[var(--text-primary)]">Performance by team</h2><p className="mt-1 text-xs text-[var(--text-muted)]">Choose a team to reveal its KPI diagnostics.</p></div><UsersRound size={17} className="text-blue-600" /></header>
      <div className="divide-y divide-[var(--border-light)]">
        {summaries.slice(0, 8).map((summary) => (
          <button key={summary.team} type="button" onClick={() => onSelect(summary.team)} className="grid w-full grid-cols-[minmax(0,1.3fr)_auto_auto_auto] items-center gap-3 px-5 py-3 text-left transition hover:bg-[var(--bg-sunken)]/55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500">
            <span className="min-w-0"><strong className="block truncate text-xs font-extrabold text-[var(--text-primary)]">{summary.team}</strong><span className="mt-0.5 block text-[10px] text-[var(--text-muted)]">{summary.impacted_employees}/{summary.total_employees} affected</span></span>
            <strong className="text-sm font-black text-[var(--text-primary)]">{summary.current_score === null ? 'N/A' : `${summary.current_score.toFixed(1)}%`}</strong>
            <span className={`text-xs font-extrabold ${summary.score_change !== null && summary.score_change < 0 ? 'text-rose-600' : 'text-emerald-600'}`}>{summary.score_change === null ? 'N/A' : `${summary.score_change > 0 ? '+' : ''}${summary.score_change.toFixed(1)}%`}</span>
            <ArrowRight size={14} className="text-blue-600" />
          </button>
        ))}
      </div>
    </section>
  );
}

function PerformanceByRole({
  summaries,
  onOpen,
}: {
  summaries: InsightRoleSummary[];
  onOpen: (id: string) => void;
}) {
  if (!summaries.length) return null;
  return (
    <section className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm" aria-labelledby="performance-by-role-title">
      <header className="flex items-start justify-between gap-3 border-b border-[var(--border-light)] px-5 py-4"><div><h2 id="performance-by-role-title" className="text-base font-extrabold text-[var(--text-primary)]">Performance by role</h2><p className="mt-1 text-xs text-[var(--text-muted)]">Role movement is scoped to its team.</p></div><Target size={17} className="text-violet-600" /></header>
      <div className="divide-y divide-[var(--border-light)]">
        {summaries.slice(0, 8).map((summary) => (
          <button key={`${summary.team}-${summary.role}`} type="button" disabled={!summary.primary_insight_id} onClick={() => summary.primary_insight_id && onOpen(summary.primary_insight_id)} className="grid w-full grid-cols-[minmax(0,1.3fr)_auto_auto] items-center gap-3 px-5 py-3 text-left transition hover:bg-[var(--bg-sunken)]/55 disabled:cursor-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500">
            <span className="min-w-0"><strong className="block truncate text-xs font-extrabold text-[var(--text-primary)]">{summary.role}</strong><span className="mt-0.5 block truncate text-[10px] text-[var(--text-muted)]">{summary.team} · {summary.affected_employees}/{summary.total_employees} affected</span></span>
            <strong className="text-sm font-black text-[var(--text-primary)]">{summary.current_score === null ? 'N/A' : `${summary.current_score.toFixed(1)}%`}</strong>
            <span className={`text-xs font-extrabold ${summary.movement !== null && summary.movement < 0 ? 'text-rose-600' : 'text-emerald-600'}`}>{summary.movement === null ? 'N/A' : `${summary.movement > 0 ? '+' : ''}${summary.movement.toFixed(1)}%`}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function KpiOverviewPanel({ overview }: { overview: InsightKpiOverview }) {
  const max = Math.max(1, ...overview.points.map((point) => point.total_kpis));
  return (
    <section className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm" aria-labelledby="kpi-overview-title">
      <header className="border-b border-[var(--border-light)] px-5 py-4"><div className="flex items-center gap-2"><BarChart3 size={17} className="text-blue-600" /><h2 id="kpi-overview-title" className="text-base font-extrabold text-[var(--text-primary)]">KPI overview</h2></div><p className="mt-1 text-xs text-[var(--text-muted)]">Health of configured KPIs across the selected scope.</p></header>
      <div className="grid grid-cols-3 gap-2 px-5 py-4 sm:grid-cols-4"><div><span className="text-[10px] font-bold uppercase text-[var(--text-faint)]">Total</span><strong className="mt-1 block text-xl font-black text-[var(--text-primary)]">{overview.total_kpis}</strong></div><div><span className="text-[10px] font-bold uppercase text-emerald-600">On track</span><strong className="mt-1 block text-xl font-black text-emerald-600">{overview.on_track}</strong></div><div><span className="text-[10px] font-bold uppercase text-amber-600">At risk</span><strong className="mt-1 block text-xl font-black text-amber-600">{overview.at_risk}</strong></div><div><span className="text-[10px] font-bold uppercase text-rose-600">Critical</span><strong className="mt-1 block text-xl font-black text-rose-600">{overview.critical}</strong></div></div>
      {overview.points.length > 0 && <div className="flex h-28 items-end gap-3 border-t border-[var(--border-light)] px-5 pb-4 pt-3">{overview.points.map((point) => <div key={point.period.key} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-1"><div className="flex h-16 w-full max-w-10 items-end gap-0.5"><span className="w-1/3 rounded-t bg-emerald-400" style={{ height: `${Math.max(4, (point.on_track / max) * 100)}%` }} /><span className="w-1/3 rounded-t bg-amber-400" style={{ height: `${Math.max(4, (point.at_risk / max) * 100)}%` }} /><span className="w-1/3 rounded-t bg-rose-400" style={{ height: `${Math.max(4, (point.critical / max) * 100)}%` }} /></div><span className="truncate text-[9px] font-bold text-[var(--text-faint)]">{point.period.month.slice(0, 3)}</span></div>)}</div>}
    </section>
  );
}

function CriticalAlertsPanel({ insights, onOpen }: { insights: InsightItem[]; onOpen: (insight: InsightItem) => void }) {
  const alerts = insights.filter((insight) => insight.severity === 'critical' || insight.severity === 'risk').slice(0, 4);
  return (
    <section className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm" aria-labelledby="critical-alerts-title">
      <header className="flex items-center justify-between border-b border-[var(--border-light)] px-5 py-4"><div className="flex items-center gap-2"><BadgeAlert size={17} className="text-rose-600" /><h2 id="critical-alerts-title" className="text-base font-extrabold text-[var(--text-primary)]">Recent critical alerts</h2></div><span className="text-xs font-bold text-[var(--text-muted)]">{alerts.length} visible</span></header>
      {alerts.length ? <div className="divide-y divide-[var(--border-light)]">{alerts.map((insight) => <button key={insight.id} type="button" onClick={() => onOpen(insight)} className="flex w-full items-center gap-3 px-5 py-3 text-left transition hover:bg-rose-500/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500"><span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg border ${severityStyles[insight.severity]}`}><AlertTriangle size={14} /></span><span className="min-w-0 flex-1"><strong className="block truncate text-xs font-extrabold text-[var(--text-primary)]">{insight.title}</strong><span className="mt-0.5 block truncate text-[10px] text-[var(--text-muted)]">{cleanScope(insight.scope)}</span></span><ArrowRight size={14} className="text-[var(--text-faint)]" /></button>)}</div> : <p className="px-5 py-8 text-center text-sm text-[var(--text-muted)]">No critical alerts in this scope.</p>}
    </section>
  );
}

function RecommendedActions({
  workspace,
  focusInsight,
  onOpenInsight,
  onSelectTeam,
  onNavigate,
}: {
  workspace: import('../features/insights/types').InsightsWorkspace;
  focusInsight: InsightItem | null;
  onOpenInsight: () => void;
  onSelectTeam: (team: string) => void;
  onNavigate: (path: string) => void;
}) {
  const leadTeam = focusInsight?.team || workspace.team_summaries.find((team) => team.main_insight_id)?.team || '';
  const actionCards = [
    {
      title: 'Create corrective action',
      copy: focusInsight ? `Build a tracked plan for ${focusInsight.title}.` : 'Turn the highest-priority issue into a tracked plan.',
      icon: PlusCircle,
      tone: 'violet',
      onClick: () => onNavigate('/corrective-actions'),
    },
    {
      title: 'Assign coaching',
      copy: 'Open the planning workspace to assign support and follow-up.',
      icon: UsersRound,
      tone: 'blue',
      onClick: () => onNavigate('/planning'),
    },
    {
      title: 'Open team review',
      copy: leadTeam ? `Review ${leadTeam} at team level.` : 'Choose a team to inspect its drivers and people.',
      icon: SearchCheck,
      tone: 'orange',
      onClick: () => leadTeam ? onSelectTeam(leadTeam) : onOpenInsight(),
    },
    {
      title: 'Review root cause',
      copy: focusInsight?.detail.recommended_focus || 'Open the evidence behind the leading insight.',
      icon: Wrench,
      tone: 'emerald',
      onClick: onOpenInsight,
    },
  ] as const;

  const toneClasses: Record<(typeof actionCards)[number]['tone'], string> = {
    violet: 'border-violet-200 bg-violet-50/70 text-violet-700 hover:border-violet-300 dark:border-violet-500/20 dark:bg-violet-500/10 dark:text-violet-200',
    blue: 'border-blue-200 bg-blue-50/70 text-blue-700 hover:border-blue-300 dark:border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-200',
    orange: 'border-orange-200 bg-orange-50/70 text-orange-700 hover:border-orange-300 dark:border-orange-500/20 dark:bg-orange-500/10 dark:text-orange-200',
    emerald: 'border-emerald-200 bg-emerald-50/70 text-emerald-700 hover:border-emerald-300 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-200',
  };

  return (
    <section className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm" aria-labelledby="recommended-actions-title">
      <header className="border-b border-[var(--border-light)] px-5 py-4 md:px-6">
        <div className="flex items-center gap-2"><ClipboardCheck size={17} className="text-blue-600" /><h2 id="recommended-actions-title" className="text-lg font-extrabold text-[var(--text-primary)]">Recommended actions</h2></div>
        <p className="mt-1 text-xs text-[var(--text-muted)]">Move from measured insight to an accountable next step.</p>
      </header>
      <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">
        {actionCards.map(({ title, copy, icon: Icon, tone, onClick }) => (
          <button key={title} type="button" onClick={onClick} className={`group flex min-h-[132px] flex-col items-start rounded-xl border p-4 text-left transition hover:-translate-y-0.5 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${toneClasses[tone]}`}>
            <span className="flex w-full items-start justify-between gap-3"><span className="grid h-9 w-9 place-items-center rounded-xl bg-white/80 shadow-sm dark:bg-white/10"><Icon size={17} /></span><ArrowUpRight size={15} className="opacity-60 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5" /></span>
            <strong className="mt-4 text-sm font-extrabold text-[var(--text-primary)]">{title}</strong>
            <span className="mt-1 line-clamp-2 text-[11px] leading-5 text-[var(--text-muted)]">{copy}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

const insightUrlFilters: Array<[keyof InsightFilters, string]> = [
  ['region', 'region'],
  ['team', 'team'],
  ['performanceLevel', 'performance_level'],
  ['position', 'position'],
  ['employeeId', 'employee_id'],
  ['kpi', 'kpi'],
  ['severity', 'severity'],
  ['insightType', 'insight_type'],
  ['status', 'status'],
];

function filtersFromUrl(params: URLSearchParams): InsightFilters {
  const filters: InsightFilters = {};
  const period = params.get('period');
  if (period) filters.periodKey = period;
  insightUrlFilters.forEach(([key, parameter]) => {
    const value = params.get(parameter);
    if (value) filters[key] = value;
  });
  return filters;
}

export default function InsightsView() {
  const navigate = useNavigate();
  const { role, fetchWithRole } = useUserRole();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState<InsightFilters>(() => filtersFromUrl(searchParams));
  const [showAdditional, setShowAdditional] = useState(false);
  const [drawerInsight, setDrawerInsight] = useState<InsightItem | null>(null);
  const [focusedInsightId, setFocusedInsightId] = useState<string | null>(null);
  const [analysisTab, setAnalysisTab] = useState<'all' | InsightSeverity>('all');
  const [analysisPage, setAnalysisPage] = useState(1);
  const [modalEmployee, setModalEmployee] = useState<TeamAgentRow | null>(null);
  const [hoverTooltip, setHoverTooltip] = useState<{ text: string; x: number; y: number } | null>(null);
  const [shareNotice, setShareNotice] = useState<string | null>(null);
  const [exportState, setExportState] = useState<'idle' | 'exporting' | 'error'>('idle');
  const [exportError, setExportError] = useState<string | null>(null);
  const query = useInsightsWorkspace(filters);
  const workspace = query.data;
  // Keep placeholder data from showing the previous KPI's trend while a new
  // KPI-only filter request is in flight. The chart must identify the KPI the
  // user selected, not merely display whatever trend was cached previously.
  const selectedKpiTrend = filters.kpi && workspace?.kpi_trend?.kpi_key !== filters.kpi
    ? null
    : workspace?.kpi_trend;
  const quickActionMonth = workspace?.comparison.current?.month || 'All';
  const quickActionLevel = (filters.performanceLevel || 'All') as PerformanceLevelFilter;
  const quickActionRegion = filters.region === 'EGY' || filters.region === 'UAE' ? filters.region : 'All';
  const quickActionData = useTeamData(
    filters.team || null,
    quickActionMonth,
    quickActionRegion,
    'all',
    undefined,
    quickActionLevel,
  );
  const { getActionsForEmployee } = useActionStore();
  const quickActionRows = useMemo(
    () => new Map(quickActionData.rows.map((row) => [
      `${row.team}\u0000${row.id}\u0000${row.performanceLevel}`,
      row,
    ])),
    [quickActionData.rows],
  );
  const teamAverages = useMemo(() => {
    const scores = new Map<string, { total: number; count: number }>();
    quickActionData.rows.forEach((row) => {
      const current = scores.get(row.team) || { total: 0, count: 0 };
      current.total += row.score;
      current.count += 1;
      scores.set(row.team, current);
    });
    return new Map(Array.from(scores, ([team, value]) => [
      team,
      value.count ? value.total / value.count : 0,
    ]));
  }, [quickActionData.rows]);

  const effectivePeriod = filters.periodKey || workspace?.comparison.current?.key || '';
  const update = (key: keyof InsightFilters, value: string) => {
    setAnalysisPage(1);
    setFilters((current) => ({ ...current, [key]: value || undefined }));
  };
  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    next.delete('period');
    insightUrlFilters.forEach(([, parameter]) => next.delete(parameter));
    if (filters.periodKey) next.set('period', filters.periodKey);
    insightUrlFilters.forEach(([key, parameter]) => {
      const value = filters[key];
      if (value) next.set(parameter, value);
    });
    if (next.toString() !== searchParams.toString()) {
      setSearchParams(next, { replace: true });
    }
  }, [filters, searchParams, setSearchParams]);
  const filteredEmployees = useMemo(() => workspace?.options.employees.filter((employee) => (
    (!filters.team || employee.team === filters.team)
    && (!filters.position || employee.position === filters.position)
    && (!filters.performanceLevel || employee.performance_level === filters.performanceLevel)
  )) || [], [workspace?.options.employees, filters.team, filters.position, filters.performanceLevel]);
  const analysisItems = Array.from(new Map([...(workspace?.team_analyses ?? []), ...(workspace?.priority_insights ?? [])].map((item) => [item.id, item])).values());
  const visibleAnalyses = analysisTab === 'all' ? analysisItems : analysisItems.filter((item) => item.severity === analysisTab);
  const analysesPerPage = 10;
  const totalAnalysisPages = Math.max(1, Math.ceil(visibleAnalyses.length / analysesPerPage));
  const currentAnalysisPage = Math.min(analysisPage, totalAnalysisPages);
  const pagedAnalyses = visibleAnalyses.slice((currentAnalysisPage - 1) * analysesPerPage, currentAnalysisPage * analysesPerPage);
  const pageNumbers = pageWindow(currentAnalysisPage, totalAnalysisPages);
  const analysisStart = visibleAnalyses.length ? ((currentAnalysisPage - 1) * analysesPerPage) + 1 : 0;
  const analysisEnd = Math.min(currentAnalysisPage * analysesPerPage, visibleAnalyses.length);

  if (query.isLoading && !workspace) {
    return <PageLoadingSkeleton variant="dashboard" label="Preparing authorized insights" />;
  }
  if (query.error || !workspace) {
    return (
      <div role="alert" className="mx-auto mt-12 max-w-xl rounded-2xl border border-red-500/20 bg-red-500/10 p-6 text-center text-red-600">
        <AlertCircle className="mx-auto mb-3" /><p className="font-extrabold">Unable to load insights</p><p className="mt-1 text-sm">{query.error?.message || 'The insights workspace is unavailable.'}</p>
        <button type="button" onClick={() => query.refetch()} className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-xl bg-red-600 px-4 text-sm font-bold text-white"><RefreshCw size={16} /> Retry</button>
      </div>
    );
  }

  const leadingDriverInsight = workspace.performance_drivers.length
    ? analysisItems.find((item) => item.id === workspace.performance_drivers[0].insight_id)
    : null;
  const focusedInsight = analysisItems.find((item) => item.id === focusedInsightId)
    || leadingDriverInsight
    || workspace.priority_insights[0]
    || analysisItems[0]
    || null;
  const tabs: Array<{ key: 'all' | InsightSeverity; label: string; count: number }> = [
    { key: 'all', label: 'All analyses', count: analysisItems.length },
    { key: 'critical', label: 'Critical', count: workspace.summary.critical },
    { key: 'risk', label: 'At risk', count: workspace.summary.at_risk },
    { key: 'opportunity', label: 'Opportunities', count: workspace.summary.opportunities },
    { key: 'information', label: 'Data issues', count: workspace.summary.data_issues },
  ];
  const netImpact = workspace.summary.weighted_net_impact;
  const summaryCards = [
    { label: 'Net weighted KPI impact', value: `${netImpact > 0 ? '+' : ''}${netImpact.toFixed(1)}%`, copy: `${workspace.summary.negative_weighted_drivers} widening / ${workspace.summary.positive_weighted_drivers} closing score drivers`, icon: BarChart3, style: netImpact < 0 ? 'border-rose-200/80 bg-gradient-to-br from-rose-50 to-white text-rose-600 dark:border-rose-500/20 dark:from-rose-500/10 dark:to-transparent' : 'border-emerald-200/80 bg-gradient-to-br from-emerald-50 to-white text-emerald-700 dark:border-emerald-500/20 dark:from-emerald-500/10 dark:to-transparent' },
    { label: 'Critical KPI issues', value: workspace.summary.critical_issues.toString(), copy: 'Unique KPI and scope issues needing immediate attention', icon: BadgeAlert, style: 'border-red-200/80 bg-gradient-to-br from-red-50 to-white text-red-600 dark:border-red-500/20 dark:from-red-500/10 dark:to-transparent' },
    { label: 'Positive weighted drivers', value: workspace.summary.positive_weighted_drivers.toString(), copy: `+${workspace.summary.weighted_positive_impact.toFixed(1)}% weighted score support`, icon: Lightbulb, style: 'border-emerald-200/80 bg-gradient-to-br from-emerald-50 to-white text-emerald-700 dark:border-emerald-500/20 dark:from-emerald-500/10 dark:to-transparent' },
    { label: 'Weighted KPI coverage', value: workspace.summary.coverage_percent === null ? 'N/A' : `${workspace.summary.coverage_percent.toFixed(1)}%`, copy: workspace.summary.expected_kpis ? `${workspace.summary.analyzed_kpis} of ${workspace.summary.expected_kpis} KPI records fully analyzed · ${workspace.summary.data_issues} data checks` : 'No configured weighted KPI records in this scope', icon: ShieldAlert, style: 'border-blue-200/80 bg-gradient-to-br from-blue-50 to-white text-blue-600 dark:border-blue-500/20 dark:from-blue-500/10 dark:to-transparent' },
  ];
  const showDiagnosticAnalysis = Boolean(filters.team || filters.kpi || filters.employeeId);
  const analysisDepth = filters.employeeId
    ? 'Employee evidence'
    : filters.kpi
      ? 'KPI diagnosis'
      : filters.team
        ? 'Team contribution'
        : filters.region
          ? 'Geography contribution'
          : 'Executive overview';
  const activeFilterEntries = [
    filters.region ? { key: 'region' as const, label: 'Region', value: filters.region } : null,
    filters.team ? { key: 'team' as const, label: 'Team', value: filters.team } : null,
    filters.performanceLevel ? { key: 'performanceLevel' as const, label: 'Level', value: filters.performanceLevel } : null,
    filters.position ? { key: 'position' as const, label: 'Position', value: filters.position } : null,
    filters.employeeId ? { key: 'employeeId' as const, label: 'Employee', value: filters.employeeId } : null,
    filters.kpi ? { key: 'kpi' as const, label: 'KPI', value: workspace.options.kpis.find((item) => item.key === filters.kpi)?.label || filters.kpi } : null,
    filters.severity ? { key: 'severity' as const, label: 'Severity', value: filters.severity } : null,
    filters.insightType ? { key: 'insightType' as const, label: 'Type', value: filters.insightType } : null,
    filters.status ? { key: 'status' as const, label: 'Status', value: filters.status } : null,
  ].filter(Boolean) as Array<{ key: keyof InsightFilters; label: string; value: string }>;
  const clearFilter = (key: keyof InsightFilters) => {
    setAnalysisPage(1);
    setFilters((current) => ({ ...current, [key]: undefined }));
  };
  const clearAnalysis = () => {
    setAnalysisPage(1);
    setFocusedInsightId(null);
    setFilters({ periodKey: filters.periodKey });
  };
  const selectRegion = (scope: string) => {
    setAnalysisPage(1);
    setFilters((current) => ({
      ...current,
      region: scope || undefined,
      team: undefined,
      position: undefined,
      employeeId: undefined,
      kpi: undefined,
    }));
  };
  const selectTeam = (team: string) => {
    setAnalysisPage(1);
    setFilters((current) => ({
      ...current,
      team: team || undefined,
      position: undefined,
      employeeId: undefined,
      kpi: undefined,
    }));
  };
  const openFocusedInsight = () => {
    if (focusedInsight) setDrawerInsight(focusedInsight);
  };
  const handleShare = async () => {
    const url = window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({ title: 'Insights workspace', text: 'PMS Insights workspace', url });
        setShareNotice('View shared');
      } else {
        await navigator.clipboard.writeText(url);
        setShareNotice('Link copied');
      }
    } catch {
      setShareNotice('Share cancelled');
    }
    window.setTimeout(() => setShareNotice(null), 2200);
  };
  const handleExport = async () => {
    const period = workspace.options.periods.find((item) => item.key === effectivePeriod);
    if (!period) {
      setExportState('error');
      setExportError('The selected Insights period is unavailable for export.');
      return;
    }
    setExportState('exporting');
    setExportError(null);
    try {
      const response = await fetchWithRole(`${API_BASE}/api/reports/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          report_type: 'insights',
          report_name: `Insights - ${period.month} ${period.year}`,
          start_month: period.month,
          start_year: period.year,
          region: filters.region || null,
          team: filters.team || null,
          position: filters.position || null,
          performance_level: filters.performanceLevel || null,
          employee_id: filters.employeeId || null,
          kpi: filters.kpi || null,
          severity: filters.severity || null,
          insight_type: filters.insightType || null,
          included_sections: ['summary', 'team_breakdown', 'kpi_breakdown', 'details'],
          output_format: 'pptx',
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || 'PowerPoint export failed.');
      }
      const responseBody = await response.json();
      let generatedReport = responseBody.data as { download_url?: string; file_name?: string; job_id?: string };
      if (generatedReport?.job_id) {
        const job = await waitForProcessingJob(generatedReport.job_id);
        if (job.status !== 'succeeded' || !job.result) {
          throw new Error(job.error?.message || 'PowerPoint generation failed.');
        }
        generatedReport = job.result as typeof generatedReport;
      }
      if (!generatedReport?.download_url) {
        throw new Error('The generated PowerPoint download is unavailable.');
      }
      const downloadUrl = generatedReport.download_url.startsWith('http')
        ? generatedReport.download_url
        : `${API_BASE}${generatedReport.download_url}`;
      const fileResponse = await fetchWithRole(downloadUrl);
      if (!fileResponse.ok) throw new Error('The generated PowerPoint could not be downloaded.');
      const blob = await fileResponse.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = generatedReport.file_name || `insights-${period.year}-${period.month}.pptx`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setExportState('idle');
    } catch (error) {
      setExportState('error');
      setExportError(error instanceof Error ? error.message : 'PowerPoint export failed.');
    }
  };

  return (
    <div className="app-page-shell rf-page rf-page--insights insights-page">
      <section className="insights-filter-shell rf-filter-panel rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm">
        <div className="flex flex-col gap-4 p-5 xl:flex-row xl:items-center xl:justify-between">
          <div><div className="flex items-center gap-2"><h1 className="text-2xl font-extrabold tracking-tight text-[var(--text-primary)]">Insights</h1><AlertCircle size={15} className="text-[var(--text-faint)]" /></div><p className="mt-1 max-w-2xl text-sm text-[var(--text-muted)]">Understand what happened, why it happened, and what to do next.</p></div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]"><span className="rounded-full bg-[var(--bg-sunken)] px-3 py-1.5 font-semibold">Current: {workspace.comparison.current ? `${workspace.comparison.current.month} ${workspace.comparison.current.year}` : 'Unavailable'}</span><span className="rounded-full bg-[var(--bg-sunken)] px-3 py-1.5 font-semibold">Compare: {workspace.comparison.previous ? `${workspace.comparison.previous.month} ${workspace.comparison.previous.year}` : 'Unavailable'}</span><button type="button" onClick={() => void handleShare()} className="inline-flex min-h-9 items-center gap-1.5 rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 font-bold text-[var(--text-secondary)] transition hover:border-blue-500/40 hover:text-blue-600"><Share2 size={14} /> Share</button><button type="button" onClick={() => void handleExport()} disabled={exportState === 'exporting'} className="inline-flex min-h-9 items-center gap-1.5 rounded-xl bg-blue-600 px-3 font-bold text-white transition hover:bg-blue-700 disabled:cursor-wait disabled:opacity-70">{exportState === 'exporting' ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} {exportState === 'exporting' ? 'Exporting PPTX…' : 'Export PowerPoint'}</button>{query.isFetching && <Loader2 size={14} className="animate-spin text-blue-600" />}{shareNotice && <span role="status" className="font-bold text-blue-600">{shareNotice}</span>}{exportError && <span role="alert" className="font-bold text-rose-600">{exportError}</span>}</div>
        </div>
        <div className="grid gap-2 border-t border-[var(--border-light)] p-4 sm:grid-cols-2 xl:grid-cols-5">
          <FilterSelect label="Insight period" value={effectivePeriod} onChange={(value) => update('periodKey', value)} options={workspace.options.periods.map((period) => ({ value: period.key, label: `${period.month} ${period.year}` }))} />
          <FilterSelect label="Region" value={filters.region || ''} onChange={selectRegion} allLabel="All regions" options={workspace.options.regions.map((value) => ({ value, label: value }))} />
          <FilterSelect label="Team" value={filters.team || ''} onChange={(value) => {
            setAnalysisPage(1);
            setFilters((current) => ({
              ...current,
              team: value || undefined,
              position: undefined,
              employeeId: undefined,
              kpi: undefined,
            }));
          }} allLabel="All teams" options={workspace.options.teams.map((value) => ({ value, label: value }))} />
          <FilterSelect label="Performance level" value={filters.performanceLevel || ''} onChange={(value) => {
            setAnalysisPage(1);
            setFilters((current) => ({
              ...current,
              performanceLevel: value || undefined,
              position: undefined,
              employeeId: undefined,
              kpi: undefined,
            }));
          }} allLabel="All levels" options={workspace.options.performance_levels.map((value) => ({ value, label: value }))} />
          <button type="button" aria-expanded={showAdditional} onClick={() => setShowAdditional((value) => !value)} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-4 text-sm font-bold text-[var(--text-secondary)] hover:border-blue-500/40"><Filter size={16} /> More filters {activeFilterEntries.length > 0 && <span className="grid h-5 min-w-5 place-items-center rounded-full bg-blue-600 px-1 text-[10px] text-white">{activeFilterEntries.length}</span>}</button>
        </div>
        {showAdditional && <div className="grid gap-2 border-t border-[var(--border-light)] bg-[var(--bg-sunken)]/40 p-4 sm:grid-cols-2 xl:grid-cols-7"><FilterSelect label="Position" value={filters.position || ''} onChange={(value) => { update('position', value); update('employeeId', ''); }} allLabel="All positions" options={workspace.options.positions.map((value) => ({ value, label: value }))} /><FilterSelect label="Employee" value={filters.employeeId || ''} onChange={(value) => { update('employeeId', value); const employeeInsight = [...workspace.priority_insights, ...workspace.team_analyses].find((insight) => insight.employee_id === value); if (employeeInsight) { setFocusedInsightId(employeeInsight.id); setDrawerInsight(employeeInsight); } }} allLabel="All employees" options={filteredEmployees.map((employee) => ({ value: employee.id, label: `${employee.name} (${employee.id})` }))} /><FilterSelect label="KPI" value={filters.kpi || ''} onChange={(value) => update('kpi', value)} allLabel="All KPIs" options={workspace.options.kpis.map((kpi) => ({ value: kpi.key, label: kpi.label }))} /><FilterSelect label="Severity" value={filters.severity || ''} onChange={(value) => update('severity', value)} allLabel="All severities" options={workspace.options.severities.map((value) => ({ value, label: value.replace('_', ' ') }))} /><FilterSelect label="Insight type" value={filters.insightType || ''} onChange={(value) => update('insightType', value)} allLabel="All types" options={workspace.options.insight_types.map((value) => ({ value, label: value.replace('_', ' ') }))} /><FilterSelect label="Status" value={filters.status || ''} onChange={(value) => update('status', value)} allLabel="All statuses" options={workspace.options.statuses.map((value) => ({ value, label: value.replace('_', ' ') }))} /><button type="button" onClick={clearAnalysis} className="min-h-11 rounded-xl border border-[var(--input-border)] px-4 text-sm font-bold text-[var(--text-secondary)] hover:text-red-600">Clear analysis</button></div>}
        {activeFilterEntries.length > 0 && <div className="flex flex-wrap items-center gap-2 border-t border-[var(--border-light)] px-4 py-3"><span className="mr-1 text-[10px] font-black uppercase tracking-[0.14em] text-[var(--text-faint)]">{analysisDepth}</span>{activeFilterEntries.map((entry) => <button key={entry.key} type="button" onClick={() => clearFilter(entry.key)} className="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-[11px] font-bold text-blue-700 hover:border-blue-400 dark:border-blue-500/25 dark:bg-blue-500/10 dark:text-blue-200">{entry.label}: {entry.value}<X size={12} /></button>)}<button type="button" onClick={clearAnalysis} className="ml-auto text-[11px] font-bold text-[var(--text-muted)] hover:text-rose-600">Reset analysis</button></div>}
      </section>

      {SHOW_EXECUTIVE_STORY && workspace.executive_story && <ExecutiveStoryCard story={workspace.executive_story} onScopeSelect={selectRegion} />}
      <ReportReference
        story={workspace.executive_story}
        trend={selectedKpiTrend}
        people={workspace.people_contribution_analysis}
        onOpenEmployee={(employeeId, level) => {
          const month = workspace.comparison.current?.month || '';
          navigate(`/employee/${encodeURIComponent(employeeId)}?month=${encodeURIComponent(month)}&performance_level=${encodeURIComponent(level || 'Employee')}`);
        }}
      />
      {!filters.region && !filters.team && !filters.kpi && (workspace.geography_summaries?.length ?? 0) > 0 && <GeographyContribution summaries={workspace.geography_summaries || []} onSelect={selectRegion} />}

      {!filters.team && !filters.kpi && !filters.employeeId && <>
        <ImpactHighlights drivers={workspace.performance_drivers} onOpen={(id) => { setFocusedInsightId(id); window.scrollTo({ top: 0, behavior: 'smooth' }); }} />
        <section className="grid gap-5 xl:grid-cols-2" aria-label="Performance summaries">
          <PerformanceByTeam summaries={workspace.team_summaries} onSelect={selectTeam} />
          <PerformanceByRole summaries={workspace.role_summaries || []} onOpen={(id) => setFocusedInsightId(id)} />
        </section>
        <section className="grid gap-5 xl:grid-cols-2" aria-label="KPI health and alerts">
          {workspace.kpi_overview && <KpiOverviewPanel overview={workspace.kpi_overview} />}
          <CriticalAlertsPanel insights={workspace.priority_insights} onOpen={(insight) => { setFocusedInsightId(insight.id); setDrawerInsight(insight); }} />
        </section>
      </>}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Insight summary">{summaryCards.map(({ label, value, copy, icon: Icon, style }) => <article key={label} className={`min-h-[142px] rounded-2xl border p-5 shadow-sm ${style}`}><div className="flex items-start justify-between"><span className="text-sm font-extrabold">{label}</span><span className="grid h-10 w-10 place-items-center rounded-xl bg-current/10"><Icon size={19} /></span></div><p className="mt-3 text-3xl font-black text-[var(--text-primary)]">{value}</p><p className="mt-1 text-xs font-medium text-[var(--text-muted)]">{copy}</p></article>)}</section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,0.75fr)]">
        <article className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm"><header className="border-b border-[var(--border-light)] px-5 py-4"><div className="flex items-center gap-2"><h2 className="text-lg font-extrabold text-[var(--text-primary)]">Weighted Score Contribution</h2><AlertCircle size={14} className="text-[var(--text-faint)]" /></div><p className="mt-1 text-xs text-[var(--text-muted)]">Measured KPI contribution movements—not assumed operational root causes.</p></header><DriverChart drivers={workspace.performance_drivers} onSelect={setFocusedInsightId} onHoverTooltip={setHoverTooltip} /></article>
        <article className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm"><header className="flex items-center justify-between border-b border-[var(--border-light)] px-5 py-4"><h2 className="text-lg font-extrabold text-[var(--text-primary)]">Insight Summary</h2>{focusedInsight && <span className={`rounded-full border px-2 py-1 text-[9px] font-black uppercase ${severityStyles[focusedInsight.severity]}`}>{severityLabels[focusedInsight.severity]}</span>}</header><InsightSpotlight insight={focusedInsight} onOpen={() => focusedInsight && setDrawerInsight(focusedInsight)} /></article>
      </section>

      {filters.kpi && workspace.people_contribution_analysis?.kpi_key === filters.kpi && (
        <PeopleContributionAnalysis
          key={workspace.people_contribution_analysis.kpi_key}
          analysis={workspace.people_contribution_analysis}
          onOpenEmployee={(employeeId, level) => {
            const month = workspace.comparison.current?.month || '';
            navigate(`/employee/${encodeURIComponent(employeeId)}?month=${encodeURIComponent(month)}&performance_level=${encodeURIComponent(level || 'Employee')}`);
          }}
          renderEmployeeActions={(contribution) => {
            const employee = quickActionRows.get(
              `${contribution.team}\u0000${contribution.employee_id}\u0000${contribution.performance_level}`,
            );
            if (!employee) {
              return <span className="text-[10px] font-semibold text-[var(--text-muted)]">Unavailable</span>;
            }
            return (
              <EmployeeRowActions
                row={employee}
                role={role}
                month={quickActionMonth}
                performanceLevel={employee.performanceLevel}
                teamAverage={teamAverages.get(employee.team) ?? quickActionData.avgScore}
                actions={getActionsForEmployee(employee.id)}
                onAddAction={setModalEmployee}
                onEmployeeChanged={() => { void refreshPerformanceData(); }}
              />
            );
          }}
        />
      )}

      {showDiagnosticAnalysis ? <section className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm" aria-labelledby="team-analysis-title">
        <div className="flex flex-col gap-3 border-b border-[var(--border-light)] px-4 pt-4 md:flex-row md:items-end md:justify-between md:px-5">
          <div><h2 id="team-analysis-title" className="text-lg font-extrabold text-[var(--text-primary)]">Team KPI Analysis</h2><p className="mt-1 text-xs text-[var(--text-muted)]">Weighted score factors and operational diagnostics from the same authorized evidence.</p></div>
          <div className="flex max-w-full gap-1 overflow-x-auto">{tabs.map((tab) => <button key={tab.key} type="button" onClick={() => { setAnalysisPage(1); setAnalysisTab(tab.key); }} className={`whitespace-nowrap border-b-2 px-3 py-3 text-xs font-extrabold ${analysisTab === tab.key ? 'border-blue-600 text-blue-600' : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]'}`}>{tab.label} ({tab.count})</button>)}</div>
        </div>
        {visibleAnalyses.length ? <div><div className="overflow-x-auto"><table className="w-full min-w-[980px] text-left"><thead><tr className="border-b border-[var(--border-light)] bg-[var(--bg-sunken)]/50 text-[9px] font-extrabold uppercase tracking-wide text-[var(--text-faint)]"><th className="px-5 py-3">Insight</th><th className="px-4 py-3">Team / role</th><th className="px-4 py-3">Current</th><th className="px-4 py-3">Target</th><th className="px-4 py-3">Impact</th><th className="px-4 py-3">Trend</th><th className="px-5 py-3 text-right">Action</th></tr></thead><tbody>{pagedAnalyses.map((insight) => <tr key={insight.id} onClick={() => setFocusedInsightId(insight.id)} className="cursor-pointer border-b border-[var(--border-light)] last:border-0 hover:bg-[var(--bg-sunken)]/55"><td className="px-5 py-4"><div className="flex items-start gap-3"><span className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg border ${severityStyles[insight.severity]}`}>{insight.severity === 'opportunity' ? <ArrowUpRight size={14} /> : <AlertTriangle size={14} />}</span><span><span className={`inline-flex rounded-full border px-1.5 py-0.5 text-[8px] font-black uppercase ${severityStyles[insight.severity]}`}>{severityLabels[insight.severity]}</span><strong className="mt-1 block max-w-[360px] text-xs text-[var(--text-primary)]">{insight.title}</strong><span className="mt-1 block text-[10px] text-[var(--text-muted)]">{insight.detail.direction?.replace('_', ' ') || 'Operational diagnostic'}</span></span></div></td><td className="px-4 py-4 text-xs text-[var(--text-secondary)]">{cleanScope(insight.scope)}</td><td className="px-4 py-4 text-xs font-extrabold text-[var(--text-primary)]">{formatMetric(insight.detail.current_value, insight.detail.unit)}</td><td className="px-4 py-4 text-xs text-[var(--text-secondary)]">{formatMetric(insight.detail.target_value, insight.detail.unit)}</td><td className={`px-4 py-4 text-xs font-extrabold ${insight.impact_points === null ? 'text-[var(--text-muted)]' : insight.impact_points >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>{impactLabel(insight.impact_points)}</td><td className="max-w-[180px] px-4 py-4 text-xs text-[var(--text-secondary)]">{insight.trend_label}</td><td className="px-5 py-4 text-right"><button type="button" aria-label={`View ${insight.title}`} onClick={(event) => { event.stopPropagation(); setDrawerInsight(insight); }} className="inline-grid h-9 w-9 place-items-center rounded-lg border border-[var(--border-light)] text-blue-600 hover:bg-blue-500/10"><Eye size={15} /></button></td></tr>)}</tbody></table></div><div className="flex flex-col gap-3 border-t border-[var(--border-light)] px-5 py-4 sm:flex-row sm:items-center sm:justify-between"><p className="text-sm font-semibold text-[var(--text-muted)]">Showing {analysisStart}–{analysisEnd} of {visibleAnalyses.length} analyses</p><div className="flex items-center gap-2"><button type="button" aria-label="Previous page" disabled={currentAnalysisPage === 1} onClick={() => setAnalysisPage((page) => Math.max(1, page - 1))} className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--border-light)] text-[var(--text-secondary)] transition hover:border-blue-500/40 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-40"><ChevronLeft size={16} /></button>{pageNumbers.map((page) => <button key={page} type="button" aria-current={page === currentAnalysisPage ? 'page' : undefined} onClick={() => setAnalysisPage(page)} className={`min-h-10 min-w-10 rounded-xl border px-3 text-sm font-bold transition ${page === currentAnalysisPage ? 'border-blue-600 bg-blue-600 text-white shadow-sm shadow-blue-500/20' : 'border-[var(--border-light)] text-[var(--text-secondary)] hover:border-blue-500/40 hover:text-blue-600'}`}>{page}</button>)}<button type="button" aria-label="Next page" disabled={currentAnalysisPage === totalAnalysisPages} onClick={() => setAnalysisPage((page) => Math.min(totalAnalysisPages, page + 1))} className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--border-light)] text-[var(--text-secondary)] transition hover:border-blue-500/40 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-40"><ChevronRight size={16} /></button></div></div></div> : <div className="px-6 py-14 text-center"><SearchX className="mx-auto text-[var(--text-faint)]" /><p className="mt-3 font-extrabold text-[var(--text-primary)]">No analyses match this view</p></div>}
      </section> : <section className="rounded-2xl border border-dashed border-blue-200 bg-blue-50/50 p-5 text-sm text-[var(--text-secondary)] dark:border-blue-500/20 dark:bg-blue-500/[0.05]"><div className="flex items-start gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-blue-600/10 text-blue-600"><Filter size={17} /></span><div><p className="font-extrabold text-[var(--text-primary)]">Choose a team or KPI to open diagnostic analysis</p><p className="mt-1 leading-6">The executive layer is intentionally compact. Select a geography above, then choose a team or KPI to reveal detailed drivers, trends, affected people, and actions.</p></div></div></section>}

      <RecommendedActions
        workspace={workspace}
        focusInsight={focusedInsight}
        onOpenInsight={openFocusedInsight}
        onSelectTeam={selectTeam}
        onNavigate={navigate}
      />

      {showDiagnosticAnalysis && <section className="grid gap-5 xl:grid-cols-2">
        <article className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm">
          <header className="border-b border-[var(--border-light)] px-5 py-4">
            <h2 className="text-base font-extrabold text-[var(--text-primary)]">Team Risk Matrix</h2>
            <p className="mt-1 text-xs text-[var(--text-muted)]">Score, movement and affected headcount for a fair cross-team comparison.</p>
          </header>
          {workspace.team_summaries.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[580px] text-left text-xs table-fixed">
                <thead>
                  <tr className="border-b border-[var(--border-light)] text-[9px] uppercase text-[var(--text-faint)] font-extrabold tracking-wide">
                    <th className="pl-5 pr-2 py-3 w-[25%]">Team</th>
                    <th className="px-2 py-3 w-[11%]">Score</th>
                    <th className="px-2 py-3 w-[11%]">Trend</th>
                    <th className="px-2 py-3 w-[12%]">Affected</th>
                    <th className="px-2 py-3 w-[10%]">Critical</th>
                    <th className="px-2 py-3 w-[10%]">At risk</th>
                    <th className="pl-2 pr-5 py-3 w-[21%]">Priority contribution</th>
                  </tr>
                </thead>
                <tbody>
                  {workspace.team_summaries.map((team) => {
                    const trendColor = team.score_change === null || team.score_change === 0
                      ? 'text-[var(--text-muted)] font-medium'
                      : team.score_change > 0
                      ? 'text-emerald-600 font-bold'
                      : 'text-rose-600 font-bold';

                    const criticalColor = team.critical > 0
                      ? 'text-rose-600 font-bold'
                      : 'text-[var(--text-muted)] font-normal opacity-40';

                    const atRiskColor = team.at_risk > 0
                      ? 'text-amber-600 font-bold'
                      : 'text-[var(--text-muted)] font-normal opacity-40';

                    const affectedColor = team.impacted_employees > 0
                      ? 'text-[var(--text-secondary)] font-semibold'
                      : 'text-[var(--text-muted)] opacity-60';

                    return (
                      <tr key={team.team} className="border-b border-[var(--border-light)] last:border-0 hover:bg-[var(--bg-sunken)]/30 transition-colors">
                        <td className="pl-5 pr-2 py-4 font-extrabold text-[var(--text-primary)] break-words leading-tight">
                          {team.team}
                        </td>
                        <td className="px-2 py-4 font-bold text-[var(--text-primary)]">
                          {team.current_score === null ? 'N/A' : `${team.current_score.toFixed(1)}%`}
                        </td>
                        <td className={`px-2 py-4 ${trendColor}`}>
                          {team.score_change === null ? 'N/A' : `${team.score_change > 0 ? '+' : ''}${team.score_change.toFixed(1)}%`}
                        </td>
                        <td className={`px-2 py-4 ${affectedColor}`}>
                          {team.impacted_employees}/{team.total_employees}
                        </td>
                        <td className={`px-2 py-4 ${criticalColor}`}>
                          {team.critical}
                        </td>
                        <td className={`px-2 py-4 ${atRiskColor}`}>
                          {team.at_risk}
                        </td>
                        <td className="pl-2 pr-5 py-4 min-w-0">
                          {team.main_insight_id ? (
                            <button
                              type="button"
                              onClick={() => team.main_insight_id && setFocusedInsightId(team.main_insight_id)}
                              className="block w-full truncate text-left font-semibold text-blue-600 hover:underline"
                              onMouseEnter={(e) => {
                                const rect = e.currentTarget.getBoundingClientRect();
                                setHoverTooltip({
                                  text: team.main_cause ?? 'No measured issue',
                                  x: rect.left + rect.width / 2,
                                  y: rect.top - 8
                                });
                              }}
                              onMouseLeave={() => setHoverTooltip(null)}
                            >
                              {team.main_cause}
                            </button>
                          ) : (
                            <span className="text-[var(--text-muted)] italic">No measured issue</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="p-8 text-center text-sm text-[var(--text-muted)]">No team-level analyses match the selected scope.</p>
          )}
        </article>
        <article className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5 shadow-sm"><div className="flex items-center gap-2"><Target size={17} className="text-blue-600" /><h2 className="text-base font-extrabold text-[var(--text-primary)]">Decision Support Notes</h2></div><div className="mt-4 space-y-3">{workspace.risks.map((risk) => <button type="button" key={risk.key} onClick={() => update('insightType', filters.insightType === risk.filter_type ? '' : risk.filter_type)} className="flex w-full items-center gap-3 rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/35 p-3 text-left hover:border-blue-500/30"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-rose-500/10 text-rose-600"><AlertTriangle size={16} /></span><span className="min-w-0 flex-1"><strong className="text-sm text-[var(--text-primary)]">{risk.count} {risk.label}</strong><span className="mt-0.5 block text-xs text-[var(--text-muted)]">{risk.explanation}</span></span><ArrowRight size={15} className="text-[var(--text-faint)]" /></button>)}</div>{workspace.deferred_capabilities.length > 0 && <p className="mt-4 rounded-xl bg-[var(--bg-sunken)] p-3 text-xs leading-5 text-[var(--text-muted)]">{workspace.deferred_capabilities.join(' ')}</p>}</article>
      </section>}

      <footer className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-4 py-3 text-[10px] text-[var(--text-muted)]"><span className="flex items-center gap-2"><AlertCircle size={13} /> Insights use the same authorized performance evidence and active configuration.</span><span>{analysisItems.length} analyses in the selected scope</span></footer>
      <InsightDetailDrawer key={drawerInsight?.id || 'closed'} insight={drawerInsight} onClose={() => setDrawerInsight(null)} />
      {modalEmployee && (
        <EmployeeActionModal
          employee={modalEmployee}
          month={quickActionMonth}
          onClose={() => setModalEmployee(null)}
        />
      )}

      {hoverTooltip && (
        <div
          className="fixed z-[9999] px-4 py-3 text-xs font-semibold text-white bg-slate-900/95 dark:bg-slate-800/95 border border-slate-700/50 rounded-xl shadow-xl backdrop-blur-sm pointer-events-none -translate-x-1/2 -translate-y-full transition-all duration-200 animate-in fade-in zoom-in-95 max-w-[320px] break-words text-left"
          style={{
            left: hoverTooltip.x,
            top: hoverTooltip.y,
          }}
        >
          {(() => {
            const separators = ['▸', '•', '>', '»'];
            const activeSeparator = separators.find(s => hoverTooltip.text.includes(s));
            if (activeSeparator) {
              const items = hoverTooltip.text
                .split(activeSeparator)
                .map(item => item.trim())
                .filter(item => item.length > 0);
              return (
                <ul className="space-y-1.5 list-disc pl-4 text-slate-100">
                  {items.map((item, idx) => (
                    <li key={idx} className="leading-relaxed">
                      {item}
                    </li>
                  ))}
                </ul>
              );
            }
            return <p className="leading-relaxed text-slate-100 text-center">{hoverTooltip.text}</p>;
          })()}
          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-0.5 border-4 border-transparent border-t-slate-900/95 dark:border-t-slate-800/95" />
        </div>
      )}
    </div>
  );
}
