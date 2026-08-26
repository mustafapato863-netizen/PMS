import './PageEnhancements.css';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AlertCircle, CheckCircle2, Download, FileSpreadsheet, FileText, Loader2, Presentation, RefreshCw, Trash2 } from 'lucide-react';
import OverlayPortal from '../components/common/OverlayPortal';
import { PageLoadingSkeleton } from '../components/common/SkeletonLoader';
import ReportsCenterWorkspace from '../components/reports/ReportsCenterWorkspace';
import { API_BASE } from '../config';
import { useUserRole } from '../context/RoleContext';
import type {
  GeneratedReport,
  ReportCenterFilters,
  ReportConfiguration,
  ReportTemplate,
} from '../features/reports/types';
import {
  useDeleteGeneratedReport,
  useDeleteGeneratedReports,
  useGeneratedReports,
  useGenerateReport,
  useReportOptions,
  useReportTemplates,
  type ReportHistoryFilters,
} from '../hooks/api/useReports';

function formatDate(value?: string) {
  if (!value) return 'N/A';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

function formatMeta(format?: string) {
  if (format === 'excel') return { label: 'Excel', icon: FileSpreadsheet };
  if (format === 'pptx') return { label: 'PPTX', icon: Presentation };
  return { label: 'PDF', icon: FileText };
}

function DeleteReportModal({
  report,
  onCancel,
  onDeleted,
}: {
  report: GeneratedReport;
  onCancel: () => void;
  onDeleted: (report: GeneratedReport) => void;
}) {
  const mutation = useDeleteGeneratedReport();
  const confirm = async () => {
    try {
      await mutation.mutateAsync(report.id);
      onDeleted(report);
    } catch {
      // The mutation error is rendered in the dialog.
    }
  };
  return (
    <OverlayPortal>
      <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget && !mutation.isPending) onCancel(); }}>
        <section role="alertdialog" aria-modal="true" aria-labelledby="delete-generated-report-title" aria-describedby="delete-generated-report-description" className="w-full max-w-lg rounded-3xl border border-rose-500/20 bg-[var(--bg-surface)] p-6 shadow-2xl">
          <div className="flex items-start gap-4"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-rose-500/10 text-rose-600"><Trash2 size={19} /></span><div><h2 id="delete-generated-report-title" className="text-xl font-extrabold text-[var(--text-primary)]">Delete this report?</h2><p id="delete-generated-report-description" className="mt-2 text-sm leading-6 text-[var(--text-muted)]"><strong>{report.name}</strong> and its generated {(report.format || 'file').toUpperCase()} file will be permanently removed.</p></div></div>
          {mutation.error && <p role="alert" className="mt-4 rounded-xl bg-rose-500/10 p-3 text-sm font-bold text-rose-600">{mutation.error instanceof Error ? mutation.error.message : 'Unable to delete this report.'}</p>}
          <div className="mt-6 flex justify-end gap-2"><button type="button" onClick={onCancel} disabled={mutation.isPending} className="min-h-11 rounded-xl border border-[var(--border-light)] px-4 font-bold text-[var(--text-secondary)] disabled:opacity-60">Cancel</button><button type="button" onClick={confirm} disabled={mutation.isPending} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-rose-600 px-5 font-bold text-white disabled:opacity-60">{mutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />} Delete report</button></div>
        </section>
      </div>
    </OverlayPortal>
  );
}

