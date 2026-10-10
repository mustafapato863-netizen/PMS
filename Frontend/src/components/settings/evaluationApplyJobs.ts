/**
 * Monthly evaluation background apply: capability, latest job, and status.
 * Synchronous POST /apply stays in the settings panel and is used only after
 * the capability payload is literal { enabled: false }.
 */

import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { API_BASE } from '../../config';
import type { ReportingSelection } from './monthlyCorrection';

export const APPLY_JOB_POLL_MS = 2000;

export const CHECKING_APPLY_NOTE = 'Checking whether background apply is available. Apply stays off until that check finishes.';

export const UNAVAILABLE_APPLY_SUFFIX = 'Apply stays off until the check succeeds. Synchronous apply is not used while the check is unavailable.';

export const ACCEPTANCE_UNKNOWN_NOTE = 'Apply acceptance was not confirmed. The latest job was refreshed and nothing was queued automatically.';

export const BACKGROUND_CONTINUES_NOTE = 'This month\'s background apply continues on the server. This page follows the scope, year, and month you select.';

export const RETRY_SAME_JOB_NOTE = 'Retry continues this same job for the admin who started it. It does not start a second apply.';

export const RETRY_OTHER_ADMIN_NOTE = 'Only the admin who started this job can retry it. Another admin can cancel the job and apply again. That captures a new job and keeps the original attribution.';

export const RECOVER_NOTE = 'Recovery acknowledges the committed revision. It does not apply the month again.';

export const RECOVER_DENIED_NOTE = 'The server did not allow recovery of this committed revision for the current request. This screen did not grant permission.';

export const CANCEL_DENIED_NOTE = 'The server did not allow cancellation for the current request. This screen did not grant permission.';

export const CANCEL_CONFIRM_NOTE = 'Cancel stops this background apply. Scores that are not committed stay unchanged. A committed revision is not rolled back here.';

export const QUEUED_DETAIL = 'Queued. Scores are unchanged.';

export const RESUMED_DETAIL = 'Queued. Scores are unchanged. The open job was resumed.';

const CONTROL_STATES = ['pending', 'staging', 'promoting', 'promoted', 'failed', 'cancelled'] as const;
const JOB_STATUSES = ['queued', 'running', 'succeeded', 'failed', 'cancelled'] as const;

export type ApplyControlState = (typeof CONTROL_STATES)[number];
export type ApplyProcessingStatus = (typeof JOB_STATUSES)[number];

export type ApplyJobPhase = 'queued' | 'staging' | 'committing' | 'awaiting_ack' | 'succeeded' | 'failed' | 'cancelled';

export type ApplyJobPermissions = {
  cancel: boolean | null;
  retry: boolean | null;
  recover: boolean | null;
};

export type ApplyJobSnapshot = {
  jobId: string;
  state: ApplyControlState;
  jobStatus: ApplyProcessingStatus;
  claimEpoch: number;
  stagedCount: number | null;
  promotedCount: number | null;
  stageCursor: string | null;
  revisionId: string | null;
  progress: number | null;
  attemptCount: number | null;
  expectedCount: number | null;
  safeReason: string | null;
  resumed: boolean | null;
  permissions: ApplyJobPermissions;
};

export type ApplyJobPresentation = {
  phase: ApplyJobPhase;
  percent: number;
  title: string;
  detail: string;
  valueText: string;
};

export type ApplyJobActions = {
  showCancel: boolean;
  showRetry: boolean;
  showRecover: boolean;
  retryNote: string | null;
  recoverNote: string | null;
  cancelNote: string | null;
};

export type CapabilityResult =
  | { kind: 'enabled' }
  | { kind: 'disabled' }
  | { kind: 'malformed'; message: string };

export type LatestApplyJobResult =
  | { kind: 'none' }
  | { kind: 'job'; job: ApplyJobSnapshot }
  | { kind: 'malformed'; message: string };

export type EvaluationFetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

type JobParseResult = { kind: 'job'; job: ApplyJobSnapshot } | { kind: 'malformed'; message: string };

const takenEvidence = new Set<string>();

export class EvaluationRequestError extends Error {
  readonly code: string | undefined;
  readonly status: number | undefined;
  readonly acceptanceUnknown: boolean;
  readonly refreshBeforeRetry: boolean;
  readonly latest: LatestApplyJobResult | null;

  constructor(message: string, options?: {
    code?: string;
    status?: number;
    acceptanceUnknown?: boolean;
    refreshBeforeRetry?: boolean;
    latest?: LatestApplyJobResult | null;
  }) {
    super(message);
    this.name = 'EvaluationRequestError';
    this.code = options?.code;
    this.status = options?.status;
    this.acceptanceUnknown = options?.acceptanceUnknown === true;
    this.refreshBeforeRetry = options?.refreshBeforeRetry === true;
    this.latest = options?.latest ?? null;
  }
}

export function resetEvidenceInvalidation(): void {
  takenEvidence.clear();
}

export function takeEvidenceInvalidation(token: string): boolean {
  if (takenEvidence.has(token)) return false;
  takenEvidence.add(token);
  return true;
}

export function reportingSelectionKey(selection: ReportingSelection): string {
  return `${selection.scopeId}|${selection.year}|${selection.month}`;
}

export function applyCapabilityQueryKey() {
  return ['evaluation-settings', 'apply-jobs', 'capabilities'] as const;
}

export function applyLatestQueryKey(selection: ReportingSelection) {
  return ['evaluation-settings', 'apply-jobs', 'latest', selection.scopeId, selection.year, selection.month] as const;
}

