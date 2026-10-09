import './PageEnhancements.css';
import { useEffect, useState } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';
import { useUserRole } from '../context/RoleContext';
import { executiveViewForRole, readHasUnrestrictedTeamAccess } from '../lib/access';
import { directorScope } from '../lib/directorScope';
import { monthNameFromPeriodKey, overviewPeriodSelector, previousReportingSelector } from '../hooks/api/scopedPeriod';
import { motion } from 'framer-motion';
import { Users, TrendingUp, Award, AlertTriangle, CalendarDays, ChevronDown, ClipboardList, Globe, MapPin } from 'lucide-react';
import Breadcrumb from '../components/common/Breadcrumb';
import { useAuth } from '../context/auth';
import { useAllTeamsSummary, usePerformanceData } from '../hooks/usePerformanceData';
import { scopedPerformanceApiEnabled, useScopedExecutiveSummary } from '../hooks/api/usePerformanceDashboard';
import { useActionStore } from '../hooks/useActionStore';
import { useMonthParam } from '../hooks/useMonthParam';
import { useLocationParam } from '../hooks/useLocationParam';
import TeamSummaryTable from '../components/executive/TeamSummaryTable';
import PerformanceLevelFilter from '../components/common/PerformanceLevelFilter';
import ResponsiveFilters from '../components/common/ResponsiveFilters';
import { usePerformanceLevelParam } from '../hooks/usePerformanceLevelParam';
import ActionsSummaryCard from '../components/executive/ActionsSummaryCard';
import ExecutivePerformancePanel from '../components/executive/ExecutivePerformancePanel';
import { ExecutiveViewSkeleton } from '../components/common/SkeletonLoader';
import NoDataEmptyState from '../components/common/NoDataEmptyState';
import KpiCard from '../components/common/KpiCard';
import { summarizeRootCauses } from '../utils/rootCauseInsights';
import type { LocationKey } from '../types';
import { apiFetch } from '../lib/apiClient';
import { filterActionsByPerformanceScope } from '../features/executive/actionScope';

type RegionFilter = 'All' | 'EGY' | 'UAE';

const REGION_OPTIONS: Array<{ value: RegionFilter; label: string }> = [
  { value: 'All', label: 'All Regions' },
  { value: 'EGY', label: 'Egypt (EGY)' },
  { value: 'UAE', label: 'UAE' },
];

const BRANCH_OPTIONS: Array<{ value: LocationKey; label: string }> = [
  { value: 'all', label: 'All Branches' },
  { value: 'dubai', label: 'Dubai' },
  { value: 'sharjah', label: 'Sharjah (Sharqa)' },
  { value: 'ajman', label: 'Ajman' },
  { value: 'clinics', label: 'Clinics' },
];

function canonicalRegion(value: string | null | undefined): RegionFilter | null {
  const normalized = value?.trim().toUpperCase();
  if (normalized === 'EGY' || normalized === 'UAE') return normalized;
  return null;
}

