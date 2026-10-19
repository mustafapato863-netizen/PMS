/**
 * Session storage cache for executive / function summary filters.
 * Keeps period, date range, region, branch, and level in sync when navigating
 * between the Executive Summary and Function Summary views.
 */

const CACHE_KEY = 'pms_executive_filter_cache';

export interface CachedExecutiveFilters {
  period?: string;
  from?: string;
  to?: string;
  region?: string;
  branch?: string;
  level?: string;
}

export function saveCachedExecutiveFilters(filters: CachedExecutiveFilters): void {
  try {
    const payload: CachedExecutiveFilters = {};
    if (filters.period && filters.period !== 'All' && filters.period !== 'all') {
      payload.period = filters.period;
    }
    if (filters.from) payload.from = filters.from;
    if (filters.to) payload.to = filters.to;
    if (filters.region && filters.region !== 'All' && filters.region !== 'all') {
      payload.region = filters.region;
    }
    if (filters.branch && filters.branch !== 'All' && filters.branch !== 'all') {
      payload.branch = filters.branch;
    }
    if (filters.level && filters.level !== 'All' && filters.level !== 'all') {
      payload.level = filters.level;
    }

    if (Object.keys(payload).length > 0) {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify(payload));
    }
  } catch {
    // Ignore storage errors in restricted contexts
  }
}

export function readCachedExecutiveFilters(): CachedExecutiveFilters | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function clearCachedExecutiveFilters(): void {
  try {
    sessionStorage.removeItem(CACHE_KEY);
  } catch {
    // Ignore
  }
}