function DeleteReportsModal({
  reports,
  onCancel,
  onDeleted,
}: {
  reports: GeneratedReport[];
  onCancel: () => void;
  onDeleted: (reports: GeneratedReport[]) => void;
}) {
  const mutation = useDeleteGeneratedReports();
  const confirm = async () => {
    try {
      await mutation.mutateAsync(reports.map((report) => report.id));
      onDeleted(reports);
    } catch {
      // The mutation error is rendered in the dialog.
    }
  };
  return (
    <OverlayPortal>
      <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget && !mutation.isPending) onCancel(); }}>
        <section role="alertdialog" aria-modal="true" aria-labelledby="delete-generated-reports-title" aria-describedby="delete-generated-reports-description" className="w-full max-w-lg rounded-3xl border border-rose-500/20 bg-[var(--bg-surface)] p-6 shadow-2xl">
          <div className="flex items-start gap-4"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-rose-500/10 text-rose-600"><Trash2 size={19} /></span><div className="min-w-0"><h2 id="delete-generated-reports-title" className="text-xl font-extrabold text-[var(--text-primary)]">Delete {reports.length} report{reports.length === 1 ? '' : 's'}?</h2><p id="delete-generated-reports-description" className="mt-2 text-sm leading-6 text-[var(--text-muted)]">The selected reports and their generated files will be permanently removed.</p><ul className="mt-3 max-h-28 list-disc space-y-1 overflow-y-auto pl-5 text-xs font-semibold text-[var(--text-secondary)]">{reports.map((report) => <li key={report.id}>{report.name}</li>)}</ul></div></div>
          {mutation.error && <p role="alert" className="mt-4 rounded-xl bg-rose-500/10 p-3 text-sm font-bold text-rose-600">{mutation.error instanceof Error ? mutation.error.message : 'Unable to delete these reports.'}</p>}
          <div className="mt-6 flex justify-end gap-2"><button type="button" onClick={onCancel} disabled={mutation.isPending} className="min-h-11 rounded-xl border border-[var(--border-light)] px-4 font-bold text-[var(--text-secondary)] disabled:opacity-60">Cancel</button><button type="button" onClick={confirm} disabled={mutation.isPending} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-rose-600 px-5 font-bold text-white disabled:opacity-60">{mutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />} Delete reports</button></div>
        </section>
      </div>
    </OverlayPortal>
  );
}

function historyFiltersFromParams(params: URLSearchParams): ReportHistoryFilters {
  return {
    report_type: params.get('history_type') || undefined,
    period: params.get('history_period') || undefined,
    status: params.get('history_status') || undefined,
    search: params.get('history_search') || undefined,
  };
}

