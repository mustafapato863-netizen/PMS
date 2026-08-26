import './PageEnhancements.css';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AlertCircle, ArrowLeft, ChevronLeft, ChevronRight, CheckCircle2, Loader2 } from 'lucide-react';
import BlockRenderer from '../components/reports/builder/BlockRenderer';
import { PanelLoadingSkeleton } from '../components/common/SkeletonLoader';
import { useUserRole } from '../context/RoleContext';
import { useStoryDraft, useStoryPage } from '../hooks/api/useReports';

export default function ReportPreviewView() {
  const { reportId } = useParams();
  const navigate = useNavigate();
  const { role } = useUserRole();
  const { data: draft, isLoading, error } = useStoryDraft(reportId);
  const [pageIndex, setPageIndex] = useState(0);
  const pages = draft?.definition.slides || [];
  const activePage = pages[pageIndex];
  const { data: pageData, isLoading: pageLoading, isFetching } = useStoryPage(reportId, activePage?.id);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'ArrowLeft') setPageIndex((value) => Math.max(0, value - 1));
      if (event.key === 'ArrowRight') setPageIndex((value) => Math.min(Math.max(pages.length - 1, 0), value + 1));
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [pages.length]);

  if (isLoading) return <PanelLoadingSkeleton rows={6} label="Loading report preview" />;
  if (error || !draft) return <div role="alert" className="m-8 rounded-2xl border border-rose-500/20 bg-rose-500/10 p-6 text-rose-700 dark:text-rose-300"><div className="flex items-center gap-2 font-extrabold"><AlertCircle size={18} /> Unable to load this report preview.</div><p className="mt-2 text-sm">{error instanceof Error ? error.message : 'The report draft was not found or is outside your authorized scope.'}</p><button type="button" onClick={() => navigate('/reports')} className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-xl border border-current px-4 text-sm font-bold"><ArrowLeft size={15} /> Back to Reports Center</button></div>;

  return (
    <div className="app-page-shell rf-page rf-page--report-preview space-y-5">
      <header className="rf-page-hero rounded-3xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5 shadow-sm md:p-7">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div><button type="button" onClick={() => navigate('/reports')} className="inline-flex items-center gap-2 text-xs font-extrabold text-blue-600 hover:underline"><ArrowLeft size={14} /> Reports Center</button><h1 className="mt-3 text-3xl font-black text-[var(--text-primary)]">{draft.name}</h1><p className="mt-2 text-sm text-[var(--text-muted)]">Read-only evidence preview · {draft.primary_period.month} {draft.primary_period.year}{draft.comparison_period ? ` compared with ${draft.comparison_period.month} ${draft.comparison_period.year}` : ''}</p><div className="mt-3 flex flex-wrap gap-2 text-xs font-bold text-[var(--text-muted)]"><span className="rounded-full bg-[var(--bg-sunken)] px-3 py-1.5">{draft.definition.language.toUpperCase()}</span><span className="rounded-full bg-[var(--bg-sunken)] px-3 py-1.5">{pages.length} pages</span><span className={`rounded-full px-3 py-1.5 ${draft.validation?.valid ? 'bg-emerald-500/10 text-emerald-700' : 'bg-amber-500/10 text-amber-700'}`}>{draft.validation?.valid ? 'Validated' : 'Draft preview'}</span></div></div>
          {role === 'Admin' && <button type="button" onClick={() => navigate(`/reports/${reportId}/edit`)} className="min-h-11 rounded-xl border border-[var(--border-light)] px-4 text-sm font-bold text-[var(--text-secondary)]">Edit draft</button>}
        </div>
      </header>

      {draft.validation && <section className={`rounded-2xl border p-4 ${draft.validation.valid ? 'border-emerald-500/20 bg-emerald-500/5' : 'border-amber-500/20 bg-amber-500/5'}`}><div className="flex items-center gap-2 font-extrabold text-[var(--text-primary)]">{draft.validation.valid ? <CheckCircle2 size={18} className="text-emerald-600" /> : <AlertCircle size={18} className="text-amber-600" />}{draft.validation.valid ? 'This draft is ready for review.' : 'This draft still has review warnings.'}</div>{draft.validation.issues.length > 0 && <ul className="mt-3 space-y-1 text-xs font-semibold text-[var(--text-secondary)]">{draft.validation.issues.map((issue, index) => <li key={`${issue.code}-${index}`}>{issue.severity.toUpperCase()}: {issue.message}</li>)}</ul>}</section>}

      {!activePage ? <div className="grid min-h-[45vh] place-items-center rounded-2xl border-2 border-dashed border-[var(--border-light)] bg-[var(--bg-surface)] text-sm font-semibold text-[var(--text-muted)]">This draft has no pages yet.</div> : <section aria-label={`Preview page ${pageIndex + 1}`} className="rf-preview-canvas rounded-3xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4 shadow-xl md:p-8"><div className="mb-5 flex items-center justify-between gap-3 border-b border-[var(--border-light)] pb-4"><div><p className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-blue-600">Page {pageIndex + 1} of {pages.length}</p><h2 className="mt-1 text-2xl font-black text-[var(--text-primary)]">{activePage.title}</h2></div>{isFetching && <span className="inline-flex items-center gap-2 text-xs font-bold text-[var(--text-muted)]"><Loader2 size={14} className="animate-spin" /> Refreshing evidence</span>}</div>{pageLoading ? <PanelLoadingSkeleton rows={4} label={`Loading ${activePage.title}`} /> : <div className={`grid gap-5 ${activePage.blocks.length > 1 ? 'md:grid-cols-2' : 'grid-cols-1'}`}>{activePage.blocks.map((block) => <div key={block.id} className="min-w-0"><BlockRenderer block={block} blockData={pageData?.blocks[block.id]} /></div>)}</div>}</section>}

      <nav aria-label="Report preview pages" className="flex items-center justify-center gap-4"><button type="button" aria-label="Previous preview page" disabled={pageIndex === 0} onClick={() => setPageIndex((value) => Math.max(0, value - 1))} className="grid min-h-11 min-w-11 place-items-center rounded-xl border border-[var(--border-light)] text-[var(--text-secondary)] disabled:opacity-40"><ChevronLeft size={18} /></button><span className="text-sm font-extrabold text-[var(--text-secondary)]">Page {pages.length ? pageIndex + 1 : 0} of {pages.length}</span><button type="button" aria-label="Next preview page" disabled={pageIndex >= pages.length - 1} onClick={() => setPageIndex((value) => Math.min(Math.max(pages.length - 1, 0), value + 1))} className="grid min-h-11 min-w-11 place-items-center rounded-xl border border-[var(--border-light)] text-[var(--text-secondary)] disabled:opacity-40"><ChevronRight size={18} /></button></nav>
    </div>
  );
}
