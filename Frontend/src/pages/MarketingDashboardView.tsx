import './PageEnhancements.css';
import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import MarketingFiltersHeader from '../components/marketing/MarketingFiltersHeader';
import MarketingOverview from '../components/marketing/MarketingOverview';
import MarketingPositionDetail from '../components/marketing/MarketingPositionDetail';
import EmployeeActionModal from '../components/team/EmployeeActionModal';
import { API_BASE } from '../config';
import { useUserRole } from '../context/RoleContext';
import { buildMarketingAnalytics, getMarketingPeriods } from '../features/marketing/marketingAnalytics';
import type {
  MarketingFilters,
  MarketingRegion,
  MarketingTeamConfig,
} from '../features/marketing/types';
import { useMarketingData } from '../features/marketing/useMarketingData';
import { useActionStore } from '../hooks/useActionStore';
import type { TeamAgentRow } from '../hooks/usePerformanceData';
import type { AgentRecord, PMSAction } from '../types';

const REGIONS = new Set<MarketingRegion>(['All', 'EGY', 'UAE']);
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

interface MarketingDashboardContentProps {
  config: MarketingTeamConfig;
  records: AgentRecord[];
  canExport: boolean;
  onExport: (filters: MarketingFilters) => Promise<void>;
  role?: string;
  getActionsForEmployee?: (employeeId: string) => PMSAction[];
  onAddAction?: (row: TeamAgentRow) => void;
  onEmployeeChanged?: () => void;
}

export const MarketingDashboardContent = ({
  config,
  records,
  canExport,
  onExport,
  role = 'Viewer',
  getActionsForEmployee = () => [],
  onAddAction = () => undefined,
  onEmployeeChanged,
}: MarketingDashboardContentProps) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const periods = useMemo(() => getMarketingPeriods(records), [records]);
  const positions = config.available_positions?.length ? config.available_positions : Object.keys(config.positions);
  const latestPeriod = periods[periods.length - 1];
  const requestedYear = Number(searchParams.get('year'));
  const validYears = new Set(periods.map((period) => period.year));
  const fallbackYear = latestPeriod?.year || new Date().getFullYear();
  const year = validYears.has(requestedYear) ? requestedYear : fallbackYear;
  const periodsForYear = periods.filter((period) => period.year === year);
  const requestedMonth = searchParams.get('month') || '';
  const fallbackMonth = periodsForYear[periodsForYear.length - 1]?.month || MONTHS[new Date().getMonth()];
  const month = requestedMonth === 'All' || periodsForYear.some((period) => period.month === requestedMonth)
    ? requestedMonth
    : fallbackMonth;
  const requestedRegion = searchParams.get('region') as MarketingRegion | null;
  const region = requestedRegion && REGIONS.has(requestedRegion) ? requestedRegion : 'All';
  const requestedPosition = searchParams.get('position') || '';
  const position = positions.includes(requestedPosition) ? requestedPosition : undefined;
  const requestedPositionView = searchParams.get('position_view') || '';
  const positionView = positions.includes(requestedPositionView) ? requestedPositionView : undefined;
  const filters = useMemo<MarketingFilters>(
    () => ({ year, month, region, position }),
    [month, position, region, year],
  );

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    next.set('year', String(filters.year));
    next.set('month', filters.month);
    next.set('region', filters.region);
    next.delete('status');
    if (filters.position) next.set('position', filters.position);
    else next.delete('position');
    if (positionView) next.set('position_view', positionView);
    else next.delete('position_view');
    if (next.toString() !== searchParams.toString()) setSearchParams(next, { replace: true });
  }, [filters.month, filters.position, filters.region, filters.year, positionView, searchParams, setSearchParams]);

  const effectiveFilters = useMemo<MarketingFilters>(
    () => ({ ...filters, position: positionView || filters.position }),
    [filters, positionView],
  );
  const analytics = useMemo(
    () => buildMarketingAnalytics(records, config, effectiveFilters),
    [config, effectiveFilters, records],
  );

  const updateFilter = (key: keyof MarketingFilters, value: string | number | undefined) => {
    const next = new URLSearchParams(searchParams);
    if (key === 'year') {
      const nextYear = Number(value);
      next.set('year', String(nextYear));
      const nextYearPeriods = periods.filter((period) => period.year === nextYear);
      const nextMonth = month === 'All'
        ? 'All'
        : nextYearPeriods[nextYearPeriods.length - 1]?.month || month;
      next.set('month', nextMonth);
    } else if (key === 'position') {
      if (value) next.set('position', String(value));
      else next.delete('position');
    } else if (value !== undefined) {
      next.set(key, String(value));
    }
    setSearchParams(next);
  };

  const updatePeriod = (periodKey: string) => {
    if (periodKey === 'All') {
      const next = new URLSearchParams(searchParams);
      next.set('month', 'All');
      next.delete('status');
      setSearchParams(next);
      return;
    }
    const period = periods.find((item) => item.key === periodKey);
    if (!period) return;
    const next = new URLSearchParams(searchParams);
    next.set('year', String(period.year));
    next.set('month', period.month);
    next.delete('status');
    setSearchParams(next);
  };

  const openPosition = (selectedPosition: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('position_view', selectedPosition);
    setSearchParams(next);
  };

  const closePosition = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('position_view');
    setSearchParams(next);
  };

  const handleExport = async () => {
    setExporting(true);
    setExportError(null);
    try {
      await onExport(effectiveFilters);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : 'Marketing export failed.');
    } finally {
      setExporting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="app-page-shell rf-page rf-page--marketing"
    >
      <MarketingFiltersHeader
        filters={filters}
        isPositionView={!!positionView}
        positionName={positionView}
        periods={periods}
        positions={positions}
        canExport={canExport}
        exporting={exporting}
        onChange={updateFilter}
        onPeriodChange={updatePeriod}
        onBack={closePosition}
        onExport={handleExport}
      />
      {exportError && (
        <div role="alert" className="rounded-xl border border-rose-500/20 bg-rose-500/8 px-4 py-3 text-sm font-semibold text-rose-700 dark:text-rose-300">
          {exportError}
        </div>
      )}

      {!records.length && (
        <div className="rounded-2xl border border-blue-500/20 bg-blue-500/8 px-5 py-4 text-sm font-semibold text-blue-800 dark:text-blue-200">
          Marketing is configured and ready. Position dashboards will populate after the first Employee performance upload.
        </div>
      )}

      {positionView ? (
        <MarketingPositionDetail
          analytics={analytics}
          position={positionView}
          thresholds={config.grade_thresholds}
          role={role}
          getActionsForEmployee={getActionsForEmployee}
          onAddAction={onAddAction}
          onEmployeeChanged={onEmployeeChanged}
        />
      ) : (
        <MarketingOverview
          analytics={analytics}
          config={config}
          selectedPosition={filters.position}
          onOpenPosition={openPosition}
        />
      )}
    </motion.div>
  );
};

