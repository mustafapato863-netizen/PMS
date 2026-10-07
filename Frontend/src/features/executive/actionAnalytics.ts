import { canonicalTeamName } from '../../types';
import { extractKpiMentions } from '../../utils/rootCauseInsights';
import type { FollowUpAction } from './compose';
import type { ExecutiveActionAnalytics, ExecutivePeriod } from './types';

const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

function actionPeriod(action: FollowUpAction, effective: ExecutivePeriod): string | null {
  const month = action.month?.trim() ?? '';
  if (/^\d{4}-\d{2}(?:$|-)/.test(month)) return month.slice(0, 7);
  const monthIndex = MONTH_NAMES.findIndex((name) => name.toLowerCase() === month.toLowerCase());
  const createdYear = action.created_at?.match(/^(\d{4})-/)?.[1];
  // Legacy actions store only a month name. Use their recorded year when available.
  if (monthIndex >= 0) return `${createdYear ?? effective.year}-${String(monthIndex + 1).padStart(2, '0')}`;
  return action.created_at?.match(/^\d{4}-\d{2}-/) ? action.created_at.slice(0, 7) : null;
}

/** Same KPI-mention classification as the original ActionsSummaryCard; all statuses count. */
export function summarizeActionAnalytics(actions: FollowUpAction[], effective: ExecutivePeriod | null): ExecutiveActionAnalytics {
  const unique = [...new Map(actions.map((action) => [String(action.id), action])).values()];
  const result: ExecutiveActionAnalytics = { actions: [], unassigned_period: 0 };
  if (!effective) return result;
  for (const action of unique) {
    const period = actionPeriod(action, effective);
    if (!period) {
      result.unassigned_period++;
      continue;
    }
    if (period !== effective.key) continue;
    const mentions = extractKpiMentions(action.root_cause_note ?? '');
    if (action.linked_kpi_key) {
      const linked = extractKpiMentions(action.linked_kpi_key);
      mentions.push(...(linked.length ? linked : [action.linked_kpi_key.replace(/[_-]+/g, ' ')]));
    }
    result.actions.push({
      id: String(action.id),
      team: canonicalTeamName(action.team) || null,
      employee_id: action.employee_id || null,
      action_type: action.action_type?.trim() || 'Unclassified',
      kpi_mentions: [...new Set(mentions)],
    });
  }
  return result;
}

export function actionAnalyticsStats(actions: ExecutiveActionAnalytics['actions']) {
  const types = new Map<string, number>();
  const teams = new Map<string, number>();
  const kpis = new Map<string, number>();
  const employees = new Set<string>();
  for (const action of actions) {
    types.set(action.action_type, (types.get(action.action_type) ?? 0) + 1);
    const team = action.team || 'Unassigned team';
    teams.set(team, (teams.get(team) ?? 0) + 1);
    for (const kpi of new Set(action.kpi_mentions)) kpis.set(kpi, (kpis.get(kpi) ?? 0) + 1);
    if (action.employee_id) employees.add(action.employee_id);
  }
  const ranked = (counts: Map<string, number>) => [...counts].map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
  return {
    total: actions.length,
    employees: employees.size,
    teams: ranked(teams),
    types: ranked(types),
    kpis: ranked(kpis),
    withoutKpi: actions.filter((action) => !action.kpi_mentions.length).length,
  };
}
