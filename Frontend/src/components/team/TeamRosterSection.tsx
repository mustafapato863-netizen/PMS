import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Search, Award, AlertTriangle, ChevronLeft, ChevronRight,
  ChevronsUpDown, ChevronUp, ChevronDown, Download, Plus, User
} from 'lucide-react';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import type { PerformanceLevelFilter, PMSAction } from '../../types';
import { GRADE_PALETTE, gradeTokenVar } from '../../constants/grades';
import EmployeeRowActions from './EmployeeRowActions';
import RosterViewTiles from './RosterViewTiles';

const PAGE_SIZE = 15;
const NARROW_QUERY = '(max-width: 767px)';
const MAIN_ISSUE_SUFFIX = /\s*\(main issue\)\s*$/i;

// ─── Sort Icon ────────────────────────────────────────────────────────────────
const SortIcon = ({ col, sortCol, sortDir }: { col: string; sortCol: string; sortDir: 'asc' | 'desc' }) => {
  if (col !== sortCol) return <ChevronsUpDown size={13} className="text-[var(--text-faint)]" />;
  return sortDir === 'asc' ? <ChevronUp size={13} className="text-blue-600 dark:text-blue-400" /> : <ChevronDown size={13} className="text-blue-600 dark:text-blue-400" />;
};

// ─── Trend Cell ───────────────────────────────────────────────────────────────
const TrendCell = ({ row, prevRows }: { row: TeamAgentRow; prevRows: Map<string, { score: number }> }) => {
  const prev = prevRows.get(row.id);
  if (!prev || !row.score) {
    return (
      <span className="text-xs font-semibold text-[var(--text-faint)]" title="No previous month">
        —<span className="sr-only"> No previous month</span>
      </span>
    );
  }
  const delta = row.score - prev.score;
  if (delta > 2) return <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400">↑ +{delta.toFixed(1)}%</span>;
  if (delta < -2) return <span className="text-xs font-bold text-red-500 dark:text-red-400">↓ {delta.toFixed(1)}%</span>;
  return <span className="text-xs font-bold text-[var(--text-muted)]">→ Stable</span>;
};

/** Score and grade as one chip in the grade's tone, e.g. "94.0% · B". */
function ScoreChip({ row }: { row: TeamAgentRow }) {
  const grade = row.gradeClass;
  return (
    <span
      className="inline-flex shrink-0 items-center whitespace-nowrap rounded-md border px-2 py-0.5 text-xs font-semibold tabular-nums"
      style={{
        background: gradeTokenVar(grade, 'badge-bg'),
        color: gradeTokenVar(grade, 'badge-text'),
        borderColor: gradeTokenVar(grade, 'border'),
      }}
    >
      {`${(row.score || 0).toFixed(1)}% · ${grade}`}
    </span>
  );
}

/** Status as a coloured dot plus the grade's status word. */
function StatusText({ row }: { row: TeamAgentRow }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-semibold text-[var(--text-secondary)]">
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: gradeTokenVar(row.gradeClass, 'solid') }} aria-hidden="true" />
      {GRADE_PALETTE[row.gradeClass].statusLabel}
    </span>
  );
}

/** Root cause on one line: the KPI and direction, with "main issue" as a small muted tag and the full text as tooltip. */
function RootCause({ row, href }: { row: TeamAgentRow; href: string }) {
  if (row.gradeClass === 'A' || row.gradeClass === 'B') {
    return <span className="text-xs font-semibold text-[var(--text-faint)]">No gap</span>;
  }
  const full = row.rootCauseAuto || 'Other';
  const kpi = full.replace(MAIN_ISSUE_SUFFIX, '') || 'Other';
  const isMainIssue = MAIN_ISSUE_SUFFIX.test(full);
  return (
    <Link
      to={href}
      title={full}
      className="flex min-w-0 items-center gap-1.5 text-xs font-semibold text-[var(--text-secondary)] hover:text-blue-600 hover:underline dark:hover:text-blue-400"
    >
      <span className="truncate">{kpi}</span>
      {isMainIssue && (
        <span className="shrink-0 rounded px-1 text-[11px] font-medium text-[var(--text-faint)] ring-1 ring-[var(--border-light)]">main issue</span>
      )}
    </Link>
  );
}

/** True below 768px, where the roster shows one stacked card per employee instead of a table. */
function useNarrowViewport(): boolean {
  const [narrow, setNarrow] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(NARROW_QUERY).matches,
  );
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia(NARROW_QUERY);
    const onChange = () => setNarrow(media.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);
  return narrow;
}

const iconButtonClass = 'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--border-medium)] bg-[var(--bg-surface)] text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 max-md:h-[2.75rem] max-md:w-[2.75rem]';
const cardButtonClass = 'inline-flex min-h-[2.75rem] items-center gap-1.5 rounded-lg border border-[var(--border-medium)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)]';

interface TeamRosterSectionProps {
  showTopBottomToggle: boolean;
  /** Team column only when the page lists more than one team (All Teams, parent or merged views). */
  showTeamColumn?: boolean;
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
  showTeamColumn = false,
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
  const narrow = useNarrowViewport();
  // Same rule as the overflow menu's "Add action" item in EmployeeRowActions.
  const canManageActions = role === 'Admin' || role === 'General Manager' || role === 'Manager';

