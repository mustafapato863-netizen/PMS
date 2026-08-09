import { useMemo, useState, type ReactNode } from 'react';
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Info } from 'lucide-react';
import type {
  InsightPersonContribution,
  InsightPeopleContributionAnalysis,
  PersonContributionClassification,
} from '../../features/insights/types';
import { formatContributionMetric } from './peopleContributionFormatters';

type ContributionTab = 'negative' | 'positive' | 'affected' | 'data_issue';

const severityClasses: Record<string, string> = {
  High: 'bg-rose-500/10 text-rose-600',
  Medium: 'bg-amber-500/10 text-amber-700',
  Low: 'bg-blue-500/10 text-blue-600',
  Positive: 'bg-emerald-500/10 text-emerald-700',
  'On target': 'bg-slate-500/10 text-slate-600',
  'Data issue': 'bg-amber-500/10 text-amber-700',
};

const classificationMatches = (
  classification: PersonContributionClassification,
  tab: ContributionTab,
) => tab === 'affected' ? classification !== 'data_issue' : classification === tab;

function signedValue(value: number | null, suffix = '%') {
  if (value === null) return 'N/A';
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}${suffix}`;
}

function impactColor(value: number | null) {
  if (value === null) return 'text-[var(--text-muted)]';
  if (value < 0) return 'text-rose-600';
  if (value > 0) return 'text-emerald-600';
  return 'text-[var(--text-muted)]';
}

export default function PeopleContributionAnalysis({
  analysis,
  onOpenEmployee,
  renderEmployeeActions,
}: {
  analysis: InsightPeopleContributionAnalysis;
  onOpenEmployee: (employeeId: string, performanceLevel: string) => void;
  renderEmployeeActions: (row: InsightPersonContribution) => ReactNode;
}) {
  const [tab, setTab] = useState<ContributionTab>('negative');
  const [page, setPage] = useState(1);
  const [topCount, setTopCount] = useState(5);
  const pageSize = 8;

  const filteredRows = useMemo(
    () => analysis.rows.filter((row) => classificationMatches(row.classification, tab)),
    [analysis.rows, tab],
  );
  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pagedRows = filteredRows.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const negativeRows = analysis.rows
    .filter((row) => row.classification === 'negative' && row.weighted_impact !== null)
    .slice(0, topCount);
  const maxNegativeImpact = Math.max(
    .01,
    ...negativeRows.map((row) => Math.abs(row.weighted_impact ?? 0)),
  );

  const tabs: Array<{ key: ContributionTab; label: string; count: number }> = [
    { key: 'negative', label: 'Negative contributors', count: analysis.negative_contributors },
    { key: 'positive', label: 'Positive contributors', count: analysis.positive_contributors },
    { key: 'affected', label: 'All affected', count: analysis.total_employees - analysis.data_issues },
    { key: 'data_issue', label: 'Data issues', count: analysis.data_issues },
  ];

  return (
    <section
      className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm"
      aria-labelledby="people-contribution-title"
    >
      <header className="flex flex-col gap-3 border-b border-[var(--border-light)] px-5 py-4 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 id="people-contribution-title" className="text-lg font-extrabold text-[var(--text-primary)]">
              People Contribution Analysis
            </h2>
            <Info size={14} className="text-[var(--text-faint)]" />
          </div>
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            Employees contributing to the {analysis.kpi_label} gap in the selected scope.
          </p>
        </div>
        <div className="flex max-w-full gap-1 overflow-x-auto">
          {tabs.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => { setTab(item.key); setPage(1); }}
              className={`whitespace-nowrap border-b-2 px-3 py-2 text-xs font-extrabold ${
                tab === item.key
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]'
              }`}
            >
              {item.label} ({item.count})
            </button>
          ))}
        </div>
      </header>

      <div className="grid gap-4 p-3 lg:grid-cols-[minmax(240px,0.72fr)_minmax(0,1.8fr)]">
        <aside className="rounded-xl border border-[var(--border-light)] p-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-xs font-extrabold text-[var(--text-primary)]">Top negative contributors</h3>
            <select
              aria-label="Top contributors count"
              value={topCount}
              onChange={(event) => setTopCount(Number(event.target.value))}
              className="rounded-lg border border-[var(--input-border)] bg-[var(--input-bg)] px-2 py-1 text-xs font-bold"
            >
              <option value={5}>Top 5</option>
              <option value={10}>Top 10</option>
            </select>
          </div>
          <div className="mt-4 space-y-4">
            {negativeRows.length ? negativeRows.map((row, index) => (
              <button
                key={`${row.team}-${row.employee_id}-${row.performance_level}-${row.position}`}
                type="button"
                onClick={() => onOpenEmployee(row.employee_id, row.performance_level)}
                className="grid w-full grid-cols-[24px_minmax(88px,1fr)_minmax(70px,1.2fr)_52px] items-center gap-2 text-left"
              >
                <span className="grid h-6 w-6 place-items-center rounded-full bg-rose-500/10 text-[10px] font-black text-rose-600">
                  {index + 1}
                </span>
                <span className="min-w-0">
                  <strong className="block truncate text-[11px] text-[var(--text-primary)]">{row.employee_name}</strong>
                  <span className="block truncate text-[9px] text-[var(--text-muted)]">{row.position}</span>
                </span>
                <span className="h-2 overflow-hidden rounded-full bg-[var(--bg-sunken)]">
                  <span
                    className="block h-full rounded-full bg-gradient-to-r from-rose-400 to-rose-600"
                    style={{ width: `${Math.max(8, (Math.abs(row.weighted_impact ?? 0) / maxNegativeImpact) * 100)}%` }}
                  />
                </span>
                <strong className="text-right text-[10px] text-rose-600">{signedValue(row.weighted_impact)}</strong>
              </button>
            )) : (
              <p className="py-10 text-center text-xs text-[var(--text-muted)]">No negative contributors for this KPI.</p>
            )}
          </div>
          <p className="mt-5 border-t border-[var(--border-light)] pt-3 text-center text-[9px] text-[var(--text-muted)]">
            Weighted impact on {analysis.kpi_label}
          </p>
        </aside>

        <div className="min-w-0 overflow-hidden rounded-xl border border-[var(--border-light)]">
          <div className="border-b border-[var(--border-light)] px-4 py-3">
            <h3 className="text-xs font-extrabold text-[var(--text-primary)]">Detailed view</h3>
          </div>
          {pagedRows.length ? (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[860px] text-left">
                  <thead>
                    <tr className="bg-[var(--bg-sunken)]/50 text-[9px] font-extrabold uppercase text-[var(--text-faint)]">
                      <th className="px-3 py-3">#</th>
                      <th className="px-3 py-3">Employee</th>
                      <th className="px-3 py-3">Position</th>
                      <th className="px-3 py-3">Current</th>
                      <th className="px-3 py-3">Target</th>
                      <th className="px-3 py-3">Gap</th>
                      <th className="px-3 py-3">Weighted impact</th>
                      <th className="px-3 py-3">Trend</th>
                      <th className="px-3 py-3">Severity</th>
                      <th className="px-3 py-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pagedRows.map((row, index) => {
                      const trendPositive = row.trend !== null && (
                        row.direction === 'lower_better' ? row.trend < 0 : row.trend > 0
                      );
                      return (
                        <tr key={`${row.team}-${row.employee_id}-${row.performance_level}-${row.position}`} className="border-t border-[var(--border-light)] text-[10px]">
                          <td className="px-3 py-3 font-bold text-[var(--text-muted)]">{(currentPage - 1) * pageSize + index + 1}</td>
                          <td className="px-3 py-3">
                            <strong className="block text-[var(--text-primary)]">{row.employee_name}</strong>
                            <span className="text-[9px] text-[var(--text-muted)]">{row.employee_id}</span>
                          </td>
                          <td className="px-3 py-3 text-[var(--text-secondary)]">{row.position}</td>
                          <td className="px-3 py-3 font-bold text-[var(--text-primary)]">{formatContributionMetric(row.current_value, row.target_value, row.unit)}</td>
                          <td className="px-3 py-3 text-[var(--text-secondary)]">{formatContributionMetric(row.target_value, row.target_value, row.unit)}</td>
                          <td className={`px-3 py-3 font-extrabold ${impactColor(row.gap)}`}>{formatContributionMetric(row.gap, row.target_value, row.unit, true)}</td>
                          <td className={`px-3 py-3 font-extrabold ${impactColor(row.weighted_impact)}`}>{signedValue(row.weighted_impact)}</td>
                          <td className={`px-3 py-3 font-bold ${row.trend === null ? 'text-[var(--text-muted)]' : trendPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
                            {row.trend === null ? 'N/A' : (
                              <span className="inline-flex items-center gap-1">
                                {row.trend > 0 ? <ArrowUp size={11} /> : <ArrowDown size={11} />}
                                {signedValue(row.trend, row.unit === '%' ? '%' : '')}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-3">
                            <span className={`rounded-full px-2 py-1 text-[9px] font-extrabold ${severityClasses[row.severity] || severityClasses['Data issue']}`}>
                              {row.severity}
                            </span>
                          </td>
                          <td className="px-3 py-3 text-right">
                            {renderEmployeeActions(row)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between border-t border-[var(--border-light)] px-4 py-3 text-xs text-[var(--text-muted)]">
                <span>Showing {(currentPage - 1) * pageSize + 1}–{Math.min(currentPage * pageSize, filteredRows.length)} of {filteredRows.length} employees</span>
                <span className="flex items-center gap-2">
                  <button type="button" aria-label="Previous people page" disabled={currentPage === 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="grid h-8 w-8 place-items-center rounded-lg border border-[var(--border-light)] disabled:opacity-40"><ChevronLeft size={14} /></button>
                  <strong className="grid h-8 min-w-8 place-items-center rounded-lg bg-blue-600 px-2 text-white">{currentPage}</strong>
                  <button type="button" aria-label="Next people page" disabled={currentPage === totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))} className="grid h-8 w-8 place-items-center rounded-lg border border-[var(--border-light)] disabled:opacity-40"><ChevronRight size={14} /></button>
                </span>
              </div>
            </>
          ) : (
            <p className="px-6 py-16 text-center text-sm text-[var(--text-muted)]">No employees match this contribution view.</p>
          )}
        </div>
      </div>

      <footer className="border-t border-[var(--border-light)] bg-[var(--bg-sunken)]/35 px-5 py-3 text-[10px] text-[var(--text-muted)]">
        Weighted impact is each employee&apos;s share of the selected KPI score gap using the active weight, actual, target, and scoring direction.
      </footer>
    </section>
  );
}
