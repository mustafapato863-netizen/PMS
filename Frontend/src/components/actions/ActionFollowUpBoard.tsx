import { Fragment, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertCircle,
  ArrowUpDown,
  CalendarDays,
  ChevronDown,
  ChevronUp,
  Clock,
  RefreshCw,
  Search,
  Trash2,
  UserRound,
} from 'lucide-react';
import CustomDropdown from '../common/CustomDropdown';
import { useActionOwners, useActionStore, useFollowUp, useUpdateActionStatus } from '../../hooks/useActionStore';
import { useUserRole } from '../../context/RoleContext';
import type { ActionStatus, PMSAction } from '../../types';
import { canDeleteCorrectiveAction, dueBadgeLabel, todayIso } from './dueBadge';
import { ActionStatusMenu, StatusPill } from './ActionStatusMenu';
import { EMPTY_FOLLOW_UP_SUMMARY, type FollowUpFilters, type FollowUpSummary } from './followUpTypes';
import { executiveFunctionForTeam } from '../../features/executive/functions';

export type { FollowUpFilters, FollowUpSummary };
export { EMPTY_FOLLOW_UP_SUMMARY };

const STATE_OPTIONS = [
  { value: '', label: 'All states' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'due_soon', label: 'Due this week' },
  { value: 'upcoming', label: 'Upcoming' },
  { value: 'no_due_date', label: 'No due date' },
  { value: 'completed', label: 'Completed' },
  { value: 'cancelled', label: 'Cancelled' },
];

type SortMode = 'urgency' | 'due_date' | 'employee' | 'status';

const SORT_OPTIONS: Array<{ value: SortMode; label: string }> = [
  { value: 'urgency', label: 'Sort: Most urgent' },
  { value: 'due_date', label: 'Sort: Due date' },
  { value: 'employee', label: 'Sort: Employee A–Z' },
  { value: 'status', label: 'Sort: Status' },
];

const LONG_ACTION_THRESHOLD = 140;

interface ActionFollowUpBoardProps {
  actions: PMSAction[];
  summary: FollowUpSummary;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  canEdit: boolean;
  owners: Array<{ id: string; name: string }>;
  teams: string[];
  months: string[];
  filters: FollowUpFilters;
  onFiltersChange: (filters: FollowUpFilters) => void;
  onStatusChange: (id: string, update: { status: ActionStatus; completion_note?: string; due_date?: string }) => Promise<unknown> | void;
  canDelete?: boolean;
  onDeleteAction?: (action: PMSAction) => Promise<boolean> | boolean;
}

function badgeClass(action: PMSAction): string {
  if (action.follow_up_state === 'overdue' || action.is_overdue) {
    return 'border-rose-500/25 bg-rose-500/10 text-rose-700';
  }
  if (action.follow_up_state === 'due_soon') {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-800';
  }
  if (action.follow_up_state === 'completed' || action.status === 'Completed') {
    return 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700';
  }
  return 'border-[var(--exec-card-border)] bg-[var(--exec-chip-bg)] text-[var(--text-secondary)]';
}

function rowAccentClass(action: PMSAction): string {
  if (action.follow_up_state === 'overdue' || action.is_overdue) return 'border-l-[3px] border-l-rose-500/80';
  if (action.follow_up_state === 'due_soon') return 'border-l-[3px] border-l-amber-400/80';
  if (action.follow_up_state === 'completed' || action.status === 'Completed') return 'border-l-[3px] border-l-emerald-500/65';
  return 'border-l-[3px] border-l-transparent';
}

function actionTypeBadgeClass(type?: string | null): string {
  const normalized = String(type || '').trim().toLowerCase();
  if (normalized.includes('pip') || normalized.includes('escalat')) {
    return 'border-rose-500/25 bg-rose-500/10 text-rose-700';
  }
  if (normalized.includes('warn')) {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-800';
  }
  if (normalized.includes('train')) {
    return 'border-violet-500/25 bg-violet-500/10 text-violet-700';
  }
  if (normalized.includes('coach')) {
    return 'border-sky-500/25 bg-sky-500/10 text-sky-700';
  }
  if (normalized.includes('recogn')) {
    return 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700';
  }
  return 'border-[var(--exec-card-border)] bg-[var(--exec-chip-bg)] text-[var(--text-secondary)]';
}

