import {
  FileBarChart,
  Filter,
  Loader2,
  Presentation,
  RefreshCw,
  Sparkles,
  X,
} from 'lucide-react';
import type {
  ReportCenterFilters,
  ReportOptions,
  ReportTemplate,
} from '../../features/reports/types';

type SelectFilterOption = { value: string; label: string };

const FILTER_KEYS: Array<keyof ReportCenterFilters> = [
  'period',
  'comparison_period',
  'region',
  'team',
  'performance_level',
  'position',
  'employee_id',
  'grade',
  'status',
  'kpi',
];

const FILTER_LABELS: Record<keyof ReportCenterFilters, string> = {
  period: 'Period',
  comparison_period: 'Compare',
  region: 'Region',
  team: 'Team',
  performance_level: 'Level',
  position: 'Position',
  employee_id: 'Employee',
  grade: 'Grade',
  status: 'Status',
  kpi: 'KPI',
};

function periodLabel(period?: { month: string; year: number } | null) {
  return period ? `${period.month} ${period.year}` : 'No period';
}

function formatFilterValue(
  key: keyof ReportCenterFilters,
  value: string,
  options: ReportOptions,
) {
  if (key === 'period' || key === 'comparison_period') {
    return periodLabel(options.periods.find((period) => period.key === value));
  }
  if (key === 'employee_id') {
    const employee = options.employees.find((item) => item.id === value);
    return employee?.name || value;
  }
  return value;
}

function SelectFilter({
  label,
  value,
  values,
  onChange,
  disabled = false,
  allLabel = 'All authorized',
}: {
  label: string;
  value?: string;
  values: Array<string | SelectFilterOption>;
  onChange: (value: string) => void;
  disabled?: boolean;
  allLabel?: string;
}) {
  return (
    <label className="min-w-[155px] flex-1 space-y-1 text-xs font-bold text-[var(--text-secondary)]">
      <span>{label}</span>
      <select
        aria-label={label}
        value={value || ''}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-10 w-full rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 text-sm font-semibold text-[var(--input-text)] outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <option value="">{allLabel}</option>
        {values.map((item) => {
          const option = typeof item === 'string' ? { value: item, label: item } : item;
          return <option key={option.value} value={option.value}>{option.label}</option>;
        })}
      </select>
    </label>
  );
}

export interface ReportsCenterWorkspaceProps {
  role: string;
  filters: ReportCenterFilters;
  options: ReportOptions;
  isFetching?: boolean;
  onFilterChange: (key: keyof ReportCenterFilters, value: string) => void;
  onApplyQuickFilter: (filters: Partial<ReportCenterFilters>) => void;
  onResetFilters: () => void;
  onRefresh: () => void;
  templates: ReportTemplate[];
  templateScopeLabel?: (template: ReportTemplate) => string;
  onGenerateTemplate: (template: ReportTemplate) => void;
  generatingTemplateType?: string | null;
}

