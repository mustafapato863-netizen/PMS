import { useMemo, useState } from 'react';
import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  Clock,
  Filter,
  Layers,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Target,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import CustomDropdown from '../common/CustomDropdown';
import {
  useAllTeamActions,
  useCreateTeamActionPlanItem,
  useDeleteTeamAction,
  useUpdateTeamActionStatus,
  type TeamActionStatus,
  type UnifiedTeamAction,
} from '../../hooks/useActionStore';
import { executiveFunctionForTeam } from '../../features/executive/functions';
import { MONTHS } from '../../features/executive/compose';
import { TEAM_DB_NAME_MAP } from '../../types';

const TEAM_STATUS_OPTIONS: TeamActionStatus[] = ['Open', 'In Progress', 'Planned', 'Completed'];

const STATUS_STYLE: Record<TeamActionStatus, { badge: string; accent: string }> = {
  Open: {
    badge: 'border-sky-300/60 bg-gradient-to-r from-sky-50 to-blue-100/80 text-sky-800',
    accent: 'var(--pms-grad-accent)',
  },
  'In Progress': {
    badge: 'border-amber-300/60 bg-gradient-to-r from-amber-50 to-orange-100/80 text-amber-800',
    accent: 'var(--pms-grad-grade-c)',
  },
  Planned: {
    badge: 'border-violet-300/60 bg-gradient-to-r from-violet-50 to-purple-100/80 text-violet-800',
    accent: 'var(--pms-grad-violet)',
  },
  Completed: {
    badge: 'border-emerald-300/60 bg-gradient-to-r from-emerald-50 to-teal-100/80 text-emerald-800',
    accent: 'var(--pms-grad-grade-a)',
  },
};

function formatDueDate(value?: string | null): string {
  if (!value) return 'No due date';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(parsed);
}