function initialsFor(name?: string | null): string {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'PL';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

function formatHumanDate(isoDate?: string | null): string {
  if (!isoDate) return 'No due date';
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate.trim());
  if (!match) return isoDate;
  const year = Number(match[1]);
  const monthIdx = Number(match[2]) - 1;
  const day = Number(match[3]);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const monthName = months[monthIdx];
  if (!monthName || !Number.isFinite(day)) return isoDate;
  return `${monthName} ${day}, ${year}`;
}

function urgencyRank(action: PMSAction): number {
  if (action.status === 'Completed') return 4;
  if (action.status === 'Cancelled') return 5;
  if (action.follow_up_state === 'overdue' || action.is_overdue) return 0;
  if (action.follow_up_state === 'due_soon') return 1;
  if (action.due_date) return 2;
  return 3;
}

function SummaryChip({ label, value, tone, bg, border, accent }: { label: string; value: string | number; tone: string; bg?: string; border?: string; accent?: string }) {
  return (
    <article
      className={`pms-glass-surface relative overflow-hidden rounded-[14px] px-3.5 py-2.5 ${tone}`}
      style={bg ? { background: bg, borderColor: border } : undefined}
    >
      {accent && <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[2.5px]" style={{ background: accent }} />}
      <p className="text-xs font-bold uppercase tracking-wide">{label}</p>
      <p className="mt-1 text-xl font-black text-[var(--text-primary)] tabular-nums">{value}</p>
    </article>
  );
}

function DueBadge({ action }: { action: PMSAction }) {
  const isOverdue = action.follow_up_state === 'overdue' || action.is_overdue;
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-bold leading-5 ${badgeClass(action)}`}>
      {isOverdue && <Clock className="size-3 shrink-0" aria-hidden="true" />}
      <span>{dueBadgeLabel(action.due_date, action.days_to_due)}</span>
    </span>
  );
}

function EmployeeIdentityCell({ action }: { action: PMSAction }) {
  const displayName = action.employee_id
    ? action.employee_name || action.employee_id
    : action.plan?.name || 'Plan action';

  return (
    <div className="flex items-start gap-2.5">
      <span
        aria-hidden="true"
        className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full border border-[var(--insights-accent-border)] bg-[var(--pms-grad-panel-info)] text-xs font-bold text-[var(--insights-accent-text)]"
      >
        {initialsFor(displayName)}
      </span>
      <div className="min-w-0 space-y-1">
        {action.employee_id ? (
          <Link
            to={`/employee/${encodeURIComponent(action.employee_id)}`}
            className="block text-sm font-bold leading-snug text-[var(--insights-heading)] transition-colors hover:text-[var(--insights-accent-text)] hover:underline"
          >
            {displayName}
          </Link>
        ) : (
          <span className="block text-sm font-bold leading-snug text-[var(--insights-heading)]">
            {displayName}
          </span>
        )}
        <span className="inline-flex max-w-full items-center whitespace-nowrap rounded-md border border-[var(--exec-card-border)] bg-[var(--exec-chip-bg)] px-2 py-0.5 text-xs font-medium text-[var(--text-secondary)]">
          {action.team || 'Unassigned'}
        </span>
      </div>
    </div>
  );
}

function ActionDescriptionCell({
  action,
  expanded,
  onToggleExpand,
}: {
  action: PMSAction;
  expanded: boolean;
  onToggleExpand: () => void;
}) {
  const text = action.action_text || '';
  const isLong = text.length > LONG_ACTION_THRESHOLD;
  return (
    <div className="min-w-0 space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span
          className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-md border px-2 py-0.5 text-xs font-semibold leading-4 ${actionTypeBadgeClass(action.action_type)}`}
        >
          {action.action_type || 'Action'}
        </span>
        {action.month && (
          <span className="text-xs font-medium text-[var(--text-muted)]">
            {action.month}{action.year ? ` ${action.year}` : ''}
          </span>
        )}
      </div>
      <p
        className={`text-[13.5px] leading-relaxed text-[var(--text-secondary)] ${
          !expanded && isLong ? 'line-clamp-2' : ''
        }`}
      >
        {text}
      </p>
      {isLong && (
        <button
          type="button"
          onClick={onToggleExpand}
          aria-expanded={expanded}
          className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--insights-accent-text)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent-ring)]"
        >
          <span>{expanded ? 'Show less' : 'Show more'}</span>
          {expanded ? <ChevronUp className="size-3.5" aria-hidden="true" /> : <ChevronDown className="size-3.5" aria-hidden="true" />}
        </button>
      )}
    </div>
  );
}

