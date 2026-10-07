import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { AgentRecord, PerformanceLevelFilter } from '../../../types';
import { canonicalTeamName } from '../../../types';
import { kpiRows, toExecRecords } from '../../../features/executive/compose';
import { executiveFunctionForTeam } from '../../../features/executive/functions';
import type { TeamFunctionMap } from '../../../features/insights/filterCascade';
import type { ExecutivePerson, ExecutiveSummary } from '../../../features/executive/types';
import { employeeProfilePath } from '../../../features/executive/viewModel';
import { useSummaryRecords } from '../../../features/executive/useSummaryRecords';
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
    const key = person.performance_level ? `${person.employee_id}:${person.performance_level}` : person.employee_id;
    const option = options.get(key) ?? { person, reasons: [] };
    if (!option.reasons.includes(reason)) option.reasons.push(reason);
    options.set(key, option);
  };

  (summary.people?.below_90 ?? [...(summary.people?.bottom ?? []), ...(summary.people?.biggest_drops ?? [])])
    .filter((person) => person.score !== null && person.score < 90)
    .forEach((person) => add(person, 'Below 90%'));
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
  const optionKey = (person: ExecutivePerson) => person.performance_level ? `${person.employee_id}:${person.performance_level}` : person.employee_id;
  const [requestedEmployeeId, setRequestedEmployeeId] = useState('');
  const selectedKey = options.some((option) => optionKey(option.person) === requestedEmployeeId)
    ? requestedEmployeeId
    : options[0] ? optionKey(options[0].person) : '';
  const selected = options.find((option) => optionKey(option.person) === selectedKey)?.person ?? null;
  const selectedEmployeeId = selected?.employee_id ?? '';
  const evidence = useSummaryRecords(Boolean(selectedEmployeeId));
  const effective = summary.period.effective;
  const previousPeriod = summary.period.previous;
  const region = summary.scope.region === 'EGY' || summary.scope.region === 'UAE' ? summary.scope.region : 'All';
  const legacyEnabled = Boolean(selectedEmployeeId && evidence.isError && source === 'composed' && !scopedPerformanceApiEnabled);

  const legacy = usePerformanceData(
    'All',
    'all',
    region,
    (performanceLevel || 'All') as PerformanceLevelFilter,
    legacyEnabled,
    summary.scope.team ?? undefined,
  );
  const history = useScopedEmployeePerformanceHistory(
    scopedPerformanceApiEnabled && evidence.isError ? selectedEmployeeId || undefined : undefined,
    {
      period_end: effective?.key,
      months: 24,
      performance_level: performanceLevel !== 'All' ? performanceLevel : undefined,
      region: summary.scope.region ?? undefined,
    },
  );

  let agents: AgentRecord[] = [];
  if (evidence.data) {
    agents = evidence.data;
  } else if (scopedPerformanceApiEnabled) {
    agents = (history.data ?? []).map((record) => mapScopedPerformanceRecord(record as never));
  } else if (source === 'composed') {
    agents = legacy.agents as never as AgentRecord[];
  }
  const records = toExecRecords(agents, effective?.year ?? new Date().getFullYear());

  const inScope = records.filter((record) => {
    if (record.employeeId !== selectedEmployeeId) return false;
    if (summary.scope.team && canonicalTeamName(record.team) !== canonicalTeamName(summary.scope.team)) return false;
    if (summary.scope.region && (record.region ?? '').toUpperCase() !== summary.scope.region.toUpperCase()) return false;
    if (summary.scope.branch && !record.branches?.includes(summary.scope.branch)) return false;
    if (summary.scope.position && record.position !== summary.scope.position) return false;
    if (summary.scope.function && executiveFunctionForTeam(record.team, teamFunctions) !== summary.scope.function) return false;
    if (performanceLevel !== 'All' && record.level !== performanceLevel) return false;
    if (selected?.performance_level && record.level !== selected.performance_level) return false;
    return true;
  });

  const current = effective ? inScope.filter((record) => record.period.key === effective.key) : [];
  const previous = previousPeriod ? inScope.filter((record) => record.period.key === previousPeriod.key) : [];
  const rows = current.length ? kpiRows(current, previous) : [];
  const loading = evidence.isLoading || (evidence.isError && (scopedPerformanceApiEnabled
    ? Boolean(selectedEmployeeId && history.isFetching)
    : legacy.loading));
  const historyUnavailable = evidence.isError && source !== 'composed' && !scopedPerformanceApiEnabled;
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
    <div className="flex flex-wrap items-center gap-[8px]">
    <label className="flex items-center gap-[7px] text-[11px] font-semibold text-[var(--text-secondary)]">
      <span className="sr-only">Affected agent</span>
      <select
        aria-label="Affected agent"
        value={selectedKey}
        disabled={!options.length}
        onChange={(event) => setRequestedEmployeeId(event.target.value)}
        className="min-h-[34px] max-w-[220px] rounded-[8px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-[9px] text-[11px] font-semibold text-[var(--insights-heading)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)]"
      >
        {!options.length && <option value="">No affected agents</option>}
        {options.map(({ person, reasons }) => (
          <option key={optionKey(person)} value={optionKey(person)}>
            {person.name + ' · ' + reasons.join(' / ')}
          </option>
        ))}
      </select>
    </label>
    {selected && <Link to={employeeProfilePath(selected, effective)} className="rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-[10px] py-[7px] text-[12px] font-semibold text-[var(--insights-accent-text)]">Open 360 profile ↗</Link>}
    </div>
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
