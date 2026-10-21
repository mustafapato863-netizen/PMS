/**
 * Monthly Presentation: pure view-model rules (no React, no fetch).
 * Design: Figma csZO4wbWLnLOcHHmGUnQ0X page 65:2. Data decisions approved by Mustafa via CoS:
 *  1. Critical KPI = weight >= 0.25.  2. Ready rule v1 (below).  3. Expected impact = completion_note.
 *  4. Overdue is measured against the end of the selected month.  5. UAE leaves out Call Center for now.
 * Every number comes from existing endpoints; anything missing degrades to "not available".
 */
import { normalizeKpiDirection } from '../executive/format';
import { getGradeClassOrNull, type GradeClass } from '../../constants/grades';

export type RegionSlug = 'egy' | 'uae';
export type RegionCode = 'EGY' | 'UAE';
export const REGION_SLUGS: readonly RegionSlug[] = ['egy', 'uae'];
export const REGION_LABEL: Record<RegionCode, string> = { EGY: 'Egypt', UAE: 'UAE' };
export const SLIDE_COUNT = 11;
export const SLIDE_IDS = Array.from({ length: SLIDE_COUNT }, (_, i) => `s${String(i + 1).padStart(2, '0')}`);

export const regionCode = (slug: RegionSlug): RegionCode => (slug === 'uae' ? 'UAE' : 'EGY');
export const regionSlug = (code: RegionCode): RegionSlug => (code === 'UAE' ? 'uae' : 'egy');

export function parseRegion(value: string | null | undefined): RegionSlug | null {
  const v = String(value ?? '').trim().toLowerCase();
  return v === 'egy' || v === 'uae' ? v : null;
}

/* ── Region scope (Data-mapping check D). Never mixed. ── */
export interface DeckFunction { name: string; teams: string[] }
export const REGION_FUNCTIONS: Record<RegionCode, DeckFunction[]> = {
  EGY: [
    { name: 'RCM Offshore EGY', teams: ['Coding EGY', 'Submission EGY', 'Pre-Approvals IP Offshore', 'Resubmission'] },
    { name: 'Call Center', teams: ['Call Center'] },
  ],
  // Decision 5: UAE leaves out Call Center for now. IP Offshore is Egypt-only.
  UAE: [
    {
      name: 'RCM · Pre-Approvals',
      teams: ['Pre-Approvals OP Dubai', 'Pre-Approvals IP Final Dubai', 'Pre-Approvals IP Elective Dubai', 'Pre-Approvals OP Final SHJ AJM', 'Pre-Approvals IP Final SHJ AJM'],
    },
  ],
};
export const regionTeams = (code: RegionCode): string[] => REGION_FUNCTIONS[code].flatMap((f) => f.teams);
const fold = (v: unknown) => String(v ?? '').trim().toLowerCase();

/** True when a team belongs to the selected region's deck. Anything else is dropped (no cross-region numbers). */
export function isRegionTeam(code: RegionCode, team: string | null | undefined): boolean {
  const t = fold(team);
  return regionTeams(code).some((name) => fold(name) === t);
}

/** Keeps only rows of the selected region: region field must match when present, team must be in the deck. */
export function filterRegionRows<T extends { team?: string | null; region?: string | null }>(code: RegionCode, rows: T[]): T[] {
  return rows.filter((row) => (row.region ? fold(row.region) === fold(code) : true) && isRegionTeam(code, row.team));
}

/** Regions the user may open. Empty grants on an all-scope user = both; Regional Manager = only its grants. */
export function accessibleRegions(user: { role?: string | null; accessible_regions?: string[] | null } | null | undefined): RegionCode[] {
  const grants = (user?.accessible_regions ?? []).map((r) => String(r).trim().toUpperCase()).filter((r): r is RegionCode => r === 'EGY' || r === 'UAE');
  const unique = [...new Set(grants)];
  if (unique.length) return unique;
  if (user?.role === 'Regional Manager') return [];
  return ['EGY', 'UAE'];
}

/* ── Strict month lock ── */
export interface LockedPeriod { key: string; year: number; month: number; monthName: string; label: string; short: string; endDate: string }
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

export function periodFromKey(key: string | null | undefined): LockedPeriod | null {
  const m = /^(\d{4})-(\d{2})$/.exec(String(key ?? '').trim());
  if (!m) return null;
  const year = Number(m[1]);
  const month = Number(m[2]);
  if (month < 1 || month > 12 || year < 2000 || year > 2100) return null;
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const name = MONTHS[month - 1];
  return {
    key: `${m[1]}-${m[2]}`, year, month, monthName: name,
    label: `${name} ${year}`, short: name.slice(0, 3),
    endDate: `${m[1]}-${m[2]}-${String(last).padStart(2, '0')}`,
  };
}