function DueDateSetter({ action, onStatusChange }: { action: PMSAction; onStatusChange: ActionFollowUpBoardProps['onStatusChange'] }) {
  const [dueDate, setDueDate] = useState('');
  if (action.due_date) {
    return (
      <span
        className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium tabular-nums text-[var(--text-muted)]"
        title={action.due_date}
      >
        <CalendarDays className="size-3.5 shrink-0 opacity-75" aria-hidden="true" />
        <span>{formatHumanDate(action.due_date)}</span>
      </span>
    );
  }
  return (
    <form
      className="flex flex-wrap items-end gap-1.5"
      onSubmit={(event) => {
        event.preventDefault();
        if (!dueDate) return;
        void onStatusChange(action.id, { status: (action.status || 'Open') as ActionStatus, due_date: dueDate });
      }}
    >
      <label className="text-xs font-semibold text-[var(--text-muted)]">
        Set due date
        <input
          aria-label={`Set due date for ${action.action_text}`}
          type="date"
          min={todayIso()}
          value={dueDate}
          onChange={(event) => setDueDate(event.target.value)}
          className="mt-1 block min-h-8 rounded-lg border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-2 text-xs text-[var(--text-primary)]"
        />
      </label>
      <button
        type="submit"
        className="min-h-8 rounded-lg bg-[var(--insights-accent)] px-2.5 text-xs font-bold text-white transition-opacity hover:opacity-90"
      >
        Save
      </button>
    </form>
  );
}

function TableLoadingSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading follow-up actions"
      className="pms-glass-surface overflow-hidden rounded-[16px]"
    >
      <div className="border-b border-[var(--exec-card-border)] bg-[var(--exec-table-head-bg)] px-5 py-3">
        <div className="h-3.5 w-44 animate-pulse rounded bg-[var(--exec-chip-bg)]" />
      </div>
      <div className="divide-y divide-[var(--exec-card-border)]">
        {[0, 1, 2, 3].map((row) => (
          <div key={row} className="flex items-center gap-4 px-5 py-4">
            <div className="size-8 shrink-0 animate-pulse rounded-full bg-[var(--exec-chip-bg)]" />
            <div className="flex-1 space-y-2">
              <div className="h-3.5 w-1/4 animate-pulse rounded bg-[var(--exec-chip-bg)]" />
              <div className="h-3 w-3/4 animate-pulse rounded bg-[var(--exec-chip-bg)]" />
            </div>
            <div className="h-6 w-24 animate-pulse rounded-full bg-[var(--exec-chip-bg)]" />
            <div className="h-8 w-24 animate-pulse rounded-lg bg-[var(--exec-chip-bg)]" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function ActionFollowUpBoard({
  actions,
  summary,
  isLoading = false,
  isError = false,
  onRetry,
  canEdit,
  owners,
  teams,
  months,
  filters,
  onFiltersChange,
  onStatusChange,
  canDelete = false,
  onDeleteAction,
}: ActionFollowUpBoardProps) {
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState<SortMode>('urgency');
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; surface: 'table' | 'card' } | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState('');

  useEffect(() => {
    if (!confirmTarget || deletingId === confirmTarget.id) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setConfirmTarget(null);
        setDeleteError('');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [confirmTarget, deletingId]);

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleConfirmDelete = async (action: PMSAction) => {
    if (!onDeleteAction) return;
    setDeletingId(action.id);
    setDeleteError('');
    try {
      const ok = await onDeleteAction(action);
      if (ok === false) {
        setDeleteError('Failed to delete corrective action.');
        return;
      }
      setConfirmTarget(null);
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : 'Failed to delete corrective action.');
    } finally {
      setDeletingId(null);
    }
  };

  const showDeleteCol = Boolean(canDelete && onDeleteAction);

  const renderDeleteDialog = (action: PMSAction) => {
    const isDeleting = deletingId === action.id;
    return (
      <div
        role="alertdialog"
        aria-label={`Confirm delete action for ${action.employee_name || action.employee_id}`}
        className="mt-1 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-500/25 bg-rose-500/5 px-4 py-3"
      >
        <div className="min-w-0">
          <p className="text-xs font-semibold text-rose-800">
            Delete corrective action for {action.employee_name || action.employee_id}?
          </p>
          {deleteError && (
            <p role="alert" className="mt-1 text-xs font-semibold text-rose-700">
              {deleteError}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            disabled={isDeleting}
            onClick={() => {
              setConfirmTarget(null);
              setDeleteError('');
            }}
            className="rounded-lg border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={isDeleting}
            onClick={() => void handleConfirmDelete(action)}
            className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-bold text-white transition-colors hover:bg-rose-700 disabled:opacity-50"
          >
            {isDeleting ? 'Deleting…' : 'Delete Action'}
          </button>
        </div>
      </div>
    );
  };

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    const filtered = !query
      ? actions
      : actions.filter((action) =>
          [action.employee_name, action.employee_id, action.team, action.action_text, action.owner?.name, action.action_type]
            .some((value) => String(value || '').toLowerCase().includes(query)),
        );

    return [...filtered].sort((left, right) => {
      if (sortBy === 'employee') {
        const leftName = left.employee_name || left.employee_id || left.plan?.name || '';
        const rightName = right.employee_name || right.employee_id || right.plan?.name || '';
        return leftName.localeCompare(rightName);
      }
      if (sortBy === 'due_date') {
        return String(left.due_date || '9999-99-99').localeCompare(String(right.due_date || '9999-99-99'));
      }
      if (sortBy === 'status') {
        return String(left.status || 'Open').localeCompare(String(right.status || 'Open'));
      }
      return (
        urgencyRank(left) - urgencyRank(right) ||
        String(left.due_date || '9999-99-99').localeCompare(String(right.due_date || '9999-99-99'))
      );
    });
  }, [actions, search, sortBy]);

  const ownerOptions = [{ value: '', label: 'All owners' }, ...owners.map((owner) => ({ value: owner.id, label: owner.name }))];

  return (
    <section className="space-y-4" aria-label="Action follow-up">
      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-6">
        <SummaryChip label="Overdue" value={summary.overdue} tone="text-rose-700" bg="var(--pms-grad-panel-neg)" border="var(--pms-grad-panel-neg-border)" accent="var(--pms-grad-grade-e)" />
        <SummaryChip label="Due this week" value={summary.due_soon} tone="text-amber-700" bg="var(--pms-grad-panel-warn)" border="var(--pms-grad-panel-warn-border)" accent="var(--pms-grad-grade-c)" />
        <SummaryChip label="Open" value={summary.open} tone="text-sky-700" bg="var(--pms-grad-panel-info)" border="var(--pms-grad-panel-info-border)" accent="var(--pms-grad-accent)" />
        <SummaryChip label="In Progress" value={summary.in_progress} tone="text-violet-700" bg="var(--pms-grad-panel-violet)" border="var(--pms-grad-panel-violet-border)" accent="var(--pms-grad-violet)" />
        <SummaryChip label="Completed this month" value={summary.completed_this_month} tone="text-emerald-700" bg="var(--pms-grad-panel-pos)" border="var(--pms-grad-panel-pos-border)" accent="var(--pms-grad-grade-a)" />
        <SummaryChip label="Completion rate" value={`${summary.completion_rate}%`} tone="text-emerald-700" bg="var(--pms-grad-panel-pos)" border="var(--pms-grad-panel-pos-border)" accent="var(--pms-grad-grade-b)" />
      </div>

      <div className="pms-glass-surface grid gap-3 rounded-[16px] p-3 lg:grid-cols-[minmax(180px,1fr)_repeat(4,minmax(130px,0.7fr))]">
        <label className="relative block">
          <span className="sr-only">Search follow-up</span>
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search employee, team or action…" className="min-h-10 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] pl-9 pr-3 text-sm outline-none focus:border-blue-500" />
        </label>
        <CustomDropdown ariaLabel="Filter follow-up by state" value={filters.state || ''} options={STATE_OPTIONS} onChange={(state) => onFiltersChange({ ...filters, state })} className="w-full" buttonClassName="w-full min-h-10 rounded-xl" />
        <CustomDropdown ariaLabel="Filter follow-up by team" value={filters.team || ''} options={[{ value: '', label: 'All teams' }, ...teams.map((team) => ({ value: team, label: team }))]} onChange={(team) => onFiltersChange({ ...filters, team })} className="w-full" buttonClassName="w-full min-h-10 rounded-xl" />
        <CustomDropdown ariaLabel="Filter follow-up by owner" value={filters.owner || ''} options={ownerOptions} onChange={(owner) => onFiltersChange({ ...filters, owner })} className="w-full" buttonClassName="w-full min-h-10 rounded-xl" />
        <CustomDropdown ariaLabel="Filter follow-up by month" value={filters.month || ''} options={[{ value: '', label: 'All months' }, ...months.map((month) => ({ value: month, label: month }))]} onChange={(month) => onFiltersChange({ ...filters, month })} icon={<CalendarDays size={14} />} className="w-full" buttonClassName="w-full min-h-10 rounded-xl" />
      </div>

      {isLoading && <TableLoadingSkeleton />}
      {isError && (
        <div role="alert" className="pms-glass-surface rounded-[16px] border-rose-500/25 px-4 py-6 text-center" style={{ background: 'var(--pms-grad-panel-neg)' }}>
          <AlertCircle className="mx-auto text-rose-600" size={22} />
          <p className="mt-2 text-sm font-bold text-rose-700">Follow-up could not be loaded.</p>
          {onRetry && <button type="button" onClick={onRetry} className="mt-3 inline-flex min-h-9 items-center gap-2 rounded-xl border border-rose-500/30 bg-[var(--bg-surface)] px-3.5 text-xs font-bold text-rose-700"><RefreshCw size={14} />Try again</button>}
        </div>
      )}
      {!isLoading && !isError && visible.length === 0 && (
        <div className="pms-glass-surface rounded-[16px] px-4 py-10 text-center">
          <p className="text-sm font-bold text-[var(--insights-heading)]">No follow-up actions</p>
          <p className="mt-1 text-xs text-[var(--text-muted)]">Tracked actions with a due date, and plan actions, will show up here.</p>
        </div>
      )}
      {!isLoading && !isError && visible.length > 0 && (
        <>
          <div className="pms-glass-surface hidden overflow-hidden rounded-[16px] md:block">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--exec-card-border)] px-5 py-3">
              <p className="text-xs font-semibold text-[var(--text-muted)] tabular-nums">
                Showing <span className="font-bold text-[var(--insights-heading)]">{visible.length}</span>{' '}
                {visible.length === 1 ? 'corrective action' : 'corrective actions'}
              </p>
              <label className="inline-flex items-center gap-2 text-xs font-semibold text-[var(--text-muted)]">
                <ArrowUpDown className="size-3.5 shrink-0" aria-hidden="true" />
                <span className="sr-only">Sort follow-up actions</span>
                <select
                  aria-label="Sort follow-up actions"
                  value={sortBy}
                  onChange={(event) => setSortBy(event.target.value as SortMode)}
                  className="h-8 cursor-pointer rounded-lg border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-2.5 text-xs font-semibold text-[var(--insights-heading)] focus:border-[var(--insights-accent)] focus:outline-none"
                >
                  {SORT_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] border-collapse text-left">
                <thead className="sticky top-0 z-10 border-b border-[var(--exec-card-border)] bg-[var(--exec-table-head-bg)] text-xs font-bold uppercase tracking-wider text-[var(--text-muted)]">
                  <tr>
                    <th className="w-[230px] px-5 py-3">Employee &amp; Team</th>
                    <th className="px-4 py-3">Action Plan</th>
                    <th className="w-[148px] whitespace-nowrap px-4 py-3">Owner</th>
                    <th className="w-[172px] whitespace-nowrap px-4 py-3">Due &amp; Timeline</th>
                    <th className="w-[142px] whitespace-nowrap px-4 py-3">Status</th>
                    {showDeleteCol && (
                      <th className="w-[56px] px-4 py-3 text-right">
                        <span className="sr-only">Actions</span>
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--exec-card-border)]">
                  {visible.map((action) => {
                    const canDeleteRow = showDeleteCol && Boolean(action.employee_id);
                    const isConfirmingTable = confirmTarget?.id === action.id && confirmTarget.surface === 'table';
                    const colCount = showDeleteCol ? 6 : 5;
                    return (
                      <Fragment key={action.id}>
                        <tr
                          className={`align-top transition-colors duration-150 hover:bg-[var(--exec-tile-bg)] ${rowAccentClass(action)}`}
                        >
                          <td className="px-5 py-4">
                            <EmployeeIdentityCell action={action} />
                          </td>

                          <td className="px-4 py-4">
                            <ActionDescriptionCell
                              action={action}
                              expanded={expandedIds.has(action.id)}
                              onToggleExpand={() => toggleExpand(action.id)}
                            />
                          </td>

                          <td className="whitespace-nowrap px-4 py-4">
                            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--text-secondary)]">
                              <UserRound className="size-3.5 shrink-0 text-[var(--text-muted)]" aria-hidden="true" />
                              <span>{action.owner?.name || 'Unassigned'}</span>
                            </span>
                          </td>

                          <td className="whitespace-nowrap px-4 py-4">
                            <div className="flex flex-col items-start gap-1.5">
                              <DueBadge action={action} />
                              {canEdit ? (
                                <DueDateSetter action={action} onStatusChange={onStatusChange} />
                              ) : (
                                <span
                                  className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium tabular-nums text-[var(--text-muted)]"
                                  title={action.due_date || undefined}
                                >
                                  <CalendarDays className="size-3.5 shrink-0 opacity-75" aria-hidden="true" />
                                  <span>{formatHumanDate(action.due_date)}</span>
                                </span>
                              )}
                            </div>
                          </td>

                          <td className="whitespace-nowrap px-4 py-4">
                            <ActionStatusMenu
                              status={action.status || 'Open'}
                              canEdit={canEdit}
                              ariaLabel={`Status for ${action.action_text}`}
                              onChange={(update) => onStatusChange(action.id, update)}
                            />
                          </td>

                          {showDeleteCol && (
                            <td className="px-4 py-4 text-right">
                              {canDeleteRow && (
                                <button
                                  type="button"
                                  data-testid={`delete-follow-up-action-${action.id}`}
                                  aria-label={`Delete action for ${action.employee_name || action.employee_id}`}
                                  title="Delete action"
                                  onClick={() => {
                                    setDeleteError('');
                                    setConfirmTarget({ id: action.id, surface: 'table' });
                                  }}
                                  className="inline-flex size-8 items-center justify-center rounded-lg text-[var(--text-muted)] transition-colors hover:bg-rose-500/10 hover:text-rose-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
                                >
                                  <Trash2 size={15} aria-hidden="true" />
                                </button>
                              )}
                            </td>
                          )}
                        </tr>
                        {isConfirmingTable && (
                          <tr className="bg-rose-500/[0.03]">
                            <td colSpan={colCount} className="px-5 pb-4 pt-0">
                              {renderDeleteDialog(action)}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid gap-3 md:hidden">
            {visible.map((action) => {
              const canDeleteCard = showDeleteCol && Boolean(action.employee_id);
              const isConfirmingCard = confirmTarget?.id === action.id && confirmTarget.surface === 'card';
              return (
                <article
                  key={action.id}
                  className={`pms-glass-surface space-y-3 rounded-[16px] p-4 ${rowAccentClass(action)}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <EmployeeIdentityCell action={action} />
                    <StatusPill status={action.status || 'Open'} />
                  </div>
                  <ActionDescriptionCell
                    action={action}
                    expanded={expandedIds.has(action.id)}
                    onToggleExpand={() => toggleExpand(action.id)}
                  />
                  <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--exec-card-border)] pt-2.5 text-xs text-[var(--text-muted)]">
                    <span className="inline-flex items-center gap-1.5 font-semibold text-[var(--text-secondary)]">
                      <UserRound className="size-3.5" aria-hidden="true" />
                      {action.owner?.name || 'Unassigned'}
                    </span>
                    <div className="flex flex-wrap items-center gap-2">
                      <DueBadge action={action} />
                      {canEdit ? (
                        <DueDateSetter action={action} onStatusChange={onStatusChange} />
                      ) : (
                        <span className="font-medium tabular-nums">{formatHumanDate(action.due_date)}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                    <ActionStatusMenu
                      status={action.status || 'Open'}
                      canEdit={canEdit}
                      ariaLabel={`Status for ${action.action_text}`}
                      onChange={(update) => onStatusChange(action.id, update)}
                    />
                    {canDeleteCard && (
                      <button
                        type="button"
                        data-testid={`delete-follow-up-card-action-${action.id}`}
                        aria-label={`Delete action for ${action.employee_name || action.employee_id}`}
                        onClick={() => {
                          setDeleteError('');
                          setConfirmTarget({ id: action.id, surface: 'card' });
                        }}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/25 px-2.5 py-1.5 text-xs font-semibold text-rose-600 transition-colors hover:bg-rose-500/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
                      >
                        <Trash2 size={14} aria-hidden="true" />
                        Delete
                      </button>
                    )}
                  </div>
                  {isConfirmingCard && renderDeleteDialog(action)}
                </article>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}

export function ActionFollowUpPanel({ canEdit, initialFilters = {}, scopeFunction }: { canEdit: boolean; initialFilters?: FollowUpFilters; scopeFunction?: string | null }) {
  const [filters, setFilters] = useState<FollowUpFilters>(initialFilters);
  return <ConnectedFollowUp filters={filters} onFiltersChange={setFilters} canEdit={canEdit} scopeFunction={scopeFunction} />;
}

function ConnectedFollowUp({
  filters,
  onFiltersChange,
  canEdit,
  scopeFunction,
}: {
  filters: FollowUpFilters;
  onFiltersChange: (filters: FollowUpFilters) => void;
  canEdit: boolean;
  scopeFunction?: string | null;
}) {
  const baseline = useFollowUp({});
  const filtered = useFollowUp(filters);
  const active = filters.state || filters.team || filters.owner || filters.month ? filtered : baseline;
  const owners = useActionOwners();
  const updateStatus = useUpdateActionStatus();
  const { role } = useUserRole();
  const actionStore = useActionStore();
  const deleteAction = actionStore?.deleteAction;
  const canDelete = canDeleteCorrectiveAction(role) && typeof deleteAction === 'function';
  const inFunction = (action: PMSAction) => !scopeFunction || executiveFunctionForTeam(action.team) === scopeFunction;
  const source = (baseline.data?.actions ?? []).filter(inFunction);
  const scopedSummaryActions = source.filter((action) => (!filters.team || action.team === filters.team)
    && (!filters.month || action.month === filters.month) && (!filters.owner || action.owner?.id === filters.owner));
  const open = scopedSummaryActions.filter((action) => action.status === 'Open').length;
  const inProgress = scopedSummaryActions.filter((action) => action.status === 'In Progress').length;
  const completed = scopedSummaryActions.filter((action) => action.status === 'Completed').length;
  const currentMonth = new Date().toISOString().slice(0, 7);
  const summary: FollowUpSummary = scopeFunction ? {
    overdue: scopedSummaryActions.filter((action) => action.follow_up_state === 'overdue').length,
    due_soon: scopedSummaryActions.filter((action) => action.follow_up_state === 'due_soon').length,
    open, in_progress: inProgress,
    completed_this_month: scopedSummaryActions.filter((action) => action.status === 'Completed' && action.completed_at?.slice(0, 7) === currentMonth).length,
    completion_rate: open + inProgress + completed ? Math.round(completed / (open + inProgress + completed) * 1000) / 10 : 0,
  } : active.data?.summary ?? EMPTY_FOLLOW_UP_SUMMARY;
  const teams = Array.from(new Set(source.map((action) => action.team).filter(Boolean))).sort();
  const months = Array.from(new Set(source.map((action) => action.month).filter(Boolean)));
  return (
    <ActionFollowUpBoard
      actions={(active.data?.actions ?? []).filter(inFunction)}
      summary={summary}
      isLoading={active.isLoading}
      isError={active.isError}
      onRetry={() => { void active.refetch(); }}
      canEdit={canEdit}
      owners={owners.data ?? []}
      teams={teams}
      months={months}
      filters={filters}
      onFiltersChange={onFiltersChange}
      onStatusChange={(id, update) => updateStatus.mutateAsync({ id, ...update })}
      canDelete={canDelete}
      onDeleteAction={
        canDelete && deleteAction
          ? (action) => deleteAction(action.id, action.employee_id)
          : undefined
      }
    />
  );
}
