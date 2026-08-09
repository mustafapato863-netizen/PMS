import { Link } from 'react-router-dom';
import {
  Search, Award, AlertTriangle, ChevronLeft, ChevronRight,
  ChevronsUpDown, ChevronUp, ChevronDown, UsersRound,
  ArrowLeftRight, Download, SlidersHorizontal
} from 'lucide-react';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import type { PerformanceLevelFilter } from '../../types';
import type { PMSAction } from '../../types';
import { GRADE_PALETTE } from '../../constants/grades';
import EmployeeRowActions from './EmployeeRowActions';

const PAGE_SIZE = 15;

// ─── Sort Icon ────────────────────────────────────────────────────────────────
const SortIcon = ({ col, sortCol, sortDir }: { col: string; sortCol: string; sortDir: 'asc' | 'desc' }) => {
  if (col !== sortCol) return <ChevronsUpDown size={13} className="text-[var(--text-faint)]" />;
  return sortDir === 'asc' ? <ChevronUp size={13} className="text-blue-600 dark:text-blue-400" /> : <ChevronDown size={13} className="text-blue-600 dark:text-blue-400" />;
};

// ─── Trend Cell ───────────────────────────────────────────────────────────────
const TrendCell = ({ row, prevRows }: { row: TeamAgentRow; prevRows: Map<string, { score: number }> }) => {
  const prev = prevRows.get(row.id);
  if (!prev || !row.score) return <span className="text-[var(--text-faint)] text-xs font-semibold">→ –</span>;
  const delta = row.score - prev.score;
  if (delta > 2) return <span className="text-emerald-600 dark:text-emerald-400 font-bold text-xs">↑ +{delta.toFixed(1)}%</span>;
  if (delta < -2) return <span className="text-red-500 dark:text-red-400 font-bold text-xs">↓ {delta.toFixed(1)}%</span>;
  return <span className="text-[var(--text-muted)] font-bold text-xs">→ Stable</span>;
};

interface TeamRosterSectionProps {
  showTopBottomToggle: boolean;
  rosterView: 'top_bottom' | 'all';
  setRosterView: (view: 'top_bottom' | 'all') => void;
  search: string;
  setSearch: (s: string) => void;
  page: number;
  setPage: (p: number | ((prev: number) => number)) => void;
  totalPages: number;
  paginated: TeamAgentRow[];
  filtered: TeamAgentRow[];
  rosterData: {
    top3: TeamAgentRow[];
    bottom3: TeamAgentRow[];
    allMeetStandards: boolean;
  };
  role: string;
  month: string;
  performanceLevel: PerformanceLevelFilter;
  prevRows: Map<string, { score: number }>;
  teamAverage: number;
  getActionsForEmployee: (id: string) => PMSAction[];
  onAddAction: (row: TeamAgentRow) => void;
  onEmployeeChanged?: () => void;
  sortCol: 'score' | 'name' | 'status';
  sortDir: 'asc' | 'desc';
  toggleSort: (col: 'score' | 'name' | 'status') => void;
  canExport: boolean;
  onExport: () => void;
}

