import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Bell,
  Calendar,
  ChevronDown,
  History,
  Info,
  Lock,
  RotateCcw,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  X,
} from 'lucide-react';
import { useAuth } from '../context/auth';
import { useAppStore } from '../store/appStore';
import { apiFetch } from '../lib/apiClient';
import type { User } from '../types';
import AiResponseCard from '../components/ai/AiResponseCard';
import AiWatchingRail from '../components/ai/AiWatchingRail';
import ConversationHistoryPanel from '../components/ai/ConversationHistoryPanel';
import ScopeFilterBar from '../components/ai/ScopeFilterBar';
import { Agent360Scorecard } from '../components/ai/agent360/Agent360Scorecard';
import AiComposerDock from '../components/ai/workspace/AiComposerDock';
import AiMorningBriefingHome from '../components/ai/workspace/AiMorningBriefingHome';
import AiThinkingProgressCard from '../components/ai/workspace/AiThinkingProgressCard';
import { buildFallbackStarterPrompts, mergeStarterScenarios } from '../features/ai/starterPrompts';
import type {
  AiChatMessage,
  AiChatResponsePayload,
  AiConversationDetailResponse,
  AiConversationListResponse,
  AiConversationSummaryItem,
  AiStarterPrompt,
  AiWatchingPayload,
  ConfirmedQueryContext,
  SessionFilterContext,
  AiConversationRetrySettings,
} from '../features/ai/types';

type CatalogChoice = string | { value?: string; key?: string; label?: string; name?: string; badge?: string | null; function?: string; function_key?: string; regions?: string[] };
interface CatalogOptions {
  eligible_functions?: CatalogChoice[];
  eligible_regions?: string[];
  metrics?: Array<{ team: string; position?: string | null; performance_level: string }>;
  functions?: CatalogChoice[];
  eligible_teams?: CatalogChoice[];
  teams?: CatalogChoice[];
  eligible_branches?: CatalogChoice[];
  branches?: CatalogChoice[];
  eligible_levels?: CatalogChoice[];
  performance_levels?: CatalogChoice[];
}

interface ConversationTurn {
  id: string;
  userPrompt: string;
  clientRequestId?: string;
  clarificationChoiceId?: string;
  variationSeed?: number;
  retrySettings?: AiConversationRetrySettings;
  response?: AiChatResponsePayload;
  error?: string;
  conflictCode?: 404 | 409;
  isPending?: boolean;
}

interface ChatSessionState {
  chatKey: string;
  conversationId: string | null;
  contextVersion: number;
  lastConfirmedQuery: ConfirmedQueryContext | null;
  turns: ConversationTurn[];
  isSending: boolean;
  abortController: AbortController | null;
  requestSeq: number;
}

function createDraftKey(): string {
  return `draft-${globalThis.crypto.randomUUID()}`;
}

function makeEmptyChatSession(chatKey: string, conversationId: string | null = null): ChatSessionState {
  return {
    chatKey,
    conversationId,
    contextVersion: 0,
    lastConfirmedQuery: null,
    turns: [],
    isSending: false,
    abortController: null,
    requestSeq: 0,
  };
}

export default function PmsAiWorkspaceView() {
  const { currentUser } = useAuth();
  return <PmsAiWorkspaceSession key={currentUser?.id ?? 'anonymous'} currentUser={currentUser} />;
}

