import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createElement, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ACCEPTANCE_UNKNOWN_NOTE,
  APPLY_JOB_POLL_MS,
  applyCancelResponse,
  applyCapabilityUrl,
  applyJobActions,
  applyJobCommandUrl,
  applyJobLatestUrl,
  applyJobRefetchInterval,
  applyJobsCollectionUrl,
  applyRecoverResponse,
  applyRetryResponse,
  boundedStagedPercent,
  enqueueMonthlyApply,
  evaluationErrorText,
  evidenceInvalidationToken,
  loadApplyCapability,
  parseApplyCapability,
  parseApplyJobStatus,
  parseLatestApplyJob,
  parseQueuedPayload,
  postApplyJobCommand,
  presentApplyJob,
  EvaluationRequestError,
  readEvaluationEnvelope,
  resetEvidenceInvalidation,
  takeEvidenceInvalidation,
  useEvaluationApplyJobs,
  type ApplyJobSnapshot,
} from './evaluationApplyJobs';
import type { ReportingSelection as Selection } from './monthlyCorrection';

const july: Selection = { scopeId: 'scope-1', year: 2026, month: 7 };
const august: Selection = { scopeId: 'scope-1', year: 2026, month: 8 };
const directory = dirname(fileURLToPath(import.meta.url));

function statusPayload(overrides: Record<string, unknown> = {}) {
  return {
    enabled: true,
    outcome: 'status',
    job_id: 'job-1',
    state: 'pending',
    job_status: 'queued',
    claim_epoch: 1,
    staged_count: 0,
    promoted_count: 0,
    stage_cursor: null,
    revision_id: null,
    progress: 0,
    attempt_count: 1,
    expected_count: 4,
    safe_reason: null,
    ...overrides,
  };
}

function queuedPayload(overrides: Record<string, unknown> = {}) {
  return {
    enabled: true,
    outcome: 'queued',
    job_id: 'job-1',
    state: 'pending',
    job_status: 'queued',
    claim_epoch: 1,
    expected_count: 4,
    resumed: false,
    ...overrides,
  };
}

function httpJson(data: unknown, status = 200): Response {
  const ok = status >= 200 && status < 300;
  return new Response(JSON.stringify(ok ? { success: true, data } : { detail: data }), { status });
}

function requireJob(result: { kind: string; job?: ApplyJobSnapshot }): ApplyJobSnapshot {
  if (result.kind !== 'job' || !result.job) throw new Error('expected a job');
  return result.job;
}

function client() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: 1 } },
  });
}

