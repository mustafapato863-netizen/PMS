import { useEffect, useRef } from 'react';
import { AlertCircle, ChevronDown, CheckCircle2 } from 'lucide-react';
import { useReportOptions } from '../../../hooks/api/useReports';
import { useReportBuilderStore } from '../../../store/reportBuilderStore';
import { PageLoadingSkeleton } from '../../common/SkeletonLoader';
import {
  generatedReportName,
  isComparisonBeforePrimary,
  isGeneratedReportName,
  previousAvailablePeriod,
  validateReportScope,
  type ScopeValidationErrors,
} from '../../../features/reports/reportBuilderValidation';

const selectClass = 'min-h-11 rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] pl-3 pr-9 text-sm font-semibold text-[var(--input-text)] outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20';

function FilterSelect({ label, value, onChange, values, allLabel, required = false, error }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  values: Array<{ value: string; label: string }>;
  allLabel?: string;
  required?: boolean;
  error?: string;
}) {
  const id = `report-filter-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-bold text-slate-700 dark:text-slate-200">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={Boolean(error)}
          className={`${selectClass} w-full appearance-none ${error ? 'border-red-400 focus:border-red-500 focus:ring-red-500/15' : ''}`}
        >
          {allLabel && <option value="">{allLabel}</option>}
          {values.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
        <ChevronDown aria-hidden="true" size={15} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />
      </div>
      {error && <p className="text-xs font-semibold text-red-600">{error}</p>}
    </div>
  );
}

export default function Step1Scope({ validationErrors = {} }: { validationErrors?: ScopeValidationErrors }) {
  const { data: options, isLoading, error } = useReportOptions();
  const { configuration, setConfiguration } = useReportBuilderStore();
  const initializedOptions = useRef(false);

  useEffect(() => {
    if (!options?.periods.length || initializedOptions.current) return;
    initializedOptions.current = true;
    const primary = options.periods.find((period) => period.year === configuration.start_year && period.month === configuration.start_month) || options.periods[0];
    const configuredComparison = options.periods.find((period) => period.year === configuration.end_year && period.month === configuration.end_month);
    const comparison = configuredComparison && isComparisonBeforePrimary(configuration)
      ? configuredComparison
      : previousAvailablePeriod(options.periods, primary);
    setConfiguration({
      report_name: configuration.report_name?.trim() || generatedReportName(primary),
      start_month: primary.month,
      start_year: primary.year,
      end_month: comparison?.month || null,
      end_year: comparison?.year || null,
    });
  }, [configuration, options, setConfiguration]);

  if (isLoading) {
    return <PageLoadingSkeleton variant="form" label="Preparing report scope" compact />;
  }

  if (error || !options) {
    return (
      <div className="mx-auto mt-12 max-w-xl rounded-2xl border border-red-500/20 bg-red-500/10 p-6 text-center text-red-600">
        <AlertCircle className="mx-auto mb-3" />
        <p className="font-extrabold">Unable to load report options</p>
      </div>
    );
  }

  const selectedStartPeriod = options.periods.find(p => p.year === configuration.start_year && p.month === configuration.start_month);
  const periodKey = selectedStartPeriod ? selectedStartPeriod.key : '';

  const selectedEndPeriod = options.periods.find(p => p.year === configuration.end_year && p.month === configuration.end_month);
  const endPeriodKey = selectedEndPeriod ? selectedEndPeriod.key : '';

  const handlePeriodChange = (val: string) => {
    const period = options.periods.find(p => p.key === val);
    if (period) {
      const nextComparison = previousAvailablePeriod(options.periods, period);
      const keepComparison = configuration.end_year && configuration.end_month && isComparisonBeforePrimary({
        ...configuration,
        start_year: period.year,
        start_month: period.month,
      });
      setConfiguration({
        start_year: period.year,
        start_month: period.month,
        ...(isGeneratedReportName(configuration.report_name) ? { report_name: generatedReportName(period) } : {}),
        ...(!keepComparison ? {
          end_year: nextComparison?.year || null,
          end_month: nextComparison?.month || null,
        } : {}),
      });
    }
  };

  const regionTeams = configuration.region
    ? [...new Set(options.employees.filter((employee) => employee.region === configuration.region).map((employee) => employee.team))].sort()
    : options.teams;
  const isScopeValid = Object.keys(validateReportScope(configuration)).length === 0;

  return (
    <div className="max-w-3xl mx-auto py-8">
      <div className="mb-8">
        <h2 className="text-2xl font-extrabold text-slate-900">Define Report Scope</h2>
        <p className="text-slate-500 mt-1">Select the parameters for the data you want to include in this report.</p>
      </div>

      <div className="space-y-6 bg-white p-6 md:p-8 rounded-2xl border border-slate-200 shadow-sm">

        {/* Basic Info */}
        <div className="space-y-1.5">
          <label htmlFor="report-name" className="block text-sm font-bold text-slate-700 dark:text-slate-200">
            Report Name <span className="text-red-500">*</span>
          </label>
          <input
            id="report-name"
            type="text"
            placeholder="e.g. Q3 Sales Team Performance"
            value={configuration.report_name || ''}
            onChange={(e) => setConfiguration({ report_name: e.target.value })}
            aria-invalid={Boolean(validationErrors.report_name)}
            className={`${selectClass} w-full pr-3 ${validationErrors.report_name ? 'border-red-400 focus:border-red-500 focus:ring-red-500/15' : ''}`}
          />
          {validationErrors.report_name && <p className="text-xs font-semibold text-red-600">{validationErrors.report_name}</p>}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <FilterSelect
            label="Reporting Period"
            value={periodKey}
            onChange={handlePeriodChange}
            values={options.periods.map(p => ({ value: p.key, label: `${p.month} ${p.year}` }))}
            allLabel="Select period..."
            required
            error={validationErrors.primary_period}
          />

          <FilterSelect
            label="Comparison Period"
            value={endPeriodKey}
            onChange={(val) => {
               if (!val) {
                 setConfiguration({ end_year: null, end_month: null });
                 return;
               }
               const period = options.periods.find(p => p.key === val);
               setConfiguration({ end_year: period?.year || null, end_month: period?.month || null });
            }}
            values={options.periods.map(p => ({ value: p.key, label: `${p.month} ${p.year}` }))}
            allLabel="Select comparison period..."
            required
            error={validationErrors.comparison_period}
          />
        </div>

        <hr className="border-slate-100" />

        {/* Data Filters */}
        <div>
           <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500 mb-4">Data Filters</h3>
           <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <FilterSelect
                label="Region"
                value={configuration.region || ''}
                onChange={(val) => setConfiguration({ region: val, team: '' })}
                values={options.regions.map(r => ({ value: r, label: r }))}
                allLabel="All regions"
              />
              <FilterSelect
                label="Team"
                value={configuration.team || ''}
                onChange={(val) => setConfiguration({ team: val })}
                values={regionTeams.map(t => ({ value: t, label: t }))}
                allLabel="All teams"
              />
              <FilterSelect
                label="Position"
                value={configuration.position || ''}
                onChange={(val) => setConfiguration({ position: val, employee_id: '' })}
                values={options.positions.map(p => ({ value: p, label: p }))}
                allLabel="All positions"
              />
              <FilterSelect
                label="Performance Level"
                value={configuration.performance_level || ''}
                onChange={(val) => setConfiguration({ performance_level: val })}
                values={options.performance_levels.map(l => ({ value: l, label: l }))}
                allLabel="All levels"
              />
           </div>
        </div>

      </div>

      {isScopeValid && (
         <div className="mt-6 flex items-center gap-2 text-green-600 bg-green-50 p-4 rounded-xl border border-green-200">
           <CheckCircle2 size={20} />
           <span className="font-semibold text-sm">Scope is fully defined. You can proceed to the next step.</span>
         </div>
      )}
    </div>
  );
}
