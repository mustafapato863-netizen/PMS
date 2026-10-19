import { useState } from 'react';
import { Activity, Search, X } from 'lucide-react';
import type { InsightKpiDiagnosisRow, InsightKpiStatus } from '../../../features/insights/types';
import { SectionCard, SectionHeader } from './InsightsOverviewPrimitives';
import { KPI_STATUS_LABEL, STATUS_CLASS, formatEffect, formatKpiValue, formatTarget } from './kpiDiagnosisFormat';

/** With more than one team, the table shows this many rows (largest negative effect first) until "Show all". */
const TOP_ROWS = 10;
/** The explanation of the effect column; also its tooltip. */
const EFFECT_EXPLANATION = "Effect on team score: the sum of each employee's weighted impact on this KPI, as in People to review.";

function Sparkline({ values }: { values: Array<number | null> }) {
  const finite = values.filter((value): value is number => value !== null && Number.isFinite(value));
  if (finite.length < 2) return <span className="text-[12px] text-[var(--text-muted)]">Not enough months</span>;
  const low = Math.min(...finite);
  const high = Math.max(...finite);
  const span = high - low || 1;
  const width = 96;
  const height = 28;
  const step = width / Math.max(values.length - 1, 1);
  const points = values
    .map((value, index) => (value === null || !Number.isFinite(value) ? null : `${(index * step).toFixed(1)},${(height - ((value - low) / span) * (height - 4) - 2).toFixed(1)}`))
    .filter((point): point is string => point !== null)
    .join(' ');
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Six-month trend" className="text-blue-600">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function chipClass(selected: boolean) {
  return `rounded-full border px-[10px] py-[3px] text-[12px] font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
    selected
      ? 'border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-300'
      : 'border-[var(--insights-row-border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
  }`;
}

