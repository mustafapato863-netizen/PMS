/**
 * Composes existing endpoints only: /api/insights/workspace, /api/performance/summary-records,
 * /api/corrective-actions/follow-up and /api/corrective-actions/owners. No new API fields.
 * Every query key carries region + locked month; region switches drop the cache (see view).
 */
import { useQueries, useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';
import { insightsWorkspaceUrl, type InsightSection } from '../../hooks/api/useInsightsWorkspace';
import type { InsightsWorkspace } from '../insights/types';
import { regionTeams, type DeckAction, type LockedPeriod, type RegionCode } from './model';

export const MP_QUERY_ROOT = 'monthly-presentation';

/**
 * The region workspace sections the deck renders. Naming them is what keeps the request on the backend's
 * period-window path (Backend/services/insights_service.py PERIOD_WINDOW_SECTIONS). Without `sections` the
 * backend resolves every stored record and computes all 20 sections, which is what hung the deck in production.
 * `kpi_overview` reads every period, so it is fetched on its own request and only slide 3 waits for it.
 */
export const DECK_WORKSPACE_SECTIONS: readonly InsightSection[] = [
  'summary', 'executive_story', 'comparison', 'kpi_diagnosis', 'performance_drivers', 'people_contribution_analysis', 'team_summaries',
];
export const DECK_OVERVIEW_SECTIONS: readonly InsightSection[] = ['kpi_overview'];
export const TEAM_SECTIONS: readonly InsightSection[] = ['kpi_diagnosis', 'team_summaries'];

/** Upper bound for one deck request, response body included. A slide never waits longer than this. */
export const DECK_REQUEST_DEADLINE_MS = 45_000;

export class DeckTimeoutError extends Error {
  constructor(ms: number) { super(`The request did not finish within ${Math.round(ms / 1000)} s`); this.name = 'DeckTimeoutError'; }
}

/**
 * Runs `run` with a signal that aborts when TanStack cancels or the deadline passes, and rejects at the
 * deadline even if the underlying promise ignores the signal (apiClient's own timeout stops at the headers,
 * not the body). A query can therefore only end in success or error, never stay pending.
 */
export function withDeadline<T>(signal: AbortSignal | undefined, ms: number, run: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController();
  const onAbort = () => controller.abort(signal?.reason);
  if (signal?.aborted) controller.abort(signal.reason); else signal?.addEventListener('abort', onAbort, { once: true });
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => { const err = new DeckTimeoutError(ms); controller.abort(err); reject(err); }, ms);
  });
  return Promise.race([run(controller.signal), deadline]).finally(() => {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  });
}
interface Envelope<T> { success: boolean; data: T; message?: string }

type RawAction = {
  id?: string; manager_action?: string; team?: string | null; region?: string | null; month?: string | null; year?: number | null;
  status?: string | null; priority?: string | null; due_date?: string | null; owner?: { id?: string; name?: string } | null;
  linked_kpi_key?: string | null; completion_note?: string | null; employee_name?: string | null; created_by_name?: string | null;
};
/**
 * Query strings for the deck requests. Every request carries the locked period (spec §3).
 * Backend reality (checked in Backend/api/routers): follow-up honours `month` only (year ignored);
 * summary-records honours only `employee_id`; owners takes no params. Ignored params are harmless,
 * and the client keeps filtering by region, month and year.
 */
export function deckRequestUrls(code: RegionCode, period: LockedPeriod) {
  const p = (extra: Record<string, string> = {}) => new URLSearchParams({ month: period.monthName, year: String(period.year), ...extra }).toString();
  return {
    followUp: `/api/corrective-actions/follow-up?${p()}`,
    summaryRecords: `/api/performance/summary-records?${p({ region: code })}`,
    owners: `/api/corrective-actions/owners?${p()}`,
  };
}

type RawRecord = { team?: string | null; region?: string | null; month?: string | null; year?: number | null; employee_id?: string; employee_name?: string; identity?: Record<string, unknown>; evaluation?: { score?: number | null } | null; score?: number | null };

const isObject = (v: unknown): v is Record<string, never> => Boolean(v) && typeof v === 'object' && !Array.isArray(v);

/**
 * Envelope guard. The corrective-actions routes answer HTTP 200 with `{ success: false }` on a server error
 * (Backend/api/routers/users_and_actions.py), which used to read as "no actions". It is an error here.
 */
