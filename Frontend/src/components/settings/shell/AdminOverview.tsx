import { useMemo, useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  CheckCircle2,
  ClipboardCheck,
  Clock,
  Database,
  Download,
  FileSpreadsheet,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  TriangleAlert,
  Users,
} from 'lucide-react';
import { AdminNotice } from './AdminNotice';
import { AdminSection } from './AdminSection';
import { AdminActionLink, OverviewCard, type CardStatus, type CardTone } from './OverviewCard';
import {
  isFailedStatus,
  latestUpload,
  type EvaluationAttentionItem,
  type EvaluationOverview,
  type OverviewUpload,
  type SystemErrorSummary,
  type UserSummary,
} from './adminOverviewData';
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

const FACT = 'text-[15px] font-semibold leading-[1.45] tracking-[-0.02em] text-[var(--insights-heading)]';
const LINE = 'text-[13px] leading-[1.5] text-[var(--text-secondary)]';

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
        <p className={FACT}>No uploads yet</p>
        <p className={LINE}>Employee and management workbooks will appear here after they are uploaded.</p>
      </div>
    );
  }
  const failed = isFailedStatus(latest.status);
  const employeeCount = uploads.filter((u) => u.kind === 'employee').length;
  const managementCount = uploads.filter((u) => u.kind === 'management').length;

  return (
    <div className="min-w-0 space-y-1.5">
      {failed && <p className={FACT}>Latest upload failed</p>}
      {!failed &&
        (latest.timestamp === null ? (
          <p className={FACT}>Upload time —</p>
        ) : (
          <p className={FACT}>
            <time dateTime={latest.uploadedAt ?? undefined} title={absoluteTime(latest.timestamp)}>
              Uploaded {relativeTime(latest.timestamp)}
            </time>
          </p>
        ))}
      <p className={`truncate ${LINE}`} title={latest.filename ?? undefined}>
        {latest.filename ?? 'Unnamed file'} · by {latest.uploadedBy ?? '—'}
      </p>
      {latest.kind === 'employee' && <p className={LINE}>Status {latest.status ?? '—'}</p>}
      {latest.recordCount !== null && <p className={LINE}>{latest.recordCount.toLocaleString()} records</p>}

      {uploads.length > 1 && (
        <div className="flex flex-wrap items-center gap-1.5 pt-1" aria-hidden="true">
          <span className="inline-flex items-center rounded-md bg-[var(--bg-sunken)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
            {employeeCount} Employee {employeeCount === 1 ? 'batch' : 'batches'}
          </span>
          <span className="inline-flex items-center rounded-md bg-[var(--bg-sunken)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
            {managementCount} Management {managementCount === 1 ? 'file' : 'files'}
          </span>
        </div>
      )}
    </div>
  );
}

function AccessSummary({ users }: { users: UserSummary }) {
  if (users.total === 0) {
    return (
      <div className="space-y-1">
        <p className={FACT}>No user accounts</p>
        <p className={LINE}>Accounts you add will appear here.</p>
      </div>
    );
  }
  const activeCount = Math.max(0, users.total - users.disabled);
  const activePct = Math.round((activeCount / users.total) * 100);

  return (
    <div className="min-w-0 space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <p className={`${FACT} tabular-nums`}>
          {users.total.toLocaleString()} {users.total === 1 ? 'user' : 'users'}
        </p>
        <span
          aria-hidden="true"
          className="text-[11px] font-semibold tabular-nums text-[var(--text-muted)]"
        >
          {activePct}% active
        </span>
      </div>
      <div
        aria-hidden="true"
        className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-sunken)]"
      >
        <div
          className="h-full rounded-full bg-emerald-500 transition-all duration-300"
          style={{ width: `${activePct}%` }}
        />
      </div>
      <ul className="flex flex-wrap gap-x-[14px] gap-y-[4px]">
        {users.byRole.map(({ role, count }) => (
          <li key={role} className={LINE}>
            <span className="font-semibold tabular-nums text-[var(--insights-heading)]">{count}</span> {role}
          </li>
        ))}
      </ul>
      <p className={LINE}>
        {users.disabled} disabled · {users.mustChangePassword} must change password
      </p>
      {users.needsReassignment > 0 && (
        <p className="text-[13px] font-semibold leading-[1.5] text-amber-800 dark:text-amber-300">
          {users.needsReassignment} need a role reassignment
        </p>
      )}
    </div>
  );
}

