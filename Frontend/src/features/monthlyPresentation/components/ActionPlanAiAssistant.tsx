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
    return (
      <div
        role="status"
        className="mt-2.5 rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-950"
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold">{outcomeHeading}</p>
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
  linkedKpiLabel,
  linkedKpiTarget,
}: IndividualEvidenceDrawerProps) {
  const trimmedImpact = String(expectedImpact ?? '').trim();
  const isNumericProjection = hasSupportedProjectedImpact(trimmedImpact);
  const showImpactLabel =
    linkedKpiLabel && linkedKpiTarget
      ? `Projected impact if ${linkedKpiLabel} reaches ${linkedKpiTarget} target:`
      : 'Projected impact:';
  const hasExplicitUnit = /\b(?:pts|points)\b|%/i.test(trimmedImpact);
  const projectionDetail = isNumericProjection
    ? `${trimmedImpact}${hasExplicitUnit ? '' : ' pts'}${
        /assuming other kpis stay constant/i.test(trimmedImpact)
          ? ''
          : ' (assuming other KPIs stay constant)'
      }`
    : '';
  const hasNeutralUnavailableNote =
    !isNumericProjection &&
    Boolean(trimmedImpact) &&
    !/^(?:—|-|n\/a|not specified)$/i.test(trimmedImpact);

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
          <span className="font-semibold">Score impact unavailable: </span>
          <span>{trimmedImpact}</span>
        </div>
      ) : null}
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
