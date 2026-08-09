import React from 'react';

// ─── Types & Interfaces ─────────────────────────────────────────
export type ViewKey = 'strategy_map' | 'perspective_summary';

export interface TooltipState {
  type: 'persp' | 'vision';
  x: number;
  y: number;
  title: string;
  rows: Array<{ k: string; v: string }>;
  hint?: string;
}

export interface PerspectiveData {
  key: string;
  label: string;
  focus?: string;
  display_order?: number;
  score?: number | null;
  status?: string;
  state?: string;
  weighted_contribution?: number | null;
  configured_weight?: number | null;
  measured_weight?: number | null;
  coverage?: number | null;
  trend_vs_previous?: number | null;
  target_score?: number | null;
  primary_driver?: {
    kpi_label?: string;
  } | null;
}

export interface KpiRowData {
  kpi_key: string;
  kpi_label: string;
  perspective: string;
  score?: number | null;
  status?: string;
  state?: string;
  weight?: number;
  measured_weight?: number | null;
  direction?: 'higher_better' | 'lower_better';
  actual_value?: number | null;
  target_value?: number | null;
  weighted_contribution?: number | null;
  performance_gap?: number | null;
  record_count?: number;
  unit?: string;
}

// ─── Constants & Color Mappings ──────────────────────────────────
export const YEAR_OPTIONS = ['2024', '2025', '2026'];
export const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

export const PERSP_COLORS: Record<string, string> = {
  Financial: '#2E6FE0',
  Customer: '#7C5CE0',
  'Internal Process': '#1A9E72',
  'Learning & Growth': '#E0832E',
};

export const PERSP_COLOR_KEY: Record<string, string> = {
  Financial: 'financial',
  Customer: 'customer',
  'Internal Process': 'internal',
  'Learning & Growth': 'learning',
};

export const AVATAR_COLORS = ['#2E6FE0', '#7C5CE0', '#1A9E72', '#E0832E', '#E03B3B', '#5B8DEF'];

// ─── Formatting Helpers ─────────────────────────────────────────
export const ck = (key: string) => PERSP_COLOR_KEY[key] ?? 'financial';
export const pc = (key: string) => PERSP_COLORS[key] ?? '#2E6FE0';

export const fmtScore = (v?: number | null, d = 1) => `${(v ?? 0).toFixed(d)}%`;

export const fmtWeightedContribution = (
  contribution?: number | null,
  configuredWeight?: number | null,
  measuredWeight?: number | null,
): string => {
  const allocatedWeight = configuredWeight ?? measuredWeight;
  if (allocatedWeight == null || allocatedWeight <= 0) return '0.0%';

  const weightLabel = `${(allocatedWeight * 100).toFixed(0)}%`;
  return contribution == null
    ? `0.0% of ${weightLabel}`
    : `${(contribution * 100).toFixed(1)}% of ${weightLabel}`;
};

export const formatCompactCurrency = (v: number): string => {
  const abs = Math.abs(v);
  const sign = v < 0 ? '-' : '';

  if (abs >= 1_000_000) {
    const millions = abs / 1_000_000;
    const formatted = millions % 1 === 0 || (millions * 10) % 10 === 0
      ? millions.toFixed(1).replace(/\.0$/, '')
      : millions.toFixed(1);
    return `${sign}AED ${formatted}M`;
  }

  if (abs >= 1_000) {
    const thousands = abs / 1_000;
    const formatted = thousands % 1 === 0 || (thousands * 10) % 10 === 0
      ? thousands.toFixed(1).replace(/\.0$/, '')
      : thousands.toFixed(1);
    return `${sign}AED ${formatted}K`;
  }

  return `${sign}AED ${Math.round(abs).toLocaleString()}`;
};

