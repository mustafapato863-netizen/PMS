/**
 * Composes existing endpoints only: /api/insights/workspace, /api/performance/summary-records,
 * /api/corrective-actions/follow-up and /api/corrective-actions/owners. No new API fields.
 * Every query key carries region + locked month; region switches drop the cache (see view).
 */
import { useQueries, useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';
import { insightsWorkspaceUrl } from '../../hooks/api/useInsightsWorkspace';
import type { InsightsWorkspace } from '../insights/types';
import { regionTeams, type DeckAction, type LockedPeriod, type RegionCode } from './model';

export const MP_QUERY_ROOT = 'monthly-presentation';
interface Envelope<T> { success: boolean; data: T; message?: string }

type RawAction = {
  id?: string; manager_action?: string; team?: string | null; region?: string | null; month?: string | null; year?: number | null;
  status?: string | null; priority?: string | null; due_date?: string | null; owner?: { name?: string } | null;
  linked_kpi_key?: string | null; completion_note?: string | null; employee_name?: string | null; created_by_name?: string | null;
};
type RawRecord = { team?: string | null; region?: string | null; month?: string | null; year?: number | null; employee_id?: string; employee_name?: string; identity?: Record<string, unknown>; evaluation?: { score?: number | null } | null; score?: number | null };

export function mapAction(item: RawAction, index: number): DeckAction {
  const text = String(item.manager_action ?? '');
  return {
    id: item.id ?? `action-${index}`,
    title: text.includes(': ') ? text.slice(text.indexOf(': ') + 2) : text || 'Untitled action',
    team: item.team ?? null, region: item.region ?? null, month: item.month ?? null, year: item.year ?? null,
    status: item.status ?? null, priority: item.priority ?? null, due_date: item.due_date ?? null,
    owner: item.owner?.name ?? null, linked_kpi_key: item.linked_kpi_key ?? null, completion_note: item.completion_note ?? null,
    people: [item.employee_name, item.created_by_name].filter((n): n is string => Boolean(n && n.trim())),
  };
}

export interface ScoreRow { team: string | null; region: string | null; month: string; year: number | null; name: string; score: number | null }
export function mapRecord(r: RawRecord): ScoreRow {
  const id = (r.identity ?? {}) as Record<string, unknown>;
  return {
    team: (r.team ?? (id.team as string) ?? null) || null,
    region: (r.region ?? (id.region as string) ?? null) || null,
    month: String(r.month ?? id.month ?? ''),
    year: r.year == null ? null : Number(r.year),
    name: String(r.employee_name ?? id.name ?? ''),
    score: r.evaluation?.score ?? r.score ?? null,
  };
}

export function useMonthlyPresentationData(code: RegionCode | null, period: LockedPeriod | null, enabled: boolean) {
  const on = Boolean(enabled && code && period);
  const base = [MP_QUERY_ROOT, code, period?.key] as const;
  const filters = { periodKey: period?.key, region: code ?? undefined };

  const workspace = useQuery({
    queryKey: [...base, 'workspace'],
    enabled: on,
    retry: false,
    queryFn: async ({ signal }) => (await apiFetch<Envelope<InsightsWorkspace>>(insightsWorkspaceUrl(filters), { signal })).data,
  });

  const teams = code ? regionTeams(code) : [];
  const teamDiagnosis = useQueries({
    queries: teams.map((team) => ({
      queryKey: [...base, 'team', team],
      enabled: on,
      retry: false,
      queryFn: async ({ signal }: { signal: AbortSignal }) => (await apiFetch<Envelope<InsightsWorkspace>>(
        insightsWorkspaceUrl({ ...filters, team }, 'full', ['kpi_diagnosis', 'team_summaries']), { signal })).data,
    })),
  });

  const followUp = useQuery({
    queryKey: [...base, 'follow-up'],
    enabled: on,
    retry: false,
    queryFn: async ({ signal }) => {
      const res = await apiFetch<Envelope<{ summary: Record<string, number>; actions: RawAction[] }>>(
        `/api/corrective-actions/follow-up?month=${encodeURIComponent(period!.monthName)}`, { signal });
      return (res?.data?.actions ?? []).map(mapAction);
    },
  });

  const owners = useQuery({
    queryKey: [...base, 'owners'],
    enabled: on,
    retry: false,
    queryFn: async ({ signal }) => (await apiFetch<Envelope<Array<{ id: string; name: string; role?: string }>>>('/api/corrective-actions/owners', { signal }))?.data ?? [],
  });

  const records = useQuery({
    queryKey: [...base, 'summary-records'],
    enabled: on,
    retry: false,
    queryFn: async ({ signal }) => ((await apiFetch<Envelope<RawRecord[]>>('/api/performance/summary-records', { signal }))?.data ?? []).map(mapRecord),
  });

  return {
    workspace, teamDiagnosis: teams.map((team, i) => ({ team, query: teamDiagnosis[i] })), followUp, owners, records,
    isLoading: workspace.isLoading,
  };
}
