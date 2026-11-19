import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Copy,
  Eye,
  ImagePlus,
  Layers,
  MessageSquareWarning,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  Wand2,
  X,
} from 'lucide-react';
import { apiFetch } from '../../lib/apiClient';
import type {
  AiApprovedPatternItem,
  AiApprovedPatternListResponse,
  AiApprovePatternResponse,
  AiClusterAnalysisResponse,
  AiFeedbackAnalyzerStatusResponse,
  AiFeedbackClusterItem,
  AiFeedbackClustersResponse,
  AiFeedbackTraceSample,
  NemotronFeedbackAnalysisResult,
  NemotronSuggestedPattern,
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

const ROOT_CAUSE_LABELS: Record<string, string> = {
  intent_misclassification: 'Intent misclassification',
  wrong_tool: 'Wrong tool selected',
  missing_kpi_alias: 'Missing KPI alias',
  scope_confusion: 'Scope confusion',
  prompt_ambiguity: 'Prompt ambiguity',
  synthesis_hallucination: 'Synthesis hallucination',
  formatting_issue: 'Formatting issue',
  data_gap: 'Data gap',
};

const MAX_SCREENSHOT_BYTES = 1_500_000;

function formatFailureLabel(code: string): string {
  return FAILURE_BADGE_LABELS[code] || code.replace(/_/g, ' ');
}

function formatRootCauseLabel(code?: string | null): string {
  if (!code) return 'General diagnosis';
  return ROOT_CAUSE_LABELS[code] || code.replace(/_/g, ' ');
}

const CLUSTERS_PAGE_SIZE = 10;

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
  const [page, setPage] = useState<number>(1);

  const [clusters, setClusters] = useState<AiFeedbackClusterItem[]>([]);
  const [totalTraces, setTotalTraces] = useState<number>(0);
  const [totalClusters, setTotalClusters] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [pendingTotal, setPendingTotal] = useState<number | null>(null);
  const [flaggedTotal, setFlaggedTotal] = useState<number | null>(null);
  const [nextPageCached, setNextPageCached] = useState<boolean>(false);
  const [patterns, setPatterns] = useState<AiApprovedPatternItem[]>([]);

  const pageCacheRef = useRef<Map<string, AiFeedbackClustersResponse>>(new Map());
  const inflightRef = useRef<Map<string, Promise<AiFeedbackClustersResponse>>>(new Map());
  const patternsLoadedRef = useRef<boolean>(false);

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

  // Admin AI Root-Cause Analyzer state
  const [analyzerStatus, setAnalyzerStatus] = useState<AiFeedbackAnalyzerStatusResponse | null>(null);
  const statusLoadedRef = useRef<boolean>(false);
  const [traceAnalyses, setTraceAnalyses] = useState<Record<string, NemotronFeedbackAnalysisResult>>({});
  const [analyzingTraceId, setAnalyzingTraceId] = useState<string | null>(null);
  const [traceAnalyzeError, setTraceAnalyzeError] = useState<string | null>(null);

  const [showScreenshotAttach, setShowScreenshotAttach] = useState<boolean>(false);
  const [screenshotDataUrl, setScreenshotDataUrl] = useState<string | null>(null);
  const [screenshotFileName, setScreenshotFileName] = useState<string | null>(null);
  const [screenshotError, setScreenshotError] = useState<string | null>(null);
  const [screenshotPiiAttested, setScreenshotPiiAttested] = useState<boolean>(false);

  const [clusterAnalysis, setClusterAnalysis] = useState<AiClusterAnalysisResponse | null>(null);
  const [analyzingCluster, setAnalyzingCluster] = useState<boolean>(false);
  const [clusterAnalyzeError, setClusterAnalyzeError] = useState<string | null>(null);
  const [copiedClusterBrief, setCopiedClusterBrief] = useState<boolean>(false);

  const fetchAnalyzerStatus = useCallback(async () => {
    try {
      const res = await apiFetch<AiFeedbackAnalyzerStatusResponse>('/api/ai/feedback/analyzer/status');
      if (res && typeof res.enabled === 'boolean' && typeof res.configured === 'boolean') {
        setAnalyzerStatus(res);
      } else {
        setAnalyzerStatus({
          success: true,
          enabled: false,
          configured: false,
          daily_used: 0,
          daily_limit: 50,
        });
      }
    } catch {
      setAnalyzerStatus({
        success: false,
        enabled: false,
        configured: false,
        daily_used: 0,
        daily_limit: 50,
      });
    }
  }, []);

  const buildCacheKey = useCallback(
    (targetPage: number) =>
      `${surfaceFilter}|${ratingFilter}|${statusFilter}|${targetPage}|${CLUSTERS_PAGE_SIZE}`,
    [surfaceFilter, ratingFilter, statusFilter],
  );

  const buildClustersUrl = useCallback(
    (targetPage: number) => {
      const qs = new URLSearchParams();
      if (surfaceFilter) qs.set('surface', surfaceFilter);
      if (ratingFilter) qs.set('rating', ratingFilter);
      if (statusFilter) qs.set('review_status', statusFilter);
      qs.set('page', String(targetPage));
      qs.set('page_size', String(CLUSTERS_PAGE_SIZE));
      return `/api/ai/feedback/clusters?${qs.toString()}`;
    },
    [surfaceFilter, ratingFilter, statusFilter],
  );

  const fetchClusterPage = useCallback(
    async (targetPage: number, forceRefresh = false): Promise<AiFeedbackClustersResponse> => {
      const key = buildCacheKey(targetPage);
      if (!forceRefresh) {
        const cached = pageCacheRef.current.get(key);
        if (cached) return cached;
        const pending = inflightRef.current.get(key);
        if (pending) return pending;
      }
      const req = apiFetch<AiFeedbackClustersResponse>(buildClustersUrl(targetPage))
        .then((res) => {
          pageCacheRef.current.set(key, res);
          inflightRef.current.delete(key);
          return res;
        })
        .catch((err) => {
          inflightRef.current.delete(key);
          throw err;
        });
      inflightRef.current.set(key, req);
      return req;
    },
    [buildCacheKey, buildClustersUrl],
  );

  const applyClusterResponse = useCallback(
    (clusterRes: AiFeedbackClustersResponse, requestedPage: number) => {
      const rawClusters = Array.isArray(clusterRes?.clusters) ? clusterRes.clusters : [];
      const serverPaginated =
        typeof clusterRes?.total_clusters === 'number' && typeof clusterRes?.total_pages === 'number';
      const resolvedTotalClusters = serverPaginated ? clusterRes.total_clusters! : rawClusters.length;
      const resolvedTotalPages = serverPaginated
        ? Math.max(1, clusterRes.total_pages!)
        : Math.max(1, Math.ceil(rawClusters.length / CLUSTERS_PAGE_SIZE));
      const visibleClusters = serverPaginated
        ? rawClusters
        : rawClusters.slice(
            (requestedPage - 1) * CLUSTERS_PAGE_SIZE,
            requestedPage * CLUSTERS_PAGE_SIZE,
          );

      setClusters(visibleClusters);
      setTotalTraces(Number(clusterRes?.total_traces ?? 0));
      setTotalClusters(resolvedTotalClusters);
      setTotalPages(resolvedTotalPages);
      setPendingTotal(typeof clusterRes?.pending_total === 'number' ? clusterRes.pending_total : null);
      setFlaggedTotal(typeof clusterRes?.flagged_total === 'number' ? clusterRes.flagged_total : null);

      // Always prefetch & cache the next 10 clusters in background for instant navigation
      const nextPage = requestedPage + 1;
      const hasNext =
        typeof clusterRes?.has_next === 'boolean'
          ? clusterRes.has_next
          : requestedPage < resolvedTotalPages;
      if (hasNext) {
        const nextKey = buildCacheKey(nextPage);
        if (pageCacheRef.current.has(nextKey)) {
          setNextPageCached(true);
        } else {
          setNextPageCached(false);
          void fetchClusterPage(nextPage)
            .then(() => {
              setNextPageCached(true);
            })
            .catch(() => {
              // Silent background prefetch failure — user can still load on click
            });
        }
      } else {
        setNextPageCached(false);
      }
    },
    [buildCacheKey, fetchClusterPage],
  );

  const loadData = useCallback(
    async (opts?: { forceRefresh?: boolean; targetPage?: number }) => {
      const targetPage = opts?.targetPage ?? page;
      const forceRefresh = Boolean(opts?.forceRefresh);
      if (forceRefresh) {
        pageCacheRef.current.clear();
        inflightRef.current.clear();
        patternsLoadedRef.current = false;
      }

      const cachedPage = !forceRefresh ? pageCacheRef.current.get(buildCacheKey(targetPage)) : undefined;
      if (cachedPage && patternsLoadedRef.current) {
        // Instant zero-flicker transition from prefetched cache
        setLoadError(null);
        setIsLoading(false);
        applyClusterResponse(cachedPage, targetPage);
        return;
      }

      setIsLoading(true);
      setLoadError(null);
      try {
        const [clusterRes, patternRes] = await Promise.all([
          fetchClusterPage(targetPage, forceRefresh),
          patternsLoadedRef.current && !forceRefresh
            ? Promise.resolve(null)
            : apiFetch<AiApprovedPatternListResponse>('/api/ai/feedback/patterns'),
        ]);
        applyClusterResponse(clusterRes, targetPage);
        if (patternRes !== null) {
          setPatterns(Array.isArray(patternRes?.patterns) ? patternRes.patterns : []);
          patternsLoadedRef.current = true;
        }
        if (!statusLoadedRef.current || forceRefresh) {
          statusLoadedRef.current = true;
          void fetchAnalyzerStatus();
        }
      } catch {
        setLoadError('Unable to load AI feedback clusters and approved patterns.');
      } finally {
        setIsLoading(false);
      }
    },
    [applyClusterResponse, buildCacheKey, fetchAnalyzerStatus, fetchClusterPage, page],
  );

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadData({ targetPage: page });
    }, 0);
    return () => clearTimeout(timer);
  }, [loadData, page]);

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

  const resetScreenshotState = () => {
    setShowScreenshotAttach(false);
    setScreenshotDataUrl(null);
    setScreenshotFileName(null);
    setScreenshotError(null);
    setScreenshotPiiAttested(false);
  };

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
    setTraceAnalyzeError(null);
    setClusterAnalysis(null);
    setClusterAnalyzeError(null);
    setCopiedClusterBrief(false);
    resetScreenshotState();
  };

  const selectTrace = (trace: AiFeedbackTraceSample) => {
    setSelectedTraceId(trace.trace_id);
    setVerifiedAgainstPms(false);
    setPatternIntent(trace.intent || 'ranking');
    setPatternOperationKind(trace.operation_kind || '');
    setCorrectedPrompt(trace.prompt_redacted || '');
    setReviewNotes('');
    setActionBanner(null);
    setTraceAnalyzeError(null);
    resetScreenshotState();
  };

  const analyzerReady = Boolean(analyzerStatus?.enabled && analyzerStatus?.configured);
  const currentTraceAnalysis = selectedTrace ? traceAnalyses[selectedTrace.trace_id] ?? null : null;

  const handleScreenshotFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setScreenshotError(null);
    setScreenshotPiiAttested(false);
    const file = e.target.files?.[0];
    if (!file) {
      setScreenshotDataUrl(null);
      setScreenshotFileName(null);
      return;
    }
    const allowedTypes = new Set(['image/png', 'image/jpeg', 'image/webp']);
    if (!allowedTypes.has(file.type)) {
      setScreenshotError('Only PNG, JPEG, or WEBP screenshots are supported.');
      setScreenshotDataUrl(null);
      setScreenshotFileName(null);
      return;
    }
    if (file.size > MAX_SCREENSHOT_BYTES) {
      setScreenshotError('Screenshot must be 1.5 MB or smaller.');
      setScreenshotDataUrl(null);
      setScreenshotFileName(null);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : null;
      if (result && result.startsWith('data:image/')) {
        setScreenshotDataUrl(result);
        setScreenshotFileName(file.name);
      } else {
        setScreenshotError('Could not read the selected image file.');
      }
    };
    reader.onerror = () => {
      setScreenshotError('Could not read the selected image file.');
    };
    reader.readAsDataURL(file);
  };

  const handleAnalyzeTrace = async (trace: AiFeedbackTraceSample, forceRefresh = false) => {
    if (screenshotDataUrl && !screenshotPiiAttested) {
      setTraceAnalyzeError('Confirm the screenshot is free of personal data before analyzing.');
      return;
    }
    setAnalyzingTraceId(trace.trace_id);
    setTraceAnalyzeError(null);
    try {
      const res = await apiFetch<NemotronFeedbackAnalysisResult>(
        `/api/ai/traces/${encodeURIComponent(trace.trace_id)}/analyze`,
        {
          method: 'POST',
          body: JSON.stringify({
            force_refresh: forceRefresh,
            screenshot_data_url: screenshotDataUrl || undefined,
            screenshot_pii_free_attested: Boolean(screenshotDataUrl && screenshotPiiAttested),
          }),
        },
      );
      setTraceAnalyses((prev) => ({ ...prev, [trace.trace_id]: res }));
      if (!res.cached && res.outcome === 'analyzed') {
        void fetchAnalyzerStatus();
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unable to analyze feedback trace right now.';
      setTraceAnalyzeError(msg);
    } finally {
      setAnalyzingTraceId(null);
    }
  };

  const handleAnalyzeCluster = async (cluster: AiFeedbackClusterItem) => {
    setAnalyzingCluster(true);
    setClusterAnalyzeError(null);
    setCopiedClusterBrief(false);
    try {
      const res = await apiFetch<AiClusterAnalysisResponse>('/api/ai/feedback/clusters/analyze', {
        method: 'POST',
        body: JSON.stringify({
          surface: cluster.surface || undefined,
          operation_family: cluster.operation_family || undefined,
          scope_team: cluster.scope_team !== 'unspecified' ? cluster.scope_team : undefined,
          reason_tag: cluster.reason_tag !== 'unspecified' ? cluster.reason_tag : undefined,
          rating: ratingFilter || undefined,
          review_status: statusFilter || undefined,
        }),
      });
      setClusterAnalysis(res);
      if (res.outcome === 'analyzed') {
        void fetchAnalyzerStatus();
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unable to summarize this feedback cluster right now.';
      setClusterAnalyzeError(msg);
    } finally {
      setAnalyzingCluster(false);
    }
  };

  const applySuggestedPattern = (
    suggestion: NemotronSuggestedPattern,
    summaryNote?: string | null,
  ) => {
    setCorrectedPrompt(suggestion.corrected_pattern_prompt);
    if ((INTENT_OPTIONS as readonly string[]).includes(suggestion.intent)) {
      setPatternIntent(suggestion.intent);
    }
    setPatternOperationKind(suggestion.operation_kind || '');
    setPatternMetricHint(suggestion.metric_hint || '');
    if (summaryNote) {
      setReviewNotes(summaryNote.slice(0, 220));
    }
    // Never auto-verify: Admin must still verify against live PMS records.
    setVerifiedAgainstPms(false);
    setActionBanner({
      kind: 'success',
      text: 'Suggested pattern applied to the form. Verify against live PMS data before saving.',
    });
  };

  const handleCopyClusterBrief = async (analysis: AiClusterAnalysisResponse) => {
    const lines = [
      `# Feedback Cluster Diagnosis`,
      analysis.primary_root_cause ? `Primary Root Cause: ${formatRootCauseLabel(analysis.primary_root_cause)}` : '',
      analysis.executive_summary ? `\nSummary: ${analysis.executive_summary}` : '',
      analysis.recurring_issues.length
        ? `\nRecurring Issues:\n${analysis.recurring_issues.map((i) => `- ${i}`).join('\n')}`
        : '',
      analysis.recommended_engineering_fixes.length
        ? `\nRecommended Engineering Fixes:\n${analysis.recommended_engineering_fixes.map((f) => `- ${f}`).join('\n')}`
        : '',
    ].filter(Boolean);
    try {
      await navigator.clipboard.writeText(lines.join('\n'));
      setCopiedClusterBrief(true);
      setTimeout(() => setCopiedClusterBrief(false), 2000);
    } catch {
      setActionBanner({ kind: 'error', text: 'Could not copy fix brief to clipboard.' });
    }
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
      pendingReview: pendingTotal ?? pending,
      flaggedIssues: flaggedTotal ?? flagged,
      activePatterns: patterns.length,
    };
  }, [clusters, totalTraces, pendingTotal, flaggedTotal, patterns.length]);

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
      await loadData({ forceRefresh: true });
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
      await loadData({ forceRefresh: true });
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
          onClick={() => void loadData({ forceRefresh: true })}
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
            onChange={(e) => {
              setSurfaceFilter(e.target.value);
              setPage(1);
            }}
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
            onChange={(e) => {
              setRatingFilter(e.target.value);
              setPage(1);
            }}
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
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
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
              setPage(1);
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
            onClick={() => void loadData({ forceRefresh: true })}
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
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
              <h3 className="text-sm font-extrabold text-slate-900">
                Feedback Clusters by Intent &amp; Failure Category
              </h3>
              {totalClusters > 0 && (
                <span className="text-xs font-semibold tabular-nums text-slate-500">
                  Showing {(page - 1) * CLUSTERS_PAGE_SIZE + 1}–{Math.min(page * CLUSTERS_PAGE_SIZE, totalClusters)} of {totalClusters}
                </span>
              )}
            </div>
            {clusters.length === 0 ? (
              <div className="p-6 text-center text-xs font-medium text-slate-500">
                No feedback clusters match the selected filters yet.
              </div>
            ) : (
              <>
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
                          <td className="max-w-[190px] px-4 py-3 align-top">
                            <p className="break-words font-bold text-slate-900">
                              {cluster.intent || cluster.operation_family}
                            </p>
                            <p className="mt-0.5 truncate text-slate-500">{cluster.scope_team}</p>
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
                              <p className="mt-0.5 truncate text-slate-500">Tool: {sample.tool_choice}</p>
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
              {totalPages > 1 && (
                <div
                  data-testid="feedback-clusters-pagination"
                  className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 bg-slate-50/60 px-4 py-2.5 text-xs"
                >
                  <div className="flex items-center gap-2 text-slate-500">
                    <span className="font-semibold tabular-nums">
                      Page {page} of {totalPages}
                    </span>
                    {nextPageCached && page < totalPages && (
                      <span
                        data-testid="next-page-cached-badge"
                        className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700"
                      >
                        Next 10 ready
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-bold text-slate-700 hover:border-blue-400 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <ChevronLeft size={13} />
                      <span>Prev 10</span>
                    </button>
                    <button
                      type="button"
                      disabled={page >= totalPages}
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-bold text-slate-700 hover:border-blue-400 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <span>Next 10</span>
                      <ChevronRight size={13} />
                    </button>
                  </div>
                </div>
              )}
              </>
            )}
          </div>

          {/* Cluster & Trace Inspection Detail Pane */}
          <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-extrabold text-slate-900">
                Trace Inspection &amp; Pattern Approval
              </h3>
              {analyzerStatus && (
                <span
                  data-testid="analyzer-status-pill"
                  className={`rounded-full px-2.5 py-0.5 text-xs font-semibold tabular-nums ${
                    analyzerReady
                      ? 'bg-blue-50 text-blue-700'
                      : 'bg-slate-100 text-slate-500'
                  }`}
                >
                  {analyzerReady
                    ? `AI Diagnosis: ${analyzerStatus.daily_used} / ${analyzerStatus.daily_limit} today`
                    : 'AI Diagnosis offline'}
                </span>
              )}
            </div>
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

                {/* AI Root-Cause Diagnosis Action Bar */}
                <div className="space-y-2.5 rounded-xl border border-slate-200/90 bg-slate-50/40 p-3 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        disabled={
                          !analyzerReady ||
                          analyzingTraceId === selectedTrace.trace_id ||
                          Boolean(screenshotDataUrl && !screenshotPiiAttested)
                        }
                        onClick={() => void handleAnalyzeTrace(selectedTrace, false)}
                        className="inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-3 py-1.5 text-xs font-bold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <Wand2 size={12} />
                        <span>
                          {analyzingTraceId === selectedTrace.trace_id
                            ? 'Analyzing...'
                            : 'Analyze Root Cause'}
                        </span>
                      </button>

                      {currentTraceAnalysis?.outcome === 'analyzed' && (
                        <button
                          type="button"
                          disabled={
                            !analyzerReady ||
                            analyzingTraceId === selectedTrace.trace_id ||
                            Boolean(screenshotDataUrl && !screenshotPiiAttested)
                          }
                          onClick={() => void handleAnalyzeTrace(selectedTrace, true)}
                          className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-bold text-slate-700 hover:border-blue-400 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          <RotateCcw size={12} />
                          <span>Re-analyze</span>
                        </button>
                      )}

                      <button
                        type="button"
                        disabled={!analyzerReady || analyzingCluster}
                        onClick={() => void handleAnalyzeCluster(selectedCluster)}
                        className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 hover:border-blue-400 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <Layers size={12} />
                        <span>{analyzingCluster ? 'Summarizing...' : 'Summarize Cluster'}</span>
                      </button>
                    </div>

                    {analyzerReady && (
                      <button
                        type="button"
                        onClick={() => setShowScreenshotAttach((prev) => !prev)}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-slate-600 hover:text-blue-700"
                      >
                        <ImagePlus size={13} />
                        <span>
                          {showScreenshotAttach
                            ? 'Hide screenshot'
                            : 'Attach redacted screenshot (optional)'}
                        </span>
                      </button>
                    )}
                  </div>

                  {analyzerStatus && !analyzerReady && (
                    <p className="text-xs text-slate-500">
                      AI feedback diagnosis is disabled on this server. Configure{' '}
                      <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs text-slate-700">
                        PMS_AI_FEEDBACK_ANALYZER_ENABLED=true
                      </code>{' '}
                      and{' '}
                      <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs text-slate-700">
                        NVIDIA_API_KEY
                      </code>{' '}
                      to enable on-demand diagnosis.
                    </p>
                  )}

                  {/* Optional Redacted Screenshot Uploader */}
                  {analyzerReady && showScreenshotAttach && (
                    <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-2.5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <label className="text-xs font-bold text-slate-700">
                          Redacted UI screenshot (PNG/JPEG/WEBP, max 1.5 MB)
                          <input
                            type="file"
                            accept="image/png,image/jpeg,image/webp"
                            onChange={handleScreenshotFileChange}
                            className="mt-1 block w-full text-xs text-slate-600 file:mr-2 file:rounded-full file:border-0 file:bg-slate-100 file:px-2.5 file:py-1 file:text-xs file:font-bold file:text-slate-700 hover:file:bg-slate-200"
                          />
                        </label>
                        {screenshotDataUrl && (
                          <button
                            type="button"
                            onClick={resetScreenshotState}
                            className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-2 py-0.5 text-xs font-semibold text-slate-600 hover:bg-slate-100"
                          >
                            <X size={11} />
                            <span>Remove</span>
                          </button>
                        )}
                      </div>
                      {screenshotFileName && (
                        <p className="text-xs font-medium text-slate-600">
                          Attached: <strong>{screenshotFileName}</strong>
                        </p>
                      )}
                      {screenshotError && (
                        <p role="alert" className="text-xs font-semibold text-rose-700">
                          {screenshotError}
                        </p>
                      )}
                      {screenshotDataUrl && (
                        <label className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50/70 p-2">
                          <input
                            type="checkbox"
                            checked={screenshotPiiAttested}
                            onChange={(e) => setScreenshotPiiAttested(e.target.checked)}
                            className="mt-0.5 h-4 w-4 rounded border-slate-300 text-blue-600"
                          />
                          <span className="text-xs font-semibold text-amber-900">
                            I confirm no employee names, IDs, or personal data appear in this screenshot
                          </span>
                        </label>
                      )}
                    </div>
                  )}

                  {/* Trace Diagnosis Loading Skeleton */}
                  {analyzingTraceId === selectedTrace.trace_id && (
                    <div
                      aria-label="Analyzing feedback root cause"
                      className="space-y-2 rounded-xl border border-slate-200 bg-white p-3"
                    >
                      <div className="h-4 w-1/3 animate-pulse rounded bg-slate-100" />
                      <div className="h-3 w-full animate-pulse rounded bg-slate-100" />
                      <div className="h-3 w-5/6 animate-pulse rounded bg-slate-100" />
                    </div>
                  )}

                  {/* Trace Diagnosis Error */}
                  {traceAnalyzeError && analyzingTraceId !== selectedTrace.trace_id && (
                    <div
                      role="alert"
                      className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800"
                    >
                      <span className="font-semibold">{traceAnalyzeError}</span>
                      <button
                        type="button"
                        onClick={() => void handleAnalyzeTrace(selectedTrace, false)}
                        className="inline-flex items-center gap-1 rounded-full border border-rose-300 bg-white px-2.5 py-1 text-xs font-bold text-rose-700 hover:bg-rose-100"
                      >
                        <RotateCcw size={11} />
                        <span>Retry</span>
                      </button>
                    </div>
                  )}

                  {/* Trace Diagnosis Result */}
                  {currentTraceAnalysis && analyzingTraceId !== selectedTrace.trace_id && (
                    <div data-testid="trace-diagnosis-card">
                      {currentTraceAnalysis.outcome === 'blocked_pii_quarantine' ? (
                        <div
                          role="alert"
                          className="space-y-1.5 rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900"
                        >
                          <div className="flex items-center gap-1.5 font-bold">
                            <ShieldAlert size={14} className="text-amber-700" />
                            <span>Blocked by privacy quarantine — no data left PMS</span>
                          </div>
                          <p>
                            {currentTraceAnalysis.message ||
                              'Residual personal or sensitive identifiers were detected in this trace.'}
                          </p>
                          {currentTraceAnalysis.quarantine_reasons.length > 0 && (
                            <p className="font-mono text-xs text-amber-800">
                              Flags: {currentTraceAnalysis.quarantine_reasons.join(', ')}
                            </p>
                          )}
                        </div>
                      ) : currentTraceAnalysis.outcome !== 'analyzed' ? (
                        <div
                          role="alert"
                          className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs font-semibold text-amber-900"
                        >
                          {currentTraceAnalysis.message ||
                            'Diagnosis could not be completed right now.'}
                        </div>
                      ) : (
                        <div className="space-y-2.5 rounded-xl border border-blue-200/80 bg-white p-3.5 text-xs">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-bold text-blue-800">
                                {formatRootCauseLabel(currentTraceAnalysis.root_cause_category)}
                              </span>
                              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold tabular-nums text-slate-700">
                                {Math.round((currentTraceAnalysis.confidence || 0) * 100)}% confidence
                              </span>
                              {currentTraceAnalysis.cached && (
                                <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                                  Cached
                                </span>
                              )}
                            </div>
                          </div>

                          {currentTraceAnalysis.root_cause_summary && (
                            <p className="font-semibold text-slate-800">
                              {currentTraceAnalysis.root_cause_summary}
                            </p>
                          )}

                          {currentTraceAnalysis.why_answer_failed.length > 0 && (
                            <div className="space-y-1">
                              <p className="font-bold text-slate-700">Why the answer missed</p>
                              <ul className="list-disc space-y-0.5 pl-4 text-slate-600">
                                {currentTraceAnalysis.why_answer_failed.map((reason, idx) => (
                                  <li key={idx}>{reason}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {currentTraceAnalysis.recommended_system_fix && (
                            <div className="rounded-lg border border-slate-200 bg-slate-50 p-2.5">
                              <p className="font-bold text-slate-700">Recommended system fix</p>
                              <p className="mt-0.5 text-slate-700">
                                {currentTraceAnalysis.recommended_system_fix}
                              </p>
                            </div>
                          )}

                          {currentTraceAnalysis.suggested_pattern && (
                            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-blue-100 bg-blue-50/60 p-2.5">
                              <div className="min-w-0 flex-1 space-y-0.5">
                                <p className="font-bold text-blue-900">
                                  Suggested routing pattern ({currentTraceAnalysis.suggested_pattern.intent})
                                </p>
                                <p className="truncate text-blue-800">
                                  {currentTraceAnalysis.suggested_pattern.corrected_pattern_prompt}
                                </p>
                              </div>
                              <button
                                type="button"
                                onClick={() =>
                                  applySuggestedPattern(
                                    currentTraceAnalysis.suggested_pattern!,
                                    currentTraceAnalysis.root_cause_summary,
                                  )
                                }
                                className="inline-flex shrink-0 items-center gap-1 rounded-full bg-blue-600 px-3 py-1 text-xs font-bold text-white hover:bg-blue-700"
                              >
                                <Sparkles size={12} />
                                <span>Apply suggestion to form</span>
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Cluster Summary Loading Skeleton */}
                  {analyzingCluster && (
                    <div
                      aria-label="Summarizing feedback cluster"
                      className="space-y-2 rounded-xl border border-slate-200 bg-white p-3"
                    >
                      <div className="h-4 w-2/5 animate-pulse rounded bg-slate-100" />
                      <div className="h-3 w-full animate-pulse rounded bg-slate-100" />
                      <div className="h-3 w-3/4 animate-pulse rounded bg-slate-100" />
                    </div>
                  )}

                  {/* Cluster Summary Error */}
                  {clusterAnalyzeError && !analyzingCluster && (
                    <div
                      role="alert"
                      className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800"
                    >
                      <span className="font-semibold">{clusterAnalyzeError}</span>
                      <button
                        type="button"
                        onClick={() => void handleAnalyzeCluster(selectedCluster)}
                        className="inline-flex items-center gap-1 rounded-full border border-rose-300 bg-white px-2.5 py-1 text-xs font-bold text-rose-700 hover:bg-rose-100"
                      >
                        <RotateCcw size={11} />
                        <span>Retry</span>
                      </button>
                    </div>
                  )}

                  {/* Cluster Summary Result */}
                  {clusterAnalysis && !analyzingCluster && (
                    <div data-testid="cluster-diagnosis-card">
                      {clusterAnalysis.outcome !== 'analyzed' ? (
                        <div
                          role="alert"
                          className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs font-semibold text-amber-900"
                        >
                          {clusterAnalysis.message ||
                            'Cluster diagnosis could not be completed right now.'}
                        </div>
                      ) : (
                        <div className="space-y-2.5 rounded-xl border border-emerald-200/80 bg-white p-3.5 text-xs">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="font-extrabold text-slate-900">Cluster Diagnosis</span>
                              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-800">
                                {formatRootCauseLabel(clusterAnalysis.primary_root_cause)}
                              </span>
                              <span className="text-xs font-semibold text-slate-500">
                                {clusterAnalysis.traces_analyzed} traces analyzed
                              </span>
                            </div>
                            <button
                              type="button"
                              onClick={() => void handleCopyClusterBrief(clusterAnalysis)}
                              className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-bold text-slate-700 hover:border-blue-400 hover:text-blue-700"
                            >
                              {copiedClusterBrief ? <Check size={11} /> : <Copy size={11} />}
                              <span>{copiedClusterBrief ? 'Copied' : 'Copy Fix Brief'}</span>
                            </button>
                          </div>

                          {clusterAnalysis.executive_summary && (
                            <p className="font-semibold text-slate-800">
                              {clusterAnalysis.executive_summary}
                            </p>
                          )}

                          {clusterAnalysis.recurring_issues.length > 0 && (
                            <div className="space-y-1">
                              <p className="font-bold text-slate-700">Recurring issues</p>
                              <ul className="list-disc space-y-0.5 pl-4 text-slate-600">
                                {clusterAnalysis.recurring_issues.map((issue, idx) => (
                                  <li key={idx}>{issue}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {clusterAnalysis.recommended_engineering_fixes.length > 0 && (
                            <div className="space-y-1">
                              <p className="font-bold text-slate-700">Recommended engineering fixes</p>
                              <ul className="list-disc space-y-0.5 pl-4 text-slate-600">
                                {clusterAnalysis.recommended_engineering_fixes.map((fix, idx) => (
                                  <li key={idx}>{fix}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {clusterAnalysis.suggested_pattern && (
                            <div className="pt-1">
                              <button
                                type="button"
                                onClick={() =>
                                  applySuggestedPattern(
                                    clusterAnalysis.suggested_pattern!,
                                    clusterAnalysis.executive_summary,
                                  )
                                }
                                className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-bold text-blue-700 hover:bg-blue-100"
                              >
                                <Sparkles size={12} />
                                <span>Apply cluster pattern</span>
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
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
