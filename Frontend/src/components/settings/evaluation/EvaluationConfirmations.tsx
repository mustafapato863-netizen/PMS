import type { EvaluationRevision } from '../evaluationSettings';
import { ROLLBACK_CONFIRM_NOTE } from '../monthlyCorrection';

export type EvaluationConfirmationsProps = {
  adoptPending: boolean;
  dirty: boolean;
  approved: boolean;
  busy: boolean;
  monthName: string;
  year: number;
  scopeLabel: string;
  onConfirmAdopt: () => void;
  onKeepAdopt: () => void;
  deletePending: boolean;
  onConfirmDelete: () => void;
  onKeepDraft: () => void;
  rollbackRevision: EvaluationRevision | undefined;
  onConfirmRollback: (revision: EvaluationRevision) => void;
  onKeepRecords: () => void;
};

/** The three confirm steps. Each one appears only after its button is pressed, and each changes nothing until confirmed. */
export function EvaluationConfirmations(props: EvaluationConfirmationsProps) {
  const { adoptPending, dirty, approved, busy, monthName, year, scopeLabel, deletePending, rollbackRevision } = props;
  return (
    <>
      {adoptPending && <div role="group" aria-label="Switch to original upload settings" className="space-y-2 rounded-xl border border-[var(--border-light)] p-3">
        <p className="text-xs text-[var(--text-secondary)]">{dirty
          ? `Unsaved target and weight edits for ${monthName} ${year} are discarded only after you confirm. Switching uses the original uploader's supported indicators, targets, and weights for this month. Approved results and history stay unchanged until you preview, approve, and Apply. Other months stay unchanged.`
          : `Switching uses the original uploader's supported indicators, targets, and weights for ${scopeLabel}, ${monthName} ${year}. ${approved ? 'The approved version stays in history and a new draft is created.' : 'This draft is updated for this month only.'} Approved results stay unchanged until you preview, approve, and Apply. Nothing changes until you confirm.`}</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={props.onConfirmAdopt} disabled={busy} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:opacity-50">Confirm switch</button>
          <button type="button" onClick={props.onKeepAdopt} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold">Keep current settings</button>
        </div>
      </div>}
      {deletePending && <div role="group" aria-label="Delete draft confirmation" className="space-y-2 rounded-xl border border-red-500/30 p-3">
        <p className="text-xs text-[var(--text-secondary)]">This draft and any unsaved edits will be removed. Approved versions and existing scores are not changed. This cannot be undone.</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={props.onConfirmDelete} disabled={busy} className="rounded-xl border border-red-500/40 px-3 py-2 text-xs font-bold text-red-600 disabled:opacity-50">Delete draft</button>
          <button type="button" onClick={props.onKeepDraft} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold">Keep draft</button>
        </div>
      </div>}
      {rollbackRevision && <div role="group" aria-label="Rollback confirmation" className="space-y-2 rounded-xl border border-[var(--border-light)] p-3">
        <p className="text-xs text-[var(--text-secondary)]">{ROLLBACK_CONFIRM_NOTE}</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => props.onConfirmRollback(rollbackRevision)} disabled={busy} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:opacity-50">Restore saved values</button>
          <button type="button" onClick={props.onKeepRecords} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold">Keep current records</button>
        </div>
      </div>}
    </>
  );
}
