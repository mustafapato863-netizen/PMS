/**
 * Monthly Performance Review: period lock, region access, and export helpers.
 * The page is one region and one month. A month opens on the 5th of the next month.
 */
import type { GradeClass } from '../../constants/grades';
import { isExecutiveFunction } from '../executive/functions';

export type RegionSlug = 'egy' | 'uae';
export type RegionCode = 'EGY' | 'UAE';
export const REGION_SLUGS: readonly RegionSlug[] = ['egy', 'uae'];
export const REGION_LABEL: Record<RegionCode, string> = { EGY: 'Egypt', UAE: 'UAE' };

/** Results, Problems, Recognition, Decisions, Month Close. */
export const SECTION_COUNT = 5;

export const regionCode = (slug: RegionSlug): RegionCode => (slug === 'uae' ? 'UAE' : 'EGY');
export const regionSlug = (code: RegionCode): RegionSlug => (code === 'UAE' ? 'uae' : 'egy');

export function parseRegion(value: string | null | undefined): RegionSlug | null {
  const v = String(value ?? '').trim().toLowerCase();
  return v === 'egy' || v === 'uae' ? v : null;
}

/** Regions the user may open. Empty grants on an all-scope user = both; Regional Manager = only its grants. */
export function accessibleRegions(user: { role?: string | null; accessible_regions?: string[] | null } | null | undefined): RegionCode[] {
  const grants = (user?.accessible_regions ?? []).map((r) => String(r).trim().toUpperCase()).filter((r): r is RegionCode => r === 'EGY' || r === 'UAE');
  const unique = [...new Set(grants)];
  if (unique.length) return unique;
  if (user?.role === 'Regional Manager') return [];
  return ['EGY', 'UAE'];
}

export interface LockedPeriod {
  key: string;
  year: number;
  month: number;
  monthName: string;
  label: string;
  short: string;
  endDate: string;
}

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

export interface DeckParams {
  region: RegionSlug | null;
  month: string | null;
  /** Executive function name, when the link names one. */
  fn: string | null;
  team: string | null;
  /** Marketing role. Never stored in `team`. */
  position: string | null;
  present: boolean;
  print: boolean;
  slide: number | null;
}

export function parseDeckParams(search: string, hash = ''): DeckParams {
  const p = new URLSearchParams(search);
  const anchor = /^#s(\d{2})$/.exec(hash);
  const slideNo = anchor ? Number(anchor[1]) : null;
  const rawFn = p.get('function')?.trim() ?? '';
  const rawTeam = p.get('team')?.trim() ?? '';
  const rawPosition = p.get('position')?.trim() ?? '';
  return {
    region: parseRegion(p.get('region')),
    month: periodFromKey(p.get('month'))?.key ?? null,
    fn: isExecutiveFunction(rawFn) ? rawFn : null,
    team: rawTeam && rawTeam.length <= 80 ? rawTeam : null,
    position: rawPosition && rawPosition.length <= 80 ? rawPosition : null,
    present: p.get('mode') === 'present',
    print: p.get('print') === '1',
    slide: slideNo && slideNo >= 1 && slideNo <= SECTION_COUNT ? slideNo : null,
  };
}

/** Canonical query: region and month always written; other params preserved. */
export function buildDeckSearch(current: string, next: Partial<{ region: RegionSlug; month: string; fn: string | null; team: string | null; position: string | null; present: boolean; print: boolean }>): string {
  const p = new URLSearchParams(current);
  if (next.region) p.set('region', next.region);
  if (next.month) p.set('month', next.month);
  if (next.fn !== undefined) { if (next.fn) p.set('function', next.fn); else p.delete('function'); }
  if (next.team !== undefined) { if (next.team) p.set('team', next.team); else p.delete('team'); }
  if (next.position !== undefined) { if (next.position) p.set('position', next.position); else p.delete('position'); }
  if (next.present !== undefined) { if (next.present) p.set('mode', 'present'); else p.delete('mode'); }
  if (next.print !== undefined) { if (next.print) p.set('print', '1'); else p.delete('print'); }
  return `?${p.toString()}`;
}

export const pdfFileName = (code: RegionCode, key: string) => `PMS_Monthly_${code}_${key}.pdf`;

/** Stable aliases. Call once per distinct name, in a fixed order, before display. */
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

/** Masked export never prints action text, root cause, or outcome notes. */
export const MASKED_DETAILS_LABEL = 'Details hidden in masked export';

export type { GradeClass };