export default function KpiDiagnosisTable({
  rows,
  selectedKey,
  onSelect,
}: {
  rows: InsightKpiDiagnosisRow[];
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
}) {
  const [team, setTeam] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<InsightKpiStatus | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showAll, setShowAll] = useState(false);

  const teams = [...new Set(rows.flatMap((row) => row.teams))].sort((a, b) => a.localeCompare(b));
  const multiTeam = teams.length > 1;

  const teamScoped = team === null ? rows : rows.filter((row) => row.teams.includes(team));
  const criticalCount = teamScoped.filter((row) => row.status === 'critical').length;
  const atRiskCount = teamScoped.filter((row) => row.status === 'at_risk').length;
  const onTrackCount = teamScoped.filter((row) => row.status === 'on_track').length;

  const trimmedQuery = searchQuery.trim().toLowerCase();
  const filtered = teamScoped.filter((row) => {
    if (statusFilter !== null && row.status !== statusFilter) return false;
    if (trimmedQuery) {
      const matchesLabel = row.label.toLowerCase().includes(trimmedQuery);
      const matchesTeam = row.teams.some((t) => t.toLowerCase().includes(trimmedQuery));
      if (!matchesLabel && !matchesTeam) return false;
    }
    return true;
  });

  const visible = multiTeam && !showAll ? filtered.slice(0, TOP_ROWS) : filtered;
  const hasExtraFilter = statusFilter !== null || trimmedQuery.length > 0;

  return (
    <SectionCard labelledBy="kpi-diagnosis-title" className="gap-[16px] py-[20px]">
      <SectionHeader
        id="kpi-diagnosis-title"
        icon={<Activity size={16} />}
        iconBackground="var(--insights-accent)"
        title="KPI diagnosis"
        subtitle="Scored KPIs in this scope, largest effect on the score first. Select a KPI to open its detail."
      />
      {rows.length === 0 ? (
        <p className="py-[24px] text-center text-[13px] text-[var(--text-muted)]">No scored KPIs in this scope.</p>
      ) : (
        <>
          <div className="flex flex-col gap-[10px]">
            {multiTeam && (
              <div role="group" aria-label="Filter KPIs by team" className="flex flex-wrap gap-[8px]">
                <button type="button" aria-pressed={team === null} onClick={() => setTeam(null)} className={chipClass(team === null)}>
                  All teams
                </button>
                {teams.map((name) => (
                  <button
                    key={name}
                    type="button"
                    aria-pressed={team === name}
                    onClick={() => setTeam(team === name ? null : name)}
                    className={chipClass(team === name)}
                  >
                    {name}
                  </button>
                ))}
              </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-[10px]">
              <div role="group" aria-label="Filter KPIs by status" className="flex flex-wrap items-center gap-[6px]">
                <button
                  type="button"
                  aria-pressed={statusFilter === null}
                  aria-label="Filter by All statuses"
                  onClick={() => setStatusFilter(null)}
                  className={chipClass(statusFilter === null)}
                >
                  All statuses ({teamScoped.length})
                </button>
                <button
                  type="button"
                  aria-pressed={statusFilter === 'critical'}
                  aria-label="Filter by Critical status"
                  onClick={() => setStatusFilter(statusFilter === 'critical' ? null : 'critical')}
                  className={chipClass(statusFilter === 'critical')}
                >
                  Critical ({criticalCount})
                </button>
                <button
                  type="button"
                  aria-pressed={statusFilter === 'at_risk'}
                  aria-label="Filter by At risk status"
                  onClick={() => setStatusFilter(statusFilter === 'at_risk' ? null : 'at_risk')}
                  className={chipClass(statusFilter === 'at_risk')}
                >
                  At risk ({atRiskCount})
                </button>
                <button
                  type="button"
                  aria-pressed={statusFilter === 'on_track'}
                  aria-label="Filter by On target status"
                  onClick={() => setStatusFilter(statusFilter === 'on_track' ? null : 'on_track')}
                  className={chipClass(statusFilter === 'on_track')}
                >
                  On target ({onTrackCount})
                </button>
              </div>

              <div className="relative min-w-[200px] flex-1 sm:max-w-[260px]">
                <Search aria-hidden="true" className="pointer-events-none absolute left-[10px] top-1/2 size-[14px] -translate-y-1/2 text-[var(--text-muted)]" />
                <input
                  type="search"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  aria-label="Search diagnosed KPIs"
                  placeholder="Search KPI or team..."
                  className="w-full rounded-lg border border-[var(--insights-row-border)] bg-[var(--bg-surface)] py-[5px] pl-[30px] pr-[28px] text-[12px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                {searchQuery && (
                  <button
                    type="button"
                    aria-label="Clear KPI diagnosis search"
                    onClick={() => setSearchQuery('')}
                    className="absolute right-[8px] top-1/2 -translate-y-1/2 rounded p-[2px] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  >
                    <X aria-hidden="true" className="size-[13px]" />
                  </button>
                )}
              </div>
            </div>
          </div>

          {filtered.length === 0 ? (
            hasExtraFilter ? (
              <div className="flex flex-wrap items-center justify-center gap-[10px] py-[20px] text-center text-[13px] text-[var(--text-muted)]">
                <span>No scored KPIs match the active filter.</span>
                <button
                  type="button"
                  onClick={() => { setStatusFilter(null); setSearchQuery(''); }}
                  className="font-semibold text-blue-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                >
                  Reset diagnosis filters
                </button>
              </div>
            ) : (
              <p className="py-[24px] text-center text-[13px] text-[var(--text-muted)]">No scored KPIs for {team}.</p>
            )
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-[13px]">
                <thead>
                  <tr className="border-b border-[var(--insights-row-border)] text-[12px] font-semibold text-[var(--text-muted)]">
                    <th scope="col" className="py-[8px] pr-[12px] font-semibold">KPI</th>
                    {multiTeam && <th scope="col" className="py-[8px] pr-[12px] font-semibold">Team</th>}
                    <th scope="col" className="py-[8px] pr-[12px] font-semibold">Team actual and target</th>
                    <th scope="col" className="py-[8px] pr-[12px] font-semibold">Six months</th>
                    <th scope="col" className="py-[8px] pr-[12px] font-semibold" title={EFFECT_EXPLANATION}>Points lost by people below target</th>
                    <th scope="col" className="py-[8px] pr-[12px] font-semibold">Status</th>
                    <th scope="col" className="py-[8px] font-semibold">Team most below target</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((row) => {
                    const selected = selectedKey === row.key;
                    const onTargetButLosing = row.status === 'on_track' && row.effect_points !== null && row.effect_points < 0 && row.people_below_target > 0;
                    return (
                      <tr key={row.key} className={`border-b border-[var(--insights-row-border)] last:border-b-0 ${selected ? 'bg-blue-500/[0.06]' : ''}`}>
                        <td className="py-[10px] pr-[12px] align-top">
                          <button
                            type="button"
                            aria-pressed={selected}
                            onClick={() => onSelect(selected ? null : row.key)}
                            className="text-left font-semibold text-[var(--text-primary)] hover:text-blue-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                          >
                            {row.label}
                          </button>
                          {row.other_cohorts.length > 0 && (
                            <p className="mt-[2px] text-[12px] text-[var(--text-muted)]" data-testid={`kpi-cohort-note-${row.key}`}>
                              Also in scope: {row.other_cohorts.join('; ')}
                            </p>
                          )}
                        </td>
                        {multiTeam && (
                          <td className="py-[10px] pr-[12px] align-top text-[var(--text-secondary)]">{row.teams.join(', ')}</td>
                        )}
                        <td className="py-[10px] pr-[12px] align-top tabular-nums">
                          <span className="font-semibold text-[var(--text-primary)]">{formatKpiValue(row.actual, row.unit)}</span>
                          <span className="text-[var(--text-muted)]"> vs {formatTarget(row)}</span>
                        </td>
                        <td className="py-[10px] pr-[12px] align-top">
                          <Sparkline values={row.six_months.map((month) => month.actual_value)} />
                        </td>
                        <td className={`py-[10px] pr-[12px] align-top font-semibold tabular-nums ${row.effect_points !== null && row.effect_points < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-[var(--text-secondary)]'}`}>
                          {formatEffect(row.effect_points)}
                          {onTargetButLosing && (
                            <p className="mt-[2px] text-[12px] font-normal text-[var(--text-muted)]" data-testid={`kpi-on-target-note-${row.key}`}>
                              Team on target · {row.people_below_target} {row.people_below_target === 1 ? 'person' : 'people'} below
                            </p>
                          )}
                        </td>
                        <td className="py-[10px] pr-[12px] align-top">
                          {row.status ? (
                            <span className={`inline-flex rounded-full border px-[8px] py-[2px] text-[12px] font-semibold ${STATUS_CLASS[row.status]}`}>
                              {KPI_STATUS_LABEL[row.status]}
                            </span>
                          ) : (
                            <span className="text-[var(--text-muted)]">No target</span>
                          )}
                        </td>
                        <td className="py-[10px] align-top text-[var(--text-secondary)]">
                          {row.most_below_team ? (
                            <span>
                              {row.most_below_team.team}
                              <span className="text-[var(--text-muted)]">
                                {' · '}
                                {row.most_below_team.achievement_percent === null ? 'N/A' : `${row.most_below_team.achievement_percent.toFixed(0)}% of target`}
                              </span>
                            </span>
                          ) : (
                            <span className="text-[var(--text-muted)]">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {multiTeam && filtered.length > TOP_ROWS && (
                <button
                  type="button"
                  onClick={() => setShowAll((value) => !value)}
                  className="mt-[10px] text-[13px] font-semibold text-blue-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                >
                  {showAll ? `Show top ${TOP_ROWS}` : `Show all ${filtered.length}`}
                </button>
              )}
            </div>
          )}
        </>
      )}
    </SectionCard>
  );
}

