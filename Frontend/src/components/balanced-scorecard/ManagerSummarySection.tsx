import { useId, useState } from 'react';
import { AlertTriangle, ArrowUpRight } from 'lucide-react';
import type { BscHistoryPoint, BscKpiRow } from '../../hooks/api/useBalancedScorecard';
import type { ManagerSnapshot } from './managerSnapshots';
import { fmtVal as fmtValFromTypes } from './types';

interface ManagerSummarySectionProps {
  activeManager: ManagerSnapshot | null;
  rosterManagers: ManagerSnapshot[];
  kpiTable: BscKpiRow[];
  history: BscHistoryPoint[];
  onSelectKpi: (kpiKey: string) => void;
  selectedKpi: string | null;
  onKpiHover?: (kpi: BscKpiRow, e: React.MouseEvent) => void;
  onKpiLeave?: () => void;
}

// Sparkline using premium gradient fill
function Sparkline({ data, color = '#3b82f6', height = 30 }: { data: number[]; color?: string; height?: number }) {
  const gradId = `sparkline-grad-${useId().replace(/:/g, '')}`;
  
  if (data.length < 2) {
    return (
      <div className="flex items-center justify-center text-[10px] text-[var(--text-muted)] font-medium h-[30px]">
        No trend data
      </div>
    );
  }
  
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  
  const points = data.map((val, index) => {
    const x = (index / (data.length - 1)) * 100;
    const y = 2 + ((max - val) / range) * (height - 4);
    return { x, y };
  });

  const pathD = `M ${points[0].x} ${points[0].y} ` + points.slice(1).map(p => `L ${p.x} ${p.y}`).join(' ');
  const areaD = `${pathD} L 100 ${height} L 0 ${height} Z`;

  return (
    <svg className="w-full" style={{ height }} viewBox={`0 0 100 ${height}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color} stopOpacity="0.00" />
        </linearGradient>
      </defs>
      <path
        d={areaD}
        fill={`url(#${gradId})`}
      />
      <path
        d={pathD}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function ManagerSummarySection({
  activeManager,
  rosterManagers,
  kpiTable,
  history,
  onSelectKpi,
  selectedKpi,
  onKpiHover,
  onKpiLeave,
}: ManagerSummarySectionProps) {
  const [activeTab, setActiveTab] = useState<string>('all');

  if (!activeManager) return null;

  // 1. Calculate Ranking
  const sorted = [...rosterManagers].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const rankIdx = sorted.findIndex(m => m.employeeId === activeManager.employeeId);
  const rank = rankIdx !== -1 ? rankIdx + 1 : 1;
  const totalRank = rosterManagers.length || 1;

  // 2. Calculate vs Target (assuming target is 90% as in mock)
  const managerScore = activeManager.score ?? 0;
  const targetVal = 90;
  const targetGap = managerScore - targetVal;

  // 3. Calculate vs Team Average
  const scores = rosterManagers.map(m => m.score).filter((s): s is number => s !== null);
  const teamAvg = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : 90;
  const teamAvgGap = managerScore - teamAvg;

  // 4. Get active manager's history for overall trend sparkline
  const overallTrendData = history
    .map((point) => point.score)
    .filter((score): score is number => typeof score === 'number' && Number.isFinite(score));
  const trendDelta = overallTrendData.length >= 2
    ? overallTrendData[overallTrendData.length - 1] - overallTrendData[overallTrendData.length - 2]
    : null;
  const trendLabel = trendDelta == null
    ? 'Awaiting trend'
    : trendDelta > 0.05
      ? `Improving +${trendDelta.toFixed(1)}%`
      : trendDelta < -0.05
        ? `Needs recovery ${trendDelta.toFixed(1)}%`
        : 'Holding steady';
  const trendClass = trendDelta == null
    ? 'text-slate-500'
    : trendDelta < -0.05
      ? 'text-rose-600'
      : 'text-emerald-600';

  // 5. Get worst KPI (needs most attention)
  const configuredKpis = kpiTable.filter(k => k.score != null && k.state !== 'not_configured');
  const worstKpi = [...configuredKpis].sort((a, b) => (a.score ?? 100) - (b.score ?? 100))[0];

  // Helper for status pill styles
  const getStatusPill = (score: number | null | undefined) => {
    if (score == null) return { text: 'N/A', cls: 'bg-slate-500/10 text-slate-500 dark:bg-slate-500/20 dark:text-slate-400' };
    if (score >= 90) return { text: 'Excellent', cls: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20' };
    if (score >= 70) return { text: 'Good', cls: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20' };
    if (score >= 50) return { text: 'Needs Attention', cls: 'bg-amber-500/10 text-amber-600 dark:text-amber-450 border border-amber-500/20' };
    return { text: 'Poor', cls: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20' };
  };

  // Helper for perspective formatting
  const getPerspectiveMeta = (perspKey: string) => {
    const key = perspKey.toLowerCase();
    if (key.includes('financial')) return { label: 'FINANCIAL', color: '#3b82f6', cls: 'text-blue-500 dark:text-blue-400' };
    if (key.includes('customer')) return { label: 'CUSTOMER', color: '#8b5cf6', cls: 'text-indigo-500 dark:text-indigo-400' };
    if (key.includes('internal')) return { label: 'INTERNAL PROCESS', color: '#10b981', cls: 'text-emerald-500 dark:text-emerald-400' };
    return { label: 'LEARNING & GROWTH', color: '#f59e0b', cls: 'text-amber-500 dark:text-amber-400' };
  };

  // Helper for formatting KPI weight consistently
  const getWeightPct = (w?: number | null) => {
    if (w == null) return 0;
    return w <= 1 ? w * 100 : w;
  };

  // Helper for formatting actual/target values with correct units
  const fmtVal = (val?: number | null, unit?: string) => {
    return fmtValFromTypes(val, unit);
  };

  // Filtered KPIs by perspective tabs
  const filteredKpis = configuredKpis.filter(kpi => {
    if (activeTab === 'all') return true;
    if (activeTab === 'attention') return (kpi.score ?? 100) < 75;
    return kpi.perspective.toLowerCase().includes(activeTab);
  });

  const tabList = [
    { key: 'all', label: 'All KPIs', count: configuredKpis.length },
    { key: 'attention', label: 'Needs Attention', count: configuredKpis.filter(k => (k.score ?? 100) < 75).length, isAlert: true },
    { key: 'financial', label: 'Financial', count: configuredKpis.filter(k => k.perspective.toLowerCase().includes('financial')).length },
    { key: 'customer', label: 'Customer', count: configuredKpis.filter(k => k.perspective.toLowerCase().includes('customer')).length },
    { key: 'internal', label: 'Internal Process', count: configuredKpis.filter(k => k.perspective.toLowerCase().includes('internal')).length },
    { key: 'learning', label: 'Learning & Growth', count: configuredKpis.filter(k => k.perspective.toLowerCase().includes('learning')).length },
  ].filter(t => t.key === 'all' || t.count > 0);

  return (
    <div className="space-y-6 w-full">
      <div className={`grid grid-cols-1 gap-4 ${worstKpi ? 'xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.55fr)]' : ''}`}>
      {/* ── 1. Compact executive summary ── */}
      <section className="glass-card rounded-2xl p-5 border border-slate-200/50 dark:border-slate-800 shadow-sm space-y-4 h-full">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-extrabold text-[var(--text-primary)]">Executive summary</h2>
            <p className="text-[10px] text-[var(--text-secondary)] font-medium mt-0.5">
              Decision-ready performance signals for the selected manager
            </p>
          </div>
          <div className="hidden sm:flex items-center gap-3 min-w-[150px]">
            <span className={`text-[9px] font-extrabold uppercase tracking-wider whitespace-nowrap ${trendClass}`}>{trendLabel}</span>
            <div className="h-7 flex-1" aria-hidden="true">
              <Sparkline data={overallTrendData} color="#10b981" height={22} />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 w-full">
          {/* metric 1 */}
          <div className="bg-[var(--bg-sunken)]/60 dark:bg-slate-900/50 rounded-xl p-3.5 border border-slate-200/20 dark:border-slate-800/40 text-center flex-1 min-w-[125px] flex flex-col justify-between min-h-[98px]">
            <p className="text-[9px] font-bold uppercase tracking-wider text-[var(--text-muted)] mb-1">Overall Score</p>
            <div className="text-xl font-extrabold text-[var(--text-primary)] leading-none">{managerScore.toFixed(1)}%</div>
            <div>
              <span className={`inline-block text-[9px] font-extrabold px-1.5 py-0.5 rounded-md mt-1.5 ${getStatusPill(managerScore).cls}`}>
                {getStatusPill(managerScore).text}
              </span>
            </div>
          </div>

          {/* metric 2 */}
          <div className="bg-[var(--bg-sunken)]/60 dark:bg-slate-900/50 rounded-xl p-3.5 border border-slate-200/20 dark:border-slate-800/40 text-center flex-1 min-w-[125px] flex flex-col justify-between min-h-[98px]">
            <p className="text-[9px] font-bold uppercase tracking-wider text-[var(--text-muted)] mb-1">Team Ranking</p>
            <div className="text-xl font-extrabold text-[var(--text-primary)] leading-none">#{rank} / {totalRank}</div>
            <div>
              <span className="inline-block text-[9px] font-extrabold text-blue-600 dark:text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded-md mt-1.5 border border-blue-500/20">
                {rank === 1 ? 'Top Performer' : 'Active Contributor'}
              </span>
            </div>
          </div>

          {/* metric 3 */}
          <div className="bg-[var(--bg-sunken)]/60 dark:bg-slate-900/50 rounded-xl p-3.5 border border-slate-200/20 dark:border-slate-800/40 text-center flex-1 min-w-[125px] flex flex-col justify-between min-h-[98px]">
            <p className="text-[9px] font-bold uppercase tracking-wider text-[var(--text-muted)] mb-1">vs Target ({targetVal}%)</p>
            <div className="text-xl font-extrabold text-[var(--text-primary)] leading-none">
              {targetGap >= 0 ? '+' : ''}{targetGap.toFixed(1)}%
            </div>
            <div>
              <span className={`inline-block text-[9px] font-extrabold px-1.5 py-0.5 rounded-md mt-1.5 ${targetGap >= 0 ? 'bg-emerald-500/10 text-emerald-600 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-600 border border-rose-500/20'}`}>
                {targetGap >= 0 ? 'Above Target' : 'Below Target'}
              </span>
            </div>
          </div>

          {/* metric 4 */}
          <div className="bg-[var(--bg-sunken)]/60 dark:bg-slate-900/50 rounded-xl p-3.5 border border-slate-200/20 dark:border-slate-800/40 text-center flex-1 min-w-[125px] flex flex-col justify-between min-h-[98px]">
            <p className="text-[9px] font-bold uppercase tracking-wider text-[var(--text-muted)] mb-1">vs Team Avg ({teamAvg.toFixed(1)}%)</p>
            <div className="text-xl font-extrabold text-[var(--text-primary)] leading-none">
              {teamAvgGap >= 0 ? '+' : ''}{teamAvgGap.toFixed(1)}%
            </div>
            <div>
              <span className={`inline-block text-[9px] font-extrabold px-1.5 py-0.5 rounded-md mt-1.5 ${teamAvgGap >= 0 ? 'bg-emerald-500/10 text-emerald-600 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-600 border border-rose-500/20'}`}>
                {teamAvgGap >= 0 ? 'Above Avg' : 'Below Avg'}
              </span>
            </div>
          </div>

        </div>
      </section>

      {/* ── 2. Priority Attention Section ── */}
      {worstKpi && (
        <section className="glass-card rounded-2xl border border-amber-200 bg-amber-500/5 dark:border-amber-900/30 p-5 h-full flex flex-col">
          <div className="flex items-center justify-between mb-3.5">
            <div>
              <h3 className="text-sm font-extrabold text-[var(--text-primary)] flex items-center gap-1.5">
                <AlertTriangle size={15} className="text-amber-500" />
                Priority attention
              </h3>
              <p className="text-[10px] text-[var(--text-secondary)] font-medium">KPIs that need the most attention to hit target limits</p>
            </div>
            <button
              type="button"
              onClick={() => onSelectKpi(worstKpi.kpi_key)}
              className="min-h-11 text-[10px] font-extrabold text-blue-600 dark:text-blue-400 bg-blue-500/10 hover:bg-blue-500/20 px-3 py-2 rounded-lg border border-blue-500/20 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              Inspect KPI
            </button>
          </div>

          {/* Worst KPI Card Layout */}
          <div className="glass-card rounded-xl p-4 bg-[var(--bg-surface)] border border-slate-200/50 dark:border-slate-800/60 shadow-sm flex flex-1 flex-col justify-between gap-5">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-[9px] font-extrabold uppercase tracking-wider text-amber-500">
                  {getPerspectiveMeta(worstKpi.perspective).label}
                </span>
                <span className="text-[8px] font-extrabold uppercase tracking-wider bg-amber-500/10 text-amber-600 dark:text-amber-400 px-1.5 py-0.5 rounded border border-amber-500/20">
                  Monitor
                </span>
              </div>
              <h4 className="text-base font-extrabold text-[var(--text-primary)]">{worstKpi.kpi_label}</h4>
              <p className="text-xs text-[var(--text-secondary)] font-semibold mt-1">
                Score: <span className="text-[var(--text-primary)] font-bold">{worstKpi.score?.toFixed(1)}%</span>
                <span className="text-[var(--text-muted)] mx-2">·</span>
                Weight: <span className="text-[var(--text-primary)] font-bold">{getWeightPct(worstKpi.measured_weight ?? worstKpi.weight).toFixed(0)}%</span>
              </p>
            </div>

            <div className="flex items-end justify-between gap-4">
              <div className="text-right">
                <p className="text-[9px] font-bold uppercase tracking-wider text-[var(--text-muted)]">Actual vs Target</p>
                <div className="text-lg font-extrabold text-[var(--text-primary)] mt-0.5">
                  {fmtVal(worstKpi.actual_value, worstKpi.unit)}
                  <span className="text-[var(--text-muted)] text-sm font-semibold mx-1">/</span>
                  <span className="text-[var(--text-muted)] text-xs font-semibold">{fmtVal(worstKpi.target_value, worstKpi.unit)}</span>
                </div>
              </div>

              {/* Sparkline for worst KPI */}
              <div className="w-24 h-10">
                <Sparkline 
                  data={overallTrendData.map(val => Math.max(0, (worstKpi.score || 0) + (val - managerScore) * 0.4))} 
                  color="#f59e0b" 
                  height={32} 
                />
              </div>
            </div>
          </div>
        </section>
      )}
      </div>

      {/* ── 3. Tabbed KPI Performance Overview Grid ── */}
      <div className="space-y-4.5">
        <div className="flex flex-col gap-3 pb-2 border-b border-slate-200/50 dark:border-slate-800/60">
          <div>
            <h3 className="text-sm font-extrabold text-[var(--text-primary)]">KPI performance overview</h3>
            <p className="text-[10px] text-[var(--text-secondary)] font-medium">Filter indicators by perspective to focus on key areas</p>
          </div>
          
          {/* Tab Filter Pills */}
          <div className="-mx-1 overflow-x-auto px-1 pb-1 custom-scrollbar">
            <div className="flex min-w-max items-center gap-1.5" role="tablist" aria-label="Filter KPI cards by perspective">
              {tabList.map(tab => {
                const active = activeTab === tab.key;
                return (
                  <button
                    key={tab.key}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => setActiveTab(tab.key)}
                    className={`min-h-11 text-[11px] font-bold px-3 py-2 rounded-xl transition-colors duration-150 flex items-center gap-1.5 border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                      active
                        ? tab.isAlert
                          ? 'bg-amber-500 text-white border-amber-500 shadow-sm'
                          : 'bg-blue-600 text-white border-blue-600 shadow-sm'
                        : tab.isAlert
                          ? 'bg-amber-500/10 text-amber-600 border-amber-500/20 hover:bg-amber-500/20'
                          : 'bg-[var(--bg-sunken)] text-[var(--text-secondary)] border-slate-200/40 dark:border-slate-800 hover:text-[var(--text-primary)]'
                    }`}
                  >
                    {tab.isAlert && <AlertTriangle size={12} aria-hidden="true" />}
                    <span>{tab.label}</span>
                    <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-extrabold ${
                      active
                        ? 'bg-white/25 text-white'
                        : 'bg-slate-200 dark:bg-slate-800 text-[var(--text-muted)]'
                    }`}>
                      {tab.count}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {filteredKpis.length === 0 ? (
          <div className="text-center py-10 text-xs text-[var(--text-muted)] font-medium bg-[var(--bg-sunken)]/40 rounded-2xl border border-dashed border-slate-200/50 dark:border-slate-800">
            No KPIs match the selected filter.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4">
            {filteredKpis.map((kpi) => {
              const persp = getPerspectiveMeta(kpi.perspective);
              const active = kpi.kpi_key === selectedKpi;
              const status = getStatusPill(kpi.score);
              const weightPct = getWeightPct(kpi.measured_weight ?? kpi.weight);
              const contribPct = (Math.min(kpi.score ?? 0, 100) * (weightPct / 100));
              
              // Local sparkline generator based on history
              const kpiTrend = overallTrendData.map(val => 
                Math.max(0, Math.min(130, (kpi.score || 0) + (val - managerScore) * 0.4))
              );

              return (
                <button
                  key={kpi.kpi_key}
                  type="button"
                  aria-pressed={active}
                  onClick={() => onSelectKpi(kpi.kpi_key)}
                  onMouseEnter={(e) => onKpiHover?.(kpi, e)}
                  onMouseLeave={onKpiLeave}
                  className={`glass-card w-full text-left rounded-2xl p-4 border shadow-sm transition-colors duration-200 cursor-pointer flex flex-col justify-between min-h-[154px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                    active 
                      ? 'border-blue-500 shadow-[0_0_15px_rgba(59,130,246,0.15)] ring-1 ring-blue-500/30 bg-blue-500/[0.02]' 
                      : 'border-slate-200/50 dark:border-slate-800/80 hover:border-blue-400/50 dark:hover:border-blue-500/50 hover:shadow-md'
                  }`}
                >
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <span className={`text-[9px] font-extrabold uppercase tracking-wider ${persp.cls}`}>
                        {persp.label}
                      </span>
                      <span className="text-[9px] font-extrabold px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 whitespace-nowrap">
                        Weight: {weightPct <= 0.01 ? 'View' : `${weightPct.toFixed(0)}%`}
                      </span>
                    </div>
                    <div>
                      <h4 className="text-sm font-extrabold text-[var(--text-primary)] line-clamp-1" title={kpi.kpi_label}>
                        {kpi.kpi_label}
                      </h4>
                      <div className="flex items-baseline justify-between mt-1.5">
                        <div className="flex items-baseline gap-1.5">
                          <span className="text-2xl font-black text-[var(--text-primary)] leading-none">
                            {kpi.score?.toFixed(1)}%
                          </span>
                          {(() => {
                            const scoreGap = kpi.score != null ? kpi.score - 100 : 0;
                            const isPos = scoreGap >= 0;
                            return (
                              <span className={`text-[10px] font-bold flex items-center ${isPos ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}`}>
                                <ArrowUpRight size={10} className={`mr-0.5 ${isPos ? '' : 'rotate-90'}`} />
                                {isPos ? '+' : ''}{scoreGap.toFixed(1)}%
                              </span>
                            );
                          })()}
                        </div>
                        <div className="text-right">
                          <span className="text-xs font-bold text-blue-600 dark:text-blue-400">
                            {weightPct <= 0.01 ? '0.0%' : `${contribPct.toFixed(1)}%`}
                          </span>
                          <span className="text-[9px] text-[var(--text-muted)] block font-semibold">
                            {weightPct <= 0.01 ? 'View Only Metric' : `Contrib of ${weightPct.toFixed(0)}%`}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 space-y-2">
                    <div className="flex items-center justify-between text-[10px] font-semibold">
                      <span className="text-[var(--text-secondary)]">
                        Actual: <strong className="text-[var(--text-primary)]">{fmtVal(kpi.actual_value, kpi.unit)}</strong>
                        <span className="text-[var(--text-muted)] mx-1.5">·</span>
                        Target: <strong className="text-[var(--text-primary)]">{fmtVal(kpi.target_value, kpi.unit)}</strong>
                      </span>
                      <span className={`text-[8px] font-extrabold px-1.5 py-0.5 rounded-sm ${status.cls}`}>
                        {status.text}
                      </span>
                    </div>

                    {/* Sparkline */}
                    <div className="h-7 w-full pt-1">
                      <Sparkline data={kpiTrend} color={persp.color} height={20} />
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export default ManagerSummarySection;
