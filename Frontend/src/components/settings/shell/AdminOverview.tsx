import { Link } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { ArrowRight, Activity, Database, SlidersHorizontal, Users } from 'lucide-react';
import { AdminNotice } from './AdminNotice';
import { AdminSection } from './AdminSection';
import { OverviewCard, type CardStatus, type CardTone } from './OverviewCard';
import { isFailedStatus, latestUpload, type EvaluationAttentionItem, type EvaluationOverview, type OverviewUpload, type SystemErrorSummary, type UserSummary } from './adminOverviewData';
import { settingsPathFor } from './settingsNavigation';
import { useAdminOverview } from './useAdminOverview';

interface QueryState {
  isPending: boolean;
  isError: boolean;
}

function statusOf(query: QueryState): CardStatus {
  if (query.isError) return 'error';
  if (query.isPending) return 'loading';
  return 'ready';
}

function relativeTime(timestamp: number) {
  return formatDistanceToNow(new Date(timestamp), { addSuffix: true });
}

function absoluteTime(timestamp: number) {
  return new Date(timestamp).toLocaleString();
}

/** Shared by the card headline and the Needs attention item, so both read the same. */
function systemErrorHeadline(summary: SystemErrorSummary) {
  const count = summary.capped ? `${summary.count.toLocaleString()}+` : summary.count.toLocaleString();
  const noun = summary.count === 1 && !summary.capped ? 'server error' : 'server errors';
  return `${count} ${noun} in the last 24 hours`;
}

function UploadSummary({ uploads }: { uploads: OverviewUpload[] }) {
  const latest = latestUpload(uploads);
  if (!latest) {
    return (
      <div className="space-y-1">
        <p className="text-xl font-bold text-[var(--text-primary)]">No uploads yet</p>
        <p className="text-sm text-[var(--text-secondary)]">Employee and management workbooks will appear here after they are uploaded.</p>
      </div>
    );
  }
  const failed = isFailedStatus(latest.status);
  return (
    <div className="min-w-0 space-y-1 text-sm">
      {failed && <p className="text-xl font-bold text-[var(--text-primary)]">Latest upload failed</p>}
      {!failed && (
        latest.timestamp === null
          ? <p className="text-xl font-bold text-[var(--text-primary)]">Upload time —</p>
          : <p className="text-xl font-bold text-[var(--text-primary)]"><time dateTime={latest.uploadedAt ?? undefined} title={absoluteTime(latest.timestamp)}>Uploaded {relativeTime(latest.timestamp)}</time></p>
      )}
      <p className="truncate text-[var(--text-secondary)]" title={latest.filename ?? undefined}>{latest.filename ?? 'Unnamed file'} · by {latest.uploadedBy ?? '—'}</p>
      {latest.kind === 'employee' && <p className="text-[var(--text-secondary)]">Status {latest.status ?? '—'}</p>}
      {latest.recordCount !== null && <p className="text-[var(--text-secondary)]">{latest.recordCount.toLocaleString()} records</p>}
    </div>
  );
}

function AccessSummary({ users }: { users: UserSummary }) {
  if (users.total === 0) {
    return (
      <div className="space-y-1">
        <p className="text-xl font-bold text-[var(--text-primary)]">No user accounts</p>
        <p className="text-sm text-[var(--text-secondary)]">Accounts you add will appear here.</p>
      </div>
    );
  }
  return (
    <div className="min-w-0 space-y-2 text-sm">
      <p className="text-xl font-bold text-[var(--text-primary)]">{users.total.toLocaleString()} {users.total === 1 ? 'user' : 'users'}</p>
      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[var(--text-secondary)]">
        {users.byRole.map(({ role, count }) => (
          <li key={role}><span className="font-bold text-[var(--text-primary)]">{count}</span> {role}</li>
        ))}
      </ul>
      <p className="text-[var(--text-secondary)]">{users.disabled} disabled · {users.mustChangePassword} must change password</p>
      {users.needsReassignment > 0 && <p className="font-semibold text-amber-800 dark:text-amber-300">{users.needsReassignment} need a role reassignment</p>}
    </div>
  );
}

function SystemSummary({ summary }: { summary: SystemErrorSummary }) {
  if (summary.count === 0) {
    const lastError = summary.lastError;
    return (
      <div className="min-w-0 space-y-1 text-sm">
        <p className="text-xl font-bold text-[var(--text-primary)]">No server errors in the last 24 hours</p>
        {lastError && lastError.timestamp !== null && (
          <p className="text-[var(--text-secondary)]">
            <time dateTime={lastError.occurredAt ?? undefined} title={absoluteTime(lastError.timestamp)}>Last error {relativeTime(lastError.timestamp)}</time>
          </p>
        )}
      </div>
    );
  }
  const latest = summary.latest;
  // The list response carries no message text, so the short description is the error class and the endpoint.
  const message = `${latest?.errorClass ?? 'Unknown error'} · ${[latest?.method, latest?.endpoint].filter(Boolean).join(' ') || '—'}`;
  return (
    <div className="min-w-0 space-y-1 text-sm">
      <p className="text-xl font-bold text-[var(--text-primary)]">{systemErrorHeadline(summary)}</p>
      {latest && latest.timestamp !== null && (
        <p className="text-[var(--text-secondary)]">
          <time dateTime={latest.occurredAt ?? undefined} title={absoluteTime(latest.timestamp)}>Latest {relativeTime(latest.timestamp)}</time>
        </p>
      )}
      {latest && <p className="truncate font-semibold text-[var(--text-primary)]" title={message}>{message}</p>}
    </div>
  );
}