export function applyStatusQueryKey(selection: ReportingSelection, jobId: string) {
  return ['evaluation-settings', 'apply-jobs', 'status', selection.scopeId, selection.year, selection.month, jobId] as const;
}

export function applyCapabilityUrl(apiBase: string): string {
  return `${apiBase}/api/settings/evaluation/apply-jobs/capabilities`;
}

export function applyJobLatestUrl(apiBase: string, selection: ReportingSelection): string {
  const params = new URLSearchParams({
    scope_id: selection.scopeId,
    year: String(selection.year),
    month: String(selection.month),
  });
  return `${apiBase}/api/settings/evaluation/apply-jobs?${params.toString()}`;
}

export function applyJobsCollectionUrl(apiBase: string): string {
  return `${apiBase}/api/settings/evaluation/apply-jobs`;
}

export function applyJobCommandUrl(apiBase: string, jobId: string, command: 'status' | 'cancel' | 'retry' | 'recover'): string {
  const encoded = encodeURIComponent(jobId);
  const root = `${applyJobsCollectionUrl(apiBase)}/${encoded}`;
  return command === 'status' ? root : `${root}/${command}`;
}

export function isAuthDenied(error: unknown): boolean {
  return error instanceof EvaluationRequestError && (error.status === 401 || error.status === 403);
}

export function evaluationErrorText(caught: unknown): string {
  if (caught instanceof EvaluationRequestError) {
    const base = caught.code ? `${caught.code}: ${caught.message}` : caught.message;
    if (isAuthDenied(caught) && !base.includes('did not grant permission')) {
      return `${base} The server denied this action. This screen did not grant permission.`;
    }
    return base;
  }
  if (caught instanceof Error && caught.message) return caught.message;
  return 'Evaluation request failed';
}

export function isOpenApplyPhase(phase: ApplyJobPhase): boolean {
  return phase === 'queued' || phase === 'staging' || phase === 'committing' || phase === 'awaiting_ack';
}

export function blocksNewEnqueue(job: ApplyJobSnapshot): boolean {
  return isOpenApplyPhase(presentApplyJob(job).phase);
}

export function evidenceInvalidationToken(job: ApplyJobSnapshot): string | null {
  const phase = presentApplyJob(job).phase;
  if (phase === 'awaiting_ack' && job.revisionId) return `${job.jobId}:${job.revisionId}`;
  if (phase === 'succeeded' && job.revisionId) return `${job.jobId}:${job.revisionId}`;
  if (phase === 'succeeded') return `${job.jobId}:succeeded`;
  return null;
}

export function boundedStagedPercent(progress: number | null, stagedCount: number | null, expectedCount: number | null): number {
  if (progress != null) return Math.min(99, Math.max(0, progress));
  if (expectedCount == null || stagedCount == null || expectedCount <= 0 || stagedCount <= 0) return 0;
  if (stagedCount >= expectedCount) return 99;
  return Math.min(99, Math.floor((stagedCount * 99) / expectedCount));
}

export function presentApplyJob(job: ApplyJobSnapshot): ApplyJobPresentation {
  const phase = phaseFor(job);
  const percent = percentFor(job, phase);
  const title = titleFor(phase);
  const detail = detailFor(job, phase, percent);
  return { phase, percent, title, detail, valueText: `${title}. ${percent} percent.` };
}

export function applyJobActions(job: ApplyJobSnapshot): ApplyJobActions {
  const phase = presentApplyJob(job).phase;
  const preCommit = phase === 'queued' || phase === 'staging';
  const showCancel = (preCommit && job.permissions.cancel !== false)
    || ((phase === 'committing' || phase === 'awaiting_ack') && job.permissions.cancel === true);
  const terminalRetry = phase === 'failed' || phase === 'cancelled';
  const showRetry = terminalRetry && job.permissions.retry !== false;
  const showRecover = phase === 'awaiting_ack' && job.revisionId != null && job.permissions.recover !== false;
  return {
    showCancel,
    showRetry,
    showRecover,
    retryNote: !terminalRetry ? null : job.permissions.retry === false ? RETRY_OTHER_ADMIN_NOTE : RETRY_SAME_JOB_NOTE,
    recoverNote: phase !== 'awaiting_ack'
      ? null
      : job.permissions.recover === false
        ? RECOVER_DENIED_NOTE
        : job.revisionId == null
          ? 'Committed progress has no revision id, so recovery is unavailable.'
          : RECOVER_NOTE,
    cancelNote: preCommit && job.permissions.cancel === false ? CANCEL_DENIED_NOTE : null,
  };
}

export function failureReasonText(value: string | null): string | null {
  if (value == null) return null;
  if (/^[a-z0-9_-]{1,80}$/.test(value)) return `Reason ${value}.`;
  return 'The failure reason was hidden because it was not a short code.';
}

export function applyJobRefetchInterval(input: {
  data: LatestApplyJobResult | undefined;
  error: unknown;
}): number | false {
  if (input.error) return false;
  if (!input.data || input.data.kind !== 'job') return false;
  return isOpenApplyPhase(presentApplyJob(input.data.job).phase) ? APPLY_JOB_POLL_MS : false;
}

export async function readEvaluationEnvelope(response: Response): Promise<unknown> {
  const body: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const status = typeof response.status === 'number' ? response.status : undefined;
    const failure = failureParts(body);
    throw new EvaluationRequestError(failure.message, { code: failure.code, status });
  }
  if (body && typeof body === 'object' && 'data' in body) {
    const data = (body as { data?: unknown }).data;
    return data ?? body;
  }
  return body;
}

