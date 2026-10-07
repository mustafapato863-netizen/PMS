/**
 * Display helpers for the Executive / Function Summary. Score maths stays in
 * compose.ts; tones are direction-aware via insightsOverviewModel.
 */
import { resolveMovementTone } from '../../components/insights/overview/insightsOverviewModel';
import type { InsightTrendStatus } from '../insights/types';

export type Tone = 'good' | 'bad' | 'neutral';
export type KpiDirection = 'higher_better' | 'lower_better';
const MINUS = '\u2212';

export function fmtScore(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${value.toFixed(digits)}%`;
}

export function fmtSigned(value: number | null | undefined, suffix = '%', digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const rounded = Number(value.toFixed(digits));
  if (rounded === 0) return `0${digits ? `.${'0'.repeat(digits)}` : ''}${suffix}`;
  return `${rounded > 0 ? '+' : MINUS}${Math.abs(rounded).toFixed(digits)}${suffix}`;
}

export function arrow(value: number | null | undefined): '↑' | '↓' | '→' {
  if (value === null || value === undefined || Math.abs(value) < 0.05) return '→';
  return value > 0 ? '↑' : '↓';
}

/** Scores are always higher-is-better. */
export function scoreTone(delta: number | null | undefined): Tone {
  if (delta === null || delta === undefined || Math.abs(delta) < 0.05) return 'neutral';
  return delta > 0 ? 'good' : 'bad';
}

export function toneColor(tone: Tone): string {
  if (tone === 'good') return 'var(--insights-positive)';
  if (tone === 'bad') return 'var(--insights-negative)';
  return 'var(--text-muted)';
}

export function isLowerBetter(direction: string | null | undefined): boolean {
  return normalizeKpiDirection(direction) === 'lower_better';
}

export function normalizeKpiDirection(direction: string | null | undefined): KpiDirection | null {
  const value = String(direction ?? '').trim().toLowerCase();
  if (value === 'lower_better' || value === 'lower_is_better' || value === 'lower') return 'lower_better';
  if (value === 'higher_better' || value === 'higher_is_better' || value === 'higher') return 'higher_better';
  return null;
}

/** Normalize a raw KPI delta so positive always means better performance. */
export function directionAdjustedDelta(delta: number | null | undefined, direction: string | null | undefined): number | null {
  if (delta === null || delta === undefined || !Number.isFinite(delta)) return null;
  const normalizedDirection = normalizeKpiDirection(direction);
  if (normalizedDirection === null) return null;
  return normalizedDirection === 'lower_better' ? -delta : delta;
}

/** Direction-normalized gap; falls back to raw gap only when direction is known. */
export function kpiGapDelta(row: { gap_value?: number | null; raw_gap?: number | null; kpi_direction?: string | null }): number | null {
  if (row.gap_value !== null && row.gap_value !== undefined && Number.isFinite(row.gap_value)) return row.gap_value;
  return directionAdjustedDelta(row.raw_gap, row.kpi_direction);
}

/** Direction-normalized month-over-month change; unknown direction stays unavailable. */
export function kpiChangeDelta(row: { change_value?: number | null; raw_change?: number | null; kpi_direction?: string | null }): number | null {
  if (row.change_value !== null && row.change_value !== undefined && Number.isFinite(row.change_value)) return row.change_value;
  return directionAdjustedDelta(row.raw_change, row.kpi_direction);
}

const unitKind = (unit: string | null | undefined) => String(unit ?? '').trim().toLowerCase();

/** KPI actual / target in its own unit. */
export function fmtKpiValue(value: number | null | undefined, unit: string | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const kind = unitKind(unit);
  if (kind === '%' || kind === 'percent' || kind === 'percentage') return `${Number(value.toFixed(1))}%`;
  if (kind === 's' || kind === 'sec' || kind === 'seconds') return `${Math.round(value)} s`;
  if (kind === 'min' || kind === 'minutes') return `${Number(value.toFixed(1))} min`;
  if (kind === 'days' || kind === 'day') return `${Number(value.toFixed(1))} days`;
  if (kind === 'aed' || kind === 'currency') {
    if (Math.abs(value) >= 1_000_000) return `AED ${Number((value / 1_000_000).toFixed(2))}M`;
    if (Math.abs(value) >= 1_000) return `AED ${Number((value / 1_000).toFixed(1))}K`;
    return `AED ${Math.round(value)}`;
  }
  return Number.isInteger(value) ? value.toLocaleString('en-US') : Number(value.toFixed(2)).toLocaleString('en-US');
}

/** Raw KPI change in its own unit; percentage deltas display with %. */
export function fmtKpiDelta(value: number | null | undefined, unit: string | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const kind = unitKind(unit);
  const sign = value > 0 ? '+' : value < 0 ? MINUS : '';
  const abs = Math.abs(value);
  if (kind === '%' || kind === 'percent' || kind === 'percentage') return `${sign}${Number(abs.toFixed(1))}%`;
  if (kind === 's' || kind === 'sec' || kind === 'seconds') return `${sign}${Math.round(abs)} s`;
  if (kind === 'min' || kind === 'minutes') return `${sign}${Number(abs.toFixed(1))} min`;
  if (kind === 'days' || kind === 'day') return `${sign}${Number(abs.toFixed(1))} d`;
  return `${sign}${Number(abs.toFixed(2)).toLocaleString('en-US')}`;
}

/**
 * Direction-aware tone of a KPI movement: prefers #15's normalised fields
 * (`trend_status` / `change_value`), falls back to raw delta × direction.
 */
export function kpiMovementTone(row: { trend_status?: InsightTrendStatus | null; change_value?: number | null; raw_change?: number | null; kpi_direction?: string | null }): Tone {
  const tone = resolveMovementTone({
    trendStatus: row.trend_status ?? null,
    changeValue: kpiChangeDelta(row),
    rawDelta: row.raw_change ?? null,
    direction: normalizeKpiDirection(row.kpi_direction),
  });
  return tone === 'good' || tone === 'bad' ? tone : 'neutral';
}

export function shortMonth(period: { month: string; year: number } | null | undefined): string {
  return period ? period.month.slice(0, 3) : '';
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const date = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}
