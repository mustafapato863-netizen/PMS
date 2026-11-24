import './PageEnhancements.css';
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  CalendarDays,
  ClipboardCheck,
  Download,
  FileText,
  Filter,
  Mail,
  RefreshCw,
  Search,
  Trash2,
  Users,
} from 'lucide-react';
import { useActionStore, useAllTeamActions, useFollowUp, useUpdateActionStatus } from '../hooks/useActionStore';
import CorrectiveActionsCard from '../components/executive/v1/CorrectiveActionsCard';
import { MONTHS, periodOf, summarizeActions } from '../features/executive/compose';
import { executiveFunctionForTeam } from '../features/executive/functions';
import { useUserRole } from '../context/RoleContext';
import CustomDropdown from '../components/common/CustomDropdown';
import ResponsiveFilters from '../components/common/ResponsiveFilters';
import { ActionFollowUpPanel } from '../components/actions/ActionFollowUpBoard';
import { TeamActionsPanel } from '../components/actions/TeamActionsPanel';
import { canDeleteCorrectiveAction, canEditActionFollowUp, dueBadgeLabel } from '../components/actions/dueBadge';
import { StatusPill } from '../components/actions/ActionStatusMenu';
import type { ActionType, PMSAction } from '../types';
import { formatActionRootCauseNote } from '../utils/actionNoteFormatter';
import { downloadCorrectiveActionsPowerPoint } from '../utils/correctiveActionPowerPoint';

const ACTION_TYPES: ActionType[] = ['Training', 'Reward', 'PIP', 'Monitor', 'Coaching'];

const ACTION_STYLES: Record<ActionType, { label: string; className: string; accent: string }> = {
  Training: { label: 'Training', className: 'border border-sky-300/60 bg-gradient-to-r from-sky-50 to-blue-100/80 text-sky-800 dark:border-sky-400/25 dark:from-sky-500/15 dark:to-blue-500/15 dark:text-sky-300', accent: 'var(--pms-grad-accent)' },
  Reward: { label: 'Reward', className: 'border border-emerald-300/60 bg-gradient-to-r from-emerald-50 to-teal-100/80 text-emerald-800 dark:border-emerald-400/25 dark:from-emerald-500/15 dark:to-teal-500/15 dark:text-emerald-300', accent: 'var(--pms-grad-grade-a)' },
  PIP: { label: 'PIP', className: 'border border-rose-300/60 bg-gradient-to-r from-rose-50 to-red-100/80 text-rose-800 dark:border-rose-400/25 dark:from-rose-500/15 dark:to-red-500/15 dark:text-rose-300', accent: 'var(--pms-grad-grade-e)' },
  Monitor: { label: 'Monitor', className: 'border border-amber-300/60 bg-gradient-to-r from-amber-50 to-orange-100/80 text-amber-800 dark:border-amber-400/25 dark:from-amber-500/15 dark:to-orange-500/15 dark:text-amber-300', accent: 'var(--pms-grad-grade-c)' },
  Coaching: { label: 'Coaching', className: 'border border-violet-300/60 bg-gradient-to-r from-violet-50 to-purple-100/80 text-violet-800 dark:border-violet-400/25 dark:from-violet-500/15 dark:to-purple-500/15 dark:text-violet-300', accent: 'var(--pms-grad-violet)' },
};

function formatDate(value: string): string {
  if (!value) return 'Date unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(date);
}

function buildOutlookComposeUrl(action: PMSAction): string {
  const subject = `Corrective action for ${action.employee_name || 'agent'} (${action.employee_id})`;
  const body = [
    `Agent: ${action.employee_name || 'Unknown employee'}`,
    `Agent ID: ${action.employee_id}`,
    `Team: ${action.team || 'Unassigned team'}`,
    `Period: ${action.month}`,
    `Action type: ${action.action_type}`,
    '',
    'Corrective action:',
    action.action_text || 'No action details provided.',
    '',
    'Root-cause note:',
    formatActionRootCauseNote(action.root_cause_note) || 'No note recorded.',
  ].join('\n');

  // Use encodeURIComponent instead of URLSearchParams — URLSearchParams encodes
  // spaces as '+' which Outlook deep-links do not decode back to spaces.
  const enc = encodeURIComponent;
  return `https://outlook.office.com/mail/deeplink/compose?to=${enc(action.employee_id)}&subject=${enc(subject)}&body=${enc(body)}`;
}

