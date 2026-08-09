import { useState, type FormEvent } from 'react';
import { CalendarDays, CheckCircle2, Flag, Loader2, Pencil, Plus, RotateCcw, Trash2, X } from 'lucide-react';
import type { MilestoneStatus, PlanDetail, PlanMilestone } from '../../features/planning/types';
import { useCreateMilestone, useDeleteMilestone, useUpdateMilestone } from '../../hooks/api/usePlanning';
import OverlayPortal from '../common/OverlayPortal';

const input = 'min-h-11 w-full rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 text-sm font-semibold text-[var(--input-text)] outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20';
const editableStatuses: Array<Exclude<MilestoneStatus, 'Overdue'>> = ['Pending', 'In Progress', 'Completed'];
const statusStyles: Record<MilestoneStatus, string> = {
  Pending: 'border-slate-300 bg-slate-100 text-slate-600 dark:border-slate-600 dark:bg-slate-700/40 dark:text-slate-300',
  'In Progress': 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300',
  Completed: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300',
  Overdue: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300',
};

type Owner = { id: string; name: string };
type Props = { detail: PlanDetail; owners: Owner[]; canEdit: boolean };

function formatDate(value: string | null) {
  if (!value) return 'N/A';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}

function MilestoneFormModal({ detail, owners, milestone, onClose }: Props & { milestone: PlanMilestone | null; onClose: () => void }) {
  const create = useCreateMilestone();
  const update = useUpdateMilestone();
  const [name, setName] = useState(milestone?.name || '');
  const [dueDate, setDueDate] = useState(milestone?.due_date || detail.due_date);
  const [ownerId, setOwnerId] = useState(milestone?.owner_id || detail.owner.id || owners[0]?.id || '');
  const [status, setStatus] = useState<Exclude<MilestoneStatus, 'Overdue'>>(milestone?.status === 'Overdue' ? 'Pending' : milestone?.status || 'Pending');
  const [note, setNote] = useState(milestone?.note || '');
  const [error, setError] = useState('');
  const pending = create.isPending || update.isPending;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    if (name.trim().length < 3) { setError('Enter a solution step of at least 3 characters.'); return; }
    if (!dueDate) { setError('Select a milestone due date.'); return; }
    if (!ownerId) { setError('Select a milestone owner.'); return; }
    const payload = { name: name.trim(), due_date: dueDate, owner_user_id: ownerId, status, note: note.trim() || null };
    try {
      if (milestone) await update.mutateAsync({ planId: detail.id, milestoneId: milestone.id, payload });
      else await create.mutateAsync({ planId: detail.id, payload });
      onClose();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Unable to save this milestone.');
    }
  };

  return <OverlayPortal><div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-3 backdrop-blur-sm"><form role="dialog" aria-modal="true" aria-labelledby="milestone-form-title" onSubmit={submit} className="w-full max-w-xl rounded-3xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-2xl">
    <header className="flex items-start justify-between border-b border-[var(--border-light)] p-5"><div><h2 id="milestone-form-title" className="text-xl font-extrabold text-[var(--text-primary)]">{milestone ? 'Edit milestone' : 'Add solution step'}</h2><p className="mt-1 text-sm text-[var(--text-muted)]">Define a reviewable step, owner, due date and status.</p></div><button type="button" aria-label="Close milestone form" onClick={onClose} className="grid h-10 w-10 place-items-center rounded-xl hover:bg-[var(--bg-sunken)]"><X size={18} /></button></header>
    <div className="grid gap-4 p-5 sm:grid-cols-2">
      <label className="sm:col-span-2"><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Solution step</span><input aria-label="Solution step" className={input} value={name} onChange={(event) => setName(event.target.value)} /></label>
      <label><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Owner</span><select aria-label="Milestone owner" className={input} value={ownerId} onChange={(event) => setOwnerId(event.target.value)}>{owners.map((owner) => <option key={owner.id} value={owner.id}>{owner.name}</option>)}</select></label>
      <label><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Due date</span><input aria-label="Milestone due date" type="date" max={detail.due_date} className={input} value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></label>
      <label><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Status</span><select aria-label="Milestone status" className={input} value={status} onChange={(event) => setStatus(event.target.value as Exclude<MilestoneStatus, 'Overdue'>)}>{editableStatuses.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label className="sm:col-span-2"><span className="mb-1.5 block text-xs font-bold text-[var(--text-secondary)]">Notes</span><textarea aria-label="Milestone notes" className={`${input} min-h-24 py-3`} value={note} onChange={(event) => setNote(event.target.value)} /></label>
      {error && <p role="alert" className="sm:col-span-2 rounded-xl bg-rose-500/10 p-3 text-sm font-bold text-rose-600">{error}</p>}
    </div>
    <footer className="flex justify-end gap-2 border-t border-[var(--border-light)] p-4"><button type="button" onClick={onClose} className="min-h-11 rounded-xl border border-[var(--border-light)] px-4 font-bold text-[var(--text-secondary)]">Cancel</button><button type="submit" disabled={pending} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-blue-600 px-5 font-bold text-white disabled:opacity-60">{pending ? <Loader2 size={16} className="animate-spin" /> : milestone ? <Pencil size={16} /> : <Plus size={16} />}{milestone ? 'Save changes' : 'Add step'}</button></footer>
  </form></div></OverlayPortal>;
}

