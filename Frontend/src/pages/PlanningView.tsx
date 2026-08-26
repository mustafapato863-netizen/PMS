import './PageEnhancements.css';
import { useMemo, useState, type FormEvent } from 'react';
import {
  AlertCircle, CalendarDays, CheckCircle2, ChevronLeft, ClipboardCheck,
  FileText, Flag, Gauge, Link2, ListChecks, Loader2, Plus, Search,
  Pencil, Target, Trash2, UserRound, X,
} from 'lucide-react';
import OverlayPortal from '../components/common/OverlayPortal';
import MilestonePanel from '../components/planning/MilestonePanel';
import PlanFormModal from '../components/planning/PlanFormModal';
import { PageLoadingSkeleton, PanelLoadingSkeleton } from '../components/common/SkeletonLoader';
import type { PlanCard, PlanDetail } from '../features/planning/types';
import {
  useAddPlanNote, useDeletePlan, usePlan, usePlanningOptions, usePlans,
  useUpdatePlan, useUpdatePlanItem,
} from '../hooks/api/usePlanning';

const input = 'min-h-11 rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 text-sm font-semibold text-[var(--input-text)] outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20';

const statusStyle: Record<string, string> = {
  Draft: 'border-slate-300 bg-slate-100 text-slate-600 dark:border-slate-600 dark:bg-slate-700/40 dark:text-slate-300',
  'In Progress': 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300',
  'At Risk': 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300',
  Completed: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300',
  Archived: 'border-slate-300 bg-slate-100 text-slate-500 dark:border-slate-600 dark:bg-slate-700/40 dark:text-slate-400',
};

const insightStyle: Record<string, string> = {
  critical: 'border-rose-200 bg-rose-50/70 dark:border-rose-500/25 dark:bg-rose-500/[0.07]',
  risk: 'border-amber-200 bg-amber-50/70 dark:border-amber-500/25 dark:bg-amber-500/[0.07]',
  opportunity: 'border-emerald-200 bg-emerald-50/70 dark:border-emerald-500/25 dark:bg-emerald-500/[0.07]',
  information: 'border-blue-200 bg-blue-50/70 dark:border-blue-500/25 dark:bg-blue-500/[0.07]',
};

function formatDate(value: string | null | undefined) {
  if (!value) return 'N/A';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatMetric(value: number | null, unit: string) {
  if (value === null || value === undefined) return 'N/A';
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${unit ? ` ${unit}` : ''}`;
}

function PlanCardView({ plan, active, onClick }: { plan: PlanCard; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative w-full overflow-hidden rounded-2xl border p-4 text-left transition ${active ? 'border-blue-500 bg-blue-500/[0.055] shadow-sm ring-1 ring-blue-500/10' : 'border-[var(--border-light)] bg-[var(--bg-surface)] hover:border-blue-500/30 hover:shadow-sm'}`}
    >
      {active && <span className="absolute inset-y-0 left-0 w-1 bg-blue-600" />}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="line-clamp-2 text-sm font-extrabold leading-5 text-[var(--text-primary)]">{plan.name}</h3>
          <p className="mt-1 truncate text-xs text-[var(--text-muted)]">{plan.team} · {plan.scope}</p>
        </div>
        <span className={`shrink-0 rounded-full border px-2 py-1 text-[9px] font-extrabold ${statusStyle[plan.status]}`}>{plan.status}</span>
      </div>
      <div className="mt-4">
        <div className="flex items-center justify-between text-[10px] font-bold text-[var(--text-muted)]"><span>Plan progress</span><span>{plan.progress.overall}%</span></div>
        <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-[var(--bg-sunken)]"><div className="h-full rounded-full bg-gradient-to-r from-blue-600 to-cyan-500" style={{ width: `${Math.min(100, Math.max(0, plan.progress.overall))}%` }} /></div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-x-3 gap-y-2 text-[10px] text-[var(--text-muted)]">
        <span className="flex items-center gap-1.5"><UserRound size={12} />{plan.owner.name}</span>
        <span className="flex items-center gap-1.5"><CalendarDays size={12} />{formatDate(plan.due_date)}</span>
        <span>{plan.counts.objectives} objective{plan.counts.objectives === 1 ? '' : 's'}</span>
        <span>{plan.counts.actions} action{plan.counts.actions === 1 ? '' : 's'} · {plan.counts.kpis} KPI{plan.counts.kpis === 1 ? '' : 's'}</span>
      </div>
    </button>
  );
}

