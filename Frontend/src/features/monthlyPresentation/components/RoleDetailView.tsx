import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ApiError } from '../../../lib/apiClient';
import {
  AiRecommendationBanner,
  AiRecommendIconButton,
  AiStatusInline,
  formatScoreChangeLabel,
  IndividualEvidenceDrawer,
  ViewEvidenceToggleButton,
} from './ActionPlanAiAssistant';
import {
  buildAiScopeKey,
  parseMonthYearFromLabel,
  requestActionPlanAiSuggestion,
  type ActionPlanAiError,
  type AiCorrectiveActionSuggestionPayload,
} from './actionPlanAiUtils';
import {
  AlertCircle,
  AlertTriangle,
  ArrowDownRight,
  ArrowLeft,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Edit3,
  Flame,
  Gauge,
  Layers,
  Plus,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Target,
  Trash2,
  UserCheck,
  Users,
} from 'lucide-react';
import { ProfileKpiSixMonthTrend } from '../../../components/employee/ScoreTrendChart';
import { GRADE_STYLES } from '../monthlyOverviewData';
import { IMPACT_LEVEL_STYLES } from '../callCenterDeepDiveData';
import type {
  RoleActionDraft,
  RoleAssignedAction,
  RoleDetailData,
  RoleIndividualActionPlan,
} from '../roleDetailData';
import { showActionSection, showPresentationControl, showStoredPlaceholder } from '../presentationMode';
import { memberPageWindow } from '../roleMemberPages';
import { SelectableKpiCard } from './SelectableKpiCard';
import { FullWordGradeBadge } from './TeamDeepDiveView';

const KPI_CARDS_PER_ROW = 4;
const DISMISSED_ROLE_IND_STORAGE_KEY = 'pms_dismissed_role_ind_cards_v1';
const DISMISSED_ROLE_COHORT_STORAGE_KEY = 'pms_dismissed_role_cohort_cards_v1';

