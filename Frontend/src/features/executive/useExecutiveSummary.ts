/**
 * Executive / Function Summary data hook.
 *
 * 1. Asks `GET /api/executive/summary` (API_NEEDS.md). When that endpoint
 *    answers, its payload is used as-is.
 * 2. Until it exists (404 / error) the same shape is composed client-side:
 *    scores, functions, regions, teams, grades and KPIs from performance
 *    records; drivers from the Insights workspace; corrective actions from
 *    the follow-up endpoint. Anything that cannot be derived honestly is
 *    listed in `meta.unavailable` so widgets hide or soften.
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';
import { usePerformanceData } from '../../hooks/usePerformanceData';
import { useInsightsWorkspace } from '../../hooks/api/useInsightsWorkspace';
import { fetchFollowUp, mapBackendAction } from '../../hooks/useActionStore';
import { canAccessBroadAppPages, canAccessCorrectiveActions } from '../../lib/access';
import { canonicalTeamName } from '../../types';
import { teamBelongsToFunction, type TeamFunctionMap } from '../insights/filterCascade';
import type { InsightFilters } from '../insights/types';
import { composeExecutiveSummary, SUMMARY_BRANCHES, SUMMARY_LEVELS, toExecRecords, type ExecRecord, type FollowUpAction } from './compose';
import { useSummaryRecords } from './useSummaryRecords';
import { EXECUTIVE_FUNCTIONS, executiveFunctionForTeam } from './functions';
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
}

interface ApiEnvelope<T> { success?: boolean; data: T; message?: string }

export function executiveSummaryUrl(view: ExecutiveView, filters: ExecutiveFilterState, functionName?: string | null) {
  const params = new URLSearchParams();
  params.set('view', view);
  if (filters.periodKey) {
    const [year, month] = filters.periodKey.split('-');
    params.set('year', year);
    params.set('month', String(Number(month)));
  }
  if (filters.region) params.set('region', filters.region);
  if (filters.branch) params.set('branch', filters.branch);
  if (filters.position) params.set('position', filters.position);
  const fn = functionName ?? filters.teamFunction;
  if (fn) params.set('function', fn);
  if (filters.team) params.set('team', filters.team);
  if (filters.performanceLevel) params.set('performance_level', filters.performanceLevel);
  return `/api/executive/summary?${params.toString()}`;
}

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

export function buildExecutiveOptions(records: ExecRecord[], filters: ExecutiveFilterState, view: ExecutiveView, teamFunctions?: TeamFunctionMap, functionName?: string | null): ExecutiveOptions {
  const fn = view === 'function' ? functionName : filters.teamFunction;
  const inFunction = (team: string) => (!fn ? true : view === 'function'
    ? executiveFunctionForTeam(team, teamFunctions) === fn
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
  view, role, filters, managerTeams, functionName = null, accessibleFunctions, enabled = true, today,
}: UseExecutiveSummaryArgs): ExecutiveSummaryResult {
  const apiQuery = useQuery({
    queryKey: ['executive', 'summary', view, filters, functionName],
    queryFn: async ({ signal }) => {
      const payload = await apiFetch<ApiEnvelope<ExecutiveSummary & { options?: ExecutiveOptions }>>(executiveSummaryUrl(view, filters, functionName), { signal });
      if (!payload?.data?.hero) throw new Error('Executive summary payload missing.');
      return payload.data;
    },
    retry: false,
    staleTime: 5 * 60_000,
    enabled,
  });
  const composeEnabled = enabled && apiQuery.isError;

  const summaryRecords = useSummaryRecords(composeEnabled);
  const legacyEnabled = composeEnabled && summaryRecords.isError;
  const performance = usePerformanceData('All', 'all', 'All', 'All', legacyEnabled);
  const records = useMemo(() => (composeEnabled ? toExecRecords(summaryRecords.data ?? (legacyEnabled ? performance.agents as never : [])) : []), [composeEnabled, legacyEnabled, performance.agents, summaryRecords.data]);
  const recordsLoading = composeEnabled && (summaryRecords.isLoading || (legacyEnabled && performance.loading));

  // Manager: the backend already scopes records to their teams; prefer /auth/me.
  const managerTeam = useMemo(() => {
    if (view !== 'managerial') return null;
    const assigned = (managerTeams ?? []).map((team) => canonicalTeamName(team)).filter(Boolean);
    if (filters.team && (!assigned.length || assigned.includes(canonicalTeamName(filters.team)))) return canonicalTeamName(filters.team);
    return assigned[0] ?? uniqueSorted(records.map((record) => record.team))[0] ?? null;
  }, [filters.team, managerTeams, records, view]);

  const baseInput = useMemo(() => ({
    view,
    role,
    records,
    filters: view === 'managerial' ? { branch: filters.branch, performanceLevel: filters.performanceLevel } : {
      region: filters.region, branch: filters.branch, position: filters.position, teamFunction: view === 'function' ? undefined : filters.teamFunction, team: filters.team, performanceLevel: filters.performanceLevel,
    },
    requestedPeriodKey: filters.periodKey ?? null,
    team: managerTeam,
    functionName,
    accessibleFunctions,
    comparisonRecords: canAccessBroadAppPages(role) ? records : null,
    today: today ?? new Date(),
  }), [accessibleFunctions, filters, functionName, managerTeam, records, role, today, view]);

  const preliminary = useMemo(() => (composeEnabled && !recordsLoading ? composeExecutiveSummary(baseInput) : null), [baseInput, composeEnabled, recordsLoading]);
  const effectiveKey = preliminary?.period.effective?.key;

  const insightFilters: InsightFilters = useMemo(() => {
    if (view === 'managerial') return { periodKey: effectiveKey, team: managerTeam ?? undefined, performanceLevel: filters.performanceLevel };
    if (view === 'function') return { periodKey: effectiveKey, region: filters.region, teamFunction: functionName ?? undefined, team: filters.team, performanceLevel: filters.performanceLevel };
    return { periodKey: effectiveKey, region: filters.region, teamFunction: filters.teamFunction, team: filters.team, performanceLevel: filters.performanceLevel };
  }, [effectiveKey, filters, functionName, managerTeam, view]);
  // The Insights endpoint does not support branch or Marketing role scope yet.
  // Never display a wider cached driver result as if it matches either selection.
  const driversEnabled = composeEnabled && Boolean(effectiveKey) && DRIVER_ROLES.has(role) && !filters.branch && !filters.position;
  const workspace = useInsightsWorkspace(insightFilters, { enabled: driversEnabled });

  const actionsEnabled = composeEnabled && canAccessCorrectiveActions(role);
  const followUp = useQuery({
    queryKey: ['corrective-actions', 'executive', 'follow-up'],
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

  const composed = useMemo(() => {
    if (!preliminary) return null;
    const scopeAction = (action: FollowUpAction) => {
      const team = canonicalTeamName(action.team);
      if (view === 'managerial' && managerTeam && team !== managerTeam) return false;
      if (filters.team && team !== canonicalTeamName(filters.team)) return false;
      if (view === 'function' && functionName && executiveFunctionForTeam(team, teamFunctions) !== functionName) return false;
      if (filters.teamFunction && team && !teamBelongsToFunction(team, filters.teamFunction, teamFunctions)) return false;
      if (filters.region || filters.branch || filters.performanceLevel || filters.position) {
        const matches = records.filter((record) => action.employee_id ? record.employeeId === action.employee_id : record.team === team);
        if (!matches.some((record) => (!filters.region || record.region === filters.region)
          && (!filters.branch || record.branches?.includes(filters.branch))
          && (!filters.performanceLevel || record.level === filters.performanceLevel)
          && (!filters.position || record.position === filters.position))) return false;
      }
      return true;
    };
    return composeExecutiveSummary({
      ...baseInput,
      teamFunctions,
      deriveScopedDrivers: DRIVER_ROLES.has(role) && Boolean(filters.branch || filters.position),
      drivers: driversEnabled && workspace.data ? { drivers: workspace.data.performance_drivers ?? [], items: [...(workspace.data.team_analyses ?? []), ...(workspace.data.priority_insights ?? []), ...(workspace.data.opportunities ?? [])] } : null,
      actions: followUp.data ? followUp.data.actions.map(toFollowUp).filter(scopeAction) : null,
    });
  }, [baseInput, driversEnabled, filters, functionName, followUp.data, managerTeam, preliminary, records, role, teamFunctions, view, workspace.data]);

  const options = useMemo(() => (
    apiQuery.data?.options ?? buildExecutiveOptions(records, filters, view, teamFunctions, functionName)
  ), [apiQuery.data, filters, functionName, records, teamFunctions, view]);

  if (apiQuery.data) {
    return { summary: apiQuery.data, options, isLoading: false, error: null, source: 'api', managerTeam: apiQuery.data.scope?.team ?? managerTeam };
  }
  const waitingSecondary = (driversEnabled && workspace.isLoading) || (actionsEnabled && followUp.isLoading);
  return {
    summary: composed,
    options,
    isLoading: enabled && (apiQuery.isLoading || recordsLoading || waitingSecondary),
    error: composeEnabled && performance.dataSource === 'empty' && performance.errorMessage ? performance.errorMessage : null,
    source: composed ? 'composed' : null,
    managerTeam,
  };
}
