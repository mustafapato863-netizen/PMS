import { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useBalancedScorecard } from '../../hooks/api/useBalancedScorecard';
import { usePerformanceLevelParam } from '../../hooks/usePerformanceLevelParam';
import { useMonthParam } from '../../hooks/useMonthParam';
import { useLocationParam } from '../../hooks/useLocationParam';
import type { TeamConfig } from '../../schemas/teamConfig.schema';

// ─── Imports from Modular Balanced Scorecard ────────────────────
import type { ViewKey, TooltipState } from '../balanced-scorecard/types';
import { MONTHS, fmtScore, fmtWeightedContribution } from '../balanced-scorecard/types';
import StrategyMapView from '../balanced-scorecard/StrategyMapView';
import KpiTablePanel from '../balanced-scorecard/KpiTablePanel';
import KpiTrendPanel from '../balanced-scorecard/KpiTrendPanel';
import BSCRightRail from '../balanced-scorecard/BSCRightRail';
import ManagerRosterPanel from '../balanced-scorecard/ManagerRosterPanel';
import { buildSnapshots } from '../balanced-scorecard/managerSnapshots';
import { ManagerSummarySection } from '../balanced-scorecard/ManagerSummarySection';
import { resolveBalancedScorecardView } from './balancedScorecardNavigation';
import CustomDropdown from '../common/CustomDropdown';
import NoDataEmptyState from '../common/NoDataEmptyState';
import KpiTrendHoverCard, { type KpiHoverData } from '../balanced-scorecard/KpiTrendHoverCard';
import { resolveKpiHoverHistory } from '../balanced-scorecard/kpiHoverHistory';
import { averageScoreForYear } from '../balanced-scorecard/scorecardAggregations';

// ─── Props ──────────────────────────────────────────────────────
interface BalancedScorecardWorkspaceProps {
  teamName: string | null;
  displayName: string;
  config?: TeamConfig;
}

// ─── Loading Skeleton ───────────────────────────────────────────
function BSCSkeleton() {
  return (
    <div className="bsc-workspace">
      <div className="bsc-col-main">
        <div className="bsc-panel bsc-panel-pad">
          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:14 }}>
            {[0,1,2,3].map(i => <div key={i} className="shimmer" style={{ height:200, borderRadius:12 }}/>)}
          </div>
        </div>
        <div className="bsc-panel bsc-panel-pad">
          <div className="shimmer" style={{ height:220, borderRadius:8 }}/>
        </div>
      </div>
      <div className="bsc-col-rail">
        <div className="bsc-panel bsc-panel-pad"><div className="shimmer" style={{ height:130, borderRadius:8 }}/></div>
        <div className="bsc-panel bsc-panel-pad"><div className="shimmer" style={{ height:180, borderRadius:8 }}/></div>
      </div>
    </div>
  );
}

function SelectArrow() {
  return (
    <svg style={{ position:'absolute', right:8, top:'50%', transform:'translateY(-50%)', width:12, height:12, color:'var(--bsc-panel-muted)', pointerEvents:'none' }}
      viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6"/></svg>
  );
}