function PmsAiWorkspaceSession({ currentUser }: { currentUser: User | null }) {
  const isSelfOnly = Boolean(currentUser?.is_self_only || currentUser?.role === 'Agent' || currentUser?.role === 'Employee');
  const activeMonth = useAppStore((s) => s.activeMonth);
  const [searchParams, setSearchParams] = useSearchParams();
  const setSearchParamsRef = useRef(setSearchParams);
  useEffect(() => {
    setSearchParamsRef.current = setSearchParams;
  });
  const storageKey = `pms_ai_last_conversation_${currentUser?.id ?? 'anonymous'}`;

  const [selectedTeam, setSelectedTeam] = useState<string>(
    () => searchParams.get('team') || 'All',
  );
  const [selectedBranch, setSelectedBranch] = useState<string>(
    () => searchParams.get('branch') || 'all',
  );
  const [selectedLevel, setSelectedLevel] = useState<string>(
    () => searchParams.get('performance_level') || 'All',
  );
  const [answerDetail, setAnswerDetail] = useState<'auto' | 'brief' | 'details'>('auto');
  const [promptInput, setPromptInput] = useState('');

  const initialConvParam = searchParams.get('conversation');
  const [activeChatKey, setActiveChatKey] = useState<string>(
    () => initialConvParam || createDraftKey(),
  );
  const [sessionsByKey, setSessionsByKey] = useState<Record<string, ChatSessionState>>(() => ({
    [initialConvParam || activeChatKey]: makeEmptyChatSession(
      initialConvParam || activeChatKey,
      initialConvParam || null,
    ),
  }));
  const [recentConversations, setRecentConversations] = useState<AiConversationSummaryItem[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [isLoadingConversation, setIsLoadingConversation] = useState<boolean>(false);
  const openConversationSequence = useRef(0);
  const [conversationNotice, setConversationNotice] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deletingConvId, setDeletingConvId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const confirmDeleteIdRef = useRef<string | null>(null);
  useEffect(() => {
    confirmDeleteIdRef.current = confirmDeleteId;
  });
  const historyFetchSeqRef = useRef<number>(0);
  const deletedConvIdsRef = useRef<Set<string>>(new Set());
  const [showHistoryPanel, setShowHistoryPanel] = useState<boolean>(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(min-width: 1024px)').matches
      : false,
  );

  const [showFilters, setShowFilters] = useState<boolean>(false);
  const [showGuardrailsInfo, setShowGuardrailsInfo] = useState<boolean>(false);
  const [showMidChatScenarios, setShowMidChatScenarios] = useState<boolean>(false);
  const [showWatchingPanel, setShowWatchingPanel] = useState<boolean>(false);

  useEffect(() => {
    if (!showGuardrailsInfo) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowGuardrailsInfo(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [showGuardrailsInfo]);

  const sessionsRef = useRef<Record<string, ChatSessionState>>(sessionsByKey);
  const activeChatKeyRef = useRef<string>(activeChatKey);
  const searchParamsRef = useRef(searchParams);
  useEffect(() => {
    sessionsRef.current = sessionsByKey;
    activeChatKeyRef.current = activeChatKey;
    searchParamsRef.current = searchParams;
  });
  const userInteractedRef = useRef<boolean>(false);
  const streamEndRef = useRef<HTMLDivElement>(null);

  const activeSession = useMemo(
    () => sessionsByKey[activeChatKey] ?? makeEmptyChatSession(activeChatKey),
    [sessionsByKey, activeChatKey],
  );
  const turns = activeSession.turns;
  const conversationId = activeSession.conversationId;
  const lastConfirmedQuery = activeSession.lastConfirmedQuery;
  const isSending = activeSession.isSending;

  const updateSession = useCallback(
    (chatKey: string, updater: (prev: ChatSessionState) => ChatSessionState) => {
      const currMap = sessionsRef.current;
      const existing = currMap[chatKey] ?? makeEmptyChatSession(chatKey);
      const nextSession = updater(existing);
      const nextMap = { ...currMap, [chatKey]: nextSession };
      sessionsRef.current = nextMap;
      setSessionsByKey(nextMap);
      return nextSession;
    },
    [],
  );

  const setUrlConversationParam = useCallback(
    (nextConvId: string | null) => {
      const next = new URLSearchParams(searchParamsRef.current);
      if (nextConvId) {
        next.set('conversation', nextConvId);
      } else {
        next.delete('conversation');
      }
      setSearchParamsRef.current(next, { replace: true });
    },
    [],
  );

  const saveLastConversationId = useCallback(
    (nextConvId: string | null) => {
      try {
        if (nextConvId) {
          sessionStorage.setItem(storageKey, nextConvId);
        } else {
          sessionStorage.removeItem(storageKey);
        }
      } catch {
        // Ignore storage errors in restricted contexts
      }
    },
    [storageKey],
  );

  const cancelActiveChatInFlight = useCallback(() => {
    const key = activeChatKeyRef.current;
    const curr = sessionsRef.current[key];
    if (!curr) return;
    if (curr.abortController) {
      curr.abortController.abort();
    }
    updateSession(key, (prev) => ({
      ...prev,
      requestSeq: prev.requestSeq + 1,
      abortController: null,
      isSending: false,
      turns: prev.turns.filter((t) => !t.isPending),
    }));
  }, [updateSession]);

  useEffect(
    () => () => {
      for (const sess of Object.values(sessionsRef.current)) {
        sess.abortController?.abort();
      }
    },
    [],
  );

  const refreshRecentConversations = useCallback(async (): Promise<AiConversationSummaryItem[]> => {
    const seq = ++historyFetchSeqRef.current;
    setIsLoadingHistory(true);
    setHistoryError(null);
    try {
      const [workspaceResult, legacyResult] = await Promise.allSettled([
        apiFetch<AiConversationListResponse>('/api/ai/conversations?origin=workspace&limit=50'),
        apiFetch<AiConversationListResponse>('/api/ai/conversations?origin=legacy&limit=50'),
      ]);
      if (seq !== historyFetchSeqRef.current) {
        return [];
      }
      if (workspaceResult.status === 'rejected' && legacyResult.status === 'rejected') {
        throw workspaceResult.reason;
      }
      const workspaceItems =
        workspaceResult.status === 'fulfilled' && Array.isArray(workspaceResult.value?.conversations)
          ? workspaceResult.value.conversations
          : [];
      const legacyItems =
        legacyResult.status === 'fulfilled' && Array.isArray(legacyResult.value?.conversations)
          ? legacyResult.value.conversations
          : [];
      const items = [...workspaceItems, ...legacyItems]
        .filter((conv) => !deletedConvIdsRef.current.has(conv.conversation_id))
        .sort((a, b) => {
          const aDate = Date.parse(a.updated_at || a.created_at || '') || 0;
          const bDate = Date.parse(b.updated_at || b.created_at || '') || 0;
          return bDate - aDate;
        })
        .slice(0, 50);
      setRecentConversations(items);
      return items;
    } catch {
      if (seq === historyFetchSeqRef.current) {
        setHistoryError('Could not load recent conversations.');
      }
      return [];
    } finally {
      if (seq === historyFetchSeqRef.current) {
        setIsLoadingHistory(false);
      }
    }
  }, []);

  const openConversation = useCallback(
    async (targetConvId: string, requestedOrigin: 'workspace' | 'legacy' = 'workspace') => {
      if (confirmDeleteIdRef.current !== null) {
        return;
      }
      const sequence = ++openConversationSequence.current;
      userInteractedRef.current = true;
      setConversationNotice(null);
      setDeleteError(null);

      // If this conversation is already live in memory with an active or loaded stream, switch straight to it
      // without disturbing any in-flight request on either chat.
      const existingInMemory = sessionsRef.current[targetConvId];
      if (requestedOrigin === 'workspace' && existingInMemory?.isSending) {
        setIsLoadingConversation(false);
        activeChatKeyRef.current = targetConvId;
        setActiveChatKey(targetConvId);
        setUrlConversationParam(targetConvId);
        saveLastConversationId(targetConvId);
        return;
      }

      setIsLoadingConversation(true);
      try {
        const res = await apiFetch<AiConversationDetailResponse>(
          `/api/ai/conversations/${encodeURIComponent(targetConvId)}?origin=${requestedOrigin}`,
        );
        if (sequence !== openConversationSequence.current) return;
        const detail = res?.data;
        if (!detail || !detail.conversation_id) {
          throw new Error('404: Conversation not found');
        }
        const storedOrigin = detail.origin ?? 'workspace';
        if (
          (requestedOrigin === 'workspace' && storedOrigin !== 'workspace') ||
          (requestedOrigin === 'legacy' && storedOrigin !== 'legacy' && storedOrigin !== 'workspace')
        ) {
          throw new Error('Conversation origin changed. Refresh recent chats and try again.');
        }
        if (requestedOrigin === 'legacy' && storedOrigin === 'legacy') {
          await apiFetch(`/api/ai/conversations/${encodeURIComponent(targetConvId)}/promote`, {
            method: 'POST',
          });
          void refreshRecentConversations();
        }
        const hydratedTurns: ConversationTurn[] = (detail.turns || []).map((t) => {
          const isFailed = t.status === 'failed' || t.status === 'pending';
          return {
            id: t.turn_id,
            userPrompt: t.user_prompt,
            clientRequestId: t.client_request_id ?? undefined,
            retrySettings: t.retry_settings ?? undefined,
            clarificationChoiceId: t.retry_settings?.clarification_choice_id ?? undefined,
            variationSeed: t.retry_settings?.variation_seed ?? undefined,
            response: t.response ?? undefined,
            error: isFailed ? t.error_message || 'Unable to complete analysis' : undefined,
          };
        });
        const resolvedId = detail.conversation_id;
        updateSession(resolvedId, (prev) => ({
          ...prev,
          chatKey: resolvedId,
          conversationId: resolvedId,
          contextVersion: detail.context_version ?? 1,
          lastConfirmedQuery: detail.confirmed_context ?? null,
          turns: prev.isSending ? prev.turns : hydratedTurns,
        }));
        activeChatKeyRef.current = resolvedId;
        setActiveChatKey(resolvedId);
        setUrlConversationParam(resolvedId);
        saveLastConversationId(resolvedId);
      } catch {
        if (sequence !== openConversationSequence.current) return;
        setConversationNotice(
          requestedOrigin === 'workspace'
            ? 'This chat is not available in PMS AI. Open it from its original assistant or select it under Older chats.'
            : 'Could not move this older chat into PMS AI. Refresh recent chats and try again.',
        );
        saveLastConversationId(null);
        const draftKey = createDraftKey();
        updateSession(draftKey, () => makeEmptyChatSession(draftKey, null));
        activeChatKeyRef.current = draftKey;
        setActiveChatKey(draftKey);
        setUrlConversationParam(null);
      } finally {
        if (sequence === openConversationSequence.current) setIsLoadingConversation(false);
      }
    },
    [refreshRecentConversations, saveLastConversationId, setUrlConversationParam, updateSession],
  );

  useEffect(() => {
    let mounted = true;
    const urlConv = searchParamsRef.current.get('conversation');
    void (async () => {
      const items = await refreshRecentConversations();
      if (!mounted || userInteractedRef.current) return;
      if (urlConv) {
        const matchedConv = items.find((c) => c.conversation_id === urlConv);
        await openConversation(urlConv, matchedConv?.origin === 'legacy' ? 'legacy' : 'workspace');
        return;
      }
      let savedId: string | null = null;
      try {
        savedId = sessionStorage.getItem(storageKey);
      } catch {
        savedId = null;
      }
      if (savedId && items.some((c) => c.conversation_id === savedId && c.origin === 'workspace')) {
        await openConversation(savedId);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [openConversation, refreshRecentConversations, storageKey]);

  const monthParam = searchParams.get('month') || (activeMonth !== 'All' ? activeMonth : null);
  const yearParam = searchParams.get('year') ? Number(searchParams.get('year')) : null;
  const functionParam = searchParams.get('function') || null;
  const positionParam = searchParams.get('position') || null;
  const regionParam = searchParams.get('region') || null;

  const prevScopeParamsRef = useRef({
    functionParam,
    positionParam,
    monthParam,
    yearParam,
  });

  useEffect(() => {
    const prev = prevScopeParamsRef.current;
    const fnChanged = prev.functionParam !== functionParam;
    const posChanged = prev.positionParam !== positionParam;
    const monthChanged = prev.monthParam !== monthParam;
    const yearChanged = prev.yearParam !== yearParam;
    if (!fnChanged && !posChanged && !monthChanged && !yearChanged) {
      return;
    }
    prevScopeParamsRef.current = {
      functionParam,
      positionParam,
      monthParam,
      yearParam,
    };
    cancelActiveChatInFlight();
    updateSession(activeChatKeyRef.current, (prev) => {
      const curr = prev.lastConfirmedQuery;
      if (!curr) return prev;
      return {
        ...prev,
        lastConfirmedQuery: {
          ...curr,
          ...(fnChanged
            ? {
                function: functionParam,
                team: null,
                position: null,
                metric_id: null,
                last_subject_employee_id: null,
                last_subject_employee_name: null,
              }
            : {}),
          ...(posChanged
            ? {
                position: positionParam,
                metric_id: null,
                last_subject_employee_id: null,
                last_subject_employee_name: null,
              }
            : {}),
          ...(monthChanged || yearChanged
            ? {
                periods: [],
                compare_period: null,
              }
            : {}),
        },
      };
    });
  }, [functionParam, positionParam, monthParam, yearParam, cancelActiveChatInFlight, updateSession]);

  const sessionState: SessionFilterContext = useMemo(
    () => ({
      function: functionParam,
      team: selectedTeam !== 'All' ? selectedTeam : null,
      position: positionParam,
      branch: selectedBranch !== 'all' ? selectedBranch : null,
      region: regionParam,
      performance_level: selectedLevel !== 'All' ? selectedLevel : null,
      month: monthParam,
      year: yearParam,
      last_confirmed_query: lastConfirmedQuery,
    }),
    [functionParam, selectedTeam, positionParam, selectedBranch, regionParam, selectedLevel, monthParam, yearParam, lastConfirmedQuery],
  );

  const handleFilterChange = (key: 'team' | 'branch' | 'performance_level' | 'function' | 'region' | 'position', value: string) => {
    cancelActiveChatInFlight();
    const next = new URLSearchParams(searchParams);
    if (value === 'All' || value === 'all' || !value) {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    if (key === 'function' || key === 'region') {
      next.delete('team');
      next.delete('position');
      setSelectedTeam('All');
    }
    if (key === 'region') {
      next.delete('branch');
      setSelectedBranch('all');
    }
    if (key === 'team' || key === 'performance_level') next.delete('position');
    setSearchParams(next, { replace: true });
    if (key === 'function' || key === 'region') {
      updateSession(activeChatKeyRef.current, (prev) => ({
        ...prev,
        lastConfirmedQuery: key === 'region' ? {} : null,
      }));
    }
    if (key === 'team') {
      setSelectedTeam(value);
      updateSession(activeChatKeyRef.current, (prev) => ({
        ...prev,
        lastConfirmedQuery: prev.lastConfirmedQuery
          ? {
              ...prev.lastConfirmedQuery,
              team: value !== 'All' ? value : null,
              position: null,
              metric_id: null,
              last_subject_employee_id: null,
              last_subject_employee_name: null,
            }
          : null,
      }));
    }
    if (key === 'branch') {
      setSelectedBranch(value);
      updateSession(activeChatKeyRef.current, (prev) => ({
        ...prev,
        lastConfirmedQuery: prev.lastConfirmedQuery
          ? {
              ...prev.lastConfirmedQuery,
              branch: value !== 'all' ? value : null,
              compare_branch: null,
            }
          : null,
      }));
    }
    if (key === 'performance_level') {
      setSelectedLevel(value);
      updateSession(activeChatKeyRef.current, (prev) => ({
        ...prev,
        lastConfirmedQuery: prev.lastConfirmedQuery
          ? {
              ...prev.lastConfirmedQuery,
              performance_level: value !== 'All' ? value : null,
              metric_id: null,
              last_subject_employee_id: null,
              last_subject_employee_name: null,
            }
          : null,
      }));
    }
  };

  const watchingQueryKey = [
    'pms-ai-watching',
    sessionState.function,
    sessionState.team,
    sessionState.position,
    sessionState.region,
    sessionState.branch,
    sessionState.performance_level,
    sessionState.month,
    sessionState.year,
  ];

  const { data: watchingData, isLoading: isWatchingLoading } = useQuery({
    queryKey: watchingQueryKey,
    queryFn: async () => {
      const qs = new URLSearchParams();
      if (sessionState.function) qs.set('function', sessionState.function);
      if (sessionState.team) qs.set('team', sessionState.team);
      if (sessionState.position) qs.set('position', sessionState.position);
      if (sessionState.region) qs.set('region', sessionState.region);
      if (sessionState.branch) qs.set('branch', sessionState.branch);
      if (sessionState.performance_level) qs.set('performance_level', sessionState.performance_level);
      if (sessionState.month) qs.set('month', sessionState.month);
      if (sessionState.year) qs.set('year', String(sessionState.year));
      const res = await apiFetch<{ success: boolean; data: AiWatchingPayload }>(
        `/api/ai/watching?${qs.toString()}`,
      );
      return res.data;
    },
    enabled: showWatchingPanel,
    staleTime: 60_000,
    retry: false,
  });

  const { data: catalogData } = useQuery({
    queryKey: ['pms-ai-catalog'],
    queryFn: async () => {
      const res = await apiFetch<{ success: boolean; data: CatalogOptions }>('/api/ai/catalog');
      return res?.data ?? null;
    },
    staleTime: 300_000,
    retry: false,
  });

  const availableFunctions = useMemo<string[]>(() => {
    const list = catalogData?.eligible_functions || catalogData?.functions || [];
    if (list && list.length > 0) {
      return list.map((fn) =>
        typeof fn === 'string' ? fn : fn.label || fn.name || fn.key || String(fn),
      );
    }
    if (watchingData?.eligible_functions && watchingData.eligible_functions.length > 0) {
      return watchingData.eligible_functions;
    }
    return [];
  }, [catalogData, watchingData]);

  const availableTeams = useMemo<Array<{ value: string; label: string; badge?: string }>>(() => {
    const list: CatalogChoice[] = catalogData?.eligible_teams ?? catalogData?.teams ?? watchingData?.eligible_teams ?? [];
    return list
      .filter((t) => typeof t === 'string' || !sessionState.region || !t.regions ||
        t.regions.includes(sessionState.region))
      .filter((t) => !sessionState.function || (typeof t !== 'string' && String(t.function || t.function_key || '').trim().toLowerCase() === sessionState.function.trim().toLowerCase()))
      .map((t) => ({
        value: typeof t === 'string' ? t : t.value || t.key || t.name || '',
        label: typeof t === 'string' ? t : t.label || t.name || t.value || '',
        badge: typeof t === 'object' ? t.badge || t.function || t.function_key : undefined,
      }));
  }, [catalogData, watchingData, sessionState.function, sessionState.region]);

  const availablePositions = useMemo(() => {
    if (!sessionState.team) return [];
    return [...new Set(
      (catalogData?.metrics ?? [])
        .filter((metric) =>
          metric.team === sessionState.team
          && (!sessionState.performance_level || metric.performance_level === sessionState.performance_level),
        )
        .flatMap((metric) => metric.position ? [metric.position] : []),
    )].sort();
  }, [catalogData, sessionState.team, sessionState.performance_level]);

  const availableBranches = useMemo<string[]>(() => {
    const list = catalogData?.eligible_branches || catalogData?.branches || [];
    if (list && list.length > 0) {
      return list.map((b) =>
        typeof b === 'string' ? b : b.value || b.key || b.label || String(b),
      );
    }
    if (watchingData?.eligible_branches && watchingData.eligible_branches.length > 0) {
      return watchingData.eligible_branches;
    }
    return [];
  }, [catalogData, watchingData]);

  const availableLevels = useMemo<string[]>(() => {
    const list = catalogData?.eligible_levels || catalogData?.performance_levels || [];
    if (list && list.length > 0) {
      return list.map((lvl) =>
        typeof lvl === 'string' ? lvl : lvl.value || lvl.key || lvl.label || String(lvl),
      );
    }
    if (watchingData?.eligible_levels && watchingData.eligible_levels.length > 0) {
      return watchingData.eligible_levels;
    }
    return [];
  }, [catalogData, watchingData]);

  useEffect(() => {
    if (turns.length > 0) {
      streamEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [turns]);

  const startNewChat = useCallback(() => {
    // Do not silently dismiss a pending delete confirmation dialog when New/New chat is triggered.
    if (confirmDeleteIdRef.current !== null) {
      return;
    }
    openConversationSequence.current += 1;
    setIsLoadingConversation(false);
    userInteractedRef.current = true;
    setConversationNotice(null);
    setDeleteError(null);
    const draftKey = createDraftKey();
    updateSession(draftKey, () => makeEmptyChatSession(draftKey, null));
    activeChatKeyRef.current = draftKey;
    setActiveChatKey(draftKey);
    setUrlConversationParam(null);
    saveLastConversationId(null);
    setPromptInput('');
  }, [saveLastConversationId, setUrlConversationParam, updateSession]);

  const handleDeleteConversation = useCallback(
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
        setRecentConversations((prev) =>
          prev.filter((c) => c.conversation_id !== targetConvId),
        );
        const existing = sessionsRef.current[targetConvId];
        if (existing?.abortController) {
          existing.abortController.abort();
        }
        const nextMap = { ...sessionsRef.current };
        delete nextMap[targetConvId];
        sessionsRef.current = nextMap;
        setSessionsByKey(nextMap);

        try {
          if (sessionStorage.getItem(storageKey) === targetConvId) {
            saveLastConversationId(null);
          }
        } catch {
          // Ignore storage errors
        }

        const activeSess = sessionsRef.current[activeChatKeyRef.current];
        if (
          activeChatKeyRef.current === targetConvId ||
          activeSess?.conversationId === targetConvId
        ) {
          const draftKey = createDraftKey();
          updateSession(draftKey, () => makeEmptyChatSession(draftKey, null));
          activeChatKeyRef.current = draftKey;
          setActiveChatKey(draftKey);
          setUrlConversationParam(null);
          saveLastConversationId(null);
        }
      } catch {
        setConfirmDeleteId(null);
        setDeleteError('Could not delete this conversation. Please try again.');
      } finally {
        setDeletingConvId(null);
      }
    },
    [saveLastConversationId, setUrlConversationParam, storageKey, updateSession],
  );

  const sendPrompt = useCallback(
    async (
      rawPrompt: string,
      clarificationChoiceId?: string,
      options?: {
        retryTurnId?: string;
        reuseClientRequestId?: string;
        conflictCode?: 404 | 409;
        variationSeed?: number;
      },
    ) => {
      const cleanPrompt = rawPrompt.trim();
      const originKey = activeChatKeyRef.current;
      const originSession = sessionsRef.current[originKey] ?? makeEmptyChatSession(originKey);
      if (!cleanPrompt || originSession.isSending) return;

      userInteractedRef.current = true;
      setConversationNotice(null);

      const reqSeq = originSession.requestSeq + 1;
      const controller = new AbortController();

      const isRetry = Boolean(options?.retryTurnId);
      const turnId = options?.retryTurnId || `turn-${Date.now()}-${reqSeq}`;

      let effectiveConversationId = originSession.conversationId || originKey;
      let effectiveContextVersion = originSession.contextVersion;
      const retrySettings = originSession.turns.find((turn) => turn.id === options?.retryTurnId)?.retrySettings;
      const effectiveAnswerDetail = retrySettings ? (retrySettings.answer_detail ?? 'auto') : answerDetail;
      let effectiveSessionState: SessionFilterContext = {
        ...(retrySettings?.session_state ?? sessionState),
        last_confirmed_query: originSession.lastConfirmedQuery,
      };
      const clientRequestId =
        options?.reuseClientRequestId && !options?.conflictCode
          ? options.reuseClientRequestId
          : globalThis.crypto.randomUUID();

      if (options?.conflictCode === 404) {
        effectiveConversationId = createDraftKey();
        effectiveSessionState = { ...sessionState, last_confirmed_query: null };
        effectiveContextVersion = 0;
        updateSession(originKey, (prev) => ({
          ...prev,
          conversationId: null,
          contextVersion: 0,
          lastConfirmedQuery: null,
        }));
      } else if (options?.conflictCode === 409) {
        updateSession(originKey, (prev) => ({
          ...prev,
          requestSeq: reqSeq,
          abortController: controller,
          isSending: true,
        }));
        effectiveContextVersion = 0;
        if (effectiveConversationId) {
          try {
            const ctxRes = await apiFetch<{
              success: boolean;
              data?: { context_version?: number; confirmed_context?: ConfirmedQueryContext };
            }>(`/api/ai/conversations/${effectiveConversationId}/context?origin=workspace`, {
              signal: controller.signal,
            });
            if (controller.signal.aborted) return;
            if (typeof ctxRes?.data?.context_version === 'number') {
              effectiveContextVersion = ctxRes.data.context_version;
              updateSession(originKey, (prev) => ({
                ...prev,
                contextVersion: ctxRes.data!.context_version!,
              }));
            }
            if (ctxRes?.data && 'confirmed_context' in ctxRes.data) {
              const refreshedConfirmed = ctxRes.data.confirmed_context ?? null;
              updateSession(originKey, (prev) => ({
                ...prev,
                lastConfirmedQuery: refreshedConfirmed,
              }));
              effectiveSessionState = { ...effectiveSessionState, last_confirmed_query: refreshedConfirmed };
            }
          } catch {
            if (controller.signal.aborted) return;
            effectiveContextVersion = 0;
          }
        }
      }

      const historySource = isRetry
        ? originSession.turns.filter((t) => t.id !== turnId).slice(-4)
        : originSession.turns.slice(-4);
      const historyPayload: AiChatMessage[] = [];
      for (const t of historySource) {
        historyPayload.push({ role: 'user', content: t.userPrompt });
        if (t.response?.headline) {
          historyPayload.push({ role: 'assistant', content: t.response.headline });
        }
      }

      updateSession(originKey, (prev) => {
        const savedRetrySettings = {
          session_state: { ...effectiveSessionState, last_confirmed_query: null },
          answer_detail: effectiveAnswerDetail,
          clarification_choice_id: clarificationChoiceId,
          variation_seed: options?.variationSeed,
        };
        const nextTurns = isRetry
          ? prev.turns.map((item) =>
              item.id === turnId
                ? {
                    ...item,
                    clientRequestId,
                    retrySettings: savedRetrySettings,
                    variationSeed: options?.variationSeed ?? item.variationSeed,
                    error: undefined,
                    conflictCode: undefined,
                    isPending: true,
                  }
                : item,
            )
          : [
              ...prev.turns,
              {
                id: turnId,
                userPrompt: cleanPrompt,
                clientRequestId,
                retrySettings: savedRetrySettings,
                clarificationChoiceId,
                variationSeed: options?.variationSeed,
                isPending: true,
              },
            ];
        return {
          ...prev,
          requestSeq: reqSeq,
          conversationId: effectiveConversationId,
          abortController: controller,
          isSending: true,
          turns: nextTurns,
        };
      });
      setPromptInput('');

      try {
        const res = await apiFetch<{ success: boolean; data: AiChatResponsePayload }>(
          '/api/ai/chat',
          {
            method: 'POST',
            signal: controller.signal,
            body: JSON.stringify({
              prompt: cleanPrompt,
              origin: 'workspace',
              conversation_id: effectiveConversationId,
              context_version: effectiveContextVersion,
              client_request_id: clientRequestId,
              clarification_choice_id: clarificationChoiceId || null,
              session_state: effectiveSessionState,
              history: historyPayload,
              provider_override: 'auto',
              answer_detail: effectiveAnswerDetail,
              ...(typeof options?.variationSeed === 'number' && options.variationSeed > 0
                ? { variation_seed: options.variationSeed }
                : {}),
            }),
          },
        );
        const latestOrigin = sessionsRef.current[originKey];
        if (!latestOrigin || latestOrigin.requestSeq !== reqSeq || controller.signal.aborted) {
          return;
        }

        const serverConvId = res.data.conversation_id || latestOrigin.conversationId;
        const targetKey = serverConvId || originKey;

        const nextConfirmedFromServer = res.data.resolved_session_state?.last_confirmed_query;
        let computedConfirmed = latestOrigin.lastConfirmedQuery;
        if (nextConfirmedFromServer) {
          computedConfirmed =
            res.data.outcome === 'clarification' && latestOrigin.lastConfirmedQuery
              ? {
                  ...latestOrigin.lastConfirmedQuery,
                  ...Object.fromEntries(
                    Object.entries(nextConfirmedFromServer).filter(
                      ([, v]) => v !== null && v !== undefined,
                    ),
                  ),
                }
              : nextConfirmedFromServer;
        }

        const completedSession: ChatSessionState = {
          ...latestOrigin,
          chatKey: targetKey,
          conversationId: serverConvId || null,
          contextVersion:
            typeof res.data.context_version === 'number'
              ? res.data.context_version
              : latestOrigin.contextVersion,
          lastConfirmedQuery: computedConfirmed,
          isSending: false,
          abortController: null,
          turns: latestOrigin.turns.map((item) =>
            item.id === turnId
              ? {
                  ...item,
                  response: res.data,
                  error: undefined,
                  conflictCode: undefined,
                  isPending: false,
                }
              : item,
          ),
        };

        const nextMap = { ...sessionsRef.current };
        if (targetKey !== originKey) {
          delete nextMap[originKey];
        }
        nextMap[targetKey] = completedSession;
        sessionsRef.current = nextMap;
        setSessionsByKey(nextMap);

        if (activeChatKeyRef.current === originKey) {
          if (targetKey !== originKey) {
            activeChatKeyRef.current = targetKey;
            setActiveChatKey(targetKey);
          }
          if (serverConvId) {
            setUrlConversationParam(serverConvId);
            saveLastConversationId(serverConvId);
          }
        }
        if (serverConvId) {
          void refreshRecentConversations();
        }
      } catch (err) {
        const latestOrigin = sessionsRef.current[originKey];
        if (!latestOrigin || latestOrigin.requestSeq !== reqSeq || controller.signal.aborted) {
          return;
        }
        const msg = err instanceof Error ? err.message : 'Unable to reach PMS AI service';
        const conflictCode: 404 | 409 | undefined =
          msg.includes('404') || /deleted|no longer available/i.test(msg)
            ? 404
            : /stale context/i.test(msg)
            ? 409
            : undefined;
        updateSession(originKey, (prev) => ({
          ...prev,
          isSending: false,
          abortController: null,
          turns: prev.turns.map((item) =>
            item.id === turnId
              ? { ...item, error: msg, conflictCode, isPending: false }
              : item,
          ),
        }));
        void refreshRecentConversations();
      }
    },
    [
      answerDetail,
      refreshRecentConversations,
      saveLastConversationId,
      sessionState,
      setUrlConversationParam,
      updateSession,
    ],
  );

  const firstName = useMemo(() => {
    const full = currentUser?.name || currentUser?.username || 'Mustafa';
    return full.split(' ')[0];
  }, [currentUser]);

  const userInitials = useMemo(() => {
    const full = currentUser?.name || currentUser?.username || 'MU';
    const parts = full.trim().split(/\s+/);
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    }
    return full.slice(0, 2).toUpperCase();
  }, [currentUser]);

  const serverStarterPrompts = watchingData?.starter_prompts;
  const fallbackStarterPrompts = useMemo(
    () =>
      buildFallbackStarterPrompts({
        functionName: sessionState.function,
        team: sessionState.team,
        branch: sessionState.branch,
        region: sessionState.region || watchingData?.resolved_session_state?.region || null,
      }),
    [
      sessionState.function,
      sessionState.team,
      sessionState.branch,
      sessionState.region,
      watchingData?.resolved_session_state?.region,
    ],
  );
  const starterPrompts: AiStarterPrompt[] = useMemo(() => {
    if (serverStarterPrompts && serverStarterPrompts.length > 0) {
      return mergeStarterScenarios(serverStarterPrompts, fallbackStarterPrompts);
    }
    return fallbackStarterPrompts;
  }, [serverStarterPrompts, fallbackStarterPrompts]);

  const homeStarters: AiStarterPrompt[] = useMemo(() => {
    const region = (
      sessionState.region ||
      watchingData?.resolved_session_state?.region ||
      ''
    ).toUpperCase();
    if (region === 'EGY') {
      const egySpecific = starterPrompts.find(
        (p) => p.label === 'Compare EGY teams & KPIs' || p.prompt === 'Compare EGY teams & KPIs',
      );
      const rest = starterPrompts.filter((p) => p !== egySpecific);
      return (egySpecific ? [egySpecific, ...rest] : rest).slice(0, 3);
    }
    return starterPrompts.slice(0, 3);
  }, [starterPrompts, sessionState.region, watchingData?.resolved_session_state?.region]);

  const activeScopeSummary = useMemo(() => {
    const parts: string[] = [];
    if (regionParam && regionParam !== 'All') {
      parts.push(regionParam === 'EGY' ? 'Egypt' : regionParam);
    }
    if (selectedTeam && selectedTeam !== 'All') {
      parts.push(selectedTeam);
    } else if (sessionState.function) {
      parts.push(sessionState.function);
    } else {
      parts.push('All Departments');
    }
    if (selectedBranch && selectedBranch !== 'all') {
      parts.push(selectedBranch.charAt(0).toUpperCase() + selectedBranch.slice(1));
    }
    if (selectedLevel && selectedLevel !== 'All') {
      parts.push(selectedLevel);
    }
    return parts.join(' · ');
  }, [regionParam, selectedTeam, sessionState.function, selectedBranch, selectedLevel]);

  const activeFilterChips = useMemo(() => {
    const chips: Array<{
      key: 'region' | 'function' | 'team' | 'position' | 'branch' | 'performance_level';
      label: string;
      resetValue: string;
    }> = [];
    if (regionParam && regionParam !== 'All') {
      chips.push({
        key: 'region',
        label: regionParam === 'EGY' ? 'Egypt' : regionParam,
        resetValue: 'All',
      });
    }
    if (sessionState.function) {
      chips.push({ key: 'function', label: sessionState.function, resetValue: 'All' });
    }
    if (selectedTeam && selectedTeam !== 'All') {
      chips.push({ key: 'team', label: selectedTeam, resetValue: 'All' });
    }
    if (positionParam && positionParam !== 'All') {
      chips.push({ key: 'position', label: positionParam, resetValue: 'All' });
    }
    if (selectedBranch && selectedBranch !== 'all') {
      chips.push({
        key: 'branch',
        label: selectedBranch.charAt(0).toUpperCase() + selectedBranch.slice(1),
        resetValue: 'all',
      });
    }
    if (selectedLevel && selectedLevel !== 'All') {
      chips.push({ key: 'performance_level', label: selectedLevel, resetValue: 'All' });
    }
    return chips;
  }, [
    regionParam,
    sessionState.function,
    selectedTeam,
    positionParam,
    selectedBranch,
    selectedLevel,
  ]);

  const sendingByConvId = useMemo<Record<string, boolean>>(() => {
    const out: Record<string, boolean> = {};
    for (const [key, sess] of Object.entries(sessionsByKey)) {
      if (sess.isSending) {
        out[sess.conversationId || key] = true;
      }
    }
    return out;
  }, [sessionsByKey]);

  const guardrailHighlights = useMemo(
    () =>
      watchingData?.guardrails?.length
        ? watchingData.guardrails
        : [
            {
              label: 'Authorized scope only',
              description: 'Every metric and agent record stays strictly inside your active RBAC scope.',
            },
            {
              label: 'Verified PMS evidence',
              description: 'Figures come from saved PMS records.',
            },
            {
              label: 'Read-only analytical copilot',
              description: 'PMS AI reads scores, targets, and employee records.',
            },
          ],
    [watchingData],
  );

  const resolvedMonthLabel =
    watchingData?.resolved_session_state?.month || sessionState.month || 'Latest';
  const resolvedYearLabel =
    watchingData?.resolved_session_state?.month || sessionState.month
      ? watchingData?.resolved_session_state?.year || sessionState.year || ''
      : 'Period';
  const fullPeriodLabel = resolvedYearLabel
    ? `${resolvedMonthLabel} ${resolvedYearLabel}`
    : resolvedMonthLabel;
  const watchingAlertCount = watchingData?.alerts?.length ?? 0;

  return (
    <div className="min-h-full bg-gradient-to-br from-[#EDF4FC] via-[#F5F9FD] to-[#EBF3FA] px-3 py-3 sm:px-5">
      <div className="mx-auto max-w-[1440px]">
        <div className="flex min-h-0 flex-col gap-4 lg:flex-row lg:items-stretch">
          {/* Left Rail (desktop lg:+) / Slide-over Drawer (< lg): Recent chats */}
          <ConversationHistoryPanel
            isOpen={showHistoryPanel}
            conversations={recentConversations}
            activeConversationId={conversationId}
            sendingByConvId={sendingByConvId}
            isLoading={isLoadingHistory}
            errorMessage={historyError}
            deleteError={deleteError}
            confirmDeleteId={confirmDeleteId}
            deletingConvId={deletingConvId}
            onClose={() => setShowHistoryPanel(false)}
            onNewChat={() => {
              if (confirmDeleteIdRef.current !== null) return;
              startNewChat();
              const isDesktop =
                typeof window !== 'undefined' &&
                typeof window.matchMedia === 'function' &&
                window.matchMedia('(min-width: 1024px)').matches;
              if (!isDesktop) setShowHistoryPanel(false);
            }}
            onSelectConversation={(convId, origin) => {
              if (confirmDeleteIdRef.current !== null) return;
              void openConversation(convId, origin ?? 'workspace');
              const isDesktop =
                typeof window !== 'undefined' &&
                typeof window.matchMedia === 'function' &&
                window.matchMedia('(min-width: 1024px)').matches;
              if (!isDesktop) setShowHistoryPanel(false);
            }}
            onRequestDelete={(convId) => {
              setDeleteError(null);
              setConfirmDeleteId(convId);
            }}
            onConfirmDelete={(convId) => void handleDeleteConversation(convId)}
            onCancelDelete={() => setConfirmDeleteId(null)}
            onDismissDeleteError={() => setDeleteError(null)}
            onRetryLoad={() => void refreshRecentConversations()}
          />

          {/* Center Conversation-First Workspace */}
          <section
            aria-label="PMS AI analytical conversation workspace"
            className="relative flex h-[calc(100dvh-108px)] min-h-[520px] min-w-0 flex-1 flex-col justify-between overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-[0_10px_35px_rgb(15,23,42,0.06)]"
          >
            {/* Seamless Top Radial Aurora Glow */}
            <div
              className="pointer-events-none absolute inset-x-0 top-0 h-56 bg-[radial-gradient(ellipse_75%_65%_at_50%_0%,rgba(56,189,248,0.16),rgba(16,185,129,0.06)_55%,transparent_100%)]"
              aria-hidden="true"
            />

            {/* Clean 3-Zone Top Header Bar */}
            <div className="relative z-30 border-b border-slate-100/90 bg-white/95 px-4 py-2.5 backdrop-blur-md sm:px-6">
              <div className="flex flex-wrap items-center justify-between gap-2.5">
                <div className="flex min-w-0 items-center gap-2.5">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 text-white shadow-xs">
                    <Sparkles size={16} />
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h1 className="text-base font-extrabold tracking-tight text-slate-900">
                      PMS AI
                    </h1>
                    <span className="inline-flex items-center gap-1 rounded-full border border-slate-200/90 bg-slate-50 px-2.5 py-0.5 text-xs font-semibold text-slate-700">
                      <Calendar size={12} className="text-blue-600" />
                      {fullPeriodLabel}
                    </span>
                    {conversationId === null ? (
                      <span data-testid="ai-session-draft-badge" className="sr-only">
                        New draft · fresh context
                      </span>
                    ) : (
                      <span data-testid="ai-session-active-badge" className="sr-only">
                        Active chat
                      </span>
                    )}
                  </div>
                </div>

                {/* Unified Scope Popover Trigger + Active Filter Chips + Actions */}
                <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                  {isSelfOnly ? (
                    <span data-testid="ai-self-only-pill" className="inline-flex cursor-default items-center gap-1.5 rounded-xl border border-blue-200 bg-blue-50/80 px-3 py-1.5 text-xs font-semibold text-blue-800">
                      <Lock size={13} className="text-blue-600" />
                      My 360°
                    </span>
                  ) : (
                  <button
                    type="button"
                    aria-expanded={showFilters}
                    aria-label={showFilters ? 'Hide scope filters' : 'Show scope filters'}
                    onClick={() => setShowFilters((prev) => !prev)}
                    className={`inline-flex cursor-pointer items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition-colors ${
                      showFilters || activeFilterChips.length > 0
                        ? 'border-blue-200 bg-blue-50/80 text-blue-800'
                        : 'border-slate-200/90 bg-white text-slate-700 hover:border-blue-300 hover:text-blue-700'
                    }`}
                  >
                    <SlidersHorizontal size={13} className="text-blue-600" />
                    <span className="max-w-[200px] truncate">Scope: {activeScopeSummary}</span>
                    <ChevronDown
                      size={13}
                      className={`transition-transform ${showFilters ? 'rotate-180' : ''}`}
                    />
                  </button>
                  )}

                  {!isSelfOnly && activeFilterChips.map((chip) => (
                    <button
                      key={`${chip.key}-${chip.label}`}
                      type="button"
                      title={`Remove ${chip.label} filter`}
                      onClick={() => handleFilterChange(chip.key, chip.resetValue)}
                      className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-blue-200/80 bg-blue-50/50 px-2 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-100/70"
                    >
                      <span>{chip.label}</span>
                      <X size={11} />
                    </button>
                  ))}

                  <button
                    type="button"
                    data-testid="ai-history-toggle"
                    aria-expanded={showHistoryPanel}
                    aria-label={showHistoryPanel ? 'Hide recent chats' : 'Show recent chats'}
                    onClick={() => setShowHistoryPanel((prev) => !prev)}
                    className={`inline-flex cursor-pointer items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition-colors ${
                      showHistoryPanel
                        ? 'border-blue-200 bg-blue-50 text-blue-700'
                        : 'border-slate-200/90 bg-white text-slate-600 hover:border-blue-300 hover:text-blue-700'
                    }`}
                  >
                    <History size={13} />
                    <span>Recent chats</span>
                    {recentConversations.length > 0 && (
                      <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-xs font-bold tabular-nums text-slate-700">
                        {recentConversations.length}
                      </span>
                    )}
                  </button>

                  <button
                    type="button"
                    aria-expanded={showWatchingPanel}
                    aria-label={
                      showWatchingPanel
                        ? 'Hide AI is watching panel'
                        : 'Show AI is watching panel'
                    }
                    onClick={() => setShowWatchingPanel((prev) => !prev)}
                    className={`inline-flex cursor-pointer items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition-colors ${
                      showWatchingPanel
                        ? 'border-amber-200 bg-amber-50 text-amber-800'
                        : 'border-slate-200/90 bg-white text-slate-600 hover:border-blue-300 hover:text-blue-700'
                    }`}
                  >
                    <Bell size={13} className={watchingAlertCount > 0 ? 'text-amber-600' : ''} />
                    <span>Needs Attention</span>
                    {watchingAlertCount > 0 && (
                      <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-xs font-bold tabular-nums text-amber-800">
                        {watchingAlertCount}
                      </span>
                    )}
                  </button>

                  <button
                    type="button"
                    aria-expanded={showGuardrailsInfo}
                    aria-label="How PMS AI protects data"
                    onClick={() => setShowGuardrailsInfo((prev) => !prev)}
                    className={`inline-flex cursor-pointer items-center gap-1 rounded-xl border px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                      showGuardrailsInfo
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                        : 'border-slate-200/90 bg-white text-slate-500 hover:border-emerald-300 hover:text-emerald-700'
                    }`}
                  >
                    <Info size={13} />
                    <span className="hidden sm:inline">Privacy</span>
                  </button>

                  {(turns.length > 0 || conversationId !== null) && (
                    <button
                      type="button"
                      data-testid="ai-new-chat-btn"
                      onClick={startNewChat}
                      className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-slate-800"
                    >
                      <RotateCcw size={12} />
                      <span>New chat</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Collapsible Scope Filter Tray — hidden for self-only users */}
              {!isSelfOnly && (
              <ScopeFilterBar
                availableRegions={catalogData?.eligible_regions ?? []}
                selectedRegion={regionParam}
                availablePositions={availablePositions}
                selectedPosition={positionParam}
                availableFunctions={availableFunctions}
                selectedFunction={sessionState.function}
                availableTeams={availableTeams}
                selectedTeam={selectedTeam}
                availableBranches={availableBranches}
                selectedBranch={selectedBranch}
                availableLevels={availableLevels}
                selectedLevel={selectedLevel}
                answerDetail={answerDetail}
                onFilterChange={handleFilterChange}
                onChangeAnswerDetail={(mode) => setAnswerDetail(mode)}
                className={
                  showFilters
                    ? 'mt-2.5 flex w-full rounded-2xl border border-slate-200/80 bg-slate-50/80 p-2.5'
                    : 'hidden'
                }
              />
              )}

              {/* First-person pronoun auto-binding hint for self-only users */}
              {isSelfOnly && turns.length === 0 && (
                <p className="mt-2 text-center text-xs text-slate-500">
                  Ask about your own numbers — e.g. “How am I doing this month?”
                </p>
              )}
              {showGuardrailsInfo && (
                <>
                  <button
                    type="button"
                    aria-label="Dismiss data protection info"
                    onClick={() => setShowGuardrailsInfo(false)}
                    className="fixed inset-0 z-30 cursor-default bg-transparent"
                  />
                  <div
                    role="dialog"
                    aria-label="How PMS AI protects data"
                    className="absolute right-4 top-full z-40 mt-2 w-80 max-w-[calc(100%-2rem)] rounded-2xl border border-slate-200 bg-white p-4 shadow-xl"
                  >
                    <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                      <div className="flex items-center gap-2">
                        <ShieldCheck size={15} className="text-emerald-600" />
                        <h2 className="text-xs font-extrabold text-slate-900">
                          How PMS AI protects data
                        </h2>
                      </div>
                      <button
                        type="button"
                        aria-label="Close data protection info"
                        onClick={() => setShowGuardrailsInfo(false)}
                        className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                      >
                        <X size={13} />
                      </button>
                    </div>
                    <ul className="mt-2.5 space-y-2">
                      {guardrailHighlights.map((g) => (
                        <li key={g.label} className="text-xs leading-relaxed text-slate-600">
                          <span className="font-bold text-slate-900">{g.label}:</span>{' '}
                          <span>{g.description}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </>
              )}
            </div>

            {/* Center Body */}
            <div className="relative z-10 min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6">
              {conversationNotice && (
                <div
                  role="status"
                  className="mb-3 flex items-center justify-between gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-3.5 py-2 text-xs font-semibold text-amber-800"
                >
                  <span>{conversationNotice}</span>
                  <button
                    type="button"
                    aria-label="Dismiss conversation notice"
                    onClick={() => setConversationNotice(null)}
                    className="rounded p-0.5 text-amber-700 hover:bg-amber-100"
                  >
                    <X size={13} />
                  </button>
                </div>
              )}
              {isLoadingConversation ? (
                <div className="mx-auto max-w-3xl space-y-3 py-6" aria-label="Loading conversation">
                  <div className="h-10 w-2/3 animate-pulse rounded-2xl bg-slate-100" />
                  <div className="h-28 w-full animate-pulse rounded-2xl bg-slate-100" />
                </div>
              ) : turns.length === 0 ? (
                isSelfOnly ? (
                  <div className="mx-auto max-w-3xl py-4">
                    <Agent360Scorecard onAskAboutKpi={(kpi) => void sendPrompt(`Tell me about my ${kpi}`)} />
                  </div>
                ) : (
                  <AiMorningBriefingHome
                    firstName={firstName}
                    periodLabel={fullPeriodLabel}
                    scopeSummaryLabel={activeScopeSummary}
                    summaryScore={watchingData?.summary_score}
                    summaryScoreChange={watchingData?.summary_score_change}
                    measuredRecords={watchingData?.measured_records}
                    alerts={showWatchingPanel ? [] : (watchingData?.alerts ?? [])}
                    starterCards={homeStarters}
                    onSelectPrompt={(prompt) => void sendPrompt(prompt)}
                  />
                )
              ) : (
                <div className="mx-auto max-w-4xl space-y-5">
                  {turns.map((turn) => (
                    <div key={turn.id} className="space-y-3.5">
                      {/* Right-aligned User Prompt Bubble */}
                      <div className="flex items-center justify-end gap-2.5">
                        <div
                          dir="auto"
                          className="max-w-xl rounded-2xl rounded-br-xs bg-blue-600 px-4 py-2.5 text-sm font-medium leading-relaxed text-white shadow-xs"
                        >
                          {turn.userPrompt}
                        </div>
                        <div
                          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-800 text-xs font-bold text-white"
                          aria-hidden="true"
                        >
                          {userInitials}
                        </div>
                      </div>

                      {/* Left-aligned Live Step-by-Step Progress Card */}
                      {turn.isPending && (
                        <AiThinkingProgressCard
                          onStop={() => {
                            activeSession.abortController?.abort();
                            updateSession(activeChatKey, (prev) => ({
                              ...prev,
                              isSending: false,
                              abortController: null,
                              turns: prev.turns.filter((t) => t.id !== turn.id),
                            }));
                          }}
                        />
                      )}

                      {turn.error && (
                        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm font-medium text-rose-900">
                          <div>
                            <p className="font-bold">Unable to complete analysis</p>
                            <p className="mt-1 text-xs text-rose-800">{turn.error}</p>
                          </div>
                          <button
                            type="button"
                            onClick={() =>
                              void sendPrompt(turn.userPrompt, turn.clarificationChoiceId, {
                                retryTurnId: turn.id,
                                reuseClientRequestId: turn.clientRequestId,
                                conflictCode: turn.conflictCode,
                                variationSeed: turn.variationSeed,
                              })
                            }
                            className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-rose-300 bg-white px-3.5 py-1.5 text-xs font-bold text-rose-700 transition-colors hover:bg-rose-100"
                          >
                            <RotateCcw size={13} />
                            <span>Retry</span>
                          </button>
                        </div>
                      )}

                      {turn.response && (
                        <AiResponseCard
                          response={turn.response}
                          variationSeed={turn.variationSeed ?? 0}
                          isSending={isSending}
                          onSelectPrompt={(p, choiceId) => void sendPrompt(p, choiceId)}
                          onRegenerateAngle={(nextSeed) =>
                            void sendPrompt(turn.userPrompt, turn.clarificationChoiceId, {
                              variationSeed: nextSeed,
                            })
                          }
                        />
                      )}
                    </div>
                  ))}
                  <div ref={streamEndRef} />
                </div>
              )}
            </div>

            {/* Clean Multi-line Composer Dock + On-Demand Guided Prompts */}
            <AiComposerDock
              promptInput={promptInput}
              onChangePromptInput={setPromptInput}
              onSubmitPrompt={(prompt) => void sendPrompt(prompt)}
              isSending={isSending}
              hasTurns={turns.length > 0}
              showPromptLibrary={showMidChatScenarios}
              onTogglePromptLibrary={() => setShowMidChatScenarios((prev) => !prev)}
              starterPrompts={starterPrompts}
            />
          </section>

          {/* Compact Right Rail: AI is watching + Guardrails */}
          {showWatchingPanel && (
            <div className="w-full shrink-0 lg:w-[300px] xl:w-[310px]">
              <AiWatchingRail
                alerts={watchingData?.alerts || []}
                guardrails={watchingData?.guardrails || []}
                isLoading={isWatchingLoading}
                onSelectAlert={(prompt) => void sendPrompt(prompt)}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