const TeamRosterSection = ({
  showTopBottomToggle,
  rosterView,
  setRosterView,
  search,
  setSearch,
  page,
  setPage,
  totalPages,
  paginated,
  filtered,
  rosterData,
  role,
  month,
  performanceLevel,
  prevRows,
  teamAverage,
  getActionsForEmployee,
  onAddAction,
  onEmployeeChanged,
  sortCol,
  sortDir,
  toggleSort,
  canExport,
  onExport,
}: TeamRosterSectionProps) => {

  const renderAgentTable = (agentRows: TeamAgentRow[]) => {
    const columns: Array<{ col: 'name' | 'score' | 'status' | null; label: string }> = [
      { col: 'name', label: 'Employee' },
      { col: null, label: 'Team' },
      { col: 'score', label: 'Score' },
      { col: null, label: 'Grade' },
      { col: null, label: 'Trend' },
      { col: 'status', label: 'Status' },
      { col: null, label: 'Root Cause' },
      { col: null, label: 'Actions' },
    ];
    const avatarTones = [
      'bg-blue-500/10 text-blue-600 border-blue-500/10',
      'bg-emerald-500/10 text-emerald-600 border-emerald-500/10',
      'bg-violet-500/10 text-violet-600 border-violet-500/10',
      'bg-orange-500/10 text-orange-600 border-orange-500/10',
    ];

    return (
      <div className="w-full overflow-x-auto rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)]">
        <table className="w-full min-w-[1080px] border-collapse">
          <thead>
            <tr className="border-b border-[var(--border-light)] bg-[var(--bg-sunken)]/40">
              {columns.map(({ col, label }) => (
                <th
                  key={label}
                  onClick={col ? () => toggleSort(col) : undefined}
                  className={`px-4 py-4 text-left text-[11px] font-extrabold uppercase tracking-[0.08em] text-[var(--text-faint)] ${
                    col ? 'cursor-pointer select-none hover:text-[var(--text-primary)]' : ''
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    {label}
                    {col && <SortIcon col={col} sortCol={sortCol} sortDir={sortDir} />}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {agentRows.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-12 text-center text-sm font-medium text-[var(--text-muted)]">
                  No employees found.
                </td>
              </tr>
            ) : (
              agentRows.map((row, idx) => {
                const employeeActions = getActionsForEmployee(row.id);
                const initials = row.name
                  .trim()
                  .split(/\s+/)
                  .slice(0, 2)
                  .map((part) => part.charAt(0).toUpperCase())
                  .join('') || '?';
                const gradePresentation = GRADE_PALETTE[row.gradeClass];
                const matchingTeamRows = filtered.filter((candidate) => candidate.team === row.team);
                const rowTeamAverage = matchingTeamRows.length > 0
                  ? matchingTeamRows.reduce((sum, candidate) => sum + candidate.score, 0) / matchingTeamRows.length
                  : teamAverage;

                return (
                  <tr
                    key={`${row.id}_${row.month}_${idx}`}
                    className="border-b border-[var(--border-light)] transition-colors last:border-b-0 hover:bg-blue-500/[0.035]"
                  >
                    <td className="px-4 py-4">
                      <div className="flex min-w-[250px] items-center gap-3">
                        <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border text-sm font-extrabold ${avatarTones[idx % avatarTones.length]}`}>
                          {initials}
                        </div>
                        <div className="min-w-0">
                          <Link
                            to={`/employee/${row.id}?month=${encodeURIComponent(month)}&performance_level=${encodeURIComponent(performanceLevel)}`}
                            className="block max-w-[240px] truncate text-sm font-extrabold text-[var(--text-primary)] transition-colors hover:text-blue-600 dark:hover:text-blue-400"
                            title={row.name}
                          >
                            {row.name}
                          </Link>
                          <div className="mt-1 text-xs font-semibold text-[var(--text-faint)]">{row.id}</div>
                        </div>
                      </div>
                    </td>

                    <td className="px-4 py-4">
                      <div className="flex max-w-[150px] items-center gap-2 text-xs font-bold text-[var(--text-secondary)]">
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-violet-500/10 text-violet-600 dark:text-violet-400">
                          <ArrowLeftRight size={14} />
                        </span>
                        <span className="line-clamp-2">{row.team}</span>
                      </div>
                    </td>

                    <td className="px-4 py-4">
                      <span className={`score-badge score-grade-${row.gradeClass}`}>
                        {(row.score || 0).toFixed(1)}%
                      </span>
                    </td>

                    <td className="px-4 py-4">
                      <span className={`grade-badge grade-${row.gradeClass} inline-flex h-8 min-w-8 items-center justify-center rounded-lg px-2 text-xs font-extrabold`}>
                        {row.gradeClass}
                      </span>
                    </td>

                    <td className="px-4 py-4">
                      <TrendCell row={row} prevRows={prevRows} />
                    </td>

                    <td className="px-4 py-4">
                      <span className={`grade-status-badge status-grade-${row.gradeClass}`}>
                        <span className="grade-status-dot" />
                        {gradePresentation.statusLabel}
                      </span>
                    </td>

                    <td className="px-4 py-4">
                      {row.gradeClass === 'A' || row.gradeClass === 'B' ? (
                        <span className="text-xs font-semibold text-[var(--text-faint)]">No gap</span>
                      ) : (
                        <div className="max-w-[150px]">
                          <Link
                            to={`/employee/${row.id}?month=${encodeURIComponent(month)}&performance_level=${encodeURIComponent(performanceLevel)}`}
                            className="line-clamp-1 text-xs font-bold text-[var(--text-secondary)] hover:text-blue-600 hover:underline dark:hover:text-blue-400"
                            title={row.rootCauseAuto || 'Other'}
                          >
                            {row.rootCauseAuto || 'Other'}
                          </Link>
                          <div className="mt-1 text-[10px] font-semibold text-[var(--text-faint)]">Primary issue</div>
                        </div>
                      )}
                    </td>

                    <td className="px-4 py-4">
                      <EmployeeRowActions
                        row={row}
                        role={role}
                        month={month}
                        performanceLevel={performanceLevel}
                        teamAverage={rowTeamAverage}
                        actions={employeeActions}
                        onAddAction={onAddAction}
                        onEmployeeChanged={onEmployeeChanged}
                      />
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    );
  };

  const renderCompactRoster = (agentRows: TeamAgentRow[], tone: 'top' | 'bottom') => {
    if (agentRows.length === 0) {
      return (
        <div className="rounded-2xl border border-dashed border-[var(--border-medium)] bg-[var(--bg-sunken)]/30 p-5 text-sm text-[var(--text-secondary)]">
          {tone === 'bottom'
            ? 'No additional below-target employees outside the Top 3.'
            : 'No employees found.'}
        </div>
      );
    }

    return (
      <div className="space-y-2.5">
        {agentRows.map((row, idx) => {
          const score = row.score || 0;
          const previousScore = prevRows.get(row.id)?.score;
          const delta = previousScore === undefined ? null : score - previousScore;
          const isTop = tone === 'top';
          const accentColor = isTop ? '#10b981' : '#f43f5e';
          const sparkStartY = delta === null || Math.abs(delta) <= 2 ? 14 : delta > 0 ? 20 : 8;
          const sparkEndY = delta === null || Math.abs(delta) <= 2 ? 14 : delta > 0 ? 8 : 20;
          const initial = row.name.trim().charAt(0).toUpperCase() || '?';

          return (
            <div
              key={`${row.id}_${row.month}_${idx}`}
              className="relative overflow-hidden rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-3 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md sm:px-4"
            >
              <span
                className={`absolute inset-y-0 left-0 w-0.5 ${isTop ? 'bg-emerald-500' : 'bg-rose-500'}`}
                aria-hidden="true"
              />

              <div className="grid grid-cols-[2rem_2.5rem_minmax(0,1fr)_auto] items-center gap-2.5 sm:grid-cols-[2.25rem_2.75rem_minmax(0,1fr)_5.25rem_3.75rem] sm:gap-3">
                <div className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-extrabold sm:h-9 sm:w-9 ${
                  isTop
                    ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                    : 'bg-rose-500/10 text-rose-600 dark:text-rose-300'
                }`}>
                  {idx + 1}
                </div>

                <div className={`flex h-10 w-10 items-center justify-center rounded-xl text-sm font-extrabold sm:h-11 sm:w-11 ${
                  isTop
                    ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                    : 'bg-blue-500/10 text-blue-600 dark:text-blue-300'
                }`}>
                  {initial}
                </div>

                <div className="min-w-0">
                  <Link
                    to={`/employee/${row.id}?month=${encodeURIComponent(month)}&performance_level=${encodeURIComponent(performanceLevel)}`}
                    className="block truncate text-xs font-extrabold leading-snug text-[var(--text-primary)] hover:text-blue-600 dark:hover:text-blue-400 sm:text-sm"
                    title={row.name}
                  >
                    {row.name}
                  </Link>
                  <div className="mt-1 truncate text-[10px] font-semibold text-[var(--text-faint)] sm:text-[11px]">
                    {row.id}
                  </div>
                </div>

                <div className="text-right">
                  <div className={`text-sm font-extrabold sm:text-base ${
                    isTop ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-500 dark:text-rose-400'
                  }`}>
                    {score.toFixed(1)}%
                  </div>
                  <div className={`mt-1 whitespace-nowrap text-[10px] font-bold ${
                    delta === null || Math.abs(delta) <= 2
                      ? 'text-[var(--text-faint)]'
                      : delta > 0
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : 'text-rose-500 dark:text-rose-400'
                  }`}>
                    {delta === null ? 'No trend' : `${delta > 2 ? '↑ +' : delta < -2 ? '↓ ' : '→ '}${Math.abs(delta) <= 2 ? 'Stable' : `${delta.toFixed(1)}%`}`}
                  </div>
                </div>

                <svg className="hidden h-7 w-14 sm:block" viewBox="0 0 56 28" role="img" aria-label="Score trend">
                  <path d={`M 3 ${sparkStartY} L 22 ${sparkStartY} L 38 ${sparkEndY} L 53 ${sparkEndY}`} fill="none" stroke={accentColor} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                  <circle cx="3" cy={sparkStartY} r="1.8" fill={accentColor} />
                  <circle cx="53" cy={sparkEndY} r="2.2" fill={accentColor} />
                </svg>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const paginationStart = Math.min(
    Math.max(page - 2, 1),
    Math.max(totalPages - 4, 1),
  );
  const visiblePages = Array.from(
    { length: Math.min(totalPages, 5) },
    (_, index) => paginationStart + index,
  );
  const isAllView = !showTopBottomToggle || rosterView === 'all';

  return (
    <div className="glass-panel rounded-xl p-4 shadow-sm sm:p-6">
      <div className="mb-5 flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div className="flex items-center gap-3">
          <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl ${
            isAllView
              ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
              : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
          }`}>
            {isAllView ? <UsersRound size={24} /> : <Award size={23} />}
          </div>
          <div>
            <h3 className="heading-3">{isAllView ? 'Employee Roster' : 'Top & Bottom Performers'}</h3>
            {showTopBottomToggle && (
              <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">
                {rosterView === 'top_bottom' ? 'Top and bottom performing agents' : 'All active agents'}
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          {/* Search Input */}
          {isAllView && (
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--text-faint)]" size={18} />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name, ID..."
                className="w-full rounded-xl border border-[var(--border-medium)] bg-[var(--bg-surface)] py-3 pl-11 pr-4 text-sm font-medium text-[var(--text-primary)] shadow-sm transition-all placeholder:text-[var(--text-faint)] focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500/10"
              />
            </div>
          )}

          {/* Dropdown Selector */}
          {showTopBottomToggle && (
            <div className="relative min-w-[210px]">
              <SlidersHorizontal className="pointer-events-none absolute left-3.5 top-1/2 z-10 -translate-y-1/2 text-blue-600 dark:text-blue-400" size={17} />
              <select
                value={rosterView}
                onChange={(e) => setRosterView(e.target.value as 'top_bottom' | 'all')}
                className="w-full cursor-pointer appearance-none rounded-xl border border-[var(--border-medium)] bg-[var(--bg-surface)] py-3 pl-11 pr-10 text-sm font-bold text-[var(--text-primary)] shadow-sm focus:border-blue-500 focus:outline-none"
              >
                <option value="top_bottom">Top/Bottom Performers</option>
                <option value="all">All Employees</option>
              </select>
              <ChevronDown className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-[var(--text-faint)]" size={17} />
            </div>
          )}

          {isAllView && canExport && (
            <button
              type="button"
              onClick={onExport}
              className="flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-bold text-white shadow-sm transition-colors hover:bg-emerald-700"
            >
              <Download size={16} />
              Export Excel
            </button>
          )}
        </div>
      </div>

      {isAllView ? (
        <>
          {renderAgentTable(paginated)}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-5 flex flex-col items-center justify-between gap-3 sm:flex-row">
              <span className="text-xs font-semibold text-[var(--text-secondary)]">
                Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length} employees
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  aria-label="Previous page"
                  disabled={page === 1}
                  className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border border-[var(--border-medium)] text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ChevronLeft size={16} />
                </button>
                {visiblePages.map((pageNumber) => (
                  <button
                    key={pageNumber}
                    onClick={() => setPage(pageNumber)}
                    aria-label={`Page ${pageNumber}`}
                    aria-current={page === pageNumber ? 'page' : undefined}
                    className={`h-9 w-9 cursor-pointer rounded-lg text-xs font-extrabold transition-colors ${
                      page === pageNumber
                        ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                        : 'border border-[var(--border-medium)] text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)]'
                    }`}
                  >
                    {pageNumber}
                  </button>
                ))}
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  aria-label="Next page"
                  disabled={page === totalPages}
                  className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border border-[var(--border-medium)] text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          )}
        </>
      ) : (
        /* Top 3 & Bottom 3 Side-by-Side Grid */
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {/* Top 3 Performers */}
          <div className="space-y-3 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/25 p-3 sm:p-4">
            <div className="flex items-center gap-3 pb-1">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                <Award className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                <h4 className="truncate text-xs font-extrabold uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-400 sm:text-sm">Top 3 Performers</h4>
                <p className="mt-1 text-[11px] font-medium text-[var(--text-secondary)]">Highest performance scores</p>
              </div>
            </div>
            {renderCompactRoster(rosterData.top3, 'top')}
          </div>

          {/* Bottom 3 Performers */}
          <div className="space-y-3 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/25 p-3 sm:p-4">
            <div className="flex items-center gap-3 pb-1">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-rose-500/10 text-rose-500 dark:text-rose-400">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                <h4 className="truncate text-xs font-extrabold uppercase tracking-[0.14em] text-rose-600 dark:text-rose-400 sm:text-sm">Bottom 3 Performers</h4>
                <p className="mt-1 text-[11px] font-medium text-[var(--text-secondary)]">Lowest performance scores</p>
              </div>
            </div>

            {rosterData.allMeetStandards ? (
              /* Encouraging Card */
              <div className="flex flex-col items-center justify-center p-8 bg-emerald-500/10 border border-emerald-500/20 rounded-2xl text-center min-h-[140px] shadow-sm">
                <div className="w-12 h-12 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-600 dark:text-emerald-400 mb-3 shadow-inner">
                  <Award className="w-6 h-6" />
                </div>
                <h5 className="text-sm font-bold text-emerald-700 dark:text-emerald-450 mb-1">
                  All Active Agents Meet Corporate Standards
                </h5>
                <p className="text-xs text-emerald-600 dark:text-emerald-400/90 font-medium">
                  Every active agent has achieved a grade of A or B (score &ge; 80%).
                </p>
              </div>
            ) : (
              renderCompactRoster(rosterData.bottom3, 'bottom')
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default TeamRosterSection;
