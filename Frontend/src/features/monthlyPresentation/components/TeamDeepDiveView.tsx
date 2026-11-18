import { useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { QueryClientContext } from '@tanstack/react-query';
import { ApiError } from '../../../lib/apiClient';
import {
  AiRecommendationBanner,
  AiRecommendIconButton,
  AiStatusInline,
  IndividualEvidenceDrawer,
  TeamEvidenceDrawer,
  ViewEvidenceToggleButton,
} from './ActionPlanAiAssistant';
import { formatScoreChangeLabel } from './scoreChangeLabel';
import {
  buildAiScopeKey,
  parseMonthYearFromLabel,
  requestActionPlanAiSuggestion,
  resolveTeamCardFocusKpiKey,
  type ActionPlanAiError,
  type AiCorrectiveActionSuggestionPayload,
} from './actionPlanAiUtils';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowLeft,
  ArrowUpRight,
  Check,
  ChevronLeft,
  ChevronRight,
  Edit3,
  Flame,
  Gauge,
  Layers,
  Plus,
  RotateCcw,
  Sparkles,
  Target,
  Trash2,
  UserCheck,
  Users,
} from 'lucide-react';
import {
  ProfileKpiSixMonthTrend,
  type SixMonthKpiSeriesItem,
} from '../../../components/employee/ScoreTrendChart';
import ScoreTrendChart from '../../../components/employee/ScoreTrendChart';
import { KpiTrendMovement, SelectableKpiCard } from './SelectableKpiCard';
import { GRADE_STYLES, type GradeLetter } from '../monthlyOverviewData';
import type { FullGradeLabel } from '../callCenterDeepDiveData';
import { showActionSection, showPresentationControl, showStoredPlaceholder } from '../presentationMode';
import {
  applyTeamTrendConfig,
  defaultTeamTrendConfig,
  selectedTeamConfigSource,
  unavailableTeamTrend,
  withEmptyTeamTrend,
  teamActionDueLabel,
  type IndividualActionPlanCard,
  type TeamDeepDiveData,
  type TeamLevelActionPlanCard,
  type TeamSlug,
} from '../teamDeepDiveData';
import { useTeamConfig } from '../../../hooks/useTeamConfig';
import { memberPageWindow, TEAM_AGENT_PAGE_SIZE } from '../roleMemberPages';

const TEAM_KPI_CARDS_PER_ROW = 4;
const DISMISSED_TEAM_IND_STORAGE_KEY = 'pms_dismissed_team_ind_cards_v1';

function readDismissedIds(storageKey: string, scopeKey: string): string[] {
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Record<string, string[]>;
    const items = parsed?.[scopeKey];
    return Array.isArray(items) ? items : [];
  } catch {
    return [];
  }
}

function writeDismissedIds(storageKey: string, scopeKey: string, ids: string[]): void {
  try {
    const raw = window.localStorage.getItem(storageKey);
    const parsed = raw ? (JSON.parse(raw) as Record<string, string[]>) : {};
    const next =
      parsed && typeof parsed === 'object'
        ? { ...parsed, [scopeKey]: ids }
        : { [scopeKey]: ids };
    window.localStorage.setItem(storageKey, JSON.stringify(next));
  } catch {
    // Ignore storage quota or SSR issues
  }
}

export interface TeamDeepDiveViewProps {
  data: TeamDeepDiveData;
  onNavigateToOverview: () => void;
  onNavigateToCallCenter: () => void;
  onSwitchTeam?: (teamSlug: TeamSlug) => void;
  onSaveIndividualAction?: (card: IndividualActionPlanCard) => Promise<void> | void;
  onDeleteIndividualAction?: (
    employeeId: string,
    monthName: string,
    actionId?: string,
  ) => Promise<void> | void;
  savedTeamActions?: TeamLevelActionPlanCard[];
  onSaveTeamAction?: (card: TeamLevelActionPlanCard) => Promise<void> | void;
  onDeleteTeamAction?: (card: TeamLevelActionPlanCard) => Promise<void> | void;
  onRestoreTeamActions?: (cardIds: string[]) => Promise<void> | void;
  toolbar?: ReactNode;
  presentationMode?: boolean;
}

/**
 * Full-word Grade Badge (never single letters, per Team Deep Dive requirements)
 */
export function FullWordGradeBadge({
  grade,
  gradeFullLabel,
  size = 'md',
}: {
  grade: GradeLetter;
  gradeFullLabel: FullGradeLabel;
  size?: 'sm' | 'md' | 'lg';
}) {
  const style = GRADE_STYLES[grade];
  const sizeClass =
    size === 'lg'
      ? 'px-3.5 py-1 text-sm font-bold rounded-xl'
      : size === 'sm'
      ? 'px-2.5 py-0.5 text-xs font-bold rounded-md'
      : 'px-3 py-1 text-xs font-bold rounded-lg';

  return (
    <span
      className={`inline-flex items-center justify-center border ${style.badgeBg} ${style.badgeText} ${style.badgeBorder} ${sizeClass}`}
    >
      {gradeFullLabel}
    </span>
  );
}

export default function TeamDeepDiveView(props: TeamDeepDiveViewProps) {
  const client = useContext(QueryClientContext);
  const data = withEmptyTeamTrend(props.data);
  if (!client) {
    const fallbackConfig = defaultTeamTrendConfig(data);
    const resolved = fallbackConfig ? applyTeamTrendConfig(data, fallbackConfig) : unavailableTeamTrend(data);
    return <TeamDeepDiveViewContent key={`${resolved.teamSlug}|${resolved.regionCode}|${resolved.periodKey}`} {...props} data={resolved} />;
  }
  return <ConfiguredTeamDeepDiveView {...props} data={data} />;
}

function ConfiguredTeamDeepDiveView(props: TeamDeepDiveViewProps) {
  const { data: original } = props;
  const { data: config } = useTeamConfig(selectedTeamConfigSource(original));
  const resolvedConfig = config ?? defaultTeamTrendConfig(original);
  const data = resolvedConfig ? applyTeamTrendConfig(original, resolvedConfig) : unavailableTeamTrend(original);
  const contextKey = `${data.teamSlug}|${data.regionCode}|${data.periodKey}`;
  return <TeamDeepDiveViewContent key={contextKey} {...props} data={data} />;
}

