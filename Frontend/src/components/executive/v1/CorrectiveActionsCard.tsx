import { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, Clock, Inbox, Plus, Shield, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ExecutiveActionItem, ExecutiveCorrectiveActions, ExecutivePeriod } from '../../../features/executive/types';
import { fmtDate } from '../../../features/executive/format';
import { actionStatus } from './execModel';
import { ActionStatusMenu } from '../../actions/ActionStatusMenu';
import type { ActionStatus } from '../../../types';
import { formatActionRootCauseNote } from '../../../utils/actionNoteFormatter';
import { ExecCard, ExecCardHeader, SoftEmpty, StatusPill } from './ExecPrimitives';

type Filter = 'all' | 'open' | 'overdue' | 'due_this_week' | 'closed';
type TileFilter = Exclude<Filter, 'all'>;

/** Rows shown before "Show all". The list is already ordered: overdue, due soonest, newest. */
const PREVIEW_ROWS = 10;
const FILTER_LABEL: Record<TileFilter, string> = {
  open: 'open',
  overdue: 'overdue',
  due_this_week: 'due this week',
  closed: 'closed this month',
};
/** Columns from md up: Employee, Action, Reason / KPI, Owner, Due, Status. */
const ROW_COLUMNS = 'md:grid-cols-[minmax(0,1.3fr)_minmax(0,2.6fr)_minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,0.85fr)_150px]';
const HEAD = 'text-[11px] font-bold uppercase tracking-wider text-[var(--text-muted)]';

const ACTION_TYPE_PILL: Record<string, string> = {
  PIP: 'border-rose-300/60 bg-gradient-to-r from-rose-50 to-red-100/80 text-rose-800 dark:border-rose-400/25 dark:from-rose-500/15 dark:to-red-500/15 dark:text-rose-300',
  Coaching: 'border-violet-300/60 bg-gradient-to-r from-violet-50 to-purple-100/80 text-violet-800 dark:border-violet-400/25 dark:from-violet-500/15 dark:to-purple-500/15 dark:text-violet-300',
  Training: 'border-sky-300/60 bg-gradient-to-r from-sky-50 to-blue-100/80 text-sky-800 dark:border-sky-400/25 dark:from-sky-500/15 dark:to-blue-500/15 dark:text-sky-300',
  Monitor: 'border-amber-300/60 bg-gradient-to-r from-amber-50 to-orange-100/80 text-amber-800 dark:border-amber-400/25 dark:from-amber-500/15 dark:to-orange-500/15 dark:text-amber-300',
  Reward: 'border-emerald-300/60 bg-gradient-to-r from-emerald-50 to-teal-100/80 text-emerald-800 dark:border-emerald-400/25 dark:from-emerald-500/15 dark:to-teal-500/15 dark:text-emerald-300',
  'Team Action': 'border-indigo-300/60 bg-gradient-to-r from-indigo-50 to-sky-100/80 text-indigo-800 dark:border-indigo-400/25 dark:from-indigo-500/15 dark:to-sky-500/15 dark:text-indigo-300',
};

const TILE_TONE: Record<TileFilter, { bg: string; border: string; accent: string }> = {
  open: {
    bg: 'var(--pms-grad-panel-info)',
    border: 'var(--pms-grad-panel-info-border)',
    accent: 'var(--pms-grad-accent)',
  },
  overdue: {
    bg: 'var(--pms-grad-panel-neg)',
    border: 'var(--pms-grad-panel-neg-border)',
    accent: 'var(--pms-grad-grade-e)',
  },
  due_this_week: {
    bg: 'var(--pms-grad-panel-warn)',
    border: 'var(--pms-grad-panel-warn-border)',
    accent: 'var(--pms-grad-grade-c)',
  },
  closed: {
    bg: 'var(--pms-grad-panel-pos)',
    border: 'var(--pms-grad-panel-pos-border)',
    accent: 'var(--pms-grad-grade-a)',
  },
};

function matches(item: ExecutiveActionItem, filter: Filter): boolean {
  if (filter === 'all') return true;
  if (filter === 'closed') return item.status === 'Completed';
  if (filter === 'open') return item.status === 'Open' || item.status === 'In Progress';
  if (filter === 'overdue') return item.follow_up_state === 'overdue';
  return item.follow_up_state === 'due_this_week';
}

