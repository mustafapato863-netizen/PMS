import { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, Clock, Inbox, Plus, Shield, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ExecutiveActionItem, ExecutiveCorrectiveActions, ExecutivePeriod } from '../../../features/executive/types';
import { fmtDate } from '../../../features/executive/format';
import { actionStatus } from './execModel';
import { ActionStatusMenu } from '../../actions/ActionStatusMenu';
import type { ActionStatus } from '../../../types';
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
const ROW_COLUMNS = 'md:grid-cols-[minmax(0,1.3fr)_minmax(0,2.6fr)_minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,0.8fr)_150px]';
const HEAD = 'text-xs font-semibold text-[var(--text-muted)]';

function matches(item: ExecutiveActionItem, filter: Filter): boolean {
  if (filter === 'all') return true;
  if (filter === 'closed') return item.status === 'Completed';
  if (filter === 'open') return item.status === 'Open' || item.status === 'In Progress';
  if (filter === 'overdue') return item.follow_up_state === 'overdue';
  return item.follow_up_state === 'due_this_week';
}

function Tile({ label, value, icon: Icon, color, active, onToggle }: {
  label: string;
  value: number | null;
  icon: LucideIcon;
  color: string;
  active: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onToggle}
      data-testid={`action-tile-${label.toLowerCase().replace(/[^a-z]+/g, '-').replace(/-$/, '')}`}
      className={`flex flex-col gap-[6px] rounded-[10px] bg-[var(--exec-tile-bg)] px-[16px] py-[14px] text-left transition-shadow focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--insights-accent)] ${active ? 'ring-2 ring-[var(--insights-accent)]' : ''}`}
    >
      <span className="inline-flex items-center gap-[6px] text-xs font-semibold text-[var(--text-muted)]">
        <Icon aria-hidden="true" className="size-[14px]" strokeWidth={1.75} />
        {label}
      </span>
      <span className="text-[24px] font-bold leading-[1.1]" style={{ color }}>{value ?? '—'}</span>
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
  return (
    <>
      <div role="row" data-testid="action-row" className={`flex flex-col gap-[6px] border-b border-[var(--insights-row-border)] px-[12px] py-[10px] md:grid md:min-h-[48px] md:items-center md:gap-[12px] md:py-[6px] ${ROW_COLUMNS}`}>
        <span role="cell" className="min-w-0">
          <Link to={employeeHref} className="block truncate text-[13px] font-semibold text-[var(--insights-heading)] hover:underline">{item.employee_name || 'Whole team'}</Link>
          {item.team && <span className="block truncate text-xs text-[var(--text-muted)]">{item.team}</span>}
        </span>
        <span role="cell" className="flex min-w-0 items-center gap-[8px]">
          {item.action_type && <span className="shrink-0 rounded-full bg-[var(--exec-chip-bg)] px-[8px] py-[2px] text-xs font-semibold text-[var(--exec-chip-text)]">{item.action_type}</span>}
          <span className="min-w-0 flex-1 truncate text-[13px] text-[var(--insights-heading)]">{firstLine || 'No action text'}</span>
          {text && (
            <button
              type="button"
              aria-expanded={open}
              aria-controls={detailId}
              aria-label={open ? `Hide full action for ${item.employee_name || 'this action'}` : `Show full action for ${item.employee_name || 'this action'}`}
              onClick={onToggle}
              className="inline-flex size-[28px] shrink-0 items-center justify-center rounded-[6px] text-[var(--text-muted)] hover:bg-[var(--bg-sunken)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--insights-accent)]"
            >
              <ChevronDown aria-hidden="true" size={14} className={open ? 'rotate-180' : ''} />
            </button>
          )}
        </span>
        <span role="cell" className="min-w-0 text-xs text-[var(--text-secondary)]">
          <span className="md:hidden text-[var(--text-muted)]">Reason: </span>
          <span className="block truncate">{item.root_cause || '—'}</span>
          {item.linked_kpi_key && <span className="block truncate text-[var(--text-muted)]">KPI: {item.linked_kpi_key}</span>}
        </span>
        <span role="cell" className={`min-w-0 text-xs ${item.owner ? 'text-[var(--text-secondary)]' : 'text-[var(--text-muted)]'}`}>
          <span className="md:hidden text-[var(--text-muted)]">Owner: </span>
          <span className="block truncate">{item.owner?.name ?? 'Unassigned'}</span>
        </span>
        <span role="cell" className="text-xs md:text-right" style={{ color: overdue ? 'var(--insights-negative)' : 'var(--text-secondary)' }}>
          <span className="md:hidden text-[var(--text-muted)]">Due: </span>
          {item.due_date ? <span>{fmtDate(item.due_date)}</span> : <span className="text-[var(--text-muted)]">No due date</span>}
          {overdue && <span className="sr-only"> (overdue)</span>}
        </span>
        <span role="cell" className="flex items-center md:justify-end">
          {canEdit && onStatusChange
            ? <ActionStatusMenu status={item.status} canEdit ariaLabel={`Status for ${firstLine || item.employee_name || 'action'}`} compact onChange={(update) => onStatusChange(item.id, update)} />
            : <StatusPill tone={status.tone} icon={status.icon}>{status.label}</StatusPill>}
        </span>
      </div>
      {open && text && (
        <div id={detailId} role="row" className="border-b border-[var(--insights-row-border)] px-[12px] py-[10px]">
          <p role="cell" className="whitespace-pre-wrap text-[13px] leading-[1.5] text-[var(--text-secondary)]">{text}</p>
        </div>
      )}
    </>
  );
}