function SummaryMetric({ label, value, hint, icon: Icon, tone }: { label: string; value: string; hint: string; icon: typeof Gauge; tone: string }) {
  return (
    <article className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/35 p-4">
      <div className="flex items-start justify-between gap-3"><span className="text-[10px] font-extrabold uppercase tracking-wide text-[var(--text-faint)]">{label}</span><span className={`grid h-8 w-8 place-items-center rounded-lg ${tone}`}><Icon size={15} /></span></div>
      <strong className="mt-2 block text-xl font-black text-[var(--text-primary)]">{value}</strong>
      <span className="mt-1 block text-[10px] text-[var(--text-muted)]">{hint}</span>
    </article>
  );
}

function KpiTable({ detail, limit }: { detail: PlanDetail; limit?: number }) {
  const rows = limit ? detail.kpis.slice(0, limit) : detail.kpis;
  if (!rows.length) return <EmptyState icon={Gauge} title="No KPIs linked" copy="Add a measurable KPI to track this plan against its intended outcome." />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-xs">
        <thead><tr className="border-b border-[var(--border-light)] bg-[var(--bg-sunken)]/45 text-[9px] uppercase tracking-wide text-[var(--text-faint)]"><th className="px-4 py-3">KPI</th><th className="px-3 py-3">Baseline</th><th className="px-3 py-3">Target</th><th className="px-3 py-3">Current</th><th className="px-3 py-3">Achievement</th><th className="px-3 py-3">Gap</th><th className="px-4 py-3">Direction</th></tr></thead>
        <tbody>{rows.map((kpi) => <tr key={kpi.id} className="border-b border-[var(--border-light)] last:border-0"><td className="px-4 py-3"><strong className="text-[var(--text-primary)]">{kpi.label}</strong><span className="ml-1 text-[10px] text-[var(--text-muted)]">({kpi.unit})</span></td><td className="px-3 py-3 text-[var(--text-secondary)]">{kpi.baseline}</td><td className="px-3 py-3 font-bold text-[var(--text-primary)]">{kpi.target}</td><td className="px-3 py-3 text-[var(--text-secondary)]">{kpi.current ?? 'N/A'}</td><td className="px-3 py-3 font-bold text-blue-600">{kpi.achievement === null ? 'N/A' : `${kpi.achievement}%`}</td><td className={`px-3 py-3 font-bold ${kpi.gap === null ? 'text-[var(--text-muted)]' : kpi.gap >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>{kpi.gap ?? 'N/A'}</td><td className="px-4 py-3 capitalize text-[var(--text-muted)]">{kpi.direction.replace('_', ' ')}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

function EmptyState({ icon: Icon, title, copy }: { icon: typeof Gauge; title: string; copy: string }) {
  return <div className="grid min-h-44 place-items-center px-6 py-10 text-center"><div><span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-[var(--bg-sunken)] text-[var(--text-faint)]"><Icon size={19} /></span><p className="mt-3 text-sm font-extrabold text-[var(--text-primary)]">{title}</p><p className="mx-auto mt-1 max-w-sm text-xs leading-5 text-[var(--text-muted)]">{copy}</p></div></div>;
}

function Overview({ detail, onOpenKpis }: { detail: PlanDetail; onOpenKpis: () => void }) {
  const readiness = [detail.counts.objectives > 0, detail.counts.actions > 0, detail.counts.kpis > 0, detail.counts.milestones > 0];
  const readyCount = readiness.filter(Boolean).length;
  const impact = detail.summary.expected_impact;
  return (
    <div className="space-y-4">
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Plan outcome summary">
        <SummaryMetric label="Baseline" value={formatMetric(detail.summary.baseline, detail.summary.unit)} hint="Starting point" icon={Gauge} tone="bg-slate-500/10 text-slate-600 dark:text-slate-300" />
        <SummaryMetric label="Target" value={formatMetric(detail.summary.target, detail.summary.unit)} hint={detail.summary.direction.replace('_', ' ')} icon={Target} tone="bg-blue-500/10 text-blue-600" />
        <SummaryMetric label="Current" value={formatMetric(detail.summary.current, detail.summary.unit)} hint="Latest measured result" icon={CheckCircle2} tone="bg-emerald-500/10 text-emerald-600" />
        <SummaryMetric label="Expected impact" value={impact === null ? 'N/A' : `${impact > 0 ? '+' : ''}${impact.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${detail.summary.unit}`} hint="Target minus baseline" icon={Flag} tone="bg-violet-500/10 text-violet-600 dark:text-violet-300" />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(280px,0.8fr)_minmax(340px,1.2fr)]">
        <div className="space-y-4">
          <article className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4">
            <div className="flex items-center justify-between"><div><h3 className="font-extrabold text-[var(--text-primary)]">Execution readiness</h3><p className="mt-1 text-xs text-[var(--text-muted)]">Required building blocks for an actionable plan.</p></div><strong className={`rounded-full px-3 py-1 text-xs ${readyCount === 4 ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'bg-amber-500/10 text-amber-700 dark:text-amber-300'}`}>{readyCount}/4 ready</strong></div>
            <div className="mt-4 grid grid-cols-2 gap-2">{[
              ['Objective', detail.counts.objectives, 'Define the measurable outcome'],
              ['Action', detail.counts.actions, 'Assign the work to execute'],
              ['KPI', detail.counts.kpis, 'Measure result movement'],
              ['Milestone', detail.counts.milestones, 'Set review checkpoints'],
            ].map(([label, count, hint]) => <div key={String(label)} className={`rounded-xl border p-3 ${Number(count) > 0 ? 'border-emerald-500/20 bg-emerald-500/[0.055]' : 'border-amber-500/20 bg-amber-500/[0.055]'}`}><div className="flex items-center gap-2">{Number(count) > 0 ? <CheckCircle2 size={15} className="text-emerald-600" /> : <AlertCircle size={15} className="text-amber-600" />}<strong className="text-xs text-[var(--text-primary)]">{label}: {count}</strong></div><p className="mt-1 text-[10px] text-[var(--text-muted)]">{hint}</p></div>)}</div>
            {detail.counts.actions === 0 && <p className="mt-3 rounded-xl border border-rose-500/20 bg-rose-500/[0.055] p-3 text-xs font-semibold text-rose-700 dark:text-rose-300">No actions assigned. The plan has a target but no defined execution step.</p>}
          </article>

          <article className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4">
            <h3 className="font-extrabold text-[var(--text-primary)]">Plan context</h3>
            <div className="mt-3 divide-y divide-[var(--border-light)]">{[
              ['Scope', detail.summary.scope_name], ['Team', detail.team], ['Owner', detail.owner.name],
              ['Period', detail.summary.period], ['Due date', formatDate(detail.due_date)],
            ].map(([label, value]) => <div key={label} className="flex items-start justify-between gap-4 py-2.5 text-xs"><span className="text-[var(--text-muted)]">{label}</span><strong className="text-right text-[var(--text-primary)]">{value}</strong></div>)}</div>
            <div className="mt-3"><div className="flex justify-between text-xs"><span className="font-bold text-[var(--text-secondary)]">Overall progress</span><strong>{detail.progress.overall}%</strong></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-[var(--bg-sunken)]"><div className="h-full rounded-full bg-gradient-to-r from-blue-600 to-cyan-500" style={{ width: `${Math.min(100, Math.max(0, detail.progress.overall))}%` }} /></div><p title={detail.progress.explanation} className="mt-2 text-[10px] leading-4 text-[var(--text-muted)]">{detail.progress.explanation}</p></div>
          </article>
        </div>

        <article className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)]">
          <header className="flex items-center justify-between border-b border-[var(--border-light)] px-4 py-3"><div><h3 className="font-extrabold text-[var(--text-primary)]">Linked evidence</h3><p className="mt-0.5 text-xs text-[var(--text-muted)]">Insights that justified creating this plan.</p></div><span className="rounded-full bg-blue-500/10 px-2.5 py-1 text-[10px] font-bold text-blue-600">{detail.linked_insights.length} linked</span></header>
          {detail.linked_insights.length ? <div className="custom-scrollbar max-h-[470px] space-y-2 overflow-y-auto p-3">{detail.linked_insights.slice(0, 5).map((insight) => <a key={insight.id} href="/insights" className={`block rounded-xl border p-3 transition hover:border-blue-500/35 ${insightStyle[insight.severity || 'information'] || insightStyle.information}`}><div className="flex items-start gap-3"><span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-white/70 text-blue-600 dark:bg-slate-900/40"><Link2 size={14} /></span><span className="min-w-0"><strong className="block text-sm leading-5 text-[var(--text-primary)]">{insight.title || 'Insight evidence unavailable'}</strong><span className="mt-1 line-clamp-3 block text-xs leading-5 text-[var(--text-muted)]">{insight.explanation || `Evidence reference: ${insight.id}`}</span>{insight.scope && <span className="mt-2 block text-[10px] font-bold text-[var(--text-faint)]">{insight.scope}</span>}</span></div></a>)}{detail.linked_insights.length > 5 && <p className="py-2 text-center text-xs font-semibold text-[var(--text-muted)]">Showing 5 of {detail.linked_insights.length}. Open Insights to review all evidence.</p>}</div> : <EmptyState icon={Link2} title="No linked evidence" copy="This plan was created without a linked insight. Review the documented business reason before activation." />}
        </article>
      </section>

      <article className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)]"><header className="flex items-center justify-between border-b border-[var(--border-light)] px-4 py-3"><div><h3 className="font-extrabold text-[var(--text-primary)]">Key KPI tracking</h3><p className="mt-0.5 text-xs text-[var(--text-muted)]">Baseline-to-target measurement for this plan.</p></div>{detail.kpis.length > 5 && <button type="button" onClick={onOpenKpis} className="text-xs font-bold text-blue-600">View all KPIs</button>}</header><KpiTable detail={detail} limit={5} /></article>

      <article className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)]"><header className="border-b border-[var(--border-light)] px-4 py-3"><h3 className="font-extrabold text-[var(--text-primary)]">Review milestones</h3><p className="mt-0.5 text-xs text-[var(--text-muted)]">Scheduled checkpoints to confirm that execution is producing movement.</p></header>{detail.milestones.length ? <div className="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-4">{detail.milestones.slice(0, 4).map((milestone) => <div key={milestone.id} className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/35 p-3"><div className="flex items-center justify-between"><span className="grid h-8 w-8 place-items-center rounded-lg bg-blue-500/10 text-blue-600"><Flag size={14} /></span><span className="text-[9px] font-bold uppercase text-[var(--text-faint)]">{milestone.status}</span></div><strong className="mt-3 block text-xs text-[var(--text-primary)]">{milestone.name}</strong><p className="mt-1 text-[10px] text-[var(--text-muted)]">{formatDate(milestone.due_date)} · {milestone.owner}</p></div>)}</div> : <EmptyState icon={Flag} title="No review milestones" copy="Add at least one checkpoint so progress can be reviewed before the final due date." />}</article>
    </div>
  );
}

function Notes({ planId, notes, canEdit, add }: { planId: string; notes: Array<{ id: string; author: string; timestamp: string; text: string }>; canEdit: boolean; add: (text: string) => void }) {
  const [text, setText] = useState('');
  return <div>{notes.map((note) => <div key={note.id} className="mb-3 rounded-xl border border-[var(--border-light)] p-4"><div className="flex gap-2 text-xs text-[var(--text-muted)]"><FileText size={14} />{note.author} · {new Date(note.timestamp).toLocaleString()}</div><p className="mt-2 text-sm text-[var(--text-primary)]">{note.text}</p></div>)}{!notes.length && <EmptyState icon={FileText} title="No review notes" copy="Capture decisions, blockers and progress evidence during each review." />}{canEdit && <div className="mt-4"><textarea aria-label={`New note for ${planId}`} className={`${input} min-h-24 w-full py-3`} value={text} onChange={(event) => setText(event.target.value)} /><button type="button" onClick={() => { if (text.trim()) { add(text); setText(''); } }} className="mt-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white">Add review note</button></div>}</div>;
}

function EditPlanModal({ detail, owners, statuses, onClose }: { detail: PlanDetail; owners: Array<{ id: string; name: string }>; statuses: string[]; onClose: () => void }) {
  const update = useUpdatePlan();
  const [name, setName] = useState(detail.name);
  const [ownerId, setOwnerId] = useState(detail.owner.id);
  const [dueDate, setDueDate] = useState(detail.due_date);
  const [target, setTarget] = useState(String(detail.summary.target));
  const [current, setCurrent] = useState(detail.summary.current === null ? '' : String(detail.summary.current));
  const [expectedImpact, setExpectedImpact] = useState(detail.summary.expected_impact === null ? '' : String(detail.summary.expected_impact));
  const [planStatus, setPlanStatus] = useState(detail.stored_status);
  const [statusReason, setStatusReason] = useState(detail.summary.status_reason || '');
  const [completionNote, setCompletionNote] = useState('');
  const [localError, setLocalError] = useState('');

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setLocalError('');
    if (name.trim().length < 3) { setLocalError('Plan name must contain at least 3 characters.'); return; }
    if (!dueDate || !Number.isFinite(Number(target))) { setLocalError('Enter a valid due date and target.'); return; }
    if (planStatus === 'At Risk' && !statusReason.trim()) { setLocalError('Explain why the plan is at risk.'); return; }
    if (planStatus === 'Completed' && !completionNote.trim()) { setLocalError('A completion note is required to complete the plan.'); return; }
    const payload: Record<string, unknown> = { name: name.trim(), owner_user_id: ownerId, due_date: dueDate, target_value: Number(target), status: planStatus, status_reason: statusReason.trim() || null };
    if (current !== '') payload.current_value = Number(current);
    if (expectedImpact !== '') payload.expected_impact = Number(expectedImpact);
    if (completionNote.trim()) payload.completion_note = completionNote.trim();
    try { await update.mutateAsync({ id: detail.id, payload }); onClose(); }
    catch (error) { setLocalError(error instanceof Error ? error.message : 'Unable to update this plan.'); }
  };

  return <OverlayPortal><div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-3 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><form role="dialog" aria-modal="true" aria-labelledby="edit-plan-title" onSubmit={submit} className="custom-scrollbar max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-3xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-2xl">
    <header className="flex items-start justify-between border-b border-[var(--border-light)] p-5"><div><h2 id="edit-plan-title" className="text-xl font-extrabold text-[var(--text-primary)]">Edit plan</h2><p className="mt-1 text-sm text-[var(--text-muted)]">Update ownership, outcome and lifecycle status.</p></div><button type="button" aria-label="Close edit plan" onClick={onClose} className="grid h-10 w-10 place-items-center rounded-xl text-[var(--text-muted)] hover:bg-[var(--bg-sunken)]"><X size={19} /></button></header>
    <div className="grid gap-4 p-5 sm:grid-cols-2">
      <label className="sm:col-span-2"><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Plan name</span><input aria-label="Edit plan name" className={`${input} w-full`} value={name} onChange={(event) => setName(event.target.value)} /></label>
      <label><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Owner</span><select aria-label="Edit plan owner" className={`${input} w-full`} value={ownerId} onChange={(event) => setOwnerId(event.target.value)}>{owners.map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</select></label>
      <label><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Due date</span><input aria-label="Edit plan due date" type="date" className={`${input} w-full`} value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></label>
      <label><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Target ({detail.summary.unit})</span><input aria-label="Edit plan target" type="number" step="any" className={`${input} w-full`} value={target} onChange={(event) => setTarget(event.target.value)} /></label>
      <label><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Current ({detail.summary.unit})</span><input aria-label="Edit plan current value" type="number" step="any" className={`${input} w-full`} value={current} onChange={(event) => setCurrent(event.target.value)} /></label>
      <label><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Expected impact</span><input aria-label="Edit expected impact" type="number" step="any" className={`${input} w-full`} value={expectedImpact} onChange={(event) => setExpectedImpact(event.target.value)} /></label>
      <label><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Status</span><select aria-label="Edit plan status" className={`${input} w-full`} value={planStatus} onChange={(event) => setPlanStatus(event.target.value as PlanDetail['stored_status'])}>{statuses.map((value) => <option key={value}>{value}</option>)}</select></label>
      {planStatus === 'At Risk' && <label className="sm:col-span-2"><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Risk reason</span><textarea aria-label="Plan risk reason" className={`${input} min-h-24 w-full py-3`} value={statusReason} onChange={(event) => setStatusReason(event.target.value)} /></label>}
      {planStatus === 'Completed' && <label className="sm:col-span-2"><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Completion note</span><textarea aria-label="Plan completion note" className={`${input} min-h-24 w-full py-3`} value={completionNote} onChange={(event) => setCompletionNote(event.target.value)} /></label>}
      {(localError || update.error) && <p role="alert" className="sm:col-span-2 rounded-xl bg-rose-500/10 p-3 text-sm font-bold text-rose-600">{localError || (update.error instanceof Error ? update.error.message : 'Unable to update this plan.')}</p>}
    </div>
    <footer className="flex justify-end gap-2 border-t border-[var(--border-light)] p-4"><button type="button" onClick={onClose} className="min-h-11 rounded-xl border border-[var(--border-light)] px-4 font-bold text-[var(--text-secondary)]">Cancel</button><button type="submit" disabled={update.isPending} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-blue-600 px-5 font-bold text-white disabled:opacity-60">{update.isPending ? <Loader2 size={16} className="animate-spin" /> : <Pencil size={16} />}Save changes</button></footer>
  </form></div></OverlayPortal>;
}

function DeletePlanModal({ detail, onClose, onDeleted }: { detail: PlanDetail; onClose: () => void; onDeleted: () => void }) {
  const remove = useDeletePlan();
  const [confirmation, setConfirmation] = useState('');
  const submit = async () => {
    if (confirmation !== detail.name) return;
    try { await remove.mutateAsync(detail.id); onDeleted(); }
    catch { /* The mutation error is rendered in the dialog. */ }
  };
  return <OverlayPortal><div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-3 backdrop-blur-sm"><div role="alertdialog" aria-modal="true" aria-labelledby="delete-plan-title" aria-describedby="delete-plan-description" className="w-full max-w-lg rounded-3xl border border-rose-500/20 bg-[var(--bg-surface)] p-5 shadow-2xl">
    <div className="flex items-start gap-4"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-rose-500/10 text-rose-600"><Trash2 size={19} /></span><div><h2 id="delete-plan-title" className="text-xl font-extrabold text-[var(--text-primary)]">Delete this plan?</h2><p id="delete-plan-description" className="mt-2 text-sm leading-6 text-[var(--text-muted)]">The plan will disappear from the Planning workspace. Its audit history is retained for governance and recovery.</p></div></div>
    <label className="mt-5 block"><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Type <strong className="text-[var(--text-primary)]">{detail.name}</strong> to confirm</span><input autoFocus aria-label="Confirm plan name" className={`${input} w-full`} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label>
    {remove.error && <p role="alert" className="mt-3 rounded-xl bg-rose-500/10 p-3 text-sm font-bold text-rose-600">{remove.error instanceof Error ? remove.error.message : 'Unable to delete this plan.'}</p>}
    <div className="mt-5 flex justify-end gap-2"><button type="button" onClick={onClose} className="min-h-11 rounded-xl border border-[var(--border-light)] px-4 font-bold text-[var(--text-secondary)]">Cancel</button><button type="button" disabled={confirmation !== detail.name || remove.isPending} onClick={submit} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-rose-600 px-5 font-bold text-white disabled:cursor-not-allowed disabled:opacity-40">{remove.isPending ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}Delete plan</button></div>
  </div></div></OverlayPortal>;
}

export default function PlanningView() {
  const options = usePlanningOptions();
  const [status, setStatus] = useState('');
  const [team, setTeam] = useState('');
  const [owner, setOwner] = useState('');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState('');
  const [tab, setTab] = useState('Overview');
  const [newOpen, setNewOpen] = useState(() => Boolean(sessionStorage.getItem('pms_planning_draft')));
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [mobileDetail, setMobileDetail] = useState(false);
  const params = useMemo(() => { const value = new URLSearchParams(); if (status) value.set('status', status); if (team) value.set('team', team); if (owner) value.set('owner_id', owner); if (search) value.set('search', search); return value; }, [status, team, owner, search]);
  const plans = usePlans(params);
  const effectiveSelected = selected || plans.data?.[0]?.id || '';
  const detail = usePlan(effectiveSelected);
  const updateItem = useUpdatePlanItem();
  const addNote = useAddPlanNote();
  const current = detail.data;

  if (options.isLoading || plans.isLoading) return <PageLoadingSkeleton variant="detail" label="Preparing planning workspace" />;
  if (options.error || plans.error || !options.data) return <div role="alert" className="m-8 rounded-2xl border border-red-500/20 bg-red-500/10 p-6 text-red-600">Unable to load planning workspace.</div>;

  const tabs = ['Overview', 'Objectives', 'Actions', 'KPIs', 'Milestones', 'Notes'];
  const countFor = (value: string) => current?.counts[value.toLowerCase() as keyof typeof current.counts] ?? 0;

  return (
    <div className="app-page-shell rf-page rf-page--planning">
      <header className="flex flex-col gap-3 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4 shadow-sm xl:flex-row xl:items-center xl:justify-between">
        <div className="shrink-0"><div className="flex items-center gap-2"><h1 className="text-xl font-extrabold text-[var(--text-primary)]">Planning</h1><ClipboardCheck size={17} className="text-blue-600" /></div><p className="mt-0.5 text-xs text-[var(--text-muted)]">Turn performance insights into owned, measurable actions.</p></div>
        <div className="grid gap-2 sm:grid-cols-2 xl:flex xl:items-center"><select aria-label="Team" className="min-h-10 min-w-0 rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 text-xs font-semibold text-[var(--input-text)] outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 xl:w-44" value={team} onChange={(event) => setTeam(event.target.value)}><option value="">All Teams</option>{options.data.teams.map((value) => <option key={value}>{value}</option>)}</select><select aria-label="Plan owner" className="min-h-10 min-w-0 rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 text-xs font-semibold text-[var(--input-text)] outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 xl:w-40" value={owner} onChange={(event) => setOwner(event.target.value)}><option value="">All Plan Owners</option>{options.data.owners.map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</select><select aria-label="Status" className="min-h-10 min-w-0 rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 text-xs font-semibold text-[var(--input-text)] outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 xl:w-32" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All Statuses</option>{options.data.statuses.map((value) => <option key={value}>{value}</option>)}</select>{options.data.can_edit && <button type="button" onClick={() => setNewOpen(true)} className="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-xl bg-blue-600 px-3.5 text-xs font-bold text-white shadow-sm hover:bg-blue-700"><Plus size={16} />New Plan</button>}</div>
      </header>

      <nav aria-label="Plan status" className="flex gap-1 overflow-x-auto rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-1.5 shadow-sm">{['', ...options.data.statuses].map((value) => <button type="button" key={value || 'All'} onClick={() => setStatus(value)} className={`min-h-9 whitespace-nowrap rounded-xl px-3.5 text-xs font-bold ${status === value ? 'bg-blue-600 text-white shadow-sm' : 'text-[var(--text-muted)] hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)]'}`}>{value || 'All Plans'}</button>)}</nav>

      <div className="grid min-h-[680px] gap-4 lg:grid-cols-[390px_minmax(0,1fr)]">
        <aside className={`${mobileDetail ? 'hidden lg:flex' : 'flex'} min-h-0 flex-col rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm`}>
          <div className="border-b border-[var(--border-light)] p-3"><label className="relative block"><Search size={16} className="absolute left-3 top-3.5 text-[var(--text-muted)]" /><input aria-label="Search plans" className={`${input} w-full pl-9`} placeholder="Search plans..." value={search} onChange={(event) => setSearch(event.target.value)} /></label><p className="mt-2 px-1 text-[10px] font-semibold text-[var(--text-muted)]">{plans.data?.length || 0} plan{plans.data?.length === 1 ? '' : 's'} in this view</p></div>
          <div className="custom-scrollbar max-h-[calc(100vh-285px)] flex-1 space-y-3 overflow-y-auto p-3">{plans.data?.map((plan) => <PlanCardView key={plan.id} plan={plan} active={effectiveSelected === plan.id} onClick={() => { setSelected(plan.id); setTab('Overview'); setMobileDetail(true); }} />)}{!plans.data?.length && <EmptyState icon={ClipboardCheck} title="No plans in this view" copy="Change the filters or create a new performance plan." />}</div>
        </aside>

        <main className={`${!mobileDetail ? 'hidden lg:block' : 'block'} min-w-0 overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm`}>
          {detail.isLoading ? <PanelLoadingSkeleton rows={6} label="Loading plan details" /> : current ? <>
            <header className="border-b border-[var(--border-light)] px-4 pt-4">
              <button type="button" onClick={() => setMobileDetail(false)} className="mb-3 inline-flex items-center gap-1 text-sm font-bold text-blue-600 lg:hidden"><ChevronLeft size={16} />Plans</button>
              <div className="flex items-start justify-between gap-3">
                <h2 className="min-w-0 text-lg font-extrabold leading-6 text-[var(--text-primary)]">{current.name}</h2>
                {options.data.can_edit && <div className="flex shrink-0 items-center gap-1.5"><button type="button" onClick={() => setEditOpen(true)} className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-blue-500/25 px-2 text-[11px] font-bold text-blue-600 hover:bg-blue-500/[0.06]"><Pencil size={13} />Edit</button><button type="button" onClick={() => setDeleteOpen(true)} className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-rose-500/25 px-2 text-[11px] font-bold text-rose-600 hover:bg-rose-500/[0.06]"><Trash2 size={13} />Delete</button></div>}
              </div>
              <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex min-w-0 flex-wrap items-center gap-2"><span className={`rounded-full border px-2 py-0.5 text-[9px] font-extrabold ${statusStyle[current.status]}`}>{current.status}</span><p className="min-w-0 truncate text-xs text-[var(--text-muted)]">{current.team} · {current.scope} · Owner {current.owner.name}</p></div>
                <div className="flex shrink-0 items-center gap-1.5 rounded-lg bg-[var(--bg-sunken)]/55 px-2 py-1"><div className="grid h-7 w-7 place-items-center rounded-md bg-blue-500/10 text-blue-600"><Gauge size={13} /></div><div><span className="block text-[8px] font-bold uppercase leading-none text-[var(--text-faint)]">Plan progress</span><strong className="text-sm leading-4 text-[var(--text-primary)]">{current.progress.overall}%</strong></div></div>
              </div>
              {current.risk_reasons.length > 0 && <div className="mt-4 flex items-start gap-2 rounded-xl border border-rose-500/20 bg-rose-500/[0.055] p-3 text-xs font-semibold text-rose-700 dark:text-rose-300"><AlertCircle size={15} className="mt-0.5 shrink-0" /><span>{current.risk_reasons.join(' · ')}</span></div>}
              <div className="mt-3 flex gap-1 overflow-x-auto">{tabs.map((value) => <button type="button" key={value} onClick={() => setTab(value)} className={`min-h-10 whitespace-nowrap border-b-2 px-2.5 text-xs font-bold ${tab === value ? 'border-blue-600 text-blue-600' : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]'}`}>{value}{value !== 'Overview' ? ` (${countFor(value)})` : ''}</button>)}</div>
            </header>

            <section className="bg-[var(--bg-sunken)]/20 p-4 md:p-5">
              {tab === 'Overview' && <Overview detail={current} onOpenKpis={() => setTab('KPIs')} />}
              {tab === 'Objectives' && (current.objectives.length ? <div className="space-y-3">{current.objectives.map((objective) => <article key={objective.id} className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4"><div className="flex items-start justify-between gap-3"><div><strong className="text-[var(--text-primary)]">{objective.name}</strong><p className="mt-1 text-xs text-[var(--text-muted)]">Measurable objective linked to the plan outcome.</p></div><span className="rounded-full bg-blue-500/10 px-2 py-1 text-[10px] font-bold text-blue-600">{objective.status}</span></div><div className="mt-4 flex items-center gap-3"><div className="h-2 flex-1 overflow-hidden rounded bg-[var(--bg-sunken)]"><div className="h-full rounded bg-blue-500" style={{ width: `${objective.progress}%` }} /></div><strong className="text-xs">{objective.progress}%</strong></div>{options.data.can_edit && <button type="button" onClick={() => updateItem.mutate({ planId: current.id, kind: 'objective', itemId: objective.id, payload: { status: 'Completed', current_value: (objective as { target?: number }).target } })} className="mt-3 text-xs font-bold text-blue-600">Mark completed</button>}</article>)}</div> : <EmptyState icon={Target} title="No objectives defined" copy="Add a measurable objective before activating this plan." />)}
              {tab === 'Actions' && (current.actions.length ? <div className="space-y-3">{current.actions.map((action) => <article key={action.id} className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4"><div className="flex items-start justify-between gap-3"><div><strong className="text-[var(--text-primary)]">{action.title}</strong><p className="mt-1 text-sm text-[var(--text-muted)]">{action.description}</p></div><span className="rounded-full bg-blue-500/10 px-2 py-1 text-[10px] font-bold text-blue-600">{action.status}</span></div>{options.data.can_edit && action.status !== 'Completed' && <button type="button" onClick={() => updateItem.mutate({ planId: current.id, kind: 'action', itemId: action.id, payload: { status: 'Completed', completion_note: 'Completed from planning review' } })} className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-xl border border-blue-500/25 px-3 text-xs font-bold text-blue-600"><CheckCircle2 size={15} />Mark completed</button>}</article>)}</div> : <EmptyState icon={ListChecks} title="No actions assigned" copy="Define the work, owner and due date required to move the KPI from baseline to target." />)}
              {tab === 'KPIs' && <article className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)]"><header className="border-b border-[var(--border-light)] px-4 py-3"><h3 className="font-extrabold text-[var(--text-primary)]">All plan KPIs</h3><p className="mt-1 text-xs text-[var(--text-muted)]">Measured progress against the configured outcome direction.</p></header><KpiTable detail={current} /></article>}
              {tab === 'Milestones' && <MilestonePanel detail={current} owners={options.data.owners} canEdit={options.data.can_edit} />}
              {tab === 'Notes' && <Notes planId={current.id} notes={current.notes} canEdit={options.data.can_edit} add={(text) => addNote.mutate({ id: current.id, text })} />}
            </section>
          </> : <EmptyState icon={Target} title="Select a plan" copy="Choose a plan from the list to inspect its execution status and evidence." />}
        </main>
      </div>

      {newOpen && <PlanFormModal options={options.data} onClose={() => setNewOpen(false)} onCreated={(id) => { setNewOpen(false); setSelected(id); setMobileDetail(true); }} />}
      {editOpen && current && <EditPlanModal detail={current} owners={options.data.owners} statuses={options.data.statuses} onClose={() => setEditOpen(false)} />}
      {deleteOpen && current && <DeletePlanModal detail={current} onClose={() => setDeleteOpen(false)} onDeleted={() => { setDeleteOpen(false); setSelected(''); setMobileDetail(false); }} />}
    </div>
  );
}
