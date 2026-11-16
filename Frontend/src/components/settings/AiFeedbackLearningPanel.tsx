import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Eye,
  MessageSquareWarning,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { apiFetch } from '../../lib/apiClient';
import type {
  AiApprovedPatternItem,
  AiApprovedPatternListResponse,
  AiApprovePatternResponse,
  AiFeedbackClusterItem,
  AiFeedbackClustersResponse,
  AiFeedbackTraceSample,
} from '../../features/ai/types';

const INTENT_OPTIONS = [
  'current_value',
  'actual_vs_target',
  'score_drivers',
  'trend',
  'compare_periods',
  'compare_branches',
  'compare_teams',
  'ranking',
  'scorecard_structure',
  'corrective_actions',
] as const;

const FAILURE_BADGE_LABELS: Record<string, string> = {
  wrong_data: 'Wrong data',
  misunderstood_question: 'Misunderstood question',
  lost_context: 'Lost context',
  too_long: 'Too long',
  helpful: 'Helpful',
  unspecified: 'General',
};

function formatFailureLabel(code: string): string {
  return FAILURE_BADGE_LABELS[code] || code.replace(/_/g, ' ');
}

function clusterKey(c: AiFeedbackClusterItem): string {
  return `${c.surface}::${c.intent || c.operation_family}::${c.failure_category || c.reason_tag}::${c.scope_team}`;
}

/**
 * Admin review panel for PMS AI feedback clustering, live PMS verification, and approved pattern learning.
 */
