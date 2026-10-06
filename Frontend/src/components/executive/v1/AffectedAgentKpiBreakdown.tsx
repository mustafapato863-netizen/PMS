import { useMemo, useState } from 'react';
import type { AgentRecord, PerformanceLevelFilter } from '../../../types';
import { canonicalTeamName } from '../../../types';
import { kpiRows, toExecRecords } from '../../../features/executive/compose';
import { executiveFunctionForTeam } from '../../../features/executive/functions';
import type { TeamFunctionMap } from '../../../features/insights/filterCascade';
import type { ExecutivePerson, ExecutiveSummary } from '../../../features/executive/types';
import { usePerformanceData, mapScopedPerformanceRecord } from '../../../hooks/usePerformanceData';
import { scopedPerformanceApiEnabled, useScopedEmployeePerformanceHistory } from '../../../hooks/api/usePerformanceDashboard';
import TeamKpiTable from './TeamKpiTable';

interface AffectedAgentOption {
  person: ExecutivePerson;
  reasons: string[];
}

function affectedAgentOptions(summary: ExecutiveSummary): AffectedAgentOption[] {
  const options = new Map<string, AffectedAgentOption>();
  const add = (person: ExecutivePerson, reason: string) => {
    const option = options.get(person.employee_id) ?? { person, reasons: [] };
    if (!option.reasons.includes(reason)) option.reasons.push(reason);
    options.set(person.employee_id, option);
  };

  summary.people?.bottom.forEach((person) => add(person, 'Lowest score'));
  summary.people?.biggest_drops.forEach((person) => add(person, 'Largest drop'));
  return [...options.values()];
}

/** KPI-level actual, target and direction-aware gap for people flagged by this filtered function view. */
export default function AffectedAgentKpiBreakdown({
  summary,
  source,
  performanceLevel,
  teamFunctions,
}: {
  summary: ExecutiveSummary;
  source: 'api' | 'composed' | null;
  performanceLevel: string;
  teamFunctions?: TeamFunctionMap;
}) {
  const options = affectedAgentOptions(summary);
  const [requestedEmployeeId, setRequestedEmployeeId] = useState('');
  const selectedEmployeeId = options.some((option) => option.person.employee_id === requestedEmployeeId)
    ? requestedEmployeeId
    : options[0]?.person.employee_id ?? '';
  const selected = options.find((option) => option.person.employee_id === selectedEmployeeId)?.person ?? null;
  const effective = summary.period.effective;
  const previousPeriod = summary.period.previous;
  const region = summary.scope.region === 'EGY' || summary.scope.region === 'UAE' ? summary.scope.region : 'All';
  const legacyEnabled = Boolean(selectedEmployeeId && source === 'composed' && !scopedPerformanceApiEnabled);

  const legacy = usePerformanceData(
    'All',
    'all',
    region,
    (performanceLevel || 'All') as PerformanceLevelFilter,
    legacyEnabled,
    summary.scope.team ?? undefined,
  );
  const history = useScopedEmployeePerformanceHistory(
    scopedPerformanceApiEnabled ? selectedEmployeeId || undefined : undefined,
    {
      period_end: effective?.key,
      months: 24,
      performance_level: performanceLevel !== 'All' ? performanceLevel : undefined,
      region: summary.scope.region ?? undefined,
    },
  );

  const records = useMemo(() => {
    let agents: AgentRecord[] = [];
    if (scopedPerformanceApiEnabled) {
      agents = (history.data ?? []).map((record) => mapScopedPerformanceRecord(record as never));
    } else if (source === 'composed') {
      agents = legacy.agents as never as AgentRecord[];
    }
    return toExecRecords(agents, effective?.year ?? new Date().getFullYear());
  }, [effective?.year, history.data, legacy.agents, source]);

  const inScope = useMemo(() => records.filter((record) => {
    if (record.employeeId !== selectedEmployeeId) return false;
    if (summary.scope.team && canonicalTeamName(record.team) !== canonicalTeamName(summary.scope.team)) return false;
    if (summary.scope.region && (record.region ?? '').toUpperCase() !== summary.scope.region.toUpperCase()) return false;
    if (summary.scope.function && executiveFunctionForTeam(record.team, teamFunctions) !== summary.scope.function) return false;
    if (performanceLevel !== 'All' && record.level !== performanceLevel) return false;
    return true;
  }), [performanceLevel, records, selectedEmployeeId, summary.scope.function, summary.scope.region, summary.scope.team, teamFunctions]);

  const current = useMemo(
    () => (effective ? inScope.filter((record) => record.period.key === effective.key) : []),
    [effective?.key, inScope],
  );
  const previous = useMemo(
    () => (previousPeriod ? inScope.filter((record) => record.period.key === previousPeriod.key) : []),
    [inScope, previousPeriod?.key],
  );
  const rows = useMemo(() => (current.length ? kpiRows(current, previous) : []), [current, previous]);
  const loading = scopedPerformanceApiEnabled
    ? Boolean(selectedEmployeeId && history.isFetching)
    : legacy.loading;
  const historyUnavailable = source !== 'composed' && !scopedPerformanceApiEnabled;
  const emptyMessage = loading
    ? 'Loading KPI history for this agent…'
    : historyUnavailable
      ? 'Individual KPI history is not available from this summary source yet.'
      : (scopedPerformanceApiEnabled && history.isError)
        ? 'Could not load KPI history for this agent.'
        : !selectedEmployeeId
          ? 'No affected agents in this filtered scope.'
          : !current.length
            ? 'No measured KPI data for this agent in the selected month.'
            : 'No KPI breakdown for this agent in this month.';

  const headerAction = (
    <label className="flex items-center gap-[7px] text-[11px] font-semibold text-[var(--text-secondary)]">
      <span className="sr-only">Affected agent</span>
      <select
        aria-label="Affected agent"
        value={selectedEmployeeId}
        disabled={!options.length}
        onChange={(event) => setRequestedEmployeeId(event.target.value)}
        className="min-h-[34px] max-w-[220px] rounded-[8px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-[9px] text-[11px] font-semibold text-[var(--insights-heading)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)]"
      >
        {!options.length && <option value="">No affected agents</option>}
        {options.map(({ person, reasons }) => (
          <option key={person.employee_id} value={person.employee_id}>
            {person.name + ' · ' + reasons.join(' / ')}
          </option>
        ))}
      </select>
    </label>
  );

  const subtitle = selected
    ? [selected.position || 'Agent', effective ? effective.month + ' ' + effective.year : null].filter(Boolean).join(' · ')
    : 'Agent-level KPI detail for the current filtered function scope';

  return (
    <TeamKpiTable
      rows={rows}
      effective={effective}
      previous={previousPeriod}
      score={current[0]?.score ?? null}
      title="Affected agent KPI breakdown"
      subtitle={subtitle}
      headerAction={headerAction}
      emptyMessage={emptyMessage}
      scoreLabel="Agent score"
    />
  );
}