/** The month a Needs attention link opens: Evaluation settings on that exact scope and period. */
function evaluationLinkFor(item: EvaluationAttentionItem) {
  const query = new URLSearchParams({ scope: item.scopeId, year: String(item.year), month: String(item.month) });
  return `${settingsPathFor('kpis')}?${query.toString()}`;
}

function evaluationScopeLabel(item: EvaluationAttentionItem) {
  return [item.scopeName, item.performanceLevel, item.positionName].filter(Boolean).join(' · ');
}

function evaluationHeadline(overview: EvaluationOverview) {
  if (overview.drafts > 0) return `${overview.drafts.toLocaleString()} ${overview.drafts === 1 ? 'draft' : 'drafts'} waiting`;
  // A null count is unknown. Saying nothing is waiting would claim more than the server reported.
  if (overview.approvedNotApplied === null) return 'No drafts waiting';
  if (overview.approvedNotApplied > 0) return `${overview.approvedNotApplied.toLocaleString()} approved, not applied`;
  return 'Nothing waiting';
}

function evaluationTone(overview: EvaluationOverview): CardTone {
  if (overview.drafts > 0 || (overview.approvedNotApplied ?? 0) > 0) return 'warning';
  if (overview.approvedNotApplied === null) return 'info';
  return 'good';
}

function EvaluationSummary({ overview }: { overview: EvaluationOverview }) {
  const { drafts, approvedNotApplied, approvedUnconfirmed, applied } = overview;
  if (drafts === 0 && approvedNotApplied === 0 && (approvedUnconfirmed ?? 0) === 0 && applied === 0) {
    return (
      <div className="space-y-1">
        <p className="text-xl font-bold text-[var(--text-primary)]">No evaluation months yet</p>
        <p className="text-sm text-[var(--text-secondary)]">Open evaluation settings to start a month.</p>
      </div>
    );
  }
  const parts: string[] = [];
  if (drafts > 0 && approvedNotApplied !== null && approvedNotApplied > 0) parts.push(`${approvedNotApplied.toLocaleString()} approved, not applied`);
  // Neutral wording. It describes months with no apply on record and does not change the tone.
  if (approvedUnconfirmed !== null && approvedUnconfirmed > 0) parts.push(`${approvedUnconfirmed.toLocaleString()} approved with no apply on record`);
  if (approvedNotApplied === null) parts.push('Approved months could not be checked');
  if (applied !== null) parts.push(`${applied.toLocaleString()} applied`);
  return (
    <div className="min-w-0 space-y-1 text-sm">
      <p className="text-xl font-bold text-[var(--text-primary)]">{evaluationHeadline(overview)}</p>
      {parts.length > 0 && <p className="text-[var(--text-secondary)]">{parts.join(' · ')}</p>}
    </div>
  );
}

interface AttentionItem {
  key: string;
  text: string;
  actionLabel: string;
  to: string;
}