function ActionCard({
  action,
  canDelete = false,
  onDelete,
}: {
  action: PMSAction;
  canDelete?: boolean;
  onDelete?: (action: PMSAction) => Promise<boolean> | boolean;
}) {
  const style = ACTION_STYLES[action.action_type] || ACTION_STYLES.Coaching;
  const formattedRootCause = formatActionRootCauseNote(action.root_cause_note);
  const showDelete = canDelete && typeof onDelete === 'function' && Boolean(action.employee_id);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  useEffect(() => {
    if (!confirmingDelete || isDeleting) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setConfirmingDelete(false);
        setDeleteError('');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [confirmingDelete, isDeleting]);

  const handleConfirmDelete = async () => {
    if (!onDelete) return;
    setIsDeleting(true);
    setDeleteError('');
    try {
      const ok = await onDelete(action);
      if (ok === false) {
        setDeleteError('Failed to delete corrective action.');
        return;
      }
      setConfirmingDelete(false);
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : 'Failed to delete corrective action.');
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <article className="pms-glass-surface pms-glass-surface--interactive rf-action-card relative overflow-hidden rounded-[16px] p-5">
      <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[3px]" style={{ background: style.accent }} />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-black text-[var(--text-primary)]">{action.employee_name || 'Unknown employee'}</h2>
          <p className="mt-1 truncate text-xs font-semibold text-[var(--text-muted)]">{action.team || 'Unassigned team'} · {action.employee_id}</p>
        </div>
        <span className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold leading-5 ${style.className}`}>
          {style.label}
        </span>
      </div>

      {action.due_date && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <StatusPill status={action.status || 'Open'} />
          <span className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold leading-5 ${action.is_overdue || action.follow_up_state === 'overdue' ? 'bg-rose-500/10 text-rose-700 dark:text-rose-300' : action.follow_up_state === 'due_soon' ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300' : 'bg-[var(--bg-sunken)] text-[var(--text-secondary)]'}`}>
            {dueBadgeLabel(action.due_date, action.days_to_due)}
          </span>
        </div>
      )}
      <p className="mt-4 whitespace-pre-line text-xs font-semibold leading-5 text-[var(--text-secondary)]">{action.action_text || 'No action details provided.'}</p>
      <div className="mt-4 rounded-xl border border-[var(--pms-grad-panel-warn-border)] px-3 py-2.5 text-xs leading-4 text-[var(--text-secondary)]" style={{ background: 'var(--pms-grad-panel-warn)' }}>
        <span className="font-black text-amber-800 dark:text-amber-300">Root-cause note: </span>
        {formattedRootCause || 'No note recorded.'}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs font-semibold text-[var(--text-muted)]">
        <span className="inline-flex items-center gap-1.5"><CalendarDays size={13} />{action.month} · {formatDate(action.created_at)}</span>
        <span className="inline-flex items-center gap-1.5"><Users size={13} />By {action.created_by || 'Unknown'}</span>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Link
          to={`/employee/${encodeURIComponent(action.employee_id)}?month=${encodeURIComponent(action.month)}`}
          className="inline-flex items-center gap-1 text-xs font-black text-blue-600 hover:underline dark:text-blue-400"
        >
          Open profile <span aria-hidden="true">↗</span>
        </Link>
        <a
          href={buildOutlookComposeUrl(action)}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 rounded-lg border border-blue-500/25 px-2.5 py-1.5 text-xs font-black text-blue-600 transition-colors hover:bg-blue-500/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:text-blue-400"
          aria-label={`Forward corrective action for ${action.employee_name || action.employee_id} in Outlook`}
        >
          <Mail size={13} aria-hidden="true" />
          Forward in Outlook
        </a>
        {showDelete && (
          <button
            type="button"
            data-testid={`delete-corrective-action-${action.id}`}
            aria-label={`Delete corrective action for ${action.employee_name || action.employee_id}`}
            onClick={() => {
              setDeleteError('');
              setConfirmingDelete(true);
            }}
            className="inline-flex items-center gap-1 rounded-lg border border-rose-500/25 px-2.5 py-1.5 text-xs font-black text-rose-600 transition-colors hover:bg-rose-500/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 dark:text-rose-400"
          >
            <Trash2 size={13} aria-hidden="true" />
            Delete
          </button>
        )}
      </div>
      {confirmingDelete && (
        <div
          role="alertdialog"
          aria-label={`Confirm delete corrective action for ${action.employee_name || action.employee_id}`}
          className="mt-3 rounded-xl border border-rose-500/25 bg-rose-500/5 p-3"
        >
          <p className="text-xs font-semibold text-rose-800 dark:text-rose-200">
            Delete corrective action for {action.employee_name || action.employee_id}?
          </p>
          {deleteError && (
            <p role="alert" className="mt-1.5 text-xs font-semibold text-rose-700 dark:text-rose-300">
              {deleteError}
            </p>
          )}
          <div className="mt-2.5 flex justify-end gap-2">
            <button
              type="button"
              disabled={isDeleting}
              onClick={() => {
                setConfirmingDelete(false);
                setDeleteError('');
              }}
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
              {isDeleting ? 'Deleting…' : 'Delete Action'}
            </button>
          </div>
        </div>
      )}
    </article>
  );
}

