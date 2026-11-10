import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ClipboardCheck,
  Compass,
  HelpCircle,
  Loader2,
  MessageSquare,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  X,
} from 'lucide-react';
import { apiFetch } from '../../lib/apiClient';
import { useAiAvailability } from '../../features/ai/aiAvailabilityContext';
import { isAdminRole } from '../../lib/access';
import { useAuth } from '../../context/auth';
import { useUserRole } from '../../context/RoleContext';
import type {
  AiChatResponsePayload,
  AiCorrectiveActionConfirmRequest,
  AiCorrectiveActionConfirmResponse,
  AiCorrectiveActionProposal,
  FeedbackCategoryType,
  PageContextV1,
} from '../../features/ai/types';

export interface ContextualAssistantPanelProps {
  pageContext: PageContextV1;
  defaultOpen?: boolean;
  onActionSaved?: () => void;
}

interface AssistantTurn {
  id: string;
  prompt: string;
  response: AiChatResponsePayload | null;
  error: string | null;
  loading: boolean;
  feedbackSubmitted?: 'helpful' | FeedbackCategoryType | null;
  showNegativeFeedbackMenu?: boolean;
  savedAction?: AiCorrectiveActionConfirmResponse | null;
}

interface ActionReviewDraft {
  action_type: AiCorrectiveActionConfirmRequest['action_type'];
  action_text: string;
  root_cause_note: string;
  priority: 'Low' | 'Medium' | 'High';
  due_date: string;
}

const FEEDBACK_CATEGORIES: Array<{ key: FeedbackCategoryType; label: string }> = [
  { key: 'incorrect_answer', label: 'Incorrect answer' },
  { key: 'incorrect_scope', label: 'Incorrect scope' },
  { key: 'incomplete_response', label: 'Incomplete response' },
  { key: 'poor_suggestion', label: 'Poor suggestion' },
];

function buildEffectiveContextLabel(ctx: PageContextV1): string {
  const pageTitle =
    ctx.page_id === 'monthly_presentation'
      ? 'Monthly Presentation'
      : ctx.page_id === 'team_dashboard'
        ? 'Team Dashboard'
        : ctx.page_id === 'executive_summary'
          ? 'Executive Summary'
          : ctx.page_id === 'function_summary'
            ? 'Function Summary'
            : ctx.page_id === 'employee_profile'
              ? 'Employee Profile'
              : 'PMS View';
  const scopePart = ctx.team_id || ctx.function_id || ctx.region || 'All Authorized Scope';
  const periodPart =
    ctx.month && ctx.year
      ? `${ctx.month} ${ctx.year}`
      : ctx.period || ctx.month || 'Latest Period';
  const parts = [pageTitle, scopePart, periodPart];
  if (ctx.branch && ctx.branch.toLowerCase() !== 'all') {
    parts.push(ctx.branch);
  }
  if (ctx.selected_metric_id) {
    parts.push(ctx.selected_metric_id);
  }
  return parts.join(' · ');
}

function buildStarterPrompts(ctx: PageContextV1, canCreateAction: boolean): string[] {
  const metric = ctx.selected_metric_id || 'Booking Rate';
  const scope = ctx.team_id || ctx.function_id || 'this view';
  if (ctx.page_id === 'monthly_presentation') {
    const prompts = [
      'Explain this page',
      `Why is ${scope} below target?`,
      'Where do I go to inspect agent scorecards?',
    ];
    if (canCreateAction && !ctx.is_fallback_data) {
      prompts.push(`Propose a corrective action for ${metric}`);
    }
    return prompts;
  }
  const prompts = [
    'Explain this page',
    `Why is ${scope} below target?`,
    `Who is the top performer in ${ctx.team_id || 'this team'}?`,
  ];
  if (canCreateAction && !ctx.is_fallback_data) {
    prompts.push(`Propose a corrective action for ${metric}`);
  }
  return prompts;
}

