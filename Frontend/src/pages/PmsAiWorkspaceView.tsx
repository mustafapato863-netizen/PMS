import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  BarChart3,
  Building2,
  Calendar,
  ChevronDown,
  ChevronUp,
  Compass,
  GitBranch,
  Info,
  Layers,
  LayoutGrid,
  PieChart,
  RotateCcw,
  Send,
  ShieldCheck,
  Sparkles,
  Target,
  Users,
} from 'lucide-react';
import { useAuth } from '../context/auth';
import { useAppStore } from '../store/appStore';
import { apiFetch } from '../lib/apiClient';
import AiResponseCard from '../components/ai/AiResponseCard';
import AiScopeDropdown from '../components/ai/AiScopeDropdown';
import AiWatchingRail from '../components/ai/AiWatchingRail';
import type {
  AiChatMessage,
  AiChatResponsePayload,
  AiStarterPrompt,
  AiWatchingPayload,
  ConfirmedQueryContext,
  SessionFilterContext,
} from '../features/ai/types';

interface ConversationTurn {
  id: string;
  userPrompt: string;
  response?: AiChatResponsePayload;
  error?: string;
  isPending?: boolean;
}

const STARTER_ICON_MAP = {
  alert: <Users size={16} />,
  users: <Users size={16} />,
  chart: <BarChart3 size={16} />,
  shield: <ShieldCheck size={16} />,
};

const CATEGORY_STYLES: Record<
  string,
  {
    badge: string;
    iconBox: string;
    cardHover: string;
  }
> = {
  team: {
    badge: 'bg-sky-100/90 text-sky-700',
    iconBox: 'border border-sky-100 bg-sky-50 text-sky-600',
    cardHover: 'hover:border-sky-300 hover:shadow-md',
  },
  people: {
    badge: 'bg-emerald-100/90 text-emerald-700',
    iconBox: 'border border-emerald-100 bg-emerald-50 text-emerald-600',
    cardHover: 'hover:border-emerald-300 hover:shadow-md',
  },
  branch: {
    badge: 'bg-sky-100/90 text-sky-700',
    iconBox: 'border border-sky-100 bg-sky-50 text-sky-600',
    cardHover: 'hover:border-sky-300 hover:shadow-md',
  },
  kpi: {
    badge: 'bg-blue-100/90 text-blue-700',
    iconBox: 'border border-blue-100 bg-blue-50 text-blue-600',
    cardHover: 'hover:border-blue-300 hover:shadow-md',
  },
  governance: {
    badge: 'bg-emerald-100/90 text-emerald-700',
    iconBox: 'border border-emerald-100 bg-emerald-50 text-emerald-600',
    cardHover: 'hover:border-emerald-300 hover:shadow-md',
  },
};

