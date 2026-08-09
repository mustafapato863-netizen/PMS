import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Eye, FileText, Loader2, Presentation, Save, X } from 'lucide-react';
import { useGenerateReport, usePreviewReport, useSaveReportTemplate } from '../../hooks/api/useReports';
import type {
  GeneratedReport,
  ReportConfiguration,
  ReportOptions,
  ReportTemplate,
} from '../../features/reports/types';
import OverlayPortal from '../common/OverlayPortal';

interface ReportConfigModalProps {
  template: ReportTemplate;
  options: ReportOptions;
  initialConfiguration: ReportConfiguration;
  onClose: () => void;
  onGenerated: (report: GeneratedReport) => void;
}

type ReportOutputFormat = 'pptx' | 'pdf' | 'excel';

const SECTION_LABELS: Record<string, string> = {
  summary: 'Executive summary',
  grade_distribution: 'Grade distribution',
  team_breakdown: 'Team breakdown',
  kpi_breakdown: 'KPI breakdown',
  status_breakdown: 'Status breakdown',
  details: 'Detailed records',
};

const OUTPUT_FORMATS: Array<{ value: 'pptx' | 'pdf'; label: string; description: string; icon: typeof Presentation }> = [
  { value: 'pptx', label: 'PowerPoint', description: 'Default presentation export', icon: Presentation },
  { value: 'pdf', label: 'PDF', description: 'Portable document export', icon: FileText },
];

function normalizeOutputFormat(value?: string | null): ReportOutputFormat {
  return value === 'pdf' ? 'pdf' : 'pptx';
}