export default function CorrectiveActionsView() {
  const { getAllActions, deleteAction } = useActionStore();
  const updateStatus = useUpdateActionStatus();
  const [params] = useSearchParams();
  const { role } = useUserRole();
  const allowDelete = canDeleteCorrectiveAction(role) && typeof deleteAction === 'function';
  const followUp = useFollowUp({});
  const overdueCount = followUp.data?.summary.overdue ?? 0;
  const teamActionsQuery = useAllTeamActions(true);
  const [pageTab, setPageTab] = useState<'all' | 'follow-up' | 'team-actions'>('all');
  const [search, setSearch] = useState('');
  const [teamFilter, setTeamFilter] = useState(params.get('team') ?? 'All teams');
  const [monthFilter, setMonthFilter] = useState(params.get('month') ?? 'All months');
  const [typeFilter, setTypeFilter] = useState('All types');
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState('');

  const actions = getAllActions();
  const functionFilter = params.get('function');
  const teamActionsCount = useMemo(() => {
    const items = teamActionsQuery.data ?? [];
    if (!functionFilter) return items.length;
    return items.filter((item) => executiveFunctionForTeam(item.team) === functionFilter).length;
  }, [teamActionsQuery.data, functionFilter]);
  const teams = useMemo(() => Array.from(new Set(actions.map((action) => action.team).filter(Boolean))).sort(), [actions]);
  const months = useMemo(() => Array.from(new Set(actions.map((action) => action.month).filter(Boolean))), [actions]);
  const filteredActions = useMemo(() => {
    const query = search.trim().toLowerCase();
    return actions.filter((action) => {
      if (functionFilter && executiveFunctionForTeam(action.team) !== functionFilter) return false;
      if (teamFilter !== 'All teams' && action.team !== teamFilter) return false;
      if (monthFilter !== 'All months' && action.month !== monthFilter) return false;
      if (typeFilter !== 'All types' && action.action_type !== typeFilter) return false;
      if (!query) return true;
      return [action.employee_name, action.employee_id, action.team, action.action_text, action.root_cause_note]
        .some((value) => String(value || '').toLowerCase().includes(query));
    });
  }, [actions, functionFilter, monthFilter, search, teamFilter, typeFilter]);
  const actionSummary = summarizeActions(filteredActions.map((action) => ({ ...action, status: action.status ?? 'Open', title: action.action_text })), new Date(), MONTHS.includes(monthFilter) ? periodOf(new Date().getFullYear(), monthFilter) : periodOf(new Date().getFullYear(), MONTHS[new Date().getMonth()]));

  const employeesActioned = new Set(filteredActions.map((action) => action.employee_id)).size;
  const teamsRepresented = new Set(filteredActions.map((action) => action.team).filter(Boolean)).size;
  const pendingSync = filteredActions.filter((action) => !action.synced).length;

  const handlePowerPointExport = async () => {
    setIsExporting(true);
    setExportError('');
    try {
      await downloadCorrectiveActionsPowerPoint(filteredActions, { team: teamFilter, month: monthFilter, type: typeFilter });
    } catch (error) {
      setExportError(error instanceof Error ? error.message : 'PowerPoint export failed.');
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="app-page-shell rf-page rf-page--corrective-actions executive-v1">
      <header className="pms-glass-surface rf-page-hero flex flex-col gap-4 rounded-[20px] p-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-[var(--insights-accent-text)]"><ClipboardCheck size={19} /><span className="text-xs font-black uppercase tracking-[0.18em]">Executive workspace</span></div>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-[var(--text-primary)]">Corrective Actions</h1>
          <p className="mt-1 max-w-2xl text-sm text-[var(--text-muted)]">Review corrective actions assigned to employees, with their notes and performance period.</p>
        </div>
        {pageTab === 'all' && (
          <button
            type="button"
            onClick={() => void handlePowerPointExport()}
            disabled={isExporting}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-black text-white shadow-sm transition-all hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 disabled:cursor-wait disabled:opacity-70"
            style={{ background: 'linear-gradient(135deg, #0284C7 0%, #3898EC 100%)' }}
          >
            <Download size={17} /> {isExporting ? 'Preparing PowerPoint…' : 'Export PowerPoint'}
          </button>
        )}
      </header>

      <div role="tablist" aria-label="Corrective action views" className="pms-glass-stage inline-flex w-fit flex-wrap gap-1.5 rounded-2xl p-1">
        <button type="button" role="tab" aria-selected={pageTab === 'all'} onClick={() => setPageTab('all')} className={`min-h-10 rounded-xl px-4 text-sm font-black transition-all ${pageTab === 'all' ? 'text-white shadow-sm' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}`} style={pageTab === 'all' ? { background: 'linear-gradient(135deg, #0284C7 0%, #3898EC 100%)' } : undefined}>All actions</button>
        <button type="button" role="tab" aria-selected={pageTab === 'follow-up'} onClick={() => setPageTab('follow-up')} className={`inline-flex min-h-10 items-center gap-2 rounded-xl px-4 text-sm font-black transition-all ${pageTab === 'follow-up' ? 'text-white shadow-sm' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}`} style={pageTab === 'follow-up' ? { background: 'linear-gradient(135deg, #0284C7 0%, #3898EC 100%)' } : undefined}>
          Follow-up
          {overdueCount > 0 && <span className="rounded-full bg-rose-500 px-2 py-0.5 text-xs font-black text-white" aria-label={`${overdueCount} overdue`}>{overdueCount}</span>}
        </button>
        <button type="button" role="tab" aria-selected={pageTab === 'team-actions'} onClick={() => setPageTab('team-actions')} className={`inline-flex min-h-10 items-center gap-2 rounded-xl px-4 text-sm font-black transition-all ${pageTab === 'team-actions' ? 'text-white shadow-sm' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}`} style={pageTab === 'team-actions' ? { background: 'linear-gradient(135deg, #0284C7 0%, #3898EC 100%)' } : undefined}>
          Team actions
          {teamActionsCount > 0 && <span className={`rounded-full px-2 py-0.5 text-xs font-black ${pageTab === 'team-actions' ? 'bg-white/25 text-white' : 'bg-indigo-500/15 text-indigo-700 dark:text-indigo-300'}`} aria-label={`${teamActionsCount} team actions`}>{teamActionsCount}</span>}
        </button>
      </div>

      {pageTab === 'follow-up' && <ActionFollowUpPanel canEdit={canEditActionFollowUp(role)} scopeFunction={functionFilter} initialFilters={{ team: teamFilter === 'All teams' ? undefined : teamFilter, month: monthFilter === 'All months' ? undefined : monthFilter }} />}

      {pageTab === 'team-actions' && <TeamActionsPanel canEdit={canEditActionFollowUp(role)} scopeFunction={functionFilter} availableTeams={teams} />}

      {pageTab === 'all' && exportError && <p role="alert" className="rounded-xl border border-rose-500/20 bg-rose-500/5 px-3 py-2 text-sm font-semibold text-rose-700 dark:text-rose-300">{exportError}</p>}

      {pageTab === 'all' && <CorrectiveActionsCard data={actionSummary} effective={MONTHS.includes(monthFilter) ? periodOf(new Date().getFullYear(), monthFilter) : null} variant="company" scopeLabel={functionFilter ?? (teamFilter !== 'All teams' ? teamFilter : 'Your authorized scope')} canEdit={canEditActionFollowUp(role)} onStatusChange={(id, update) => updateStatus.mutateAsync({ id, ...update })} hideWorkspaceLink />}

      {pageTab === 'all' && <section className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4" aria-label="Corrective action summary">
        <article className="pms-glass-surface rf-stat-card relative overflow-hidden rounded-[16px] p-4" style={{ background: 'var(--pms-grad-panel-info)', borderColor: 'var(--pms-grad-panel-info-border)' }}><span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[3px]" style={{ background: 'var(--pms-grad-accent)' }} /><p className="text-xs font-bold uppercase tracking-wider text-sky-700 dark:text-sky-300">Visible actions</p><p className="mt-2 text-3xl font-black text-[var(--text-primary)]">{filteredActions.length}</p></article>
        <article className="pms-glass-surface rf-stat-card relative overflow-hidden rounded-[16px] p-4" style={{ background: 'var(--pms-grad-panel-violet)', borderColor: 'var(--pms-grad-panel-violet-border)' }}><span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[3px]" style={{ background: 'var(--pms-grad-violet)' }} /><p className="text-xs font-bold uppercase tracking-wider text-violet-700 dark:text-violet-300">Employees actioned</p><p className="mt-2 text-3xl font-black text-[var(--text-primary)]">{employeesActioned}</p></article>
        <article className="pms-glass-surface rf-stat-card relative overflow-hidden rounded-[16px] p-4" style={{ background: 'var(--pms-grad-panel-pos)', borderColor: 'var(--pms-grad-panel-pos-border)' }}><span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[3px]" style={{ background: 'var(--pms-grad-grade-a)' }} /><p className="text-xs font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">Teams represented</p><p className="mt-2 text-3xl font-black text-[var(--text-primary)]">{teamsRepresented}</p></article>
        <article className="pms-glass-surface rf-stat-card relative overflow-hidden rounded-[16px] p-4" style={{ background: 'var(--pms-grad-panel-warn)', borderColor: 'var(--pms-grad-panel-warn-border)' }}><span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[3px]" style={{ background: 'var(--pms-grad-grade-c)' }} /><p className="text-xs font-bold uppercase tracking-wider text-amber-700 dark:text-amber-300">Pending sync</p><p className="mt-2 text-3xl font-black text-[var(--text-primary)]">{pendingSync}</p></article>
      </section>}

      {pageTab === 'all' && <ResponsiveFilters
        label="Action filters"
        activeCount={Number(Boolean(search.trim())) + Number(teamFilter !== 'All teams') + Number(monthFilter !== 'All months') + Number(typeFilter !== 'All types')}
      >
        <section className="responsive-filter-content" aria-label="Corrective action filters">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="relative block sm:col-span-2">
              <span className="sr-only">Search corrective actions</span>
              <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search employee, team or action…" className="min-h-11 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] pl-10 pr-3 text-sm outline-none transition focus:border-blue-500" />
            </label>
            <CustomDropdown value={teamFilter} options={['All teams', ...teams]} onChange={setTeamFilter} icon={<Filter size={15} />} ariaLabel="Filter by team" className="w-full" buttonClassName="w-full min-h-11 rounded-xl" size="lg" />
            <CustomDropdown value={monthFilter} options={['All months', ...months]} onChange={setMonthFilter} icon={<CalendarDays size={15} />} ariaLabel="Filter by month" className="w-full" buttonClassName="w-full min-h-11 rounded-xl" size="lg" />
            <CustomDropdown value={typeFilter} options={['All types', ...ACTION_TYPES]} onChange={setTypeFilter} icon={<FileText size={15} />} ariaLabel="Filter by action type" className="w-full sm:col-span-2" buttonClassName="w-full min-h-11 rounded-xl" size="lg" />
          </div>
        </section>
      </ResponsiveFilters>}

      {pageTab === 'all' && filteredActions.length > 0 ? (
        <section className="grid gap-4 md:grid-cols-2" aria-label="Corrective action records">
          {filteredActions.map((action) => (
            <ActionCard
              key={action.id}
              action={action}
              canDelete={allowDelete}
              onDelete={allowDelete ? (item) => deleteAction(item.id, item.employee_id) : undefined}
            />
          ))}
        </section>
      ) : pageTab === 'all' ? (
        <section className="glass-panel rf-empty-state rounded-2xl p-12 text-center shadow-sm">
          {actions.length === 0 ? <RefreshCw size={32} className="mx-auto text-[var(--text-muted)]" /> : <AlertCircle size={32} className="mx-auto text-[var(--text-muted)]" />}
          <h2 className="mt-4 text-lg font-black text-[var(--text-primary)]">{actions.length === 0 ? 'No corrective actions available' : 'No actions match these filters'}</h2>
          <p className="mt-2 text-sm text-[var(--text-muted)]">{actions.length === 0 ? 'The connected database returned no active actions for your scope.' : 'Try clearing a filter or changing the search term.'}</p>
        </section>
      ) : null}
    </div>
  );
}
