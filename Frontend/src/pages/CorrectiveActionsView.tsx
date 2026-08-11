import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertCircle,
  CalendarDays,
  ClipboardCheck,
  Download,
  FileText,
  Filter,
  RefreshCw,
  Search,
  Users,
} from 'lucide-react';
import { useActionStore } from '../hooks/useActionStore';
import CustomDropdown from '../components/common/CustomDropdown';
import type { ActionType, PMSAction } from '../types';
import { downloadCorrectiveActionsPowerPoint } from '../utils/correctiveActionPowerPoint';

const ACTION_TYPES: ActionType[] = ['Training', 'Reward', 'PIP', 'Monitor', 'Coaching'];

const ACTION_STYLES: Record<ActionType, { label: string; className: string }> = {
  Training: { label: 'Training', className: 'bg-blue-500/10 text-blue-700 dark:text-blue-300' },
  Reward: { label: 'Reward', className: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' },
  PIP: { label: 'PIP', className: 'bg-rose-500/10 text-rose-700 dark:text-rose-300' },
  Monitor: { label: 'Monitor', className: 'bg-amber-500/10 text-amber-700 dark:text-amber-300' },
  Coaching: { label: 'Coaching', className: 'bg-purple-500/10 text-purple-700 dark:text-purple-300' },
};

function formatDate(value: string): string {
  if (!value) return 'Date unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(date);
}

function ActionCard({ action }: { action: PMSAction }) {
  const style = ACTION_STYLES[action.action_type] || ACTION_STYLES.Coaching;
  return (
    <article className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-black text-[var(--text-primary)]">{action.employee_name || 'Unknown employee'}</h2>
          <p className="mt-1 truncate text-[11px] font-semibold text-[var(--text-muted)]">{action.team || 'Unassigned team'} · {action.employee_id}</p>
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] font-black uppercase tracking-wide ${style.className}`}>
          {style.label}
        </span>
      </div>

      <p className="mt-4 whitespace-pre-line text-xs font-semibold leading-5 text-[var(--text-secondary)]">{action.action_text || 'No action details provided.'}</p>
      <div className="mt-4 rounded-xl border border-amber-500/15 bg-amber-500/5 px-3 py-2.5 text-[11px] leading-4 text-[var(--text-secondary)]">
        <span className="font-black text-amber-700 dark:text-amber-300">Root-cause note: </span>
        {action.root_cause_note || 'No note recorded.'}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-[10px] font-semibold text-[var(--text-muted)]">
        <span className="inline-flex items-center gap-1.5"><CalendarDays size={13} />{action.month} · {formatDate(action.created_at)}</span>
        <span className="inline-flex items-center gap-1.5"><Users size={13} />By {action.created_by || 'Unknown'}</span>
      </div>
      <Link
        to={`/employee/${encodeURIComponent(action.employee_id)}?month=${encodeURIComponent(action.month)}`}
        className="mt-3 inline-flex items-center gap-1 text-[11px] font-black text-blue-600 hover:underline dark:text-blue-400"
      >
        Open profile <span aria-hidden="true">↗</span>
      </Link>
    </article>
  );
}

export default function CorrectiveActionsView() {
  const { getAllActions } = useActionStore();
  const [search, setSearch] = useState('');
  const [teamFilter, setTeamFilter] = useState('All teams');
  const [monthFilter, setMonthFilter] = useState('All months');
  const [typeFilter, setTypeFilter] = useState('All types');
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState('');

  const actions = getAllActions();
  const teams = useMemo(() => Array.from(new Set(actions.map((action) => action.team).filter(Boolean))).sort(), [actions]);
  const months = useMemo(() => Array.from(new Set(actions.map((action) => action.month).filter(Boolean))), [actions]);
  const filteredActions = useMemo(() => {
    const query = search.trim().toLowerCase();
    return actions.filter((action) => {
      if (teamFilter !== 'All teams' && action.team !== teamFilter) return false;
      if (monthFilter !== 'All months' && action.month !== monthFilter) return false;
      if (typeFilter !== 'All types' && action.action_type !== typeFilter) return false;
      if (!query) return true;
      return [action.employee_name, action.employee_id, action.team, action.action_text, action.root_cause_note]
        .some((value) => String(value || '').toLowerCase().includes(query));
    });
  }, [actions, monthFilter, search, teamFilter, typeFilter]);

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
    <div className="app-page-shell">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-blue-600 dark:text-blue-400"><ClipboardCheck size={19} /><span className="text-[11px] font-black uppercase tracking-[0.18em]">Executive workspace</span></div>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-[var(--text-primary)]">Corrective Actions</h1>
          <p className="mt-1 max-w-2xl text-sm text-[var(--text-muted)]">Review corrective actions assigned to employees, with their notes and performance period.</p>
        </div>
        <button
          type="button"
          onClick={() => void handlePowerPointExport()}
          disabled={isExporting}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-black text-white shadow-sm transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:cursor-wait disabled:opacity-70"
        >
          <Download size={17} /> {isExporting ? 'Preparing PowerPoint…' : 'Export PowerPoint'}
        </button>
      </header>

      {exportError && <p role="alert" className="rounded-xl border border-rose-500/20 bg-rose-500/5 px-3 py-2 text-sm font-semibold text-rose-700 dark:text-rose-300">{exportError}</p>}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Corrective action summary">
        <article className="rounded-2xl border border-blue-500/15 bg-blue-500/5 p-4"><p className="text-[10px] font-black uppercase tracking-wider text-blue-700 dark:text-blue-300">Visible actions</p><p className="mt-2 text-3xl font-black text-[var(--text-primary)]">{filteredActions.length}</p></article>
        <article className="rounded-2xl border border-purple-500/15 bg-purple-500/5 p-4"><p className="text-[10px] font-black uppercase tracking-wider text-purple-700 dark:text-purple-300">Employees actioned</p><p className="mt-2 text-3xl font-black text-[var(--text-primary)]">{employeesActioned}</p></article>
        <article className="rounded-2xl border border-emerald-500/15 bg-emerald-500/5 p-4"><p className="text-[10px] font-black uppercase tracking-wider text-emerald-700 dark:text-emerald-300">Teams represented</p><p className="mt-2 text-3xl font-black text-[var(--text-primary)]">{teamsRepresented}</p></article>
        <article className="rounded-2xl border border-amber-500/15 bg-amber-500/5 p-4"><p className="text-[10px] font-black uppercase tracking-wider text-amber-700 dark:text-amber-300">Pending sync</p><p className="mt-2 text-3xl font-black text-[var(--text-primary)]">{pendingSync}</p></article>
      </section>

      <section className="glass-panel rounded-2xl p-4 shadow-sm" aria-label="Corrective action filters">
        <div className="grid gap-3 lg:grid-cols-[minmax(240px,1fr)_repeat(3,minmax(150px,0.7fr))]">
          <label className="relative block">
            <span className="sr-only">Search corrective actions</span>
            <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search employee, team or action…" className="min-h-11 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] pl-10 pr-3 text-sm outline-none transition focus:border-blue-500" />
          </label>
          <CustomDropdown value={teamFilter} options={['All teams', ...teams]} onChange={setTeamFilter} icon={<Filter size={15} />} ariaLabel="Filter by team" className="w-full" buttonClassName="w-full min-h-11 rounded-xl" size="lg" />
          <CustomDropdown value={monthFilter} options={['All months', ...months]} onChange={setMonthFilter} icon={<CalendarDays size={15} />} ariaLabel="Filter by month" className="w-full" buttonClassName="w-full min-h-11 rounded-xl" size="lg" />
          <CustomDropdown value={typeFilter} options={['All types', ...ACTION_TYPES]} onChange={setTypeFilter} icon={<FileText size={15} />} ariaLabel="Filter by action type" className="w-full" buttonClassName="w-full min-h-11 rounded-xl" size="lg" />
        </div>
      </section>

      {filteredActions.length > 0 ? (
        <section className="grid gap-4 md:grid-cols-2" aria-label="Corrective action records">
          {filteredActions.map((action) => <ActionCard key={action.id} action={action} />)}
        </section>
      ) : (
        <section className="glass-panel rounded-2xl p-12 text-center shadow-sm">
          {actions.length === 0 ? <RefreshCw size={32} className="mx-auto text-[var(--text-muted)]" /> : <AlertCircle size={32} className="mx-auto text-[var(--text-muted)]" />}
          <h2 className="mt-4 text-lg font-black text-[var(--text-primary)]">{actions.length === 0 ? 'No corrective actions available' : 'No actions match these filters'}</h2>
          <p className="mt-2 text-sm text-[var(--text-muted)]">{actions.length === 0 ? 'The connected database returned no active actions for your scope.' : 'Try clearing a filter or changing the search term.'}</p>
        </section>
      )}
    </div>
  );
}