const ExecutiveOverview = () => {
  const { role } = useUserRole();
  const { currentUser } = useAuth();
  const assigned = directorScope(role, currentUser);
  const [searchParams, setSearchParams] = useSearchParams();
  const { location: locationFromUrl, setLocation } = useLocationParam('all');
  const { month: monthParam } = useMonthParam('All');
  const { performanceLevel, setPerformanceLevel } = usePerformanceLevelParam('All');
  const [weightsList, setWeightsList] = useState<Array<{ team: string; weights: Record<string, number> }>>([]);
  const periodSelector = overviewPeriodSelector(searchParams.get('period'), monthParam);
  const selectedMonth = monthNameFromPeriodKey(periodSelector) || monthParam;
  // Assigned branch and region stay in force even when the URL, reset, or back stack says otherwise.
  const forcedRegion = assigned.regionLocked ? canonicalRegion(assigned.region) : null;
  const region: RegionFilter = assigned.regionLocked ? (forcedRegion ?? 'All') : (canonicalRegion(searchParams.get('region')) ?? 'All');
  const forcedBranch = assigned.branchLocked && assigned.branch && BRANCH_OPTIONS.some((option) => option.value === assigned.branch)
    ? assigned.branch as LocationKey
    : null;
  const locationKey: LocationKey = assigned.branchLocked ? (forcedBranch ?? 'all') : locationFromUrl;
  const legacySummary = useAllTeamsSummary(periodSelector, region, locationKey, performanceLevel, weightsList, !scopedPerformanceApiEnabled);
  const scopedSummary = useScopedExecutiveSummary(periodSelector, region, locationKey, performanceLevel);
  const { summaries, totalAgents, uniqueTeamCount, overallAvgScore, pctAB, pctDE, allClassCounts, loading, dataSource, errorMessage } = scopedPerformanceApiEnabled
    ? scopedSummary
    : legacySummary;
  const legacyAllData = usePerformanceData('All', locationKey, region, performanceLevel, !scopedPerformanceApiEnabled);
  const uniqueMonths = scopedPerformanceApiEnabled ? scopedSummary.uniqueMonths : legacyAllData.uniqueMonths;
  const allAgents = scopedPerformanceApiEnabled ? [] : legacyAllData.agents;
  const activeMonth = selectedMonth === 'All'
    ? (scopedPerformanceApiEnabled ? scopedSummary.activePeriod?.month : uniqueMonths[uniqueMonths.length - 1]) || 'January'
    : selectedMonth;
  const activeMonthIndex = uniqueMonths.indexOf(activeMonth);
  const legacyPreviousKey = !scopedPerformanceApiEnabled && periodSelector !== 'All'
    ? previousReportingSelector(
        legacyAllData.agents.map((agent) => ({ month: agent.identity.month, year: agent.year })),
        periodSelector,
      )
    : null;
  const previousMonth = scopedPerformanceApiEnabled
    ? scopedSummary.previousPeriod?.month || null
    : legacyPreviousKey
      ?? (selectedMonth !== 'All' && activeMonthIndex > 0 ? uniqueMonths[activeMonthIndex - 1] : null);
  const legacyPreviousSummary = useAllTeamsSummary(
    previousMonth || activeMonth,
    region,
    locationKey,
    performanceLevel,
    weightsList,
    !scopedPerformanceApiEnabled,
  );
  const previousData = scopedPerformanceApiEnabled
    ? {
      summaries: scopedSummary.previousSummaries,
      previousTotalAgents: scopedSummary.previousTotalAgents,
      previousOverallAvgScore: scopedSummary.previousOverallAvgScore,
      previousPctAB: scopedSummary.previousPctAB,
      previousPctDE: scopedSummary.previousPctDE,
    }
    : {
      summaries: legacyPreviousSummary.summaries,
      previousTotalAgents: legacyPreviousSummary.totalAgents,
      previousOverallAvgScore: legacyPreviousSummary.overallAvgScore,
      previousPctAB: legacyPreviousSummary.pctAB,
      previousPctDE: legacyPreviousSummary.pctDE,
    };
  const {
    summaries: previousSummaries,
    previousTotalAgents,
    previousOverallAvgScore,
    previousPctAB,
    previousPctDE,
  } = previousData;
  const headcountMoM = previousMonth && previousTotalAgents > 0
    ? ((totalAgents - previousTotalAgents) / previousTotalAgents) * 100
    : undefined;
  const scoreMoM = previousMonth && previousOverallAvgScore !== 0
    ? overallAvgScore - previousOverallAvgScore
    : undefined;
  const pctABMoM = previousMonth && previousPctAB !== 0 ? pctAB - previousPctAB : undefined;
  const pctDEMoM = previousMonth && previousPctDE !== 0 ? pctDE - previousPctDE : undefined;
  const { getAllActions } = useActionStore();
  const teamCountLabel = uniqueTeamCount || new Set(summaries.map((summary) => summary.teamId)).size;

  useEffect(() => {
    // The scoped summary already contains the data needed by this page. The
    // legacy weights request is only required by the legacy aggregation path.
    if (scopedPerformanceApiEnabled) return;

    apiFetch<{ success: boolean; data: Array<{ team: string; weights: Record<string, number> }> }>('/api/settings/weights')
      .then((res) => {
        if (res?.success && Array.isArray(res.data)) {
          setWeightsList(res.data);
        }
      })
      .catch(() => { });
  }, [region]);

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    console.debug('performance_summary', {
      page: 'Executive Summary',
      month: selectedMonth,
      region,
      branch: locationKey,
      recordsUsed: totalAgents,
      uniqueTeams: summaries.map((summary) => summary.teamName),
      uniqueTeamCount: teamCountLabel,
      averageScore: overallAvgScore,
      classABCount: allClassCounts.A + allClassCounts.B,
      classABPercentage: pctAB,
      classDECount: allClassCounts.D + allClassCounts.E,
      classDEPercentage: pctDE,
    });
  }, [selectedMonth, region, locationKey, totalAgents, summaries, teamCountLabel, overallAvgScore, allClassCounts, pctAB, pctDE]);

  const allActions = getAllActions();
  const scopedActions = currentUser?.role === 'Manager' && !readHasUnrestrictedTeamAccess(currentUser)
    ? allActions.filter((action) => {
        const team = (action.team || '').toLowerCase();
        return (currentUser.accessible_teams || []).some((assignedTeam) => assignedTeam.toLowerCase() === team);
      })
    : allActions;
  const dashboardScopedActions = scopedPerformanceApiEnabled
    ? (currentUser?.role === 'Agent' || currentUser?.role === 'Executive'
      ? scopedActions.filter((action) => String(action.employee_id || '') === String(currentUser.employee_id || ''))
      : scopedActions)
    : filterActionsByPerformanceScope(scopedActions, allAgents);
  const actionStats = summarizeRootCauses(
    dashboardScopedActions.filter((action) => action.month === activeMonth)
  );
  const setRegion = (value: RegionFilter) => {
    if (assigned.regionLocked) return;
    const next = new URLSearchParams(searchParams);
    if (value === 'All') next.delete('region');
    else next.set('region', value);
    setSearchParams(next);
  };
  const setBranch = (value: LocationKey) => {
    if (assigned.branchLocked) return;
    setLocation(value);
  };
  const onMonthChange = (value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('month', value);
    next.delete('period');
    setSearchParams(next);
  };
  const clearFilters = () => {
    const next = new URLSearchParams(searchParams);
    if (!assigned.regionLocked) next.delete('region');
    if (!assigned.branchLocked) {
      next.delete('branch');
      next.delete('location');
      next.delete('branches');
    }
    next.delete('performance_level');
    setSearchParams(next, { replace: true });
  };
  const regionOptions = assigned.regionLocked
    ? forcedRegion
      ? REGION_OPTIONS.filter((option) => option.value === forcedRegion)
      : [{ value: 'All' as const, label: assigned.regionLabel }]
    : REGION_OPTIONS;
  const branchOptions = assigned.branchLocked
    ? forcedBranch
      ? BRANCH_OPTIONS.filter((option) => option.value === forcedBranch)
      : [{ value: 'all' as const, label: assigned.branchLabel }]
    : BRANCH_OPTIONS;
  const monthOptions = selectedMonth !== 'All' && !uniqueMonths.includes(selectedMonth)
    ? [...uniqueMonths, selectedMonth]
    : uniqueMonths;
  const activeFilterCount = [
    performanceLevel !== 'All',
    region !== 'All',
    locationKey !== 'all',
    selectedMonth !== 'All',
  ].filter(Boolean).length;
  const clearableCount = [
    performanceLevel !== 'All',
    !assigned.regionLocked && region !== 'All',
    !assigned.branchLocked && locationKey !== 'all',
  ].filter(Boolean).length;

  if (loading) {
    return <ExecutiveViewSkeleton />;
  }



  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.35 }}
      className="app-page-shell rf-page rf-page--executive"
    >
      {/* Page Header */}
      <div className="executive-page-heading rf-page-heading-row flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="executive-page-title flex min-w-0 flex-col gap-1">
          <h2 className="heading-2 mb-0">Executive Overview</h2>
          <Breadcrumb
            items={[
              { label: 'Dashboard', href: '/executive', icon: 'home' },
              { label: 'Executive Overview', icon: 'dashboard' },
            ]}
          />
        </div>

        {/* Selectors */}
        <ResponsiveFilters activeCount={activeFilterCount} clearableCount={clearableCount} onClear={clearFilters}>
          <PerformanceLevelFilter value={performanceLevel} onChange={setPerformanceLevel} />
          {/* Region Selector */}
          <div className="relative group flex-1 sm:flex-none min-w-[130px] sm:min-w-[150px]">
            <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
            <select
              aria-label="Filter by region"
              title={assigned.regionLocked ? 'Assigned region' : undefined}
              value={region}
              disabled={assigned.regionLocked}
              onChange={(event) => setRegion(event.target.value as RegionFilter)}
              className="w-full appearance-none bg-[var(--bg-surface)] border border-[var(--border-medium)] text-[var(--text-primary)] text-xs font-semibold rounded-xl pl-8 pr-7 py-2.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all cursor-pointer shadow-sm disabled:cursor-not-allowed disabled:opacity-70"
            >
              {regionOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
          </div>

          {/* Branch Selector */}
          <div className="relative group flex-1 sm:flex-none min-w-[130px] sm:min-w-[150px]">
            <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
            <select
              aria-label="Filter by branch"
              title={assigned.branchLocked ? 'Assigned branch' : undefined}
              value={locationKey}
              disabled={assigned.branchLocked}
              onChange={(event) => setBranch(event.target.value as LocationKey)}
              className="w-full appearance-none bg-[var(--bg-surface)] border border-[var(--border-medium)] text-[var(--text-primary)] text-xs font-semibold rounded-xl pl-8 pr-7 py-2.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all cursor-pointer shadow-sm disabled:cursor-not-allowed disabled:opacity-70"
            >
              {branchOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
          </div>

          {/* Month Selector */}
          <div className="relative group flex-1 sm:flex-none min-w-[130px] sm:min-w-[150px]">
            <CalendarDays className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
            <select
              aria-label="Filter by month"
              value={selectedMonth}
              onChange={(event) => onMonthChange(event.target.value)}
              className="w-full appearance-none bg-[var(--bg-surface)] border border-[var(--border-medium)] text-[var(--text-primary)] text-xs font-semibold rounded-xl pl-8 pr-7 py-2.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all cursor-pointer shadow-sm"
            >
              <option value="All">All Months</option>
              {monthOptions.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
          </div>
        </ResponsiveFilters>
      </div>

      {totalAgents === 0 ? (
        <NoDataEmptyState
          availablePeriods={uniqueMonths.map(m => ({ month: m, year: new Date().getFullYear() }))}
          selectedMonth={selectedMonth}
          dataSource={dataSource}
          errorMessage={errorMessage}
          onSelectPeriod={onMonthChange}
        />
      ) : (
        <>
          {/* All-Months Warning Banner */}
          {selectedMonth === 'All' && (
            <div className="rounded-xl border border-amber-400/30 bg-amber-500/8 px-4 py-3 text-xs font-semibold text-amber-700 dark:text-amber-300 flex items-center gap-2">
              <AlertTriangle size={14} className="shrink-0" />
              Performance metrics are aggregated across all selected months. Headcount is shown from the latest available month.
            </div>
          )}

          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            <KpiCard
              icon={<Users size={17} />}
              label="Total Agents"
              value={totalAgents.toString()}
              sub={`Across ${teamCountLabel} ${teamCountLabel === 1 ? 'team' : 'teams'}`}
              trendDelta={headcountMoM}
              showStableTrend
              note={activeMonth
                ? `${selectedMonth === 'All' ? 'Latest headcount' : 'Headcount'} · ${activeMonth}`
                : 'Headcount unavailable'}
              accent="border-l-blue-500"
            />
            <KpiCard
              icon={<TrendingUp size={17} />}
              label="Avg Performance Score"
              value={`${overallAvgScore.toFixed(1)}%`}
              sub="All teams combined"
              trendDelta={scoreMoM}
              accent="border-l-indigo-500"
            />
            <KpiCard
              icon={<Award size={17} />}
              label="Class A & B (≥80%)"
              value={`${pctAB.toFixed(1)}%`}
              sub={`${(allClassCounts.A + allClassCounts.B)} agents meeting expectations`}
              trendDelta={pctABMoM}
              accent="border-l-emerald-500"
            />
            <KpiCard
              icon={<AlertTriangle size={17} />}
              label="Class D & E (<70%)"
              value={`${pctDE.toFixed(1)}%`}
              sub={`${(allClassCounts.D + allClassCounts.E)} agents need attention`}
              trendDelta={pctDEMoM}
              lowerTrendIsBetter
              accent="border-l-red-500"
            />
          </div>

          {/* Main Content Grid */}
          <div className="grid grid-cols-1 items-stretch gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(360px,1fr)]">

            {/* Grade Distribution Chart — 2 cols */}
            <ExecutivePerformancePanel
              classCounts={allClassCounts}
              teams={summaries}
              previousTeams={previousMonth ? previousSummaries : []}
              currentMonth={activeMonth}
              previousMonth={previousMonth}
              performanceLevel={performanceLevel}
            />

            {/* Actions Summary — 1 col */}
            <div className="glass-panel flex h-full min-w-0 flex-col rounded-xl p-4 shadow-sm sm:p-5">
              <div className="mb-4 flex items-center gap-2">
                <ClipboardList size={18} className="text-purple-500" />
                <h3 className="heading-3">Actions Summary</h3>
                <span className="ml-auto text-xs text-[var(--text-secondary)] bg-[var(--bg-sunken)] px-2 py-0.5 rounded-full font-semibold">
                  {activeMonth}
                </span>
              </div>
              <div className="min-h-0 flex-1">
                <ActionsSummaryCard month={activeMonth} stats={actionStats} />
              </div>
            </div>
          </div>

          {/* Team Summary Table */}
          <div className="glass-panel rounded-xl p-6 shadow-sm">
            <div className="flex items-center gap-2 mb-5">
              <Users size={18} className="text-blue-500" />
              <h3 className="heading-3">Team Summary</h3>
              <span className="ml-auto text-xs text-[var(--text-secondary)] font-semibold bg-[var(--bg-sunken)] px-2.5 py-1 rounded-full">
                {currentUser?.role === 'Manager' ? 'Assigned teams only' : 'Click team to drill down'}
              </span>
            </div>
            <TeamSummaryTable teams={summaries} currentMonth={activeMonth} performanceLevel={performanceLevel} />
          </div>
        </>
      )}
    </motion.div>
  );
};

const ExecutiveView = () => {
  const { role } = useUserRole();
  if (executiveViewForRole(role) === 'function') return <Navigate to="/function-summary" replace />;
  return <ExecutiveOverview />;
};

export default ExecutiveView;