export default function CorrectiveActionsCard({ data, effective, variant, canCreate, scopeLabel, canEdit = false, onStatusChange }: {
  data: ExecutiveCorrectiveActions | null;
  effective: ExecutivePeriod | null;
  variant: 'company' | 'team' | 'function';
  canCreate?: boolean;
  scopeLabel?: string;
  canEdit?: boolean;
  onStatusChange?: (id: string, update: { status: ActionStatus; completion_note?: string }) => Promise<unknown>;
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

  const action = (
    <div className="flex flex-wrap gap-[8px]">
      {variant === 'team' && canCreate && (
        <Link to="/corrective-actions" className="inline-flex shrink-0 items-center gap-[4px] rounded-[8px] bg-[var(--insights-accent)] px-[10px] py-[6px] text-[12px] font-semibold text-white">
          <Plus aria-hidden="true" className="size-[13px]" strokeWidth={2} />New action
        </Link>
      )}
      <Link to={workspaceHref} className="inline-flex shrink-0 items-center rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-[10px] py-[6px] text-[12px] font-semibold text-[var(--insights-accent-text)]">{variant === 'team' ? 'View all' : 'Open Corrective Actions'}</Link>
    </div>
  );
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
            <Tile label="Open" value={data.summary.open} icon={Inbox} color="var(--insights-heading)" active={filter === 'open'} onToggle={() => toggleFilter('open')} />
            <Tile label="Overdue" value={data.summary.overdue} icon={AlertTriangle} color="var(--insights-negative)" active={filter === 'overdue'} onToggle={() => toggleFilter('overdue')} />
            <Tile label="Due this week" value={data.summary.due_this_week} icon={Clock} color="var(--exec-warning)" active={filter === 'due_this_week'} onToggle={() => toggleFilter('due_this_week')} />
            {variant !== 'team' && <Tile label={`Closed in ${effective?.month ?? 'month'}`} value={data.summary.closed_in_month} icon={CheckCircle2} color="var(--insights-positive)" active={filter === 'closed'} onToggle={() => toggleFilter('closed')} />}
          </div>
          {filter !== 'all' && (
            <div className="flex items-center justify-between gap-[8px] text-xs text-[var(--text-secondary)]">
              <span>{visible.length} {FILTER_LABEL[filter]}</span>
              <button type="button" onClick={() => { setFilter('all'); setShowAll(false); }} className="font-semibold text-[var(--insights-accent-text)] hover:underline">Show all actions</button>
            </div>
          )}
          {rows.length === 0 ? (
            <SoftEmpty>No open corrective actions.</SoftEmpty>
          ) : visible.length === 0 ? (
            <SoftEmpty>No {FILTER_LABEL[filter as TileFilter]} actions.</SoftEmpty>
          ) : (
            <>
              <div role="table" aria-label={title} className="flex flex-col">
                <div role="row" className={`hidden rounded-[8px] bg-[var(--exec-table-head-bg)] px-[12px] py-[8px] md:grid md:items-center md:gap-[12px] ${ROW_COLUMNS}`}>
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
                <button type="button" aria-expanded={showAll} onClick={() => setShowAll((value) => !value)} className="self-start text-xs font-semibold text-[var(--insights-accent-text)] hover:underline">
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
