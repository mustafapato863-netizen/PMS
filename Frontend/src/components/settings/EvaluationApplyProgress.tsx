import { AlertTriangle, Check, Clock, Play, RefreshCw } from 'lucide-react';
import {
  CANCEL_CONFIRM_NOTE,
  failureReasonText,
  type ApplyJobActions,
  type ApplyJobPresentation,
  type ApplyJobSnapshot,
} from './evaluationApplyJobs';

const actionButtonClass = 'rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-xs font-bold text-[var(--text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary,#00A3E0)] disabled:cursor-not-allowed disabled:opacity-50';

type EvaluationApplyProgressProps = {
  job: ApplyJobSnapshot;
  presentation: ApplyJobPresentation;
  actions: ApplyJobActions;
  confirmCancel: boolean;
  busy: boolean;
  onArmCancel: () => void;
  onConfirmCancel: () => void;
  onDismissCancel: () => void;
  onRetry: () => void;
  onRecover: () => void;
};

export function EvaluationApplyProgress({
  job,
  presentation,
  actions,
  confirmCancel,
  busy,
  onArmCancel,
  onConfirmCancel,
  onDismissCancel,
  onRetry,
  onRecover,
}: EvaluationApplyProgressProps) {
  const titleId = `apply-job-${job.jobId}-title`;
  const reason = failureReasonText(job.safeReason);
  return (
    <section aria-labelledby={titleId} className="min-w-0 w-full max-w-full space-y-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-3">
      <h3 id={titleId} className="flex min-w-0 items-center gap-2 text-xs font-black text-[var(--text-primary)]">
        <ApplyPhaseIcon phase={presentation.phase} />
        <span className="break-words">{presentation.title}</span>
      </h3>
      <p role="status" className="break-words text-xs text-[var(--text-secondary)]">{presentation.detail}</p>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={presentation.percent}
        aria-valuetext={presentation.valueText}
        aria-labelledby={titleId}
        className="h-2 w-full overflow-hidden rounded-full bg-[var(--bg-sunken)]"
      >
        <div className="h-full bg-[var(--sgh-cyan-primary,#00A3E0)]" style={{ width: `${presentation.percent}%` }} />
      </div>
      <p className="break-words text-xs text-[var(--text-muted)]">
        Staged {job.stagedCount ?? '—'}{job.expectedCount != null ? ` of ${job.expectedCount}` : ''}.
        {job.attemptCount != null ? ` Attempt ${job.attemptCount}.` : ''}
      </p>
      {reason && <p className="break-words text-xs text-[var(--text-secondary)]">{reason}</p>}
      {job.revisionId && <p className="break-words text-xs text-[var(--text-secondary)]">Revision {job.revisionId} is in this month&apos;s history. Rollback remains on the latest revision only.</p>}
      {actions.retryNote && <p className="break-words text-xs text-[var(--text-secondary)]">{actions.retryNote}</p>}
      {actions.recoverNote && <p className="break-words text-xs text-[var(--text-secondary)]">{actions.recoverNote}</p>}
      {actions.cancelNote && <p className="break-words text-xs text-[var(--text-secondary)]">{actions.cancelNote}</p>}
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:flex-wrap">
        {actions.showCancel && !confirmCancel && <button type="button" onClick={onArmCancel} disabled={busy} className={actionButtonClass}>Cancel background apply</button>}
        {actions.showRetry && <button type="button" onClick={onRetry} disabled={busy} className={`${actionButtonClass} inline-flex items-center gap-1`}><RefreshCw size={14} aria-hidden="true" /> Retry this job</button>}
        {actions.showRecover && <button type="button" onClick={onRecover} disabled={busy} className={actionButtonClass}>Acknowledge committed revision</button>}
      </div>
      {confirmCancel && <div role="group" aria-label="Cancel background apply" className="min-w-0 space-y-2 rounded-xl border border-red-500/30 p-3">
        <p className="break-words text-xs text-[var(--text-secondary)]">{CANCEL_CONFIRM_NOTE}</p>
        <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:flex-wrap">
          <button type="button" onClick={onConfirmCancel} disabled={busy} className={`${actionButtonClass} text-red-700`}>Cancel this apply</button>
          <button type="button" onClick={onDismissCancel} className={actionButtonClass}>Keep this apply</button>
        </div>
      </div>}
    </section>
  );
}

function ApplyPhaseIcon({ phase }: { phase: ApplyJobPresentation['phase'] }) {
  if (phase === 'queued') return <Clock size={16} aria-hidden="true" />;
  if (phase === 'staging' || phase === 'committing') return <Play size={16} aria-hidden="true" />;
  if (phase === 'failed' || phase === 'cancelled') return <AlertTriangle size={16} aria-hidden="true" />;
  return <Check size={16} aria-hidden="true" />;
}
