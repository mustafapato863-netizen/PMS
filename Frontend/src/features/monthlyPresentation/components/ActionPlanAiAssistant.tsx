import { useState } from 'react';
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, Sparkles, X } from 'lucide-react';
import { ApiError } from '../../../lib/apiClient';
import {
  enableCorrectiveActionPilotSetting,
  isPilotDisabled403,
  useCanUseActionPlanAi,
  type ActionPlanAiError,
  type AiCorrectiveActionSuggestionPayload,
} from './actionPlanAiUtils';

export interface AiRecommendIconButtonProps {
  loading?: boolean;
  disabled?: boolean;
  presentationMode?: boolean;
  onClick: () => void;
  title?: string;
  ariaLabel?: string;
  compact?: boolean;
  className?: string;
}

export function AiRecommendIconButton({
  loading = false,
  disabled = false,
  presentationMode = false,
  onClick,
  title = 'Generate AI corrective-action draft',
  ariaLabel = 'Generate AI recommendation',
  compact = false,
  className = '',
}: AiRecommendIconButtonProps) {
  const { canEditActions } = useCanUseActionPlanAi(presentationMode);
  if (!canEditActions) return null;

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || loading}
      aria-label={ariaLabel}
      aria-busy={loading}
      title={title}
      className={`inline-flex items-center gap-1 rounded border border-indigo-200 bg-indigo-50/80 px-2 py-1 text-xs font-medium text-indigo-700 transition-colors hover:border-indigo-300 hover:bg-indigo-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
    >
      {loading ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-600" aria-hidden="true" />
      ) : (
        <Sparkles className="h-3.5 w-3.5 text-indigo-600" aria-hidden="true" />
      )}
      <span>{loading ? 'Drafting…' : compact ? 'AI' : 'AI Draft'}</span>
    </button>
  );
}

export interface AiRecommendationBannerProps {
  loading?: boolean;
  payload?: AiCorrectiveActionSuggestionPayload | null;
  error?: ActionPlanAiError | null;
  needsOverwriteConfirm?: boolean;
  draftApplied?: boolean;
  presentationMode?: boolean;
  onApplyDraft: () => void;
  onDiscard: () => void;
  onRetry: () => void;
}

export function AiRecommendationBanner({
  loading = false,
  payload = null,
  error = null,
  needsOverwriteConfirm = false,
  draftApplied = false,
  presentationMode = false,
  onApplyDraft,
  onDiscard,
  onRetry,
}: AiRecommendationBannerProps) {
  const { canEditActions, isAdmin } = useCanUseActionPlanAi(presentationMode);
  const [enablingPilot, setEnablingPilot] = useState(false);
  const [enableError, setEnableError] = useState<string | null>(null);

  if (!canEditActions) return null;
  if (!loading && !payload && !error) return null;

  if (loading) {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label="Generating AI corrective-action draft"
        className="mt-2.5 rounded-lg border border-indigo-200/80 bg-indigo-50/50 p-3"
      >
        <div className="flex items-center gap-2 text-xs font-medium text-indigo-800">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-600" aria-hidden="true" />
          <span>Analyzing multi-month KPI evidence and drafting recommendation…</span>
        </div>
        <div className="mt-2.5 space-y-2 animate-pulse" aria-hidden="true">
          <div className="h-3 w-2/3 rounded bg-indigo-200/60" />
          <div className="h-3 w-full rounded bg-indigo-200/50" />
          <div className="h-3 w-4/5 rounded bg-indigo-200/40" />
        </div>
      </div>
    );
  }

  if (error) {
    const pilotBlocked = isPilotDisabled403(error);
    const handleEnableAndRetry = async () => {
      setEnablingPilot(true);
      setEnableError(null);
      try {
        await enableCorrectiveActionPilotSetting();
        onRetry();
      } catch (err) {
        const msg =
          err instanceof ApiError || err instanceof Error
            ? err.message
            : 'Could not enable AI Corrective Action Pilot.';
        setEnableError(msg);
      } finally {
        setEnablingPilot(false);
      }
    };

    return (
      <div
        role="alert"
        className="mt-2.5 rounded-lg border border-rose-200 bg-rose-50/70 p-3 text-xs text-rose-900"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" aria-hidden="true" />
            <div>
              <p className="font-semibold text-rose-950">
                {pilotBlocked
                  ? 'AI Corrective Action Pilot is currently disabled'
                  : 'Could not generate AI recommendation'}
              </p>
              <p className="mt-0.5 text-rose-800">
                {pilotBlocked && !isAdmin
                  ? 'Ask an Administrator to enable the AI Corrective Action Pilot in Settings.'
                  : error.message}
              </p>
              {enableError && (
                <p className="mt-1 font-medium text-rose-700">{enableError}</p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onDiscard}
            aria-label="Dismiss AI error"
            className="rounded p-1 text-rose-700 hover:bg-rose-100"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          {pilotBlocked && isAdmin && (
            <button
              type="button"
              disabled={enablingPilot}
              onClick={handleEnableAndRetry}
              className="inline-flex items-center gap-1.5 rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
            >
              {enablingPilot && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
              <span>{enablingPilot ? 'Enabling Pilot…' : 'Enable AI Pilot & Generate'}</span>
            </button>
          )}
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1 rounded border border-rose-300 bg-white px-2.5 py-1 text-xs font-medium text-rose-800 hover:bg-rose-50"
          >
            <RefreshCw className="h-3 w-3" aria-hidden="true" />
            <span>Retry</span>
          </button>
        </div>
      </div>
    );
  }

  if (!payload) return null;

  const providerLabel =
    payload.provider_used === 'cloudflare'
      ? 'Cloudflare AI'
      : payload.provider_used === 'gemini'
        ? 'Gemini Fallback'
        : 'Evidence Check';

  const measuredFacts = Array.isArray(payload.measured_facts) ? payload.measured_facts : [];

  if (payload.outcome !== 'suggested' || !payload.draft) {
    const reasons = [
      ...(Array.isArray(payload.insufficient_evidence_reasons) ? payload.insufficient_evidence_reasons : []),
      ...(Array.isArray(payload.evidence_limitations) ? payload.evidence_limitations : []),
    ].filter(Boolean);
    return (
      <div
        role="status"
        className="mt-2.5 rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-950"
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold">
              {payload.outcome === 'insufficient_evidence'
                ? 'Insufficient KPI evidence for an AI draft'
                : 'AI draft unavailable for this record'}
            </p>
            {reasons.length > 0 && (
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-amber-900">
                {reasons.map((reason, idx) => (
                  <li key={`${idx}-${reason.slice(0, 20)}`}>{reason}</li>
                ))}
              </ul>
            )}
          </div>
          <button
            type="button"
            onClick={onDiscard}
            aria-label="Dismiss AI notice"
            className="rounded p-1 text-amber-800 hover:bg-amber-100"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
        {measuredFacts.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {measuredFacts.map((fact, idx) => (
              <span
                key={`${idx}-${fact.slice(0, 18)}`}
                className="rounded border border-amber-200 bg-white px-2 py-0.5 text-xs text-amber-900"
              >
                {fact}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      role="region"
      aria-label="AI corrective action draft"
      className="mt-2.5 rounded-lg border border-indigo-200 bg-indigo-50/40 p-3 text-xs text-slate-800"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-900">
            <Sparkles className="h-3 w-3 text-amber-700" aria-hidden="true" />
            <span>Unapproved AI Draft — review &amp; click Save to apply</span>
          </span>
          <span className="rounded-full border border-indigo-200 bg-white px-2 py-0.5 text-xs font-medium text-indigo-700">
            {providerLabel}
          </span>
          {draftApplied && !needsOverwriteConfirm && (
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
              <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
              <span>Populated in editor</span>
            </span>
          )}
        </div>
        {!needsOverwriteConfirm && (
          <button
            type="button"
            onClick={onDiscard}
            aria-label="Discard Draft"
            className="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            <X className="h-3 w-3" aria-hidden="true" />
            <span>Discard Draft</span>
          </button>
        )}
      </div>

      {measuredFacts.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {measuredFacts.map((fact, idx) => (
            <span
              key={`${idx}-${fact.slice(0, 18)}`}
              className="rounded border border-slate-200 bg-white px-2 py-0.5 text-xs text-slate-700"
            >
              {fact}
            </span>
          ))}
        </div>
      )}

      {needsOverwriteConfirm ? (
        <div className="mt-2.5 rounded border border-amber-300 bg-amber-50 p-2.5 text-xs text-amber-950">
          <p className="font-semibold">
            You have unsaved manual edits on this card. Replace your draft with this AI recommendation?
          </p>
          <p className="mt-1 text-amber-900">
            <span className="font-medium">AI Focus ({payload.draft.focus_kpi_name}):</span>{' '}
            {payload.draft.recommended_steps.join(' ')}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onApplyDraft}
              className="rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700"
            >
              Apply AI Draft
            </button>
            <button
              type="button"
              onClick={onDiscard}
              className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              Discard Draft
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-2 space-y-1 text-slate-700">
          <p className="font-medium text-slate-900">
            {payload.draft.title} <span className="font-normal text-slate-500">({payload.draft.focus_kpi_name})</span>
          </p>
          <p className="text-slate-600">{payload.draft.measured_issue}</p>
          {payload.draft.uncertainty && (
            <p className="text-amber-800">{payload.draft.uncertainty}</p>
          )}
          {!draftApplied && (
            <div className="pt-1">
              <button
                type="button"
                onClick={onApplyDraft}
                className="rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700"
              >
                Apply AI Draft
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