function SystemSummary({ summary }: { summary: SystemErrorSummary }) {
  if (summary.count === 0) {
    const lastError = summary.lastError;
    return (
      <div className="min-w-0 space-y-1.5">
        <p className={FACT}>No server errors in the last 24 hours</p>
        <div
          aria-hidden="true"
          className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-sunken)]"
        >
          <div className="h-full w-full rounded-full bg-emerald-500" />
        </div>
        {lastError && lastError.timestamp !== null && (
          <p className={LINE}>
            <time dateTime={lastError.occurredAt ?? undefined} title={absoluteTime(lastError.timestamp)}>
              Last error {relativeTime(lastError.timestamp)}
            </time>
          </p>
        )}
      </div>
    );
  }
  const latest = summary.latest;
  // The list response carries no message text, so the short description is the error class and the endpoint.
  const message = `${latest?.errorClass ?? 'Unknown error'} · ${[latest?.method, latest?.endpoint].filter(Boolean).join(' ') || '—'}`;
  return (
    <div className="min-w-0 space-y-1.5">
      <p className={FACT}>{systemErrorHeadline(summary)}</p>
      {latest && latest.timestamp !== null && (
        <p className={LINE}>
          <time dateTime={latest.occurredAt ?? undefined} title={absoluteTime(latest.timestamp)}>
            Latest {relativeTime(latest.timestamp)}
          </time>
        </p>
      )}
      {latest && (
        <p
          className="truncate text-[13px] font-medium leading-[1.5] text-[var(--insights-heading)]"
          title={message}
        >
          {message}
        </p>
      )}
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
        <p className={FACT}>No evaluation months yet</p>
        <p className={LINE}>Open evaluation settings to start a month.</p>
      </div>
    );
  }
  const parts: string[] = [];
  if (drafts > 0 && approvedNotApplied !== null && approvedNotApplied > 0)
    parts.push(`${approvedNotApplied.toLocaleString()} approved, not applied`);
  // Neutral wording. It describes months with no apply on record and does not change the tone.
  if (approvedUnconfirmed !== null && approvedUnconfirmed > 0)
    parts.push(`${approvedUnconfirmed.toLocaleString()} approved with no apply on record`);
  if (approvedNotApplied === null) parts.push('Approved months could not be checked');
  if (applied !== null) parts.push(`${applied.toLocaleString()} applied`);

  const totalKnown = drafts + (approvedNotApplied ?? 0) + (applied ?? 0);
  const appliedPct = totalKnown > 0 ? Math.round(((applied ?? 0) / totalKnown) * 100) : 0;
  const approvedPct = totalKnown > 0 ? Math.round(((approvedNotApplied ?? 0) / totalKnown) * 100) : 0;

  return (
    <div className="min-w-0 space-y-1.5">
      <p className={`${FACT} tabular-nums`}>{evaluationHeadline(overview)}</p>
      {totalKnown > 0 && (
        <div
          aria-hidden="true"
          className="flex h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-sunken)]"
        >
          <div className="h-full bg-emerald-500 transition-all duration-300" style={{ width: `${appliedPct}%` }} />
          <div className="h-full bg-amber-500 transition-all duration-300" style={{ width: `${approvedPct}%` }} />
        </div>
      )}
      {parts.length > 0 && <p className={LINE}>{parts.join(' · ')}</p>}
    </div>
  );
}

type AttentionCategory = 'all' | 'data' | 'evaluation' | 'access' | 'system';

interface AttentionItem {
  key: string;
  category: Exclude<AttentionCategory, 'all'>;
  severity: 'critical' | 'warning';
  text: string;
  actionLabel: string;
  to: string;
}