export const fmtVal = (v?: number | null, unit?: string) => {
  if (v == null || !Number.isFinite(v)) return 'N/A';

  const cleanUnit = (unit ?? '').replace(/\bcount\b/gi, '').trim();

  if (cleanUnit === 'currency' || cleanUnit === 'AED' || cleanUnit.toLowerCase().includes('aed')) {
    return formatCompactCurrency(v);
  }
  if (cleanUnit === 'number' || cleanUnit === '' || cleanUnit === 'count') {
    return Math.round(v) === v ? v.toLocaleString() : v.toFixed(1);
  }
  if (cleanUnit === 'visits') {
    return `${Math.round(v).toLocaleString()} visits`;
  }
  if (cleanUnit && cleanUnit !== '%') {
    const valStr = Math.round(v) === v ? v.toLocaleString() : v.toFixed(1);
    return `${valStr} ${cleanUnit}`.trim();
  }

  // Percentage / Ratio formatting (e.g. 0.9 -> 90%, 0.8123 -> 81.2%, -0.0877 -> -8.8%, -94.5 -> -94.5%, 100 -> 100%)
  const abs = Math.abs(v);
  if (abs > 1 || abs === 0) {
    const decimals = v % 1 === 0 ? 0 : 1;
    return `${v.toFixed(decimals)}%`;
  }
  const pct = v * 100;
  const decimals = pct % 1 === 0 ? 0 : 1;
  return `${pct.toFixed(decimals)}%`;
};

export const fmtVariance = (v?: number | null, unit?: string) => {
  if (v == null || !Number.isFinite(v)) return 'N/A';
  const cleanUnit = (unit ?? '').replace(/\bcount\b/gi, '').trim();

  if (v > 0) {
    if (cleanUnit === 'currency' || cleanUnit === 'AED') {
      return `+AED ${Math.round(v).toLocaleString()}`;
    }
    const valFormatted = fmtVal(v, unit);
    return `+${valFormatted}`;
  }

  return fmtVal(v, unit);
};

export const statusClass = (s?: string) => {
  const t = (s ?? '').toLowerCase();
  if (t.includes('excellent')) return 'excellent';
  if (t.includes('good'))      return 'good';
  if (t.includes('attention') || t.includes('warning')) return 'attention';
  if (t.includes('poor'))      return 'poor';
  return 'na';
};

export const statusLabel = (s?: string) => {
  const t = (s ?? '').toLowerCase();
  if (t.includes('excellent'))  return 'Excellent';
  if (t.includes('good'))       return 'Good';
  if (t.includes('attention'))  return 'Needs Attention';
  if (t.includes('poor'))       return 'Poor';
  if (t.includes('not_configured') || t.includes('not configured')) return 'Not Configured';
  return s || 'N/A';
};

export const scoreClass = (v?: number | null) =>
  v == null ? 'na' : v >= 90 ? 'excellent' : v >= 75 ? 'good' : v >= 60 ? 'attention' : 'poor';

export const initials = (n: string) =>
  n.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase();

export const avatarColor = (i: number) => AVATAR_COLORS[i % AVATAR_COLORS.length];

// ─── SVG Icons ──────────────────────────────────────────────────
export const PERSP_SVG: Record<string, React.ReactNode> = {
  Financial: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      <circle cx="12" cy="12" r="9"/>
      <path d="M12 7v10M9 10a3 3 0 013-3h.5a2.5 2.5 0 010 5H12a2.5 2.5 0 000 5h.5a3 3 0 003-3"/>
    </svg>
  ),
  Customer: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      <circle cx="9" cy="8" r="3.2"/>
      <path d="M3 20v-1a5 5 0 015-5h2a5 5 0 015 5v1"/>
      <circle cx="17.5" cy="9" r="2.3"/>
      <path d="M16 20v-.6a3.6 3.6 0 013.6-3.6h.4"/>
    </svg>
  ),
  'Internal Process': (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.65 1.65 0 00.33 1.82 2 2 0 11-2.83 2.83 1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51 2 2 0 01-4 0 1.65 1.65 0 00-1-1.51 1.65 1.65 0 00-1-1.51 1.65 1.65 0 00-1.82.33 2 2 0 11-2.83-2.83A1.65 1.65 0 005 15a1.65 1.65 0 00-1.51-1 2 2 0 010-4A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82 2 2 0 112.83-2.83A1.65 1.65 0 009 4.6a1.65 1.65 0 001-1.51 2 2 0 014 0 1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33 2 2 0 112.83 2.83A1.65 1.65 0 0019 9c.21.51.62.9 1.13 1.07a2 2 0 010 4 1.65 1.65 0 00-.73.93"/>
    </svg>
  ),
  'Learning & Growth': (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      <path d="M22 10L12 5 2 10l10 5 10-5z"/>
      <path d="M6 12v5c0 1.5 2.5 3 6 3s6-1.5 6-3v-5"/>
    </svg>
  ),
};