function TeamActionCard({
  item,
  canEdit,
  onStatusChange,
  onDelete,
}: {
  item: UnifiedTeamAction;
  canEdit: boolean;
  onStatusChange: (id: string, status: TeamActionStatus) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [actionError, setActionError] = useState('');

  const tone = STATUS_STYLE[item.status] ?? STATUS_STYLE.Open;
  const isCohort = item.kind === 'cohort_plan';

  const handleStatusSelect = async (nextStatus: TeamActionStatus) => {
    if (nextStatus === item.status) return;
    setUpdatingStatus(true);
    setActionError('');
    try {
      await onStatusChange(item.id, nextStatus);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to update status.');
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleConfirmDelete = async () => {
    setIsDeleting(true);
    setActionError('');
    try {
      await onDelete(item.id);
      setConfirmingDelete(false);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to delete team action.');
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <article
      data-testid={`team-action-card-${item.id}`}
      className="pms-glass-surface pms-glass-surface--interactive relative flex flex-col justify-between overflow-hidden rounded-[18px] p-5"
    >
      <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[3px]" style={{ background: tone.accent }} />

      <div>
        {/* Header badges */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="inline-flex items-center gap-1 rounded-full border border-indigo-300/60 bg-gradient-to-r from-indigo-50 to-sky-100/80 px-2.5 py-1 text-[11px] font-bold text-indigo-800">
              {isCohort ? <Layers size={12} aria-hidden="true" /> : <Users size={12} aria-hidden="true" />}
              {isCohort ? 'Whole-Team Action' : 'Team Summary Action'}
            </span>
            <span className="rounded-full border border-[var(--pms-glass-stage-border)] bg-[var(--pms-glass-stage-bg)] px-2.5 py-1 text-[11px] font-bold text-[var(--text-primary)]">
              {item.team}
              {item.region ? ` · ${item.region}` : ''}
            </span>
          </div>

          {canEdit ? (
            <label className="inline-flex items-center">
              <span className="sr-only">Status for {item.title}</span>
              <select
                aria-label={`Status for ${item.title}`}
                value={item.status}
                disabled={updatingStatus}
                onChange={(event) => void handleStatusSelect(event.target.value as TeamActionStatus)}
                className={`cursor-pointer rounded-full border px-2.5 py-1 text-[11px] font-bold outline-none transition focus-visible:ring-2 focus-visible:ring-sky-500 disabled:opacity-60 ${tone.badge}`}
              >
                {TEAM_STATUS_OPTIONS.map((option) => (
                  <option key={option} value={option} className="bg-[var(--bg-surface)] text-[var(--text-primary)]">
                    {option}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <span className={`rounded-full border px-2.5 py-1 text-[11px] font-bold ${tone.badge}`}>
              {item.status}
            </span>
          )}
        </div>

        {/* Target KPI inset pill (matches Team-Level Action Plan) */}
        {item.target_kpi && (
          <div className="pms-glass-stage mt-3 flex items-start gap-2 rounded-xl px-3 py-2 text-xs font-semibold text-[var(--text-secondary)]">
            <Target size={14} className="mt-0.5 shrink-0 text-indigo-600" aria-hidden="true" />
            <span className="leading-snug">{item.target_kpi}</span>
          </div>
        )}

        {/* Action title / description */}
        <h3 className="mt-3 whitespace-pre-line text-[14px] font-extrabold leading-snug text-[var(--text-primary)]">
          {item.title}
        </h3>

        {item.scope_description && (
          <p className="mt-2 whitespace-pre-line text-xs leading-5 text-[var(--text-secondary)]">
            {item.scope_description}
          </p>
        )}

        {item.expected_team_impact && (
          <div
            className="mt-3 flex items-start gap-2 rounded-xl border border-[var(--pms-grad-panel-pos-border)] px-3 py-2 text-xs text-[var(--text-secondary)]"
            style={{ background: 'var(--pms-grad-panel-pos)' }}
          >
            <Sparkles size={13} className="mt-0.5 shrink-0 text-emerald-700" aria-hidden="true" />
            <span>
              <strong className="font-bold text-emerald-800">Expected impact: </strong>
              {item.expected_team_impact}
            </span>
          </div>
        )}
      </div>

      {/* Metadata & actions */}
      <div className="mt-4 border-t border-[var(--border-light)] pt-3">
        <dl className="space-y-1.5 text-xs">
          <div className="flex items-center justify-between gap-2">
            <dt className="font-semibold text-[var(--text-muted)]">Owner</dt>
            <dd className="truncate font-bold text-[var(--text-primary)]">{item.owner || 'Unassigned'}</dd>
          </div>
          <div className="flex items-center justify-between gap-2">
            <dt className="font-semibold text-[var(--text-muted)]">Review date</dt>
            <dd className="font-bold text-[var(--text-secondary)]">{formatDueDate(item.due_date)}</dd>
          </div>
          <div className="flex items-center justify-between gap-2">
            <dt className="font-semibold text-[var(--text-muted)]">Period</dt>
            <dd className="inline-flex items-center gap-1 font-semibold text-[var(--text-secondary)]">
              <CalendarDays size={12} aria-hidden="true" />
              {item.month} {item.year}
            </dd>
          </div>
        </dl>

        {actionError && (
          <p role="alert" className="mt-2.5 rounded-lg border border-rose-500/25 bg-rose-500/10 px-2.5 py-1.5 text-xs font-semibold text-rose-700">
            {actionError}
          </p>
        )}

        {canEdit && !confirmingDelete && (
          <div className="mt-3 flex items-center justify-end">
            <button
              type="button"
              onClick={() => {
                setActionError('');
                setConfirmingDelete(true);
              }}
              aria-label={`Delete team action ${item.title}`}
              className="inline-flex items-center gap-1 rounded-lg border border-rose-500/25 px-2.5 py-1.5 text-xs font-bold text-rose-600 transition-colors hover:bg-rose-500/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
            >
              <Trash2 size={12} aria-hidden="true" />
              Delete
            </button>
          </div>
        )}

        {confirmingDelete && (
          <div
            role="alertdialog"
            aria-label={`Confirm delete team action ${item.title}`}
            className="mt-3 rounded-xl border border-rose-500/25 bg-rose-500/5 p-3"
          >
            <p className="text-xs font-semibold text-rose-800">
              Remove this whole-team action for {item.team}?
            </p>
            <div className="mt-2.5 flex justify-end gap-2">
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => setConfirmingDelete(false)}
                className="rounded-lg border border-[var(--border-light)] bg-[var(--bg-surface)] px-2.5 py-1 text-xs font-bold text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)] disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => void handleConfirmDelete()}
                className="rounded-lg bg-rose-600 px-3 py-1 text-xs font-black text-white hover:bg-rose-700 disabled:opacity-50"
              >
                {isDeleting ? 'Deleting…' : 'Delete Team Action'}
              </button>
            </div>
          </div>
        )}
      </div>
    </article>
  );
}

export function TeamActionsPanel({
  canEdit,
  scopeFunction,
  availableTeams = [],
}: {
  canEdit: boolean;
  scopeFunction?: string | null;
  availableTeams?: string[];
}) {
  const { data: rawItems = [], isLoading, isError, refetch } = useAllTeamActions(true);
  const createMutation = useCreateTeamActionPlanItem();
  const updateStatusMutation = useUpdateTeamActionStatus();
  const deleteMutation = useDeleteTeamAction();

  const [search, setSearch] = useState('');
  const [teamFilter, setTeamFilter] = useState('All teams');
  const [monthFilter, setMonthFilter] = useState('All months');
  const [statusFilter, setStatusFilter] = useState('All statuses');
  const [isAdding, setIsAdding] = useState(false);

  // Add Team Action form state
  const currentYear = new Date().getFullYear();
  const currentMonth = MONTHS[new Date().getMonth()] || 'January';
  const selectableTeams = useMemo(() => {
    const set = new Set<string>([
      ...availableTeams,
      ...Object.values(TEAM_DB_NAME_MAP),
      ...rawItems.map((item) => item.team),
    ].filter(Boolean));
    return Array.from(set).sort();
  }, [availableTeams, rawItems]);

  const [newTeam, setNewTeam] = useState('');
  const [newMonth, setNewMonth] = useState(currentMonth);
  const [newYear, setNewYear] = useState(currentYear);
  const [newTitle, setNewTitle] = useState('');
  const [newTargetKpi, setNewTargetKpi] = useState('');
  const [newOwner, setNewOwner] = useState('');
  const [newDueDate, setNewDueDate] = useState('');
  const [newImpact, setNewImpact] = useState('');
  const [newStatus, setNewStatus] = useState<TeamActionStatus>('Open');
  const [formError, setFormError] = useState('');

  const scopedItems = useMemo(() => {
    if (!scopeFunction) return rawItems;
    return rawItems.filter((item) => executiveFunctionForTeam(item.team) === scopeFunction);
  }, [rawItems, scopeFunction]);

  const teams = useMemo(() => Array.from(new Set(scopedItems.map((item) => item.team).filter(Boolean))).sort(), [scopedItems]);
  const months = useMemo(() => Array.from(new Set(scopedItems.map((item) => item.month).filter(Boolean))), [scopedItems]);

  const filteredItems = useMemo(() => {
    const query = search.trim().toLowerCase();
    return scopedItems.filter((item) => {
      if (teamFilter !== 'All teams' && item.team !== teamFilter) return false;
      if (monthFilter !== 'All months' && item.month !== monthFilter) return false;
      if (statusFilter !== 'All statuses' && item.status !== statusFilter) return false;
      if (!query) return true;
      return [item.team, item.title, item.target_kpi, item.scope_description, item.owner, item.expected_team_impact]
        .some((field) => String(field || '').toLowerCase().includes(query));
    });
  }, [scopedItems, teamFilter, monthFilter, statusFilter, search]);

  const openOrInProgress = scopedItems.filter((item) => item.status === 'Open' || item.status === 'In Progress' || item.status === 'Planned').length;
  const completedCount = scopedItems.filter((item) => item.status === 'Completed').length;
  const teamsCovered = new Set(scopedItems.map((item) => item.team).filter(Boolean)).size;

  const handleCreateSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const chosenTeam = newTeam || selectableTeams[0] || '';
    if (!chosenTeam.trim()) {
      setFormError('Please select a team.');
      return;
    }
    if (!newTitle.trim()) {
      setFormError('Please enter the whole-team action plan title.');
      return;
    }
    setFormError('');
    try {
      await createMutation.mutateAsync({
        team: chosenTeam.trim(),
        month: newMonth,
        year: newYear,
        title: newTitle.trim(),
        target_kpi: newTargetKpi.trim(),
        owner: newOwner.trim(),
        due_date: newDueDate || null,
        expected_team_impact: newImpact.trim(),
        status: newStatus,
      });
      setNewTitle('');
      setNewTargetKpi('');
      setNewOwner('');
      setNewDueDate('');
      setNewImpact('');
      setNewStatus('Open');
      setIsAdding(false);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Could not save team action.');
    }
  };

  return (
    <section aria-label="Team actions" className="space-y-4">
      {/* Header strip + CTA */}
      <div className="pms-glass-surface flex flex-col gap-3 rounded-[18px] p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[11px] font-black uppercase tracking-[0.16em] text-emerald-700">
            Cohort-wide interventions
          </p>
          <h2 className="mt-1 text-xl font-black tracking-tight text-[var(--text-primary)]">
            Team-Level Action Plans
          </h2>
          <p className="mt-0.5 text-xs font-medium text-[var(--text-muted)]">
            Whole-team corrective actions and cohort-wide interventions across teams (excluding individual employee actions).
          </p>
        </div>
        {canEdit && (
          <button
            type="button"
            onClick={() => {
              setFormError('');
              if (!newTeam && selectableTeams.length > 0) setNewTeam(selectableTeams[0]);
              setIsAdding((prev) => !prev);
            }}
            className="inline-flex min-h-10 shrink-0 items-center justify-center gap-1.5 rounded-xl px-4 text-xs font-black text-white shadow-sm transition-all hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
            style={{ background: 'linear-gradient(135deg, #0284C7 0%, #3898EC 100%)' }}
          >
            {isAdding ? <X size={15} /> : <Plus size={15} />}
            {isAdding ? 'Close form' : 'Add Team Action'}
          </button>
        )}
      </div>

      {/* Add Team Action inline frosted form */}
      {isAdding && canEdit && (
        <form
          onSubmit={(event) => void handleCreateSubmit(event)}
          aria-label="Add whole-team action form"
          className="pms-glass-surface relative overflow-hidden rounded-[18px] p-5"
        >
          <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[3px]" style={{ background: 'var(--pms-grad-accent)' }} />
          <h3 className="text-sm font-black text-[var(--text-primary)]">New Whole-Team Action</h3>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            Assign an operational intervention for an entire team. It will also sync with Monthly Presentation & Team Deep Dive views.
          </p>

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="block text-xs font-bold text-[var(--text-secondary)]">
              Team
              <select
                value={newTeam || selectableTeams[0] || ''}
                onChange={(event) => setNewTeam(event.target.value)}
                className="mt-1 min-h-10 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 text-xs font-semibold text-[var(--text-primary)] outline-none focus:border-sky-500"
              >
                {selectableTeams.map((teamOption) => (
                  <option key={teamOption} value={teamOption}>{teamOption}</option>
                ))}
              </select>
            </label>
            <label className="block text-xs font-bold text-[var(--text-secondary)]">
              Month
              <select
                value={newMonth}
                onChange={(event) => setNewMonth(event.target.value)}
                className="mt-1 min-h-10 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 text-xs font-semibold text-[var(--text-primary)] outline-none focus:border-sky-500"
              >
                {MONTHS.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </label>
            <label className="block text-xs font-bold text-[var(--text-secondary)]">
              Year
              <input
                type="number"
                min={2020}
                max={2100}
                value={newYear}
                onChange={(event) => setNewYear(Number(event.target.value) || currentYear)}
                className="mt-1 min-h-10 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 text-xs font-semibold text-[var(--text-primary)] outline-none focus:border-sky-500"
              />
            </label>
            <label className="block text-xs font-bold text-[var(--text-secondary)]">
              Status
              <select
                value={newStatus}
                onChange={(event) => setNewStatus(event.target.value as TeamActionStatus)}
                className="mt-1 min-h-10 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 text-xs font-semibold text-[var(--text-primary)] outline-none focus:border-sky-500"
              >
                {TEAM_STATUS_OPTIONS.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>

            <label className="block text-xs font-bold text-[var(--text-secondary)] sm:col-span-2 lg:col-span-4">
              Action plan title
              <textarea
                rows={2}
                required
                value={newTitle}
                onChange={(event) => setNewTitle(event.target.value)}
                placeholder="e.g. Institute mandatory 100% pre-bill peer audit on OP Coding batches..."
                className="mt-1 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-xs font-semibold text-[var(--text-primary)] outline-none focus:border-sky-500"
              />
            </label>

            <label className="block text-xs font-bold text-[var(--text-secondary)] sm:col-span-2">
              Target KPI & gap (optional)
              <input
                type="text"
                value={newTargetKpi}
                onChange={(event) => setNewTargetKpi(event.target.value)}
                placeholder="e.g. Pre-Approvals IP Error % (1.5% → ≤ 1.0%)"
                className="mt-1 min-h-10 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 text-xs font-semibold text-[var(--text-primary)] outline-none focus:border-sky-500"
              />
            </label>
            <label className="block text-xs font-bold text-[var(--text-secondary)]">
              Owner (optional)
              <input
                type="text"
                value={newOwner}
                onChange={(event) => setNewOwner(event.target.value)}
                placeholder="e.g. Coding & Audit QA Lead"
                className="mt-1 min-h-10 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 text-xs font-semibold text-[var(--text-primary)] outline-none focus:border-sky-500"
              />
            </label>
            <label className="block text-xs font-bold text-[var(--text-secondary)]">
              Review / due date (optional)
              <input
                type="date"
                value={newDueDate}
                onChange={(event) => setNewDueDate(event.target.value)}
                className="mt-1 min-h-10 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 text-xs font-semibold text-[var(--text-primary)] outline-none focus:border-sky-500"
              />
            </label>
            <label className="block text-xs font-bold text-[var(--text-secondary)] sm:col-span-2 lg:col-span-4">
              Expected team impact (optional)
              <input
                type="text"
                value={newImpact}
                onChange={(event) => setNewImpact(event.target.value)}
                placeholder="e.g. Reduce rework backlog by 40% and raise Coding TAT above 85%"
                className="mt-1 min-h-10 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 text-xs font-semibold text-[var(--text-primary)] outline-none focus:border-sky-500"
              />
            </label>
          </div>

          {formError && (
            <p role="alert" className="mt-3 rounded-xl border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-xs font-semibold text-rose-700">
              {formError}
            </p>
          )}

          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setIsAdding(false)}
              className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)]"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="rounded-xl px-4 py-2 text-xs font-black text-white shadow-sm transition-all hover:brightness-95 disabled:opacity-60"
              style={{ background: 'linear-gradient(135deg, #0284C7 0%, #3898EC 100%)' }}
            >
              {createMutation.isPending ? 'Saving…' : 'Save Team Action'}
            </button>
          </div>
        </form>
      )}

      {/* 4 Summary KPI cards */}
      <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4" aria-label="Team action summary">
        <article className="pms-glass-surface relative overflow-hidden rounded-[16px] p-4" style={{ background: 'var(--pms-grad-panel-info)', borderColor: 'var(--pms-grad-panel-info-border)' }}>
          <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[3px]" style={{ background: 'var(--pms-grad-accent)' }} />
          <p className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-sky-700">
            <ClipboardList size={14} aria-hidden="true" /> Total team actions
          </p>
          <p className="mt-2 text-3xl font-black text-[var(--text-primary)]">{scopedItems.length}</p>
        </article>
        <article className="pms-glass-surface relative overflow-hidden rounded-[16px] p-4" style={{ background: 'var(--pms-grad-panel-warn)', borderColor: 'var(--pms-grad-panel-warn-border)' }}>
          <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[3px]" style={{ background: 'var(--pms-grad-grade-c)' }} />
          <p className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-amber-700">
            <Clock size={14} aria-hidden="true" /> Active & planned
          </p>
          <p className="mt-2 text-3xl font-black text-[var(--text-primary)]">{openOrInProgress}</p>
        </article>
        <article className="pms-glass-surface relative overflow-hidden rounded-[16px] p-4" style={{ background: 'var(--pms-grad-panel-pos)', borderColor: 'var(--pms-grad-panel-pos-border)' }}>
          <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[3px]" style={{ background: 'var(--pms-grad-grade-a)' }} />
          <p className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-emerald-700">
            <CheckCircle2 size={14} aria-hidden="true" /> Completed
          </p>
          <p className="mt-2 text-3xl font-black text-[var(--text-primary)]">{completedCount}</p>
        </article>
        <article className="pms-glass-surface relative overflow-hidden rounded-[16px] p-4" style={{ background: 'var(--pms-grad-panel-violet)', borderColor: 'var(--pms-grad-panel-violet-border)' }}>
          <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[3px]" style={{ background: 'var(--pms-grad-violet)' }} />
          <p className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-violet-700">
            <Users size={14} aria-hidden="true" /> Teams covered
          </p>
          <p className="mt-2 text-3xl font-black text-[var(--text-primary)]">{teamsCovered}</p>
        </article>
      </div>

      {/* Filters toolbar */}
      <div className="pms-glass-surface grid grid-cols-1 gap-3 rounded-[16px] p-3.5 sm:grid-cols-2 lg:grid-cols-4">
        <label className="relative block sm:col-span-2 lg:col-span-1">
          <span className="sr-only">Search team actions</span>
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search team, KPI, owner…"
            className="min-h-10 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] pl-9 pr-3 text-xs font-semibold outline-none transition focus:border-sky-500"
          />
        </label>
        <CustomDropdown
          value={teamFilter}
          options={['All teams', ...teams]}
          onChange={setTeamFilter}
          icon={<Filter size={14} />}
          ariaLabel="Filter team actions by team"
          className="w-full"
          buttonClassName="w-full min-h-10 rounded-xl"
          size="md"
        />
        <CustomDropdown
          value={monthFilter}
          options={['All months', ...months]}
          onChange={setMonthFilter}
          icon={<CalendarDays size={14} />}
          ariaLabel="Filter team actions by month"
          className="w-full"
          buttonClassName="w-full min-h-10 rounded-xl"
          size="md"
        />
        <CustomDropdown
          value={statusFilter}
          options={['All statuses', ...TEAM_STATUS_OPTIONS]}
          onChange={setStatusFilter}
          icon={<Layers size={14} />}
          ariaLabel="Filter team actions by status"
          className="w-full"
          buttonClassName="w-full min-h-10 rounded-xl"
          size="md"
        />
      </div>

      {/* Content states */}
      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label="Loading team actions">
          {[0, 1, 2].map((idx) => (
            <div key={idx} className="pms-glass-surface h-56 animate-pulse rounded-[18px] p-5" />
          ))}
        </div>
      ) : isError ? (
        <div role="alert" className="pms-glass-surface flex flex-col items-center justify-center rounded-[18px] p-10 text-center">
          <AlertCircle size={30} className="text-rose-500" />
          <h3 className="mt-3 text-base font-black text-[var(--text-primary)]">Could not load whole-team actions</h3>
          <p className="mt-1 text-xs text-[var(--text-muted)]">Check your connection and retry.</p>
          <button
            type="button"
            onClick={() => void refetch()}
            className="mt-4 inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold text-white"
            style={{ background: 'linear-gradient(135deg, #0284C7 0%, #3898EC 100%)' }}
          >
            <RefreshCw size={13} /> Retry
          </button>
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="pms-glass-surface flex flex-col items-center justify-center rounded-[18px] p-12 text-center">
          <Layers size={32} className="text-[var(--text-muted)]" />
          <h3 className="mt-3 text-base font-black text-[var(--text-primary)]">
            {scopedItems.length === 0 ? 'No whole-team actions recorded yet' : 'No team actions match these filters'}
          </h3>
          <p className="mt-1 max-w-md text-xs text-[var(--text-muted)]">
            {scopedItems.length === 0
              ? 'Whole-team interventions created from Team-Level Action Plans, Team Dashboards, or right here will appear in this view.'
              : 'Try clearing a team, month, or status filter.'}
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label="Whole-team action records">
          {filteredItems.map((item) => (
            <TeamActionCard
              key={item.id}
              item={item}
              canEdit={canEdit}
              onStatusChange={async (id, status) => {
                await updateStatusMutation.mutateAsync({ id, status });
              }}
              onDelete={async (id) => {
                await deleteMutation.mutateAsync(id);
              }}
            />
          ))}
        </div>
      )}
    </section>
  );
}
