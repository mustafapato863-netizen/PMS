import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ClipboardCheck,
  Compass,
  HelpCircle,
  History,
  Loader2,
  MessageSquare,
  RefreshCw,
  RotateCcw,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  X,
} from 'lucide-react';
import { apiFetch } from '../../lib/apiClient';
import { useAiAvailability } from '../../features/ai/aiAvailabilityContext';
import { isAdminRole } from '../../lib/access';
import { useAuth } from '../../context/auth';
import { useUserRole } from '../../context/RoleContext';
import ExecutiveKpiStrip from './response/ExecutiveKpiStrip';
import VisualEvidenceCard from './response/VisualEvidenceCard';
import {
  formatBasisWarning,
  formatManagerReadableText,
} from './response/responseFormatting';
import type {
  AiChatMessage,
  AiChatResponsePayload,
  AiConversationDetailResponse,
  AiConversationListResponse,
  AiConversationSummaryItem,
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
  variationSeed?: number;
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
              : ctx.page_id === 'insights'
                ? 'Performance Insights'
                : ctx.page_id === 'corrective_actions'
                  ? 'Corrective Actions'
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
  const periodLabel = ctx.month || 'the latest period';

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

  if (ctx.page_id === 'team_dashboard') {
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

  if (ctx.page_id === 'executive_summary') {
    return [
      'Explain this page',
      `Which team in ${scope} dropped most?`,
      'Compare branch performance in this scope',
      'Show KPI achievement vs target',
    ];
  }

  if (ctx.page_id === 'function_summary') {
    return [
      'Explain this page',
      `Which team in ${scope} dropped most?`,
      `Show 6-month performance trend for ${scope}`,
      `What are the largest KPI gaps in ${scope}?`,
    ];
  }

  if (ctx.page_id === 'employee_profile') {
    const prompts = [
      'Explain this page',
      `Why did performance change in ${periodLabel}?`,
      'Which KPI has the largest gap?',
    ];
    if (canCreateAction && !ctx.is_fallback_data) {
      prompts.push(`Propose a corrective action for ${metric}`);
    }
    return prompts;
  }

  if (ctx.page_id === 'insights') {
    return [
      'Explain this page',
      `Which team in ${scope} dropped most?`,
      `What are the largest KPI gaps in ${scope}?`,
      'Show overdue corrective actions',
    ];
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
  const navigate = useNavigate();
  const pilotVisible = aiEnabled && isAdminRole(role);
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const [input, setInput] = useState('');
  const [turns, setTurns] = useState<AssistantTurn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [activeProposalTurnId, setActiveProposalTurnId] = useState<string | null>(null);
  const [reviewDraft, setReviewDraft] = useState<ActionReviewDraft | null>(null);
  const [savingAction, setSavingAction] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [historyItems, setHistoryItems] = useState<AiConversationSummaryItem[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deletingConvId, setDeletingConvId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [promotingConvId, setPromotingConvId] = useState<string | null>(null);
  const [promoteError, setPromoteError] = useState<string | null>(null);

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
  const historyFetchSeqRef = useRef(0);
  const deletedConvIdsRef = useRef<Set<string>>(new Set());
  const confirmDeleteIdRef = useRef<string | null>(null);
  useEffect(() => {
    confirmDeleteIdRef.current = confirmDeleteId;
  });
  const cancelDeleteBtnRef = useRef<HTMLButtonElement>(null);

  const confirmDeleteConv = confirmDeleteId
    ? historyItems.find((c) => c.conversation_id === confirmDeleteId) ?? {
        conversation_id: confirmDeleteId,
        title: null,
      }
    : null;

  useEffect(() => {
    if (!isOpen || !confirmDeleteId) return;
    cancelDeleteBtnRef.current?.focus();
  }, [isOpen, confirmDeleteId]);

  const refreshPageAssistantHistory = useCallback(async () => {
    const seq = ++historyFetchSeqRef.current;
    setIsLoadingHistory(true);
    setHistoryError(null);
    try {
      const res = await apiFetch<AiConversationListResponse>(
        '/api/ai/conversations?origin=page_assistant',
      );
      if (seq !== historyFetchSeqRef.current) return;
      const items = (Array.isArray(res?.conversations) ? res.conversations : []).filter(
        (conv) => !deletedConvIdsRef.current.has(conv.conversation_id),
      );
      setHistoryItems(items);
    } catch {
      if (seq === historyFetchSeqRef.current) {
        setHistoryError('Could not load recent page-assistant conversations.');
      }
    } finally {
      if (seq === historyFetchSeqRef.current) {
        setIsLoadingHistory(false);
      }
    }
  }, []);

  useEffect(() => {
    if (isOpen && showHistory) {
      const timer = setTimeout(() => {
        void refreshPageAssistantHistory();
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [isOpen, showHistory, refreshPageAssistantHistory]);

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

  const handleNewChat = useCallback(() => {
    if (confirmDeleteIdRef.current !== null) {
      return;
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    requestSeqRef.current += 1;
    setTurns([]);
    setConversationId(null);
    setActiveProposalTurnId(null);
    setReviewDraft(null);
    setSaveError(null);
    setPromoteError(null);
    setDeleteError(null);
    setShowHistory(false);
    setInput('');
  }, []);

  const handleResumeConversation = useCallback(async (targetConvId: string) => {
    if (confirmDeleteIdRef.current !== null) return;
    setIsLoadingConversation(true);
    setHistoryError(null);
    setPromoteError(null);
    try {
      const res = await apiFetch<AiConversationDetailResponse>(
        `/api/ai/conversations/${encodeURIComponent(targetConvId)}?origin=page_assistant`,
      );
      const detail = res?.data;
      if (!detail?.conversation_id || detail.origin !== 'page_assistant') {
        throw new Error('Conversation not found');
      }
      const hydrated: AssistantTurn[] = (detail.turns || []).map((t) => ({
        id: t.turn_id,
        prompt: t.user_prompt,
        variationSeed: t.retry_settings?.variation_seed ?? 0,
        response: t.response ?? null,
        error:
          t.status === 'failed' || t.status === 'pending'
            ? t.error_message || 'Unable to complete the assistant request right now.'
            : null,
        loading: false,
      }));
      setConversationId(detail.conversation_id);
      setTurns(hydrated);
      setActiveProposalTurnId(null);
      setReviewDraft(null);
      setSaveError(null);
      setShowHistory(false);
    } catch {
      setHistoryError('Could not load this conversation. Please try again.');
    } finally {
      setIsLoadingConversation(false);
    }
  }, []);

  const handleDeletePageAssistantConversation = useCallback(
    async (targetConvId: string) => {
      setDeletingConvId(targetConvId);
      setDeleteError(null);
      try {
        await apiFetch(`/api/ai/conversations/${encodeURIComponent(targetConvId)}`, {
          method: 'DELETE',
        });
        deletedConvIdsRef.current.add(targetConvId);
        historyFetchSeqRef.current += 1;
        setIsLoadingHistory(false);
        setConfirmDeleteId(null);
        setHistoryItems((prev) =>
          prev.filter((conv) => conv.conversation_id !== targetConvId),
        );
        if (conversationId === targetConvId) {
          setConversationId(null);
          setTurns([]);
          setActiveProposalTurnId(null);
          setReviewDraft(null);
        }
      } catch {
        setConfirmDeleteId(null);
        setDeleteError('Could not delete this conversation. Please try again.');
      } finally {
        setDeletingConvId(null);
      }
    },
    [conversationId],
  );

  const handleContinueInWorkspace = useCallback(
    async (targetConvId: string) => {
      if (!targetConvId || promotingConvId) return;
      setPromotingConvId(targetConvId);
      setPromoteError(null);
      try {
        await apiFetch(`/api/ai/conversations/${encodeURIComponent(targetConvId)}/promote`, {
          method: 'POST',
        });
        setIsOpen(false);
        navigate(`/ai?conversation=${encodeURIComponent(targetConvId)}`);
      } catch {
        setPromoteError('Could not open this conversation in PMS AI. Please try again.');
      } finally {
        setPromotingConvId(null);
      }
    },
    [navigate, promotingConvId],
  );

  const sendPrompt = useCallback(
    async (promptText: string, opts?: { variationSeed?: number }) => {
      const trimmed = promptText.trim();
      if (!trimmed || !isAdminRole(role) || !aiEnabled) return;

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const controller = new AbortController();
      abortControllerRef.current = controller;
      const currentSeq = requestSeqRef.current + 1;
      requestSeqRef.current = currentSeq;

      const historyPayload: AiChatMessage[] = [];
      for (const t of turns.filter((item) => !item.loading && item.response?.headline).slice(-4)) {
        historyPayload.push({ role: 'user', content: t.prompt });
        if (t.response?.headline) {
          historyPayload.push({ role: 'assistant', content: t.response.headline });
        }
      }

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
          variationSeed: opts?.variationSeed ?? 0,
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
              origin: 'page_assistant',
              conversation_id: conversationId,
              client_request_id: turnId,
              answer_detail: 'brief',
              page_context: pageContext,
              history: historyPayload,
              ...(typeof opts?.variationSeed === 'number' && opts.variationSeed > 0
                ? { variation_seed: opts.variationSeed }
                : {}),
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
    [aiEnabled, conversationId, pageContext, role, turns],
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

  // Keyboard Escape closes active sub-dialog first, then panel
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (confirmDeleteId) {
          e.preventDefault();
          if (deletingConvId !== confirmDeleteId) {
            setConfirmDeleteId(null);
          }
        } else if (activeProposalTurnId) {
          cancelProposalReview();
        } else if (showHistory) {
          setShowHistory(false);
        } else {
          setIsOpen(false);
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeProposalTurnId, cancelProposalReview, confirmDeleteId, deletingConvId, isOpen, showHistory]);

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
            <span className="rounded-full bg-blue-500/20 px-2 py-0.5 text-xs font-semibold text-blue-200">
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
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Sparkles className="size-4 shrink-0 text-blue-400" aria-hidden="true" />
                <h2 className="text-sm font-bold tracking-tight">PMS Contextual Assistant</h2>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    if (confirmDeleteIdRef.current !== null) return;
                    setShowHistory((prev) => !prev);
                  }}
                  aria-expanded={showHistory}
                  aria-label={showHistory ? 'Hide recent assistant chats' : 'Show recent assistant chats'}
                  data-testid="contextual-assistant-history-toggle"
                  className={`inline-flex cursor-pointer items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold transition ${
                    showHistory
                      ? 'bg-blue-600 text-white'
                      : 'bg-white/10 text-slate-200 hover:bg-white/20'
                  }`}
                >
                  <History className="size-3" />
                  <span>Recent</span>
                </button>
                {(turns.length > 0 || conversationId !== null) && (
                  <button
                    type="button"
                    onClick={handleNewChat}
                    data-testid="contextual-assistant-new-chat"
                    aria-label="Start new chat"
                    className="inline-flex cursor-pointer items-center gap-1 rounded-md bg-white/10 px-2 py-1 text-xs font-semibold text-slate-200 transition hover:bg-white/20"
                  >
                    <RotateCcw className="size-3" />
                    <span>New chat</span>
                  </button>
                )}
                <Link
                  to="/ai"
                  className="rounded-md bg-white/10 px-2 py-1 text-xs font-semibold text-slate-200 transition hover:bg-white/20"
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
              className="mt-1.5 truncate rounded-lg bg-white/10 px-2.5 py-1 text-xs font-medium text-blue-100"
              title={effectiveContextLabel}
            >
              {effectiveContextLabel}
            </p>
            {conversationId && !showHistory && (
              <div className="mt-2 flex items-center justify-between gap-2 rounded-lg bg-white/10 px-2.5 py-1.5">
                <span className="text-xs font-medium text-slate-200">
                  Saved in page assistant
                </span>
                <button
                  type="button"
                  disabled={promotingConvId === conversationId}
                  data-testid="contextual-assistant-continue-workspace"
                  onClick={() => void handleContinueInWorkspace(conversationId)}
                  className="inline-flex cursor-pointer items-center gap-1 rounded-md bg-blue-600 px-2.5 py-1 text-xs font-bold text-white transition hover:bg-blue-500 disabled:opacity-50"
                >
                  {promotingConvId === conversationId ? (
                    <>
                      <Loader2 className="size-3 animate-spin" />
                      <span>Opening…</span>
                    </>
                  ) : (
                    <>
                      <span>Continue in PMS AI</span>
                      <ArrowRight className="size-3" />
                    </>
                  )}
                </button>
              </div>
            )}
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

          {promoteError && (
            <div
              role="alert"
              className="flex items-center justify-between gap-2 border-b border-rose-200 bg-rose-50 px-3.5 py-2 text-xs font-semibold text-rose-800"
            >
              <span>{promoteError}</span>
              <button
                type="button"
                aria-label="Dismiss error"
                onClick={() => setPromoteError(null)}
                className="rounded p-0.5 text-rose-700 hover:bg-rose-100"
              >
                <X className="size-3" />
              </button>
            </div>
          )}

          {/* Conversation / Recent History Body */}
          <div className="flex-1 space-y-3 overflow-y-auto p-3.5">
            {showHistory ? (
              <div data-testid="contextual-assistant-history-view" className="space-y-2.5">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <h3 className="text-xs font-extrabold text-slate-900 dark:text-slate-100">
                      Recent page-assistant chats ({historyItems.length})
                    </h3>
                    <p className="text-xs font-medium text-slate-500">
                      Resume here or promote to Full PMS AI
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowHistory(false)}
                    className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                  >
                    Back to chat
                  </button>
                </div>

                {deleteError && (
                  <div
                    role="alert"
                    data-testid="contextual-assistant-delete-error"
                    className="flex items-center justify-between gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-800"
                  >
                    <span>{deleteError}</span>
                    <button
                      type="button"
                      aria-label="Dismiss delete error"
                      onClick={() => setDeleteError(null)}
                      className="rounded p-0.5 text-rose-700 hover:bg-rose-100"
                    >
                      <X className="size-3" />
                    </button>
                  </div>
                )}

                {isLoadingHistory && historyItems.length === 0 ? (
                  <div className="space-y-2" aria-label="Loading recent page-assistant chats">
                    <div className="h-14 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
                    <div className="h-14 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
                    <div className="h-14 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
                  </div>
                ) : historyError && historyItems.length === 0 ? (
                  <div
                    role="alert"
                    className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-center text-xs text-rose-800"
                  >
                    <p className="font-semibold">{historyError}</p>
                    <button
                      type="button"
                      onClick={() => void refreshPageAssistantHistory()}
                      className="mt-2 inline-flex items-center gap-1 rounded-full border border-rose-300 bg-white px-3 py-1 text-xs font-bold text-rose-700 hover:bg-rose-100"
                    >
                      <RotateCcw className="size-3" />
                      <span>Retry</span>
                    </button>
                  </div>
                ) : historyItems.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-4 text-center text-xs font-medium text-slate-500 dark:border-slate-800 dark:bg-slate-900">
                    No saved page-assistant conversations yet.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {historyError && (
                      <div
                        role="alert"
                        className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-800"
                      >
                        {historyError}
                      </div>
                    )}
                    {historyItems.map((conv) => {
                      const isActive = conversationId === conv.conversation_id;
                      const isPromoting = promotingConvId === conv.conversation_id;
                      return (
                        <div
                          key={conv.conversation_id}
                          data-testid={`contextual-assistant-history-item-${conv.conversation_id}`}
                          className={`space-y-2 rounded-xl border p-2.5 transition-colors ${
                            isActive
                              ? 'border-blue-300 bg-blue-50/70'
                              : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <button
                              type="button"
                              disabled={isLoadingConversation}
                              onClick={() => void handleResumeConversation(conv.conversation_id)}
                              className="min-w-0 flex-1 cursor-pointer text-left disabled:opacity-60"
                            >
                              <div className="flex items-center gap-1.5">
                                <p className="truncate text-xs font-bold text-slate-900 dark:text-slate-100">
                                  {conv.title || 'New conversation'}
                                </p>
                                {isActive && (
                                  <span className="shrink-0 rounded-full border border-blue-200 bg-blue-100 px-1.5 py-0.5 text-xs font-bold text-blue-700">
                                    Active
                                  </span>
                                )}
                              </div>
                              <p className="mt-0.5 truncate text-xs text-slate-500">
                                {conv.turn_count} {conv.turn_count === 1 ? 'turn' : 'turns'}
                                {conv.last_scope_banner ? ` · ${conv.last_scope_banner}` : ''}
                              </p>
                            </button>
                            <button
                              type="button"
                              aria-label={`Delete conversation ${conv.title || conv.conversation_id}`}
                              onClick={() => {
                                setDeleteError(null);
                                setConfirmDeleteId(conv.conversation_id);
                              }}
                              className="rounded-lg p-1 text-slate-400 transition-colors hover:bg-rose-50 hover:text-rose-600"
                            >
                              <Trash2 className="size-3.5" />
                            </button>
                          </div>
                          <div className="flex items-center justify-end">
                            <button
                              type="button"
                              disabled={isPromoting}
                              data-testid={`contextual-assistant-promote-${conv.conversation_id}`}
                              onClick={() => void handleContinueInWorkspace(conv.conversation_id)}
                              className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-bold text-blue-700 transition hover:bg-blue-600 hover:text-white disabled:opacity-50"
                            >
                              {isPromoting ? (
                                <>
                                  <Loader2 className="size-3 animate-spin" />
                                  <span>Opening…</span>
                                </>
                              ) : (
                                <>
                                  <span>Continue in PMS AI</span>
                                  <ArrowRight className="size-3" />
                                </>
                              )}
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : (
              <>
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

            {turns.map((turn, idx) => {
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

                  {/* Structured 3-bar skeleton loader */}
                  {turn.loading && (
                    <div
                      role="status"
                      aria-label="Loading assistant answer"
                      className="space-y-2 py-1.5"
                    >
                      <div className="h-3 w-3/4 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
                      <div className="h-3 w-full animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
                      <div className="h-3 w-5/6 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
                      <span className="sr-only">Verifying authorized PMS evidence…</span>
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
                        <div className="flex flex-wrap items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
                          <span className="rounded bg-slate-200/70 px-1.5 py-0.5 dark:bg-slate-800">
                            {res.effective_context_label || res.scope_banner}
                          </span>
                        </div>
                      )}

                      {/* 1-2 sentence direct answer */}
                      <p
                        data-testid="contextual-assistant-direct-answer"
                        className="text-sm font-bold leading-relaxed text-slate-900 dark:text-slate-100"
                      >
                        {formatManagerReadableText(res.headline)}
                      </p>

                      {/* Compact Executive KPI Summary Tiles */}
                      <ExecutiveKpiStrip tiles={res.summary_tiles ?? []} compact />

                      {/* Supporting Narrative Bullets (up to 3) */}
                      {res.narrative_bullets && res.narrative_bullets.length > 0 && (
                        <ul
                          data-testid="contextual-assistant-bullets"
                          className="space-y-1.5 rounded-xl border border-slate-200/80 bg-white/95 px-3 py-2.5 text-sm leading-relaxed text-slate-700 dark:border-slate-800 dark:bg-slate-950/70 dark:text-slate-200"
                        >
                          {res.narrative_bullets.slice(0, 3).map((bullet, bIdx) => (
                            <li key={bIdx} className="flex items-start gap-2">
                              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500" />
                              <span>{formatManagerReadableText(bullet)}</span>
                            </li>
                          ))}
                        </ul>
                      )}

                      {/* Primary Inline Visual Evidence (Chart / Bars / Table) */}
                      {res.visual_cards &&
                        res.visual_cards.filter((c) => c.card_type !== 'decision_playbook')[0] && (
                          <VisualEvidenceCard
                            card={
                              res.visual_cards.filter((c) => c.card_type !== 'decision_playbook')[0]
                            }
                          />
                        )}

                      {/* Material basis warning */}
                      {res.basis_warning && (
                        <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50/80 px-3 py-2 text-xs font-medium text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200">
                          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
                          <span>{formatBasisWarning(res.basis_warning)}</span>
                        </div>
                      )}

                      {/* Page Help Section */}
                      {res.page_help && (
                        <div className="space-y-1.5 rounded-lg border border-slate-200 bg-white p-2.5 dark:border-slate-800 dark:bg-slate-950">
                          <div className="flex items-center gap-1 font-bold text-slate-800 dark:text-slate-100">
                            <HelpCircle className="size-3 text-blue-600" />
                            <span>{res.page_help.page_title}</span>
                          </div>
                          <p className="text-xs leading-relaxed text-slate-600 dark:text-slate-300">
                            {res.page_help.summary}
                          </p>
                          {res.page_help.metric_explanation && (
                            <p className="text-xs font-medium text-blue-700 dark:text-blue-300">
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
                            className="inline-flex items-center gap-1 text-xs font-bold text-blue-600 hover:underline dark:text-blue-400"
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
                            <span className="inline-flex items-center gap-1 text-xs font-extrabold uppercase tracking-wider text-indigo-800 dark:text-indigo-300">
                              <ClipboardCheck className="size-3.5" />
                              <span>Evidence-Based Proposal ({proposal.team})</span>
                            </span>
                            {proposal.metric_display_name && (
                              <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-xs font-bold text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200">
                                {proposal.metric_display_name}
                              </span>
                            )}
                          </div>

                          {/* Observed Facts vs Hypotheses */}
                          {proposal.observed_facts.length > 0 && (
                            <div className="space-y-0.5">
                              <span className="text-xs font-bold uppercase text-slate-500">
                                Observed PMS Facts
                              </span>
                              <ul className="list-disc space-y-0.5 pl-4 text-xs text-slate-700 dark:text-slate-200">
                                {proposal.observed_facts.map((fact, idx) => (
                                  <li key={idx}>{fact}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {proposal.hypothesis && (
                            <div className="space-y-0.5">
                              <span className="text-xs font-bold uppercase text-slate-500">
                                Hypothesis to Verify
                              </span>
                              <p className="text-xs italic text-slate-600 dark:text-slate-300">
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
                                    <span className="text-xs font-bold text-slate-600 dark:text-slate-300">
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
                                    <span className="text-xs font-bold text-slate-600 dark:text-slate-300">
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
                                  <span className="text-xs font-bold text-slate-600 dark:text-slate-300">
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
                                  <span className="text-xs font-bold text-slate-600 dark:text-slate-300">
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
                                    className="text-xs font-semibold text-rose-600 dark:text-rose-400"
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
                            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                              Read-only role: share this proposal with an authorized manager to log an
                              Open action.
                            </p>
                          )}
                        </div>
                      )}

                      {/* Up to 3 Suggested Follow-Ups */}
                      {res.suggested_followups && res.suggested_followups.length > 0 && (
                        <div
                          data-testid="contextual-assistant-followups"
                          className="flex flex-wrap gap-1.5 pt-0.5"
                        >
                          {res.suggested_followups.slice(0, 3).map((followup) => (
                            <button
                              key={followup}
                              type="button"
                              onClick={() => sendPrompt(followup)}
                              className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 transition hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                            >
                              <MessageSquare className="size-3 text-blue-500" />
                              <span>{followup}</span>
                            </button>
                          ))}
                        </div>
                      )}

                      {/* Different Angle + Useful / Not Useful Feedback */}
                      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200/70 pt-2 dark:border-slate-800">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-xs font-medium text-slate-400">
                            Verified PMS Service · {evaluatedRecordsCount} records
                          </span>
                          <button
                            type="button"
                            data-testid={`rephrase-turn-${idx}`}
                            aria-label="Get a different reply angle"
                            onClick={() =>
                              sendPrompt(turn.prompt, {
                                variationSeed: (turn.variationSeed ?? 0) + 1,
                              })
                            }
                            className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-xs font-semibold text-slate-600 transition hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                          >
                            <RefreshCw className="size-3" />
                            <span>Different angle</span>
                          </button>
                        </div>
                        {turn.feedbackSubmitted ? (
                          <span
                            data-testid="contextual-assistant-feedback-recorded"
                            className="text-xs font-semibold text-emerald-600 dark:text-emerald-400"
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
                              className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-xs font-semibold text-slate-600 hover:border-emerald-300 hover:text-emerald-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
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
                              className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-xs font-semibold text-slate-600 hover:border-rose-300 hover:text-rose-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
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
                              className="cursor-pointer rounded-md border border-rose-200 bg-rose-50 px-2 py-0.5 text-xs font-semibold text-rose-800 hover:bg-rose-100 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-200"
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
              </>
            )}
          </div>

          {/* Input Footer */}
          {!showHistory && (
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
          )}

          {confirmDeleteConv && (
            <div
              className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/45 p-4 backdrop-blur-[1px]"
              onClick={(e) => {
                if (
                  e.target === e.currentTarget &&
                  deletingConvId !== confirmDeleteConv.conversation_id
                ) {
                  setConfirmDeleteId(null);
                }
              }}
            >
              <div
                role="dialog"
                aria-modal="true"
                aria-labelledby="ctx-delete-conv-dialog-title"
                aria-describedby="ctx-delete-conv-dialog-desc"
                data-testid="contextual-assistant-delete-dialog"
                className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl dark:border-slate-800 dark:bg-slate-950"
              >
                <h3
                  id="ctx-delete-conv-dialog-title"
                  className="text-sm font-extrabold text-slate-900 dark:text-slate-100"
                >
                  Delete "{confirmDeleteConv.title || 'New conversation'}"?
                </h3>
                <p
                  id="ctx-delete-conv-dialog-desc"
                  className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-slate-300"
                >
                  This permanently removes this saved page-assistant conversation.
                </p>
                <div className="mt-4 flex items-center justify-end gap-2">
                  <button
                    ref={cancelDeleteBtnRef}
                    type="button"
                    disabled={deletingConvId === confirmDeleteConv.conversation_id}
                    onClick={() => setConfirmDeleteId(null)}
                    className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 transition-colors hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={deletingConvId === confirmDeleteConv.conversation_id}
                    onClick={() =>
                      void handleDeletePageAssistantConversation(confirmDeleteConv.conversation_id)
                    }
                    className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-bold text-white transition-colors hover:bg-rose-700 disabled:opacity-50"
                  >
                    {deletingConvId === confirmDeleteConv.conversation_id ? (
                      <>
                        <Loader2 className="size-3 animate-spin" />
                        <span>Deleting…</span>
                      </>
                    ) : (
                      <span>Delete chat</span>
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

export default ContextualAssistantPanel;