export default function ReportsView() {
  const { role, fetchWithRole } = useUserRole();
  const [params, setParams] = useSearchParams();
  const templatesQuery = useReportTemplates();
  const optionsQuery = useReportOptions();
  const [page, setPage] = useState(1);
  const [generatingTemplateType, setGeneratingTemplateType] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<GeneratedReport | null>(null);
  const [deleteCandidates, setDeleteCandidates] = useState<GeneratedReport[] | null>(null);
  const [selectedReportIds, setSelectedReportIds] = useState<string[]>([]);

  const filters = useMemo<ReportCenterFilters>(() => {
    const keys: Array<keyof ReportCenterFilters> = ['period', 'comparison_period', 'region', 'team', 'performance_level', 'position', 'employee_id', 'grade', 'status', 'kpi'];
    return keys.reduce((result, key) => {
      const value = params.get(key);
      if (value) result[key] = value;
      return result;
    }, {} as ReportCenterFilters);
  }, [params]);
  const historyFilters = useMemo(() => historyFiltersFromParams(params), [params]);
  const options = optionsQuery.data;
  const templates = templatesQuery.data || [];
  const reportsQuery = useGeneratedReports(false, page, historyFilters);
  const generateReportMutation = useGenerateReport();
  const reports = reportsQuery.data?.items || [];
  const selectedReports = reports.filter((report) => selectedReportIds.includes(report.id));
  const allSelected = reports.length > 0 && reports.every((report) => selectedReportIds.includes(report.id));

  useEffect(() => {
    if (!options?.periods.length || filters.period) return;
    const next = new URLSearchParams(params);
    next.set('period', options.periods[0].key);
    setParams(next, { replace: true });
  }, [filters.period, options?.periods, params, setParams]);

  const setReportFilters = (changes: Partial<ReportCenterFilters>) => {
    const next = new URLSearchParams(params);
    (Object.entries(changes) as Array<[keyof ReportCenterFilters, string | undefined]>).forEach(([key, value]) => {
      if (value) next.set(key, value); else next.delete(key);
    });

    const selectedPeriod = next.get('period');
    if (selectedPeriod && next.get('comparison_period') === selectedPeriod) next.delete('comparison_period');

    const selectedEmployeeId = next.get('employee_id');
    const selectedEmployee = selectedEmployeeId
      ? options?.employees.find((employee) => employee.id === selectedEmployeeId)
      : undefined;
    if (selectedEmployee && (
      (next.get('region') && next.get('region') !== selectedEmployee.region)
      || (next.get('team') && next.get('team') !== selectedEmployee.team)
      || (next.get('performance_level') && next.get('performance_level') !== selectedEmployee.performance_level)
      || (next.get('position') && next.get('position') !== selectedEmployee.position)
    )) {
      next.delete('employee_id');
    }

    setParams(next, { replace: true });
  };

  const updateFilter = (key: keyof ReportCenterFilters, value: string) => {
    setReportFilters({ [key]: value });
  };

  const resetFilters = () => {
    const next = new URLSearchParams();
    if (options?.periods[0]?.key) next.set('period', options.periods[0].key);
    setParams(next, { replace: true });
  };

  const updateHistoryFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    const paramKey = `history_${key}`;
    if (value) next.set(paramKey, value); else next.delete(paramKey);
    setPage(1);
    setParams(next, { replace: true });
  };

  const makeConfiguration = (template: ReportTemplate): ReportConfiguration | null => {
    const period = options?.periods.find((item) => item.key === filters.period) || options?.periods[0];
    if (!period) return null;
    const comparisonPeriod = filters.comparison_period
      ? options?.periods.find((item) => item.key === filters.comparison_period)
      : undefined;
    const selectedEmployeeName = filters.employee_id
      ? options?.employees.find((employee) => employee.id === filters.employee_id)?.name || filters.employee_id
      : null;
    const activeScope = [
      filters.region ? `Region ${filters.region}` : null,
      filters.team || (template.type === 'team_marketing' ? 'Marketing' : null),
      filters.performance_level ? `Level ${filters.performance_level}` : null,
      filters.position ? `Position ${filters.position}` : null,
      selectedEmployeeName ? `Employee ${selectedEmployeeName}` : null,
      filters.grade ? `Grade ${filters.grade}` : null,
      filters.status ? `Status ${filters.status}` : null,
      filters.kpi ? `KPI ${filters.kpi}` : null,
    ].filter(Boolean);
    return {
      report_type: template.type,
      report_name: `${period.month} ${period.year} - ${template.name}${activeScope.length ? ` - ${activeScope.join(', ')}` : ''}`,
      start_month: period.month,
      start_year: period.year,
      end_month: null,
      end_year: null,
      comparison_month: comparisonPeriod?.month || null,
      comparison_year: comparisonPeriod?.year || null,
      region: filters.region || (template.type === 'monthly_uae' || template.type === 'uae_executive_summary' ? 'UAE' : template.type === 'monthly_egypt' ? 'EGY' : null),
      team: filters.team || (template.type === 'team_marketing' ? 'Marketing' : null),
      position: filters.position || null,
      performance_level: filters.performance_level || null,
      employee_id: filters.employee_id || null,
      grade: filters.grade || null,
      status: filters.status || null,
      kpi: filters.kpi || null,
      included_sections: template.sections,
      output_format: 'pptx',
    };
  };

  const templateScopeLabel = (template: ReportTemplate) => {
    const configuration = makeConfiguration(template);
    if (!configuration) return 'Choose a reporting period';
    const selectedEmployeeName = configuration.employee_id
      ? options?.employees.find((employee) => employee.id === configuration.employee_id)?.name || configuration.employee_id
      : null;
    const scope = [
      `${configuration.start_month} ${configuration.start_year}`,
      configuration.region ? `Region ${configuration.region}` : null,
      configuration.team ? `Team ${configuration.team}` : 'All teams',
      configuration.performance_level ? `Level ${configuration.performance_level}` : null,
      configuration.position ? `Position ${configuration.position}` : null,
      selectedEmployeeName ? `Employee ${selectedEmployeeName}` : null,
      configuration.grade ? `Grade ${configuration.grade}` : null,
      configuration.status ? `Status ${configuration.status}` : null,
      configuration.kpi ? `KPI ${configuration.kpi}` : null,
      configuration.comparison_month && configuration.comparison_year
        ? `Compare ${configuration.comparison_month} ${configuration.comparison_year}`
        : null,
    ].filter(Boolean);
    return scope.join(' / ');
  };

  const downloadReport = async (report: GeneratedReport) => {
    setDownloadError(null);
    setMessage(null);
    setDownloadingId(report.id);
    try {
      const response = await fetchWithRole(`${API_BASE}${report.download_url}`);
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || 'Unable to download this report.');
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = report.file_name;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setMessage(`${report.name} downloaded successfully.`);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : 'Unable to download this report.');
    } finally {
      setDownloadingId(null);
    }
  };

  const toggleSelection = (id: string) => setSelectedReportIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  const toggleAll = () => setSelectedReportIds(allSelected ? [] : reports.map((report) => report.id));

  if (templatesQuery.isLoading || optionsQuery.isLoading || !options) return <PageLoadingSkeleton variant="table" label="Preparing reports" />;
  if (templatesQuery.error || optionsQuery.error) return <div role="alert" className="mx-auto mt-12 max-w-xl rounded-2xl border border-red-500/20 bg-red-500/10 p-6 text-center text-red-600"><AlertCircle className="mx-auto mb-3" /><p className="font-extrabold">Unable to load reports</p></div>;

  const renderPage = () => {
    const canExport = options.can_export;
    const allowedFormats = options.allowed_formats ?? [];
    const canGeneratePptx = canExport && (allowedFormats.length === 0 || allowedFormats.includes('pptx'));
    const generateDirectPptx = async (template: ReportTemplate) => {
      if (!canGeneratePptx || generatingTemplateType) return;
      const configuration = makeConfiguration(template);
      if (!configuration) {
        setDownloadError('Choose a reporting period before generating a PowerPoint.');
        return;
      }
      setDownloadError(null);
      setMessage(null);
      setGeneratingTemplateType(template.type);
      try {
        const report = await generateReportMutation.mutateAsync(configuration);
        setMessage(`${report.name} generated as a PowerPoint. Download it from history.`);
        await reportsQuery.refetch();
      } catch (error) {
        setDownloadError(error instanceof Error ? error.message : 'Unable to generate this PowerPoint report.');
      } finally {
        setGeneratingTemplateType(null);
      }
    };
    return (
      <div className="app-page-shell rf-page rf-page--reports space-y-5">
        {downloadError && <div role="alert" className="flex items-center gap-2 rounded-xl bg-red-500/10 px-4 py-3 text-sm font-semibold text-red-600"><AlertCircle size={17} /> {downloadError}</div>}
        {message && <div role="status" className="flex items-center gap-2 rounded-xl bg-emerald-500/10 px-4 py-3 text-sm font-semibold text-emerald-700 dark:text-emerald-300"><CheckCircle2 size={17} /> {message}</div>}
        <ReportsCenterWorkspace
          role={role}
          filters={filters}
          options={options}
          isFetching={Boolean(reportsQuery.isFetching || optionsQuery.isFetching || templatesQuery.isFetching)}
          onFilterChange={updateFilter}
          onApplyQuickFilter={setReportFilters}
          onResetFilters={resetFilters}
          onRefresh={() => { optionsQuery.refetch(); templatesQuery.refetch(); reportsQuery.refetch(); }}
          templates={templates}
          templateScopeLabel={templateScopeLabel}
          onGenerateTemplate={generateDirectPptx}
          generatingTemplateType={generatingTemplateType}
        />

        <section className="rf-data-panel rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm">
          <div className="flex flex-col gap-3 border-b border-[var(--border-light)] px-5 py-4 lg:flex-row lg:items-end lg:justify-between"><div><h2 className="font-extrabold text-[var(--text-primary)]">Generated report history</h2><p className="mt-1 text-xs text-[var(--text-muted)]">Generated PowerPoint files stay here until you explicitly download or delete them.</p></div><div className="flex flex-wrap gap-2"><input aria-label="Search generated reports" value={historyFilters.search || ''} onChange={(event) => updateHistoryFilter('search', event.target.value)} placeholder="Search history" className="min-h-10 rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 text-sm" /><select aria-label="History report type" value={historyFilters.report_type || ''} onChange={(event) => updateHistoryFilter('report_type', event.target.value)} className="min-h-10 rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 text-sm"><option value="">All report types</option>{Array.from(new Set(templates.map((template) => template.type))).map((type) => <option key={type} value={type}>{type}</option>)}</select><select aria-label="History period" value={historyFilters.period || ''} onChange={(event) => updateHistoryFilter('period', event.target.value)} className="min-h-10 rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 text-sm"><option value="">All periods</option>{options.periods.map((period) => <option key={period.key} value={`${period.month} ${period.year}`}>{period.month} {period.year}</option>)}</select><select aria-label="History status" value={historyFilters.status || ''} onChange={(event) => updateHistoryFilter('status', event.target.value)} className="min-h-10 rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 text-sm"><option value="">All statuses</option><option value="ready">Ready</option><option value="failed">Failed</option></select><button type="button" onClick={() => reportsQuery.refetch()} aria-label="Refresh reports" className="min-h-10 min-w-10 rounded-xl border border-[var(--border-light)] text-[var(--text-muted)] hover:text-blue-600"><RefreshCw size={16} className={`mx-auto ${reportsQuery.isFetching ? 'animate-spin' : ''}`} /></button></div></div>
          {!canExport && <div role="status" className="border-b border-[var(--border-light)] bg-amber-500/10 px-5 py-3 text-sm font-semibold text-amber-700 dark:text-amber-300">Preview only - your role cannot generate, download, or delete files.</div>}
          <div className="overflow-x-auto"><table className="min-w-[900px] w-full text-left text-sm"><thead className="bg-[var(--bg-sunken)]/70 text-[10px] font-extrabold uppercase tracking-wider text-[var(--text-faint)]"><tr><th className="w-12 px-5 py-3">{canExport && <input type="checkbox" aria-label="Select all reports on this page" checked={allSelected} onChange={toggleAll} disabled={!reports.length} className="h-4 w-4 rounded border-[var(--border-medium)] text-blue-600" />}</th><th className="px-5 py-3">Report name</th><th className="px-4 py-3">Type</th><th className="px-4 py-3">Period</th><th className="px-4 py-3">Created at</th><th className="px-4 py-3">Format</th><th className="px-5 py-3 text-right">Actions</th></tr></thead><tbody>{reports.map((report) => { const meta = formatMeta(report.format); const FormatIcon = meta.icon; return <tr key={report.id} className="border-t border-[var(--border-light)] text-[var(--text-secondary)]"><td className="px-5 py-4">{canExport && <input type="checkbox" aria-label={`Select ${report.name}`} checked={selectedReportIds.includes(report.id)} onChange={() => toggleSelection(report.id)} className="h-4 w-4 rounded border-[var(--border-medium)] text-blue-600" />}</td><td className="px-5 py-4 font-bold text-[var(--text-primary)]">{report.name}</td><td className="px-4 py-4">{report.report_type}</td><td className="px-4 py-4 whitespace-nowrap">{report.period}</td><td className="px-4 py-4 whitespace-nowrap">{formatDate(report.created_at)}</td><td className="px-4 py-4"><span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-1 text-xs font-bold text-emerald-700 dark:text-emerald-300"><FormatIcon size={13} /> {meta.label}</span></td><td className="px-5 py-4"><div className="flex justify-end gap-2">{canExport && <button type="button" aria-label={`Download ${report.name}`} onClick={() => downloadReport(report)} disabled={downloadingId === report.id} className="flex min-h-9 min-w-9 items-center justify-center rounded-lg border border-[var(--border-light)] text-blue-600 disabled:opacity-50">{downloadingId === report.id ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}</button>}{canExport && <button type="button" aria-label={`Delete ${report.name}`} onClick={() => setDeleteCandidate(report)} className="flex min-h-9 min-w-9 items-center justify-center rounded-lg border border-rose-500/20 text-rose-600"><Trash2 size={15} /></button>}</div></td></tr>; })}{!reportsQuery.isLoading && reports.length === 0 && <tr><td colSpan={7} className="px-5 py-12 text-center text-sm text-[var(--text-muted)]">No generated reports yet.</td></tr>}</tbody></table></div>
          {selectedReports.length > 0 && canExport && <div className="flex justify-end border-t border-[var(--border-light)] px-5 py-3"><button type="button" onClick={() => setDeleteCandidates(selectedReports)} className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-rose-500/20 px-3 text-xs font-extrabold text-rose-600"><Trash2 size={15} /> Delete {selectedReports.length} selected report{selectedReports.length === 1 ? '' : 's'}</button></div>}
          {(reportsQuery.data?.total || 0) > 10 && <div className="flex items-center justify-end gap-2 border-t border-[var(--border-light)] px-5 py-3"><button disabled={page === 1} onClick={() => { setSelectedReportIds([]); setPage((value) => Math.max(1, value - 1)); }} className="rounded-lg border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:opacity-40">Previous</button><span className="text-xs text-[var(--text-muted)]">Page {page}</span><button disabled={page * 10 >= (reportsQuery.data?.total || 0)} onClick={() => { setSelectedReportIds([]); setPage((value) => value + 1); }} className="rounded-lg border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:opacity-40">Next</button></div>}
        </section>

        {deleteCandidate && <DeleteReportModal report={deleteCandidate} onCancel={() => setDeleteCandidate(null)} onDeleted={(report) => { setDeleteCandidate(null); setSelectedReportIds((current) => current.filter((id) => id !== report.id)); setMessage(`${report.name} deleted successfully.`); reportsQuery.refetch(); }} />}
        {deleteCandidates && <DeleteReportsModal reports={deleteCandidates} onCancel={() => setDeleteCandidates(null)} onDeleted={(deleted) => { setDeleteCandidates(null); setSelectedReportIds([]); setMessage(`${deleted.length} reports deleted successfully.`); reportsQuery.refetch(); }} />}
      </div>
    );
  };

  return renderPage();
}
