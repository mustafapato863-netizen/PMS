import { useCallback, useEffect, useMemo, useState } from 'react';
import './macCursor.css';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/auth';
import { useUserRole } from '../../context/RoleContext';
import { directorScope } from '../../lib/directorScope';
import { isFunctionViewerRole, readAccessibleFunctions } from '../../lib/access';
import { usePerformanceCatalog } from '../../hooks/api/usePerformanceCatalog';
import { composeExecutiveSummary, normalizeRegion, toExecRecords } from '../executive/compose';
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
  type IndividualActionPlanCard,
  type TeamDeepDiveData,
} from './teamDeepDiveData';
import { buildRoleDetail, hasRoleDetailForSlug, isRoleBasedFunction, resolveRoleCards, type RoleActionDraft } from './roleDetailData';
import {
  FunctionsOverviewSection,
  GradeDistributionSection,
  MonthlyOverviewHeader,
  OverallCompanyPerformanceCard,
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
import { PresentationSectionFrame } from './components/SectionRail';
import RoleDetailView from './components/RoleDetailView';
import TeamDeepDiveView from './components/TeamDeepDiveView';
import { isMonthAvailable, periodFromKey } from './model';
import { presentationMonthOptions, stepPresentation } from './presentationControls';

export type MonthlyRegionFilter = 'EGY' | 'UAE';

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
            {team.team}{team.region ? ` · ${team.region}` : ''}
          </li>
        ))}
      </ul>
    </section>
  );
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
}: MonthlyPresentationViewProps) {
  useEffect(() => {
    document.body.classList.add('mp-mac-cursor');
    return () => {
      document.body.classList.remove('mp-mac-cursor');
    };
  }, []);

  const { role } = useUserRole();
  const { currentUser } = useAuth();
  const assigned = directorScope(role, currentUser);
  const [searchParams, setSearchParams] = useSearchParams();
  const params = useParams<{ functionSlug?: string; teamSlug?: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  // Connect to real performance summary records & corrective actions store
  const summaryRecordsQuery = useSummaryRecords(true);
  const catalogQuery = usePerformanceCatalog(true);
  const execRecords = useMemo(
    () => toExecRecords(summaryRecordsQuery.data ?? []),
    [summaryRecordsQuery.data],
  );
  const explicitPreview = Boolean(data || callCenterDeepDiveData || teamDeepDiveData);
  const functionScopeRestricted = isFunctionViewerRole(role);
  const serverTeams = catalogQuery.data?.teams ?? [];
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
    if (explicitPreview) return ['EGY', 'UAE'];
    const regions = new Set<MonthlyRegionFilter>();
    for (const team of serverTeams) {
      const normalized = normalizeRegion(team.region);
      if (normalized === 'EGY' || normalized === 'UAE') regions.add(normalized);
    }
    return [...regions].sort((a, b) => (a === 'EGY' ? -1 : b === 'EGY' ? 1 : 0));
  }, [explicitPreview, serverTeams]);
  const { getAllActions, saveAction } = useActionStore();
  const storedActions = getAllActions();

  const rawRegion = searchParams.get('region');
  const normalizedUrlRegion = normalizeRegion(rawRegion);
  const periodParam = searchParams.get('period') || searchParams.get('month') || undefined;

  const activeRegion: MonthlyRegionFilter = useMemo(() => {
    const validRegions: MonthlyRegionFilter[] = availableRegions.length ? availableRegions : ['EGY'];
    if (
      (normalizedUrlRegion === 'UAE' || normalizedUrlRegion === 'EGY') &&
      validRegions.includes(normalizedUrlRegion)
    ) return normalizedUrlRegion;
    const assignedRegion = normalizeRegion(assigned.region);
    if ((assignedRegion === 'UAE' || assignedRegion === 'EGY') && validRegions.includes(assignedRegion)) {
      return assignedRegion;
    }
    if (explicitPreview && data?.regionCode && validRegions.includes(data.regionCode)) {
      return data.regionCode;
    }
    return validRegions[0];
  }, [
    assigned.region,
    data?.regionCode,
    explicitPreview,
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
      return serverTeams.some((team) => {
        if (slugifyIdentifier(team.team) !== slugifyIdentifier(record.team)) return false;
        const teamRegion = normalizeRegion(team.region);
        if (recordRegion && teamRegion && recordRegion !== teamRegion) return false;
        return team.performance_levels.some((level) => level.toLowerCase() === recordLevel);
      });
    });
  }, [execRecords, explicitPreview, serverTeams]);

  const overviewData: MonthlyOverviewData = useMemo(() => {
    const base =
      explicitPreview && data && data.regionCode === activeRegion
        ? data
        : adaptSummaryToMonthlyOverview(
            composeExecutiveSummary({
              view: 'corporate',
              role,
              records: authorizedRecords,
              filters: { region: activeRegion },
              today: clock,
              requestedPeriodKey,
            }),
            activeRegion,
            { allowSnapshotFallback: explicitPreview },
          );
    const regionFunctionSlugs = new Set(
      (explicitPreview ? authorizedFunctionNames : serverTeams
        .filter((team) => normalizeRegion(team.region) === activeRegion)
        .flatMap((team) => team.functions))
        .map(normalizeFunctionSlug),
    );
    return {
      ...base,
      functions: base.functions.filter((fn) =>
        regionFunctionSlugs.has(fn.slug) &&
        (!functionScopeRestricted || authorizedFunctionSlugs.has(fn.slug)),
      ),
    };
  }, [
    activeRegion,
    authorizedFunctionNames,
    authorizedFunctionSlugs,
    authorizedRecords,
    clock,
    data,
    explicitPreview,
    functionScopeRestricted,
    requestedPeriodKey,
    role,
    serverTeams,
  ]);

  const latestAuthorizedPeriod = authorizedRecords
    .filter((record) => normalizeRegion(record.region) === activeRegion)
    .map((record) => record.period.key)
    .sort((a, b) => b.localeCompare(a))[0];
  const currentPeriodKey = `${clock.getFullYear()}-${String(clock.getMonth() + 1).padStart(2, '0')}`;
  const displayedPeriodKey = requestedPeriodKey ??
    (explicitPreview && data?.regionCode === activeRegion ? data.periodKey : undefined) ??
    latestAuthorizedPeriod ??
    currentPeriodKey;
  const monthOptions = useMemo(
    () => presentationMonthOptions(
      authorizedRecords.map((record) => ({ region: record.region, periodKey: record.period.key })),
      activeRegion,
      clock,
      displayedPeriodKey,
    ),
    [activeRegion, authorizedRecords, clock, displayedPeriodKey],
  );
  const selectedPeriodKey = displayedPeriodKey;

  const rawDeepDive = (searchParams.get('deepDive') || params.functionSlug || '').trim();
  const functionSlug = rawDeepDive ? normalizeFunctionSlug(rawDeepDive) : '';
  const rawTeamParam = (searchParams.get('team') || params.teamSlug || '').trim();
  const activeTeamSlug = rawTeamParam ? slugifyIdentifier(rawTeamParam) : '';
  const rawRoleParam = (searchParams.get('role') || '').trim();
  const activeRoleSlug = rawRoleParam ? slugifyIdentifier(rawRoleParam) : '';

  const allowedFunctions = functionScopeRestricted ? authorizedFunctionNames : null;

  const isFunctionAuthorized = useCallback((fnSlug: string) => {
    if (!fnSlug) return false;
    if (functionScopeRestricted) return authorizedFunctionSlugs.has(fnSlug);
    if (explicitPreview) return overviewData.functions.some((fn) => fn.slug === fnSlug);
    return serverTeams.some((team) =>
      normalizeRegion(team.region) === activeRegion &&
      team.functions.some((name) => normalizeFunctionSlug(name) === fnSlug),
    );
  }, [activeRegion, authorizedFunctionSlugs, explicitPreview, functionScopeRestricted, overviewData.functions, serverTeams]);

  const teamBelongsToFunction = useCallback(
    (
      teamSlug: string,
      fnSlug: string,
      region: MonthlyRegionFilter,
    ) => {
      return serverTeams.some((team) =>
        slugifyIdentifier(team.team) === teamSlug &&
        normalizeRegion(team.region) === region &&
        team.functions.some((name) => normalizeFunctionSlug(name) === fnSlug),
      );
    },
    [serverTeams],
  );

  const selectedPeriodRecords = useMemo(
    () => authorizedRecords.filter(
      (record) => normalizeRegion(record.region) === activeRegion && record.period.key === selectedPeriodKey,
    ),
    [activeRegion, authorizedRecords, selectedPeriodKey],
  );
  const currentFunctionRecords = useMemo(
    () => selectedPeriodRecords.filter((record) => {
      const metadata = serverTeams.find((team) =>
        slugifyIdentifier(team.team) === slugifyIdentifier(record.team) &&
        normalizeRegion(team.region) === activeRegion,
      );
      return metadata?.functions.some((name) => normalizeFunctionSlug(name) === functionSlug) ?? false;
    }),
    [activeRegion, functionSlug, selectedPeriodRecords, serverTeams],
  );
  const currentTeamRecords = useMemo(
    () => selectedPeriodRecords.filter((record) => slugifyIdentifier(record.team) === activeTeamSlug),
    [activeTeamSlug, selectedPeriodRecords],
  );
  const currentRoleRecords = useMemo(
    () => currentFunctionRecords.filter((record) => slugifyIdentifier(record.position ?? '') === activeRoleSlug),
    [activeRoleSlug, currentFunctionRecords],
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
    if ((normalizedUrlRegion === 'EGY' || normalizedUrlRegion === 'UAE') && availableRegions.includes(normalizedUrlRegion)) return;
    const next = new URLSearchParams(searchParams);
    next.delete('region');
    next.delete('deepDive');
    next.delete('team');
    next.delete('role');
    setSearchParams(next, { replace: true });
  }, [availableRegions, catalogQuery.isLoading, normalizedUrlRegion, rawRegion, searchParams, setSearchParams]);

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
    if (params.functionSlug) {
      const basePath = location.pathname.startsWith('/monthly-view')
        ? '/monthly-view'
        : '/monthly-presentation';
      const query = next.toString();
      navigate(`${basePath}${query ? `?${query}` : ''}`);
    } else {
      setSearchParams(next);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [location.pathname, navigate, params.functionSlug, searchParams, setSearchParams]);

  const handleSelectAgentTeam = useCallback(
    (teamSlug: string, functionName?: string) => {
      const next = new URLSearchParams(searchParams);
      const targetFunction = functionName
        ? normalizeFunctionSlug(functionName)
        : functionSlug || 'call-center';
      next.set('deepDive', targetFunction);
      next.set('team', slugifyIdentifier(teamSlug));
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
    next.delete('role');
    setSearchParams(next);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [functionSlug, searchParams, setSearchParams]);

  const resolvedFunctionData: CallCenterDeepDiveData | null = useMemo(() => {
    if (!functionSlug || !isFunctionAuthorized(functionSlug)) return null;
    if (!explicitPreview && currentFunctionRecords.length === 0) return null;
    if (functionSlug === 'call-center' && explicitPreview && callCenterDeepDiveData) return callCenterDeepDiveData;
    return buildFunctionDeepDiveFromRecords(
      functionSlug,
      authorizedRecords,
      storedActions,
      activeRegion,
      selectedPeriodKey,
    );
  }, [activeRegion, authorizedRecords, callCenterDeepDiveData, currentFunctionRecords.length, explicitPreview, functionSlug, isFunctionAuthorized, selectedPeriodKey, storedActions]);

  const roleCards = useMemo(() => {
    if (!resolvedFunctionData || !isRoleBasedFunction(resolvedFunctionData.functionSlug)) return [];
    return resolveRoleCards(resolvedFunctionData, authorizedRecords);
  }, [authorizedRecords, resolvedFunctionData]);

  const resolvedTeamData: TeamDeepDiveData | null = useMemo(() => {
    if (!activeTeamSlug || activeRoleSlug || !functionSlug || !teamBelongsToFunction(activeTeamSlug, functionSlug, activeRegion)) return null;
    if (!explicitPreview && currentTeamRecords.length === 0) return null;
    if (explicitPreview && teamDeepDiveData && teamDeepDiveData.teamSlug === activeTeamSlug) {
      return teamDeepDiveData;
    }
    return buildTeamDeepDiveFromRecords(
      activeTeamSlug,
      authorizedRecords,
      storedActions,
      activeRegion,
      selectedPeriodKey,
    );
  }, [activeRegion, activeRoleSlug, activeTeamSlug, authorizedRecords, currentTeamRecords.length, explicitPreview, functionSlug, selectedPeriodKey, storedActions, teamBelongsToFunction, teamDeepDiveData]);

  const resolvedRoleData = useMemo(() => {
    if (!activeRoleSlug || !resolvedFunctionData || (!explicitPreview && currentRoleRecords.length === 0)) return null;
    if (!hasRoleDetailForSlug(resolvedFunctionData, activeRoleSlug, authorizedRecords)) return null;
    return buildRoleDetail(resolvedFunctionData, activeRoleSlug, storedActions, authorizedRecords);
  }, [activeRoleSlug, authorizedRecords, currentRoleRecords.length, explicitPreview, resolvedFunctionData, storedActions]);

  const teamsInActiveRegion = serverTeams.filter((team) => normalizeRegion(team.region) === activeRegion);
  const teamsInCurrentFunction = functionSlug
    ? teamsInActiveRegion.filter((team) => team.functions.some((name) => normalizeFunctionSlug(name) === functionSlug))
    : teamsInActiveRegion;
  const teamsWithoutData = teamsInCurrentFunction.filter((team) =>
    !selectedPeriodRecords.some((record) =>
      slugifyIdentifier(record.team) === slugifyIdentifier(team.team) &&
      team.performance_levels.some((level) => level.toLowerCase() === String(record.level || 'Employee').toLowerCase()),
    ),
  );

  const handleSaveRoleAction = useCallback(
    async (draft: RoleActionDraft) => {
      await saveAction({
        employee_id: draft.employeeId,
        employee_name: draft.personName,
        team: draft.team,
        month: draft.month,
        action_type: 'Coaching',
        action_text: draft.description,
        root_cause_note: `Owner: ${draft.owner}. Status: ${draft.status}. Expected impact: ${draft.expectedImpact || 'Not specified'}.`,
        due_date: draft.dueDate || null,
        linked_kpi_key: draft.linkedKpiKey,
      });
    },
    [saveAction],
  );

  const handleSaveIndividualAction = useCallback(
    async (card: IndividualActionPlanCard) => {
      if (!resolvedTeamData) return;
      const monthName = resolvedTeamData.monthLabel.split(' ')[0] || 'September';
      await saveAction({
        employee_id: card.employeeId,
        employee_name: card.agentName,
        team: resolvedTeamData.canonicalTeam,
        month: monthName,
        action_type: 'Coaching',
        action_text: card.actionText,
        root_cause_note: card.mainIssue,
        linked_kpi_key: card.linkedKpiKey,
      });
    },
    [resolvedTeamData, saveAction],
  );

  const [presentationMode, setPresentationMode] = useState(false);
  const headerToolbar = (
    <>
      {availableRegions.length > 1 && (
        <div
          role="tablist"
          aria-label="Region filter"
          className="inline-flex h-9 items-center rounded-xl border border-slate-200 bg-slate-100 p-0.5 shadow-2xs"
        >
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


    </>
  );

  const insideDetail = Boolean(activeTeamSlug || activeRoleSlug);
  const functionSlugs = overviewData.functions.map((fn) => fn.slug);
  const previousDisabled = !functionSlug && !insideDetail;
  const nextDisabled = !insideDetail && (
    functionSlugs.length === 0 || functionSlug === functionSlugs[functionSlugs.length - 1]
  );

  const handlePeriodChange = useCallback((key: string) => {
    const next = new URLSearchParams(searchParams);
    if (!searchParams.has('period') && searchParams.has('month')) next.set('month', key);
    else next.set('period', key);
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

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
    if (!result.slug && params.functionSlug) {
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

    if (activeRoleSlug && resolvedRoleData) {
      return (
        <RoleDetailView
          key={resolvedRoleData.roleSlug}
          data={resolvedRoleData}
          onNavigateToOverview={handleBackToOverview}
          onNavigateToFunction={handleBackToFunction}
          onSaveAction={handleSaveRoleAction}
          toolbar={headerToolbar}
          presentationMode={presentationMode}
        />
      );
    }

    if (activeTeamSlug && resolvedTeamData) {
      return (
        <TeamDeepDiveView
          data={resolvedTeamData}
          onNavigateToOverview={handleBackToOverview}
          onNavigateToCallCenter={handleBackToFunction}
          onSwitchTeam={handleSelectAgentTeam}
          onSaveIndividualAction={handleSaveIndividualAction}
          toolbar={headerToolbar}
          presentationMode={presentationMode}
        />
      );
    }

    if (functionSlug && resolvedFunctionData) {
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
          monthLabel={overviewData.monthLabel}
          regionCode={overviewData.regionCode}
          pageIndicatorLabel={overviewData.pageIndicator.label}
          toolbar={headerToolbar}
        />

        {/* 2. Overall Company Performance & 3. 6-Month Score Trend */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <OverallCompanyPerformanceCard
              overall={overviewData.overall}
              previousMonthLabel={overviewData.previousMonthLabel}
            />
          </div>
          <div className="lg:col-span-5">
            <SixMonthTrendCard trend={overviewData.trend} />
          </div>
        </div>

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
            handleSelectAgentTeam(slugifyIdentifier(row.team), match?.slug || row.functionName);
          }}
        />
        {selectedPeriodRecords.length > 0 && (
          <TeamsWithoutMonthlyData
            teams={teamsWithoutData.map(({ team, region }) => ({ team, region }))}
            periodLabel={periodFromKey(selectedPeriodKey)?.label ?? selectedPeriodKey}
          />
        )}
      </div>
    );
  };

  const agendaTimeline = useMemo<AgendaTimelineFunction[]>(() => {
    const sorted = [...overviewData.functions].sort((a, b) => a.score - b.score);
    return sorted.map((fn) => {
      const fnDeepDive =
        explicitPreview && fn.slug === 'call-center' && callCenterDeepDiveData
          ? callCenterDeepDiveData
          : buildFunctionDeepDiveFromRecords(
              fn.slug,
              authorizedRecords,
              storedActions,
              activeRegion,
              selectedPeriodKey,
            );

      if (isRoleBasedFunction(fn.slug)) {
        const cards = resolveRoleCards(fnDeepDive, authorizedRecords).sort(
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
    activeRegion,
    authorizedRecords,
    callCenterDeepDiveData,
    explicitPreview,
    overviewData.functions,
    selectedPeriodKey,
    storedActions,
  ]);

  const sectionViewKey = [
    activeRegion,
    selectedPeriodKey,
    functionSlug,
    activeTeamSlug,
    activeRoleSlug,
    presentationMode ? 'present' : 'edit',
  ].join('|');

  const pageIsLoading = !explicitPreview && (summaryRecordsQuery.isLoading || catalogQuery.isLoading);
  const pageHasError = !explicitPreview && (summaryRecordsQuery.isError || catalogQuery.isError);
  const hasNoAssignments = !pageIsLoading && !pageHasError &&
    (functionScopeRestricted
      ? authorizedFunctionNames.length === 0
      : !explicitPreview && serverTeams.length === 0);
  const invalidRegionRequest = !explicitPreview && Boolean(rawRegion) &&
    (!normalizedUrlRegion || !availableRegions.includes(normalizedUrlRegion as MonthlyRegionFilter));
  const invalidFunctionRequest = Boolean(functionSlug) && !isFunctionAuthorized(functionSlug);
  const invalidTeamRequest = Boolean(activeTeamSlug) && (
    !functionSlug || !teamBelongsToFunction(activeTeamSlug, functionSlug, activeRegion)
  );
  const invalidRoleRequest = Boolean(activeRoleSlug) && (
    !resolvedFunctionData || !hasRoleDetailForSlug(resolvedFunctionData, activeRoleSlug, authorizedRecords)
  );
  const invalidScopeRequest = invalidRegionRequest || invalidFunctionRequest || invalidTeamRequest || invalidRoleRequest;
  const selectionHasData = activeRoleSlug
    ? currentRoleRecords.length > 0
    : activeTeamSlug
      ? currentTeamRecords.length > 0
      : functionSlug
        ? currentFunctionRecords.length > 0
        : selectedPeriodRecords.length > 0;
  const noDataForSelection = !explicitPreview && !pageIsLoading && !pageHasError &&
    !hasNoAssignments && !invalidScopeRequest && !selectionHasData;
  const scopeTeamsForNoData = activeTeamSlug
    ? teamsInCurrentFunction.filter((team) => slugifyIdentifier(team.team) === activeTeamSlug)
    : teamsInCurrentFunction;
  const selectedPeriodLabel = periodFromKey(selectedPeriodKey)?.label ?? selectedPeriodKey;

  if (pageIsLoading || pageHasError || hasNoAssignments || invalidScopeRequest || noDataForSelection) {
    const heading = pageIsLoading
      ? 'Loading Monthly Review data'
      : pageHasError
        ? 'Monthly Review data could not be loaded'
        : hasNoAssignments
          ? 'No monthly review assignments'
          : invalidScopeRequest
            ? 'This Monthly Review link is outside your access'
            : `No performance data for ${selectedPeriodLabel}`;
    const detail = pageIsLoading
      ? 'Loading the teams and performance records available to your account.'
      : pageHasError
        ? 'The authorized team list or performance records could not be fetched. Retry to load your scope again.'
        : hasNoAssignments
          ? functionScopeRestricted
            ? 'Your account has no authorized function for Monthly Review. Contact your administrator to request access.'
            : 'No active teams are currently assigned to your account. Contact your administrator if this looks wrong.'
          : invalidScopeRequest
            ? 'The requested region, function, team, or position is not included in your authorized scope.'
            : functionSlug
              ? 'No results were uploaded for this function, team, or position in the selected period.'
              : 'No results were uploaded for your authorized scope in the selected period.';

    return (
      <main className="mx-auto max-w-7xl space-y-5 px-4 py-8 sm:px-6 lg:px-8">
        {headerToolbar && <div className="flex flex-wrap items-center gap-3">{headerToolbar}</div>}
        <section
          data-testid={hasNoAssignments ? 'monthly-assignment-message' : noDataForSelection ? 'monthly-no-data' : pageHasError ? 'monthly-data-error' : invalidScopeRequest ? 'monthly-scope-restricted' : 'monthly-loading'}
          role={pageHasError || invalidScopeRequest ? 'alert' : 'status'}
          aria-live="polite"
          className={`rounded-2xl border p-5 sm:p-6 ${pageHasError || invalidScopeRequest ? 'border-rose-200 bg-rose-50' : 'border-slate-200 bg-white'}`}
        >
          <h1 className="text-lg font-bold text-slate-900">{heading}</h1>
          <p className="mt-2 text-sm text-slate-600">{detail}</p>
          {!pageIsLoading && !pageHasError && !hasNoAssignments && !invalidScopeRequest && (
            <label className="mt-4 flex max-w-xs flex-col gap-1 text-xs font-semibold text-slate-600">
              Reporting month
              <select
                aria-label="Reporting month"
                value={selectedPeriodKey}
                onChange={(event) => handlePeriodChange(event.target.value)}
                className="h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900"
              >
                {monthOptions.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}
              </select>
            </label>
          )}
          {pageHasError && (
            <button
              type="button"
              className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
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

  return (
    <>
      <PresentationSectionFrame viewKey={sectionViewKey}>
        <div className="pb-28">{renderActiveView()}</div>
      </PresentationSectionFrame>
      <PresentationControlBar
        region={activeRegion}
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
    </>
  );
}
