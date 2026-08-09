import { useMemo, useState } from 'react';
import {
  AlertCircle, ArrowRight, Building2, Check, CheckCircle2, FileBarChart,
  FileSpreadsheet, LayoutTemplate, LoaderCircle, RefreshCw, ShieldCheck,
  Sparkles, UserRound, UsersRound, X,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useCreateStoryDraft, useReportOptions, useStoryTemplates } from '../../../hooks/api/useReports';
import { useReportBuilderStore } from '../../../store/reportBuilderStore';
import type { StoryTemplate } from '../../../features/reports/types';
import { PageLoadingSkeleton } from '../../common/SkeletonLoader';

const TEMPLATE_ICON: Record<string, typeof FileBarChart> = {
  executive: Building2, team: UsersRound, position: ShieldCheck, employee: UserRound,
  corrective_actions: CheckCircle2, data_quality: FileSpreadsheet,
};

export default function Step2Template() {
  const navigate = useNavigate();
  const { data: templates, isLoading, error, refetch } = useStoryTemplates();
  const { data: options } = useReportOptions();
  const createDraft = useCreateStoryDraft();
  const { configuration, activeTemplate, setTemplate, loadDraft } = useReportBuilderStore();
  const [preview, setPreview] = useState<StoryTemplate | null | undefined>(undefined);

  const scopedTeamCount = useMemo(() => {
    if (configuration.team) return 1;
    const teams = new Set(
      (options?.employees || [])
        .filter((employee) => !configuration.region || employee.region === configuration.region)
        .map((employee) => employee.team)
        .filter(Boolean),
    );
    return Math.max(teams.size, 1);
  }, [configuration.region, configuration.team, options?.employees]);

  const estimatedPages = (template: StoryTemplate | null) => {
    if (!template) return 1;
    const metadata = template.definition.story_metadata;
    if (!metadata?.pages_per_team) return template.page_count;
    return metadata.fixed_page_count + metadata.pages_per_team * scopedTeamCount;
  };

  const create = async (template: StoryTemplate | null) => {
    if (!configuration.report_name || !configuration.start_month || !configuration.start_year) return;
    setTemplate(template);
    const draft = await createDraft.mutateAsync({
      name: configuration.report_name,
      report_type: template?.report_type || 'executive',
      template_id: template?.id || null,
      primary_period: { month: configuration.start_month, year: configuration.start_year },
      comparison_period: configuration.end_month && configuration.end_year ? { month: configuration.end_month, year: configuration.end_year } : null,
      scope: {
        region: configuration.region || null, team: configuration.team || null,
        position: configuration.position || null, performance_level: configuration.performance_level || null,
        employee_id: configuration.employee_id || null, grade: configuration.grade || null, status: configuration.status || null,
      },
    });
    loadDraft(draft, template);
    navigate(`/reports/${draft.id}/edit`, { replace: true });
  };

  if (isLoading) return <PageLoadingSkeleton variant="builder" label="Loading report templates" compact />;
  if (error || !templates) return <div role="alert" className="mx-auto mt-12 max-w-xl rounded-2xl border border-red-500/20 bg-red-500/10 p-6 text-center text-red-600"><AlertCircle className="mx-auto mb-3" /><p className="font-extrabold">Unable to load templates</p><p className="mt-2 text-sm">{error?.message || 'The template service did not return a valid response.'}</p><button type="button" onClick={() => void refetch()} className="mx-auto mt-5 inline-flex min-h-10 items-center gap-2 rounded-xl border border-red-500/25 bg-[var(--bg-surface)] px-4 text-sm font-bold text-red-600 hover:bg-red-500/5"><RefreshCw size={15} />Try again</button></div>;

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-8">
        <h2 className="text-2xl font-extrabold text-[var(--text-primary)]">Choose the management story</h2>
        <p className="mt-1 text-[var(--text-muted)]">Preview the story first, then generate a complete editable report from authorized PMS data.</p>
      </div>
      {createDraft.error && <div role="alert" className="mb-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">{createDraft.error.message}</div>}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
        {templates.map((template) => {
          const Icon = TEMPLATE_ICON[template.report_type] || FileBarChart;
          const selected = activeTemplate?.id === template.id;
          const metadata = template.definition.story_metadata;
          return <article key={template.id} className={`relative flex min-h-72 flex-col rounded-2xl border-2 bg-[var(--bg-surface)] p-6 text-left transition hover:-translate-y-0.5 hover:border-blue-400 hover:shadow-lg ${selected ? 'border-blue-600 ring-4 ring-blue-600/10' : 'border-[var(--border-light)]'}`}>
            <div className="mb-5 flex items-start justify-between gap-3">
              <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-50 text-blue-600 dark:bg-blue-950/40"><Icon /></span>
              <div className="flex flex-wrap justify-end gap-2">
                {metadata?.recommended && <span className="rounded-full bg-blue-600 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wide text-white">Recommended</span>}
                {metadata?.mode && metadata.mode !== 'standard' && <span className="rounded-full bg-[var(--bg-sunken)] px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wide text-[var(--text-secondary)]">{metadata.mode}</span>}
              </div>
            </div>
            <h3 className="text-lg font-extrabold text-[var(--text-primary)]">{template.name}</h3>
            <p className="mt-2 flex-1 text-sm leading-6 text-[var(--text-muted)]">{template.description}</p>
            <div className="mt-4 rounded-xl bg-[var(--bg-sunken)] p-3 text-xs text-[var(--text-secondary)]">
              <div className="flex items-center justify-between font-bold"><span>Estimated story</span><span>{estimatedPages(template)} pages</span></div>
              {metadata?.pages_per_team ? <p className="mt-1 text-[11px] text-[var(--text-muted)]">Includes one filtered page for each team with data.</p> : null}
            </div>
            <button type="button" onClick={() => setPreview(template)} className="mt-4 inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-blue-500/25 bg-blue-50 px-4 text-sm font-extrabold text-blue-700 transition hover:bg-blue-100 dark:bg-blue-950/30 dark:text-blue-300">
              Preview story <ArrowRight size={16} />
            </button>
          </article>;
        })}
        <article className="flex min-h-72 flex-col rounded-2xl border-2 border-dashed border-[var(--border-medium)] bg-[var(--bg-surface)] p-6 text-left">
          <span className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--bg-sunken)] text-[var(--text-secondary)]"><LayoutTemplate /></span>
          <h3 className="text-lg font-extrabold text-[var(--text-primary)]">Blank Report</h3>
          <p className="mt-2 flex-1 text-sm leading-6 text-[var(--text-muted)]">Start empty only when none of the governed management stories fits your purpose.</p>
          <button type="button" onClick={() => setPreview(null)} className="mt-4 min-h-11 rounded-xl border border-[var(--border-medium)] px-4 text-sm font-extrabold text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)]">Review blank report</button>
        </article>
      </div>

      {preview !== undefined && <div role="dialog" aria-modal="true" aria-labelledby="template-preview-title" className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm">
        <div className="w-full max-w-2xl overflow-hidden rounded-3xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-2xl">
          <header className="flex items-start justify-between border-b border-[var(--border-light)] p-6">
            <div><div className="mb-2 flex items-center gap-2 text-xs font-extrabold uppercase tracking-wide text-blue-600"><Sparkles size={15} />Story preview</div><h3 id="template-preview-title" className="text-2xl font-black text-[var(--text-primary)]">{preview?.name || 'Blank Report'}</h3><p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">{preview?.description || 'An empty page ready for governed PMS blocks.'}</p></div>
            <button type="button" onClick={() => setPreview(undefined)} className="rounded-xl p-2 text-[var(--text-muted)] hover:bg-[var(--bg-sunken)]" aria-label="Close template preview"><X /></button>
          </header>
          <div className="p-6">
            <div className="mb-5 flex items-center justify-between rounded-2xl border border-blue-500/15 bg-blue-50/70 p-4 dark:bg-blue-950/20"><div><p className="text-xs font-bold uppercase text-[var(--text-muted)]">Generated for this scope</p><p className="mt-1 text-2xl font-black text-[var(--text-primary)]">{estimatedPages(preview)} pages</p></div><p className="max-w-xs text-right text-xs leading-5 text-[var(--text-muted)]">Exact team pages use authorized teams with data in {configuration.start_month} {configuration.start_year}.</p></div>
            <ol className="grid gap-2 sm:grid-cols-2">
              {(preview?.definition.story_metadata?.outline || ['Empty report page']).map((item, index) => <li key={item} className="flex items-center gap-3 rounded-xl bg-[var(--bg-sunken)] p-3 text-sm font-bold text-[var(--text-secondary)]"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-blue-600 text-xs text-white">{index + 1}</span>{item}</li>)}
            </ol>
          </div>
          <footer className="flex items-center justify-between gap-3 border-t border-[var(--border-light)] p-5">
            <span className="flex items-center gap-2 text-xs font-semibold text-[var(--text-muted)]"><Check size={15} className="text-emerald-600" />Every page remains editable after generation.</span>
            <button type="button" disabled={createDraft.isPending} onClick={() => void create(preview)} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-blue-600 px-5 text-sm font-extrabold text-white shadow-lg shadow-blue-600/20 hover:bg-blue-700 disabled:opacity-60">
              {createDraft.isPending ? <><LoaderCircle size={16} className="animate-spin" />Generating story</> : <>Use Template <ArrowRight size={16} /></>}
            </button>
          </footer>
        </div>
      </div>}
    </div>
  );
}