function SelectField({
  label,
  value,
  values,
  onChange,
  allLabel = 'All authorized',
  required = false,
}: {
  label: string;
  value: string;
  values: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
  allLabel?: string;
  required?: boolean;
}) {
  return (
    <label className="space-y-1.5 text-xs font-bold text-[var(--text-secondary)]">
      <span>{label}</span>
      <select
        value={value}
        required={required}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-11 w-full rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 text-sm text-[var(--input-text)] outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
      >
        {!required && <option value="">{allLabel}</option>}
        {values.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
      </select>
    </label>
  );
}

export default function ReportConfigModal({
  template,
  options,
  initialConfiguration,
  onClose,
  onGenerated,
}: ReportConfigModalProps) {
  const [configuration, setConfiguration] = useState({
    ...initialConfiguration,
    output_format: normalizeOutputFormat(initialConfiguration.output_format),
  });
  const [templateName, setTemplateName] = useState(initialConfiguration.report_name);
  const previewMutation = usePreviewReport();
  const generateMutation = useGenerateReport();
  const saveMutation = useSaveReportTemplate();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [onClose]);

  const update = <K extends keyof ReportConfiguration>(key: K, value: ReportConfiguration[K]) => {
    setConfiguration((current) => ({ ...current, [key]: value }));
    previewMutation.reset();
  };

  const periodValues = options.periods.map((period) => ({
    value: period.key,
    label: `${period.month} ${period.year}`,
  }));
  const exactStart = options.periods.find(
    (period) => period.month === configuration.start_month && period.year === configuration.start_year,
  )?.key || '';
  const endKey = configuration.end_month && configuration.end_year
    ? options.periods.find((period) => period.month === configuration.end_month && period.year === configuration.end_year)?.key || ''
    : '';

  const employees = useMemo(() => options.employees.filter((employee) => (
    (!configuration.team || employee.team === configuration.team)
    && (!configuration.region || employee.region === configuration.region)
    && (!configuration.position || employee.position === configuration.position)
    && (!configuration.performance_level || employee.performance_level === configuration.performance_level)
  )), [configuration.performance_level, configuration.position, configuration.region, configuration.team, options.employees]);

  const setPeriod = (key: 'start' | 'end', value: string) => {
    if (!value && key === 'end') {
      setConfiguration((current) => ({ ...current, end_month: null, end_year: null }));
      previewMutation.reset();
      return;
    }
    const period = options.periods.find((item) => item.key === value);
    if (!period) return;
    setConfiguration((current) => ({
      ...current,
      [`${key}_month`]: period.month,
      [`${key}_year`]: period.year,
    }));
    previewMutation.reset();
  };

  const toggleSection = (section: string) => {
    const next = configuration.included_sections.includes(section)
      ? configuration.included_sections.filter((value) => value !== section)
      : [...configuration.included_sections, section];
    update('included_sections', next);
  };

  const error = previewMutation.error || generateMutation.error || saveMutation.error;
  const isBusy = previewMutation.isPending || generateMutation.isPending;

  return (
    <OverlayPortal>
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 p-0 backdrop-blur-sm sm:p-3" onMouseDown={onClose}>
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="report-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
        className="custom-scrollbar h-full max-h-none w-full max-w-5xl overflow-y-auto rounded-none border border-[var(--border-medium)] bg-[var(--bg-surface)] shadow-2xl sm:h-auto sm:max-h-[94vh] sm:rounded-3xl"
      >
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-[var(--border-light)] bg-[var(--bg-surface)]/95 px-5 py-4 backdrop-blur md:px-7">
          <div>
            <p className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-blue-600">Configure report</p>
            <h2 id="report-dialog-title" className="mt-1 text-xl font-extrabold text-[var(--text-primary)]">{template.name}</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">Preview the authorized data before generating the presentation or PDF.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close report configuration" className="min-h-11 min-w-11 rounded-xl text-[var(--text-muted)] hover:bg-[var(--bg-sunken)]">
            <X className="mx-auto" size={19} />
          </button>
        </header>

        <div className="grid gap-6 p-5 md:p-7 lg:grid-cols-[1fr_0.9fr]">
          <div className="space-y-5">
            <label className="block space-y-1.5 text-xs font-bold text-[var(--text-secondary)]">
              <span>Report name</span>
              <input
                value={configuration.report_name}
                onChange={(event) => update('report_name', event.target.value)}
                maxLength={180}
                className="min-h-11 w-full rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 text-sm text-[var(--input-text)] outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
              />
            </label>

            <div className="grid gap-3 sm:grid-cols-2">
              <SelectField label="Start period" value={exactStart} values={periodValues} required onChange={(value) => setPeriod('start', value)} />
              <SelectField label="End period" value={endKey} values={periodValues} allLabel="Same as start" onChange={(value) => setPeriod('end', value)} />
              <SelectField label="Region" value={configuration.region || ''} values={options.regions.map((value) => ({ value, label: value }))} onChange={(value) => update('region', value || null)} />
              <SelectField label="Team" value={configuration.team || ''} values={options.teams.map((value) => ({ value, label: value }))} required={template.type === 'team'} onChange={(value) => update('team', value || null)} />
              <SelectField label="Performance level" value={configuration.performance_level || ''} values={options.performance_levels.map((value) => ({ value, label: value }))} onChange={(value) => update('performance_level', value || null)} />
              <SelectField label="Position" value={configuration.position || ''} values={options.positions.map((value) => ({ value, label: value }))} required={template.type === 'position'} onChange={(value) => update('position', value || null)} />
              <SelectField label="Employee" value={configuration.employee_id || ''} values={employees.map((employee) => ({ value: employee.id, label: `${employee.name} (${employee.id})` }))} required={template.type === 'employee'} onChange={(value) => update('employee_id', value || null)} />
              <SelectField label="Grade" value={configuration.grade || ''} values={options.grades.map((value) => ({ value, label: value }))} onChange={(value) => update('grade', value || null)} />
              <SelectField label="Status" value={configuration.status || ''} values={options.statuses.map((value) => ({ value, label: value }))} onChange={(value) => update('status', value || null)} />
            </div>

            <fieldset>
              <legend className="text-xs font-bold text-[var(--text-secondary)]">Included sections</legend>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {template.sections.map((section) => (
                  <label key={section} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/60 px-3 text-sm font-semibold text-[var(--text-secondary)]">
                    <input type="checkbox" checked={configuration.included_sections.includes(section)} onChange={() => toggleSection(section)} className="h-4 w-4 accent-blue-600" />
                    {SECTION_LABELS[section] || section}
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 px-3 py-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-extrabold text-blue-800 dark:text-blue-200">Output format</p>
                  <p className="text-[11px] text-blue-700 dark:text-blue-300">PowerPoint is selected by default.</p>
                </div>
                <Presentation size={20} className="text-blue-600" />
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {OUTPUT_FORMATS.map((format) => {
                  const Icon = format.icon;
                  const selected = configuration.output_format === format.value;
                  return (
                    <button
                      key={format.value}
                      type="button"
                      onClick={() => update('output_format', format.value)}
                      className={`flex items-center gap-3 rounded-xl border px-3 py-3 text-left transition-colors ${
                        selected
                          ? 'border-blue-500 bg-blue-500/10 text-blue-700 dark:text-blue-300'
                          : 'border-[var(--border-light)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:border-blue-400/40'
                      }`}
                    >
                      <span className={`rounded-lg p-2 ${selected ? 'bg-blue-500/15' : 'bg-[var(--bg-sunken)]'}`}>
                        <Icon size={16} />
                      </span>
                      <span>
                        <span className="block text-sm font-extrabold">{format.label}</span>
                        <span className="block text-[11px] opacity-80">{format.description}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/50 p-3">
              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  aria-label="Saved template name"
                  value={templateName}
                  onChange={(event) => setTemplateName(event.target.value)}
                  className="min-h-10 flex-1 rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 text-sm text-[var(--input-text)]"
                />
                <button
                  type="button"
                  disabled={!templateName.trim() || saveMutation.isPending}
                  onClick={() => saveMutation.mutate({ templateName: templateName.trim(), configuration })}
                  className="inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-[var(--border-medium)] px-4 text-xs font-bold text-[var(--text-secondary)] disabled:opacity-50"
                >
                  <Save size={15} /> {saveMutation.isPending ? 'Saving...' : 'Save configuration'}
                </button>
              </div>
              {saveMutation.isSuccess && <p className="mt-2 flex items-center gap-1 text-xs font-bold text-emerald-600"><CheckCircle2 size={14} /> Saved privately.</p>}
            </div>
          </div>

          <aside className="min-h-[360px] rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/40 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="font-extrabold text-[var(--text-primary)]">Data preview</h3>
                <p className="text-xs text-[var(--text-muted)]">First five matching records</p>
              </div>
              <button
                type="button"
                disabled={isBusy || !configuration.report_name.trim() || configuration.included_sections.length === 0}
                onClick={() => previewMutation.mutate(configuration)}
                className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-blue-600 px-4 text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {previewMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Eye size={15} />} Preview
              </button>
            </div>

            {!previewMutation.data && !previewMutation.isPending && (
              <div className="flex min-h-[270px] flex-col items-center justify-center text-center text-[var(--text-muted)]">
                <Presentation size={34} className="mb-3 text-blue-500" />
                <p className="text-sm font-bold text-[var(--text-secondary)]">Preview is required</p>
                <p className="mt-1 max-w-xs text-xs">The report is generated only after current filters return authorized data.</p>
              </div>
            )}

            {previewMutation.data && (
              <div className="mt-4 space-y-4">
                <div className="rounded-xl border border-blue-500/15 bg-blue-500/5 p-3">
                  <p className="font-extrabold text-[var(--text-primary)]">{previewMutation.data.title}</p>
                  <p className="mt-1 text-xs text-[var(--text-muted)]">{previewMutation.data.scope} · {previewMutation.data.period}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {Object.entries(previewMutation.data.filters).filter(([, value]) => value != null && value !== '').slice(0, 6).map(([key, value]) => (
                      <span key={key} className="rounded-full border border-[var(--border-light)] bg-[var(--bg-surface)] px-2 py-1 text-[10px] font-bold text-[var(--text-secondary)]">{key.replaceAll('_', ' ')}: {String(value)}</span>
                    ))}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(previewMutation.data.summary).filter(([, value]) => typeof value !== 'object').slice(0, 6).map(([key, value]) => (
                    <div key={key} className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-3">
                      <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-faint)]">{key.replaceAll('_', ' ')}</p>
                      <p className="mt-1 text-lg font-extrabold text-[var(--text-primary)]">{value == null ? 'N/A' : String(value)}</p>
                    </div>
                  ))}
                </div>
                {previewMutation.data.warnings.map((warning) => <p key={warning} className="rounded-xl bg-amber-500/10 p-3 text-xs font-semibold text-amber-700 dark:text-amber-300">{warning}</p>)}
                {previewMutation.data.table_preview.length > 0 && (
                  <div className="overflow-x-auto rounded-xl border border-[var(--border-light)]">
                    <table className="min-w-full text-left text-[11px]">
                      <thead className="bg-[var(--bg-sunken)] text-[var(--text-faint)]">
                        <tr>{Object.keys(previewMutation.data.table_preview[0]).slice(0, 4).map((key) => <th key={key} className="whitespace-nowrap px-3 py-2 font-extrabold">{key}</th>)}</tr>
                      </thead>
                      <tbody>{previewMutation.data.table_preview.map((row, index) => <tr key={index} className="border-t border-[var(--border-light)]">{Object.keys(row).slice(0, 4).map((key) => <td key={key} className="max-w-[140px] truncate px-3 py-2 text-[var(--text-secondary)]">{String(row[key] ?? '')}</td>)}</tr>)}</tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </aside>
        </div>

        {error && <div role="alert" className="mx-5 mb-4 flex items-center gap-2 rounded-xl bg-red-500/10 px-4 py-3 text-sm font-semibold text-red-600 md:mx-7"><AlertCircle size={17} /> {error.message}</div>}
        <footer className="sticky bottom-0 flex flex-wrap items-center justify-end gap-3 border-t border-[var(--border-light)] bg-[var(--bg-surface)]/95 px-5 py-4 backdrop-blur md:px-7">
          <button type="button" onClick={onClose} className="min-h-11 rounded-xl border border-[var(--border-medium)] px-5 text-sm font-bold text-[var(--text-secondary)]">Cancel</button>
          <button
            type="button"
            disabled={!previewMutation.data || generateMutation.isPending || !options.can_export}
            title={!options.can_export ? 'Your role can preview reports but cannot export them.' : undefined}
            onClick={() => generateMutation.mutate(configuration, { onSuccess: onGenerated })}
            className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-5 text-sm font-bold text-white shadow-lg shadow-blue-500/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {generateMutation.isPending ? <Loader2 size={17} className="animate-spin" /> : (configuration.output_format === 'pdf' ? <FileText size={17} /> : <Presentation size={17} />)}
            {options.can_export ? `Generate ${configuration.output_format.toUpperCase()}` : 'Export permission required'}
          </button>
        </footer>
      </section>
    </div>
    </OverlayPortal>
  );
}
