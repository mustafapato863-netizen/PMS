/** Page-level helpers for the Executive / Function Summary headers. */
import type { FilterOption } from '../../components/insights/overview/InsightsHeader';
import { MONTHS, formatPeriod, periodOf } from './compose';
import type { ExecutiveSummary, ExecutiveView } from './types';

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