function withClient(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

function ownValue(source: object, key: string): unknown {
  if (!Object.hasOwn(source, key)) return undefined;
  for (const [name, value] of Object.entries(source)) {
    if (name === key) return value;
  }
  return undefined;
}

function isPollInterval(value: unknown): value is (query: { state: { data?: unknown; error: unknown } }) => number | false | undefined {
  return typeof value === 'function';
}

function refetchChoice(queryClient: QueryClient, part: string) {
  const found = queryClient.getQueryCache().getAll().find((query) => query.queryKey.includes(part) && query.queryKey.includes('job-1'));
  if (!found) return { interval: undefined, background: undefined };
  const intervalOption = ownValue(found.options, 'refetchInterval');
  const backgroundOption = ownValue(found.options, 'refetchIntervalInBackground');
  const interval = isPollInterval(intervalOption)
    ? intervalOption(found)
    : intervalOption === false || typeof intervalOption === 'number'
      ? intervalOption
      : undefined;
  const background = typeof backgroundOption === 'boolean' ? backgroundOption : undefined;
  return { interval, background };
}

beforeEach(() => {
  resetEvidenceInvalidation();
});

describe('capability and payload parsing', () => {
  it('accepts only a literal boolean capability', () => {
    expect(parseApplyCapability({ enabled: true })).toEqual({ kind: 'enabled' });
    expect(parseApplyCapability({ enabled: false })).toEqual({ kind: 'disabled' });
    expect(parseApplyCapability({ enabled: 'true' }).kind).toBe('malformed');
    expect(parseApplyCapability({ enabled: 1 }).kind).toBe('malformed');
    expect(parseApplyCapability({}).kind).toBe('malformed');
    expect(parseApplyCapability(null).kind).toBe('malformed');
  });

  it('parses a queued acceptance and rejects a status document that only says ok', () => {
    const queued = requireJob(parseQueuedPayload(queuedPayload({ resumed: true, claim_epoch: 0 })));
    expect(queued).toMatchObject({ jobId: 'job-1', claimEpoch: 0, resumed: true, progress: 0, state: 'pending', jobStatus: 'queued' });
    expect(parseQueuedPayload({ ...queuedPayload(), resumed: 'yes' }).kind).toBe('malformed');
    expect(parseQueuedPayload({ message: 'ok' }).kind).toBe('malformed');
    expect(parseApplyJobStatus({ message: 'ok' }).kind).toBe('malformed');
    expect(parseApplyJobStatus({ ...statusPayload(), outcome: 'ok', job_status: 'succeeded' }).kind).toBe('malformed');
    expect(parseApplyJobStatus({ ...statusPayload(), enabled: false }).kind).toBe('malformed');
    expect(parseApplyJobStatus({ ...statusPayload(), state: 'pending', job_status: 'running' }).kind).toBe('malformed');
    expect(parseApplyJobStatus({ ...statusPayload(), claim_epoch: true }).kind).toBe('malformed');
    expect(parseApplyJobStatus({ ...statusPayload(), claim_epoch: 1.5 }).kind).toBe('malformed');
    expect(parseApplyJobStatus({ ...statusPayload(), progress: null }).kind).toBe('malformed');
    expect(parseApplyJobStatus({ ...statusPayload(), progress: 101 }).kind).toBe('malformed');
    expect(parseApplyJobStatus({ ...statusPayload(), can_retry: 'yes' }).kind).toBe('malformed');
    const status = requireJob(parseApplyJobStatus(statusPayload({ claim_epoch: 0 })));
    expect(status.claimEpoch).toBe(0);
    expect(status.permissions).toEqual({ cancel: null, retry: null, recover: null });
  });

  it('keeps latest parsing to one helper and treats an ok message as malformed', () => {
    const snapshot = statusPayload();
    expect(parseLatestApplyJob(null)).toEqual({ kind: 'none' });
    expect(parseLatestApplyJob({ data: null })).toEqual({ kind: 'none' });
    expect(parseLatestApplyJob({ success: true, data: null })).toEqual({ kind: 'none' });
    expect(parseLatestApplyJob({ job: null })).toEqual({ kind: 'none' });
    expect(parseLatestApplyJob({ latest: null })).toEqual({ kind: 'none' });
    expect(parseLatestApplyJob({ jobs: [] })).toEqual({ kind: 'none' });
    expect(requireJob(parseLatestApplyJob({ job: snapshot })).jobId).toBe('job-1');
    expect(requireJob(parseLatestApplyJob({ latest: snapshot })).jobId).toBe('job-1');
    expect(requireJob(parseLatestApplyJob({ jobs: [snapshot] })).jobId).toBe('job-1');
    expect(requireJob(parseLatestApplyJob(snapshot)).jobId).toBe('job-1');
    expect(parseLatestApplyJob({ message: 'ok' }).kind).toBe('malformed');
    expect(parseLatestApplyJob({ success: true }).kind).toBe('malformed');
    expect(parseLatestApplyJob({}).kind).toBe('malformed');
    expect(parseLatestApplyJob({ jobs: [snapshot, snapshot] }).kind).toBe('malformed');
    expect(parseLatestApplyJob({ job: snapshot, latest: snapshot }).kind).toBe('malformed');
    expect(parseLatestApplyJob({ employee_name: 'Hidden Person' }).kind).toBe('malformed');
  });

  it('reads the standard data wrapper and keeps an error code', async () => {
    const wrapped = await readEvaluationEnvelope(httpJson({ enabled: false }));
    expect(wrapped).toEqual({ enabled: false });
    const empty = await readEvaluationEnvelope(httpJson(null));
    expect(parseLatestApplyJob(empty).kind).toBe('none');
    await expect(readEvaluationEnvelope(httpJson({ message: 'nope', code: 'permission_denied' }, 403))).rejects.toMatchObject({
      message: 'nope',
      code: 'permission_denied',
      status: 403,
    });
  });
});

describe('progress presentation', () => {
  it('bounds staged progress and separates commit from success', () => {
    expect(boundedStagedPercent(100, 4, 4)).toBe(99);
    expect(boundedStagedPercent(null, 1, 2)).toBe(49);
    expect(boundedStagedPercent(null, 4, 4)).toBe(99);
    expect(boundedStagedPercent(null, 0, 4)).toBe(0);
    const queued = requireJob(parseQueuedPayload(queuedPayload()));
    expect(presentApplyJob(queued)).toMatchObject({ phase: 'queued', percent: 0, title: 'Queued' });
    expect(presentApplyJob(queued).detail).toContain('Scores are unchanged.');
    const resumed = requireJob(parseQueuedPayload(queuedPayload({ resumed: true })));
    expect(presentApplyJob(resumed).detail).toContain('resumed');
    const stagingJob = requireJob(parseApplyJobStatus(statusPayload({ state: 'staging', job_status: 'running', progress: 40, staged_count: 2 })));
    expect(presentApplyJob(stagingJob)).toMatchObject({ phase: 'staging', percent: 40, title: 'Staging' });
    const committing = requireJob(parseApplyJobStatus(statusPayload({ state: 'promoting', job_status: 'running', progress: 80 })));
    expect(presentApplyJob(committing)).toMatchObject({ phase: 'committing', percent: 99, title: 'Committing' });
    const waiting = requireJob(parseApplyJobStatus(statusPayload({ state: 'promoted', job_status: 'running', revision_id: 'revision-9', progress: 80 })));
    expect(presentApplyJob(waiting)).toMatchObject({ phase: 'awaiting_ack', percent: 99, title: 'Committed' });
    const succeeded = requireJob(parseApplyJobStatus(statusPayload({ state: 'promoted', job_status: 'succeeded', revision_id: 'revision-9', progress: 100 })));
    expect(presentApplyJob(succeeded)).toMatchObject({ phase: 'succeeded', percent: 100, title: 'Succeeded' });
  });

  it('shows retry and recovery only when the phase and flags allow them', () => {
    const failed = requireJob(parseApplyJobStatus(statusPayload({ state: 'failed', job_status: 'failed', safe_reason: 'lease_expired' })));
    expect(applyJobActions(failed).showRetry).toBe(true);
    expect(applyJobActions(failed).retryNote).toContain('same job');
    const denied = requireJob(parseApplyJobStatus(statusPayload({ state: 'failed', job_status: 'failed', can_retry: false })));
    expect(applyJobActions(denied).showRetry).toBe(false);
    expect(applyJobActions(denied).retryNote).toContain('Another admin can cancel');
    const waiting = requireJob(parseApplyJobStatus(statusPayload({ state: 'promoted', job_status: 'running', revision_id: 'revision-9' })));
    expect(applyJobActions(waiting)).toMatchObject({ showRecover: true, showCancel: false, showRetry: false });
    const explicitCancel = requireJob(parseApplyJobStatus(statusPayload({
      state: 'promoted',
      job_status: 'running',
      revision_id: 'revision-9',
      can_cancel: true,
      can_recover: false,
    })));
    expect(applyJobActions(explicitCancel).showCancel).toBe(true);
    expect(applyJobActions(explicitCancel).showRecover).toBe(false);
    const queued = requireJob(parseQueuedPayload(queuedPayload()));
    expect(applyJobActions(queued).showCancel).toBe(true);
    expect(applyJobActions({ ...queued, permissions: { ...queued.permissions, cancel: false } }).showCancel).toBe(false);
  });

  it('polls only an open job and invalidates one token per job and revision', () => {
    const queued = requireJob(parseQueuedPayload(queuedPayload()));
    const failed = requireJob(parseApplyJobStatus(statusPayload({ state: 'failed', job_status: 'failed' })));
    const waiting = requireJob(parseApplyJobStatus(statusPayload({ state: 'promoted', job_status: 'running', revision_id: 'revision-9' })));
    const succeeded = requireJob(parseApplyJobStatus(statusPayload({ state: 'promoted', job_status: 'succeeded', revision_id: 'revision-9', progress: 100 })));
    expect(applyJobRefetchInterval({ data: { kind: 'job', job: queued }, error: null })).toBe(APPLY_JOB_POLL_MS);
    expect(applyJobRefetchInterval({ data: { kind: 'job', job: waiting }, error: null })).toBe(APPLY_JOB_POLL_MS);
    expect(applyJobRefetchInterval({ data: { kind: 'job', job: failed }, error: null })).toBe(false);
    expect(applyJobRefetchInterval({ data: { kind: 'job', job: succeeded }, error: null })).toBe(false);
    expect(applyJobRefetchInterval({ data: { kind: 'none' }, error: null })).toBe(false);
    expect(applyJobRefetchInterval({ data: undefined, error: new Error('denied') })).toBe(false);
    expect(evidenceInvalidationToken(queued)).toBeNull();
    expect(evidenceInvalidationToken(waiting)).toBe('job-1:revision-9');
    expect(evidenceInvalidationToken(succeeded)).toBe('job-1:revision-9');
    expect(evidenceInvalidationToken({ ...succeeded, revisionId: null })).toBe('job-1:succeeded');
    expect(takeEvidenceInvalidation('job-1:revision-9')).toBe(true);
    expect(takeEvidenceInvalidation('job-1:revision-9')).toBe(false);
    resetEvidenceInvalidation();
    expect(takeEvidenceInvalidation('job-1:revision-9')).toBe(true);
  });
});

describe('requests', () => {
  it('builds scope, year, and month into one latest query', () => {
    const url = applyJobLatestUrl('http://127.0.0.1:8000', { scopeId: 'a/b', year: 2026, month: 8 });
    expect(url).toContain('/api/settings/evaluation/apply-jobs?');
    expect(url).toContain('scope_id=a%2Fb');
    expect(url).toContain('year=2026');
    expect(url).toContain('month=8');
    expect(applyCapabilityUrl('http://127.0.0.1:8000')).toBe('http://127.0.0.1:8000/api/settings/evaluation/apply-jobs/capabilities');
    expect(applyJobsCollectionUrl('http://127.0.0.1:8000')).toBe('http://127.0.0.1:8000/api/settings/evaluation/apply-jobs');
    expect(applyJobCommandUrl('http://127.0.0.1:8000', 'job/1', 'retry')).toBe('http://127.0.0.1:8000/api/settings/evaluation/apply-jobs/job%2F1/retry');
  });

  it('does not post again after an unknown acceptance, and adopts an open job', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    let latest: unknown = { job: null };
    const fetchWithRole = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, init });
      if (init?.method === 'POST') {
        if (latest && typeof latest === 'object' && latest !== null && 'job' in latest && (latest as { job: unknown }).job) {
          return httpJson({ message: 'duplicate' }, 409);
        }
        throw new Error('socket down');
      }
      return httpJson(latest);
    });
    await expect(enqueueMonthlyApply({ fetchWithRole, selection: july, recheck: false })).rejects.toThrow(ACCEPTANCE_UNKNOWN_NOTE);
    expect(calls.filter((call) => call.init?.method === 'POST')).toHaveLength(1);
    expect(calls.filter((call) => String(call.url).includes('/apply-jobs?'))).toHaveLength(1);

    latest = { job: statusPayload() };
    calls.length = 0;
    const adopted = await enqueueMonthlyApply({ fetchWithRole, selection: july, recheck: true });
    expect(adopted.kind).toBe('adopted');
    expect(calls.filter((call) => call.init?.method === 'POST')).toHaveLength(0);

    latest = { job: null };
    calls.length = 0;
    const denied = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), init });
      if (init?.method === 'POST') return httpJson({ message: 'nope', code: 'permission_denied' }, 403);
      return httpJson({ job: null });
    });
    await expect(enqueueMonthlyApply({ fetchWithRole: denied, selection: july, recheck: false })).rejects.toMatchObject({
      message: 'nope',
      status: 403,
      acceptanceUnknown: false,
    });
  });

  it('posts an empty object for cancel and retry, and the claim epoch for recovery', async () => {
    const previous = requireJob(parseApplyJobStatus(statusPayload({
      state: 'failed',
      job_status: 'failed',
      revision_id: 'revision-9',
      can_retry: false,
      claim_epoch: 0,
    })));
    const calls: Array<{ url: string; body: string }> = [];
    const fetchWithRole = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), body: String(init?.body) });
      if (String(input).endsWith('/cancel')) return httpJson({ state: 'cancelled', job_status: 'cancelled' });
      if (String(input).endsWith('/retry')) return httpJson({ state: 'pending', job_status: 'queued', claim_epoch: 2 });
      return httpJson({ state: 'promoted', job_status: 'succeeded', revision_id: 'revision-9' });
    });
    const cancelled = await postApplyJobCommand({ fetchWithRole, job: previous, command: 'cancel' });
    expect(calls[0]?.body).toBe('{}');
    expect(cancelled.permissions.retry).toBe(false);
    expect(cancelled.revisionId).toBe('revision-9');
    const retried = await postApplyJobCommand({ fetchWithRole, job: previous, command: 'retry' });
    expect(calls[1]?.body).toBe('{}');
    expect(retried).toMatchObject({ state: 'pending', jobStatus: 'queued', claimEpoch: 2, revisionId: null, progress: 0 });
    expect(retried.permissions.retry).toBe(false);
    const recovered = await postApplyJobCommand({ fetchWithRole, job: { ...previous, state: 'promoted', jobStatus: 'running' }, command: 'recover' });
    expect(JSON.parse(calls[2]?.body ?? '{}')).toEqual({ expected_epoch: 0 });
    expect(recovered.jobStatus).toBe('succeeded');
    expect(recovered.revisionId).toBe('revision-9');
    expect(applyCancelResponse(previous, { state: 'cancelled', job_status: 'cancelled' }).kind).toBe('job');
    expect(applyRetryResponse(previous, { state: 'failed', job_status: 'failed', claim_epoch: 2 }).kind).toBe('malformed');
    expect(applyRecoverResponse(previous, { state: 'promoted', job_status: 'succeeded' }).kind).toBe('malformed');
  });

  it('asks the capability endpoint and preserves an auth denial sentence', async () => {
    const fetchWithRole = vi.fn(async (input: RequestInfo | URL) => httpJson(
      { enabled: false },
      String(input).includes('/apply-jobs/capabilities') ? 200 : 500,
    ));
    await expect(loadApplyCapability(fetchWithRole)).resolves.toEqual({ kind: 'disabled' });
    expect(String(fetchWithRole.mock.calls[0]?.[0])).toContain('/apply-jobs/capabilities');
    expect(evaluationErrorText(new EvaluationRequestError('nope', { status: 403, code: 'permission_denied' }))).toContain('did not grant permission');
  });
});