export function parseApplyCapability(data: unknown): CapabilityResult {
  const body = record(data);
  if (!body || !('enabled' in body)) return { kind: 'malformed', message: unavailableCapability('enabled was missing') };
  if (body.enabled === true) return { kind: 'enabled' };
  if (body.enabled === false) return { kind: 'disabled' };
  return { kind: 'malformed', message: unavailableCapability('enabled was not a boolean') };
}

export function parseQueuedPayload(data: unknown): JobParseResult {
  const body = record(data);
  if (!body) return malformed('queued apply was not an object');
  if (body.enabled !== true) return malformed('enabled is not true');
  if (body.outcome !== 'queued') return malformed('outcome was not queued');
  if (body.state !== 'pending' || body.job_status !== 'queued') return malformed('queued apply was not pending');
  const jobId = requireToken(body.job_id, 'job_id');
  const claimEpoch = requireCount(body.claim_epoch, 'claim_epoch');
  const expectedCount = requireCount(body.expected_count, 'expected_count');
  if (!jobId.ok) return malformed(jobId.reason);
  if (!claimEpoch.ok) return malformed(claimEpoch.reason);
  if (!expectedCount.ok) return malformed(expectedCount.reason);
  if (typeof body.resumed !== 'boolean') return malformed('resumed was not a boolean');
  const permissions = readPermissions(body);
  if (!permissions) return malformed('permission flag was not a boolean');
  return {
    kind: 'job',
    job: {
      jobId: jobId.value,
      state: 'pending',
      jobStatus: 'queued',
      claimEpoch: claimEpoch.value,
      stagedCount: 0,
      promotedCount: 0,
      stageCursor: null,
      revisionId: null,
      progress: 0,
      attemptCount: null,
      expectedCount: expectedCount.value,
      safeReason: null,
      resumed: body.resumed,
      permissions,
    },
  };
}

export function parseApplyJobStatus(data: unknown): JobParseResult {
  const body = record(data);
  if (!body) return malformed('job was not an object');
  if (body.enabled !== true) return malformed('enabled is not true');
  if (body.outcome !== 'status') return malformed('outcome was not status');
  return parseStatusFields(body, { resumed: 'resumed' in body ? body.resumed : null });
}

export function parseLatestApplyJob(data: unknown): LatestApplyJobResult {
  if (data == null) return { kind: 'none' };
  if (isNullDataEnvelope(data)) return { kind: 'none' };
  const body = record(data);
  if (!body) return malformed('latest job was not an object');
  const hasJob = 'job' in body;
  const hasJobs = 'jobs' in body;
  const hasLatest = 'latest' in body;
  const markers = Number(hasJob) + Number(hasJobs) + Number(hasLatest);
  if (markers > 1) return malformed('latest job used more than one envelope field');
  if (hasJob) return body.job == null ? { kind: 'none' } : asLatestJob(body.job);
  if (hasLatest) return body.latest == null ? { kind: 'none' } : asLatestJob(body.latest);
  if (hasJobs) {
    if (!Array.isArray(body.jobs)) return malformed('jobs was not a list');
    if (body.jobs.length === 0) return { kind: 'none' };
    if (body.jobs.length > 1) return malformed('more than one job was returned');
    return asLatestJob(body.jobs[0]);
  }
  if ('job_id' in body) return asLatestJob(body);
  if ('message' in body || 'success' in body) return malformed('job_status is missing');
  return malformed('latest job shape was not recognized');
}

export function applyCancelResponse(previous: ApplyJobSnapshot, data: unknown): JobParseResult {
  const patch = parseCommandPair(data, 'cancel response');
  if (patch.kind === 'malformed') return patch;
  if (patch.jobId && patch.jobId !== previous.jobId) return malformed('cancel response job_id changed');
  return {
    kind: 'job',
    job: {
      ...previous,
      state: patch.state,
      jobStatus: patch.jobStatus,
      permissions: patch.permissionsSpecified ? patch.permissions : previous.permissions,
      safeReason: patch.safeReason === undefined ? previous.safeReason : patch.safeReason,
    },
  };
}

export function applyRetryResponse(previous: ApplyJobSnapshot, data: unknown): JobParseResult {
  const patch = parseCommandPair(data, 'retry response');
  if (patch.kind === 'malformed') return patch;
  if (patch.state !== 'pending' || patch.jobStatus !== 'queued') return malformed('retry did not return a queued job');
  if (patch.claimEpoch == null) return malformed('claim_epoch was missing');
  if (patch.jobId && patch.jobId !== previous.jobId) return malformed('retry response job_id changed');
  return {
    kind: 'job',
    job: {
      ...previous,
      state: 'pending',
      jobStatus: 'queued',
      claimEpoch: patch.claimEpoch,
      stagedCount: 0,
      promotedCount: 0,
      stageCursor: null,
      revisionId: null,
      progress: 0,
      safeReason: null,
      resumed: patch.resumed,
      permissions: patch.permissionsSpecified ? patch.permissions : previous.permissions,
    },
  };
}

export function applyRecoverResponse(previous: ApplyJobSnapshot, data: unknown): JobParseResult {
  const patch = parseCommandPair(data, 'recovery response');
  if (patch.kind === 'malformed') return patch;
  if (!patch.revisionId) return malformed('recovery did not include a revision id');
  if (patch.jobId && patch.jobId !== previous.jobId) return malformed('recovery response job_id changed');
  return {
    kind: 'job',
    job: {
      ...previous,
      state: patch.state,
      jobStatus: patch.jobStatus,
      revisionId: patch.revisionId,
      claimEpoch: patch.claimEpoch ?? previous.claimEpoch,
      permissions: patch.permissionsSpecified ? patch.permissions : previous.permissions,
      safeReason: patch.safeReason === undefined ? previous.safeReason : patch.safeReason,
      progress: patch.jobStatus === 'succeeded' ? 100 : previous.progress,
    },
  };
}

