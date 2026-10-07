import { describe, expect, it } from 'vitest';
import { actionAnalyticsStats, summarizeActionAnalytics } from './actionAnalytics';
import type { FollowUpAction } from './compose';
import type { ExecutivePeriod } from './types';

const period: ExecutivePeriod = { key: '2026-06', year: 2026, month: 'June' };
const action = (id: string, patch: Partial<FollowUpAction> = {}): FollowUpAction => ({
  id, team: 'Inbound', month: 'June', created_at: '2026-07-01T10:00:00Z',
  action_type: 'Coaching', status: 'Open', employee_id: 'e1', root_cause_note: 'Booking rate below target', ...patch,
});

describe('monthly corrective action analytics', () => {
  it('counts all statuses and all records, not only the four open follow-up items', () => {
    const result = summarizeActionAnalytics([
      ...Array.from({ length: 5 }, (_, i) => action(`open-${i}`)),
      action('done', { status: 'Completed' }),
      action('cancelled', { status: 'Cancelled' }),
    ], period);
    expect(result.actions).toHaveLength(7);
    expect(actionAnalyticsStats(result.actions).types).toEqual([{ label: 'Coaching', count: 7 }]);
  });

  it('uses the performance month, excludes other years and deduplicates persisted IDs', () => {
    const result = summarizeActionAnalytics([
      action('june'), action('june'), action('may', { month: 'May' }),
      action('old-year', { created_at: '2025-06-30T10:00:00Z' }),
      action('explicit', { month: '2026-06', created_at: '2025-01-01' }),
      action('legacy', { created_at: null }),
      action('timestamp', { month: '', created_at: '2026-06-10' }),
      action('undated', { month: '', created_at: null }),
    ], period);
    expect(result.actions.map((item) => item.id)).toEqual(['june', 'explicit', 'legacy', 'timestamp']);
    expect(result.unassigned_period).toBe(1);
    expect(summarizeActionAnalytics([action('june')], null).actions).toEqual([]);
  });

  it('ranks action types and teams by frequency and counts unique employees, excluding team-only actions', () => {
    const stats = actionAnalyticsStats(summarizeActionAnalytics([
      action('1'), action('2'), action('3', { team: 'Coding', action_type: 'Training', employee_id: 'e2' }),
      action('4', { employee_id: null, action_type: 'Training' }),
    ], period).actions);
    expect(stats.total).toBe(4);
    expect(stats.employees).toBe(2);
    expect(stats.teams).toEqual([{ label: 'Inbound', count: 3 }, { label: 'Coding', count: 1 }]);
    expect(stats.types).toEqual([{ label: 'Coaching', count: 2 }, { label: 'Training', count: 2 }]);
  });

  it('reuses legacy KPI extraction and counts a repeated or linked KPI once per action', () => {
    const stats = actionAnalyticsStats(summarizeActionAnalytics([
      action('1', { root_cause_note: 'AHT / handle time and booking rate. AHT again.', linked_kpi_key: 'aht' }),
      action('2', { root_cause_note: 'Booking rate', linked_kpi_key: 'booking_rate' }),
      action('3', { root_cause_note: '', linked_kpi_key: 'first_call_resolution' }),
      action('4', { root_cause_note: 'Needs support' }),
    ], period).actions);
    expect(stats.kpis).toEqual([
      { label: 'Booking Rate', count: 2 },
      { label: 'AHT (Handle Time)', count: 1 },
      { label: 'first call resolution', count: 1 },
    ]);
    expect(stats.withoutKpi).toBe(1);
    expect(stats.kpis.some((item) => item.label === 'Other')).toBe(false);
  });
});
