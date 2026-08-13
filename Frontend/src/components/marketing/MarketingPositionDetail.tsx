import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Award,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Gauge,
  Lightbulb,
  SlidersHorizontal,
  Target,
  TrendingDown,
  TrendingUp,
  Users,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import type { PerformanceLevelFilter, PMSAction } from '../../types';
import type {
  MarketingAnalytics,
  MarketingKpiAggregate,
  MarketingTeamConfig,
} from '../../features/marketing/types';
import {
  buildKpiAnalysis,
  buildKpiRecommendation,
  formatMarketingGap,
  rankKpisByNegativeImpact,
} from '../../features/marketing/marketingPositionAnalysis';
import type { KpiAnalysisTone } from '../../features/marketing/marketingPositionAnalysis';
import { getMarketingKpiIcon } from '../../features/marketing/marketingKpiIcons';
import { formatMarketingValue } from '../../features/marketing/marketingNumberFormat';
import { GRADE_PALETTE } from '../../constants/grades';
import SummaryKpiCard from '../common/KpiCard';
import MoMIndicator from '../common/MoMIndicator';
import PerformanceKpiCard from '../common/PerformanceKpiCard';
import type { PerformanceKpiBadgeType } from '../common/PerformanceKpiCard';
import { resolveKpiTargetStatus } from '../common/performanceKpiProgress';
import EmployeeRowActions from '../team/EmployeeRowActions';
import TeamChartsSection from '../team/TeamChartsSection';

const EMPLOYEE_PAGE_SIZE = 10;

const KPI_TONES: Record<
  ReturnType<typeof resolveKpiTargetStatus>['status'],
  { badgeType: PerformanceKpiBadgeType; label: string }
> = {
  on_target: { badgeType: 'success', label: 'On Target' },
  needs_attention: { badgeType: 'warning', label: 'Needs Attention' },
  below_target: { badgeType: 'danger', label: 'Below Target' },
  no_data: { badgeType: 'neutral', label: 'No Data' },
  target_review: { badgeType: 'neutral', label: 'Target Requires Review' },
};

const PositionKpiCard = ({ kpi }: { kpi: MarketingKpiAggregate }) => {
  const targetState = resolveKpiTargetStatus(
    kpi.averageActual,
    kpi.averageTarget,
    kpi.direction === 'lower_better',
  );
  const tone = KPI_TONES[targetState.status];
  const analysis = buildKpiAnalysis(kpi);
  const kpiIcon = getMarketingKpiIcon(kpi);
  const actual = formatMarketingValue(kpi.averageActual, kpi.unit);
  const target = formatMarketingValue(kpi.averageTarget, kpi.unit);
  return (
    <PerformanceKpiCard
      icon={kpiIcon}
      iconAccentColor={kpi.color}
      label={kpi.label}
      value={actual.display}
      targetValue={target.display}
      detailLabel={kpi.direction === 'lower_better' ? 'Lower is better' : 'Higher is better'}
      badgeText={tone.label}
      badgeType={tone.badgeType}
      trendDelta={kpi.achievementDelta}
      isTrendGood={analysis.movement.positive ?? undefined}
      progressPercent={targetState.progressPercent}
      contribution={kpi.averageContribution}
      weight={kpi.weight}
    />
  );
};

interface MarketingPositionDetailProps {
  analytics: MarketingAnalytics;
  position: string;
  thresholds: MarketingTeamConfig['grade_thresholds'];
  role?: string;
  getActionsForEmployee?: (employeeId: string) => PMSAction[];
  onAddAction?: (row: TeamAgentRow) => void;
  onEmployeeChanged?: () => void;
}

