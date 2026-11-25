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
    } else {
      sessionStorage.removeItem(CACHE_KEY);
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

/**
 * Pure helper that fills missing URL search params from the session filter cache.
 * Returns `{ params, changed }` so pages can read hydrated params synchronously on
 * initial render without firing a throwaway unfiltered query pass.
 */
export function mergeCachedExecutiveSearchParams(
  searchParams: URLSearchParams,
  cached: CachedExecutiveFilters | null,
  locked: { regionLocked?: boolean; branchLocked?: boolean } = {},
): { params: URLSearchParams; changed: boolean } {
  if (!cached) return { params: searchParams, changed: false };
  const next = new URLSearchParams(searchParams);
  let changed = false;
  if (!next.get('period') && !next.get('from') && !next.get('to')) {
    if (cached.from && cached.to) {
      next.set('from', cached.from);
      next.set('to', cached.to);
      changed = true;
    } else if (cached.period) {
      next.set('period', cached.period);
      changed = true;
    }
  }
  if (!next.get('region') && cached.region && !locked.regionLocked) {
    next.set('region', cached.region);
    changed = true;
  }
  if (!next.get('branch') && cached.branch && !locked.branchLocked) {
    next.set('branch', cached.branch);
    changed = true;
  }
  if (!next.get('level') && cached.level) {
    next.set('level', cached.level);
    changed = true;
  }
  return { params: changed ? next : searchParams, changed };
}
