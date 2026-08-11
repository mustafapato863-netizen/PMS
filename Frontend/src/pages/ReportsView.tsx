import { useState } from 'react';
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  Download,
  FileBarChart,
  Loader2,
  RefreshCw,
  Sparkles,
  Presentation,
  Trash2,
  UsersRound,
} from 'lucide-react';
import { API_BASE } from '../config';
import OverlayPortal from '../components/common/OverlayPortal';
import { PageLoadingSkeleton } from '../components/common/SkeletonLoader';
import { useUserRole } from '../context/RoleContext';
import type { GeneratedReport, ReportConfiguration, ReportTemplate } from '../features/reports/types';
import {
  useGeneratedReports,
  useDeleteGeneratedReport,
  useReportOptions,
  useReportTemplates,
} from '../hooks/api/useReports';
import { waitForProcessingJob } from '../hooks/api/useProcessingJobs';

const TEMPLATE_ICON: Record<string, typeof FileBarChart> = {
  monthly_uae: Building2,
  monthly_egypt: Building2,
  team_marketing: UsersRound,
};

const FORMAT_META: Record<string, { label: string; icon: typeof Presentation }> = {
  pptx: { label: 'PPTX', icon: Presentation },
  pdf: { label: 'PDF', icon: FileBarChart },
};

function normalizeOutputFormat(value?: string | null): string {
  if (value === 'pptx') return 'pptx';
  return 'pdf';
}

function formatDate(value: string) {
  if (!value) return 'N/A';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
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
  const removeReport = useDeleteGeneratedReport();
  const confirmDelete = async () => {
    try {
      await removeReport.mutateAsync(report.id);
      onDeleted(report);
    } catch {
      // The mutation error is rendered in the confirmation dialog.
    }
  };

  return (
    <OverlayPortal>
      <div
        className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget && !removeReport.isPending) onCancel();
        }}
      >
        <section
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="delete-generated-report-title"
          aria-describedby="delete-generated-report-description"
          className="w-full max-w-lg rounded-3xl border border-rose-500/20 bg-[var(--bg-surface)] p-6 shadow-2xl"
        >
          <div className="flex items-start gap-4">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-rose-500/10 text-rose-600">
              <Trash2 size={19} />
            </span>
            <div>
              <h2 id="delete-generated-report-title" className="text-xl font-extrabold text-[var(--text-primary)]">Delete this report?</h2>
              <p id="delete-generated-report-description" className="mt-2 text-sm leading-6 text-[var(--text-muted)]">
                <strong>{report.name}</strong> and its generated {report.format.toUpperCase()} file will be permanently removed.
              </p>
            </div>
          </div>
          {removeReport.error && (
            <p role="alert" className="mt-4 rounded-xl bg-rose-500/10 p-3 text-sm font-bold text-rose-600">
              {removeReport.error instanceof Error ? removeReport.error.message : 'Unable to delete this report.'}
            </p>
          )}
          <div className="mt-6 flex justify-end gap-2">
            <button type="button" onClick={onCancel} disabled={removeReport.isPending} className="min-h-11 rounded-xl border border-[var(--border-light)] px-4 font-bold text-[var(--text-secondary)] disabled:opacity-60">Cancel</button>
            <button type="button" onClick={confirmDelete} disabled={removeReport.isPending} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-rose-600 px-5 font-bold text-white hover:bg-rose-700 disabled:opacity-60">
              {removeReport.isPending ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
              Delete report
            </button>
          </div>
        </section>
      </div>
    </OverlayPortal>
  );
}