/** Last complete month: a month opens on the 5th of the following month. */
export function lastCompleteMonth(today: Date): string {
  const back = today.getDate() >= 5 ? 1 : 2;
  const d = new Date(today.getFullYear(), today.getMonth() - back, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/** The date a month's data opens (5th of the following month), e.g. "5 Nov". */
export function opensOn(key: string): string {
  const p = periodFromKey(key);
  if (!p) return '';
  const d = new Date(p.year, p.month, 5);
  return `5 ${MONTHS[d.getMonth()].slice(0, 3)}`;
}

export const isMonthAvailable = (key: string, today: Date): boolean => key <= lastCompleteMonth(today);

export function shiftMonth(key: string, delta: number): string {
  const p = periodFromKey(key)!;
  const d = new Date(p.year, p.month - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/* ── URL params ── */
export interface DeckParams { region: RegionSlug | null; month: string | null; present: boolean; print: boolean; slide: number | null }

export function parseDeckParams(search: string, hash = ''): DeckParams {
  const p = new URLSearchParams(search);
  const anchor = /^#s(\d{2})$/.exec(hash);
  const slideNo = anchor ? Number(anchor[1]) : null;
  return {
    region: parseRegion(p.get('region')),
    month: periodFromKey(p.get('month'))?.key ?? null,
    present: p.get('mode') === 'present',
    print: p.get('print') === '1',
    slide: slideNo && slideNo >= 1 && slideNo <= SLIDE_COUNT ? slideNo : null,
  };
}

/** Canonical query: region and month always written; other params preserved. */
export function buildDeckSearch(current: string, next: Partial<{ region: RegionSlug; month: string; present: boolean; print: boolean }>): string {
  const p = new URLSearchParams(current);
  if (next.region) p.set('region', next.region);
  if (next.month) p.set('month', next.month);
  if (next.present !== undefined) { if (next.present) p.set('mode', 'present'); else p.delete('mode'); }
  if (next.print !== undefined) { if (next.print) p.set('print', '1'); else p.delete('print'); }
  return `?${p.toString()}`;
}

export const pdfFileName = (code: RegionCode, key: string) => `PMS_Monthly_${code}_${key}.pdf`;

/* ── Direction-aware tone ── */
export type Tone = 'good' | 'bad' | 'neutral';
/** Arrow shows raw movement; color depends on the KPI direction. Unknown direction stays grey. */
export function kpiMovementTone(delta: number | null | undefined, direction: string | null | undefined): Tone {
  if (delta === null || delta === undefined || !Number.isFinite(delta) || Math.abs(delta) < 0.05) return 'neutral';
  const d = normalizeKpiDirection(direction);
  if (!d) return 'neutral';
  const better = d === 'lower_better' ? delta < 0 : delta > 0;
  return better ? 'good' : 'bad';
}
export function movementArrow(delta: number | null | undefined): '▲' | '▼' | '→' {
  if (delta === null || delta === undefined || !Number.isFinite(delta) || Math.abs(delta) < 0.05) return '→';
  return delta > 0 ? '▲' : '▼';
}

/* ── KPI status: No data is its own badge, never a miss ── */
export type KpiBadge = 'on_track' | 'at_risk' | 'critical' | 'no_data';
export function kpiBadge(achievement: number | null | undefined, actual?: number | null): KpiBadge {
  if (actual === null || achievement === null || achievement === undefined || !Number.isFinite(achievement)) return 'no_data';
  if (achievement >= 100) return 'on_track';
  if (achievement >= 70) return 'at_risk';
  return 'critical';
}
export const isMiss = (badge: KpiBadge) => badge === 'at_risk' || badge === 'critical';

/* ── Ready rule v1 ── */
export interface ReadinessKpi { key: string; label: string; weight: number; actual: number | null; achievement_percent: number | null }
export type Readiness = 'ready' | 'partial' | 'not_ready' | 'no_data';
/** Weights may arrive as fractions (0.3) or percents (30). */
export const normalizedWeight = (w: number) => (w > 1 ? w / 100 : w);
export const isCriticalKpi = (k: Pick<ReadinessKpi, 'weight'>) => normalizedWeight(Number(k.weight) || 0) >= 0.25;

export function teamReadiness(kpis: ReadinessKpi[], openHighActions: number): { status: Readiness; critical: ReadinessKpi[]; worst: ReadinessKpi | null } {
  const critical = kpis.filter(isCriticalKpi);
  const badges = critical.map((k) => ({ k, b: kpiBadge(k.achievement_percent, k.actual) }));
  const worst = [...critical].filter((k) => k.achievement_percent != null).sort((a, b) => (a.achievement_percent! - b.achievement_percent!))[0] ?? null;
  if (!critical.length || badges.some((x) => x.b === 'no_data')) return { status: 'no_data', critical, worst };
  if (badges.some((x) => x.b === 'critical')) return { status: 'not_ready', critical, worst };
  if (badges.some((x) => x.b === 'at_risk') || openHighActions > 0) return { status: 'partial', critical, worst };
  return { status: 'ready', critical, worst };
}

/* ── Corrective actions ── */
export interface DeckAction {
  id: string; title: string; team: string | null; region?: string | null; month?: string | null; year?: number | null;
  status: string | null; priority: string | null; due_date: string | null; owner: string | null;
  linked_kpi_key: string | null; completion_note: string | null;
}
const CLOSED = new Set(['completed', 'cancelled']);
export const isOpenAction = (a: Pick<DeckAction, 'status'>) => a.status === 'Open' || a.status === 'In Progress';

/** Decision 4: overdue = due before the end of the selected month and not Completed/Cancelled. Never "today". */
export function isOverdueForPeriod(a: Pick<DeckAction, 'status' | 'due_date'>, periodEnd: string): boolean {
  if (!a.due_date || CLOSED.has(fold(a.status))) return false;
  return a.due_date.slice(0, 10) < periodEnd;
}

export function displayActionState(a: DeckAction, periodEnd: string): 'Overdue' | 'Completed' | 'Cancelled' | 'In progress' | 'Open' {
  if (isOverdueForPeriod(a, periodEnd)) return 'Overdue';
  if (a.status === 'Completed') return 'Completed';
  if (a.status === 'Cancelled') return 'Cancelled';
  if (a.status === 'In Progress') return 'In progress';
  return 'Open';
}

/** Actions of the locked period and the selected region only. */
export function periodRegionActions(actions: DeckAction[], code: RegionCode, period: LockedPeriod): DeckAction[] {
  return filterRegionRows(code, actions).filter((a) =>
    fold(a.month) === fold(period.monthName) && (a.year == null || Number(a.year) === period.year));
}

export const openHighCount = (actions: DeckAction[], team: string) =>
  actions.filter((a) => fold(a.team) === fold(team) && a.priority === 'High' && isOpenAction(a)).length;

/** Decision 3: expected impact = completion_note verbatim; empty → null ("No note" badge). */
export const expectedImpact = (a: Pick<DeckAction, 'completion_note'>) => {
  const note = String(a.completion_note ?? '').trim();
  return note ? note : null;
};

export function actionMix(actions: DeckAction[], periodEnd: string) {
  return {
    total: actions.length,
    open: actions.filter((a) => a.status === 'Open').length,
    in_progress: actions.filter((a) => a.status === 'In Progress').length,
    completed: actions.filter((a) => a.status === 'Completed').length,
    overdue: actions.filter((a) => isOverdueForPeriod(a, periodEnd)).length,
  };
}

/** Qualitative outlook from the status mix only (no projected score). */
export function outlookLine(mix: ReturnType<typeof actionMix>): string {
  if (!mix.total) return 'No actions are in flight, so no improvement is expected from actions.';
  const active = mix.open + mix.in_progress;
  if (!active) return 'All actions for the period are closed; no further movement is expected from actions.';
  if (mix.overdue) return `${active} action${active === 1 ? '' : 's'} still open, ${mix.overdue} overdue for the period: improvement depends on clearing the overdue items first.`;
  return `${active} action${active === 1 ? '' : 's'} in flight and none overdue for the period: improvement is expected as they complete.`;
}

/* ── Mask names ── */
export function nameMasker() {
  const map = new Map<string, string>();
  return (name: string | null | undefined): string => {
    const key = String(name ?? '').trim();
    if (!key) return '—';
    if (!map.has(key)) {
      const i = map.size;
      const letters = i < 26 ? String.fromCharCode(65 + i) : `${String.fromCharCode(65 + Math.floor(i / 26) - 1)}${String.fromCharCode(65 + (i % 26))}`;
      map.set(key, `Person ${letters}`);
    }
    return map.get(key)!;
  };
}

/* ── Draft / Final ── */
export type DeckStatus = 'Draft' | 'Final';
/** Reopening a Final deck as Draft is Admin-only. */
export const canReopenDraft = (role: string | null | undefined) => role === 'Admin';

/* ── Grade mix (employees, Partial teams excluded) ── */
export function gradeMix(scores: Array<{ team?: string | null; score: number | null }>, excludedTeams: string[]): Record<GradeClass, number> {
  const out: Record<GradeClass, number> = { A: 0, B: 0, C: 0, D: 0, E: 0 };
  const excluded = new Set(excludedTeams.map(fold));
  scores.forEach((s) => {
    if (excluded.has(fold(s.team))) return;
    const g = getGradeClassOrNull(s.score);
    if (g) out[g] += 1;
  });
  return out;
}

/** Region MoM: only when the API says the comparison is adjacent and like-for-like; otherwise not available. */
export function regionMoM(story: { score_change: number | null; basis_context?: { like_for_like: boolean } | null } | null | undefined, isAdjacent: boolean): number | null {
  if (!story || story.score_change == null || !Number.isFinite(story.score_change)) return null;
  if (!isAdjacent || story.basis_context?.like_for_like === false) return null;
  return story.score_change;
}
