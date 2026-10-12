import { Circle, CircleCheck, CircleDot, RotateCcw, type LucideIcon } from 'lucide-react';
import { AdminSection } from '../shell/AdminSection';
import { revisionLabel, type EvaluationPeriodData, type EvaluationRevision } from '../evaluationSettings';
import { ChecksumCopy } from './EvaluationChecksumCopy';
import { versionEntry, type VersionEntry } from './evaluationHistoryEntries';

export type EvaluationHistoryProps = {
  history: EvaluationPeriodData['history'];
  revisions: readonly EvaluationRevision[];
  periodLoading: boolean;
  monthName: string;
  busy: boolean;
  onRequestRollback: (revisionId: string) => void;
};

const VERSION_ICON: Record<string, LucideIcon> = {
  approved: CircleCheck,
  draft: CircleDot,
};

const MARKER = 'flex size-6 shrink-0 items-center justify-center rounded-full bg-[var(--bg-sunken)] text-[var(--text-secondary)]';

function VersionRow({ entry }: { entry: VersionEntry }) {
  const Icon = VERSION_ICON[entry.status] ?? Circle;
  return (
    <li className="flex min-w-0 gap-3">
      <span className={`mt-0.5 ${MARKER}`}><Icon size={14} aria-hidden="true" /></span>
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-[14px] font-bold text-[var(--text-primary)]">{entry.title}</p>
        <p className="text-xs capitalize text-[var(--text-secondary)]">{entry.detail}</p>
        {entry.checksum && entry.shortChecksum && <ChecksumCopy value={entry.checksum} short={entry.shortChecksum} subject={entry.title} />}
        {entry.sourceVersionId && <p className="truncate text-xs text-[var(--text-muted)]" title={`Built from ${entry.sourceVersionId}`}>Built from {entry.sourceVersionId}</p>}
      </div>
    </li>
  );
}

function RevisionRow({ item, busy, onRequestRollback }: { item: EvaluationRevision; busy: boolean; onRequestRollback: (revisionId: string) => void }) {
  const label = revisionLabel(item);
  return (
    <li className="flex min-w-0 items-center gap-3">
      <span className={MARKER}><RotateCcw size={14} aria-hidden="true" /></span>
      <p className="min-w-0 flex-1 truncate text-xs text-[var(--text-secondary)]" title={label}>{label}</p>
      {item.canRollback && <button type="button" onClick={() => onRequestRollback(item.id)} disabled={busy} className="min-h-[44px] shrink-0 rounded-lg border border-[var(--border-light)] px-3 text-xs font-bold text-[var(--text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary,#00A3E0)] disabled:cursor-not-allowed disabled:opacity-50 lg:!min-h-[32px]">Rollback</button>}
    </li>
  );
}

/**
 * The month's saved versions and revisions as a timeline, in the order they were received. Versions show a short
 * checksum with a copy action; revisions keep their full label, truncated on one line.
 */
export function EvaluationHistory({ history, revisions, periodLoading, monthName, busy, onRequestRollback }: EvaluationHistoryProps) {
  const empty = history.length === 0 && revisions.length === 0;
  return (
    <AdminSection title="History">
      {periodLoading && <p className="text-xs text-[var(--text-muted)]">Loading this month…</p>}
      {!periodLoading && empty && <p className="text-xs text-[var(--text-secondary)]">No saved versions for this month.</p>}
      {!periodLoading && !empty && <ol className="space-y-4">
        {history.map((item) => <VersionRow key={item.id} entry={versionEntry(item, monthName)} />)}
        {revisions.map((item) => <RevisionRow key={item.id} item={item} busy={busy} onRequestRollback={onRequestRollback} />)}
      </ol>}
    </AdminSection>
  );
}