function DeleteMilestoneModal({ detail, milestone, onClose }: { detail: PlanDetail; milestone: PlanMilestone; onClose: () => void }) {
  const remove = useDeleteMilestone();
  const submit = async () => {
    try { await remove.mutateAsync({ planId: detail.id, milestoneId: milestone.id }); onClose(); }
    catch { /* Mutation error is rendered below. */ }
  };
  return <OverlayPortal><div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-3 backdrop-blur-sm"><div role="alertdialog" aria-modal="true" aria-labelledby="delete-milestone-title" className="w-full max-w-lg rounded-3xl border border-rose-500/20 bg-[var(--bg-surface)] p-5 shadow-2xl">
    <div className="flex items-start gap-4"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-rose-500/10 text-rose-600"><Trash2 size={19} /></span><div><h2 id="delete-milestone-title" className="text-xl font-extrabold text-[var(--text-primary)]">Delete this milestone?</h2><p className="mt-2 text-sm leading-6 text-[var(--text-muted)]"><strong>{milestone.name}</strong> will be removed from the plan and its progress calculation.</p></div></div>
    {remove.error && <p role="alert" className="mt-4 rounded-xl bg-rose-500/10 p-3 text-sm font-bold text-rose-600">{remove.error instanceof Error ? remove.error.message : 'Unable to delete this milestone.'}</p>}
    <div className="mt-5 flex justify-end gap-2"><button type="button" onClick={onClose} className="min-h-11 rounded-xl border border-[var(--border-light)] px-4 font-bold text-[var(--text-secondary)]">Cancel</button><button type="button" disabled={remove.isPending} onClick={submit} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-rose-600 px-5 font-bold text-white disabled:opacity-60">{remove.isPending ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}Delete milestone</button></div>
  </div></div></OverlayPortal>;
}

