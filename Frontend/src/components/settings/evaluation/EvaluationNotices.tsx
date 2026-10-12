import { AlertCircle } from 'lucide-react';
import { CHECKING_APPLY_NOTE } from '../evaluationApplyJobs';
import { READ_ONLY_APPROVED_NOTE, UNSAVED_PREVIEW_NOTE, UNSUPPORTED_FORMULA_NOTE, type EvaluationLine } from '../evaluationSettings';
import { MISSING_CHECKSUM_MESSAGE } from './evaluationMessages';
import { dedupedNote } from './evaluationNotes';
import type { ApplyMode } from './evaluationWorkflowState';

const RETRY_BUTTON = 'rounded-xl border border-red-500/30 px-3 py-2 text-xs font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary,#00A3E0)]';
const ALERT_STACK = 'space-y-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-xs font-semibold text-red-600';

export type MissingIndicatorItem = { kpiKey: string; count: number };

export type EvaluationAlertsProps = {
  error: string;
  missing: readonly MissingIndicatorItem[];
  lines: readonly EvaluationLine[];
  message: string;
  applyMode: ApplyMode;
  unavailableMessage: string | null | undefined;
  onRetryAvailability: () => void;
  backgroundNote: string | null;
  problem: string | null | undefined;
  onRefreshJob: () => void;
};

/** Top-of-panel alerts and status lines. The error alert is the panel's only role=alert in the normal case. */
export function EvaluationAlerts(props: EvaluationAlertsProps) {
  const { error, missing, lines, message, applyMode, unavailableMessage, backgroundNote, problem } = props;
  return (
    <>
      {error && <div role="alert" className="flex items-start gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-xs font-semibold text-red-600">
        <AlertCircle size={16} className="shrink-0" aria-hidden="true" />
        {missing.length ? <div className="space-y-2">
          <p>Some scored indicators are missing saved values. Your draft is still editable; approval and application are blocked until this is resolved.</p>
          <ul className="list-disc space-y-1 pl-4">{missing.map((item) => <li key={item.kpiKey}>{lines.find((line) => line.kpi_key === item.kpiKey)?.label || item.kpiKey}: {item.count} {item.count === 1 ? 'record needs' : 'records need'} a saved actual value.</li>)}</ul>
          <p>If an indicator is only for monitoring, choose tracking only and adjust the other weights to total 100%. Otherwise, its saved values must be restored before scoring.</p>
        </div> : error}
      </div>}
      {message && <p className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-xs font-semibold text-emerald-700" role="status">{message}</p>}
      {applyMode === 'pending' && <p role="status" className="text-xs text-[var(--text-muted)]">{CHECKING_APPLY_NOTE}</p>}
      {applyMode === 'unavailable' && <div role="alert" className={ALERT_STACK}>
        <p>{unavailableMessage}</p>
        <button type="button" onClick={props.onRetryAvailability} className={RETRY_BUTTON}>Retry availability check</button>
      </div>}
      {backgroundNote && <p role="status" className="break-words rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-4 py-3 text-xs text-[var(--text-secondary)]">{backgroundNote}</p>}
      {problem && <div role="alert" className={ALERT_STACK}>
        <p>{problem}</p>
        <button type="button" onClick={props.onRefreshJob} className={RETRY_BUTTON}>Refresh background apply</button>
      </div>}
    </>
  );
}

export type EvaluationSettingsNotesProps = {
  blocked: boolean;
  /** The contract label, or null when the period has no contract. */
  settingsSource: string | null;
  monthName: string;
  year: number;
  level: string;
  /** Shows the switch explanation. The switch button itself is in the actions, under Draft management. */
  canAdopt: boolean;
  blockReason: string | null | undefined;
  historyNote: string | null | undefined;
};

/** Where this month's settings come from, what the switch to the original upload settings does, and a blocked scope's reason. */
export function EvaluationSettingsNotes(props: EvaluationSettingsNotesProps) {
  const { blocked, settingsSource, monthName, year, level, canAdopt, blockReason, historyNote } = props;
  return (
    <>
      {!blocked && settingsSource && <p role="status" className="text-xs font-semibold text-[var(--text-secondary)]">Settings source: {settingsSource} · {monthName} {year} · {level}</p>}
      {!blocked && canAdopt && <p role="status" className="text-xs text-[var(--text-secondary)]">Switching uses the original uploader&apos;s supported indicators, targets, and weights for this month. Approved results and history stay unchanged until you preview, approve, and Apply. Unsaved edits are discarded only after you confirm.</p>}
      {blocked && <div role="status" className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-800">{blockReason} {historyNote}</div>}
    </>
  );
}

export type EvaluationDraftNotesProps = {
  blocked: boolean;
  approved: boolean;
  checksumMissing: boolean;
  conflictText: string;
  dirty: boolean;
  unsupported: boolean;
  sourceVersionId: string | null | undefined;
  sourceChecksum: string | null | undefined;
  notes: string | null | undefined;
  onReload: () => void;
  onDiscard: () => void;
};

/** Notes about the draft or approved month under the action buttons. Repeated sentences in the stored notes show once. */
export function EvaluationDraftNotes(props: EvaluationDraftNotesProps) {
  const { blocked, approved, checksumMissing, conflictText, dirty, unsupported, sourceVersionId, sourceChecksum, notes } = props;
  return (
    <>
      {!blocked && approved && <p role="status" className="text-xs text-[var(--text-secondary)]">{READ_ONLY_APPROVED_NOTE}</p>}
      {!blocked && checksumMissing && <p role="status" className="text-xs font-semibold text-amber-800">{MISSING_CHECKSUM_MESSAGE}</p>}
      {!blocked && conflictText && <p role="status" className="text-xs font-semibold text-[var(--text-secondary)]">{conflictText}</p>}
      {!blocked && conflictText && <div className="flex flex-wrap gap-2">
        <button type="button" onClick={props.onReload} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold">Reload draft</button>
        <button type="button" onClick={props.onDiscard} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold">Discard edits</button>
      </div>}
      {!blocked && dirty && <p role="status" className="text-xs font-semibold text-[var(--text-secondary)]">{UNSAVED_PREVIEW_NOTE}</p>}
      {!blocked && unsupported && <p role="status" className="text-xs font-semibold text-amber-800">{UNSUPPORTED_FORMULA_NOTE}</p>}
      {!!sourceVersionId && <p className="text-xs [overflow-wrap:anywhere] text-[var(--text-secondary)]">Source version {sourceVersionId}{sourceChecksum ? ` · source checksum ${sourceChecksum}` : ''}. The source version remains in this month&apos;s history.</p>}
      {!!notes && <p className="text-xs text-[var(--text-muted)]">{dedupedNote(notes)}</p>}
    </>
  );
}
