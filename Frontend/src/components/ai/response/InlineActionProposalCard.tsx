import { useState } from 'react';
import { Check, ClipboardCheck, Loader2 } from 'lucide-react';
import { apiFetch } from '../../../lib/apiClient';
import type {
  AiCorrectiveActionConfirmRequest,
  AiCorrectiveActionConfirmResponse,
  AiCorrectiveActionProposal,
} from '../../../features/ai/types';

interface InlineActionProposalCardProps {
  proposal: AiCorrectiveActionProposal;
  traceId?: string;
  canCreateAction?: boolean;
  isFallbackData?: boolean;
  onActionSaved?: () => void;
}

export default function InlineActionProposalCard({
  proposal,
  traceId,
  canCreateAction = true,
  isFallbackData = false,
  onActionSaved,
}: InlineActionProposalCardProps) {
  const [isReviewing, setIsReviewing] = useState(false);
  const [actionType, setActionType] = useState<AiCorrectiveActionConfirmRequest['action_type']>(
    proposal.action_type || 'Coaching',
  );
  const [priority, setPriority] = useState<'Low' | 'Medium' | 'High'>(
    proposal.priority || 'Medium',
  );
  const [actionText, setActionText] = useState(proposal.proposed_action_text || '');
  const [rootCauseNote, setRootCauseNote] = useState(proposal.proposed_root_cause_note || '');
  const [dueDate, setDueDate] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAction, setSavedAction] = useState<AiCorrectiveActionConfirmResponse | null>(null);

  const handleConfirm = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const payload: AiCorrectiveActionConfirmRequest = {
        proposal_id: proposal.proposal_id,
        team: proposal.team,
        month: proposal.month,
        year: proposal.year,
        employee_id: proposal.employee_id ?? null,
        linked_kpi_key: proposal.linked_kpi_key ?? null,
        action_type: actionType,
        action_text: actionText.trim(),
        root_cause_note: rootCauseNote.trim(),
        priority,
        due_date: dueDate ? dueDate : null,
        evidence_revision: proposal.evidence_revision,
        is_fallback_data: isFallbackData,
        trace_id: traceId ?? null,
      };
      const saved = await apiFetch<AiCorrectiveActionConfirmResponse>(
        '/api/ai/proposals/confirm',
        {
          method: 'POST',
          body: JSON.stringify(payload),
        },
      );
      setSavedAction(saved);
      setIsReviewing(false);
      onActionSaved?.();
    } catch (err) {
      setSaveError(
        err instanceof Error
          ? err.message
          : 'Could not save corrective action. Please verify your permissions and try again.',
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      data-testid="contextual-assistant-proposal-card"
      className="mt-3.5 space-y-2.5 rounded-2xl border border-indigo-200/90 bg-indigo-50/40 p-3.5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-indigo-900">
          <ClipboardCheck className="size-4 text-indigo-600" />
          <span>Suggested Action Plan · {proposal.team}</span>
        </span>
        {proposal.metric_display_name && (
          <span className="rounded-md border border-indigo-200 bg-white px-2 py-0.5 text-xs font-semibold text-indigo-800">
            {proposal.metric_display_name} ({proposal.actual_display} vs {proposal.target_display})
          </span>
        )}
      </div>

      {proposal.observed_facts.length > 0 && (
        <div className="space-y-1">
          <span className="text-xs font-semibold text-slate-500">Observed PMS Facts</span>
          <ul className="list-disc space-y-1 pl-4 text-sm text-slate-700">
            {proposal.observed_facts.map((fact, idx) => (
              <li key={idx}>{fact}</li>
            ))}
          </ul>
        </div>
      )}

      {proposal.hypothesis && (
        <div className="rounded-xl border border-indigo-100 bg-white/80 px-3 py-2 text-xs text-slate-600">
          <span className="font-bold text-slate-700">Hypothesis to verify: </span>
          <span>{proposal.hypothesis}</span>
        </div>
      )}

      {savedAction ? (
        <div
          data-testid="contextual-assistant-saved-action-status"
          className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-800"
        >
          <Check className="size-4 shrink-0 text-emerald-600" />
          <span>Action saved with status: {savedAction.persisted_status}</span>
        </div>
      ) : proposal.can_user_create_action && canCreateAction ? (
        !isReviewing ? (
          <button
            type="button"
            data-testid="contextual-assistant-review-action-btn"
            onClick={() => setIsReviewing(true)}
            className="inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-xl bg-indigo-600 px-3.5 py-2 text-xs font-bold text-white transition-colors hover:bg-indigo-700"
          >
            <ClipboardCheck className="size-3.5" />
            <span>Review & Assign Action</span>
          </button>
        ) : (
          <div
            data-testid="contextual-assistant-proposal-form"
            className="space-y-2.5 border-t border-indigo-200/80 pt-3"
          >
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
              <label className="block space-y-1">
                <span className="text-xs font-semibold text-slate-600">Action Type</span>
                <select
                  aria-label="Action Type"
                  value={actionType}
                  onChange={(e) =>
                    setActionType(
                      e.target.value as AiCorrectiveActionConfirmRequest['action_type'],
                    )
                  }
                  className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-800"
                >
                  <option value="Coaching">Coaching</option>
                  <option value="Training">Training</option>
                  <option value="Monitor">Monitor</option>
                  <option value="PIP">PIP</option>
                </select>
              </label>

              <label className="block space-y-1">
                <span className="text-xs font-semibold text-slate-600">Priority</span>
                <select
                  aria-label="Priority"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value as 'Low' | 'Medium' | 'High')}
                  className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-800"
                >
                  <option value="High">High</option>
                  <option value="Medium">Medium</option>
                  <option value="Low">Low</option>
                </select>
              </label>

              <label className="block space-y-1">
                <span className="text-xs font-semibold text-slate-600">Due Date (Optional)</span>
                <input
                  type="date"
                  aria-label="Due Date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-800"
                />
              </label>
            </div>

            <label className="block space-y-1">
              <span className="text-xs font-semibold text-slate-600">
                Action Plan (Saved as Open Action)
              </span>
              <textarea
                aria-label="Action Plan"
                rows={2}
                value={actionText}
                onChange={(e) => setActionText(e.target.value)}
                className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-800"
              />
            </label>

            <label className="block space-y-1">
              <span className="text-xs font-semibold text-slate-600">
                Root Cause Note (To Verify)
              </span>
              <textarea
                aria-label="Root Cause Note"
                rows={2}
                value={rootCauseNote}
                onChange={(e) => setRootCauseNote(e.target.value)}
                className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-800"
              />
            </label>

            {saveError && (
              <p role="alert" className="text-xs font-semibold text-rose-600">
                {saveError}
              </p>
            )}

            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                type="button"
                data-testid="contextual-assistant-cancel-proposal-btn"
                onClick={() => {
                  setIsReviewing(false);
                  setSaveError(null);
                }}
                className="cursor-pointer rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={saving || !actionText.trim()}
                data-testid="contextual-assistant-confirm-proposal-btn"
                onClick={() => void handleConfirm()}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {saving && <Loader2 className="size-3.5 animate-spin" />}
                <span>{saving ? 'Saving…' : 'Confirm Open Action'}</span>
              </button>
            </div>
          </div>
        )
      ) : null}
    </div>
  );
}