export function AdminOverview() {
  const { uploads, users, systemErrors, evaluation } = useAdminOverview();
  const uploadsStatus = statusOf(uploads);
  const usersStatus = statusOf(users);
  const systemStatus = statusOf(systemErrors);
  const evaluationStatus = statusOf(evaluation);

  const latest = uploadsStatus === 'ready' && uploads.data ? latestUpload(uploads.data) : null;
  const uploadFailed = latest !== null && isFailedStatus(latest.status);
  const systemSummary = systemStatus === 'ready' && systemErrors.data ? systemErrors.data : null;
  const evaluationOverview = evaluationStatus === 'ready' && evaluation.data ? evaluation.data : null;
  const errorCount = systemSummary ? systemSummary.count : 0;
  const reassignments = usersStatus === 'ready' && users.data ? users.data.needsReassignment : 0;

  const attention: AttentionItem[] = [];
  if (uploadFailed) {
    attention.push({ key: 'upload', text: `Latest upload failed: ${latest?.filename ?? 'Unnamed file'}.`, actionLabel: 'Go to data uploads', to: settingsPathFor('upload') });
  }
  if (systemSummary && errorCount > 0) {
    attention.push({ key: 'system', text: `${systemErrorHeadline(systemSummary)}.`, actionLabel: 'Go to system errors', to: settingsPathFor('system_errors') });
  }
  if (reassignments > 0) {
    attention.push({ key: 'access', text: `${reassignments.toLocaleString()} ${reassignments === 1 ? 'user needs' : 'users need'} a role reassignment.`, actionLabel: 'Go to users', to: settingsPathFor('users') });
  }
  for (const item of evaluationOverview?.attention ?? []) {
    const month = `${item.monthName} ${item.year}`;
    const scope = evaluationScopeLabel(item);
    attention.push(item.state === 'draft'
      ? { key: `evaluation-${item.versionId}`, text: `Draft for ${scope} · ${month} is waiting for approval.`, actionLabel: 'Open draft', to: evaluationLinkFor(item) }
      : { key: `evaluation-${item.versionId}`, text: `${scope} · ${month} is approved but not applied.`, actionLabel: 'Open to apply', to: evaluationLinkFor(item) });
  }

  const unavailable = [
    uploadsStatus === 'error' ? 'Data' : null,
    usersStatus === 'error' ? 'Access' : null,
    systemStatus === 'error' ? 'System' : null,
    evaluationStatus === 'error' ? 'Evaluation' : null,
  ].filter((name): name is string => name !== null);
  const checking = [uploadsStatus, usersStatus, systemStatus, evaluationStatus].includes('loading');

  return (
    <div className="space-y-4">
      <AdminSection title="Areas" description="Each card shows the current state of its area. Choose an area to configure it.">
        <ul className="grid grid-cols-[minmax(0,1fr)] gap-3 md:grid-cols-2 xl:grid-cols-4">
          <li className="flex">
            <OverviewCard
              title="Data"
              description="Upload employee and management workbooks, and back up or restore corrective action records."
              icon={Database}
              actionLabel="Open data uploads"
              to={settingsPathFor('upload')}
              status={uploadsStatus}
              tone={uploadFailed ? 'attention' : 'info'}
              onRetry={() => void uploads.refetch()}
            >
              {uploads.data && <UploadSummary uploads={uploads.data} />}
            </OverviewCard>
          </li>
          <li className="flex">
            <OverviewCard
              title="Evaluation"
              description="Set monthly targets, weights and direction for each scope, then approve and apply the month."
              icon={SlidersHorizontal}
              actionLabel="Open evaluation settings"
              to={settingsPathFor('kpis')}
              status={evaluationStatus}
              tone={evaluationOverview ? evaluationTone(evaluationOverview) : 'info'}
              onRetry={() => void evaluation.refetch()}
            >
              {evaluationOverview && <EvaluationSummary overview={evaluationOverview} />}
            </OverviewCard>
          </li>
          <li className="flex">
            <OverviewCard
              title="Access"
              description="Manage user accounts, their roles and their access to teams."
              icon={Users}
              actionLabel="Manage users"
              to={settingsPathFor('users')}
              status={usersStatus}
              tone={reassignments > 0 ? 'warning' : 'info'}
              onRetry={() => void users.refetch()}
            >
              {users.data && <AccessSummary users={users.data} />}
            </OverviewCard>
          </li>
          <li className="flex">
            <OverviewCard
              title="System"
              description="Review recent server failures and trace each one to the request that caused it."
              icon={Activity}
              actionLabel="Review system errors"
              to={settingsPathFor('system_errors')}
              status={systemStatus}
              tone={errorCount > 0 ? 'warning' : 'good'}
              onRetry={() => void systemErrors.refetch()}
            >
              {systemErrors.data && <SystemSummary summary={systemErrors.data} />}
            </OverviewCard>
          </li>
        </ul>
      </AdminSection>

      <AdminSection title="Needs attention" description="Only items that need action appear here.">
        {attention.length > 0 && (
          <ul className="space-y-2">
            {attention.map((item) => (
              <li key={item.key} className="flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-4 py-3">
                <span className="min-w-0 text-sm font-semibold text-[var(--text-primary)]">{item.text}</span>
                <Link
                  to={item.to}
                  className="inline-flex min-h-11 items-center gap-1 rounded-lg px-2 text-sm font-bold text-blue-600 underline-offset-4 hover:underline dark:text-blue-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary)]"
                >
                  {item.actionLabel}
                  <ArrowRight size={14} aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        )}
        {unavailable.length > 0 && (
          <AdminNotice tone="warning">Could not check {unavailable.join(', ')}. Use Retry on the card above.</AdminNotice>
        )}
        {attention.length === 0 && unavailable.length === 0 && checking && (
          <p role="status" className="text-sm text-[var(--text-secondary)]">Checking areas…</p>
        )}
        {attention.length === 0 && unavailable.length === 0 && !checking && (
          <AdminNotice tone="success">Nothing needs attention.</AdminNotice>
        )}
      </AdminSection>
    </div>
  );
}
