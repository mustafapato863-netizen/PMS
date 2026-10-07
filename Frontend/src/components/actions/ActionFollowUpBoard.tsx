import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, CalendarDays, RefreshCw, Search } from 'lucide-react';
import CustomDropdown from '../common/CustomDropdown';
import { useActionOwners, useFollowUp, useUpdateActionStatus } from '../../hooks/useActionStore';
import type { ActionStatus, PMSAction } from '../../types';
import { dueBadgeLabel, todayIso } from './dueBadge';
import { ActionStatusMenu, StatusPill } from './ActionStatusMenu';
import { EMPTY_FOLLOW_UP_SUMMARY, type FollowUpFilters, type FollowUpSummary } from './followUpTypes';
import { executiveFunctionForTeam } from '../../features/executive/functions';

export type { FollowUpFilters, FollowUpSummary };
export { EMPTY_FOLLOW_UP_SUMMARY };;

const STATE_OPTIONS = [
  { value: '', label: 'All states' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'due_soon', label: 'Due this week' },
  { value: 'upcoming', label: 'Upcoming' },
  { value: 'no_due_date', label: 'No due date' },
  { value: 'completed', label: 'Completed' },
  { value: 'cancelled', label: 'Cancelled' },
];

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
}

function badgeClass(action: PMSAction): string {
  if (action.follow_up_state === 'overdue' || action.is_overdue) return 'bg-rose-500/10 text-rose-700 dark:text-rose-300';
  if (action.follow_up_state === 'due_soon') return 'bg-amber-500/10 text-amber-700 dark:text-amber-300';
  if (action.follow_up_state === 'completed') return 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300';
  return 'bg-[var(--bg-sunken)] text-[var(--text-secondary)]';
}

function SummaryChip({ label, value, tone }: { label: string; value: string | number; tone: string }) {
  return (
    <article className={`rounded-2xl border px-3 py-2 ${tone}`}>
      <p className="text-[10px] font-black uppercase tracking-wide">{label}</p>
      <p className="mt-1 text-xl font-black text-[var(--text-primary)]">{value}</p>
    </article>
  );
}

function DueBadge({ action }: { action: PMSAction }) {
  return (
    <span className={`inline-flex rounded-full px-2 py-1 text-[10px] font-black ${badgeClass(action)}`}>
      {dueBadgeLabel(action.due_date, action.days_to_due)}
    </span>
  );
}

function EmployeeCell({ action }: { action: PMSAction }) {
  if (!action.employee_id) {
    return <span className="font-black text-[var(--text-primary)]">{action.plan?.name || 'Plan action'}</span>;
  }
  return (
    <Link to={`/employee/${encodeURIComponent(action.employee_id)}`} className="font-black text-blue-600 hover:underline dark:text-blue-400">
      {action.employee_name || action.employee_id}
    </Link>
  );
}

