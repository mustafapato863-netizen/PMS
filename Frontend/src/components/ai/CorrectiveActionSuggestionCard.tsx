import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  ArrowDown,
  Info,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  X,
} from 'lucide-react';
import { apiFetch, ApiError } from '../../lib/apiClient';
import type { ActionType } from '../../types';
import type {
  AiCorrectiveActionSuggestionKpiEvidence,
  AiCorrectiveActionSuggestionPayload,
  AiCorrectiveActionSuggestionRequest,
  AiCorrectiveActionSuggestionResponse,
} from '../../features/ai/types';

export interface CorrectiveActionSuggestionCardProps {
  employeeId?: string | null;
  employeeName?: string | null;
  team: string;
  month: string;
  year?: number;
  linkedKpiKey?: string | null;
  onApplyDraft: (draft: { actionType: ActionType; actionDescription: string }) => void;
  onDismiss?: () => void;
  className?: string;
}

type CardState =
  | 'idle'
  | 'loading'
  | 'suggested'
  | 'insufficient_evidence'
  | 'model_unavailable'
  | 'draft_rejected'
  | 'error';

function formatKpiEvidenceValue(val?: number | null, unit?: string | null): string {
  if (val === null || val === undefined) {
    return 'Unavailable';
  }
  if (val === 0) {
    return unit === '%' ? '0.0%' : unit === 'min' ? '0.0 min' : '0';
  }
  const formatted = val.toLocaleString(undefined, { maximumFractionDigits: 1 });
  if (unit === '%') return `${formatted}%`;
  if (unit === 'min') return `${formatted} min`;
  return unit ? `${formatted} ${unit}` : formatted;
}

function getProviderBadgeText(provider: string): string {
  switch (provider) {
    case 'cloudflare':
      return 'Cloudflare Workers AI';
    case 'gemini':
      return 'Google Gemini';
    case 'deterministic':
      return 'Rule-Based Engine';
    default:
      return 'PMS AI Engine';
  }
}

