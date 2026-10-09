const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const PERIOD_KEY = /^(\d{4})-(0[1-9]|1[0-2])$/;

export interface ScopedPeriod {
  key: string;
  month: string;
  year: number;
}

/**
 * Exact `YYYY-MM` selects that period, including the next older catalog period across years.
 * A month name still means the latest catalog period with that name. Empty or All stays latest.
 */
export function resolveScopedPeriod(periods: ScopedPeriod[], selector: string): { active: ScopedPeriod | null; previous: ScopedPeriod | null } {
  const ordered = periods
    .filter((period) => period.key)
    .map((period) => ({ key: period.key, month: period.month, year: period.year }))
    .sort((left, right) => right.key.localeCompare(left.key));
  const requested = selector.trim();
  const exact = PERIOD_KEY.exec(requested);
  let active: ScopedPeriod | null;
  if (!requested || requested === 'All') {
    active = ordered[0] ?? null;
  } else if (exact) {
    const key = `${exact[1]}-${exact[2]}`;
    const month = MONTH_NAMES[Number(exact[2]) - 1];
    active = ordered.find((period) => period.key === key) ?? { key, month, year: Number(exact[1]) };
  } else {
    active = ordered.find((period) => period.month === requested) ?? ordered[0] ?? null;
  }
  const previous = active ? ordered.find((period) => period.key < active.key) ?? null : null;
  return { active, previous };
}

/** Shared month param stays in force until a valid `period=YYYY-MM` is present. */
export function overviewPeriodSelector(period: string | null | undefined, month: string | null | undefined): string {
  const exact = period?.trim() || '';
  if (PERIOD_KEY.test(exact)) return exact;
  const monthName = month?.trim() || '';
  if (monthName && monthName !== 'All') return monthName;
  return 'All';
}

export function monthNameFromPeriodKey(key: string): string | null {
  const exact = PERIOD_KEY.exec(key.trim());
  if (!exact) return null;
  return MONTH_NAMES[Number(exact[2]) - 1] ?? null;
}

export type ReportingSelector =
  | { kind: 'all' }
  | { kind: 'month'; month: string }
  | { kind: 'exact'; key: string; month: string; year: number };

/** `YYYY-MM` is one year. A month name stays a month name. Empty or All is unrestricted. */
export function parseReportingSelector(selector: string): ReportingSelector {
  const requested = selector.trim();
  if (!requested || requested === 'All') return { kind: 'all' };
  const exact = PERIOD_KEY.exec(requested);
  if (!exact) return { kind: 'month', month: requested };
  const monthNumber = Number(exact[2]);
  return {
    kind: 'exact',
    key: `${exact[1]}-${exact[2]}`,
    month: MONTH_NAMES[monthNumber - 1],
    year: Number(exact[1]),
  };
}

export function reportingMonthName(selector: string): string | null {
  const parsed = parseReportingSelector(selector);
  return parsed.kind === 'all' ? null : parsed.month;
}

type DatedMonth = { month?: string | null; year?: number | null };

function periodStamp(record: DatedMonth): string | null {
  const monthIndex = MONTH_NAMES.indexOf(record.month || '');
  const year = Number(record.year);
  if (monthIndex < 0 || !Number.isInteger(year) || year <= 0) return null;
  return `${year}-${String(monthIndex + 1).padStart(2, '0')}`;
}

/**
 * Exact keys keep that year only. A month name keeps the latest year for that
 * name so July 2025 and July 2026 are never added together.
 */
export function filterByReportingPeriod<T>(
  records: readonly T[],
  selector: string,
  read: (record: T) => DatedMonth,
): T[] {
  const parsed = parseReportingSelector(selector);
  if (parsed.kind === 'all') return records as T[];
  const sameMonth = records.filter((record) => read(record).month === parsed.month);
  if (parsed.kind === 'exact') {
    return sameMonth.filter((record) => Number(read(record).year) === parsed.year);
  }
  const latestYear = sameMonth.reduce((latest, record) => {
    const year = Number(read(record).year);
    return Number.isInteger(year) && year > latest ? year : latest;
  }, 0);
  if (!latestYear) return sameMonth;
  return sameMonth.filter((record) => Number(read(record).year) === latestYear);
}

/** The newest catalog-style key strictly before the selected year and month. */
export function previousReportingSelector(records: readonly DatedMonth[], selector: string): string | null {
  const parsed = parseReportingSelector(selector);
  if (parsed.kind === 'all') return null;
  const keys = Array.from(new Set(
    records.map(periodStamp).filter((key): key is string => Boolean(key)),
  )).sort((left, right) => right.localeCompare(left));
  const monthSuffix = `-${String(MONTH_NAMES.indexOf(parsed.month) + 1).padStart(2, '0')}`;
  const activeKey = parsed.kind === 'exact'
    ? parsed.key
    : keys.find((key) => key.endsWith(monthSuffix)) ?? null;
  if (!activeKey) return null;
  return keys.find((key) => key < activeKey) ?? null;
}
