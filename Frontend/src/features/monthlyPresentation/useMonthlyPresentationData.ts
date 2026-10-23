/**
 * Composes existing endpoints only: /api/insights/workspace, /api/corrective-actions/follow-up and
 * /api/corrective-actions/owners (summary-records is not called, see deckRequestUrls). No new API fields.
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
export const DECK_REQUEST_DEADLINE_MS = 15_000;
/**
 * Requests in flight per lane (per tab). Insights calls (region, overview, per-team) share one lane; follow-up
 * and owners have their own, so a slow Insights call can never hold up slides 8-10. At most 3 overall.
 */
export const DECK_LANES = { insights: 2, actions: 1 } as const;
export type DeckLane = keyof typeof DECK_LANES;
/** Kept for callers/tests: the Insights lane cap. */
export const DECK_MAX_CONCURRENT = DECK_LANES.insights;
/**
 * A queued request is never sent with less than this left of its deadline; it fails locally instead
 * (no fetch), so the queue cannot release a burst of requests that are aborted milliseconds later.
 */
export const DECK_MIN_START_MS = 2_000;
/**
 * Deadlock fallback only. A slot is held until the aborted request has actually settled; with abortBody the
 * fetch and its body read reject as soon as the abort lands, so this should never fire. If a broken fetch
 * implementation never settles, the slot is reclaimed after this long, by which point the browser has long
 * dropped the connection. It is 4x the request deadline, so it cannot overlap a live request's lifetime.
 */
export const DECK_SLOT_FALLBACK_MS = 60_000;

/**
 * Deck data is a locked past month: never refetch it on its own. One retry, but never after a timeout
 * (a timeout already used the whole 15 s budget), so an error shows after about 15 s at most.
 */
export const DECK_QUERY_OPTIONS = {
  retry: (failureCount: number, error: unknown) => failureCount < 1 && !(error instanceof DeckTimeoutError) && !isAbort(error),
  retryDelay: 1_000, staleTime: 30 * 60_000, gcTime: 30 * 60_000,
  refetchOnWindowFocus: false, refetchOnReconnect: false, refetchOnMount: false, refetchInterval: false,
} as const;
function isAbort(error: unknown) {
  return Boolean(error) && typeof error === 'object' && ['AbortError', 'TimeoutError'].includes(String((error as { name?: unknown }).name));
}

const lanes: Record<DeckLane, { active: number; waiting: Array<() => void> }> = {
  insights: { active: 0, waiting: [] }, actions: { active: 0, waiting: [] },
};
/**
 * FIFO semaphore per lane. A slot is freed only when the request itself settles (the abort now reaches the
 * body read, so an aborted request settles promptly); DECK_SLOT_FALLBACK_MS is a deadlock guard only.
 * A queued request whose signal aborts leaves the queue without running.
 */
export function limitDeckRequest<T>(
  signal: AbortSignal | undefined, run: () => Promise<T>, lane: DeckLane = 'insights', deadlineAt?: number,
): Promise<T> {
  const L = lanes[lane];
  return new Promise<T>((resolve, reject) => {
    const next = () => L.waiting.shift()?.();
    const start = () => {
      signal?.removeEventListener('abort', onQueuedAbort);
      // Expired or cancelled while queued: fail locally, keep the slot for the next one, never call fetch.
      if (signal?.aborted) { reject(signal.reason ?? new DOMException('Aborted', 'AbortError')); next(); return; }
      if (deadlineAt != null && deadlineAt - Date.now() < DECK_MIN_START_MS) {
        reject(new DeckTimeoutError(DECK_REQUEST_DEADLINE_MS)); next(); return;
      }
      L.active += 1;
      let freed = false; let fallback: ReturnType<typeof setTimeout> | undefined;
      const free = () => {
        if (freed) return; freed = true; clearTimeout(fallback);
        signal?.removeEventListener('abort', onRunningAbort);
        L.active -= 1; next();
      };
      const onRunningAbort = () => { fallback = setTimeout(free, DECK_SLOT_FALLBACK_MS); };
      signal?.addEventListener('abort', onRunningAbort, { once: true });
      let p: Promise<T>;
      try { p = run(); } catch (e) { p = Promise.reject(e); }
      p.then(resolve, reject).finally(free);
    };
    const onQueuedAbort = () => { const i = L.waiting.indexOf(start); if (i >= 0) L.waiting.splice(i, 1); reject(signal?.reason ?? new DOMException('Aborted', 'AbortError')); };
    if (signal?.aborted) { onQueuedAbort(); return; }
    if (L.active < DECK_LANES[lane]) start();
    else { L.waiting.push(start); signal?.addEventListener('abort', onQueuedAbort, { once: true }); }
  });
}
/** Test hooks. */
export function resetDeckLimiter() { for (const L of Object.values(lanes)) { L.active = 0; L.waiting.length = 0; } }
export function deckRequestsInFlight(lane: DeckLane = 'insights') { return { active: lanes[lane].active, queued: lanes[lane].waiting.length }; }

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
  let rejectCancel: (e: unknown) => void = () => {};
  const cancelled = new Promise<never>((_, reject) => { rejectCancel = reject; });
  const onAbort = () => { controller.abort(signal?.reason); rejectCancel(signal?.reason ?? new DOMException('Aborted', 'AbortError')); };
  if (signal?.aborted) onAbort(); else signal?.addEventListener('abort', onAbort, { once: true });
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => { const err = new DeckTimeoutError(ms); controller.abort(err); reject(err); }, ms);
  });
  cancelled.catch(() => {}); deadline.catch(() => {});
  return Promise.race([run(controller.signal), deadline, cancelled]).finally(() => {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  });
}
interface Envelope<T> { success: boolean; data: T; message?: string }

