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
import { fetchFollowUp } from '../../hooks/useActionStore';
import { canAccessBroadAppPages, canAccessCorrectiveActions } from '../../lib/access';
import { canonicalTeamName } from '../../types';
import { teamBelongsToFunction, type TeamFunctionMap } from '../insights/filterCascade';
import type { InsightFilters } from '../insights/types';
import { composeExecutiveSummary, toExecRecords, type ExecRecord, type FollowUpAction } from './compose';
import { EXECUTIVE_FUNCTIONS, executiveFunctionForTeam } from './functions';
import type { ExecutiveFunction, ExecutiveSummary, ExecutiveView } from './types';

export interface ExecutiveFilterState {
  periodKey?: string;
  region?: string;
  teamFunction?: string;
  team?: string;
  performanceLevel?: string;
}

export interface ExecutiveOptions {
  regions: string[];
  functions: string[];
  teams: string[];
  levels: string[];
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
    status: action.status ?? null,
    follow_up_state: action.follow_up_state ?? null,
    completed_at: action.completed_at ?? null,
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
    teams: uniqueSorted(records.filter((record) => (!filters.region || record.region === filters.region) && inFunction(record.team)).map((record) => record.team)),
    levels: uniqueSorted(records.map((record) => record.level)),
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

  const performance = usePerformanceData('All', 'all', 'All', 'All', composeEnabled);
  const records = useMemo(() => (composeEnabled ? toExecRecords(performance.agents as never) : []), [composeEnabled, performance.agents]);

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
    filters: view === 'managerial' ? { performanceLevel: filters.performanceLevel } : {
      region: filters.region, teamFunction: view === 'function' ? undefined : filters.teamFunction, team: filters.team, performanceLevel: filters.performanceLevel,
    },
    requestedPeriodKey: filters.periodKey ?? null,
    team: managerTeam,
    functionName,
    accessibleFunctions,
    comparisonRecords: canAccessBroadAppPages(role) ? records : null,
    today: today ?? new Date(),
  }), [accessibleFunctions, filters, functionName, managerTeam, records, role, today, view]);

  const preliminary = useMemo(() => (composeEnabled && !performance.loading ? composeExecutiveSummary(baseInput) : null), [baseInput, composeEnabled, performance.loading]);
  const effectiveKey = preliminary?.period.effective?.key;

  const insightFilters: InsightFilters = useMemo(() => {
    if (view === 'managerial') return { periodKey: effectiveKey, team: managerTeam ?? undefined, performanceLevel: filters.performanceLevel };
    if (view === 'function') return { periodKey: effectiveKey, region: filters.region, teamFunction: functionName ?? undefined, team: filters.team, performanceLevel: filters.performanceLevel };
    return { periodKey: effectiveKey, region: filters.region, teamFunction: filters.teamFunction, team: filters.team, performanceLevel: filters.performanceLevel };
  }, [effectiveKey, filters, functionName, managerTeam, view]);
  const driversEnabled = composeEnabled && Boolean(effectiveKey) && DRIVER_ROLES.has(role);
  const workspace = useInsightsWorkspace(insightFilters, { enabled: driversEnabled });

  const actionsEnabled = composeEnabled && canAccessCorrectiveActions(role) && view !== 'function';
  const followUp = useQuery({
    queryKey: ['executive', 'follow-up'],
    queryFn: () => fetchFollowUp({}),
    enabled: actionsEnabled,
    retry: false,
  });

  const teamFunctions = workspace.data?.options?.team_functions as TeamFunctionMap | undefined;

  const composed = useMemo(() => {
    if (!preliminary) return null;
    const scopeAction = (action: FollowUpAction) => {
      const team = canonicalTeamName(action.team);
      if (view === 'managerial') return !managerTeam || team === managerTeam;
      if (filters.team && team !== canonicalTeamName(filters.team)) return false;
      if (filters.teamFunction && team && !teamBelongsToFunction(team, filters.teamFunction, teamFunctions)) return false;
      return true;
    };
    return composeExecutiveSummary({
      ...baseInput,
      teamFunctions,
      drivers: workspace.data ? { drivers: workspace.data.performance_drivers ?? [], items: [...(workspace.data.team_analyses ?? []), ...(workspace.data.priority_insights ?? []), ...(workspace.data.opportunities ?? [])] } : null,
      actions: followUp.data ? followUp.data.actions.map(toFollowUp).filter(scopeAction) : null,
    });
  }, [baseInput, filters.team, filters.teamFunction, followUp.data, managerTeam, preliminary, teamFunctions, view, workspace.data]);

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
    isLoading: enabled && (apiQuery.isLoading || (composeEnabled && (performance.loading || waitingSecondary))),
    error: composeEnabled && performance.dataSource === 'empty' && performance.errorMessage ? performance.errorMessage : null,
    source: composed ? 'composed' : null,
    managerTeam,
  };
}
