/**
 * Period range for the Executive Summary. A month stays `period=YYYY-MM`; a range is `from=YYYY-MM&to=YYYY-MM`.
 * Both ends are inclusive. A range whose From is after its To is not a range.
 */
import { MONTHS, periodOf } from './compose';
import type { ExecutivePeriod } from './types';

export interface RangeSelection {
  /** First month, YYYY-MM. */
  from: string;
  /** Last month, YYYY-MM. */
  to: string;
}

export type RangePresetId = 'last3' | 'last6' | 'q1' | 'q2' | 'q3' | 'q4' | 'ytd';

const KEY = /^(\d{4})-(\d{2})$/;

/** Absolute month index (year * 12 + month) for a YYYY-MM key, or null when the key is not a month. */
function monthIndex(key: string | null | undefined): number | null {
  const match = KEY.exec(key ?? '');
  if (!match) return null;
  const month = Number(match[2]);
  return month >= 1 && month <= 12 ? Number(match[1]) * 12 + (month - 1) : null;
}

function keyOf(index: number): string {
  const year = Math.floor(index / 12);
  return `${year}-${String((index % 12) + 1).padStart(2, '0')}`;
}

/** The range in the URL, or null when there is none, or when the two months are invalid or in the wrong order. */
export function readRangeSelection(searchParams: URLSearchParams): RangeSelection | null {
  const from = searchParams.get('from');
  const to = searchParams.get('to');
  const start = monthIndex(from);
  const end = monthIndex(to);
  if (start === null || end === null || start > end) return null;
  return { from: keyOf(start), to: keyOf(end) };
}

/** Whether the URL asks for a range that cannot be shown (From after To, or a malformed month). */
export function rangeRequestIsInvalid(searchParams: URLSearchParams): boolean {
  if (!searchParams.get('from') && !searchParams.get('to')) return false;
  return readRangeSelection(searchParams) === null;
}

/** The URL parameters for a range; the caller removes `period`. */
export function rangeSearchValues(selection: RangeSelection): { from: string; to: string } {
  return { from: selection.from, to: selection.to };
}

/** Every month from `from` to `to`, YYYY-MM, oldest first. Empty for an invalid range. */
export function rangeMonthKeys(selection: RangeSelection): string[] {
  const start = monthIndex(selection.from);
  const end = monthIndex(selection.to);
  if (start === null || end === null || start > end) return [];
  return Array.from({ length: end - start + 1 }, (_, index) => keyOf(start + index));
}

/** The presets, relative to an anchor month: the selected month, or the range's last month. */
export function rangePresets(anchorKey: string): Array<{ id: RangePresetId; label: string; selection: RangeSelection }> {
  const anchor = monthIndex(anchorKey);
  if (anchor === null) return [];
  const year = Math.floor(anchor / 12);
  const quarter = (index: number) => {
    const start = year * 12 + index * 3;
    return { from: keyOf(start), to: keyOf(start + 2) };
  };
  return [
    { id: 'last3', label: 'Last 3 months', selection: { from: keyOf(anchor - 2), to: keyOf(anchor) } },
    { id: 'last6', label: 'Last 6 months', selection: { from: keyOf(anchor - 5), to: keyOf(anchor) } },
    { id: 'q1', label: 'Q1', selection: quarter(0) },
    { id: 'q2', label: 'Q2', selection: quarter(1) },
    { id: 'q3', label: 'Q3', selection: quarter(2) },
    { id: 'q4', label: 'Q4', selection: quarter(3) },
    { id: 'ytd', label: 'Year to date', selection: { from: keyOf(year * 12), to: keyOf(anchor) } },
  ];
}

/** The preset a range matches exactly for the anchor, or null for a custom range. */
export function presetIdFor(selection: RangeSelection, anchorKey: string): RangePresetId | null {
  return rangePresets(anchorKey).find((preset) => preset.selection.from === selection.from && preset.selection.to === selection.to)?.id ?? null;
}

/** "Jun – Sep 2026" within a year, "Nov 2025 – Feb 2026" across years. */
export function rangeLabel(first: ExecutivePeriod, last: ExecutivePeriod): string {
  const short = (period: ExecutivePeriod) => period.month.slice(0, 3);
  if (first.year === last.year) return `${short(first)} – ${short(last)} ${last.year}`;
  return `${short(first)} ${first.year} – ${short(last)} ${last.year}`;
}

/** Period objects for a selection, for labels. */
export function rangePeriods(selection: RangeSelection): { first: ExecutivePeriod; last: ExecutivePeriod } | null {
  const months = rangeMonthKeys(selection);
  if (!months.length) return null;
  const toPeriod = (key: string) => {
    const [year, month] = key.split('-').map(Number);
    return periodOf(year, MONTHS[month - 1]);
  };
  return { first: toPeriod(months[0]), last: toPeriod(months[months.length - 1]) };
}