describe('useEvaluationApplyJobs', () => {
  function renderJobs(active = true, prepare?: (seed: {
    latest: Map<string, unknown>;
    status: Map<string, unknown | { error: number; detail: unknown }>;
    setCapability: (value: unknown, statusCode?: number) => void;
  }) => void) {
    const queryClient = client();
    const seen: string[] = [];
    let capability: unknown = { enabled: true };
    let capabilityStatus = 200;
    let releaseEnqueue: ((response: Response) => void) | null = null;
    let enqueueMode: 'queue' | 'hang' | 'throw' | 'deny' | 'malformed' = 'queue';
    const latest = new Map<string, unknown>();
    const status = new Map<string, unknown | { error: number; detail: unknown }>();
    const setCapability = (value: unknown, statusCode = 200) => { capability = value; capabilityStatus = statusCode; };
    prepare?.({ latest, status, setCapability });
    const current = { ...july };
    const invalidate = vi.fn();
    const report = vi.fn();
    const fetchWithRole = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      seen.push(`${init?.method ?? 'GET'} ${url}`);
      if (url.includes('/capabilities')) return httpJson(capability, capabilityStatus);
      if (init?.method === 'POST' && new URL(url).pathname.endsWith('/apply-jobs')) {
        if (enqueueMode === 'hang') return new Promise<Response>((resolve) => { releaseEnqueue = resolve; });
        if (enqueueMode === 'throw') throw new Error('socket down');
        if (enqueueMode === 'deny') return httpJson({ message: 'nope', code: 'permission_denied' }, 403);
        if (enqueueMode === 'malformed') return httpJson({ message: 'ok' });
        return httpJson(queuedPayload());
      }
      if (init?.method === 'POST') return httpJson({ state: 'cancelled', job_status: 'cancelled' });
      if (new URL(url).searchParams.has('scope_id')) {
        const params = new URL(url).searchParams;
        const key = `${params.get('scope_id')}|${params.get('year')}|${params.get('month')}`;
        return httpJson(latest.get(key) ?? { job: null });
      }
      const id = decodeURIComponent(new URL(url).pathname.split('/').pop() ?? '');
      const body = status.get(id);
      if (body && typeof body === 'object' && body !== null && 'error' in body) {
        const failed = body as { error: number; detail: unknown };
        return httpJson(failed.detail, failed.error);
      }
      return httpJson(body ?? statusPayload({ job_id: id || 'job-1' }));
    });
    const hook = renderHook(
      (selection: Selection) => useEvaluationApplyJobs({
        active,
        selection,
        selectionReady: true,
        isCurrent: (item) => item.scopeId === current.scopeId && item.year === current.year && item.month === current.month,
        fetchWithRole,
        releaseGate: vi.fn(),
        reportError: report,
        invalidateCommitted: invalidate,
      }),
      { initialProps: july, wrapper: withClient(queryClient) },
    );
    return {
      ...hook,
      queryClient,
      seen,
      current,
      invalidate,
      report,
      latest,
      status,
      fetchWithRole,
      setCapability,
      hangEnqueue: () => { enqueueMode = 'hang'; },
      throwEnqueue: () => { enqueueMode = 'throw'; },
      denyEnqueue: () => { enqueueMode = 'deny'; },
      malformedEnqueue: () => { enqueueMode = 'malformed'; },
      releaseEnqueue: () => releaseEnqueue,
    };
  }

  it('makes no request for a non-admin screen', async () => {
    const view = renderJobs(false);
    await waitFor(() => expect(view.result.current.mode).toBe('pending'));
    expect(view.fetchWithRole).not.toHaveBeenCalled();
  });

  it('keeps synchronous apply only after an explicit false capability', async () => {
    const view = renderJobs(true, (seed) => seed.setCapability({ enabled: false }));
    await waitFor(() => expect(view.result.current.mode).toBe('sync'));
    expect(view.result.current.blockEnqueue).toBe(false);
    expect(view.seen.filter((entry) => entry.includes('/apply-jobs?'))).toHaveLength(0);
    expect(view.result.current.enqueue(july)).toBe(false);
  });

  it('does not enqueue while capability is pending, failed, or not a boolean', async () => {
    let release: (value: unknown) => void = () => {};
    const queryClient = client();
    const fetchWithRole = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') return httpJson({ message: 'blocked' }, 500);
      if (String(input).includes('/capabilities')) return httpJson(await new Promise((resolve) => { release = resolve; }));
      return httpJson({ job: null });
    });
    const view = renderHook(() => useEvaluationApplyJobs({
      active: true,
      selection: july,
      selectionReady: true,
      isCurrent: () => true,
      fetchWithRole,
      releaseGate: vi.fn(),
      reportError: vi.fn(),
      invalidateCommitted: vi.fn(),
    }), { wrapper: withClient(queryClient) });
    await waitFor(() => expect(fetchWithRole).toHaveBeenCalled());
    expect(view.result.current.mode).toBe('pending');
    expect(view.result.current.blockEnqueue).toBe(true);
    expect(view.result.current.enqueue(july)).toBe(false);
    expect(fetchWithRole.mock.calls.filter((call) => call[1]?.method === 'POST')).toHaveLength(0);
    release({ enabled: 'true' });
    await waitFor(() => expect(view.result.current.mode).toBe('unavailable'));
    expect(view.result.current.enqueue(july)).toBe(false);
    expect(fetchWithRole.mock.calls.filter((call) => call[1]?.method === 'POST')).toHaveLength(0);
  });

  it('posts one queued job and ignores a same-tick second enqueue', async () => {
    const view = renderJobs();
    await waitFor(() => expect(view.result.current.blockEnqueue).toBe(false));
    expect(view.result.current.enqueue(july)).toBe(true);
    expect(view.result.current.enqueue(july)).toBe(false);
    await waitFor(() => expect(view.result.current.presentation?.phase).toBe('queued'));
    const posts = view.seen.filter((entry) => entry.startsWith('POST') && entry.includes('/apply-jobs'));
    expect(posts).toHaveLength(1);
    expect(view.invalidate).not.toHaveBeenCalled();
    expect(view.result.current.presentation?.detail).toContain('Scores are unchanged.');
  });

  it('refreshes the latest job after an unknown acceptance and does not post automatically', async () => {
    const view = renderJobs();
    view.throwEnqueue();
    await waitFor(() => expect(view.result.current.blockEnqueue).toBe(false));
    expect(view.result.current.enqueue(july)).toBe(true);
    await waitFor(() => expect(view.report).toHaveBeenCalled());
    expect(String(view.report.mock.calls[0]?.[1])).toContain(ACCEPTANCE_UNKNOWN_NOTE);
    expect(view.seen.filter((entry) => entry.startsWith('POST'))).toHaveLength(1);
    view.latest.set('scope-1|2026|7', { job: statusPayload({ job_id: 'job-open' }) });
    expect(view.result.current.enqueue(july)).toBe(true);
    await waitFor(() => expect(view.result.current.job?.jobId).toBe('job-open'));
    expect(view.seen.filter((entry) => entry.startsWith('POST'))).toHaveLength(1);
  });

  it('does not describe an auth denial as unknown acceptance', async () => {
    const view = renderJobs();
    view.denyEnqueue();
    await waitFor(() => expect(view.result.current.blockEnqueue).toBe(false));
    expect(view.result.current.enqueue(july)).toBe(true);
    await waitFor(() => expect(view.report).toHaveBeenCalled());
    expect(String(view.report.mock.calls[0]?.[1])).toContain('did not grant permission');
    expect(String(view.report.mock.calls[0]?.[1])).not.toContain('acceptance was not confirmed');
    expect(view.seen.filter((entry) => entry.startsWith('POST'))).toHaveLength(1);
  });

  it('adopts a malformed acceptance when the latest job is already open', async () => {
    const view = renderJobs();
    view.malformedEnqueue();
    view.latest.set('scope-1|2026|7', { job: null });
    await waitFor(() => expect(view.result.current.blockEnqueue).toBe(false));
    view.latest.set('scope-1|2026|7', { job: statusPayload() });
    expect(view.result.current.enqueue(july)).toBe(true);
    await waitFor(() => expect(view.result.current.job?.jobId).toBe('job-1'));
    expect(view.report).not.toHaveBeenCalled();
    expect(view.seen.filter((entry) => entry.startsWith('POST'))).toHaveLength(1);
    expect(view.invalidate).not.toHaveBeenCalled();
  });

  it('does not let a stale queued response or a stale promoted job refresh another month', async () => {
    const view = renderJobs();
    view.hangEnqueue();
    await waitFor(() => expect(view.result.current.blockEnqueue).toBe(false));
    expect(view.result.current.enqueue(july)).toBe(true);
    await waitFor(() => expect(view.seen.filter((entry) => entry.startsWith('POST'))).toHaveLength(1));
    view.current.month = 8;
    view.rerender(august);
    view.releaseEnqueue()?.(httpJson(queuedPayload()));
    await waitFor(() => expect(view.seen.some((entry) => entry.includes('month=8'))).toBe(true));
    expect(view.result.current.job).toBeNull();
    expect(view.invalidate).not.toHaveBeenCalled();
    expect(view.report).not.toHaveBeenCalled();

    view.latest.set('scope-b|2026|8', { job: null });
    view.current.scopeId = 'scope-b';
    view.rerender({ scopeId: 'scope-b', year: 2026, month: 8 });
    await waitFor(() => expect(view.seen.some((entry) => entry.includes('scope-b'))).toBe(true));
    expect(view.invalidate).not.toHaveBeenCalled();
  });

  it('invalidates the promoted revision once, including after the screen closes and opens', async () => {
    const promoted = { job: statusPayload({ state: 'promoted', job_status: 'running', revision_id: 'revision-9', progress: 90, staged_count: 4, promoted_count: 4 }) };
    const view = renderJobs(true, (seed) => {
      seed.latest.set('scope-1|2026|7', promoted);
      seed.status.set('job-1', promoted.job);
    });
    await waitFor(() => expect(view.invalidate).toHaveBeenCalledTimes(1));
    expect(view.invalidate).toHaveBeenCalledWith(july);
    await view.queryClient.refetchQueries({ queryKey: ['evaluation-settings', 'apply-jobs', 'status'] });
    expect(view.invalidate).toHaveBeenCalledTimes(1);
    view.status.set('job-1', statusPayload({ state: 'promoted', job_status: 'succeeded', revision_id: 'revision-9', progress: 100, staged_count: 4, promoted_count: 4 }));
    await view.queryClient.refetchQueries({ queryKey: ['evaluation-settings', 'apply-jobs', 'status'] });
    await waitFor(() => expect(view.result.current.presentation?.phase).toBe('succeeded'));
    expect(view.invalidate).toHaveBeenCalledTimes(1);
    view.unmount();
    const reopened = renderJobs(true, (seed) => {
      seed.latest.set('scope-1|2026|7', promoted);
      seed.status.set('job-1', promoted.job);
    });
    await waitFor(() => expect(reopened.result.current.presentation?.phase).toBe('awaiting_ack'));
    expect(reopened.invalidate).not.toHaveBeenCalled();
  });

  it('stops polling for a terminal job, an auth error, and a hidden tab', async () => {
    const view = renderJobs(true, (seed) => {
      seed.latest.set('scope-1|2026|7', { job: statusPayload() });
      seed.status.set('job-1', statusPayload());
    });
    await waitFor(() => expect(refetchChoice(view.queryClient, 'status').interval).toBe(2000));
    expect(refetchChoice(view.queryClient, 'status').background).toBe(false);
    view.status.set('job-1', statusPayload({ state: 'cancelled', job_status: 'cancelled' }));
    await view.queryClient.refetchQueries({ queryKey: ['evaluation-settings', 'apply-jobs', 'status'] });
    await waitFor(() => expect(refetchChoice(view.queryClient, 'status').interval).toBe(false));
    view.status.set('job-1', { error: 403, detail: { message: 'nope', code: 'permission_denied' } });
    await view.queryClient.refetchQueries({ queryKey: ['evaluation-settings', 'apply-jobs', 'status'] });
    await waitFor(() => expect(view.result.current.problem).toContain('did not grant permission'));
    expect(refetchChoice(view.queryClient, 'status').interval).toBe(false);
    expect(view.invalidate).not.toHaveBeenCalled();
  });
});

describe('source boundaries', () => {
  it('does not store the job in web storage or start its own timer', () => {
    for (const name of ['evaluationApplyJobs.ts', 'EvaluationApplyProgress.tsx', 'EvaluationSettingsPanel.tsx']) {
      const text = readFileSync(join(directory, name), 'utf8');
      expect(text).not.toContain('localStorage');
      expect(text).not.toContain('sessionStorage');
      expect(text).not.toContain('setInterval');
      expect(text).not.toContain('setTimeout');
    }
  });
});