export default function CorrectiveActionSuggestionCard({
  employeeId,
  employeeName,
  team,
  month,
  year = 2026,
  linkedKpiKey,
  onApplyDraft,
  onDismiss,
  className = '',
}: CorrectiveActionSuggestionCardProps) {
  const [state, setState] = useState<CardState>('idle');
  const [data, setData] = useState<AiCorrectiveActionSuggestionPayload | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Stale request / context change protection:
  // Reset state during render when context changes (React recommended pattern)
  const contextKey = `${employeeId || ''}-${team}-${month}-${year}`;
  const [prevContextKey, setPrevContextKey] = useState(contextKey);
  if (prevContextKey !== contextKey) {
    setPrevContextKey(contextKey);
    setState('idle');
    setData(null);
    setErrorMessage(null);
    setErrorStatus(null);
  }

  // Abort active in-flight request when context changes or on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    };
  }, [employeeId, team, month, year]);

  const handleGenerate = useCallback(async () => {
    if (!team || !month) return;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setState('loading');
    setErrorMessage(null);
    setErrorStatus(null);

    const payload: AiCorrectiveActionSuggestionRequest = {
      team,
      month,
      year,
      performance_level: 'Employee',
      employee_id: employeeId || null,
      linked_kpi_key: linkedKpiKey || null,
    };

    try {
      const response = await apiFetch<AiCorrectiveActionSuggestionResponse>(
        '/api/ai/corrective-action-suggestions',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          signal: controller.signal,
        }
      );

      const result = response.data;
      setData(result);

      switch (result.outcome) {
        case 'suggested':
          setState('suggested');
          break;
        case 'insufficient_evidence':
          setState('insufficient_evidence');
          break;
        case 'model_unavailable':
          setState('model_unavailable');
          break;
        case 'draft_rejected':
          setState('draft_rejected');
          break;
        default:
          setState('idle');
          break;
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        return; // Silent on user cancellation / context switch
      }

      let status: number | null = null;
      let message = 'Failed to generate corrective action suggestion.';

      if (err instanceof ApiError) {
        status = err.status;
        if (status === 401 || status === 403) {
          message = 'Administrative access required to use the suggestion pilot.';
        } else if (status === 429) {
          message = 'Daily suggestion limit reached. Please enter the action manually.';
        } else if (status === 408) {
          message = 'Request timed out. Please retry or enter the action manually.';
        } else {
          message = err.message || message;
        }
      } else if (err instanceof Error) {
        message = err.message;
      }

      setErrorStatus(status);
      setErrorMessage(message);
      setState('error');
    } finally {
      abortControllerRef.current = null;
    }
  }, [team, month, year, employeeId, linkedKpiKey]);

  const handleApplyDraft = useCallback(() => {
    if (!data?.draft) return;

    // Convert draft steps to formatted action description
    const formattedSteps = data.draft.recommended_steps
      .map((step, idx) => `${idx + 1}. ${step}`)
      .join('\n');

    onApplyDraft({
      actionType: data.draft.action_type as ActionType,
      actionDescription: formattedSteps,
    });
  }, [data, onApplyDraft]);

  return (
    <div
      data-testid="ai-corrective-action-card"
      className={`rounded-2xl border border-purple-500/25 bg-gradient-to-b from-purple-500/[0.04] to-[var(--bg-surface)] p-4 shadow-sm transition-all dark:border-purple-400/20 dark:from-purple-950/20 ${className}`}
    >
      {/* Card Header */}
      <div className="flex items-start justify-between gap-3 border-b border-[var(--border-light)] pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-purple-500/15 text-purple-600 dark:bg-purple-500/25 dark:text-purple-300">
            <Sparkles size={16} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="text-xs font-extrabold uppercase tracking-wider text-[var(--text-primary)]">
                AI Corrective Action Suggestion
              </h4>
              <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-700 dark:text-amber-400">
                Draft — Requires Review
              </span>
            </div>
            <p className="mt-0.5 text-[11px] font-medium text-[var(--text-muted)]">
              {employeeName || 'Selected Employee'} · {team} · {month} {year}
              {linkedKpiKey ? ` · Focus KPI: ${linkedKpiKey}` : ''}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {data?.provider_used && data.provider_used !== 'none' && (
            <span
              data-testid="provider-badge"
              className="rounded-md border border-[var(--border-light)] bg-[var(--bg-sunken)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]"
            >
              {getProviderBadgeText(data.provider_used)}
            </span>
          )}
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              aria-label="Dismiss AI Suggestion Card"
              className="rounded-lg p-1 text-[var(--text-faint)] transition-colors hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)]"
            >
              <X size={15} />
            </button>
          )}
        </div>
      </div>

      {/* Card Body by State */}
      <div className="pt-3">
        {/* 1. Idle State */}
        {state === 'idle' && (
          <div className="space-y-3 py-1">
            <p className="text-xs font-medium text-[var(--text-secondary)] leading-relaxed">
              Generate an evidence-grounded corrective action draft for this employee based on verified
              KPI records. The suggestion is an unapproved recommendation and will not be saved automatically.
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleGenerate}
                data-testid="generate-suggestion-btn"
                className="flex items-center gap-2 rounded-xl bg-purple-600 px-3.5 py-2 text-xs font-bold text-white shadow-sm transition-all hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-purple-400 focus:ring-offset-1 cursor-pointer"
              >
                <Sparkles size={14} />
                Generate Suggestion
              </button>
              {onDismiss && (
                <button
                  type="button"
                  onClick={onDismiss}
                  className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)] cursor-pointer"
                >
                  Enter Action Manually
                </button>
              )}
            </div>
          </div>
        )}

        {/* 2. Loading State */}
        {state === 'loading' && (
          <div
            role="status"
            aria-busy="true"
            data-testid="ai-card-loading"
            className="space-y-3 py-2 animate-pulse"
          >
            <div className="flex items-center gap-2 text-xs font-semibold text-purple-600 dark:text-purple-400">
              <Loader2 size={15} className="animate-spin" />
              <span>Analyzing KPI evidence and generating recommendation...</span>
            </div>
            <div className="h-14 w-full rounded-xl bg-[var(--bg-sunken)]" />
            <div className="space-y-1.5">
              <div className="h-4 w-3/4 rounded bg-[var(--bg-sunken)]" />
              <div className="h-4 w-1/2 rounded bg-[var(--bg-sunken)]" />
            </div>
          </div>
        )}

        {/* 3. Suggested State */}
        {state === 'suggested' && data?.draft && (
          <div data-testid="ai-card-suggested" className="space-y-3.5">
            {/* Supporting KPI Evidence Grid */}
            {data.supporting_kpis && data.supporting_kpis.length > 0 && (
              <div className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-2.5">
                <span className="block text-[11px] font-bold uppercase tracking-wider text-[var(--text-muted)] mb-2">
                  Verified Performance Evidence:
                </span>
                <div className="space-y-1.5">
                  {data.supporting_kpis.slice(0, 3).map((kpi: AiCorrectiveActionSuggestionKpiEvidence) => {
                    const actualStr = formatKpiEvidenceValue(kpi.actual, kpi.unit);
                    const targetStr = formatKpiEvidenceValue(kpi.target, kpi.unit);
                    const isBelow = kpi.status === 'below_target';

                    return (
                      <div
                        key={kpi.kpi_key}
                        data-testid={`kpi-evidence-row-${kpi.kpi_key}`}
                        className="flex items-center justify-between gap-2 rounded-lg bg-[var(--bg-sunken)] px-2.5 py-1.5 text-xs"
                      >
                        <span className="font-semibold text-[var(--text-primary)] truncate">
                          {kpi.display_name}
                        </span>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="font-medium text-[var(--text-secondary)]">
                            Actual: <strong className="text-[var(--text-primary)]">{actualStr}</strong> / Target: {targetStr}
                          </span>
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                              isBelow
                                ? 'bg-rose-500/10 text-rose-700 dark:text-rose-400 border border-rose-500/20'
                                : 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20'
                            }`}
                          >
                            {isBelow ? 'Below Target' : 'Target Met'}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* AI Recommendation Details */}
            <div className="rounded-xl border border-purple-500/20 bg-purple-500/5 p-3 space-y-2 dark:bg-purple-950/20">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold text-[var(--text-primary)]">
                  {data.draft.title}
                </span>
                <span className="rounded-md border border-purple-500/30 bg-purple-500/10 px-2 py-0.5 text-[11px] font-bold text-purple-700 dark:text-purple-300">
                  {data.draft.action_type}
                </span>
              </div>

              {/* Recommended Steps */}
              <div className="space-y-1 pt-1">
                <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
                  Recommended Steps:
                </span>
                <ol className="list-decimal list-inside space-y-1 text-xs font-medium text-[var(--text-primary)]">
                  {data.draft.recommended_steps.map((step, idx) => (
                    <li key={idx} className="leading-snug">
                      {step}
                    </li>
                  ))}
                </ol>
              </div>

              {/* Evidence Limitation / Uncertainty Caveat */}
              {(data.draft.uncertainty || (data.evidence_limitations && data.evidence_limitations[0])) && (
                <div className="border-t border-purple-500/15 pt-2 text-[11px] font-medium text-[var(--text-muted)]">
                  <span className="font-bold text-[var(--text-secondary)]">Evidence Limitation: </span>
                  {data.draft.uncertainty || data.evidence_limitations?.[0]}
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                type="button"
                onClick={handleApplyDraft}
                data-testid="insert-draft-btn"
                className="flex items-center gap-1.5 rounded-xl bg-purple-600 px-3.5 py-2 text-xs font-bold text-white shadow-sm transition-all hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-purple-400 focus:ring-offset-1 cursor-pointer"
              >
                <ArrowDown size={14} />
                Insert Editable Draft
              </button>
              <button
                type="button"
                onClick={handleGenerate}
                data-testid="retry-btn"
                className="flex items-center gap-1.5 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)] cursor-pointer"
              >
                <RefreshCw size={13} />
                Regenerate
              </button>
              {onDismiss && (
                <button
                  type="button"
                  onClick={onDismiss}
                  className="rounded-xl px-3 py-2 text-xs font-semibold text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors cursor-pointer"
                >
                  Enter Action Manually
                </button>
              )}
            </div>
          </div>
        )}

        {/* 4. Insufficient Evidence State */}
        {state === 'insufficient_evidence' && (
          <div data-testid="ai-card-insufficient-evidence" className="space-y-3 py-1">
            <div className="flex items-start gap-2.5 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-300">
              <Info size={16} className="shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
              <div>
                <p className="font-bold">Not enough verified performance data is available.</p>
                <p className="mt-0.5 text-[11px] opacity-90">
                  {data?.insufficient_evidence_reasons?.[0] ||
                    'There is not enough recorded evidence to generate an actionable draft for this selection.'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleGenerate}
                className="flex items-center gap-1.5 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] cursor-pointer"
              >
                <RefreshCw size={13} />
                Retry
              </button>
              {onDismiss && (
                <button
                  type="button"
                  onClick={onDismiss}
                  className="rounded-xl bg-[var(--bg-sunken)] px-3.5 py-2 text-xs font-bold text-[var(--text-primary)] hover:bg-[var(--border-light)] transition-colors cursor-pointer"
                >
                  Enter Action Manually
                </button>
              )}
            </div>
          </div>
        )}

        {/* 5. Model Unavailable State */}
        {state === 'model_unavailable' && (
          <div data-testid="ai-card-model-unavailable" className="space-y-3 py-1">
            <div className="flex items-start gap-2.5 rounded-xl border border-amber-500/25 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-300">
              <AlertTriangle size={16} className="shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
              <div>
                <p className="font-bold">AI suggestion service is temporarily unavailable.</p>
                <p className="mt-0.5 text-[11px] opacity-90">
                  The AI model could not be reached. You can retry or enter the action manually.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleGenerate}
                className="flex items-center gap-1.5 rounded-xl bg-purple-600 px-3.5 py-2 text-xs font-bold text-white shadow-sm hover:bg-purple-700 transition-colors cursor-pointer"
              >
                <RefreshCw size={13} />
                Retry
              </button>
              {onDismiss && (
                <button
                  type="button"
                  onClick={onDismiss}
                  className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)] transition-colors cursor-pointer"
                >
                  Enter Action Manually
                </button>
              )}
            </div>
          </div>
        )}

        {/* 6. Draft Rejected State */}
        {state === 'draft_rejected' && (
          <div data-testid="ai-card-draft-rejected" className="space-y-3 py-1">
            <div className="flex items-start gap-2.5 rounded-xl border border-rose-500/25 bg-rose-500/10 p-3 text-xs text-rose-800 dark:text-rose-300">
              <ShieldAlert size={16} className="shrink-0 mt-0.5 text-rose-600 dark:text-rose-400" />
              <div>
                <p className="font-bold">Suggestion discarded for safety.</p>
                <p className="mt-0.5 text-[11px] opacity-90">
                  The AI draft did not match the verified performance evidence and was safely discarded.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleGenerate}
                className="flex items-center gap-1.5 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)] transition-colors cursor-pointer"
              >
                <RefreshCw size={13} />
                Retry
              </button>
              {onDismiss && (
                <button
                  type="button"
                  onClick={onDismiss}
                  className="rounded-xl bg-[var(--bg-sunken)] px-3.5 py-2 text-xs font-bold text-[var(--text-primary)] hover:bg-[var(--border-light)] transition-colors cursor-pointer"
                >
                  Enter Action Manually
                </button>
              )}
            </div>
          </div>
        )}

        {/* 7. Error State */}
        {state === 'error' && (
          <div data-testid="ai-card-error" className="space-y-3 py-1">
            <div className="flex items-start gap-2.5 rounded-xl border border-rose-500/20 bg-rose-500/10 p-3 text-xs text-rose-700 dark:text-rose-300">
              <AlertCircle size={16} className="shrink-0 mt-0.5 text-rose-600 dark:text-rose-400" />
              <div>
                <p className="font-bold">Request Error</p>
                <p className="mt-0.5 text-[11px] opacity-90">{errorMessage || 'An error occurred.'}</p>
              </div>
            </div>
            {errorStatus !== 401 && errorStatus !== 403 && (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleGenerate}
                  className="flex items-center gap-1.5 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)] transition-colors cursor-pointer"
                >
                  <RefreshCw size={13} />
                  Retry
                </button>
                {onDismiss && (
                  <button
                    type="button"
                    onClick={onDismiss}
                    className="rounded-xl px-3 py-2 text-xs font-semibold text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors cursor-pointer"
                  >
                    Enter Action Manually
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
