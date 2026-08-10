import { lazy, Suspense, useState, useMemo, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useTeamData, usePerformanceData, parseAHTtoSeconds, formatSecondsToMMSS, agentMatchesLocation, refreshPerformanceData, resolveTeamMonths, hasRealActivity } from '../hooks/usePerformanceData';
import { useActionStore } from '../hooks/useActionStore';
import { useMonthParam } from '../hooks/useMonthParam';
import { useLocationParam, useLocationsParam } from '../hooks/useLocationParam';
import EmployeeActionModal from '../components/team/EmployeeActionModal';
import { OperationalViewSkeleton } from '../components/common/SkeletonLoader';
import { TrendingUp, Target, Activity, Phone, Shield, Lightbulb, Edit2, Check, X, Award, AlertCircle, AlertTriangle, MessageSquare, Code, Headphones, Pill, Users, Send } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { TeamAgentRow, TeamWeightConfig } from '../hooks/usePerformanceData';
import { TEAM_NAME_MAP, TEAM_DB_NAME_MAP, MERGED_OP_FINAL_TEAM, MERGED_IP_FINAL_TEAM, PRE_APPROVALS_UAE_TEAM, PRE_APPROVALS_UAE_SOURCE_TEAMS, CALL_CENTER_TEAM, RCM_TEAM, isCallCenterChannelTeam, isPreApprovalsWorkflowTeam, isRcmDomainTeam, isRcmGroupTeam, isMergedBranchTeam, isMergedOpFinalTeam, sameCanonicalTeam } from '../types';
import type { AgentRecord, GeoBreakdown, LocationKey, PreApprovalsWorkflowFilter, CallCenterChannelFilter, RcmDomainFilter, RcmGroupFilter } from '../types';
import { useUserRole } from '../context/RoleContext';
import { useAuth } from '../context/auth';
import { API_BASE } from '../config';
import { apiFetch } from '../lib/apiClient';

// Import sub-components
import NoDataEmptyState from '../components/common/NoDataEmptyState';
import KpiCard from '../components/common/KpiCard';
import TeamHeader from '../components/team/TeamHeader';
import TeamKpiSection from '../components/team/TeamKpiSection';
import PreApprovalsWorkflowSummary from '../components/team/PreApprovalsWorkflowSummary';
import CallCenterChannelSummary from '../components/team/CallCenterChannelSummary';
import RcmDomainSummary from '../components/team/RcmDomainSummary';
import RcmGroupSummary from '../components/team/RcmGroupSummary';
import TeamRosterSection from '../components/team/TeamRosterSection';
import TeamPerformanceAnalysis from '../components/team/TeamPerformanceAnalysis';
import { TeamPerformanceIntelligence } from '../components/team/TeamPerformanceIntelligence';
import { useInsightsWorkspace } from '../hooks/api/useInsightsWorkspace';
import { usePerformanceLevelParam } from '../hooks/usePerformanceLevelParam';
import { usePreApprovalsWorkflowParam } from '../hooks/usePreApprovalsWorkflowParam';
import { useCallCenterChannelParam } from '../hooks/useCallCenterChannelParam';
import { useRcmDomainParam } from '../hooks/useRcmDomainParam';
import { useRcmGroupParam } from '../hooks/useRcmGroupParam';
import { resolveDisplayScore } from '../utils/kpiScore';
import { matchesTeamConfig, normalizeTeamName } from '../hooks/api/useKpiWeights';
import { useTeamConfig } from '../hooks/useTeamConfig';
import BalancedScorecardWorkspace from '../components/team/BalancedScorecardWorkspace';
import { GRADE_PALETTE } from '../constants/grades';
import { buildTeamKpiAnalysis } from '../features/team/teamKpiAnalysis';
import { aggregatePreApprovalsIpMetrics } from '../features/team/preApprovalsIpMetrics';
import { aggregateConfiguredTeamKpis, calculateAggregatedTeamPerformance } from '../features/team/teamKpiAggregator';
import { resolveAvailableTeamPeriods } from '../features/team/teamPeriods';

const TeamChartsSection = lazy(() => import('../components/team/TeamChartsSection'));

const PAGE_SIZE = 15;

const MONTH_NUMBER: Record<string, number> = {
  January: 1, February: 2, March: 3, April: 4, May: 5, June: 6,
  July: 7, August: 8, September: 9, October: 10, November: 11, December: 12,
};

const GRADE_PIE_COLORS = {
  A: GRADE_PALETTE.A.text,
  B: GRADE_PALETTE.B.text,
  C: GRADE_PALETTE.C.text,
  D: GRADE_PALETTE.D.text,
  E: GRADE_PALETTE.E.text,
};

const getActionTypeIcon = (type: string) => {
  switch (type) {
    case 'Training': return Target;
    case 'Reward': return Award;
    case 'PIP': return AlertTriangle;
    case 'Monitor': return Activity;
    default: return MessageSquare;
  }
};

const getActionTypeColor = (type: string) => {
  switch (type) {
    case 'Training': return 'from-blue-500 to-indigo-500 text-white';
    case 'Reward': return 'from-emerald-500 to-teal-500 text-white';
    case 'PIP': return 'from-rose-500 to-pink-500 text-white';
    case 'Monitor': return 'from-amber-500 to-orange-500 text-white';
    default: return 'from-purple-500 to-fuchsia-500 text-white';
  }
};

const getGeoValue = (geo: GeoBreakdown | undefined, loc: LocationKey) => {
  if (!geo) return 0;
  if (loc === 'all') {
    return (geo.dubai || 0) + (geo.sharjah || 0) + (geo.ajman || 0) + (geo.clinics || 0);
  }
  return geo[loc] || 0;
};

const sameTeam = (left: string | null | undefined, right: string | null | undefined) =>
  sameCanonicalTeam(left, right);

const scoreForDisplay = (row: TeamAgentRow) => row.displayWeightedScore ?? row.score;

const configuredKpiActual = (
  kpis: ReturnType<typeof aggregateConfiguredTeamKpis>,
  label: string,
) => kpis.get(label.trim().toLowerCase().replace(/[^a-z0-9]+/g, ''))?.actual;

const configuredKpiPercent = (
  kpis: ReturnType<typeof aggregateConfiguredTeamKpis>,
  label: string,
) => {
  const actual = configuredKpiActual(kpis, label);
  return actual === undefined ? undefined : actual * 100;
};

const unslugTeam = (slug: string) =>
  slug
    .split('-')
    .filter(Boolean)
    .map((part) => (part.length <= 3 ? part.toUpperCase() : part.charAt(0).toUpperCase() + part.slice(1)))
    .join(' ');

interface TeamDashboardViewProps {
  teamIdOverride?: string;
}

