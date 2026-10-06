import './PageEnhancements.css';
import BackToTop from '../components/common/BackToTop';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertCircle, AlertTriangle, ArrowRight, ArrowUpRight,
  ChevronLeft, ChevronRight, DatabaseZap,
  Download, Eye, Filter, Loader2, RefreshCw, SearchX,
  Share2, Sparkles, Target, TrendingDown, TrendingUp, X,
} from 'lucide-react';
import InsightDetailDrawer from '../components/insights/InsightDetailDrawer';
import KpiSixMonthTrend from '../components/insights/KpiSixMonthTrend';
import PeopleContributionAnalysis from '../components/insights/PeopleContributionAnalysis';
import { SEVERITY_LABELS, SEVERITY_STYLES, severityDisplay } from '../features/insights/severity';
import ExecutiveSummary from '../components/insights/overview/ExecutiveSummary';
import InsightsHeader from '../components/insights/overview/InsightsHeader';
import {
  GeographySection,
  KeyDriversSection,
  MoreAnalysisSection,
  PeopleToReviewSection,
  RecommendedActionsSection,
  TeamsNeedingAttentionSection,
} from '../components/insights/overview/OverviewSections';
import { MORE_ANALYSIS_KEYS, resolveMovementTone, type MoreAnalysisKey } from '../components/insights/overview/insightsOverviewModel';
import EmployeeActionModal from '../components/team/EmployeeActionModal';
import EmployeeRowActions from '../components/team/EmployeeRowActions';
import type { InsightFilters, InsightItem, InsightSeverity, InsightKpiOverview, InsightRoleSummary } from '../features/insights/types';
import { useInsightsWorkspace } from '../hooks/api/useInsightsWorkspace';
import {
  INSIGHT_FUNCTIONS,
  apiTeamParam,
  functionOptionsFor,
  reconcileCascade,
  teamBelongsToFunction,
  teamOptionsFor,
} from '../features/insights/filterCascade';
import { PageLoadingSkeleton } from '../components/common/SkeletonLoader';
import { refreshPerformanceData, useTeamData, type TeamAgentRow } from '../hooks/usePerformanceData';
import { useActionStore } from '../hooks/useActionStore';
import { useUserRole } from '../context/RoleContext';
import { canonicalTeamName, type PerformanceLevelFilter } from '../types';
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

