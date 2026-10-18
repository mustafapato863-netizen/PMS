import './PageEnhancements.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertCircle, Download, Loader2, RefreshCw, Share2, X,
} from 'lucide-react';
import InsightDetailDrawer from '../components/insights/InsightDetailDrawer';
import KpiSixMonthTrend from '../components/insights/KpiSixMonthTrend';
import TrackingIndicatorsCard from '../components/insights/TrackingIndicatorsCard';
import PeopleContributionAnalysis from '../components/insights/PeopleContributionAnalysis';
import InsightHeader from '../components/insights/overview/InsightsHeader';
import InsightsSummaryStrip from '../components/insights/overview/InsightsSummaryStrip';
import KpiDiagnosisTable from '../components/insights/overview/KpiDiagnosisTable';
import InsightsActionsSection, { type PersonBelowTarget } from '../components/insights/overview/InsightsActionsSection';
import { PeopleToReviewSection } from '../components/insights/overview/OverviewSections';
import EmployeeActionModal from '../components/team/EmployeeActionModal';
import EmployeeRowActions from '../components/team/EmployeeRowActions';
import type { InsightFilters, InsightItem } from '../features/insights/types';
import { INSIGHTS_PAGE_SECTIONS, useInsightsWorkspace } from '../hooks/api/useInsightsWorkspace';
import {
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
import { canonicalTeamName, type PerformanceLevelFilter, type LocationKey } from '../types';
import CustomDropdown from '../components/common/CustomDropdown';
import { API_BASE } from '../config';
import { waitForProcessingJob } from '../hooks/api/useProcessingJobs';
import { SUMMARY_BRANCHES } from '../features/executive/compose';

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

const insightUrlFilters: Array<[keyof InsightFilters, string]> = [
  ['region', 'region'],
  ['branch', 'branch'],
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

/** Write the filter params into `base` (other params are kept). */
function filtersToSearch(filters: InsightFilters, base: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(base);
  next.delete('period');
  insightUrlFilters.forEach(([, parameter]) => next.delete(parameter));
  if (filters.periodKey) next.set('period', filters.periodKey);
  insightUrlFilters.forEach(([key, parameter]) => {
    const value = filters[key];
    if (value) next.set(parameter, value);
  });
  return next;
}

/** Canonical identity of a filter set, as it would appear in the URL. */
function filtersKey(filters: InsightFilters): string {
  return filtersToSearch(filters, new URLSearchParams()).toString();
}

/**
 * Read filters from the URL. `legacy` (initial load only) maps pre-Teams links
 * that stored a function in `team` (e.g. `?team=Call Center`). In-app history
 * entries are always written in the current format, where `team=Marketing`
 * really means the Marketing team, so navigation reads them strictly.
 */
function filtersFromUrl(params: URLSearchParams, { legacy = true }: { legacy?: boolean } = {}): InsightFilters {
  const filters: InsightFilters = {};
  const period = params.get('period');
  if (period) filters.periodKey = period;
  insightUrlFilters.forEach(([key, parameter]) => {
    const value = params.get(parameter);
    if (value) filters[key] = value;
  });
  // Links shared before the Teams filter existed stored the Function filter
  // in `team`; read those as a function selection.
  const legacyFunction = legacy && !filters.teamFunction && filters.team
    ? ['Call Center', 'RCM', 'Marketing'].find((teamFunction) => teamFunction.toLowerCase() === filters.team?.toLowerCase())
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
  // URL → filters (QA BUG-1): Back/Forward, the sidebar "Insights" link
  // (/insights with no params) and any other navigation re-derive the filters
  // from the URL. Our own writes are recognised because the URL then already
  // matches `filters`, so state and URL never ping-pong.
  const urlFiltersKey = filtersKey(filtersFromUrl(searchParams, { legacy: false }));
  const [syncedUrlKey, setSyncedUrlKey] = useState(urlFiltersKey);
  const urlNavigated = urlFiltersKey !== syncedUrlKey;
  // User-initiated filter changes add a history entry; automatic corrections
  // (cascade auto-clear, scope rejection, canonical names) replace it.
  const historyMode = useRef<'push' | 'replace'>('replace');
  const setUserFilters: typeof setFilters = (value) => {
    historyMode.current = 'push';
    setFilters(value);
  };
  const [drawerInsight, setDrawerInsight] = useState<InsightItem | null>(null);
  const [shareNotice, setShareNotice] = useState<string | null>(null);
  const [exportState, setExportState] = useState<'idle' | 'exporting' | 'error'>('idle');
  const [exportError, setExportError] = useState<string | null>(null);
  const [modalEmployee, setModalEmployee] = useState<TeamAgentRow | null>(null);
  // The page renders only these fields; the backend computes nothing else for this request.
  const query = useInsightsWorkspace(filters, { sections: INSIGHTS_PAGE_SECTIONS });
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
    && (filters.team || filters.teamFunction || filters.performanceLevel || filters.branch),
  );
  if (urlNavigated) {
    setSyncedUrlKey(urlFiltersKey);
    if (urlFiltersKey !== filtersKey(filters)) {
      setFilters(filtersFromUrl(searchParams, { legacy: false }));
    }
  } else if (reconciledFilters) {
    setFilters(reconciledFilters);
  } else if (scopeRejected) {
    setFilters({
      ...filters,
      branch: undefined,
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
  const quickActionLocation: LocationKey = (filters.branch && ['dubai', 'sharjah', 'ajman', 'clinics'].includes(filters.branch.toLowerCase())
    ? filters.branch.toLowerCase() as LocationKey
    : 'all');
  const quickActionData = useTeamData(
    apiTeamParam(filters) || null,
    quickActionMonth,
    quickActionRegion,
    quickActionLocation,
    undefined,
    quickActionLevel,
  );
  // The store already holds every corrective action the role can see. The actions section filters it.
  const { getActionsForEmployee, getAllActions } = useActionStore();
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

  const branchOptions = useMemo(() => {
    if (workspace?.options?.branches?.length) {
      const available = new Set(workspace.options.branches.map((b) => b.toLowerCase()));
      const filtered = SUMMARY_BRANCHES.filter((item) => available.has(item.value.toLowerCase()));
      if (filtered.length > 0) return filtered;
    }
    return SUMMARY_BRANCHES;
  }, [workspace]);

  const effectivePeriod = filters.periodKey || workspace?.comparison.current?.key || '';
  const update = (key: keyof InsightFilters, value: string) => {
    setUserFilters((current) => ({ ...current, [key]: value || undefined }));
  };
  // Filters → URL. Only writes when the URL differs (no duplicate entries).
  useEffect(() => {
    const replace = historyMode.current !== 'push';
    historyMode.current = 'replace';
    const next = filtersToSearch(filters, searchParams);
    if (next.toString() !== searchParams.toString()) {
      setSearchParams(next, { replace });
    }
  }, [filters, searchParams, setSearchParams]);

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

  const analysisDepth = filters.employeeId
    ? 'Employee evidence'
    : filters.kpi
      ? 'KPI diagnosis'
      : filters.team || filters.teamFunction
        ? 'Team contribution'
        : filters.region || filters.branch
          ? 'Geography contribution'
          : 'Executive overview';
  const activeFilterEntries = [
    filters.region ? { key: 'region' as const, label: 'Region', value: filters.region } : null,
    filters.branch ? { key: 'branch' as const, label: 'Branch', value: branchOptions.find((b) => b.value.toLowerCase() === filters.branch?.toLowerCase())?.label || filters.branch } : null,
    filters.teamFunction ? { key: 'teamFunction' as const, label: 'Function', value: filters.teamFunction } : null,
    filters.team ? { key: 'team' as const, label: 'Team', value: filters.team } : null,
    filters.performanceLevel ? { key: 'performanceLevel' as const, label: 'Level', value: filters.performanceLevel } : null,
    filters.position ? { key: 'position' as const, label: 'Position', value: filters.position } : null,
    filters.employeeId ? { key: 'employeeId' as const, label: 'Employee', value: filters.employeeId } : null,
    filters.kpi ? { key: 'kpi' as const, label: 'KPI', value: workspace.options.kpis.find((item) => item.key === filters.kpi)?.label || filters.kpi } : null,
  ].filter(Boolean) as Array<{ key: keyof InsightFilters; label: string; value: string }>;
  const clearFilter = (key: keyof InsightFilters) => {
    // Clearing the function keeps a team, like picking "All functions" (QA BUG-4).
    setUserFilters((current) => ({ ...current, [key]: undefined }));
  };
  const clearAnalysis = () => {
    setUserFilters({ periodKey: filters.periodKey });
  };
  const selectRegion = (scope: string) => {
    setUserFilters((current) => ({
      ...current,
      // Function / team / level stay selected and are auto-cleared by the
      // cascade only if the new region's options no longer contain them.
      region: scope || undefined,
      branch: scope === 'EGY' ? undefined : current.branch,
      position: undefined,
      employeeId: undefined,
      kpi: undefined,
    }));
  };
  const selectBranch = (value: string) => {
    setUserFilters((current) => ({
      ...current,
      branch: value || undefined,
      region: value && current.region === 'EGY' ? undefined : current.region,
      position: undefined,
      employeeId: undefined,
      kpi: undefined,
    }));
  };
  const selectTeam = (value: string) => {
    // Merged branch teams (e.g. OP Dubai + OP Final SHJAJM) are one header option.
    const team = canonicalTeamName(value);
    setUserFilters((current) => ({
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
          branch: filters.branch || null,
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
  const selectFunction = (value: string) => {
    setUserFilters((current) => ({
      ...current,
      teamFunction: value || undefined,
      // "All functions" keeps the team (it is valid on its own; the cascade still
      // drops it if the options no longer list it). A specific function keeps it
      // only when the team belongs to that function.
      team: current.team && (!value || teamBelongsToFunction(current.team, value, workspace.options.team_functions)) ? current.team : undefined,
      position: undefined,
      employeeId: undefined,
      kpi: undefined,
    }));
  };
  const leadingPeopleKpi = workspace.people_contribution_analysis?.kpi_key;
  const functionOptions = functionOptionsFor(workspace.options).map((value) => ({ value, label: value }));
  const teamOptions = teamOptionsFor(workspace.options.teams, filters.teamFunction, workspace.options.team_functions).map((value) => ({ value, label: value }));
  const additionalActiveCount = [filters.position, filters.kpi].filter(Boolean).length;
  const additionalFilterControls = (
    <div className="responsive-filter-content responsive-filter-content--insights-extra">
      <FilterSelect label="Position" value={filters.position || ''} onChange={(value) => { update('position', value); update('employeeId', ''); }} allLabel="All positions" options={workspace.options.positions.map((value) => ({ value, label: value }))} />
      <FilterSelect label="KPI" value={filters.kpi || ''} onChange={(value) => update('kpi', value)} allLabel="All KPIs" options={workspace.options.kpis.map((kpi) => ({ value: kpi.key, label: kpi.label }))} />
      <button type="button" onClick={clearAnalysis} className="min-h-11 rounded-xl border border-[var(--input-border)] px-4 text-sm font-bold text-[var(--text-secondary)] hover:text-red-600">Clear analysis</button>
    </div>
  );

  // One KPI diagnosis row per scored KPI. Selecting a row selects the KPI (the existing `kpi` filter).
  const diagnosisRows = workspace.kpi_diagnosis ?? [];
  const criticalInsights = workspace.priority_insights.filter((insight) => insight.severity === 'critical');
  // People below target on the selected KPI. The analysis is for the selected KPI when one is selected.
  const peopleBelowTarget: PersonBelowTarget[] = filters.kpi && workspace.people_contribution_analysis?.kpi_key === filters.kpi
    ? workspace.people_contribution_analysis.rows
      .filter((row) => row.target_status === 'missed')
      .map((row) => ({
        employee_id: row.employee_id,
        employee_name: row.employee_name,
        team: row.team,
        performance_level: row.performance_level,
      }))
    : [];
  const canAddForPerson = (person: PersonBelowTarget) => quickActionRows.has(
    `${person.team}\u0000${person.employee_id}\u0000${person.performance_level}`,
  );
  const openActionForPerson = (person: PersonBelowTarget) => {
    const employee = quickActionRows.get(`${person.team}\u0000${person.employee_id}\u0000${person.performance_level}`);
    if (employee) setModalEmployee(employee);
  };
  const executiveHref = `/executive${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
  const selectedKpiLabel = filters.kpi
    ? (workspace.options.kpis.find((item) => item.key === filters.kpi)?.label || filters.kpi)
    : null;

  return (
    <div className="app-page-shell rf-page rf-page--insights insights-page [--app-section-gap:16px] [--rf-page-gap:16px]">
      <InsightHeader
        period={effectivePeriod}
        periodOptions={workspace.options.periods.map((period) => ({ value: period.key, label: `${period.month} ${period.year}` }))}
        onPeriodChange={(value) => update('periodKey', value)}
        region={filters.region || ''}
        regionOptions={workspace.options.regions.map((value) => ({ value, label: value }))}
        onRegionChange={selectRegion}
        branch={filters.branch || ''}
        branchOptions={branchOptions}
        onBranchChange={selectBranch}
        functionValue={filters.teamFunction || ''}
        functionOptions={functionOptions}
        onFunctionChange={selectFunction}
        team={filters.team || ''}
        teamOptions={teamOptions}
        onTeamChange={selectTeam}
        level={filters.performanceLevel || ''}
        levelOptions={workspace.options.performance_levels.map((value) => ({ value, label: value }))}
        onLevelChange={(value) => {
          setUserFilters((current) => ({
            ...current,
            performanceLevel: value || undefined,
            position: undefined,
            employeeId: undefined,
            kpi: undefined,
          }));
        }}
        additionalFilters={additionalFilterControls}
        additionalActiveCount={additionalActiveCount}
      />

      {/* Existing secondary controls kept from the previous Insights page (not part of Figma 18:3). */}
      <div className="insights-filter-tools flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-end gap-2 text-xs text-[var(--text-muted)]">
          {query.isFetching && <Loader2 size={14} className="animate-spin text-[var(--insights-accent)]" aria-label="Refreshing insights" />}
          {shareNotice && <span role="status" className="font-bold text-[var(--insights-accent-text)]">{shareNotice}</span>}
          {exportError && <span role="alert" className="font-bold text-rose-600">{exportError}</span>}
          <button type="button" onClick={() => void handleShare()} className="inline-flex h-[32px] items-center gap-1.5 rounded-[8px] border border-[var(--insights-card-border)] bg-[var(--bg-surface)] px-3 font-semibold text-[var(--text-secondary)] transition hover:border-[var(--insights-accent-border)]"><Share2 size={14} /> Share</button>
          <button type="button" onClick={() => void handleExport()} disabled={exportState === 'exporting'} className="inline-flex h-[32px] items-center gap-1.5 rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-3 font-semibold text-[var(--insights-accent-text)] transition hover:border-[var(--insights-accent)] disabled:cursor-wait disabled:opacity-70">{exportState === 'exporting' ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} {exportState === 'exporting' ? 'Exporting PPTX…' : 'Export PowerPoint'}</button>
        </div>
        {activeFilterEntries.length > 0 && <div className="flex flex-wrap items-center gap-2"><span className="mr-1 text-xs font-black uppercase tracking-[0.14em] text-[var(--text-faint)]">{analysisDepth}</span>{activeFilterEntries.map((entry) => <button key={entry.key} type="button" onClick={() => clearFilter(entry.key)} className="inline-flex items-center gap-1.5 rounded-full border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-2.5 py-1 text-xs font-bold text-[var(--insights-accent-text)] hover:border-[var(--insights-accent)]">{entry.label}: {entry.value}<X size={12} /></button>)}<button type="button" onClick={clearAnalysis} className="ml-auto text-xs font-bold text-[var(--text-muted)] hover:text-rose-600">Reset analysis</button></div>}
      </div>

      <InsightsSummaryStrip
        story={workspace.executive_story}
        rows={diagnosisRows}
        criticalInsights={criticalInsights}
        onOpenInsight={(insight) => setDrawerInsight(insight)}
      />

      <KpiDiagnosisTable
        rows={diagnosisRows}
        selectedKey={filters.kpi || null}
        onSelect={(key) => update('kpi', key ?? '')}
      />

      {filters.kpi && selectedKpiTrend && (
        <section className="overflow-hidden rounded-[12px] border border-[var(--insights-card-border)] bg-[var(--bg-surface)]" aria-label="Selected KPI trend">
          <KpiSixMonthTrend trend={selectedKpiTrend} />
        </section>
      )}

      <PeopleToReviewSection
        analysis={workspace.people_contribution_analysis}
        onOpenEmployee={openEmployee}
        fullAnalysisOpen={Boolean(leadingPeopleKpi) && filters.kpi === leadingPeopleKpi}
        onOpenFullAnalysis={leadingPeopleKpi ? () => update('kpi', leadingPeopleKpi) : undefined}
        onBackToOverview={() => update('kpi', '')}
      />

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
              return <span className="text-xs font-semibold text-[var(--text-muted)]">Unavailable</span>;
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

      <InsightsActionsSection
        kpiKey={filters.kpi || null}
        kpiLabel={selectedKpiLabel}
        actions={getAllActions()}
        team={filters.team || undefined}
        month={workspace.comparison.current?.month || undefined}
        peopleBelowTarget={peopleBelowTarget}
        onAddActionForFirst={openActionForPerson}
        canAddForPerson={canAddForPerson}
      />

      <p className="text-[13px] text-[var(--text-secondary)]">
        <Link to={executiveHref} className="font-semibold text-blue-600 hover:underline">Teams and regions are on the Executive Summary</Link>
      </p>

      {(workspace.tracking_indicators ?? []).length > 0 && (
        <div className="mt-4">
          <TrackingIndicatorsCard indicators={workspace.tracking_indicators ?? []} />
        </div>
      )}

      <InsightDetailDrawer key={drawerInsight?.id || 'closed'} insight={drawerInsight} onClose={() => setDrawerInsight(null)} />
      {modalEmployee && (
        <EmployeeActionModal
          employee={modalEmployee}
          month={quickActionMonth}
          onClose={() => setModalEmployee(null)}
        />
      )}
    </div>
  );
}