export default function PmsAiWorkspaceView() {
  const { currentUser } = useAuth();
  const activeMonth = useAppStore((s) => s.activeMonth);
  const [searchParams, setSearchParams] = useSearchParams();

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
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [lastConfirmedQuery, setLastConfirmedQuery] = useState<ConfirmedQueryContext | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [showScenarioTray, setShowScenarioTray] = useState<boolean>(true);
  const streamEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setAnswerDetail('auto');
    setTurns([]);
    setLastConfirmedQuery(null);
  }, [currentUser?.id]);

  const monthParam = searchParams.get('month') || (activeMonth !== 'All' ? activeMonth : null);
  const yearParam = searchParams.get('year') ? Number(searchParams.get('year')) : null;
  const functionParam = searchParams.get('function') || 'Call Center';
  const positionParam = searchParams.get('position') || null;

  const sessionState: SessionFilterContext = useMemo(
    () => ({
      function: functionParam,
      team: selectedTeam !== 'All' ? selectedTeam : null,
      position: positionParam,
      branch: selectedBranch !== 'all' ? selectedBranch : null,
      performance_level: selectedLevel !== 'All' ? selectedLevel : null,
      month: monthParam,
      year: yearParam,
      last_confirmed_query: lastConfirmedQuery,
    }),
    [functionParam, selectedTeam, positionParam, selectedBranch, selectedLevel, monthParam, yearParam, lastConfirmedQuery],
  );

  const handleFilterChange = (key: 'team' | 'branch' | 'performance_level', value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value === 'All' || value === 'all' || !value) {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    setSearchParams(next, { replace: true });
    if (key === 'team') {
      setSelectedTeam(value);
      setLastConfirmedQuery((prev) =>
        prev ? { ...prev, team: value !== 'All' ? value : null, position: null, metric_id: null } : null,
      );
    }
    if (key === 'branch') {
      setSelectedBranch(value);
      setLastConfirmedQuery((prev) =>
        prev ? { ...prev, branch: value !== 'all' ? value : null, compare_branch: null } : null,
      );
    }
    if (key === 'performance_level') {
      setSelectedLevel(value);
      setLastConfirmedQuery((prev) =>
        prev ? { ...prev, performance_level: value !== 'All' ? value : null, metric_id: null } : null,
      );
    }
  };

  const watchingQueryKey = [
    'pms-ai-watching',
    sessionState.function,
    sessionState.team,
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
      if (sessionState.branch) qs.set('branch', sessionState.branch);
      if (sessionState.performance_level) qs.set('performance_level', sessionState.performance_level);
      if (sessionState.month) qs.set('month', sessionState.month);
      if (sessionState.year) qs.set('year', String(sessionState.year));
      const res = await apiFetch<{ success: boolean; data: AiWatchingPayload }>(
        `/api/ai/watching?${qs.toString()}`,
      );
      return res.data;
    },
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => {
    if (turns.length > 0) {
      streamEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [turns]);

  const sendPrompt = useCallback(
    async (rawPrompt: string) => {
      const cleanPrompt = rawPrompt.trim();
      if (!cleanPrompt || isSending) return;

      const turnId = `turn-${Date.now()}`;
      const historyPayload: AiChatMessage[] = [];
      for (const t of turns.slice(-4)) {
        historyPayload.push({ role: 'user', content: t.userPrompt });
        if (t.response?.headline) {
          historyPayload.push({ role: 'assistant', content: t.response.headline });
        }
      }

      setTurns((prev) => [
        ...prev,
        { id: turnId, userPrompt: cleanPrompt, isPending: true },
      ]);
      setPromptInput('');
      setIsSending(true);

      try {
        const res = await apiFetch<{ success: boolean; data: AiChatResponsePayload }>(
          '/api/ai/chat',
          {
            method: 'POST',
            body: JSON.stringify({
              prompt: cleanPrompt,
              session_state: sessionState,
              history: historyPayload,
              provider_override: 'auto',
              answer_detail: answerDetail,
            }),
          },
        );
        if (res.data.resolved_session_state?.last_confirmed_query) {
          const nextConfirmed = res.data.resolved_session_state.last_confirmed_query;
          setLastConfirmedQuery((prev) =>
            res.data.outcome === 'clarification' && prev
              ? {
                  ...prev,
                  ...Object.fromEntries(
                    Object.entries(nextConfirmed).filter(([, v]) => v !== null && v !== undefined),
                  ),
                }
              : nextConfirmed,
          );
        }
        setTurns((prev) =>
          prev.map((item) =>
            item.id === turnId
              ? { ...item, response: res.data, isPending: false }
              : item,
          ),
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Unable to reach PMS AI service';
        setTurns((prev) =>
          prev.map((item) =>
            item.id === turnId
              ? { ...item, error: msg, isPending: false }
              : item,
          ),
        );
      } finally {
        setIsSending(false);
      }
    },
    [answerDetail, isSending, sessionState, turns],
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

  const starterPrompts: AiStarterPrompt[] = useMemo(() => {
    if (watchingData?.starter_prompts && watchingData.starter_prompts.length > 0) {
      return watchingData.starter_prompts;
    }
    return [
      {
        id: 'team-drop',
        label: 'Which Call Center team dropped most?',
        subtitle:
          'Identify the team with the largest performance drop and key KPI drivers.',
        badge: 'TEAM',
        prompt:
          'Which Call Center team dropped the most this month, what is the main KPI driver, and what decisions do you recommend?',
        category: 'team',
        icon_key: 'users',
      },
      {
        id: 'people-root-cause',
        label: 'Who caused the Attendance gap?',
        subtitle:
          'Find employees driving the attendance gap and What-If coaching ROI.',
        badge: 'PEOPLE',
        prompt:
          'Who are the top negative contributors to the Attendance Rate gap in Call Center and what happens if we coach the bottom 3?',
        category: 'people',
        icon_key: 'users',
      },
      {
        id: 'branch-compare',
        label: 'Compare Dubai vs Sharjah & Branches',
        subtitle:
          'Compare attendance, bookings, and no-shows across all UAE branches.',
        badge: 'BRANCH',
        prompt:
          'Compare all UAE branches (Dubai, Sharjah, Ajman, Clinics) Attendance and Booking conversion for Call Center and recommend branch decisions.',
        category: 'branch',
        icon_key: 'chart',
      },
      {
        id: 'governance-actions',
        label: 'Pending corrective actions & SIP',
        subtitle:
          'Review open corrective actions, overdue items, and SIP candidates.',
        badge: 'GOVERNANCE',
        prompt:
          'Summarize open or overdue corrective actions and SIP/PI risk candidates in Call Center with recommended next steps.',
        category: 'governance',
        icon_key: 'shield',
      },
      {
        id: 'agent-spotlight-trend',
        label: 'Best Agent & 6-Month Score Trend',
        subtitle:
          'Instant spotlight of the #1 agent with grade, KPIs, and 6-month trend.',
        badge: 'TREND',
        prompt: 'Who is the best agent in Inbound and his trend?',
        category: 'people',
        icon_key: 'users',
      },
      {
        id: 'outbound-paradox',
        label: 'Outbound Booking vs. No-Show',
        subtitle:
          'Diagnose why Booking is 100% while Attendance is 56.6% with actions.',
        badge: 'DECISIONS',
        prompt:
          'Diagnose Outbound KPIs (Attendance Rate, Reachability, Booking Rate) and propose an executive decision playbook to reduce patient no-shows.',
        category: 'kpi',
        icon_key: 'chart',
      },
    ];
  }, [watchingData?.starter_prompts]);

  const filteredStarterPrompts = useMemo(() => {
    if (selectedCategory === 'all') return starterPrompts;
    return starterPrompts.filter((p) => p.category === selectedCategory);
  }, [starterPrompts, selectedCategory]);

  const latestSuggestedChips: string[] = useMemo(() => {
    const lastCompleted = [...turns].reverse().find((t) => t.response?.suggested_followups?.length);
    if (lastCompleted?.response?.suggested_followups) {
      return lastCompleted.response.suggested_followups;
    }
    return starterPrompts.map((p) => p.prompt);
  }, [turns, starterPrompts]);

  const resolvedMonthLabel =
    watchingData?.resolved_session_state?.month || sessionState.month || 'September';
  const resolvedYearLabel =
    watchingData?.resolved_session_state?.year || sessionState.year || 2026;

  return (
    <div className="min-h-full bg-gradient-to-br from-[#EDF4FC] via-[#F5F9FD] to-[#EBF3FA] px-3 py-3 sm:px-5">
      <div className="mx-auto max-w-[1440px]">
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_310px]">
          {/* Center Workspace Card */}
          <section
            aria-label="PMS AI analytical conversation workspace"
            className="relative flex min-h-[calc(100dvh-108px)] flex-col justify-between overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-[0_10px_35px_rgb(15,23,42,0.06)]"
          >
            {/* Seamless Top Radial Aurora Glow (no sharp rectangular cutoff) */}
            <div
              className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-[radial-gradient(ellipse_75%_65%_at_50%_0%,rgba(56,189,248,0.18),rgba(16,185,129,0.07)_55%,transparent_100%)]"
              aria-hidden="true"
            />

            {/* Top Header Bar */}
            <div className="relative z-30 flex flex-wrap items-center justify-between gap-2.5 border-b border-slate-100/90 bg-white/85 px-4 py-2.5 backdrop-blur-md sm:px-5">
              <div className="flex items-center gap-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 via-blue-600 to-indigo-700 text-white shadow-sm shadow-blue-500/30">
                  <Sparkles size={16} />
                </div>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h1 className="text-sm font-extrabold tracking-tight text-slate-900">
                      PMS AI
                    </h1>
                    <span className="inline-flex items-center gap-1 rounded-full border border-sky-200/80 bg-sky-50 px-2 py-0.5 text-[11px] font-bold text-sky-700">
                      <Calendar size={11} className="text-sky-600" />
                      {resolvedMonthLabel} {resolvedYearLabel}
                    </span>
                  </div>
                  <p className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
                    Reads your workspace · Proposes quantified decisions · Never acts without you
                  </p>
                </div>
              </div>

              {/* Custom Luminous Scope Context Dropdowns + New Chat */}
              <div className="flex flex-wrap items-center gap-1.5">
                <AiScopeDropdown
                  ariaLabel="Filter Call Center Team"
                  prefix="Team"
                  value={selectedTeam}
                  defaultValue="All"
                  icon={<Users size={12} />}
                  onChange={(val) => handleFilterChange('team', val)}
                  options={
                    watchingData?.eligible_teams && watchingData.eligible_teams.length > 0
                      ? [
                          {
                            value: 'All',
                            label: `All ${sessionState.function || 'Teams'}`,
                            badge: `${watchingData.eligible_teams.length} Teams`,
                          },
                          ...watchingData.eligible_teams.map((t) => ({
                            value: t.value,
                            label: t.label,
                            badge: t.badge || t.function,
                          })),
                        ]
                      : [
                          { value: 'All', label: 'All Call Center', badge: '3 Scopes' },
                          { value: 'Inbound', label: 'Inbound', badge: '35 Agents' },
                          { value: 'Outbound', label: 'Outbound', badge: '7 Agents' },
                          { value: 'Support Positions', label: 'Support Positions', badge: 'Call Center' },
                        ]
                  }
                />

                <AiScopeDropdown
                  ariaLabel="Filter UAE Branch"
                  prefix="Branch"
                  value={selectedBranch}
                  defaultValue="all"
                  icon={<Building2 size={12} />}
                  onChange={(val) => handleFilterChange('branch', val)}
                  options={
                    watchingData?.eligible_branches && watchingData.eligible_branches.length > 0
                      ? [
                          ...(watchingData.eligible_branches.length > 1
                            ? [
                                {
                                  value: 'all',
                                  label: 'All UAE',
                                  badge: `${watchingData.eligible_branches.length} Branches`,
                                },
                              ]
                            : []),
                          ...watchingData.eligible_branches.map((b) => ({
                            value: b,
                            label: b.charAt(0).toUpperCase() + b.slice(1),
                            badge: b === 'clinics' ? 'Outpatient' : 'Hospital',
                          })),
                        ]
                      : [
                          { value: 'all', label: 'All UAE', badge: '4 Branches' },
                          { value: 'dubai', label: 'Dubai', badge: 'Hospital' },
                          { value: 'sharjah', label: 'Sharjah', badge: 'Hospital' },
                          { value: 'ajman', label: 'Ajman', badge: 'Hospital' },
                          { value: 'clinics', label: 'Clinics', badge: 'Outpatient' },
                        ]
                  }
                />

                <AiScopeDropdown
                  ariaLabel="Filter Performance Level"
                  prefix="Level"
                  value={selectedLevel}
                  defaultValue="All"
                  icon={<Layers size={12} />}
                  onChange={(val) => handleFilterChange('performance_level', val)}
                  options={
                    watchingData?.eligible_levels && watchingData.eligible_levels.length > 0
                      ? [
                          ...(watchingData.eligible_levels.length > 1
                            ? [{ value: 'All', label: 'All Levels', badge: 'Full Scope' }]
                            : []),
                          ...watchingData.eligible_levels.map((lvl) => ({
                            value: lvl,
                            label: lvl === 'Employee' ? 'Employee' : `${lvl} BSC`,
                            badge:
                              lvl === 'Employee'
                                ? 'Agents'
                                : lvl === 'Managerial'
                                ? 'Leaders'
                                : 'Executive',
                          })),
                        ]
                      : [
                          { value: 'All', label: 'All Levels', badge: 'Full Scope' },
                          { value: 'Employee', label: 'Employee', badge: 'Agents' },
                          { value: 'Managerial', label: 'Managerial BSC', badge: 'Leaders' },
                          { value: 'Corporate', label: 'Corporate BSC', badge: 'Executive' },
                        ]
                  }
                />

                <div
                  role="group"
                  aria-label="Response detail mode"
                  className="inline-flex items-center rounded-full border border-slate-200/90 bg-slate-50/90 p-0.5 text-[11px] font-bold"
                >
                  <button
                    type="button"
                    aria-pressed={answerDetail === 'brief' || answerDetail === 'auto'}
                    onClick={() => setAnswerDetail('brief')}
                    className={`rounded-full px-2.5 py-1 transition-colors ${
                      answerDetail === 'brief' || answerDetail === 'auto'
                        ? 'bg-blue-600 text-white shadow-2xs'
                        : 'text-slate-600 hover:text-blue-600'
                    }`}
                  >
                    Brief
                  </button>
                  <button
                    type="button"
                    aria-pressed={answerDetail === 'details'}
                    onClick={() => setAnswerDetail('details')}
                    className={`rounded-full px-2.5 py-1 transition-colors ${
                      answerDetail === 'details'
                        ? 'bg-blue-600 text-white shadow-2xs'
                        : 'text-slate-600 hover:text-blue-600'
                    }`}
                  >
                    Details
                  </button>
                </div>

                {turns.length > 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      setTurns([]);
                      setLastConfirmedQuery(null);
                    }}
                    className="inline-flex items-center gap-1 rounded-full border border-slate-200/90 bg-white px-3 py-1.5 text-[11px] font-bold text-slate-700 shadow-2xs transition-colors hover:border-blue-400 hover:text-blue-600"
                  >
                    <RotateCcw size={12} />
                    <span>New chat</span>
                  </button>
                )}
              </div>
            </div>

            {/* Center Body */}
            <div className="relative z-10 flex-1 overflow-y-auto px-4 py-4 sm:px-6">
              {turns.length === 0 ? (
                <div className="mx-auto flex h-full max-w-4xl flex-col items-center justify-center py-2">
                  {/* Compact Glossy 3D Squircle Hero Badge */}
                  <div className="relative mb-2.5">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-400 via-blue-600 to-indigo-700 text-white shadow-[0_10px_24px_-4px_rgba(37,99,235,0.5)] ring-4 ring-white">
                      <Sparkles size={22} />
                    </div>
                    <span
                      className="pointer-events-none absolute -top-1.5 -right-2.5 text-sky-500"
                      aria-hidden="true"
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <path
                          d="M4 10L1 7M12 5V1M18 11L22 9"
                          stroke="currentColor"
                          strokeWidth="2.5"
                          strokeLinecap="round"
                        />
                      </svg>
                    </span>
                  </div>

                  <h2 className="bg-gradient-to-r from-slate-900 via-blue-600 to-slate-900 bg-clip-text text-center text-xl font-extrabold tracking-tight text-transparent sm:text-2xl">
                    Hi {firstName}, how can I help?
                  </h2>
                  <p className="mt-1 max-w-lg text-center text-xs font-medium text-slate-500">
                    Select a quick scenario below, or ask about any agent, 6-month trend, team, or branch.
                  </p>

                  {/* Compact Pill Category Tabs */}
                  <div
                    role="tablist"
                    aria-label="Filter analytical scenarios by category"
                    className="mt-3.5 flex flex-wrap items-center justify-center gap-1.5"
                  >
                    {[
                      { key: 'all', label: 'All Scenarios', icon: <LayoutGrid size={12} /> },
                      { key: 'team', label: 'Teams', icon: <Users size={12} /> },
                      { key: 'people', label: 'People & Trends', icon: <PieChart size={12} /> },
                      { key: 'branch', label: 'Branches', icon: <GitBranch size={12} /> },
                      { key: 'kpi', label: 'KPIs & Decisions', icon: <BarChart3 size={12} /> },
                      { key: 'governance', label: 'SIP & Actions', icon: <Target size={12} /> },
                    ].map((tab) => {
                      const active = selectedCategory === tab.key;
                      return (
                        <button
                          key={tab.key}
                          type="button"
                          role="tab"
                          aria-selected={active}
                          onClick={() => setSelectedCategory(tab.key)}
                          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-bold transition-all ${
                            active
                              ? 'bg-gradient-to-r from-blue-600 to-sky-500 text-white shadow-sm shadow-blue-500/25'
                              : 'border border-slate-200/90 bg-white/90 text-slate-600 hover:border-blue-300 hover:text-blue-600'
                          }`}
                        >
                          <span className={active ? 'text-white' : 'text-blue-600'}>
                            {tab.icon}
                          </span>
                          <span>{tab.label}</span>
                        </button>
                      );
                    })}
                  </div>

                  {/* Sleek, Compact 3-Column Scenario Cards (2 rows x 3 columns) */}
                  <div className="mt-4 grid w-full grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                    {filteredStarterPrompts.map((item) => {
                      const style = CATEGORY_STYLES[item.category] || CATEGORY_STYLES.team;
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => void sendPrompt(item.prompt)}
                          className={`group flex flex-col justify-between rounded-2xl border border-slate-200/85 bg-white/95 p-3 text-left shadow-2xs transition-all hover:-translate-y-0.5 ${style.cardHover}`}
                        >
                          <div>
                            <div className="flex items-center justify-between gap-2">
                              <div className="flex items-center gap-2">
                                <div
                                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl transition-transform group-hover:scale-105 ${style.iconBox}`}
                                >
                                  {STARTER_ICON_MAP[item.icon_key] || STARTER_ICON_MAP.chart}
                                </div>
                                <span
                                  className={`inline-block rounded-md px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wider ${style.badge}`}
                                >
                                  {item.badge || item.category.toUpperCase()}
                                </span>
                              </div>
                              <span className="inline-flex items-center gap-0.5 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-blue-600 transition-colors group-hover:bg-blue-600 group-hover:text-white">
                                <span>Run</span>
                                <ArrowRight size={10} />
                              </span>
                            </div>

                            <p className="mt-2 line-clamp-1 text-xs font-extrabold text-slate-900">
                              {item.label}
                            </p>
                            {item.subtitle && (
                              <p
                                dir="auto"
                                className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-slate-500"
                              >
                                {item.subtitle}
                              </p>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {turns.map((turn) => (
                    <div key={turn.id} className="space-y-3">
                      {/* Right-aligned User Prompt Bubble */}
                      <div className="flex items-center justify-end gap-2">
                        <div
                          dir="auto"
                          className="max-w-xl rounded-2xl rounded-br-xs bg-gradient-to-r from-blue-600 to-sky-500 px-3.5 py-2 text-xs font-bold text-white shadow-sm shadow-blue-500/20"
                        >
                          {turn.userPrompt}
                        </div>
                        <div
                          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-600 text-[11px] font-extrabold text-white shadow-2xs"
                          aria-hidden="true"
                        >
                          {userInitials}
                        </div>
                      </div>

                      {/* Left-aligned Assistant Skeleton */}
                      {turn.isPending && (
                        <div className="flex items-start gap-2.5" aria-label="Analyzing workspace data">
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 via-blue-600 to-indigo-700 text-white shadow-2xs">
                            <Sparkles size={15} className="animate-spin" />
                          </div>
                          <div className="flex-1 space-y-2.5 rounded-2xl border border-slate-200/90 bg-white p-4 shadow-2xs">
                            <div className="h-3.5 w-2/3 animate-pulse rounded bg-slate-100" />
                            <div className="h-20 w-full animate-pulse rounded-xl bg-slate-50" />
                          </div>
                        </div>
                      )}

                      {turn.error && (
                        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-3.5 text-xs font-semibold text-rose-800">
                          <div>
                            <p className="font-bold">Unable to complete analysis</p>
                            <p className="mt-1">{turn.error}</p>
                          </div>
                          <button
                            type="button"
                            onClick={() => void sendPrompt(turn.userPrompt)}
                            className="inline-flex items-center gap-1.5 rounded-full border border-rose-300 bg-white px-3 py-1.5 text-[11px] font-bold text-rose-700 shadow-2xs transition-colors hover:bg-rose-100"
                          >
                            <RotateCcw size={12} />
                            <span>Retry</span>
                          </button>
                        </div>
                      )}

                      {turn.response && (
                        <AiResponseCard
                          response={turn.response}
                          onSelectPrompt={(p) => void sendPrompt(p)}
                        />
                      )}
                    </div>
                  ))}
                  <div ref={streamEndRef} />
                </div>
              )}
            </div>

            {/* Bottom Dock: Compact Follow-Up Chips + Pill Composer */}
            <div className="relative z-20 border-t border-slate-100 bg-white/95 px-4 pb-3 pt-2.5 sm:px-6">
              {turns.length > 0 && (
                <div className="mb-2 rounded-xl border border-slate-200/80 bg-slate-50/70 px-2.5 py-1.5">
                  <div className="flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => setShowScenarioTray((v) => !v)}
                      className="inline-flex items-center gap-1.5 text-[11px] font-extrabold text-slate-700 hover:text-blue-600"
                    >
                      <Compass size={13} className="text-blue-600" />
                      <span>Quick Follow-Ups</span>
                      {showScenarioTray ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
                    </button>
                    <span className="text-[10px] font-semibold text-slate-400">
                      Click to run
                    </span>
                  </div>

                  {showScenarioTray && (
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {latestSuggestedChips.slice(0, 4).map((chipPrompt) => (
                        <button
                          key={chipPrompt}
                          type="button"
                          disabled={isSending}
                          onClick={() => void sendPrompt(chipPrompt)}
                          dir="auto"
                          className="group inline-flex items-center gap-1.5 rounded-full border border-slate-200/90 bg-white px-2.5 py-1 text-left text-[11px] font-bold text-slate-700 shadow-2xs transition-all hover:border-blue-400 hover:bg-blue-50/50 hover:text-blue-700 disabled:opacity-50"
                        >
                          <span className="max-w-[260px] truncate">{chipPrompt}</span>
                          <ArrowRight
                            size={11}
                            className="shrink-0 text-blue-600 transition-transform group-hover:translate-x-0.5"
                          />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void sendPrompt(promptInput);
                }}
                className="flex items-center gap-2 rounded-full border border-slate-200/90 bg-white px-3.5 py-1 shadow-xs transition-all focus-within:border-blue-500 focus-within:ring-3 focus-within:ring-blue-500/10"
              >
                <input
                  type="text"
                  dir="auto"
                  value={promptInput}
                  onChange={(e) => setPromptInput(e.target.value)}
                  disabled={isSending}
                  placeholder="Ask anything about performance, agents, 6-month trends, branches, or request decisions..."
                  aria-label="Ask PMS AI a question"
                  className="min-w-0 flex-1 bg-transparent py-1 text-xs font-semibold text-slate-900 placeholder:text-slate-400 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={isSending || !promptInput.trim()}
                  aria-label="Send prompt"
                  className="flex h-8 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-r from-blue-600 to-sky-500 text-white shadow-sm shadow-blue-500/30 transition-all hover:opacity-95 disabled:opacity-40"
                >
                  <Send size={14} />
                </button>
              </form>

              <p className="mt-1.5 flex items-center justify-center gap-1 text-center text-[10px] font-medium text-slate-400">
                <Info size={11} className="shrink-0" />
                <span>
                  Every answer &amp; decision playbook is computed deterministically by the official PMS scoring engine and scoped to your role.
                </span>
              </p>
            </div>
          </section>

          {/* Compact Right Rail: AI is watching + Guardrails */}
          <AiWatchingRail
            alerts={watchingData?.alerts || []}
            guardrails={watchingData?.guardrails || []}
            isLoading={isWatchingLoading}
            onSelectAlert={(prompt) => void sendPrompt(prompt)}
          />
        </div>
      </div>
    </div>
  );
}
