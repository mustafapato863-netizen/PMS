import { History } from 'lucide-react';
import { revisionLabel, versionLabel, type EvaluationPeriodData, type EvaluationRevision } from '../evaluationSettings';

export type EvaluationHistoryProps = {
  history: EvaluationPeriodData['history'];
  revisions: readonly EvaluationRevision[];
  periodLoading: boolean;
  monthName: string;
  busy: boolean;
  onRequestRollback: (revisionId: string) => void;
};

/** The month's saved versions and revisions, with a rollback request on the revisions that allow one. */
export function EvaluationHistory({ history, revisions, periodLoading, monthName, busy, onRequestRollback }: EvaluationHistoryProps) {
  return (
    <section className="min-w-0">
      <h3 className="mb-2 flex items-center gap-2 text-lg font-black text-[var(--text-primary)]"><History size={16} aria-hidden="true" />History</h3>
      <ul className="space-y-2 text-xs [overflow-wrap:anywhere] text-[var(--text-secondary)]">
        {periodLoading && <li>Loading this month…</li>}
        {!periodLoading && history.map((item) => <li key={item.id}>{versionLabel(item, monthName)}</li>)}
        {!periodLoading && revisions.map((item) => <li key={item.id} className="flex flex-wrap items-center gap-2">
          <span>{revisionLabel(item)}</span>
          {item.canRollback && <button type="button" onClick={() => onRequestRollback(item.id)} disabled={busy} className="rounded-lg border border-[var(--border-light)] px-2 py-1 text-xs font-bold disabled:opacity-50">Rollback</button>}
        </li>)}
        {!periodLoading && !history.length && !revisions.length && <li>No saved versions for this month.</li>}
      </ul>
    </section>
  );
}