const TeamDashboardView = ({ teamIdOverride }: TeamDashboardViewProps = {}) => {
  const { teamId: routeTeamId } = useParams<{ teamId: string }>();
  const teamId = teamIdOverride ?? routeTeamId;
  const navigate = useNavigate();
  const { role, fetchWithRole } = useUserRole();
  const { currentUser } = useAuth();

  // Resolve team identity before loading config-driven defaults. New teams should
  // not require another hardcoded region branch in this page.
  const resolvedTeamName = teamId === 'all' ? null : (TEAM_DB_NAME_MAP[teamId ?? ''] ?? unslugTeam(teamId ?? ''));
  const isPreApprovalsParent = resolvedTeamName === PRE_APPROVALS_UAE_TEAM;
  const isCallCenterParent = resolvedTeamName === CALL_CENTER_TEAM;
  const isRcmParent = resolvedTeamName === RCM_TEAM;
  const isMergedTeam = isMergedBranchTeam(resolvedTeamName) || isPreApprovalsParent || isCallCenterParent;
  const isMergedOpFinal = isMergedOpFinalTeam(resolvedTeamName);
  const mergedTeamName = isMergedOpFinal ? MERGED_OP_FINAL_TEAM : MERGED_IP_FINAL_TEAM;
  const teamName = isPreApprovalsParent
    ? PRE_APPROVALS_UAE_TEAM
    : isCallCenterParent
      ? CALL_CENTER_TEAM
      : isRcmParent
        ? RCM_TEAM
      : isMergedTeam ? mergedTeamName : resolvedTeamName;
  const displayName = teamId === 'all'
    ? 'All Teams'
    : isPreApprovalsParent
      ? PRE_APPROVALS_UAE_TEAM
      : isCallCenterParent
        ? CALL_CENTER_TEAM
        : isRcmParent
          ? RCM_TEAM
      : isMergedTeam
      ? mergedTeamName
      : (TEAM_NAME_MAP[teamId ?? ''] ?? unslugTeam(teamId ?? ''));
  const [regionSelection, setRegionSelection] = useState<{
    teamName: string | null;
    value: 'All' | 'EGY' | 'UAE';
  } | null>(null);
  const { location: requestedLocation, setLocation: setRequestedLocation } = useLocationParam('all');
  const { locations: branchSelections, setLocations: setBranchSelections } = useLocationsParam(['all']);
  const location = isMergedTeam ? 'all' : requestedLocation;
  const setLocation = setRequestedLocation;
  const { month, setMonth } = useMonthParam('All');
  const { performanceLevel, setPerformanceLevel } = usePerformanceLevelParam('All');
  const { workflow: preApprovalsWorkflow, setWorkflow: setPreApprovalsWorkflow } = usePreApprovalsWorkflowParam('all');
  const { channel: callCenterChannel, setChannel: setCallCenterChannel } = useCallCenterChannelParam('all');
  const { domain: rcmDomain, setDomain: setRcmDomain } = useRcmDomainParam('all');
  const { group: rcmGroup, setGroup: setRcmGroup } = useRcmGroupParam('all');

  const canExport = role === 'Manager' || role === 'Admin';
  const [hoverTooltip, setHoverTooltip] = useState<{ text: string; x: number; y: number } | null>(null);
  const [weightsList, setWeightsList] = useState<TeamWeightConfig[]>([]);

  const workflowConfigTeam = isPreApprovalsParent
    ? preApprovalsWorkflow === 'op_final'
      ? MERGED_OP_FINAL_TEAM
      : preApprovalsWorkflow === 'ip_final'
        ? MERGED_IP_FINAL_TEAM
        : preApprovalsWorkflow === 'ip_elective'
          ? 'Pre-Approvals IP Elective Dubai'
          : ''
    : isCallCenterParent
      ? callCenterChannel === 'inbound'
        ? 'Inbound'
        : callCenterChannel === 'outbound'
          ? 'Outbound'
          : ''
    : isRcmParent
      ? rcmDomain === 'pre_approvals'
        ? rcmGroup === 'offshore_egy'
          ? 'Pre-Approvals IP Offshore'
          : preApprovalsWorkflow === 'op_final'
          ? MERGED_OP_FINAL_TEAM
          : preApprovalsWorkflow === 'ip_final'
            ? MERGED_IP_FINAL_TEAM
            : preApprovalsWorkflow === 'ip_elective'
              ? 'Pre-Approvals IP Elective Dubai'
              : PRE_APPROVALS_UAE_TEAM
        : rcmDomain === 'submission'
          ? 'Submission'
          : rcmDomain === 're_submission'
            ? 'Re-Submission'
            : rcmDomain === 'coding'
              ? 'Coding'
              : ''
    : teamName || '';
  const { data: teamConfig } = useTeamConfig(workflowConfigTeam);
  const region = regionSelection?.teamName === teamName
    ? regionSelection.value
    : isPreApprovalsParent ? 'UAE' : isCallCenterParent ? 'EGY' : teamName ? (teamConfig?.region ?? 'All') : 'All';
  const setRegion = useCallback((value: 'All' | 'EGY' | 'UAE') => {
    setRegionSelection({ teamName, value });
  }, [teamName, setRegionSelection]);
  const bscConfig = teamConfig?.performance_levels?.[performanceLevel === 'All' ? 'Managerial' : performanceLevel];
  const isBscContext = !!teamName && (performanceLevel === 'Managerial' || performanceLevel === 'Corporate');
  // Management templates are DB-backed and may not exist in the static team
  // config (Marketing is the first such team). An explicitly configured,
  // disabled BSC remains disabled; a missing level config falls through to
  // the database-backed Balanced Scorecard API.
  const hasBalancedScorecard = isBscContext && !isMergedTeam && (
    bscConfig === undefined || !!bscConfig.balanced_scorecard?.enabled
  );
  const showBscFallbackMessage = isBscContext && !hasBalancedScorecard;

  const isTeamAccessRestricted = useMemo(() => {
    if (!currentUser) return false;
    if (role === 'Admin' || currentUser.is_general_manager) return false;
    if (!teamName) return false; // 'all' view has its own scoping
    
    const normTeam = normalizeTeamName(teamName);
    const allowed = (currentUser.accessible_teams || []).map(normalizeTeamName);
    if (isRcmParent) {
      const rcmSourceTeams = [
        'RCM',
        'Coding',
        'Submission',
        'Re-Submission',
        'Pre-Approvals',
        ...PRE_APPROVALS_UAE_SOURCE_TEAMS,
        'Pre-Approvals IP Elective',
      ];
      return !rcmSourceTeams.some((source) => allowed.includes(normalizeTeamName(source)));
    }
    if (isMergedTeam) {
      const sourceTeams = isPreApprovalsParent
        ? PRE_APPROVALS_UAE_SOURCE_TEAMS
        : isCallCenterParent
          ? ['Inbound', 'Outbound']
        : isMergedOpFinal
          ? ['Pre-Approvals OP Dubai', 'Pre-Approvals OP Final SHJAJM']
          : ['Pre-Approvals IP Final Dubai', 'Pre-Approvals IP Final SHJAJM'];
      const hasSourceAccess = sourceTeams.some((source) => allowed.includes(normalizeTeamName(source)));
      const hasParentAccess = isPreApprovalsParent && allowed.includes(normalizeTeamName(PRE_APPROVALS_UAE_TEAM));
      const hasCallCenterParentAccess = isCallCenterParent && allowed.includes(normalizeTeamName(CALL_CENTER_TEAM));
      return !(hasParentAccess || hasCallCenterParentAccess || hasSourceAccess || allowed.includes(normalizeTeamName(mergedTeamName)));
    }
    return !allowed.includes(normTeam);
  }, [currentUser, role, teamName, isMergedTeam, isPreApprovalsParent, isCallCenterParent, isRcmParent, isMergedOpFinal, mergedTeamName]);

  const isCallCenterView = teamId?.toLowerCase() === 'inbound' || teamId?.toLowerCase() === 'inbound-uae' || teamId?.toLowerCase() === 'outbound'
    || (isCallCenterParent && callCenterChannel !== 'all');
  const isInbound = teamId?.toLowerCase() === 'inbound' || teamId?.toLowerCase() === 'inbound-uae'
    || (isCallCenterParent && callCenterChannel === 'inbound');
  const scoredTeamId = isCallCenterParent
    ? callCenterChannel === 'outbound' ? 'outbound' : 'inbound'
    : teamId;

  // Load current month's team data directly
  const {
    rows,
    avgScore: hookAvgScore,
    classCounts: hookClassCounts,
    pctAB: hookPctAB,
    pctDE: hookPctDE,
    totalAgents: hookTotalAgents,
    uniqueTeamCount: hookUniqueTeamCount,
    prevMonth,
    loading,
    dataSource,
    errorMessage,
    prevAvgScore,
    prevPctAB,
    prevPctDE,
    prevTotalAgents,
  } = useTeamData(
    teamName,
    month,
    region,
    location,
    weightsList,
    performanceLevel,
    isMergedTeam && !isCallCenterParent ? branchSelections : undefined,
    isPreApprovalsParent ? preApprovalsWorkflow : 'all',
    isCallCenterParent ? callCenterChannel : 'all',
    isRcmParent ? rcmDomain : 'all',
    isRcmParent ? rcmGroup : 'all',
  );

  const { uniqueMonths, agents: allAgentsRaw } = usePerformanceData('All', location, region, performanceLevel);
  const allAgents = useMemo(
    () => isMergedTeam && !isCallCenterParent && !branchSelections.includes('all')
      ? allAgentsRaw.filter((agent) => branchSelections.some((branch) => agentMatchesLocation(agent, branch)))
      : allAgentsRaw,
    [allAgentsRaw, branchSelections, isMergedTeam, isCallCenterParent],
  );

  const availableTeamPeriods = useMemo(
    () => resolveAvailableTeamPeriods(allAgents, teamName),
    [allAgents, teamName],
  );
  const dashboardMonths = useMemo(
    () => teamId === 'all' ? uniqueMonths : resolveTeamMonths(allAgents, teamName),
    [allAgents, teamId, teamName, uniqueMonths],
  );

  const latestMonth = dashboardMonths[dashboardMonths.length - 1] || '';
  const headcountMonth = month === 'All' ? latestMonth : month;
  const displayTotalAgents = hookTotalAgents;
  const headcountNote = headcountMonth
    ? `${month === 'All' ? 'Latest headcount' : 'Headcount'} · ${headcountMonth}`
    : 'Headcount unavailable';
  const { getActionsForEmployee, getAllActions } = useActionStore();

  useEffect(() => {
    apiFetch<{ success: boolean; data: TeamWeightConfig[] }>('/api/settings/weights')
      .then((res) => {
        if (res?.success && Array.isArray(res.data)) {
          setWeightsList(res.data);
          if (import.meta.env.DEV) {
            res.data.forEach((w) => {
              const scopes = w.scopes && w.scopes.length > 0 ? w.scopes : [{ position: null, weights: w.weights }];
              scopes.forEach((scope) => {
                const weightsObj = scope.weights || {};
                const sum = Object.values(weightsObj).reduce((acc, val) => acc + val, 0);
                if (Object.keys(weightsObj).length > 0 && Math.abs(sum - 1.0) > 0.001) {
                  console.warn(
                    `[Team Weight Validation] Team "${w.team}"${scope.position ? ` (${scope.position})` : ''} weights sum to ${(sum * 100).toFixed(1)}%, expected 100%!`,
                    weightsObj
                  );
                }
              });
            });
          }
        }
      })
      .catch(() => { });
  }, [role]);

  // Smart Employee Roster view state
  const [rosterView, setRosterView] = useState<'top_bottom' | 'all'>('top_bottom');

  // Previous month's data for trend calculation
  const prevRows = useMemo(() => {
    const map = new Map<string, { score: number }>();
    if (!prevMonth) return map;

    let prevAgents = allAgents.filter((a) => {
      if (a.identity.month !== prevMonth) return false;
      if (isCallCenterParent && callCenterChannel !== 'all' && !isCallCenterChannelTeam(a.identity.team, callCenterChannel)) return false;
      return !teamName || sameTeam(a.identity.team, teamName);
    });

    if (location !== 'all') {
      prevAgents = prevAgents.filter((a) => agentMatchesLocation(a, location));
    }

      prevAgents.forEach((agent) => {
      const id = agent.identity.employee_id;
      const rowWeights = weightsList.find((w) => matchesTeamConfig({ team: String(w.team || w.db_name || w.name || ''), weights: w.weights }, String(agent.identity.team || '')))?.weights;
      const score = resolveDisplayScore(agent, rowWeights);
      if (id) {
        map.set(id, { score });
      }
    });

    return map;
  }, [prevMonth, allAgents, teamName, location, weightsList, isCallCenterParent, callCenterChannel]);

  // Table state
  const [search, setSearch] = useState('');
  const [sortCol, setSortCol] = useState<'score' | 'name' | 'status'>('score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);
  const [modalEmployee, setModalEmployee] = useState<TeamAgentRow | null>(null);
  const handlePreApprovalsWorkflowChange = useCallback((workflow: PreApprovalsWorkflowFilter) => {
    setPreApprovalsWorkflow(workflow);
    setPage(1);
  }, [setPreApprovalsWorkflow]);
  const handleCallCenterChannelChange = useCallback((channel: CallCenterChannelFilter) => {
    setCallCenterChannel(channel);
    setPage(1);
  }, [setCallCenterChannel]);
  const handleRcmDomainChange = useCallback((domain: RcmDomainFilter) => {
    setRcmDomain(domain);
    setPage(1);
  }, [setRcmDomain]);
  const handleRcmGroupChange = useCallback((group: RcmGroupFilter) => {
    setRcmGroup(group, { clearDomain: true });
    setPage(1);
  }, [setRcmGroup]);

  const matchesPresentationScope = useCallback((agent: AgentRecord) => {
    if (isRcmParent && rcmGroup !== 'all' && !isRcmGroupTeam(agent.identity.team, rcmGroup, agent.region ?? agent.identity.region)) return false;
    if (isRcmParent && rcmDomain !== 'all' && !isRcmDomainTeam(agent.identity.team, rcmDomain)) return false;
    if ((isPreApprovalsParent || (isRcmParent && rcmDomain === 'pre_approvals'))
      && preApprovalsWorkflow !== 'all'
      && !isPreApprovalsWorkflowTeam(agent.identity.team, preApprovalsWorkflow)) return false;
    if (isCallCenterParent && callCenterChannel !== 'all' && !isCallCenterChannelTeam(agent.identity.team, callCenterChannel)) return false;
    return true;
  }, [isRcmParent, rcmGroup, rcmDomain, isPreApprovalsParent, preApprovalsWorkflow, isCallCenterParent, callCenterChannel]);

  const activeMonth = month === 'All'
    ? (dashboardMonths[dashboardMonths.length - 1] || 'January')
    : month;

  const previousTeamAgents = useMemo(() => {
    if (!prevMonth) return [];
    return allAgents.filter((agent) => {
      if (agent.identity.month !== prevMonth) return false;
      if (teamName && !sameTeam(agent.identity.team, teamName)) return false;
      if (!matchesPresentationScope(agent)) return false;
      return location === 'all' || agentMatchesLocation(agent, location);
    });
  }, [prevMonth, allAgents, teamName, location, matchesPresentationScope]);
  const historicalTeamAgents = useMemo(
    () => allAgents.filter((agent) => {
      if (teamName && !sameTeam(agent.identity.team, teamName)) return false;
      if (!matchesPresentationScope(agent)) return false;
      return location === 'all' || agentMatchesLocation(agent, location);
    }),
    [allAgents, teamName, location, matchesPresentationScope],
  );
  const weightsTeamName = (isCallCenterParent && callCenterChannel !== 'all')
    || (isPreApprovalsParent && preApprovalsWorkflow !== 'all')
    || (isRcmParent && rcmDomain !== 'all' && workflowConfigTeam)
    ? workflowConfigTeam
    : teamName || '';
  const activeTeamWeights = useMemo(
    () => weightsList.find((weightConfig) => matchesTeamConfig(
      {
        team: String(weightConfig.team || weightConfig.db_name || weightConfig.name || ''),
        weights: weightConfig.weights,
      },
      weightsTeamName,
    ))?.weights,
    [weightsList, weightsTeamName],
  );
  const teamKpiAnalysis = useMemo(
    () => {
      if ((isPreApprovalsParent && preApprovalsWorkflow === 'all')
        || (isCallCenterParent && callCenterChannel === 'all')
        || (isRcmParent && (rcmDomain === 'all' || (rcmDomain === 'pre_approvals' && preApprovalsWorkflow === 'all' && rcmGroup !== 'offshore_egy')))) return [];
      return buildTeamKpiAnalysis(
        (rows || []).map((row) => row.raw).filter((record) => record.identity.month === activeMonth),
        previousTeamAgents,
        {
          includeNoShow: isCallCenterView,
          includeAht: scoredTeamId === 'outbound',
          location,
          teamWeights: activeTeamWeights,
          teamConfig,
          baselineRecords: historicalTeamAgents,
        },
      );
    },
    [rows, previousTeamAgents, historicalTeamAgents, activeMonth, isCallCenterView, scoredTeamId, location, activeTeamWeights, teamConfig, isPreApprovalsParent, preApprovalsWorkflow, isCallCenterParent, callCenterChannel, isRcmParent, rcmDomain, rcmGroup],
  );

  const insightYear = useMemo(() => {
    const currentRowYear = (rows || []).find((row) => row.raw.year)?.raw.year;
    if (currentRowYear) return currentRowYear;
    return allAgents.find((agent) =>
      agent.identity.month === activeMonth && (!teamName || sameTeam(agent.identity.team, teamName)) && agent.year
    )?.year;
  }, [rows, allAgents, activeMonth, teamName]);
  const insightPeriodKey = insightYear && MONTH_NUMBER[activeMonth]
    ? `${insightYear}-${String(MONTH_NUMBER[activeMonth]).padStart(2, '0')}`
    : undefined;
  const canViewTeamInsights = ['Admin', 'Manager', 'Executive'].includes(role || '');
  const teamInsightsQuery = useInsightsWorkspace(
    {
      periodKey: insightPeriodKey,
      team: teamName || undefined,
      region: region === 'All' ? undefined : region,
      performanceLevel: performanceLevel === 'All' ? undefined : performanceLevel,
    },
    {
      enabled: canViewTeamInsights
        && !isTeamAccessRestricted
        && !hasBalancedScorecard
        && teamKpiAnalysis.length === 0
        && !!teamName
        && !!insightPeriodKey,
      view: 'priority',
    },
  );
  const teamPerformanceInsights = useMemo(
    () => (teamInsightsQuery.data?.priority_insights || []).filter((insight) =>
      !insight.team || sameTeam(insight.team, teamName)
    ),
    [teamInsightsQuery.data?.priority_insights, teamName],
  );
  const allActions = getAllActions();
  const teamActionsThisMonth = useMemo(() => {
    const agentIds = new Set((rows || []).map(r => r.id));
    return allActions.filter(act => agentIds.has(act.employee_id) && act.month === activeMonth);
  }, [allActions, rows, activeMonth]);

  const [teamAction, setTeamAction] = useState<string>('');
  const [isEditingAction, setIsEditingAction] = useState<boolean>(false);
  const [actionInput, setActionInput] = useState<string>('');
  const [savingAction, setSavingAction] = useState<boolean>(false);

  useEffect(() => {
    const fetchTeamAction = async () => {
      try {
        const result = await apiFetch<{ success: boolean; data?: { overall_action: string } }>(
          `/api/team-actions/?team_id=${teamId}&month=${activeMonth}&year=${insightYear}`
        );
        if (result.success && result.data) {
          setTeamAction(result.data.overall_action);
          setActionInput(result.data.overall_action);
        } else {
          setTeamAction('');
          setActionInput('');
        }
      } catch (err) {
        console.error('Failed to fetch team action', err);
        setTeamAction('');
        setActionInput('');
      }
    };
    if (teamId && teamId !== 'all' && insightYear) {
      fetchTeamAction();
    }
  }, [teamId, activeMonth, insightYear]);

  const handleSaveTeamAction = async () => {
    setSavingAction(true);
    try {
      const result = await apiFetch<{ success: boolean; message?: string }>(
        '/api/team-actions/',
        {
          method: 'POST',
          body: JSON.stringify({
            team_id: teamId,
            month: activeMonth,
            year: insightYear,
            overall_action: actionInput,
          }),
        }
      );
      if (result.success) {
        setTeamAction(actionInput);
        setIsEditingAction(false);
      } else {
        alert('Failed to save: ' + (result.message || 'Unknown error'));
      }
    } catch (err) {
      console.error('Failed to save team action', err);
      alert('Failed to save action: check permissions.');
    } finally {
      setSavingAction(false);
    }
  };

  // Team overall is calculated from pooled KPI totals, never by averaging
  // employee performance scores. Individual scores remain the source for the
  // roster and grade distribution only.
  const getCanonicalTeamScore = useCallback((agents: AgentRecord[]) => (
    calculateAggregatedTeamPerformance(agents, teamConfig, { location, preferConfiguredWeights: isMergedTeam })?.score ?? null
  ), [location, teamConfig, isMergedTeam]);
  // Memoized current month aggregate performance score
  const calculatedAvgScore = useMemo(() => {
    if (teamId === 'all') return hookAvgScore;
    // The merged OP Final view is intentionally an employee-score average
    // across the selected branches; KPI cards still use their configured
    // pooled KPI aggregation below.
    if (isMergedTeam) return hookAvgScore;
    const teamAgents = (rows || []).map((row) => row.raw).filter((record) => record.identity.month === activeMonth);
    const canonical = getCanonicalTeamScore(teamAgents);
    if (canonical !== null && canonical > 0 && Math.abs(canonical - hookAvgScore) <= 15) {
      return canonical;
    }
    return hookAvgScore;
  }, [teamId, activeMonth, getCanonicalTeamScore, hookAvgScore, rows, isMergedTeam]);

  const calculatedPrevAvgScore = useMemo(() => {
    if (teamId === 'all') return prevAvgScore;
    if (isMergedTeam) return prevAvgScore;
    if (!prevMonth) return prevAvgScore;
    const canonical = getCanonicalTeamScore(previousTeamAgents);
    if (canonical !== null && canonical > 0 && Math.abs(canonical - prevAvgScore) <= 15) {
      return canonical;
    }
    return prevAvgScore;
  }, [teamId, prevMonth, getCanonicalTeamScore, prevAvgScore, previousTeamAgents, isMergedTeam]);

  // Compute metrics dynamically for the current month
  const metrics = useMemo(() => {
    return {
      totalAgents: displayTotalAgents,
      avgScore: calculatedAvgScore,
      classCounts: hookClassCounts,
      pctAB: hookPctAB,
      pctDE: hookPctDE,
      uniqueTeamCount: hookUniqueTeamCount || new Set((rows || []).map((row) => row.team)).size,
    };
  }, [displayTotalAgents, calculatedAvgScore, hookClassCounts, hookPctAB, hookPctDE, hookUniqueTeamCount, rows]);

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    console.debug('performance_summary', {
      month,
      region,
      branch: location,
      recordsUsed: metrics.totalAgents,
      uniqueTeams: [...new Set((rows || []).map((row) => row.team))],
      uniqueTeamCount: metrics.uniqueTeamCount,
      averageScore: metrics.avgScore,
      classABCount: metrics.classCounts.A + metrics.classCounts.B,
      classABPercentage: metrics.pctAB,
      classDECount: metrics.classCounts.D + metrics.classCounts.E,
      classDEPercentage: metrics.pctDE,
    });
  }, [month, region, location, metrics, rows]);

  // Compute call center metrics for the current month
  const teamMetrics = useMemo(() => {
    const filteredAgents = rows || [];

    let totalBookings = 0;
    let totalAttended = 0;
    let totalCallsHandled = 0;
    let totalAbandoned = 0;
    let totalAHTSeconds = 0;
    let totalReachability = 0;
    let agentsWithReachability = 0;
    let totalUTZ = 0;
    let agentsWithUTZ = 0;

    let totalSubmission = 0;
    let agentsWithSubmission = 0;
    let totalRejection = 0;
    let agentsWithRejection = 0;
    let totalError = 0;
    let agentsWithError = 0;

    let totalOPCensus = 0;
    let agentsWithOPCensus = 0;
    let totalOPRevenue = 0;
    let agentsWithOPRevenue = 0;
    let totalIPCensus = 0;
    let agentsWithIPCensus = 0;
    let totalIPRevenue = 0;
    let agentsWithIPRevenue = 0;
    let totalActivity = 0;
    let agentsWithActivity = 0;
    let totalTotalCensus = 0;
    let agentsWithTotalCensus = 0;
    let totalTotalRevenue = 0;
    let agentsWithTotalRevenue = 0;

    let salesOPCensusActual = 0;
    let salesOPCensusTarget = 0;
    let salesOPRevenueActual = 0;
    let salesOPRevenueTarget = 0;
    let salesIPCensusActual = 0;
    let salesIPCensusTarget = 0;
    let salesIPRevenueActual = 0;
    let salesIPRevenueTarget = 0;
    let salesTotalCensusActual = 0;
    let salesTotalCensusTarget = 0;
    let salesTotalRevenueActual = 0;
    let salesTotalRevenueTarget = 0;
    let salesActivityActual = 0;
    let salesActivityTarget = 0;

    filteredAgents.forEach((agent) => {
      const rawAgent = agent.raw;
      if (!rawAgent) return;

      const geoB = rawAgent.geo?.bookings || { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 };
      const geoA = rawAgent.geo?.attended || { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 };

      totalBookings += getGeoValue(geoB, location);
      totalAttended += getGeoValue(geoA, location);

      const calls = rawAgent.calls || { total_handled: 0, inbound: 0, abandoned: 0, aht_raw: '00:00:00' };
      totalCallsHandled += calls.total_handled;
      totalAbandoned += calls.abandoned;

      totalAHTSeconds += parseAHTtoSeconds(calls.aht_raw || '00:00:00');

      const actual = rawAgent.actual || {};
      if (actual.reachability_rate !== undefined) {
        totalReachability += actual.reachability_rate;
        agentsWithReachability++;
      }

      if (actual.utz_rate !== undefined && actual.utz_rate > 0) {
        totalUTZ += actual.utz_rate;
        agentsWithUTZ++;
      }

      if (actual.submission_rate !== undefined) {
        totalSubmission += actual.submission_rate;
        agentsWithSubmission++;
      }

      if (actual.rejection_rate !== undefined) {
        totalRejection += actual.rejection_rate;
        agentsWithRejection++;
      }

      if (actual.initial_error_rate !== undefined) {
        totalError += actual.initial_error_rate;
        agentsWithError++;
      }

      // Sales achievements mapping
      const ach = rawAgent.achievement || {};
      if (ach.op_census_ach !== undefined && ach.op_census_ach > 0) {
        totalOPCensus += ach.op_census_ach;
        agentsWithOPCensus++;
      } else if (rawAgent.raw_data?.['OPCensusAch%'] !== undefined) {
        totalOPCensus += parseFloat(rawAgent.raw_data['OPCensusAch%']) / 100.0 || 0; // fallback if percent
        agentsWithOPCensus++;
      }

      if (ach.op_revenue_ach !== undefined && ach.op_revenue_ach > 0) {
        totalOPRevenue += ach.op_revenue_ach;
        agentsWithOPRevenue++;
      }

      if (ach.ip_census_ach !== undefined && ach.ip_census_ach > 0) {
        totalIPCensus += ach.ip_census_ach;
        agentsWithIPCensus++;
      }

      if (ach.ip_revenue_ach !== undefined && ach.ip_revenue_ach > 0) {
        totalIPRevenue += ach.ip_revenue_ach;
        agentsWithIPRevenue++;
      }

      if (ach.activity_ach !== undefined && ach.activity_ach > 0) {
        totalActivity += ach.activity_ach;
        agentsWithActivity++;
      }

      if (rawAgent.raw_data?.['Total Census Ach%'] !== undefined) {
        totalTotalCensus += parseFloat(rawAgent.raw_data['Total Census Ach%']) / 100.0 || 0;
        agentsWithTotalCensus++;
      } else {
        const act = parseFloat(rawAgent.raw_data?.['A.Total Census'] ?? '0') || 0;
        const tgt = parseFloat(rawAgent.raw_data?.['T.Total Census'] ?? '0') || 0;
        if (tgt > 0) {
          totalTotalCensus += act / tgt;
          agentsWithTotalCensus++;
        }
      }

      if (rawAgent.raw_data?.['Total Revenue Ach%'] !== undefined) {
        totalTotalRevenue += parseFloat(rawAgent.raw_data['Total Revenue Ach%']) / 100.0 || 0;
        agentsWithTotalRevenue++;
      } else {
        const act = parseFloat(rawAgent.raw_data?.['A.Total Revenue'] ?? '0') || 0;
        const tgt = parseFloat(rawAgent.raw_data?.['T.Total Revenue'] ?? '0') || 0;
        if (tgt > 0) {
          totalTotalRevenue += act / tgt;
          agentsWithTotalRevenue++;
        }
      }

      // Sales actual volumes mapping
      if (rawAgent.raw_data) {
        const rd = rawAgent.raw_data;
        salesOPCensusActual += parseFloat(rd['A.OPCensus']) || 0;
        salesOPCensusTarget += parseFloat(rd['T.OPCensus']) || 0;

        salesOPRevenueActual += parseFloat(rd['A.OPRevenue']) || 0;
        salesOPRevenueTarget += parseFloat(rd['T.OPRevenue']) || 0;

        salesIPCensusActual += parseFloat(rd['A.IPCensus']) || 0;
        salesIPCensusTarget += parseFloat(rd['T.IPCensus']) || 0;

        salesIPRevenueActual += parseFloat(rd['A.IPRevenue']) || 0;
        salesIPRevenueTarget += parseFloat(rd['T.IPRevenue']) || 0;

        salesTotalCensusActual += (parseFloat(rd['A.OPCensus']) || 0) + (parseFloat(rd['A.IPCensus']) || 0);
        salesTotalCensusTarget += (parseFloat(rd['T.OPCensus']) || 0) + (parseFloat(rd['T.IPCensus']) || 0);

        salesTotalRevenueActual += (parseFloat(rd['A.OPRevenue']) || 0) + (parseFloat(rd['A.IPRevenue']) || 0);
        salesTotalRevenueTarget += (parseFloat(rd['T.OPRevenue']) || 0) + (parseFloat(rd['T.IPRevenue']) || 0);
        
        salesActivityActual += (parseFloat(rd['A.ClinicActivity/AgentActivity']) || 0) +
                               (parseFloat(rd['A.CorporateActivity(HealthCheckup)']) || 0) +
                               (parseFloat(rd['A.CBDTour']) || 0) +
                               (parseFloat(rd['A.ReqularVisits']) || 0);

        salesActivityTarget += (parseFloat(rd['T.ClinicActivity/AgentActivity']) || 0) +
                               (parseFloat(rd['T.CorporateActivity(HealthCheckup)']) || 0) +
                               (parseFloat(rd['T.CBDTour']) || 0) +
                               (parseFloat(rd['T.ReqularVisits']) || 0);
      }

    });

    const currentRecords = filteredAgents.map((agent) => agent.raw);
    const configuredKpis = calculateAggregatedTeamPerformance(
      currentRecords,
      teamConfig,
      { location, preferConfiguredWeights: isMergedTeam },
    )?.kpis ?? aggregateConfiguredTeamKpis(currentRecords, teamConfig, { location, preferConfiguredWeights: isMergedTeam });
    const dynamicKpis = [...configuredKpis.values()];
    const bookingCR = configuredKpiPercent(configuredKpis, 'Booking Rate')
      ?? (totalCallsHandled > 0 ? (totalBookings / totalCallsHandled) * 100 : 0);
    const attendCR = configuredKpiPercent(configuredKpis, 'Attendance Rate')
      ?? (totalBookings > 0 ? (totalAttended / totalBookings) * 100 : 0);

    const configuredAhtMinutes = configuredKpiActual(configuredKpis, 'AHT (Handle Time)');
    const avgAHTSec = configuredAhtMinutes !== undefined
      ? configuredAhtMinutes * 60
      : filteredAgents.length > 0 ? totalAHTSeconds / filteredAgents.length : 0;
    const avgAHT = formatSecondsToMMSS(avgAHTSec);

    const abandonRate = configuredKpiPercent(configuredKpis, 'Abandon Rate')
      ?? (totalCallsHandled > 0 ? (totalAbandoned / totalCallsHandled) * 100 : 0);
    const reachabilityRate = configuredKpiPercent(configuredKpis, 'Reachability')
      ?? (agentsWithReachability > 0 ? (totalReachability / agentsWithReachability) * 100 : 0);
    const utzRate = agentsWithUTZ > 0 ? (totalUTZ / agentsWithUTZ) * 100 : 0;
    const hasUtz = agentsWithUTZ > 0;

    const preApprovalsIpMetrics = teamId === 'pre-approvals'
      ? aggregatePreApprovalsIpMetrics(filteredAgents.map((agent) => agent.raw))
      : null;
    const submissionRate = configuredKpiPercent(configuredKpis, 'Submission Rate')
      ?? preApprovalsIpMetrics?.submissionRate
      ?? (agentsWithSubmission > 0 ? (totalSubmission / agentsWithSubmission) * 100 : 0);
    const rejectionRate = configuredKpiPercent(configuredKpis, 'Rejection Rate')
      ?? preApprovalsIpMetrics?.rejectionRate
      ?? (agentsWithRejection > 0 ? (totalRejection / agentsWithRejection) * 100 : 0);
    const errorRate = configuredKpiPercent(configuredKpis, 'Initial Error Rate')
      ?? preApprovalsIpMetrics?.errorRate
      ?? (agentsWithError > 0 ? (totalError / agentsWithError) * 100 : 0);

    const opCensusRate = configuredKpiPercent(configuredKpis, 'OP Census Ach') ?? (salesOPCensusTarget > 0 ? (salesOPCensusActual / salesOPCensusTarget) * 100 : (agentsWithOPCensus > 0 ? (totalOPCensus / agentsWithOPCensus) * 100 : 0));
    const opRevenueRate = configuredKpiPercent(configuredKpis, 'OP Revenue Ach') ?? (salesOPRevenueTarget > 0 ? (salesOPRevenueActual / salesOPRevenueTarget) * 100 : (agentsWithOPRevenue > 0 ? (totalOPRevenue / agentsWithOPRevenue) * 100 : 0));
    const ipCensusRate = configuredKpiPercent(configuredKpis, 'IP Census Ach') ?? (salesIPCensusTarget > 0 ? (salesIPCensusActual / salesIPCensusTarget) * 100 : (agentsWithIPCensus > 0 ? (totalIPCensus / agentsWithIPCensus) * 100 : 0));
    const ipRevenueRate = configuredKpiPercent(configuredKpis, 'IP Revenue Ach') ?? (salesIPRevenueTarget > 0 ? (salesIPRevenueActual / salesIPRevenueTarget) * 100 : (agentsWithIPRevenue > 0 ? (totalIPRevenue / agentsWithIPRevenue) * 100 : 0));
    const activityRate = configuredKpiPercent(configuredKpis, 'Activity Score') ?? (salesActivityTarget > 0 ? (salesActivityActual / salesActivityTarget) * 100 : (agentsWithActivity > 0 ? (totalActivity / agentsWithActivity) * 100 : 0));
    const totalCensusRate = salesTotalCensusTarget > 0 ? (salesTotalCensusActual / salesTotalCensusTarget) * 100 : (agentsWithTotalCensus > 0 ? (totalTotalCensus / agentsWithTotalCensus) * 100 : 0);
    const totalRevenueRate = salesTotalRevenueTarget > 0 ? (salesTotalRevenueActual / salesTotalRevenueTarget) * 100 : (agentsWithTotalRevenue > 0 ? (totalTotalRevenue / agentsWithTotalRevenue) * 100 : 0);

    // Funnel data
    const funnelData = {
      calls: totalCallsHandled,
      bookings: totalBookings,
      attended: totalAttended,
      callToBookingRate: totalCallsHandled > 0 ? totalBookings / totalCallsHandled : 0,
      bookingToAttendRate: totalBookings > 0 ? totalAttended / totalBookings : 0,
    };

    return {
      bookingCR,
      attendCR,
      avgAHT,
      avgAHTSec,
      abandonRate,
      reachabilityRate,
      funnelData,
      totalBookings,
      totalAttended,
      totalCallsHandled,
      totalAbandoned,
      utzRate,
      hasUtz,
      submissionRate,
      rejectionRate,
      errorRate,
      rejectionWeight: preApprovalsIpMetrics?.rejectionWeight,
      rejectionContribution: preApprovalsIpMetrics?.rejectionContribution,
      errorWeight: preApprovalsIpMetrics?.errorWeight,
      errorContribution: preApprovalsIpMetrics?.errorContribution,
      submissionWeight: preApprovalsIpMetrics?.submissionWeight,
      submissionContribution: preApprovalsIpMetrics?.submissionContribution,
      opCensusRate,
      opRevenueRate,
      ipCensusRate,
      ipRevenueRate,
      activityRate,
      totalCensusRate,
      totalRevenueRate,
      salesOPCensusActual,
      salesOPCensusTarget,
      salesOPRevenueActual,
      salesOPRevenueTarget,
      salesIPCensusActual,
      salesIPCensusTarget,
      salesIPRevenueActual,
      salesIPRevenueTarget,
      salesTotalCensusActual,
      salesTotalCensusTarget,
      salesTotalRevenueActual,
      salesTotalRevenueTarget,
      salesActivityActual,
      salesActivityTarget,
      dynamicKpis,
    };
  }, [rows, location, teamId, teamConfig, isMergedTeam]);

  // Compute call center metrics for the previous month (for MoM delta calculation)
  const prevTeamMetrics = useMemo(() => {
    if (!prevMonth) return null;

    let prevAgents = allAgents.filter((a) => {
      if (a.identity.month !== prevMonth) return false;
      if (isCallCenterParent && callCenterChannel !== 'all' && !isCallCenterChannelTeam(a.identity.team, callCenterChannel)) return false;
      return !teamName || sameTeam(a.identity.team, teamName);
    });

    if (location !== 'all') {
      prevAgents = prevAgents.filter((a) => agentMatchesLocation(a, location));
    }

    let totalBookings = 0;
    let totalAttended = 0;
    let totalCallsHandled = 0;
    let totalAbandoned = 0;
    let totalAHTSeconds = 0;
    let totalReachability = 0;
    let agentsWithReachability = 0;
    let totalUTZ = 0;
    let agentsWithUTZ = 0;

    let totalOPCensus = 0;
    let agentsWithOPCensus = 0;
    let totalOPRevenue = 0;
    let agentsWithOPRevenue = 0;
    let totalIPCensus = 0;
    let agentsWithIPCensus = 0;
    let totalIPRevenue = 0;
    let agentsWithIPRevenue = 0;
    let totalActivity = 0;
    let agentsWithActivity = 0;
    let totalSubmission = 0;
    let agentsWithSubmission = 0;
    let totalRejection = 0;
    let agentsWithRejection = 0;
    let totalError = 0;
    let agentsWithError = 0;
    let totalTotalCensus = 0;
    let agentsWithTotalCensus = 0;
    let totalTotalRevenue = 0;
    let agentsWithTotalRevenue = 0;

    let salesOPCensusActual = 0;
    let salesOPCensusTarget = 0;
    let salesOPRevenueActual = 0;
    let salesOPRevenueTarget = 0;
    let salesIPCensusActual = 0;
    let salesIPCensusTarget = 0;
    let salesIPRevenueActual = 0;
    let salesIPRevenueTarget = 0;
    let salesTotalCensusActual = 0;
    let salesTotalCensusTarget = 0;
    let salesTotalRevenueActual = 0;
    let salesTotalRevenueTarget = 0;
    let salesActivityActual = 0;
    let salesActivityTarget = 0;

    prevAgents.forEach((agent) => {
      const geoB = agent.geo?.bookings || { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 };
      const geoA = agent.geo?.attended || { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 };

      totalBookings += getGeoValue(geoB, location);
      totalAttended += getGeoValue(geoA, location);

      const calls = agent.calls || { total_handled: 0, inbound: 0, abandoned: 0, aht_raw: '00:00:00' };
      totalCallsHandled += calls.total_handled;
      totalAbandoned += calls.abandoned;

      totalAHTSeconds += parseAHTtoSeconds(calls.aht_raw || '00:00:00');

      const actual = agent.actual || {};
      if (actual.reachability_rate !== undefined) {
        totalReachability += actual.reachability_rate;
        agentsWithReachability++;
      }

      if (actual.utz_rate !== undefined && actual.utz_rate > 0) {
        totalUTZ += actual.utz_rate;
        agentsWithUTZ++;
      }

      if (actual.submission_rate !== undefined) {
        totalSubmission += actual.submission_rate;
        agentsWithSubmission++;
      }

      if (actual.rejection_rate !== undefined) {
        totalRejection += actual.rejection_rate;
        agentsWithRejection++;
      }

      if (actual.initial_error_rate !== undefined) {
        totalError += actual.initial_error_rate;
        agentsWithError++;
      }

      // Sales achievements mapping
      const ach = agent.achievement || {};
      if (ach.op_census_ach !== undefined && ach.op_census_ach > 0) {
        totalOPCensus += ach.op_census_ach;
        agentsWithOPCensus++;
      }
      if (ach.op_revenue_ach !== undefined && ach.op_revenue_ach > 0) {
        totalOPRevenue += ach.op_revenue_ach;
        agentsWithOPRevenue++;
      }
      if (ach.ip_census_ach !== undefined && ach.ip_census_ach > 0) {
        totalIPCensus += ach.ip_census_ach;
        agentsWithIPCensus++;
      }
      if (ach.ip_revenue_ach !== undefined && ach.ip_revenue_ach > 0) {
        totalIPRevenue += ach.ip_revenue_ach;
        agentsWithIPRevenue++;
      }
      if (ach.activity_ach !== undefined && ach.activity_ach > 0) {
        totalActivity += ach.activity_ach;
        agentsWithActivity++;
      }

      if (agent.raw_data?.['Total Census Ach%'] !== undefined) {
        totalTotalCensus += parseFloat(agent.raw_data['Total Census Ach%']) / 100.0 || 0;
        agentsWithTotalCensus++;
      } else {
        const act = parseFloat(agent.raw_data?.['A.Total Census'] ?? '0') || 0;
        const tgt = parseFloat(agent.raw_data?.['T.Total Census'] ?? '0') || 0;
        if (tgt > 0) {
          totalTotalCensus += act / tgt;
          agentsWithTotalCensus++;
        }
      }

      if (agent.raw_data?.['Total Revenue Ach%'] !== undefined) {
        totalTotalRevenue += parseFloat(agent.raw_data['Total Revenue Ach%']) / 100.0 || 0;
        agentsWithTotalRevenue++;
      } else {
        const act = parseFloat(agent.raw_data?.['A.Total Revenue'] ?? '0') || 0;
        const tgt = parseFloat(agent.raw_data?.['T.Total Revenue'] ?? '0') || 0;
        if (tgt > 0) {
          totalTotalRevenue += act / tgt;
          agentsWithTotalRevenue++;
        }
      }

      // Sales actual volumes mapping
      if (agent.raw_data) {
        const rd = agent.raw_data;
        salesOPCensusActual += parseFloat(rd['A.OPCensus']) || 0;
        salesOPCensusTarget += parseFloat(rd['T.OPCensus']) || 0;

        salesOPRevenueActual += parseFloat(rd['A.OPRevenue']) || 0;
        salesOPRevenueTarget += parseFloat(rd['T.OPRevenue']) || 0;

        salesIPCensusActual += parseFloat(rd['A.IPCensus']) || 0;
        salesIPCensusTarget += parseFloat(rd['T.IPCensus']) || 0;

        salesIPRevenueActual += parseFloat(rd['A.IPRevenue']) || 0;
        salesIPRevenueTarget += parseFloat(rd['T.IPRevenue']) || 0;

        salesTotalCensusActual += (parseFloat(rd['A.OPCensus']) || 0) + (parseFloat(rd['A.IPCensus']) || 0);
        salesTotalCensusTarget += (parseFloat(rd['T.OPCensus']) || 0) + (parseFloat(rd['T.IPCensus']) || 0);

        salesTotalRevenueActual += (parseFloat(rd['A.OPRevenue']) || 0) + (parseFloat(rd['A.IPRevenue']) || 0);
        salesTotalRevenueTarget += (parseFloat(rd['T.OPRevenue']) || 0) + (parseFloat(rd['T.IPRevenue']) || 0);
        
        salesActivityActual += (parseFloat(rd['A.ClinicActivity/AgentActivity']) || 0) +
                               (parseFloat(rd['A.CorporateActivity(HealthCheckup)']) || 0) +
                               (parseFloat(rd['A.CBDTour']) || 0) +
                               (parseFloat(rd['A.ReqularVisits']) || 0);

        salesActivityTarget += (parseFloat(rd['T.ClinicActivity/AgentActivity']) || 0) +
                               (parseFloat(rd['T.CorporateActivity(HealthCheckup)']) || 0) +
                               (parseFloat(rd['T.CBDTour']) || 0) +
                               (parseFloat(rd['T.ReqularVisits']) || 0);
      }

    });

    const configuredKpis = calculateAggregatedTeamPerformance(prevAgents, teamConfig, { location, preferConfiguredWeights: isMergedTeam })?.kpis
      ?? aggregateConfiguredTeamKpis(prevAgents, teamConfig, { location, preferConfiguredWeights: isMergedTeam });
    const dynamicKpis = [...configuredKpis.values()];
    const bookingCR = configuredKpiPercent(configuredKpis, 'Booking Rate')
      ?? (totalCallsHandled > 0 ? (totalBookings / totalCallsHandled) * 100 : 0);
    const attendCR = configuredKpiPercent(configuredKpis, 'Attendance Rate')
      ?? (totalBookings > 0 ? (totalAttended / totalBookings) * 100 : 0);
    const configuredAhtMinutes = configuredKpiActual(configuredKpis, 'AHT (Handle Time)');
    const avgAHTSec = configuredAhtMinutes !== undefined
      ? configuredAhtMinutes * 60
      : prevAgents.length > 0 ? totalAHTSeconds / prevAgents.length : 0;
    const abandonRate = configuredKpiPercent(configuredKpis, 'Abandon Rate')
      ?? (totalCallsHandled > 0 ? (totalAbandoned / totalCallsHandled) * 100 : 0);
    const reachabilityRate = configuredKpiPercent(configuredKpis, 'Reachability')
      ?? (agentsWithReachability > 0 ? (totalReachability / agentsWithReachability) * 100 : 0);
    const utzRate = agentsWithUTZ > 0 ? (totalUTZ / agentsWithUTZ) * 100 : 0;

    const opCensusRate = configuredKpiPercent(configuredKpis, 'OP Census Ach') ?? (salesOPCensusTarget > 0 ? (salesOPCensusActual / salesOPCensusTarget) * 100 : (agentsWithOPCensus > 0 ? (totalOPCensus / agentsWithOPCensus) * 100 : 0));
    const opRevenueRate = configuredKpiPercent(configuredKpis, 'OP Revenue Ach') ?? (salesOPRevenueTarget > 0 ? (salesOPRevenueActual / salesOPRevenueTarget) * 100 : (agentsWithOPRevenue > 0 ? (totalOPRevenue / agentsWithOPRevenue) * 100 : 0));
    const ipCensusRate = configuredKpiPercent(configuredKpis, 'IP Census Ach') ?? (salesIPCensusTarget > 0 ? (salesIPCensusActual / salesIPCensusTarget) * 100 : (agentsWithIPCensus > 0 ? (totalIPCensus / agentsWithIPCensus) * 100 : 0));
    const ipRevenueRate = configuredKpiPercent(configuredKpis, 'IP Revenue Ach') ?? (salesIPRevenueTarget > 0 ? (salesIPRevenueActual / salesIPRevenueTarget) * 100 : (agentsWithIPRevenue > 0 ? (totalIPRevenue / agentsWithIPRevenue) * 100 : 0));
    const activityRate = configuredKpiPercent(configuredKpis, 'Activity Score') ?? (salesActivityTarget > 0 ? (salesActivityActual / salesActivityTarget) * 100 : (agentsWithActivity > 0 ? (totalActivity / agentsWithActivity) * 100 : 0));
    const totalCensusRate = salesTotalCensusTarget > 0 ? (salesTotalCensusActual / salesTotalCensusTarget) * 100 : (agentsWithTotalCensus > 0 ? (totalTotalCensus / agentsWithTotalCensus) * 100 : 0);
    const totalRevenueRate = salesTotalRevenueTarget > 0 ? (salesTotalRevenueActual / salesTotalRevenueTarget) * 100 : (agentsWithTotalRevenue > 0 ? (totalTotalRevenue / agentsWithTotalRevenue) * 100 : 0);
    const preApprovalsIpMetrics = teamId === 'pre-approvals'
      ? aggregatePreApprovalsIpMetrics(prevAgents)
      : null;
    const submissionRate = configuredKpiPercent(configuredKpis, 'Submission Rate')
      ?? preApprovalsIpMetrics?.submissionRate
      ?? (agentsWithSubmission > 0 ? (totalSubmission / agentsWithSubmission) * 100 : 0);
    const rejectionRate = configuredKpiPercent(configuredKpis, 'Rejection Rate')
      ?? preApprovalsIpMetrics?.rejectionRate
      ?? (agentsWithRejection > 0 ? (totalRejection / agentsWithRejection) * 100 : 0);
    const errorRate = configuredKpiPercent(configuredKpis, 'Initial Error Rate')
      ?? preApprovalsIpMetrics?.errorRate
      ?? (agentsWithError > 0 ? (totalError / agentsWithError) * 100 : 0);

    return {
      bookingCR,
      attendCR,
      avgAHTSec,
      abandonRate,
      reachabilityRate,
      utzRate,
      opCensusRate,
      opRevenueRate,
      ipCensusRate,
      ipRevenueRate,
      activityRate,
      totalCensusRate,
      totalRevenueRate,
      submissionRate,
      rejectionRate,
      errorRate,
      rejectionWeight: preApprovalsIpMetrics?.rejectionWeight,
      rejectionContribution: preApprovalsIpMetrics?.rejectionContribution,
      errorWeight: preApprovalsIpMetrics?.errorWeight,
      errorContribution: preApprovalsIpMetrics?.errorContribution,
      submissionWeight: preApprovalsIpMetrics?.submissionWeight,
      submissionContribution: preApprovalsIpMetrics?.submissionContribution,
      dynamicKpis,
    };
  }, [prevMonth, allAgents, teamName, location, teamId, teamConfig, isMergedTeam, isCallCenterParent, callCenterChannel]);

  // Filter and compute Top 3 / Bottom 3 performers on the fly
  const rosterData = useMemo(() => {
    const teamAgents = rows || [];
    const takeUniqueEmployees = (agents: TeamAgentRow[], limit: number) => {
      const selected: TeamAgentRow[] = [];
      const seenEmployeeIds = new Set<string>();

      for (const agent of agents) {
        if (seenEmployeeIds.has(agent.id)) continue;
        seenEmployeeIds.add(agent.id);
        selected.push(agent);
        if (selected.length === limit) break;
      }

      return selected;
    };

    // Sort to find Top 3 (Score descending)
    const sortedDesc = [...teamAgents].sort((a, b) => scoreForDisplay(b) - scoreForDisplay(a));
    const top3 = takeUniqueEmployees(sortedDesc, 3);
    const topEmployeeIds = new Set(top3.map((agent) => agent.id));

    // Bottom performers must be below target and must not already appear in Top 3.
    const belowTargetAgents = teamAgents.filter((agent) => scoreForDisplay(agent) < 80);
    const bottomCandidates = belowTargetAgents.filter((agent) => !topEmployeeIds.has(agent.id));
    const sortedAsc = [...bottomCandidates].sort((a, b) => scoreForDisplay(a) - scoreForDisplay(b));
    const bottom3 = takeUniqueEmployees(sortedAsc, 3);

    const allMeetStandards = belowTargetAgents.length === 0;

    return {
      top3,
      bottom3,
      allMeetStandards,
      teamAgents,
    };
  }, [rows]);

  // Filter + sort for the full list view
  const filtered = useMemo(() => {
    const data = [...(rows || [])];
    if (search) {
      const query = search.toLowerCase();
      return data.filter((r) => r.name.toLowerCase().includes(query));
    }
    data.sort((a, b) => {
      let cmp = 0;
      if (sortCol === 'score') cmp = scoreForDisplay(a) - scoreForDisplay(b);
      else if (sortCol === 'name') cmp = a.name.localeCompare(b.name);
      else if (sortCol === 'status') cmp = a.status.localeCompare(b.status);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return data;
  }, [rows, search, sortCol, sortDir]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const toggleSort = (col: 'score' | 'name' | 'status') => {
    if (sortCol === col) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    else {
      setSortCol(col);
      setSortDir('desc');
    }    setPage(1);
  };

  // Pie data
  const pieData = (['A', 'B', 'C', 'D', 'E'] as const)
    .map((g) => ({ name: `Class ${g}`, value: metrics.classCounts[g], color: GRADE_PIE_COLORS[g] }))
    .filter((d) => d.value > 0);

  // Trend line: avg score over months (team-filtered)
  const trendData = useMemo(() => {
    let filteredAgents = teamName
      ? allAgents.filter((a) => sameTeam(a.identity.team, teamName))
      : allAgents;

    if (isCallCenterParent && callCenterChannel !== 'all') {
      filteredAgents = filteredAgents.filter((a) => isCallCenterChannelTeam(a.identity.team, callCenterChannel));
    }
    filteredAgents = filteredAgents.filter(matchesPresentationScope);

    if (location !== 'all') {
      filteredAgents = filteredAgents.filter((a) => agentMatchesLocation(a, location));
    }

    return dashboardMonths.slice(-6).map((m) => {
      const monthAgents = filteredAgents.filter((a) => a.identity.month === m && hasRealActivity(a));
      const canonicalScore = getCanonicalTeamScore(monthAgents);
      const fallbackScore = monthAgents.length > 0
        ? monthAgents.reduce((sum, a) => sum + resolveDisplayScore(a, activeTeamWeights), 0) / monthAgents.length
        : 0;

      const avgScore = (canonicalScore !== null && canonicalScore > 0 && Math.abs(canonicalScore - fallbackScore) <= 15)
        ? canonicalScore
        : fallbackScore;

      return {
        month: m.slice(0, 3),
        score: Math.round(avgScore * 10) / 10,
      };
    });
  }, [dashboardMonths, allAgents, teamName, location, getCanonicalTeamScore, activeTeamWeights, isCallCenterParent, callCenterChannel, matchesPresentationScope]);

  const performanceBullets = useMemo(() => {
    const bullets: Array<{
      icon: LucideIcon;
      title: string;
      desc: string;
      badgeText?: string;
      status: 'success' | 'warning' | 'danger' | 'info';
    }> = [];

    if (!rows || rows.length === 0) {
      bullets.push({
        icon: AlertCircle,
        title: 'No Performance Data',
        desc: 'No performance records are available for this team in the selected month.',
        badgeText: 'NO DATA',
        status: 'info'
      });
      return bullets;
    }

    const avg = hookAvgScore;

    // 1. Grade Distribution description (Always present if rows exist)
    let gradesDesc = 'mixed with standard performance distribution';
    let avgStatus: 'success' | 'warning' | 'danger' | 'info' = 'warning';
    let avgBadge = 'STABLE';
    let avgIcon = TrendingUp;;

    if (avg >= 85) {
      gradesDesc = 'strong with most agents meeting or exceeding expectations';
      avgStatus = 'success';
      avgBadge = 'EXCELLENT';
      avgIcon = Award;
    } else if (avg >= 75) {
      avgStatus = 'warning';
      avgBadge = 'STABLE';
      avgIcon = TrendingUp;
      if (scoredTeamId === 'outbound') {
        gradesDesc = 'mixed with structural blockers in lead quality';
      } else if (scoredTeamId === 'inbound') {
        gradesDesc = 'mixed with structural blockers in queue handling';
      } else if (scoredTeamId === 'inbound-uae') {
        gradesDesc = 'mixed with structural blockers in SLA compliance';
      } else if (teamId === 'pre-approvals') {
        gradesDesc = 'mixed with structural blockers in approval pipelines';
      } else if (teamId === 'sales') {
        gradesDesc = 'mixed with structural blockers in sales conversion';
      } else {
        gradesDesc = 'mixed with some structural blockers in performance';
      }
    } else if (avg > 0) {
      gradesDesc = 'low with multiple agents requiring close supervision';
      avgStatus = 'danger';
      avgBadge = 'NEEDS ATTENTION';
      avgIcon = AlertCircle;
    }

    bullets.push({
      icon: avgIcon,
      title: `Team Average Score: ${avg.toFixed(1)}%`,
      desc: `Overall team grades are ${gradesDesc}.`,
      badgeText: avgBadge,
      status: avgStatus
    });

    // Worst performing agent details
    const sortedRows = [...(rows || [])].sort((a, b) => (a.displayWeightedScore ?? a.score) - (b.displayWeightedScore ?? b.score));
    const worstAgent = sortedRows.length > 0 && (sortedRows[0].displayWeightedScore ?? sortedRows[0].score) < 80 ? sortedRows[0] : null;
    const worstAgentName = worstAgent ? worstAgent.name.split(' ')[0] : '';

    // Check availability of each KPI in the filtered month's records (non-zero check)
    const hasBooking = (rows || []).some(r => r.raw.actual?.booking_rate !== undefined && r.raw.actual?.booking_rate > 0);
    const hasReachability = (rows || []).some(r => r.raw.actual?.reachability_rate !== undefined && r.raw.actual?.reachability_rate > 0);
    const hasAbandon = (rows || []).some(r => r.raw.actual?.abandon_rate !== undefined && r.raw.actual?.abandon_rate > 0);
    const hasUtz = (rows || []).some(r => r.raw.actual?.utz_rate !== undefined && r.raw.actual?.utz_rate > 0);
    const hasSubmission = (rows || []).some(r => r.raw.actual?.submission_rate !== undefined && r.raw.actual?.submission_rate > 0);
    const hasRejectionOrError = (rows || []).some(r =>
      (r.raw.actual?.rejection_rate !== undefined && r.raw.actual?.rejection_rate > 0) ||
      (r.raw.actual?.initial_error_rate !== undefined && r.raw.actual?.initial_error_rate > 0)
    );

    // 2. Core targets & 3. Reachability/Abandon Rate/worst performer
    if (scoredTeamId === 'outbound') {
      if (hasBooking) {
        const bTarget = 46;
        const bCR = teamMetrics.bookingCR;
        const meetsB = bCR >= bTarget;
        bullets.push({
          icon: Target,
          title: `Booking Conversion: ${bCR.toFixed(1)}%`,
          desc: `Target is ${bTarget}%. Performance is currently running ${meetsB ? 'above' : 'below'} standard.`,
          badgeText: meetsB ? 'TARGET MET' : bCR < bTarget * 0.7 ? 'CRITICAL' : 'BELOW TARGET',
          status: meetsB ? 'success' : bCR < bTarget * 0.7 ? 'danger' : 'warning'
        });
      }

      if (hasReachability) {
        const rCR = teamMetrics.reachabilityRate;
        const meetsR = rCR >= 75;
        if (worstAgent) {
          bullets.push({
            icon: Activity,
            title: `Reachability Rate: ${rCR.toFixed(1)}%`,
            desc: `Departmental target is 75%. Coaching is recommended for ${worstAgentName} (Attendance CR: ${(worstAgent.attendRate * 100).toFixed(1)}%) to improve outbound performance.`,
            badgeText: meetsR ? 'STABLE' : 'NEEDS FOCUS',
            status: meetsR ? 'success' : 'warning'
          });
        } else {
          bullets.push({
            icon: Activity,
            title: `Reachability Rate: ${rCR.toFixed(1)}%`,
            desc: `Departmental target is 75%. Reachability is performing stably and all agents meet standards.`,
            badgeText: 'TARGET MET',
            status: 'success'
          });
        }
      }
    } else if (scoredTeamId === 'inbound') {
      if (hasBooking) {
        const bTarget = 45;
        const bCR = teamMetrics.bookingCR;
        const meetsB = bCR >= bTarget;
        bullets.push({
          icon: Target,
          title: `Booking Conversion: ${bCR.toFixed(1)}%`,
          desc: `Target is ${bTarget}%. Performance is currently running ${meetsB ? 'above' : 'below'} standard.`,
          badgeText: meetsB ? 'TARGET MET' : bCR < bTarget * 0.7 ? 'CRITICAL' : 'BELOW TARGET',
          status: meetsB ? 'success' : bCR < bTarget * 0.7 ? 'danger' : 'warning'
        });
      }

      if (hasUtz) {
        const utzR = teamMetrics.utzRate;
        const meetsU = utzR >= 85;
        bullets.push({
          icon: Activity,
          title: `Utilization Rate: ${utzR.toFixed(1)}%`,
          desc: `Target is 85%. Current rate is running ${meetsU ? 'above' : 'below'} standard.`,
          badgeText: meetsU ? 'TARGET MET' : 'BELOW TARGET',
          status: meetsU ? 'success' : 'warning'
        });
      } else if (hasAbandon) {
        const abR = teamMetrics.abandonRate;
        const meetsA = abR <= 1.0;
        if (worstAgent) {
          bullets.push({
            icon: Activity,
            title: `Call Abandon Rate: ${abR.toFixed(1)}%`,
            desc: `Inbound threshold is 1.0%. Coaching is recommended for ${worstAgentName} (AHT: ${worstAgent.ahtMinutes.toFixed(1)} min) to reduce queue hold times.`,
            badgeText: meetsA ? 'STABLE' : 'HIGH ABANDON',
            status: meetsA ? 'success' : 'danger'
          });
        } else {
          bullets.push({
            icon: Activity,
            title: `Call Abandon Rate: ${abR.toFixed(1)}%`,
            desc: `Inbound threshold is 1.0%. Abandon rate is within target bounds.`,
            badgeText: 'TARGET MET',
            status: 'success'
          });
        }
      }
    } else if (scoredTeamId === 'inbound-uae') {
      if (hasBooking) {
        const bTarget = 60;
        const bCR = teamMetrics.bookingCR;
        const meetsB = bCR >= bTarget;
        bullets.push({
          icon: Target,
          title: `Booking Conversion: ${bCR.toFixed(1)}%`,
          desc: `Target is ${bTarget}%. Performance is currently running ${meetsB ? 'above' : 'below'} standard.`,
          badgeText: meetsB ? 'TARGET MET' : bCR < bTarget * 0.7 ? 'CRITICAL' : 'BELOW TARGET',
          status: meetsB ? 'success' : bCR < bTarget * 0.7 ? 'danger' : 'warning'
        });
      }

      if (hasUtz) {
        const utzR = teamMetrics.utzRate;
        const meetsU = utzR >= 85;
        bullets.push({
          icon: Activity,
          title: `Utilization Rate: ${utzR.toFixed(1)}%`,
          desc: `Target is 85%. Current rate is running ${meetsU ? 'above' : 'below'} standard.`,
          badgeText: meetsU ? 'TARGET MET' : 'BELOW TARGET',
          status: meetsU ? 'success' : 'warning'
        });
      } else if (hasAbandon) {
        const abR = teamMetrics.abandonRate;
        const meetsA = abR <= 1.0;
        if (worstAgent) {
          bullets.push({
            icon: Activity,
            title: `Call Abandon Rate: ${abR.toFixed(1)}%`,
            desc: `Inbound threshold is 1.0%. Coaching is recommended for ${worstAgentName} (Booking CR: ${(worstAgent.bookingRate * 100).toFixed(1)}%) to improve service levels.`,
            badgeText: meetsA ? 'STABLE' : 'HIGH ABANDON',
            status: meetsA ? 'success' : 'danger'
          });
        } else {
          bullets.push({
            icon: Activity,
            title: `Call Abandon Rate: ${abR.toFixed(1)}%`,
            desc: `Inbound threshold is 1.0%. Abandon rate is within target bounds.`,
            badgeText: 'TARGET MET',
            status: 'success'
          });
        }
      }
    } else if (teamId === 'pre-approvals') {
      if (hasSubmission) {
        const sTarget = 90;
        const sRate = teamMetrics.submissionRate || 0;
        const meetsS = sRate >= sTarget;
        bullets.push({
          icon: Target,
          title: `Submission Rate: ${sRate.toFixed(1)}%`,
          desc: `Pre-approvals target is ${sTarget}%. Current rate is running ${meetsS ? 'above' : 'below'} target.`,
          badgeText: meetsS ? 'TARGET MET' : sRate < sTarget * 0.7 ? 'CRITICAL' : 'BELOW TARGET',
          status: meetsS ? 'success' : sRate < sTarget * 0.7 ? 'danger' : 'warning'
        });
      }

      if (hasRejectionOrError) {
        const rejR = teamMetrics.rejectionRate || 0;
        const errR = teamMetrics.errorRate || 0;
        const meetsRE = rejR <= 3.0 && errR <= 3.0;
        if (worstAgent) {
          const rawActual = worstAgent.raw?.actual || {};
          const agentErrorRate = (rawActual.initial_error_rate ?? 0) * 100;
          bullets.push({
            icon: AlertTriangle,
            title: `Rejection (${rejR.toFixed(1)}%) & Error (${errR.toFixed(1)}%)`,
            desc: `Monitored threshold is 3.0%. Coaching recommended for ${worstAgentName} (Error Rate: ${agentErrorRate.toFixed(1)}%) to enhance accuracy.`,
            badgeText: meetsRE ? 'STABLE' : 'NEEDS ACTION',
            status: meetsRE ? 'success' : 'warning'
          });
        } else {
          bullets.push({
            icon: AlertTriangle,
            title: `Rejection (${rejR.toFixed(1)}%) & Error (${errR.toFixed(1)}%)`,
            desc: `Monitored threshold is 3.0%. Rejection and Error metrics are stable and on target.`,
            badgeText: 'TARGET MET',
            status: 'success'
          });
        }
      }
    } else if (teamMetrics.dynamicKpis && teamMetrics.dynamicKpis.length > 0) {
      teamMetrics.dynamicKpis.forEach((kpi) => {
        const isOnTarget = kpi.isLowerBetter ? kpi.actual <= kpi.target : kpi.actual >= kpi.target;
        const diffPct = kpi.target !== 0 ? Math.abs((kpi.actual - kpi.target) / kpi.target) * 100 : 0;
        
        let status: 'success' | 'warning' | 'danger' | 'info' = 'success';
        let badgeText = 'TARGET MET';
        
        if (!isOnTarget) {
          status = diffPct > 20 ? 'danger' : 'warning';
          badgeText = diffPct > 20 ? 'CRITICAL' : 'BELOW TARGET';
        }

        const formatVal = (val: number, unit: string) => {
          if (unit === '%') return `${(val * 100).toFixed(1)}%`;
          if (unit === 'currency') return `AED ${val.toFixed(1)}`;
          if (unit === 'min') return `${val.toFixed(1)} min`;
          return val.toFixed(1);
        };

        let bulletIcon = Activity;
        if (kpi.label.toLowerCase().includes('error')) bulletIcon = AlertTriangle;
        else if (kpi.label.toLowerCase().includes('rejection')) bulletIcon = AlertCircle;
        else if (isOnTarget) bulletIcon = Target;

        bullets.push({
          icon: bulletIcon,
          title: `${kpi.label}: ${formatVal(kpi.actual, kpi.unit)}`,
          desc: `Target is ${formatVal(kpi.target, kpi.unit)}. Team is currently ${isOnTarget ? 'meeting' : 'missing'} the target.`,
          badgeText,
          status
        });
      });
    } else {
      bullets.push({
        icon: Activity,
        title: 'Cross-Departmental Performance',
        desc: 'Metrics are aggregated across all active departments.',
        status: 'info'
      });
    }

    return bullets;
  }, [teamId, scoredTeamId, hookAvgScore, rows, teamMetrics]);

  if (loading) {
    return <OperationalViewSkeleton />;
  }

  // Export Excel
  const handleExport = async () => {
    const exportTeam = isRcmParent
      ? RCM_TEAM
      : isPreApprovalsParent
      ? preApprovalsWorkflow === 'op_final'
        ? MERGED_OP_FINAL_TEAM
        : preApprovalsWorkflow === 'ip_final'
          ? MERGED_IP_FINAL_TEAM
          : preApprovalsWorkflow === 'ip_elective'
            ? 'Pre-Approvals IP Elective Dubai'
            : PRE_APPROVALS_UAE_TEAM
      : isCallCenterParent
        ? callCenterChannel === 'inbound'
          ? 'Inbound'
          : callCenterChannel === 'outbound'
            ? 'Outbound'
            : CALL_CENTER_TEAM
      : teamName || 'All';
    const params = new URLSearchParams({
      month: month === 'All' ? 'All' : month,
      team: exportTeam,
      format: 'excel',
      performance_level: performanceLevel,
    });
    if (isPreApprovalsParent) params.set('workflow', preApprovalsWorkflow);
    if (isCallCenterParent) params.set('channel', callCenterChannel);
    if (isRcmParent) params.set('domain', rcmDomain);
    if (isRcmParent) params.set('group', rcmGroup);
    try {
      const res = await fetchWithRole(`${API_BASE}/api/performance/export?${params}`);
      if (!res.ok) {
        alert('Export failed. Check your role permissions.');
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `PMS_${displayName}_${month}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert('Export failed: backend offline.');
    }
  };

  if (!isTeamAccessRestricted && hasBalancedScorecard && teamName) {
    return (
      <BalancedScorecardWorkspace
        teamName={teamName}
        displayName={displayName}
        config={teamConfig}
      />
    );
  }

  if (isTeamAccessRestricted || hookTotalAgents === 0) {
    const branchLabels: Record<LocationKey, string> = {
      all: 'all branches',
      dubai: 'Dubai',
      sharjah: 'Sharjah',
      ajman: 'Ajman',
      clinics: 'Clinics',
    };
    const hasEmptyBranchSelection = isMergedTeam && !isCallCenterParent && !branchSelections.includes('all') && !isTeamAccessRestricted;
    const emptyBranchLabel = hasEmptyBranchSelection
      ? branchSelections.map((branch) => branchLabels[branch]).join(' and ')
      : '';
    return (
      <div className="max-w-[1600px] mx-auto space-y-6 text-slate-800 dark:text-slate-100">
        <TeamHeader
          displayName={displayName}
          month={month}
          uniqueMonths={dashboardMonths}
          setMonth={(m) => {
            setMonth(m);
            setPage(1);
          }}
          region={region}
          setRegion={(r) => {
            setRegion(r);
            setPage(1);
          }}
          location={location}
          setLocation={(l) => {
            setLocation(l);
            setPage(1);
          }}
          branchSelections={branchSelections}
          setBranchSelections={(next) => {
            setBranchSelections(next);
            setPage(1);
          }}
          multiBranchFilter={isMergedTeam && !isCallCenterParent}
          showPreApprovalsWorkflowFilter={isPreApprovalsParent || (isRcmParent && rcmDomain === 'pre_approvals' && rcmGroup !== 'offshore_egy')}
          preApprovalsWorkflow={preApprovalsWorkflow}
          setPreApprovalsWorkflow={handlePreApprovalsWorkflowChange}
          showCallCenterChannelFilter={isCallCenterParent}
          callCenterChannel={callCenterChannel}
          setCallCenterChannel={handleCallCenterChannelChange}
          showRcmDomainFilter={isRcmParent}
          rcmDomain={rcmDomain}
          setRcmDomain={handleRcmDomainChange}
          showRcmGroupFilter={isRcmParent}
          rcmGroup={rcmGroup}
          setRcmGroup={handleRcmGroupChange}
          onBack={() => navigate('/executive')}
          showRegionFilter={teamId === 'all'}
          performanceLevel={performanceLevel}
          setPerformanceLevel={(level) => {
            setPerformanceLevel(level);
            setPage(1);
          }}
          disabledPerformanceLevel={true}
        />
        <NoDataEmptyState
          availablePeriods={isTeamAccessRestricted ? [] : availableTeamPeriods}
          selectedMonth={month}
          dataSource={dataSource}
          errorMessage={isTeamAccessRestricted ? '403: Access Denied for this team.' : errorMessage}
          emptyTitle={hasEmptyBranchSelection ? 'No Performance Data for Selected Branch' : undefined}
          emptyDescription={hasEmptyBranchSelection
            ? `No KPI numbers are available for ${emptyBranchLabel} in the selected period. Try another branch or choose All Branches.`
            : undefined}
          onSelectPeriod={(m) => {
            setMonth(m);
            setPage(1);
          }}
        />
      </div>
    );
  }

  const getTeamIcon = () => {
    if (teamId === 'pre-approvals') {
      return <Shield size={18} className="text-white" />;
    }
    if (teamId === 'sales') {
      return <Target size={18} className="text-white" />;
    }
    if (teamId === 'coding') {
      return <Code size={18} className="text-white" />;
    }
    if (teamId === 'csr') {
      return <Headphones size={18} className="text-white" />;
    }
    if (teamId === 'pharmacy') {
      return <Pill size={18} className="text-white" />;
    }
    if (teamId === 'submission') {
      return <Send size={18} className="text-white" />;
    }
    return <Phone size={18} className="text-white" />;
  };

  const summaryCards = teamId === 'all' ? [
    {
      label: role === 'Manager' ? 'Assigned Teams' : 'All Teams',
      value: metrics.totalAgents.toString(),
      sub: role === 'Manager'
        ? `${metrics.uniqueTeamCount} assigned teams`
        : `Across ${metrics.uniqueTeamCount} teams`,
      note: headcountNote,
      icon: <Users size={17} />,
      accent: 'border-l-blue-500',
      trendDelta: month !== 'All' && prevMonth && prevTotalAgents > 0
        ? ((metrics.totalAgents - prevTotalAgents) / prevTotalAgents) * 100
        : undefined,
      lowerTrendIsBetter: false,
      showStableTrend: true,
    },
    {
      label: 'Avg Performance Score',
      value: `${metrics.avgScore.toFixed(1)}%`,
      sub: 'All teams combined',
      icon: <TrendingUp size={17} />,
      accent: 'border-l-indigo-500',
      trendDelta: month !== 'All' && prevMonth && prevAvgScore !== 0 ? metrics.avgScore - prevAvgScore : undefined,
      lowerTrendIsBetter: false,
      showStableTrend: false,
    },
    {
      label: 'Class A & B (>=80%)',
      value: `${metrics.pctAB.toFixed(1)}%`,
      sub: `${metrics.classCounts.A + metrics.classCounts.B} agents meeting expectations`,
      icon: <Award size={17} />,
      accent: 'border-l-emerald-500',
      trendDelta: month !== 'All' && prevMonth && prevPctAB !== 0 ? metrics.pctAB - prevPctAB : undefined,
      lowerTrendIsBetter: false,
      showStableTrend: false,
    },
    {
      label: 'Class D & E (<70%)',
      value: `${metrics.pctDE.toFixed(1)}%`,
      sub: `${metrics.classCounts.D + metrics.classCounts.E} agents need attention`,
      icon: <AlertTriangle size={17} />,
      accent: 'border-l-red-500',
      trendDelta: month !== 'All' && prevMonth && prevPctDE !== 0 ? metrics.pctDE - prevPctDE : undefined,
      lowerTrendIsBetter: true,
      showStableTrend: false,
    },
  ] : [];

  return (
    <div className="max-w-[1600px] mx-auto space-y-6 text-slate-800 dark:text-slate-100">
      {/* Header */}
      {showBscFallbackMessage && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
          Balanced Scorecard is not configured for this context yet.
        </div>
      )}
      <TeamHeader
        displayName={displayName}
        month={month}
        uniqueMonths={dashboardMonths}
        setMonth={(m) => {
          setMonth(m);
          setPage(1);
        }}
        region={region}
        setRegion={(r) => {
          setRegion(r);
          setPage(1);
        }}
        location={location}
        setLocation={(l) => {
          setLocation(l);
          setPage(1);
        }}
        branchSelections={branchSelections}
        setBranchSelections={(next) => {
          setBranchSelections(next);
          setPage(1);
        }}
        multiBranchFilter={isMergedTeam && !isCallCenterParent}
        showPreApprovalsWorkflowFilter={isPreApprovalsParent || (isRcmParent && rcmDomain === 'pre_approvals' && rcmGroup !== 'offshore_egy')}
        preApprovalsWorkflow={preApprovalsWorkflow}
        setPreApprovalsWorkflow={handlePreApprovalsWorkflowChange}
        showCallCenterChannelFilter={isCallCenterParent}
        callCenterChannel={callCenterChannel}
        setCallCenterChannel={handleCallCenterChannelChange}
        showRcmDomainFilter={isRcmParent}
        rcmDomain={rcmDomain}
        setRcmDomain={handleRcmDomainChange}
        showRcmGroupFilter={isRcmParent}
        rcmGroup={rcmGroup}
        setRcmGroup={handleRcmGroupChange}
        onBack={() => navigate('/executive')}
        showRegionFilter={teamId === 'all'}
        performanceLevel={performanceLevel}
        setPerformanceLevel={(level) => {
          setPerformanceLevel(level);
          setPage(1);
        }}
        disabledPerformanceLevel={true}
      />

      {teamId === 'all' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {summaryCards.map((card) => (
            <KpiCard
              key={card.label}
              icon={card.icon}
              label={card.label}
              value={card.value}
              sub={card.sub}
              note={card.note}
              trendDelta={card.trendDelta}
              lowerTrendIsBetter={card.lowerTrendIsBetter}
              showStableTrend={card.showStableTrend}
              accent={card.accent}
            />
          ))}
        </div>
      )}

      {/* KPI Cards section */}
      {teamId !== 'all' && (
        isRcmParent && rcmGroup === 'all' && rcmDomain === 'all' ? (
          <RcmGroupSummary rows={rows} onGroupSelect={handleRcmGroupChange} />
        ) : isRcmParent && rcmDomain === 'all' ? (
          <RcmDomainSummary rows={rows} onDomainSelect={handleRcmDomainChange} />
        ) : isRcmParent && rcmDomain === 'pre_approvals' && preApprovalsWorkflow === 'all' && rcmGroup !== 'offshore_egy' ? (
          <PreApprovalsWorkflowSummary rows={rows} onWorkflowSelect={handlePreApprovalsWorkflowChange} />
        ) : isPreApprovalsParent && preApprovalsWorkflow === 'all' ? (
          <PreApprovalsWorkflowSummary rows={rows} onWorkflowSelect={handlePreApprovalsWorkflowChange} />
        ) : isCallCenterParent && callCenterChannel === 'all' ? (
          <CallCenterChannelSummary rows={rows} onChannelSelect={handleCallCenterChannelChange} />
        ) : (
          <TeamKpiSection
            totalAgents={metrics.totalAgents}
            avgScore={metrics.avgScore}
            pctAB={metrics.pctAB}
            pctDE={metrics.pctDE}
            classCounts={metrics.classCounts}
            isCallCenterView={isCallCenterView}
            isInbound={isInbound}
            teamMetrics={teamMetrics}
            prevTeamMetrics={prevTeamMetrics}
            avgAHTSec={teamMetrics.avgAHTSec}
            teamId={isRcmParent && workflowConfigTeam ? workflowConfigTeam.toLowerCase().replace(/[^a-z0-9]+/g, '-') : scoredTeamId}
            teamWeights={activeTeamWeights}
            headcountNote={headcountNote}
            prevAvgScore={calculatedPrevAvgScore}
            prevPctAB={prevPctAB}
            prevPctDE={prevPctDE}
            month={month}
            teamName={(isRcmParent && workflowConfigTeam ? workflowConfigTeam : teamName) ?? undefined}
          />
        )
      )}

      <Suspense
        fallback={
          <div
            className="grid grid-cols-1 gap-6 xl:grid-cols-2"
            aria-label="Loading performance charts"
          >
            <div className="h-[292px] animate-pulse rounded-xl bg-[var(--bg-sunken)]" />
            <div className="h-[292px] animate-pulse rounded-xl bg-[var(--bg-sunken)]" />
          </div>
        }
      >
        <TeamChartsSection pieData={pieData} trendData={trendData} />
      </Suspense>

      {/* Main Table / Roster Panel */}
      <TeamRosterSection
        showTopBottomToggle={teamId !== 'all'}
        rosterView={rosterView}
        setRosterView={setRosterView}
        search={search}
        setSearch={(s) => {
          setSearch(s);
          setPage(1);
        }}
        page={page}
        setPage={setPage}
        totalPages={totalPages}
        paginated={paginated}
        filtered={filtered}
        rosterData={rosterData}
        role={role || 'Viewer'}
        month={month}
        performanceLevel={performanceLevel}
        prevRows={prevRows}
        teamAverage={metrics.avgScore}
        getActionsForEmployee={getActionsForEmployee}
        onAddAction={(row) => setModalEmployee(row)}
        onEmployeeChanged={refreshPerformanceData}
        sortCol={sortCol}
        sortDir={sortDir}
        toggleSort={toggleSort}
        canExport={canExport}
        onExport={handleExport}
      />

      {/* Team Performance Summary & Action Needed Cards */}
      {teamId !== 'all' && (
        <div className={`mt-10 grid w-full grid-cols-1 gap-6 ${teamKpiAnalysis.length > 0 ? 'xl:grid-cols-1' : 'xl:grid-cols-2'}`}>
          {/* Card 1: Performance Summary */}
          {teamKpiAnalysis.length === 0 && <div className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-[0_12px_32px_rgba(15,23,42,0.06)] dark:border-slate-800 dark:bg-slate-950/95 dark:shadow-2xl">
            <div className="flex h-full flex-col">
              {/* Header Banner */}
              <div className="team-summary-header flex items-center justify-between border-b border-[var(--border-light)] px-6 py-4.5">
                <h3 className="flex items-center gap-2 text-base font-extrabold tracking-wide text-[var(--team-summary-header-text)]">
                  {getTeamIcon()}
                  {scoredTeamId === 'outbound' ? 'Call Center – Outbound' :
                    scoredTeamId === 'inbound' ? 'Call Center – Inbound' :
                      scoredTeamId === 'inbound-uae' ? 'Call Center – Inbound' :
                        displayName} – Performance Summary
                </h3>
              </div>

              {/* Body Content */}
              <div className="p-6 space-y-4 flex-1">
                <ul className="space-y-3.5 list-none pl-0 m-0">
                  {performanceBullets.map((bullet, idx) => {
                    const getIconConfig = (status: string) => {
                      switch (status) {
                        case 'success':
                          return {
                            bg: 'from-emerald-500 to-teal-500',
                            glow: 'shadow-[0_0_15px_rgba(16,185,129,0.35)]',
                            badge: 'bg-[var(--grade-a-bg)] text-[var(--grade-a-text)] border border-[var(--grade-a-border)]',
                            iconColor: 'text-white'
                          };
                        case 'warning':
                          return {
                            bg: 'from-amber-500 to-orange-500',
                            glow: 'shadow-[0_0_15px_rgba(245,158,11,0.35)]',
                            badge: 'bg-[var(--grade-c-bg)] text-[var(--grade-c-text)] border border-[var(--grade-c-border)]',
                            iconColor: 'text-white'
                          };
                        case 'danger':
                          return {
                            bg: 'from-rose-500 to-pink-500',
                            glow: 'shadow-[0_0_15px_rgba(244,63,94,0.35)]',
                            badge: 'bg-[var(--grade-e-bg)] text-[var(--grade-e-text)] border border-[var(--grade-e-border)]',
                            iconColor: 'text-white'
                          };
                        default:
                          return {
                            bg: 'from-blue-500 to-indigo-500',
                            glow: 'shadow-[0_0_15px_rgba(59,130,246,0.35)]',
                            badge: 'bg-[var(--grade-b-bg)] text-[var(--grade-b-text)] border border-[var(--grade-b-border)]',
                            iconColor: 'text-white'
                          };
                      }
                    };

                    const config = getIconConfig(bullet.status);
                    const BulletIcon = bullet.icon;

                    return (
                      <li
                        key={idx}
                        className="flex items-start gap-4.5 rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/45 p-4 transition-colors hover:border-blue-200 hover:bg-blue-50/40 dark:border-white/[0.05] dark:bg-white/[0.02] dark:hover:border-white/10 dark:hover:bg-white/[0.05]"
                      >
                        <div className={`p-2.5 rounded-xl shrink-0 mt-0.5 bg-gradient-to-br ${config.bg} ${config.glow} ${config.iconColor}`}>
                          <BulletIcon size={18} />
                        </div>
                        <div className="flex-1 space-y-1">
                          <div className="flex items-center gap-2.5 flex-wrap">
                            <span className="text-sm font-bold text-[var(--text-primary)] dark:text-slate-100">{bullet.title}</span>
                            {bullet.badgeText && (
                              <span className={`text-[9px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded-md ${config.badge}`}>
                                {bullet.badgeText}
                              </span>
                            )}
                          </div>
                          <p className="text-xs font-medium leading-relaxed text-[var(--text-secondary)] dark:text-slate-300">{bullet.desc}</p>
                        </div>
                      </li>
                    );
                  })}
                </ul>
                <TeamPerformanceAnalysis
                  insights={teamPerformanceInsights}
                  loading={teamInsightsQuery.isLoading && canViewTeamInsights}
                />
              </div>
            </div>
          </div>}

          {/* Card 2: Key Actions & Corrective Action Summary */}
          <div className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-[0_12px_32px_rgba(15,23,42,0.06)] dark:border-slate-800 dark:bg-slate-950/95 dark:shadow-2xl">
            <div className="flex h-full flex-col">
              {/* Header Banner */}
              <div className="team-summary-header flex items-center justify-between border-b border-[var(--border-light)] px-6 py-4.5">
                <h3 className="flex items-center gap-2 text-base font-extrabold tracking-wide text-[var(--team-summary-header-text)]">
                  <Lightbulb size={18} />
                  {scoredTeamId === 'outbound' ? 'Call Center – Outbound' :
                    scoredTeamId === 'inbound' ? 'Call Center – Inbound' :
                      scoredTeamId === 'inbound-uae' ? 'Call Center – Inbound' :
                        displayName} – Development & Actions
                </h3>
                {role === 'Admin' && !isEditingAction && (
                  <button
                    onClick={() => setIsEditingAction(true)}
                    className="team-summary-edit-button flex cursor-pointer items-center gap-1.5 rounded-lg border px-3.5 py-1.5 text-xs font-bold shadow-sm transition-all hover:shadow-md"
                  >
                    <Edit2 size={13} />
                    Edit Key Action
                  </button>
                )}
              </div>

              {/* Body Content */}
              <div className="p-6 space-y-5 flex-1 flex flex-col justify-between">
                <div className="space-y-4">
                  {/* Key Action bullet */}
                  <div className="flex items-start gap-4.5 rounded-xl border border-amber-500/20 bg-gradient-to-br from-amber-500/[0.08] to-orange-500/[0.08] p-4 shadow-[0_0_30px_rgba(245,158,11,0.05)] transition-all duration-300 dark:from-amber-500/[0.03] dark:to-orange-500/[0.03]">
                    <div className="p-2.5 rounded-xl bg-gradient-to-br from-amber-500 to-orange-500 shadow-[0_0_15px_rgba(245,158,11,0.4)] text-white shrink-0 mt-0.5">
                      <Lightbulb size={18} className="animate-pulse" />
                    </div>
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center justify-between gap-2.5">
                        <span className="text-sm font-bold uppercase tracking-wide text-amber-700 dark:text-amber-300">
                          Key Action Required
                        </span>
                        {!isEditingAction && (
                          <span className="animate-pulse rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wider text-amber-700 dark:text-amber-400">
                            HIGH PRIOR
                          </span>
                        )}
                      </div>
                      <div className="text-xs leading-relaxed text-[var(--text-secondary)] dark:text-slate-200">
                        {isEditingAction ? (
                          <div className="space-y-3.5 mt-2">
                            <textarea
                              value={actionInput}
                              onChange={(e) => setActionInput(e.target.value)}
                              placeholder="Specify the key action needed for this team..."
                              rows={3}
                              className="w-full rounded-xl border border-amber-500/30 bg-[var(--bg-surface)] px-4 py-3 text-xs font-semibold text-[var(--text-primary)] transition-all placeholder:text-[var(--text-faint)] focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-500/20 dark:bg-slate-950/90 dark:text-slate-100 dark:placeholder:text-slate-600"
                            />
                            <div className="flex justify-end gap-2.5">
                              <button
                                type="button"
                                onClick={() => {
                                  setIsEditingAction(false);
                                  setActionInput(teamAction);
                                }}
                                className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3.5 py-1.5 text-xs font-bold text-[var(--text-secondary)] transition-all hover:bg-[var(--bg-surface)] dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
                              >
                                <X size={13} />
                                Cancel
                              </button>
                              <button
                                type="button"
                                onClick={handleSaveTeamAction}
                                disabled={savingAction}
                                className="px-3.5 py-1.5 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-white text-xs font-extrabold rounded-lg border border-amber-500/20 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50 shadow-md shadow-amber-500/10"
                              >
                                <Check size={13} />
                                {savingAction ? 'Saving...' : 'Save'}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <p className="mt-1 font-semibold italic leading-relaxed text-[var(--text-secondary)] dark:text-slate-200">
                            "{teamAction || 'Under review by administration. Admin can click edit to add key action.'}"
                          </p>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Summary of Corrective Actions */}
                  <div className="space-y-3 border-t border-[var(--border-light)] pt-4 dark:border-white/10">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--text-secondary)] dark:text-slate-300">
                      Corrective Actions Summary for Agents ({teamActionsThisMonth.length})
                    </h4>
                    {teamActionsThisMonth.length === 0 ? (
                      <p className="text-xs italic text-[var(--text-muted)]">No corrective actions logged for this team's agents this month.</p>
                    ) : (
                      <div className="space-y-2.5 max-h-[220px] overflow-y-auto pr-1.5 custom-scrollbar">
                        {teamActionsThisMonth.map((act) => {
                          const ActIcon = getActionTypeIcon(act.action_type);
                          const actColor = getActionTypeColor(act.action_type);
                          return (
                            <div
                              key={act.id}
                              className="flex items-start gap-3 rounded-lg border border-transparent bg-[var(--bg-sunken)]/40 p-3 text-xs transition-colors hover:border-blue-100 hover:bg-blue-50/50 dark:border-white/[0.02] dark:bg-white/[0.01] dark:hover:border-white/5 dark:hover:bg-white/[0.03]"
                            >
                              <div className={`p-1.5 rounded-lg bg-gradient-to-br ${actColor} shrink-0 mt-0.5 shadow-xs`}>
                                <ActIcon size={12} />
                              </div>
                              <div className="flex-1 min-w-0 space-y-0.5">
                                <div className="flex items-center justify-between gap-2">
                                  <Link
                                    to={`/employee/${act.employee_id}?month=${encodeURIComponent(month)}&performance_level=${encodeURIComponent(performanceLevel)}`}
                                    className="truncate font-bold text-blue-600 hover:underline dark:text-blue-400"
                                  >
                                    {act.employee_name}
                                  </Link>
                                  <span className="text-[9px] font-bold uppercase text-[var(--text-muted)] dark:text-slate-400">
                                    {act.action_type}
                                  </span>
                                </div>
                                <p
                                  className="truncate font-semibold text-[var(--text-primary)] dark:text-slate-200"
                                  onMouseEnter={(e) => {
                                    const rect = e.currentTarget.getBoundingClientRect();
                                    setHoverTooltip({
                                      text: act.action_text,
                                      x: rect.left + rect.width / 2,
                                      y: rect.top - 8
                                    });
                                  }}
                                  onMouseLeave={() => setHoverTooltip(null)}
                                >
                                  {act.action_text}
                                </p>
                                {act.root_cause_note && (
                                  <p className="text-[11px] italic leading-relaxed text-[var(--text-muted)] dark:text-slate-400">
                                    "{act.root_cause_note}"
                                  </p>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {teamId !== 'all' && teamKpiAnalysis.length > 0 && (
        <TeamPerformanceIntelligence
          displayName={displayName}
          month={activeMonth}
          averageScore={metrics.avgScore}
          atRiskEmployees={metrics.classCounts.D + metrics.classCounts.E}
          kpis={teamKpiAnalysis}
        />
      )}

      {/* Action Modal */}
      {modalEmployee && (
        <EmployeeActionModal
          employee={modalEmployee}
          month={month === 'All' ? dashboardMonths[dashboardMonths.length - 1] || 'January' : month}
          teamWeights={weightsList.find((w) => matchesTeamConfig({ team: String(w.team || w.db_name || w.name || ''), weights: w.weights }, String(modalEmployee.team || '')))?.weights}
          onClose={() => setModalEmployee(null)}
        />
      )}

      {hoverTooltip && (
        <div
          className="fixed z-[9999] px-4 py-3 text-xs font-semibold text-white bg-slate-900/95 dark:bg-slate-800/95 border border-slate-700/50 rounded-xl shadow-xl backdrop-blur-sm pointer-events-none -translate-x-1/2 -translate-y-full transition-all duration-200 animate-in fade-in zoom-in-95 max-w-[320px] break-words text-left"
          style={{
            left: hoverTooltip.x,
            top: hoverTooltip.y,
          }}
        >
          {(() => {
            const separators = ['▸', '•', '>', '»'];
            const activeSeparator = separators.find(s => hoverTooltip.text.includes(s));
            if (activeSeparator) {
              const items = hoverTooltip.text
                .split(activeSeparator)
                .map(item => item.trim())
                .filter(item => item.length > 0);
              return (
                <ul className="space-y-1.5 list-disc pl-4 text-slate-100">
                  {items.map((item, idx) => (
                    <li key={idx} className="leading-relaxed">
                      {item}
                    </li>
                  ))}
                </ul>
              );
            }
            return <p className="leading-relaxed text-slate-100 text-center">{hoverTooltip.text}</p>;
          })()}
          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-0.5 border-4 border-transparent border-t-slate-900/95 dark:border-t-slate-800/95" />
        </div>
      )}
    </div>
  );
};

export default TeamDashboardView;
