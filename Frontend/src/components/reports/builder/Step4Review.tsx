import { useState } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { useStoryPage, useValidateStoryDraft } from '../../../hooks/api/useReports';
import { useReportBuilderStore } from '../../../store/reportBuilderStore';
import type { StoryReportPage } from '../../../features/reports/types';
import BlockRenderer from './BlockRenderer';
import { PanelLoadingSkeleton } from '../../common/SkeletonLoader';

function ReviewPage({ draftId, page }: { draftId: string; page: StoryReportPage }) {
  const { data, isLoading } = useStoryPage(draftId, page.id);
  return <article className="aspect-video overflow-hidden rounded-2xl border border-slate-200 bg-white p-8 shadow-md dark:border-slate-700 dark:bg-slate-950"><div className="mb-4 flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800"><h3 className="text-xl font-black text-slate-900 dark:text-white">{page.title}</h3><span className="text-xs font-bold text-slate-400">Page {page.order + 1}</span></div>{isLoading ? <PanelLoadingSkeleton rows={3} label={`Loading ${page.title}`} /> : <div className={`grid gap-4 ${page.blocks.length > 1 ? 'grid-cols-2' : 'grid-cols-1'}`}>{page.blocks.map((block) => <BlockRenderer key={block.id} blockData={data?.blocks[block.id]} block={block} />)}</div>}</article>;
}

export default function Step4Review() {
  const { draftId, slides, saveState } = useReportBuilderStore();
  const validate = useValidateStoryDraft();
  const [pageIndex, setPageIndex] = useState(0);
  if (!draftId) return <div className="grid min-h-[50vh] place-items-center text-[var(--text-muted)]">Create a report draft before review.</div>;
  return <div className="mx-auto max-w-6xl px-6 py-8"><div className="mb-6 flex flex-wrap items-end justify-between gap-4"><div><h2 className="text-2xl font-extrabold text-slate-900 dark:text-white">Review the evidence-to-decision story</h2><p className="mt-1 text-sm text-[var(--text-muted)]">This preview uses the same block contracts and authorized data used by PDF generation.</p></div><button disabled={saveState !== 'saved' || validate.isPending} onClick={() => validate.mutate(draftId)} className="flex items-center gap-2 rounded-xl bg-[var(--sgh-cyan-primary,#00A3E0)] px-4 py-2 text-sm font-extrabold text-white transition hover:bg-[var(--sgh-cyan-dark,#0084CE)] disabled:opacity-50">{validate.isPending ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />} Validate report</button></div>
    {validate.data && <div className={`mb-7 rounded-xl border p-4 ${validate.data.valid ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-200' : 'border-red-200 bg-red-50 text-red-900 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-200'}`}><div className="flex items-center gap-2 font-extrabold">{validate.data.valid ? <CheckCircle2 className="text-emerald-600 dark:text-emerald-400" /> : <AlertCircle className="text-red-600 dark:text-red-400" />} {validate.data.valid ? 'Ready for PDF export' : 'Resolve validation errors before export'}</div>{validate.data.issues.length > 0 && <ul className="mt-3 space-y-2">{validate.data.issues.map((issue, index) => <li key={`${issue.code}-${index}`} className="flex gap-2 text-sm text-slate-700 dark:text-slate-200"><AlertTriangle size={15} className={issue.severity === 'error' ? 'text-red-600 dark:text-red-400' : 'text-amber-600 dark:text-amber-400'} /><b>{issue.severity.toUpperCase()}:</b> {issue.message}</li>)}</ul>}</div>}
    {slides[pageIndex] && <ReviewPage draftId={draftId} page={slides[pageIndex]} />}
    <div className="mt-5 flex items-center justify-center gap-4"><button disabled={pageIndex === 0} onClick={() => setPageIndex((value) => value - 1)} className="rounded-lg border border-slate-200 p-2 text-slate-600 hover:bg-slate-100 disabled:opacity-30 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"><ChevronLeft /></button><b className="text-sm text-slate-600 dark:text-slate-300">Page {pageIndex + 1} of {slides.length}</b><button disabled={pageIndex >= slides.length - 1} onClick={() => setPageIndex((value) => value + 1)} className="rounded-lg border border-slate-200 p-2 text-slate-600 hover:bg-slate-100 disabled:opacity-30 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"><ChevronRight /></button></div>
  </div>;
}
