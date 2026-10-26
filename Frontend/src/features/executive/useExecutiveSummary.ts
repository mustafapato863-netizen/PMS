/**
 * Executive Summary data hook (`/executive`; the Function Summary shares it).
 *
 * The summary is composed in the browser from the performance summary records
 * (`/api/performance/summary-records`, server-side access scope). Drivers come
 * from the Insights workspace, corrective actions from the follow-up endpoint,
 * and Pending Sync from this device's unsynced action queue. Anything that
 * cannot be derived honestly is listed in `meta.unavailable` so widgets hide or
 * soften. No request is made to `/api/executive/summary`: that endpoint does
 * not exist.
 */
import { useCallback, useMemo, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';
import { performanceSessionKey } from '../../lib/performanceSessionKey';
import { usePerformanceData } from '../../hooks/usePerformanceData';
import { useAllTeamConfigs } from '../../hooks/useTeamConfig';
import { useInsightsWorkspace } from '../../hooks/api/useInsightsWorkspace';
import { fetchFollowUp, mapBackendAction } from '../../hooks/useActionStore';
import { canAccessBroadAppPages, canSeeSummaryActionAnalytics } from '../../lib/access';
import { canonicalTeamName, type PMSAction } from '../../types';
import { teamBelongsToFunction, type TeamFunctionMap } from '../insights/filterCascade';
import type { InsightFilters } from '../insights/types';
import { composeExecutiveSummary, monthsBetween, normalizeRegion, periodFromKey, previousRangeOf, SUMMARY_BRANCHES, SUMMARY_LEVELS, toExecRecords, type ExecRecord, type FollowUpAction } from './compose';
import { useSummaryRecords } from './useSummaryRecords';
import { EXECUTIVE_FUNCTIONS, summaryFunctionMatches, summaryTeamMatches } from './functions';
import type { ExecutiveFunction, ExecutiveSummary, ExecutiveView } from './types';

export interface ExecutiveFilterState {
  periodKey?: string;
  region?: string;
  branch?: string;
  teamFunction?: string;
  team?: string;
  position?: string;
  performanceLevel?: string;
}

export interface ExecutiveOptions {
  regions: string[];
  functions: string[];
  teams: string[];
  levels: string[];
  branches?: string[];
  roles?: string[];
  team_functions?: TeamFunctionMap;
}

export interface UseExecutiveSummaryArgs {
  view: ExecutiveView;
  role: string;
  filters: ExecutiveFilterState;
  /** Manager: their team(s) from /auth/me (`accessible_teams`). */
  managerTeams?: string[];
  /** Function view: the selected function. */
  functionName?: ExecutiveFunction | null;
  accessibleFunctions?: string[];
  /** Actions queued on this device (the page reads them from the action store). Only the unsynced ones count, as Pending Sync. */
  queuedActions?: PMSAction[] | null;
  /** Range mode: the first and last month (YYYY-MM), both inclusive. Null for a single month. */
  range?: { from: string; to: string } | null;
  enabled?: boolean;
  /** Injected for tests. */
  today?: Date;
}

export interface ExecutiveSummaryResult {
  summary: ExecutiveSummary | null;
  options: ExecutiveOptions;
  isLoading: boolean;
  error: string | null;
  source: 'api' | 'composed' | null;
  managerTeam: string | null;
  /** Manager: the assigned teams the team filter offers (empty for other views). */
  managerTeamOptions: string[];
}

interface ApiEnvelope<T> { success?: boolean; data: T; message?: string }

const DRIVER_ROLES = new Set(['Admin', 'General Manager', 'Manager', 'Executive']);
const uniqueSorted = (values: Array<string | null | undefined>) => [...new Set(values.filter((value): value is string => Boolean(value)))].sort((l, r) => l.localeCompare(r));

function toFollowUp(action: Awaited<ReturnType<typeof fetchFollowUp>>['actions'][number]): FollowUpAction {
  return {
    id: action.id,
    title: action.action_text || action.action_type,
    action_type: action.action_type,
    team: action.team || null,
    employee_name: action.employee_name || null,
    owner: action.owner ?? null,
    due_date: action.due_date ?? null,
    status: action.status ?? 'Open',
    follow_up_state: action.follow_up_state ?? null,
    completed_at: action.completed_at ?? null,
    employee_id: action.employee_id,
    month: action.month,
    created_at: action.created_at,
    root_cause_note: action.root_cause_note,
    linked_kpi_key: action.linked_kpi_key,
  };
}

/** An action queued on this device, on the same shape as the follow-up rows (analytics fields only). */
function queuedToFollowUp(action: PMSAction): FollowUpAction {
  return {
    id: action.id,
    title: action.action_text || action.action_type,
    action_type: action.action_type,
    team: action.team || null,
    employee_name: action.employee_name || null,
    employee_id: action.employee_id,
    month: action.month,
    created_at: action.created_at,
    root_cause_note: action.root_cause_note,
  };
}

export function buildExecutiveOptions(records: ExecRecord[], filters: ExecutiveFilterState, view: ExecutiveView, teamFunctions?: TeamFunctionMap, functionName?: string | null): ExecutiveOptions {
  const fn = view === 'function' ? functionName : filters.teamFunction;
  const inFunction = (team: string) => (!fn ? true : view === 'function'
    ? summaryFunctionMatches(team, fn, teamFunctions)
    : teamBelongsToFunction(team, fn, teamFunctions));
  return {
    regions: uniqueSorted(records.map((record) => record.region)),
    functions: [...EXECUTIVE_FUNCTIONS],
    teams: uniqueSorted(records.filter((record) => (!filters.region || record.region === filters.region) && (!filters.branch || record.branches?.includes(filters.branch)) && inFunction(record.team)).map((record) => record.team)),
    branches: SUMMARY_BRANCHES.map((branch) => branch.value),
    roles: uniqueSorted(records.filter((record) => (!filters.region || record.region === filters.region) && (!filters.branch || record.branches?.includes(filters.branch)) && inFunction(record.team) && (!filters.performanceLevel || record.level === filters.performanceLevel)).map((record) => record.position)),
    levels: [...SUMMARY_LEVELS],
    team_functions: teamFunctions,
  };
}

export function useExecutiveSummary({
  view, role, filters, managerTeams, functionName = null, accessibleFunctions, queuedActions = null, range = null, enabled = true, today,
}: UseExecutiveSummaryArgs): ExecutiveSummaryResult {
  // A new filters object with the same values must not recompose.
  const periodKey = filters.periodKey;
  const region = filters.region;
  const branch = filters.branch;
  const teamFunction = filters.teamFunction;
  const team = filters.team;
  const position = filters.position;
  const performanceLevel = filters.performanceLevel;
  const filterFields = useMemo<ExecutiveFilterState>(() => ({
    periodKey, region, branch, teamFunction, team, position, performanceLevel,
  }), [periodKey, region, branch, teamFunction, team, position, performanceLevel]);
  // The default clock is taken once per visit. An injected `today` still wins.
  const visitClock = useRef(new Date());
  const resolvedToday = today ?? visitClock.current;

  const summaryRecords = useSummaryRecords(enabled);
  const legacyEnabled = enabled && summaryRecords.isError;
  const performance = usePerformanceData('All', 'all', 'All', 'All', legacyEnabled);
  const records = useMemo(() => (enabled ? toExecRecords(summaryRecords.data ?? (legacyEnabled ? performance.agents as never : [])) : []), [enabled, legacyEnabled, performance.agents, summaryRecords.data]);
  const recordsLoading = enabled && (summaryRecords.isLoading || (legacyEnabled && performance.loading));
  const { data: teamConfigsList } = useAllTeamConfigs();

  // Manager: every assigned team (from /auth/me; the records are already scoped to them) is in scope.
  // The team filter narrows to one of them; an unassigned team in the URL is ignored.
  const managerTeamOptions = useMemo(() => {
    if (view !== 'managerial') return [] as string[];
    const assigned = uniqueSorted((managerTeams ?? []).map((team) => canonicalTeamName(team)));
    return assigned.length ? assigned : uniqueSorted(records.map((record) => record.team));
  }, [managerTeams, records, view]);
  const managerTeam = useMemo(() => {
    if (view !== 'managerial') return null;
    const requested = team ? canonicalTeamName(team) : '';
    if (requested && (!managerTeamOptions.length || managerTeamOptions.includes(requested))) return requested;
    return managerTeamOptions.length === 1 ? managerTeamOptions[0] : null;
  }, [team, managerTeamOptions, view]);

  // Range mode: the months averaged, and the range of the same length before them.
  const rangeFromKey = range?.from ?? '';
  const rangeToKey = range?.to ?? '';
  const rangeInput = useMemo(() => {
    const from = rangeFromKey ? periodFromKey(rangeFromKey) : null;
    const to = rangeToKey ? periodFromKey(rangeToKey) : null;
    if (!from || !to) return null;
    const months = monthsBetween(from, to);
    return months.length ? { months, previousMonths: previousRangeOf(months) } : null;
  }, [rangeFromKey, rangeToKey]);

  const baseInput = useMemo(() => ({
    view,
    role,
    records,
    filters: view === 'managerial' ? { branch, performanceLevel } : {
      region, branch, position, teamFunction: view === 'function' ? undefined : teamFunction, team, performanceLevel,
    },
    requestedPeriodKey: rangeInput ? null : (periodKey ?? null),
    range: rangeInput,
    team: managerTeam,
    teamScope: view === 'managerial' ? managerTeamOptions : null,
    functionName,
    accessibleFunctions,
    comparisonRecords: canAccessBroadAppPages(role) ? records : null,
    today: resolvedToday,
    teamConfigs: teamConfigsList,
  }), [accessibleFunctions, branch, functionName, managerTeam, managerTeamOptions, performanceLevel, periodKey, position, rangeInput, records, region, resolvedToday, role, team, teamConfigsList, teamFunction, view]);

  const preliminary = useMemo(() => (enabled && !recordsLoading ? composeExecutiveSummary(baseInput) : null), [baseInput, enabled, recordsLoading]);
  const effectiveKey = preliminary?.period.effective?.key;

  const insightFilters: InsightFilters = useMemo(() => {
    if (view === 'managerial') return { periodKey: effectiveKey, team: managerTeam ?? undefined, performanceLevel };
    if (view === 'function') return { periodKey: effectiveKey, region, teamFunction: functionName ?? undefined, team, performanceLevel };
    return { periodKey: effectiveKey, region, teamFunction, team, performanceLevel };
  }, [effectiveKey, functionName, managerTeam, performanceLevel, region, team, teamFunction, view]);
  // The Insights endpoint does not support branch or Marketing role scope yet.
  // Never display a wider cached driver result as if it matches either selection.
  // Range mode hides the Insights drivers: they are defined for one month, not for an average over several.
  const driversEnabled = enabled && !rangeInput && Boolean(effectiveKey) && DRIVER_ROLES.has(role) && !branch && !position;
  const workspace = useInsightsWorkspace(insightFilters, { enabled: driversEnabled });

  const actionsEnabled = enabled && canSeeSummaryActionAnalytics(role);
  const followUp = useQuery({
    queryKey: ['corrective-actions', 'executive', 'follow-up', performanceSessionKey()],
    queryFn: async () => {
      // Existing employee actions without due dates remain visible in the summary.
      // Follow-up also supplies tracked plan/team actions and current due metadata.
      const [tracked, collection] = await Promise.all([
        fetchFollowUp({}).catch(() => null),
        apiFetch<ApiEnvelope<Array<Parameters<typeof mapBackendAction>[0]>>>('/api/corrective-actions/')
          .then((response) => {
            if (response.success === false || !Array.isArray(response.data)) throw new Error('Action collection unavailable.');
            return response.data.map(mapBackendAction);
          }).catch(() => null),
      ]);
      if (!tracked && !collection) throw new Error('Corrective actions could not be loaded.');
      const actions = new Map((collection ?? []).map((action) => [action.id, action]));
      for (const action of tracked?.actions ?? []) {
        const existing = actions.get(action.id);
        actions.set(action.id, {
          ...existing,
          ...action,
          root_cause_note: action.root_cause_note || existing?.root_cause_note || '',
          linked_kpi_key: action.linked_kpi_key || existing?.linked_kpi_key,
          created_at: action.created_at || existing?.created_at || '',
          month: action.month || existing?.month || '',
        });
      }
      return { actions: [...actions.values()] };
    },
    enabled: actionsEnabled,
    retry: false,
  });
  const teamFunctions = workspace.data?.options?.team_functions as TeamFunctionMap | undefined;

  // One scope rule for every action list: the follow-up rows and the Pending Sync queue.
  const scopeAction = useCallback((action: FollowUpAction) => {
    const actionTeam = canonicalTeamName(action.team);
    if (view === 'managerial' && !managerTeamOptions.some((allowed) => summaryTeamMatches(actionTeam, allowed))) return false;
    if (view === 'managerial' && managerTeam && !summaryTeamMatches(actionTeam, managerTeam)) return false;
    // Managerial scope is the team filter above (the URL team is validated there), so the raw URL team does not apply again.
    if (view !== 'managerial' && team && !summaryTeamMatches(actionTeam, team)) return false;
    if (view === 'function' && functionName && !summaryFunctionMatches(actionTeam, functionName, teamFunctions)) return false;
    if (teamFunction && actionTeam && !teamBelongsToFunction(actionTeam, teamFunction, teamFunctions)) return false;
    if (region || branch || performanceLevel || position) {
      const matches = records.filter((record) => action.employee_id ? record.employeeId === action.employee_id : record.team === actionTeam);
      if (!matches.some((record) => (!normalizeRegion(region) || normalizeRegion(record.region) === normalizeRegion(region))
        && (!branch || record.branches?.includes(branch))
        && (!performanceLevel || record.level === performanceLevel)
        && (!position || record.position === position))) return false;
    }
    return true;
  }, [branch, functionName, managerTeam, managerTeamOptions, performanceLevel, position, records, region, team, teamFunction, teamFunctions, view]);

  // Pending Sync: unsynced actions on this device, in the same page scope. Counted only; never added to the totals.
  const pendingActions = useMemo(() => (actionsEnabled && queuedActions
    ? queuedActions.filter((action) => !action.synced).map(queuedToFollowUp).filter(scopeAction)
    : null), [actionsEnabled, queuedActions, scopeAction]);

  const composed = useMemo(() => {
    if (!preliminary) return null;
    return composeExecutiveSummary({
      ...baseInput,
      teamFunctions,
      deriveScopedDrivers: DRIVER_ROLES.has(role) && Boolean(branch || position),
      drivers: driversEnabled && workspace.data ? { drivers: workspace.data.performance_drivers ?? [], items: [...(workspace.data.team_analyses ?? []), ...(workspace.data.priority_insights ?? []), ...(workspace.data.opportunities ?? [])] } : null,
      actions: followUp.data ? followUp.data.actions.map(toFollowUp).filter(scopeAction) : null,
      pendingActions,
    });
  }, [baseInput, branch, driversEnabled, followUp.data, pendingActions, position, preliminary, role, scopeAction, teamFunctions, workspace.data]);

  const options = useMemo(() => buildExecutiveOptions(records, filterFields, view, teamFunctions, functionName), [filterFields, functionName, records, teamFunctions, view]);

  const waitingSecondary = (driversEnabled && workspace.isLoading) || (actionsEnabled && followUp.isLoading);
  return {
    summary: composed,
    options,
    isLoading: enabled && (recordsLoading || waitingSecondary),
    error: enabled && performance.dataSource === 'empty' && performance.errorMessage ? performance.errorMessage : null,
    source: composed ? 'composed' : null,
    managerTeam,
    managerTeamOptions,
  };
}
