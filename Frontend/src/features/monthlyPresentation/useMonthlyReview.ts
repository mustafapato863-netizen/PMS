/**
 * Bounded reads for one region and one locked month.
 * Three summary-records calls (selected, previous, and the month before) and
 * two follow-up calls (selected and previous). Each URL carries the region.
 * Year is applied here for follow-up, because that API matches the month name only.
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';
import { insightsWorkspaceUrl, type InsightSection } from '../../hooks/api/useInsightsWorkspace';
import { mapScopedPerformanceRecord } from '../../hooks/usePerformanceData';
import { normalizeRegion, toExecRecords } from '../executive/compose';
import type { InsightsWorkspace } from '../insights/types';
import { periodFromKey, shiftMonth, type LockedPeriod, type RegionCode } from './model';
import { REVIEW_SECTIONS, followUpUrl, mapReviewAction, summaryRecordsUrl } from './reviewModel';

export const REVIEW_QUERY_ROOT = 'monthly-review';

interface Envelope<T> { success: boolean; data: T; message?: string }

function readEnvelope<T>(res: Envelope<T> | null | undefined, url: string): T {
  if (!res || typeof res !== 'object' || typeof res.success !== 'boolean') {
    throw new Error(`Unexpected response from ${url.split('?')[0]}`);
  }
  if (!res.success) throw new Error(res.message || `Request failed: ${url.split('?')[0]}`);
  return res.data;
}

function asArray<T>(value: unknown, label: string): T[] {
  if (!Array.isArray(value)) throw new Error(`Unexpected ${label} response shape`);
  return value as T[];
}

export function useMonthlyReview(
  code: RegionCode | null,
  period: LockedPeriod | null,
  enabled: boolean,
  scope: { fn: string; team: string; position: string },
) {
  const months = useMemo(() => {
    if (!period) return [];
    return [0, -1, -2]
      .map((delta) => periodFromKey(shiftMonth(period.key, delta)))
      .filter((month): month is LockedPeriod => month != null);
  }, [period]);
  const active = enabled && Boolean(code && period && months.length === 3);

  const records = useQuery({
    queryKey: [REVIEW_QUERY_ROOT, 'records', code, period?.key],
    enabled: active,
    retry: false,
    queryFn: async ({ signal }) => {
      const batches = await Promise.all(months.map(async (month) => {
        const url = summaryRecordsUrl(code!, month.year, month.monthName);
        const data = readEnvelope<unknown>(await apiFetch<Envelope<unknown>>(url, { signal }), url);
        return asArray<Record<string, unknown>>(data, 'summary-records').map((item) => mapScopedPerformanceRecord(item));
      }));
      return toExecRecords(batches.flat()).filter((record) => normalizeRegion(record.region) === code);
    },
  });

  const actions = useQuery({
    queryKey: [REVIEW_QUERY_ROOT, 'actions', code, period?.key],
    enabled: active,
    retry: false,
    queryFn: async ({ signal }) => {
      const batches = await Promise.all(months.slice(0, 2).map(async (month) => {
        const url = followUpUrl(code!, month.monthName);
        const data = readEnvelope<{ actions?: unknown }>(await apiFetch<Envelope<{ actions?: unknown }>>(url, { signal }), url);
        return asArray<Parameters<typeof mapReviewAction>[0]>(data?.actions, 'follow-up')
          .map((item, index) => mapReviewAction(item, index))
          .filter((action) => action.year === month.year);
      }));
      return batches.flat();
    },
  });

  const insights = useQuery({
    queryKey: [REVIEW_QUERY_ROOT, 'insights', code, period?.key, scope.fn, scope.team, scope.position],
    enabled: active,
    retry: false,
    queryFn: async ({ signal }) => {
      const url = insightsWorkspaceUrl({
        periodKey: period!.key,
        region: code ?? undefined,
        teamFunction: scope.fn || undefined,
        team: scope.team || undefined,
        position: scope.position || undefined,
      }, 'full', REVIEW_SECTIONS as readonly InsightSection[]);
      return readEnvelope(await apiFetch<Envelope<InsightsWorkspace>>(url, { signal }), url);
    },
  });

  return { records, actions, insights };
}