  const profileHref = (row: TeamAgentRow) =>
    `/employee/${encodeURIComponent(row.id)}?month=${encodeURIComponent(month)}&performance_level=${encodeURIComponent(performanceLevel)}`;

  const rowTeamAverageFor = (row: TeamAgentRow) => {
    const matchingTeamRows = filtered.filter((candidate) => candidate.team === row.team);
    return matchingTeamRows.length > 0
      ? matchingTeamRows.reduce((sum, candidate) => sum + candidate.score, 0) / matchingTeamRows.length
      : teamAverage;
  };

  const renderTable = (agentRows: TeamAgentRow[]) => {
    const columns: Array<{ col: 'name' | 'score' | 'status' | null; label: string; width: string; show: boolean }> = [
      { col: 'name', label: 'Employee', width: showTeamColumn ? 'w-[24%]' : 'w-[30%]', show: true },
      { col: null, label: 'Team', width: 'w-[14%]', show: showTeamColumn },
      { col: 'score', label: 'Score', width: 'w-[13%]', show: true },
      { col: 'status', label: 'Status', width: 'w-[12%]', show: true },
      { col: null, label: 'Root cause', width: showTeamColumn ? 'w-[20%]' : 'w-[24%]', show: true },
      { col: null, label: 'Trend', width: 'w-[9%]', show: true },
      { col: null, label: 'Actions', width: 'w-[140px]', show: true },
    ];
    const visibleColumns = columns.filter((column) => column.show);
    const avatarTones = [
      'bg-blue-500/10 text-blue-600 border-blue-500/10',
      'bg-emerald-500/10 text-emerald-600 border-emerald-500/10',
      'bg-violet-500/10 text-violet-600 border-violet-500/10',
      'bg-orange-500/10 text-orange-600 border-orange-500/10',
    ];

    return (
      <div className="max-h-[70vh] w-full overflow-auto rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)]">
        <table className="w-full min-w-[44rem] table-fixed border-collapse">
          <thead className="sticky top-0 z-10">
            <tr className="border-b border-[var(--border-light)] bg-[var(--bg-sunken)]">
              {visibleColumns.map(({ col, label, width }) => (
                <th
                  key={label}
                  scope="col"
                  onClick={col ? () => toggleSort(col) : undefined}
                  aria-sort={col && col === sortCol ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
                  className={`${width} h-10 px-3 text-left text-xs font-semibold text-[var(--text-muted)] ${
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
                <td colSpan={visibleColumns.length} className="py-12 text-center text-sm font-medium text-[var(--text-muted)]">
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

                return (
                  <tr
                    key={`${row.id}_${row.month}_${idx}`}
                    className="h-[3rem] border-b border-[var(--border-light)] transition-colors last:border-b-0 hover:bg-blue-500/[0.035]"
                  >
                    <td className="px-3">
                      <div className="flex min-w-0 items-center gap-2.5">
                        <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border text-xs font-semibold ${avatarTones[idx % avatarTones.length]}`} aria-hidden="true">
                          {initials}
                        </div>
                        <div className="min-w-0">
                          <Link
                            to={profileHref(row)}
                            aria-label={row.name}
                            title={row.name}
                            className="block truncate text-sm font-semibold leading-tight text-[var(--text-primary)] transition-colors hover:text-blue-600 dark:hover:text-blue-400"
                          >
                            {row.name}
                          </Link>
                          <div className="truncate text-xs text-[var(--text-muted)]">{row.id}</div>
                        </div>
                      </div>
                    </td>

                    {showTeamColumn && (
                      <td className="px-3">
                        <span className="block truncate text-xs text-[var(--text-secondary)]" title={row.team}>{row.team}</span>
                      </td>
                    )}

                    <td className="px-3">
                      <ScoreChip row={row} />
                    </td>

                    <td className="px-3">
                      <StatusText row={row} />
                    </td>

                    <td className="px-3">
                      <RootCause row={row} href={profileHref(row)} />
                    </td>

                    <td className="px-3">
                      <TrendCell row={row} prevRows={prevRows} />
                    </td>

                    <td className="px-3">
                      <div className="flex items-center justify-end gap-1.5">
                        {canManageActions && (
                          <button
                            type="button"
                            onClick={() => onAddAction(row)}
                            aria-label={`Add action for ${row.name}`}
                            title="Add action"
                            className={iconButtonClass}
                          >
                            <Plus size={16} aria-hidden="true" />
                          </button>
                        )}
                        <Link
                          to={profileHref(row)}
                          aria-label={`Open profile for ${row.name}`}
                          title="Open profile"
                          className={iconButtonClass}
                        >
                          <User size={16} aria-hidden="true" />
                        </Link>
                        <EmployeeRowActions
                          row={row}
                          role={role}
                          month={month}
                          performanceLevel={performanceLevel}
                          teamAverage={rowTeamAverageFor(row)}
                          actions={employeeActions}
                          onAddAction={onAddAction}
                          onEmployeeChanged={onEmployeeChanged}
                        />
                      </div>
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

  /** Below 768px: one stacked card per employee, with the two most used actions as labelled buttons. */
  const renderCards = (agentRows: TeamAgentRow[]) => {
    if (agentRows.length === 0) {
      return <div className="rounded-xl border border-dashed border-[var(--border-medium)] p-5 text-center text-sm text-[var(--text-muted)]">No employees found.</div>;
    }
    return (
      <div className="flex flex-col gap-2.5">
        {agentRows.map((row, idx) => {
          const employeeActions = getActionsForEmployee(row.id);
          return (
            <article key={`${row.id}_${row.month}_${idx}`} className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-3 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <Link
                    to={profileHref(row)}
                    aria-label={row.name}
                    title={row.name}
                    className="block truncate text-sm font-semibold text-[var(--text-primary)] hover:text-blue-600 dark:hover:text-blue-400"
                  >
                    {row.name}
                  </Link>
                  <div className="truncate text-xs text-[var(--text-muted)]">
                    {row.id}{showTeamColumn ? ` · ${row.team}` : ''}
                  </div>
                </div>
                <ScoreChip row={row} />
              </div>
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                <StatusText row={row} />
                <TrendCell row={row} prevRows={prevRows} />
              </div>
              <div className="mt-2 min-w-0">
                <RootCause row={row} href={profileHref(row)} />
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {canManageActions && (
                  <button
                    type="button"
                    onClick={() => onAddAction(row)}
                    aria-label={`Add action for ${row.name}`}
                    className={cardButtonClass}
                  >
                    <Plus size={15} aria-hidden="true" />
                    Add action
                  </button>
                )}
                <Link
                  to={profileHref(row)}
                  aria-label={`Open profile for ${row.name}`}
                  className={cardButtonClass}
                >
                  <User size={15} aria-hidden="true" />
                  Open profile
                </Link>
                <div className="ml-auto">
                  <EmployeeRowActions
                    row={row}
                    role={role}
                    month={month}
                    performanceLevel={performanceLevel}
                    teamAverage={rowTeamAverageFor(row)}
                    actions={employeeActions}
                    onAddAction={onAddAction}
                    onEmployeeChanged={onEmployeeChanged}
                  />
                </div>
              </div>
            </article>
          );
        })}
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
                    to={profileHref(row)}
                    className="block truncate text-xs font-extrabold leading-snug text-[var(--text-primary)] hover:text-blue-600 dark:hover:text-blue-400 sm:text-sm"
                    title={row.name}
                  >
                    {row.name}
                  </Link>
                  <div className="mt-1 truncate text-xs font-semibold text-[var(--text-faint)]">
                    {row.id}
                  </div>
                </div>

                <div className="text-right">
                  <div className={`text-sm font-extrabold sm:text-base ${
                    isTop ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-500 dark:text-rose-400'
                  }`}>
                    {score.toFixed(1)}%
                  </div>
                  <div className={`mt-1 whitespace-nowrap text-xs font-bold ${
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
    <div className="glass-panel rounded-xl p-4 shadow-sm sm:p-5">
      <div className="mb-3 flex flex-col gap-1">
        <h3 className="heading-3">{isAllView ? 'Employee roster' : 'Top and bottom performers'}</h3>
        {showTopBottomToggle && (
          <p className="text-xs font-medium text-[var(--text-secondary)]">
            {rosterView === 'top_bottom' ? 'Top and bottom performing agents' : 'All active agents'}
          </p>
        )}
      </div>

      {/* One compact toolbar: search, the view switch and export. Wraps on narrow screens. */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {isAllView && (
          <div className="relative min-w-[12rem] flex-1 sm:max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-faint)]" size={16} aria-hidden="true" />
            <input
              aria-label="Search employees"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name, ID..."
              className="h-9 w-full rounded-lg border border-[var(--border-medium)] bg-[var(--bg-surface)] pl-9 pr-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-faint)] focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500/10"
            />
          </div>
        )}
        {showTopBottomToggle && (
          <div className="ml-auto">
            <RosterViewTiles value={rosterView} onChange={setRosterView} />
          </div>
        )}
        {isAllView && canExport && (
          <button
            type="button"
            onClick={onExport}
            title="Export to Excel"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border-medium)] bg-[var(--bg-surface)] px-3 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)]"
          >
            <Download size={15} aria-hidden="true" />
            Export
          </button>
        )}
      </div>

      {isAllView ? (
        <>
          {narrow ? renderCards(paginated) : renderTable(paginated)}

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
                <h4 className="truncate text-sm font-semibold text-emerald-700 dark:text-emerald-400">Top 3 performers</h4>
                <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">Highest performance scores</p>
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
                <h4 className="truncate text-sm font-semibold text-rose-600 dark:text-rose-400">Bottom 3 performers</h4>
                <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">Lowest performance scores</p>
              </div>
            </div>

            {rosterData.allMeetStandards ? (
              /* Encouraging Card */
              <div className="flex flex-col items-center justify-center p-8 bg-emerald-500/10 border border-emerald-500/20 rounded-2xl text-center min-h-[126px] shadow-sm">
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