export default function MilestonePanel({ detail, owners, canEdit }: Props) {
  const update = useUpdateMilestone();
  const [formMilestone, setFormMilestone] = useState<PlanMilestone | null | undefined>(undefined);
  const [deleteMilestone, setDeleteMilestone] = useState<PlanMilestone | null>(null);
  const [error, setError] = useState('');

  const toggleCompleted = async (milestone: PlanMilestone) => {
    setError('');
    try {
      await update.mutateAsync({
        planId: detail.id,
        milestoneId: milestone.id,
        payload: { status: milestone.status === 'Completed' ? 'Pending' : 'Completed' },
      });
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Unable to update milestone status.');
    }
  };

  return <section aria-label="Milestones and solution steps" className="space-y-3">
    <header className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between"><div><h3 className="text-base font-extrabold text-[var(--text-primary)]">Milestones & solution steps</h3><p className="mt-0.5 text-xs text-[var(--text-muted)]">Add execution checkpoints, assign ownership and track whether each step is done.</p></div>{canEdit && <button type="button" onClick={() => setFormMilestone(null)} className="inline-flex min-h-9 items-center justify-center gap-1.5 rounded-lg border border-blue-500/25 bg-blue-500/[0.06] px-3 text-xs font-bold text-blue-600 transition-colors hover:bg-blue-500/10"><Plus size={14} />Add solution step</button>}</header>
    {error && <p role="alert" className="rounded-xl bg-rose-500/10 p-3 text-sm font-bold text-rose-600">{error}</p>}
    {detail.milestones.length ? <div className="grid gap-3 md:grid-cols-2">{detail.milestones.map((milestone) => <article key={milestone.id} className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4">
      <div className="flex items-start justify-between gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-blue-500/10 text-blue-600"><Flag size={17} /></span><span className={`rounded-full border px-2.5 py-1 text-[10px] font-extrabold ${statusStyles[milestone.status]}`}>{milestone.status}</span></div>
      <strong className="mt-3 block text-sm text-[var(--text-primary)]">{milestone.name}</strong>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--text-muted)]"><span className="inline-flex items-center gap-1.5"><CalendarDays size={13} />{formatDate(milestone.due_date)}</span><span>Owner: {milestone.owner}</span></div>
      {milestone.note && <p className="mt-3 rounded-xl bg-[var(--bg-sunken)]/60 p-3 text-xs leading-5 text-[var(--text-secondary)]">{milestone.note}</p>}
      {milestone.completion_date && <p className="mt-2 text-[10px] font-bold text-emerald-600">Completed {formatDate(milestone.completion_date)}</p>}
      {canEdit && <div className="mt-4 flex flex-wrap gap-1.5 border-t border-[var(--border-light)] pt-3"><button type="button" disabled={update.isPending} onClick={() => toggleCompleted(milestone)} className={`inline-flex min-h-8 items-center gap-1 rounded-lg px-2.5 text-[11px] font-bold ${milestone.status === 'Completed' ? 'border border-[var(--border-light)] text-[var(--text-secondary)]' : 'bg-emerald-600 text-white'}`}>{milestone.status === 'Completed' ? <RotateCcw size={13} /> : <CheckCircle2 size={13} />}{milestone.status === 'Completed' ? 'Reopen' : 'Mark completed'}</button><button type="button" aria-label={`Edit ${milestone.name}`} onClick={() => setFormMilestone(milestone)} className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-blue-500/25 px-2 text-[11px] font-bold text-blue-600"><Pencil size={13} />Edit</button><button type="button" aria-label={`Delete ${milestone.name}`} onClick={() => setDeleteMilestone(milestone)} className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-rose-500/25 px-2 text-[11px] font-bold text-rose-600"><Trash2 size={13} />Delete</button></div>}
    </article>)}</div> : <div className="grid min-h-44 place-items-center rounded-2xl border border-dashed border-[var(--border-light)] px-6 py-8 text-center"><div><span className="mx-auto grid h-10 w-10 place-items-center rounded-xl bg-[var(--bg-sunken)] text-[var(--text-faint)]"><Flag size={18} /></span><p className="mt-2.5 text-sm font-extrabold text-[var(--text-primary)]">No solution steps yet</p><p className="mx-auto mt-1 max-w-sm text-xs leading-5 text-[var(--text-muted)]">Add the first milestone to define what will be done, by whom and by when.</p></div></div>}
    {formMilestone !== undefined && <MilestoneFormModal detail={detail} owners={owners} canEdit={canEdit} milestone={formMilestone} onClose={() => setFormMilestone(undefined)} />}
    {deleteMilestone && <DeleteMilestoneModal detail={detail} milestone={deleteMilestone} onClose={() => setDeleteMilestone(null)} />}
  </section>;
}