export async function loadApplyCapability(fetchWithRole: EvaluationFetcher, signal?: AbortSignal): Promise<CapabilityResult> {
  const response = await fetchWithRole(applyCapabilityUrl(API_BASE), { signal });
  return parseApplyCapability(await readEvaluationEnvelope(response));
}

export async function fetchLatestApplyJob(fetchWithRole: EvaluationFetcher, selection: ReportingSelection, signal?: AbortSignal): Promise<LatestApplyJobResult> {
  assertSelection(selection);
  const response = await fetchWithRole(applyJobLatestUrl(API_BASE, selection), { signal });
  return parseLatestApplyJob(await readEvaluationEnvelope(response));
}

export async function fetchApplyJobStatus(fetchWithRole: EvaluationFetcher, jobId: string, signal?: AbortSignal): Promise<JobParseResult> {
  const response = await fetchWithRole(applyJobCommandUrl(API_BASE, jobId, 'status'), { signal });
  return parseApplyJobStatus(await readEvaluationEnvelope(response));
}

export async function enqueueMonthlyApply(input: {
  fetchWithRole: EvaluationFetcher;
  selection: ReportingSelection;
  recheck: boolean;
}): Promise<{ kind: 'queued' | 'adopted'; job: ApplyJobSnapshot }> {
  assertSelection(input.selection);
  if (input.recheck) {
    const latest = await readLatestForRetry(input.fetchWithRole, input.selection);
    if (latest.kind === 'job' && blocksNewEnqueue(latest.job)) return { kind: 'adopted', job: latest.job };
    if (latest.kind === 'malformed') {
      throw new EvaluationRequestError(`${latest.message} Apply was not sent again.`, { refreshBeforeRetry: true, latest });
    }
  }
  let response: Response;
  try {
    response = await input.fetchWithRole(applyJobsCollectionUrl(API_BASE), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope_id: input.selection.scopeId, year: input.selection.year, month: input.selection.month }),
    });
  } catch (caught) {
    if (isAbortError(caught)) throw caught;
    return adoptOrThrow(input.fetchWithRole, input.selection, caught);
  }
  try {
    const data = await readEvaluationEnvelope(response);
    const parsed = parseQueuedPayload(data);
    if (parsed.kind === 'malformed') {
      return adoptOrThrow(input.fetchWithRole, input.selection, new EvaluationRequestError(parsed.message));
    }
    return { kind: 'queued', job: parsed.job };
  } catch (caught) {
    if (isAbortError(caught)) throw caught;
    return adoptOrThrow(input.fetchWithRole, input.selection, caught);
  }
}