const MarketingDashboardView = () => {
  const { role, fetchWithRole } = useUserRole();
  const { config, records, loading, error, refetch } = useMarketingData();
  const { getActionsForEmployee } = useActionStore();
  const [modalEmployee, setModalEmployee] = useState<TeamAgentRow | null>(null);
  const canExport = role === 'Admin' || role === 'Manager';

  const exportMarketing = async (filters: MarketingFilters) => {
    const params = new URLSearchParams({
      team: 'Marketing',
      performance_level: 'Employee',
      year: String(filters.year),
      month: filters.month,
      format: 'excel',
    });
    if (filters.position) params.set('position', filters.position);
    if (filters.region !== 'All') params.set('region', filters.region);
    const response = await fetchWithRole(`${API_BASE}/api/performance/export?${params}`);
    if (!response.ok) throw new Error('Marketing export failed');
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    const positionPart = filters.position ? `_${filters.position.replace(/\s+/g, '_')}` : '';
    anchor.href = url;
    anchor.download = `Marketing${positionPart}_${filters.year}_${filters.month}.xlsx`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-[1680px] animate-pulse space-y-5">
        <div className="h-20 rounded-2xl bg-[var(--bg-sunken)]" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[1, 2, 3, 4].map((item) => <div key={item} className="h-32 rounded-2xl bg-[var(--bg-sunken)]" />)}
        </div>
        <div className="h-[420px] rounded-2xl bg-[var(--bg-sunken)]" />
      </div>
    );
  }

  if (error || !config) {
    return (
      <div className="mx-auto flex min-h-[55vh] max-w-xl items-center justify-center">
        <div className="glass-panel w-full rounded-3xl p-8 text-center shadow-xl">
          <AlertCircle size={34} className="mx-auto text-rose-500" />
          <h2 className="mt-4 text-xl font-extrabold text-[var(--text-primary)]">Unable to load Marketing performance.</h2>
          <p className="mt-2 text-sm font-semibold text-[var(--text-muted)]">{error instanceof Error ? error.message : 'Marketing configuration is unavailable.'}</p>
          <button type="button" onClick={() => void refetch()} className="mx-auto mt-5 flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white">
            <RefreshCw size={15} /> Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      <MarketingDashboardContent
        config={config}
        records={records}
        canExport={canExport}
        onExport={exportMarketing}
        role={role || 'Viewer'}
        getActionsForEmployee={getActionsForEmployee}
        onAddAction={setModalEmployee}
        onEmployeeChanged={refetch}
      />
      {modalEmployee && (
        <EmployeeActionModal
          employee={modalEmployee}
          month={modalEmployee.month}
          onClose={() => setModalEmployee(null)}
        />
      )}
    </>
  );
};

export default MarketingDashboardView;