export function AiFeedbackLearningPanel() {
  const [surfaceFilter, setSurfaceFilter] = useState<string>('');
  const [ratingFilter, setRatingFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');

  const [clusters, setClusters] = useState<AiFeedbackClusterItem[]>([]);
  const [totalTraces, setTotalTraces] = useState<number>(0);
  const [patterns, setPatterns] = useState<AiApprovedPatternItem[]>([]);

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionBanner, setActionBanner] = useState<{ kind: 'success' | 'error'; text: string } | null>(
    null,
  );

  const [selectedClusterKey, setSelectedClusterKey] = useState<string | null>(null);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);

  const [verifiedAgainstPms, setVerifiedAgainstPms] = useState<boolean>(false);
  const [patternIntent, setPatternIntent] = useState<string>('ranking');
  const [patternOperationKind, setPatternOperationKind] = useState<string>('');
  const [patternMetricHint, setPatternMetricHint] = useState<string>('');
  const [correctedPrompt, setCorrectedPrompt] = useState<string>('');
  const [reviewNotes, setReviewNotes] = useState<string>('');
  const [submittingTraceId, setSubmittingTraceId] = useState<string | null>(null);

  const [confirmRemovePatternId, setConfirmRemovePatternId] = useState<string | null>(null);
  const [removingPatternId, setRemovingPatternId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const qs = new URLSearchParams();
      if (surfaceFilter) qs.set('surface', surfaceFilter);
      if (ratingFilter) qs.set('rating', ratingFilter);
      if (statusFilter) qs.set('review_status', statusFilter);
      const querySuffix = qs.toString() ? `?${qs.toString()}` : '';

      const [clusterRes, patternRes] = await Promise.all([
        apiFetch<AiFeedbackClustersResponse>(`/api/ai/feedback/clusters${querySuffix}`),
        apiFetch<AiApprovedPatternListResponse>('/api/ai/feedback/patterns'),
      ]);
      const nextClusters = Array.isArray(clusterRes?.clusters) ? clusterRes.clusters : [];
      setClusters(nextClusters);
      setTotalTraces(Number(clusterRes?.total_traces ?? 0));
      setPatterns(Array.isArray(patternRes?.patterns) ? patternRes.patterns : []);
    } catch {
      setLoadError('Unable to load AI feedback clusters and approved patterns.');
    } finally {
      setIsLoading(false);
    }
  }, [surfaceFilter, ratingFilter, statusFilter]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const selectedCluster = useMemo(
    () => clusters.find((c) => clusterKey(c) === selectedClusterKey) ?? null,
    [clusters, selectedClusterKey],
  );

  const selectedTrace: AiFeedbackTraceSample | null = useMemo(() => {
    if (!selectedCluster || !selectedCluster.traces.length) return null;
    return (
      selectedCluster.traces.find((t) => t.trace_id === selectedTraceId) ??
      selectedCluster.traces[0]
    );
  }, [selectedCluster, selectedTraceId]);

  const selectCluster = (cluster: AiFeedbackClusterItem) => {
    setSelectedClusterKey(clusterKey(cluster));
    const firstTrace = cluster.traces[0] ?? null;
    setSelectedTraceId(firstTrace?.trace_id ?? null);
    setVerifiedAgainstPms(false);
    setPatternIntent(firstTrace?.intent || cluster.intent || 'ranking');
    setPatternOperationKind(firstTrace?.operation_kind || '');
    setPatternMetricHint('');
    setCorrectedPrompt(firstTrace?.prompt_redacted || '');
    setReviewNotes('');
    setActionBanner(null);
  };

  const selectTrace = (trace: AiFeedbackTraceSample) => {
    setSelectedTraceId(trace.trace_id);
    setVerifiedAgainstPms(false);
    setPatternIntent(trace.intent || 'ranking');
    setPatternOperationKind(trace.operation_kind || '');
    setCorrectedPrompt(trace.prompt_redacted || '');
    setReviewNotes('');
    setActionBanner(null);
  };

  const summary = useMemo(() => {
    let pending = 0;
    let flagged = 0;
    for (const c of clusters) {
      pending += c.pending_count;
      flagged += c.down_count;
    }
    return {
      totalFeedback: totalTraces,
      pendingReview: pending,
      flaggedIssues: flagged,
      activePatterns: patterns.length,
    };
  }, [clusters, totalTraces, patterns.length]);

  const handleReviewDecision = async (traceId: string, decision: 'approved' | 'rejected') => {
    setSubmittingTraceId(traceId);
    setActionBanner(null);
    try {
      await apiFetch(`/api/ai/traces/${encodeURIComponent(traceId)}/review`, {
        method: 'POST',
        body: JSON.stringify({
          decision,
          reviewer_verified: decision === 'approved',
          notes: reviewNotes.trim() || undefined,
        }),
      });
      setActionBanner({
        kind: 'success',
        text:
          decision === 'approved'
            ? 'Trace verified against PMS data.'
            : 'Trace marked as rejected.',
      });
      await loadData();
    } catch {
      setActionBanner({
        kind: 'error',
        text: 'Could not update trace review status.',
      });
    } finally {
      setSubmittingTraceId(null);
    }
  };

  const handleApprovePattern = async (trace: AiFeedbackTraceSample) => {
    if (!verifiedAgainstPms) return;
    setSubmittingTraceId(trace.trace_id);
    setActionBanner(null);
    try {
      const res = await apiFetch<AiApprovePatternResponse>(
        `/api/ai/traces/${encodeURIComponent(trace.trace_id)}/approve-pattern`,
        {
          method: 'POST',
          body: JSON.stringify({
            corrected_pattern_prompt: correctedPrompt.trim() || undefined,
            intent: patternIntent.trim() || 'ranking',
            operation_kind: patternOperationKind.trim() || undefined,
            metric_hint: patternMetricHint.trim() || undefined,
            failure_category: trace.failure_category || undefined,
            verified_against_pms: true,
            review_notes: reviewNotes.trim() || undefined,
          }),
        },
      );
      setActionBanner({
        kind: 'success',
        text: res?.message || 'Approved pattern verified and saved.',
      });
      setVerifiedAgainstPms(false);
      await loadData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unable to approve pattern.';
      setActionBanner({ kind: 'error', text: msg });
    } finally {
      setSubmittingTraceId(null);
    }
  };

  const handleRemovePattern = async (patternId: string) => {
    setRemovingPatternId(patternId);
    setActionBanner(null);
    try {
      await apiFetch(`/api/ai/feedback/patterns/${encodeURIComponent(patternId)}`, {
        method: 'DELETE',
      });
      setConfirmRemovePatternId(null);
      setPatterns((prev) => prev.filter((p) => p.id !== patternId));
      setActionBanner({ kind: 'success', text: 'Approved pattern removed.' });
    } catch {
      setActionBanner({ kind: 'error', text: 'Failed to remove approved pattern.' });
    } finally {
      setRemovingPatternId(null);
    }
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200/90 bg-white p-5 shadow-xs">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
            <MessageSquareWarning size={20} />
          </div>
          <div>
            <h2 className="text-base font-extrabold text-slate-900">
              AI Feedback &amp; Approved Pattern Learning
            </h2>
            <p className="mt-0.5 text-xs font-medium text-slate-500">
              Inspect redacted feedback clusters, verify answers against live PMS records, and approve sanitized routing patterns.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void loadData()}
          className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-bold text-slate-700 hover:border-blue-400 hover:text-blue-600"
        >
          <RotateCcw size={13} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs">
          <p className="text-xs font-semibold text-slate-500">Total Feedback</p>
          <p className="mt-1 text-2xl font-extrabold tabular-nums text-slate-900">
            {summary.totalFeedback}
          </p>
          <p className="mt-1 text-xs text-slate-500">Matched redacted traces</p>
        </div>
        <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs">
          <p className="text-xs font-semibold text-slate-500">Pending Review</p>
          <p className="mt-1 text-2xl font-extrabold tabular-nums text-amber-600">
            {summary.pendingReview}
          </p>
          <p className="mt-1 text-xs text-slate-500">Awaiting Admin verification</p>
        </div>
        <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs">
          <p className="text-xs font-semibold text-slate-500">Flagged Issues</p>
          <p className="mt-1 text-2xl font-extrabold tabular-nums text-rose-600">
            {summary.flaggedIssues}
          </p>
          <p className="mt-1 text-xs text-slate-500">Wrong data, context, or phrasing</p>
        </div>
        <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs">
          <p className="text-xs font-semibold text-slate-500">Active Approved Patterns</p>
          <p className="mt-1 text-2xl font-extrabold tabular-nums text-emerald-600">
            {summary.activePatterns}
          </p>
          <p className="mt-1 text-xs text-slate-500">PMS-verified router hints</p>
        </div>
      </div>

      {actionBanner && (
        <div
          role={actionBanner.kind === 'error' ? 'alert' : 'status'}
          className={`flex items-center justify-between gap-2 rounded-xl border px-4 py-2.5 text-xs font-semibold ${
            actionBanner.kind === 'error'
              ? 'border-rose-200 bg-rose-50 text-rose-800'
              : 'border-emerald-200 bg-emerald-50 text-emerald-800'
          }`}
        >
          <span>{actionBanner.text}</span>
          <button
            type="button"
            aria-label="Dismiss notification"
            onClick={() => setActionBanner(null)}
            className="rounded p-0.5 hover:bg-black/5"
          >
            <X size={13} />
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs">
        <label className="flex items-center gap-2 text-xs font-bold text-slate-700">
          <span>Surface</span>
          <select
            aria-label="Filter feedback by surface"
            value={surfaceFilter}
            onChange={(e) => setSurfaceFilter(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-800"
          >
            <option value="">All surfaces</option>
            <option value="workspace_chat">Workspace chat</option>
            <option value="corrective_action_pilot">Corrective-action pilot</option>
          </select>
        </label>

        <label className="flex items-center gap-2 text-xs font-bold text-slate-700">
          <span>Rating</span>
          <select
            aria-label="Filter feedback by rating"
            value={ratingFilter}
            onChange={(e) => setRatingFilter(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-800"
          >
            <option value="">All ratings</option>
            <option value="down">Not helpful</option>
            <option value="up">Helpful</option>
          </select>
        </label>

        <label className="flex items-center gap-2 text-xs font-bold text-slate-700">
          <span>Review status</span>
          <select
            aria-label="Filter feedback by review status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-800"
          >
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
        </label>

        {(surfaceFilter || ratingFilter || statusFilter) && (
          <button
            type="button"
            onClick={() => {
              setSurfaceFilter('');
              setRatingFilter('');
              setStatusFilter('');
            }}
            className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-100"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Loading / Error / Empty / Cluster Table + Inspection Pane */}
      {isLoading ? (
        <div className="space-y-3 rounded-2xl border border-slate-200/90 bg-white p-5" aria-label="Loading AI feedback clusters">
          <div className="h-8 w-1/3 animate-pulse rounded-lg bg-slate-100" />
          <div className="h-14 w-full animate-pulse rounded-xl bg-slate-100" />
          <div className="h-14 w-full animate-pulse rounded-xl bg-slate-100" />
        </div>
      ) : loadError ? (
        <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-xs text-rose-800">
          <p className="font-bold">{loadError}</p>
          <button
            type="button"
            onClick={() => void loadData()}
            className="mt-2 inline-flex items-center gap-1 rounded-full border border-rose-300 bg-white px-3 py-1.5 text-xs font-bold text-rose-700 hover:bg-rose-100"
          >
            <RotateCcw size={12} />
            <span>Retry</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_1fr]">
          {/* Clusters Table */}
          <div className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-xs">
            <div className="border-b border-slate-100 px-4 py-3">
              <h3 className="text-sm font-extrabold text-slate-900">
                Feedback Clusters by Intent &amp; Failure Category
              </h3>
            </div>
            {clusters.length === 0 ? (
              <div className="p-6 text-center text-xs font-medium text-slate-500">
                No feedback clusters match the selected filters yet.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left text-xs">
                  <thead className="sticky top-0 bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-4 py-2.5 font-bold">Intent &amp; Team</th>
                      <th className="px-3 py-2.5 font-bold">Category</th>
                      <th className="px-3 py-2.5 font-bold">Sample Prompt</th>
                      <th className="px-3 py-2.5 font-bold text-right">Counts</th>
                      <th className="px-4 py-2.5 font-bold text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {clusters.map((cluster) => {
                      const key = clusterKey(cluster);
                      const isSelected = selectedClusterKey === key;
                      const sample = cluster.traces[0];
                      return (
                        <tr
                          key={key}
                          className={isSelected ? 'bg-blue-50/60' : 'hover:bg-slate-50/80'}
                        >
                          <td className="px-4 py-3 align-top">
                            <p className="font-bold text-slate-900">
                              {cluster.intent || cluster.operation_family}
                            </p>
                            <p className="mt-0.5 text-slate-500">{cluster.scope_team}</p>
                          </td>
                          <td className="px-3 py-3 align-top">
                            <span
                              className={`inline-block rounded-full px-2 py-0.5 text-xs font-bold ${
                                cluster.down_count > 0
                                  ? 'bg-rose-100 text-rose-800'
                                  : 'bg-emerald-100 text-emerald-800'
                              }`}
                            >
                              {formatFailureLabel(cluster.failure_category || cluster.reason_tag)}
                            </span>
                          </td>
                          <td className="max-w-[240px] px-3 py-3 align-top">
                            <p className="line-clamp-2 font-medium text-slate-700">
                              {sample?.prompt_redacted || 'Redacted prompt'}
                            </p>
                            {sample?.tool_choice && (
                              <p className="mt-0.5 text-slate-500">Tool: {sample.tool_choice}</p>
                            )}
                          </td>
                          <td className="px-3 py-3 text-right align-top tabular-nums">
                            <span className="font-extrabold text-slate-900">{cluster.total_count}</span>
                            <p className="text-slate-500">
                              {cluster.pending_count} pending
                            </p>
                          </td>
                          <td className="px-4 py-3 text-right align-top">
                            <button
                              type="button"
                              onClick={() => selectCluster(cluster)}
                              className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-bold text-blue-700 hover:border-blue-400 hover:bg-blue-50"
                            >
                              <Eye size={12} />
                              <span>Inspect</span>
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Cluster & Trace Inspection Detail Pane */}
          <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs">
            <h3 className="text-sm font-extrabold text-slate-900">
              Trace Inspection &amp; Pattern Approval
            </h3>
            {!selectedCluster || !selectedTrace ? (
              <div className="mt-3 rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-6 text-center text-xs font-medium text-slate-500">
                Select a feedback cluster on the left and click <strong>Inspect</strong> to verify against PMS data or approve a pattern.
              </div>
            ) : (
              <div className="mt-3 space-y-4">
                {/* Trace selector if cluster has multiple redacted samples */}
                {selectedCluster.traces.length > 1 && (
                  <div className="flex flex-wrap gap-1.5">
                    {selectedCluster.traces.map((t, idx) => (
                      <button
                        key={t.trace_id}
                        type="button"
                        onClick={() => selectTrace(t)}
                        className={`rounded-full border px-2.5 py-1 text-xs font-bold ${
                          t.trace_id === selectedTrace.trace_id
                            ? 'border-blue-400 bg-blue-50 text-blue-700'
                            : 'border-slate-200 bg-white text-slate-600'
                        }`}
                      >
                        Sample #{idx + 1} ({t.review_status})
                      </button>
                    ))}
                  </div>
                )}

                <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 text-xs space-y-1.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-bold text-slate-900">Redacted Prompt</span>
                    <span className="rounded bg-white px-2 py-0.5 font-bold text-slate-700 border border-slate-200">
                      Status: {selectedTrace.review_status}
                    </span>
                  </div>
                  <p className="font-semibold text-slate-800">{selectedTrace.prompt_redacted}</p>
                  <div className="flex flex-wrap gap-3 text-slate-600">
                    <span>Intent: <strong>{selectedTrace.intent}</strong></span>
                    {selectedTrace.tool_choice && (
                      <span>Tool: <strong>{selectedTrace.tool_choice}</strong></span>
                    )}
                    <span>Tag: <strong>{formatFailureLabel(selectedTrace.failure_category)}</strong></span>
                  </div>
                  {selectedTrace.feedback_reason && (
                    <p className="text-slate-600">
                      User note: <em>{selectedTrace.feedback_reason}</em>
                    </p>
                  )}
                </div>

                {/* Pattern approval form */}
                <div className="space-y-2.5 text-xs">
                  <label className="block">
                    <span className="font-bold text-slate-700">Redacted Pattern Example</span>
                    <input
                      type="text"
                      value={correctedPrompt}
                      onChange={(e) => setCorrectedPrompt(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-900"
                    />
                  </label>

                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <label className="block">
                      <span className="font-bold text-slate-700">Target Intent</span>
                      <select
                        value={patternIntent}
                        onChange={(e) => setPatternIntent(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-900"
                      >
                        {INTENT_OPTIONS.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="block">
                      <span className="font-bold text-slate-700">Metric Hint (optional)</span>
                      <input
                        type="text"
                        value={patternMetricHint}
                        onChange={(e) => setPatternMetricHint(e.target.value)}
                        placeholder="e.g. bookings_count"
                        className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-900"
                      />
                    </label>
                  </div>

                  <label className="block">
                    <span className="font-bold text-slate-700">Review Notes (optional)</span>
                    <input
                      type="text"
                      value={reviewNotes}
                      onChange={(e) => setReviewNotes(e.target.value)}
                      placeholder="Verified against Monthly Presentation"
                      className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-900"
                    />
                  </label>

                  <label className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50/70 p-2.5">
                    <input
                      type="checkbox"
                      checked={verifiedAgainstPms}
                      onChange={(e) => setVerifiedAgainstPms(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-slate-300 text-blue-600"
                    />
                    <span className="text-xs font-semibold text-amber-900">
                      I verified this behavior against live PMS data
                    </span>
                  </label>

                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <button
                      type="button"
                      disabled={!verifiedAgainstPms || submittingTraceId === selectedTrace.trace_id}
                      onClick={() => void handleApprovePattern(selectedTrace)}
                      className="inline-flex items-center gap-1.5 rounded-full bg-blue-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Sparkles size={13} />
                      <span>Approve &amp; save pattern</span>
                    </button>

                    <button
                      type="button"
                      disabled={submittingTraceId === selectedTrace.trace_id}
                      onClick={() => void handleReviewDecision(selectedTrace.trace_id, 'approved')}
                      className="inline-flex items-center gap-1 rounded-full border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
                    >
                      <CheckCircle2 size={13} />
                      <span>Verify only</span>
                    </button>

                    <button
                      type="button"
                      disabled={submittingTraceId === selectedTrace.trace_id}
                      onClick={() => void handleReviewDecision(selectedTrace.trace_id, 'rejected')}
                      className="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-white px-3 py-1.5 text-xs font-bold text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                    >
                      <AlertTriangle size={13} />
                      <span>Reject</span>
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Active Approved Patterns Management */}
      <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs">
        <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <ShieldCheck size={16} className="text-emerald-600" />
            <h3 className="text-sm font-extrabold text-slate-900">
              Active Approved Routing Patterns ({patterns.length})
            </h3>
          </div>
        </div>

        {patterns.length === 0 ? (
          <div className="p-5 text-center text-xs font-medium text-slate-500">
            No approved patterns active yet. Inspect a trace above and verify against live PMS data to save one.
          </div>
        ) : (
          <div className="mt-3 space-y-2">
            {patterns.map((pat) => {
              const isConfirming = confirmRemovePatternId === pat.id;
              return (
                <div
                  key={pat.id}
                  data-testid={`ai-approved-pattern-${pat.id}`}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200/80 bg-slate-50/50 p-3 text-xs"
                >
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded bg-blue-100 px-2 py-0.5 font-bold text-blue-800">
                        {pat.intent}
                      </span>
                      {pat.metric_hint && (
                        <span className="rounded bg-slate-200/80 px-2 py-0.5 font-semibold text-slate-700">
                          Metric: {pat.metric_hint}
                        </span>
                      )}
                      {pat.verified_against_pms && (
                        <span className="rounded bg-emerald-100 px-2 py-0.5 font-bold text-emerald-800">
                          Verified PMS
                        </span>
                      )}
                    </div>
                    <p className="font-semibold text-slate-900">{pat.example_prompt_redacted}</p>
                    <p className="text-slate-500">Normalized: {pat.normalized_pattern}</p>
                  </div>

                  {!isConfirming ? (
                    <button
                      type="button"
                      onClick={() => setConfirmRemovePatternId(pat.id)}
                      className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-bold text-rose-700 hover:border-rose-300 hover:bg-rose-50"
                    >
                      <Trash2 size={12} />
                      <span>Remove</span>
                    </button>
                  ) : (
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        disabled={removingPatternId === pat.id}
                        onClick={() => void handleRemovePattern(pat.id)}
                        className="inline-flex items-center gap-1 rounded-full bg-rose-600 px-3 py-1 text-xs font-bold text-white hover:bg-rose-700 disabled:opacity-50"
                      >
                        <Check size={12} />
                        <span>Confirm remove</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmRemovePatternId(null)}
                        className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-bold text-slate-600 hover:bg-slate-100"
                      >
                        <X size={12} />
                        <span>Cancel</span>
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