export async function postApplyJobCommand(input: {
  fetchWithRole: EvaluationFetcher;
  job: ApplyJobSnapshot;
  command: 'cancel' | 'retry' | 'recover';
}): Promise<ApplyJobSnapshot> {
  const body = input.command === 'recover'
    ? JSON.stringify({ expected_epoch: input.job.claimEpoch })
    : '{}';
  const response = await input.fetchWithRole(applyJobCommandUrl(API_BASE, input.job.jobId, input.command), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
  const data = await readEvaluationEnvelope(response);
  const parsed = input.command === 'cancel'
    ? applyCancelResponse(input.job, data)
    : input.command === 'retry'
      ? applyRetryResponse(input.job, data)
      : applyRecoverResponse(input.job, data);
  if (parsed.kind === 'malformed') throw new EvaluationRequestError(parsed.message);
  return parsed.job;
}

export function useEvaluationApplyJobs(input: {
  active: boolean;
  selection: ReportingSelection;
  selectionReady: boolean;
  isCurrent: (selection: ReportingSelection) => boolean;
  fetchWithRole: EvaluationFetcher;
  releaseGate: () => void;
  reportError: (selection: ReportingSelection, message: string) => void;
  invalidateCommitted: (selection: ReportingSelection) => void;
}) {
  const queryClient = useQueryClient();
  const fetchRef = useRef(input.fetchWithRole);
  const isCurrentRef = useRef(input.isCurrent);
  const reportRef = useRef(input.reportError);
  const releaseRef = useRef(input.releaseGate);
  const invalidateRef = useRef(input.invalidateCommitted);
  const recheckKeys = useRef(new Set<string>());
  const enqueueLock = useRef(false);
  const commandLock = useRef(false);
  useEffect(() => {
    fetchRef.current = input.fetchWithRole;
    isCurrentRef.current = input.isCurrent;
    reportRef.current = input.reportError;
    releaseRef.current = input.releaseGate;
    invalidateRef.current = input.invalidateCommitted;
  }, [input.fetchWithRole, input.isCurrent, input.reportError, input.releaseGate, input.invalidateCommitted]);

  const capabilityQuery = useQuery<CapabilityResult>({
    queryKey: applyCapabilityQueryKey(),
    enabled: input.active,
    retry: false,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) => loadApplyCapability(fetchRef.current, signal),
  });

  const mode = capabilityMode(capabilityQuery.data, capabilityQuery.error, capabilityQuery.isPending || capabilityQuery.isFetching);
  const latestQuery = useQuery<LatestApplyJobResult>({
    queryKey: applyLatestQueryKey(input.selection),
    enabled: input.active && input.selectionReady && mode === 'async',
    retry: false,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchOnWindowFocus: false,
    refetchInterval: false,
    queryFn: ({ signal }) => fetchLatestApplyJob(fetchRef.current, input.selection, signal),
  });
  const latestJobId = latestQuery.data?.kind === 'job' ? latestQuery.data.job.jobId : null;
  const statusQuery = useQuery<JobParseResult>({
    queryKey: applyStatusQueryKey(input.selection, latestJobId ?? ''),
    enabled: input.active && input.selectionReady && mode === 'async' && latestJobId != null,
    retry: false,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchOnWindowFocus: false,
    refetchIntervalInBackground: false,
    refetchInterval: (query) => applyJobRefetchInterval({ data: query.state.data, error: query.state.error }),
    queryFn: ({ signal }) => fetchApplyJobStatus(fetchRef.current, latestJobId ?? '', signal),
  });

  const statusJob = statusQuery.data?.kind === 'job' ? statusQuery.data.job : null;
  const listedJob = latestQuery.data?.kind === 'job' ? latestQuery.data.job : null;
  const malformed = statusQuery.data?.kind === 'malformed' || (latestQuery.data?.kind === 'malformed' && !statusJob);
  const observed = mode === 'async' && !statusQuery.error && !malformed ? (statusJob ?? listedJob) : null;
  const problem = jobProblem(mode, statusQuery.data, latestQuery.data, statusQuery.error, latestQuery.error);
  const presentation = observed ? presentApplyJob(observed) : null;
  const actions = observed ? applyJobActions(observed) : null;
  const token = observed ? evidenceInvalidationToken(observed) : null;
  const scopeId = input.selection.scopeId;
  const year = input.selection.year;
  const month = input.selection.month;

  useEffect(() => {
    if (!token) return;
    if (!takeEvidenceInvalidation(token)) return;
    invalidateRef.current({ scopeId, year, month });
  }, [token, scopeId, year, month]);

  const selectionKey = reportingSelectionKey(input.selection);
  const [armedCancel, setArmedCancel] = useState<{ key: string; jobId: string } | null>(null);
  const confirmCancel = Boolean(observed && armedCancel?.key === selectionKey && armedCancel.jobId === observed.jobId);

  const storeJob = (selection: ReportingSelection, job: ApplyJobSnapshot) => {
    const latest: LatestApplyJobResult = { kind: 'job', job };
    queryClient.setQueryData(applyLatestQueryKey(selection), latest);
    queryClient.setQueryData(applyStatusQueryKey(selection, job.jobId), { kind: 'job', job });
  };

  const enqueueMutation = useMutation({
    retry: false,
    mutationFn: (selection: ReportingSelection) => enqueueMonthlyApply({
      fetchWithRole: fetchRef.current,
      selection,
      recheck: recheckKeys.current.has(reportingSelectionKey(selection)),
    }),
    onSuccess: (result, selection) => {
      recheckKeys.current.delete(reportingSelectionKey(selection));
      storeJob(selection, result.job);
    },
    onError: (caught, selection) => {
      if (caught instanceof EvaluationRequestError && caught.refreshBeforeRetry) {
        recheckKeys.current.add(reportingSelectionKey(selection));
      }
      if (caught instanceof EvaluationRequestError && caught.latest) {
        queryClient.setQueryData(applyLatestQueryKey(selection), caught.latest);
      }
      if (!isCurrentRef.current(selection)) return;
      reportRef.current(selection, evaluationErrorText(caught));
    },
    onSettled: () => {
      enqueueLock.current = false;
      releaseRef.current();
    },
  });

  const commandMutation = useMutation({
    retry: false,
    mutationFn: (vars: { selection: ReportingSelection; job: ApplyJobSnapshot; command: 'cancel' | 'retry' | 'recover' }) => postApplyJobCommand({
      fetchWithRole: fetchRef.current,
      job: vars.job,
      command: vars.command,
    }),
    onSuccess: (job, vars) => {
      storeJob(vars.selection, job);
      setArmedCancel(null);
    },
    onError: (caught, vars) => {
      void queryClient.invalidateQueries({ queryKey: applyLatestQueryKey(vars.selection), exact: true });
      if (!isCurrentRef.current(vars.selection)) return;
      reportRef.current(vars.selection, evaluationErrorText(caught));
    },
    onSettled: () => {
      commandLock.current = false;
      releaseRef.current();
    },
  });

  const unavailableMessage = mode !== 'unavailable'
    ? null
    : capabilityQuery.data?.kind === 'malformed'
      ? capabilityQuery.data.message
      : capabilityQuery.error
        ? `${evaluationErrorText(capabilityQuery.error)} ${UNAVAILABLE_APPLY_SUFFIX}`
        : UNAVAILABLE_APPLY_SUFFIX;

  const blockEnqueue = mode !== 'sync' && (
    mode !== 'async'
    || latestQuery.isPending
    || Boolean(latestQuery.error)
    || latestQuery.data?.kind === 'malformed'
    || (latestQuery.data?.kind === 'job' && blocksNewEnqueue(latestQuery.data.job))
    || Boolean(statusQuery.error)
    || statusQuery.data?.kind === 'malformed'
    || (statusQuery.data?.kind === 'job' && blocksNewEnqueue(statusQuery.data.job))
  );

  const startCommand = (command: 'cancel' | 'retry' | 'recover') => {
    if (!observed || commandLock.current || enqueueLock.current) return false;
    commandLock.current = true;
    commandMutation.mutate({ selection: input.selection, job: observed, command });
    return true;
  };

  return {
    mode,
    unavailableMessage,
    retryAvailability: () => { void capabilityQuery.refetch(); },
    blockEnqueue,
    pending: enqueueMutation.isPending || commandMutation.isPending,
    enqueue: (selection: ReportingSelection) => {
      if (mode !== 'async' || enqueueLock.current || commandLock.current) return false;
      enqueueLock.current = true;
      enqueueMutation.mutate(selection);
      return true;
    },
    job: observed,
    presentation,
    actions,
    problem,
    refreshJob: () => {
      void latestQuery.refetch();
      if (latestJobId) void statusQuery.refetch();
    },
    confirmCancel,
    armCancel: () => { if (observed) setArmedCancel({ key: selectionKey, jobId: observed.jobId }); },
    dismissCancel: () => setArmedCancel(null),
    commitCancel: () => startCommand('cancel'),
    commitRetry: () => startCommand('retry'),
    commitRecover: () => startCommand('recover'),
    tracksOpenJob: Boolean(presentation && isOpenApplyPhase(presentation.phase)),
  };
}