interface ActivityEvent {
  id: string;
  kind: 'upload' | 'evaluation';
  title: string;
  subtitle: string;
  timestamp: number | null;
  badge: string;
  badgeTone: 'emerald' | 'amber' | 'rose' | 'blue';
}

export function AdminOverview() {
  const navigate = useNavigate();
  const { uploads, users, systemErrors, evaluation } = useAdminOverview();
  const [attentionFilter, setAttentionFilter] = useState<AttentionCategory>('all');
  const [activityFilter, setActivityFilter] = useState<'all' | 'upload' | 'evaluation'>('all');
  const [activitySearch, setActivitySearch] = useState('');

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
    attention.push({
      key: 'upload',
      category: 'data',
      severity: 'critical',
      text: `Latest upload failed: ${latest?.filename ?? 'Unnamed file'}.`,
      actionLabel: 'Go to data uploads',
      to: settingsPathFor('upload'),
    });
  }
  if (systemSummary && errorCount > 0) {
    attention.push({
      key: 'system',
      category: 'system',
      severity: 'warning',
      text: `${systemErrorHeadline(systemSummary)}.`,
      actionLabel: 'Go to system errors',
      to: settingsPathFor('system_errors'),
    });
  }
  if (reassignments > 0) {
    attention.push({
      key: 'access',
      category: 'access',
      severity: 'warning',
      text: `${reassignments.toLocaleString()} ${reassignments === 1 ? 'user needs' : 'users need'} a role reassignment.`,
      actionLabel: 'Go to users',
      to: settingsPathFor('users'),
    });
  }
  for (const item of evaluationOverview?.attention ?? []) {
    const month = `${item.monthName} ${item.year}`;
    const scope = evaluationScopeLabel(item);
    attention.push(
      item.state === 'draft'
        ? {
            key: `evaluation-${item.versionId}`,
            category: 'evaluation',
            severity: 'warning',
            text: `Draft for ${scope} · ${month} is waiting for approval.`,
            actionLabel: 'Open draft',
            to: evaluationLinkFor(item),
          }
        : {
            key: `evaluation-${item.versionId}`,
            category: 'evaluation',
            severity: 'warning',
            text: `${scope} · ${month} is approved but not applied.`,
            actionLabel: 'Open to apply',
            to: evaluationLinkFor(item),
          },
    );
  }

  const unavailable = [
    uploadsStatus === 'error' ? 'Data' : null,
    usersStatus === 'error' ? 'Access' : null,
    systemStatus === 'error' ? 'System' : null,
    evaluationStatus === 'error' ? 'Evaluation' : null,
  ].filter((name): name is string => name !== null);
  const checking = [uploadsStatus, usersStatus, systemStatus, evaluationStatus].includes('loading');

  const filteredAttention = useMemo(() => {
    if (attentionFilter === 'all') return attention;
    return attention.filter((item) => item.category === attentionFilter);
  }, [attention, attentionFilter]);

  const governanceChecks = useMemo(() => {
    const dataOk = uploadsStatus === 'ready' && !uploadFailed;
    const evalOk =
      evaluationStatus === 'ready' &&
      evaluationOverview !== null &&
      evaluationOverview.drafts === 0 &&
      (evaluationOverview.approvedNotApplied ?? 0) === 0;
    const accessOk = usersStatus === 'ready' && reassignments === 0;
    const systemOk = systemStatus === 'ready' && errorCount === 0;

    return [
      {
        id: 'pipeline',
        label: 'Workbook Ingestion Pipeline',
        detail: uploadFailed
          ? 'Latest workbook batch reported an ingestion failure'
          : latest
            ? 'Latest workbook processed without schema or row errors'
            : 'Ready to receive employee and management workbooks',
        ok: dataOk,
        loading: uploadsStatus === 'loading',
      },
      {
        id: 'evaluation',
        label: 'Monthly Evaluation Governance',
        detail:
          (evaluationOverview?.drafts ?? 0) > 0 || (evaluationOverview?.approvedNotApplied ?? 0) > 0
            ? 'Pending monthly drafts or unapplied approvals require sign-off'
            : 'All approved monthly evaluations are synchronized',
        ok: evalOk,
        loading: evaluationStatus === 'loading',
      },
      {
        id: 'identity',
        label: 'Role & Access Hygiene',
        detail:
          reassignments > 0
            ? 'Legacy user roles require reassignment to current RBAC scopes'
            : 'All active accounts conform to current role and branch policies',
        ok: accessOk,
        loading: usersStatus === 'loading',
      },
      {
        id: 'stability',
        label: '24-Hour Runtime Stability',
        detail:
          errorCount > 0
            ? 'Server exceptions detected within the rolling 24-hour window'
            : 'Zero unhandled server exceptions in the rolling 24-hour window',
        ok: systemOk,
        loading: systemStatus === 'loading',
      },
    ];
  }, [
    errorCount,
    evaluationOverview,
    evaluationStatus,
    latest,
    reassignments,
    systemStatus,
    uploadFailed,
    uploadsStatus,
    usersStatus,
  ]);

  const passingChecksCount = governanceChecks.filter((c) => c.ok).length;
  const healthScore = Math.round((passingChecksCount / governanceChecks.length) * 100);

  const activityStream = useMemo<ActivityEvent[]>(() => {
    const events: ActivityEvent[] = [];
    for (const item of uploads.data ?? []) {
      const failed = isFailedStatus(item.status);
      events.push({
        id: `up-${item.id}`,
        kind: 'upload',
        title: item.filename ?? 'Workbook upload',
        subtitle: `Uploaded by ${item.uploadedBy ?? 'Admin'} · ${item.kind === 'employee' ? 'Employee batch' : 'Management config'}${item.recordCount !== null ? ` (${item.recordCount.toLocaleString()} rows)` : ''}`,
        timestamp: item.timestamp,
        badge: failed ? 'Failed' : 'Processed',
        badgeTone: failed ? 'rose' : 'emerald',
      });
    }
    for (const item of evaluationOverview?.attention ?? []) {
      const scope = evaluationScopeLabel(item);
      events.push({
        id: `ev-${item.versionId}`,
        kind: 'evaluation',
        title: `${scope} · ${item.monthName} ${item.year}`,
        subtitle:
          item.state === 'draft'
            ? `Version ${item.versionNumber ?? 1} saved as draft awaiting approval`
            : `Version ${item.versionNumber ?? 1} approved and ready to apply`,
        timestamp: null,
        badge: item.state === 'draft' ? 'Draft' : 'Approved',
        badgeTone: item.state === 'draft' ? 'blue' : 'amber',
      });
    }
    return events.sort((a, b) => (b.timestamp ?? 0) - (a.timestamp ?? 0));
  }, [evaluationOverview?.attention, uploads.data]);

  const filteredActivity = useMemo(() => {
    const term = activitySearch.trim().toLowerCase();
    return activityStream
      .filter((item) => activityFilter === 'all' || item.kind === activityFilter)
      .filter(
        (item) =>
          !term ||
          item.title.toLowerCase().includes(term) ||
          item.subtitle.toLowerCase().includes(term),
      )
      .slice(0, 6);
  }, [activityFilter, activitySearch, activityStream]);

  const handleRefreshAll = () => {
    void uploads.refetch();
    void evaluation.refetch();
    void users.refetch();
    void systemErrors.refetch();
  };

  const handleExportSnapshot = () => {
    const snapshot = {
      exportedAt: new Date().toISOString(),
      healthScore,
      passingChecks: `${passingChecksCount}/${governanceChecks.length}`,
      areas: {
        uploadsCount: uploads.data?.length ?? 0,
        usersTotal: users.data?.total ?? 0,
        systemErrors24h: errorCount,
        evaluationDrafts: evaluationOverview?.drafts ?? 0,
        evaluationApprovedNotApplied: evaluationOverview?.approvedNotApplied ?? 0,
      },
      attentionItems: attention.map((a) => ({ category: a.category, text: a.text })),
    };
    const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `pms-admin-health-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col gap-[18px]">
      {/* Executive Admin Command Center Banner */}
      <div className="relative overflow-hidden rounded-[16px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-[16px] shadow-[var(--exec-card-shadow)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-3.5">
            <div
              className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-[var(--exec-tile-bg)] text-[15px] font-black tabular-nums text-[var(--insights-accent)] shadow-[0_8px_24px_-8px_rgba(0,163,224,0.32)] transition-shadow duration-300"
              aria-hidden="true"
            >
              {checking ? '•••' : `${healthScore}%`}
            </div>
            <div className="min-w-0 space-y-0.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-bold tracking-tight text-[var(--insights-heading)]">
                  System Governance Posture
                </span>
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                    checking
                      ? 'bg-slate-500/10 text-[var(--text-secondary)]'
                      : attention.length === 0 && unavailable.length === 0
                        ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                        : 'bg-amber-500/10 text-amber-700 dark:text-amber-300'
                  }`}
                >
                  <Sparkles size={11} aria-hidden="true" />
                  {checking
                    ? 'Synchronizing telemetry'
                    : attention.length === 0 && unavailable.length === 0
                      ? 'All controls healthy'
                      : `${attention.length} ${attention.length === 1 ? 'item requires' : 'items require'} review`}
                </span>
              </div>
              <p className="text-xs text-[var(--text-secondary)]">
                {passingChecksCount} of {governanceChecks.length} automated operational checks verified across data, evaluation, access, and runtime logs.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleRefreshAll}
              disabled={checking}
              className="inline-flex min-h-9 items-center gap-1.5 rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/70 px-3 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-sunken)] disabled:opacity-50"
            >
              <RefreshCw size={13} className={checking ? 'animate-spin' : ''} aria-hidden="true" />
              Sync status
            </button>
            <button
              type="button"
              onClick={handleExportSnapshot}
              className="inline-flex min-h-9 items-center gap-1.5 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)]"
            >
              <Download size={13} aria-hidden="true" />
              Export snapshot
            </button>
          </div>
        </div>

        {/* Quick Workflow Launch Bar */}
        <div className="mt-3.5 flex flex-wrap items-center gap-1.5 border-t border-[var(--border-light)] pt-3">
          <span className="mr-1 text-[11px] font-semibold tracking-wider text-[var(--text-muted)] uppercase">
            Quick launch:
          </span>
          <button
            type="button"
            onClick={() => navigate(settingsPathFor('upload'))}
            className="inline-flex min-h-7 items-center gap-1.5 rounded-lg border border-[var(--border-light)] bg-[var(--bg-sunken)]/50 px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--border-medium)] hover:text-[var(--text-primary)]"
          >
            <FileSpreadsheet size={12} className="text-[var(--insights-accent)]" aria-hidden="true" />
            Upload workbook
          </button>
          <button
            type="button"
            onClick={() => navigate(settingsPathFor('corrective_actions'))}
            className="inline-flex min-h-7 items-center gap-1.5 rounded-lg border border-[var(--border-light)] bg-[var(--bg-sunken)]/50 px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--border-medium)] hover:text-[var(--text-primary)]"
          >
            <ClipboardCheck size={12} className="text-emerald-500" aria-hidden="true" />
            Action backups
          </button>
          <button
            type="button"
            onClick={() => navigate(settingsPathFor('kpis'))}
            className="inline-flex min-h-7 items-center gap-1.5 rounded-lg border border-[var(--border-light)] bg-[var(--bg-sunken)]/50 px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--border-medium)] hover:text-[var(--text-primary)]"
          >
            <SlidersHorizontal size={12} className="text-amber-500" aria-hidden="true" />
            Configure KPIs
          </button>
          <button
            type="button"
            onClick={() => navigate(settingsPathFor('users'))}
            className="inline-flex min-h-7 items-center gap-1.5 rounded-lg border border-[var(--border-light)] bg-[var(--bg-sunken)]/50 px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--border-medium)] hover:text-[var(--text-primary)]"
          >
            <Users size={12} className="text-blue-500" aria-hidden="true" />
            Directory & RBAC
          </button>
          <button
            type="button"
            onClick={() => navigate(settingsPathFor('system_errors'))}
            className="inline-flex min-h-7 items-center gap-1.5 rounded-lg border border-[var(--border-light)] bg-[var(--bg-sunken)]/50 px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--border-medium)] hover:text-[var(--text-primary)]"
          >
            <Activity size={12} className="text-rose-500" aria-hidden="true" />
            Diagnostics trace
          </button>
        </div>
      </div>

      <AdminSection
        plain
        title="Areas"
        description="Each card shows the current state of its area. Choose an area to configure it."
      >
        <ul className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,280px),1fr))] gap-[12px]">
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

      <AdminSection
        plain
        title="Needs attention"
        description="Only items that need action appear here."
        actions={
          attention.length > 1 ? (
            <div className="flex flex-wrap items-center gap-1">
              {(['all', 'data', 'evaluation', 'access', 'system'] as const).map((cat) => {
                const count =
                  cat === 'all' ? attention.length : attention.filter((a) => a.category === cat).length;
                if (cat !== 'all' && count === 0) return null;
                const active = attentionFilter === cat;
                return (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setAttentionFilter(cat)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-semibold capitalize transition-colors ${
                      active
                        ? 'bg-[var(--sidebar-active-bg)] text-[var(--sidebar-active-text)] border border-[var(--sidebar-active-border)]'
                        : 'bg-[var(--bg-surface)] text-[var(--text-secondary)] border border-[var(--border-light)] hover:bg-[var(--bg-sunken)]'
                    }`}
                  >
                    {cat} ({count})
                  </button>
                );
              })}
            </div>
          ) : undefined
        }
      >
        {filteredAttention.length > 0 && (
          <ul className="overflow-hidden rounded-[16px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] shadow-[var(--exec-card-shadow)]">
            {filteredAttention.map((item) => (
              <li
                key={item.key}
                className="flex min-h-[56px] min-w-0 flex-col justify-center gap-2 border-b border-[var(--exec-card-border)] px-[16px] py-[10px] transition-colors hover:bg-[var(--bg-sunken)]/35 last:border-b-0 sm:flex-row sm:items-center sm:justify-between sm:gap-4"
              >
                <div className="flex min-w-0 items-center gap-2.5">
                  <span
                    aria-hidden="true"
                    className={`inline-flex shrink-0 items-center rounded-md px-2 py-0.5 text-[11px] font-bold uppercase ${
                      item.severity === 'critical'
                        ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                        : 'bg-amber-500/10 text-amber-700 dark:text-amber-300'
                    }`}
                  >
                    {item.category}
                  </span>
                  <span className="min-w-0 text-[13px] font-medium leading-[1.5] text-[var(--insights-heading)]">
                    {item.text}
                  </span>
                </div>
                <AdminActionLink to={item.to}>{item.actionLabel}</AdminActionLink>
              </li>
            ))}
          </ul>
        )}
        {unavailable.length > 0 && (
          <AdminNotice tone="warning">
            Could not check {unavailable.join(', ')}. Use Retry on the card above.
          </AdminNotice>
        )}
        {attention.length === 0 && unavailable.length === 0 && checking && (
          <p role="status" className="text-sm text-[var(--text-secondary)]">
            Checking areas…
          </p>
        )}
        {attention.length === 0 && unavailable.length === 0 && !checking && (
          <AdminNotice tone="success">Nothing needs attention.</AdminNotice>
        )}
      </AdminSection>

      {/* Enterprise Upgrade: Governance & Operational Readiness + Activity Stream */}
      <div className="grid gap-4 lg:grid-cols-2">
        <AdminSection
          plain
          title="Governance & readiness"
          description="Automated compliance verification across core administrative controls."
        >
          <div className="rounded-[16px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-[16px] shadow-[var(--exec-card-shadow)]">
            <ul className="divide-y divide-[var(--border-light)]">
              {governanceChecks.map((check) => (
                <li
                  key={check.id}
                  className="flex items-start justify-between gap-3 py-3 first:pt-0 last:pb-0"
                >
                  <div className="flex min-w-0 items-start gap-2.5">
                    {check.loading ? (
                      <Clock size={16} className="mt-0.5 shrink-0 text-[var(--text-muted)]" aria-hidden="true" />
                    ) : check.ok ? (
                      <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-500" aria-hidden="true" />
                    ) : (
                      <TriangleAlert size={16} className="mt-0.5 shrink-0 text-amber-500" aria-hidden="true" />
                    )}
                    <div className="min-w-0">
                      <p className="text-[13px] font-semibold text-[var(--insights-heading)]">
                        {check.label}
                      </p>
                      <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{check.detail}</p>
                    </div>
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                      check.loading
                        ? 'bg-slate-500/10 text-[var(--text-muted)]'
                        : check.ok
                          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                          : 'bg-amber-500/10 text-amber-700 dark:text-amber-300'
                    }`}
                  >
                    {check.loading ? 'Pending' : check.ok ? 'Verified' : 'Review'}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </AdminSection>

        <AdminSection
          plain
          title="Recent activity"
          description="Chronological stream of workbook uploads and evaluation workflow milestones."
          actions={
            <div className="flex items-center gap-1">
              {(['all', 'upload', 'evaluation'] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActivityFilter(tab)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-semibold capitalize transition-colors ${
                    activityFilter === tab
                      ? 'bg-[var(--sidebar-active-bg)] text-[var(--sidebar-active-text)] border border-[var(--sidebar-active-border)]'
                      : 'bg-[var(--bg-surface)] text-[var(--text-secondary)] border border-[var(--border-light)] hover:bg-[var(--bg-sunken)]'
                  }`}
                >
                  {tab === 'all' ? 'All' : tab === 'upload' ? 'Uploads' : 'Evaluations'}
                </button>
              ))}
            </div>
          }
        >
          <div className="flex flex-col gap-3 rounded-[16px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-[16px] shadow-[var(--exec-card-shadow)]">
            {activityStream.length > 0 && (
              <label className="flex items-center gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/60 px-3 py-1.5">
                <Search size={13} className="text-[var(--text-muted)]" aria-hidden="true" />
                <input
                  type="text"
                  value={activitySearch}
                  onChange={(event) => setActivitySearch(event.target.value)}
                  placeholder="Filter activity by file, uploader or scope…"
                  className="min-w-0 flex-1 bg-transparent text-xs text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
                />
              </label>
            )}

            {filteredActivity.length === 0 ? (
              <div className="flex min-h-[140px] flex-col items-center justify-center text-center">
                <ShieldCheck size={20} className="text-[var(--text-muted)]" aria-hidden="true" />
                <p className="mt-2 text-xs font-semibold text-[var(--text-secondary)]">
                  {activitySearch.trim()
                    ? 'No activity matches your filter'
                    : 'No recent administrative events recorded'}
                </p>
              </div>
            ) : (
              <ul className="divide-y divide-[var(--border-light)]">
                {filteredActivity.map((event) => (
                  <li
                    key={event.id}
                    className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-semibold text-[var(--insights-heading)]">
                        {event.title}
                      </p>
                      <p className="truncate text-xs text-[var(--text-secondary)]">{event.subtitle}</p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                          event.badgeTone === 'emerald'
                            ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                            : event.badgeTone === 'rose'
                              ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                              : event.badgeTone === 'amber'
                                ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300'
                                : 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
                        }`}
                      >
                        {event.badge}
                      </span>
                      {event.timestamp !== null && (
                        <span className="text-[11px] text-[var(--text-muted)]">
                          {relativeTime(event.timestamp)}
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </AdminSection>
      </div>
    </div>
  );
}