// `information` splits into "Watch" (on target but worsening, PR #15) and "Data issue" (data quality).
const severityStyle = (insight: InsightItem) => SEVERITY_STYLES[severityDisplay(insight)];
const severityLabel = (insight: InsightItem) => SEVERITY_LABELS[severityDisplay(insight)];

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
    return <div className="grid min-h-[324px] place-items-center px-6 text-center text-sm text-[var(--text-muted)]">No weighted score drivers match the selected scope.</div>;
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
  if (!insight) return <div className="grid min-h-[324px] place-items-center px-7 text-center text-sm text-[var(--text-muted)]">Select an analysis to inspect its evidence.</div>;
  const display = severityDisplay(insight);
  const Icon = display === 'critical' ? Target : display === 'risk' ? AlertTriangle : display === 'opportunity' ? Sparkles : display === 'watch' ? Eye : DatabaseZap;
  // Direction-aware: for lower-is-better KPIs a falling value is the improvement.
  // Colour = good / bad (API trend_status / change_value first); arrow = raw movement direction.
  const { detail } = insight;
  const rawDelta = detail.raw_change ?? (detail.current_value !== null && detail.previous_value !== null
    ? detail.current_value - detail.previous_value
    : null);
  const movement = resolveMovementTone({
    trendStatus: detail.trend_status, changeValue: detail.change_value, rawDelta, direction: detail.direction,
  });
  const MovementIcon = rawDelta !== null && rawDelta > 0 ? TrendingUp : rawDelta !== null && rawDelta < 0 ? TrendingDown : null;
  return (
    <div className="p-5 md:p-6">
      <div className="flex items-start gap-4">
        <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-2xl border ${severityStyle(insight)}`}><Icon size={21} /></span>
        <div className="min-w-0">
          <span className={`inline-flex rounded-full border px-2 py-1 text-[9px] font-black uppercase ${severityStyle(insight)}`}>{severityLabel(insight)}</span>
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
          <div><span className="text-[10px] text-[var(--text-muted)]">Trend</span><strong data-testid="spotlight-trend" data-tone={movement} className={`mt-1 flex items-center gap-1 text-sm ${movement === 'good' ? 'text-emerald-600' : movement === 'bad' ? 'text-rose-600' : 'text-[var(--text-primary)]'}`}>{(movement === 'good' || movement === 'bad') && MovementIcon && <MovementIcon size={14} aria-hidden="true" />}{insight.trend_label}</strong></div>
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

// The panels below are the bodies of the "More analysis (optional)" accordions
// (Figma 18:491). The accordion header carries the section title.
function PerformanceByRolePanel({
  summaries,
  onOpen,
}: {
  summaries: InsightRoleSummary[];
  onOpen: (id: string) => void;
}) {
  if (!summaries.length) return <p className="px-5 py-6 text-center text-sm text-[var(--text-muted)]">No role-level results in this scope.</p>;
  return (
    <div className="divide-y divide-[var(--border-light)]">
      <p className="px-5 py-2.5 text-[11px] text-[var(--text-muted)]">Role movement is scoped to its team.</p>
      {summaries.slice(0, 8).map((summary) => (
        <button key={`${summary.team}-${summary.role}`} type="button" disabled={!summary.primary_insight_id} onClick={() => summary.primary_insight_id && onOpen(summary.primary_insight_id)} className="grid w-full grid-cols-[minmax(0,1.3fr)_auto_auto] items-center gap-3 px-5 py-3 text-left transition hover:bg-[var(--bg-sunken)]/55 disabled:cursor-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500">
          <span className="min-w-0"><strong className="block truncate text-xs font-extrabold text-[var(--text-primary)]">{summary.role}</strong><span className="mt-0.5 block truncate text-[10px] text-[var(--text-muted)]">{summary.team} · {summary.affected_employees}/{summary.total_employees} affected</span></span>
          <strong className="text-sm font-black text-[var(--text-primary)]">{summary.current_score === null ? 'N/A' : `${summary.current_score.toFixed(1)}%`}</strong>
          <span className={`text-xs font-extrabold ${summary.movement !== null && summary.movement < 0 ? 'text-rose-600' : 'text-emerald-600'}`}>{summary.movement === null ? 'N/A' : `${summary.movement > 0 ? '+' : ''}${summary.movement.toFixed(1)}%`}</span>
        </button>
      ))}
    </div>
  );
}

function KpiOverviewBody({ overview, summary }: { overview: InsightKpiOverview | undefined; summary: import('../features/insights/types').InsightsWorkspace['summary'] }) {
  const coverage = (
    <p className="border-t border-[var(--border-light)] px-5 py-3 text-xs text-[var(--text-muted)]">
      <span className="font-bold text-[var(--text-secondary)]">Weighted KPI coverage: </span>
      <strong className="text-[var(--text-primary)]">{summary.coverage_percent === null ? 'N/A' : `${summary.coverage_percent.toFixed(1)}%`}</strong>
      {summary.expected_kpis ? ` · ${summary.analyzed_kpis} of ${summary.expected_kpis} KPI records fully analyzed · ${summary.data_issues} data checks` : ' · No configured weighted KPI records in this scope'}
    </p>
  );
  if (!overview) return coverage;
  const max = Math.max(1, ...overview.points.map((point) => point.total_kpis));
  return (
    <div>
      <div className="grid grid-cols-2 gap-2 px-5 py-4 sm:grid-cols-4"><div><span className="text-[10px] font-bold uppercase text-[var(--text-faint)]">Total</span><strong className="mt-1 block text-xl font-black text-[var(--text-primary)]">{overview.total_kpis}</strong></div><div><span className="text-[10px] font-bold uppercase text-emerald-600">On track</span><strong className="mt-1 block text-xl font-black text-emerald-600">{overview.on_track}</strong></div><div><span className="text-[10px] font-bold uppercase text-amber-600">At risk</span><strong className="mt-1 block text-xl font-black text-amber-600">{overview.at_risk}</strong></div><div><span className="text-[10px] font-bold uppercase text-rose-600">Critical</span><strong className="mt-1 block text-xl font-black text-rose-600">{overview.critical}</strong></div></div>
      {overview.points.length > 0 && <div className="flex h-28 items-end gap-3 border-t border-[var(--border-light)] px-5 pb-4 pt-3">{overview.points.map((point) => <div key={point.period.key} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-1"><div className="flex h-16 w-full max-w-10 items-end gap-0.5"><span className="w-1/3 rounded-t bg-emerald-400" style={{ height: `${Math.max(4, (point.on_track / max) * 100)}%` }} /><span className="w-1/3 rounded-t bg-amber-400" style={{ height: `${Math.max(4, (point.at_risk / max) * 100)}%` }} /><span className="w-1/3 rounded-t bg-rose-400" style={{ height: `${Math.max(4, (point.critical / max) * 100)}%` }} /></div><span className="truncate text-[9px] font-bold text-[var(--text-faint)]">{point.period.month.slice(0, 3)}</span></div>)}</div>}
      {coverage}
    </div>
  );
}

function CriticalAlertsBody({ insights, onOpen }: { insights: InsightItem[]; onOpen: (insight: InsightItem) => void }) {
  const alerts = insights.filter((insight) => insight.severity === 'critical' || insight.severity === 'risk').slice(0, 4);
  return alerts.length ? <div className="divide-y divide-[var(--border-light)]">{alerts.map((insight) => <button key={insight.id} type="button" onClick={() => onOpen(insight)} className="flex w-full items-center gap-3 px-5 py-3 text-left transition hover:bg-rose-500/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500"><span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg border ${severityStyle(insight)}`}><AlertTriangle size={14} /></span><span className="min-w-0 flex-1"><strong className="block truncate text-xs font-extrabold text-[var(--text-primary)]">{insight.title}</strong><span className="mt-0.5 block truncate text-[10px] text-[var(--text-muted)]">{cleanScope(insight.scope)}</span></span><ArrowRight size={14} className="text-[var(--text-faint)]" /></button>)}</div> : <p className="px-5 py-8 text-center text-sm text-[var(--text-muted)]">No critical alerts in this scope.</p>;
}