function capabilityMode(data: CapabilityResult | undefined, error: unknown, fetching: boolean): 'pending' | 'sync' | 'async' | 'unavailable' {
  if (fetching) return 'pending';
  if (error || !data || data.kind === 'malformed') return 'unavailable';
  return data.kind === 'enabled' ? 'async' : 'sync';
}

function jobProblem(
  mode: 'pending' | 'sync' | 'async' | 'unavailable',
  status: JobParseResult | undefined,
  latest: LatestApplyJobResult | undefined,
  statusError: unknown,
  latestError: unknown,
): string | null {
  if (mode !== 'async') return null;
  if (status?.kind === 'malformed') return status.message;
  if (!status && latest?.kind === 'malformed') return latest.message;
  if (statusError) return evaluationErrorText(statusError);
  if (latestError) return evaluationErrorText(latestError);
  return null;
}

function phaseFor(job: ApplyJobSnapshot): ApplyJobPhase {
  if (job.state === 'pending') return 'queued';
  if (job.state === 'staging') return 'staging';
  if (job.state === 'promoting') return 'committing';
  if (job.state === 'promoted' && job.jobStatus === 'succeeded') return 'succeeded';
  if (job.state === 'promoted') return 'awaiting_ack';
  if (job.state === 'cancelled') return 'cancelled';
  return 'failed';
}

function percentFor(job: ApplyJobSnapshot, phase: ApplyJobPhase): number {
  if (phase === 'queued') return 0;
  if (phase === 'succeeded') return 100;
  if (phase === 'committing' || phase === 'awaiting_ack') return 99;
  return boundedStagedPercent(job.progress, job.stagedCount, job.expectedCount);
}

function titleFor(phase: ApplyJobPhase): string {
  if (phase === 'queued') return 'Queued';
  if (phase === 'staging') return 'Staging';
  if (phase === 'committing') return 'Committing';
  if (phase === 'awaiting_ack') return 'Committed';
  if (phase === 'succeeded') return 'Succeeded';
  if (phase === 'cancelled') return 'Cancelled';
  return 'Failed';
}

function detailFor(job: ApplyJobSnapshot, phase: ApplyJobPhase, percent: number): string {
  if (phase === 'queued') return job.resumed === true ? RESUMED_DETAIL : QUEUED_DETAIL;
  if (phase === 'staging') return `Staged progress ${percent} of 99. Scores are not committed.`;
  if (phase === 'committing') return 'Committing. Scores are not committed yet.';
  if (phase === 'awaiting_ack') return 'Committed. Awaiting acknowledgement. Scores for this revision are committed.';
  if (phase === 'succeeded') return 'Succeeded. Background apply finished at 100 percent.';
  if (phase === 'cancelled') return 'Background apply was cancelled. Scores that were not committed are unchanged.';
  return 'Background apply failed. Scores that were not committed are unchanged.';
}

function unavailableCapability(reason: string): string {
  return `Background apply availability could not be confirmed (${reason}). ${UNAVAILABLE_APPLY_SUFFIX}`;
}

function malformed(reason: string): { kind: 'malformed'; message: string } {
  return {
    kind: 'malformed',
    message: `Background apply status is missing or malformed (${reason}). This is not a successful apply.`,
  };
}

function record(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function isNullDataEnvelope(value: unknown): boolean {
  const body = record(value);
  if (!body || !('data' in body) || body.data != null) return false;
  return !('job_id' in body) && !('job_status' in body);
}

function failureParts(body: unknown): { message: string; code?: string } {
  const bodyRecord = record(body) ?? {};
  const detail = bodyRecord.detail;
  let message = 'Evaluation request failed';
  if (typeof detail === 'string') message = detail;
  else if (detail && typeof detail === 'object') {
    const detailRecord = detail as Record<string, unknown>;
    const detailMessage = detailRecord.message;
    const bodyMessage = bodyRecord.message;
    if (typeof detailMessage === 'string' && detailMessage) message = detailMessage;
    else if (typeof bodyMessage === 'string' && bodyMessage) message = bodyMessage;
  } else if (typeof bodyRecord.message === 'string' && bodyRecord.message) {
    message = bodyRecord.message;
  }
  const codeValue = detail && typeof detail === 'object' ? (detail as Record<string, unknown>).code : undefined;
  return { message, code: typeof codeValue === 'string' ? codeValue : undefined };
}

function isAbortError(caught: unknown): boolean {
  return caught instanceof Error && caught.name === 'AbortError';
}

function assertSelection(selection: ReportingSelection): void {
  if (!selection.scopeId || !Number.isInteger(selection.year) || selection.year < 2000 || selection.year > 2100) {
    throw new EvaluationRequestError('Apply was not sent because the scope or year is not valid.');
  }
  if (!Number.isInteger(selection.month) || selection.month < 1 || selection.month > 12) {
    throw new EvaluationRequestError('Apply was not sent because the month is not valid.');
  }
}

function requireToken(value: unknown, label: string): { ok: true; value: string } | { ok: false; reason: string } {
  if (typeof value !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(value)) {
    return { ok: false, reason: `${label} was missing or not a safe id` };
  }
  return { ok: true, value };
}

function requireCount(value: unknown, label: string): { ok: true; value: number } | { ok: false; reason: string } {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) {
    return { ok: false, reason: `${label} was not a non-negative integer` };
  }
  return { ok: true, value };
}

