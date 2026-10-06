import type { InsightItem, InsightSeverity } from './types';

/**
 * Display bucket for an insight's severity. The API uses `information` both
 * for data-quality items and (PR #15) for KPIs that are still on target but
 * moving the wrong way; the latter are shown as a neutral "Watch" item, not
 * as a data issue.
 */
export type SeverityDisplay = Exclude<InsightSeverity, 'information'> | 'watch' | 'data_issue';

export function severityDisplay(insight: Pick<InsightItem, 'severity' | 'insight_type'>): SeverityDisplay {
  if (insight.severity !== 'information') return insight.severity;
  return insight.insight_type === 'data_quality' ? 'data_issue' : 'watch';
}

export const SEVERITY_LABELS: Record<SeverityDisplay, string> = {
  critical: 'Critical',
  risk: 'At risk',
  opportunity: 'Opportunity',
  watch: 'Watch',
  data_issue: 'Data issue',
};

/** Bordered pill / tile styles used across Insights. */
export const SEVERITY_STYLES: Record<SeverityDisplay, string> = {
  critical: 'border-rose-200 bg-rose-50 text-rose-600 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-300',
  risk: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-300',
  opportunity: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-300',
  // Neutral: on target, but worth keeping an eye on.
  watch: 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-500/30 dark:bg-slate-500/10 dark:text-slate-300',
  data_issue: 'border-blue-200 bg-blue-50 text-blue-600 dark:border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-300',
};