function Tile({ label, value, icon: Icon, color, tone, active, onToggle }: {
  label: string;
  value: number | null;
  icon: LucideIcon;
  color: string;
  tone: TileFilter;
  active: boolean;
  onToggle: () => void;
}) {
  const palette = TILE_TONE[tone];
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onToggle}
      data-testid={`action-tile-${label.toLowerCase().replace(/[^a-z]+/g, '-').replace(/-$/, '')}`}
      className={`pms-glass-surface pms-glass-surface--interactive relative flex flex-col gap-[6px] overflow-hidden rounded-[14px] px-[16px] py-[14px] text-left transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--insights-accent)] ${active ? 'ring-2 ring-[var(--insights-accent)]' : ''}`}
      style={{ background: palette.bg, borderColor: palette.border }}
    >
      <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[3px]" style={{ background: palette.accent }} />
      <span className="inline-flex items-center gap-[6px] text-xs font-bold text-[var(--text-secondary)]">
        <Icon aria-hidden="true" className="size-[14px]" strokeWidth={2} style={{ color }} />
        {label}
      </span>
      <span className="text-[26px] font-black leading-[1.08] tracking-tight tabular-nums" style={{ color }}>
        {value ?? '—'}
      </span>
    </button>
  );
}

function ActionRow({ item, workspaceHref, canEdit, onStatusChange, open, onToggle }: {
  item: ExecutiveActionItem;
  workspaceHref: string;
  canEdit: boolean;
  onStatusChange?: (id: string, update: { status: ActionStatus; completion_note?: string }) => Promise<unknown>;
  open: boolean;
  onToggle: () => void;
}) {
  const status = actionStatus(item);
  const overdue = item.follow_up_state === 'overdue';
  const text = (item.action_text || item.title || '').trim();
  const firstLine = text.split('\n')[0];
  const detailId = `action-detail-${item.id}`;
  const employeeHref = item.employee_id ? `/employee/${encodeURIComponent(item.employee_id)}${item.month ? `?month=${encodeURIComponent(item.month)}` : ''}` : workspaceHref;
  const pillClass = item.action_type
    ? (ACTION_TYPE_PILL[item.action_type] ?? 'border-[var(--border-light)] bg-[var(--exec-chip-bg)] text-[var(--exec-chip-text)]')
    : '';
  return (
    <>
      <div
        role="row"
        data-testid="action-row"
        className={`flex flex-col gap-[6px] border-b border-[var(--insights-row-border)] px-[14px] py-[11px] transition-colors last:border-b-0 hover:bg-white/60 dark:hover:bg-slate-800/35 md:grid md:min-h-[54px] md:items-center md:gap-[12px] md:py-[8px] ${ROW_COLUMNS}`}
      >
        <span role="cell" className="min-w-0">
          <Link to={employeeHref} className="block truncate text-[13px] font-bold text-[var(--insights-heading)] hover:text-sky-600 hover:underline dark:hover:text-sky-400">
            {item.employee_name || 'Whole team'}
          </Link>
          {item.team && <span className="block truncate text-xs font-medium text-[var(--text-muted)]">{item.team}</span>}
        </span>
        <span role="cell" className="flex min-w-0 items-center gap-[8px]">
          {item.action_type && (
            <span className={`shrink-0 rounded-full border px-[9px] py-[2px] text-[11px] font-bold ${pillClass}`}>
              {item.action_type}
            </span>
          )}
          <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-[var(--insights-heading)]">{firstLine || 'No action text'}</span>
          {text && (
            <button
              type="button"
              aria-expanded={open}
              aria-controls={detailId}
              aria-label={open ? `Hide full action for ${item.employee_name || 'this action'}` : `Show full action for ${item.employee_name || 'this action'}`}
              onClick={onToggle}
              className="inline-flex size-[28px] shrink-0 items-center justify-center rounded-lg border border-transparent text-[var(--text-muted)] transition-colors hover:border-[var(--border-light)] hover:bg-[var(--bg-surface)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--insights-accent)]"
            >
              <ChevronDown aria-hidden="true" size={14} className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
            </button>
          )}
        </span>
        <span role="cell" className="min-w-0 text-xs text-[var(--text-secondary)]">
          <span className="md:hidden text-[var(--text-muted)]">Reason: </span>
          <span className="block truncate font-medium">{formatActionRootCauseNote(item.root_cause) || '—'}</span>
          {item.linked_kpi_key && <span className="block truncate text-[11px] text-[var(--text-muted)]">KPI: {item.linked_kpi_key}</span>}
        </span>
        <span role="cell" className={`min-w-0 text-xs font-medium ${item.owner ? 'text-[var(--text-secondary)]' : 'text-[var(--text-muted)]'}`}>
          <span className="md:hidden text-[var(--text-muted)]">Owner: </span>
          <span className="block truncate">{item.owner?.name ?? 'Unassigned'}</span>
        </span>
        <span role="cell" className="text-xs md:text-right" style={{ color: overdue ? 'var(--insights-negative)' : 'var(--text-secondary)' }}>
          <span className="md:hidden text-[var(--text-muted)]">Due: </span>
          {item.due_date ? (
            <span className={overdue ? 'inline-flex rounded-full border border-rose-300/60 bg-rose-500/10 px-2 py-0.5 font-bold text-rose-700 dark:border-rose-400/30 dark:text-rose-300' : 'font-medium'}>
              {fmtDate(item.due_date)}
            </span>
          ) : (
            <span className="text-[var(--text-muted)]">No due date</span>
          )}
          {overdue && <span className="sr-only"> (overdue)</span>}
        </span>
        <span role="cell" className="flex items-center md:justify-end">
          {canEdit && onStatusChange
            ? <ActionStatusMenu status={item.status} canEdit ariaLabel={`Status for ${firstLine || item.employee_name || 'action'}`} compact onChange={(update) => onStatusChange(item.id, update)} />
            : <StatusPill tone={status.tone} icon={status.icon}>{status.label}</StatusPill>}
        </span>
      </div>
      {open && text && (
        <div id={detailId} role="row" className="border-b border-[var(--insights-row-border)] bg-sky-50/40 px-[16px] py-[12px] dark:bg-sky-950/20">
          <p role="cell" className="whitespace-pre-wrap text-[13px] leading-[1.55] text-[var(--text-secondary)]">{text}</p>
        </div>
      )}
    </>
  );
}

