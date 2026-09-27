import { useState } from 'react';
import type { ActionStatus } from '../../types';
import { ACTION_STATUSES } from './dueBadge';

const STATUS_CLASS: Record<string, string> = {
  Open: 'bg-blue-500/10 text-blue-700 dark:text-blue-300',
  'In Progress': 'bg-amber-500/10 text-amber-700 dark:text-amber-300',
  Completed: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  Cancelled: 'bg-[var(--bg-sunken)] text-[var(--text-muted)]',
};

interface ActionStatusMenuProps {
  status: string;
  canEdit: boolean;
  ariaLabel: string;
  compact?: boolean;
  onChange: (update: { status: ActionStatus; completion_note?: string }) => Promise<unknown> | void;
}

export function ActionStatusMenu({ status, canEdit, ariaLabel, compact = false, onChange }: ActionStatusMenuProps) {
  const [pending, setPending] = useState<ActionStatus | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const current = (ACTION_STATUSES.includes(status as ActionStatus) ? status : 'Open') as ActionStatus;

  const commit = async (next: ActionStatus, completionNote?: string) => {
    setSaving(true);
    setError('');
    try {
      await onChange({ status: next, completion_note: completionNote });
      setPending(null);
      setNote('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Status update failed.');
    } finally {
      setSaving(false);
    }
  };

  const choose = (next: string) => {
    const value = next as ActionStatus;
    if (value === 'Completed' || value === 'Cancelled') {
      setPending(value);
      setNote('');
      setError('');
      return;
    }
    void commit(value);
  };

  const submitNote = () => {
    if (!pending) return;
    if (note.trim().length < 3) {
      setError(pending === 'Completed' ? 'A completion note of at least 3 characters is required.' : 'A cancellation reason of at least 3 characters is required.');
      return;
    }
    void commit(pending, note.trim());
  };

  return (
    <>
      {canEdit ? (
        <select
          aria-label={ariaLabel}
          value={current}
          disabled={saving}
          onChange={(event) => choose(event.target.value)}
          className={`rounded-lg border border-[var(--border-light)] bg-[var(--bg-surface)] font-bold text-[var(--text-primary)] ${compact ? 'min-h-8 px-2 text-[10px]' : 'min-h-10 px-2 text-xs'}`}
        >
          {ACTION_STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
      ) : (
        <span className={`inline-flex items-center rounded-full px-2 py-1 font-black uppercase tracking-wide ${compact ? 'text-[9px]' : 'text-[10px]'} ${STATUS_CLASS[current]}`}>{current}</span>
      )}
      {pending && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-900/50 p-4" role="presentation">
          <div role="dialog" aria-modal="true" aria-labelledby="action-status-note-title" className="glass-card w-full max-w-md rounded-2xl p-5 shadow-xl">
            <h2 id="action-status-note-title" className="text-base font-black text-[var(--text-primary)]">
              {pending === 'Completed' ? 'Complete this action' : 'Cancel this action'}
            </h2>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              {pending === 'Completed' ? 'Add a completion note before closing the action.' : 'Add the reason for cancelling this action.'}
            </p>
            <label className="mt-4 block text-xs font-bold text-[var(--text-secondary)]" htmlFor="action-status-note">Note</label>
            <textarea
              id="action-status-note"
              value={note}
              onChange={(event) => { setNote(event.target.value); if (error) setError(''); }}
              rows={3}
              className="mt-1 w-full rounded-xl border border-[var(--border-medium)] bg-[var(--bg-sunken)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-blue-500"
            />
            {error && <p role="alert" className="mt-2 text-xs font-semibold text-rose-600">{error}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setPending(null)} className="min-h-10 rounded-xl border border-[var(--border-light)] px-3 text-xs font-bold text-[var(--text-secondary)]">Back</button>
              <button type="button" onClick={submitNote} disabled={saving} className="min-h-10 rounded-xl bg-blue-600 px-3 text-xs font-bold text-white disabled:opacity-70">Save status</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function StatusPill({ status }: { status: string }) {
  const current = status || 'Open';
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-black uppercase tracking-wide ${STATUS_CLASS[current] || STATUS_CLASS.Open}`}>{current}</span>;
}