const insightUrlFilters: Array<[keyof InsightFilters, string]> = [
  ['region', 'region'],
  ['teamFunction', 'function'],
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
  // Links shared before the Teams filter existed stored the Function filter
  // in `team`; read those as a function selection.
  const legacyFunction = !filters.teamFunction && filters.team
    ? INSIGHT_FUNCTIONS.find((teamFunction) => teamFunction.toLowerCase() === filters.team?.toLowerCase())
    : undefined;
  if (legacyFunction) {
    filters.teamFunction = legacyFunction;
    delete filters.team;
  } else if (filters.team) {
    filters.team = canonicalTeamName(filters.team);
  }
  return filters;
}

const INSIGHT_SCOPE_ERROR = /outside the authorized insights scope/i;

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
  const [moreAnalysisOpen, setMoreAnalysisOpen] = useState<Record<MoreAnalysisKey, boolean>>({
    kpi: false, role: false, weighted: false, alerts: false,
  });
  const moreAnalysisRef = useRef<HTMLDivElement>(null);
  const query = useInsightsWorkspace(filters);
  const workspace = query.data;
  // Cascade auto-clear: once the API has answered for the *current* filters
  // (not placeholder data from the previous request), drop any header
  // selection its option lists no longer support, including invalid URL
  // combos. Adjusting state during render (instead of in an effect) avoids
  // ever rendering the contradictory selection.
  const reconciledFilters = query.data && !query.isPlaceholderData
    ? reconcileCascade(filters, query.data.options)
    : null;
  // A team / level outside a manager's scope is rejected with 403 before any
  // options are returned; clear the cascade instead of leaving an error state.
  const scopeRejected = Boolean(
    query.error
    && INSIGHT_SCOPE_ERROR.test(query.error.message)
    && (filters.team || filters.teamFunction || filters.performanceLevel),
  );
  if (reconciledFilters) {
    setAnalysisPage(1);
    setFilters(reconciledFilters);
  } else if (scopeRejected) {
    setAnalysisPage(1);
    setFilters({
      ...filters,
      teamFunction: undefined,
      team: undefined,
      performanceLevel: undefined,
      position: undefined,
      employeeId: undefined,
      kpi: undefined,
    });
  }
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
    apiTeamParam(filters) || null,
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
    // `information` = Watch items (on target but worsening) plus data-quality issues.
    { key: 'information', label: 'Watch & data issues', count: analysisItems.filter((item) => item.severity === 'information').length },
  ];
  const showDiagnosticAnalysis = Boolean(filters.team || filters.teamFunction || filters.kpi || filters.employeeId);
  const analysisDepth = filters.employeeId
    ? 'Employee evidence'
    : filters.kpi
      ? 'KPI diagnosis'
      : filters.team || filters.teamFunction
        ? 'Team contribution'
        : filters.region
          ? 'Geography contribution'
          : 'Executive overview';
  const activeFilterEntries = [
    filters.region ? { key: 'region' as const, label: 'Region', value: filters.region } : null,
    filters.teamFunction ? { key: 'teamFunction' as const, label: 'Function', value: filters.teamFunction } : null,
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
    // A team only exists inside its function, so clearing the function clears it too.
    setFilters((current) => ({ ...current, [key]: undefined, ...(key === 'teamFunction' ? { team: undefined } : {}) }));
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
      // Function / team / level stay selected and are auto-cleared by the
      // cascade only if the new region's options no longer contain them.
      region: scope || undefined,
      position: undefined,
      employeeId: undefined,
      kpi: undefined,
    }));
  };
  const selectTeam = (value: string) => {
    // Merged branch teams (e.g. OP Dubai + OP Final SHJAJM) are one header option.
    const team = canonicalTeamName(value);
    setAnalysisPage(1);
    setFilters((current) => ({
      ...current,
      team: team || undefined,
      teamFunction: team && current.teamFunction && !teamBelongsToFunction(team, current.teamFunction, workspace.options.team_functions)
        ? undefined
        : current.teamFunction,
      position: undefined,
      employeeId: undefined,
      kpi: undefined,
    }));
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
          team: apiTeamParam(filters) || null,
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

  const openEmployee = (employeeId: string, level: string) => {
    const month = workspace.comparison.current?.month || '';
    navigate(`/employee/${encodeURIComponent(employeeId)}?month=${encodeURIComponent(month)}&performance_level=${encodeURIComponent(level || 'Employee')}`);
  };
  const openDriverInsight = (insightId: string) => {
    setFocusedInsightId(insightId);
    const insight = analysisItems.find((item) => item.id === insightId);
    if (insight) setDrawerInsight(insight);
  };
  const viewAllDrivers = () => {
    setMoreAnalysisOpen((current) => ({ ...current, weighted: true }));
    window.requestAnimationFrame(() => moreAnalysisRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' }));
  };
  const selectFunction = (value: string) => {
    setAnalysisPage(1);
    setFilters((current) => ({
      ...current,
      teamFunction: value || undefined,
      team: current.team && value && teamBelongsToFunction(current.team, value, workspace.options.team_functions) ? current.team : undefined,
      position: undefined,
      employeeId: undefined,
      kpi: undefined,
    }));
  };
  const leadingPeopleKpi = workspace.people_contribution_analysis?.kpi_key;
  const functionOptions = functionOptionsFor(workspace.options).map((value) => ({ value, label: value }));
  const teamOptions = teamOptionsFor(workspace.options.teams, filters.teamFunction, workspace.options.team_functions).map((value) => ({ value, label: value }));
  const filterKey = JSON.stringify(filters);

  return (
    <div className="app-page-shell rf-page rf-page--insights insights-page [--app-section-gap:16px] [--rf-page-gap:16px]">
      <InsightsHeader
        period={effectivePeriod}
        periodOptions={workspace.options.periods.map((period) => ({ value: period.key, label: `${period.month} ${period.year}` }))}
        onPeriodChange={(value) => update('periodKey', value)}
        region={filters.region || ''}
        regionOptions={workspace.options.regions.map((value) => ({ value, label: value }))}
        onRegionChange={selectRegion}
        functionValue={filters.teamFunction || ''}
        functionOptions={functionOptions}
        onFunctionChange={selectFunction}
        team={filters.team || ''}
        teamOptions={teamOptions}
        onTeamChange={selectTeam}
        level={filters.performanceLevel || ''}
        levelOptions={workspace.options.performance_levels.map((value) => ({ value, label: value }))}
        onLevelChange={(value) => {
          setAnalysisPage(1);
          setFilters((current) => ({
            ...current,
            performanceLevel: value || undefined,
            position: undefined,
            employeeId: undefined,
            kpi: undefined,
          }));
        }}
      />

      {/* Existing secondary controls kept from the previous Insights page (not part of Figma 18:3). */}
      <div className="insights-filter-tools flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-end gap-2 text-xs text-[var(--text-muted)]">
          {query.isFetching && <Loader2 size={14} className="animate-spin text-[var(--insights-accent)]" aria-label="Refreshing insights" />}
          {shareNotice && <span role="status" className="font-bold text-[var(--insights-accent-text)]">{shareNotice}</span>}
          {exportError && <span role="alert" className="font-bold text-rose-600">{exportError}</span>}
          <button type="button" aria-expanded={showAdditional} onClick={() => setShowAdditional((value) => !value)} className="inline-flex h-[32px] items-center gap-1.5 rounded-[8px] border border-[var(--insights-card-border)] bg-[var(--bg-surface)] px-3 font-semibold text-[var(--text-secondary)] transition hover:border-[var(--insights-accent-border)]"><Filter size={14} /> More filters {activeFilterEntries.length > 0 && <span className="grid h-5 min-w-5 place-items-center rounded-full bg-[var(--insights-accent)] px-1 text-[10px] text-white">{activeFilterEntries.length}</span>}</button>
          <button type="button" onClick={() => void handleShare()} className="inline-flex h-[32px] items-center gap-1.5 rounded-[8px] border border-[var(--insights-card-border)] bg-[var(--bg-surface)] px-3 font-semibold text-[var(--text-secondary)] transition hover:border-[var(--insights-accent-border)]"><Share2 size={14} /> Share</button>
          <button type="button" onClick={() => void handleExport()} disabled={exportState === 'exporting'} className="inline-flex h-[32px] items-center gap-1.5 rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-3 font-semibold text-[var(--insights-accent-text)] transition hover:border-[var(--insights-accent)] disabled:cursor-wait disabled:opacity-70">{exportState === 'exporting' ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} {exportState === 'exporting' ? 'Exporting PPTX…' : 'Export PowerPoint'}</button>
        </div>
        {showAdditional && <div className="grid gap-2 rounded-[12px] border border-[var(--insights-card-border)] bg-[var(--bg-surface)] p-4 sm:grid-cols-2 xl:grid-cols-6"><FilterSelect label="Position" value={filters.position || ''} onChange={(value) => { update('position', value); update('employeeId', ''); }} allLabel="All positions" options={workspace.options.positions.map((value) => ({ value, label: value }))} /><FilterSelect label="KPI" value={filters.kpi || ''} onChange={(value) => update('kpi', value)} allLabel="All KPIs" options={workspace.options.kpis.map((kpi) => ({ value: kpi.key, label: kpi.label }))} /><FilterSelect label="Severity" value={filters.severity || ''} onChange={(value) => update('severity', value)} allLabel="All severities" options={workspace.options.severities.map((value) => ({ value, label: value.replace('_', ' ') }))} /><FilterSelect label="Insight type" value={filters.insightType || ''} onChange={(value) => update('insightType', value)} allLabel="All types" options={workspace.options.insight_types.map((value) => ({ value, label: value.replace('_', ' ') }))} /><FilterSelect label="Status" value={filters.status || ''} onChange={(value) => update('status', value)} allLabel="All statuses" options={workspace.options.statuses.map((value) => ({ value, label: value.replace('_', ' ') }))} /><button type="button" onClick={clearAnalysis} className="min-h-11 rounded-xl border border-[var(--input-border)] px-4 text-sm font-bold text-[var(--text-secondary)] hover:text-red-600">Clear analysis</button></div>}
        {activeFilterEntries.length > 0 && <div className="flex flex-wrap items-center gap-2"><span className="mr-1 text-[10px] font-black uppercase tracking-[0.14em] text-[var(--text-faint)]">{analysisDepth}</span>{activeFilterEntries.map((entry) => <button key={entry.key} type="button" onClick={() => clearFilter(entry.key)} className="inline-flex items-center gap-1.5 rounded-full border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-2.5 py-1 text-[11px] font-bold text-[var(--insights-accent-text)] hover:border-[var(--insights-accent)]">{entry.label}: {entry.value}<X size={12} /></button>)}<button type="button" onClick={clearAnalysis} className="ml-auto text-[11px] font-bold text-[var(--text-muted)] hover:text-rose-600">Reset analysis</button></div>}
      </div>

      <ExecutiveSummary
        story={workspace.executive_story}
        comparison={workspace.comparison}
        trend={selectedKpiTrend}
        overallTrend={workspace.overall_trend}
        // Placeholder data belongs to the previous filters: show a skeleton, not a stale or empty trend.
        trendLoading={Boolean(query.isPlaceholderData || (filters.kpi && !selectedKpiTrend && query.isFetching))}
        filterKey={filterKey}
      />

      <KeyDriversSection drivers={workspace.performance_drivers} onSelectDriver={openDriverInsight} onViewAll={viewAllDrivers} />

      <section className="grid gap-[16px] xl:grid-cols-2" aria-label="Geography and teams">
        <GeographySection summaries={workspace.geography_summaries || []} regionFilter={filters.region} onSelectRegion={selectRegion} />
        <TeamsNeedingAttentionSection teams={workspace.team_summaries} onSelectTeam={selectTeam} />
      </section>

      <RecommendedActionsSection
        drivers={workspace.performance_drivers}
        teams={workspace.team_summaries}
        onOpenDriver={openDriverInsight}
        onSelectTeam={selectTeam}
        onCoach={() => navigate('/planning')}
      />

      <PeopleToReviewSection
        analysis={workspace.people_contribution_analysis}
        onOpenEmployee={openEmployee}
        onViewAll={filters.kpi || !leadingPeopleKpi ? undefined : () => update('kpi', leadingPeopleKpi)}
      />

      {filters.kpi && selectedKpiTrend && (
        <section className="overflow-hidden rounded-[12px] border border-[var(--insights-card-border)] bg-[var(--bg-surface)]" aria-label="Selected KPI trend">
          <KpiSixMonthTrend trend={selectedKpiTrend} />
        </section>
      )}

      {filters.kpi && workspace.people_contribution_analysis?.kpi_key === filters.kpi && (
        <PeopleContributionAnalysis
          key={workspace.people_contribution_analysis.kpi_key}
          analysis={workspace.people_contribution_analysis}
          onOpenEmployee={openEmployee}
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

      {showDiagnosticAnalysis && <section className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm" aria-labelledby="team-analysis-title">
        <div className="flex flex-col gap-3 border-b border-[var(--border-light)] px-4 pt-4 md:flex-row md:items-end md:justify-between md:px-5">
          <div><h2 id="team-analysis-title" className="text-lg font-extrabold text-[var(--text-primary)]">Team KPI Analysis</h2><p className="mt-1 text-xs text-[var(--text-muted)]">Weighted score factors and operational diagnostics from the same authorized evidence.</p></div>
          <div className="flex max-w-full gap-1 overflow-x-auto">{tabs.map((tab) => <button key={tab.key} type="button" onClick={() => { setAnalysisPage(1); setAnalysisTab(tab.key); }} className={`whitespace-nowrap border-b-2 px-3 py-3 text-xs font-extrabold ${analysisTab === tab.key ? 'border-blue-600 text-blue-600' : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]'}`}>{tab.label} ({tab.count})</button>)}</div>
        </div>
        {visibleAnalyses.length ? <div><div className="overflow-x-auto"><table className="w-full min-w-[980px] text-left"><thead><tr className="border-b border-[var(--border-light)] bg-[var(--bg-sunken)]/50 text-[9px] font-extrabold uppercase tracking-wide text-[var(--text-faint)]"><th className="px-5 py-3">Insight</th><th className="px-4 py-3">Team / role</th><th className="px-4 py-3">Current</th><th className="px-4 py-3">Target</th><th className="px-4 py-3">Impact</th><th className="px-4 py-3">Trend</th><th className="px-5 py-3 text-right">Action</th></tr></thead><tbody>{pagedAnalyses.map((insight) => <tr key={insight.id} onClick={() => setFocusedInsightId(insight.id)} className="cursor-pointer border-b border-[var(--border-light)] last:border-0 hover:bg-[var(--bg-sunken)]/55"><td className="px-5 py-4"><div className="flex items-start gap-3"><span className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg border ${severityStyle(insight)}`}>{insight.severity === 'opportunity' ? <ArrowUpRight size={14} /> : <AlertTriangle size={14} />}</span><span><span className={`inline-flex rounded-full border px-1.5 py-0.5 text-[8px] font-black uppercase ${severityStyle(insight)}`}>{severityLabel(insight)}</span><strong className="mt-1 block max-w-[360px] text-xs text-[var(--text-primary)]">{insight.title}</strong><span className="mt-1 block text-[10px] text-[var(--text-muted)]">{insight.detail.direction?.replace('_', ' ') || 'Operational diagnostic'}</span></span></div></td><td className="px-4 py-4 text-xs text-[var(--text-secondary)]">{cleanScope(insight.scope)}</td><td className="px-4 py-4 text-xs font-extrabold text-[var(--text-primary)]">{formatMetric(insight.detail.current_value, insight.detail.unit)}</td><td className="px-4 py-4 text-xs text-[var(--text-secondary)]">{formatMetric(insight.detail.target_value, insight.detail.unit)}</td><td className={`px-4 py-4 text-xs font-extrabold ${insight.impact_points === null ? 'text-[var(--text-muted)]' : insight.impact_points >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>{impactLabel(insight.impact_points)}</td><td className="max-w-[180px] px-4 py-4 text-xs text-[var(--text-secondary)]">{insight.trend_label}</td><td className="px-5 py-4 text-right"><button type="button" aria-label={`View ${insight.title}`} onClick={(event) => { event.stopPropagation(); setDrawerInsight(insight); }} className="inline-grid h-9 w-9 place-items-center rounded-lg border border-[var(--border-light)] text-blue-600 hover:bg-blue-500/10"><Eye size={15} /></button></td></tr>)}</tbody></table></div><div className="flex flex-col gap-3 border-t border-[var(--border-light)] px-5 py-4 sm:flex-row sm:items-center sm:justify-between"><p className="text-sm font-semibold text-[var(--text-muted)]">Showing {analysisStart}–{analysisEnd} of {visibleAnalyses.length} analyses</p><div className="flex items-center gap-2"><button type="button" aria-label="Previous page" disabled={currentAnalysisPage === 1} onClick={() => setAnalysisPage((page) => Math.max(1, page - 1))} className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--border-light)] text-[var(--text-secondary)] transition hover:border-blue-500/40 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-40"><ChevronLeft size={16} /></button>{pageNumbers.map((page) => <button key={page} type="button" aria-current={page === currentAnalysisPage ? 'page' : undefined} onClick={() => setAnalysisPage(page)} className={`min-h-10 min-w-10 rounded-xl border px-3 text-sm font-bold transition ${page === currentAnalysisPage ? 'border-blue-600 bg-blue-600 text-white shadow-sm shadow-blue-500/20' : 'border-[var(--border-light)] text-[var(--text-secondary)] hover:border-blue-500/40 hover:text-blue-600'}`}>{page}</button>)}<button type="button" aria-label="Next page" disabled={currentAnalysisPage === totalAnalysisPages} onClick={() => setAnalysisPage((page) => Math.min(totalAnalysisPages, page + 1))} className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--border-light)] text-[var(--text-secondary)] transition hover:border-blue-500/40 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-40"><ChevronRight size={16} /></button></div></div></div> : <div className="px-6 py-14 text-center"><SearchX className="mx-auto text-[var(--text-faint)]" /><p className="mt-3 font-extrabold text-[var(--text-primary)]">No analyses match this view</p></div>}
      </section>}

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

      <div ref={moreAnalysisRef} className="scroll-mt-4">
        <MoreAnalysisSection
          open={moreAnalysisOpen}
          onToggle={(key) => setMoreAnalysisOpen((current) => ({ ...current, [key]: !current[key] }))}
          onToggleAll={(expand) => setMoreAnalysisOpen(Object.fromEntries(MORE_ANALYSIS_KEYS.map((key) => [key, expand])) as Record<MoreAnalysisKey, boolean>)}
          panels={{
            kpi: <KpiOverviewBody overview={workspace.kpi_overview} summary={workspace.summary} />,
            role: <PerformanceByRolePanel summaries={workspace.role_summaries || []} onOpen={(id) => setFocusedInsightId(id)} />,
            weighted: (
              <div className="grid xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,0.75fr)]">
                <div className="min-w-0"><p className="px-5 pt-3 text-[11px] text-[var(--text-muted)]">Measured KPI contribution movements—not assumed operational root causes.</p><DriverChart drivers={workspace.performance_drivers} onSelect={setFocusedInsightId} onHoverTooltip={setHoverTooltip} /></div>
                <div className="min-w-0 border-t border-[var(--border-light)] xl:border-l xl:border-t-0">
                  <div className="flex items-center justify-between px-5 pt-4"><h4 className="text-sm font-extrabold text-[var(--text-primary)]">Insight summary</h4>{focusedInsight && <span className={`rounded-full border px-2 py-1 text-[9px] font-black uppercase ${severityStyle(focusedInsight)}`}>{severityLabel(focusedInsight)}</span>}</div>
                  <InsightSpotlight insight={focusedInsight} onOpen={() => focusedInsight && setDrawerInsight(focusedInsight)} />
                </div>
              </div>
            ),
            alerts: <CriticalAlertsBody insights={workspace.priority_insights} onOpen={(insight) => { setFocusedInsightId(insight.id); setDrawerInsight(insight); }} />,
          }}
        />
      </div>

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
      <BackToTop />
    </div>
  );
}
