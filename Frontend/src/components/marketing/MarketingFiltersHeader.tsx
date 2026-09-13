import { ArrowLeft, Download, Megaphone } from 'lucide-react';
import Breadcrumb from '../common/Breadcrumb';
import CustomDropdown from '../common/CustomDropdown';
import ResponsiveFilters from '../common/ResponsiveFilters';
import type {
  MarketingFilters,
  MarketingPeriod,
  MarketingRegion,
} from '../../features/marketing/types';

interface MarketingFiltersHeaderProps {
  filters: MarketingFilters;
  isPositionView: boolean;
  positionName?: string;
  periods: MarketingPeriod[];
  positions: string[];
  canExport: boolean;
  exporting: boolean;
  onChange: (key: keyof MarketingFilters, value: string | number | undefined) => void;
  onPeriodChange: (periodKey: string) => void;
  onBack: () => void;
  onExport: () => void;
}

const MarketingFiltersHeader = ({
  filters,
  isPositionView,
  positionName,
  periods,
  positions,
  canExport,
  exporting,
  onChange,
  onPeriodChange,
  onBack,
  onExport,
}: MarketingFiltersHeaderProps) => {
  const yearPeriods = periods.filter((period) => period.year === filters.year);
  const selectedPeriod = periods.find(
    (period) => period.year === filters.year && period.month === filters.month,
  );
  const monthControl = (
    <CustomDropdown
      value={filters.month === 'All' ? 'All' : selectedPeriod?.key || ''}
      options={[
        { value: 'All', label: 'All Months' },
        ...yearPeriods.map((period) => ({
          value: period.key,
          label: period.label || `${period.month} ${period.year}`,
        })),
      ]}
      onChange={(val) => onPeriodChange(String(val))}
      ariaLabel="Marketing month"
      size="md"
    />
  );
  const activeFilterCount = [
    filters.region !== 'All',
    filters.month !== 'All',
    !isPositionView && Boolean(filters.position),
  ].filter(Boolean).length;

  return (
    <header className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4 sm:p-5 shadow-sm">
      <div className="marketing-header-layout flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="marketing-header-heading flex items-center gap-3">
          {isPositionView ? (
            <button
              type="button"
              onClick={onBack}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-[var(--border-medium)] text-[var(--text-secondary)] transition hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)]"
              aria-label="Back to Marketing Overview"
            >
              <ArrowLeft size={20} />
            </button>
          ) : (
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-400">
              <Megaphone size={22} />
            </div>
          )}
          <div className="marketing-header-copy">
            <h2 className="heading-2 font-extrabold text-[var(--text-primary)] mb-0">
              {isPositionView ? `${positionName} · Employee` : 'Marketing Overview'}
            </h2>
            <Breadcrumb
              items={[
                { label: 'Executive Dashboard', href: '/executive' },
                ...(isPositionView ? [
                  { label: 'Marketing Overview', href: '/team/marketing' },
                  { label: positionName || 'Position Detail' },
                ] : [
                  { label: 'Marketing Overview' },
                ]),
              ]}
            />
          </div>
        </div>

        <div className="marketing-header-controls">
          <ResponsiveFilters activeCount={activeFilterCount} label="Filters">
          {isPositionView && (
            <CustomDropdown
              value="Employee"
              options={['Employee']}
              onChange={() => {}}
              ariaLabel="Marketing performance level"
              disabled
              size="md"
            />
          )}

          {!isPositionView && monthControl}

          <CustomDropdown
            value={filters.region}
            options={(['All', 'EGY', 'UAE'] as MarketingRegion[]).map((r) => ({
              value: r,
              label: r === 'All' ? 'All Regions' : r,
            }))}
            onChange={(val) => onChange('region', val as MarketingRegion)}
            ariaLabel="Marketing region"
            size="md"
          />

          {isPositionView && monthControl}

          {!isPositionView && (
            <CustomDropdown
              value={filters.position || ''}
              options={[
                { value: '', label: 'All Positions' },
                ...positions.map((p) => ({ value: p, label: p })),
              ]}
              onChange={(val) => onChange('position', val ? String(val) : undefined)}
              ariaLabel="Marketing position"
              size="md"
            />
          )}

          </ResponsiveFilters>

          {canExport && (
            <button
              type="button"
              onClick={onExport}
              disabled={exporting}
              className="marketing-export-button inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-bold text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-50"
            >
              <Download size={15} aria-hidden="true" />
              <span>{exporting ? 'Exporting...' : 'Export Excel'}</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
};

export default MarketingFiltersHeader;
