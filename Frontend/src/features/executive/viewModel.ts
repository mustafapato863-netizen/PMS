/** Page-level helpers for the Executive / Function Summary headers. */
import type { FilterOption } from '../../components/insights/overview/InsightsHeader';
import { MONTHS, formatPeriod, periodOf } from './compose';
import { teamPath } from './functions';
import type { ExecutivePerson, ExecutivePeriod, ExecutiveSummary, ExecutiveView } from './types';

export function employeeProfilePath(person: ExecutivePerson, period: ExecutivePeriod | null) {
  const params = new URLSearchParams();
  if (period) { params.set('month', period.month); params.set('year', String(period.year)); }
  if (person.performance_level) params.set('performance_level', person.performance_level);
  const query = params.toString();
  return `/employee/${encodeURIComponent(person.employee_id)}${query ? `?${query}` : ''}`;
}

export function employeeBalancedScorecardPath(
  person: ExecutivePerson,
  period: ExecutivePeriod | null,
  branch?: string | null,
) {
  if (!person.team) return employeeProfilePath(person, period);

  const params = new URLSearchParams();
  params.set('performance_level', person.performance_level || 'Corporate');
  if (period) {
    params.set('month', period.month);
    params.set('year', String(period.year));
  }
  params.set('employee_ids', person.employee_id);
  if (branch && branch !== 'All') params.set('branch', branch.toLowerCase());
  return `${teamPath(person.team)}?${params.toString()}`;
}

export function executivePersonPath(
  person: ExecutivePerson,
  period: ExecutivePeriod | null,
  branch?: string | null,
) {
  return person.performance_level === 'Corporate'
    ? employeeBalancedScorecardPath(person, period, branch)
    : employeeProfilePath(person, period);
}

export function currentPeriodKey(today = new Date()) {
  return periodOf(today.getFullYear(), MONTHS[today.getMonth()]).key;
}

export function periodOptionsFor(summary: ExecutiveSummary | null, requestedKey: string | undefined, today = new Date()): FilterOption[] {
  const options = (summary?.periods ?? []).map((period) => ({ value: period.key, label: formatPeriod(period) }));
  [requestedKey, currentPeriodKey(today)].forEach((key) => {
    if (!key || options.some((option) => option.value === key)) return;
    const [year, month] = key.split('-').map(Number);
    if (!year || !month) return;
    options.unshift({ value: key, label: `${MONTHS[month - 1]} ${year} (no data)` });
  });
  return options.sort((left, right) => right.value.localeCompare(left.value));
}

export function subtitleFor(summary: ExecutiveSummary | null, view: ExecutiveView) {
  const prefix = view === 'managerial' ? 'Managerial view' : view === 'function' ? 'Function view' : 'Corporate view';
  if (!summary?.period.effective) return `${prefix} · target 100%`;
  const team = view === 'managerial' && summary.scope.team ? ` · ${summary.scope.team}` : '';
  const vs = summary.period.previous ? ` vs ${formatPeriod(summary.period.previous)}` : '';
  if (view === 'function') {
    const { hero } = summary;
    const people = `${hero.teams_count} ${hero.teams_count === 1 ? 'team' : 'teams'} · ${hero.employees.toLocaleString('en-US')} people`;
    return `${summary.scope.function ?? hero.label} · ${formatPeriod(summary.period.effective)}${vs} · ${people}`;
  }
  return `${prefix}${team} · ${formatPeriod(summary.period.effective)}${vs} · target 100%`;
}