export default function ReportsView() {
  const { fetchWithRole } = useUserRole();
  const templatesQuery = useReportTemplates();
  const optionsQuery = useReportOptions();
  const [page, setPage] = useState(1);
  const reportsQuery = useGeneratedReports(false, page);
  const [periodKey, setPeriodKey] = useState('');
  
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [generatingType, setGeneratingType] = useState<string | null>(null);
  const [downloadSuccess, setDownloadSuccess] = useState<string | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<GeneratedReport | null>(null);

  const templates = templatesQuery.data || [];
  const options = optionsQuery.data;
  const effectivePeriodKey = periodKey || options?.periods[0]?.key || '';

  const generateDirectly = async (template: ReportTemplate) => {
    if (!options) return;
    const period = options.periods.find((item) => item.key === effectivePeriodKey) || options.periods[0];
    if (!period) return;
    
    setDownloadError(null);
    setDownloadSuccess(null);
    setGeneratingType(template.type);
    
    const configuration: ReportConfiguration = {
      report_type: template.type,
      report_name: `${period.month} ${period.year} - ${template.name}`,
      start_month: period.month,
      start_year: period.year,
      end_month: null,
      end_year: null,
      region: template.type === 'monthly_uae' ? 'UAE' : template.type === 'monthly_egypt' ? 'Egypt' : null,
      team: template.type === 'team_marketing' ? 'Marketing' : null,
      position: null,
      performance_level: null,
      employee_id: null,
      grade: null,
      status: null,
      included_sections: template.sections,
      output_format: template.type === 'team_marketing' ? 'pptx' : 'pdf',
    };

    try {
      const response = await fetchWithRole(`${API_BASE}/api/reports/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(configuration),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || 'Failed to generate report');
      }

      const responseBody = await response.json();
      let generatedReport = responseBody.data as GeneratedReport;
      if (generatedReport && typeof (generatedReport as GeneratedReport & { job_id?: unknown }).job_id === 'string') {
        const job = await waitForProcessingJob((generatedReport as GeneratedReport & { job_id: string }).job_id, (state) => {
          if (state.status === 'queued' || state.status === 'running') {
            setDownloadSuccess(`Report ${state.status} (${state.progress}%).`);
          }
        });
        if (job.status !== 'succeeded' || !job.result) {
          throw new Error(job.error?.message || 'Report generation failed.');
        }
        generatedReport = job.result as unknown as GeneratedReport;
      }
      reportsQuery.refetch();
      
      // Auto download
      await downloadReport(generatedReport);
      
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : 'An error occurred during generation.');
    } finally {
      setGeneratingType(null);
    }
  };

  const downloadReport = async (report: GeneratedReport) => {
    setDownloadError(null);
    setDownloadSuccess(null);
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
      setDownloadSuccess(`${report.name} downloaded successfully.`);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : 'Unable to download this report.');
    } finally {
      setDownloadingId(null);
    }
  };

  if (templatesQuery.isLoading || optionsQuery.isLoading) {
    return <PageLoadingSkeleton variant="table" label="Preparing reports" />;
  }

  if (templatesQuery.error || optionsQuery.error || !options) {
    return (
      <div role="alert" className="mx-auto mt-12 max-w-xl rounded-2xl border border-red-500/20 bg-red-500/10 p-6 text-center text-red-600">
        <AlertCircle className="mx-auto mb-3" />
        <p className="font-extrabold">Unable to load reports</p>
      </div>
    );
  }

  return (
      <div className="app-page-shell">
      <section className="rounded-3xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5 shadow-sm md:p-7">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="flex items-center gap-2 text-blue-600"><Sparkles size={16} /><span className="text-[10px] font-extrabold uppercase tracking-[0.18em]">Automated Reports</span></div>
            <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-[var(--text-primary)]">Report Builder</h1>
            <p className="mt-1 text-sm text-[var(--text-muted)] mb-4">Click on any report below to generate and download it instantly.</p>
          </div>
          <div className="w-full xl:w-64">
            <label htmlFor="reporting-period" className="block text-sm font-bold text-[var(--text-secondary)] mb-2">Select Reporting Period</label>
            <div className="relative">
              <select
                id="reporting-period"
                value={effectivePeriodKey} 
                onChange={(e) => setPeriodKey(e.target.value)} 
                className="w-full min-h-11 rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] pl-3 pr-9 text-sm font-semibold outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 appearance-none"
              >
                {options.periods.map((period) => (
                  <option key={period.key} value={period.key}>{period.month} {period.year}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </section>

      {downloadError && <div role="alert" className="flex items-center gap-2 rounded-xl bg-red-500/10 px-4 py-3 text-sm font-semibold text-red-600"><AlertCircle size={17} /> {downloadError}</div>}
      {downloadSuccess && <div role="status" className="flex items-center gap-2 rounded-xl bg-emerald-500/10 px-4 py-3 text-sm font-semibold text-emerald-700 dark:text-emerald-300"><CheckCircle2 size={17} /> {downloadSuccess}</div>}
      {!options.can_export && <div role="status" className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm font-semibold text-amber-700 dark:text-amber-300">Preview only — your role cannot generate or download reports.</div>}

      <div className="grid gap-4 sm:gap-6 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
        {templates.map((template) => {
          const Icon = TEMPLATE_ICON[template.type] || FileBarChart;
          const isGenerating = generatingType === template.type;
          return (
            <article key={template.type} className="group flex flex-col rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-6 shadow-sm transition-all hover:-translate-y-1 hover:border-blue-500/30 hover:shadow-lg">
              <div className="flex items-start justify-between gap-4">
                <span className="rounded-xl p-3 bg-blue-500/10 text-blue-600"><Icon size={24} /></span>
                <span className="flex gap-1">
                  {template.formats.map((format) => {
                    const meta = FORMAT_META[normalizeOutputFormat(format)] || FORMAT_META.pdf;
                    const FormatIcon = meta.icon;
                    return (
                      <span key={format} className="inline-flex items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-[10px] font-extrabold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
                        <FormatIcon size={11} /> {meta.label}
                      </span>
                    );
                  })}
                </span>
              </div>
              <h3 className="mt-5 text-lg font-extrabold text-[var(--text-primary)]">{template.name}</h3>
              <p className="mt-2 mb-6 flex-1 text-sm leading-6 text-[var(--text-muted)]">{template.description}</p>
              
              <button 
                onClick={() => generateDirectly(template)}
                disabled={isGenerating || !options.can_export}
                className="w-full inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-bold text-white transition-colors hover:bg-blue-700 disabled:opacity-70"
              >
                {isGenerating ? <><Loader2 size={18} className="animate-spin" /> Generating...</> : options.can_export ? 'Generate Report' : 'Preview only'}
              </button>
            </article>
          );
        })}
      </div>

      <section className="mt-8 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm">
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border-light)] px-5 py-4">
          <div><h2 className="font-extrabold text-[var(--text-primary)]">Recent Reports</h2><p className="mt-1 text-xs text-[var(--text-muted)]">History of generated reports.</p></div>
          <button type="button" onClick={() => reportsQuery.refetch()} aria-label="Refresh reports" className="min-h-10 min-w-10 rounded-xl border border-[var(--border-light)] text-[var(--text-muted)] hover:text-blue-600"><RefreshCw size={16} className={`mx-auto ${reportsQuery.isFetching ? 'animate-spin' : ''}`} /></button>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[900px] w-full text-left text-sm">
            <thead className="bg-[var(--bg-sunken)]/70 text-[10px] font-extrabold uppercase tracking-wider text-[var(--text-faint)]"><tr><th className="px-5 py-3">Report name</th><th className="px-4 py-3">Type</th><th className="px-4 py-3">Period</th><th className="px-4 py-3">Created at</th><th className="px-4 py-3">Format</th><th className="px-5 py-3 text-right">Actions</th></tr></thead>
            <tbody>
              {reportsQuery.data?.items.map((report) => {
                const reportFormat = report.format === 'pdf' || report.format === 'pptx' ? report.format : 'pdf';
                const FormatIcon = FORMAT_META[reportFormat]?.icon || FileBarChart;
                return (
                  <tr key={report.id} className="border-t border-[var(--border-light)] text-[var(--text-secondary)]">
                    <td className="px-5 py-4 font-bold text-[var(--text-primary)]">{report.name}</td>
                    <td className="px-4 py-4">{report.report_type}</td>
                    <td className="px-4 py-4 whitespace-nowrap">{report.period}</td>
                    <td className="px-4 py-4 whitespace-nowrap">{formatDate(report.created_at)}</td>
                    <td className="px-4 py-4">
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-1 text-xs font-bold text-emerald-700 dark:text-emerald-300">
                        <FormatIcon size={13} /> {FORMAT_META[reportFormat]?.label}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex justify-end gap-2">
                        <button type="button" aria-label={`Download ${report.name}`} onClick={() => downloadReport(report)} disabled={downloadingId === report.id} className="min-h-9 min-w-9 rounded-lg border border-[var(--border-light)] text-blue-600 disabled:opacity-50 flex items-center justify-center">
                          {downloadingId === report.id ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
                        </button>
                        {options.can_export && (
                          <button type="button" aria-label={`Delete ${report.name}`} onClick={() => setDeleteCandidate(report)} className="flex min-h-9 min-w-9 items-center justify-center rounded-lg border border-rose-500/20 text-rose-600 hover:bg-rose-500/10">
                            <Trash2 size={15} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {!reportsQuery.isLoading && !reportsQuery.data?.items.length && <tr><td colSpan={6} className="px-5 py-12 text-center text-sm text-[var(--text-muted)]">No generated reports yet.</td></tr>}
            </tbody>
          </table>
        </div>
        {(reportsQuery.data?.total || 0) > 10 && <div className="flex items-center justify-end gap-2 border-t border-[var(--border-light)] px-5 py-3"><button disabled={page === 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="rounded-lg border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:opacity-40">Previous</button><span className="text-xs text-[var(--text-muted)]">Page {page}</span><button disabled={page * 10 >= (reportsQuery.data?.total || 0)} onClick={() => setPage((value) => value + 1)} className="rounded-lg border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:opacity-40">Next</button></div>}
      </section>
      {deleteCandidate && (
        <DeleteReportModal
          report={deleteCandidate}
          onCancel={() => setDeleteCandidate(null)}
          onDeleted={(report) => {
            setDeleteCandidate(null);
            setDownloadSuccess(`${report.name} deleted successfully.`);
            if ((reportsQuery.data?.items.length || 0) === 1 && page > 1) setPage((value) => value - 1);
          }}
        />
      )}
    </div>
  );
}