export default function ReportsCenterWorkspace({
  role,
  filters,
  options,
  isFetching = false,
  onFilterChange,
  onApplyQuickFilter,
  onResetFilters,
  onRefresh,
  templates,
  templateScopeLabel,
  onGenerateTemplate,
  generatingTemplateType = null,
}: ReportsCenterWorkspaceProps) {
  const capabilities = {
    role,
    can_export: options.can_export,
    can_view_people: options.can_view_people ?? (role === 'Admin' || role === 'Manager'),
    can_view_actions: options.can_view_actions ?? false,
    allowed_formats: options.allowed_formats || [],
  };
  const currentPeriod = options.periods.find((period) => period.key === filters.period) || options.periods[0];
  const latestPeriod = options.periods[0];
  const marketingTeam = options.teams.find((team) => team.toLowerCase() === 'marketing');
  const allowedFormats = capabilities.allowed_formats || [];
  const canGeneratePptx = capabilities.can_export && (allowedFormats.length === 0 || allowedFormats.includes('pptx'));
  const pptxTemplates = templates.filter((template) => template.formats.includes('pptx'));

  const employeeOptions = options.employees.filter((employee) => (
    (!filters.region || employee.region === filters.region)
    && (!filters.team || employee.team === filters.team)
    && (!filters.performance_level || employee.performance_level === filters.performance_level)
    && (!filters.position || employee.position === filters.position)
  ));
  const selectedEmployee = filters.employee_id
    ? options.employees.find((employee) => employee.id === filters.employee_id)
    : undefined;
  const visibleEmployeeOptions = selectedEmployee && !employeeOptions.some((employee) => employee.id === selectedEmployee.id)
    ? [selectedEmployee, ...employeeOptions]
    : employeeOptions;
  const allEmployeeLabel = filters.team || filters.region || filters.performance_level || filters.position
    ? 'All employees in selected scope'
    : 'All authorized employees';

  const activeFilterEntries = FILTER_KEYS
    .filter((key) => key !== 'period' && Boolean(filters[key]))
    .map((key) => ({
      key,
      value: filters[key] as string,
      label: FILTER_LABELS[key],
      displayValue: formatFilterValue(key, filters[key] as string, options),
    }));
  const scopeFilterCount = activeFilterEntries.filter((item) => item.key !== 'comparison_period').length;
  const selectedScope = [
    periodLabel(currentPeriod),
    filters.region || 'All regions',
    filters.team || 'All teams',
    filters.employee_id
      ? formatFilterValue('employee_id', filters.employee_id, options)
      : allEmployeeLabel,
  ];
  if (filters.comparison_period) {
    selectedScope.push(`Compare ${formatFilterValue('comparison_period', filters.comparison_period, options)}`);
  }
  const scopeSummary = selectedScope.join(' / ');

  const quickButtonClass = (active: boolean) => `inline-flex min-h-9 items-center justify-center rounded-lg border px-3 text-xs font-extrabold transition-colors ${active
    ? 'border-blue-500 bg-blue-500/10 text-blue-700 dark:text-blue-300'
    : 'border-[var(--border-light)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:border-blue-400/60 hover:text-blue-600'
  }`;

  return (
    <div className="space-y-5">
      <section className="rounded-3xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5 shadow-sm md:p-7">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="flex items-center gap-2 text-blue-600"><Sparkles size={16} /><span className="text-[10px] font-extrabold uppercase tracking-[0.18em]">Reports</span></div>
            <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-[var(--text-primary)]">PowerPoint reports</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">Choose a report type, apply the filters, and generate a ready-made PowerPoint from the authorized reporting data.</p>
            <div className="mt-4 flex flex-wrap gap-2 text-xs font-bold text-[var(--text-muted)]">
              <span className="rounded-full bg-[var(--bg-sunken)] px-3 py-1.5">Role: {role}</span>
              <span className="rounded-full bg-[var(--bg-sunken)] px-3 py-1.5">Period: {periodLabel(currentPeriod)}</span>
              <span className="rounded-full bg-blue-500/10 px-3 py-1.5 text-blue-700 dark:text-blue-300" aria-live="polite">{scopeFilterCount === 0 ? 'All authorized scope' : `${scopeFilterCount} scope filter${scopeFilterCount === 1 ? '' : 's'} active`}</span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 xl:justify-end">
            <button type="button" onClick={onRefresh} className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-[var(--border-light)] px-4 text-sm font-bold text-[var(--text-secondary)] hover:border-blue-400/50 hover:text-blue-600">
              <RefreshCw size={16} className={isFetching ? 'animate-spin' : ''} /> Refresh
            </button>
          </div>
        </div>
      </section>

      <section aria-label="Report filters" className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4 shadow-sm md:p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2"><Filter size={16} className="text-blue-600" /><h2 className="font-extrabold text-[var(--text-primary)]">Report filters</h2></div>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-[var(--text-muted)]">Set the period first, then narrow the scope. Changes apply immediately to every report type below.</p>
          </div>
          <button type="button" onClick={onResetFilters} className="self-start text-xs font-extrabold text-blue-600 hover:underline">Clear all</button>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          <SelectFilter label="Select Reporting Period" value={filters.period} values={options.periods.map((period) => period.key)} onChange={(value) => onFilterChange('period', value)} />
          <SelectFilter label="Comparison period" value={filters.comparison_period} values={options.periods.map((period) => period.key).filter((period) => period !== filters.period)} allLabel="No comparison" onChange={(value) => onFilterChange('comparison_period', value)} />
          <SelectFilter label="Region" value={filters.region} values={options.regions} allLabel="All regions" onChange={(value) => onFilterChange('region', value)} />
          <SelectFilter label="Team" value={filters.team} values={options.teams} allLabel="All teams" onChange={(value) => onFilterChange('team', value)} />
          <SelectFilter label="Performance level" value={filters.performance_level} values={options.performance_levels} allLabel="All levels" onChange={(value) => onFilterChange('performance_level', value)} />
          <SelectFilter label="Position" value={filters.position} values={options.positions} allLabel="All positions" onChange={(value) => onFilterChange('position', value)} />
          {capabilities.can_view_people && <SelectFilter label="Employee" value={filters.employee_id} values={visibleEmployeeOptions.map((employee) => ({ value: employee.id, label: employee.name || employee.id }))} allLabel={allEmployeeLabel} onChange={(value) => onFilterChange('employee_id', value)} />}
          <SelectFilter label="Grade" value={filters.grade} values={options.grades} allLabel="All grades" onChange={(value) => onFilterChange('grade', value)} />
          <SelectFilter label="Status" value={filters.status} values={options.statuses} allLabel="All statuses" onChange={(value) => onFilterChange('status', value)} />
          <SelectFilter label="KPI" value={filters.kpi} values={options.kpis || []} allLabel="All KPIs" onChange={(value) => onFilterChange('kpi', value)} />
        </div>

        <div className="mt-4 rounded-2xl border border-blue-500/20 bg-blue-500/5 p-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-2.5">
              <span className="rounded-lg bg-blue-500/10 p-2 text-blue-600"><Sparkles size={15} /></span>
              <div>
                <p className="text-sm font-extrabold text-[var(--text-primary)]">Quick setup</p>
                <p className="mt-0.5 text-xs text-[var(--text-muted)]">Use a shortcut, then refine any filter above.</p>
              </div>
            </div>
            <span className="text-xs font-extrabold text-blue-700 dark:text-blue-300" aria-live="polite">{scopeFilterCount === 0 ? 'All authorized scope' : `${scopeFilterCount} scope filter${scopeFilterCount === 1 ? '' : 's'} active`}</span>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {latestPeriod && <button type="button" aria-pressed={filters.period === latestPeriod.key} onClick={() => onApplyQuickFilter({ period: latestPeriod.key })} className={quickButtonClass(filters.period === latestPeriod.key)}>Latest period</button>}
            {marketingTeam && <button type="button" aria-pressed={filters.team === marketingTeam} onClick={() => onApplyQuickFilter({ team: marketingTeam })} className={quickButtonClass(filters.team === marketingTeam)}>Marketing</button>}
            <button type="button" aria-pressed={scopeFilterCount === 0} onClick={() => onApplyQuickFilter({ comparison_period: '', region: '', team: '', performance_level: '', position: '', employee_id: '', grade: '', status: '', kpi: '' })} className={quickButtonClass(scopeFilterCount === 0)}>All authorized</button>
          </div>
          <p className="mt-3 text-[11px] font-semibold text-[var(--text-muted)]">The active filters are passed to every Generate button. Leave Employee at “All employees in selected scope” and Level at “All levels” for the complete authorized team average; selecting a person intentionally narrows the report.</p>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2" aria-label="Active report filters">
          <span className="text-[11px] font-extrabold uppercase tracking-[0.12em] text-[var(--text-faint)]">Active filters</span>
          {activeFilterEntries.length > 0 ? activeFilterEntries.map((item) => (
            <button key={item.key} type="button" aria-label={`Remove ${item.label} filter`} onClick={() => onFilterChange(item.key, '')} className="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-[var(--border-light)] bg-[var(--bg-sunken)] px-2.5 text-[11px] font-bold text-[var(--text-secondary)] hover:border-blue-400/60 hover:text-blue-600">
              {item.label}: {item.displayValue}<X size={13} />
            </button>
          )) : <span className="text-xs font-semibold text-[var(--text-muted)]">All authorized records</span>}
        </div>

        {!canGeneratePptx && <p className="mt-3 rounded-xl bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-700 dark:text-amber-300">Preview only - report generation is unavailable for your role.</p>}
      </section>

      {isFetching && <div role="status" className="text-right text-xs font-semibold text-[var(--text-muted)]">Refreshing report options...</div>}

      <section aria-label="Report types" className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5 shadow-sm">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="font-extrabold text-[var(--text-primary)]">Choose a report type</h2>
            <p className="mt-1 text-xs leading-5 text-[var(--text-muted)]">Generate a ready-made PowerPoint sample using the filters above. The generated file will appear in report history for download.</p>
          </div>
          <span className="rounded-full bg-blue-500/10 px-3 py-1 text-xs font-extrabold text-blue-700 dark:text-blue-300">{pptxTemplates.length} available</span>
        </div>

        <div className="mt-4 flex flex-col gap-3 rounded-2xl border border-blue-500/20 bg-blue-500/5 p-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-2.5">
            <span className="rounded-lg bg-blue-500/10 p-2 text-blue-600"><FileBarChart size={16} /></span>
            <div className="min-w-0">
              <p className="text-xs font-extrabold text-blue-800 dark:text-blue-200">Active filters for report generation</p>
              <p className="mt-1 truncate text-xs font-semibold text-blue-700 dark:text-blue-300" aria-live="polite" title={scopeSummary}>{scopeSummary}</p>
            </div>
          </div>
          <span className="shrink-0 rounded-full bg-[var(--bg-surface)] px-2.5 py-1 text-[11px] font-extrabold text-[var(--text-secondary)]">{scopeFilterCount} scope filter{scopeFilterCount === 1 ? '' : 's'}</span>
        </div>

        {pptxTemplates.length > 0 ? <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{pptxTemplates.map((template) => {
          const isGenerating = generatingTemplateType === template.type;
          const canGenerateTemplate = canGeneratePptx;
          const effectiveScope = templateScopeLabel?.(template) || scopeSummary;
          return <article key={template.type} className="flex flex-col rounded-2xl border border-[var(--border-light)] p-4 transition-colors hover:border-blue-400/50">
            <div className="flex items-start justify-between gap-2">
              <span className="rounded-xl bg-blue-500/10 p-2 text-blue-600"><FileBarChart size={20} /></span>
              <div className="flex flex-wrap justify-end gap-1">
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-1 text-[10px] font-extrabold text-emerald-700 dark:text-emerald-300"><Presentation size={11} /> PPTX</span>
                <span className="rounded-full bg-[var(--bg-sunken)] px-2 py-1 text-[10px] font-extrabold text-[var(--text-muted)]">{template.category || template.type}</span>
              </div>
            </div>
            <h3 className="mt-4 font-extrabold text-[var(--text-primary)]">{template.name}</h3>
            <p className="mt-1 flex-1 text-xs leading-5 text-[var(--text-muted)]">{template.description}</p>
            <p className="mt-3 rounded-lg bg-[var(--bg-sunken)] px-2.5 py-2 text-[11px] font-semibold text-[var(--text-secondary)]" title={effectiveScope}>Effective sample scope: {effectiveScope}</p>
            <button type="button" aria-label={canGenerateTemplate ? `Generate PPTX for ${template.name}` : 'Preview only'} title={canGenerateTemplate ? `Generate ${template.name} for ${effectiveScope}` : undefined} disabled={!canGenerateTemplate || Boolean(generatingTemplateType)} onClick={() => onGenerateTemplate(template)} className="mt-4 inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-blue-600 px-3 text-sm font-bold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">{isGenerating ? <><Loader2 size={16} className="animate-spin" /> Generating PPTX</> : canGenerateTemplate ? 'Generate PPTX' : 'Preview only'}</button>
          </article>;
        })}</div> : <div className="mt-4 rounded-xl border border-dashed border-[var(--border-light)] px-4 py-10 text-center text-sm font-semibold text-[var(--text-muted)]">No PowerPoint report types are available for your role.</div>}
      </section>
    </div>
  );
}
