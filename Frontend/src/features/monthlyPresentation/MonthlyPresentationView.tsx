import { useCallback, useEffect, useMemo, useState } from 'react';
import './macCursor.css';
import { useLocation, useNavigate, useParams, useSearchParams, type SetURLSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/auth';
import { useUserRole } from '../../context/RoleContext';
import { directorScope } from '../../lib/directorScope';
import { canSeeSummaryActionAnalytics, isFunctionViewerRole, readAccessibleFunctions } from '../../lib/access';
import { usePerformanceCatalog } from '../../hooks/api/usePerformanceCatalog';
import {
  SUMMARY_BRANCHES,
  composeExecutiveSummary,
  normalizeRegion,
  periodFromKey as execPeriodFromKey,
  projectExecRecordForBranch,
  summarizeActions,
  toExecRecords,
  type ExecRecord,
  type FollowUpAction,
} from '../executive/compose';
import type { TeamFunctionMap } from '../insights/filterCascade';
import { apiFetch } from '../../lib/apiClient';
import {
  businessTeamName,
  distinctCatalogTeams,
  legacySharedTeamRedirect,
  mergedTeamName,
  parseTeamCountry,
  presentationTeamName,
  recordMatchesCatalogTeam,
  sameCountryBusinessTeam,
  sameMergedTeam,
} from '../team/countryTeamIdentity';
import { useSummaryRecords } from '../executive/useSummaryRecords';
import { useActionStore } from '../../hooks/useActionStore';
import {
  adaptSummaryToMonthlyOverview,
  type FunctionOverviewItem,
  type MonthlyOverviewData,
} from './monthlyOverviewData';
import {
  buildFunctionDeepDiveFromRecords,
  normalizeFunctionSlug,
  slugifyIdentifier,
  type CallCenterDeepDiveData,
} from './callCenterDeepDiveData';
import {
  buildTeamDeepDiveFromRecords,
  encodeIndividualActionMeta,
  type IndividualActionPlanCard,
  type TeamDeepDiveData,
  type TeamLevelActionPlanCard,
} from './teamDeepDiveData';
import {
  buildRoleDetail,
  hasRoleDetailForSlug,
  isRoleBasedFunction,
  recordMatchesRole,
  resolveRoleCards,
  type RoleActionDraft,
  type RoleAssignedAction,
} from './roleDetailData';
import { MonthlyReviewLoading } from './components/MonthlyReviewLoading';
import {
  FunctionsOverviewSection,
  GradeDistributionSection,
  MonthlyOverviewHeader,
  OverallCompanyPerformanceCard,
  RegionPerformanceShareSection,
  ScoreDriversSection,
  SixMonthTrendCard,
  TeamsAtRiskSection,
} from './components/MonthlyOverviewSections';
import CallCenterDeepDiveView from './components/CallCenterDeepDiveView';
import FunctionDeepDiveView from './components/FunctionDeepDiveView';
import {
  PresentationControlBar,
  type AgendaTimelineFunction,
} from './components/PresentationControlBar';
import RoleDetailView from './components/RoleDetailView';
import TeamDeepDiveView from './components/TeamDeepDiveView';
import { isMonthAvailable, periodFromKey } from './model';
import { presentationMonthOptions, stepPresentation } from './presentationControls';
import { ContextualAssistantPanel } from '../../components/ai/ContextualAssistantPanel';
import { isHiddenTeam } from '../../components/common/sidebarTeamItems';
import { CALL_CENTER_TEAM, canonicalTeamName, type PMSAction } from '../../types';
import CorrectiveActionInsightsCard from '../../components/executive/v1/CorrectiveActionInsightsCard';
import type { PageContextV1 } from '../ai/types';
import { ExecutiveEmployeeReview, ExecutiveFunctionReview, ExecutiveTeamDecisions, reviewButtonClass } from '../executive/ExecutiveReviewDetails';
import { actionMatchesRecord, isSavedRoleIntervention, type ReviewUnit } from '../executive/executiveReviewModel';

const TEAM_ACTION_PLANS_STORAGE_KEY = 'pms_team_action_plans_v1';
const ACTION_UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

interface TeamPlanItemApiRow {
  id: string;
  card_id: string;
  team: string;
  region?: string | null;
  month: string;
  year: number;
  title: string;
  target_kpi: string;
  scope_description: string;
  owner: string;
  status: TeamLevelActionPlanCard['status'];
  due_date?: string | null;
  expected_team_impact: string;
  is_deleted?: boolean;
}

const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

function resolvePeriodMonthName(periodMonth?: number | string, monthLabel?: string): string {
  if (typeof periodMonth === 'number' && periodMonth >= 1 && periodMonth <= 12) {
    return MONTH_NAMES[periodMonth - 1];
  }
  if (typeof periodMonth === 'string' && periodMonth.trim()) {
    const trimmed = periodMonth.trim();
    const numeric = Number(trimmed);
    if (Number.isInteger(numeric) && numeric >= 1 && numeric <= 12) {
      return MONTH_NAMES[numeric - 1];
    }
    return trimmed;
  }
  const labelMonth = String(monthLabel ?? '').trim().split(/\s+/)[0];
  return labelMonth || 'September';
}

function teamPlanScopeKey(
  team: string,
  month: string,
  year: number,
  region: string,
): string {
  return `${region.toUpperCase()}::${team.trim().toLowerCase()}::${year}-${month.trim().toLowerCase()}`;
}

function readStoredTeamPlans(scopeKey: string): TeamLevelActionPlanCard[] {
  try {
    const raw = window.localStorage.getItem(TEAM_ACTION_PLANS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Record<string, TeamLevelActionPlanCard[]>;
    const items = parsed?.[scopeKey];
    return Array.isArray(items) ? items : [];
  } catch {
    return [];
  }
}

function writeStoredTeamPlans(
  scopeKey: string,
  items: TeamLevelActionPlanCard[],
): void {
  try {
    const raw = window.localStorage.getItem(TEAM_ACTION_PLANS_STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as Record<string, TeamLevelActionPlanCard[]>) : {};
    const next = parsed && typeof parsed === 'object' ? { ...parsed, [scopeKey]: items } : { [scopeKey]: items };
    window.localStorage.setItem(TEAM_ACTION_PLANS_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Ignore storage quota or SSR issues
  }
}

function mergeTeamPlanItems(
  base: TeamLevelActionPlanCard[],
  overlay: TeamLevelActionPlanCard[],
): TeamLevelActionPlanCard[] {
  const byId = new Map<string, TeamLevelActionPlanCard>();
  for (const item of base) {
    byId.set(item.id, item);
  }
  for (const item of overlay) {
    byId.set(item.id, item);
  }
  return Array.from(byId.values());
}

export type MonthlyRegionFilter = 'EGY' | 'UAE' | 'ALL';

export interface MonthlyPresentationViewProps {
  /** Optional API-adapted or custom data override */
  data?: MonthlyOverviewData;
  /** Optional Call Center Deep Dive data override */
  callCenterDeepDiveData?: CallCenterDeepDiveData;
  /** Optional Team Deep Dive data override */
  teamDeepDiveData?: TeamDeepDiveData;
  /** Optional handler invoked when a Function card is clicked */
  onSelectFunction?: (fn: FunctionOverviewItem) => void;
  today?: Date;
  inlineAnalysis?: { searchParams: URLSearchParams; setSearchParams: SetURLSearchParams };
}

function TeamsWithoutMonthlyData({
  teams,
  periodLabel,
}: {
  teams: Array<{ team: string; region: string | null }>;
  periodLabel: string;
}) {
  if (!teams.length) return null;
  return (
    <section
      data-testid="monthly-teams-without-data"
      aria-label={`Teams without data for ${periodLabel}`}
      className="rounded-2xl border border-amber-200 bg-amber-50/70 p-4"
    >
      <h2 className="text-sm font-bold text-amber-950">Teams without data for {periodLabel}</h2>
      <p className="mt-1 text-sm text-amber-900">
        These active teams are in your authorized scope, but no results were uploaded for this period.
      </p>
      <ul className="mt-3 flex flex-wrap gap-2">
        {teams.map((team) => (
          <li key={`${team.team}:${team.region ?? ''}`} className="rounded-full border border-amber-200 bg-white px-3 py-1 text-xs font-semibold text-amber-950">
            {presentationTeamName(team.team)}
          </li>
        ))}
      </ul>
    </section>
  );
}

interface RawFollowUpActionItem {
  id?: string;
  employee_id?: string | null;
  employee_name?: string | null;
  team?: string | null;
  region?: string | null;
  month?: string;
  manager_action?: string;
  manager_notes?: string;
  timestamp?: string;
  status?: string;
  due_date?: string | null;
  owner?: { id: string; name: string } | null;
  linked_kpi_key?: string | null;
  completed_at?: string | null;
  follow_up_state?: string | null;
}

const KNOWN_ACTION_TYPES = ['Coaching', 'Training', 'Reward', 'Monitor', 'PIP'] as const;
const LEGACY_PIP_TYPES = new Set(['SIP', 'PI', 'Suspension', 'Warning']);

function rawFollowUpToFollowUpAction(item: RawFollowUpActionItem): FollowUpAction {
  let actionType = 'Coaching';
  let actionText = item.manager_action || '';
  const sepIdx = actionText.indexOf(': ');
  if (sepIdx > 0) {
    const typeStr = actionText.substring(0, sepIdx);
    const rest = actionText.substring(sepIdx + 2);
    if (KNOWN_ACTION_TYPES.includes(typeStr as (typeof KNOWN_ACTION_TYPES)[number])) {
      actionType = typeStr;
      actionText = rest;
    } else if (LEGACY_PIP_TYPES.has(typeStr)) {
      actionType = 'PIP';
      actionText = rest;
    } else if (typeStr === 'SOP Review') {
      actionType = 'Training';
      actionText = rest;
    }
  }
  return {
    id: item.id || `${item.employee_id || 'plan'}_${item.month || ''}_${item.timestamp || ''}`,
    title: actionText || actionType,
    action_type: actionType,
    action_text: actionText,
    team: item.team || null,
    region: item.region || null,
    employee_name: item.employee_name || null,
    owner: item.owner ?? null,
    due_date: item.due_date ?? null,
    status: item.status ?? 'Open',
    follow_up_state: item.follow_up_state ?? null,
    completed_at: item.completed_at ?? null,
    employee_id: item.employee_id || null,
    month: item.month,
    created_at: item.timestamp || '',
    root_cause_note: item.manager_notes || '',
    linked_kpi_key: item.linked_kpi_key ?? null,
  };
}

function pmsActionToFollowUp(action: PMSAction): FollowUpAction {
  return {
    id: action.id,
    title: action.action_text || action.action_type,
    action_type: action.action_type,
    action_text: action.action_text,
    team: action.team || null,
    employee_name: action.employee_name || null,
    owner: action.owner ?? null,
    due_date: action.due_date ?? null,
    status: action.status ?? 'Open',
    follow_up_state: action.follow_up_state ?? null,
    completed_at: action.completed_at ?? null,
    employee_id: action.employee_id || null,
    month: action.month,
    created_at: action.created_at,
    root_cause_note: action.root_cause_note,
    linked_kpi_key: action.linked_kpi_key ?? null,
  };
}

function EgyptFlag({ className = 'size-4 shrink-0 rounded-xs' }: { className?: string }) {
  return (
    <svg viewBox="0 0 640 480" className={className} aria-hidden="true">
      <g fillRule="evenodd" strokeWidth="1pt">
        <path fill="#e4312b" d="M0 0h640v160H0z" />
        <path fill="#ffffff" d="M0 160h640v160H0z" />
        <path fill="#000000" d="M0 320h640v160H0z" />
        <path fill="#c09300" d="M295 195h50v90h-50z" />
      </g>
    </svg>
  );
}

function UaeFlag({ className = 'size-4 shrink-0 rounded-xs' }: { className?: string }) {
  return (
    <svg viewBox="0 0 640 480" className={className} aria-hidden="true">
      <g fillRule="evenodd">
        <path fill="#00732f" d="M0 0h640v160H0z" />
        <path fill="#ffffff" d="M0 160h640v160H0z" />
        <path fill="#000000" d="M0 320h640v160H0z" />
        <path fill="#e4312b" d="M0 0h175v480H0z" />
      </g>
    </svg>
  );
}

export default function MonthlyPresentationView(props: MonthlyPresentationViewProps) {
  // Function roles are allowed to open Monthly Review in their authorized scope.
  // (The /executive redirect is preserved separately in ExecutiveSummaryView.)
  return <MonthlyPresentationScreen {...props} />;
}

function MonthlyPresentationScreen({
  data,
  callCenterDeepDiveData,
  teamDeepDiveData,
  onSelectFunction,
  today,
  inlineAnalysis,
}: MonthlyPresentationViewProps) {
  const isInline = Boolean(inlineAnalysis);
  useEffect(() => {
    if (isInline) return;
    document.body.classList.add('mp-mac-cursor');
    return () => {
      document.body.classList.remove('mp-mac-cursor');
    };
  }, [isInline]);

  const { role } = useUserRole();
  const { currentUser } = useAuth();
  const assigned = directorScope(role, currentUser);
  const [routeSearchParams, setRouteSearchParams] = useSearchParams();
  const searchParams = inlineAnalysis?.searchParams ?? routeSearchParams;
  const setSearchParams = inlineAnalysis?.setSearchParams ?? setRouteSearchParams;
  const canReadInlineActions = canSeeSummaryActionAnalytics(role);
  const params = useParams<{ functionSlug?: string; teamSlug?: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  // Connect to real performance summary records & corrective actions store
  const summaryRecordsQuery = useSummaryRecords(true);
  const catalogQuery = usePerformanceCatalog(true);
  const execRecords = useMemo(
    () => toExecRecords(summaryRecordsQuery.data ?? []).filter((record) => !isHiddenTeam(record.team)),
    [summaryRecordsQuery.data],
  );
  const explicitPreview = Boolean(data || callCenterDeepDiveData || teamDeepDiveData);
  const functionScopeRestricted = isFunctionViewerRole(role);
  const serverTeams = useMemo(
    () => (catalogQuery.data?.teams ?? []).filter((team) => !isHiddenTeam(team.team)),
    [catalogQuery.data?.teams],
  );
  const authorizedFunctionNames = useMemo(
    () => functionScopeRestricted
      ? (explicitPreview
          ? readAccessibleFunctions(currentUser)
          : (catalogQuery.data?.authorized_functions ?? []))
      : [...new Set(serverTeams.flatMap((team) => team.functions))],
    [catalogQuery.data?.authorized_functions, currentUser, explicitPreview, functionScopeRestricted, serverTeams],
  );
  const authorizedFunctionSlugs = useMemo(
    () => new Set(authorizedFunctionNames.map(normalizeFunctionSlug)),
    [authorizedFunctionNames],
  );
  const availableRegions = useMemo<MonthlyRegionFilter[]>(() => {
    // The combined All view is offered whenever both regions are present
    // (including the explicit preview), listed first, then EGY, UAE.
    const regions = new Set<MonthlyRegionFilter>();
    if (explicitPreview) {
      regions.add('EGY');
      regions.add('UAE');
    } else {
      for (const team of serverTeams) {
        const normalized = normalizeRegion(team.region);
        if (normalized === 'EGY' || normalized === 'UAE') regions.add(normalized);
      }
    }
    const ordered = [...regions].sort((a, b) => (a === 'EGY' ? -1 : b === 'EGY' ? 1 : 0));
    return regions.size === 2 ? (['ALL', ...ordered] as MonthlyRegionFilter[]) : ordered;
  }, [explicitPreview, serverTeams]);
  const { getAllActions, saveAction, updateAction, deleteAction } = useActionStore();
  const storedActions = useMemo(
    () => isInline ? (canReadInlineActions ? getAllActions().filter((action) => action.synced) : []) : getAllActions(),
    [canReadInlineActions, getAllActions, isInline],
  );

  const regionParam = searchParams.get('teamRegion') || searchParams.get('region');
  const rawRegion = isInline && regionParam?.toLowerCase() === 'all' && availableRegions.length === 1
    ? availableRegions[0] : regionParam;
  const level = isInline ? searchParams.get('level')?.toLowerCase() : undefined;
  const normalizedUrlRegion = normalizeRegion(rawRegion);
  const rawBranch = (searchParams.get('branch') || '').trim().toLowerCase();
  const periodParam = searchParams.get('period') || searchParams.get('month') || undefined;

  const availableBranches = useMemo(() => {
    if (assigned.branchLocked) {
      if (assigned.branches.length === 0) return [];
      return assigned.branches.map((value) => {
        const known = SUMMARY_BRANCHES.find((item) => item.value === value);
        return known ?? { value, label: value.charAt(0).toUpperCase() + value.slice(1) };
      });
    }
    return SUMMARY_BRANCHES;
  }, [assigned.branchLocked, assigned.branches]);

  const availableBranchValues = useMemo(
    () => new Set(availableBranches.map((item) => item.value)),
    [availableBranches],
  );
  const branchLockedSingle = assigned.branchLocked && availableBranches.length <= 1;

  const activeBranch = useMemo(() => {
    if (assigned.branchLocked && assigned.branch) return assigned.branch;
    if (rawBranch && availableBranchValues.has(rawBranch)) return rawBranch;
    return '';
  }, [assigned.branch, assigned.branchLocked, availableBranchValues, rawBranch]);

  const activeBranchLabel = useMemo(() => {
    if (!activeBranch) return undefined;
    return (
      availableBranches.find((item) => item.value === activeBranch)?.label ??
      SUMMARY_BRANCHES.find((item) => item.value === activeBranch)?.label ??
      activeBranch
    );
  }, [activeBranch, availableBranches]);

  const previewRegion = data?.regionCode;
  const activeRegion: MonthlyRegionFilter = useMemo(() => {
    const validRegions: MonthlyRegionFilter[] = availableRegions.length ? availableRegions : ['EGY'];
    // Default to All when both regions are present; otherwise fall back to the
    // available single region. URL, assigned-region, and preview scopes still apply.
    const defaultRegion = validRegions.includes('ALL') ? 'ALL' : validRegions[0];
    const assignedRegion = normalizeRegion(assigned.region);
    const validAssignedRegion = (assignedRegion === 'UAE' || assignedRegion === 'EGY') && validRegions.includes(assignedRegion)
      ? assignedRegion : null;
    if (isInline && assigned.regionLocked && validAssignedRegion) return validAssignedRegion;
    if (
      (normalizedUrlRegion === 'UAE' || normalizedUrlRegion === 'EGY' || normalizedUrlRegion === 'ALL') &&
      validRegions.includes(normalizedUrlRegion)
    ) return normalizedUrlRegion;
    if (validAssignedRegion) return validAssignedRegion;
    if (explicitPreview && previewRegion && validRegions.includes(previewRegion)) {
      return previewRegion;
    }
    return defaultRegion;
  }, [
    assigned.region,
    assigned.regionLocked,
    previewRegion,
    explicitPreview,
    isInline,
    normalizedUrlRegion,
    availableRegions,
  ]);

  const handleRegionChange = useCallback(
    (nextRegion: MonthlyRegionFilter) => {
      const next = new URLSearchParams(searchParams);
      next.set('region', nextRegion.toLowerCase());
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const handleBranchChange = useCallback(
    (nextBranch: string) => {
      if (branchLockedSingle) return;
      const normalized = nextBranch.trim().toLowerCase();
      const next = new URLSearchParams(searchParams);
      if (normalized && availableBranchValues.has(normalized)) next.set('branch', normalized);
      else next.delete('branch');
      // Role slugs can carry a branch suffix (e.g. csr-ajman); clear role when switching branches.
      next.delete('role');
      setSearchParams(next, { replace: true });
    },
    [availableBranchValues, branchLockedSingle, searchParams, setSearchParams],
  );

  // Kept up here because the header toolbar below uses this handler.
  const handlePeriodChange = useCallback((key: string) => {
    const next = new URLSearchParams(searchParams);
    if (!searchParams.has('period') && searchParams.has('month')) next.set('month', key);
    else next.set('period', key);
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const clock = useMemo(() => today ?? new Date(), [today]);
  const parsedUrlPeriod = periodFromKey(periodParam);
  const requestedPeriodKey = parsedUrlPeriod && isMonthAvailable(parsedUrlPeriod.key, clock)
    ? parsedUrlPeriod.key
    : undefined;

  const authorizedRecords = useMemo(() => {
    if (explicitPreview) return execRecords;
    return execRecords.filter((record) => {
      const recordRegion = normalizeRegion(record.region);
      const recordLevel = String(record.level || 'Employee').trim().toLowerCase();
      if (level && level !== 'all' && recordLevel !== level) return false;
      return serverTeams.some((team) => recordMatchesCatalogTeam({
        recordTeam: record.team,
        recordRegion,
        recordLevel,
        catalogTeam: team.team,
        catalogRegion: normalizeRegion(team.region),
        levels: team.performance_levels,
      }));
    });
  }, [execRecords, explicitPreview, level, serverTeams]);

  const branchScopedRecords = useMemo(() => {
    if (!activeBranch) return authorizedRecords;
    return authorizedRecords
      .filter((record) =>
        (record.branches ?? []).some((branch) => branch.trim().toLowerCase() === activeBranch),
      )
      .map((record) => projectExecRecordForBranch(record, activeBranch));
  }, [activeBranch, authorizedRecords]);

  const catalogTeamFunctions = useMemo<TeamFunctionMap>(() => {
    const map: TeamFunctionMap = {};
    for (const item of serverTeams) {
      if (item.team && item.functions?.length) {
        map[item.team] = item.functions;
      }
    }
    return map;
  }, [serverTeams]);

  const overviewData: MonthlyOverviewData = useMemo(() => {
    const base =
      explicitPreview && data && data.regionCode === activeRegion && !activeBranch
        ? data
        : adaptSummaryToMonthlyOverview(
            composeExecutiveSummary({
              view: 'corporate',
              role,
              records: branchScopedRecords,
              // The All view aggregates both regions: no region filter.
              filters: {
                region: activeRegion === 'ALL' ? undefined : activeRegion,
                branch: activeBranch || undefined,
              },
              teamFunctions: catalogTeamFunctions,
              deriveScopedDrivers: true,
              today: clock,
              requestedPeriodKey,
            }),
            activeRegion,
            { allowSnapshotFallback: explicitPreview && !activeBranch },
          );
    const regionFunctionSlugs = new Set(
      (explicitPreview ? authorizedFunctionNames : serverTeams
        .filter((team) => activeRegion === 'ALL' || normalizeRegion(team.region) === activeRegion)
        .flatMap((team) => team.functions))
        .map(normalizeFunctionSlug),
    );
    const driverAllowed = (functionName: string) =>
      !functionScopeRestricted || authorizedFunctionSlugs.has(normalizeFunctionSlug(functionName));
    return {
      ...base,
      drivers: {
        negative: base.drivers.negative.filter((d) => driverAllowed(d.functionName)),
        positive: base.drivers.positive.filter((d) => driverAllowed(d.functionName)),
      },
      functions: base.functions.filter((fn) =>
        regionFunctionSlugs.has(fn.slug) &&
        (!functionScopeRestricted || authorizedFunctionSlugs.has(fn.slug)),
      ),
    };
  }, [
    activeBranch,
    activeRegion,
    authorizedFunctionNames,
    authorizedFunctionSlugs,
    branchScopedRecords,
    catalogTeamFunctions,
    clock,
    data,
    explicitPreview,
    functionScopeRestricted,
    requestedPeriodKey,
    role,
    serverTeams,
  ]);

  const branchRegionRecords = useMemo(
    () => branchScopedRecords.filter((record) => activeRegion === 'ALL' || normalizeRegion(record.region) === activeRegion),
    [activeRegion, branchScopedRecords],
  );
  const periodOptionSource = branchRegionRecords.length > 0 ? branchScopedRecords : authorizedRecords;
  const latestAuthorizedPeriod = periodOptionSource
    .filter((record) => activeRegion === 'ALL' || normalizeRegion(record.region) === activeRegion)
    .map((record) => record.period.key)
    .sort((a, b) => b.localeCompare(a))[0];
  const currentPeriodKey = `${clock.getFullYear()}-${String(clock.getMonth() + 1).padStart(2, '0')}`;
  const displayedPeriodKey = requestedPeriodKey ??
    (explicitPreview && data?.regionCode === activeRegion && !activeBranch ? data.periodKey : undefined) ??
    latestAuthorizedPeriod ??
    currentPeriodKey;
  const monthOptions = useMemo(
    () => presentationMonthOptions(
      periodOptionSource.map((record) => ({ region: record.region, periodKey: record.period.key })),
      activeRegion,
      clock,
      displayedPeriodKey,
    ),
    [activeRegion, clock, displayedPeriodKey, periodOptionSource],
  );
  const selectedPeriodKey = displayedPeriodKey;
  const selectedExecPeriod = useMemo(
    () => execPeriodFromKey(selectedPeriodKey),
    [selectedPeriodKey],
  );

  // Fetch tracked follow-up actions so the overview Corrective Actions card matches
  // Executive Summary (including tracked plan/team actions and Executive-role scope).
  const [followUpActions, setFollowUpActions] = useState<FollowUpAction[]>([]);
  useEffect(() => {
    if (isInline || explicitPreview || !canReadInlineActions) {
      setFollowUpActions([]);
      return;
    }
    let cancelled = false;
    apiFetch<{ success?: boolean; data?: { actions?: RawFollowUpActionItem[] } }>(
      '/api/corrective-actions/follow-up',
    )
      .then((res) => {
        if (cancelled || !res?.success || !Array.isArray(res.data?.actions)) return;
        setFollowUpActions(res.data.actions.map(rawFollowUpToFollowUpAction));
      })
      .catch(() => {
        // Fall back gracefully to synced actions already loaded in useActionStore.
      });
    return () => {
      cancelled = true;
    };
  }, [canReadInlineActions, explicitPreview, isInline]);

  const actionRecordIndex = useMemo(() => {
    const byEmployee = new Map<string, ExecRecord[]>();
    const byTeam = new Map<string, ExecRecord[]>();
    for (const record of authorizedRecords) {
      if (record.employeeId) {
        const list = byEmployee.get(record.employeeId);
        if (list) list.push(record);
        else byEmployee.set(record.employeeId, [record]);
      }
      const canonical = canonicalTeamName(record.team);
      if (canonical) {
        const list = byTeam.get(canonical);
        if (list) list.push(record);
        else byTeam.set(canonical, [record]);
      }
    }
    return { byEmployee, byTeam };
  }, [authorizedRecords]);

  const scopeOverviewAction = useCallback((action: FollowUpAction) => {
    const actionTeam = canonicalTeamName(action.team);
    if (functionScopeRestricted) {
      const fns =
        catalogTeamFunctions[actionTeam] ??
        serverTeams.find((team) => canonicalTeamName(team.team) === actionTeam)?.functions ??
        [];
      if (fns.length > 0 && !fns.some((fn) => authorizedFunctionSlugs.has(normalizeFunctionSlug(fn)))) {
        return false;
      }
    }
    if (activeRegion !== 'ALL' || activeBranch) {
      const matches = action.employee_id
        ? (actionRecordIndex.byEmployee.get(action.employee_id) ?? [])
        : (actionRecordIndex.byTeam.get(actionTeam) ?? []);
      if (matches.length === 0) {
        if (!activeBranch && action.region) {
          return normalizeRegion(action.region) === activeRegion;
        }
        return false;
      }
      return matches.some((record) =>
        (activeRegion === 'ALL' || normalizeRegion(record.region) === activeRegion) &&
        (!activeBranch || (record.branches ?? []).some((branch) => branch.trim().toLowerCase() === activeBranch)),
      );
    }
    return true;
  }, [
    actionRecordIndex,
    activeBranch,
    activeRegion,
    authorizedFunctionSlugs,
    catalogTeamFunctions,
    functionScopeRestricted,
    serverTeams,
  ]);

  const overviewCorrectiveActions = useMemo(() => {
    if (!canReadInlineActions) return null;
    const merged = new Map<string, FollowUpAction>();
    for (const action of storedActions) {
      if (action.synced === false) continue;
      const mapped = pmsActionToFollowUp(action);
      merged.set(String(mapped.id), mapped);
    }
    for (const action of followUpActions) {
      const key = String(action.id);
      const existing = merged.get(key);
      merged.set(key, {
        ...existing,
        ...action,
        root_cause_note: action.root_cause_note || existing?.root_cause_note || '',
        linked_kpi_key: action.linked_kpi_key || existing?.linked_kpi_key || null,
        created_at: action.created_at || existing?.created_at || '',
        month: action.month || existing?.month || '',
      });
    }
    const scopedSynced = [...merged.values()].filter(scopeOverviewAction);
    const scopedPending = storedActions
      .filter((action) => action.synced === false)
      .map(pmsActionToFollowUp)
      .filter(scopeOverviewAction);
    return summarizeActions(scopedSynced, clock, selectedExecPeriod, scopedPending);
  }, [
    canReadInlineActions,
    clock,
    followUpActions,
    scopeOverviewAction,
    selectedExecPeriod,
    storedActions,
  ]);

  const overviewActionsScopeLabel = useMemo(() => {
    const regionPart = activeRegion === 'ALL' ? 'Company-wide' : overviewData.regionName;
    return activeBranchLabel ? `${regionPart} · ${activeBranchLabel} branch` : regionPart;
  }, [activeBranchLabel, activeRegion, overviewData.regionName]);

  const rawDeepDive = (searchParams.get('deepDive') || params.functionSlug || '').trim();
  const functionSlug = rawDeepDive ? normalizeFunctionSlug(rawDeepDive) : '';
  const rawTeamParam = (searchParams.get('team') || params.teamSlug || '').trim();
  const activeTeamSlug = useMemo(() => {
    const rawTeamSlug = rawTeamParam ? slugifyIdentifier(rawTeamParam) : '';
    const legacyTeam = legacySharedTeamRedirect(rawTeamSlug);
    return legacyTeam && (!rawRegion || activeRegion === legacyTeam.region) ? legacyTeam.routeId : rawTeamSlug;
  }, [activeRegion, rawRegion, rawTeamParam]);
  const rawRoleParam = (searchParams.get('role') || '').trim();
  const activeRoleSlug = rawRoleParam ? slugifyIdentifier(rawRoleParam) : '';
  const activeEmployeeId = isInline ? searchParams.get('employee') : null;

  const allowedFunctions = functionScopeRestricted ? authorizedFunctionNames : null;

  const isFunctionAuthorized = useCallback((fnSlug: string) => {
    if (!fnSlug) return false;
    if (functionScopeRestricted) return authorizedFunctionSlugs.has(fnSlug);
    if (explicitPreview) return overviewData.functions.some((fn) => fn.slug === fnSlug);
    return serverTeams.some((team) =>
      (activeRegion === 'ALL' || normalizeRegion(team.region) === activeRegion) &&
      team.functions.some((name) => normalizeFunctionSlug(name) === fnSlug),
    );
  }, [activeRegion, authorizedFunctionSlugs, explicitPreview, functionScopeRestricted, overviewData.functions, serverTeams]);

  const teamBelongsToFunction = useCallback(
    (
      teamSlug: string,
      fnSlug: string,
      region: MonthlyRegionFilter,
    ) => {
      return serverTeams.some((team) => {
        // In the All view a team belongs by its own region, not the view's.
        const teamCountry = parseTeamCountry(normalizeRegion(team.region));
        return (
          (slugifyIdentifier(team.team) === teamSlug
            || slugifyIdentifier(mergedTeamName(team.team)) === teamSlug
            || (teamCountry !== null && sameCountryBusinessTeam(team.team, teamSlug, teamCountry))) &&
          (region === 'ALL' || normalizeRegion(team.region) === region) &&
          team.functions.some((name) => normalizeFunctionSlug(name) === fnSlug)
        );
      });
    },
    [serverTeams],
  );

  const selectedPeriodRecords = useMemo(
    () => branchScopedRecords.filter(
      (record) => (activeRegion === 'ALL' || normalizeRegion(record.region) === activeRegion) && record.period.key === selectedPeriodKey,
    ),
    [activeRegion, branchScopedRecords, selectedPeriodKey],
  );
  const currentFunctionRecords = useMemo(
    () => selectedPeriodRecords.filter((record) => {
      // The catalog team for a record sits in the record's own region; in a
      // single-region view that is the active region.
      const recordCountry = parseTeamCountry(normalizeRegion(record.region)) ?? parseTeamCountry(activeRegion);
      const metadata = serverTeams.find((team) =>
        (slugifyIdentifier(team.team) === slugifyIdentifier(record.team)
          || sameMergedTeam(team.team, record.team)
          || (recordCountry !== null && sameCountryBusinessTeam(team.team, record.team, recordCountry))) &&
        (activeRegion === 'ALL'
          ? normalizeRegion(record.region) === null || normalizeRegion(team.region) === normalizeRegion(record.region)
          : normalizeRegion(team.region) === activeRegion),
      );
      return metadata?.functions.some((name) => normalizeFunctionSlug(name) === functionSlug) ?? false;
    }),
    [activeRegion, functionSlug, selectedPeriodRecords, serverTeams],
  );
  const currentTeamRecords = useMemo(
    () => selectedPeriodRecords.filter((record) => {
      const recordCountry = parseTeamCountry(normalizeRegion(record.region)) ?? parseTeamCountry(activeRegion);
      return slugifyIdentifier(record.team) === activeTeamSlug
        || (recordCountry !== null && sameCountryBusinessTeam(record.team, activeTeamSlug, recordCountry));
    }),
    [activeRegion, activeTeamSlug, selectedPeriodRecords],
  );

  // Open the single assigned function automatically for function-scoped accounts.
  useEffect(() => {
    if (catalogQuery.isLoading || !functionScopeRestricted || !allowedFunctions || allowedFunctions.length !== 1) return;
    if (functionSlug) return;
    const slug = normalizeFunctionSlug(allowedFunctions[0]);
    const next = new URLSearchParams(searchParams);
    next.set('deepDive', slug);
    next.delete('team');
    next.delete('role');
    setSearchParams(next, { replace: true });
  }, [catalogQuery.isLoading, functionScopeRestricted, allowedFunctions, functionSlug, searchParams, setSearchParams]);

  // Keep deep links inside the server-enforced function scope.
  useEffect(() => {
    if (catalogQuery.isLoading || !functionScopeRestricted || !allowedFunctions || !functionSlug) return;
    const allowedSlugs = new Set(allowedFunctions.map(normalizeFunctionSlug));
    if (allowedSlugs.has(functionSlug)) return;
    const next = new URLSearchParams(searchParams);
    next.delete('deepDive');
    next.delete('team');
    next.delete('role');
    setSearchParams(next, { replace: true });
  }, [catalogQuery.isLoading, functionScopeRestricted, allowedFunctions, functionSlug, searchParams, setSearchParams]);

  useEffect(() => {
    if (catalogQuery.isLoading || !rawRegion || !normalizedUrlRegion) return;
    if ((normalizedUrlRegion === 'EGY' || normalizedUrlRegion === 'UAE' || normalizedUrlRegion === 'ALL') && availableRegions.includes(normalizedUrlRegion)) return;
    const next = new URLSearchParams(searchParams);
    next.delete('region');
    next.delete('teamRegion');
    next.delete('deepDive');
    next.delete('team');
    next.delete('role');
    setSearchParams(next, { replace: true });
  }, [availableRegions, catalogQuery.isLoading, normalizedUrlRegion, rawRegion, searchParams, setSearchParams]);

  useEffect(() => {
    if (catalogQuery.isLoading || !rawBranch) return;
    const branchAllowed = assigned.branchLocked && assigned.branch
      ? rawBranch === assigned.branch
      : availableBranchValues.has(rawBranch);
    if (branchAllowed) return;
    const next = new URLSearchParams(searchParams);
    next.delete('branch');
    next.delete('role');
    setSearchParams(next, { replace: true });
  }, [assigned.branch, assigned.branchLocked, availableBranchValues, catalogQuery.isLoading, rawBranch, searchParams, setSearchParams]);

  useEffect(() => {
    if (catalogQuery.isLoading || (!explicitPreview && catalogQuery.isError)) return;
    if (!functionSlug || functionScopeRestricted) return;
    if (isFunctionAuthorized(functionSlug)) return;
    const next = new URLSearchParams(searchParams);
    next.delete('deepDive');
    next.delete('team');
    next.delete('role');
    setSearchParams(next, { replace: true });
  }, [catalogQuery.isError, catalogQuery.isLoading, explicitPreview, functionScopeRestricted, functionSlug, isFunctionAuthorized, searchParams, setSearchParams]);

  // Clear team-only, invalid-team, and zero-grant deep links before rendering detail.
  useEffect(() => {
    if (catalogQuery.isLoading || (!explicitPreview && catalogQuery.isError)) return;
    if (activeTeamSlug && !functionSlug) {
      const next = new URLSearchParams(searchParams);
      next.delete('team');
      next.delete('role');
      setSearchParams(next, { replace: true });
      return;
    }
    if (activeRoleSlug && !functionSlug) {
      const next = new URLSearchParams(searchParams);
      next.delete('role');
      setSearchParams(next, { replace: true });
      return;
    }
    if (
      functionScopeRestricted &&
      (!allowedFunctions || allowedFunctions.length === 0) &&
      (functionSlug || activeTeamSlug || activeRoleSlug)
    ) {
      const next = new URLSearchParams(searchParams);
      next.delete('deepDive');
      next.delete('team');
      next.delete('role');
      setSearchParams(next, { replace: true });
      return;
    }
    if (
      activeTeamSlug &&
      functionSlug &&
      !teamBelongsToFunction(activeTeamSlug, functionSlug, activeRegion)
    ) {
      const next = new URLSearchParams(searchParams);
      next.delete('team');
      next.delete('role');
      setSearchParams(next, { replace: true });
    }
  }, [
    activeTeamSlug,
    activeRoleSlug,
    functionSlug,
    functionScopeRestricted,
    allowedFunctions,
    activeRegion,
    searchParams,
    setSearchParams,
    teamBelongsToFunction,
    catalogQuery.isError,
    catalogQuery.isLoading,
    explicitPreview,
  ]);

  const handleFunctionClick = useCallback(
    (fn: FunctionOverviewItem) => {
      onSelectFunction?.(fn);
      const next = new URLSearchParams(searchParams);
      next.set('deepDive', fn.slug);
      next.delete('team');
      next.delete('role');
      setSearchParams(next);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },
    [onSelectFunction, searchParams, setSearchParams],
  );

  const handleBackToOverview = useCallback(() => {
    const next = new URLSearchParams(searchParams);
    next.delete('deepDive');
    next.delete('team');
    next.delete('role');
    if (!isInline && params.functionSlug) {
      const basePath = location.pathname.startsWith('/monthly-view')
        ? '/monthly-view'
        : '/monthly-presentation';
      const query = next.toString();
      navigate(`${basePath}${query ? `?${query}` : ''}`);
    } else {
      setSearchParams(next);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [isInline, location.pathname, navigate, params.functionSlug, searchParams, setSearchParams]);

  const handleClearFilters = useCallback(() => {
    const next = new URLSearchParams(searchParams);
    if (!branchLockedSingle) next.delete('branch');
    next.delete('deepDive');
    next.delete('team');
    next.delete('role');
    if (!isInline && params.functionSlug) {
      const basePath = location.pathname.startsWith('/monthly-view')
        ? '/monthly-view'
        : '/monthly-presentation';
      const query = next.toString();
      navigate(`${basePath}${query ? `?${query}` : ''}`);
    } else {
      setSearchParams(next);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [branchLockedSingle, isInline, location.pathname, navigate, params.functionSlug, searchParams, setSearchParams]);

  const handleSelectAgentTeam = useCallback(
    (teamSlug: string, functionName?: string) => {
      const next = new URLSearchParams(searchParams);
      const targetFunction = functionName
        ? normalizeFunctionSlug(functionName)
        : functionSlug || 'call-center';
      next.set('deepDive', targetFunction);
      next.set('team', slugifyIdentifier(businessTeamName(teamSlug)));
      next.delete('employee');
      next.delete('role');
      setSearchParams(next);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },
    [functionSlug, searchParams, setSearchParams],
  );

  const handleSelectRole = useCallback(
    (roleSlug: string) => {
      if (!functionSlug) return;
      const next = new URLSearchParams(searchParams);
      next.set('deepDive', functionSlug);
      next.set('role', roleSlug);
      next.delete('team');
      setSearchParams(next);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },
    [functionSlug, searchParams, setSearchParams],
  );

  const handleBackToFunction = useCallback(() => {
    const next = new URLSearchParams(searchParams);
    if (functionSlug) next.set('deepDive', functionSlug);
    next.delete('team');
    next.delete('teamRegion');
    next.delete('employee');
    next.delete('role');
    setSearchParams(next);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [functionSlug, searchParams, setSearchParams]);

  const selectEmployee = (employeeId: string) => {
    const next = new URLSearchParams(searchParams);
    if (employeeId) next.set('employee', employeeId);
    else next.delete('employee');
    setSearchParams(next);
    window.scrollTo({ top: 0 });
  };

  const openEmployeeProfile = useCallback(
    (employeeId: string) => {
      const id = String(employeeId || '').trim();
      if (!id) return;
      const parsed = periodFromKey(selectedPeriodKey);
      const params = new URLSearchParams();
      const monthName = parsed?.label?.split(' ')[0];
      if (monthName) params.set('month', monthName);
      if (parsed?.year) params.set('year', String(parsed.year));
      params.set('performance_level', 'Employee');
      navigate(`/employee/${encodeURIComponent(id)}?${params.toString()}`);
    },
    [navigate, selectedPeriodKey],
  );

  const selectReviewUnit = (unit: ReviewUnit) => {
    const next = new URLSearchParams(searchParams);
    next.delete('employee');
    next.delete('team');
    next.delete('role');
    next.delete('teamRegion');
    if (unit.region) next.set('teamRegion', unit.region);
    if (unit.role) next.set('role', unit.role);
    else if (unit.team) next.set('team', slugifyIdentifier(businessTeamName(unit.team)));
    setSearchParams(next);
    window.scrollTo({ top: 0 });
  };

  const resolvedFunctionData: CallCenterDeepDiveData | null = useMemo(() => {
    if (!functionSlug || !isFunctionAuthorized(functionSlug)) return null;
    if (!explicitPreview && currentFunctionRecords.length === 0) return null;
    if (functionSlug === 'call-center' && explicitPreview && !activeBranch && callCenterDeepDiveData) return callCenterDeepDiveData;
    return buildFunctionDeepDiveFromRecords(
      functionSlug,
      branchScopedRecords,
      storedActions,
      activeRegion,
      selectedPeriodKey,
      // Explicit preview (the September 2026 presentation demo) may stand
      // in the published September snapshot when nothing was measured at
      // all. Production measured dives never fall back to it.
      { allowSnapshotFallback: explicitPreview && !activeBranch },
    );
  }, [activeBranch, activeRegion, branchScopedRecords, callCenterDeepDiveData, currentFunctionRecords.length, explicitPreview, functionSlug, isFunctionAuthorized, selectedPeriodKey, storedActions]);

  const roleCards = useMemo(() => {
    if (!resolvedFunctionData || !isRoleBasedFunction(resolvedFunctionData.functionSlug)) return [];
    return resolveRoleCards(resolvedFunctionData, branchScopedRecords);
  }, [branchScopedRecords, resolvedFunctionData]);

  const currentRoleRecords = useMemo(() => {
    if (!activeRoleSlug) return [];
    const directMatches = currentFunctionRecords.filter((record) =>
      recordMatchesRole(record, activeRoleSlug, resolvedFunctionData),
    );
    if (directMatches.length > 0) return directMatches;
    const effectivePeriodKey = resolvedFunctionData?.periodKey;
    if (effectivePeriodKey && effectivePeriodKey !== selectedPeriodKey) {
      return branchScopedRecords.filter(
        (record) =>
          (activeRegion === 'ALL' || normalizeRegion(record.region) === activeRegion) &&
          record.period.key === effectivePeriodKey &&
          recordMatchesRole(record, activeRoleSlug, resolvedFunctionData),
      );
    }
    return [];
  }, [activeRegion, activeRoleSlug, branchScopedRecords, currentFunctionRecords, resolvedFunctionData, selectedPeriodKey]);

  const resolvedTeamData: TeamDeepDiveData | null = useMemo(() => {
    if (!activeTeamSlug || activeRoleSlug || !functionSlug || !teamBelongsToFunction(activeTeamSlug, functionSlug, activeRegion)) return null;
    if (!explicitPreview && currentTeamRecords.length === 0) return null;
    if (explicitPreview && !activeBranch && teamDeepDiveData && teamDeepDiveData.teamSlug === activeTeamSlug) {
      return teamDeepDiveData;
    }
    const teamActions = isInline
      ? storedActions.filter((action) => !isSavedRoleIntervention(action) && currentTeamRecords.some((record) => actionMatchesRecord(action, record)))
      : storedActions;
    return buildTeamDeepDiveFromRecords(
      activeTeamSlug,
      branchScopedRecords,
      teamActions,
      activeRegion,
      selectedPeriodKey,
    );
  }, [activeBranch, activeRegion, activeRoleSlug, activeTeamSlug, branchScopedRecords, currentTeamRecords, explicitPreview, functionSlug, isInline, selectedPeriodKey, storedActions, teamBelongsToFunction, teamDeepDiveData]);

  const resolvedRoleData = useMemo(() => {
    if (!activeRoleSlug || !resolvedFunctionData) return null;
    if (!hasRoleDetailForSlug(resolvedFunctionData, activeRoleSlug, branchScopedRecords)) return null;
    if (!isInline) return buildRoleDetail(resolvedFunctionData, activeRoleSlug, storedActions, branchScopedRecords);
    const scopedActions = storedActions.filter((action) => currentRoleRecords.some((record) => actionMatchesRecord(action, record)));
    return buildRoleDetail(
      resolvedFunctionData, activeRoleSlug,
      scopedActions.filter((action) => !isSavedRoleIntervention(action)),
      branchScopedRecords,
      scopedActions.filter(isSavedRoleIntervention),
    );
  }, [activeRoleSlug, branchScopedRecords, currentRoleRecords, isInline, resolvedFunctionData, storedActions]);

  const reviewUnits = useMemo<ReviewUnit[]>(() => {
    if (!isInline || !resolvedFunctionData || activeTeamSlug || activeRoleSlug) return [];
    if (isRoleBasedFunction(functionSlug)) return roleCards.map((card) => ({
      id: card.roleSlug, name: card.branchLabel ? `${card.roleTitle} · ${card.branchLabel}` : card.roleTitle,
      score: card.score, people: card.headcount, role: card.roleSlug, bottleneck: card.signal,
    }));
    const regions = activeRegion === 'ALL' ? ['EGY', 'UAE'] as const : [activeRegion];
    return regions.flatMap((region) => {
      const detail = activeRegion === region
        ? resolvedFunctionData
        : buildFunctionDeepDiveFromRecords(functionSlug, branchScopedRecords, [], region, selectedPeriodKey, { allowSnapshotFallback: false });
      return detail.agentTeams.filter((team) => team.headcount > 0).map((team) => ({
        id: `${region}:${team.teamSlug}`, name: presentationTeamName(team.teamName), score: team.score,
        people: team.headcount, team: team.canonicalTeam, region, bottleneck: team.keyStrengthOrDrag,
      }));
    });
  }, [activeRegion, activeRoleSlug, activeTeamSlug, branchScopedRecords, functionSlug, isInline, resolvedFunctionData, roleCards, selectedPeriodKey]);

  const inlineMembers = useMemo(() => {
    if (!isInline) return [];
    if (resolvedTeamData) return currentTeamRecords;
    if (!resolvedRoleData) return [];
    const memberIds = new Set(resolvedRoleData.members.map((member) => member.employeeId.toLowerCase()));
    return currentFunctionRecords.filter((record) => memberIds.has(record.employeeId.toLowerCase()));
  }, [currentFunctionRecords, currentTeamRecords, isInline, resolvedRoleData, resolvedTeamData]);
  const teamCountries = useMemo(() => [...new Set(currentTeamRecords.flatMap((record) => {
    const country = parseTeamCountry(record.region);
    return country ? [country] : [];
  }))].sort(), [currentTeamRecords]);
  const chooseTeamCountry = isInline && activeRegion === 'ALL' && Boolean(activeTeamSlug) && teamCountries.length > 1;
  const selectedEmployee = inlineMembers.find((record) => record.employeeId === activeEmployeeId);
  const teamLabel = resolvedRoleData?.roleTitle ?? resolvedTeamData?.teamDisplayName ?? '';
  const employeePicker = isInline && inlineMembers.length > 0 ? (
    <label className="inline-flex flex-wrap items-center gap-2 text-xs font-semibold text-[var(--text-secondary)]">
      <span>Employee</span>
      <select
        aria-label="Review employee"
        className="h-9 rounded-[10px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-3 text-xs font-semibold text-[var(--insights-heading)] focus:border-[var(--insights-accent)] focus:outline-none"
        value=""
        onChange={(event) => selectEmployee(event.target.value)}
      >
        <option value="">Select employee</option>
        {[...new Map(inlineMembers.map((record) => [record.employeeId, record])).values()]
          .sort((a, b) => a.name.localeCompare(b.name))
          .map((record) => <option key={record.employeeId} value={record.employeeId}>{record.name}</option>)}
      </select>
    </label>
  ) : undefined;

  // The combined view dedupes each country's catalog separately, so a shared
  // business team present in both regions lists once per region.
  const teamsInActiveRegion = activeRegion === 'ALL'
    ? [
        ...distinctCatalogTeams(serverTeams.filter((team) => normalizeRegion(team.region) === 'EGY'), 'EGY'),
        ...distinctCatalogTeams(serverTeams.filter((team) => normalizeRegion(team.region) === 'UAE'), 'UAE'),
      ]
    : distinctCatalogTeams(
        serverTeams.filter((team) => normalizeRegion(team.region) === activeRegion),
        activeRegion,
      );
  const teamsInCurrentFunction = functionSlug
    ? teamsInActiveRegion.filter((team) => team.functions.some((name) => normalizeFunctionSlug(name) === functionSlug))
    : teamsInActiveRegion;
  // 'Call Center' is a deprecated parent team (replaced by Inbound/Outbound);
  // it never has its own records, so hide only that row from the box. RCM
  // and the *_management teams stay listed until the user decides otherwise.
  // Catalog teams do not store per-branch membership, so omit missing-upload
  // attribution while a single branch filter is active.
  const teamsWithoutData = activeBranch
    ? []
    : teamsInCurrentFunction.filter((team) =>
        team.team !== CALL_CENTER_TEAM &&
        !selectedPeriodRecords.some((record) => recordMatchesCatalogTeam({
          recordTeam: record.team,
          recordRegion: record.region,
          recordLevel: record.level,
          catalogTeam: team.team,
          catalogRegion: normalizeRegion(team.region),
          levels: team.performance_levels,
        })),
      );

  const canonicalTeam = resolvedTeamData?.canonicalTeam ?? '';
  const teamPeriodKey = resolvedTeamData?.periodKey ?? '';
  const teamMonthLabel = resolvedTeamData?.monthLabel ?? '';

  // Action plans are stored per region; in the All view a team deep dive
  // keeps the scope of the team's own region so its saved plans still load.
  const canonicalTeamRegion = useMemo(() => {
    if (!canonicalTeam) return null;
    if (activeRegion !== 'ALL') return activeRegion;
    const countries = new Set(currentTeamRecords.map((record) => parseTeamCountry(record.region)));
    if (countries.size === 1) return [...countries][0];
    const match = serverTeams.find((team) => slugifyIdentifier(team.team) === slugifyIdentifier(canonicalTeam));

    const normalized = normalizeRegion(match?.region);
    return normalized === 'EGY' || normalized === 'UAE' ? normalized : null;
  }, [activeRegion, canonicalTeam, currentTeamRecords, serverTeams]);

  const activeTeamPlanScope = useMemo(() => {
    if (!canonicalTeam) return null;
    const parsedPeriod = periodFromKey(teamPeriodKey);
    const [, labelYear] = teamMonthLabel.split(' ');
    const month = resolvePeriodMonthName(parsedPeriod?.month, teamMonthLabel);
    const year = parsedPeriod?.year || Number(labelYear) || new Date().getFullYear();
    const planRegion = canonicalTeamRegion ?? activeRegion;
    return {
      team: canonicalTeam,
      region: planRegion,
      month,
      year,
      scopeKey: teamPlanScopeKey(canonicalTeam, month, year, planRegion),
    };
  }, [activeRegion, canonicalTeam, canonicalTeamRegion, teamPeriodKey, teamMonthLabel]);

  const [teamPlanItemsByScope, setTeamPlanItemsByScope] = useState<
    Record<string, TeamLevelActionPlanCard[]>
  >({});

  useEffect(() => {
    if (!activeTeamPlanScope || explicitPreview || chooseTeamCountry || (isInline && !canReadInlineActions)) return;
    const { team, region, month, year, scopeKey } = activeTeamPlanScope;
    const localItems = isInline ? [] : readStoredTeamPlans(scopeKey);

    let cancelled = false;
    const params = new URLSearchParams({
      team,
      month,
      year: String(year),
      region,
    });
    apiFetch<{ success: boolean; data?: TeamPlanItemApiRow[] }>(
      `/api/team-actions/plan-items?${params.toString()}`,
    )
      .then((res) => {
        if (cancelled || !res?.success || !Array.isArray(res.data)) return;
        const remoteItems: TeamLevelActionPlanCard[] = res.data.map((row) => ({
          id: row.card_id || row.id,
          title: row.title,
          targetKpi: row.target_kpi,
          scopeDescription: row.scope_description,
          owner: row.owner,
          expectedTeamImpact: row.expected_team_impact,
          status: row.status,
          dueDate: row.due_date ?? null,
          isDeleted: Boolean(row.is_deleted),
        }));
        const merged = mergeTeamPlanItems(localItems, remoteItems);
        if (!isInline) writeStoredTeamPlans(scopeKey, merged);
        setTeamPlanItemsByScope((prev) => ({
          ...prev,
          [scopeKey]: merged,
        }));
      })
      .catch(() => {
        // Keep localStorage fallback when backend endpoint is unavailable
      });

    return () => {
      cancelled = true;
    };
  }, [activeTeamPlanScope, canReadInlineActions, chooseTeamCountry, explicitPreview, isInline]);

  const savedTeamActionsForActiveScope = useMemo(() => {
    if (!activeTeamPlanScope || (isInline && !canReadInlineActions)) return undefined;
    return teamPlanItemsByScope[activeTeamPlanScope.scopeKey] ?? (isInline ? undefined : readStoredTeamPlans(activeTeamPlanScope.scopeKey));
  }, [activeTeamPlanScope, canReadInlineActions, isInline, teamPlanItemsByScope]);

  const handleSaveTeamAction = useCallback(
    async (card: TeamLevelActionPlanCard) => {
      if (!activeTeamPlanScope) return;
      const { team, region, month, year, scopeKey } = activeTeamPlanScope;
      const cleanCard: TeamLevelActionPlanCard = { ...card, isDeleted: false };
      const currentList = teamPlanItemsByScope[scopeKey] ?? readStoredTeamPlans(scopeKey);
      const nextList = mergeTeamPlanItems(currentList, [cleanCard]);
      writeStoredTeamPlans(scopeKey, nextList);
      setTeamPlanItemsByScope((prev) => ({
        ...prev,
        [scopeKey]: nextList,
      }));
      if (explicitPreview) return;
      await apiFetch<{ success: boolean; data?: TeamPlanItemApiRow }>(
        '/api/team-actions/plan-items',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            card_id: cleanCard.id,
            team,
            region,
            month,
            year,
            title: cleanCard.title,
            target_kpi: cleanCard.targetKpi,
            scope_description: cleanCard.scopeDescription,
            owner: cleanCard.owner,
            status: cleanCard.status,
            due_date: cleanCard.dueDate ?? null,
            expected_team_impact: cleanCard.expectedTeamImpact,
          }),
        },
      );
    },
    [activeTeamPlanScope, explicitPreview, teamPlanItemsByScope],
  );

  const handleDeleteTeamAction = useCallback(
    async (card: TeamLevelActionPlanCard) => {
      if (!activeTeamPlanScope) return;
      const { team, region, month, year, scopeKey } = activeTeamPlanScope;
      const isCustom = card.id.startsWith('team-act-custom-');
      if (!explicitPreview) {
        const params = new URLSearchParams({
          team,
          month,
          year: String(year),
          region,
        });
        const res = await apiFetch<{ success?: boolean; message?: string }>(
          `/api/team-actions/plan-items/${encodeURIComponent(card.id)}?${params.toString()}`,
          { method: 'DELETE' },
        );
        if (res && res.success === false) {
          throw new Error(res.message || 'Failed to delete team action');
        }
      }
      const currentList = teamPlanItemsByScope[scopeKey] ?? readStoredTeamPlans(scopeKey);
      const nextList = isCustom
        ? currentList.filter((item) => item.id !== card.id)
        : mergeTeamPlanItems(currentList, [{ ...card, isDeleted: true }]);
      writeStoredTeamPlans(scopeKey, nextList);
      setTeamPlanItemsByScope((prev) => ({
        ...prev,
        [scopeKey]: nextList,
      }));
    },
    [activeTeamPlanScope, explicitPreview, teamPlanItemsByScope],
  );

  const handleRestoreTeamActions = useCallback(
    async (cardIds: string[]) => {
      if (!activeTeamPlanScope || cardIds.length === 0) return;
      const { team, region, month, year, scopeKey } = activeTeamPlanScope;
      if (!explicitPreview) {
        const params = new URLSearchParams({
          team,
          month,
          year: String(year),
          region,
          purge_tombstone: 'true',
        });
        await Promise.all(
          cardIds.map(async (cardId) => {
            const res = await apiFetch<{ success?: boolean; message?: string }>(
              `/api/team-actions/plan-items/${encodeURIComponent(cardId)}?${params.toString()}`,
              { method: 'DELETE' },
            );
            if (res && res.success === false) {
              throw new Error(res.message || 'Failed to restore team actions');
            }
          }),
        );
      }
      const idSet = new Set(cardIds);
      const currentList = teamPlanItemsByScope[scopeKey] ?? readStoredTeamPlans(scopeKey);
      const nextList = currentList.filter((item) => !idSet.has(item.id));
      writeStoredTeamPlans(scopeKey, nextList);
      setTeamPlanItemsByScope((prev) => ({
        ...prev,
        [scopeKey]: nextList,
      }));
    },
    [activeTeamPlanScope, explicitPreview, teamPlanItemsByScope],
  );

  const handleSaveRoleAction = useCallback(
    async (draft: RoleActionDraft) => {
      const rootCauseNote =
        draft.mainIssue !== undefined
          ? encodeIndividualActionMeta(
              {
                mainIssue: draft.mainIssue,
                owner: draft.owner,
                expectedImpact: draft.expectedImpact,
              },
              draft.mainIssue,
            )
          : `Owner: ${draft.owner}. Status: ${draft.status}. Expected impact: ${draft.expectedImpact || 'Not specified'}.`;

      if (draft.actionId && ACTION_UUID_RE.test(draft.actionId) && typeof updateAction === 'function') {
        await updateAction(
          draft.actionId,
          {
            action_text: draft.description,
            root_cause_note: rootCauseNote,
            status: draft.status,
            due_date: draft.dueDate || null,
            linked_kpi_key: draft.linkedKpiKey,
          },
          {
            id: draft.employeeId,
            name: draft.personName,
            team: draft.team,
          },
          draft.month,
        );
        return;
      }

      await saveAction({
        employee_id: draft.employeeId,
        employee_name: draft.personName,
        team: draft.team,
        month: draft.month,
        action_type: 'Coaching',
        action_text: draft.description,
        root_cause_note: rootCauseNote,
        due_date: draft.dueDate || null,
        linked_kpi_key: draft.linkedKpiKey,
      });
    },
    [saveAction, updateAction],
  );

  const handleSaveIndividualAction = useCallback(
    async (card: IndividualActionPlanCard) => {
      if (!resolvedTeamData) return;
      const parsedPeriod = periodFromKey(resolvedTeamData.periodKey);
      const monthName = resolvePeriodMonthName(parsedPeriod?.month, resolvedTeamData.monthLabel);
      const rootCauseNote = encodeIndividualActionMeta(
        {
          mainIssue: card.mainIssue,
          owner: card.owner,
          expectedImpact: card.expectedImpact,
        },
        card.mainIssue,
      );

      if (ACTION_UUID_RE.test(card.id) && typeof updateAction === 'function') {
        await updateAction(
          card.id,
          {
            action_text: card.actionText,
            root_cause_note: rootCauseNote,
            linked_kpi_key: card.linkedKpiKey,
          },
          {
            id: card.employeeId,
            name: card.agentName,
            team: resolvedTeamData.canonicalTeam,
          },
          monthName,
        );
        return;
      }

      await saveAction({
        employee_id: card.employeeId,
        employee_name: card.agentName,
        team: resolvedTeamData.canonicalTeam,
        month: monthName,
        action_type: 'Coaching',
        action_text: card.actionText,
        root_cause_note: rootCauseNote,
        linked_kpi_key: card.linkedKpiKey,
      });
    },
    [resolvedTeamData, saveAction, updateAction],
  );

  const handleDeleteIndividualAction = useCallback(
    async (employeeId: string, monthName: string, actionId?: string) => {
      const targetMonth = monthName.trim().toLowerCase();
      const targetEmployee = employeeId.trim().toLowerCase();
      const matched =
        (actionId ? storedActions.find((a) => a.id === actionId) : undefined) ??
        storedActions.find(
          (a) =>
            (a.employee_id || '').trim().toLowerCase() === targetEmployee &&
            (!targetMonth || (a.month || '').trim().toLowerCase() === targetMonth),
        );
      const idToDelete =
        matched?.id ?? (actionId && ACTION_UUID_RE.test(actionId) ? actionId : undefined);
      if (idToDelete && typeof deleteAction === 'function') {
        const ok = await deleteAction(idToDelete, matched?.employee_id || employeeId);
        if (!ok) {
          throw new Error('Failed to delete corrective action on server');
        }
      }
    },
    [deleteAction, storedActions],
  );

  const handleDeleteRoleAction = useCallback(
    async (action: RoleAssignedAction) => {
      const isInStore = storedActions.some((a) => a.id === action.id);
      if ((!action.suggested || isInStore) && typeof deleteAction === 'function') {
        const targetEmployeeId =
          action.employeeId ||
          resolvedRoleData?.employeeId ||
          storedActions.find((a) => a.id === action.id)?.employee_id ||
          '';
        const ok = await deleteAction(action.id, targetEmployeeId || undefined);
        if (!ok) {
          throw new Error('Failed to delete role action on server');
        }
      }
    },
    [deleteAction, resolvedRoleData?.employeeId, storedActions],
  );

  const [presentationMode, setPresentationMode] = useState(false);
  // The global filter counts the always-applied region plus any active branch
  // and function deep dive; the reporting month is a required dimension, not a
  // filter (same as InsightsHeader, which does not count its period either).
  // Unlocked branch and function deep dive can be cleared back to the overview.
  // The combined All view is the unfiltered state, so it adds nothing to the badge.
  const monthlyFilterActiveCount =
    (activeRegion !== 'ALL' ? 1 : 0) +
    (activeBranch ? 1 : 0) +
    (functionSlug ? 1 : 0);
  const monthlyFilterClearableCount =
    (!branchLockedSingle && activeBranch ? 1 : 0) +
    (functionSlug ? 1 : 0);
  const hasRegionTabs = availableRegions.length > 1;
  const headerToolbar = hasRegionTabs || activeBranchLabel ? (
    <>
      {hasRegionTabs && (
        <div
          role="tablist"
          aria-label="Region filter"
          className="inline-flex h-9 items-center rounded-xl border border-slate-200 bg-slate-100 p-0.5 shadow-2xs"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeRegion === 'ALL'}
            data-testid="region-all"
            onClick={() => handleRegionChange('ALL')}
            disabled={!availableRegions.includes('ALL')}
            className={`compact-control inline-flex h-8 !min-h-0 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition-all ${
              activeRegion === 'ALL'
                ? 'bg-white font-bold text-blue-600 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <span>All regions</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeRegion === 'EGY'}
            data-testid="region-egy"
            onClick={() => handleRegionChange('EGY')}
            disabled={!availableRegions.includes('EGY')}
            className={`compact-control inline-flex h-8 !min-h-0 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition-all ${
              activeRegion === 'EGY'
                ? 'bg-white font-bold text-blue-600 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <EgyptFlag className="size-3.5" />
            <span>Egypt (EGY)</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeRegion === 'UAE'}
            data-testid="region-uae"
            onClick={() => handleRegionChange('UAE')}
            disabled={!availableRegions.includes('UAE')}
            className={`compact-control inline-flex h-8 !min-h-0 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition-all ${
              activeRegion === 'UAE'
                ? 'bg-white font-bold text-blue-600 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <UaeFlag className="size-3.5" />
            <span>UAE</span>
          </button>
        </div>
      )}
      {activeBranchLabel && (
        <span
          data-testid="active-branch-pill"
          className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-cyan-200 bg-cyan-50 px-3 text-xs font-semibold text-cyan-800 shadow-2xs"
        >
          <span className="size-1.5 rounded-full bg-cyan-500" aria-hidden="true" />
          <span>Branch: {activeBranchLabel}</span>
          {!branchLockedSingle && (
            <button
              type="button"
              aria-label={`Clear ${activeBranchLabel} branch filter`}
              onClick={() => handleBranchChange('')}
              className="compact-control ml-0.5 inline-flex size-5 !min-h-0 items-center justify-center rounded-md text-cyan-700 transition-colors hover:bg-cyan-100 hover:text-cyan-950"
            >
              ×
            </button>
          )}
        </span>
      )}
    </>
  ) : null;

  const insideDetail = Boolean(activeTeamSlug || activeRoleSlug);
  const functionSlugs = overviewData.functions.map((fn) => fn.slug);
  const previousDisabled = !functionSlug && !insideDetail;
  const nextDisabled = !insideDetail && (
    functionSlugs.length === 0 || functionSlug === functionSlugs[functionSlugs.length - 1]
  );

  const handleStep = useCallback((direction: 'next' | 'previous') => {
    if (direction === 'previous' && previousDisabled) return;
    if (direction === 'next' && nextDisabled) return;
    const result = stepPresentation({
      slugs: functionSlugs,
      currentSlug: functionSlug,
      direction,
      insideDetail,
    });
    const next = new URLSearchParams(searchParams);
    if (result.slug) next.set('deepDive', result.slug);
    else next.delete('deepDive');
    if (result.clearDetail || result.slug === null) {
      next.delete('team');
      next.delete('role');
    }
    if (!isInline && !result.slug && params.functionSlug) {
      const basePath = location.pathname.startsWith('/monthly-view')
        ? '/monthly-view'
        : '/monthly-presentation';
      const query = next.toString();
      navigate(`${basePath}${query ? `?${query}` : ''}`);
    } else {
      setSearchParams(next);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [
    functionSlug,
    functionSlugs,
    insideDetail,
    isInline,
    location.pathname,
    navigate,
    nextDisabled,
    params.functionSlug,
    previousDisabled,
    searchParams,
    setSearchParams,
  ]);

  const renderActiveView = () => {
    if (activeTeamSlug && !functionSlug) {
      return null;
    }

    if (activeTeamSlug && functionSlug && !teamBelongsToFunction(activeTeamSlug, functionSlug, activeRegion)) {
      return null;
    }

    if (chooseTeamCountry) return (
      <section aria-label="Choose team country" className="pms-glass-surface mx-auto w-full max-w-7xl space-y-3 rounded-[16px] p-5">
        <button type="button" className={reviewButtonClass} onClick={handleBackToOverview}>Executive Summary</button>
        <h1 className="text-xl font-bold text-[var(--insights-heading)]">{resolvedTeamData?.teamDisplayName ?? businessTeamName(rawTeamParam)}</h1>
        <p className="text-sm text-[var(--text-secondary)]">Select a country to review this team.</p>
        <div className="flex flex-wrap gap-2">
          {teamCountries.map((country) => (
            <button key={country} type="button" className={reviewButtonClass} onClick={() => {
              const next = new URLSearchParams(searchParams);
              next.set('teamRegion', country);
              next.delete('employee');
              setSearchParams(next);
            }}>{country === 'EGY' ? 'Egypt' : 'UAE'}</button>
          ))}
        </div>
      </section>
    );

    if (activeRoleSlug && resolvedRoleData) {
      const roleDetail = isInline ? {
        ...resolvedRoleData,
        actions: resolvedRoleData.actions.filter((action) => !action.suggested),
        individualActionPlans: resolvedRoleData.individualActionPlans.filter((action) => !action.suggested),
      } : resolvedRoleData;
      return (
        <>
        <RoleDetailView
          key={resolvedRoleData.roleSlug}
          data={roleDetail}
          onNavigateToOverview={handleBackToOverview}
          onNavigateToFunction={handleBackToFunction}
          onSaveAction={handleSaveRoleAction}
          onDeleteAction={handleDeleteRoleAction}
          onDeleteIndividualAction={handleDeleteIndividualAction}
          toolbar={isInline ? employeePicker : headerToolbar}
          presentationMode={isInline || presentationMode}
          overviewLabel={isInline ? 'Executive Summary' : undefined}
          onSelectEmployee={isInline ? selectEmployee : openEmployeeProfile}
        />
        {isInline && canReadInlineActions && <ExecutiveTeamDecisions records={inlineMembers} />}
        </>
      );
    }

    if (activeTeamSlug && resolvedTeamData) {
      const teamDetail = isInline ? {
        ...resolvedTeamData,
        individualActionPlans: resolvedTeamData.individualActionPlans.filter((action) => action.isSavedToStore),
        teamActionPlans: [],
      } : resolvedTeamData;
      return (
        <>
        <TeamDeepDiveView
          data={teamDetail}
          onNavigateToOverview={handleBackToOverview}
          onNavigateToCallCenter={handleBackToFunction}
          onSwitchTeam={handleSelectAgentTeam}
          onSaveIndividualAction={handleSaveIndividualAction}
          onDeleteIndividualAction={handleDeleteIndividualAction}
          savedTeamActions={savedTeamActionsForActiveScope}
          onSaveTeamAction={handleSaveTeamAction}
          onDeleteTeamAction={handleDeleteTeamAction}
          onRestoreTeamActions={handleRestoreTeamActions}
          toolbar={isInline ? employeePicker : headerToolbar}
          presentationMode={isInline || presentationMode}
          overviewLabel={isInline ? 'Executive Summary' : undefined}
          onSelectEmployee={isInline ? selectEmployee : openEmployeeProfile}
        />
        {isInline && canReadInlineActions && <ExecutiveTeamDecisions records={inlineMembers} overallOnly />}
        </>
      );
    }

    if (functionSlug && resolvedFunctionData) {
      if (isInline) {
        const inlineScopeChips = [
          activeRegion === 'ALL' ? 'All countries' : activeRegion === 'EGY' ? 'Egypt (EGY)' : 'UAE',
          activeBranchLabel ? `Branch: ${activeBranchLabel}` : null,
          level && level !== 'all' ? `${level.charAt(0).toUpperCase()}${level.slice(1)} level` : null,
        ].filter((chip): chip is string => Boolean(chip));
        return (
          <ExecutiveFunctionReview
            name={resolvedFunctionData.functionName}
            month={resolvedFunctionData.monthLabel}
            score={resolvedFunctionData.headline.score}
            records={currentFunctionRecords}
            units={reviewUnits}
            actions={storedActions}
            canSeeActions={canReadInlineActions}
            scopeChips={inlineScopeChips}
            onOverview={handleBackToOverview}
            onSelectUnit={selectReviewUnit}
          />
        );
      }
      if (isRoleBasedFunction(resolvedFunctionData.functionSlug)) {
        return (
          <div className="mx-auto max-w-7xl space-y-6">
            <FunctionDeepDiveView
              data={resolvedFunctionData}
              roles={roleCards}
              onBackToOverview={handleBackToOverview}
              onSelectRole={handleSelectRole}
              toolbar={headerToolbar}
              presentationMode={presentationMode}
            />
            {!explicitPreview && currentFunctionRecords.length > 0 && (
              <TeamsWithoutMonthlyData
                teams={teamsWithoutData.map(({ team, region }) => ({ team, region }))}
                periodLabel={periodFromKey(selectedPeriodKey)?.label ?? selectedPeriodKey}
              />
            )}
          </div>
        );
      }
      return (
        <div className="mx-auto max-w-7xl space-y-6">
          <CallCenterDeepDiveView
            data={resolvedFunctionData}
            onBackToOverview={handleBackToOverview}
            onSelectAgentTeam={handleSelectAgentTeam}
            onSelectRole={handleSelectRole}
            onSelectEmployee={openEmployeeProfile}
            toolbar={headerToolbar}
          />
          {!explicitPreview && currentFunctionRecords.length > 0 && (
            <TeamsWithoutMonthlyData
              teams={teamsWithoutData.map(({ team, region }) => ({ team, region }))}
              periodLabel={periodFromKey(selectedPeriodKey)?.label ?? selectedPeriodKey}
            />
          )}
        </div>
      );
    }

    // Level 1: Monthly Overview
    return (
      <div
        data-testid="monthly-overview-page"
        className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8"
      >
        {/* 1. Header */}
        <MonthlyOverviewHeader
          title={overviewData.title}
          flowName={overviewData.FlowName}
          regionName={overviewData.regionName}
          branchLabel={activeBranchLabel}
          monthLabel={overviewData.monthLabel}
          regionCode={overviewData.regionCode}
          pageIndicatorLabel={overviewData.pageIndicator.label}
          toolbar={headerToolbar}
        />

        {/* 2. Overall Company Performance & 3. Company Score Trend */}
        <div className="grid grid-cols-1 items-stretch gap-6 lg:grid-cols-12">
          <div className="flex lg:col-span-6">
            <OverallCompanyPerformanceCard
              overall={overviewData.overall}
              previousMonthLabel={overviewData.previousMonthLabel}
            />
          </div>
          <div className="flex lg:col-span-6">
            <SixMonthTrendCard
              trend={overviewData.trend}
              executiveTrend={overviewData.executiveTrend}
            />
          </div>
        </div>

        {/* 3b. Region Performance Share (All regions view, matching Executive Summary) */}
        {overviewData.regionCode === 'ALL' && (overviewData.regions?.length ?? 0) > 1 && (
          <RegionPerformanceShareSection
            regions={overviewData.regions ?? []}
            previousMonthLabel={overviewData.previousMonthLabel}
            onSelectRegion={(region) => handleRegionChange(region)}
          />
        )}

        {/* 4. Grade Distribution */}
        <GradeDistributionSection
          totalEmployees={overviewData.gradeDistribution.totalEmployees}
          rows={overviewData.gradeDistribution.rows}
          takeaway={overviewData.gradeDistribution.takeaway}
          previousMonthLabel={overviewData.previousMonthLabel}
        />

        {/* 5. What Moved the Score vs August */}
        <ScoreDriversSection
          previousMonthLabel={overviewData.previousMonthLabel}
          negativeDrivers={overviewData.drivers.negative}
          positiveDrivers={overviewData.drivers.positive}
        />

        {/* 6. Functions Overview */}
        <FunctionsOverviewSection
          functions={overviewData.functions}
          previousMonthLabel={overviewData.previousMonthLabel}
          onSelectFunction={handleFunctionClick}
        />

        {/* 7. Teams at Risk (Summary) */}
        <TeamsAtRiskSection
          teams={overviewData.teamsAtRisk}
          onSelectTeam={(row) => {
            const match = overviewData.functions.find((fn) => fn.functionName === row.functionName);
            handleSelectAgentTeam(businessTeamName(row.team), match?.slug || row.functionName);
          }}
        />

        {/* 8. Corrective Actions (Monthly Review main page only) */}
        {canReadInlineActions && (
          <div
            id="presentation-section-actions"
            data-section-label="Actions"
            className="scroll-mt-24"
          >
            <CorrectiveActionInsightsCard
              data={overviewCorrectiveActions}
              effective={selectedExecPeriod}
              scopeLabel={overviewActionsScopeLabel}
              workspaceHref="/corrective-actions"
            />
          </div>
        )}
      </div>
    );
  };

  const agendaTimeline = useMemo<AgendaTimelineFunction[]>(() => {
    if (isInline) return [];
    const sorted = [...overviewData.functions].sort((a, b) => a.score - b.score);
    return sorted.map((fn) => {
      const fnDeepDive =
        explicitPreview && !activeBranch && fn.slug === 'call-center' && callCenterDeepDiveData
          ? callCenterDeepDiveData
          : buildFunctionDeepDiveFromRecords(
              fn.slug,
              branchScopedRecords,
              storedActions,
              activeRegion,
              selectedPeriodKey,
              { allowSnapshotFallback: explicitPreview && !activeBranch },
            );

      if (isRoleBasedFunction(fn.slug)) {
        const cards = resolveRoleCards(fnDeepDive, branchScopedRecords).sort(
          (a, b) => a.score - b.score,
        );
        const withIssues = cards.filter((c) => c.score < 90);
        const displayCards = withIssues.length > 0 ? withIssues : cards.slice(0, 3);
        return {
          slug: fn.slug,
          functionName: fn.functionName,
          score: fn.score,
          subKindLabel: 'Roles',
          subItems: displayCards.map((c) => ({
            slug: c.roleSlug,
            name: c.roleTitle,
            score: c.score,
            kind: 'role' as const,
            hasIssue: c.score < 90,
          })),
          allUnits: cards.map((c) => ({
            slug: c.roleSlug,
            name: c.roleTitle,
            score: c.score,
            kind: 'role' as const,
            hasIssue: c.score < 90,
          })),
        };
      }

      const teams = [...(fnDeepDive.agentTeams ?? [])].sort((a, b) => a.score - b.score);
      const withIssues = teams.filter((t) => t.score < 90 || t.roleTone === 'warning');
      const displayTeams = withIssues.length > 0 ? withIssues : teams;
      return {
        slug: fn.slug,
        functionName: fn.functionName,
        score: fn.score,
        subKindLabel: 'Teams',
        subItems: displayTeams.map((t) => ({
          slug: t.teamSlug,
          name: t.teamName,
          score: t.score,
          kind: 'team' as const,
          hasIssue: t.score < 90 || t.roleTone === 'warning',
        })),
        allUnits: teams.map((t) => ({
          slug: t.teamSlug,
          name: t.teamName,
          score: t.score,
          kind: 'team' as const,
          hasIssue: t.score < 90 || t.roleTone === 'warning',
        })),
      };
    });
  }, [
    activeBranch,
    activeRegion,
    branchScopedRecords,
    callCenterDeepDiveData,
    explicitPreview,
    isInline,
    overviewData.functions,
    selectedPeriodKey,
    storedActions,
  ]);

  const monthlyPageContext = useMemo<PageContextV1>(() => {
    const primaryDriverMetric =
      resolvedTeamData?.kpis?.[0]?.label ??
      overviewData.drivers?.negative?.[0]?.kpiName ??
      null;
    const isFallbackData =
      !summaryRecordsQuery.isLoading &&
      !explicitPreview &&
      authorizedRecords.length === 0;
    const monthParts = (
      resolvedTeamData?.monthLabel ??
      resolvedFunctionData?.monthLabel ??
      overviewData.monthLabel ??
      ''
    ).split(' ');
    const parsedYear = Number(monthParts[1]);
    return {
      page_id: isInline ? 'executive_summary' : 'monthly_presentation',
      route_id: `${location.pathname}${location.search}`,
      region: activeRegion,
      branch: activeBranch || null,
      employee_id: selectedEmployee?.employeeId ?? null,
      period: selectedPeriodKey,
      month: monthParts[0] || null,
      year: Number.isFinite(parsedYear) && parsedYear >= 2000 ? parsedYear : null,
      function_id: resolvedFunctionData?.functionName ?? null,
      team_id: resolvedTeamData?.canonicalTeam ?? resolvedTeamData?.teamDisplayName ?? null,
      position_id: resolvedRoleData?.roleTitle ?? null,
      selected_metric_id: primaryDriverMetric,
      is_fallback_data: isFallbackData,
    };
  }, [
    activeBranch,
    activeRegion,
    authorizedRecords.length,
    explicitPreview,
    isInline,
    location.pathname,
    location.search,
    overviewData.drivers?.negative,
    overviewData.monthLabel,
    resolvedFunctionData?.functionName,
    resolvedFunctionData?.monthLabel,
    resolvedRoleData?.roleTitle,
    resolvedTeamData?.canonicalTeam,
    resolvedTeamData?.kpis,
    resolvedTeamData?.monthLabel,
    resolvedTeamData?.teamDisplayName,
    selectedEmployee?.employeeId,
    selectedPeriodKey,
    summaryRecordsQuery.isLoading,
  ]);
  const pageIsLoading = !explicitPreview && (summaryRecordsQuery.isLoading || catalogQuery.isLoading);
  const pageHasError = !explicitPreview && (summaryRecordsQuery.isError || catalogQuery.isError);
  const hasNoAssignments = !pageIsLoading && !pageHasError &&
    (functionScopeRestricted
      ? authorizedFunctionNames.length === 0
      : !explicitPreview && serverTeams.length === 0);
  const invalidRegionRequest = !explicitPreview && Boolean(rawRegion) &&
    (!normalizedUrlRegion || !availableRegions.includes(normalizedUrlRegion as MonthlyRegionFilter));
  const invalidBranchRequest = !explicitPreview && Boolean(rawBranch) &&
    !(assigned.branchLocked && assigned.branch ? rawBranch === assigned.branch : availableBranchValues.has(rawBranch));
  const invalidFunctionRequest = Boolean(functionSlug) && !isFunctionAuthorized(functionSlug);
  const invalidTeamRequest = Boolean(activeTeamSlug) && (
    !functionSlug || !teamBelongsToFunction(activeTeamSlug, functionSlug, activeRegion)
  );
  const invalidRoleRequest = Boolean(activeRoleSlug) && (
    !resolvedFunctionData || !hasRoleDetailForSlug(resolvedFunctionData, activeRoleSlug, branchScopedRecords)
  );
  const invalidScopeRequest =
    invalidRegionRequest || invalidBranchRequest || invalidFunctionRequest || invalidTeamRequest || invalidRoleRequest;
  const selectionHasData = activeRoleSlug
    ? Boolean(
        resolvedRoleData && (
          currentRoleRecords.length > 0 ||
          (resolvedRoleData.members && resolvedRoleData.members.length > 0) ||
          resolvedRoleData.score > 0
        ),
      )
    : activeTeamSlug
      ? currentTeamRecords.length > 0
      : functionSlug
        ? currentFunctionRecords.length > 0
        : selectedPeriodRecords.length > 0;
  const noDataForSelection = !explicitPreview && !pageIsLoading && !pageHasError &&
    !hasNoAssignments && !invalidScopeRequest && !selectionHasData;
  const scopeTeamsForNoData = activeBranch
    ? []
    : activeTeamSlug
      ? teamsInCurrentFunction.filter((team) => {
          const teamCountry = parseTeamCountry(normalizeRegion(team.region));
          return team.team !== CALL_CENTER_TEAM &&
            (slugifyIdentifier(team.team) === activeTeamSlug
              || (teamCountry !== null && sameCountryBusinessTeam(team.team, activeTeamSlug, teamCountry)));
        })
      : teamsInCurrentFunction.filter((team) => team.team !== CALL_CENTER_TEAM);
  const selectedPeriodLabel = periodFromKey(selectedPeriodKey)?.label ?? selectedPeriodKey;

  if (pageIsLoading) {
    return <MonthlyReviewLoading toolbar={headerToolbar} />;
  }

  if (pageHasError || hasNoAssignments || invalidScopeRequest || noDataForSelection) {
    const surfaceName = isInline ? 'Executive Summary analysis' : 'Monthly Review';
    const heading = pageHasError
        ? `${surfaceName} data could not be loaded`
        : hasNoAssignments
          ? isInline
            ? 'No assigned teams in scope'
            : 'No monthly review assignments'
          : invalidScopeRequest
            ? `This ${surfaceName} scope is outside your access`
            : activeBranchLabel
              ? `No performance data for ${activeBranchLabel} in ${selectedPeriodLabel}`
              : `No performance data for ${selectedPeriodLabel}`;
    const detail = pageHasError
        ? 'The authorized team list or performance records could not be fetched. Retry to load your scope again.'
        : hasNoAssignments
          ? functionScopeRestricted
            ? `Your account has no authorized function for ${surfaceName}. Contact your administrator to request access.`
            : 'No active teams are currently assigned to your account. Contact your administrator if this looks wrong.'
          : invalidScopeRequest
            ? 'The requested region, branch, function, team, or position is not included in your authorized scope.'
            : activeBranchLabel
              ? `No results were found for ${activeBranchLabel} in the selected scope and period.`
              : functionSlug
                ? 'No results were uploaded for this function, team, or position in the selected period.'
                : 'No results were uploaded for your authorized scope in the selected period.';

    return (
      <main className="mx-auto max-w-7xl space-y-5 px-4 py-8 sm:px-6 lg:px-8">
        {isInline && <button type="button" className={reviewButtonClass} onClick={handleBackToOverview}>Back to Executive Summary</button>}
        {!isInline && headerToolbar && <div className="flex flex-wrap items-center gap-3">{headerToolbar}</div>}
        <section
          data-testid={hasNoAssignments ? 'monthly-assignment-message' : noDataForSelection ? 'monthly-no-data' : pageHasError ? 'monthly-data-error' : 'monthly-scope-restricted'}
          role={pageHasError || invalidScopeRequest ? 'alert' : 'status'}
          aria-live="polite"
          className={
            isInline
              ? `pms-glass-surface rounded-[16px] p-5 sm:p-6 ${pageHasError || invalidScopeRequest ? 'border-[var(--pms-grad-panel-neg-border)]' : ''}`
              : `rounded-2xl border p-5 sm:p-6 ${pageHasError || invalidScopeRequest ? 'border-rose-200 bg-rose-50' : 'border-slate-200 bg-white'}`
          }
          style={isInline && (pageHasError || invalidScopeRequest) ? { background: 'var(--pms-grad-panel-neg)' } : undefined}
        >
          <h1 className={`text-lg font-bold ${isInline ? 'text-[var(--insights-heading)]' : 'text-slate-900'}`}>{heading}</h1>
          <p className={`mt-2 text-sm ${isInline ? 'text-[var(--text-secondary)]' : 'text-slate-600'}`}>{detail}</p>
          {!pageIsLoading && !pageHasError && !hasNoAssignments && !invalidScopeRequest && (
            <div className="mt-4 flex flex-wrap items-end gap-3">
              <label className={`flex max-w-xs flex-col gap-1 text-xs font-semibold ${isInline ? 'text-[var(--text-secondary)]' : 'text-slate-600'}`}>
                Reporting month
                <select
                  aria-label="Reporting month"
                  value={selectedPeriodKey}
                  onChange={(event) => handlePeriodChange(event.target.value)}
                  className={
                    isInline
                      ? 'h-10 rounded-[10px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-3 text-sm text-[var(--insights-heading)]'
                      : 'h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900'
                  }
                >
                  {monthOptions.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}
                </select>
              </label>
              {availableBranches.length > 0 && (
                <label className={`flex max-w-xs flex-col gap-1 text-xs font-semibold ${isInline ? 'text-[var(--text-secondary)]' : 'text-slate-600'}`}>
                  Branch
                  <select
                    aria-label="Branch"
                    value={activeBranch}
                    disabled={branchLockedSingle}
                    onChange={(event) => handleBranchChange(event.target.value)}
                    className={
                      isInline
                        ? 'h-10 rounded-[10px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-3 text-sm text-[var(--insights-heading)] disabled:cursor-not-allowed disabled:opacity-60'
                        : 'h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500'
                    }
                  >
                    {!branchLockedSingle && <option value="">All branches</option>}
                    {availableBranches.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
              )}
              {!isInline && functionSlug && (
                <button
                  type="button"
                  onClick={handleBackToOverview}
                  className="h-10 rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Back to overview
                </button>
              )}
            </div>
          )}
          {pageHasError && (
            <button
              type="button"
              className={
                isInline
                  ? `mt-4 ${reviewButtonClass}`
                  : 'mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700'
              }
              onClick={() => { void summaryRecordsQuery.refetch(); void catalogQuery.refetch(); }}
            >
              Try again
            </button>
          )}
        </section>
        {noDataForSelection && scopeTeamsForNoData.length > 0 && (
          <TeamsWithoutMonthlyData
            teams={scopeTeamsForNoData.map(({ team, region }) => ({ team, region }))}
            periodLabel={selectedPeriodLabel}
          />
        )}
      </main>
    );
  }

  if (isInline) return (
    <>
      {activeEmployeeId && !selectedEmployee && <p role="status" className="px-4 py-2 text-sm">This employee is outside the selected analysis.</p>}
      <div hidden={Boolean(selectedEmployee)}>{renderActiveView()}</div>
      {selectedEmployee && (
        <ExecutiveEmployeeReview
          record={selectedEmployee}
          team={teamLabel}
          functionName={resolvedFunctionData?.functionName ?? functionSlug}
          actions={storedActions.filter((action) => !isSavedRoleIntervention(action) && actionMatchesRecord(action, selectedEmployee))}
          canSeeActions={canReadInlineActions}
          onOverview={handleBackToOverview}
          onFunction={handleBackToFunction}
          onTeam={() => selectEmployee('')}
        />
      )}
      <ContextualAssistantPanel pageContext={monthlyPageContext} />
    </>
  );

  return (
    <>
      <div className="pb-28">{renderActiveView()}</div>
      <PresentationControlBar
        region={activeRegion}
        availableRegions={availableRegions}
        onRegionChange={handleRegionChange}
        branch={activeBranch}
        branchOptions={availableBranches}
        branchLocked={branchLockedSingle}
        onBranchChange={handleBranchChange}
        filterActiveCount={monthlyFilterActiveCount}
        filterClearableCount={monthlyFilterClearableCount}
        onClearFilters={handleClearFilters}
        periodKey={selectedPeriodKey}
        monthOptions={monthOptions}
        onPeriodChange={handlePeriodChange}
        presentationMode={presentationMode}
        onPresentationModeChange={setPresentationMode}
        onPrevious={() => handleStep('previous')}
        onNext={() => handleStep('next')}
        previousDisabled={previousDisabled}
        nextDisabled={nextDisabled}
        functions={overviewData.functions}
        timelineItems={agendaTimeline}
        drivers={overviewData.drivers}
        overallScore={overviewData.overall.score}
        activeFunctionSlug={functionSlug}
        activeTeamSlug={activeTeamSlug}
        activeRoleSlug={activeRoleSlug}
        onSelectOverview={handleBackToOverview}
        onSelectFunctionSlug={(slug) => {
          const match = overviewData.functions.find((fn) => fn.slug === slug);
          if (match) {
            handleFunctionClick(match);
          }
        }}
        onSelectSubItem={(fnSlug, sub) => {
          if (sub.kind === 'team') {
            handleSelectAgentTeam(sub.slug, fnSlug);
          } else {
            const next = new URLSearchParams(searchParams);
            next.set('deepDive', fnSlug);
            next.set('role', sub.slug);
            next.delete('team');
            setSearchParams(next);
            window.scrollTo({ top: 0, behavior: 'smooth' });
          }
        }}
      />
      <ContextualAssistantPanel pageContext={monthlyPageContext} />
    </>
  );
}