const MarketingPositionDetail = ({
  analytics,
  position,
  thresholds,
  role = 'Viewer',
  getActionsForEmployee = () => [],
  onAddAction = () => undefined,
  onEmployeeChanged,
}: MarketingPositionDetailProps) => {
  const [rosterView, setRosterView] = useState<'top_bottom' | 'all'>('top_bottom');
  const [employeeView, setEmployeeView] = useState<'all' | 'attention'>('all');
  const [employeePage, setEmployeePage] = useState(1);
  const [showAllAnalysis, setShowAllAnalysis] = useState(false);
  const [expandedKpis, setExpandedKpis] = useState<Record<string, boolean>>({});
  const grades = analytics.gradeDistribution;
  const gradeData = Object.entries(grades).map(([grade, value]) => ({
    name: `Grade ${grade}`,
    value,
    color: GRADE_PALETTE[grade as keyof typeof GRADE_PALETTE].text,
  }));
  const trendData = analytics.trend.map((point) => ({ month: point.period, score: point.score }));
  const filteredEmployees = useMemo(() => {
    if (employeeView === 'attention') {
      return analytics.employeeRows.filter((employee) => employee.grade === 'D' || employee.grade === 'E');
    }
    return analytics.employeeRows;
  }, [analytics.employeeRows, employeeView]);
  const employeePages = Math.max(1, Math.ceil(filteredEmployees.length / EMPLOYEE_PAGE_SIZE));
  const safeEmployeePage = Math.min(employeePage, employeePages);
  const paginatedEmployees = filteredEmployees.slice(
    (safeEmployeePage - 1) * EMPLOYEE_PAGE_SIZE,
    safeEmployeePage * EMPLOYEE_PAGE_SIZE,
  );

  const { topPerformers, bottomPerformers } = useMemo(() => {
    const rows = analytics.employeeRows;
    const topCount = Math.min(3, Math.ceil(rows.length / 2));
    const bottomCount = Math.min(3, rows.length - topCount);
    return {
      topPerformers: rows.slice(0, topCount),
      bottomPerformers: bottomCount ? rows.slice(-bottomCount).reverse() : [],
    };
  }, [analytics.employeeRows]);

  const attentionKpis = useMemo(
    () => rankKpisByNegativeImpact(analytics.kpiAggregates),
    [analytics.kpiAggregates],
  );
  const strongestKpi = useMemo(
    () => analytics.kpiAggregates
      .filter((kpi) => kpi.averageAchievement !== null)
      .slice()
      .sort((left, right) => (right.averageAchievement ?? 0) - (left.averageAchievement ?? 0))[0] || null,
    [analytics.kpiAggregates],
  );
  const analysisKpis = useMemo(() => {
    const attentionKeys = new Set(attentionKpis.map((kpi) => kpi.key));
    return [
      ...attentionKpis,
      ...analytics.kpiAggregates.filter((kpi) => !attentionKeys.has(kpi.key)),
    ];
  }, [analytics.kpiAggregates, attentionKpis]);
  const visibleAnalysisKpis = showAllAnalysis ? analysisKpis : analysisKpis.slice(0, 3);

  const visibleKeys = visibleAnalysisKpis.map((kpi) => kpi.key);
  const allExpanded = visibleKeys.length > 0 && visibleKeys.every((key) => !!expandedKpis[key]);

  const toggleAllExpanded = () => {
    if (allExpanded) {
      const nextExpanded = { ...expandedKpis };
      visibleKeys.forEach((key) => {
        nextExpanded[key] = false;
      });
      setExpandedKpis(nextExpanded);
    } else {
      const nextExpanded = { ...expandedKpis };
      visibleKeys.forEach((key) => {
        nextExpanded[key] = true;
      });
      setExpandedKpis(nextExpanded);
    }
  };
  const atRiskEmployees = grades.D + grades.E;
  const overallResult = !analytics.currentRecords.length
    ? 'No result available'
    : analytics.averageScore >= thresholds.A
      ? 'Exceeds expectations'
      : analytics.averageScore >= thresholds.C
        ? 'Meets expectations'
        : 'Below target';
  const employeeActionRows = useMemo(
    () => new Map(analytics.employeeRows.map((employee) => {
      const weakestKpi = employee.weakestKpi;
      const rootCauseAuto = weakestKpi
        ? weakestKpi.averageTarget === 0
          ? `${weakestKpi.label} target requires review`
          : `${weakestKpi.label} (main issue)`
        : '';
      const row: TeamAgentRow = {
        id: employee.id,
        name: employee.name,
        team: 'Marketing',
        month: employee.record.identity.month,
        performanceLevel: 'Employee',
        score: employee.score,
        displayWeightedScore: employee.score,
        gradeClass: employee.grade,
        gradeLabel: employee.record.evaluation.grade,
        status: employee.grade === 'A' || employee.grade === 'B'
          ? 'Meet'
          : employee.grade === 'C'
            ? 'Average'
            : 'Below',
        rootCauseAuto,
        rootCauseNote: employee.record.evaluation.manager_notes || '',
        correctiveAction: employee.record.evaluation.corrective_action || '',
        suggestedAction: employee.record.evaluation.suggested_action || '',
        ahtMinutes: 0,
        bookingRate: 0,
        attendRate: 0,
        raw: employee.record,
      };
      return [employee.id, row];
    })),
    [analytics.employeeRows],
  );

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryKpiCard label="Total Employees" value={String(analytics.employeeCount)} icon={<Users size={17} />} trendDelta={analytics.employeeDelta ?? undefined} accent="border-l-blue-500" />
        <SummaryKpiCard label="Average Score" value={`${analytics.averageScore.toFixed(1)}%`} icon={<TrendingUp size={17} />} trendDelta={analytics.scoreDelta ?? undefined} accent="border-l-indigo-500" />
        <SummaryKpiCard label="Class A & B" value={`${analytics.classABPercentage.toFixed(1)}%`} sub={`${grades.A + grades.B} employees`} icon={<Award size={17} />} trendDelta={analytics.classABDelta ?? undefined} accent="border-l-emerald-500" />
        <SummaryKpiCard label="Class D & E" value={`${analytics.classDEPercentage.toFixed(1)}%`} sub={`${atRiskEmployees} employees`} icon={<AlertTriangle size={17} />} trendDelta={analytics.classDEDelta ?? undefined} lowerTrendIsBetter accent="border-l-red-500" />
      </div>

      <section aria-labelledby="position-kpis-title">
        <div className="mb-3 flex items-center gap-2">
          <Gauge size={18} className="text-blue-600 dark:text-blue-400" />
          <h3 id="position-kpis-title" className="heading-3">{position} KPIs</h3>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {analytics.kpiAggregates.map((kpi) => <PositionKpiCard key={kpi.key} kpi={kpi} />)}
        </div>
        {!analytics.currentRecords.length && (
          <div className="mt-4 rounded-xl border border-dashed border-amber-400/40 bg-amber-500/8 p-4 text-center">
            <p className="font-extrabold text-amber-700 dark:text-amber-300">No uploaded results match this position and filter selection.</p>
            <p className="mt-1 text-sm font-semibold text-[var(--text-muted)]">Configured KPIs remain visible until matching data is uploaded.</p>
          </div>
        )}
      </section>

      <TeamChartsSection pieData={gradeData} trendData={trendData} />

      <section className="glass-panel overflow-hidden rounded-xl p-4 shadow-sm sm:p-5" aria-labelledby="position-roster-title">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${
              rosterView === 'top_bottom'
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                : 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
            }`}>
              {rosterView === 'top_bottom' ? <Award size={20} /> : <Users size={20} />}
            </span>
            <div>
              <h3 id="position-roster-title" className="heading-3">
                {rosterView === 'top_bottom' ? 'Top & Bottom Performers' : 'Employee Performance'}
              </h3>
              <p className="mt-1 text-xs font-semibold text-[var(--text-muted)]">
                {rosterView === 'top_bottom'
                  ? 'Highest and lowest employee scores without duplicate employees.'
                  : 'Individual results for the selected position and period.'}
              </p>
            </div>
          </div>
          <div className="relative min-w-[220px]">
            <SlidersHorizontal className="pointer-events-none absolute left-3.5 top-1/2 z-10 -translate-y-1/2 text-blue-600 dark:text-blue-400" size={16} />
            <select
              aria-label="Marketing roster view"
              value={rosterView}
              onChange={(event) => {
                setRosterView(event.target.value as 'top_bottom' | 'all');
                setEmployeePage(1);
              }}
              className="w-full cursor-pointer appearance-none rounded-xl border border-[var(--border-medium)] bg-[var(--bg-surface)] py-2.5 pl-10 pr-10 text-xs font-extrabold text-[var(--text-primary)] shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10"
            >
              <option value="top_bottom">Top/Bottom Performers</option>
              <option value="all">All Employees</option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-[var(--text-faint)]" size={16} />
          </div>
        </div>

        {rosterView === 'top_bottom' ? (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <PerformerGroup title="Top Performers" subtitle="Highest performance scores" tone="top" employees={topPerformers} />
            <PerformerGroup title="Bottom Performers" subtitle="Lowest performance scores" tone="bottom" employees={bottomPerformers} />
          </div>
        ) : (
          <>
            <div className="mb-3 flex justify-end">
              <div className="flex rounded-lg bg-[var(--bg-sunken)] p-1" role="group" aria-label="Employee performance view">
                {([
                  ['all', 'All Employees'],
                  ['attention', 'Needs Attention'],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => {
                      setEmployeeView(value);
                      setEmployeePage(1);
                    }}
                    className={`rounded-md px-3 py-2 text-xs font-extrabold transition ${employeeView === value ? 'bg-[var(--bg-surface)] text-blue-600 shadow-sm' : 'text-[var(--text-muted)]'}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="w-full overflow-x-auto rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)]">
              <table className="w-full min-w-[1080px] border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border-light)] bg-[var(--bg-sunken)]/40 text-left text-[10px] font-extrabold uppercase tracking-[0.08em] text-[var(--text-faint)]">
                    <th className="px-4 py-3">Employee</th><th className="px-4 py-3">Region</th><th className="px-4 py-3">Score</th><th className="px-4 py-3">Grade</th><th className="px-4 py-3">Trend</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Root Cause</th><th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedEmployees.map((employee) => {
                    const actionRow = employeeActionRows.get(employee.id);
                    const initials = employee.name
                      .trim()
                      .split(/\s+/)
                      .slice(0, 2)
                      .map((part) => part.charAt(0).toUpperCase())
                      .join('') || '?';
                    return (
                      <tr key={employee.id} className="border-b border-[var(--border-light)] text-sm font-semibold text-[var(--text-secondary)] transition-colors last:border-b-0 hover:bg-blue-500/[0.035]">
                        <td className="px-4 py-3">
                          <div className="flex min-w-[220px] items-center gap-3">
                            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-blue-500/10 bg-blue-500/10 text-xs font-extrabold text-blue-600 dark:text-blue-400">
                              {initials}
                            </span>
                            <div>
                              <Link
                                to={`/employee/${encodeURIComponent(employee.id)}?month=${encodeURIComponent(employee.record.identity.month)}&performance_level=Employee`}
                                className="font-extrabold text-[var(--text-primary)] transition-colors hover:text-blue-600 dark:hover:text-blue-400"
                              >
                                {employee.name}
                              </Link>
                              <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">{employee.id}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3">{employee.region}</td>
                        <td className="px-4 py-3"><span className={`score-badge score-grade-${employee.grade}`}>{employee.score.toFixed(1)}%</span></td>
                        <td className="px-4 py-3"><span className={`grade-badge grade-${employee.grade} inline-flex h-8 min-w-8 items-center justify-center rounded-lg px-2 text-xs font-extrabold`}>{employee.grade}</span></td>
                        <td className="px-4 py-3"><MoMIndicator delta={employee.scoreDelta} showStable /></td>
                        <td className="px-4 py-3">
                          <span className={`grade-status-badge status-grade-${employee.grade}`}>
                            <span className="grade-status-dot" />
                            {employee.status}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {employee.grade === 'A' || employee.grade === 'B' || !actionRow?.rootCauseAuto ? (
                            <span className="text-xs font-semibold text-[var(--text-faint)]">No gap</span>
                          ) : (
                            <div className="max-w-[190px]">
                              <Link
                                to={`/employee/${encodeURIComponent(employee.id)}?month=${encodeURIComponent(employee.record.identity.month)}&performance_level=Employee`}
                                className="line-clamp-1 text-xs font-bold text-[var(--text-secondary)] hover:text-blue-600 hover:underline dark:hover:text-blue-400"
                                title={actionRow.rootCauseAuto}
                              >
                                {actionRow.rootCauseAuto}
                              </Link>
                              <div className="mt-1 text-[10px] font-semibold text-[var(--text-faint)]">
                                Primary issue
                              </div>
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {actionRow && (
                            <EmployeeRowActions
                              row={actionRow}
                              role={role}
                              month={employee.record.identity.month}
                              performanceLevel={'Employee' as PerformanceLevelFilter}
                              teamAverage={analytics.averageScore}
                              actions={getActionsForEmployee(employee.id)}
                              onAddAction={onAddAction}
                              onEmployeeChanged={onEmployeeChanged}
                            />
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {!paginatedEmployees.length && (
                    <tr><td colSpan={8} className="px-5 py-10 text-center text-sm font-semibold text-[var(--text-muted)]">No employees match this view.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            {filteredEmployees.length > 0 && (
              <div className="mt-4 flex flex-col items-center justify-between gap-3 sm:flex-row">
                <span className="text-xs font-semibold text-[var(--text-muted)]">
                  Showing {(safeEmployeePage - 1) * EMPLOYEE_PAGE_SIZE + 1}–{Math.min(safeEmployeePage * EMPLOYEE_PAGE_SIZE, filteredEmployees.length)} of {filteredEmployees.length}
                </span>
                <div className="flex items-center gap-2">
                  <button type="button" aria-label="Previous employee page" disabled={safeEmployeePage === 1} onClick={() => setEmployeePage((page) => Math.max(1, page - 1))} className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border-medium)] text-[var(--text-secondary)] disabled:opacity-40">
                    <ChevronLeft size={16} />
                  </button>
                  <span className="text-xs font-extrabold text-[var(--text-secondary)]">{safeEmployeePage} / {employeePages}</span>
                  <button type="button" aria-label="Next employee page" disabled={safeEmployeePage === employeePages} onClick={() => setEmployeePage((page) => Math.min(employeePages, page + 1))} className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border-medium)] text-[var(--text-secondary)] disabled:opacity-40">
                    <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-[0.72fr_1.55fr]" aria-labelledby="position-summary-title">
        <div className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4 shadow-sm">
          <div className="flex items-center gap-2 text-sm font-extrabold text-[var(--text-primary)]">
            <Target size={17} className="text-blue-600 dark:text-blue-400" />
            <h3 id="position-summary-title">{position} Performance Summary</h3>
          </div>
          <div className="mt-3 space-y-2">
            <SummaryLine icon={<Gauge size={15} />} label="Overall result" value={`${overallResult}${analytics.currentRecords.length ? ` · ${analytics.averageScore.toFixed(1)}%` : ''}`} tone={analytics.currentRecords.length && analytics.averageScore < thresholds.C ? 'critical' : 'neutral'} />
            <SummaryLine icon={<Award size={15} />} label="Strongest KPI" value={strongestKpi ? `${strongestKpi.label} (${strongestKpi.averageAchievement?.toFixed(1)}%)` : 'Unavailable'} tone="positive" />
            <SummaryLine icon={<AlertTriangle size={15} />} label="KPIs needing attention" value={String(attentionKpis.length)} tone={attentionKpis.length ? 'warning' : 'positive'} />
            <SummaryLine icon={<Users size={15} />} label="Employees at risk" value={String(atRiskEmployees)} tone={atRiskEmployees ? 'critical' : 'positive'} />
            <SummaryLine icon={<TrendingDown size={15} />} label="Main score factors" value={attentionKpis.slice(0, 3).map((kpi) => kpi.label).join(', ') || 'No negative KPI gap detected'} tone={attentionKpis.length ? 'warning' : 'positive'} />
          </div>
        </div>

        <div className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4 shadow-sm" aria-labelledby="performance-analysis-title">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-extrabold text-[var(--text-primary)]">
              <Lightbulb size={16} className="text-violet-600 dark:text-violet-400" />
              <h3 id="performance-analysis-title">Performance Analysis</h3>
            </div>
            <div className="flex items-center gap-2">
              {visibleAnalysisKpis.length > 0 && (
                <button
                  type="button"
                  onClick={toggleAllExpanded}
                  className="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-[var(--border-medium)] px-2.5 text-[10px] font-extrabold text-[var(--text-secondary)] transition hover:bg-[var(--bg-sunken)]"
                >
                  {allExpanded ? 'Collapse all' : 'Expand all'}
                </button>
              )}
              {analysisKpis.length > 3 && (
                <button
                  type="button"
                  onClick={() => setShowAllAnalysis((current) => !current)}
                  aria-expanded={showAllAnalysis}
                  className="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-[var(--border-medium)] px-2.5 text-[10px] font-extrabold text-[var(--text-secondary)] transition hover:bg-[var(--bg-sunken)]"
                >
                  {showAllAnalysis ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                  {showAllAnalysis ? 'Show priority only' : `Show all ${analysisKpis.length}`}
                </button>
              )}
            </div>
          </div>
          {analytics.currentRecords.length ? (
            <>
              <div className="mt-3 space-y-2">
                {visibleAnalysisKpis.map((kpi) => (
                  <KpiAnalysisRow
                    key={kpi.key}
                    kpi={kpi}
                    isOpen={!!expandedKpis[kpi.key]}
                    onToggle={() => setExpandedKpis(prev => ({ ...prev, [kpi.key]: !prev[kpi.key] }))}
                  />
                ))}
              </div>
              <div className="mt-3 flex flex-col gap-2 rounded-lg border border-violet-500/15 bg-violet-500/[0.055] p-2.5 sm:flex-row sm:items-center">
                <span className="shrink-0 text-[10px] font-extrabold text-violet-700 dark:text-violet-300">Recommended focus</span>
                <div className="flex flex-wrap gap-2">
                  {attentionKpis.length ? attentionKpis.slice(0, 3).map((kpi) => (
                    <span key={kpi.key} className="rounded-md border border-violet-500/20 bg-[var(--bg-surface)] px-2.5 py-1 text-[9px] font-extrabold text-violet-700 dark:text-violet-300">
                      {buildKpiRecommendation(kpi)}
                    </span>
                  )) : (
                    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                      <CheckCircle2 size={14} /> Maintain current KPI performance
                    </span>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="mt-4 rounded-xl border border-dashed border-[var(--border-medium)] bg-[var(--bg-sunken)]/30 p-5 text-center text-sm font-semibold text-[var(--text-muted)]">
              Performance analysis will appear when results are available for this position and period.
            </div>
          )}
        </div>
      </section>
    </div>
  );
};

const PerformerGroup = ({
  title,
  subtitle,
  tone,
  employees,
}: {
  title: string;
  subtitle: string;
  tone: 'top' | 'bottom';
  employees: MarketingAnalytics['employeeRows'];
}) => (
  <div className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/25 p-3">
    <div className="mb-3 flex items-center gap-2.5">
      <span className={`flex h-9 w-9 items-center justify-center rounded-lg ${tone === 'top' ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'}`}>
        {tone === 'top' ? <Award size={17} /> : <AlertTriangle size={17} />}
      </span>
      <div>
        <h4 className={`text-xs font-extrabold uppercase tracking-wide ${tone === 'top' ? 'text-emerald-700 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>{title}</h4>
        <p className="mt-0.5 text-[10px] font-semibold text-[var(--text-muted)]">{subtitle}</p>
      </div>
    </div>
    <div className="space-y-2">
      {employees.length ? employees.map((employee, index) => (
        <Link key={employee.id} to={`/employee/${encodeURIComponent(employee.id)}`} className="flex min-h-14 items-center gap-3 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2.5 transition hover:border-blue-500/25">
          <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[10px] font-extrabold ${tone === 'top' ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'bg-rose-500/10 text-rose-600 dark:text-rose-300'}`}>{index + 1}</span>
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-500/10 text-xs font-extrabold text-blue-600 dark:text-blue-400">{employee.name.trim().charAt(0).toUpperCase() || '?'}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-extrabold text-[var(--text-primary)]">{employee.name}</span>
            <span className="mt-0.5 block text-[10px] font-medium text-[var(--text-muted)]">{employee.id}</span>
          </span>
          <span className={`text-sm font-extrabold ${tone === 'top' ? 'text-emerald-600' : 'text-rose-600'}`}>{employee.score.toFixed(1)}%</span>
          <MoMIndicator delta={employee.scoreDelta} showStable />
        </Link>
      )) : (
        <div className="flex min-h-20 items-center justify-center rounded-xl border border-dashed border-[var(--border-medium)] px-4 text-center text-xs font-semibold text-[var(--text-muted)]">
          No additional employees are available for this group.
        </div>
      )}
    </div>
  </div>
);

const ANALYSIS_TONES: Record<KpiAnalysisTone, {
  shell: string;
  icon: string;
  badge: string;
}> = {
  positive: {
    shell: 'border-emerald-500/20 bg-emerald-500/[0.045]',
    icon: 'bg-emerald-500/12 text-emerald-600 dark:text-emerald-400',
    badge: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  },
  warning: {
    shell: 'border-amber-500/25 bg-amber-500/[0.045]',
    icon: 'bg-amber-500/12 text-amber-600 dark:text-amber-400',
    badge: 'bg-amber-500/10 text-amber-700 dark:text-amber-300',
  },
  critical: {
    shell: 'border-rose-500/25 bg-rose-500/[0.045]',
    icon: 'bg-rose-500/12 text-rose-600 dark:text-rose-400',
    badge: 'bg-rose-500/10 text-rose-700 dark:text-rose-300',
  },
  neutral: {
    shell: 'border-slate-400/20 bg-slate-500/[0.035]',
    icon: 'bg-slate-500/10 text-slate-600 dark:text-slate-300',
    badge: 'bg-slate-500/10 text-slate-600 dark:text-slate-300',
  },
};

const KpiAnalysisRow = ({
  kpi,
  isOpen,
  onToggle,
}: {
  kpi: MarketingKpiAggregate;
  isOpen: boolean;
  onToggle: () => void;
}) => {
  const analysis = buildKpiAnalysis(kpi);
  const tone = ANALYSIS_TONES[analysis.tone];
  const movementColor = analysis.movement.positive === true
    ? 'text-emerald-700 dark:text-emerald-300'
    : analysis.movement.positive === false
      ? 'text-rose-700 dark:text-rose-300'
      : 'text-[var(--text-secondary)]';
  const MovementIcon = analysis.movement.kind === 'increase'
    ? TrendingUp
    : analysis.movement.kind === 'decrease'
      ? TrendingDown
      : Gauge;
  const StatusIcon = analysis.tone === 'positive' ? CheckCircle2 : AlertTriangle;
  const baselineValue = formatMarketingValue(kpi.baselineActual, kpi.unit).display;
  const baselineGap = analysis.baseline.gap === null
    ? null
    : formatMarketingGap(analysis.baseline.gap, kpi.unit);

  return (
    <details open={isOpen} className={`group rounded-lg border ${tone.shell}`}>
      <summary
        onClick={(e) => {
          e.preventDefault();
          onToggle();
        }}
        className="flex cursor-pointer list-none items-center gap-2.5 px-3 py-2.5 [&::-webkit-details-marker]:hidden"
      >
        <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${tone.icon}`}>
          <StatusIcon size={13} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h4 className="text-[11px] font-extrabold text-[var(--text-primary)]">{kpi.label}</h4>
            <span className="text-[8px] font-bold text-[var(--text-muted)]">
              {kpi.direction === 'lower_better' ? 'Lower is better' : 'Higher is better'}
            </span>
          </div>
          <div className="mt-1 flex min-w-0 items-center gap-1.5 text-[10px]">
            <MovementIcon size={12} className={`shrink-0 ${movementColor}`} />
            <span className={`font-extrabold ${movementColor}`}>{analysis.movement.verb}</span>
            {kpi.previousPeriodLabel && (
              <span className="shrink-0 rounded bg-[var(--bg-sunken)] px-1.5 py-0.5 text-[8px] font-bold text-[var(--text-muted)]">
                vs {kpi.previousPeriodLabel}
              </span>
            )}
            {analysis.movement.fromValue && analysis.movement.toValue && (
              <span className="truncate font-semibold text-[var(--text-secondary)]">
                {analysis.movement.fromValue} → {analysis.movement.toValue}
              </span>
            )}
            {(analysis.impact.lostPoints ?? 0) > 0 && (
              <span className="shrink-0 font-extrabold text-rose-600 dark:text-rose-400">
                · -{analysis.impact.lostPoints?.toFixed(1)}%
              </span>
            )}
          </div>
          {analysis.baseline.available && (
            <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[9px] font-semibold text-[var(--text-muted)]">
              <span>Baseline <strong className="text-[var(--text-primary)]">{baselineValue}</strong></span>
              <span>· {kpi.baselinePeriodLabel}</span>
              {analysis.baseline.isNew ? (
                <span className="font-extrabold text-emerald-700 dark:text-emerald-300">
                  · New baseline{baselineGap ? ` +${baselineGap}` : ''}
                </span>
              ) : baselineGap && analysis.baseline.gap !== 0 ? (
                <span className="font-extrabold text-amber-700 dark:text-amber-300">
                  · {kpi.currentPeriodLabel} - {baselineGap} From Baseline
                </span>
              ) : (
                <span className="font-extrabold text-emerald-700 dark:text-emerald-300">· At baseline</span>
              )}
            </div>
          )}
        </div>
        <span className={`shrink-0 rounded-full px-2 py-1 text-[8px] font-extrabold uppercase tracking-wide ${tone.badge}`}>
          {analysis.statusLabel}
        </span>
        <ChevronDown size={13} className="shrink-0 text-[var(--text-muted)] transition-transform group-open:rotate-180" />
      </summary>

      <div className="grid gap-1.5 border-t border-current/10 px-3 pb-3 pt-2 text-[10px] leading-4">
        <div className="flex items-start gap-2">
          <MovementIcon size={12} className={`mt-0.5 shrink-0 ${movementColor}`} />
          <p className="font-medium text-[var(--text-secondary)]">{analysis.movement.detail}</p>
        </div>
        <div className="flex items-start gap-2">
          <Award size={12} className={`mt-0.5 shrink-0 ${analysis.baseline.isNew ? 'text-emerald-600 dark:text-emerald-400' : 'text-blue-600 dark:text-blue-400'}`} />
          <p className="font-medium text-[var(--text-secondary)]">{analysis.baseline.detail}</p>
        </div>
        <div className="flex items-start gap-2">
          <Target size={12} className={`mt-0.5 shrink-0 ${
            analysis.target.achieved === true
              ? 'text-emerald-600 dark:text-emerald-400'
              : analysis.target.achieved === false
                ? 'text-amber-600 dark:text-amber-400'
                : 'text-[var(--text-muted)]'
          }`} />
          <p className="font-medium text-[var(--text-secondary)]">{analysis.target.detail}</p>
        </div>
        <div className="flex items-start gap-2">
          <Gauge size={12} className={`mt-0.5 shrink-0 ${
            (analysis.impact.lostPoints ?? 0) > 0
              ? 'text-rose-600 dark:text-rose-400'
              : 'text-emerald-600 dark:text-emerald-400'
          }`} />
          <p className="font-medium text-[var(--text-secondary)]">{analysis.impact.detail}</p>
        </div>
      </div>
    </details>
  );
};

type SummaryTone = 'neutral' | 'positive' | 'warning' | 'critical';

const SummaryLine = ({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone: SummaryTone;
}) => {
  const toneClass = {
    neutral: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
    positive: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
    warning: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
    critical: 'bg-rose-500/10 text-rose-600 dark:text-rose-400',
  }[tone];
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-[var(--border-light)] bg-[var(--bg-sunken)]/25 p-2.5">
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${toneClass}`}>{icon}</span>
      <div className="min-w-0">
        <p className="text-[9px] font-bold uppercase tracking-wide text-[var(--text-muted)]">{label}</p>
        <p className="mt-0.5 text-[11px] font-extrabold leading-4 text-[var(--text-primary)]">{value}</p>
      </div>
    </div>
  );
};

export default MarketingPositionDetail;