function TeamDeepDiveViewContent({
  data,
  onNavigateToOverview,
  onNavigateToCallCenter,
  onSwitchTeam,
  onSaveIndividualAction,
  onDeleteIndividualAction,
  savedTeamActions,
  onSaveTeamAction,
  onDeleteTeamAction,
  onRestoreTeamActions,
  toolbar,
  presentationMode = false,
}: TeamDeepDiveViewProps) {
  const summaryGradeStyle = GRADE_STYLES[data.summary.grade];
  const measuredChange = data.scoreTrend ? data.scoreTrend.changeVsPrevious : data.summary.changeVsPrev;
  const showChange = measuredChange !== null && Number.isFinite(measuredChange);
  const isPositiveChange = showChange && measuredChange > 0;
  const comparedMonth = data.scoreTrend?.previousMonthLabel ?? data.previousMonthLabel;

  // Enrich & sort team KPIs from worst to best (lowest achievement / highest points lost first)
  const enrichedKpis = useMemo(() => {
    const count = data.kpis.length;
    const weights =
      count === 1
        ? [100]
        : count === 2
        ? [50, 50]
        : count === 3
        ? [40, 30, 30]
        : [30, 30, 20, 20];
    const items = data.kpis.map((kpi, idx) => {
      const weightPct = weights[idx] ?? Math.round(100 / Math.max(1, count));
      const cappedPct = Math.min(
        100,
        Math.max(0, Number.isFinite(kpi.achievementPct) ? kpi.achievementPct : 0),
      );
      const contributionPct = Math.round(((cappedPct / 100) * weightPct) * 10) / 10;
      const pointsLost = Math.max(0, Math.round((weightPct - contributionPct) * 10) / 10);
      const statusBadge: 'On Target' | 'Needs Attention' | 'Below Target' =
        cappedPct >= 99.95 || kpi.verdictBadge === 'Target Met'
          ? 'On Target'
          : cappedPct >= 80
          ? 'Needs Attention'
          : 'Below Target';
      return {
        ...kpi,
        weightPct,
        cappedPct,
        contributionPct,
        pointsLost,
        statusBadge,
      };
    });

    items.sort(
      (a, b) => a.cappedPct - b.cappedPct || b.pointsLost - a.pointsLost,
    );

    let maxLost = 0;
    let maxIdx = -1;
    items.forEach((item, idx) => {
      if (item.pointsLost > maxLost) {
        maxLost = item.pointsLost;
        maxIdx = idx;
      }
    });

    return items.map((item, idx) => ({
      ...item,
      isBiggestGap: idx === maxIdx && maxLost > 0.1,
    }));
  }, [data.kpis]);

  const biggestGapKpi = useMemo(
    () =>
      enrichedKpis.find((k) => k.isBiggestGap && k.pointsLost > 0) ??
      enrichedKpis.filter((k) => k.pointsLost > 0).sort((a, b) => b.pointsLost - a.pointsLost)[0] ??
      null,
    [enrichedKpis],
  );

  // Selected KPI in the KPI Trend Explorer
  const [selectedKpiKey, setSelectedKpiKey] = useState<string>(
    data.kpis[0]?.kpiKey ?? 'AHT',
  );
  const [carouselStart, setCarouselStart] = useState(0);
  const viewScopeKey = `${data.teamSlug}|${data.regionCode}|${data.periodKey}`;
  const [prevViewScopeKey, setPrevViewScopeKey] = useState(viewScopeKey);

  // Dismissed / Delete state for Individual Action Plans (per viewScopeKey in localStorage)
  const [dismissedIndIds, setDismissedIndIds] = useState<string[]>(() =>
    readDismissedIds(DISMISSED_TEAM_IND_STORAGE_KEY, viewScopeKey),
  );
  const [confirmDeleteIndId, setConfirmDeleteIndId] = useState<string | null>(null);
  const [deletingIndId, setDeletingIndId] = useState<string | null>(null);
  const [indDeleteError, setIndDeleteError] = useState<Record<string, string>>({});

  // Editable Individual Action Plans state (derived from props + local overrides)
  const [individualOverrides, setIndividualOverrides] = useState<
    Record<string, IndividualActionPlanCard>
  >({});
  const individualCards = useMemo(
    () =>
      data.individualActionPlans.map(
        (card) => individualOverrides[card.id] ?? card,
      ),
    [data.individualActionPlans, individualOverrides],
  );
  const [editingIndividualId, setEditingIndividualId] = useState<string | null>(null);
  const [draftActionText, setDraftActionText] = useState<string>('');
  const [draftMainIssue, setDraftMainIssue] = useState<string>('');
  const [draftOwner, setDraftOwner] = useState<string>('');
  const [draftImpact, setDraftImpact] = useState<string>('');
  const [draftFollowUpLabel, setDraftFollowUpLabel] = useState<string>('');
  const [draftObservationStatus, setDraftObservationStatus] =
    useState<IndividualActionPlanCard['observationStatus']>(undefined);
  const [indSaveFeedback, setIndSaveFeedback] = useState<
    Record<string, { type: 'success' | 'error'; message: string }>
  >({});
  const [savingIndividualId, setSavingIndividualId] = useState<string | null>(null);

  // Agent pagination state (10 agents per page with cachedNext buffer)
  const agentListKey = `${data.teamSlug}|${data.regionCode}|${data.periodKey}`;
  const [agentPageState, setAgentPageState] = useState({
    listKey: agentListKey,
    page: 0,
  });
  const requestedAgentPage = agentPageState.listKey === agentListKey ? agentPageState.page : 0;

  const agentPages = useMemo(
    () => memberPageWindow(data.agentsAverageOrBelow, requestedAgentPage, TEAM_AGENT_PAGE_SIZE),
    [data.agentsAverageOrBelow, requestedAgentPage],
  );
  const visibleAgents = agentPages.visible;

  // Individual Action Plans synchronized to visible agents on the current page (excluding dismissed)
  const dismissedIndSet = useMemo(
    () => new Set(dismissedIndIds.map((id) => id.toLowerCase())),
    [dismissedIndIds],
  );
  const displayedIndividualCards = useMemo(() => {
    const activeCards = individualCards.filter(
      (c) => !dismissedIndSet.has(c.employeeId.toLowerCase()),
    );
    if (individualCards.length <= TEAM_AGENT_PAGE_SIZE && agentPages.pageCount <= 1) {
      return activeCards;
    }
    const visibleIds = new Set(visibleAgents.map((a) => a.employeeId.toLowerCase()));
    const visibleNames = new Set(visibleAgents.map((a) => a.agentName.toLowerCase()));
    return activeCards.filter(
      (c) =>
        visibleIds.has(c.employeeId.toLowerCase()) ||
        visibleNames.has(c.agentName.toLowerCase()),
    );
  }, [individualCards, dismissedIndSet, visibleAgents, agentPages.pageCount]);

  // Editable Team-Level Action Plans state (derived from base + savedTeamActions + local overrides)
  const [addedTeamCards, setAddedTeamCards] = useState<TeamLevelActionPlanCard[]>([]);
  const [teamCardOverrides, setTeamCardOverrides] = useState<
    Record<string, TeamLevelActionPlanCard>
  >({});
  const [deletedTeamCardIds, setDeletedTeamCardIds] = useState<string[]>([]);
  const [confirmDeleteTeamId, setConfirmDeleteTeamId] = useState<string | null>(null);
  const [deletingTeamId, setDeletingTeamId] = useState<string | null>(null);
  const [teamDeleteError, setTeamDeleteError] = useState<Record<string, string>>({});
  const [restoringTeam, setRestoringTeam] = useState(false);
  const [teamRestoreError, setTeamRestoreError] = useState<string | null>(null);

  const allMergedTeamCards = useMemo(() => {
    const savedById = new Map<string, TeamLevelActionPlanCard>();
    for (const saved of savedTeamActions ?? []) {
      savedById.set(saved.id, saved);
    }
    const baseIds = new Set(data.teamActionPlans.map((c) => c.id));
    const mergedBase = data.teamActionPlans.map((c) => {
      const saved = savedById.get(c.id);
      return teamCardOverrides[c.id] ?? saved ?? c;
    });
    const extraSaved = (savedTeamActions ?? [])
      .filter((c) => !baseIds.has(c.id))
      .map((c) => teamCardOverrides[c.id] ?? c);
    const extraIds = new Set(extraSaved.map((c) => c.id));
    const localAdded = addedTeamCards
      .filter((c) => !baseIds.has(c.id) && !extraIds.has(c.id))
      .map((c) => teamCardOverrides[c.id] ?? c);
    return [...localAdded, ...extraSaved, ...mergedBase];
  }, [addedTeamCards, data.teamActionPlans, savedTeamActions, teamCardOverrides]);

  const builtInTeamIdSet = useMemo(
    () => new Set(data.teamActionPlans.map((c) => c.id)),
    [data.teamActionPlans],
  );
  const deletedBuiltInIds = useMemo(() => {
    const ids = new Set<string>();
    for (const card of allMergedTeamCards) {
      if ((card.isDeleted || deletedTeamCardIds.includes(card.id)) && builtInTeamIdSet.has(card.id)) {
        ids.add(card.id);
      }
    }
    for (const saved of savedTeamActions ?? []) {
      if (saved.isDeleted && builtInTeamIdSet.has(saved.id)) {
        ids.add(saved.id);
      }
    }
    return Array.from(ids);
  }, [allMergedTeamCards, builtInTeamIdSet, deletedTeamCardIds, savedTeamActions]);

  const teamCards = useMemo(
    () =>
      allMergedTeamCards.filter(
        (c) => !c.isDeleted && !deletedTeamCardIds.includes(c.id),
      ),
    [allMergedTeamCards, deletedTeamCardIds],
  );

  const [isAddingTeamAction, setIsAddingTeamAction] = useState(false);
  const [newTeamTitle, setNewTeamTitle] = useState('');
  const [newTeamTargetKpi, setNewTeamTargetKpi] = useState('');
  const [newTeamScope, setNewTeamScope] = useState(
    `All ${data.summary.headcount} ${data.teamDisplayName}`,
  );
  const [newTeamOwner, setNewTeamOwner] = useState(`${data.canonicalTeam} Team Leader`);
  const [newTeamStatus, setNewTeamStatus] = useState<TeamLevelActionPlanCard['status']>('Open');
  const [newTeamDueDate, setNewTeamDueDate] = useState('');
  const [newTeamImpact, setNewTeamImpact] = useState('+1.0% team score lift');

  // Inline editing state for Team-Level Action cards
  const [editingTeamId, setEditingTeamId] = useState<string | null>(null);
  const [draftTeamTitle, setDraftTeamTitle] = useState('');
  const [draftTeamTargetKpi, setDraftTeamTargetKpi] = useState('');
  const [draftTeamScope, setDraftTeamScope] = useState('');
  const [draftTeamOwner, setDraftTeamOwner] = useState('');
  const [draftTeamStatus, setDraftTeamStatus] = useState<TeamLevelActionPlanCard['status']>('Open');
  const [draftTeamDueDate, setDraftTeamDueDate] = useState('');
  const [draftTeamImpact, setDraftTeamImpact] = useState('');
  const [teamSaveFeedback, setTeamSaveFeedback] = useState<
    Record<string, { type: 'success' | 'error'; message: string }>
  >({});

  // AI Draft state keyed by 'ind:<id>', 'team:<id>', or 'new-team'
  type CardAiState = {
    loading: boolean;
    scopeKey?: string;
    payload: AiCorrectiveActionSuggestionPayload | null;
    error: ActionPlanAiError | null;
    needsOverwriteConfirm: boolean;
    draftApplied: boolean;
  };
  const [aiStateByTarget, setAiStateByTarget] = useState<Record<string, CardAiState>>({});
  const [expandedEvidenceIds, setExpandedEvidenceIds] = useState<Record<string, boolean>>({});
  const abortControllersRef = useRef<Record<string, AbortController>>({});
  const inFlightScopesRef = useRef<Record<string, string>>({});

  if (prevViewScopeKey !== viewScopeKey) {
    setPrevViewScopeKey(viewScopeKey);
    setAiStateByTarget({});
    setExpandedEvidenceIds({});
    setIndividualOverrides({});
    setEditingIndividualId(null);
    setDismissedIndIds(readDismissedIds(DISMISSED_TEAM_IND_STORAGE_KEY, viewScopeKey));
    setConfirmDeleteIndId(null);
    setDeletingIndId(null);
    setIndDeleteError({});
    setDeletedTeamCardIds([]);
    setConfirmDeleteTeamId(null);
    setDeletingTeamId(null);
    setTeamDeleteError({});
    setTeamRestoreError(null);
    setSavingIndividualId(null);
  }

  useEffect(() => {
    if (!confirmDeleteIndId && !confirmDeleteTeamId) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (confirmDeleteIndId && deletingIndId !== confirmDeleteIndId) {
        setConfirmDeleteIndId(null);
      }
      if (confirmDeleteTeamId && deletingTeamId !== confirmDeleteTeamId) {
        setConfirmDeleteTeamId(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [confirmDeleteIndId, confirmDeleteTeamId, deletingIndId, deletingTeamId]);

  useEffect(() => {
    const controllers = abortControllersRef.current;
    const scopes = inFlightScopesRef.current;
    return () => {
      Object.values(controllers).forEach((ctrl) => ctrl.abort());
      Object.keys(controllers).forEach((k) => delete controllers[k]);
      Object.keys(scopes).forEach((k) => delete scopes[k]);
    };
  }, [viewScopeKey]);

  const maxCarouselStart = Math.max(0, enrichedKpis.length - TEAM_KPI_CARDS_PER_ROW);
  const safeCarouselStart = Math.min(carouselStart, maxCarouselStart);
  const visibleKpis = enrichedKpis.slice(
    safeCarouselStart,
    safeCarouselStart + TEAM_KPI_CARDS_PER_ROW,
  );

  const handleSelectTeamKpi = (kpiKey: string) => {
    setSelectedKpiKey(kpiKey);
    const idx = enrichedKpis.findIndex((k) => k.kpiKey === kpiKey);
    if (idx >= 0) {
      if (idx < safeCarouselStart) {
        setCarouselStart(idx);
      } else if (idx >= safeCarouselStart + TEAM_KPI_CARDS_PER_ROW) {
        setCarouselStart(Math.min(maxCarouselStart, idx - TEAM_KPI_CARDS_PER_ROW + 1));
      }
    }
  };

  const activeExplorerKpi =
    enrichedKpis.find((k) => k.kpiKey === selectedKpiKey) ?? enrichedKpis[0];

  const profileTrendKpis = useMemo<SixMonthKpiSeriesItem[]>(
    () =>
      enrichedKpis.map((kpi) => ({
        id: kpi.kpiKey,
        kpiKey: kpi.kpiKey,
        name: kpi.label,
        shortName: kpi.shortLabel,
        unit: kpi.unit,
        betterDirection: kpi.betterDirection,
        actualDisplay: kpi.actualFormatted,
        targetDisplay: kpi.targetFormatted,
        achievementPct: kpi.achievementPct,
        gapLabel:
          kpi.statusBadge === 'On Target'
            ? 'On target'
            : `${kpi.actualFormatted} vs ${kpi.targetFormatted}`,
        diagnosis: kpi.explorerDiagnosis,
        trend6Mo: kpi.trend6Mo,
      })),
    [enrichedKpis],
  );
  const isCallCenter = (data.functionSlug ?? 'call-center') === 'call-center' && data.functionName === 'Call Center';
  const siblings = data.siblingTeams?.length
    ? data.siblingTeams
    : isCallCenter
      ? [
          { slug: 'inbound', label: 'Inbound Agents' },
          { slug: 'outbound', label: 'Outbound Agents' },
        ]
      : [];
  const peopleLabel = isCallCenter ? 'agents' : 'people';

  const { month: activeMonthName, year: activeYearNum } = useMemo(
    () => parseMonthYearFromLabel(data.monthLabel, data.periodKey),
    [data.monthLabel, data.periodKey],
  );

  const startEditIndividual = (card: IndividualActionPlanCard) => {
    setEditingIndividualId(card.id);
    setDraftActionText(card.actionText);
    setDraftMainIssue(card.mainIssue);
    setDraftOwner(card.owner);
    setDraftImpact(card.expectedImpact);
    setDraftFollowUpLabel(card.followUpLabel ?? '');
    setDraftObservationStatus(card.observationStatus);
  };

  const cancelEditIndividual = (card: IndividualActionPlanCard) => {
    setEditingIndividualId(null);
    setDraftActionText(card.actionText);
    setDraftMainIssue(card.mainIssue);
    setDraftOwner(card.owner);
    setDraftImpact(card.expectedImpact);
    setDraftFollowUpLabel(card.followUpLabel ?? '');
    setDraftObservationStatus(card.observationStatus);
  };

  const saveEditIndividual = async (card: IndividualActionPlanCard) => {
    const updated: IndividualActionPlanCard = {
      ...card,
      mainIssue: draftMainIssue.trim() || card.mainIssue,
      actionText: draftActionText.trim() || card.actionText,
      owner: draftOwner.trim() || card.owner,
      expectedImpact: draftImpact.trim() || card.expectedImpact,
      followUpLabel: draftFollowUpLabel.trim() || card.followUpLabel,
      observationStatus: draftObservationStatus ?? card.observationStatus,
      isSavedToStore: true,
    };
    setIndividualOverrides((prev) => ({ ...prev, [card.id]: updated }));
    setEditingIndividualId(null);
    setDismissedIndIds((prev) => {
      const next = prev.filter((id) => id.toLowerCase() !== card.employeeId.toLowerCase());
      if (next.length !== prev.length) {
        writeDismissedIds(DISMISSED_TEAM_IND_STORAGE_KEY, viewScopeKey, next);
      }
      return next;
    });
    setAiStateByTarget((prev) => {
      if (!prev[`ind:${card.id}`]) return prev;
      const next = { ...prev };
      delete next[`ind:${card.id}`];
      return next;
    });
    if (onSaveIndividualAction) {
      try {
        await onSaveIndividualAction(updated);
        setIndSaveFeedback((prev) => ({
          ...prev,
          [card.id]: { type: 'success', message: 'Saved action plan' },
        }));
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Save failed';
        setIndSaveFeedback((prev) => ({
          ...prev,
          [card.id]: { type: 'error', message: msg },
        }));
      }
    }
  };

  const quickSaveIndividual = async (card: IndividualActionPlanCard) => {
    const updated: IndividualActionPlanCard = {
      ...card,
      isSavedToStore: true,
    };
    setSavingIndividualId(card.id);
    try {
      if (onSaveIndividualAction) {
        await onSaveIndividualAction(updated);
      }
      setIndividualOverrides((prev) => ({ ...prev, [card.id]: updated }));
      setDismissedIndIds((prev) => {
        const next = prev.filter((id) => id.toLowerCase() !== card.employeeId.toLowerCase());
        if (next.length !== prev.length) {
          writeDismissedIds(DISMISSED_TEAM_IND_STORAGE_KEY, viewScopeKey, next);
        }
        return next;
      });
      setIndSaveFeedback((prev) => ({
        ...prev,
        [card.id]: { type: 'success', message: 'Saved action plan' },
      }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Save failed';
      setIndSaveFeedback((prev) => ({
        ...prev,
        [card.id]: { type: 'error', message: msg },
      }));
    } finally {
      setSavingIndividualId(null);
    }
  };

  const confirmDeleteIndividual = async (card: IndividualActionPlanCard) => {
    setDeletingIndId(card.employeeId);
    setIndDeleteError((prev) => {
      if (!prev[card.employeeId]) return prev;
      const next = { ...prev };
      delete next[card.employeeId];
      return next;
    });
    try {
      if (onDeleteIndividualAction) {
        await onDeleteIndividualAction(card.employeeId, activeMonthName, card.id);
      }
      setDismissedIndIds((prev) => {
        const exists = prev.some(
          (id) => id.toLowerCase() === card.employeeId.toLowerCase(),
        );
        const next = exists ? prev : [...prev, card.employeeId];
        writeDismissedIds(DISMISSED_TEAM_IND_STORAGE_KEY, viewScopeKey, next);
        return next;
      });
      setIndividualOverrides((prev) => {
        if (!prev[card.id]) return prev;
        const next = { ...prev };
        delete next[card.id];
        return next;
      });
      setIndSaveFeedback((prev) => {
        if (!prev[card.id]) return prev;
        const next = { ...prev };
        delete next[card.id];
        return next;
      });
      setConfirmDeleteIndId(null);
      if (editingIndividualId === card.id) {
        setEditingIndividualId(null);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to delete action plan';
      setIndDeleteError((prev) => ({
        ...prev,
        [card.employeeId]: msg,
      }));
    } finally {
      setDeletingIndId(null);
    }
  };

  const restoreAllIndividual = () => {
    setDismissedIndIds([]);
    writeDismissedIds(DISMISSED_TEAM_IND_STORAGE_KEY, viewScopeKey, []);
    setIndDeleteError({});
    setConfirmDeleteIndId(null);
  };

  const startEditTeam = (card: TeamLevelActionPlanCard) => {
    setEditingTeamId(card.id);
    setDraftTeamTitle(card.title);
    setDraftTeamTargetKpi(card.targetKpi);
    setDraftTeamScope(card.scopeDescription);
    setDraftTeamOwner(card.owner);
    setDraftTeamStatus(card.status);
    setDraftTeamDueDate(card.dueDate ?? '');
    setDraftTeamImpact(card.expectedTeamImpact);
  };

  const saveEditTeam = async (card: TeamLevelActionPlanCard) => {
    const updated: TeamLevelActionPlanCard = {
      ...card,
      title: draftTeamTitle.trim() || card.title,
      targetKpi: draftTeamTargetKpi.trim() || card.targetKpi,
      scopeDescription: draftTeamScope.trim() || card.scopeDescription,
      owner: draftTeamOwner.trim() || card.owner,
      status: draftTeamStatus,
      dueDate: draftTeamDueDate.trim() || null,
      expectedTeamImpact: draftTeamImpact.trim() || card.expectedTeamImpact,
      isDeleted: false,
    };
    setTeamCardOverrides((prev) => ({ ...prev, [card.id]: updated }));
    setDeletedTeamCardIds((prev) => prev.filter((id) => id !== card.id));
    setEditingTeamId(null);
    setAiStateByTarget((prev) => {
      if (!prev[`team:${card.id}`]) return prev;
      const next = { ...prev };
      delete next[`team:${card.id}`];
      return next;
    });
    if (onSaveTeamAction) {
      try {
        await onSaveTeamAction(updated);
        setTeamSaveFeedback((prev) => ({
          ...prev,
          [card.id]: { type: 'success', message: 'Saved team action' },
        }));
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Server sync failed';
        setTeamSaveFeedback((prev) => ({
          ...prev,
          [card.id]: { type: 'error', message: `Saved locally (${msg})` },
        }));
      }
    }
  };

  const handleAddTeamAction = async () => {
    if (!newTeamTitle.trim()) return;
    const created: TeamLevelActionPlanCard = {
      id: `team-act-custom-${Date.now()}`,
      title: newTeamTitle.trim(),
      targetKpi: newTeamTargetKpi.trim() || `${activeExplorerKpi?.label ?? 'Team KPI'}`,
      scopeDescription:
        newTeamScope.trim() || `All ${data.summary.headcount} ${data.teamDisplayName}`,
      owner: newTeamOwner.trim() || `${data.canonicalTeam} Team Leader`,
      expectedTeamImpact: newTeamImpact.trim() || '+1.0% team score lift',
      status: newTeamStatus,
      dueDate: newTeamDueDate.trim() || null,
      isDeleted: false,
    };
    setAddedTeamCards((prev) => [created, ...prev]);
    setDeletedTeamCardIds((prev) => prev.filter((id) => id !== created.id));
    setNewTeamTitle('');
    setNewTeamTargetKpi('');
    setNewTeamScope(`All ${data.summary.headcount} ${data.teamDisplayName}`);
    setNewTeamStatus('Open');
    setNewTeamDueDate('');
    setIsAddingTeamAction(false);
    setAiStateByTarget((prev) => {
      if (!prev['new-team']) return prev;
      const next = { ...prev };
      delete next['new-team'];
      return next;
    });
    if (onSaveTeamAction) {
      try {
        await onSaveTeamAction(created);
        setTeamSaveFeedback((prev) => ({
          ...prev,
          [created.id]: { type: 'success', message: 'Saved team action' },
        }));
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Server sync failed';
        setTeamSaveFeedback((prev) => ({
          ...prev,
          [created.id]: { type: 'error', message: `Saved locally (${msg})` },
        }));
      }
    }
  };

  const confirmDeleteTeamAction = async (card: TeamLevelActionPlanCard) => {
    setDeletingTeamId(card.id);
    setTeamDeleteError((prev) => {
      if (!prev[card.id]) return prev;
      const next = { ...prev };
      delete next[card.id];
      return next;
    });
    try {
      if (onDeleteTeamAction) {
        await onDeleteTeamAction(card);
      }
      setDeletedTeamCardIds((prev) => (prev.includes(card.id) ? prev : [...prev, card.id]));
      setAddedTeamCards((prev) => prev.filter((c) => c.id !== card.id));
      setTeamCardOverrides((prev) => ({
        ...prev,
        [card.id]: { ...card, isDeleted: true },
      }));
      setTeamSaveFeedback((prev) => {
        if (!prev[card.id]) return prev;
        const next = { ...prev };
        delete next[card.id];
        return next;
      });
      setConfirmDeleteTeamId(null);
      if (editingTeamId === card.id) {
        setEditingTeamId(null);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to delete team action';
      setTeamDeleteError((prev) => ({
        ...prev,
        [card.id]: msg,
      }));
    } finally {
      setDeletingTeamId(null);
    }
  };

  const restoreBuiltInTeamActions = async () => {
    if (deletedBuiltInIds.length === 0) return;
    setRestoringTeam(true);
    setTeamRestoreError(null);
    try {
      if (onRestoreTeamActions) {
        await onRestoreTeamActions(deletedBuiltInIds);
      }
      setDeletedTeamCardIds((prev) =>
        prev.filter((id) => !deletedBuiltInIds.includes(id)),
      );
      setTeamCardOverrides((prev) => {
        const next = { ...prev };
        for (const id of deletedBuiltInIds) {
          if (next[id]) {
            next[id] = { ...next[id], isDeleted: false };
          }
        }
        return next;
      });
      setTeamDeleteError({});
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to restore default actions';
      setTeamRestoreError(msg);
    } finally {
      setRestoringTeam(false);
    }
  };

  const formatDraftActionText = (
    payload: AiCorrectiveActionSuggestionPayload,
  ): string => {
    const draft = payload.draft;
    if (!draft) return '';
    const steps = draft.recommended_steps.map((s) => s.trim()).filter(Boolean);
    if (steps.length > 0) {
      return `${draft.title}: ${steps.join(' ')}`;
    }
    return draft.title;
  };

  const applyIndividualAiDraft = useCallback(
    (card: IndividualActionPlanCard, payload: AiCorrectiveActionSuggestionPayload) => {
      if (!payload.draft) return;
      setEditingIndividualId(card.id);
      setDraftActionText(formatDraftActionText(payload));
      setDraftMainIssue(payload.draft.measured_issue || card.mainIssue);
      setDraftOwner((prev) =>
        editingIndividualId === card.id && prev.trim() !== card.owner.trim()
          ? prev
          : payload.draft?.responsible_role || card.owner,
      );
      setDraftImpact((prev) => (editingIndividualId === card.id ? prev : card.expectedImpact));
      setDraftFollowUpLabel(payload.draft.recommended_follow_up || card.followUpLabel || '');
      setDraftObservationStatus(payload.draft.observation_status || card.observationStatus);
      setAiStateByTarget((prev) => ({
        ...prev,
        [`ind:${card.id}`]: {
          loading: false,
          payload,
          error: null,
          needsOverwriteConfirm: false,
          draftApplied: true,
        },
      }));
    },
    [editingIndividualId],
  );

  const applyIndividualEvidenceFallback = useCallback(
    (card: IndividualActionPlanCard, payload: AiCorrectiveActionSuggestionPayload) => {
      if (!payload.evidence_next_step) return;
      setEditingIndividualId(card.id);
      setDraftActionText(payload.evidence_next_step);
      setDraftMainIssue(payload.measured_facts?.[0] || card.mainIssue);
      setDraftOwner(payload.evidence_next_step_role || card.owner);
      setDraftImpact(card.expectedImpact);
      setDraftFollowUpLabel(payload.evidence_next_step_follow_up || card.followUpLabel || '');
      setDraftObservationStatus(card.observationStatus);
    },
    [],
  );

  const applyTeamAiDraft = useCallback(
    (card: TeamLevelActionPlanCard, payload: AiCorrectiveActionSuggestionPayload) => {
      if (!payload.draft) return;
      setEditingTeamId(card.id);
      setDraftTeamTitle(payload.draft.title || card.title);
      setDraftTeamTargetKpi(payload.draft.focus_kpi_name || card.targetKpi);
      setDraftTeamScope(payload.draft.measured_issue || card.scopeDescription);
      if (editingTeamId !== card.id) {
        setDraftTeamOwner(payload.draft.responsible_role || card.owner);
        setDraftTeamStatus(card.status);
        setDraftTeamDueDate(card.dueDate ?? '');
        setDraftTeamImpact(card.expectedTeamImpact);
      }
      setAiStateByTarget((prev) => ({
        ...prev,
        [`team:${card.id}`]: {
          loading: false,
          payload,
          error: null,
          needsOverwriteConfirm: false,
          draftApplied: true,
        },
      }));
    },
    [editingTeamId],
  );

  const applyTeamEvidenceFallback = useCallback(
    (card: TeamLevelActionPlanCard, payload: AiCorrectiveActionSuggestionPayload) => {
      if (!payload.evidence_next_step) return;
      setEditingTeamId(card.id);
      setDraftTeamTitle(payload.evidence_next_step);
      setDraftTeamTargetKpi(card.targetKpi);
      setDraftTeamScope(payload.cohort_coverage_label || card.scopeDescription);
      setDraftTeamOwner(payload.evidence_next_step_role || card.owner);
      setDraftTeamStatus(card.status);
      setDraftTeamDueDate(card.dueDate ?? '');
      setDraftTeamImpact(card.expectedTeamImpact);
    },
    [],
  );

  const applyNewTeamAiDraft = useCallback(
    (payload: AiCorrectiveActionSuggestionPayload) => {
      if (!payload.draft) return;
      setIsAddingTeamAction(true);
      setNewTeamTitle(formatDraftActionText(payload));
      setNewTeamTargetKpi(payload.draft.focus_kpi_name || '');
      if (payload.draft.measured_issue) {
        setNewTeamScope(payload.draft.measured_issue);
      }
      setAiStateByTarget((prev) => ({
        ...prev,
        'new-team': {
          loading: false,
          payload,
          error: null,
          needsOverwriteConfirm: false,
          draftApplied: true,
        },
      }));
    },
    [],
  );

  const runAiRequest = useCallback(
    async (
      targetKey: string,
      scopeKey: string,
      requestFn: (signal: AbortSignal) => Promise<AiCorrectiveActionSuggestionPayload>,
      hasUnsavedEdits: boolean,
      onAutoApply: (payload: AiCorrectiveActionSuggestionPayload) => void,
    ) => {
      if (inFlightScopesRef.current[targetKey] === scopeKey) {
        return;
      }
      abortControllersRef.current[targetKey]?.abort();
      const controller = new AbortController();
      abortControllersRef.current[targetKey] = controller;
      inFlightScopesRef.current[targetKey] = scopeKey;

      setAiStateByTarget((prev) => ({
        ...prev,
        [targetKey]: {
          loading: true,
          scopeKey,
          payload: null,
          error: null,
          needsOverwriteConfirm: false,
          draftApplied: false,
        },
      }));

      try {
        const payload = await requestFn(controller.signal);
        if (controller.signal.aborted || abortControllersRef.current[targetKey] !== controller) {
          return;
        }
        if (payload.outcome === 'suggested' && payload.draft && !hasUnsavedEdits) {
          onAutoApply(payload);
          return;
        }
        setAiStateByTarget((prev) => ({
          ...prev,
          [targetKey]: {
            loading: false,
            scopeKey,
            payload,
            error: null,
            needsOverwriteConfirm: Boolean(
              payload.outcome === 'suggested' && payload.draft && hasUnsavedEdits,
            ),
            draftApplied: false,
          },
        }));
      } catch (err) {
        if (controller.signal.aborted || abortControllersRef.current[targetKey] !== controller) {
          return;
        }
        const aiError: ActionPlanAiError =
          err instanceof ApiError
            ? { message: err.message, status: err.status }
            : {
                message:
                  err instanceof Error
                    ? err.message
                    : 'Could not generate AI recommendation.',
              };
        setAiStateByTarget((prev) => ({
          ...prev,
          [targetKey]: {
            loading: false,
            scopeKey,
            payload: null,
            error: aiError,
            needsOverwriteConfirm: false,
            draftApplied: false,
          },
        }));
      } finally {
        if (abortControllersRef.current[targetKey] === controller) {
          delete abortControllersRef.current[targetKey];
          delete inFlightScopesRef.current[targetKey];
        }
      }
    },
    [],
  );

  const triggerIndividualAi = useCallback(
    (card: IndividualActionPlanCard) => {
      const targetKey = `ind:${card.id}`;
      const scopeTeam = card.recordTeam || data.canonicalTeam;
      const scopeKey = buildAiScopeKey(scopeTeam, data.periodKey, card.employeeId, card.linkedKpiKey);
      const isEditingThis = editingIndividualId === card.id;
      const hasUnsaved =
        isEditingThis &&
        (draftActionText.trim() !== card.actionText.trim() ||
          draftMainIssue.trim() !== card.mainIssue.trim() ||
          draftOwner.trim() !== card.owner.trim() ||
          draftImpact.trim() !== card.expectedImpact.trim());
      void runAiRequest(
        targetKey,
        scopeKey,
        (signal) =>
          requestActionPlanAiSuggestion({
            team: scopeTeam,
            month: activeMonthName,
            year: activeYearNum,
            performanceLevel: card.performanceLevel,
            employeeId: card.employeeId,
            focusKpiKey: card.linkedKpiKey,
            signal,
          }),
        hasUnsaved,
        (payload) => applyIndividualAiDraft(card, payload),
      );
    },
    [
      activeMonthName,
      activeYearNum,
      applyIndividualAiDraft,
      data.canonicalTeam,
      draftActionText,
      draftImpact,
      draftMainIssue,
      draftOwner,
      editingIndividualId,
      runAiRequest,
    ],
  );

  const triggerTeamAi = useCallback(
    (card: TeamLevelActionPlanCard) => {
      const targetKey = `team:${card.id}`;
      const focusKpiKey = resolveTeamCardFocusKpiKey(card, data.kpis, activeExplorerKpi?.kpiKey);
      const scopeKey = buildAiScopeKey(data.canonicalTeam, data.periodKey, null, focusKpiKey);
      const isEditingThis = editingTeamId === card.id;
      const hasUnsaved =
        isEditingThis &&
        (draftTeamTitle.trim() !== card.title.trim() ||
          draftTeamTargetKpi.trim() !== card.targetKpi.trim() ||
          draftTeamScope.trim() !== card.scopeDescription.trim() ||
          draftTeamOwner.trim() !== card.owner.trim() ||
          draftTeamImpact.trim() !== card.expectedTeamImpact.trim() ||
          draftTeamStatus !== card.status ||
          draftTeamDueDate.trim() !== (card.dueDate ?? '').trim());
      void runAiRequest(
        targetKey,
        scopeKey,
        (signal) =>
          requestActionPlanAiSuggestion({
            team: data.canonicalTeam,
            month: activeMonthName,
            year: activeYearNum,
            employeeId: null,
            focusKpiKey,
            signal,
          }),
        hasUnsaved,
        (payload) => applyTeamAiDraft(card, payload),
      );
    },
    [
      activeExplorerKpi?.kpiKey,
      activeMonthName,
      activeYearNum,
      applyTeamAiDraft,
      data.canonicalTeam,
      data.kpis,
      draftTeamDueDate,
      draftTeamImpact,
      draftTeamOwner,
      draftTeamScope,
      draftTeamStatus,
      draftTeamTargetKpi,
      draftTeamTitle,
      editingTeamId,
      runAiRequest,
    ],
  );

  const triggerNewTeamAi = useCallback(() => {
    const focusKpiKey =
      activeExplorerKpi && activeExplorerKpi.verdictBadge !== 'Target Met'
        ? activeExplorerKpi.kpiKey
        : null;
    const scopeKey = buildAiScopeKey(data.canonicalTeam, data.periodKey, null, focusKpiKey);
    const hasUnsaved =
      newTeamTitle.trim().length > 0 || newTeamTargetKpi.trim().length > 0;
    void runAiRequest(
      'new-team',
      scopeKey,
      (signal) =>
        requestActionPlanAiSuggestion({
          team: data.canonicalTeam,
          month: activeMonthName,
          year: activeYearNum,
          employeeId: null,
          focusKpiKey,
          signal,
        }),
      hasUnsaved,
      (payload) => applyNewTeamAiDraft(payload),
    );
  }, [
    activeExplorerKpi,
    activeMonthName,
    activeYearNum,
    applyNewTeamAiDraft,
    data.canonicalTeam,
    newTeamTargetKpi,
    newTeamTitle,
    runAiRequest,
  ]);

  const discardAiTarget = useCallback(
    (targetKey: string, onRevertApplied?: () => void) => {
      abortControllersRef.current[targetKey]?.abort();
      delete abortControllersRef.current[targetKey];
      delete inFlightScopesRef.current[targetKey];
      const wasApplied = aiStateByTarget[targetKey]?.draftApplied;
      setAiStateByTarget((prev) => {
        const next = { ...prev };
        delete next[targetKey];
        return next;
      });
      if (wasApplied && onRevertApplied) {
        onRevertApplied();
      }
    },
    [aiStateByTarget],
  );

  return (
    <div
      data-testid="team-deep-dive-page"
      className="mx-auto max-w-7xl space-y-7 px-4 py-6 sm:px-6 lg:px-8"
    >
      {/* ================================================================== */}
      {/* 1. HEADER WITH BREADCRUMB                                          */}
      {/* ================================================================== */}
      <header
        aria-label="Team Deep Dive Header"
        className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
      >
        {/* Top Row: Breadcrumb + Toolbar */}
        <div className="flex min-w-0 flex-col gap-3 border-b border-slate-100 pb-4">
          <nav
            aria-label="Breadcrumb"
            data-testid="team-deep-dive-breadcrumb"
            className="flex flex-wrap items-center gap-1.5 text-xs font-semibold text-slate-500"
          >
            <button
              type="button"
              data-testid="breadcrumb-overview"
              onClick={onNavigateToOverview}
              className="rounded-lg px-2 py-1 text-slate-600 transition-colors hover:bg-slate-100 hover:text-blue-600"
            >
              Overview
            </button>
            <ChevronRight className="size-3.5 text-slate-400" />
            <button
              type="button"
              data-testid={isCallCenter ? 'breadcrumb-call-center' : 'breadcrumb-function'}
              onClick={onNavigateToCallCenter}
              className="rounded-lg px-2 py-1 text-slate-600 transition-colors hover:bg-slate-100 hover:text-blue-600"
            >
              {data.functionName}
            </button>
            <ChevronRight className="size-3.5 text-slate-400" />
            <span className="rounded-lg bg-blue-50 px-2.5 py-1 font-bold text-blue-700">
              {data.teamDisplayName}
            </span>
          </nav>

          <div className="flex w-full min-w-0 max-w-full flex-wrap items-center gap-2">
            <button
              type="button"
              data-testid="back-to-call-center-deep-dive"
              onClick={onNavigateToCallCenter}
              className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 text-xs font-bold text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700"
            >
              <ArrowLeft className="size-3.5" />
              <span>Back to {data.functionName} Deep Dive</span>
            </button>

            {onSwitchTeam && siblings.length > 1 && (
              <div
                role="tablist"
                aria-label={`Switch ${data.functionName} team`}
                className="inline-flex h-9 items-center rounded-xl border border-slate-200 bg-slate-100 p-0.5"
              >
                {siblings.map((sibling) => (
                  <button
                    key={sibling.slug}
                    type="button"
                    role="tab"
                    aria-selected={data.teamSlug === sibling.slug}
                    data-testid={`switch-team-${sibling.slug}`}
                    onClick={() => onSwitchTeam(sibling.slug)}
                    className={`h-full rounded-lg px-3 text-xs font-semibold transition-all ${
                      data.teamSlug === sibling.slug
                        ? 'bg-white font-bold text-blue-600 shadow-2xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {sibling.label}
                  </button>
                ))}
              </div>
            )}

            {toolbar}
          </div>
        </div>

        {/* Team Hero Summary: Name, Score, Full-Word Grade, Gap, Diagnosis */}
        <div className="mt-5 space-y-4">
          {/* Identity & Diagnosis */}
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-2.5 py-0.5 text-xs font-bold tracking-wider text-white uppercase">
                Team Deep Dive
              </span>
              <span className="text-xs font-semibold text-slate-500">
                {data.regionName} · {data.monthLabel}
              </span>
              <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-semibold text-slate-700">
                <Users className="size-3.5 text-slate-400" />
                {data.summary.headcount} measured {peopleLabel} ({data.summary.averageOrBelowCount} Average or below)
              </span>
            </div>

            <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              {data.teamDisplayName}
            </h1>

            <p
              data-testid="team-header-diagnosis"
              className="max-w-4xl text-sm leading-relaxed text-slate-600"
            >
              {data.summary.diagnosis}
            </p>
          </div>

          {/* Performance Summary Grid: Score Card + 6-Month Trend */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-12 items-stretch">
            {/* Score Card */}
            <div
              className={`flex flex-col justify-between rounded-2xl border border-slate-200/80 bg-slate-50/70 p-4 sm:p-5 ${
                data.scoreTrend ? 'lg:col-span-5' : 'lg:col-span-12 max-w-xl'
              }`}
            >
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  {data.summary.scoreLabel ?? 'Team Score'}
                </div>
                <div className="mt-1 flex flex-wrap items-baseline gap-3">
                  <span
                    data-testid="team-deep-dive-score"
                    className={`text-4xl font-extrabold tracking-tight sm:text-5xl ${summaryGradeStyle.scoreText}`}
                  >
                    {data.summary.scoreLabel === 'Unmeasured team score' ? '—' : `${data.summary.score.toFixed(1)}%`}
                  </span>
                  {data.summary.scoreLabel !== 'Unmeasured team score' && (
                    <FullWordGradeBadge
                      grade={data.summary.grade}
                      gradeFullLabel={data.summary.gradeFullLabel}
                      size="lg"
                    />
                  )}
                </div>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-200/60 pt-3 text-xs">
                {data.summary.scoreLabel !== 'Unmeasured team score' && (
                  <span className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1 font-bold text-rose-700">
                    <Target className="size-3.5" />
                    {data.summary.gap.toFixed(1)}% gap to 100% target
                  </span>
                )}

                {showChange && measuredChange !== null && (
                  <span
                    className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 font-bold ${
                      isPositiveChange
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                        : measuredChange < 0
                        ? 'border-rose-200 bg-rose-50 text-rose-700'
                        : 'border-slate-200 bg-white text-slate-700'
                    }`}
                  >
                    {isPositiveChange ? (
                      <ArrowUpRight className="size-3.5" />
                    ) : measuredChange < 0 ? (
                      <ArrowDownRight className="size-3.5" />
                    ) : null}
                    {isPositiveChange ? `+${measuredChange.toFixed(1)}%` : `${measuredChange.toFixed(1)}%`} vs {comparedMonth}
                  </span>
                )}
                {!showChange && (
                  <span
                    title={`No measured score for ${comparedMonth || 'the previous month'}`}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 font-bold text-slate-400"
                  >
                    — No previous-month data
                  </span>
                )}
                {data.scoreTrend?.basisNote && (
                  <span
                    data-testid="team-score-basis-note"
                    className="w-full text-xs font-semibold leading-snug text-amber-800"
                  >
                    {data.scoreTrend.basisNote}
                  </span>
                )}
              </div>
            </div>

            {/* 6-Month Team Score Trend */}
            {data.scoreTrend && (
              <section
                aria-label={`${data.teamDisplayName} score trend`}
                data-testid="team-score-trend"
                className="flex flex-col justify-between rounded-2xl border border-slate-200/80 bg-white p-4 shadow-2xs lg:col-span-7"
              >
                <div>
                  <div className="flex items-center justify-between pb-1">
                    <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                      6-month team score
                    </div>
                    <span className="text-xs font-medium text-slate-400">
                      Target: 100%
                    </span>
                  </div>
                  <ScoreTrendChart
                    data={data.scoreTrend.points.map((point) => ({
                      month: point.month,
                      score: point.score,
                      periodKey: point.periodKey,
                      selected: point.selected,
                      basisDetail: point.basisDetail,
                    }))}
                    targetScore={100}
                    targetLabel="100% target"
                    targetLabelPosition="insideTopRight"
                    height={140}
                    animate={false}
                    caption={`${data.teamDisplayName} ${data.regionName} team score, selected month and five preceding months`}
                  />
                </div>
                {data.scoreTrend.points.some((point) => point.basisDetail) && (
                  <p className="mt-2 border-t border-slate-100 pt-2 text-xs leading-relaxed text-slate-500">
                    Hover over a month to see what is known about its scoring basis. Team scores use current pooling rules.
                  </p>
                )}
              </section>
            )}
          </div>
        </div>
      </header>

      {/* ================================================================== */}
      {/* 2. KEY TEAM KPIS — Compact Single-Row Carousel (Worst to Best)     */}
      {/* ================================================================== */}
      <section id="presentation-section-team-kpis" data-section-label="KPIs" aria-labelledby="key-team-kpis-heading" data-testid="team-kpis-section" className="scroll-mt-24 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2.5 px-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex size-7 items-center justify-center rounded-lg border border-blue-200/80 bg-blue-50 text-blue-600">
              <Gauge className="size-3.5" aria-hidden />
            </span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 id="key-team-kpis-heading" className="text-sm font-bold tracking-tight text-slate-900 sm:text-base">
                  Key Team KPIs
                </h2>
                <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs font-semibold text-slate-500">
                  {enrichedKpis.length} {enrichedKpis.length === 1 ? 'measure' : 'measures'} · sorted worst to best
                </span>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {biggestGapKpi && (
              <div
                data-testid="team-biggest-gap-summary-pill"
                className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200/90 bg-rose-50/80 px-2.5 py-1 text-xs font-semibold text-rose-900 shadow-2xs"
              >
                <Flame className="size-3.5 shrink-0 text-rose-600" aria-hidden />
                <span>
                  Biggest Gap Driver:{' '}
                  <strong className="font-extrabold text-rose-700">
                    {biggestGapKpi.shortLabel}
                  </strong>{' '}
                  (−{biggestGapKpi.pointsLost.toFixed(1)} pts ·{' '}
                  {biggestGapKpi.contributionPct.toFixed(1)}% of{' '}
                  {Math.round(biggestGapKpi.weightPct)}% weight)
                </span>
              </div>
            )}

            {enrichedKpis.length > 0 && (
              <div
                data-testid="team-kpi-carousel-controls"
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200/90 bg-white px-2 py-1 shadow-2xs"
              >
                <span className="px-1 text-xs font-bold text-slate-500 tabular-nums">
                  {safeCarouselStart + 1}–
                  {Math.min(enrichedKpis.length, safeCarouselStart + TEAM_KPI_CARDS_PER_ROW)} of{' '}
                  {enrichedKpis.length}
                </span>
                <button
                  type="button"
                  data-testid="team-kpi-carousel-prev"
                  aria-label="Previous team KPI cards"
                  disabled={safeCarouselStart === 0}
                  onClick={() => setCarouselStart((prev) => Math.max(0, prev - 1))}
                  className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-35"
                >
                  <ChevronLeft className="size-3.5" aria-hidden />
                </button>
                <button
                  type="button"
                  data-testid="team-kpi-carousel-next"
                  aria-label="Next team KPI cards"
                  disabled={safeCarouselStart >= maxCarouselStart}
                  onClick={() =>
                    setCarouselStart((prev) => Math.min(maxCarouselStart, prev + 1))
                  }
                  className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-35"
                >
                  <ChevronRight className="size-3.5" aria-hidden />
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {visibleKpis.map((kpi) => (
            <SelectableKpiCard
              key={kpi.kpiKey}
              selected={activeExplorerKpi?.kpiKey === kpi.kpiKey}
              status={kpi.statusBadge}
              title={kpi.label}
              betterDirection={kpi.betterDirection}
              actual={kpi.actualFormatted}
              target={kpi.targetFormatted}
              achievementPct={kpi.cappedPct}
              movement={
                <KpiTrendMovement
                  label={kpi.movementFormatted}
                  betterDirection={kpi.betterDirection}
                />
              }
              biggestGap={kpi.isBiggestGap}
              weightPct={kpi.weightPct}
              contributionPct={kpi.contributionPct}
              pointsLost={kpi.pointsLost}
              testId={`team-kpi-card-${kpi.kpiKey}`}
              onSelect={() => handleSelectTeamKpi(kpi.kpiKey)}
            />
          ))}
        </div>
      </section>

      {/* ================================================================== */}
      {/* 3. KPI TREND EXPLORER (360-Profile Interactive 6-Month Line Chart) */}
      {/* ================================================================== */}
      {activeExplorerKpi && (
        <section
          id="presentation-section-team-trend"
          data-section-label="Trend"
          aria-labelledby="role-trend-heading"
          data-testid="kpi-trend-explorer"
          className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
        >
          {/* Reused 360-Profile Interactive 6-Month Line Chart (includes single KPI switcher) */}
          <ProfileKpiSixMonthTrend
            kpis={profileTrendKpis}
            selectedId={activeExplorerKpi.kpiKey}
            onSelectKpi={handleSelectTeamKpi}
          />

          {/* Diagnostic Answer: Is the target unrealistic or is execution the issue? */}
          <div
            data-testid="trend-explorer-diagnosis"
            className="mt-5 flex flex-wrap items-start justify-between gap-3 rounded-xl border border-blue-200/80 bg-blue-50/50 p-4"
          >
            <div className="flex items-start gap-3">
              <Sparkles className="mt-0.5 size-4 shrink-0 text-blue-600" />
              <div className="text-xs leading-relaxed text-slate-800 sm:text-sm">
                <span className="font-bold text-blue-950">
                  Target vs. Execution Diagnosis:{' '}
                </span>
                {activeExplorerKpi.explorerDiagnosis}
              </div>
            </div>

            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <span
                className={`rounded-full border px-2.5 py-0.5 text-xs font-bold ${
                  activeExplorerKpi.verdictBadge === 'Target Met'
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : activeExplorerKpi.verdictBadge === 'Execution Issue'
                    ? 'border-amber-200 bg-amber-50 text-amber-800'
                    : 'border-rose-200 bg-rose-50 text-rose-700'
                }`}
              >
                Verdict: {activeExplorerKpi.verdictBadge}
              </span>
              <span className="rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-xs font-semibold text-slate-600">
                {activeExplorerKpi.agentsMeetingTarget} of {activeExplorerKpi.totalAgents} {peopleLabel} met target
              </span>
            </div>
          </div>
        </section>
      )}

      {/* ================================================================== */}
      {/* 4. AGENTS — AVERAGE AND BELOW (Grade C or Lower, Full Words Only)  */}
      {/* ================================================================== */}
      <section
        id="presentation-section-team-agents"
        data-section-label="Agents"
        aria-labelledby="agents-average-below-heading"
        className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-4">
          <div>
            <span className="text-xs font-semibold tracking-wider text-amber-700 uppercase">
              Focus Cohort (Score &lt; 90%)
            </span>
            <h2
              id="agents-average-below-heading"
              className="mt-0.5 text-lg font-bold text-slate-900"
            >
              Agents — Average and Below
            </h2>
          </div>

          <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-bold text-amber-800">
            {data.agentsAverageOrBelow.length} of {data.summary.headcount} agents require action
          </span>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table
            data-testid="agents-average-below-table"
            className="w-full border-collapse text-left text-sm"
          >
            <thead>
              <tr className="border-b border-slate-200 text-xs font-semibold tracking-wider text-slate-500 uppercase">
                <th className="py-3 pr-4">Agent</th>
                <th className="px-4 py-3 text-right">Score</th>
                {data.kpis.slice(0, 4).map((kpi) => (
                  <th key={kpi.kpiKey} className="px-4 py-3 text-right">
                    {kpi.shortLabel}
                    <span className="block text-xs font-normal text-slate-400 normal-case">
                      Target: {kpi.targetFormatted}
                    </span>
                  </th>
                ))}
                <th className="py-3 pl-4 text-center">Grade</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {visibleAgents.length === 0 ? (
                <tr>
                  <td
                    colSpan={2 + Math.min(4, data.kpis.length) + 1}
                    className="py-8 text-center text-xs text-slate-500"
                  >
                    No agents in this team are Average or below for this month.
                  </td>
                </tr>
              ) : (
                visibleAgents.map((agent) => {
                  const gradeStyle = GRADE_STYLES[agent.grade];
                  return (
                    <tr
                      key={agent.employeeId}
                      data-testid={`low-agent-row-${agent.employeeId}`}
                      className="transition-colors hover:bg-slate-50/80"
                    >
                      <td className="py-3.5 pr-4">
                        <div className="font-bold text-slate-900">{agent.agentName}</div>
                        <div className="mt-0.5 text-xs text-slate-500">{agent.mainIssue}</div>
                      </td>

                      <td className="px-4 py-3.5 text-right">
                        <div className={`text-base font-extrabold ${gradeStyle.scoreText}`}>
                          {agent.score.toFixed(1)}%
                        </div>
                        {agent.changeVsPrev !== null ? (
                          <div
                            className={`text-xs font-semibold ${
                              agent.changeVsPrev >= 0 ? 'text-emerald-600' : 'text-rose-600'
                            }`}
                          >
                            {agent.changeVsPrev >= 0
                              ? `+${agent.changeVsPrev.toFixed(1)}%`
                              : `${agent.changeVsPrev.toFixed(1)}%`}{' '}
                            vs {data.previousMonthLabel}
                          </div>
                        ) : (
                          <div
                            className="text-xs font-semibold text-slate-400"
                            title="No previous-month data"
                          >
                            —
                          </div>
                        )}
                      </td>

                      {agent.kpiCells.map((cell) => (
                        <td key={cell.kpiKey} className="px-4 py-3.5 text-right">
                          <span
                            className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-bold ${
                              cell.metTarget
                                ? 'bg-emerald-50 text-emerald-700'
                                : cell.achievementPct < 75
                                ? 'bg-rose-50 text-rose-700'
                                : 'bg-amber-50 text-amber-800'
                            }`}
                          >
                            {cell.actualFormatted}
                          </span>
                        </td>
                      ))}

                      <td className="py-3.5 pl-4 text-center">
                        <FullWordGradeBadge
                          grade={agent.grade}
                          gradeFullLabel={agent.gradeFullLabel}
                          size="sm"
                        />
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
          {agentPages.pageCount > 1 && (
            <nav
              data-testid="agents-average-below-pager"
              aria-label="Agent pages"
              className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3"
            >
              <p className="text-xs font-semibold text-slate-500 tabular-nums" aria-live="polite">
                Showing {agentPages.rangeStart}–{agentPages.rangeEnd} of {data.agentsAverageOrBelow.length} agents
              </p>
              <div className="inline-flex items-center gap-1.5">
                <button
                  type="button"
                  data-testid="agents-average-below-prev"
                  aria-label="Previous agents"
                  disabled={agentPages.page === 0}
                  onClick={() =>
                    setAgentPageState({
                      listKey: agentListKey,
                      page: Math.max(0, agentPages.page - 1),
                    })
                  }
                  className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-bold text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ChevronLeft className="size-3.5" aria-hidden />
                  Previous
                </button>
                <span className="px-1 text-xs font-bold text-slate-500 tabular-nums">
                  {agentPages.page + 1} / {agentPages.pageCount}
                </span>
                <button
                  type="button"
                  data-testid="agents-average-below-next"
                  aria-label="Next agents"
                  disabled={agentPages.page >= agentPages.pageCount - 1}
                  onClick={() =>
                    setAgentPageState({
                      listKey: agentListKey,
                      page: Math.min(agentPages.pageCount - 1, agentPages.page + 1),
                    })
                  }
                  className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-bold text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Next
                  <ChevronRight className="size-3.5" aria-hidden />
                </button>
              </div>
            </nav>
          )}
        </div>
      </section>

      {/* ================================================================== */}
      {/* 5. INDIVIDUAL ACTION PLAN (Card Layout, Editable)                  */}
      {/* ================================================================== */}
      {(showActionSection(displayedIndividualCards.length, presentationMode) ||
        (!presentationMode && dismissedIndIds.length > 0)) && (
      <section
        id="presentation-section-team-coaching"
        data-section-label="Coaching"
        aria-labelledby="individual-action-plan-heading"
        className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-4">
          <div>
            <span className="text-xs font-semibold tracking-wider text-blue-600 uppercase">
              1-on-1 Coaching & Remediation
            </span>
            <h2
              id="individual-action-plan-heading"
              className="mt-0.5 text-lg font-bold text-slate-900"
            >
              Individual Action Plan
            </h2>
          </div>
          {showPresentationControl(presentationMode) && (
            <div className="flex flex-wrap items-center gap-2">
              {dismissedIndIds.length > 0 && (
                <button
                  type="button"
                  onClick={restoreAllIndividual}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:border-blue-300 hover:text-blue-700"
                >
                  <RotateCcw className="size-3.5" aria-hidden="true" />
                  <span>Restore {dismissedIndIds.length} dismissed</span>
                </button>
              )}
              <p className="text-xs font-medium text-slate-500">
                One action card per agent shown above · Click &ldquo;Edit&rdquo; on any card to customize & save
              </p>
            </div>
          )}
        </div>

        {displayedIndividualCards.length === 0 ? (
          <div className="mt-5 rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-6 text-center">
            <p className="text-sm font-medium text-slate-600">
              No individual action plans for this period.
            </p>
            {showPresentationControl(presentationMode) && dismissedIndIds.length > 0 && (
              <button
                type="button"
                onClick={restoreAllIndividual}
                className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:border-blue-300 hover:text-blue-700"
              >
                <RotateCcw className="size-3.5" aria-hidden="true" />
                <span>Restore dismissed suggestions</span>
              </button>
            )}
          </div>
        ) : (
        <div className="mt-5 grid grid-cols-1 items-start gap-4 md:grid-cols-2">
          {displayedIndividualCards.map((card) => {
            const isEditing = showPresentationControl(presentationMode) && editingIndividualId === card.id;
            const isConfirmingDelete =
              showPresentationControl(presentationMode) && confirmDeleteIndId === card.employeeId;
            const isDeleting = deletingIndId === card.employeeId;
            const deleteError = indDeleteError[card.employeeId];
            const gradeStyle = GRADE_STYLES[card.grade];
            const indAiTargetKey = `ind:${card.id}`;
            const indAiState = aiStateByTarget[indAiTargetKey];
            const indFeedback = indSaveFeedback[card.id];
            const isEvidenceOpen = Boolean(expandedEvidenceIds[card.id]);
            const evidencePanelId = `ind-evidence-panel-${card.id}`;
            const linkedEvidence = card.allKpiEvidence?.find(
              (item) => item.kpiKey === card.linkedKpiKey,
            );
            const changeLabel = formatScoreChangeLabel(
              card.changeVsPrev,
              card.previousPeriodLabel,
            );

            return (
              <article
                key={card.id}
                data-testid={`individual-action-card-${card.employeeId}`}
                className="flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-slate-50/50 p-5 transition-all hover:bg-white hover:shadow-xs"
              >
                <div>
                  {/* 1. Score and change */}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-base font-bold text-slate-900">
                        {card.agentName}
                      </h3>
                      <span className={`text-sm font-extrabold tabular-nums ${gradeStyle.scoreText}`}>
                        {card.score.toFixed(1)}%
                      </span>
                      <FullWordGradeBadge
                        grade={card.grade}
                        gradeFullLabel={card.gradeFullLabel}
                        size="sm"
                      />
                    </div>
                    <span
                      data-testid={`individual-score-change-${card.employeeId}`}
                      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold tabular-nums ${
                        card.changeVsPrev == null
                          ? 'border-slate-200 bg-white text-slate-600'
                          : card.changeVsPrev >= 0
                            ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                            : 'border-rose-200 bg-rose-50 text-rose-700'
                      }`}
                    >
                      {changeLabel}
                    </span>
                  </div>

                  {/* 2. Main issue */}
                  <div
                    data-testid={`individual-main-issue-${card.employeeId}`}
                    className="mt-3 rounded-xl border border-rose-200/70 bg-rose-50/50 px-3.5 py-2.5 text-xs text-slate-700"
                  >
                    <span className="font-bold text-rose-800">
                      <AlertTriangle className="mr-1 inline size-3.5 text-rose-600" aria-hidden="true" />
                      Main issue:{' '}
                    </span>
                    {card.mainIssue}
                  </div>

                  {indFeedback && !isEditing && (
                    <p
                      role="status"
                      className={`mt-2 text-xs font-medium ${
                        indFeedback.type === 'error' ? 'text-rose-700' : 'text-emerald-700'
                      }`}
                    >
                      {indFeedback.message}
                    </p>
                  )}

                  {/* 3. Next step (remains visible & editable during loading and after AI errors) */}
                  {isEditing ? (
                    <div className="mt-3 space-y-2.5 rounded-xl border border-blue-200 bg-white p-3">
                      <div>
                        <label className="block text-xs font-bold text-slate-600">
                          Main Issue
                        </label>
                        <input
                          type="text"
                          value={draftMainIssue}
                          onChange={(e) => setDraftMainIssue(e.target.value)}
                          className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-slate-600">
                          Corrective Action
                        </label>
                        <textarea
                          rows={2}
                          value={draftActionText}
                          onChange={(e) => setDraftActionText(e.target.value)}
                          className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                        />
                      </div>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        <div>
                          <label className="block text-xs font-bold text-slate-600">
                            Owner
                          </label>
                          <input
                            type="text"
                            value={draftOwner}
                            onChange={(e) => setDraftOwner(e.target.value)}
                            className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-bold text-slate-600">
                            Expected Impact
                          </label>
                          <input
                            type="text"
                            value={draftImpact}
                            onChange={(e) => setDraftImpact(e.target.value)}
                            className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                          />
                        </div>
                      </div>
                      <div className="flex justify-end gap-2 pt-1">
                        <button
                          type="button"
                          onClick={() => cancelEditIndividual(card)}
                          className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => saveEditIndividual(card)}
                          className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1 text-xs font-bold text-white hover:bg-blue-700"
                        >
                          <Check className="size-3.5" />
                          <span>Save Action</span>
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-3 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                          Next step
                        </span>
                        {card.isSavedToStore ? (
                          <span className="rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-xs font-medium text-emerald-700">
                            Saved
                          </span>
                        ) : (
                          <span className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-xs font-medium text-slate-600">
                            Suggested — not saved
                          </span>
                        )}
                      </div>
                      <p
                        data-testid={`individual-action-text-${card.employeeId}`}
                        className="text-xs font-medium leading-relaxed text-slate-800 sm:text-sm"
                      >
                        {card.actionText}
                      </p>
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 font-semibold text-slate-700">
                          <UserCheck className="size-3.5 text-blue-600" aria-hidden="true" />
                          <span>Role: {card.owner}</span>
                        </span>
                        {card.followUpLabel && (
                          <span className="inline-flex items-center rounded-lg border border-indigo-200 bg-indigo-50/70 px-2.5 py-1 font-medium text-indigo-800">
                            Follow-up: {card.followUpLabel}
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* AI Draft Banner (Hidden in Presentation Mode; stays separate so Next step stays visible) */}
                  {showPresentationControl(presentationMode) && (
                    <AiRecommendationBanner
                      inlineStatusHandled
                      loading={indAiState?.loading}
                      payload={indAiState?.payload}
                      error={indAiState?.error}
                      needsOverwriteConfirm={indAiState?.needsOverwriteConfirm}
                      draftApplied={indAiState?.draftApplied}
                      presentationMode={presentationMode}
                      onApplyDraft={() => {
                        if (indAiState?.payload) {
                          applyIndividualAiDraft(card, indAiState.payload);
                        }
                      }}
                      onApplyEvidenceStep={() => {
                        if (indAiState?.payload) {
                          applyIndividualEvidenceFallback(card, indAiState.payload);
                        }
                      }}
                      onDiscard={() =>
                        discardAiTarget(indAiTargetKey, () => {
                          setDraftActionText(card.actionText);
                          setDraftMainIssue(card.mainIssue);
                          setDraftOwner(card.owner);
                          setDraftImpact(card.expectedImpact);
                          setDraftFollowUpLabel(card.followUpLabel ?? '');
                          setDraftObservationStatus(card.observationStatus);
                          setEditingIndividualId((prev) => (prev === card.id ? null : prev));
                        })
                      }
                      onRetry={() => triggerIndividualAi(card)}
                    />
                  )}
                </div>

                {/* 4. Action bar + Collapsed-by-default View evidence drawer */}
                <div className="mt-4 border-t border-slate-200/70 pt-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {showPresentationControl(presentationMode) && (
                        <>
                          <AiRecommendIconButton
                            loading={indAiState?.loading}
                            presentationMode={presentationMode}
                            ariaLabel={`Generate AI recommendation for ${card.agentName}`}
                            onClick={() => triggerIndividualAi(card)}
                          />
                          <AiStatusInline
                            loading={indAiState?.loading}
                            payload={indAiState?.payload}
                            error={indAiState?.error}
                            draftApplied={indAiState?.draftApplied}
                            presentationMode={presentationMode}
                            onRetry={() => triggerIndividualAi(card)}
                            onDismiss={() => discardAiTarget(indAiTargetKey)}
                          />
                          {!isEditing && (
                            <>
                              {!card.isSavedToStore && (
                                <button
                                  type="button"
                                  disabled={savingIndividualId === card.id}
                                  data-testid={`quick-save-individual-action-${card.employeeId}`}
                                  aria-label={`Save action plan for ${card.agentName}`}
                                  onClick={() => void quickSaveIndividual(card)}
                                  className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 transition-colors hover:bg-emerald-100 disabled:opacity-50"
                                >
                                  <Check className="size-3" aria-hidden="true" />
                                  <span>{savingIndividualId === card.id ? 'Saving…' : 'Save'}</span>
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => startEditIndividual(card)}
                                className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:border-blue-300 hover:text-blue-600"
                              >
                                <Edit3 className="size-3" aria-hidden="true" />
                                <span>Edit</span>
                              </button>
                              <button
                                type="button"
                                data-testid={`delete-individual-action-${card.employeeId}`}
                                onClick={() => setConfirmDeleteIndId(card.employeeId)}
                                className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-2.5 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-50"
                              >
                                <Trash2 className="size-3" aria-hidden="true" />
                                <span>Delete</span>
                              </button>
                            </>
                          )}
                        </>
                      )}
                    </div>
                    <ViewEvidenceToggleButton
                      isOpen={isEvidenceOpen}
                      panelId={evidencePanelId}
                      onToggle={() =>
                        setExpandedEvidenceIds((prev) => ({
                          ...prev,
                          [card.id]: !prev[card.id],
                        }))
                      }
                    />
                  </div>

                  {isConfirmingDelete && (
                    <div
                      role="alertdialog"
                      aria-label={`Confirm delete action for ${card.agentName}`}
                      className="mt-3 rounded-xl border border-rose-200 bg-rose-50/80 p-3"
                    >
                      <p className="text-xs font-semibold text-rose-900">
                        Delete this individual action plan for {card.agentName}?
                      </p>
                      {deleteError && (
                        <p role="alert" className="mt-1 text-xs font-medium text-rose-700">
                          {deleteError}
                        </p>
                      )}
                      <div className="mt-2 flex justify-end gap-2">
                        <button
                          type="button"
                          disabled={isDeleting}
                          onClick={() => setConfirmDeleteIndId(null)}
                          className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          disabled={isDeleting}
                          data-testid={`confirm-delete-individual-action-${card.employeeId}`}
                          onClick={() => confirmDeleteIndividual(card)}
                          className="rounded-lg bg-rose-600 px-3 py-1 text-xs font-bold text-white hover:bg-rose-700 disabled:opacity-50"
                        >
                          {isDeleting ? 'Deleting…' : 'Delete Action'}
                        </button>
                      </div>
                    </div>
                  )}

                  <IndividualEvidenceDrawer
                    panelId={evidencePanelId}
                    isOpen={isEvidenceOpen}
                    employeeId={card.employeeId}
                    testIdPrefix="individual"
                    changeVsPrev={card.changeVsPrev}
                    previousPeriodLabel={card.previousPeriodLabel}
                    previousIsAdjacent={card.previousIsAdjacent}
                    missingIntermediatePeriods={card.missingIntermediatePeriods}
                    fullWindowComparisonLabel={card.fullWindowComparisonLabel}
                    scoreTrendLabel={card.scoreTrendLabel}
                    weakKpis={card.weakKpis}
                    allKpiEvidence={card.allKpiEvidence}
                    priorActions={card.priorActions}
                    expectedImpact={card.expectedImpact}
                    projectedAgentScoreLift={linkedEvidence?.projectedAgentScoreLift}
                    linkedKpiLabel={linkedEvidence?.label}
                    linkedKpiTarget={linkedEvidence?.targetFormatted}
                  />
                </div>
              </article>
            );
          })}
        </div>
        )}
      </section>
      )}

      {/* ================================================================== */}
      {/* 6. TEAM-LEVEL ACTION PLAN (Systemic Actions for Whole Team)        */}
      {/* ================================================================== */}
      {(showActionSection(teamCards.length, presentationMode) ||
        (!presentationMode && deletedBuiltInIds.length > 0)) && (
      <section
        id="presentation-section-team-actions"
        data-section-label="Actions"
        aria-labelledby="team-level-action-plan-heading"
        className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-4">
          <div>
            <span className="text-xs font-semibold tracking-wider text-emerald-600 uppercase">
              Cohort-Wide Interventions
            </span>
            <h2
              id="team-level-action-plan-heading"
              className="mt-0.5 text-lg font-bold text-slate-900"
            >
              Team-Level Action Plan
            </h2>
          </div>

          {showPresentationControl(presentationMode) && (
            <div className="flex flex-wrap items-center gap-2">
              {deletedBuiltInIds.length > 0 && (
                <button
                  type="button"
                  disabled={restoringTeam}
                  onClick={restoreBuiltInTeamActions}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition-colors hover:border-blue-300 hover:text-blue-700 disabled:opacity-50"
                >
                  <RotateCcw className="size-3.5" aria-hidden="true" />
                  <span>
                    {restoringTeam
                      ? 'Restoring…'
                      : `Restore ${deletedBuiltInIds.length} dismissed`}
                  </span>
                </button>
              )}
              <button
                type="button"
                data-testid="add-team-action-btn"
                onClick={() => setIsAddingTeamAction((prev) => !prev)}
                className="inline-flex items-center gap-1.5 rounded-xl border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-bold text-blue-700 transition-colors hover:bg-blue-100"
              >
                <Plus className="size-3.5" />
                <span>Add Team Action</span>
              </button>
            </div>
          )}
        </div>

        {teamRestoreError && showPresentationControl(presentationMode) && (
          <p role="alert" className="mt-3 text-xs font-medium text-rose-700">
            {teamRestoreError}
          </p>
        )}

        {isAddingTeamAction && showPresentationControl(presentationMode) && (
          <div className="mt-4 space-y-3 rounded-2xl border border-blue-200 bg-blue-50/30 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-xs font-bold text-slate-900">
                New Team-Level Action for {data.teamDisplayName}
              </div>
              <AiRecommendIconButton
                loading={aiStateByTarget['new-team']?.loading}
                presentationMode={presentationMode}
                ariaLabel={`Generate AI recommendation for ${data.teamDisplayName}`}
                onClick={triggerNewTeamAi}
              />
            </div>

            <AiRecommendationBanner
              loading={aiStateByTarget['new-team']?.loading}
              payload={aiStateByTarget['new-team']?.payload}
              error={aiStateByTarget['new-team']?.error}
              needsOverwriteConfirm={aiStateByTarget['new-team']?.needsOverwriteConfirm}
              draftApplied={aiStateByTarget['new-team']?.draftApplied}
              presentationMode={presentationMode}
              onApplyDraft={() => {
                const payload = aiStateByTarget['new-team']?.payload;
                if (payload) applyNewTeamAiDraft(payload);
              }}
              onDiscard={() =>
                discardAiTarget('new-team', () => {
                  setNewTeamTitle('');
                  setNewTeamTargetKpi('');
                  setNewTeamScope(`All ${data.summary.headcount} ${data.teamDisplayName}`);
                })
              }
              onRetry={triggerNewTeamAi}
            />

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="sm:col-span-2">
                <label className="block text-xs font-semibold text-slate-600">
                  Action Description
                </label>
                <input
                  type="text"
                  placeholder="Describe the team-wide workflow, scheduling, or training action..."
                  value={newTeamTitle}
                  onChange={(e) => setNewTeamTitle(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600">
                  Target KPI
                </label>
                <input
                  type="text"
                  placeholder="e.g. AHT · 3.01 min → 2.50 min"
                  value={newTeamTargetKpi}
                  onChange={(e) => setNewTeamTargetKpi(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="block text-xs font-semibold text-slate-600">
                  Scope
                </label>
                <input
                  type="text"
                  value={newTeamScope}
                  onChange={(e) => setNewTeamScope(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600">
                  Status
                </label>
                <select
                  value={newTeamStatus}
                  onChange={(e) =>
                    setNewTeamStatus(e.target.value as TeamLevelActionPlanCard['status'])
                  }
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                >
                  <option value="Open">Open</option>
                  <option value="In Progress">In Progress</option>
                  <option value="Planned">Planned</option>
                  <option value="Completed">Completed</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600">
                  Owner
                </label>
                <input
                  type="text"
                  value={newTeamOwner}
                  onChange={(e) => setNewTeamOwner(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600">
                  Due Date
                </label>
                <input
                  type="date"
                  value={newTeamDueDate}
                  onChange={(e) => setNewTeamDueDate(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600">
                  Expected Team-Level Impact
                </label>
                <input
                  type="text"
                  value={newTeamImpact}
                  onChange={(e) => setNewTeamImpact(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div className="flex items-end justify-end gap-2 sm:col-span-3">
                <button
                  type="button"
                  onClick={() => setIsAddingTeamAction(false)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleAddTeamAction}
                  className="rounded-lg bg-blue-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-blue-700"
                >
                  Save Team Action
                </button>
              </div>
            </div>
          </div>
        )}

        {teamCards.length === 0 ? (
          <div className="mt-5 rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-6 text-center">
            <p className="text-sm font-medium text-slate-600">
              No team-level actions for this period. Click &lsquo;Add Team Action&rsquo; to create one.
            </p>
            {showPresentationControl(presentationMode) && deletedBuiltInIds.length > 0 && (
              <button
                type="button"
                disabled={restoringTeam}
                onClick={restoreBuiltInTeamActions}
                className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:border-blue-300 hover:text-blue-700 disabled:opacity-50"
              >
                <RotateCcw className="size-3.5" aria-hidden="true" />
                <span>{restoringTeam ? 'Restoring…' : 'Restore default actions'}</span>
              </button>
            )}
          </div>
        ) : (
        <div className="mt-5 grid grid-cols-1 items-start gap-4 lg:grid-cols-3">
          {teamCards.map((card) => {
            const isEditingTeam =
              editingTeamId === card.id && showPresentationControl(presentationMode);
            const isConfirmingTeamDelete =
              confirmDeleteTeamId === card.id && showPresentationControl(presentationMode);
            const isDeletingTeam = deletingTeamId === card.id;
            const cardDeleteError = teamDeleteError[card.id];
            const teamAiKey = `team:${card.id}`;
            const teamAiState = aiStateByTarget[teamAiKey];
            const saveFb = teamSaveFeedback[card.id];
            const teamEvidenceId = `team-evidence-panel-${card.id}`;
            const isTeamEvidenceOpen = Boolean(expandedEvidenceIds[teamEvidenceId]);
            const resolvedFocusKey = resolveTeamCardFocusKpiKey(
              card,
              data.kpis,
              activeExplorerKpi?.kpiKey,
            );
            const matchedKpi = resolvedFocusKey
              ? data.kpis.find(
                  (k) => k.kpiKey.trim().toLowerCase() === resolvedFocusKey.trim().toLowerCase(),
                )
              : undefined;

            return (
              <article
                key={card.id}
                data-testid={`team-action-card-${card.id}`}
                className="flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-slate-50/50 p-5 transition-all hover:bg-white hover:shadow-xs"
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-2.5 py-0.5 text-xs font-bold text-blue-700">
                      <Layers className="size-3" />
                      Whole-Team Action
                    </span>
                    <span
                      data-testid={`team-action-status-${card.id}`}
                      className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                        card.status === 'In Progress'
                          ? 'bg-amber-100 text-amber-800'
                          : card.status === 'Completed'
                          ? 'bg-emerald-100 text-emerald-800'
                          : card.status === 'Planned'
                          ? 'bg-sky-100 text-sky-800'
                          : 'bg-slate-200 text-slate-700'
                      }`}
                    >
                      {card.status}
                    </span>
                  </div>

                  {isEditingTeam ? (
                    <div className="mt-3 space-y-2.5 rounded-xl border border-blue-200 bg-white p-3">
                      <div>
                        <label className="block text-xs font-bold text-slate-600">
                          Action Title
                        </label>
                        <textarea
                          rows={2}
                          value={draftTeamTitle}
                          onChange={(e) => setDraftTeamTitle(e.target.value)}
                          className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                        />
                      </div>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        <div>
                          <label className="block text-xs font-bold text-slate-600">
                            Target KPI
                          </label>
                          <input
                            type="text"
                            value={draftTeamTargetKpi}
                            onChange={(e) => setDraftTeamTargetKpi(e.target.value)}
                            className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-bold text-slate-600">
                            Status
                          </label>
                          <select
                            value={draftTeamStatus}
                            onChange={(e) =>
                              setDraftTeamStatus(
                                e.target.value as TeamLevelActionPlanCard['status'],
                              )
                            }
                            className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                          >
                            <option value="Open">Open</option>
                            <option value="In Progress">In Progress</option>
                            <option value="Planned">Planned</option>
                            <option value="Completed">Completed</option>
                          </select>
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-slate-600">
                          Scope
                        </label>
                        <input
                          type="text"
                          value={draftTeamScope}
                          onChange={(e) => setDraftTeamScope(e.target.value)}
                          className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                        />
                      </div>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        <div>
                          <label className="block text-xs font-bold text-slate-600">
                            Owner
                          </label>
                          <input
                            type="text"
                            value={draftTeamOwner}
                            onChange={(e) => setDraftTeamOwner(e.target.value)}
                            className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-bold text-slate-600">
                            Due Date
                          </label>
                          <input
                            type="date"
                            value={draftTeamDueDate}
                            onChange={(e) => setDraftTeamDueDate(e.target.value)}
                            className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                          />
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-slate-600">
                          Expected Team Impact
                        </label>
                        <input
                          type="text"
                          value={draftTeamImpact}
                          onChange={(e) => setDraftTeamImpact(e.target.value)}
                          className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                        />
                      </div>
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => setEditingTeamId(null)}
                          className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => saveEditTeam(card)}
                          className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1 text-xs font-bold text-white hover:bg-blue-700"
                        >
                          <Check className="size-3.5" />
                          <span>Save Team Action</span>
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      {/* 1. KPI gap */}
                      <div className="mt-3 rounded-xl border border-slate-200/80 bg-white px-3 py-2 text-xs font-semibold text-slate-800">
                        <Target className="mr-1 inline size-3.5 text-blue-600" aria-hidden="true" />
                        <span>{card.targetKpi}</span>
                      </div>

                      {/* 2. Next step */}
                      <h3 className="mt-3 text-sm font-bold leading-snug text-slate-900">
                        {card.title}
                      </h3>
                    </>
                  )}

                  {showPresentationControl(presentationMode) && (
                    <AiRecommendationBanner
                      inlineStatusHandled
                      loading={teamAiState?.loading}
                      payload={teamAiState?.payload}
                      error={teamAiState?.error}
                      needsOverwriteConfirm={teamAiState?.needsOverwriteConfirm}
                      draftApplied={teamAiState?.draftApplied}
                      presentationMode={presentationMode}
                      onApplyDraft={() => {
                        if (teamAiState?.payload) {
                          applyTeamAiDraft(card, teamAiState.payload);
                        }
                      }}
                      onApplyEvidenceStep={() => {
                        if (teamAiState?.payload) {
                          applyTeamEvidenceFallback(card, teamAiState.payload);
                        }
                      }}
                      onDiscard={() =>
                        discardAiTarget(teamAiKey, () => {
                          setDraftTeamTitle(card.title);
                          setDraftTeamTargetKpi(card.targetKpi);
                          setDraftTeamScope(card.scopeDescription);
                        })
                      }
                      onRetry={() => triggerTeamAi(card)}
                    />
                  )}

                  {saveFb && !isEditingTeam && (
                    <p
                      role="status"
                      className={`mt-2 text-xs font-medium ${
                        saveFb.type === 'error' ? 'text-amber-700' : 'text-emerald-700'
                      }`}
                    >
                      {saveFb.message}
                    </p>
                  )}
                </div>

                {/* 3. Owner and review date */}
                <div className="mt-4 flex flex-col gap-1.5 border-t border-slate-200/70 pt-3 text-xs">
                  <div className="flex items-center justify-between text-slate-700">
                    <span className="font-medium text-slate-400">Owner</span>
                    <span data-testid={`team-action-owner-${card.id}`} className="font-bold text-slate-800">
                      {card.owner}
                    </span>
                  </div>
                  {showStoredPlaceholder(teamActionDueLabel(card.dueDate), presentationMode) && (
                    <div className="flex items-center justify-between text-slate-700">
                      <span className="font-medium text-slate-400">Review date</span>
                      <span data-testid={`team-action-due-${card.id}`} className="font-semibold text-slate-800">
                        {teamActionDueLabel(card.dueDate)}
                      </span>
                    </div>
                  )}
                </div>

                {isConfirmingTeamDelete && (
                  <div
                    role="alertdialog"
                    aria-label={`Confirm delete team action ${card.title}`}
                    className="mt-3 rounded-xl border border-rose-200 bg-rose-50/80 p-3"
                  >
                    <p className="text-xs font-semibold text-rose-900">
                      Delete this team-level action?
                    </p>
                    {cardDeleteError && (
                      <p role="alert" className="mt-1 text-xs font-medium text-rose-700">
                        {cardDeleteError}
                      </p>
                    )}
                    <div className="mt-2 flex justify-end gap-2">
                      <button
                        type="button"
                        disabled={isDeletingTeam}
                        onClick={() => setConfirmDeleteTeamId(null)}
                        className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        disabled={isDeletingTeam}
                        data-testid={`confirm-delete-team-action-${card.id}`}
                        onClick={() => confirmDeleteTeamAction(card)}
                        className="rounded-lg bg-rose-600 px-3 py-1 text-xs font-bold text-white hover:bg-rose-700 disabled:opacity-50"
                      >
                        {isDeletingTeam ? 'Deleting…' : 'Delete Action'}
                      </button>
                    </div>
                  </div>
                )}

                <div className="mt-3 border-t border-slate-200/70 pt-3">
                  <div className="flex flex-wrap items-center justify-between gap-1.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {showPresentationControl(presentationMode) && (
                        <>
                          <AiRecommendIconButton
                            compact
                            loading={teamAiState?.loading}
                            presentationMode={presentationMode}
                            ariaLabel={`Generate AI recommendation for ${card.title}`}
                            onClick={() => triggerTeamAi(card)}
                          />
                          <AiStatusInline
                            loading={teamAiState?.loading}
                            payload={teamAiState?.payload}
                            error={teamAiState?.error}
                            draftApplied={teamAiState?.draftApplied}
                            presentationMode={presentationMode}
                            onRetry={() => triggerTeamAi(card)}
                            onDismiss={() => discardAiTarget(teamAiKey)}
                          />
                          {!isEditingTeam && (
                            <>
                              <button
                                type="button"
                                data-testid={`edit-team-action-${card.id}`}
                                onClick={() => startEditTeam(card)}
                                className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-semibold text-slate-600 hover:border-blue-300 hover:text-blue-600"
                              >
                                <Edit3 className="size-3" />
                                <span>Edit</span>
                              </button>
                              <button
                                type="button"
                                data-testid={`delete-team-action-${card.id}`}
                                onClick={() => setConfirmDeleteTeamId(card.id)}
                                className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-2 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-50"
                              >
                                <Trash2 className="size-3" aria-hidden="true" />
                                <span>Delete</span>
                              </button>
                            </>
                          )}
                        </>
                      )}
                    </div>
                    <ViewEvidenceToggleButton
                      isOpen={isTeamEvidenceOpen}
                      panelId={teamEvidenceId}
                      onToggle={() =>
                        setExpandedEvidenceIds((prev) => ({
                          ...prev,
                          [teamEvidenceId]: !prev[teamEvidenceId],
                        }))
                      }
                    />
                  </div>

                  <TeamEvidenceDrawer
                    panelId={teamEvidenceId}
                    isOpen={isTeamEvidenceOpen}
                    cardId={card.id}
                    scopeDescription={card.scopeDescription}
                    expectedTeamImpact={card.expectedTeamImpact}
                    targetKpiLabel={matchedKpi?.label || card.targetKpi}
                    linkedKpiActualLabel={matchedKpi?.actualFormatted}
                    linkedKpiTargetLabel={matchedKpi?.targetFormatted}
                    teamTrendLabel={matchedKpi?.movementFormatted || null}
                    aiPayload={teamAiState?.payload}
                  />
                </div>
              </article>
            );
          })}
        </div>
        )}
      </section>
      )}
    </div>
  );
}