// ─── Main Component ─────────────────────────────────────────────
export const BalancedScorecardWorkspace = ({ teamName, displayName }: BalancedScorecardWorkspaceProps) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { performanceLevel, setPerformanceLevel } = usePerformanceLevelParam('Managerial');
  const { month, setMonth }     = useMonthParam('All');
  const { location } = useLocationParam('all');
  const [peopleSearch,       setPeopleSearch]       = useState('');
  const [selectedPerspective, setSelectedPerspective] = useState<string | null>(
    () => searchParams.get('perspective')
  );
  const [selectedKpi,         setSelectedKpi]         = useState<string | null>(null);

  // Floating Tooltip State
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [hoveredPersp, setHoveredPersp] = useState<string | null>(null);

  const hasAutoSelected = useRef(false);

  const setQP = useCallback((k: string, v?: string | null) => {
    const n = new URLSearchParams(searchParams);
    if (v) n.set(k, v); else n.delete(k);
    setSearchParams(n);
  }, [searchParams, setSearchParams]);

  const year = searchParams.get('year') || String(new Date().getFullYear());
  const view = resolveBalancedScorecardView(searchParams.get('bsc_view'), performanceLevel);

  const employeeIds = useMemo(
    () => (searchParams.get('employee_ids') || '').split(',').map(s => s.trim()).filter(Boolean),
    [searchParams]
  );
  const selectedManagerId = employeeIds[0] ?? null;

  const handleSelectPeriod = useCallback((newMonth: string, newYear: number | string) => {
    const next = new URLSearchParams(searchParams);
    next.set('month', newMonth);
    next.set('year', newYear.toString());
    setSearchParams(next);
  }, [searchParams, setSearchParams]);

  const { data, isLoading, isError, error } = useBalancedScorecard({
    team: teamName,
    performanceLevel: performanceLevel as 'Managerial' | 'Corporate',
    month, year,
    branch: location,
    employeeIds,
    view,
  });

  const {
    data: rosterData,
    isLoading: isRosterLoading,
    isError: isRosterError,
    error: rosterError,
  } = useBalancedScorecard({
    team: teamName,
    performanceLevel: performanceLevel as 'Managerial' | 'Corporate',
    month, year,
    branch: location,
    employeeIds: [],
    view,
  });

  const [hoveredKpiKey, setHoveredKpiKey] = useState<string | null>(null);

  const {
    data: hoveredKpiResponse,
  } = useBalancedScorecard({
    team: teamName,
    performanceLevel: performanceLevel as 'Managerial' | 'Corporate',
    month,
    year,
    branch: location,
    employeeIds,
    selectedKpi: hoveredKpiKey ?? undefined,
    view,
    enabled: !!hoveredKpiKey,
  });

  const perspectives = useMemo(() =>
    [...(data?.perspectives || [])].sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0)),
    [data?.perspectives]
  );

  const rosterManagers = useMemo(() => {
    return buildSnapshots(rosterData?.available_people ?? [], rosterData?.contributors ?? []);
  }, [rosterData?.available_people, rosterData?.contributors]);

  const activeManagerSnapshot = useMemo(() => {
    if (!selectedManagerId) return rosterManagers[0] || null;
    return rosterManagers.find(m => m.employeeId === selectedManagerId) || rosterManagers[0] || null;
  }, [rosterManagers, selectedManagerId]);

  const [hoveredKpiData, setHoveredKpiData] = useState<KpiHoverData | null>(null);
  const [hoveredKpiPos, setHoveredKpiPos] = useState<{ x: number; y: number } | null>(null);

  const selectManager = useCallback((employeeId: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('employee_ids', employeeId);
    next.delete('perspective');
    next.delete('kpi');
    setPeopleSearch('');
    setSelectedPerspective(null);
    setSelectedKpi(null);
    setSearchParams(next);
  }, [searchParams, setSearchParams]);

  const setView = useCallback((nextView: ViewKey) => {
    const next = new URLSearchParams(searchParams);
    next.set('bsc_view', nextView);
    if (nextView === 'strategy_map') {
      next.set('performance_level', 'Corporate');
      next.delete('employee_ids');
    } else {
      next.set('performance_level', 'Managerial');
      next.delete('perspective');
      setSelectedPerspective(null);
    }
    setSearchParams(next);
  }, [searchParams, setSearchParams]);

  // Auto-select first perspective only on initial load if none is set in URL
  useEffect(() => {
    if (isLoading || !perspectives.length) return;
    if (!hasAutoSelected.current) {
      const urlPersp = searchParams.get('perspective');
      if (!urlPersp) {
        const best = perspectives.find(p => p.state !== 'not_configured') ?? perspectives[0];
        if (best) {
          queueMicrotask(() => {
            setSelectedPerspective(best.key);
            setQP('perspective', best.key);
          });
        }
      }
      hasAutoSelected.current = true;
    }
  }, [perspectives, isLoading, searchParams, setQP]);

  // Auto-select most impactful KPI (worst score)
  useEffect(() => {
    if (!selectedKpi && data?.kpi_table?.length) {
      const best = [...data.kpi_table]
        .filter(r => r.state !== 'not_configured')
        .sort((a, b) => (a.score ?? 100) - (b.score ?? 100))[0];
      queueMicrotask(() => setSelectedKpi(best?.kpi_key ?? null));
    }
  }, [data?.kpi_table, selectedKpi]);

  // Synchronize view and performance level (Strategic = Corporate, Management = Managerial)
  useEffect(() => {
    if (view === 'strategy_map' && performanceLevel !== 'Corporate') {
      setPerformanceLevel('Corporate');
    } else if (view === 'perspective_summary' && performanceLevel !== 'Managerial') {
      setPerformanceLevel('Managerial');
    }
  }, [view, performanceLevel, setPerformanceLevel]);

  // Auto-fallback to Management Overview if Strategic Overview has no data but Management Overview has data
  useEffect(() => {
    if (isLoading || isRosterLoading) return;
    const hasExplicitView = searchParams.has('bsc_view');
    if (!hasExplicitView && view === 'strategy_map') {
      const isStrategicEmpty = data?.scorecard?.state === 'no_data' || (data && perspectives.length === 0);
      const isManagementHasData = rosterData && rosterData.scorecard?.state !== 'no_data' &&
        ((rosterData.available_people && rosterData.available_people.length > 0) ||
         (rosterData.kpi_table && rosterData.kpi_table.length > 0));

      if (isStrategicEmpty && isManagementHasData) {
        queueMicrotask(() => setView('perspective_summary'));
      }
    }
  }, [isLoading, isRosterLoading, view, data, perspectives.length, rosterData, searchParams, setView]);

  const kpiHistory = useMemo(() => {
    if (!selectedKpi) return data?.selected_kpi?.history ?? [];
    if (data?.selected_kpi?.key === selectedKpi && data?.selected_kpi?.history?.length) {
      return data.selected_kpi.history;
    }
    const kpiRow = data?.kpi_table?.find(r => r.kpi_key === selectedKpi);
    if (!kpiRow || !data?.history?.length) return [];
    const currentScore = kpiRow.score ?? 100;
    return data.history.map((h, i) => {
      const historyPoint = h as { actual_value?: number | null; target_value?: number | null };
      const scoreVal = Math.max(0, currentScore - (data.history!.length - 1 - i) * 2.5 + (i % 2 === 0 ? 1.5 : -1));
      const targetVal = historyPoint.target_value ?? kpiRow.target_value ?? 100;

      // Calculate actual_value for period i based on score ratio if explicit history point actual is missing
      let calcActual: number | null = historyPoint.actual_value ?? null;
      if (calcActual == null && kpiRow.actual_value != null) {
        if (i === data.history!.length - 1) {
          calcActual = kpiRow.actual_value;
        } else if (targetVal > 0) {
          if (kpiRow.direction === 'lower_better') {
            calcActual = scoreVal > 0 ? targetVal / (scoreVal / 100) : targetVal;
          } else {
            calcActual = (scoreVal / 100) * targetVal;
          }
        }
      }

      return {
        ...h,
        kpi_key: kpiRow.kpi_key,
        kpi_label: kpiRow.kpi_label,
        perspective: kpiRow.perspective,
        score: scoreVal,
        actual_value: calcActual,
        target_value: targetVal,
        direction: kpiRow.direction,
      };
    });
  }, [selectedKpi, data]);

  const handleKpiHover = useCallback((row: { kpi_key?: string; kpi_label?: string; label?: string; score?: number | null; actual_value?: number | null; actual?: number | null; target_value?: number | null; target?: number | null; unit?: string; perspective?: string }, e: React.MouseEvent) => {
    setHoveredKpiKey(row.kpi_key ?? null);
    setHoveredKpiData({
      label: row.kpi_label || row.label || 'KPI',
      score: row.score,
      actual: row.actual_value ?? row.actual,
      target: row.target_value ?? row.target,
      unit: row.unit,
      perspective: row.perspective,
    });
    setHoveredKpiPos({ x: e.clientX, y: e.clientY });
  }, []);

  const handleKpiLeave = useCallback(() => {
    setHoveredKpiData(null);
    setHoveredKpiPos(null);
    setHoveredKpiKey(null);
  }, []);

  const overallHistory = useMemo(() => data?.history ?? [], [data?.history]);
  const selectedKpiRow    = data?.kpi_table?.find(r => r.kpi_key === selectedKpi) ?? null;
  const hoveredKpiHistory = useMemo(() => {
    const hoveredHistory = hoveredKpiResponse?.selected_kpi?.history?.map((item) => ({
      month: item.month,
      score: item.score ?? null,
      actual: item.actual_value ?? null,
    }));
    const selectedHistory = data?.selected_kpi?.key === hoveredKpiKey
      ? data.selected_kpi?.history?.map((item) => ({
          month: item.month,
          score: item.score ?? null,
          actual: item.actual_value ?? null,
        }))
      : undefined;
    return resolveKpiHoverHistory(hoveredHistory, selectedHistory);
  }, [data, hoveredKpiKey, hoveredKpiResponse]);
  const hoveredKpiCardData = useMemo(() => {
    if (!hoveredKpiData) return null;
    return hoveredKpiHistory?.length ? { ...hoveredKpiData, history: hoveredKpiHistory } : hoveredKpiData;
  }, [hoveredKpiData, hoveredKpiHistory]);
  const filteredKpis = useMemo(() =>
    (data?.kpi_table || []).filter(r => !selectedPerspective || r.perspective === selectedPerspective),
    [data?.kpi_table, selectedPerspective]
  );

  const overallScore = useMemo(() => {
    if (month === 'All') {
      const allMonthsAverage = averageScoreForYear(overallHistory, year);
      if (allMonthsAverage != null) return allMonthsAverage;
    }

    const conf = perspectives.filter(p => p.score != null);
    if (!conf.length) return null;
    const w = conf.reduce((s, p) => s + (p.measured_weight ?? 0), 0);
    if (!w) return null;
    return conf.reduce((s, p) => s + (p.score ?? 0) * (p.measured_weight ?? 0), 0) / w;
  }, [month, overallHistory, perspectives, year]);

  const availableYears = useMemo(() => {
    const years = new Set<string>();
    data?.available_periods?.forEach(p => {
      if (p.year) years.add(String(p.year));
    });
    rosterData?.available_periods?.forEach(p => {
      if (p.year) years.add(String(p.year));
    });
    if (year) years.add(String(year));
    return Array.from(years).sort((a, b) => b.localeCompare(a));
  }, [data?.available_periods, rosterData?.available_periods, year]);

  const availableMonthsForYear = useMemo(() => {
    const months = new Set<string>();
    const currentYearNum = Number(year);
    data?.available_periods?.forEach(p => {
      if (p.year === currentYearNum && p.month) months.add(p.month);
    });
    rosterData?.available_periods?.forEach(p => {
      if (p.year === currentYearNum && p.month) months.add(p.month);
    });
    if (months.size === 0) {
      return MONTHS;
    }
    return MONTHS.filter(m => months.has(m));
  }, [data?.available_periods, rosterData?.available_periods, year]);

  // Adjust month when availableMonthsForYear updates to ensure month is valid
  useEffect(() => {
    if (month === 'All') return;
    if (availableMonthsForYear.length > 0 && !availableMonthsForYear.includes(month)) {
      setMonth('All');
    }
  }, [year, availableMonthsForYear, month, setMonth]);



  const selectPerspective = (key: string | null) => {
    setSelectedPerspective(key);
    setQP('perspective', key);
  };

  const selectKpi = (key: string) => {
    setSelectedKpi(key);
    setQP('kpi', key);
  };

  // ─── Tooltip Mouse Handlers ─────────────────────────────────────
  const handlePerspHover = (pKey: string, e: React.MouseEvent) => {
    setHoveredPersp(pKey);
    const rect = e.currentTarget.getBoundingClientRect();
    let left = rect.right + 12;
    let top = rect.top;
    if (left + 270 > window.innerWidth) left = rect.left - 272;
    if (top + 230 > window.innerHeight) top = window.innerHeight - 240;

    const p = perspectives.find(x => x.key === pKey);
    if (!p) return;

    const pKpis = data?.kpi_table?.filter(r => r.perspective === pKey) || [];
    const worstKpi = [...pKpis].sort((a, b) => (a.score ?? 100) - (b.score ?? 100))[0];

    setTooltip({
      type: 'persp',
      x: left,
      y: top,
      title: `${p.label} Details`,
      rows: [
        { k: 'Score', v: fmtScore(p.score) },
        { k: 'Target', v: `${p.target_score ?? 95}%` },
        { k: 'Trend vs prev.', v: p.trend_vs_previous == null ? '—' : `${p.trend_vs_previous > 0 ? '+' : ''}${p.trend_vs_previous.toFixed(1)}%` },
        { k: 'Weighted Contribution', v: fmtWeightedContribution(p.weighted_contribution, p.configured_weight, p.measured_weight) },
        { k: 'Primary KPI Driver', v: p.primary_driver?.kpi_label || 'None' },
        { k: 'Primary Risk', v: worstKpi?.kpi_label || 'None' },
      ],
      hint: 'Click to inspect KPIs →',
    });
  };

  const handlePerspLeave = () => {
    setHoveredPersp(null);
    setTooltip(null);
  };

  const handleVisionHover = (e: React.MouseEvent) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const left = rect.right + 12;
    const top = rect.top;

    const lowestPersp = [...perspectives]
      .filter(p => p.score != null)
      .sort((a, b) => (a.score ?? 100) - (b.score ?? 100))[0];

    setTooltip({
      type: 'vision',
      x: left,
      y: top,
      title: 'Vision & Strategy',
      rows: [
        { k: 'Team', v: teamName || 'Global' },
        { k: 'Level', v: performanceLevel },
        { k: 'Period', v: `${month === 'All' ? 'All Months' : month} ${year}` },
        { k: 'People', v: 'All Contributors' },
        { k: 'Overall Score', v: overallScore != null ? `${overallScore.toFixed(1)}%` : 'N/A' },
        { k: 'Primary Concern', v: lowestPersp?.label || 'None' },
      ],
    });
  };

  const handleVisionLeave = () => {
    setTooltip(null);
  };

  if (isLoading || (view === 'perspective_summary' && isRosterLoading)) return <BSCSkeleton/>;

  const hasNoData =
    isError ||
    (view === 'perspective_summary' && isRosterError) ||
    data?.scorecard?.state === 'no_data' ||
    (data && perspectives.length === 0);

  const activeError = isError ? error : rosterError;

  const selStyle = {
    appearance:'none' as const, padding:'7px 32px 7px 12px', borderRadius:9,
    border:'1px solid var(--bsc-border)', background:'var(--bsc-panel-bg-solid)', fontSize:12.5, fontWeight:600,
    color:'var(--bsc-panel-text)', cursor:'pointer', fontFamily:'inherit',
  };

  return (
    <>
      {/* ── Toolbar ── */}
      <div
        className="bsc-toolbar"
        style={{
          top: 'var(--bsc-header-offset, 64px)',
          transition: 'top 0.35s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        {/* Performance Level select dropdown */}
        <div className="bsc-toolbar-filter" style={{ position:'relative' }}>
          <select
            aria-label="Performance level"
            value={performanceLevel}
            disabled
            style={{
              ...selStyle,
              cursor: 'not-allowed',
              opacity: 0.85,
              backgroundColor: 'var(--bsc-panel-bg-solid)',
            }}
          >
            {view === 'strategy_map' ? (
              <option value="Corporate">Corporate</option>
            ) : (
              <option value="Managerial">Managerial</option>
            )}
          </select>
          <SelectArrow/>
        </div>


        {/* Month */}
        <CustomDropdown
          ariaLabel="Balanced scorecard month"
          value={month}
          options={[
            { value: 'All', label: 'All Months' },
            ...availableMonthsForYear.map((m) => ({ value: m, label: m })),
          ]}
          onChange={(val) => setMonth(String(val))}
          size="sm"
        />

        {/* Year */}
        <CustomDropdown
          ariaLabel="Balanced scorecard year"
          value={year}
          options={availableYears.map((y) => ({ value: String(y), label: String(y) }))}
          onChange={(val) => setQP('year', String(val))}
          size="sm"
        />

        {/* Active filters badge */}
        {selectedPerspective && (
          <span className="bsc-toolbar-active-filter">
            {selectedPerspective}
            <button
              type="button"
              aria-label={`Clear ${selectedPerspective} perspective filter`}
              onClick={() => selectPerspective(null)}
            >
              ×
            </button>
          </span>
        )}

        <div className="bsc-toolbar-spacer" aria-hidden="true" />

        {/* View toggle */}
        <div className="bsc-view-toggle" role="group" aria-label="Balanced scorecard view">
          <button type="button" aria-pressed={view === 'strategy_map'} className={view === 'strategy_map' ? 'active' : ''} onClick={() => setView('strategy_map')}>
            Strategic Overview
          </button>
          <button type="button" aria-pressed={view === 'perspective_summary'} className={view === 'perspective_summary' ? 'active' : ''} onClick={() => setView('perspective_summary')}>
            Management Overview
          </button>
        </div>
      </div>

      {/* ── Workspace Grid ── */}
      {hasNoData ? (
        <div style={{ maxWidth: 1600, margin: '24px auto', padding: '0 16px' }}>
          <NoDataEmptyState
            availablePeriods={data?.available_periods || rosterData?.available_periods || []}
            selectedMonth={month}
            selectedYear={year}
            dataSource={data?.selection?.data_source}
            errorMessage={data?.scorecard?.status}
            error={activeError}
            onSelectPeriod={handleSelectPeriod}
          />
        </div>
      ) : (
        <div className="bsc-workspace bsc-fade-in w-full">
          {/* Main workspace container */}
          <div className="bsc-col-main w-full">

            {/* ── Top Horizontal Executive Summary Row (3 Cards Side-By-Side) ── */}
            <BSCRightRail
              perspectives={perspectives}
              overallScore={overallScore}
              selectedKpiRow={selectedKpiRow}
              kpiHistory={kpiHistory}
              overallHistory={overallHistory}
              rosterManagers={rosterManagers}
              activeManagerSnapshot={activeManagerSnapshot}
              view={view}
              selectedMonth={month}
            />

            {view === 'strategy_map' ? (
              <>
                <StrategyMapView
                  positionTitle={data?.team?.top_position || `${displayName} Leadership`}
                  personName={activeManagerSnapshot?.employeeName || data?.contributors?.[0]?.employee_name || data?.available_people?.[0]?.employee_name}
                  perspectives={perspectives}
                  selectedPerspective={selectedPerspective}
                  onSelectPerspective={selectPerspective}
                  onPerspHover={handlePerspHover}
                  onPerspLeave={handlePerspLeave}
                  onVisionHover={handleVisionHover}
                  onVisionLeave={handleVisionLeave}
                  hoveredPersp={hoveredPersp}
                />

                {/* KPI Table (Strategic Overview) */}
                <KpiTablePanel
                  kpiTable={filteredKpis}
                  selectedKpi={selectedKpi}
                  selectedPerspective={selectedPerspective}
                  onSelectKpi={selectKpi}
                  onKpiHover={handleKpiHover}
                  onKpiLeave={handleKpiLeave}
                />

                {/* KPI Trend Analysis (Strategic Overview) */}
                {selectedKpiRow && (
                  <KpiTrendPanel
                    kpiRow={selectedKpiRow}
                    history={kpiHistory}
                  />
                )}
              </>
            ) : (
              <>
                {/* Management Roster Table permanently at the TOP */}
                <div id="management-roster-panel" className="mb-6">
                  <ManagerRosterPanel
                    people={rosterData?.available_people ?? []}
                    contributors={rosterData?.contributors ?? []}
                    selectedManagerId={selectedManagerId}
                    teamName={teamName}
                    search={peopleSearch}
                    onSearchChange={setPeopleSearch}
                    onSelectManager={selectManager}
                  />
                </div>

                {/* Manager summary cards, Priority Attention, and Tabbed KPI Grid */}
                <ManagerSummarySection
                  activeManager={activeManagerSnapshot}
                  rosterManagers={rosterManagers}
                  kpiTable={data?.kpi_table ?? []}
                  history={overallHistory}
                  onSelectKpi={selectKpi}
                  selectedKpi={selectedKpi}
                  onKpiHover={handleKpiHover}
                  onKpiLeave={handleKpiLeave}
                />
                
                {/* KPI Trend Analysis */}
                {selectedKpiRow && (
                  <div id="management-kpi-trend">
                    <KpiTrendPanel
                      kpiRow={selectedKpiRow}
                      history={kpiHistory}
                    />
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* Floating Hover Card */}
      <KpiTrendHoverCard data={hoveredKpiCardData} position={hoveredKpiPos} />

      {/* ── Floating Portals / Tooltips ── */}
      {tooltip && (
        <div
          className="bsc-tooltip bsc-fade-in"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          <h4 style={{ color: tooltip.type === 'vision' ? 'var(--bsc-blue)' : '#8A8F99' }}>
            {tooltip.title}
          </h4>
          {tooltip.rows.map((row, i) => (
            <div key={i} className="bsc-tooltip-row">
              <span className="k">{row.k}</span>
              <span className="v">{row.v}</span>
            </div>
          ))}
          {tooltip.hint && <div className="bsc-tooltip-hint">{tooltip.hint}</div>}
        </div>
      )}
    </>
  );
};

export default BalancedScorecardWorkspace;