export default function CorrectiveActionsCard({ data, effective, variant, canCreate, scopeLabel, canEdit = false, onStatusChange, hideWorkspaceLink = false }: {
  data: ExecutiveCorrectiveActions | null;
  effective: ExecutivePeriod | null;
  variant: 'company' | 'team' | 'function';
  canCreate?: boolean;
  scopeLabel?: string;
  canEdit?: boolean;
  onStatusChange?: (id: string, update: { status: ActionStatus; completion_note?: string }) => Promise<unknown>;
  hideWorkspaceLink?: boolean;
}) {
  const [filter, setFilter] = useState<Filter>('all');
  const [showAll, setShowAll] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const title = variant === 'team' ? 'My corrective actions' : 'Corrective actions';
  const scope = scopeLabel ?? (variant === 'team' ? 'Your team' : 'Company-wide');
  const workspaceHref = variant === 'function' && scopeLabel ? `/corrective-actions?function=${encodeURIComponent(scopeLabel)}` : '/corrective-actions';
  const rows = useMemo(() => (data ? (data.rows ?? data.actions) : []), [data]);
  const visible = useMemo(() => rows.filter((item) => matches(item, filter)), [rows, filter]);
  const shown = showAll ? visible : visible.slice(0, PREVIEW_ROWS);

  // A tile is a filter: clicking the active tile again, or "Show all actions", returns to every row.
  const toggleFilter = (next: TileFilter) => {
    setFilter((current) => (current === next ? 'all' : next));
    setShowAll(false);
  };
  const toggleExpanded = (id: string) => setExpanded((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

  const action = (variant === 'team' && canCreate) || !hideWorkspaceLink ? (
    <div className="flex flex-wrap gap-[8px]">
      {variant === 'team' && canCreate && (
        <Link to="/corrective-actions" className="inline-flex shrink-0 items-center gap-[4px] rounded-[10px] px-[12px] py-[7px] text-[12px] font-bold text-white shadow-sm transition-all hover:brightness-95" style={{ background: 'linear-gradient(135deg, #0284C7 0%, #3898EC 100%)' }}>
          <Plus aria-hidden="true" className="size-[13px]" strokeWidth={2} />New action
        </Link>
      )}
      {!hideWorkspaceLink && (
        <Link to={workspaceHref} className="inline-flex shrink-0 items-center rounded-[10px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-[12px] py-[7px] text-[12px] font-bold text-[var(--insights-accent-text)] transition-colors hover:brightness-95">
          {variant === 'team' ? 'View all' : 'Open Corrective Actions'}
        </Link>
      )}
    </div>
  ) : undefined;
  return (
    <ExecCard aria-labelledby="exec-actions-title">
      <ExecCardHeader
        titleId="exec-actions-title"
        icon={Shield}
        iconBg="var(--exec-info-bg)"
        iconColor="var(--exec-info-text)"
        title={title}
        subtitle={data ? `${scope} · as of ${fmtDate(data.summary.as_of)}` : scope}
        action={action}
      />
      {!data ? (
        <SoftEmpty>Corrective actions couldn&apos;t be loaded for this view.</SoftEmpty>
      ) : (
        <>
          <div className={`grid gap-[12px] ${variant === 'team' ? 'grid-cols-3' : 'grid-cols-2 lg:grid-cols-4'}`}>
            <Tile label="Open" value={data.summary.open} icon={Inbox} color="var(--insights-accent-text)" tone="open" active={filter === 'open'} onToggle={() => toggleFilter('open')} />
            <Tile label="Overdue" value={data.summary.overdue} icon={AlertTriangle} color="var(--insights-negative)" tone="overdue" active={filter === 'overdue'} onToggle={() => toggleFilter('overdue')} />
            <Tile label="Due this week" value={data.summary.due_this_week} icon={Clock} color="var(--exec-warning)" tone="due_this_week" active={filter === 'due_this_week'} onToggle={() => toggleFilter('due_this_week')} />
            {variant !== 'team' && <Tile label={`Closed in ${effective?.month ?? 'month'}`} value={data.summary.closed_in_month} icon={CheckCircle2} color="var(--insights-positive)" tone="closed" active={filter === 'closed'} onToggle={() => toggleFilter('closed')} />}
          </div>
          {filter !== 'all' && (
            <div className="flex items-center justify-between gap-[8px] rounded-xl border border-[var(--pms-glass-stage-border)] bg-[var(--pms-glass-stage-bg)] px-3 py-2 text-xs text-[var(--text-secondary)]">
              <span className="font-semibold">{visible.length} {FILTER_LABEL[filter]}</span>
              <button type="button" onClick={() => { setFilter('all'); setShowAll(false); }} className="font-bold text-[var(--insights-accent-text)] hover:underline">Show all actions</button>
            </div>
          )}
          {rows.length === 0 ? (
            <SoftEmpty>No open corrective actions.</SoftEmpty>
          ) : visible.length === 0 ? (
            <SoftEmpty>No {FILTER_LABEL[filter as TileFilter]} actions.</SoftEmpty>
          ) : (
            <>
              <div role="table" aria-label={title} className="pms-glass-stage flex flex-col overflow-hidden rounded-[14px]">
                <div role="row" className={`hidden border-b border-[var(--insights-row-border)] bg-[var(--exec-table-head-bg)] px-[14px] py-[10px] md:grid md:items-center md:gap-[12px] ${ROW_COLUMNS}`}>
                  <span role="columnheader" className={HEAD}>Employee</span>
                  <span role="columnheader" className={HEAD}>Action</span>
                  <span role="columnheader" className={HEAD}>Reason / KPI</span>
                  <span role="columnheader" className={HEAD}>Owner</span>
                  <span role="columnheader" className={`${HEAD} md:text-right`}>Due</span>
                  <span role="columnheader" className={HEAD}>Status</span>
                </div>
                {shown.map((item) => (
                  <ActionRow
                    key={item.id}
                    item={item}
                    workspaceHref={workspaceHref}
                    canEdit={canEdit}
                    onStatusChange={onStatusChange}
                    open={expanded.has(item.id)}
                    onToggle={() => toggleExpanded(item.id)}
                  />
                ))}
              </div>
              {visible.length > PREVIEW_ROWS && (
                <button
                  type="button"
                  aria-expanded={showAll}
                  onClick={() => setShowAll((value) => !value)}
                  className="inline-flex self-start items-center gap-1.5 rounded-xl border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-3 py-1.5 text-xs font-bold text-[var(--insights-accent-text)] transition-colors hover:brightness-95"
                >
                  {showAll ? 'Show fewer' : `Show all ${visible.length}`}
                </button>
              )}
            </>
          )}
        </>
      )}
    </ExecCard>
  );
}