type RawAction = {
  id?: string; manager_action?: string; team?: string | null; region?: string | null; month?: string | null; year?: number | null;
  status?: string | null; priority?: string | null; due_date?: string | null; owner?: { id?: string; name?: string } | null;
  linked_kpi_key?: string | null; completion_note?: string | null; employee_name?: string | null; created_by_name?: string | null;
  employee_id?: string | null; suggested_action?: string | null; root_cause?: string | null; score?: number | null; grade?: string | null;
  plan?: { id?: string; name?: string } | null;
};
/**
 * Query strings for the deck requests, carrying only params the backend honours (Backend/api/routers):
 * follow-up reads `month` (no year/region), owners takes none. Region and year are filtered on the client.
 * /api/performance/summary-records is deliberately NOT called: it reads only `employee_id` and otherwise
 * returns every authorized scored record (unbounded).
 */
export function deckRequestUrls(_code: RegionCode, period: LockedPeriod) {
  return {
    followUp: `/api/corrective-actions/follow-up?${new URLSearchParams({ month: period.monthName })}`,
    owners: '/api/corrective-actions/owners',
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
    employee_id: item.employee_id ?? null,
    employee_name: item.employee_name ?? null,
    action_type: item.suggested_action?.trim() || (text.includes(': ') ? text.slice(0, text.indexOf(': ')).trim() : null) || null,
    root_cause: item.root_cause && item.root_cause.trim() && item.root_cause.trim() !== 'None' ? item.root_cause.trim() : null,
    score: typeof item.score === 'number' && Number.isFinite(item.score) ? item.score : null,
    grade: item.grade ?? null,
    plan_name: item.plan?.name ?? null,
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

// The 15 s deadline covers queueing + headers + body; its abort reaches the body read (abortBody) and the
// limiter slot frees when the request actually settles. Module-level so the clock is read only in queryFns.
function fetchWs(url: string, signal: AbortSignal | undefined) {
  const at = Date.now() + DECK_REQUEST_DEADLINE_MS;
  return withDeadline(signal, DECK_REQUEST_DEADLINE_MS, async (s) => {
    const res = await limitDeckRequest(s, () => apiFetch<Envelope<InsightsWorkspace>>(url, { signal: s }, { abortBody: true }), 'insights', at);
    const data = readEnvelope(res, url);
    if (!isObject(data)) throw new Error('Unexpected insights workspace response shape');
    return data;
  });
}
function get<T>(url: string, signal: AbortSignal | undefined) {
  const at = Date.now() + DECK_REQUEST_DEADLINE_MS;
  return withDeadline(signal, DECK_REQUEST_DEADLINE_MS,
    async (s) => readEnvelope<T>(await limitDeckRequest(s, () => apiFetch<Envelope<T>>(url, { signal: s }, { abortBody: true }), 'actions', at), url));
}

export function useMonthlyPresentationData(code: RegionCode | null, period: LockedPeriod | null, enabled: boolean) {
  const on = Boolean(enabled && code && period);
  const base = [MP_QUERY_ROOT, code, period?.key] as const;
  const urls = code && period ? deckRequestUrls(code, period) : null;
  const filters = { periodKey: period?.key, region: code ?? undefined };

  const workspace = useQuery({
    queryKey: [...base, 'workspace', DECK_WORKSPACE_SECTIONS.join(',')],
    enabled: on,
    ...DECK_QUERY_OPTIONS,
    queryFn: ({ signal }) => fetchWs(insightsWorkspaceUrl(filters, 'full', DECK_WORKSPACE_SECTIONS), signal),
  });

  const overview = useQuery({
    queryKey: [...base, 'workspace', 'kpi_overview'],
    enabled: on,
    ...DECK_QUERY_OPTIONS,
    queryFn: ({ signal }) => fetchWs(insightsWorkspaceUrl(filters, 'full', DECK_OVERVIEW_SECTIONS), signal),
  });

  const teams = code ? regionTeams(code) : [];
  const teamDiagnosis = useQueries({
    queries: teams.map((team) => ({
      queryKey: [...base, 'team', team],
      enabled: on,
      ...DECK_QUERY_OPTIONS,
      queryFn: ({ signal }: { signal: AbortSignal }) => fetchWs(insightsWorkspaceUrl({ ...filters, team }, 'full', TEAM_SECTIONS), signal),
    })),
  });

  const followUp = useQuery({
    queryKey: [...base, 'follow-up'],
    enabled: on,
    ...DECK_QUERY_OPTIONS,
    queryFn: async ({ signal }) => {
      const data = await get<{ summary?: Record<string, number>; actions?: RawAction[] }>(urls!.followUp, signal);
      if (!data || typeof data !== 'object' || !Array.isArray(data.actions)) throw new Error('Unexpected follow-up response shape');
      return data.actions.filter(isObject).map(mapAction);
    },
  });

  const owners = useQuery({
    queryKey: [MP_QUERY_ROOT, code, 'owners'],
    enabled: on,
    ...DECK_QUERY_OPTIONS,
    queryFn: async ({ signal }) => asArray<{ id: string; name: string; role?: string }>(await get<unknown>(urls!.owners, signal), 'owners')
      .filter((o) => typeof o?.id === 'string' && typeof o?.name === 'string'),
  });


  return {
    workspace, overview, teamDiagnosis: teams.map((team, i) => ({ team, query: teamDiagnosis[i] })), followUp, owners,
  };
}