function requireState(value: unknown): ApplyControlState | null {
  return CONTROL_STATES.some((state) => state === value) ? value as ApplyControlState : null;
}

function requireJobStatus(value: unknown): ApplyProcessingStatus | null {
  return JOB_STATUSES.some((status) => status === value) ? value as ApplyProcessingStatus : null;
}

function isValidPair(state: ApplyControlState, jobStatus: ApplyProcessingStatus): boolean {
  return (state === 'pending' && jobStatus === 'queued')
    || (state === 'staging' && jobStatus === 'running')
    || (state === 'promoting' && jobStatus === 'running')
    || (state === 'promoted' && (jobStatus === 'running' || jobStatus === 'succeeded'))
    || (state === 'failed' && jobStatus === 'failed')
    || (state === 'cancelled' && jobStatus === 'cancelled');
}

function readPermissions(body: Record<string, unknown>): ApplyJobPermissions | null {
  const nested = body.permissions;
  if (nested != null && !record(nested)) return null;
  const nestedRecord = record(nested);
  const cancel = readFlag(body.can_cancel, nestedRecord?.cancel);
  const retry = readFlag(body.can_retry, nestedRecord?.retry);
  const recover = readFlag(body.can_recover, nestedRecord?.recover);
  if (cancel === 'invalid' || retry === 'invalid' || recover === 'invalid') return null;
  return { cancel, retry, recover };
}

function readFlag(direct: unknown, nested: unknown): boolean | null | 'invalid' {
  const left = direct === undefined ? null : boolOrInvalid(direct);
  const right = nested === undefined ? null : boolOrInvalid(nested);
  if (left === 'invalid' || right === 'invalid') return 'invalid';
  if (left != null && right != null && left !== right) return 'invalid';
  return left ?? right;
}

function boolOrInvalid(value: unknown): boolean | 'invalid' {
  return typeof value === 'boolean' ? value : 'invalid';
}

function optionalCount(value: unknown, label: string, required: boolean): number | null | 'invalid' {
  if (value == null && !required) return null;
  const parsed = requireCount(value, label);
  return parsed.ok ? parsed.value : 'invalid';
}

function optionalProgress(value: unknown): number | null | 'invalid' {
  if (value == null) return null;
  const parsed = requireCount(value, 'progress');
  if (!parsed.ok || parsed.value > 100) return 'invalid';
  return parsed.value;
}

function optionalRevision(value: unknown, required: boolean): string | null | 'invalid' {
  if (value == null) return required ? 'invalid' : null;
  const parsed = requireToken(value, 'revision_id');
  return parsed.ok ? parsed.value : 'invalid';
}

function optionalCursor(value: unknown): string | null | 'invalid' {
  if (value == null || value === '') return null;
  if (typeof value !== 'string' || value.length > 200 || hasControlCharacter(value)) return 'invalid';
  return value;
}

function hasControlCharacter(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    if (value.charCodeAt(index) <= 31) return true;
  }
  return false;
}

function optionalSafeReason(value: unknown): string | null | 'invalid' {
  if (value == null) return null;
  if (typeof value !== 'string') return 'invalid';
  return value;
}

function parseStatusFields(body: Record<string, unknown>, extras: { resumed: unknown }): JobParseResult {
  const jobId = requireToken(body.job_id, 'job_id');
  const state = requireState(body.state);
  const jobStatus = requireJobStatus(body.job_status);
  const claimEpoch = requireCount(body.claim_epoch, 'claim_epoch');
  if (!jobId.ok) return malformed(jobId.reason);
  if (!state || !jobStatus) return malformed('state or job_status was missing');
  if (!isValidPair(state, jobStatus)) return malformed('state does not match job_status');
  if (!claimEpoch.ok) return malformed(claimEpoch.reason);
  const stagedCount = optionalCount(body.staged_count, 'staged_count', true);
  const promotedCount = optionalCount(body.promoted_count, 'promoted_count', true);
  const progress = optionalProgress(body.progress);
  const attemptCount = optionalCount(body.attempt_count, 'attempt_count', true);
  const expectedCount = optionalCount(body.expected_count, 'expected_count', false);
  const stageCursor = optionalCursor(body.stage_cursor);
  const revisionId = optionalRevision(body.revision_id, false);
  const safeReason = 'safe_reason' in body ? optionalSafeReason(body.safe_reason) : null;
  if (
    stagedCount === 'invalid'
    || promotedCount === 'invalid'
    || progress === 'invalid'
    || attemptCount === 'invalid'
    || expectedCount === 'invalid'
    || stageCursor === 'invalid'
    || revisionId === 'invalid'
    || safeReason === 'invalid'
  ) {
    return malformed('a progress field had the wrong type');
  }
  if (!('staged_count' in body) || !('promoted_count' in body) || !('progress' in body) || !('attempt_count' in body) || !('stage_cursor' in body) || !('revision_id' in body) || !('safe_reason' in body)) {
    return malformed('a status field was missing');
  }
  if (progress == null || stagedCount == null || promotedCount == null || attemptCount == null) {
    return malformed('a status count was missing');
  }
  const permissions = readPermissions(body);
  if (!permissions) return malformed('permission flag was not a boolean');
  let resumed: boolean | null = null;
  if (extras.resumed != null) {
    if (typeof extras.resumed !== 'boolean') return malformed('resumed was not a boolean');
    resumed = extras.resumed;
  }
  return {
    kind: 'job',
    job: {
      jobId: jobId.value,
      state,
      jobStatus,
      claimEpoch: claimEpoch.value,
      stagedCount,
      promotedCount,
      stageCursor,
      revisionId,
      progress,
      attemptCount,
      expectedCount,
      safeReason,
      resumed,
      permissions,
    },
  };
}