function DueDateSetter({ action, onStatusChange }: { action: PMSAction; onStatusChange: ActionFollowUpBoardProps['onStatusChange'] }) {
  const [dueDate, setDueDate] = useState('');
  if (action.due_date) return <span className="text-xs font-semibold text-[var(--text-secondary)]">{action.due_date}</span>;
  return (
    <form
      className="flex flex-wrap items-center gap-1"
      onSubmit={(event) => {
        event.preventDefault();
        if (!dueDate) return;
        void onStatusChange(action.id, { status: (action.status || 'Open') as ActionStatus, due_date: dueDate });
      }}
    >
      <label className="text-[10px] font-bold text-[var(--text-muted)]">
        Set due date
        <input
          aria-label={`Set due date for ${action.action_text}`}
          type="date"
          min={todayIso()}
          value={dueDate}
          onChange={(event) => setDueDate(event.target.value)}
          className="mt-1 block min-h-9 rounded-lg border border-[var(--border-light)] bg-[var(--bg-surface)] px-2 text-xs"
        />
      </label>
      <button type="submit" className="min-h-9 rounded-lg bg-blue-600 px-2 text-[10px] font-black text-white">Save</button>
    </form>
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
}: ActionFollowUpBoardProps) {
  const [search, setSearch] = useState('');
  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return actions;
    return actions.filter((action) => [action.employee_name, action.employee_id, action.team, action.action_text, action.owner?.name, action.action_type]
      .some((value) => String(value || '').toLowerCase().includes(query)));
  }, [actions, search]);

  const ownerOptions = [{ value: '', label: 'All owners' }, ...owners.map((owner) => ({ value: owner.id, label: owner.name }))];

  return (
    <section className="space-y-4" aria-label="Action follow-up">
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-6">
        <SummaryChip label="Overdue" value={summary.overdue} tone="border-rose-500/20 bg-rose-500/5 text-rose-700 dark:text-rose-300" />
        <SummaryChip label="Due this week" value={summary.due_soon} tone="border-amber-500/20 bg-amber-500/5 text-amber-700 dark:text-amber-300" />
        <SummaryChip label="Open" value={summary.open} tone="border-blue-500/20 bg-blue-500/5 text-blue-700 dark:text-blue-300" />
        <SummaryChip label="In Progress" value={summary.in_progress} tone="border-[var(--border-light)] bg-[var(--bg-surface)] text-[var(--text-secondary)]" />
        <SummaryChip label="Completed this month" value={summary.completed_this_month} tone="border-emerald-500/20 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300" />
        <SummaryChip label="Completion rate" value={`${summary.completion_rate}%`} tone="border-emerald-500/20 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300" />
      </div>

      <div className="glass-card grid gap-3 rounded-2xl p-3 lg:grid-cols-[minmax(180px,1fr)_repeat(4,minmax(130px,0.7fr))]">
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

      {isLoading && <p className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-4 py-8 text-center text-sm font-semibold text-[var(--text-muted)]">Loading follow-up…</p>}
      {isError && (
        <div role="alert" className="rounded-2xl border border-rose-500/20 bg-rose-500/5 px-4 py-6 text-center">
          <AlertCircle className="mx-auto text-rose-600" size={22} />
          <p className="mt-2 text-sm font-bold text-rose-700">Follow-up could not be loaded.</p>
          {onRetry && <button type="button" onClick={onRetry} className="mt-3 inline-flex min-h-10 items-center gap-2 rounded-xl border border-rose-500/30 px-3 text-xs font-bold text-rose-700"><RefreshCw size={14} />Try again</button>}
        </div>
      )}
      {!isLoading && !isError && visible.length === 0 && (
        <div className="glass-card rounded-2xl px-4 py-10 text-center">
          <p className="text-sm font-black text-[var(--text-primary)]">No follow-up actions</p>
          <p className="mt-1 text-xs text-[var(--text-muted)]">Tracked actions with a due date, and plan actions, will show up here.</p>
        </div>
      )}
      {!isLoading && !isError && visible.length > 0 && (
        <>
          <div className="hidden overflow-x-auto rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] md:block">
            <table className="w-full min-w-[920px] text-left">
              <thead className="text-[10px] font-black uppercase tracking-wide text-[var(--text-muted)]">
                <tr>
                  {['Employee', 'Team', 'Type', 'Action', 'Owner', 'Due date', 'Due', 'Status'].map((heading) => (
                    <th key={heading} className="px-3 py-2">{heading}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((action) => (
                  <tr key={action.id} className="border-t border-[var(--border-light)] align-top">
                    {['employee', 'team', 'type', 'action', 'owner', 'due', 'badge', 'status'].map((cell) => (
                      <td key={cell} className="px-3 py-3">
                        {cell === 'employee' && <EmployeeCell action={action} />}
                        {cell === 'team' && <span className="text-xs font-semibold text-[var(--text-secondary)]">{action.team || 'Unassigned'}</span>}
                        {cell === 'type' && <span className="text-xs font-bold text-[var(--text-primary)]">{action.action_type}</span>}
                        {cell === 'action' && <span className="text-xs font-semibold text-[var(--text-secondary)]">{action.action_text}</span>}
                        {cell === 'owner' && <span className="text-xs font-semibold text-[var(--text-secondary)]">{action.owner?.name || 'Unassigned'}</span>}
                        {cell === 'due' && (canEdit ? <DueDateSetter action={action} onStatusChange={onStatusChange} /> : <span className="text-xs font-semibold text-[var(--text-secondary)]">{action.due_date || 'No due date'}</span>)}
                        {cell === 'badge' && <DueBadge action={action} />}
                        {cell === 'status' && (
                          <ActionStatusMenu
                            status={action.status || 'Open'}
                            canEdit={canEdit}
                            ariaLabel={`Status for ${action.action_text}`}
                            onChange={(update) => onStatusChange(action.id, update)}
                          />
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="grid gap-3 md:hidden">
            {visible.map((action) => (
              <article key={action.id} className="glass-card space-y-2 rounded-2xl p-3">
                <div className="flex items-start justify-between gap-2">
                  <EmployeeCell action={action} />
                  <StatusPill status={action.status || 'Open'} />
                </div>
                <p className="text-[11px] font-semibold text-[var(--text-muted)]">{action.team || 'Unassigned'} · {action.action_type}</p>
                <p className="text-xs font-semibold text-[var(--text-secondary)]">{action.action_text}</p>
                <p className="text-[11px] font-semibold text-[var(--text-muted)]">Owner {action.owner?.name || 'Unassigned'}</p>
                <div className="flex flex-wrap items-center gap-2">
                  <DueBadge action={action} />
                  {canEdit ? <DueDateSetter action={action} onStatusChange={onStatusChange} /> : <span className="text-xs font-semibold">{action.due_date || 'No due date'}</span>}
                </div>
                <ActionStatusMenu
                  status={action.status || 'Open'}
                  canEdit={canEdit}
                  ariaLabel={`Status for ${action.action_text}`}
                  onChange={(update) => onStatusChange(action.id, update)}
                />
              </article>
            ))}
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
    />
  );
}
