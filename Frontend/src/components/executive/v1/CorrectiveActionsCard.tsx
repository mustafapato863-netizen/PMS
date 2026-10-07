import { AlertTriangle, CheckCircle2, Clock, Inbox, Plus, Shield, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ExecutiveCorrectiveActions, ExecutivePeriod } from '../../../features/executive/types';
import { fmtDate } from '../../../features/executive/format';
import { actionStatus } from './execModel';
import { ActionStatusMenu } from '../../actions/ActionStatusMenu';
import type { ActionStatus } from '../../../types';
import { ExecCard, ExecCardHeader, SoftEmpty, StatusPill } from './ExecPrimitives';

function Tile({ label, value, icon: Icon, color }: { label: string; value: number | null; icon: LucideIcon; color: string }) {
  return (
    <div className="flex flex-col gap-[6px] rounded-[10px] bg-[var(--exec-tile-bg)] px-[16px] py-[14px]" data-testid={`action-tile-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <span className="inline-flex items-center gap-[6px] text-[10px] font-semibold uppercase tracking-[0.6px] text-[var(--text-muted)]">
        <Icon aria-hidden="true" className="size-[14px]" strokeWidth={1.75} />
        {label}
      </span>
      <span className="text-[26px] font-bold leading-[1.1]" style={{ color }}>{value ?? '—'}</span>
    </div>
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
  const title = variant === 'team' ? 'My corrective actions' : 'Corrective actions';
  const scope = scopeLabel ?? (variant === 'team' ? 'Your team' : 'Company-wide');
  const workspaceHref = variant === 'function' && scopeLabel ? `/corrective-actions?function=${encodeURIComponent(scopeLabel)}` : '/corrective-actions';
  const head = 'text-[10px] font-semibold uppercase tracking-[0.6px] text-[var(--text-muted)]';
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
            <Tile label="Open" value={data.summary.open} icon={Inbox} color="var(--insights-heading)" />
            <Tile label="Overdue" value={data.summary.overdue} icon={AlertTriangle} color="var(--insights-negative)" />
            <Tile label="Due this week" value={data.summary.due_this_week} icon={Clock} color="var(--exec-warning)" />
            {variant !== 'team' && <Tile label={`Closed in ${effective?.month ?? 'month'}`} value={data.summary.closed_in_month} icon={CheckCircle2} color="var(--insights-positive)" />}
          </div>
          {variant === 'team' && data.actions.length ? (
            <ul aria-label={title} className="flex flex-col">
              {data.actions.map((item) => {
                const status = actionStatus(item);
                return (
                  <li key={item.id} className="flex items-center gap-[12px] border-b border-[var(--insights-row-border)] py-[10px] last:border-b-0" data-testid="action-row">
                    <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
                          <Link to={item.employee_id ? `/employee/${encodeURIComponent(item.employee_id)}${item.month ? `?month=${encodeURIComponent(item.month)}` : ''}` : workspaceHref} className="truncate text-[13px] font-semibold text-[var(--insights-heading)] hover:underline">{item.title}</Link>
                      <span className="truncate text-[11px] text-[var(--text-muted)]">{item.employee_name || 'Whole team'}</span>
                    </span>
                    <span className="flex shrink-0 flex-col items-end gap-[3px]">
                      <StatusPill tone={status.tone} icon={status.icon}>{status.label}</StatusPill>
                      {canEdit && onStatusChange && <ActionStatusMenu status={item.status} canEdit ariaLabel={`Status for ${item.title}`} compact onChange={(update) => onStatusChange(item.id, update)} />}
                      <span className="text-[11px]" style={{ color: status.tone === 'danger' ? 'var(--insights-negative)' : 'var(--text-muted)' }}>Due {fmtDate(item.due_date)}</span>
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : data.actions.length ? (
            <div role="table" aria-label={title} className="flex flex-col">
              <div role="row" className="flex items-center gap-[12px] rounded-[8px] bg-[var(--exec-table-head-bg)] px-[12px] py-[9px]">
                <span role="columnheader" className={`${head} min-w-0 flex-1`}>Action</span>
                <span role="columnheader" className={`${head} hidden w-[200px] md:block`}>Team</span>
                <span role="columnheader" className={`${head} hidden w-[140px] lg:block`}>Owner</span>
                <span role="columnheader" className={`${head} w-[90px] text-right`}>Due</span>
                <span role="columnheader" className={`${head} w-[130px]`}>Status</span>
              </div>
              {data.actions.map((item) => {
                const status = actionStatus(item);
                return (
                  <div role="row" key={item.id} className="flex items-center gap-[12px] border-b border-[var(--insights-row-border)] px-[12px] py-[10px] last:border-b-0" data-testid="action-row">
                    <span role="cell" className="min-w-0 flex-1 truncate text-[13px] font-medium text-[var(--insights-heading)]"><Link to={item.employee_id ? `/employee/${encodeURIComponent(item.employee_id)}${item.month ? `?month=${encodeURIComponent(item.month)}` : ''}` : workspaceHref} className="hover:underline">{item.title}{item.employee_name ? ` — ${item.employee_name}` : ''}</Link></span>
                    <span role="cell" className="hidden w-[200px] truncate text-[12px] text-[var(--text-secondary)] md:block">{[item.team, item.region].filter(Boolean).join(' · ') || '—'}</span>
                    <span role="cell" className="hidden w-[140px] truncate text-[12px] text-[var(--text-secondary)] lg:block">{item.owner?.name ?? 'Unassigned'}</span>
                    <span role="cell" className="w-[90px] text-right text-[12px]" style={{ color: status.tone === 'danger' ? 'var(--insights-negative)' : 'var(--text-secondary)' }}>{fmtDate(item.due_date)}</span>
                    <span role="cell" className="flex w-[130px] flex-col items-start gap-[4px]"><StatusPill tone={status.tone} icon={status.icon}>{status.label}</StatusPill>{canEdit && onStatusChange && <ActionStatusMenu status={item.status} canEdit ariaLabel={`Status for ${item.title}`} compact onChange={(update) => onStatusChange(item.id, update)} />}</span>
                  </div>
                );
              })}
            </div>
          ) : <SoftEmpty>No open corrective actions.</SoftEmpty>}
        </>
      )}
    </ExecCard>
  );
}