function asLatestJob(value: unknown): LatestApplyJobResult {
  const parsed = parseApplyJobStatus(value);
  return parsed.kind === 'job' ? parsed : parsed;
}

type CommandPatch = {
  kind: 'command';
  state: ApplyControlState;
  jobStatus: ApplyProcessingStatus;
  jobId: string | null;
  claimEpoch: number | null;
  revisionId: string | null;
  safeReason: string | null | undefined;
  resumed: boolean | null;
  permissions: ApplyJobPermissions;
  permissionsSpecified: boolean;
};

function parseCommandPair(data: unknown, label: string): CommandPatch | { kind: 'malformed'; message: string } {
  const body = record(data);
  if (!body) return malformed(`${label} was not an object`);
  const state = requireState(body.state);
  const jobStatus = requireJobStatus(body.job_status);
  if (!state || !jobStatus) return malformed(`${label} did not include state and job_status`);
  if (!isValidPair(state, jobStatus)) return malformed('state does not match job_status');
  const jobId = body.job_id == null ? null : requireToken(body.job_id, 'job_id');
  if (jobId && !jobId.ok) return malformed(jobId.reason);
  const claimEpoch = body.claim_epoch == null ? null : requireCount(body.claim_epoch, 'claim_epoch');
  if (claimEpoch && !claimEpoch.ok) return malformed(claimEpoch.reason);
  const revision = 'revision_id' in body ? optionalRevision(body.revision_id, false) : null;
  if (revision === 'invalid') return malformed('revision_id was not a safe id');
  const safeReason = 'safe_reason' in body ? optionalSafeReason(body.safe_reason) : undefined;
  if (safeReason === 'invalid') return malformed('safe_reason was not a string or null');
  let resumed: boolean | null = null;
  if ('resumed' in body && body.resumed != null) {
    if (typeof body.resumed !== 'boolean') return malformed('resumed was not a boolean');
    resumed = body.resumed;
  }
  const permissionsSpecified = 'can_cancel' in body || 'can_retry' in body || 'can_recover' in body || 'permissions' in body;
  const permissions = permissionsSpecified ? readPermissions(body) : { cancel: null, retry: null, recover: null };
  if (!permissions) return malformed('permission flag was not a boolean');
  return {
    kind: 'command',
    state,
    jobStatus,
    jobId: jobId ? jobId.value : null,
    claimEpoch: claimEpoch ? claimEpoch.value : null,
    revisionId: revision,
    safeReason,
    resumed,
    permissions,
    permissionsSpecified,
  };
}

async function readLatestForRetry(fetchWithRole: EvaluationFetcher, selection: ReportingSelection): Promise<LatestApplyJobResult> {
  try {
    return await fetchLatestApplyJob(fetchWithRole, selection);
  } catch (caught) {
    if (isAbortError(caught)) throw caught;
    throw new EvaluationRequestError('The latest background apply could not be read. Apply was not sent again.', {
      refreshBeforeRetry: true,
      latest: null,
      code: caught instanceof EvaluationRequestError ? caught.code : undefined,
      status: caught instanceof EvaluationRequestError ? caught.status : undefined,
    });
  }
}

async function adoptOrThrow(
  fetchWithRole: EvaluationFetcher,
  selection: ReportingSelection,
  caught: unknown,
): Promise<{ kind: 'adopted'; job: ApplyJobSnapshot }> {
  let latest: LatestApplyJobResult;
  try {
    latest = await fetchLatestApplyJob(fetchWithRole, selection);
  } catch (lookup) {
    if (isAbortError(lookup)) throw lookup;
    throw new EvaluationRequestError('Apply acceptance was not confirmed, and the latest job could not be refreshed. Nothing was queued automatically.', {
      acceptanceUnknown: true,
      refreshBeforeRetry: true,
      latest: null,
    });
  }
  if (latest.kind === 'job' && blocksNewEnqueue(latest.job)) return { kind: 'adopted', job: latest.job };
  const raw = caught instanceof EvaluationRequestError
    ? caught.message
    : caught instanceof Error && caught.message
      ? caught.message
      : 'Evaluation request failed';
  const denied = isAuthDenied(caught);
  throw new EvaluationRequestError(denied ? raw : `${raw} ${ACCEPTANCE_UNKNOWN_NOTE}`, {
    code: caught instanceof EvaluationRequestError ? caught.code : undefined,
    status: caught instanceof EvaluationRequestError ? caught.status : undefined,
    acceptanceUnknown: !denied,
    refreshBeforeRetry: true,
    latest,
  });
}