function readRoleDismissedIds(storageKey: string, scopeKey: string): string[] {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const list = parsed?.[scopeKey];
    return Array.isArray(list) ? list.filter((x): x is string => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

function writeRoleDismissedIds(storageKey: string, scopeKey: string, ids: string[]): void {
  try {
    const raw = localStorage.getItem(storageKey);
    const parsed = raw ? (JSON.parse(raw) as Record<string, string[]>) : {};
    const next = { ...parsed, [scopeKey]: ids };
    if (ids.length === 0) {
      delete next[scopeKey];
    }
    localStorage.setItem(storageKey, JSON.stringify(next));
  } catch {
    // Ignore storage quota errors
  }
}

export interface RoleDetailViewProps {
  data: RoleDetailData;
  onNavigateToOverview: () => void;
  onNavigateToFunction: () => void;
  onSaveAction: (draft: RoleActionDraft) => Promise<void> | void;
  onDeleteIndividualAction?: (
    employeeId: string,
    monthName: string,
    actionId?: string,
  ) => Promise<void> | void;
  onDeleteAction?: (action: RoleAssignedAction) => Promise<void> | void;
  toolbar?: ReactNode;
  presentationMode?: boolean;
}

const fieldClass =
  'mt-1.5 w-full rounded-xl border border-slate-200/90 bg-white px-3.5 text-sm text-slate-900 outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-100';

export default function RoleDetailView({
  data,
  onNavigateToOverview,
  onNavigateToFunction,
  onSaveAction,
  onDeleteIndividualAction,
  onDeleteAction,
  toolbar,
  presentationMode = false,
}: RoleDetailViewProps) {
  const [selectedId, setSelectedId] = useState(data.kpis[0]?.id ?? '');
  const [carouselStart, setCarouselStart] = useState(0);
  const [showAllMembers, setShowAllMembers] = useState(false);
  const [description, setDescription] = useState('');
  const [owner, setOwner] = useState(data.roleTitle);
  const [dueDate, setDueDate] = useState('');
  const [status, setStatus] = useState<RoleActionDraft['status']>('Open');
  const [expectedImpact, setExpectedImpact] = useState('');
  const [targetKpiKey, setTargetKpiKey] = useState<string>(data.kpis[0]?.kpiKey ?? '');
  const [affectedPerson, setAffectedPerson] = useState<string>('ALL_LOW');
  const [addedActions, setAddedActions] = useState<RoleAssignedAction[]>([]);
  const [saving, setSaving] = useState(false);

  // 1-on-1 Individual Action Plan inline editing state
  const [editingIndividualId, setEditingIndividualId] = useState<string | null>(null);
  const [draftIndAction, setDraftIndAction] = useState('');
  const [draftIndMainIssue, setDraftIndMainIssue] = useState('');
  const [draftIndOwner, setDraftIndOwner] = useState('');
  const [draftIndImpact, setDraftIndImpact] = useState('');
  const [draftIndFollowUpLabel, setDraftIndFollowUpLabel] = useState('');
  const [draftIndObservationStatus, setDraftIndObservationStatus] =
    useState<RoleIndividualActionPlan['observationStatus']>(undefined);
  const [individualOverrides, setIndividualOverrides] = useState<
    Record<string, Partial<RoleIndividualActionPlan>>
  >({});

  // Role-level Assigned Action inline editing state
  const [editingRoleActionId, setEditingRoleActionId] = useState<string | null>(null);
  const [draftRoleDesc, setDraftRoleDesc] = useState('');
  const [draftRoleOwner, setDraftRoleOwner] = useState('');
  const [draftRoleStatus, setDraftRoleStatus] = useState<RoleActionDraft['status']>('Open');
  const [draftRoleDueDate, setDraftRoleDueDate] = useState('');
  const [draftRoleImpact, setDraftRoleImpact] = useState('');
  const [roleActionOverrides, setRoleActionOverrides] = useState<
    Record<string, Partial<RoleAssignedAction>>
  >({});

  // AI Draft state keyed by 'ind:<id>', 'role-act:<id>', or 'role-form'
  type RoleAiState = {
    loading: boolean;
    scopeKey?: string;
    payload: AiCorrectiveActionSuggestionPayload | null;
    error: ActionPlanAiError | null;
    needsOverwriteConfirm: boolean;
    draftApplied: boolean;
  };
  const viewScopeKey = `${data.roleSlug}|${data.periodKey}`;
  const [prevViewScopeKey, setPrevViewScopeKey] = useState(viewScopeKey);
  const [dismissedIndIds, setDismissedIndIds] = useState<string[]>(() =>
    readRoleDismissedIds(DISMISSED_ROLE_IND_STORAGE_KEY, viewScopeKey),
  );
  const [confirmDeleteIndId, setConfirmDeleteIndId] = useState<string | null>(null);
  const [deletingIndId, setDeletingIndId] = useState<string | null>(null);
  const [indDeleteError, setIndDeleteError] = useState<Record<string, string>>({});

  const [dismissedRoleActionIds, setDismissedRoleActionIds] = useState<string[]>(() =>
    readRoleDismissedIds(DISMISSED_ROLE_COHORT_STORAGE_KEY, viewScopeKey),
  );
  const [confirmDeleteRoleId, setConfirmDeleteRoleId] = useState<string | null>(null);
  const [deletingRoleId, setDeletingRoleId] = useState<string | null>(null);
  const [roleDeleteError, setRoleDeleteError] = useState<Record<string, string>>({});
  const [savingIndividualId, setSavingIndividualId] = useState<string | null>(null);
  const [indSaveFeedback, setIndSaveFeedback] = useState<
    Record<string, { type: 'success' | 'error'; message: string }>
  >({});
  const [savingRoleActionId, setSavingRoleActionId] = useState<string | null>(null);
  const [roleSaveFeedback, setRoleSaveFeedback] = useState<
    Record<string, { type: 'success' | 'error'; message: string }>
  >({});

  const [aiStateByTarget, setAiStateByTarget] = useState<Record<string, RoleAiState>>({});
  const [expandedEvidenceIds, setExpandedEvidenceIds] = useState<Record<string, boolean>>({});
  const abortControllersRef = useRef<Record<string, AbortController>>({});
  const inFlightScopesRef = useRef<Record<string, string>>({});

  if (prevViewScopeKey !== viewScopeKey) {
    setPrevViewScopeKey(viewScopeKey);
    setAiStateByTarget({});
    setExpandedEvidenceIds({});
    setIndividualOverrides({});
    setEditingIndividualId(null);
    setRoleActionOverrides({});
    setEditingRoleActionId(null);
    setDismissedIndIds(readRoleDismissedIds(DISMISSED_ROLE_IND_STORAGE_KEY, viewScopeKey));
    setConfirmDeleteIndId(null);
    setDeletingIndId(null);
    setIndDeleteError({});
    setDismissedRoleActionIds(readRoleDismissedIds(DISMISSED_ROLE_COHORT_STORAGE_KEY, viewScopeKey));
    setConfirmDeleteRoleId(null);
    setDeletingRoleId(null);
    setRoleDeleteError({});
    setSavingIndividualId(null);
    setIndSaveFeedback({});
    setSavingRoleActionId(null);
    setRoleSaveFeedback({});
  }

  useEffect(() => {
    if (!confirmDeleteIndId && !confirmDeleteRoleId) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (confirmDeleteIndId && deletingIndId !== confirmDeleteIndId) {
        setConfirmDeleteIndId(null);
      }
      if (confirmDeleteRoleId && deletingRoleId !== confirmDeleteRoleId) {
        setConfirmDeleteRoleId(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [confirmDeleteIndId, confirmDeleteRoleId, deletingIndId, deletingRoleId]);

  useEffect(() => {
    const controllers = abortControllersRef.current;
    const scopes = inFlightScopesRef.current;
    return () => {
      Object.values(controllers).forEach((ctrl) => ctrl.abort());
      Object.keys(controllers).forEach((k) => delete controllers[k]);
      Object.keys(scopes).forEach((k) => delete scopes[k]);
    };
  }, [viewScopeKey]);

  const selected = useMemo(
    () => data.kpis.find((kpi) => kpi.id === selectedId) ?? data.kpis[0],
    [data.kpis, selectedId],
  );

  const biggestGapKpi = useMemo(
    () => data.kpis.find((kpi) => kpi.isBiggestGap && kpi.pointsLost > 0) ?? null,
    [data.kpis],
  );

  // People in this Role: Average or below (score < 90) by default
  const below90Members = useMemo(
    () => data.members.filter((member) => member.score < 90),
    [data.members],
  );

  const displayedMembers = useMemo(
    () => (showAllMembers ? data.members : below90Members),
    [below90Members, data.members, showAllMembers],
  );

  const memberListKey = `${data.roleSlug}|${data.periodKey}|${showAllMembers ? 'all' : 'below-90'}`;
  const [memberPageState, setMemberPageState] = useState({
    listKey: memberListKey,
    page: 0,
  });
  const requestedPage = memberPageState.listKey === memberListKey ? memberPageState.page : 0;

  const memberPages = useMemo(
    () => memberPageWindow(displayedMembers, requestedPage),
    [displayedMembers, requestedPage],
  );
  const visibleMembers = memberPages.visible;

  const dismissedIndSet = useMemo(
    () => new Set(dismissedIndIds.map((id) => id.toLowerCase())),
    [dismissedIndIds],
  );

  const displayedIndividualCards = useMemo(() => {
    const displayedIds = new Set(visibleMembers.map((m) => m.employeeId));
    const base = (data.individualActionPlans ?? []).filter(
      (c) => displayedIds.has(c.employeeId) && !dismissedIndSet.has(c.employeeId.toLowerCase()),
    );
    return base.map((card) => ({
      ...card,
      ...(individualOverrides[card.id] ?? {}),
    }));
  }, [data.individualActionPlans, dismissedIndSet, visibleMembers, individualOverrides]);

  const { month: activeMonthName, year: activeYearNum } = useMemo(
    () => parseMonthYearFromLabel(data.monthLabel, data.periodKey),
    [data.monthLabel, data.periodKey],
  );

  const startEditIndividual = (card: RoleIndividualActionPlan) => {
    setEditingIndividualId(card.id);
    setDraftIndAction(card.actionText);
    setDraftIndMainIssue(card.mainIssue);
    setDraftIndOwner(card.owner);
    setDraftIndImpact(card.expectedImpact);
    setDraftIndFollowUpLabel(card.followUpLabel ?? '');
    setDraftIndObservationStatus(card.observationStatus);
  };

  const cancelEditIndividual = (card: RoleIndividualActionPlan) => {
    setEditingIndividualId(null);
    setDraftIndAction(card.actionText);
    setDraftIndMainIssue(card.mainIssue);
    setDraftIndOwner(card.owner);
    setDraftIndImpact(card.expectedImpact);
    setDraftIndFollowUpLabel(card.followUpLabel ?? '');
    setDraftIndObservationStatus(card.observationStatus);
  };

  const saveEditIndividual = async (card: RoleIndividualActionPlan) => {
    const nextText = draftIndAction.trim() || card.actionText;
    const nextMainIssue = draftIndMainIssue.trim() || card.mainIssue;
    const nextOwner = draftIndOwner.trim() || card.owner;
    const nextImpact = draftIndImpact.trim() || card.expectedImpact;
    const nextFollowUpLabel = draftIndFollowUpLabel.trim() || card.followUpLabel;
    const nextObservationStatus = draftIndObservationStatus ?? card.observationStatus;
    await onSaveAction({
      actionId: card.actionId,
      employeeId: card.employeeId,
      personName: card.personName,
      team: data.roleTitle,
      month: activeMonthName,
      description: nextText,
      mainIssue: nextMainIssue,
      owner: nextOwner,
      dueDate: '',
      status: 'Open',
      expectedImpact: nextImpact,
      linkedKpiKey: card.linkedKpiKey,
    });
    setIndividualOverrides((prev) => ({
      ...prev,
      [card.id]: {
        ...(prev[card.id] ?? {}),
        actionText: nextText,
        mainIssue: nextMainIssue,
        owner: nextOwner,
        expectedImpact: nextImpact,
        followUpLabel: nextFollowUpLabel,
        observationStatus: nextObservationStatus,
        suggested: false,
      },
    }));
    setDismissedIndIds((prev) => {
      const next = prev.filter((id) => id.toLowerCase() !== card.employeeId.toLowerCase());
      if (next.length !== prev.length) {
        writeRoleDismissedIds(DISMISSED_ROLE_IND_STORAGE_KEY, viewScopeKey, next);
      }
      return next;
    });
    setEditingIndividualId(null);
    setAiStateByTarget((prev) => {
      if (!prev[`ind:${card.id}`]) return prev;
      const next = { ...prev };
      delete next[`ind:${card.id}`];
      return next;
    });
  };

  const quickSaveRoleIndividual = async (card: RoleIndividualActionPlan) => {
    setSavingIndividualId(card.id);
    try {
      await onSaveAction({
        actionId: card.actionId,
        employeeId: card.employeeId,
        personName: card.personName,
        team: data.roleTitle,
        month: activeMonthName,
        description: card.actionText,
        mainIssue: card.mainIssue,
        owner: card.owner,
        dueDate: '',
        status: 'Open',
        expectedImpact: card.expectedImpact,
        linkedKpiKey: card.linkedKpiKey,
      });
      setIndividualOverrides((prev) => ({
        ...prev,
        [card.id]: {
          ...(prev[card.id] ?? {}),
          suggested: false,
        },
      }));
      setDismissedIndIds((prev) => {
        const next = prev.filter((id) => id.toLowerCase() !== card.employeeId.toLowerCase());
        if (next.length !== prev.length) {
          writeRoleDismissedIds(DISMISSED_ROLE_IND_STORAGE_KEY, viewScopeKey, next);
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

  const confirmDeleteIndividual = async (card: RoleIndividualActionPlan) => {
    setDeletingIndId(card.employeeId);
    setIndDeleteError((prev) => {
      if (!prev[card.employeeId]) return prev;
      const next = { ...prev };
      delete next[card.employeeId];
      return next;
    });
    try {
      if (onDeleteIndividualAction) {
        await onDeleteIndividualAction(card.employeeId, activeMonthName, card.actionId);
      }
      setDismissedIndIds((prev) => {
        const exists = prev.some(
          (id) => id.toLowerCase() === card.employeeId.toLowerCase(),
        );
        const next = exists ? prev : [...prev, card.employeeId];
        writeRoleDismissedIds(DISMISSED_ROLE_IND_STORAGE_KEY, viewScopeKey, next);
        return next;
      });
      setIndividualOverrides((prev) => {
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
    writeRoleDismissedIds(DISMISSED_ROLE_IND_STORAGE_KEY, viewScopeKey, []);
    setIndDeleteError({});
    setConfirmDeleteIndId(null);
  };

  const dismissedRoleSet = useMemo(
    () => new Set(dismissedRoleActionIds),
    [dismissedRoleActionIds],
  );

  const restorableDismissedRoleIds = useMemo(
    () => dismissedRoleActionIds.filter((id) => data.actions.some((a) => a.id === id)),
    [dismissedRoleActionIds, data.actions],
  );

  const localActions = useMemo(
    () =>
      [...addedActions, ...data.actions]
        .filter((act) => !dismissedRoleSet.has(act.id))
        .map((act) => ({
          ...act,
          ...(roleActionOverrides[act.id] ?? {}),
        })),
    [addedActions, data.actions, dismissedRoleSet, roleActionOverrides],
  );

  const startEditRoleAction = (action: RoleAssignedAction) => {
    setEditingRoleActionId(action.id);
    setDraftRoleDesc(action.description);
    setDraftRoleOwner(action.owner);
    setDraftRoleStatus(action.status === 'Cancelled' ? 'Open' : action.status);
    setDraftRoleDueDate(action.dueDate ?? '');
    setDraftRoleImpact(action.expectedImpact);
  };

  const saveEditRoleAction = async (action: RoleAssignedAction) => {
    const nextDesc = draftRoleDesc.trim() || action.description;
    const nextOwner = draftRoleOwner.trim() || action.owner;
    const nextImpact = draftRoleImpact.trim() || action.expectedImpact;
    const nextDue = draftRoleDueDate.trim();
    await onSaveAction({
      actionId: action.id,
      employeeId: action.employeeId || data.employeeId,
      personName: data.personName,
      team: data.roleTitle,
      month: activeMonthName,
      description: nextDesc,
      owner: nextOwner,
      dueDate: nextDue,
      status: draftRoleStatus,
      expectedImpact: nextImpact,
      linkedKpiKey: action.linkedKpiKey ?? selected?.kpiKey ?? null,
    });
    setRoleActionOverrides((prev) => ({
      ...prev,
      [action.id]: {
        description: nextDesc,
        owner: nextOwner,
        status: draftRoleStatus,
        dueDate: nextDue || null,
        expectedImpact: nextImpact,
        suggested: false,
      },
    }));
    setDismissedRoleActionIds((prev) => {
      const next = prev.filter((id) => id !== action.id);
      if (next.length !== prev.length) {
        writeRoleDismissedIds(DISMISSED_ROLE_COHORT_STORAGE_KEY, viewScopeKey, next);
      }
      return next;
    });
    setEditingRoleActionId(null);
    setAiStateByTarget((prev) => {
      if (!prev[`role-act:${action.id}`]) return prev;
      const next = { ...prev };
      delete next[`role-act:${action.id}`];
      return next;
    });
  };

  const quickSaveRoleAction = async (action: RoleAssignedAction) => {
    setSavingRoleActionId(action.id);
    try {
      await onSaveAction({
        actionId: action.id,
        employeeId: action.employeeId || data.employeeId,
        personName: data.personName,
        team: data.roleTitle,
        month: activeMonthName,
        description: action.description,
        owner: action.owner,
        dueDate: action.dueDate ?? '',
        status: action.status === 'Cancelled' ? 'Open' : action.status,
        expectedImpact: action.expectedImpact,
        linkedKpiKey: action.linkedKpiKey ?? selected?.kpiKey ?? null,
      });
      setRoleActionOverrides((prev) => ({
        ...prev,
        [action.id]: {
          ...(prev[action.id] ?? {}),
          suggested: false,
        },
      }));
      setDismissedRoleActionIds((prev) => {
        const next = prev.filter((id) => id !== action.id);
        if (next.length !== prev.length) {
          writeRoleDismissedIds(DISMISSED_ROLE_COHORT_STORAGE_KEY, viewScopeKey, next);
        }
        return next;
      });
      setRoleSaveFeedback((prev) => ({
        ...prev,
        [action.id]: { type: 'success', message: 'Saved role action' },
      }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Save failed';
      setRoleSaveFeedback((prev) => ({
        ...prev,
        [action.id]: { type: 'error', message: msg },
      }));
    } finally {
      setSavingRoleActionId(null);
    }
  };

  const confirmDeleteRoleAction = async (action: RoleAssignedAction) => {
    setDeletingRoleId(action.id);
    setRoleDeleteError((prev) => {
      if (!prev[action.id]) return prev;
      const next = { ...prev };
      delete next[action.id];
      return next;
    });
    try {
      if (onDeleteAction) {
        await onDeleteAction(action);
      }
      setAddedActions((prev) => prev.filter((a) => a.id !== action.id));
      setRoleActionOverrides((prev) => {
        if (!prev[action.id]) return prev;
        const next = { ...prev };
        delete next[action.id];
        return next;
      });
      if (data.actions.some((a) => a.id === action.id)) {
        setDismissedRoleActionIds((prev) => {
          const next = prev.includes(action.id) ? prev : [...prev, action.id];
          writeRoleDismissedIds(DISMISSED_ROLE_COHORT_STORAGE_KEY, viewScopeKey, next);
          return next;
        });
      }
      setConfirmDeleteRoleId(null);
      if (editingRoleActionId === action.id) {
        setEditingRoleActionId(null);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to delete role action';
      setRoleDeleteError((prev) => ({
        ...prev,
        [action.id]: msg,
      }));
    } finally {
      setDeletingRoleId(null);
    }
  };

  const restoreDismissedRoleActions = () => {
    setDismissedRoleActionIds([]);
    writeRoleDismissedIds(DISMISSED_ROLE_COHORT_STORAGE_KEY, viewScopeKey, []);
    setRoleDeleteError({});
    setConfirmDeleteRoleId(null);
  };

  const formatRoleDraftText = (
    payload: AiCorrectiveActionSuggestionPayload,
  ): string => {
    const draft = payload.draft;
    if (!draft) return '';
    const steps = draft.recommended_steps.map((s) => s.trim()).filter(Boolean);
    return steps.length > 0 ? `${draft.title}: ${steps.join(' ')}` : draft.title;
  };

  const applyRoleIndividualAiDraft = useCallback(
    (card: RoleIndividualActionPlan, payload: AiCorrectiveActionSuggestionPayload) => {
      if (!payload.draft) return;
      setEditingIndividualId(card.id);
      setDraftIndAction(formatRoleDraftText(payload));
      setDraftIndMainIssue(payload.draft.measured_issue || card.mainIssue);
      setDraftIndOwner((prev) =>
        editingIndividualId === card.id && prev.trim() !== card.owner.trim()
          ? prev
          : payload.draft?.responsible_role || card.owner,
      );
      setDraftIndImpact((prev) =>
        editingIndividualId === card.id ? prev : card.expectedImpact,
      );
      setDraftIndFollowUpLabel(payload.draft.recommended_follow_up || card.followUpLabel || '');
      setDraftIndObservationStatus(payload.draft.observation_status || card.observationStatus);
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

  const applyRoleIndividualEvidenceFallback = useCallback(
    (card: RoleIndividualActionPlan, payload: AiCorrectiveActionSuggestionPayload) => {
      if (!payload.evidence_next_step) return;
      setEditingIndividualId(card.id);
      setDraftIndAction(payload.evidence_next_step);
      setDraftIndMainIssue(payload.measured_facts?.[0] || card.mainIssue);
      setDraftIndOwner(payload.evidence_next_step_role || card.owner);
      setDraftIndImpact(card.expectedImpact);
      setDraftIndFollowUpLabel(payload.evidence_next_step_follow_up || card.followUpLabel || '');
      setDraftIndObservationStatus(card.observationStatus);
    },
    [],
  );

  const applyRoleActionAiDraft = useCallback(
    (action: RoleAssignedAction, payload: AiCorrectiveActionSuggestionPayload) => {
      if (!payload.draft) return;
      setEditingRoleActionId(action.id);
      setDraftRoleDesc(formatRoleDraftText(payload));
      if (editingRoleActionId !== action.id) {
        setDraftRoleOwner(action.owner);
        setDraftRoleStatus(action.status === 'Cancelled' ? 'Open' : action.status);
        setDraftRoleDueDate(action.dueDate ?? '');
        setDraftRoleImpact(action.expectedImpact);
      }
      setAiStateByTarget((prev) => ({
        ...prev,
        [`role-act:${action.id}`]: {
          loading: false,
          payload,
          error: null,
          needsOverwriteConfirm: false,
          draftApplied: true,
        },
      }));
    },
    [editingRoleActionId],
  );

  const applyRoleActionEvidenceFallback = useCallback(
    (action: RoleAssignedAction, payload: AiCorrectiveActionSuggestionPayload) => {
      if (!payload.evidence_next_step) return;
      setEditingRoleActionId(action.id);
      setDraftRoleDesc(payload.evidence_next_step);
      setDraftRoleOwner(payload.evidence_next_step_role || action.owner);
      setDraftRoleStatus(action.status === 'Cancelled' ? 'Open' : action.status);
      setDraftRoleDueDate(action.dueDate ?? '');
      setDraftRoleImpact(action.expectedImpact);
    },
    [],
  );

  const applyRoleFormAiDraft = useCallback(
    (payload: AiCorrectiveActionSuggestionPayload) => {
      if (!payload.draft) return;
      setDescription(formatRoleDraftText(payload));
      const matchedKpi = data.kpis.find(
        (k) =>
          k.kpiKey.toLowerCase() === payload.draft!.focus_kpi_key.toLowerCase() ||
          k.name.toLowerCase() === payload.draft!.focus_kpi_name.toLowerCase(),
      );
      if (matchedKpi) {
        setTargetKpiKey(matchedKpi.kpiKey);
      }
      setAiStateByTarget((prev) => ({
        ...prev,
        'role-form': {
          loading: false,
          payload,
          error: null,
          needsOverwriteConfirm: false,
          draftApplied: true,
        },
      }));
    },
    [data.kpis],
  );

  const runRoleAiRequest = useCallback(
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

  const resolvedRoleTeam = data.individualActionPlans[0]?.recordTeam || data.functionName;
  const resolvedRoleLevel = data.individualActionPlans[0]?.performanceLevel || undefined;

  const triggerRoleIndividualAi = useCallback(
    (card: RoleIndividualActionPlan) => {
      const targetKey = `ind:${card.id}`;
      const scopeTeam = card.recordTeam || resolvedRoleTeam;
      const scopeKey = buildAiScopeKey(scopeTeam, data.periodKey, card.employeeId, card.linkedKpiKey);
      const isEditingThis = editingIndividualId === card.id;
      const hasUnsaved =
        isEditingThis &&
        (draftIndAction.trim() !== card.actionText.trim() ||
          draftIndMainIssue.trim() !== card.mainIssue.trim() ||
          draftIndOwner.trim() !== card.owner.trim() ||
          draftIndImpact.trim() !== card.expectedImpact.trim());
      void runRoleAiRequest(
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
        (payload) => applyRoleIndividualAiDraft(card, payload),
      );
    },
    [
      activeMonthName,
      activeYearNum,
      applyRoleIndividualAiDraft,
      draftIndAction,
      draftIndImpact,
      draftIndMainIssue,
      draftIndOwner,
      editingIndividualId,
      resolvedRoleTeam,
      runRoleAiRequest,
    ],
  );

  const triggerRoleActionAi = useCallback(
    (action: RoleAssignedAction) => {
      const targetKey = `role-act:${action.id}`;
      const empId =
        action.employeeId || (data.headcount === 1 && data.employeeId ? data.employeeId : null);
      const focusKpiKey = action.linkedKpiKey || selected?.kpiKey || null;
      const scopeKey = buildAiScopeKey(resolvedRoleTeam, data.periodKey, empId, focusKpiKey);
      const isEditingThis = editingRoleActionId === action.id;
      const hasUnsaved =
        isEditingThis &&
        (draftRoleDesc.trim() !== action.description.trim() ||
          draftRoleOwner.trim() !== action.owner.trim() ||
          draftRoleImpact.trim() !== action.expectedImpact.trim() ||
          draftRoleDueDate.trim() !== (action.dueDate ?? '').trim());
      void runRoleAiRequest(
        targetKey,
        scopeKey,
        (signal) =>
          requestActionPlanAiSuggestion({
            team: resolvedRoleTeam,
            month: activeMonthName,
            year: activeYearNum,
            performanceLevel: resolvedRoleLevel,
            employeeId: empId,
            focusKpiKey,
            signal,
          }),
        hasUnsaved,
        (payload) => applyRoleActionAiDraft(action, payload),
      );
    },
    [
      activeMonthName,
      activeYearNum,
      applyRoleActionAiDraft,
      data.employeeId,
      data.headcount,
      draftRoleDesc,
      draftRoleDueDate,
      draftRoleImpact,
      draftRoleOwner,
      editingRoleActionId,
      resolvedRoleLevel,
      resolvedRoleTeam,
      runRoleAiRequest,
      selected?.kpiKey,
    ],
  );

  const triggerRoleFormAi = useCallback(() => {
    const hasUnsaved = description.trim().length > 0;
    const candidateKpiKey = targetKpiKey || selected?.kpiKey || null;
    const candidateKpi = candidateKpiKey
      ? data.kpis.find((k) => k.kpiKey === candidateKpiKey)
      : selected;
    const focusKpiKey =
      candidateKpiKey && (!candidateKpi || candidateKpi.statusBadge !== 'On Target')
        ? candidateKpiKey
        : null;
    const scopeKey = buildAiScopeKey(resolvedRoleTeam, data.periodKey, null, focusKpiKey);
    void runRoleAiRequest(
      'role-form',
      scopeKey,
      (signal) =>
        requestActionPlanAiSuggestion({
          team: resolvedRoleTeam,
          month: activeMonthName,
          year: activeYearNum,
          performanceLevel: resolvedRoleLevel,
          employeeId: null,
          focusKpiKey,
          signal,
        }),
      hasUnsaved,
      (payload) => applyRoleFormAiDraft(payload),
    );
  }, [
    activeMonthName,
    activeYearNum,
    applyRoleFormAiDraft,
    data.kpis,
    description,
    resolvedRoleLevel,
    resolvedRoleTeam,
    runRoleAiRequest,
    selected,
    targetKpiKey,
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

  const gradeStyle = GRADE_STYLES[data.grade];
  const impact = IMPACT_LEVEL_STYLES[data.impactLevel];
  const up = data.changeVsPrev !== null && data.changeVsPrev >= 0;
  const isProblemRole = data.score < 90;
  const monthName = data.monthLabel.split(' ')[0] || data.periodKey;

  const maxCarouselStart = Math.max(0, data.kpis.length - KPI_CARDS_PER_ROW);
  const safeCarouselStart = Math.min(carouselStart, maxCarouselStart);
  const visibleKpis = useMemo(
    () => data.kpis.slice(safeCarouselStart, safeCarouselStart + KPI_CARDS_PER_ROW),
    [data.kpis, safeCarouselStart],
  );
  const hasCarousel = data.kpis.length > KPI_CARDS_PER_ROW;

  const handleSelectKpi = (kpiId: string) => {
    setSelectedId(kpiId);
    const idx = data.kpis.findIndex((k) => k.id === kpiId);
    if (idx >= 0) {
      if (idx < safeCarouselStart) {
        setCarouselStart(idx);
      } else if (idx >= safeCarouselStart + KPI_CARDS_PER_ROW) {
        setCarouselStart(Math.min(maxCarouselStart, idx - KPI_CARDS_PER_ROW + 1));
      }
    }
  };

  const kpiGridColsClass =
    visibleKpis.length === 1
      ? 'grid-cols-1'
      : visibleKpis.length === 2
      ? 'grid-cols-1 sm:grid-cols-2'
      : visibleKpis.length === 3
      ? 'grid-cols-1 sm:grid-cols-3'
      : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4';

  const save = async () => {
    const text = description.trim();
    if (!text) return;
    const chosenKpi =
      data.kpis.find((k) => k.kpiKey === targetKpiKey) ?? selected ?? data.kpis[0];
    const resolvedPeople =
      affectedPerson === 'ALL_LOW'
        ? below90Members.length > 0
          ? below90Members.map((m) => m.personName)
          : data.members.map((m) => m.personName)
        : [affectedPerson];

    const draft: RoleActionDraft = {
      employeeId: data.employeeId,
      personName: data.personName,
      team: data.roleTitle,
      month: monthName,
      description: text,
      owner: owner.trim() || data.roleTitle,
      dueDate,
      status,
      expectedImpact: expectedImpact.trim(),
      linkedKpiKey: chosenKpi?.kpiKey ?? null,
    };
    setSaving(true);
    try {
      await onSaveAction(draft);
      setAddedActions((current) => [
        {
          id: `local-${Date.now()}`,
          title: `${data.roleTitle} Corrective Action`,
          description: draft.description,
          owner: draft.owner,
          dueDate: draft.dueDate || null,
          status: draft.status,
          expectedImpact: draft.expectedImpact || 'Impact to be confirmed',
          linkedKpiName: chosenKpi?.shortName || 'Role Execution',
          affectedPeople: resolvedPeople,
        },
        ...current,
      ]);
      setDescription('');
      setExpectedImpact('');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      data-testid="role-detail-page"
      className="mx-auto max-w-6xl space-y-7 px-4 py-8 sm:px-6 lg:px-8"
    >
      {/* ================================================================== */}
      {/* 1. HEADER — Calm Executive Hierarchy                               */}
      {/* ================================================================== */}
      <header className="rounded-2xl border border-slate-200/85 bg-white p-6 shadow-2xs sm:p-8">
        {/* Top Bar: Breadcrumb + Back Action */}
        <div className="flex min-w-0 flex-col gap-3 border-b border-slate-100 pb-5">
          <nav
            aria-label="Breadcrumb"
            data-testid="role-detail-breadcrumb"
            className="flex flex-wrap items-center gap-1.5 text-xs font-medium text-slate-500"
          >
            <button
              type="button"
              onClick={onNavigateToOverview}
              className="rounded-md px-2 py-1 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
            >
              Overview
            </button>
            <ChevronRight className="size-3.5 text-slate-300" aria-hidden />
            <button
              type="button"
              data-testid="breadcrumb-function"
              onClick={onNavigateToFunction}
              className="rounded-md px-2 py-1 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
            >
              {data.functionName}
            </button>
            <ChevronRight className="size-3.5 text-slate-300" aria-hidden />
            <span className="rounded-md bg-slate-100 px-2.5 py-1 font-semibold text-slate-900">
              {data.roleTitle}
              {data.branchLabel ? ` · ${data.branchLabel}` : ''}
            </span>
          </nav>

          <div className="flex w-full min-w-0 max-w-full flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onNavigateToFunction}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200/90 bg-white px-3 text-xs font-semibold text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50"
            >
              <ArrowLeft className="size-3.5 text-slate-500" aria-hidden />
              <span>Back to {data.functionName}</span>
            </button>
            {toolbar}
          </div>
        </div>

        {/* Main Header Content: Role Title, Person/Count Underneath, Score & Diagnosis */}
        <div className="mt-6 flex flex-col justify-between gap-6 lg:flex-row lg:items-center">
          <div className="max-w-2xl">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span className="font-medium">
                {data.regionName} · {data.monthLabel}
              </span>
              <span className="text-slate-300" aria-hidden>
                ·
              </span>
              <span
                data-testid="role-impact-badge"
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${impact.badgeBg} ${impact.badgeText} ${impact.badgeBorder}`}
              >
                <span className={`size-1.5 rounded-full ${impact.dotColor}`} />
                {data.impactLevel} Impact
              </span>
            </div>

            {/* Role Name as Main Title */}
            <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              {data.roleTitle}
              {data.branchLabel ? (
                <span className="font-semibold text-slate-500"> · {data.branchLabel}</span>
              ) : null}
            </h1>

            {/* Person Name Underneath (or Count if Multiple) */}
            {data.members.length <= 1 ? (
              <p className="mt-1 text-base font-medium text-slate-600">
                {data.personName}
              </p>
            ) : (
              <p className="mt-1.5 inline-flex items-center gap-1.5 text-sm font-medium text-slate-600">
                <Users className="size-4 text-slate-400" aria-hidden />
                <span>
                  {data.headcount} people in {data.branchLabel ?? 'this role'} · {data.below90Count} Average or below
                </span>
              </p>
            )}

            {/* Concise Executive Diagnosis Sentence */}
            <p
              data-testid="role-diagnosis"
              className="mt-3 text-sm leading-relaxed text-slate-600 sm:text-[15px]"
            >
              {data.diagnosis}
            </p>
          </div>

          {/* Right Metric Cluster: Dominant Score, Full-Word Grade, Movement & Gap */}
          <div className="flex shrink-0 flex-wrap items-center gap-5 rounded-2xl border border-slate-200/80 bg-slate-50/60 px-5 py-4 sm:px-6 sm:py-5">
            <div>
              <div className="text-xs font-bold tracking-wider text-slate-400 uppercase">
                {data.headcount > 1 ? 'Combined Score' : 'Role Score'}
              </div>
              <div className="mt-1 flex items-baseline gap-3">
                <p
                  data-testid="role-detail-score"
                  className={`text-4xl font-extrabold tracking-tight tabular-nums sm:text-5xl ${
                    isProblemRole ? 'text-rose-600' : gradeStyle.scoreText
                  }`}
                >
                  {data.score.toFixed(1)}%
                </p>
                <FullWordGradeBadge
                  grade={data.grade}
                  gradeFullLabel={data.gradeFullLabel}
                  size="lg"
                />
              </div>
            </div>

            <div className="hidden h-12 w-px bg-slate-200/80 sm:block" />

            <div className="flex flex-col gap-1.5 text-xs">
              <span
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-semibold tabular-nums ${
                  isProblemRole
                    ? 'border-rose-200/80 bg-rose-50/70 text-rose-700'
                    : 'border-slate-200 bg-white text-slate-700'
                }`}
              >
                <Target
                  className={`size-3.5 ${
                    isProblemRole ? 'text-rose-500' : 'text-slate-400'
                  }`}
                  aria-hidden
                />
                Gap {data.gap.toFixed(1)}%
              </span>

              <span
                className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 font-semibold tabular-nums ${
                  data.changeVsPrev === null
                    ? 'border-slate-200 bg-white text-slate-400'
                    : up
                    ? 'border-emerald-200/80 bg-emerald-50/70 text-emerald-700'
                    : 'border-rose-200/80 bg-rose-50/70 text-rose-700'
                }`}
              >
                {data.changeVsPrev === null ? (
                  <span title="No previous-month data">— No previous-month data</span>
                ) : (
                  <>
                    {up ? (
                      <ArrowUpRight className="size-3.5" aria-hidden />
                    ) : (
                      <ArrowDownRight className="size-3.5" aria-hidden />
                    )}
                    {up ? '+' : ''}
                    {data.changeVsPrev.toFixed(1)}% vs {data.previousMonthLabel}
                  </>
                )}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* ================================================================== */}
      {/* 2. KEY ROLE KPIs — Compact Single-Row Carousel (Worst to Best)     */}
      {/* ================================================================== */}
      <section
        id="presentation-section-role-kpis"
        data-section-label="KPIs"
        aria-labelledby="role-kpis-heading"
        data-testid="role-kpis"
        className="scroll-mt-24 space-y-3"
      >
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex size-7 items-center justify-center rounded-lg border border-blue-200/80 bg-blue-50 text-blue-600">
              <Gauge className="size-3.5" aria-hidden />
            </span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2
                  id="role-kpis-heading"
                  className="text-sm font-bold tracking-tight text-slate-900 sm:text-base"
                >
                  {data.roleTitle} KPIs
                </h2>
                <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs font-semibold text-slate-500">
                  {data.kpis.length} {data.kpis.length === 1 ? 'measure' : 'measures'} · sorted worst to best
                </span>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {biggestGapKpi && (
              <div
                data-testid="biggest-gap-summary-pill"
                className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200/90 bg-rose-50/80 px-2.5 py-1 text-xs font-semibold text-rose-900 shadow-2xs"
              >
                <Flame className="size-3.5 shrink-0 text-rose-600" aria-hidden />
                <span>
                  Biggest Gap Driver:{' '}
                  <strong className="font-extrabold text-rose-700">
                    {biggestGapKpi.shortName}
                  </strong>{' '}
                  (−{biggestGapKpi.pointsLost.toFixed(1)} pts ·{' '}
                  {biggestGapKpi.contributionPct.toFixed(1)}% of{' '}
                  {Math.round(biggestGapKpi.weightPct)}% weight)
                </span>
              </div>
            )}

            {data.kpis.length > 0 && (
              <div
                data-testid="kpi-carousel-controls"
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200/90 bg-white px-2 py-1 shadow-2xs"
              >
                <span className="px-1 text-xs font-bold text-slate-500 tabular-nums">
                  {safeCarouselStart + 1}–
                  {Math.min(data.kpis.length, safeCarouselStart + KPI_CARDS_PER_ROW)} of{' '}
                  {data.kpis.length}
                </span>
                <button
                  type="button"
                  data-testid="kpi-carousel-prev"
                  aria-label="Previous KPI cards"
                  disabled={safeCarouselStart === 0}
                  onClick={() =>
                    setCarouselStart((prev) => Math.max(0, prev - 1))
                  }
                  className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-35"
                >
                  <ChevronLeft className="size-3.5" aria-hidden />
                </button>
                <button
                  type="button"
                  data-testid="kpi-carousel-next"
                  aria-label="Next KPI cards"
                  disabled={safeCarouselStart >= maxCarouselStart}
                  onClick={() =>
                    setCarouselStart((prev) =>
                      Math.min(maxCarouselStart, prev + 1),
                    )
                  }
                  className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-35"
                >
                  <ChevronRight className="size-3.5" aria-hidden />
                </button>
              </div>
            )}
          </div>
        </div>

        {data.kpis.length === 0 ? (
          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 text-sm text-slate-500">
            No KPI series available for this role in the selected month.
          </div>
        ) : (
          <div>
            <div
              role="tablist"
              aria-label="Key Role KPIs"
              className={`grid gap-3 ${kpiGridColsClass}`}
            >
              {visibleKpis.map((kpi) => (
                <SelectableKpiCard
                  key={kpi.id}
                  selected={selected?.id === kpi.id}
                  status={kpi.statusBadge}
                  title={kpi.shortName}
                  titleTooltip={kpi.name}
                  betterDirection={kpi.betterDirection}
                  actual={kpi.actualDisplay}
                  target={kpi.targetDisplay}
                  achievementPct={kpi.achievementPct}
                  gapLabel={kpi.gapLabel}
                  movement={
                    kpi.momDeltaPct !== null ? (
                      <span
                        className={`inline-flex shrink-0 items-center gap-0.5 font-medium tabular-nums ${
                          kpi.isMomGood === true
                            ? 'text-emerald-700'
                            : kpi.isMomGood === false
                            ? 'text-rose-700'
                            : 'text-slate-500'
                        }`}
                      >
                        {kpi.momDeltaPct > 0 ? (
                          <ArrowUpRight className="size-3.5" aria-hidden />
                        ) : kpi.momDeltaPct < 0 ? (
                          <ArrowDownRight className="size-3.5" aria-hidden />
                        ) : null}
                        {kpi.momDeltaPct > 0 ? '+' : ''}
                        {kpi.momDeltaPct.toFixed(1)}% MoM
                      </span>
                    ) : null
                  }
                  biggestGap={kpi.isBiggestGap}
                  biggestGapTestId={`biggest-gap-badge-${kpi.kpiKey}`}
                  weightPct={kpi.weightPct}
                  contributionPct={kpi.contributionPct}
                  pointsLost={kpi.pointsLost}
                  testId={`role-kpi-tab-${kpi.kpiKey}`}
                  onSelect={() => handleSelectKpi(kpi.id)}
                  asTab
                />
              ))}
            </div>

            {/* Carousel Step Dots when > 4 KPIs */}
            {hasCarousel && (
              <div className="mt-2.5 flex items-center justify-center gap-1.5">
                {Array.from({ length: maxCarouselStart + 1 }, (_, stepIdx) => {
                  const isCurrent = stepIdx === safeCarouselStart;
                  return (
                    <button
                      key={stepIdx}
                      type="button"
                      aria-label={`Show KPIs starting at ${stepIdx + 1}`}
                      onClick={() => setCarouselStart(stepIdx)}
                      className={`h-1.5 rounded-full transition-all ${
                        isCurrent
                          ? 'w-5 bg-blue-600'
                          : 'w-1.5 bg-slate-300 hover:bg-slate-400'
                      }`}
                    />
                  );
                })}
              </div>
            )}
          </div>
        )}
      </section>

      {/* ================================================================== */}
      {/* 3. 6-MONTH TREND — Reused 360 Profile Interactive Trend Component  */}
      {/* ================================================================== */}
      {selected && (
        <section
          id="presentation-section-role-trend"
          data-section-label="Trend"
          aria-labelledby="role-trend-heading"
          className="scroll-mt-24 rounded-2xl border border-slate-200/85 bg-white p-6 shadow-2xs sm:p-8"
        >
          <ProfileKpiSixMonthTrend
            kpis={data.kpis}
            selectedId={selected.id}
            onSelectKpi={handleSelectKpi}
          />

          {/* Short, Precise Structural Diagnosis Under the Chart */}
          <div
            data-testid="role-kpi-structural-diagnosis"
            className="mt-5 rounded-xl border border-slate-200/80 bg-slate-50/60 px-4 py-3.5 text-xs leading-relaxed text-slate-700 sm:text-sm"
          >
            <div className="flex items-start gap-2.5">
              <Sparkles
                className="mt-0.5 size-4 shrink-0 text-blue-600"
                aria-hidden
              />
              <div className="space-y-1">
                <p className="font-semibold text-slate-900">{selected.diagnosis}</p>
                {selected.structuralDiagnosis && (
                  <p className="text-slate-600">{selected.structuralDiagnosis}</p>
                )}
              </div>
            </div>
          </div>

          {/* Clean, Non-Repetitive Accountability & Ownership Bar */}
          <div
            data-testid="role-accountability"
            className="mt-4 flex flex-col justify-between gap-3 rounded-xl border border-slate-200/75 bg-white px-4 py-3 text-xs sm:flex-row sm:items-center"
          >
            <div className="flex items-center gap-2 text-slate-600">
              <ShieldCheck className="size-4 shrink-0 text-slate-400" aria-hidden />
              <span className="font-semibold text-slate-800">
                {data.accountabilityGaps[0]?.ownership ||
                  `Accountable owner: ${data.roleTitle} inside ${data.functionName}`}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-1.5">
              {data.accountabilityGaps.slice(0, 3).map((gap) => (
                <span
                  key={gap.id}
                  className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${
                    isProblemRole
                      ? 'border-rose-200/80 bg-rose-50/60 text-rose-700'
                      : 'border-slate-200 bg-slate-50 text-slate-600'
                  }`}
                >
                  <AlertCircle className="size-3 shrink-0" aria-hidden />
                  {gap.statement}
                </span>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ================================================================== */}
      {/* 4. FOCUS COHORT TABLE — People in This Role (Multi-KPI Breakdown)  */}
      {/* ================================================================== */}
      <section
        id="presentation-section-role-members"
        data-section-label="People"
        aria-labelledby="role-members-heading"
        data-testid="role-members-section"
        className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs sm:p-7"
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
          <div>
            <span className="text-xs font-semibold tracking-wider text-amber-700 uppercase">
              Focus Cohort (Score &lt; 90%)
            </span>
            <h2
              id="role-members-heading"
              className="mt-0.5 text-lg font-bold tracking-tight text-slate-900"
            >
              People in This Role — Average and Below
            </h2>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-bold text-amber-800">
              {below90Members.length} of {data.members.length}{' '}
              {data.members.length === 1 ? 'person requires' : 'people require'} action
            </span>

            {data.members.length > below90Members.length && (
              <button
                type="button"
                data-testid="toggle-show-all-members"
                onClick={() => setShowAllMembers((prev) => !prev)}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200/90 bg-slate-50 px-3 text-xs font-bold text-slate-700 transition-colors hover:border-blue-300 hover:bg-white hover:text-blue-600"
              >
                <Users className="size-3.5 text-slate-500" aria-hidden />
                <span>
                  {showAllMembers
                    ? `Show Average & Below Only (${below90Members.length})`
                    : `View All (${data.members.length})`}
                </span>
              </button>
            )}
          </div>
        </div>

        {displayedMembers.length === 0 ? (
          <div className="mt-4 flex flex-col items-center justify-between gap-3 rounded-xl border border-emerald-200/70 bg-emerald-50/40 px-4 py-4 sm:flex-row">
            <div className="flex items-center gap-2.5 text-xs font-medium text-emerald-900 sm:text-sm">
              <CheckCircle2 className="size-4 shrink-0 text-emerald-600" aria-hidden />
              <span>
                No people in this role are Average or below — all {data.members.length}{' '}
                {data.members.length === 1 ? 'person is' : 'people are'} Meeting Expectations
                or Excellent.
              </span>
            </div>
            <button
              type="button"
              onClick={() => setShowAllMembers(true)}
              className="shrink-0 rounded-lg border border-emerald-300 bg-white px-3 py-1.5 text-xs font-bold text-emerald-800 transition-colors hover:bg-emerald-50"
            >
              View All ({data.members.length})
            </button>
          </div>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table
              data-testid="role-members-table"
              className="w-full border-collapse text-left text-sm"
            >
              <thead>
                <tr className="border-b border-slate-200 text-xs font-semibold tracking-wider text-slate-500 uppercase">
                  <th className="py-3 pr-4">Employee</th>
                  <th className="px-4 py-3 text-right">Score</th>
                  {data.kpis.slice(0, 4).map((kpi) => (
                    <th key={kpi.kpiKey} className="px-4 py-3 text-right">
                      {kpi.shortName}
                      <span className="block text-xs font-normal text-slate-400 normal-case">
                        Target: {kpi.targetDisplay}
                      </span>
                    </th>
                  ))}
                  <th className="py-3 pl-4 text-center">Grade</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {visibleMembers.map((member) => {
                  const memberGradeStyle = GRADE_STYLES[member.grade];
                  return (
                    <tr
                      key={member.employeeId}
                      data-testid={`role-member-${member.employeeId}`}
                      className="transition-colors hover:bg-slate-50/80"
                    >
                      {/* Employee Name + Root-Cause Main Issue */}
                      <td className="py-3.5 pr-4">
                        <div className="font-bold text-slate-900">{member.personName}</div>
                        <div className="mt-0.5 max-w-md text-xs text-slate-500">
                          {member.signal}
                        </div>
                      </td>

                      {/* Score + MoM movement */}
                      <td className="px-4 py-3.5 text-right tabular-nums">
                        <div
                          className={`text-base font-extrabold ${memberGradeStyle.scoreText}`}
                        >
                          {member.score.toFixed(1)}%
                        </div>
                        {member.changeVsPrev !== null ? (
                          <div
                            className={`text-xs font-semibold ${
                              member.changeVsPrev >= 0 ? 'text-emerald-600' : 'text-rose-600'
                            }`}
                          >
                            {member.changeVsPrev >= 0
                              ? `+${member.changeVsPrev.toFixed(1)}%`
                              : `${member.changeVsPrev.toFixed(1)}%`}{' '}
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

                      {/* Per-KPI Actual Cells with Diagnostic Coloring */}
                      {(member.kpiCells ?? []).map((cell) => (
                        <td
                          key={cell.kpiKey}
                          className="px-4 py-3.5 text-right tabular-nums"
                        >
                          <span
                            className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-bold ${
                              cell.metTarget === null
                                ? 'bg-slate-100 text-slate-500'
                                : cell.metTarget
                                ? 'bg-emerald-50 text-emerald-700'
                                : (cell.achievementPct ?? 0) < 75
                                ? 'bg-rose-50 text-rose-700'
                                : 'bg-amber-50 text-amber-800'
                            }`}
                          >
                            {cell.actualFormatted}
                          </span>
                        </td>
                      ))}

                      {/* Full-Word Grade */}
                      <td className="py-3.5 pl-4 text-center">
                        <FullWordGradeBadge
                          grade={member.grade}
                          gradeFullLabel={member.gradeFullLabel}
                          size="sm"
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {memberPages.pageCount > 1 && (
              <nav
                data-testid="role-members-pager"
                aria-label="People pages"
                className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3"
              >
                <p className="text-xs font-semibold text-slate-500 tabular-nums" aria-live="polite">
                  {memberPages.rangeStart}–{memberPages.rangeEnd} of {displayedMembers.length}
                </p>
                <div className="inline-flex items-center gap-1.5">
                  <button
                    type="button"
                    data-testid="role-members-prev"
                    aria-label="Previous people"
                    disabled={memberPages.page === 0}
                    onClick={() => setMemberPageState({ listKey: memberListKey, page: Math.max(0, memberPages.page - 1) })}
                    className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-bold text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <ChevronLeft className="size-3.5" aria-hidden />
                    Previous
                  </button>
                  <span className="px-1 text-xs font-bold text-slate-500 tabular-nums">
                    {memberPages.page + 1} / {memberPages.pageCount}
                  </span>
                  <button
                    type="button"
                    data-testid="role-members-next"
                    aria-label="Next people"
                    disabled={memberPages.page >= memberPages.pageCount - 1}
                    onClick={() => setMemberPageState({ listKey: memberListKey, page: Math.min(memberPages.pageCount - 1, memberPages.page + 1) })}
                    className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-bold text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Next
                    <ChevronRight className="size-3.5" aria-hidden />
                  </button>
                </div>
              </nav>
            )}
          </div>
        )}
      </section>

      {/* ================================================================== */}
      {/* 5A. 1-ON-1 COACHING & REMEDIATION — Individual Action Plan         */}
      {/* ================================================================== */}
      {((showActionSection(displayedIndividualCards.length, presentationMode) &&
        displayedIndividualCards.length > 0) ||
        (!presentationMode && dismissedIndIds.length > 0)) && (
        <section
          id="presentation-section-role-coaching"
          data-section-label="Coaching"
          aria-labelledby="role-individual-action-plan-heading"
          data-testid="role-individual-action-plan-section"
          className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs sm:p-7"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-4">
            <div>
              <span className="text-xs font-semibold tracking-wider text-blue-600 uppercase">
                1-on-1 Coaching &amp; Remediation
              </span>
              <h2
                id="role-individual-action-plan-heading"
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
                  One action card per employee shown above · Click &ldquo;Edit&rdquo; on any card to customize &amp; save
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
          <div
            className={`mt-5 grid grid-cols-1 items-start gap-4 ${
              displayedIndividualCards.length > 1 ? 'md:grid-cols-2' : 'md:grid-cols-1'
            }`}
          >
            {displayedIndividualCards.map((card) => {
              const isEditing =
                showPresentationControl(presentationMode) && editingIndividualId === card.id;
              const isConfirmingDelete =
                showPresentationControl(presentationMode) && confirmDeleteIndId === card.employeeId;
              const isDeleting = deletingIndId === card.employeeId;
              const deleteError = indDeleteError[card.employeeId];
              const cardGradeStyle = GRADE_STYLES[card.grade];
              const indAiTargetKey = `ind:${card.id}`;
              const indAiState = aiStateByTarget[indAiTargetKey];
              const indFeedback = indSaveFeedback[card.id];

              const isEvidenceOpen = Boolean(expandedEvidenceIds[card.id]);
              const evidencePanelId = `role-ind-evidence-panel-${card.id}`;
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
                  data-testid={`role-individual-action-card-${card.employeeId}`}
                  className="flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-slate-50/50 p-5 transition-all hover:bg-white hover:shadow-xs"
                >
                  <div>
                    {/* 1. Score and change */}
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base font-bold text-slate-900">
                          {card.personName}
                        </h3>
                        <span
                          className={`text-sm font-extrabold tabular-nums ${cardGradeStyle.scoreText}`}
                        >
                          {card.score.toFixed(1)}%
                        </span>
                        <FullWordGradeBadge
                          grade={card.grade}
                          gradeFullLabel={card.gradeFullLabel}
                          size="sm"
                        />
                      </div>
                      <span
                        data-testid={`role-individual-score-change-${card.employeeId}`}
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
                      data-testid={`role-individual-main-issue-${card.employeeId}`}
                      className="mt-3 rounded-xl border border-rose-200/70 bg-rose-50/50 px-3.5 py-2.5 text-xs text-slate-700"
                    >
                      <span className="font-bold text-rose-800">
                        <AlertTriangle
                          className="mr-1 inline size-3.5 text-rose-600"
                          aria-hidden
                        />
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

                    {/* 3. Next step (remains visible & editable during AI loading and errors) */}
                    {isEditing ? (
                      <div className="mt-3 space-y-2.5 rounded-xl border border-blue-200 bg-white p-3">
                        <div>
                          <label className="block text-xs font-bold text-slate-600">
                            Main Issue
                          </label>
                          <input
                            type="text"
                            value={draftIndMainIssue}
                            onChange={(e) => setDraftIndMainIssue(e.target.value)}
                            className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-bold text-slate-600">
                            Corrective Action
                          </label>
                          <textarea
                            rows={2}
                            value={draftIndAction}
                            onChange={(e) => setDraftIndAction(e.target.value)}
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
                              value={draftIndOwner}
                              onChange={(e) => setDraftIndOwner(e.target.value)}
                              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-bold text-slate-600">
                              Expected Impact
                            </label>
                            <input
                              type="text"
                              value={draftIndImpact}
                              onChange={(e) => setDraftIndImpact(e.target.value)}
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
                            onClick={() => void saveEditIndividual(card)}
                            className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1 text-xs font-bold text-white hover:bg-blue-700"
                          >
                            <Check className="size-3.5" aria-hidden />
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
                          {card.suggested ? (
                            <span className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-xs font-medium text-slate-600">
                              Suggested — not saved
                            </span>
                          ) : (
                            <span className="rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-xs font-medium text-emerald-700">
                              Saved
                            </span>
                          )}
                        </div>
                        <p className="text-xs font-medium leading-relaxed text-slate-800 sm:text-sm">
                          {card.actionText}
                        </p>
                        <div className="flex flex-wrap items-center gap-2 text-xs">
                          <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 font-semibold text-slate-700">
                            <UserCheck className="size-3.5 text-blue-600" aria-hidden />
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
                            applyRoleIndividualAiDraft(card, indAiState.payload);
                          }
                        }}
                        onApplyEvidenceStep={() => {
                          if (indAiState?.payload) {
                            applyRoleIndividualEvidenceFallback(card, indAiState.payload);
                          }
                        }}
                        onDiscard={() =>
                          discardAiTarget(indAiTargetKey, () => {
                            setDraftIndAction(card.actionText);
                            setDraftIndMainIssue(card.mainIssue);
                            setDraftIndOwner(card.owner);
                            setDraftIndImpact(card.expectedImpact);
                            setDraftIndFollowUpLabel(card.followUpLabel ?? '');
                            setDraftIndObservationStatus(card.observationStatus);
                            setEditingIndividualId((prev) => (prev === card.id ? null : prev));
                          })
                        }
                        onRetry={() => triggerRoleIndividualAi(card)}
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
                              ariaLabel={`Generate AI recommendation for ${card.personName}`}
                              onClick={() => triggerRoleIndividualAi(card)}
                            />
                            <AiStatusInline
                              loading={indAiState?.loading}
                              payload={indAiState?.payload}
                              error={indAiState?.error}
                              draftApplied={indAiState?.draftApplied}
                              presentationMode={presentationMode}
                              onRetry={() => triggerRoleIndividualAi(card)}
                              onDismiss={() => discardAiTarget(indAiTargetKey)}
                            />
                            {!isEditing && (
                              <>
                                {card.suggested && (
                                  <button
                                    type="button"
                                    disabled={savingIndividualId === card.id}
                                    data-testid={`quick-save-role-individual-action-${card.employeeId}`}
                                    aria-label={`Save action plan for ${card.personName}`}
                                    onClick={() => void quickSaveRoleIndividual(card)}
                                    className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 transition-colors hover:bg-emerald-100 disabled:opacity-50"
                                  >
                                    <Check className="size-3" aria-hidden />
                                    <span>{savingIndividualId === card.id ? 'Saving…' : 'Save'}</span>
                                  </button>
                                )}
                                <button
                                  type="button"
                                  onClick={() => startEditIndividual(card)}
                                  className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 transition-colors hover:border-blue-300 hover:text-blue-600"
                                >
                                  <Edit3 className="size-3" aria-hidden />
                                  <span>Edit</span>
                                </button>
                                <button
                                  type="button"
                                  data-testid={`delete-role-individual-action-${card.employeeId}`}
                                  onClick={() => setConfirmDeleteIndId(card.employeeId)}
                                  className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-2.5 py-1 text-xs font-semibold text-rose-700 transition-colors hover:bg-rose-50"
                                >
                                  <Trash2 className="size-3" aria-hidden />
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
                        aria-label={`Confirm delete action for ${card.personName}`}
                        className="mt-3 rounded-xl border border-rose-200 bg-rose-50/80 p-3"
                      >
                        <p className="text-xs font-semibold text-rose-900">
                          Delete this individual action plan for {card.personName}?
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
                            data-testid={`confirm-delete-role-individual-action-${card.employeeId}`}
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
                      testIdPrefix="role-individual"
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
      {/* 5. COHORT-WIDE INTERVENTIONS — Role-Level Action Plan              */}
      {/* ================================================================== */}
      {(showActionSection(localActions.length, presentationMode) ||
        (!presentationMode && restorableDismissedRoleIds.length > 0)) ? (
      <section
        id="presentation-section-role-actions"
        data-section-label="Actions"
        aria-labelledby="role-actions-heading"
        data-testid="role-actions-section"
        className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs sm:p-8"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-5">
          <div>
            <span className="text-xs font-semibold tracking-wider text-emerald-600 uppercase">
              Cohort-Wide Interventions
            </span>
            <h2
              id="role-actions-heading"
              className="mt-0.5 text-lg font-bold tracking-tight text-slate-900 sm:text-xl"
            >
              Role-Level Action Plan
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Systemic interventions linked directly to the affected KPIs and people in {data.roleTitle}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {showPresentationControl(presentationMode) && restorableDismissedRoleIds.length > 0 && (
              <button
                type="button"
                onClick={restoreDismissedRoleActions}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-700 hover:border-blue-300 hover:text-blue-700"
              >
                <RotateCcw className="size-3.5" aria-hidden="true" />
                <span>Restore {restorableDismissedRoleIds.length} dismissed</span>
              </button>
            )}
            <span className="rounded-full border border-slate-200/80 bg-slate-50 px-3 py-1 text-xs font-bold text-slate-700">
              {localActions.length} {localActions.length === 1 ? 'action' : 'actions'}
            </span>
          </div>
        </div>

        {/* Existing Actions as Cohort-Wide Intervention Cards */}
        {localActions.length === 0 ? (
          <div className="mt-5 rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-6 text-center">
            <p className="text-sm font-medium text-slate-600">
              No corrective actions recorded for this role yet.
            </p>
            {showPresentationControl(presentationMode) && restorableDismissedRoleIds.length > 0 && (
              <button
                type="button"
                onClick={restoreDismissedRoleActions}
                className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:border-blue-300 hover:text-blue-700"
              >
                <RotateCcw className="size-3.5" aria-hidden="true" />
                <span>Restore dismissed suggestions</span>
              </button>
            )}
          </div>
        ) : (
          <ul
            className={`mt-6 grid grid-cols-1 items-start gap-4 ${
              localActions.length > 2
                ? 'lg:grid-cols-3'
                : localActions.length > 1
                ? 'lg:grid-cols-2'
                : 'lg:grid-cols-1'
            }`}
          >
            {localActions.map((action) => {
              const linkedKpiLabel =
                action.linkedKpiName ||
                selected?.shortName ||
                data.accountableKpis[0] ||
                'Role Execution';
              const peopleList =
                action.affectedPeople && action.affectedPeople.length > 0
                  ? action.affectedPeople
                  : below90Members.length > 0
                  ? below90Members.map((m) => m.personName)
                  : data.members.map((m) => m.personName);

              const isEditingRoleAct =
                showPresentationControl(presentationMode) && editingRoleActionId === action.id;
              const isConfirmingRoleDelete =
                showPresentationControl(presentationMode) && confirmDeleteRoleId === action.id;
              const isDeletingRole = deletingRoleId === action.id;
              const cardRoleDeleteError = roleDeleteError[action.id];
              const roleActAiKey = `role-act:${action.id}`;
              const roleActAiState = aiStateByTarget[roleActAiKey];
              const roleSaveFb = roleSaveFeedback[action.id];

              return (
                <li
                  key={action.id}
                  data-testid={`role-action-${action.id}`}
                  className="flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-slate-50/50 p-5 transition-all hover:bg-white hover:shadow-xs"
                >
                  <div>
                    {/* Card Top: Whole-Role Action Badge + Status Pill */}
                    <div className="flex items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-2.5 py-0.5 text-xs font-bold text-blue-700">
                        <Layers className="size-3" aria-hidden />
                        {action.suggested ? 'Suggested action — not saved' : 'Whole-Role Action'}
                      </span>

                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                          action.status === 'In Progress'
                            ? 'bg-amber-100 text-amber-800'
                            : action.status === 'Completed'
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-slate-200 text-slate-700'
                        }`}
                      >
                        {action.suggested ? 'Suggestion' : action.status}
                      </span>
                    </div>

                    {showPresentationControl(presentationMode) && (
                      <AiRecommendationBanner
                        inlineStatusHandled
                        loading={roleActAiState?.loading}
                        payload={roleActAiState?.payload}
                        error={roleActAiState?.error}
                        needsOverwriteConfirm={roleActAiState?.needsOverwriteConfirm}
                        draftApplied={roleActAiState?.draftApplied}
                        presentationMode={presentationMode}
                        onApplyDraft={() => {
                          if (roleActAiState?.payload) {
                            applyRoleActionAiDraft(action, roleActAiState.payload);
                          }
                        }}
                        onApplyEvidenceStep={() => {
                          if (roleActAiState?.payload) {
                            applyRoleActionEvidenceFallback(action, roleActAiState.payload);
                          }
                        }}
                        onDiscard={() =>
                          discardAiTarget(roleActAiKey, () => {
                            setDraftRoleDesc(action.description);
                          })
                        }
                        onRetry={() => triggerRoleActionAi(action)}
                      />
                    )}

                    {isEditingRoleAct ? (
                      <div className="mt-3 space-y-2.5 rounded-xl border border-blue-200 bg-white p-3">
                        <div>
                          <label className="block text-xs font-bold text-slate-600">
                            Action Description
                          </label>
                          <textarea
                            rows={2}
                            value={draftRoleDesc}
                            onChange={(e) => setDraftRoleDesc(e.target.value)}
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
                              value={draftRoleOwner}
                              onChange={(e) => setDraftRoleOwner(e.target.value)}
                              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-bold text-slate-600">
                              Status
                            </label>
                            <select
                              value={draftRoleStatus}
                              onChange={(e) =>
                                setDraftRoleStatus(e.target.value as RoleActionDraft['status'])
                              }
                              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                            >
                              <option value="Open">Open</option>
                              <option value="In Progress">In Progress</option>
                              <option value="Completed">Completed</option>
                            </select>
                          </div>
                          <div>
                            <label className="block text-xs font-bold text-slate-600">
                              Due Date
                            </label>
                            <input
                              type="date"
                              value={draftRoleDueDate}
                              onChange={(e) => setDraftRoleDueDate(e.target.value)}
                              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-bold text-slate-600">
                              Expected Impact
                            </label>
                            <input
                              type="text"
                              value={draftRoleImpact}
                              onChange={(e) => setDraftRoleImpact(e.target.value)}
                              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                            />
                          </div>
                        </div>
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => setEditingRoleActionId(null)}
                            className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={() => void saveEditRoleAction(action)}
                            className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1 text-xs font-bold text-white hover:bg-blue-700"
                          >
                            <Check className="size-3.5" aria-hidden />
                            <span>Save Role Action</span>
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        {/* Action Title */}
                        <h3 className="mt-3 text-sm font-bold leading-snug text-slate-900">
                          {action.title || action.description}
                        </h3>

                        {/* Inner Target KPI & Scope Box (matches Team-Level Action Plan) */}
                        <div className="mt-3 space-y-1.5 rounded-xl border border-slate-200/80 bg-white p-3 text-xs">
                          <div
                            data-testid={`action-linked-kpi-${action.id}`}
                            className="font-semibold text-slate-800"
                          >
                            <Target
                              className="mr-1 inline size-3.5 text-blue-600"
                              aria-hidden
                            />
                            <span>Affects KPI: {linkedKpiLabel}</span>
                          </div>
                          {peopleList.length > 0 && (
                            <div
                              data-testid={`action-affected-people-${action.id}`}
                              className="text-slate-500"
                            >
                              People: {peopleList.join(', ')}
                            </div>
                          )}
                          {action.title && action.description !== action.title && (
                            <div className="border-t border-slate-100 pt-1.5 text-xs leading-relaxed text-slate-500">
                              {action.description}
                            </div>
                          )}
                        </div>
                      </>
                    )}

                    {roleSaveFb && !isEditingRoleAct && (
                      <p
                        role="status"
                        className={`mt-2 text-xs font-medium ${
                          roleSaveFb.type === 'error' ? 'text-rose-700' : 'text-emerald-700'
                        }`}
                      >
                        {roleSaveFb.message}
                      </p>
                    )}
                  </div>

                  {/* Metadata Footer: Owner & Expected Impact */}
                  <dl className="mt-4 flex flex-col gap-2 border-t border-slate-200/70 pt-3 text-xs">
                    <div className="flex items-center justify-between text-slate-700">
                      <dt className="font-medium text-slate-400">Owner</dt>
                      <dd className="font-bold text-slate-800">{action.owner}</dd>
                    </div>
                    {!action.suggested && showStoredPlaceholder(action.dueDate?.trim() || 'No due date', presentationMode) && (
                      <div className="flex items-center justify-between text-slate-700">
                        <dt className="font-medium text-slate-400">Due</dt>
                        <dd className="font-bold text-slate-800">{action.dueDate?.trim() || 'No due date'}</dd>
                      </div>
                    )}
                    <div className="flex items-center justify-between">
                      <dt className="font-medium text-slate-400">Expected Impact</dt>
                      <dd className="inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-extrabold text-emerald-700">
                        <CheckCircle2 className="size-3" aria-hidden />
                        {action.expectedImpact}
                      </dd>
                    </div>
                  </dl>

                  {isConfirmingRoleDelete && (
                    <div
                      role="alertdialog"
                      aria-label={`Confirm delete role action ${action.title || action.description}`}
                      className="mt-3 rounded-xl border border-rose-200 bg-rose-50/80 p-3"
                    >
                      <p className="text-xs font-semibold text-rose-900">
                        Delete this role-level action?
                      </p>
                      {cardRoleDeleteError && (
                        <p role="alert" className="mt-1 text-xs font-medium text-rose-700">
                          {cardRoleDeleteError}
                        </p>
                      )}
                      <div className="mt-2 flex justify-end gap-2">
                        <button
                          type="button"
                          disabled={isDeletingRole}
                          onClick={() => setConfirmDeleteRoleId(null)}
                          className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          disabled={isDeletingRole}
                          data-testid={`confirm-delete-role-action-${action.id}`}
                          onClick={() => confirmDeleteRoleAction(action)}
                          className="rounded-lg bg-rose-600 px-3 py-1 text-xs font-bold text-white hover:bg-rose-700 disabled:opacity-50"
                        >
                          {isDeletingRole ? 'Deleting…' : 'Delete Action'}
                        </button>
                      </div>
                    </div>
                  )}

                  {showPresentationControl(presentationMode) && (
                    <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-slate-200/70 pt-3">
                      <AiRecommendIconButton
                        compact
                        loading={roleActAiState?.loading}
                        presentationMode={presentationMode}
                        ariaLabel={`Generate AI recommendation for ${action.title || action.description}`}
                        onClick={() => triggerRoleActionAi(action)}
                      />
                      <AiStatusInline
                        loading={roleActAiState?.loading}
                        payload={roleActAiState?.payload}
                        error={roleActAiState?.error}
                        draftApplied={roleActAiState?.draftApplied}
                        presentationMode={presentationMode}
                        onRetry={() => triggerRoleActionAi(action)}
                        onDismiss={() => discardAiTarget(roleActAiKey)}
                      />
                      {!isEditingRoleAct && (
                        <>
                          {action.suggested && (
                            <button
                              type="button"
                              disabled={savingRoleActionId === action.id}
                              data-testid={`quick-save-role-action-${action.id}`}
                              onClick={() => void quickSaveRoleAction(action)}
                              className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700 transition-colors hover:bg-emerald-100 disabled:opacity-50"
                            >
                              <Check className="size-3" aria-hidden />
                              <span>{savingRoleActionId === action.id ? 'Saving…' : 'Save'}</span>
                            </button>
                          )}
                          <button
                            type="button"
                            data-testid={`edit-role-action-${action.id}`}
                            onClick={() => startEditRoleAction(action)}
                            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-semibold text-slate-600 transition-colors hover:border-blue-300 hover:text-blue-600"
                          >
                            <Edit3 className="size-3" aria-hidden />
                            <span>Edit</span>
                          </button>
                          <button
                            type="button"
                            data-testid={`delete-role-action-${action.id}`}
                            onClick={() => setConfirmDeleteRoleId(action.id)}
                            className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-2 py-1 text-xs font-semibold text-rose-700 transition-colors hover:bg-rose-50"
                          >
                            <Trash2 className="size-3" aria-hidden />
                            <span>Delete</span>
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        {showPresentationControl(presentationMode) && (
        <form
          data-testid="role-action-form"
          className="mt-6 rounded-2xl border border-slate-200/85 bg-slate-50/50 p-5"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-xs font-bold tracking-wider text-slate-700 uppercase">
              Add Corrective Action
            </h3>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium text-slate-500">
                Links directly to KPI &amp; people in {data.roleTitle}
              </span>
              <AiRecommendIconButton
                loading={aiStateByTarget['role-form']?.loading}
                presentationMode={presentationMode}
                ariaLabel={`Generate AI recommendation for ${data.roleTitle}`}
                onClick={triggerRoleFormAi}
              />
            </div>
          </div>

          <AiRecommendationBanner
            loading={aiStateByTarget['role-form']?.loading}
            payload={aiStateByTarget['role-form']?.payload}
            error={aiStateByTarget['role-form']?.error}
            needsOverwriteConfirm={aiStateByTarget['role-form']?.needsOverwriteConfirm}
            draftApplied={aiStateByTarget['role-form']?.draftApplied}
            presentationMode={presentationMode}
            onApplyDraft={() => {
              const payload = aiStateByTarget['role-form']?.payload;
              if (payload) applyRoleFormAiDraft(payload);
            }}
            onDiscard={() =>
              discardAiTarget('role-form', () => {
                setDescription('');
              })
            }
            onRetry={triggerRoleFormAi}
          />

          <div className="mt-3.5 grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
            <label className="block text-xs font-semibold text-slate-700 sm:col-span-2 lg:col-span-3">
              Description
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                required
                rows={2}
                placeholder="Describe the corrective action and target workflow adjustment..."
                className={`${fieldClass} py-2`}
              />
            </label>

            <label className="block text-xs font-semibold text-slate-700">
              Target KPI
              <select
                value={targetKpiKey || selected?.kpiKey || ''}
                onChange={(event) => setTargetKpiKey(event.target.value)}
                className={`${fieldClass} h-9`}
              >
                {data.kpis.map((kpi) => (
                  <option key={kpi.kpiKey} value={kpi.kpiKey}>
                    {kpi.shortName} ({kpi.actualDisplay} vs {kpi.targetDisplay})
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-xs font-semibold text-slate-700">
              Affected person
              <select
                value={affectedPerson}
                onChange={(event) => setAffectedPerson(event.target.value)}
                className={`${fieldClass} h-9`}
              >
                <option value="ALL_LOW">
                  {below90Members.length > 0
                    ? `All Average & Below (${below90Members.map((m) => m.personName).join(', ')})`
                    : `All in ${data.roleTitle}`}
                </option>
                {data.members.map((member) => (
                  <option key={member.employeeId} value={member.personName}>
                    {member.personName} ({member.score.toFixed(1)}%)
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-xs font-semibold text-slate-700">
              Owner
              <input
                value={owner}
                onChange={(event) => setOwner(event.target.value)}
                className={`${fieldClass} h-9`}
              />
            </label>

            <label className="block text-xs font-semibold text-slate-700">
              Due date
              <input
                type="date"
                value={dueDate}
                onChange={(event) => setDueDate(event.target.value)}
                className={`${fieldClass} h-9`}
              />
            </label>

            <label className="block text-xs font-semibold text-slate-700">
              Status
              <select
                value={status}
                onChange={(event) =>
                  setStatus(event.target.value as RoleActionDraft['status'])
                }
                className={`${fieldClass} h-9`}
              >
                <option>Open</option>
                <option>In Progress</option>
                <option>Completed</option>
              </select>
            </label>

            <label className="block text-xs font-semibold text-slate-700">
              Expected impact
              <input
                value={expectedImpact}
                onChange={(event) => setExpectedImpact(event.target.value)}
                placeholder="e.g., +2.5% role score lift"
                className={`${fieldClass} h-9`}
              />
            </label>
          </div>

          <div className="mt-4 flex justify-end">
            <button
              type="submit"
              data-testid="save-role-action"
              disabled={saving || !description.trim()}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-blue-600 px-4 text-xs font-bold text-white shadow-2xs transition-colors hover:bg-blue-700 disabled:opacity-40"
            >
              <Plus className="size-3.5" aria-hidden />
              <span>{saving ? 'Saving…' : 'Add action'}</span>
            </button>
          </div>
        </form>
        )}
      </section>
      ) : null}
    </div>
  );
}