export function ContextualAssistantPanel({
  pageContext,
  defaultOpen = false,
  onActionSaved,
}: ContextualAssistantPanelProps) {
  const { role } = useUserRole();
  const { currentUser } = useAuth();
  const { enabled: aiEnabled } = useAiAvailability();
  const pilotVisible = aiEnabled && isAdminRole(role);
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const [input, setInput] = useState('');
  const [turns, setTurns] = useState<AssistantTurn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [activeProposalTurnId, setActiveProposalTurnId] = useState<string | null>(null);
  const [reviewDraft, setReviewDraft] = useState<ActionReviewDraft | null>(null);
  const [savingAction, setSavingAction] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const canCreateAction = useMemo(
    () => ['Admin', 'General Manager', 'Manager', 'Performance Team'].includes(role || ''),
    [role],
  );

  const contextFingerprint = useMemo(
    () =>
      JSON.stringify({
        user: currentUser?.id ?? role,
        page_id: pageContext.page_id,
        route_id: pageContext.route_id,
        region: pageContext.region,
        branch: pageContext.branch,
        period: pageContext.period,
        month: pageContext.month,
        year: pageContext.year,
        function_id: pageContext.function_id,
        team_id: pageContext.team_id,
        position_id: pageContext.position_id,
        performance_level: pageContext.performance_level,
        selected_metric_id: pageContext.selected_metric_id,
        employee_id: pageContext.employee_id,
        is_fallback_data: Boolean(pageContext.is_fallback_data),
      }),
    [currentUser?.id, role, pageContext],
  );

  const abortControllerRef = useRef<AbortController | null>(null);
  const requestSeqRef = useRef(0);
  const prevFingerprintRef = useRef(contextFingerprint);

  // Cancel any in-flight request and reset active proposal review when context or user changes
  useEffect(() => {
    if (prevFingerprintRef.current !== contextFingerprint) {
      prevFingerprintRef.current = contextFingerprint;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      requestSeqRef.current += 1;
      setActiveProposalTurnId(null);
      setReviewDraft(null);
      setSaveError(null);
      setTurns((prev) => prev.filter((t) => !t.loading));
    }
  }, [contextFingerprint]);

  const effectiveContextLabel = useMemo(
    () => buildEffectiveContextLabel(pageContext),
    [pageContext],
  );

  const starterPrompts = useMemo(
    () => buildStarterPrompts(pageContext, canCreateAction),
    [pageContext, canCreateAction],
  );

  const sendPrompt = useCallback(
    async (promptText: string) => {
      const trimmed = promptText.trim();
      if (!trimmed || !isAdminRole(role) || !aiEnabled) return;

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const controller = new AbortController();
      abortControllerRef.current = controller;
      const currentSeq = requestSeqRef.current + 1;
      requestSeqRef.current = currentSeq;

      const turnId = `turn-${Date.now()}-${currentSeq}`;
      setInput('');
      setActiveProposalTurnId(null);
      setReviewDraft(null);
      setSaveError(null);

      setTurns((prev) => [
        ...prev,
        {
          id: turnId,
          prompt: trimmed,
          response: null,
          error: null,
          loading: true,
        },
      ]);

      try {
        const rawRes = await apiFetch<{ data?: AiChatResponsePayload } & Partial<AiChatResponsePayload>>(
          '/api/ai/chat',
          {
            method: 'POST',
            signal: controller.signal,
            body: JSON.stringify({
              prompt: trimmed,
              conversation_id: conversationId,
              client_request_id: turnId,
              answer_detail: 'brief',
              page_context: pageContext,
              session_state: {
                function: pageContext.function_id ?? null,
                team: pageContext.team_id ?? null,
                position: pageContext.position_id ?? null,
                branch: pageContext.branch ?? null,
                region: pageContext.region ?? null,
                performance_level: pageContext.performance_level ?? 'Employee',
                month: pageContext.month ?? null,
                year: pageContext.year ?? null,
                employee_id: pageContext.employee_id ?? null,
              },
            }),
          },
        );

        // Ignore late response if context or sequence changed
        if (requestSeqRef.current !== currentSeq || controller.signal.aborted) {
          return;
        }

        const res: AiChatResponsePayload = (rawRes.data ?? rawRes) as AiChatResponsePayload;

        if (res.conversation_id) {
          setConversationId(res.conversation_id);
        }

        setTurns((prev) =>
          prev.map((t) =>
            t.id === turnId
              ? {
                  ...t,
                  response: res,
                  loading: false,
                }
              : t,
          ),
        );
      } catch (err) {
        if (requestSeqRef.current !== currentSeq || controller.signal.aborted) {
          return;
        }
        const message =
          err instanceof Error && err.name !== 'AbortError'
            ? err.message
            : 'Unable to complete the assistant request right now.';
        setTurns((prev) =>
          prev.map((t) =>
            t.id === turnId
              ? {
                  ...t,
                  error: message,
                  loading: false,
                }
              : t,
          ),
        );
      }
    },
    [aiEnabled, conversationId, pageContext, role],
  );

  const openProposalReview = useCallback((turnId: string, proposal: AiCorrectiveActionProposal) => {
    setActiveProposalTurnId(turnId);
    setSaveError(null);
    setReviewDraft({
      action_type: proposal.action_type || 'Coaching',
      action_text: proposal.proposed_action_text,
      root_cause_note: proposal.proposed_root_cause_note,
      priority: proposal.priority || 'High',
      due_date: '',
    });
  }, []);

  const cancelProposalReview = useCallback(() => {
    setActiveProposalTurnId(null);
    setReviewDraft(null);
    setSaveError(null);
  }, []);

  const handleConfirmProposal = useCallback(
    async (turnId: string, proposal: AiCorrectiveActionProposal, traceId?: string) => {
      if (!reviewDraft) return;
      setSavingAction(true);
      setSaveError(null);
      try {
        const payload: AiCorrectiveActionConfirmRequest = {
          proposal_id: proposal.proposal_id,
          team: proposal.team,
          month: proposal.month,
          year: proposal.year,
          employee_id: proposal.employee_id ?? null,
          linked_kpi_key: proposal.linked_kpi_key ?? null,
          action_type: reviewDraft.action_type,
          action_text: reviewDraft.action_text.trim(),
          root_cause_note: reviewDraft.root_cause_note.trim(),
          priority: reviewDraft.priority,
          due_date: reviewDraft.due_date ? reviewDraft.due_date : null,
          evidence_revision: proposal.evidence_revision,
          is_fallback_data: Boolean(pageContext.is_fallback_data),
          trace_id: traceId ?? null,
        };
        const saved = await apiFetch<AiCorrectiveActionConfirmResponse>(
          '/api/ai/proposals/confirm',
          {
            method: 'POST',
            body: JSON.stringify(payload),
          },
        );
        setTurns((prev) =>
          prev.map((t) =>
            t.id === turnId
              ? {
                  ...t,
                  savedAction: saved,
                }
              : t,
          ),
        );
        setActiveProposalTurnId(null);
        setReviewDraft(null);
        onActionSaved?.();
      } catch (err) {
        setSaveError(
          err instanceof Error
            ? err.message
            : 'Could not save corrective action. Please verify your permissions and try again.',
        );
      } finally {
        setSavingAction(false);
      }
    },
    [onActionSaved, pageContext.is_fallback_data, reviewDraft],
  );

  const submitFeedback = useCallback(
    async (
      turnId: string,
      traceId: string,
      rating: 'up' | 'down',
      category: FeedbackCategoryType,
    ) => {
      try {
        await apiFetch('/api/ai/feedback', {
          method: 'POST',
          body: JSON.stringify({
            trace_id: traceId,
            rating,
            category,
          }),
        });
        setTurns((prev) =>
          prev.map((t) =>
            t.id === turnId
              ? {
                  ...t,
                  feedbackSubmitted: rating === 'up' ? 'helpful' : category,
                  showNegativeFeedbackMenu: false,
                }
              : t,
          ),
        );
      } catch {
        // Non-blocking feedback submission
      }
    },
    [],
  );

  // Keyboard Escape closes panel
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (activeProposalTurnId) {
          cancelProposalReview();
        } else {
          setIsOpen(false);
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeProposalTurnId, cancelProposalReview, isOpen]);

  if (!pilotVisible) return null;

  return (
    <div
      className="fixed bottom-5 right-5 z-50 print:hidden"
      data-testid="contextual-assistant-root"
    >
      {!isOpen ? (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          aria-label="Open PMS AI Contextual Assistant"
          data-testid="contextual-assistant-launcher"
          className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-blue-500/30 bg-slate-900 px-4 py-2.5 text-xs font-bold text-white shadow-lg transition-all duration-200 hover:-translate-y-0.5 hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <Sparkles className="size-4 text-blue-400" aria-hidden="true" />
          <span>Ask PMS AI</span>
          {pageContext.team_id && (
            <span className="rounded-full bg-blue-500/20 px-2 py-0.5 text-[11px] font-semibold text-blue-200">
              {pageContext.team_id}
            </span>
          )}
        </button>
      ) : (
        <section
          role="dialog"
          aria-label="PMS Contextual AI Assistant"
          data-testid="contextual-assistant-panel"
          className="flex max-h-[82vh] w-[92vw] max-w-[430px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-950"
        >
          {/* Header & Scope Banner */}
          <header className="border-b border-slate-200 bg-slate-900 px-4 py-3 text-white dark:border-slate-800">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Sparkles className="size-4 shrink-0 text-blue-400" aria-hidden="true" />
                <h2 className="text-sm font-bold tracking-tight">PMS Contextual Assistant</h2>
              </div>
              <div className="flex items-center gap-1.5">
                <Link
                  to="/ai"
                  className="rounded-md bg-white/10 px-2 py-1 text-[11px] font-semibold text-slate-200 transition hover:bg-white/20"
                >
                  Full AI Workspace
                </Link>
                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  aria-label="Close PMS Contextual Assistant"
                  data-testid="contextual-assistant-close"
                  className="rounded-md p-1 text-slate-300 transition hover:bg-white/10 hover:text-white"
                >
                  <X className="size-4" />
                </button>
              </div>
            </div>
            <p
              data-testid="contextual-assistant-scope-banner"
              className="mt-1.5 truncate rounded-lg bg-white/10 px-2.5 py-1 text-[11px] font-medium text-blue-100"
              title={effectiveContextLabel}
            >
              {effectiveContextLabel}
            </p>
          </header>

          {/* Fallback Sample Data Warning */}
          {pageContext.is_fallback_data && (
            <div
              role="status"
              data-testid="contextual-assistant-fallback-warning"
              className="flex items-start gap-2 border-b border-amber-200 bg-amber-50 px-3.5 py-2 text-xs text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200"
            >
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
              <span>
                Fallback sample data is displayed on this view. Page explanations and navigation are
                available; analytical claims and action proposals require live PMS records.
              </span>
            </div>
          )}

          {/* Conversation Body */}
          <div className="flex-1 space-y-3 overflow-y-auto p-3.5">
            {turns.length === 0 && (
              <div className="space-y-2.5">
                <p className="text-xs font-medium text-slate-600 dark:text-slate-300">
                  Ask about this view, metric targets, score drivers, or authorized next steps:
                </p>
                <div className="flex flex-wrap gap-1.5" data-testid="contextual-assistant-starters">
                  {starterPrompts.map((starter) => (
                    <button
                      key={starter}
                      type="button"
                      onClick={() => sendPrompt(starter)}
                      className="cursor-pointer rounded-xl border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-left text-xs font-semibold text-slate-700 transition hover:border-blue-300 hover:bg-blue-50/60 hover:text-blue-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
                    >
                      {starter}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {turns.map((turn) => {
              const res = turn.response;
              const proposal = res?.action_proposal ?? null;
              const isReviewingThisProposal =
                activeProposalTurnId === turn.id && proposal && reviewDraft;
              const evaluatedRecordsCount = (res?.tool_calls ?? []).reduce(
                (acc, tc) => acc + (tc.records_evaluated || 0),
                0,
              );

              return (
                <div
                  key={turn.id}
                  data-testid="contextual-assistant-turn"
                  className="space-y-2 rounded-xl border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-900/60"
                >
                  {/* User question */}
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-xs font-bold text-slate-900 dark:text-slate-100">
                      {turn.prompt}
                    </span>
                  </div>

                  {/* Loading skeleton */}
                  {turn.loading && (
                    <div
                      role="status"
                      aria-label="Loading assistant answer"
                      className="flex items-center gap-2 py-2 text-xs font-medium text-slate-500"
                    >
                      <Loader2 className="size-3.5 animate-spin text-blue-600" />
                      <span>Verifying authorized PMS evidence…</span>
                    </div>
                  )}

                  {/* Error */}
                  {turn.error && (
                    <div
                      role="alert"
                      className="rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-2 text-xs text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-200"
                    >
                      {turn.error}
                    </div>
                  )}

                  {/* Response payload */}
                  {res && (
                    <div className="space-y-2.5 text-xs text-slate-700 dark:text-slate-200">
                      {/* Effective context chip per response */}
                      {(res.effective_context_label || res.scope_banner) && (
                        <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold text-slate-500 dark:text-slate-400">
                          <span className="rounded bg-slate-200/70 px-1.5 py-0.5 dark:bg-slate-800">
                            {res.effective_context_label || res.scope_banner}
                          </span>
                        </div>
                      )}

                      {/* 1-2 sentence direct answer */}
                      <p
                        data-testid="contextual-assistant-direct-answer"
                        className="font-semibold leading-relaxed text-slate-900 dark:text-slate-100"
                      >
                        {res.headline}
                      </p>

                      {/* Material basis warning */}
                      {res.basis_warning && (
                        <div className="flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50/80 px-2.5 py-1.5 text-[11px] font-medium text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200">
                          <AlertTriangle className="mt-0.5 size-3 shrink-0 text-amber-600" />
                          <span>{res.basis_warning}</span>
                        </div>
                      )}

                      {/* Page Help Section */}
                      {res.page_help && (
                        <div className="space-y-1.5 rounded-lg border border-slate-200 bg-white p-2.5 dark:border-slate-800 dark:bg-slate-950">
                          <div className="flex items-center gap-1 font-bold text-slate-800 dark:text-slate-100">
                            <HelpCircle className="size-3 text-blue-600" />
                            <span>{res.page_help.page_title}</span>
                          </div>
                          <p className="text-[11px] leading-relaxed text-slate-600 dark:text-slate-300">
                            {res.page_help.summary}
                          </p>
                          {res.page_help.metric_explanation && (
                            <p className="text-[11px] font-medium text-blue-700 dark:text-blue-300">
                              {res.page_help.metric_explanation}
                            </p>
                          )}
                        </div>
                      )}

                      {/* Navigation Targets */}
                      {res.navigation_targets && res.navigation_targets.length > 0 && (
                        <div className="space-y-1.5">
                          {res.navigation_targets.map((nav) => (
                            <Link
                              key={nav.route}
                              to={nav.route}
                              className="flex items-center justify-between gap-2 rounded-lg border border-blue-200 bg-blue-50/70 px-2.5 py-2 text-xs font-semibold text-blue-800 transition hover:bg-blue-100 dark:border-blue-900/50 dark:bg-blue-950/40 dark:text-blue-200"
                            >
                              <span className="flex items-center gap-1.5">
                                <Compass className="size-3.5 shrink-0 text-blue-600" />
                                <span>{nav.label}</span>
                              </span>
                              <ArrowRight className="size-3.5 shrink-0" />
                            </Link>
                          ))}
                        </div>
                      )}

                      {/* Evidence Source Link */}
                      {res.primary_source_link && (
                        <div>
                          <Link
                            to={res.primary_source_link.route}
                            className="inline-flex items-center gap-1 text-[11px] font-bold text-blue-600 hover:underline dark:text-blue-400"
                          >
                            <span>{res.primary_source_link.label}</span>
                            <ArrowRight className="size-3" />
                          </Link>
                        </div>
                      )}

                      {/* Corrective Action Proposal Section */}
                      {proposal && (
                        <div
                          data-testid="contextual-assistant-proposal-card"
                          className="space-y-2 rounded-xl border border-indigo-200 bg-indigo-50/50 p-2.5 dark:border-indigo-900/50 dark:bg-indigo-950/30"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="inline-flex items-center gap-1 text-[11px] font-extrabold uppercase tracking-wider text-indigo-800 dark:text-indigo-300">
                              <ClipboardCheck className="size-3.5" />
                              <span>Evidence-Based Proposal ({proposal.team})</span>
                            </span>
                            {proposal.metric_display_name && (
                              <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-bold text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200">
                                {proposal.metric_display_name}
                              </span>
                            )}
                          </div>

                          {/* Observed Facts vs Hypotheses */}
                          {proposal.observed_facts.length > 0 && (
                            <div className="space-y-0.5">
                              <span className="text-[10px] font-bold uppercase text-slate-500">
                                Observed PMS Facts
                              </span>
                              <ul className="list-disc space-y-0.5 pl-4 text-[11px] text-slate-700 dark:text-slate-200">
                                {proposal.observed_facts.map((fact, idx) => (
                                  <li key={idx}>{fact}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {proposal.hypothesis && (
                            <div className="space-y-0.5">
                              <span className="text-[10px] font-bold uppercase text-slate-500">
                                Hypothesis to Verify
                              </span>
                              <p className="text-[11px] italic text-slate-600 dark:text-slate-300">
                                {proposal.hypothesis}
                              </p>
                            </div>
                          )}

                          {/* Saved confirmation state */}
                          {turn.savedAction ? (
                            <div
                              data-testid="contextual-assistant-saved-action-status"
                              className="flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-xs font-bold text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-200"
                            >
                              <Check className="size-3.5 shrink-0 text-emerald-600" />
                              <span>
                                Saved with status: {turn.savedAction.persisted_status}
                              </span>
                            </div>
                          ) : proposal.can_user_create_action && canCreateAction ? (
                            !isReviewingThisProposal ? (
                              <button
                                type="button"
                                data-testid="contextual-assistant-review-action-btn"
                                onClick={() => openProposalReview(turn.id, proposal)}
                                className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-bold text-white shadow-xs transition hover:bg-indigo-500"
                              >
                                <ClipboardCheck className="size-3.5" />
                                <span>Review action</span>
                              </button>
                            ) : (
                              <div
                                data-testid="contextual-assistant-proposal-form"
                                className="space-y-2 border-t border-indigo-200/80 pt-2 dark:border-indigo-900/50"
                              >
                                <div className="grid grid-cols-2 gap-2">
                                  <label className="block space-y-0.5">
                                    <span className="text-[10px] font-bold text-slate-600 dark:text-slate-300">
                                      Action Type
                                    </span>
                                    <select
                                      aria-label="Action Type"
                                      value={reviewDraft.action_type}
                                      onChange={(e) =>
                                        setReviewDraft((prev) =>
                                          prev
                                            ? {
                                                ...prev,
                                                action_type: e.target
                                                  .value as ActionReviewDraft['action_type'],
                                              }
                                            : prev,
                                        )
                                      }
                                      className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                                    >
                                      <option value="Coaching">Coaching</option>
                                      <option value="Training">Training</option>
                                      <option value="Monitor">Monitor</option>
                                      <option value="PIP">PIP</option>
                                    </select>
                                  </label>

                                  <label className="block space-y-0.5">
                                    <span className="text-[10px] font-bold text-slate-600 dark:text-slate-300">
                                      Priority
                                    </span>
                                    <select
                                      aria-label="Priority"
                                      value={reviewDraft.priority}
                                      onChange={(e) =>
                                        setReviewDraft((prev) =>
                                          prev
                                            ? {
                                                ...prev,
                                                priority: e.target
                                                  .value as ActionReviewDraft['priority'],
                                              }
                                            : prev,
                                        )
                                      }
                                      className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                                    >
                                      <option value="High">High</option>
                                      <option value="Medium">Medium</option>
                                      <option value="Low">Low</option>
                                    </select>
                                  </label>
                                </div>

                                <label className="block space-y-0.5">
                                  <span className="text-[10px] font-bold text-slate-600 dark:text-slate-300">
                                    Action Plan (Saved as Open Action)
                                  </span>
                                  <textarea
                                    aria-label="Action Plan"
                                    rows={2}
                                    value={reviewDraft.action_text}
                                    onChange={(e) =>
                                      setReviewDraft((prev) =>
                                        prev ? { ...prev, action_text: e.target.value } : prev,
                                      )
                                    }
                                    className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs font-medium text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                                  />
                                </label>

                                <label className="block space-y-0.5">
                                  <span className="text-[10px] font-bold text-slate-600 dark:text-slate-300">
                                    Root Cause Note (To Verify)
                                  </span>
                                  <textarea
                                    aria-label="Root Cause Note"
                                    rows={2}
                                    value={reviewDraft.root_cause_note}
                                    onChange={(e) =>
                                      setReviewDraft((prev) =>
                                        prev ? { ...prev, root_cause_note: e.target.value } : prev,
                                      )
                                    }
                                    className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs font-medium text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                                  />
                                </label>

                                {saveError && (
                                  <p
                                    role="alert"
                                    className="text-[11px] font-semibold text-rose-600 dark:text-rose-400"
                                  >
                                    {saveError}
                                  </p>
                                )}

                                <div className="flex items-center justify-end gap-2 pt-1">
                                  <button
                                    type="button"
                                    data-testid="contextual-assistant-cancel-proposal-btn"
                                    onClick={cancelProposalReview}
                                    className="cursor-pointer rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                                  >
                                    Cancel
                                  </button>
                                  <button
                                    type="button"
                                    disabled={savingAction || !reviewDraft.action_text.trim()}
                                    data-testid="contextual-assistant-confirm-proposal-btn"
                                    onClick={() => handleConfirmProposal(turn.id, proposal, res.trace_id)}
                                    className="inline-flex cursor-pointer items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1 text-xs font-bold text-white shadow-xs transition hover:bg-emerald-500 disabled:opacity-50"
                                  >
                                    <Check className="size-3.5" />
                                    <span>
                                      {savingAction ? 'Saving…' : 'Save as Open Action'}
                                    </span>
                                  </button>
                                </div>
                              </div>
                            )
                          ) : (
                            <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
                              Read-only role: share this proposal with an authorized manager to log an
                              Open action.
                            </p>
                          )}
                        </div>
                      )}

                      {/* Single Suggested Follow-Up */}
                      {res.suggested_followups && res.suggested_followups.length > 0 && (
                        <div className="pt-0.5">
                          <button
                            type="button"
                            onClick={() => sendPrompt(res.suggested_followups[0])}
                            className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700 transition hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                          >
                            <MessageSquare className="size-3 text-blue-500" />
                            <span>{res.suggested_followups[0]}</span>
                          </button>
                        </div>
                      )}

                      {/* Useful / Not Useful Feedback */}
                      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200/70 pt-2 dark:border-slate-800">
                        <span className="text-[10px] font-medium text-slate-400">
                          Verified PMS Service · {evaluatedRecordsCount} records
                        </span>
                        {turn.feedbackSubmitted ? (
                          <span
                            data-testid="contextual-assistant-feedback-recorded"
                            className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400"
                          >
                            Feedback recorded
                          </span>
                        ) : (
                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              aria-label="Useful"
                              data-testid={`feedback-up-${res.trace_id}`}
                              onClick={() =>
                                submitFeedback(turn.id, res.trace_id, 'up', 'helpful')
                              }
                              className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-600 hover:border-emerald-300 hover:text-emerald-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                            >
                              <ThumbsUp className="size-2.5" />
                              <span>Useful</span>
                            </button>
                            <button
                              type="button"
                              aria-label="Not useful"
                              data-testid={`feedback-down-${res.trace_id}`}
                              onClick={() =>
                                setTurns((prev) =>
                                  prev.map((t) =>
                                    t.id === turn.id
                                      ? {
                                          ...t,
                                          showNegativeFeedbackMenu: !t.showNegativeFeedbackMenu,
                                        }
                                      : t,
                                  ),
                                )
                              }
                              className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-600 hover:border-rose-300 hover:text-rose-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                            >
                              <ThumbsDown className="size-2.5" />
                              <span>Not useful</span>
                            </button>
                          </div>
                        )}
                      </div>

                      {/* Categorized Negative Feedback Menu */}
                      {turn.showNegativeFeedbackMenu && !turn.feedbackSubmitted && (
                        <div
                          data-testid="contextual-assistant-feedback-categories"
                          className="flex flex-wrap gap-1 pt-1"
                        >
                          {FEEDBACK_CATEGORIES.map((cat) => (
                            <button
                              key={cat.key}
                              type="button"
                              data-testid={`feedback-cat-${res.trace_id}-${cat.key}`}
                              onClick={() =>
                                submitFeedback(turn.id, res.trace_id, 'down', cat.key)
                              }
                              className="cursor-pointer rounded-md border border-rose-200 bg-rose-50 px-2 py-0.5 text-[10px] font-semibold text-rose-800 hover:bg-rose-100 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-200"
                            >
                              {cat.label}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Input Footer */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              sendPrompt(input);
            }}
            className="flex items-center gap-2 border-t border-slate-200 bg-slate-50 px-3 py-2.5 dark:border-slate-800 dark:bg-slate-900"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about this page, KPIs, or next steps…"
              aria-label="Ask PMS Contextual Assistant"
              data-testid="contextual-assistant-input"
              className="flex-1 rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
            <button
              type="submit"
              disabled={!input.trim()}
              aria-label="Send question"
              data-testid="contextual-assistant-send"
              className="inline-flex cursor-pointer items-center justify-center rounded-xl bg-blue-600 p-2 text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send className="size-3.5" />
            </button>
          </form>
        </section>
      )}
    </div>
  );
}

export default ContextualAssistantPanel;
