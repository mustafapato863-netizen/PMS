import './PageEnhancements.css';
import { useEffect, useState } from 'react';
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

const ExecutiveView = () => {
  const [region, setRegion] = useState<'All' | 'EGY' | 'UAE'>('All');
  const { currentUser } = useAuth();
  const { location, setLocation } = useLocationParam('all');
  const { month, setMonth } = useMonthParam('All');
  const { performanceLevel, setPerformanceLevel } = usePerformanceLevelParam('All');
  const [weightsList, setWeightsList] = useState<Array<{ team: string; weights: Record<string, number> }>>([]);
  const locationKey: LocationKey = (['all', 'dubai', 'sharjah', 'ajman', 'clinics'].includes(location)
    ? location
    : 'all') as LocationKey;
  const legacySummary = useAllTeamsSummary(month, region, locationKey, performanceLevel, weightsList, !scopedPerformanceApiEnabled);
  const scopedSummary = useScopedExecutiveSummary(month, region, locationKey, performanceLevel);
  const { summaries, totalAgents, uniqueTeamCount, overallAvgScore, pctAB, pctDE, allClassCounts, loading, dataSource, errorMessage } = scopedPerformanceApiEnabled
    ? scopedSummary
    : legacySummary;
  const legacyAllData = usePerformanceData('All', locationKey, region, performanceLevel, !scopedPerformanceApiEnabled);
  const uniqueMonths = scopedPerformanceApiEnabled ? scopedSummary.uniqueMonths : legacyAllData.uniqueMonths;
  const allAgents = scopedPerformanceApiEnabled ? [] : legacyAllData.agents;
  const activeMonth = month === 'All'
    ? (scopedPerformanceApiEnabled ? scopedSummary.activePeriod?.month : uniqueMonths[uniqueMonths.length - 1]) || 'January'
    : month;
  const activeMonthIndex = uniqueMonths.indexOf(activeMonth);
  const previousMonth = scopedPerformanceApiEnabled
    ? scopedSummary.previousPeriod?.month || null
    : month !== 'All' && activeMonthIndex > 0
      ? uniqueMonths[activeMonthIndex - 1]
      : null;
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
      month,
      region,
      branch: location,
      recordsUsed: totalAgents,
      uniqueTeams: summaries.map((summary) => summary.teamName),
      uniqueTeamCount: teamCountLabel,
      averageScore: overallAvgScore,
      classABCount: allClassCounts.A + allClassCounts.B,
      classABPercentage: pctAB,
      classDECount: allClassCounts.D + allClassCounts.E,
      classDEPercentage: pctDE,
    });
  }, [month, region, location, totalAgents, summaries, teamCountLabel, overallAvgScore, allClassCounts, pctAB, pctDE]);

  const allActions = getAllActions();
  const scopedActions = currentUser?.role === 'Manager' && !currentUser.is_general_manager
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
      <div className="rf-page-heading-row flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="flex flex-col gap-1">
          <h2 className="heading-2 mb-0">Executive Overview</h2>
          <Breadcrumb
            items={[
              { label: 'Dashboard', icon: 'home' },
              { label: 'Executive Overview', icon: 'dashboard' },
            ]}
          />
        </div>

        {/* Selectors */}
        <div className="flex w-full flex-wrap items-center gap-2.5 sm:gap-3 xl:w-auto xl:justify-end">
          <PerformanceLevelFilter value={performanceLevel} onChange={setPerformanceLevel} />
          {/* Region Selector */}
          <div className="relative group flex-1 sm:flex-none min-w-[130px] sm:min-w-[150px]">
            <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
            <select
              aria-label="Filter by region"
              value={region}
              onChange={(e) => setRegion(e.target.value as 'All' | 'EGY' | 'UAE')}
              className="w-full appearance-none bg-[var(--bg-surface)] border border-[var(--border-medium)] text-[var(--text-primary)] text-xs font-semibold rounded-xl pl-8 pr-7 py-2.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all cursor-pointer shadow-sm"
            >
              <option value="All">All Regions</option>
              <option value="EGY">Egypt (EGY)</option>
              <option value="UAE">UAE</option>
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
          </div>

          {/* Branch Selector */}
          <div className="relative group flex-1 sm:flex-none min-w-[130px] sm:min-w-[150px]">
            <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
            <select
              aria-label="Filter by branch"
              value={location}
              onChange={(e) => setLocation(e.target.value as LocationKey)}
              className="w-full appearance-none bg-[var(--bg-surface)] border border-[var(--border-medium)] text-[var(--text-primary)] text-xs font-semibold rounded-xl pl-8 pr-7 py-2.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all cursor-pointer shadow-sm"
            >
              <option value="all">All Branches</option>
              <option value="dubai">Dubai</option>
              <option value="sharjah">Sharjah (Sharqa)</option>
              <option value="ajman">Ajman</option>
              <option value="clinics">Clinics</option>
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
          </div>

          {/* Month Selector */}
          <div className="relative group flex-1 sm:flex-none min-w-[130px] sm:min-w-[150px]">
            <CalendarDays className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
            <select
              aria-label="Filter by month"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              className="w-full appearance-none bg-[var(--bg-surface)] border border-[var(--border-medium)] text-[var(--text-primary)] text-xs font-semibold rounded-xl pl-8 pr-7 py-2.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all cursor-pointer shadow-sm"
            >
              <option value="All">All Months</option>
              {uniqueMonths.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
          </div>
        </div>
      </div>

      {totalAgents === 0 ? (
        <NoDataEmptyState
          availablePeriods={uniqueMonths.map(m => ({ month: m, year: new Date().getFullYear() }))}
          selectedMonth={month}
          dataSource={dataSource}
          errorMessage={errorMessage}
          onSelectPeriod={(m) => setMonth(m)}
        />
      ) : (
        <>
          {/* All-Months Warning Banner */}
          {month === 'All' && (
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
                ? `${month === 'All' ? 'Latest headcount' : 'Headcount'} · ${activeMonth}`
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

export default ExecutiveView;
