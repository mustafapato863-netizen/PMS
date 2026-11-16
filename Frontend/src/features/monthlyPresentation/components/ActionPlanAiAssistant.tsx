import { useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, Loader2, RefreshCw, Sparkles, X } from 'lucide-react';
import { ApiError } from '../../../lib/apiClient';
import type { AgentKpiEvidenceItem, PriorActionSummary, WeakKpiContext } from '../teamDeepDiveData';
import {
  collectSuggestionNotices,
  enableCorrectiveActionPilotSetting,
  formatMeasuredFact,
  hasSupportedProjectedImpact,
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
      <span>{loading ? 'Drafting…' : compact ? 'Suggest' : 'Suggest action'}</span>
    </button>
  );
}

export interface AiStatusInlineProps {
  loading?: boolean;
  payload?: AiCorrectiveActionSuggestionPayload | null;
  error?: ActionPlanAiError | null;
  draftApplied?: boolean;
  presentationMode?: boolean;
  onRetry: () => void;
  onDismiss?: () => void;
}

/**
 * Renders a concise, single-sentence AI status indicator right beside Suggest action,
 * keeping provider errors, missing-evidence checks, and Retry out of the card body.
 */
export function AiStatusInline({
  loading = false,
  payload = null,
  error = null,
  draftApplied = false,
  presentationMode = false,
  onRetry,
  onDismiss,
}: AiStatusInlineProps) {
  const { canEditActions, isAdmin } = useCanUseActionPlanAi(presentationMode);
  const [enablingPilot, setEnablingPilot] = useState(false);
  const [enableError, setEnableError] = useState<string | null>(null);

  if (!canEditActions) return null;
  if (!loading && !payload && !error) return null;

  if (loading) {
    return (
      <span
        role="status"
        aria-busy="true"
        className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-700"
      >
        <span>Generating draft…</span>
      </span>
    );
  }

  if (error) {
    const pilotBlocked = isPilotDisabled403(error);
    const isUnauthorized = error.status === 401;
    const isForbidden = error.status === 403 && !pilotBlocked;

    const handleEnableAndRetry = async () => {
      setEnablingPilot(true);
      setEnableError(null);
      try {
        await enableCorrectiveActionPilotSetting();
        onRetry();
      } catch (err) {
        setEnableError(
          err instanceof ApiError || err instanceof Error
            ? err.message
            : 'Could not enable AI Corrective Action Pilot.',
        );
      } finally {
        setEnablingPilot(false);
      }
    };

    const statusText = pilotBlocked
      ? isAdmin
        ? 'AI Corrective Action Pilot is currently disabled.'
        : 'AI Pilot is disabled; ask an Administrator to enable it.'
      : isUnauthorized
        ? 'Sign in required to generate AI suggestions.'
        : isForbidden
          ? 'Permission required for AI suggestions.'
          : 'Could not generate AI recommendation.';

    return (
      <div role="alert" className="flex flex-wrap items-center gap-1.5 text-xs text-rose-800">
        <span>{enableError || statusText}</span>
        {!isUnauthorized && !isForbidden && (
          <>
            {pilotBlocked && isAdmin && (
              <button
                type="button"
                disabled={enablingPilot}
                onClick={handleEnableAndRetry}
                className="inline-flex items-center gap-1 rounded bg-indigo-600 px-2 py-0.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {enablingPilot && <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />}
                <span>{enablingPilot ? 'Enabling Pilot…' : 'Enable AI Pilot & Generate'}</span>
              </button>
            )}
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center gap-1 rounded border border-rose-300 bg-white px-2 py-0.5 text-xs font-medium text-rose-800 hover:bg-rose-50"
            >
              <RefreshCw className="h-3 w-3" aria-hidden="true" />
              <span>Retry</span>
            </button>
          </>
        )}
      </div>
    );
  }

  if (!payload) return null;

  if (payload.outcome === 'suggested') {
    if (!draftApplied) return null;
    return (
      <span role="status" className="text-xs font-medium text-emerald-700">
        Draft loaded in editor.
      </span>
    );
  }

  if (payload.outcome === 'insufficient_evidence') {
    const firstNotice = collectSuggestionNotices(payload)[0];
    const verifyText = firstNotice
      ? `Insufficient KPI evidence — verify source records: ${firstNotice}`
      : 'Insufficient KPI evidence — verify source records.';
    return (
      <div role="status" className="flex flex-wrap items-center gap-1.5 text-xs text-amber-900">
        <span>{verifyText}</span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss AI notice"
            className="rounded p-0.5 text-amber-800 hover:bg-amber-100"
          >
            <X className="h-3 w-3" aria-hidden="true" />
          </button>
        )}
      </div>
    );
  }

  const outcomeSentence =
    payload.outcome === 'model_unavailable'
      ? 'AI suggestion provider is temporarily unavailable.'
      : payload.outcome === 'draft_rejected'
        ? 'AI draft did not pass evidence verification.'
        : 'AI draft unavailable for this record.';

  return (
    <div role="status" className="flex flex-wrap items-center gap-1.5 text-xs text-amber-950">
      <span>{outcomeSentence}</span>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-1 rounded border border-amber-300 bg-white px-2 py-0.5 text-xs font-medium text-amber-900 hover:bg-amber-100"
      >
        <RefreshCw className="h-3 w-3" aria-hidden="true" />
        <span>Retry</span>
      </button>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss AI notice"
          className="rounded p-0.5 text-amber-800 hover:bg-amber-100"
        >
          <X className="h-3 w-3" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

export interface AiRecommendationBannerProps {
  loading?: boolean;
  payload?: AiCorrectiveActionSuggestionPayload | null;
  error?: ActionPlanAiError | null;
  needsOverwriteConfirm?: boolean;
  draftApplied?: boolean;
  presentationMode?: boolean;
  inlineStatusHandled?: boolean;
  onApplyDraft: () => void;
  onApplyEvidenceStep?: () => void;
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
  inlineStatusHandled = false,
  onApplyDraft,
  onApplyEvidenceStep,
  onDiscard,
  onRetry,
}: AiRecommendationBannerProps) {
  const { canEditActions, isAdmin } = useCanUseActionPlanAi(presentationMode);
  const [enablingPilot, setEnablingPilot] = useState(false);
  const [enableError, setEnableError] = useState<string | null>(null);

  if (!canEditActions) return null;
  if (!loading && !payload && !error) return null;

  if (loading) {
    if (inlineStatusHandled) return null;
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
      </div>
    );
  }

  if (error) {
    if (inlineStatusHandled) return null;
    const pilotBlocked = isPilotDisabled403(error);
    const isUnauthorized = error.status === 401;
    const isForbidden = error.status === 403 && !pilotBlocked;
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
                  : isUnauthorized
                    ? 'Sign in required to generate AI suggestions'
                    : isForbidden
                      ? 'Permission required for AI suggestions'
                      : 'Could not generate AI recommendation'}
              </p>
              <p className="mt-0.5 text-rose-800">
                {pilotBlocked && !isAdmin
                  ? 'Ask an Administrator to enable the AI Corrective Action Pilot in Settings.'
                  : isUnauthorized
                    ? 'Your session may have expired (401). Sign in again, or continue editing the action manually.'
                    : isForbidden
                      ? 'Your role does not have permission to invoke AI corrective action drafts (403). You can continue editing manually.'
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
        {!isUnauthorized && !isForbidden && (
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
        )}
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

  const measuredFacts = (Array.isArray(payload.measured_facts) ? payload.measured_facts : [])
    .map((fact) => formatMeasuredFact(fact, payload.supporting_kpis))
    .filter(Boolean);

  if (payload.outcome !== 'suggested' || !payload.draft) {
    const hasEvidenceStep = Boolean(payload.evidence_next_step && payload.outcome !== 'insufficient_evidence');
    if (inlineStatusHandled && !hasEvidenceStep) {
      return null;
    }

    const reasons = collectSuggestionNotices(payload);
    const canRetryOutcome =
      payload.outcome === 'model_unavailable' || payload.outcome === 'draft_rejected';
    const outcomeHeading =
      payload.outcome === 'insufficient_evidence'
        ? 'Insufficient KPI evidence — verify source records'
        : payload.outcome === 'model_unavailable'
          ? 'AI suggestion provider is temporarily unavailable'
          : payload.outcome === 'draft_rejected'
            ? 'AI draft did not pass evidence verification'
            : 'AI draft unavailable for this record';

    if (inlineStatusHandled && hasEvidenceStep) {
      return (
        <div
          role="region"
          aria-label="Suggested next step from PMS evidence"
          className="mt-2.5 rounded-lg border border-amber-200 bg-amber-50/60 p-3 text-xs text-slate-800"
        >
          <div className="flex items-start justify-between gap-2">
            <span className="inline-flex items-center rounded-full border border-amber-300 bg-white px-2 py-0.5 text-xs font-semibold text-amber-900">
              {payload.evidence_next_step_label || 'Suggested next step from PMS evidence'}
            </span>
            <button
              type="button"
              onClick={onDiscard}
              aria-label="Dismiss AI notice"
              className="rounded p-0.5 text-amber-800 hover:bg-amber-100"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
          <p className="mt-2 font-medium leading-relaxed text-slate-900">
            {payload.evidence_next_step}
          </p>
          {(payload.evidence_next_step_role || payload.evidence_next_step_follow_up) && (
            <p className="mt-1 text-xs text-slate-600">
              {[
                payload.evidence_next_step_role ? `Role: ${payload.evidence_next_step_role}` : null,
                payload.evidence_next_step_follow_up ? `Follow-up: ${payload.evidence_next_step_follow_up}` : null,
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
          )}
          {onApplyEvidenceStep && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={onApplyEvidenceStep}
                className="rounded bg-slate-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-800"
              >
                Use suggested step
              </button>
            </div>
          )}
        </div>
      );
    }

    return (
      <div
        role="status"
        className="mt-2.5 rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-950"
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold">{outcomeHeading}</p>
            {reasons.length > 0 && (
              <p className="mt-1 text-amber-900">{reasons[0]}</p>
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
        {hasEvidenceStep && (
          <div className="mt-2 rounded border border-amber-200 bg-white p-2.5 text-slate-800">
            <p className="text-xs font-semibold text-amber-900">
              {payload.evidence_next_step_label || 'Suggested next step from PMS evidence'}
            </p>
            <p className="mt-1 font-medium text-slate-900">{payload.evidence_next_step}</p>
            {onApplyEvidenceStep && (
              <button
                type="button"
                onClick={onApplyEvidenceStep}
                className="mt-2 rounded bg-slate-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-800"
              >
                Use suggested step
              </button>
            )}
          </div>
        )}
        {canRetryOutcome && (
          <div className="mt-2.5 flex items-center gap-2">
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center gap-1 rounded border border-amber-300 bg-white px-2.5 py-1 text-xs font-medium text-amber-900 hover:bg-amber-100"
            >
              <RefreshCw className="h-3 w-3" aria-hidden="true" />
              <span>Retry</span>
            </button>
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
          <div className="flex flex-wrap items-center gap-1.5">
            <p className="font-medium text-slate-900">
              {payload.draft.title}{' '}
              <span className="font-normal text-slate-500">({payload.draft.focus_kpi_name})</span>
            </p>
            {payload.draft.responsible_role && (
              <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-700">
                Role: {payload.draft.responsible_role}
              </span>
            )}
            {payload.draft.observation_status === 'unverified_zero' && (
              <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">
                Unverified 0.0% — verify source first
              </span>
            )}
          </div>
          <p className="text-slate-600">{payload.draft.measured_issue}</p>
          {payload.draft.official_target_label && (
            <p className="text-xs text-slate-600">
              <span className="font-semibold text-slate-700">Official KPI target:</span>{' '}
              {payload.draft.official_target_label}
              {payload.draft.action_milestone_note ? ` · ${payload.draft.action_milestone_note}` : ''}
            </p>
          )}
          {payload.draft.recommended_follow_up && (
            <p className="text-xs font-medium text-indigo-800">
              Follow-up: {payload.draft.recommended_follow_up}
            </p>
          )}
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

export function formatScoreChangeLabel(
  changeVsPrev: number | null | undefined,
  previousPeriodLabel: string | null | undefined,
): string {
  if (changeVsPrev === null || changeVsPrev === undefined || !Number.isFinite(changeVsPrev)) {
    return 'No prior period score';
  }
  const signed = `${changeVsPrev >= 0 ? '+' : ''}${changeVsPrev.toFixed(1)} pts`;
  return previousPeriodLabel ? `${signed} vs ${previousPeriodLabel}` : `${signed} vs prior period`;
}

export interface IndividualEvidenceDrawerProps {
  panelId: string;
  isOpen: boolean;
  employeeId: string;
  testIdPrefix: 'individual' | 'role-individual';
  changeVsPrev?: number | null;
  previousPeriodLabel?: string | null;
  previousIsAdjacent?: boolean;
  missingIntermediatePeriods?: string[];
  fullWindowComparisonLabel?: string | null;
  scoreTrendLabel?: string | null;
  weakKpis?: WeakKpiContext[];
  allKpiEvidence?: AgentKpiEvidenceItem[];
  priorActions?: PriorActionSummary[];
  expectedImpact: string;
  projectedAgentScoreLift?: number | null;
  linkedKpiLabel?: string;
  linkedKpiTarget?: string;
}

export function IndividualEvidenceDrawer({
  panelId,
  isOpen,
  employeeId,
  testIdPrefix,
  changeVsPrev,
  previousPeriodLabel,
  previousIsAdjacent = true,
  missingIntermediatePeriods = [],
  fullWindowComparisonLabel,
  scoreTrendLabel,
  weakKpis = [],
  allKpiEvidence = [],
  priorActions = [],
  expectedImpact,
  projectedAgentScoreLift,
  linkedKpiLabel,
  linkedKpiTarget,
}: IndividualEvidenceDrawerProps) {
  const trimmedImpact = String(expectedImpact ?? '').trim();
  const isNumericProjection = hasSupportedProjectedImpact(projectedAgentScoreLift);
  const showImpactLabel =
    linkedKpiLabel && linkedKpiTarget
      ? `Potential score lift if ${linkedKpiLabel} reaches ${linkedKpiTarget} target:`
      : 'Potential score lift:';
  const projectionDetail = isNumericProjection
    ? `+${projectedAgentScoreLift!.toFixed(1)} pts agent score (assuming other KPIs stay constant)`
    : '';
  const hasNeutralUnavailableNote =
    !isNumericProjection &&
    Boolean(trimmedImpact) &&
    !/^(?:—|-|n\/a|not specified|impact to be confirmed)$/i.test(trimmedImpact);

  return (
    <div
      id={panelId}
      data-testid={`${testIdPrefix}-evidence-drawer-${employeeId}`}
      hidden={!isOpen}
      className="mt-3 space-y-2.5 rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-700"
    >
      {/* Trend Comparisons */}
      <div className="space-y-1">
        <div className="font-bold uppercase tracking-wider text-slate-500">
          Performance Trend
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {scoreTrendLabel && (
            <span
              data-testid={`${testIdPrefix}-trend-badge-${employeeId}`}
              className="inline-flex items-center rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-700"
            >
              Trend: {scoreTrendLabel}
            </span>
          )}
          {changeVsPrev !== null && changeVsPrev !== undefined && (
            <span className="inline-flex items-center rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-700">
              {formatScoreChangeLabel(changeVsPrev, previousPeriodLabel)}
              {!previousIsAdjacent && missingIntermediatePeriods.length > 0
                ? ` (missing ${missingIntermediatePeriods.join(', ')})`
                : ''}
            </span>
          )}
        </div>
        {fullWindowComparisonLabel && (
          <p className="text-xs text-slate-600">{fullWindowComparisonLabel}</p>
        )}
      </div>

      {/* KPI Evidence (Scored vs Diagnostic) */}
      {(allKpiEvidence.length > 0 || weakKpis.length > 0) && (
        <div className="space-y-1.5">
          <div className="font-bold uppercase tracking-wider text-slate-500">
            KPI Evidence
          </div>
          {allKpiEvidence.length > 0 ? (
            <div className="space-y-1">
              {allKpiEvidence.map((item) => {
                const isWeak = item.contributesToScore && item.metTarget === false;
                const weightLabel = item.contributesToScore
                  ? item.weight != null
                    ? `Scored · Weight ${item.weight <= 1 ? Math.round(item.weight * 100) : Math.round(item.weight)}%`
                    : 'Scored'
                  : 'Diagnostic';
                return (
                  <div
                    key={item.kpiKey}
                    data-testid={
                      isWeak
                        ? `${testIdPrefix}-weak-kpi-${employeeId}-${item.kpiKey}`
                        : `${testIdPrefix}-kpi-${employeeId}-${item.kpiKey}`
                    }
                    className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 text-xs ${
                      isWeak
                        ? 'border-rose-200/80 bg-rose-50/70 text-rose-900'
                        : 'border-slate-200 bg-slate-50/70 text-slate-700'
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-semibold">{item.label}</span>
                      <span className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-xs font-medium text-slate-600">
                        {weightLabel}
                      </span>
                      {item.observationStatus === 'missing' && (
                        <span className="rounded border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-xs font-medium text-amber-800">
                          Unavailable
                        </span>
                      )}
                      {item.observationStatus === 'unverified_zero' && (
                        <span className="rounded border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-xs font-medium text-amber-800">
                          Unverified zero
                        </span>
                      )}
                    </div>
                    <div className="font-medium tabular-nums">
                      Actual: <strong>{item.actualFormatted}</strong> / Target: {item.targetFormatted}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {weakKpis.map((wk) => (
                <span
                  key={wk.key}
                  data-testid={`${testIdPrefix}-weak-kpi-${employeeId}-${wk.key}`}
                  className="inline-flex items-center rounded-md border border-rose-200/80 bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-800"
                >
                  {wk.name}: {wk.gapText}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Prior Actions */}
      {priorActions.length > 0 && (
        <div className="space-y-1">
          <div className="font-bold uppercase tracking-wider text-slate-500">
            Prior Actions
          </div>
          <ul className="space-y-1">
            {priorActions.map((pa) => (
              <li
                key={pa.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700"
              >
                <span className="font-medium">{pa.actionType}</span>
                <span className="text-slate-600">
                  {pa.status} · {pa.month} {pa.year || ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Projected Score Impact */}
      {isNumericProjection ? (
        <div
          data-testid={`${testIdPrefix}-projected-impact-${employeeId}`}
          className="rounded-lg border border-emerald-200/80 bg-emerald-50/60 px-2.5 py-1.5 text-xs text-emerald-900"
        >
          <span className="font-semibold">{showImpactLabel} </span>
          <span>{projectionDetail}</span>
        </div>
      ) : hasNeutralUnavailableNote ? (
        <div
          data-testid={`${testIdPrefix}-impact-unavailable-${employeeId}`}
          className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-600"
        >
          <span className="font-semibold">Action plan note (not recalculated from KPI evidence): </span>
          <span>{trimmedImpact}</span>
        </div>
      ) : null}
    </div>
  );
}

export interface TeamEvidenceDrawerProps {
  panelId: string;
  isOpen: boolean;
  cardId: string;
  scopeDescription: string;
  expectedTeamImpact: string;
  targetKpiLabel?: string;
  linkedKpiActualLabel?: string;
  linkedKpiTargetLabel?: string;
  teamTrendLabel?: string | null;
  aiPayload?: AiCorrectiveActionSuggestionPayload | null;
}

export function TeamEvidenceDrawer({
  panelId,
  isOpen,
  cardId,
  scopeDescription,
  expectedTeamImpact,
  targetKpiLabel,
  linkedKpiActualLabel,
  linkedKpiTargetLabel,
  teamTrendLabel,
  aiPayload,
}: TeamEvidenceDrawerProps) {
  const trimmedImpact = String(expectedTeamImpact ?? '').trim();
  const hasPlanEstimate =
    Boolean(trimmedImpact) &&
    !/^(?:—|-|n\/a|not specified|impact to be confirmed)$/i.test(trimmedImpact);

  const cohortCoverage =
    aiPayload?.cohort_coverage_label?.trim() || scopeDescription;
  const aiFacts = (Array.isArray(aiPayload?.measured_facts) ? aiPayload.measured_facts : [])
    .map((fact) => formatMeasuredFact(fact, aiPayload?.supporting_kpis))
    .filter(Boolean);

  return (
    <div
      id={panelId}
      data-testid={`team-evidence-drawer-${cardId}`}
      hidden={!isOpen}
      className="mt-3 space-y-2.5 rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-700"
    >
      {/* Cohort Counts */}
      {cohortCoverage && (
        <div className="space-y-1">
          <div className="font-bold uppercase tracking-wider text-slate-500">
            Cohort Counts
          </div>
          <p
            data-testid={`team-cohort-counts-${cardId}`}
            className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 font-medium text-slate-800"
          >
            {cohortCoverage}
          </p>
        </div>
      )}

      {/* Performance Trend */}
      {(teamTrendLabel || aiPayload?.trend_summary?.score_direction) && (
        <div className="space-y-1">
          <div className="font-bold uppercase tracking-wider text-slate-500">
            Performance Trend
          </div>
          <div className="flex flex-wrap gap-1.5">
            {teamTrendLabel && (
              <span className="inline-flex items-center rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-700">
                {teamTrendLabel}
              </span>
            )}
            {aiPayload?.trend_summary?.previous_score != null &&
              aiPayload?.trend_summary?.current_score != null && (
                <span className="inline-flex items-center rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-700">
                  Team score: {aiPayload.trend_summary.previous_score.toFixed(1)}% →{' '}
                  {aiPayload.trend_summary.current_score.toFixed(1)}%
                  {aiPayload.trend_summary.previous_period
                    ? ` vs ${aiPayload.trend_summary.previous_period}`
                    : ''}
                </span>
              )}
          </div>
        </div>
      )}

      {/* Source Evidence */}
      {(targetKpiLabel || linkedKpiActualLabel || aiFacts.length > 0) && (
        <div className="space-y-1">
          <div className="font-bold uppercase tracking-wider text-slate-500">
            Source Evidence
          </div>
          {(linkedKpiActualLabel || linkedKpiTargetLabel || aiPayload?.official_target_label) && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 font-medium text-slate-800">
              <span>{targetKpiLabel || 'Focus KPI'}</span>
              <span className="tabular-nums">
                {linkedKpiActualLabel ? `Actual: ${linkedKpiActualLabel} · ` : ''}
                Official target: {aiPayload?.official_target_label || linkedKpiTargetLabel || '—'}
              </span>
            </div>
          )}
          {aiFacts.length > 0 && (
            <ul className="space-y-1 text-slate-600">
              {aiFacts.slice(0, 4).map((fact, idx) => (
                <li key={`${idx}-${fact.slice(0, 16)}`}>{fact}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Stored action-plan estimates are not recalculated from current score evidence. */}
      {hasPlanEstimate && (
        <div
          data-testid={`team-action-plan-estimate-${cardId}`}
          className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-600"
        >
          <span className="font-semibold">
            Action plan estimate (not recalculated from KPI evidence):{' '}
          </span>
          <span>{trimmedImpact}</span>
        </div>
      )}
    </div>
  );
}

export interface ViewEvidenceToggleButtonProps {
  isOpen: boolean;
  panelId: string;
  onToggle: () => void;
}

export function ViewEvidenceToggleButton({
  isOpen,
  panelId,
  onToggle,
}: ViewEvidenceToggleButtonProps) {
  return (
    <button
      type="button"
      aria-expanded={isOpen}
      aria-controls={panelId}
      onClick={onToggle}
      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50"
    >
      <span>View evidence</span>
      {isOpen ? (
        <ChevronUp className="size-3.5 text-slate-500" aria-hidden="true" />
      ) : (
        <ChevronDown className="size-3.5 text-slate-500" aria-hidden="true" />
      )}
    </button>
  );
}