export function readEnvelope<T>(res: Envelope<T> | null | undefined, url: string): T {
  if (!isObject(res) || typeof (res as Envelope<T>).success !== 'boolean') throw new Error(`Unexpected response from ${url.split('?')[0]}`);
  if (!res.success) throw new Error(res.message || `Request failed: ${url.split('?')[0]}`);
  return res.data;
}
export function asArray<T>(value: unknown, label: string): T[] {
  if (!Array.isArray(value)) throw new Error(`Unexpected ${label} response shape`);
  return value as T[];
}

export function mapAction(item: RawAction, index: number): DeckAction {
  const text = String(item.manager_action ?? '');
  return {
    id: item.id ?? `action-${index}`,
    title: text.includes(': ') ? text.slice(text.indexOf(': ') + 2) : text || 'Untitled action',
    team: item.team ?? null, region: item.region ?? null, month: item.month ?? null, year: item.year ?? null,
    status: item.status ?? null, priority: item.priority ?? null, due_date: item.due_date ?? null,
    owner: item.owner?.name ?? null, linked_kpi_key: item.linked_kpi_key ?? null, completion_note: item.completion_note ?? null,
    owner_id: item.owner?.id ?? null,
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
  const urls = code && period ? deckRequestUrls(code, period) : null;
  const filters = { periodKey: period?.key, region: code ?? undefined };

  const fetchWs = (url: string, signal: AbortSignal | undefined) => withDeadline(signal, DECK_REQUEST_DEADLINE_MS,
    async (s) => {
      const data = readEnvelope(await apiFetch<Envelope<InsightsWorkspace>>(url, { signal: s }), url);
      if (!isObject(data)) throw new Error('Unexpected insights workspace response shape');
      return data;
    });
  const get = <T,>(url: string, signal: AbortSignal | undefined) => withDeadline(signal, DECK_REQUEST_DEADLINE_MS, async (s) => readEnvelope<T>(await apiFetch<Envelope<T>>(url, { signal: s }), url));

  const workspace = useQuery({
    queryKey: [...base, 'workspace', DECK_WORKSPACE_SECTIONS.join(',')],
    enabled: on,
    retry: false,
    queryFn: ({ signal }) => fetchWs(insightsWorkspaceUrl(filters, 'full', DECK_WORKSPACE_SECTIONS), signal),
  });

  const overview = useQuery({
    queryKey: [...base, 'workspace', 'kpi_overview'],
    enabled: on,
    retry: false,
    queryFn: ({ signal }) => fetchWs(insightsWorkspaceUrl(filters, 'full', DECK_OVERVIEW_SECTIONS), signal),
  });

  const teams = code ? regionTeams(code) : [];
  const teamDiagnosis = useQueries({
    queries: teams.map((team) => ({
      queryKey: [...base, 'team', team],
      enabled: on,
      retry: false,
      queryFn: ({ signal }: { signal: AbortSignal }) => fetchWs(insightsWorkspaceUrl({ ...filters, team }, 'full', TEAM_SECTIONS), signal),
    })),
  });

  const followUp = useQuery({
    queryKey: [...base, 'follow-up'],
    enabled: on,
    retry: false,
    queryFn: async ({ signal }) => {
      const data = await get<{ summary?: Record<string, number>; actions?: RawAction[] }>(urls!.followUp, signal);
      if (!data || typeof data !== 'object' || !Array.isArray(data.actions)) throw new Error('Unexpected follow-up response shape');
      return data.actions.filter(isObject).map(mapAction);
    },
  });

  const owners = useQuery({
    queryKey: [...base, 'owners'],
    enabled: on,
    retry: false,
    queryFn: async ({ signal }) => asArray<{ id: string; name: string; role?: string }>(await get<unknown>(urls!.owners, signal), 'owners')
      .filter((o) => typeof o?.id === 'string' && typeof o?.name === 'string'),
  });

  const records = useQuery({
    queryKey: [...base, 'summary-records'],
    enabled: on,
    retry: false,
    queryFn: async ({ signal }) => asArray<RawRecord>(await get<unknown>(urls!.summaryRecords, signal), 'summary records').filter(isObject).map(mapRecord),
  });

  return {
    workspace, overview, teamDiagnosis: teams.map((team, i) => ({ team, query: teamDiagnosis[i] })), followUp, owners, records,
  };
}
